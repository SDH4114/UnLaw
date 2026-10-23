//! The terminal side: one-shot answers, piped input, the interactive chat and
//! generated media. When `ul lm serve` is running the CLI goes through it
//! (sharing its loaded models); otherwise it starts its own workers. Answers
//! stream token by token, reasoning is shown dimmed, long jobs show progress,
//! and Ctrl-C stops the current job without leaving.

use std::fs;
use std::io::{self, BufRead, BufReader, ErrorKind, IsTerminal, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use super::http;
use super::media;
use super::service::{Purpose, Service};
use super::store::{Kind, Model};
use super::worker::Failure;

static GENERATING: AtomicBool = AtomicBool::new(false);
static INTERRUPTED: AtomicBool = AtomicBool::new(false);

extern "C" fn on_sigint(_: libc::c_int) {
    if GENERATING.load(Ordering::SeqCst) {
        INTERRUPTED.store(true, Ordering::SeqCst);
    } else {
        // At the prompt Ctrl-C leaves, like any shell tool.
        // SAFETY: write and _exit are async-signal-safe.
        unsafe {
            libc::write(2, b"\n".as_ptr().cast(), 1);
            libc::_exit(130);
        }
    }
}

pub fn install_interrupt_handler() {
    // SAFETY: the handler only touches atomics and async-signal-safe calls.
    unsafe {
        libc::signal(libc::SIGINT, on_sigint as *const () as libc::sighandler_t);
    }
}

/// Where jobs run: through a running server, or in this process.
pub enum Backend {
    Remote(u16),
    Local,
}

/// A `ul lm serve` of ours on the port (LM Studio or Ollama there don't count).
pub fn running_server(port: u16) -> bool {
    http::fetch(port, "GET", "/ul/ps", None, Duration::from_millis(300))
        .is_ok_and(|response| response.status == 200 && response.header("x-unlaw") == Some("lm"))
}

fn lost(error: io::Error) -> Failure {
    Failure::new("engine_unavailable", format!("Lost the ul lm server: {error}"))
}

impl Backend {
    pub fn detect(service: &Service) -> Backend {
        if running_server(service.settings.port) {
            Backend::Remote(service.settings.port)
        } else {
            Backend::Local
        }
    }

    /// Run a job; `on_event` sees tokens, progress and periodic ticks and
    /// returns false to cancel. Terminal jobs may name local files.
    pub fn run(&self, service: &Service, mut job: Value, model: &Model, mut on_event: impl FnMut(&Value) -> bool) -> Result<Value, Failure> {
        job["local"] = json!(true);
        match self {
            Backend::Local => service.run(job, model, |event| on_event(event) && !INTERRUPTED.load(Ordering::SeqCst)),
            Backend::Remote(port) => {
                let body = json!({"model": model.id, "job": job}).to_string();
                let (status, _, mut reader) =
                    http::send(*port, "POST", "/ul/job", Some(body.as_bytes()), Duration::from_secs(24 * 3600)).map_err(lost)?;
                if status != 200 {
                    let mut text = String::new();
                    let _ = io::Read::read_to_string(&mut reader, &mut text);
                    let error: Value = serde_json::from_str(&text).unwrap_or(Value::Null);
                    return Err(Failure {
                        code: error["error"]["code"].as_str().unwrap_or("engine_unavailable").into(),
                        message: error["error"]["message"].as_str().unwrap_or("The server refused the request").into(),
                    });
                }
                // Short reads so Ctrl-C works while the model is still thinking.
                let _ = reader.get_ref().set_read_timeout(Some(Duration::from_millis(200)));
                let mut line = Vec::new();
                loop {
                    let cancel = |reader: &io::BufReader<std::net::TcpStream>| {
                        // Closing the connection cancels the job on the server.
                        let _ = reader.get_ref().shutdown(std::net::Shutdown::Both);
                        Ok(json!({"event": "done", "text": "", "finish_reason": "cancelled"}))
                    };
                    match reader.read_until(b'\n', &mut line) {
                        Ok(0) => return Err(Failure::new("engine_unavailable", "The ul lm server closed the connection")),
                        Ok(_) if line.ends_with(b"\n") => {
                            let event: Value = serde_json::from_slice(&line).unwrap_or(Value::Null);
                            line.clear();
                            match event["event"].as_str() {
                                Some("done") => return Ok(event),
                                Some("error") => {
                                    return Err(Failure {
                                        code: event["code"].as_str().unwrap_or("").into(),
                                        message: event["message"].as_str().unwrap_or("").into(),
                                    })
                                }
                                _ => {
                                    if !on_event(&event) || INTERRUPTED.load(Ordering::SeqCst) {
                                        return cancel(&reader);
                                    }
                                }
                            }
                        }
                        Ok(_) => {}
                        Err(error) if matches!(error.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) => {
                            if !on_event(&json!({"event": "tick"})) || INTERRUPTED.load(Ordering::SeqCst) {
                                return cancel(&reader);
                            }
                        }
                        Err(error) => return Err(lost(error)),
                    }
                }
            }
        }
    }
}

/// Streams an answer: reasoning dimmed (terminal only), content as is.
struct Printer {
    tty: bool,
    show_reasoning: bool,
    in_reasoning: bool,
    wrote: bool,
}

impl Printer {
    fn new(show_reasoning: bool) -> Printer {
        Printer { tty: io::stdout().is_terminal(), show_reasoning, in_reasoning: false, wrote: false }
    }

    fn piece(&mut self, channel: &str, text: &str) {
        let mut out = io::stdout().lock();
        if channel == "reasoning" {
            if !(self.show_reasoning && self.tty) {
                return;
            }
            if !self.in_reasoning {
                let _ = write!(out, "\x1b[2m");
                self.in_reasoning = true;
            }
        } else if self.in_reasoning {
            let _ = writeln!(out, "\x1b[0m");
            self.in_reasoning = false;
        }
        let text = if !self.wrote && channel != "reasoning" { text.trim_start() } else { text };
        if text.is_empty() {
            return;
        }
        if channel != "reasoning" {
            self.wrote = true;
        }
        let _ = out.write_all(text.as_bytes());
        let _ = out.flush();
    }

    fn finish(&mut self, done: &Value) {
        let mut out = io::stdout().lock();
        if self.in_reasoning {
            let _ = write!(out, "\x1b[0m");
        }
        if let Some(calls) = done["tool_calls"].as_array().filter(|calls| !calls.is_empty()) {
            for call in calls {
                let _ = write!(out, "\n[tool call] {}({})", call["function"]["name"].as_str().unwrap_or(""), call["function"]["arguments"].as_str().unwrap_or(""));
            }
        }
        let _ = writeln!(out);
        if self.tty {
            let tokens = done["usage"]["completion_tokens"].as_u64().unwrap_or(0);
            let speed = done["stats"]["generation_tps"].as_f64().unwrap_or(0.0);
            let seconds = done["stats"]["seconds"].as_f64().unwrap_or(0.0);
            let note = match done["finish_reason"].as_str() {
                Some("length") => " · stopped at max_tokens",
                Some("cancelled") => " · stopped",
                _ => "",
            };
            if tokens > 0 {
                let _ = writeln!(out, "\x1b[2m{tokens} tokens · {speed:.1} tok/s · {seconds:.1}s{note}\x1b[0m");
            } else if !note.is_empty() {
                let _ = writeln!(out, "\x1b[2m{}\x1b[0m", note.trim_start_matches(" · "));
            }
        }
        let _ = out.flush();
    }
}

/// One status line on stderr for long jobs: spinner, step and elapsed time.
struct Progress {
    label: String,
    started: Instant,
    step: Option<(u64, u64)>,
    frame: usize,
    tty: bool,
}

impl Progress {
    fn new(label: impl Into<String>) -> Progress {
        Progress { label: label.into(), started: Instant::now(), step: None, frame: 0, tty: io::stderr().is_terminal() }
    }

    fn update(&mut self, event: &Value) -> bool {
        if event["event"] == "progress" {
            self.step = Some((event["step"].as_u64().unwrap_or(0), event["total"].as_u64().unwrap_or(0)));
        }
        if self.tty {
            const FRAMES: [&str; 10] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
            self.frame = (self.frame + 1) % FRAMES.len();
            let step = match self.step {
                Some((step, total)) if total > 0 => format!(" · step {step}/{total}"),
                Some((step, _)) => format!(" · part {step}"),
                None => String::new(),
            };
            eprint!("\r\x1b[2K{} {}{} · {:.0}s", FRAMES[self.frame], self.label, step, self.started.elapsed().as_secs_f64());
            let _ = io::stderr().flush();
        }
        true
    }

    fn clear(&self) {
        if self.tty {
            eprint!("\r\x1b[2K");
            let _ = io::stderr().flush();
        }
    }
}

#[derive(Clone, Default)]
pub struct Options {
    pub model: Option<String>,
    pub images: Vec<String>,
    pub system: Option<String>,
    pub temperature: Option<f64>,
    pub max_tokens: Option<i64>,
    pub think: Option<bool>,
    /// Spoken language for transcription and speech.
    pub language: Option<String>,
    pub output: Option<String>,
    pub size: Option<(u32, u32)>,
    pub steps: Option<u64>,
    pub seed: Option<u64>,
    pub frames: Option<u64>,
    pub seconds: Option<f64>,
    pub voice: Option<String>,
    pub speed: Option<f64>,
    pub lyrics: Option<String>,
    pub quantize: Option<u8>,
    pub strength: Option<f64>,
    /// Open (`open`) or play (`afplay`) the result.
    pub open: bool,
    pub srt: bool,
    pub json: bool,
}

fn params(options: &Options) -> Value {
    json!({"temperature": options.temperature, "max_tokens": options.max_tokens})
}

fn absolute(path: &str) -> PathBuf {
    let path = crate::util::expand_user(path.trim().trim_matches(['"', '\'']));
    if path.is_absolute() {
        path
    } else {
        std::env::current_dir().map(|d| d.join(&path)).unwrap_or(path)
    }
}

fn existing_file(path: &str, what: &str) -> Result<String, String> {
    let path = absolute(path);
    if path.is_file() {
        Ok(path.to_string_lossy().into_owned())
    } else {
        Err(format!("{what} not found: {}", path.display()))
    }
}

/// Resolve a model; in a terminal with several candidates and no default,
/// offer a numbered choice and remember it in the purpose's setting.
pub fn pick_model(service: &Service, requested: Option<&str>, purpose: Purpose) -> Result<Model, String> {
    match service.resolve(requested, purpose) {
        Ok(model) => Ok(model),
        Err(failure) if requested.is_none() && failure.message.contains("models are downloaded") && io::stdin().is_terminal() => {
            let models: Vec<Model> = service.models().into_iter().filter(|m| purpose.accepts(m.kind) && !m.partial).collect();
            eprintln!("Choose a default {} model:", purpose.noun());
            for (index, model) in models.iter().enumerate() {
                eprintln!("  {}) {} ({}, {})", index + 1, model.id, model.kind.name(), super::store::human_size(model.bytes));
            }
            eprint!("Number: ");
            let _ = io::stderr().flush();
            let mut answer = String::new();
            io::stdin().read_line(&mut answer).map_err(|error| error.to_string())?;
            let index: usize = answer.trim().parse().map_err(|_| "No model chosen".to_string())?;
            let model = models.get(index.wrapping_sub(1)).cloned().ok_or("No model chosen")?;
            let key = purpose.setting().unwrap_or("lm.model");
            if crate::config::set(key, toml_edit::Item::Value(model.id.as_str().into())).is_ok() {
                eprintln!("Saved as {key}; change it with `ul lm use <model>`.");
            }
            Ok(model)
        }
        Err(failure) => Err(failure.message),
    }
}

fn ask(backend: &Backend, service: &Service, model: &Model, messages: &[Value], options: &Options, printer: &mut Printer) -> Result<Value, Failure> {
    let mut job = json!({"op": "chat", "messages": messages, "params": params(options)});
    if let Some(think) = options.think {
        job["think"] = json!(think);
    }
    INTERRUPTED.store(false, Ordering::SeqCst);
    GENERATING.store(true, Ordering::SeqCst);
    let result = backend.run(service, job, model, |event| {
        if let Some(text) = event["text"].as_str() {
            printer.piece(event["channel"].as_str().unwrap_or("content"), text);
        }
        true
    });
    GENERATING.store(false, Ordering::SeqCst);
    result
}

fn system_message(service: &Service, options: &Options) -> Option<Value> {
    let system = options.system.clone().unwrap_or_else(|| service.settings.system_prompt.clone());
    (!system.trim().is_empty()).then(|| json!({"role": "system", "content": system}))
}

fn fail(message: &str) -> i32 {
    eprintln!("unlaw lm: {message}");
    1
}

/// `ul lm "question"`, optionally with piped stdin appended.
pub fn one_shot(service: &Service, prompt: String, options: &Options) -> i32 {
    let model = match pick_model(service, options.model.as_deref(), Purpose::Chat) {
        Ok(model) => model,
        Err(message) => return fail(&message),
    };
    let mut images = Vec::new();
    for image in &options.images {
        match existing_file(image, "Image") {
            Ok(path) => images.push(path),
            Err(message) => return fail(&message),
        }
    }
    if !images.is_empty() && model.kind != Kind::Vision {
        return fail(&format!("{} cannot see images; use a vision model (-m <vision model>)", model.id));
    }
    let mut messages: Vec<Value> = system_message(service, options).into_iter().collect();
    let mut user = json!({"role": "user", "content": prompt});
    if !images.is_empty() {
        user["images"] = json!(images);
    }
    messages.push(user);
    install_interrupt_handler();
    let backend = Backend::detect(service);
    let mut printer = Printer::new(true);
    match ask(&backend, service, &model, &messages, options, &mut printer) {
        Ok(done) => {
            printer.finish(&done);
            if done["finish_reason"] == "cancelled" {
                130
            } else {
                0
            }
        }
        Err(failure) => fail(&failure.message),
    }
}

const CHAT_HELP: &str = "Commands:
  /model [name]     Show or switch the model     /models   List chat models
  /image <path>     Attach an image to the next message (vision models)
  /system <text>    Replace the system prompt    /clear    Start over
  /think on|off     Toggle reasoning (models that support it)
  /save [file]      Save the conversation as Markdown
  /exit             Leave (also Ctrl-D; Ctrl-C stops an answer)";

fn save(messages: &[Value], model: &Model, target: Option<&str>) -> Result<PathBuf, String> {
    let path = match target.filter(|t| !t.is_empty()) {
        Some(target) => crate::util::expand_user(target),
        None => PathBuf::from(format!("chat-{}.md", media::stamp())),
    };
    let mut text = format!("# Chat with {}\n\n", model.id);
    for message in messages {
        let role = message["role"].as_str().unwrap_or("");
        let content = message["content"].as_str().unwrap_or("");
        let heading = match role {
            "system" => "System",
            "user" => "You",
            _ => "Assistant",
        };
        text.push_str(&format!("## {heading}\n\n{content}\n\n"));
    }
    let path = media::unique(&path);
    fs::write(&path, text).map_err(|error| error.to_string())?;
    Ok(path)
}

/// The interactive chat.
pub fn interactive(service: &Service, options: Options) -> i32 {
    let mut options = options;
    let mut model = match pick_model(service, options.model.as_deref(), Purpose::Chat) {
        Ok(model) => model,
        Err(message) => return fail(&message),
    };
    install_interrupt_handler();
    let backend = Backend::detect(service);
    let via = match backend {
        Backend::Remote(port) => format!(" via server :{port}"),
        Backend::Local => String::new(),
    };
    let tty = io::stdout().is_terminal();
    let dim = |text: &str| if tty { format!("\x1b[2m{text}\x1b[0m") } else { text.to_string() };
    println!("{}", dim(&format!("ul lm · {}{via} · /help for commands, Ctrl-D to leave", model.id)));
    let mut messages: Vec<Value> = system_message(service, &options).into_iter().collect();
    let mut pending_images: Vec<String> = Vec::new();
    let stdin = io::stdin();
    let mut lines = BufReader::new(stdin.lock()).lines();
    loop {
        print!("{}", if tty { "\x1b[1m›\x1b[0m " } else { "› " });
        let _ = io::stdout().flush();
        let Some(Ok(line)) = lines.next() else {
            println!();
            return 0;
        };
        let line = line.trim().to_string();
        if line.is_empty() {
            continue;
        }
        if let Some(command) = line.strip_prefix('/') {
            let (name, argument) = command.split_once(' ').map(|(n, a)| (n, a.trim())).unwrap_or((command, ""));
            match name {
                "exit" | "quit" | "q" => return 0,
                "help" | "?" => println!("{CHAT_HELP}"),
                "clear" | "reset" => {
                    messages = system_message(service, &options).into_iter().collect();
                    pending_images.clear();
                    println!("{}", dim("Context cleared."));
                }
                "model" if argument.is_empty() => println!("{} ({})", model.id, model.kind.name()),
                "model" => match service.resolve(Some(argument), Purpose::Chat) {
                    Ok(found) => {
                        model = found;
                        println!("{}", dim(&format!("Now using {}; context kept.", model.id)));
                    }
                    Err(failure) => eprintln!("{}", failure.message),
                },
                "models" => {
                    for candidate in service.models().iter().filter(|m| m.kind.generates()) {
                        let mark = if candidate.id == model.id { "*" } else { " " };
                        println!("{mark} {} ({})", candidate.id, candidate.kind.name());
                    }
                }
                "image" => match existing_file(argument, "Image") {
                    Ok(path) if model.kind == Kind::Vision => {
                        pending_images.push(path);
                        println!("{}", dim(&format!("Attached ({} image(s)); it goes with your next message.", pending_images.len())));
                    }
                    Ok(_) => eprintln!("{} cannot see images; switch with /model <vision model>", model.id),
                    Err(message) => eprintln!("{message}"),
                },
                "system" => {
                    options.system = Some(argument.to_string());
                    messages.retain(|m| m["role"] != "system");
                    if !argument.is_empty() {
                        messages.insert(0, json!({"role": "system", "content": argument}));
                    }
                    println!("{}", dim("System prompt set."));
                }
                "think" => {
                    options.think = match argument {
                        "on" | "true" | "yes" => Some(true),
                        "off" | "false" | "no" => Some(false),
                        _ => None,
                    };
                    println!("{}", dim(&format!("Reasoning: {}", match options.think { Some(true) => "on", Some(false) => "off", None => "model default" })));
                }
                "save" => match save(&messages, &model, Some(argument)) {
                    Ok(path) => println!("{}", dim(&format!("Saved {}", path.display()))),
                    Err(message) => eprintln!("{message}"),
                },
                _ => eprintln!("Unknown command /{name}; /help lists them"),
            }
            continue;
        }
        let mut user = json!({"role": "user", "content": line});
        if !pending_images.is_empty() {
            user["images"] = json!(std::mem::take(&mut pending_images));
        }
        messages.push(user);
        let mut printer = Printer::new(true);
        match ask(&backend, service, &model, &messages, &options, &mut printer) {
            Ok(done) => {
                printer.finish(&done);
                let text = done["text"].as_str().unwrap_or("");
                if done["finish_reason"] == "cancelled" && text.is_empty() {
                    messages.pop();
                } else {
                    messages.push(json!({"role": "assistant", "content": text}));
                }
            }
            Err(failure) => {
                println!();
                eprintln!("{}", failure.message);
                messages.pop();
            }
        }
    }
}

/// Run a media job with a progress line; Ctrl-C cancels it.
fn generate(service: &Service, purpose: Purpose, options: &Options, label: &str, job: Value) -> Result<(Model, Value), String> {
    let model = pick_model(service, options.model.as_deref(), purpose)?;
    install_interrupt_handler();
    INTERRUPTED.store(false, Ordering::SeqCst);
    GENERATING.store(true, Ordering::SeqCst);
    let mut progress = Progress::new(format!("{label} with {}", model.id));
    let result = Backend::detect(service).run(service, job, &model, |event| progress.update(event));
    GENERATING.store(false, Ordering::SeqCst);
    progress.clear();
    match result {
        Ok(done) if done["finish_reason"] == "cancelled" => Err("Stopped.".into()),
        Ok(done) => Ok((model, done)),
        Err(failure) => Err(failure.message),
    }
}

/// Where a result goes: `-o` (a folder or a file, never overwritten) or
/// `storage.root/generated/<kind>/`.
fn destination(service: &Service, options: &Options, kind: &str, prompt: &str, extension: &str) -> PathBuf {
    match options.output.as_deref() {
        Some(output) => {
            let path = absolute(output);
            if path.is_dir() {
                media::unique(&path.join(media::output_path(Path::new(""), kind, prompt, extension).file_name().unwrap_or_default()))
            } else if path.extension().is_none() {
                media::unique(&path.with_extension(extension))
            } else {
                media::unique(&path)
            }
        }
        None => media::output_path(&service.storage, kind, prompt, extension),
    }
}

fn reveal(path: &str, options: &Options, player: bool) {
    println!("{path}");
    if options.open {
        let program = if player { "afplay" } else { "open" };
        let _ = Command::new(program).arg(path).status();
    }
}

/// `ul lm image "prompt"`.
pub fn image(service: &Service, prompt: &str, options: &Options) -> i32 {
    let (width, height) = options.size.unwrap_or((1024, 1024));
    let output = destination(service, options, "images", prompt, "png");
    let mut job = json!({"op": "image", "prompt": prompt, "width": width, "height": height, "steps": options.steps, "seed": options.seed,
                         "quantize": options.quantize, "output": output});
    if let Some(init) = options.images.first() {
        match existing_file(init, "Image") {
            Ok(path) => {
                job["image"] = json!(path);
                job["strength"] = json!(options.strength);
            }
            Err(message) => return fail(&message),
        }
    }
    match generate(service, Purpose::Image, options, "drawing", job) {
        Ok((_, done)) => {
            if io::stderr().is_terminal() {
                eprintln!("\x1b[2m{}x{} · seed {} · {:.1}s\x1b[0m", done["width"], done["height"], done["seed"], done["stats"]["seconds"].as_f64().unwrap_or(0.0));
            }
            reveal(done["path"].as_str().unwrap_or_default(), options, false);
            0
        }
        Err(message) => fail(&message),
    }
}

/// `ul lm video "prompt"`.
pub fn video(service: &Service, prompt: &str, options: &Options) -> i32 {
    let output = destination(service, options, "videos", prompt, "mp4");
    let frames = options.frames.or(options.seconds.map(|s| (s * 24.0).round() as u64 + 1));
    let mut job = json!({"op": "video", "prompt": prompt, "width": options.size.map(|s| s.0), "height": options.size.map(|s| s.1),
                         "frames": frames, "steps": options.steps, "seed": options.seed, "output": output});
    if let Some(start) = options.images.first() {
        match existing_file(start, "Image") {
            Ok(path) => job["image"] = json!(path),
            Err(message) => return fail(&message),
        }
    }
    match generate(service, Purpose::Video, options, "filming", job) {
        Ok((_, done)) => {
            if io::stderr().is_terminal() {
                eprintln!(
                    "\x1b[2m{}x{} · {} frames · seed {} · {:.0}s\x1b[0m",
                    done["width"], done["height"], done["frames"], done["seed"], done["stats"]["seconds"].as_f64().unwrap_or(0.0)
                );
            }
            reveal(done["path"].as_str().unwrap_or_default(), options, false);
            0
        }
        Err(message) => fail(&message),
    }
}

/// `ul lm speak "text"`.
pub fn speak(service: &Service, text: &str, options: &Options) -> i32 {
    let output = destination(service, options, "speech", text, "wav");
    let job = json!({"op": "speak", "text": text, "voice": options.voice, "speed": options.speed, "language": options.language,
                     "instructions": options.system, "output": output});
    match generate(service, Purpose::Speak, options, "speaking", job) {
        Ok((_, done)) => {
            if io::stderr().is_terminal() {
                let voices = done["voices"].as_array().map(|v| v.iter().filter_map(Value::as_str).collect::<Vec<_>>().join(", ")).unwrap_or_default();
                let voice = done["voice"].as_str().map(|v| format!(" · voice {v}")).unwrap_or_default();
                let others = if voices.is_empty() { String::new() } else { format!(" (voices: {voices})") };
                eprintln!("\x1b[2m{:.1}s of audio{voice}{others}\x1b[0m", done["audio_seconds"].as_f64().unwrap_or(0.0));
            }
            reveal(done["path"].as_str().unwrap_or_default(), options, true);
            0
        }
        Err(message) => fail(&message),
    }
}

/// `ul lm music "style"`.
pub fn music(service: &Service, prompt: &str, options: &Options) -> i32 {
    let output = destination(service, options, "music", prompt, "wav");
    let lyrics = match options.lyrics.as_deref() {
        Some(lyrics) if absolute(lyrics).is_file() => fs::read_to_string(absolute(lyrics)).unwrap_or_default(),
        Some(lyrics) => lyrics.to_string(),
        None => String::new(),
    };
    let job = json!({"op": "music", "prompt": prompt, "lyrics": lyrics, "duration": options.seconds, "steps": options.steps,
                     "seed": options.seed, "output": output});
    match generate(service, Purpose::Music, options, "composing", job) {
        Ok((_, done)) => {
            reveal(done["path"].as_str().unwrap_or_default(), options, true);
            0
        }
        Err(message) => fail(&message),
    }
}

/// `ul lm embed`: vectors as JSON lines, one per input.
pub fn embed(service: &Service, texts: Vec<String>, options: &Options) -> i32 {
    match generate(service, Purpose::Embed, options, "embedding", json!({"op": "embed", "input": texts})) {
        Ok((_, done)) => {
            for vector in done["embeddings"].as_array().into_iter().flatten() {
                println!("{vector}");
            }
            0
        }
        Err(message) => fail(&message),
    }
}

/// `ul lm transcribe <audio or video>`.
pub fn transcribe(service: &Service, input: &Path, options: &Options) -> i32 {
    let input = match fs::canonicalize(input) {
        Ok(path) if path.is_file() => path,
        _ => return fail(&format!("Audio file not found: {}", input.display())),
    };
    let scratch = super::engine::engine_dir(&service.storage).join("uploads");
    let (audio, temporary) = match media::readable_audio(&input, &scratch) {
        Ok(found) => found,
        Err(message) => return fail(&message),
    };
    let job = json!({"op": "transcribe", "path": audio, "language": options.language});
    let result = generate(service, Purpose::Transcribe, options, "listening", job);
    if temporary {
        let _ = fs::remove_file(&audio);
    }
    match result {
        Ok((_, done)) => {
            let segments = done["segments"].as_array().cloned().unwrap_or_default();
            if options.json {
                println!("{}", json!({"text": done["text"], "language": done["language"], "segments": segments}));
            } else if options.srt && !segments.is_empty() {
                for (index, segment) in segments.iter().enumerate() {
                    let clock = |seconds: f64| {
                        let millis = (seconds.max(0.0) * 1000.0).round() as u64;
                        format!("{:02}:{:02}:{:02},{:03}", millis / 3_600_000, millis / 60_000 % 60, millis / 1000 % 60, millis % 1000)
                    };
                    println!(
                        "{}\n{} --> {}\n{}\n",
                        index + 1,
                        clock(segment["start"].as_f64().unwrap_or(0.0)),
                        clock(segment["end"].as_f64().unwrap_or(0.0)),
                        segment["text"].as_str().unwrap_or("").trim()
                    );
                }
            } else {
                println!("{}", done["text"].as_str().unwrap_or(""));
            }
            0
        }
        Err(message) => fail(&message),
    }
}
