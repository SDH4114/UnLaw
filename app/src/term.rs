//! Edit's terminal: shell command lines run one at a time on a pseudo-terminal, so the
//! programs see a real terminal (colors, `input()`, Ctrl-C) while the page shows their
//! output. Not a full terminal emulator: full-screen programs (vim, top) are not drawn.
//! Also the line that runs a source file ("Run" in Edit), picked by its suffix.

use std::fs::File;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};

/// `'text'` for a POSIX shell.
pub fn quote(word: &str) -> String {
    if !word.is_empty() && word.chars().all(|c| c.is_ascii_alphanumeric() || "-_./:@,+%".contains(c)) {
        return word.to_string();
    }
    format!("'{}'", word.replace('\'', r"'\''"))
}

/// The folder to run in and the command line that runs `file`; None for a file that
/// cannot be run. Rust files inside a Cargo project use `cargo run`.
pub fn run_line(file: &Path) -> Option<(PathBuf, String)> {
    let dir = file.parent()?.to_path_buf();
    let name = file.file_name()?.to_str()?;
    let stem = file.file_stem()?.to_str()?;
    let suffix = file.extension().and_then(|suffix| suffix.to_str()).unwrap_or("").to_ascii_lowercase();
    let (file_q, out_q) = (quote(name), quote(&format!("./{stem}")));
    let compiled = |compiler: &str| format!("{compiler} {file_q} -o {} && {out_q}", quote(stem));
    let line = match suffix.as_str() {
        "py" => format!("python3 {file_q}"),
        "rs" => {
            if let Some(project) = file.ancestors().skip(1).find(|dir| dir.join("Cargo.toml").is_file()) {
                return Some((project.to_path_buf(), "cargo run".to_string()));
            }
            compiled("rustc")
        }
        "c" => compiled("cc"),
        "cpp" | "cc" | "cxx" => format!("c++ -std=c++20 {file_q} -o {} && {out_q}", quote(stem)),
        "go" => format!("go run {file_q}"),
        "js" | "mjs" | "cjs" => format!("node {file_q}"),
        "ts" => format!("npx --yes tsx {file_q}"),
        "sh" | "bash" => format!("bash {file_q}"),
        "zsh" => format!("zsh {file_q}"),
        "rb" => format!("ruby {file_q}"),
        "lua" => format!("lua {file_q}"),
        "swift" => format!("swift {file_q}"),
        "java" => format!("java {file_q}"),
        "pl" => format!("perl {file_q}"),
        "php" => format!("php {file_q}"),
        _ => {
            use std::os::unix::fs::PermissionsExt;
            let executable =
                file.metadata().map(|meta| meta.is_file() && meta.permissions().mode() & 0o111 != 0).unwrap_or(false);
            if !executable {
                return None;
            }
            format!("./{file_q}")
        }
    };
    Some((dir, line))
}

/// `cd ARG` in the terminal: the folder it means (`~`, relative, `..`), which must exist.
pub fn cd_target(cwd: &Path, arg: &str, home: &Path) -> Result<PathBuf, String> {
    let arg = arg.trim();
    let unquoted = arg.trim_matches(|c| c == '\'' || c == '"');
    let target = match unquoted {
        "" | "~" => home.to_path_buf(),
        _ if unquoted.starts_with("~/") => home.join(&unquoted[2..]),
        _ => cwd.join(unquoted),
    };
    match target.canonicalize() {
        Ok(real) if real.is_dir() => Ok(real),
        Ok(_) => Err(format!("cd: not a folder: {unquoted}")),
        Err(_) => Err(format!("cd: no such folder: {unquoted}")),
    }
}

/// The text of `bytes` that is complete UTF-8; an incomplete character at the end stays in
/// `bytes` for the next read (a read may cut one in two).
pub fn take_text(bytes: &mut Vec<u8>) -> String {
    let complete = match std::str::from_utf8(bytes) {
        Ok(_) => bytes.len(),
        Err(error) if error.error_len().is_none() => error.valid_up_to(),
        Err(_) => bytes.len(),
    };
    let text = String::from_utf8_lossy(&bytes[..complete]).into_owned();
    bytes.drain(..complete);
    text
}

/// A command running on its own pseudo-terminal; `master` reads its output and takes input.
pub struct Pty {
    pub child: Child,
    pub master: File,
}

/// Runs `line` with the user's shell (`-lc`, so PATH is the login one) in `cwd`, as the
/// leader of a new session whose controlling terminal is the pty.
pub fn spawn(line: &str, cwd: &Path, cols: u16, rows: u16) -> io::Result<Pty> {
    let (mut master, mut slave) = (-1, -1);
    let mut size = libc::winsize { ws_row: rows.max(2), ws_col: cols.max(10), ws_xpixel: 0, ws_ypixel: 0 };
    // SAFETY: openpty fills two descriptors we then own.
    if unsafe { libc::openpty(&mut master, &mut slave, std::ptr::null_mut(), std::ptr::null_mut(), &mut size) } != 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: both descriptors were just created and belong to nothing else.
    let (master, slave) = unsafe { (OwnedFd::from_raw_fd(master), OwnedFd::from_raw_fd(slave)) };
    // SAFETY: plain fcntl on a valid descriptor; the command must not inherit the master.
    unsafe { libc::fcntl(master.as_raw_fd(), libc::F_SETFD, libc::FD_CLOEXEC) };
    let shell = std::env::var("SHELL").ok().filter(|shell| shell.starts_with('/')).unwrap_or_else(|| "/bin/zsh".into());
    let mut command = Command::new(shell);
    command
        .arg("-lc")
        .arg(line)
        .current_dir(cwd)
        .stdin(Stdio::from(slave.try_clone()?))
        .stdout(Stdio::from(slave.try_clone()?))
        .stderr(Stdio::from(slave))
        .env("TERM", "xterm-256color")
        .env("COLORTERM", "truecolor")
        .env("CLICOLOR", "1")
        .env_remove("NO_COLOR")
        .env_remove("UNLAW_APP");
    // SAFETY: only async-signal-safe calls between fork and exec.
    unsafe {
        command.pre_exec(|| {
            if libc::setsid() < 0 || libc::ioctl(0, libc::TIOCSCTTY as _, 0) < 0 {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        });
    }
    let child = command.spawn()?;
    Ok(Pty { child, master: File::from(master) })
}

pub fn resize(master: &File, cols: u16, rows: u16) {
    let size = libc::winsize { ws_row: rows.max(2), ws_col: cols.max(10), ws_xpixel: 0, ws_ypixel: 0 };
    // SAFETY: TIOCSWINSZ on our own pty master with a valid winsize.
    unsafe { libc::ioctl(master.as_raw_fd(), libc::TIOCSWINSZ, &size) };
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read;

    fn sandbox(name: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!("unlaw-term-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        root.canonicalize().unwrap()
    }

    #[test]
    fn files_run_by_their_kind() {
        let root = sandbox("run");
        let line = |name: &str| run_line(&root.join(name)).map(|(_, line)| line);
        assert_eq!(line("main.py").unwrap(), "python3 main.py");
        assert_eq!(line("bit wise.rs").unwrap(), "rustc 'bit wise.rs' -o 'bit wise' && './bit wise'");
        assert_eq!(line("a.c").unwrap(), "cc a.c -o a && ./a");
        assert_eq!(line("notes.md"), None, "not a program");
        std::fs::create_dir_all(root.join("app/src")).unwrap();
        std::fs::write(root.join("app/Cargo.toml"), "[package]\n").unwrap();
        assert_eq!(run_line(&root.join("app/src/main.rs")), Some((root.join("app"), "cargo run".to_string())));
    }

    #[test]
    fn cd_understands_home_and_relative_folders() {
        let root = sandbox("cd");
        std::fs::create_dir_all(root.join("a/b")).unwrap();
        assert_eq!(cd_target(&root, "a/b", Path::new("/")).unwrap(), root.join("a/b"));
        assert_eq!(cd_target(&root.join("a/b"), "..", Path::new("/")).unwrap(), root.join("a"));
        assert_eq!(cd_target(&root, "", &root.join("a")).unwrap(), root.join("a"));
        assert_eq!(cd_target(&root, "~/b", &root.join("a")).unwrap(), root.join("a/b"));
        assert!(cd_target(&root, "nope", &root).unwrap_err().contains("no such folder"));
    }

    #[test]
    fn a_character_cut_by_a_read_waits_for_the_rest() {
        let mut bytes = "да".as_bytes().to_vec();
        let last = bytes.pop().unwrap();
        assert_eq!(take_text(&mut bytes), "д");
        assert_eq!(bytes.len(), 1);
        bytes.push(last);
        assert_eq!(take_text(&mut bytes), "а");
        assert!(bytes.is_empty());
    }

    #[test]
    fn commands_see_a_terminal_and_take_input() {
        let root = sandbox("pty");
        let mut pty = spawn("test -t 1 && echo tty; read name; echo hi $name", &root, 80, 24).unwrap();
        use std::io::Write;
        pty.master.write_all(b"bob\r").unwrap();
        let mut output = Vec::new();
        let mut buffer = [0u8; 4096];
        loop {
            match pty.master.read(&mut buffer) {
                Ok(0) | Err(_) => break,
                Ok(count) => output.extend_from_slice(&buffer[..count]),
            }
        }
        let text = String::from_utf8_lossy(&output);
        assert!(text.contains("tty"), "{text}");
        assert!(text.contains("hi bob"), "{text}");
        assert!(pty.child.wait().unwrap().success());
    }
}
