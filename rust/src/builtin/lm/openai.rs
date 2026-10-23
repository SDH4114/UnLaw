//! OpenAI-compatible endpoints, the same surface LM Studio exposes plus
//! images, speech and video, so any OpenAI SDK works with
//! `base_url = http://127.0.0.1:<port>/v1`.

use std::collections::HashMap;
use std::fs;
use std::io::{self, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::sync::{Arc, Mutex, OnceLock, PoisonError};
use std::thread;
use std::time::Instant;

use serde_json::{json, Map, Value};

use super::engine::engine_dir;
use super::http::{self, Request};
use super::media;
use super::server::{client_gone, log_request, now, parse_body, send_error};
use super::service::{Purpose, Service};
use super::worker::Failure;

pub fn random_id(prefix: &str) -> String {
    let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    format!("{prefix}-{:x}{:x}", nanos, std::process::id())
}

pub fn models(service: &Service, stream: &mut TcpStream) -> io::Result<()> {
    let data: Vec<Value> = service
        .models()
        .into_iter()
        .filter(|m| m.kind.runnable() && !m.partial)
        .map(|m| {
            let owner = m.id.split('/').next().unwrap_or("local").to_string();
            json!({"id": m.id, "object": "model", "created": 0, "owned_by": owner, "type": m.kind.name()})
        })
        .collect();
    http::respond_json(stream, 200, &json!({"object": "list", "data": data}))
}

/// Split OpenAI content (a string or typed parts) into text and image sources.
pub fn content_parts(content: &Value) -> (String, Vec<String>) {
    match content {
        Value::String(text) => (text.clone(), Vec::new()),
        Value::Array(parts) => {
            let mut texts = Vec::new();
            let mut images = Vec::new();
            for part in parts {
                match part["type"].as_str().unwrap_or("") {
                    "text" | "input_text" => texts.push(part["text"].as_str().unwrap_or("").to_string()),
                    "image_url" | "input_image" => {
                        let url = part["image_url"]["url"].as_str().or(part["image_url"].as_str()).or(part["url"].as_str());
                        if let Some(url) = url {
                            images.push(url.to_string());
                        }
                    }
                    _ => {}
                }
            }
            (texts.join("\n"), images)
        }
        Value::Null => (String::new(), Vec::new()),
        other => (other.to_string(), Vec::new()),
    }
}

/// Messages for the chat template: plain text content, images on the side,
/// tool-call arguments as objects (what HF templates expect).
pub fn normalize_messages(messages: &Value) -> Result<Vec<Value>, Failure> {
    let list = messages.as_array().ok_or_else(|| Failure::new("invalid_request", "messages must be an array"))?;
    if list.is_empty() {
        return Err(Failure::new("invalid_request", "messages must not be empty"));
    }
    let mut out = Vec::new();
    for message in list {
        let role = message["role"].as_str().ok_or_else(|| Failure::new("invalid_request", "every message needs a role"))?;
        let role = if role == "developer" { "system" } else { role };
        let (text, images) = content_parts(&message["content"]);
        let mut normalized = Map::new();
        normalized.insert("role".into(), json!(role));
        normalized.insert("content".into(), json!(text));
        if !images.is_empty() {
            normalized.insert("images".into(), json!(images));
        }
        for key in ["name", "tool_call_id"] {
            if let Some(value) = message.get(key).filter(|v| !v.is_null()) {
                normalized.insert(key.into(), value.clone());
            }
        }
        if let Some(calls) = message["tool_calls"].as_array() {
            let calls: Vec<Value> = calls
                .iter()
                .map(|call| {
                    let mut call = call.clone();
                    if let Some(arguments) = call["function"]["arguments"].as_str() {
                        if let Ok(parsed) = serde_json::from_str::<Value>(arguments) {
                            call["function"]["arguments"] = parsed;
                        }
                    }
                    call
                })
                .collect();
            normalized.insert("tool_calls".into(), json!(calls));
        }
        out.push(Value::Object(normalized));
    }
    Ok(out)
}

fn stops(value: &Value) -> Vec<Value> {
    match value {
        Value::String(text) => vec![json!(text)],
        Value::Array(items) => items.iter().filter(|item| item.is_string()).cloned().collect(),
        _ => Vec::new(),
    }
}

/// Only what the request sets; the worker fills the rest from the model's
/// generation_config.json, then from lm.* settings.
pub fn params(body: &Value) -> Value {
    json!({
        "temperature": body["temperature"].as_f64(),
        "top_p": body["top_p"].as_f64(),
        "top_k": body["top_k"].as_i64(),
        "min_p": body["min_p"].as_f64(),
        "max_tokens": body["max_completion_tokens"].as_i64().or(body["max_tokens"].as_i64()).filter(|n| *n > 0),
        "stop": stops(&body["stop"]),
        "seed": body["seed"].as_i64(),
        "presence_penalty": body["presence_penalty"].as_f64().filter(|v| *v != 0.0),
        "frequency_penalty": body["frequency_penalty"].as_f64().filter(|v| *v != 0.0),
        "repetition_penalty": body["repetition_penalty"].as_f64(),
    })
}

fn finish_reason(done: &Value) -> &str {
    match done["finish_reason"].as_str() {
        Some("length") => "length",
        Some("tool_calls") => "tool_calls",
        _ => "stop",
    }
}

fn usage(done: &Value) -> Value {
    let prompt = done["usage"]["prompt_tokens"].as_u64().unwrap_or(0);
    let completion = done["usage"]["completion_tokens"].as_u64().unwrap_or(0);
    json!({"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion})
}

/// `/v1/chat/completions` and, with `legacy`, `/v1/completions`.
pub fn chat(service: &Service, request: &Request, stream: &mut TcpStream, legacy: bool) -> io::Result<()> {
    let started = Instant::now();
    let prepared = (|| {
        let body = parse_body(request)?;
        let model = service.resolve(body["model"].as_str(), Purpose::Chat)?;
        let mut job = json!({"op": if legacy { "complete" } else { "chat" }, "params": params(&body)});
        if legacy {
            let prompt = match &body["prompt"] {
                Value::String(text) => text.clone(),
                Value::Array(items) if items.len() == 1 && items[0].is_string() => items[0].as_str().unwrap_or("").to_string(),
                _ => return Err(Failure::new("invalid_request", "prompt must be a string")),
            };
            job["prompt"] = json!(prompt);
        } else {
            job["messages"] = json!(normalize_messages(&body["messages"])?);
            if body["tools"].as_array().is_some_and(|tools| !tools.is_empty()) {
                job["tools"] = body["tools"].clone();
            }
            // LM Studio / vLLM style switches for reasoning models.
            let think = body["chat_template_kwargs"]["enable_thinking"].as_bool().or(body["enable_thinking"].as_bool());
            if let Some(think) = think {
                job["think"] = json!(think);
            } else if body["reasoning_effort"].as_str() == Some("none") {
                job["think"] = json!(false);
            }
        }
        Ok((body, model, job))
    })();
    let (body, model, job) = match prepared {
        Ok(prepared) => prepared,
        Err(failure) => return send_error(stream, &failure),
    };
    let id = random_id(if legacy { "cmpl" } else { "chatcmpl" });
    let created = now();
    let object = if legacy { "text_completion" } else { "chat.completion" };

    if !body["stream"].as_bool().unwrap_or(false) {
        let watch = stream.try_clone()?;
        return match service.run(job, &model, |event| event["event"] != "tick" || !client_gone(&watch)) {
            Ok(done) => {
                log_request("POST", &request.path, &model.id, &done, started);
                let choice = if legacy {
                    json!({"index": 0, "text": done["text"], "finish_reason": finish_reason(&done), "logprobs": null})
                } else {
                    let mut message = json!({"role": "assistant", "content": done["text"]});
                    if done["reasoning"].as_str().is_some_and(|r| !r.is_empty()) {
                        message["reasoning_content"] = done["reasoning"].clone();
                    }
                    if done["tool_calls"].as_array().is_some_and(|calls| !calls.is_empty()) {
                        message["tool_calls"] = done["tool_calls"].clone();
                        if done["text"].as_str().is_some_and(|text| text.trim().is_empty()) {
                            message["content"] = Value::Null;
                        }
                    }
                    json!({"index": 0, "message": message, "finish_reason": finish_reason(&done), "logprobs": null})
                };
                http::respond_json(
                    stream,
                    200,
                    &json!({"id": id, "object": object, "created": created, "model": model.id, "choices": [choice], "usage": usage(&done)}),
                )
            }
            Err(failure) => send_error(stream, &failure),
        };
    }

    http::start_stream(stream, "text/event-stream")?;
    let chunk_object = if legacy { "text_completion" } else { "chat.completion.chunk" };
    let chunk = |choice: Value| json!({"id": id, "object": chunk_object, "created": created, "model": model.id, "choices": [choice]});
    let mut writer = stream.try_clone()?;
    let watch = stream.try_clone()?;
    let mut send = |value: &Value| -> bool { write!(writer, "data: {value}\n\n").and_then(|_| writer.flush()).is_ok() };
    if !legacy && !send(&chunk(json!({"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": null}))) {
        return Ok(());
    }
    let result = service.run(job, &model, |event| {
        if event["event"] == "tick" {
            return !client_gone(&watch);
        }
        let Some(text) = event["text"].as_str() else { return true };
        let delta = if legacy {
            json!({"index": 0, "text": text, "finish_reason": null})
        } else if event["channel"] == "reasoning" {
            json!({"index": 0, "delta": {"reasoning_content": text}, "finish_reason": null})
        } else {
            json!({"index": 0, "delta": {"content": text}, "finish_reason": null})
        };
        send(&chunk(delta))
    });
    match result {
        Ok(done) => {
            log_request("POST", &request.path, &model.id, &done, started);
            let mut last = if legacy {
                json!({"index": 0, "text": "", "finish_reason": finish_reason(&done)})
            } else {
                json!({"index": 0, "delta": {}, "finish_reason": finish_reason(&done)})
            };
            if let Some(calls) = done["tool_calls"].as_array().filter(|calls| !calls.is_empty()) {
                let indexed: Vec<Value> = calls
                    .iter()
                    .enumerate()
                    .map(|(index, call)| {
                        let mut call = call.clone();
                        call["index"] = json!(index);
                        call
                    })
                    .collect();
                last["delta"]["tool_calls"] = json!(indexed);
            }
            send(&chunk(last));
            if body["stream_options"]["include_usage"].as_bool().unwrap_or(false) {
                let mut final_usage = chunk(json!(null));
                final_usage["choices"] = json!([]);
                final_usage["usage"] = usage(&done);
                send(&final_usage);
            }
        }
        Err(failure) => {
            send(&json!({"error": {"message": failure.message, "type": failure.code, "code": failure.code}}));
        }
    }
    write!(stream, "data: [DONE]\n\n")?;
    stream.flush()
}

fn base64_floats(values: &[Value]) -> String {
    let bytes: Vec<u8> = values.iter().flat_map(|v| (v.as_f64().unwrap_or(0.0) as f32).to_le_bytes()).collect();
    media::base64(&bytes)
}

pub fn embeddings(service: &Service, request: &Request, stream: &mut TcpStream) -> io::Result<()> {
    let started = Instant::now();
    let prepared = (|| {
        let body = parse_body(request)?;
        let input = match &body["input"] {
            Value::String(_) => body["input"].clone(),
            Value::Array(items) if !items.is_empty() && items.iter().all(Value::is_string) => body["input"].clone(),
            _ => return Err(Failure::new("invalid_request", "input must be a string or a non-empty array of strings")),
        };
        let model = service.resolve(body["model"].as_str(), Purpose::Embed)?;
        Ok((body, input, model))
    })();
    let (body, input, model) = match prepared {
        Ok(prepared) => prepared,
        Err(failure) => return send_error(stream, &failure),
    };
    match service.run(json!({"op": "embed", "input": input}), &model, |_| true) {
        Ok(done) => {
            log_request("POST", &request.path, &model.id, &done, started);
            let as_base64 = body["encoding_format"].as_str() == Some("base64");
            let data: Vec<Value> = done["embeddings"]
                .as_array()
                .map(|vectors| {
                    vectors
                        .iter()
                        .enumerate()
                        .map(|(index, vector)| {
                            let embedding =
                                if as_base64 { json!(base64_floats(vector.as_array().map(Vec::as_slice).unwrap_or(&[]))) } else { vector.clone() };
                            json!({"object": "embedding", "index": index, "embedding": embedding})
                        })
                        .collect()
                })
                .unwrap_or_default();
            let tokens = done["usage"]["prompt_tokens"].as_u64().unwrap_or(0);
            http::respond_json(
                stream,
                200,
                &json!({"object": "list", "data": data, "model": model.id, "usage": {"prompt_tokens": tokens, "total_tokens": tokens}}),
            )
        }
        Err(failure) => send_error(stream, &failure),
    }
}

/// One multipart/form-data field: (name, filename, bytes).
pub type Field = (String, Option<String>, Vec<u8>);

pub fn multipart(content_type: &str, body: &[u8]) -> Option<Vec<Field>> {
    let boundary = content_type.split(';').find_map(|part| part.trim().strip_prefix("boundary="))?.trim_matches('"');
    let delimiter = format!("--{boundary}").into_bytes();
    let find = |haystack: &[u8], needle: &[u8], from: usize| {
        haystack.get(from..)?.windows(needle.len()).position(|window| window == needle).map(|index| index + from)
    };
    let mut fields = Vec::new();
    let mut position = find(body, &delimiter, 0)? + delimiter.len();
    loop {
        if body.get(position..position + 2) == Some(b"--") {
            break;
        }
        let head_end = find(body, b"\r\n\r\n", position)?;
        let head = String::from_utf8_lossy(&body[position..head_end]).to_string();
        let next = find(body, &delimiter, head_end + 4)?;
        let content = body[head_end + 4..next.saturating_sub(2)].to_vec();
        let disposition = head.lines().find(|line| line.to_ascii_lowercase().starts_with("content-disposition"))?.to_string();
        let attribute = |key: &str| {
            disposition.split(';').find_map(|part| part.trim().strip_prefix(&format!("{key}=")).map(|v| v.trim_matches('"').to_string()))
        };
        fields.push((attribute("name")?, attribute("filename"), content));
        position = next + delimiter.len();
    }
    Some(fields)
}

/// A file this request owns; removed when it goes out of scope.
struct Scratch(Vec<PathBuf>);

impl Drop for Scratch {
    fn drop(&mut self) {
        for path in &self.0 {
            let _ = fs::remove_file(path);
        }
    }
}

fn scratch_file(service: &Service, extension: &str) -> PathBuf {
    let directory = engine_dir(&service.storage).join("uploads");
    let _ = fs::create_dir_all(&directory);
    directory.join(format!("{}.{extension}", random_id("file")))
}

fn srt(segments: &[Value]) -> String {
    let clock = |seconds: f64| {
        let millis = (seconds.max(0.0) * 1000.0).round() as u64;
        format!("{:02}:{:02}:{:02},{:03}", millis / 3_600_000, millis / 60_000 % 60, millis / 1000 % 60, millis % 1000)
    };
    segments
        .iter()
        .enumerate()
        .map(|(index, segment)| {
            format!(
                "{}\n{} --> {}\n{}\n",
                index + 1,
                clock(segment["start"].as_f64().unwrap_or(0.0)),
                clock(segment["end"].as_f64().unwrap_or(0.0)),
                segment["text"].as_str().unwrap_or("").trim()
            )
        })
        .collect::<Vec<_>>()
        .join("\n")
}

pub fn transcriptions(service: &Service, request: &Request, stream: &mut TcpStream) -> io::Result<()> {
    let started = Instant::now();
    let fields = request.header("content-type").and_then(|kind| multipart(kind, &request.body));
    let Some(fields) = fields else {
        return send_error(stream, &Failure::new("invalid_request", "Send multipart/form-data with a file field"));
    };
    let text = |name: &str| {
        fields.iter().find(|(field, _, _)| field == name).map(|(_, _, value)| String::from_utf8_lossy(value).trim().to_string())
    };
    let Some((_, filename, audio)) = fields.iter().find(|(name, _, _)| name == "file") else {
        return send_error(stream, &Failure::new("invalid_request", "The form has no file field"));
    };
    let model = match service.resolve(text("model").as_deref(), Purpose::Transcribe) {
        Ok(model) => model,
        Err(failure) => return send_error(stream, &failure),
    };
    let extension: String = filename
        .as_deref()
        .and_then(|name| name.rsplit_once('.'))
        .map(|(_, ext)| ext.chars().filter(char::is_ascii_alphanumeric).take(8).collect())
        .filter(|ext: &String| !ext.is_empty())
        .unwrap_or_else(|| "wav".into());
    let upload = scratch_file(service, &extension);
    let mut cleanup = Scratch(vec![upload.clone()]);
    if let Err(error) = fs::write(&upload, audio) {
        return send_error(stream, &Failure::new("internal_error", format!("Cannot store the upload: {error}")));
    }
    let audio = match media::readable_audio(&upload, &engine_dir(&service.storage).join("uploads")) {
        Ok((path, temporary)) => {
            if temporary {
                cleanup.0.push(path.clone());
            }
            path
        }
        Err(message) => return send_error(stream, &Failure::new("invalid_request", message)),
    };
    let mut job = json!({"op": "transcribe", "path": audio});
    if let Some(language) = text("language").filter(|l| !l.is_empty()) {
        job["language"] = json!(language);
    }
    let result = service.run(job, &model, |_| true);
    drop(cleanup);
    match result {
        Ok(done) => {
            log_request("POST", &request.path, &model.id, &done, started);
            match text("response_format").as_deref() {
                Some("text") => http::respond(stream, 200, "text/plain; charset=utf-8", done["text"].as_str().unwrap_or("").as_bytes()),
                Some("srt") => http::respond(stream, 200, "text/plain; charset=utf-8", srt(done["segments"].as_array().map(Vec::as_slice).unwrap_or(&[])).as_bytes()),
                Some("verbose_json") => http::respond_json(
                    stream,
                    200,
                    &json!({"text": done["text"], "language": done["language"], "segments": done["segments"], "task": "transcribe"}),
                ),
                _ => http::respond_json(stream, 200, &json!({"text": done["text"], "language": done["language"]})),
            }
        }
        Err(failure) => send_error(stream, &failure),
    }
}

/// `/v1/images/generations`: the picture comes back as base64 PNG.
pub fn images(service: &Service, request: &Request, stream: &mut TcpStream) -> io::Result<()> {
    let started = Instant::now();
    let prepared = (|| {
        let body = parse_body(request)?;
        let prompt = body["prompt"].as_str().filter(|p| !p.trim().is_empty()).ok_or_else(|| Failure::new("invalid_request", "prompt is required"))?;
        if body["n"].as_u64().unwrap_or(1) != 1 {
            return Err(Failure::new("invalid_request", "n must be 1; send several requests for more images"));
        }
        let (width, height) = match body["size"].as_str() {
            None | Some("auto") => (1024, 1024),
            Some(size) => media::parse_size(size).ok_or_else(|| Failure::new("invalid_request", "size must look like 1024x1024"))?,
        };
        let model = service.resolve(body["model"].as_str(), Purpose::Image)?;
        let job = json!({"op": "image", "prompt": prompt, "width": width, "height": height, "seed": body["seed"], "steps": body["steps"],
                         "output": scratch_file(service, "png")});
        Ok((model, job))
    })();
    let (model, job) = match prepared {
        Ok(prepared) => prepared,
        Err(failure) => return send_error(stream, &failure),
    };
    let output = PathBuf::from(job["output"].as_str().unwrap_or_default());
    let _cleanup = Scratch(vec![output.clone()]);
    let watch = stream.try_clone()?;
    match service.run(job, &model, |event| event["event"] != "tick" || !client_gone(&watch)) {
        Ok(done) => {
            log_request("POST", &request.path, &model.id, &done, started);
            match fs::read(&output) {
                Ok(png) => http::respond_json(
                    stream,
                    200,
                    &json!({"created": now(), "data": [{"b64_json": media::base64(&png), "revised_prompt": null}], "seed": done["seed"],
                            "model": model.id}),
                ),
                Err(error) => send_error(stream, &Failure::new("generation_failed", format!("The image is missing: {error}"))),
            }
        }
        Err(failure) => send_error(stream, &failure),
    }
}

/// `/v1/audio/speech`: the audio bytes, like OpenAI's TTS endpoint.
pub fn speech(service: &Service, request: &Request, stream: &mut TcpStream) -> io::Result<()> {
    let started = Instant::now();
    let prepared = (|| {
        let body = parse_body(request)?;
        let input = body["input"].as_str().filter(|text| !text.trim().is_empty()).ok_or_else(|| Failure::new("invalid_request", "input is required"))?;
        let format = body["response_format"].as_str().unwrap_or("wav");
        let (extension, mime) = match format {
            "wav" => ("wav", "audio/wav"),
            "mp3" => ("mp3", "audio/mpeg"),
            "flac" => ("flac", "audio/flac"),
            "opus" => ("opus", "audio/ogg"),
            _ => return Err(Failure::new("invalid_request", "response_format must be wav, mp3, flac or opus")),
        };
        let model = service.resolve(body["model"].as_str(), Purpose::Speak)?;
        let voice = body["voice"].as_str().filter(|v| !v.is_empty() && *v != "default");
        let job = json!({"op": "speak", "text": input, "voice": voice, "speed": body["speed"], "language": body["language"],
                         "instructions": body["instructions"], "output": scratch_file(service, extension)});
        Ok((model, job, mime))
    })();
    let (model, job, mime) = match prepared {
        Ok(prepared) => prepared,
        Err(failure) => return send_error(stream, &failure),
    };
    let output = PathBuf::from(job["output"].as_str().unwrap_or_default());
    let _cleanup = Scratch(vec![output.clone()]);
    match service.run(job, &model, |_| true) {
        Ok(done) => {
            log_request("POST", &request.path, &model.id, &done, started);
            match fs::read(&output) {
                Ok(audio) => http::respond(stream, 200, mime, &audio),
                Err(error) => send_error(stream, &Failure::new("generation_failed", format!("The audio is missing: {error}"))),
            }
        }
        Err(failure) => send_error(stream, &failure),
    }
}

/// Video jobs: generation takes minutes, so like OpenAI's video API the
/// request returns a job to poll and the MP4 is fetched when it is done.
#[derive(Clone)]
struct VideoJob {
    id: String,
    model: String,
    prompt: String,
    status: &'static str,
    progress: u64,
    created: u64,
    path: Option<PathBuf>,
    error: Option<String>,
    size: String,
}

impl VideoJob {
    fn json(&self) -> Value {
        let mut value = json!({"id": self.id, "object": "video", "model": self.model, "status": self.status, "progress": self.progress,
                               "created_at": self.created, "prompt": self.prompt, "size": self.size});
        if let Some(error) = &self.error {
            value["error"] = json!({"message": error});
        }
        value
    }
}

fn video_jobs() -> &'static Mutex<HashMap<String, VideoJob>> {
    static JOBS: OnceLock<Mutex<HashMap<String, VideoJob>>> = OnceLock::new();
    JOBS.get_or_init(|| Mutex::new(HashMap::new()))
}

pub fn create_video(service: &Arc<Service>, request: &Request, stream: &mut TcpStream) -> io::Result<()> {
    let prepared = (|| {
        let body = parse_body(request)?;
        let prompt = body["prompt"].as_str().filter(|p| !p.trim().is_empty()).ok_or_else(|| Failure::new("invalid_request", "prompt is required"))?;
        let size = body["size"].as_str().map(|s| media::parse_size(s).ok_or_else(|| Failure::new("invalid_request", "size must look like 832x480"))).transpose()?;
        let model = service.resolve(body["model"].as_str(), Purpose::Video)?;
        let seconds = body["seconds"].as_str().and_then(|s| s.parse::<f64>().ok()).or(body["seconds"].as_f64());
        let frames = body["frames"].as_u64().or(seconds.map(|s| (s * 24.0).round() as u64 + 1));
        let id = random_id("video");
        let output = media::output_path(&service.storage, "videos", prompt, "mp4");
        let job = json!({"op": "video", "prompt": prompt, "width": size.map(|s| s.0), "height": size.map(|s| s.1), "frames": frames,
                         "seed": body["seed"], "steps": body["steps"], "output": output});
        Ok((id, model, job, prompt.to_string(), size))
    })();
    let (id, model, job, prompt, size) = match prepared {
        Ok(prepared) => prepared,
        Err(failure) => return send_error(stream, &failure),
    };
    let record = VideoJob {
        id: id.clone(),
        model: model.id.clone(),
        prompt,
        status: "queued",
        progress: 0,
        created: now(),
        path: None,
        error: None,
        size: size.map(|(w, h)| format!("{w}x{h}")).unwrap_or_default(),
    };
    video_jobs().lock().unwrap_or_else(PoisonError::into_inner).insert(id.clone(), record.clone());
    let service = service.clone();
    thread::spawn(move || {
        let started = Instant::now();
        let update = |change: &dyn Fn(&mut VideoJob)| {
            if let Some(job) = video_jobs().lock().unwrap_or_else(PoisonError::into_inner).get_mut(&id) {
                change(job);
            }
        };
        update(&|job| job.status = "in_progress");
        let result = service.run(job, &model, |event| {
            if event["event"] == "progress" {
                let (step, total) = (event["step"].as_u64().unwrap_or(0), event["total"].as_u64().unwrap_or(0));
                if total > 0 {
                    update(&|job| job.progress = (step * 100 / total).min(99));
                }
            }
            true
        });
        match result {
            Ok(done) => {
                log_request("POST", "/v1/videos", &model.id, &done, started);
                let path = PathBuf::from(done["path"].as_str().unwrap_or_default());
                update(&|job| {
                    job.status = "completed";
                    job.progress = 100;
                    job.path = Some(path.clone());
                });
            }
            Err(failure) => update(&|job| {
                job.status = "failed";
                job.error = Some(failure.message.clone());
            }),
        }
    });
    http::respond_json(stream, 200, &record.json())
}

/// `GET /v1/videos/{id}` and `GET /v1/videos/{id}/content`.
pub fn video(request: &Request, stream: &mut TcpStream) -> io::Result<()> {
    let rest = request.path.trim_start_matches("/v1/videos/");
    let (id, content) = match rest.strip_suffix("/content") {
        Some(id) => (id, true),
        None => (rest, false),
    };
    let job = video_jobs().lock().unwrap_or_else(PoisonError::into_inner).get(id).cloned();
    let Some(job) = job else {
        return send_error(stream, &Failure::new("not_found", format!("No video job {id}")));
    };
    if !content {
        return http::respond_json(stream, 200, &job.json());
    }
    match (&job.path, job.status) {
        (Some(path), "completed") => match fs::read(path) {
            Ok(bytes) => http::respond(stream, 200, "video/mp4", &bytes),
            Err(error) => send_error(stream, &Failure::new("not_found", format!("The video file is gone: {error}"))),
        },
        _ => send_error(stream, &Failure::new("invalid_request", format!("Video {id} is {}", job.status))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn content_parts_split_text_and_images() {
        let (text, images) = content_parts(&json!([
            {"type": "text", "text": "what is"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}},
            {"type": "text", "text": "this?"}
        ]));
        assert_eq!(text, "what is\nthis?");
        assert_eq!(images, ["data:image/png;base64,AAA"]);
        assert_eq!(content_parts(&json!("hi")).0, "hi");
        assert_eq!(content_parts(&Value::Null).0, "");
    }

    #[test]
    fn messages_are_normalized_for_templates() {
        let messages = normalize_messages(&json!([
            {"role": "developer", "content": "be brief"},
            {"role": "assistant", "content": null, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{\"x\": 1}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "42"}
        ]))
        .unwrap();
        assert_eq!(messages[0]["role"], "system");
        assert_eq!(messages[1]["tool_calls"][0]["function"]["arguments"]["x"], 1);
        assert_eq!(messages[1]["content"], "");
        assert_eq!(messages[2]["tool_call_id"], "c1");
        assert!(normalize_messages(&json!([])).is_err());
        assert!(normalize_messages(&json!([{"content": "x"}])).is_err());
        assert!(normalize_messages(&json!("x")).is_err());
    }

    #[test]
    fn params_carry_only_what_the_request_sets() {
        let sent = params(&json!({"temperature": 0.2, "max_tokens": 0, "stop": "x"}));
        assert_eq!(sent["temperature"], 0.2);
        assert!(sent["top_p"].is_null() && sent["max_tokens"].is_null());
        assert_eq!(sent["stop"], json!(["x"]));
        assert_eq!(params(&json!({"max_completion_tokens": 5}))["max_tokens"], 5);
    }

    #[test]
    fn floats_encode_like_numpy_base64() {
        // numpy: base64.b64encode(np.array([1.0, -2.5], dtype="<f4").tobytes())
        assert_eq!(base64_floats(&[json!(1.0), json!(-2.5)]), "AACAPwAAIMA=");
        assert_eq!(base64_floats(&[json!(0.0)]), "AAAAAA==");
    }

    #[test]
    fn subtitles_are_srt() {
        let text = srt(&[json!({"start": 0.0, "end": 1.5, "text": " Hi "}), json!({"start": 61.25, "end": 3725.0, "text": "Bye"})]);
        assert_eq!(text, "1\n00:00:00,000 --> 00:00:01,500\nHi\n\n2\n00:01:01,250 --> 01:02:05,000\nBye\n");
    }

    #[test]
    fn multipart_fields_are_extracted() {
        let body = b"--XX\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nwhisper\r\n--XX\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.mp3\"\r\nContent-Type: audio/mpeg\r\n\r\n\x00\x01\r\n\x02\r\n--XX--\r\n";
        let fields = multipart("multipart/form-data; boundary=XX", body).unwrap();
        assert_eq!(fields[0], ("model".to_string(), None, b"whisper".to_vec()));
        assert_eq!(fields[1], ("file".to_string(), Some("a.mp3".to_string()), b"\x00\x01\r\n\x02".to_vec()));
        assert!(multipart("application/json", body).is_none());
    }
}
