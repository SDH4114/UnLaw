//! Supervisor for the Python MLX worker. The worker is a separate process
//! that speaks JSON lines over stdin/stdout, so a crash inside MLX (or an
//! out-of-memory kill) never takes the CLI or the HTTP server down: pending
//! requests get a clear error and the next request starts a fresh worker.
//! An idle worker is stopped, which returns all of its memory to macOS.

use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::os::unix::process::CommandExt;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicI32, AtomicU64, Ordering};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex, PoisonError};
use std::thread;
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use super::store::{human_size, Model};

/// How to start the worker: the engine's interpreter and script.
#[derive(Clone, Debug)]
pub struct Launch {
    pub python: PathBuf,
    pub script: PathBuf,
    pub log: PathBuf,
}

/// An error with a stable code for API clients and a human message.
#[derive(Clone, Debug, PartialEq)]
pub struct Failure {
    pub code: String,
    pub message: String,
}

impl Failure {
    pub fn new(code: &str, message: impl Into<String>) -> Failure {
        Failure { code: code.into(), message: message.into() }
    }

    /// HTTP status that matches the error code.
    pub fn status(&self) -> u16 {
        match self.code.as_str() {
            "model_not_found" | "not_found" => 404,
            "invalid_request" | "unsupported_model" | "bad_image" => 400,
            "out_of_memory" => 507,
            "worker_crashed" | "engine_unavailable" => 503,
            _ => 500,
        }
    }
}

impl std::fmt::Display for Failure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}

type Pending = Arc<Mutex<HashMap<u64, Sender<Value>>>>;

/// Process groups of live workers (each leads its own), readable from a
/// signal handler: stopping `ul` must not leave llama.cpp or a generator
/// holding gigabytes of memory.
static GROUPS: [AtomicI32; 32] = [const { AtomicI32::new(0) }; 32];

fn remember_group(group: i32) {
    for slot in &GROUPS {
        if slot.compare_exchange(0, group, Ordering::SeqCst, Ordering::SeqCst).is_ok() {
            return;
        }
    }
}

fn end_group(group: i32) {
    // SAFETY: plain signal to a process group this process created.
    unsafe { libc::killpg(group, libc::SIGKILL) };
    for slot in &GROUPS {
        let _ = slot.compare_exchange(group, 0, Ordering::SeqCst, Ordering::SeqCst);
    }
}

/// Kill every worker group; async-signal-safe (atomics and killpg only).
pub fn end_all_workers() {
    for slot in &GROUPS {
        let group = slot.swap(0, Ordering::SeqCst);
        if group > 0 {
            // SAFETY: killpg is async-signal-safe.
            unsafe { libc::killpg(group, libc::SIGKILL) };
        }
    }
}

extern "C" fn on_stop_signal(signal: libc::c_int) {
    end_all_workers();
    // SAFETY: _exit is async-signal-safe.
    unsafe { libc::_exit(128 + signal) };
}

/// Ctrl-C, `kill` and a closed terminal end the workers with this process.
pub fn end_workers_on_signals() {
    for signal in [libc::SIGINT, libc::SIGTERM, libc::SIGHUP] {
        // SAFETY: the handler only uses async-signal-safe calls.
        unsafe { libc::signal(signal, on_stop_signal as *const () as libc::sighandler_t) };
    }
}

struct Running {
    child: Child,
    stdin: ChildStdin,
    pending: Pending,
    alive: Arc<AtomicBool>,
}

struct State {
    running: Option<Running>,
    /// Model ids the worker reports as loaded.
    loaded: Arc<Mutex<Vec<String>>>,
    last_used: Instant,
    busy: usize,
}

pub struct Supervisor {
    launch: Launch,
    state: Mutex<State>,
    next_id: AtomicU64,
    /// Fraction of physical memory a model may take (weights × 1.2).
    memory_limit: u64,
}

/// Physical memory in bytes (`sysctl hw.memsize`).
pub fn physical_memory() -> u64 {
    let mut value: u64 = 0;
    let mut size = std::mem::size_of::<u64>();
    let name = c"hw.memsize";
    // SAFETY: hw.memsize is a u64 and `size` describes `value` exactly.
    let result = unsafe {
        libc::sysctlbyname(name.as_ptr(), (&mut value as *mut u64).cast(), &mut size, std::ptr::null_mut(), 0)
    };
    if result == 0 {
        value
    } else {
        0
    }
}

/// The last lines this worker wrote, skipping earlier runs in the same log.
fn log_tail(path: &PathBuf, offset: u64) -> String {
    let bytes = fs::read(path).unwrap_or_default();
    let text = String::from_utf8_lossy(bytes.get(offset as usize..).unwrap_or_default());
    let lines: Vec<&str> = text.lines().map(str::trim).filter(|line| !line.is_empty() && !line.starts_with("warnings.warn")).collect();
    lines[lines.len().saturating_sub(3)..].join(" | ")
}

const MAX_LOG: u64 = 5 * 1024 * 1024;

impl Supervisor {
    pub fn new(launch: Launch) -> Arc<Supervisor> {
        let memory = physical_memory();
        Arc::new(Supervisor {
            launch,
            state: Mutex::new(State {
                running: None,
                loaded: Arc::new(Mutex::new(Vec::new())),
                last_used: Instant::now(),
                busy: 0,
            }),
            next_id: AtomicU64::new(1),
            memory_limit: if memory == 0 { u64::MAX } else { memory / 4 * 3 },
        })
    }

    /// Stop the worker after `idle` without requests; zero keeps it forever.
    pub fn reap_when_idle(self: &Arc<Self>, idle: Duration) {
        if idle.is_zero() {
            return;
        }
        let supervisor = Arc::downgrade(self);
        thread::spawn(move || loop {
            thread::sleep(Duration::from_secs(5).min(idle));
            let Some(supervisor) = supervisor.upgrade() else { return };
            let mut state = supervisor.state.lock().unwrap_or_else(PoisonError::into_inner);
            if state.busy == 0 && state.running.is_some() && state.last_used.elapsed() >= idle {
                Self::stop_locked(&mut state);
            }
        });
    }

    pub fn loaded(&self) -> Vec<String> {
        let state = self.state.lock().unwrap_or_else(PoisonError::into_inner);
        let alive = state.running.as_ref().is_some_and(|running| running.alive.load(Ordering::SeqCst));
        if alive {
            state.loaded.lock().unwrap_or_else(PoisonError::into_inner).clone()
        } else {
            Vec::new()
        }
    }

    /// Requests in flight.
    pub fn busy(&self) -> usize {
        self.state.lock().unwrap_or_else(PoisonError::into_inner).busy
    }

    /// Stop the worker unless it is working; true when it was stopped.
    pub fn stop_if_idle(&self) -> bool {
        let mut state = self.state.lock().unwrap_or_else(PoisonError::into_inner);
        if state.busy > 0 || state.running.is_none() {
            return false;
        }
        Self::stop_locked(&mut state);
        true
    }

    fn stop_locked(state: &mut State) {
        if let Some(mut running) = state.running.take() {
            // The worker leads its own process group: this also ends what it
            // started (llama.cpp servers, image and video generators).
            if let Ok(group) = i32::try_from(running.child.id()) {
                end_group(group);
            }
            let _ = running.child.kill();
            let _ = running.child.wait();
        }
        state.loaded.lock().unwrap_or_else(PoisonError::into_inner).clear();
    }

    fn spawn(&self, state: &mut State) -> Result<(), Failure> {
        Self::stop_locked(state);
        if let Some(parent) = self.launch.log.parent() {
            let _ = fs::create_dir_all(parent);
        }
        if fs::metadata(&self.launch.log).is_ok_and(|meta| meta.len() > MAX_LOG) {
            let _ = fs::remove_file(&self.launch.log);
        }
        let offset = fs::metadata(&self.launch.log).map(|meta| meta.len()).unwrap_or(0);
        let log = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.launch.log)
            .map_err(|error| Failure::new("engine_unavailable", format!("Cannot open {}: {error}", self.launch.log.display())))?;
        let mut child = Command::new(&self.launch.python)
            .arg("-u")
            .arg(&self.launch.script)
            .arg("serve")
            .env("HF_HUB_OFFLINE", "1")
            .env("TOKENIZERS_PARALLELISM", "false")
            .env("PYTHONUNBUFFERED", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(log)
            // Its own process group: Ctrl-C in a chat cancels the answer
            // instead of killing the loaded model.
            .process_group(0)
            .spawn()
            .map_err(|error| {
                Failure::new("engine_unavailable", format!("Cannot start the MLX worker {}: {error}", self.launch.python.display()))
            })?;
        let group = i32::try_from(child.id()).unwrap_or(0);
        remember_group(group);
        let stdin = child.stdin.take().expect("piped stdin");
        let stdout = child.stdout.take().expect("piped stdout");
        let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
        let alive = Arc::new(AtomicBool::new(true));
        let loaded = Arc::new(Mutex::new(Vec::new()));
        state.loaded = loaded.clone();
        {
            let pending = pending.clone();
            let alive = alive.clone();
            let log = self.launch.log.clone();
            thread::spawn(move || {
                for line in BufReader::new(stdout).lines() {
                    let Ok(line) = line else { break };
                    let Ok(event) = serde_json::from_str::<Value>(&line) else { continue };
                    if let Some(models) = event.get("loaded").and_then(Value::as_array) {
                        *loaded.lock().unwrap_or_else(PoisonError::into_inner) = models.iter().filter_map(|m| m.as_str().map(str::to_string)).collect();
                    }
                    let Some(id) = event.get("id").and_then(Value::as_u64) else { continue };
                    let finished = matches!(event.get("event").and_then(Value::as_str), Some("done" | "error"));
                    let mut pending = pending.lock().unwrap_or_else(PoisonError::into_inner);
                    if let Some(sender) = pending.get(&id) {
                        let _ = sender.send(event);
                    }
                    if finished {
                        pending.remove(&id);
                    }
                }
                alive.store(false, Ordering::SeqCst);
                // A crashed worker must not leave its llama.cpp server behind.
                if group > 0 {
                    end_group(group);
                }
                loaded.lock().unwrap_or_else(PoisonError::into_inner).clear();
                let tail = log_tail(&log, offset);
                let message = if tail.is_empty() {
                    format!(
                        "The MLX worker was killed (out of memory, or by another process); the next request starts a new one. Log: {}",
                        log.display()
                    )
                } else {
                    format!("The MLX worker stopped unexpectedly: {tail} (full log: {})", log.display())
                };
                for (id, sender) in pending.lock().unwrap_or_else(PoisonError::into_inner).drain() {
                    let _ = sender.send(json!({"id": id, "event": "error", "code": "worker_crashed", "message": message}));
                }
            });
        }
        state.running = Some(Running { child, stdin, pending, alive });
        Ok(())
    }

    fn check_memory(&self, model: &Model, loaded: &[String]) -> Result<(), Failure> {
        if loaded.contains(&model.id) {
            return Ok(());
        }
        let needed = model.load_bytes() / 5 * 6;
        if needed > self.memory_limit {
            return Err(Failure::new(
                "out_of_memory",
                format!(
                    "{} needs about {} of memory but this Mac allows {} for models; choose a smaller or more quantized \
                     model (e.g. a 4bit build) or quantize it with `ul lm convert {} --bits 4`",
                    model.id,
                    human_size(needed),
                    human_size(self.memory_limit),
                    model.id
                ),
            ));
        }
        Ok(())
    }

    /// Send one job and receive its events; the worker is started (or
    /// restarted after a crash) on demand.
    fn submit(&self, mut job: Value, model: Option<&Model>) -> Result<(u64, Receiver<Value>), Failure> {
        let mut state = self.state.lock().unwrap_or_else(PoisonError::into_inner);
        let alive = state.running.as_ref().is_some_and(|running| running.alive.load(Ordering::SeqCst));
        if !alive {
            self.spawn(&mut state)?;
        }
        if let Some(model) = model {
            let loaded = state.loaded.lock().unwrap_or_else(PoisonError::into_inner).clone();
            self.check_memory(model, &loaded)?;
        }
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        job["id"] = json!(id);
        let (sender, receiver) = mpsc::channel();
        let running = state.running.as_mut().expect("worker was just started");
        running.pending.lock().unwrap_or_else(PoisonError::into_inner).insert(id, sender);
        let line = format!("{job}\n");
        if running.stdin.write_all(line.as_bytes()).and_then(|_| running.stdin.flush()).is_err() {
            running.pending.lock().unwrap_or_else(PoisonError::into_inner).remove(&id);
            Self::stop_locked(&mut state);
            return Err(Failure::new("worker_crashed", "The MLX worker stopped accepting requests; try again"));
        }
        state.busy += 1;
        state.last_used = Instant::now();
        Ok((id, receiver))
    }

    fn cancel(&self, id: u64) {
        let mut state = self.state.lock().unwrap_or_else(PoisonError::into_inner);
        if let Some(running) = state.running.as_mut() {
            let _ = writeln!(running.stdin, "{}", json!({"op": "cancel", "target": id}));
            let _ = running.stdin.flush();
        }
    }

    fn finish(&self) {
        let mut state = self.state.lock().unwrap_or_else(PoisonError::into_inner);
        state.busy = state.busy.saturating_sub(1);
        state.last_used = Instant::now();
    }

    /// Run a job to completion. `on_event` sees every streamed event and
    /// returns false to cancel (client gone, Ctrl-C); the final `done` event
    /// is returned either way.
    pub fn call(&self, job: Value, model: Option<&Model>, mut on_event: impl FnMut(&Value) -> bool) -> Result<Value, Failure> {
        let (id, receiver) = self.submit(job, model)?;
        let mut cancelled = false;
        let result = loop {
            let event = match receiver.recv_timeout(Duration::from_millis(200)) {
                Ok(event) => event,
                Err(mpsc::RecvTimeoutError::Timeout) => {
                    if !cancelled && !on_event(&json!({"event": "tick"})) {
                        cancelled = true;
                        self.cancel(id);
                    }
                    continue;
                }
                Err(mpsc::RecvTimeoutError::Disconnected) => {
                    break Err(Failure::new("worker_crashed", "The MLX worker stopped unexpectedly; try again"))
                }
            };
            match event.get("event").and_then(Value::as_str) {
                Some("done") => break Ok(event),
                Some("error") => {
                    let field = |key: &str| event.get(key).and_then(Value::as_str).unwrap_or("").to_string();
                    break Err(Failure { code: field("code"), message: field("message") });
                }
                _ => {
                    if !cancelled && !on_event(&event) {
                        cancelled = true;
                        self.cancel(id);
                    }
                }
            }
        };
        self.finish();
        result
    }
}

impl Drop for Supervisor {
    fn drop(&mut self) {
        if let Ok(mut state) = self.state.lock() {
            Self::stop_locked(&mut state);
        }
    }
}

#[cfg(test)]
pub mod tests {
    use super::*;
    use crate::builtin::lm::store::{tests::scratch, Kind};

    /// A worker that echoes jobs, streams two tokens, crashes on request and
    /// honours cancellation, written in Python like the real one.
    pub const FAKE_WORKER: &str = r#"
import json, os, sys, threading, time
cancelled = set()
jobs = []
lock = threading.Condition()
def emit(event):
    sys.stdout.write(json.dumps(event) + "\n"); sys.stdout.flush()
def reader():
    for line in sys.stdin:
        job = json.loads(line)
        with lock:
            if job.get("op") == "cancel":
                cancelled.add(job["target"])
            else:
                jobs.append(job)
            lock.notify()
    os._exit(0)
threading.Thread(target=reader, daemon=True).start()
while True:
    with lock:
        while not jobs:
            lock.wait()
        job = jobs.pop(0)
    op, ident = job["op"], job["id"]
    if op == "crash":
        sys.stderr.write("Traceback: boom\n"); sys.stderr.flush(); os._exit(3)
    if op == "fail":
        emit({"id": ident, "event": "error", "code": "invalid_request", "message": "bad"}); continue
    model = job.get("model", {}).get("id")
    emit({"loaded": [model] if model else []})
    text = ""
    for piece in ["Hel", "lo"]:
        if ident in cancelled:
            break
        text += piece
        emit({"id": ident, "event": "token", "text": piece})
        time.sleep(float(job.get("delay", 0)))
    reason = "cancelled" if ident in cancelled else "stop"
    emit({"id": ident, "event": "done", "text": text, "finish_reason": reason, "pid": os.getpid(), "job": job})
"#;

    pub fn fake_launch(name: &str) -> Launch {
        let dir = scratch(name);
        let script = dir.join("worker.py");
        fs::write(&script, FAKE_WORKER).unwrap();
        let python = crate::commands::python(None).expect("python3 is needed for lm tests");
        Launch { python, script, log: dir.join("worker.log") }
    }

    fn model(id: &str, bytes: u64) -> Model {
        Model { id: id.into(), path: "/x".into(), kind: Kind::Text, bytes, partial: false, root: "/x".into(), gguf: None }
    }

    #[test]
    fn jobs_stream_tokens_and_finish() {
        let supervisor = Supervisor::new(fake_launch("stream"));
        let mut tokens = Vec::new();
        let done = supervisor
            .call(json!({"op": "chat", "model": {"id": "a/b"}}), Some(&model("a/b", 10)), |event| {
                if let Some(text) = event.get("text").and_then(Value::as_str) {
                    tokens.push(text.to_string());
                }
                true
            })
            .unwrap();
        assert_eq!(tokens, ["Hel", "lo"]);
        assert_eq!(done["text"], "Hello");
        assert_eq!(done["job"]["model"]["id"], "a/b");
        assert_eq!(supervisor.loaded(), ["a/b"]);
        let error = supervisor.call(json!({"op": "fail"}), None, |_| true).unwrap_err();
        assert_eq!((error.code.as_str(), error.status()), ("invalid_request", 400));
    }

    #[test]
    fn a_crash_fails_the_request_and_the_next_one_restarts_the_worker() {
        let supervisor = Supervisor::new(fake_launch("crash"));
        let first = supervisor.call(json!({"op": "chat"}), None, |_| true).unwrap();
        let error = supervisor.call(json!({"op": "crash"}), None, |_| true).unwrap_err();
        assert_eq!(error.code, "worker_crashed");
        assert!(error.message.contains("Traceback: boom"), "{}", error.message);
        assert!(supervisor.loaded().is_empty());
        let second = supervisor.call(json!({"op": "chat"}), None, |_| true).unwrap();
        assert_ne!(first["pid"], second["pid"]);
    }

    #[test]
    fn cancelling_stops_generation() {
        let supervisor = Supervisor::new(fake_launch("cancel"));
        let done = supervisor.call(json!({"op": "chat", "delay": 0.5}), None, |event| event["event"] != "token").unwrap();
        assert_eq!((done["text"].as_str(), done["finish_reason"].as_str()), (Some("Hel"), Some("cancelled")));
    }

    #[test]
    fn oversized_models_are_refused_before_loading() {
        let supervisor = Supervisor::new(fake_launch("memory"));
        let error = supervisor.call(json!({"op": "chat"}), Some(&model("huge/model", u64::MAX / 2)), |_| true).unwrap_err();
        assert_eq!((error.code.as_str(), error.status()), ("out_of_memory", 507));
        assert!(error.message.contains("ul lm convert huge/model --bits 4"));
        assert!(physical_memory() > 1 << 30);
    }

    #[test]
    fn idle_workers_are_stopped() {
        let supervisor = Supervisor::new(fake_launch("idle"));
        supervisor.reap_when_idle(Duration::from_millis(300));
        supervisor.call(json!({"op": "chat", "model": {"id": "a/b"}}), None, |_| true).unwrap();
        assert_eq!(supervisor.loaded(), ["a/b"]);
        thread::sleep(Duration::from_millis(1500));
        assert!(supervisor.loaded().is_empty());
        assert!(supervisor.state.lock().unwrap().running.is_none());
    }
}
