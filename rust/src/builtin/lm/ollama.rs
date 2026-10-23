//! Ollama-compatible endpoints, so apps and plugins written for Ollama work
//! unchanged (point them at the server, or start it with `--ollama`).

use std::io::{self, Write};
use std::net::TcpStream;
use std::time::Instant;

use serde_json::{json, Value};

use super::http::{self, Request};
use super::openai::normalize_messages;
use super::server::{client_gone, log_request, now, parse_body, send_error};
use super::service::{Purpose, Service};
use super::store::{Kind, Model};
use super::worker::Failure;

/// RFC 3339 UTC timestamp, which Ollama clients parse.
fn timestamp() -> String {
    let seconds = now() as libc::time_t;
    // SAFETY: gmtime_r writes into the zeroed tm we own.
    let mut tm: libc::tm = unsafe { std::mem::zeroed() };
    unsafe { libc::gmtime_r(&seconds, &mut tm) };
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
        tm.tm_year + 1900,
        tm.tm_mon + 1,
        tm.tm_mday,
        tm.tm_hour,
        tm.tm_min,
        tm.tm_sec
    )
}

fn details(model: &Model) -> Value {
    let config = std::fs::read_to_string(model.path.join("config.json"))
        .ok()
        .and_then(|text| serde_json::from_str::<Value>(&text).ok())
        .unwrap_or(Value::Null);
    let bits = config["quantization"]["bits"].as_u64().map(|bits| format!("Q{bits}")).unwrap_or_else(|| "F16".into());
    json!({
        "format": "mlx",
        "family": config["model_type"].as_str().unwrap_or(""),
        "families": [config["model_type"].as_str().unwrap_or("")],
        "parameter_size": "",
        "quantization_level": bits,
    })
}

fn entry(model: &Model) -> Value {
    json!({
        "name": model.id,
        "model": model.id,
        "modified_at": timestamp(),
        "size": model.bytes,
        "digest": "",
        "details": details(model),
    })
}

pub fn tags(service: &Service, stream: &mut TcpStream) -> io::Result<()> {
    let models: Vec<Value> = service.models().iter().filter(|m| m.kind.runnable() && !m.partial).map(entry).collect();
    http::respond_json(stream, 200, &json!({"models": models}))
}

pub fn ps(service: &Service, stream: &mut TcpStream) -> io::Result<()> {
    let loaded = service.loaded();
    let models: Vec<Value> = service
        .models()
        .iter()
        .filter(|m| loaded.contains(&m.id))
        .map(|m| {
            let mut value = entry(m);
            value["size_vram"] = json!(m.bytes);
            value["expires_at"] = json!(timestamp());
            value
        })
        .collect();
    http::respond_json(stream, 200, &json!({"models": models}))
}

pub fn show(service: &Service, request: &Request, stream: &mut TcpStream) -> io::Result<()> {
    let result = parse_body(request).and_then(|body| {
        let name = body["model"].as_str().or(body["name"].as_str()).map(str::to_string);
        let model = service.models().into_iter().find(|m| Some(&m.id) == name.as_ref());
        model
            .or_else(|| service.resolve(name.as_deref(), Purpose::Chat).ok())
            .ok_or_else(|| Failure::new("model_not_found", "Model is not downloaded"))
    });
    match result {
        Ok(model) => {
            let mut capabilities = vec![if model.kind == Kind::Embedding { "embedding" } else { "completion" }];
            if model.kind == Kind::Vision {
                capabilities.push("vision");
            }
            let template = std::fs::read_to_string(model.path.join("tokenizer_config.json")).unwrap_or_default();
            if template.contains("tools") {
                capabilities.push("tools");
            }
            http::respond_json(
                stream,
                200,
                &json!({"details": details(&model), "model_info": {}, "capabilities": capabilities, "modified_at": timestamp()}),
            )
        }
        Err(failure) => send_error(stream, &failure),
    }
}

/// Ollama `options` → worker sampling parameters; unset ones fall back to the
/// model's generation_config.json, then lm.* settings.
fn params(options: &Value) -> Value {
    let stop: Vec<Value> = options["stop"].as_array().cloned().unwrap_or_default();
    json!({
        "temperature": options["temperature"].as_f64(),
        "top_p": options["top_p"].as_f64(),
        "top_k": options["top_k"].as_i64(),
        "min_p": options["min_p"].as_f64(),
        "max_tokens": options["num_predict"].as_i64().filter(|n| *n > 0),
        "stop": stop,
        "seed": options["seed"].as_i64(),
        "repetition_penalty": options["repeat_penalty"].as_f64().filter(|v| *v != 1.0),
        "presence_penalty": options["presence_penalty"].as_f64().filter(|v| *v != 0.0),
        "frequency_penalty": options["frequency_penalty"].as_f64().filter(|v| *v != 0.0),
    })
}

/// Ollama sends bare base64 images; the worker accepts data URLs and paths.
fn images(value: &Value) -> Vec<Value> {
    value
        .as_array()
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(|image| if image.starts_with("data:") { json!(image) } else { json!(format!("data:image/png;base64,{image}")) })
                .collect()
        })
        .unwrap_or_default()
}

fn ollama_tool_calls(done: &Value) -> Vec<Value> {
    done["tool_calls"]
        .as_array()
        .map(|calls| {
            calls
                .iter()
                .map(|call| {
                    let arguments = call["function"]["arguments"]
                        .as_str()
                        .and_then(|text| serde_json::from_str::<Value>(text).ok())
                        .unwrap_or_else(|| call["function"]["arguments"].clone());
                    json!({"function": {"name": call["function"]["name"], "arguments": arguments}})
                })
                .collect()
        })
        .unwrap_or_default()
}

/// `/api/chat`, and with `generate` the prompt-based `/api/generate`.
pub fn chat(service: &Service, request: &Request, stream: &mut TcpStream, generate: bool) -> io::Result<()> {
    let started = Instant::now();
    let prepared = (|| {
        let body = parse_body(request)?;
        let model = service.resolve(body["model"].as_str(), Purpose::Chat)?;
        let mut job = json!({"op": "chat", "params": params(&body["options"])});
        if generate {
            let prompt = body["prompt"].as_str().unwrap_or("");
            if body["raw"].as_bool().unwrap_or(false) {
                job["op"] = json!("complete");
                job["prompt"] = json!(prompt);
            } else {
                let mut messages = Vec::new();
                if let Some(system) = body["system"].as_str().filter(|s| !s.is_empty()) {
                    messages.push(json!({"role": "system", "content": system}));
                }
                let mut user = json!({"role": "user", "content": prompt});
                let attached = images(&body["images"]);
                if !attached.is_empty() {
                    user["images"] = json!(attached);
                }
                messages.push(user);
                job["messages"] = json!(messages);
            }
        } else {
            let mut messages = normalize_messages(&body["messages"])?;
            for (message, original) in messages.iter_mut().zip(body["messages"].as_array().into_iter().flatten()) {
                let attached = images(&original["images"]);
                if !attached.is_empty() {
                    message["images"] = json!(attached);
                }
            }
            job["messages"] = json!(messages);
            if body["tools"].as_array().is_some_and(|tools| !tools.is_empty()) {
                job["tools"] = body["tools"].clone();
            }
        }
        if let Some(think) = body["think"].as_bool() {
            job["think"] = json!(think);
        }
        Ok((body, model, job))
    })();
    let (body, model, job) = match prepared {
        Ok(prepared) => prepared,
        Err(failure) => return send_error(stream, &failure),
    };
    // An empty /api/generate prompt only loads the model (Ollama's preload).
    let preload = generate && body["prompt"].as_str().unwrap_or("").is_empty() && body["images"].is_null();
    let job = if preload { json!({"op": "load"}) } else { job };
    let field = if generate { "response" } else { "message" };
    let piece = |text: &str, thinking: bool| -> Value {
        if generate {
            if thinking {
                json!({"response": "", "thinking": text})
            } else {
                json!({"response": text})
            }
        } else if thinking {
            json!({"message": {"role": "assistant", "content": "", "thinking": text}})
        } else {
            json!({"message": {"role": "assistant", "content": text}})
        }
    };
    let finish = |done: &Value| -> Value {
        let elapsed = started.elapsed().as_nanos() as u64;
        let mut last = json!({
            "model": model.id,
            "created_at": timestamp(),
            "done": true,
            "done_reason": if done["finish_reason"] == "length" { "length" } else if preload { "load" } else { "stop" },
            "total_duration": elapsed,
            "load_duration": 0,
            "prompt_eval_count": done["usage"]["prompt_tokens"].as_u64().unwrap_or(0),
            "eval_count": done["usage"]["completion_tokens"].as_u64().unwrap_or(0),
            "eval_duration": elapsed,
        });
        last[field] = if generate { json!("") } else { json!({"role": "assistant", "content": ""}) };
        let calls = ollama_tool_calls(done);
        if !calls.is_empty() && !generate {
            last["message"]["tool_calls"] = json!(calls);
        }
        last
    };

    if !body["stream"].as_bool().unwrap_or(true) || preload {
        let watch = stream.try_clone()?;
        return match service.run(job, &model, |event| event["event"] != "tick" || !client_gone(&watch)) {
            Ok(done) => {
                log_request("POST", &request.path, &model.id, &done, started);
                let mut last = finish(&done);
                let text = done["text"].as_str().unwrap_or("");
                let reasoning = done["reasoning"].as_str().unwrap_or("");
                if generate {
                    last["response"] = json!(text);
                    if !reasoning.is_empty() {
                        last["thinking"] = json!(reasoning);
                    }
                } else {
                    last["message"]["content"] = json!(text);
                    if !reasoning.is_empty() {
                        last["message"]["thinking"] = json!(reasoning);
                    }
                }
                http::respond_json(stream, 200, &last)
            }
            Err(failure) => http::respond_json(stream, failure.status(), &json!({"error": failure.message})),
        };
    }

    http::start_stream(stream, "application/x-ndjson")?;
    let mut writer = stream.try_clone()?;
    let watch = stream.try_clone()?;
    let result = service.run(job, &model, |event| {
        if event["event"] == "tick" {
            return !client_gone(&watch);
        }
        let Some(text) = event["text"].as_str() else { return true };
        let mut line = piece(text, event["channel"] == "reasoning");
        line["model"] = json!(model.id);
        line["created_at"] = json!(timestamp());
        line["done"] = json!(false);
        writeln!(writer, "{line}").and_then(|_| writer.flush()).is_ok()
    });
    let last = match result {
        Ok(done) => {
            log_request("POST", &request.path, &model.id, &done, started);
            finish(&done)
        }
        Err(failure) => json!({"error": failure.message}),
    };
    writeln!(stream, "{last}")?;
    stream.flush()
}

/// `/api/embed` (`input`, many) and the older `/api/embeddings` (`prompt`, one).
pub fn embed(service: &Service, request: &Request, stream: &mut TcpStream, legacy: bool) -> io::Result<()> {
    let started = Instant::now();
    let prepared = (|| {
        let body = parse_body(request)?;
        let input = if legacy { body["prompt"].clone() } else { body["input"].clone() };
        let valid = input.is_string() || input.as_array().is_some_and(|items| !items.is_empty() && items.iter().all(Value::is_string));
        if !valid {
            return Err(Failure::new("invalid_request", "input must be a string or a non-empty array of strings"));
        }
        let model = service.resolve(body["model"].as_str(), Purpose::Embed)?;
        Ok((input, model))
    })();
    let (input, model) = match prepared {
        Ok(prepared) => prepared,
        Err(failure) => return http::respond_json(stream, failure.status(), &json!({"error": failure.message})),
    };
    match service.run(json!({"op": "embed", "input": input}), &model, |_| true) {
        Ok(done) => {
            log_request("POST", &request.path, &model.id, &done, started);
            if legacy {
                http::respond_json(stream, 200, &json!({"embedding": done["embeddings"][0]}))
            } else {
                http::respond_json(
                    stream,
                    200,
                    &json!({"model": model.id, "embeddings": done["embeddings"], "prompt_eval_count": done["usage"]["prompt_tokens"]}),
                )
            }
        }
        Err(failure) => http::respond_json(stream, failure.status(), &json!({"error": failure.message})),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn timestamps_are_rfc3339() {
        let stamp = timestamp();
        assert_eq!(stamp.len(), 20);
        assert!(stamp.ends_with('Z') && stamp.as_bytes()[10] == b'T');
    }

    #[test]
    fn images_become_data_urls_and_tool_arguments_objects() {
        assert_eq!(images(&json!(["AAA", "data:image/jpeg;base64,BBB"])), [json!("data:image/png;base64,AAA"), json!("data:image/jpeg;base64,BBB")]);
        let calls = ollama_tool_calls(&json!({"tool_calls": [{"function": {"name": "f", "arguments": "{\"a\":1}"}}]}));
        assert_eq!(calls[0]["function"]["arguments"]["a"], 1);
    }
}
