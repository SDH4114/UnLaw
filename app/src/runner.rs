//! Running `ul` for the app: every command goes through the real `ul`, so
//! aliases, config, user overrides and timeouts behave as in the terminal. Each
//! run gets stdin from /dev/null, its own process group (a timeout kills
//! everything it started) and capped output.

use std::io::{BufRead, BufReader, Read};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

/// Output kept per stream; the rest is read and dropped so the child never blocks.
pub const MAX_OUTPUT: usize = 64 * 1024;
/// For JSON lists the app reads whole (`ul clip list 500 --json` passed 64 KB with
/// a few dozen copied texts, and a cut list does not parse).
pub const MAX_LIST_OUTPUT: usize = 8 * 1024 * 1024;

#[derive(Clone, Debug, PartialEq)]
pub struct Outcome {
    /// None when it was killed (timeout) or died from a signal.
    pub code: Option<i32>,
    pub stdout: String,
    pub stderr: String,
    pub timed_out: bool,
}

impl Outcome {
    pub fn ok(&self) -> bool {
        self.code == Some(0)
    }

    /// The last lines a person should see about this run.
    pub fn summary(&self, lines: usize) -> String {
        let text = if self.ok() || self.stderr.trim().is_empty() { &self.stdout } else { &self.stderr };
        let kept: Vec<&str> = text.lines().filter(|line| !line.trim().is_empty()).collect();
        let start = kept.len().saturating_sub(lines);
        let mut out = kept[start..].join("\n");
        if self.timed_out {
            out.push_str("\n(stopped: it took too long)");
        }
        strip_ansi(&out)
    }
}

/// Terminal colors out (a command may color its output even without a terminal).
pub fn strip_ansi(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut chars = text.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\u{1b}' {
            if chars.peek() == Some(&'[') {
                chars.next();
                for c in chars.by_ref() {
                    if ('@'..='~').contains(&c) {
                        break;
                    }
                }
            }
            continue;
        }
        if !c.is_control() || c == '\n' || c == '\t' {
            out.push(c);
        }
    }
    out
}

fn is_executable(path: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    path.metadata().is_ok_and(|meta| meta.is_file() && meta.permissions().mode() & 0o111 != 0)
}

/// The `ul` to run. Never `/usr/bin/ul`: macOS ships an unrelated `ul` there.
pub fn find_ul() -> Option<PathBuf> {
    if let Some(path) = std::env::var_os("UNLAW_BIN").map(PathBuf::from).filter(|path| is_executable(path)) {
        return Some(path);
    }
    let beside = std::env::current_exe().ok().and_then(|exe| exe.parent().map(|folder| folder.join("ul")));
    let local = crate::settings::home().join(".local/bin/ul");
    let on_path = std::env::var_os("PATH")
        .map(|path| std::env::split_paths(&path).map(|folder| folder.join("ul")).collect::<Vec<_>>())
        .unwrap_or_default();
    beside
        .into_iter()
        .chain([local, crate::settings::home().join(".cargo/bin/ul")])
        .chain(on_path)
        .find(|path| path != Path::new("/usr/bin/ul") && is_executable(path))
}

fn command(program: &Path, args: &[String]) -> Command {
    let mut command = Command::new(program);
    command
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env("UNLAW_APP", "1")
        .env("NO_COLOR", "1")
        .process_group(0);
    command
}

/// Output read by a background thread, up to `MAX_OUTPUT` bytes.
struct Collected {
    cap: usize,
    kept: Arc<Mutex<Vec<u8>>>,
    done: mpsc::Receiver<()>,
}

impl Collected {
    /// What was read, once the stream ends or after `wait` at most: a daemon the
    /// command started in its own session may hold the pipe open for hours, and
    /// the run must not wait for it (the reader thread is left to finish alone).
    fn finish(self, wait: Duration) -> String {
        let _ = self.done.recv_timeout(wait);
        let kept = self.kept.lock().map(|kept| kept.clone()).unwrap_or_default();
        let mut text = String::from_utf8_lossy(&kept).into_owned();
        // The cap may cut a character in two; drop the broken end.
        if kept.len() >= self.cap && text.ends_with('\u{FFFD}') {
            text.pop();
        }
        text
    }
}

fn collect(mut stream: impl Read + Send + 'static, cap: usize) -> Collected {
    let kept = Arc::new(Mutex::new(Vec::new()));
    let (sender, done) = mpsc::channel();
    let shared = kept.clone();
    thread::spawn(move || {
        let mut buffer = [0u8; 8192];
        while let Ok(read) = stream.read(&mut buffer) {
            if read == 0 {
                break;
            }
            if let Ok(mut kept) = shared.lock() {
                let room = cap.saturating_sub(kept.len());
                kept.extend_from_slice(&buffer[..read.min(room)]);
            }
        }
        let _ = sender.send(());
    });
    Collected { cap, kept, done }
}

/// How long the output readers get after the command has ended.
const DRAIN: Duration = Duration::from_secs(1);

/// Whether the child has exited, without reaping it: while the zombie exists its
/// pid (and so its process group id) cannot be reused, so signalling the group
/// afterwards never reaches an unrelated process.
fn exited(child: &Child) -> bool {
    peek(child) != Peek::Running
}

#[derive(PartialEq)]
enum Peek {
    Running,
    /// Exited, not reaped: the group id is still ours.
    Exited,
    /// Already reaped (by `wait`/`try_wait`): its pid may belong to another process now.
    Reaped,
}

fn peek(child: &Child) -> Peek {
    let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
    // SAFETY: waitid on our own child with WNOWAIT only peeks at its state.
    let result = unsafe {
        libc::waitid(libc::P_PID, child.id() as libc::id_t, &mut info, libc::WEXITED | libc::WNOHANG | libc::WNOWAIT)
    };
    match result {
        0 if unsafe { info.si_pid() } != 0 => Peek::Exited,
        0 => Peek::Running,
        _ => Peek::Reaped,
    }
}

fn kill_group(child: &Child, signal: libc::c_int) {
    // SAFETY: kill(2) on the process group our child leads; the leader is not yet
    // reaped (see `exited`), so the group id still belongs to it.
    unsafe { libc::kill(-(child.id() as libc::pid_t), signal) };
}

/// SIGTERM to the whole group, then SIGKILL after a grace period; reaps the child.
/// A child that was already reaped is left alone: its pid may belong to someone else now.
pub fn stop_group(child: &mut Child, grace: Duration) {
    if peek(child) == Peek::Reaped {
        return;
    }
    if !exited(child) {
        kill_group(child, libc::SIGTERM);
        let deadline = Instant::now() + grace;
        while Instant::now() < deadline && !exited(child) {
            thread::sleep(Duration::from_millis(25));
        }
    }
    kill_group(child, libc::SIGKILL);
    let _ = child.wait();
}

/// Run to the end, or stop it after `timeout`.
pub fn run(program: &Path, args: &[String], timeout: Duration) -> Outcome {
    run_capped(program, args, timeout, MAX_OUTPUT)
}

/// `run` keeping up to `cap` bytes of each stream (`MAX_LIST_OUTPUT` for JSON lists).
pub fn run_capped(program: &Path, args: &[String], timeout: Duration, cap: usize) -> Outcome {
    let mut child = match command(program, args).spawn() {
        Ok(child) => child,
        Err(error) => {
            return Outcome {
                code: Some(127),
                stdout: String::new(),
                stderr: format!("could not start {}: {error}", program.display()),
                timed_out: false,
            }
        }
    };
    let stdout = collect(child.stdout.take().expect("piped"), cap);
    let stderr = collect(child.stderr.take().expect("piped"), MAX_OUTPUT);
    let deadline = Instant::now() + timeout;
    let mut timed_out = false;
    while !exited(&child) {
        if Instant::now() >= deadline {
            timed_out = true;
            break;
        }
        thread::sleep(Duration::from_millis(20));
    }
    if timed_out {
        stop_group(&mut child, Duration::from_secs(2));
    } else {
        // Children the command left running in its group would keep the pipes open.
        kill_group(&child, libc::SIGKILL);
    }
    let code = if timed_out { None } else { child.wait().ok().and_then(|status| status.code()) };
    Outcome { code, stdout: stdout.finish(DRAIN), stderr: stderr.finish(DRAIN), timed_out }
}

const PATH_MARK: &str = "__UNLAW_PATH__";

/// The PATH a login shell prints after the marker (shell start-up files may
/// print other things first).
pub fn path_after_mark(output: &str) -> Option<String> {
    let path = output.rsplit_once(PATH_MARK)?.1.lines().next()?.trim();
    (!path.is_empty() && path.contains('/') && !path.chars().any(char::is_control)).then(|| path.to_string())
}

/// Opened from the Dock or Finder, a Mac app gets PATH=/usr/bin:/bin:/usr/sbin:/sbin,
/// so commands would find macOS' old python3 and miss Homebrew. Ask the user's
/// login shell for its PATH (what VS Code does), at most 4 s; else add the usual folders.
pub fn adopt_login_path() {
    let shell = std::env::var("SHELL").ok().filter(|shell| shell.starts_with('/')).unwrap_or_else(|| "/bin/zsh".into());
    let script = format!("printf '\\n{PATH_MARK}%s\\n' \"$PATH\"");
    let outcome = run(Path::new(&shell), &["-ilc".into(), script], Duration::from_secs(4));
    let found = path_after_mark(&outcome.stdout);
    let current = std::env::var("PATH").unwrap_or_default();
    let home = crate::settings::home();
    let usual = [home.join(".local/bin"), PathBuf::from("/opt/homebrew/bin"), PathBuf::from("/usr/local/bin")];
    let mut parts: Vec<String> = found.map(|path| path.split(':').map(str::to_string).collect()).unwrap_or_default();
    for folder in usual.iter().map(|folder| folder.display().to_string()).chain(current.split(':').map(str::to_string))
    {
        if !folder.is_empty() && !parts.contains(&folder) {
            parts.push(folder);
        }
    }
    std::env::set_var("PATH", parts.join(":"));
}

/// The first local page address in a line: `http://127.0.0.1:PORT/...` or
/// `http://localhost:PORT/...` (a desk-like command prints it when it is ready).
pub fn local_url(line: &str) -> Option<String> {
    let start = ["http://127.0.0.1:", "http://localhost:"].iter().filter_map(|prefix| line.find(prefix)).min()?;
    let url: String = line[start..].chars().take_while(|c| !c.is_whitespace() && *c != '"' && *c != '\'').collect();
    let rest = url.split_once("://").map(|(_, rest)| rest)?;
    let (_, after_host) = rest.split_once(':')?;
    let port: String = after_host.chars().take_while(char::is_ascii_digit).collect();
    // Right after the port only a path, query or the end: `127.0.0.1:80@evil.com`
    // would make another host the window's own origin.
    let next = after_host[port.len()..].chars().next();
    let clean = matches!(next, None | Some('/' | '?' | '#'));
    (clean && !port.is_empty() && port.parse::<u16>().is_ok()).then_some(url)
}

/// A command that serves a page: started in the background; returns it and its
/// address once printed. The rest of its output is read and dropped.
pub fn serve(program: &Path, args: &[String], wait: Duration) -> Result<(Child, String), String> {
    let mut child = command(program, args).spawn().map_err(|error| format!("could not start: {error}"))?;
    let stdout = child.stdout.take().expect("piped");
    let stderr = collect(child.stderr.take().expect("piped"), MAX_OUTPUT);
    let (sender, receiver) = mpsc::channel();
    thread::spawn(move || {
        let mut sent = false;
        // Read to the end, bytes not UTF-8 lines: stopping early would close the
        // pipe and the server would die of SIGPIPE on its next print.
        let mut reader = BufReader::new(stdout);
        let mut line = Vec::new();
        while matches!(reader.read_until(b'\n', &mut line), Ok(read) if read > 0) {
            if !sent {
                if let Some(url) = local_url(&String::from_utf8_lossy(&line)) {
                    let _ = sender.send(url);
                    sent = true;
                }
            }
            line.clear();
        }
    });
    match receiver.recv_timeout(wait) {
        Ok(url) => Ok((child, url)),
        Err(_) => {
            stop_group(&mut child, Duration::from_secs(2));
            let text = stderr.finish(DRAIN);
            let reason = strip_ansi(text.trim());
            Err(if reason.is_empty() { "it printed no local address".into() } else { reason })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sh(script: &str) -> (PathBuf, Vec<String>) {
        (PathBuf::from("/bin/sh"), vec!["-c".into(), script.into()])
    }

    #[test]
    fn a_daemon_holding_the_pipe_does_not_hold_the_run() {
        // The daemon gets its own session (out of reach of the group kill) and
        // inherits stdout, like a supervisor a command starts and leaves running.
        let (program, args) = sh(
            "python3 -c 'import subprocess; subprocess.Popen([\"sleep\", \"4\"], start_new_session=True)'; echo started",
        );
        let begun = Instant::now();
        let outcome = run(&program, &args, Duration::from_secs(10));
        assert!(begun.elapsed() < Duration::from_secs(3), "waited {:?} for the daemon", begun.elapsed());
        assert_eq!((outcome.code, outcome.stdout.as_str()), (Some(0), "started\n"));
    }

    #[test]
    fn the_login_path_is_read_after_the_marker() {
        assert_eq!(
            path_after_mark("motd\n__UNLAW_PATH__/opt/homebrew/bin:/usr/bin\n").as_deref(),
            Some("/opt/homebrew/bin:/usr/bin")
        );
        assert_eq!(path_after_mark("no marker"), None);
        assert_eq!(path_after_mark("__UNLAW_PATH__\n"), None);
    }

    #[test]
    fn a_reaped_child_is_never_signalled() {
        let (program, args) = sh("exit 0");
        let mut child = command(&program, &args).spawn().unwrap();
        child.wait().unwrap();
        // Would SIGTERM/SIGKILL a reused process group before the fix; now returns at once.
        stop_group(&mut child, Duration::from_secs(1));
    }

    #[test]
    fn output_and_exit_code() {
        let (program, args) = sh("echo out; echo err >&2; exit 3");
        let outcome = run(&program, &args, Duration::from_secs(5));
        assert_eq!((outcome.code, outcome.stdout.as_str(), outcome.stderr.as_str()), (Some(3), "out\n", "err\n"));
        assert_eq!(outcome.summary(5), "err");
    }

    #[test]
    fn stdin_is_closed_and_env_is_set() {
        let (program, args) = sh("read line || echo no-stdin; echo $UNLAW_APP");
        assert_eq!(run(&program, &args, Duration::from_secs(5)).stdout, "no-stdin\n1\n");
    }

    #[test]
    fn a_hanging_command_and_its_children_are_stopped() {
        let marker = std::env::temp_dir().join(format!("unlaw-app-runner-{}", std::process::id()));
        let script = format!("(sleep 3; touch {}) & sleep 30", marker.display());
        let (program, args) = sh(&script);
        let started = Instant::now();
        let outcome = run(&program, &args, Duration::from_millis(300));
        assert!(outcome.timed_out && outcome.code.is_none());
        assert!(started.elapsed() < Duration::from_secs(5));
        thread::sleep(Duration::from_millis(3500));
        assert!(!marker.exists(), "the background child was killed with the group");
    }

    #[test]
    fn huge_output_is_capped() {
        let (program, args) = sh("head -c 1000000 /dev/zero | tr '\\0' x");
        let outcome = run(&program, &args, Duration::from_secs(10));
        assert_eq!((outcome.code, outcome.stdout.len()), (Some(0), MAX_OUTPUT));
    }

    #[test]
    fn a_list_keeps_more_than_the_normal_cap() {
        let (program, args) = sh("head -c 100000 /dev/zero | tr '\\0' x");
        let outcome = run_capped(&program, &args, Duration::from_secs(10), MAX_LIST_OUTPUT);
        assert_eq!((outcome.code, outcome.stdout.len()), (Some(0), 100_000));
    }

    #[test]
    fn missing_program() {
        let outcome = run(Path::new("/nonexistent/ul"), &[], Duration::from_secs(1));
        assert_eq!(outcome.code, Some(127));
        assert!(outcome.stderr.contains("could not start"));
    }

    #[test]
    fn local_addresses() {
        assert_eq!(
            local_url("Desk: http://127.0.0.1:8765/?token=ab").as_deref(),
            Some("http://127.0.0.1:8765/?token=ab")
        );
        assert_eq!(local_url("at \"http://localhost:3000\" now").as_deref(), Some("http://localhost:3000"));
        assert_eq!(local_url("http://example.com:80/"), None);
        assert_eq!(local_url("http://127.0.0.1:/x"), None);
        assert_eq!(local_url("http://127.0.0.1:99999/"), None);
        assert_eq!(local_url("http://127.0.0.1:8765@evil.com/"), None);
        assert_eq!(local_url("http://127.0.0.1:8765?t=1").as_deref(), Some("http://127.0.0.1:8765?t=1"));
    }

    #[test]
    fn serve_reads_the_address_and_keeps_running() {
        let (program, args) = sh("echo starting; echo 'Page: http://127.0.0.1:4321/?t=1'; sleep 30");
        let (mut child, url) = serve(&program, &args, Duration::from_secs(5)).unwrap();
        assert_eq!(url, "http://127.0.0.1:4321/?t=1");
        assert!(child.try_wait().unwrap().is_none());
        stop_group(&mut child, Duration::from_secs(2));
        let (program, args) = sh("echo broken >&2; exit 1");
        assert_eq!(serve(&program, &args, Duration::from_secs(5)).unwrap_err(), "broken");
    }

    #[test]
    fn ansi_is_stripped() {
        assert_eq!(strip_ansi("\u{1b}[1;31mred\u{1b}[0m ok\u{7}"), "red ok");
    }
}
