//! Running `ul` for the app: every command goes through the real `ul`, so
//! aliases, config, user overrides and timeouts behave as in the terminal. Each
//! run gets stdin from /dev/null, its own process group (a timeout kills
//! everything it started) and capped output.

use std::io::{BufRead, BufReader, Read};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

/// Output kept per stream; the rest is read and dropped so the child never blocks.
pub const MAX_OUTPUT: usize = 64 * 1024;

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

fn collect(mut stream: impl Read + Send + 'static) -> thread::JoinHandle<String> {
    thread::spawn(move || {
        let mut kept = Vec::new();
        let mut buffer = [0u8; 8192];
        while let Ok(read) = stream.read(&mut buffer) {
            if read == 0 {
                break;
            }
            let room = MAX_OUTPUT.saturating_sub(kept.len());
            kept.extend_from_slice(&buffer[..read.min(room)]);
        }
        String::from_utf8_lossy(&kept).into_owned()
    })
}

/// Whether the child has exited, without reaping it: while the zombie exists its
/// pid (and so its process group id) cannot be reused, so signalling the group
/// afterwards never reaches an unrelated process.
fn exited(child: &Child) -> bool {
    let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
    // SAFETY: waitid on our own child with WNOWAIT only peeks at its state.
    let result = unsafe {
        libc::waitid(libc::P_PID, child.id() as libc::id_t, &mut info, libc::WEXITED | libc::WNOHANG | libc::WNOWAIT)
    };
    result == 0 && unsafe { info.si_pid() } != 0
}

fn kill_group(child: &Child, signal: libc::c_int) {
    // SAFETY: kill(2) on the process group our child leads; the leader is not yet
    // reaped (see `exited`), so the group id still belongs to it.
    unsafe { libc::kill(-(child.id() as libc::pid_t), signal) };
}

/// SIGTERM to the whole group, then SIGKILL after a grace period; reaps the child.
pub fn stop_group(child: &mut Child, grace: Duration) {
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
    let stdout = collect(child.stdout.take().expect("piped"));
    let stderr = collect(child.stderr.take().expect("piped"));
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
    Outcome { code, stdout: stdout.join().unwrap_or_default(), stderr: stderr.join().unwrap_or_default(), timed_out }
}

/// The first local page address in a line: `http://127.0.0.1:PORT/...` or
/// `http://localhost:PORT/...` (a desk-like command prints it when it is ready).
pub fn local_url(line: &str) -> Option<String> {
    let start = ["http://127.0.0.1:", "http://localhost:"].iter().filter_map(|prefix| line.find(prefix)).min()?;
    let url: String = line[start..].chars().take_while(|c| !c.is_whitespace() && *c != '"' && *c != '\'').collect();
    let rest = url.split_once("://").map(|(_, rest)| rest)?;
    let port: String = rest.split_once(':')?.1.chars().take_while(char::is_ascii_digit).collect();
    (!port.is_empty() && port.parse::<u16>().is_ok()).then_some(url)
}

/// A command that serves a page: started in the background; returns it and its
/// address once printed. The rest of its output is read and dropped.
pub fn serve(program: &Path, args: &[String], wait: Duration) -> Result<(Child, String), String> {
    let mut child = command(program, args).spawn().map_err(|error| format!("could not start: {error}"))?;
    let stdout = child.stdout.take().expect("piped");
    let stderr = collect(child.stderr.take().expect("piped"));
    let (sender, receiver) = mpsc::channel();
    thread::spawn(move || {
        let mut sent = false;
        for line in BufReader::new(stdout).lines() {
            let Ok(line) = line else { break };
            if !sent {
                if let Some(url) = local_url(&line) {
                    let _ = sender.send(url);
                    sent = true;
                }
            }
        }
    });
    match receiver.recv_timeout(wait) {
        Ok(url) => Ok((child, url)),
        Err(_) => {
            stop_group(&mut child, Duration::from_secs(2));
            let text = stderr.join().unwrap_or_default();
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
