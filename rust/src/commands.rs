//! User commands: `commands/<name>/` with one entry point, run as a child
//! process (or exec'd) with a small, documented environment.

use std::collections::BTreeMap;
use std::env;
use std::ffi::OsString;
use std::fs::File;
use std::io::{self, Read};
use std::os::unix::process::{CommandExt, ExitStatusExt};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus};
use std::thread;
use std::time::{Duration, Instant};

use crate::config::{commands_dir, config_dir, Config};
use crate::util::{is_executable, shell_join, which};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Python,
    Shell,
    Node,
    /// A Cargo project, built on demand into target/release.
    Cargo,
    Executable,
}

/// Checked in this order; the first existing file is the command.
pub const ENTRY_POINTS: [(&str, Kind); 5] = [
    ("main.py", Kind::Python),
    ("main.sh", Kind::Shell),
    ("main.js", Kind::Node),
    ("Cargo.toml", Kind::Cargo),
    ("main", Kind::Executable),
];

#[derive(Clone, Debug)]
pub struct UserCommand {
    pub name: String,
    pub path: PathBuf,
    pub kind: Kind,
}

impl UserCommand {
    pub fn directory(&self) -> &Path {
        self.path.parent().unwrap_or(Path::new("."))
    }
}

pub fn entry_point(directory: &Path) -> Option<(PathBuf, Kind)> {
    ENTRY_POINTS.iter().find_map(|(file, kind)| {
        let path = directory.join(file);
        let usable = if *kind == Kind::Executable { is_executable(&path) } else { path.is_file() };
        usable.then_some((path, *kind))
    })
}

fn valid_directory_name(name: &str) -> bool {
    !name.is_empty() && !name.starts_with('.') && !name.contains('/')
}

pub fn discover() -> BTreeMap<String, UserCommand> {
    let mut found = BTreeMap::new();
    let Ok(entries) = std::fs::read_dir(commands_dir()) else {
        return found;
    };
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        if !valid_directory_name(&name) || !entry.path().is_dir() {
            continue;
        }
        if let Some((path, kind)) = entry_point(&entry.path()) {
            found.insert(name.clone(), UserCommand { name, path, kind });
        }
    }
    found
}

pub fn resolve(name: &str) -> Option<UserCommand> {
    if !valid_directory_name(name) {
        return None;
    }
    let directory = commands_dir().join(name);
    entry_point(&directory).map(|(path, kind)| UserCommand { name: name.to_string(), path, kind })
}

const PYTHONS: [&str; 5] = ["python3.14", "python3.13", "python3.12", "python3.11", "python3"];

/// Interpreter for `main.py`: `UNLAW_PYTHON`, then `core.python`, then the
/// newest versioned `python3.x` on PATH (macOS' /usr/bin/python3 is too old
/// for tomllib, so versioned names are preferred).
pub fn python(config: Option<&Config>) -> Option<PathBuf> {
    if let Ok(explicit) = env::var("UNLAW_PYTHON") {
        if !explicit.is_empty() {
            return which(&explicit).or(Some(PathBuf::from(explicit)));
        }
    }
    if let Some(configured) = config.map(|c| c.string("core.python")) {
        if !configured.is_empty() && configured != "auto" {
            return which(&crate::util::expand_user(&configured).to_string_lossy()).or(Some(configured.into()));
        }
    }
    PYTHONS.iter().find_map(|name| which(name))
}

pub fn command_line(command: &UserCommand, args: &[String], config: &Config) -> Vec<OsString> {
    let path = command.path.clone().into_os_string();
    let mut line: Vec<OsString> = match command.kind {
        Kind::Python => {
            vec![python(Some(config)).map(PathBuf::into_os_string).unwrap_or_else(|| "python3".into()), path]
        }
        Kind::Shell if !is_executable(&command.path) => vec!["/bin/sh".into(), path],
        Kind::Node => vec!["node".into(), path],
        Kind::Cargo => vec![cargo_binary(&command.path).into_os_string()],
        Kind::Shell | Kind::Executable => vec![path],
    };
    line.extend(args.iter().map(OsString::from));
    line
}

fn manifest(path: &Path) -> Option<toml_edit::DocumentMut> {
    std::fs::read_to_string(path).ok()?.parse().ok()
}

/// target/release/<first [[bin]] name, else the package name>.
pub fn cargo_binary(manifest_path: &Path) -> PathBuf {
    let directory = manifest_path.parent().unwrap_or(Path::new("."));
    let name = manifest(manifest_path)
        .and_then(|document| {
            let bin = document.get("bin").and_then(|bins| bins.as_array_of_tables()).and_then(|bins| bins.iter().next());
            bin.and_then(|bin| bin.get("name")?.as_str().map(str::to_string))
                .or_else(|| document.get("package")?.get("name")?.as_str().map(str::to_string))
        })
        .unwrap_or_else(|| "main".into());
    directory.join("target").join("release").join(name)
}

fn newest_source(directory: &Path) -> Option<std::time::SystemTime> {
    fn walk(path: &Path, newest: &mut Option<std::time::SystemTime>) {
        let Ok(meta) = std::fs::metadata(path) else { return };
        if meta.is_dir() {
            for entry in std::fs::read_dir(path).into_iter().flatten().flatten() {
                walk(&entry.path(), newest);
            }
        } else if let Ok(modified) = meta.modified() {
            *newest = Some(newest.map_or(modified, |current| current.max(modified)));
        }
    }
    let mut newest = None;
    for part in ["Cargo.toml", "Cargo.lock", "build.rs", "src"] {
        walk(&directory.join(part), &mut newest);
    }
    newest
}

/// Rebuild a Cargo command when its binary is missing or older than its sources.
pub fn ensure_built(command: &UserCommand) -> Result<(), i32> {
    let binary = cargo_binary(&command.path);
    let built = std::fs::metadata(&binary).and_then(|meta| meta.modified()).ok();
    let stale = match (built, newest_source(command.directory())) {
        (Some(built), Some(source)) => source > built,
        (Some(_), None) => false,
        (None, _) => true,
    };
    if !stale {
        return Ok(());
    }
    let Some(cargo) = which("cargo").or_else(|| Some(crate::util::home().join(".cargo/bin/cargo")).filter(|p| is_executable(p))) else {
        eprintln!("unlaw: {} is a Rust command but cargo was not found; install Rust from https://rustup.rs", command.name);
        return Err(1);
    };
    eprintln!("unlaw: building {}…", command.name);
    let mut build = Command::new(cargo);
    // An explicit target dir: a global CARGO_TARGET_DIR must not move the binary.
    build
        .args(["build", "--release", "--quiet", "--manifest-path"])
        .arg(&command.path)
        .arg("--target-dir")
        .arg(command.directory().join("target"));
    match status_shielded(&mut build) {
        Ok(status) if status.success() && binary.is_file() => Ok(()),
        Ok(status) if status.success() => {
            eprintln!("unlaw: {} built, but {} is missing; check [[bin]] in Cargo.toml", command.name, binary.display());
            Err(1)
        }
        Ok(status) => {
            eprintln!("unlaw: building {} failed", command.name);
            Err(exit_code(status))
        }
        Err(error) => {
            eprintln!("unlaw: could not run cargo: {error}");
            Err(1)
        }
    }
}

pub fn environment(command: &UserCommand, config: &Config) -> Vec<(&'static str, OsString)> {
    vec![
        ("UNLAW_COMMAND", command.name.clone().into()),
        ("UNLAW_COMMAND_DIR", command.directory().as_os_str().to_owned()),
        ("UNLAW_CONFIG_DIR", config_dir().into_os_string()),
        ("UNLAW_STORAGE", config.storage_root().into_os_string()),
    ]
}

pub struct RunOptions {
    pub dry_run: bool,
    pub verbose: bool,
    pub timeout: Duration,
}

pub(crate) fn exit_code(status: ExitStatus) -> i32 {
    status.code().unwrap_or_else(|| 128 + status.signal().unwrap_or(0))
}

fn run_error(name: &str, program: &OsString, error: &io::Error) -> i32 {
    if error.kind() == io::ErrorKind::NotFound {
        let hint = if program.to_string_lossy().contains("python") {
            "; install Python 3.11+ or set core.python / UNLAW_PYTHON"
        } else {
            ""
        };
        eprintln!("unlaw: Could not run {name}: {} not found{hint}", program.to_string_lossy());
    } else {
        eprintln!("unlaw: Could not run {name}: {error}");
    }
    1
}

/// Ignore terminal signals in the waiting parent (like `system(3)`); the
/// child restores defaults so Ctrl-C reaches the command itself.
struct IgnoreSignals(libc::sighandler_t, libc::sighandler_t);

impl IgnoreSignals {
    fn new() -> Self {
        unsafe { IgnoreSignals(libc::signal(libc::SIGINT, libc::SIG_IGN), libc::signal(libc::SIGQUIT, libc::SIG_IGN)) }
    }
}

impl Drop for IgnoreSignals {
    fn drop(&mut self) {
        unsafe {
            libc::signal(libc::SIGINT, self.0);
            libc::signal(libc::SIGQUIT, self.1);
        }
    }
}

/// Run a helper tool to completion: Ctrl-C reaches the tool, while Unlaw keeps
/// running so it can clean up and report (a SIGINT exit becomes 130).
pub(crate) fn status_shielded(process: &mut Command) -> io::Result<ExitStatus> {
    let _guard = IgnoreSignals::new();
    spawn_shielded(process)?.wait()
}

/// Spawn with default signal handling in the child; pair with `shield()`.
pub(crate) fn spawn_shielded(process: &mut Command) -> io::Result<std::process::Child> {
    unsafe {
        process.pre_exec(|| {
            libc::signal(libc::SIGINT, libc::SIG_DFL);
            libc::signal(libc::SIGQUIT, libc::SIG_DFL);
            Ok(())
        });
    }
    process.spawn()
}

/// Ignore Ctrl-C in Unlaw itself until the returned guard is dropped.
pub(crate) fn shield() -> impl Drop {
    IgnoreSignals::new()
}

pub fn run(command: &UserCommand, args: &[String], config: &Config, options: &RunOptions) -> i32 {
    let line = command_line(command, args, config);
    if command.kind == Kind::Cargo && !options.dry_run {
        if let Err(code) = ensure_built(command) {
            return code;
        }
    }
    if options.dry_run {
        println!("DRY RUN: {}", shell_join(&line));
        return 0;
    }
    if options.verbose {
        eprintln!("unlaw: running {} (config): {}", command.name, shell_join(&line));
    }
    let mut process = Command::new(&line[0]);
    process.args(&line[1..]).envs(environment(command, config));

    // Fast path: become the command, so TTY, signals and exit status are native.
    if !options.verbose && options.timeout.is_zero() {
        let error = process.exec();
        return run_error(&command.name, &line[0], &error);
    }

    let _guard = IgnoreSignals::new();
    unsafe {
        process.pre_exec(|| {
            libc::signal(libc::SIGINT, libc::SIG_DFL);
            libc::signal(libc::SIGQUIT, libc::SIG_DFL);
            Ok(())
        });
    }
    let started = Instant::now();
    let mut child = match process.spawn() {
        Ok(child) => child,
        Err(error) => return run_error(&command.name, &line[0], &error),
    };
    let status = if options.timeout.is_zero() {
        child.wait()
    } else {
        loop {
            match child.try_wait() {
                Ok(Some(status)) => break Ok(status),
                Ok(None) if started.elapsed() >= options.timeout => {
                    let _ = child.kill();
                    let _ = child.wait();
                    eprintln!("unlaw: Command timed out: {}", command.name);
                    return 124;
                }
                Ok(None) => thread::sleep(Duration::from_millis(10)),
                Err(error) => break Err(error),
            }
        }
    };
    if options.verbose {
        eprintln!("unlaw: finished in {:.3}s", started.elapsed().as_secs_f64());
    }
    match status {
        Ok(status) => exit_code(status),
        Err(error) => run_error(&command.name, &line[0], &error),
    }
}

fn first_line(text: &str) -> Option<String> {
    text.lines().map(str::trim).find(|line| !line.is_empty()).map(str::to_string)
}

fn python_docstring(head: &str) -> Option<String> {
    let mut lines = head.lines().map(str::trim_start).skip_while(|line| line.is_empty() || line.starts_with('#'));
    let first = lines.next()?;
    let body = first.strip_prefix(['r', 'R', 'u', 'U']).unwrap_or(first);
    let quote = ["\"\"\"", "'''", "\"", "'"].into_iter().find(|quote| body.starts_with(quote))?;
    let mut text = body[quote.len()..].to_string();
    for line in lines {
        if text.contains(quote) {
            break;
        }
        text.push('\n');
        text.push_str(line);
    }
    let text = text.split(quote).next().unwrap_or("");
    first_line(&text.replace("\\\"", "\"").replace("\\'", "'").replace("\\\\", "\\"))
}

fn script_comment(head: &str) -> Option<String> {
    head.lines()
        .map(str::trim)
        .find(|line| !line.starts_with("#!") && !line.is_empty())
        .and_then(|line| line.strip_prefix("//").or_else(|| line.strip_prefix('#')))
        .and_then(first_line)
}

/// One-line description without running the command: `help.txt`, the
/// `main.py` docstring, or a leading `#`/`//` comment in other scripts.
pub fn summary(command: &UserCommand) -> Option<String> {
    if let Ok(help) = std::fs::read_to_string(command.directory().join("help.txt")) {
        if let Some(line) = first_line(&help) {
            return Some(line);
        }
    }
    let mut head = Vec::with_capacity(4096);
    File::open(&command.path).ok()?.take(4096).read_to_end(&mut head).ok()?;
    let head = match std::str::from_utf8(&head) {
        Ok(text) => text,
        Err(error) if error.error_len().is_none() => std::str::from_utf8(&head[..error.valid_up_to()]).ok()?,
        Err(_) => return None,
    };
    match command.kind {
        Kind::Python => python_docstring(head),
        Kind::Cargo => manifest(&command.path)
            .and_then(|document| document.get("package")?.get("description")?.as_str().map(str::to_string))
            .and_then(|text| first_line(&text)),
        _ => script_comment(head),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn docstrings_after_comments_and_on_many_lines() {
        assert_eq!(python_docstring("# header\n\"\"\"Open apps.\"\"\"\nimport x").as_deref(), Some("Open apps."));
        assert_eq!(python_docstring("#!/usr/bin/env python3\n'''\n  Multi line.\n  More.\n'''").as_deref(), Some("Multi line."));
        assert_eq!(python_docstring("r\"\"\"Say \\\"hi\\\".\"\"\"").as_deref(), Some("Say \"hi\"."));
        assert_eq!(python_docstring("import sys\n\"\"\"Not a docstring.\"\"\""), None);
    }

    #[test]
    fn script_comments_skip_the_shebang() {
        assert_eq!(script_comment("#!/bin/sh\n# Print the weather.\necho").as_deref(), Some("Print the weather."));
        assert_eq!(script_comment("// Format JSON.\nconsole.log(1)").as_deref(), Some("Format JSON."));
        assert_eq!(script_comment("#!/bin/sh\necho hi"), None);
    }

    fn scratch(name: &str) -> PathBuf {
        let directory = std::env::temp_dir().join(format!("unlaw-commands-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&directory);
        std::fs::create_dir_all(&directory).unwrap();
        directory
    }

    fn command(directory: &Path, file: &str, body: &[u8], kind: Kind) -> UserCommand {
        let path = directory.join(file);
        std::fs::write(&path, body).unwrap();
        UserCommand { name: "demo".into(), path, kind }
    }

    #[test]
    fn entry_points_are_checked_in_order() {
        use std::os::unix::fs::PermissionsExt;
        let directory = scratch("entries");
        assert_eq!(entry_point(&directory), None);
        std::fs::write(directory.join("main"), "#!/bin/sh\n").unwrap();
        assert_eq!(entry_point(&directory), None, "main needs the executable bit");
        std::fs::set_permissions(directory.join("main"), std::fs::Permissions::from_mode(0o755)).unwrap();
        assert_eq!(entry_point(&directory).unwrap().1, Kind::Executable);
        std::fs::write(directory.join("main.js"), "").unwrap();
        assert_eq!(entry_point(&directory).unwrap().1, Kind::Node);
        std::fs::write(directory.join("main.sh"), "").unwrap();
        assert_eq!(entry_point(&directory).unwrap().1, Kind::Shell);
        std::fs::write(directory.join("main.py"), "").unwrap();
        assert_eq!(entry_point(&directory).unwrap(), (directory.join("main.py"), Kind::Python));
        std::fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn unsafe_names_never_resolve() {
        for name in ["", ".hidden", "../escape", "a/b"] {
            assert!(resolve(name).is_none(), "{name}");
        }
    }

    #[test]
    fn summaries_handle_help_files_binaries_and_truncated_utf8() {
        let directory = scratch("summary");
        let script = command(&directory, "main.sh", b"#!/bin/sh\n# Shell summary.\n", Kind::Shell);
        assert_eq!(summary(&script).as_deref(), Some("Shell summary."));
        std::fs::write(directory.join("help.txt"), "\n\n").unwrap();
        assert_eq!(summary(&script).as_deref(), Some("Shell summary."), "empty help.txt is ignored");
        std::fs::write(directory.join("help.txt"), "  From help.\n").unwrap();
        assert_eq!(summary(&script).as_deref(), Some("From help."));
        std::fs::remove_file(directory.join("help.txt")).unwrap();
        let binary = command(&directory, "main", &[0x7f, b'E', b'L', b'F', 0xff, 0xfe], Kind::Executable);
        assert_eq!(summary(&binary), None);
        // A multi-byte character cut by the 4096-byte read must not hide the docstring.
        let mut long = "\"\"\"Ünïcode summary.\"\"\"\n#".as_bytes().to_vec();
        long.resize(4095, b'x');
        long.extend("é".as_bytes());
        let python = command(&directory, "main.py", &long, Kind::Python);
        assert_eq!(summary(&python).as_deref(), Some("Ünïcode summary."));
        let missing = UserCommand { name: "x".into(), path: directory.join("nope.py"), kind: Kind::Python };
        assert_eq!(summary(&missing), None);
        std::fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn command_lines_pick_the_interpreter() {
        let directory = scratch("lines");
        let config = Config { data: crate::config::defaults() };
        let args = vec!["a b".to_string()];
        let js = command(&directory, "main.js", b"", Kind::Node);
        assert_eq!(command_line(&js, &args, &config), vec![OsString::from("node"), js.path.clone().into(), "a b".into()]);
        let sh = command(&directory, "main.sh", b"", Kind::Shell);
        assert_eq!(command_line(&sh, &[], &config), vec![OsString::from("/bin/sh"), sh.path.clone().into()]);
        let exe = command(&directory, "main", b"", Kind::Executable);
        assert_eq!(command_line(&exe, &[], &config), vec![OsString::from(exe.path.clone())]);
        std::fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn exit_codes_include_signals() {
        assert_eq!(exit_code(ExitStatus::from_raw(3 << 8)), 3);
        assert_eq!(exit_code(ExitStatus::from_raw(15)), 143);
    }

    #[test]
    fn docstring_edge_cases() {
        assert_eq!(python_docstring(""), None);
        assert_eq!(python_docstring("# only comments\n"), None);
        assert_eq!(python_docstring("\"Single-quoted line.\"\n").as_deref(), Some("Single-quoted line."));
        assert_eq!(python_docstring("\"\"\"\n\n\"\"\"\n"), None);
    }
}
