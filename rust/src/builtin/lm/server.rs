//! `ul lm serve`: OpenAI-compatible `/v1/*` (what LM Studio offers) and
//! Ollama-compatible `/api/*` on 127.0.0.1, plus `/ul/*` for the CLI. Each
//! connection has its own thread; a failing request answers with a JSON error
//! and never stops the server.

use std::io::{self, Write};
use std::net::{Shutdown, TcpListener, TcpStream};
use std::panic::{self, AssertUnwindSafe};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};


use serde_json::{json, Value};

use super::http::{self, ReadError, Request};
use super::service::Service;
use super::store::human_size;
use super::worker::Failure;
use super::{ollama, openai};

pub fn now() -> u64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}

/// True once the client has closed its side (checked between tokens).
pub fn client_gone(stream: &TcpStream) -> bool {
    if stream.set_nonblocking(true).is_err() {
        return true;
    }
    let mut byte = [0u8; 1];
    let gone = match stream.peek(&mut byte) {
        Ok(read) => read == 0,
        Err(error) => error.kind() != io::ErrorKind::WouldBlock,
    };
    let _ = stream.set_nonblocking(false);
    gone
}

pub fn parse_body(request: &Request) -> Result<Value, Failure> {
    if request.body.is_empty() {
        return Ok(json!({}));
    }
    serde_json::from_slice(&request.body).map_err(|error| Failure::new("invalid_request", format!("Body is not valid JSON: {error}")))
}

/// OpenAI-style error body.
pub fn send_error(stream: &mut TcpStream, failure: &Failure) -> io::Result<()> {
    http::respond_json(
        stream,
        failure.status(),
        &json!({"error": {"message": failure.message, "type": failure.code, "code": failure.code}}),
    )
}

/// One line per finished request on the server's terminal.
pub fn log_request(method: &str, path: &str, model: &str, done: &Value, started: Instant) {
    let tokens = done["usage"]["completion_tokens"].as_u64().unwrap_or(0);
    let speed = done["stats"]["generation_tps"].as_f64().unwrap_or(0.0);
    let detail = if tokens > 0 { format!(" {tokens} tok {speed:.1} tok/s") } else { String::new() };
    eprintln!("{} {method} {path} {model}{detail} {:.1}s", clock(), started.elapsed().as_secs_f64());
}

fn clock() -> String {
    let seconds = now() as libc::time_t;
    // SAFETY: localtime_r writes into the zeroed tm we own.
    let mut tm: libc::tm = unsafe { std::mem::zeroed() };
    unsafe { libc::localtime_r(&seconds, &mut tm) };
    format!("{:02}:{:02}:{:02}", tm.tm_hour, tm.tm_min, tm.tm_sec)
}

fn route(service: &Arc<Service>, request: &Request, stream: &mut TcpStream) -> io::Result<()> {
    if !http::local_host(request) {
        return http::respond_json(stream, 403, &json!({"error": {"message": "Only localhost may use this server", "type": "forbidden"}}));
    }
    let path = request.path.trim_end_matches('/');
    let path = if path.is_empty() { "/" } else { path };
    match (request.method.as_str(), path) {
        ("OPTIONS", _) => http::respond(stream, 204, "text/plain", b""),
        ("GET" | "HEAD", "/") => http::respond(stream, 200, "text/plain", b"Ollama is running (ul lm)"),
        ("GET", "/v1/models") => openai::models(service, stream),
        ("POST", "/v1/chat/completions") => openai::chat(service, request, stream, false),
        ("POST", "/v1/completions") => openai::chat(service, request, stream, true),
        ("POST", "/v1/embeddings") => openai::embeddings(service, request, stream),
        ("POST", "/v1/audio/transcriptions") => openai::transcriptions(service, request, stream),
        ("POST", "/v1/audio/speech") => openai::speech(service, request, stream),
        ("POST", "/v1/images/generations") => openai::images(service, request, stream),
        ("POST", "/v1/videos") => openai::create_video(service, request, stream),
        ("GET", video) if video.starts_with("/v1/videos/") => openai::video(request, stream),
        ("GET", "/api/tags") => ollama::tags(service, stream),
        ("GET", "/api/ps") => ollama::ps(service, stream),
        ("GET", "/api/version") => http::respond_json(stream, 200, &json!({"version": "0.12.0", "server": crate::version_line()})),
        ("POST", "/api/show") => ollama::show(service, request, stream),
        ("POST", "/api/chat") => ollama::chat(service, request, stream, false),
        ("POST", "/api/generate") => ollama::chat(service, request, stream, true),
        ("POST", "/api/embed") => ollama::embed(service, request, stream, false),
        ("POST", "/api/embeddings") => ollama::embed(service, request, stream, true),
        ("POST", "/api/pull" | "/api/delete" | "/api/create" | "/api/push" | "/api/copy") => send_error(
            stream,
            &Failure::new("invalid_request", "Manage models in the terminal: ul lm pull | rm"),
        ),
        ("GET", "/ul/ps") => {
            let lanes: Vec<Value> =
                service.lanes().into_iter().map(|(lane, loaded, busy)| json!({"lane": lane, "loaded": loaded, "busy": busy})).collect();
            http::respond_json(stream, 200, &json!({"loaded": service.loaded(), "lanes": lanes, "pid": std::process::id()}))
        }
        ("POST", "/ul/job") => cli_job(service, request, stream),
        (_, "/v1/models" | "/v1/chat/completions" | "/v1/completions" | "/v1/embeddings" | "/api/chat" | "/api/generate") => {
            send_error(stream, &Failure { code: "method_not_allowed".into(), message: format!("{} is not allowed here", request.method) })
        }
        _ => send_error(stream, &Failure::new("not_found", format!("No route for {} {}", request.method, request.path))),
    }
}

/// The CLI's own endpoint: a worker job in, worker events out as NDJSON.
fn cli_job(service: &Service, request: &Request, stream: &mut TcpStream) -> io::Result<()> {
    let body = match parse_body(request) {
        Ok(body) => body,
        Err(failure) => return send_error(stream, &failure),
    };
    let model = match service.models().into_iter().find(|m| Some(m.id.as_str()) == body["model"].as_str()) {
        Some(model) => model,
        None => return send_error(stream, &Failure::new("model_not_found", "Model is not downloaded")),
    };
    let started = Instant::now();
    http::start_stream(stream, "application/x-ndjson")?;
    let mut writer = stream.try_clone()?;
    let watch = stream.try_clone()?;
    let mut job = body["job"].clone();
    // The terminal's own jobs may name local files (images to look at).
    job["local"] = json!(true);
    let result = service.run(job, &model, |event| {
        if event["event"] == "tick" {
            return !client_gone(&watch);
        }
        writeln!(writer, "{event}").and_then(|_| writer.flush()).is_ok()
    });
    let last = match result {
        Ok(done) => {
            log_request("POST", &request.path, &model.id, &done, started);
            done
        }
        Err(failure) => json!({"event": "error", "code": failure.code, "message": failure.message}),
    };
    writeln!(stream, "{last}")?;
    stream.flush()
}

fn handle(service: &Arc<Service>, mut stream: TcpStream) {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(60)));
    let request = match http::read_request(&mut stream) {
        Ok(request) => request,
        Err(ReadError::Bad(status, message)) => {
            let _ = http::respond_json(&mut stream, status, &json!({"error": {"message": message, "type": "invalid_request"}}));
            return;
        }
        Err(ReadError::Io(_)) => return,
    };
    let _ = stream.set_read_timeout(None);
    let outcome = panic::catch_unwind(AssertUnwindSafe(|| route(service, &request, &mut stream)));
    if outcome.is_err() {
        let _ = send_error(&mut stream, &Failure::new("internal_error", "Internal error; the server keeps running"));
    }
    let _ = stream.shutdown(Shutdown::Both);
}

fn accept(service: Arc<Service>, listener: TcpListener) {
    for connection in listener.incoming() {
        let Ok(stream) = connection else { continue };
        let service = service.clone();
        thread::spawn(move || handle(&service, stream));
    }
}

pub fn bind(port: u16) -> Result<TcpListener, String> {
    TcpListener::bind(("127.0.0.1", port)).map_err(|error| {
        if error.kind() == io::ErrorKind::AddrInUse {
            format!("Port {port} is already in use (another `ul lm serve`, LM Studio or Ollama?); stop it or use --port <N>")
        } else {
            format!("Cannot listen on 127.0.0.1:{port}: {error}")
        }
    })
}

pub fn serve(service: Service, listeners: Vec<TcpListener>) -> i32 {
    let service = Arc::new(service);
    let ports: Vec<u16> = listeners.iter().filter_map(|l| l.local_addr().ok()).map(|a| a.port()).collect();
    let port = ports[0];
    let models = service.models();
    let runnable = models.iter().filter(|m| m.kind.runnable()).count();
    let total: u64 = models.iter().map(|m| m.bytes).sum();
    println!("ul lm server is running on http://127.0.0.1:{port}");
    println!("  OpenAI API  http://127.0.0.1:{port}/v1   base_url for OpenAI/LM Studio clients; any api_key works");
    for extra in &ports[1..] {
        println!("  Ollama API  http://127.0.0.1:{extra}      for Ollama clients");
    }
    if ports.len() == 1 {
        println!("  Ollama API  http://127.0.0.1:{port}      (add --ollama to also listen on :11434)");
    }
    println!(
        "  Models      {runnable} runnable of {} downloaded ({}); default: {}",
        models.len(),
        human_size(total),
        service.settings.default_model().unwrap_or("auto")
    );
    println!("  Media       /v1/images/generations · /v1/audio/speech · /v1/audio/transcriptions · /v1/videos");
    println!("  Unloads after {} min idle. Ctrl-C stops.", service.settings.idle_minutes);
    let _ = io::stdout().flush();
    let mut threads = Vec::new();
    for listener in listeners {
        let service = service.clone();
        threads.push(thread::spawn(move || accept(service, listener)));
    }
    for thread in threads {
        let _ = thread.join();
    }
    0
}
