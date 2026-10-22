//! System commands that live in the dispatcher.

use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::io::{self, BufRead, Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use crate::commands;
use crate::config::{self, commands_dir, config_dir, config_file, templates_dir, Config, ConfigError};
use crate::help::{self, is_system, print_if_requested, system_names, system_summary};
use crate::layout::{ensure_layout, STORAGE_SUBDIRECTORIES};
use crate::shell;
use crate::util::{home, shell_join, which, Json};
use crate::workspace;
use crate::VERSION;

const COMMAND_TEMPLATE: &str = include_str!("../assets/command_main.py");

struct Record {
    name: String,
    source: &'static str,
    path: Option<PathBuf>,
    expansion: Option<Vec<String>>,
    summary: Option<String>,
}

fn records(config: &Config, describe: bool) -> Vec<Record> {
    let discovered = commands::discover();
    let mut by_name: BTreeMap<String, Record> = BTreeMap::new();
    for name in system_names() {
        let summary = describe.then(|| system_summary(name).to_string());
        by_name.insert(name.into(), Record { name: name.into(), source: "system", path: None, expansion: None, summary });
    }
    for (name, command) in &discovered {
        if is_system(name) {
            continue;
        }
        let summary = if describe { commands::summary(command) } else { None };
        by_name.insert(
            name.clone(),
            Record { name: name.clone(), source: "config", path: Some(command.path.clone()), expansion: None, summary },
        );
    }
    for (name, expansion) in config.aliases() {
        if !is_system(&name) {
            let summary = describe.then(|| format!("alias -> {}", shell_join(&expansion)));
            by_name.insert(
                name.clone(),
                Record { name, source: "alias", path: None, expansion: Some(expansion), summary },
            );
        }
    }
    by_name.into_values().collect()
}

fn usage(text: &str) -> i32 {
    eprintln!("{text}");
    2
}

pub fn list_commands(args: &[String]) -> i32 {
    if print_if_requested("commands", args) {
        return 0;
    }
    let flag = match args {
        [] => "",
        [flag] if ["--verbose", "--json", "--describe"].contains(&flag.as_str()) => flag.as_str(),
        _ => return usage("Usage: ul commands [--verbose|--describe|--json]"),
    };
    let config = match config::load() {
        Ok(config) => config,
        Err(error) => {
            eprintln!("unlaw commands: {error}");
            return 2;
        }
    };
    let records = records(&config, matches!(flag, "--json" | "--describe"));
    match flag {
        "--json" => {
            let items = records
                .iter()
                .map(|record| {
                    let mut fields = vec![
                        ("name".to_string(), Json::str(record.name.clone())),
                        ("source".to_string(), Json::str(record.source)),
                        (
                            "path".to_string(),
                            record.path.as_ref().map_or(Json::Null, |path| Json::str(path.to_string_lossy())),
                        ),
                    ];
                    if let Some(expansion) = &record.expansion {
                        fields.push((
                            "expansion".into(),
                            Json::Array(expansion.iter().map(|token| Json::str(token.clone())).collect()),
                        ));
                    }
                    fields.push(("summary".into(), record.summary.clone().map_or(Json::Null, Json::Str)));
                    Json::Object(fields)
                })
                .collect();
            println!("{}", Json::Array(items).render());
        }
        "--verbose" => {
            for record in &records {
                let suffix = record.path.as_ref().map(|path| format!("  {}", path.display())).unwrap_or_default();
                println!("{:<16} {}{suffix}", record.name, record.source);
            }
        }
        "--describe" => {
            for record in &records {
                println!("{:<16} {}", record.name, record.summary.as_deref().unwrap_or(""));
            }
        }
        _ => {
            for record in &records {
                println!("{}", record.name);
            }
        }
    }
    0
}

pub fn list_templates(args: &[String]) -> i32 {
    if print_if_requested("templates", args) {
        return 0;
    }
    if !args.is_empty() {
        return usage("Usage: ul templates");
    }
    match workspace::discover() {
        Ok(templates) => {
            for name in templates.keys() {
                println!("{name}");
            }
            0
        }
        Err(error) => {
            eprintln!("unlaw templates: {error}");
            2
        }
    }
}

pub fn list_all(args: &[String]) -> i32 {
    if print_if_requested("list", args) {
        return 0;
    }
    if !args.is_empty() {
        return usage("Usage: ul list");
    }
    let templates = match workspace::discover() {
        Ok(templates) => templates,
        Err(error) => {
            eprintln!("unlaw list: {error}");
            return 2;
        }
    };
    let config = match config::load() {
        Ok(config) => config,
        Err(error) => {
            eprintln!("unlaw list: {error}");
            return 2;
        }
    };
    println!("Templates");
    for name in templates.keys() {
        println!("{name}");
    }
    println!("\nCommands");
    for record in records(&config, false) {
        println!("{}", record.name);
    }
    0
}

pub fn init(args: &[String]) -> i32 {
    if print_if_requested("init", args) {
        return 0;
    }
    if !args.is_empty() {
        return usage("Usage: ul init");
    }
    let storage = config::load().map(|config| config.storage_root()).unwrap_or_else(|_| config::configured_storage_root());
    println!("Unlaw configuration: {}", config_dir().display());
    println!("Commands: {}", commands_dir().display());
    println!("Templates: {}", templates_dir().display());
    println!("Storage: {}", storage.display());
    0
}

pub fn which_command(args: &[String]) -> i32 {
    if print_if_requested("which", args) {
        return 0;
    }
    let [name] = args else {
        return usage("Usage: ul which <command>");
    };
    if is_system(name) {
        println!("{name}: system");
        return 0;
    }
    match config::load() {
        Ok(config) => {
            if let Some(alias) = config.alias(name) {
                println!("{name}: alias -> {}", shell_join(&alias));
                return 0;
            }
        }
        Err(error) => {
            eprintln!("unlaw which: {error}");
            return 2;
        }
    }
    match commands::resolve(name) {
        Some(command) => {
            println!("{name}: config {}", command.path.display());
            0
        }
        None => {
            eprintln!("unlaw: Unknown command: {name}");
            1
        }
    }
}

pub fn version(args: &[String]) -> i32 {
    if print_if_requested("version", args) {
        return 0;
    }
    if !args.is_empty() {
        return usage("Usage: ul version");
    }
    println!("Unlaw {VERSION}");
    0
}

pub fn venv(args: &[String]) -> i32 {
    if print_if_requested("venv", args) {
        return 0;
    }
    if !args.is_empty() {
        return usage("Usage: ul venv");
    }
    eprintln!(
        "unlaw venv: Current-shell integration is required. Run `ul doctor --fix`, then restart the shell or run `exec zsh`."
    );
    1
}

pub fn completion(args: &[String]) -> i32 {
    if print_if_requested("completion", args) {
        return 0;
    }
    if args != ["zsh"] {
        return usage("Usage: ul completion zsh");
    }
    print!("{}", shell::ZSH_COMPLETION);
    0
}

fn candidate(name: &str, description: &str) -> String {
    format!("{}:{}", name.replace(':', "\\:"), description.replace('\n', " "))
}

/// Hidden `_complete <position> <words...>`; reads no Python and runs nothing.
pub fn complete(args: &[String]) -> i32 {
    let position: usize = args.first().and_then(|value| value.parse().ok()).unwrap_or(1);
    let words = args.get(1..).unwrap_or(&[]);
    let config = config::load().ok();
    let all_commands = || {
        let mut lines = Vec::new();
        if let Some(config) = &config {
            for record in records(config, true) {
                lines.push(candidate(&record.name, record.summary.as_deref().unwrap_or("")));
            }
        }
        if let Ok(templates) = workspace::discover() {
            for (name, template) in templates {
                lines.push(candidate(&name, &format!("project template ({})", template.path.display())));
            }
        }
        lines
    };
    let lines: Vec<String> = match (position, words.first().map(String::as_str)) {
        (1, _) => all_commands(),
        (2, Some("help" | "which")) => all_commands(),
        (2, Some("config")) => [
            ("path", "Print the config.toml path"),
            ("show", "Print config.toml"),
            ("get", "Read a dotted key"),
            ("set", "Set and validate a value"),
            ("edit", "Open config.toml in $VISUAL/$EDITOR"),
            ("check", "Validate the configuration"),
            ("reset", "Reset defaults (needs --yes)"),
        ]
        .iter()
        .map(|(name, text)| candidate(name, text))
        .collect(),
        (2, Some("create")) => vec![
            candidate("command", "Create commands/<name>/main.py"),
            candidate("template", "Save the current project as a template"),
        ],
        (2, Some("completion")) => vec![candidate("zsh", "Zsh completion code")],
        (2, Some("commands")) => ["--verbose", "--describe", "--json"].iter().map(|f| candidate(f, "")).collect(),
        (2, Some("update")) => [("--check", "Compare with GitHub"), ("--branch", "Install a branch"), ("--tag", "Install a tag")]
            .iter()
            .map(|(name, text)| candidate(name, text))
            .collect(),
        (2, Some("doctor")) => ["--verbose", "--json", "--fix"].iter().map(|f| candidate(f, "")).collect(),
        _ => Vec::new(),
    };
    for line in lines {
        println!("{line}");
    }
    0
}

fn create_user_command(args: &[String]) -> i32 {
    let [name] = args else {
        return usage("Usage: ul create command <name>");
    };
    if !workspace::valid_name(name) || is_system(name) {
        eprintln!(
            "unlaw: Command names must start with a lowercase letter and contain only lowercase letters, numbers, '-' or '_'."
        );
        return 2;
    }
    let directory = commands_dir().join(name);
    let destination = directory.join("main.py");
    if let Some((existing, _)) = commands::entry_point(&directory) {
        eprintln!("unlaw: Command already exists: {}", existing.display());
        return 1;
    }
    if destination.exists() {
        eprintln!("unlaw: Command already exists: {}", destination.display());
        return 1;
    }
    let user_template = templates_dir().join("commands").join("main.py");
    let template = if user_template.is_file() {
        match fs::read_to_string(&user_template) {
            Ok(text) => text,
            Err(error) => {
                eprintln!("unlaw: Could not read {}: {error}", user_template.display());
                return 1;
            }
        }
    } else {
        COMMAND_TEMPLATE.to_string()
    };
    if let Err(error) = fs::create_dir_all(&directory).and_then(|_| fs::write(&destination, template)) {
        eprintln!("unlaw: Could not create {}: {error}", destination.display());
        return 1;
    }
    println!("Created command '{name}': {}", destination.display());
    println!("Run it with: ul {name}");
    0
}

struct Cancelled;

fn prompt(text: &str) -> Result<String, Cancelled> {
    print!("{text}");
    let _ = io::stdout().flush();
    let mut line = String::new();
    match io::stdin().lock().read_line(&mut line) {
        Ok(0) | Err(_) => Err(Cancelled),
        Ok(_) => Ok(line.trim().to_string()),
    }
}

fn prompt_choice(text: &str, allowed: &[&str], error: &str) -> Result<String, Cancelled> {
    loop {
        let value = prompt(text)?.to_lowercase();
        if allowed.contains(&value.as_str()) {
            return Ok(value);
        }
        eprintln!("{error}");
    }
}

fn create_project_template(args: &[String]) -> i32 {
    if args.len() > 1 {
        return usage("Usage: ul create template [name]");
    }
    let cancelled = || {
        eprintln!("unlaw create template: Cancelled.");
        1
    };
    let name = match args.first() {
        Some(name) => name.clone(),
        None => match prompt("Name of template > ") {
            Ok(name) => name,
            Err(Cancelled) => return cancelled(),
        },
    };
    let fail = |error: &dyn std::fmt::Display| {
        eprintln!("unlaw create template: {error}");
        2
    };
    if let Err(error) = workspace::validate_name(&name) {
        return fail(&error);
    }
    let config = match config::load() {
        Ok(config) => config,
        Err(error) => return fail(&error),
    };
    let templates = match workspace::discover() {
        Ok(templates) => templates,
        Err(error) => return fail(&error),
    };
    if is_system(&name) || commands::resolve(&name).is_some() || config.alias(&name).is_some() || templates.contains_key(&name)
    {
        eprintln!("unlaw create template: Name already in use: {name}");
        return 1;
    }
    let Ok(app) = prompt_choice("Open with (zed/obsidian) > ", &["zed", "obsidian"], "Please enter zed or obsidian.") else {
        return cancelled();
    };
    let Ok(ai) = prompt_choice("Add AI? (y/n) > ", &["y", "n"], "Please enter y or n.") else {
        return cancelled();
    };
    let cwd = match env::current_dir() {
        Ok(cwd) => cwd,
        Err(error) => return fail(&error),
    };
    match workspace::create(&name, &cwd, &app, ai == "y") {
        Ok(template) => {
            println!("Created template '{name}' for {}", template.path.display());
            println!("Run it with: ul {name}");
            0
        }
        Err(error) => fail(&error),
    }
}

pub fn create(args: &[String]) -> i32 {
    if print_if_requested("create", args) {
        return 0;
    }
    match args.first().map(String::as_str) {
        Some("command") => create_user_command(&args[1..]),
        Some("template") => create_project_template(&args[1..]),
        _ => usage("Usage: ul create command <name> | ul create template [name]"),
    }
}

// ---------------------------------------------------------------- doctor

struct Check {
    name: &'static str,
    available: bool,
    required: bool,
    detail: String,
}

impl Check {
    fn json(&self) -> Json {
        Json::Object(vec![
            ("name".into(), Json::str(self.name)),
            ("available".into(), Json::Bool(self.available)),
            ("required".into(), Json::Bool(self.required)),
            ("detail".into(), Json::str(self.detail.clone())),
        ])
    }
}

fn tool(name: &'static str, executable: &str, detail: &str) -> Check {
    let path = which(executable);
    Check {
        name,
        available: path.is_some(),
        required: false,
        detail: path.map(|path| path.display().to_string()).unwrap_or_else(|| detail.into()),
    }
}

/// Run a program with a deadline, returning (success, stdout, stderr).
fn run_with_timeout(program: &Path, args: &[&str], timeout: Duration) -> Result<(bool, String, String), String> {
    let mut child = Command::new(program)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| error.to_string())?;
    let mut stdout = child.stdout.take().unwrap();
    let mut stderr = child.stderr.take().unwrap();
    let out = thread::spawn(move || {
        let mut text = String::new();
        let _ = stdout.read_to_string(&mut text);
        text
    });
    let err = thread::spawn(move || {
        let mut text = String::new();
        let _ = stderr.read_to_string(&mut text);
        text
    });
    let started = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) if started.elapsed() >= timeout => {
                let _ = child.kill();
                let _ = child.wait();
                return Err("timed out".into());
            }
            Ok(None) => thread::sleep(Duration::from_millis(20)),
            Err(error) => return Err(error.to_string()),
        }
    };
    Ok((status.success(), out.join().unwrap_or_default(), err.join().unwrap_or_default()))
}

fn harness_permissions(executable: Option<&Path>) -> (bool, String) {
    let Some(executable) = executable else {
        return (false, "not installed".into());
    };
    match run_with_timeout(executable, &["doctor"], Duration::from_secs(10)) {
        Err(error) if error == "timed out" => (false, "permission check timed out".into()),
        Err(error) => (false, error),
        Ok((ok, stdout, stderr)) => {
            let text = if stdout.trim().is_empty() { stderr } else { stdout };
            let detail = text.trim().lines().last().unwrap_or("no details").to_string();
            (ok, detail)
        }
    }
}

fn python_check(config: Option<&Config>) -> Check {
    let Some(python) = commands::python(config) else {
        return Check {
            name: "Python",
            available: false,
            required: true,
            detail: "Python 3.11+ not found; install it or set core.python".into(),
        };
    };
    let probe = "import sys; print('%d.%d.%d' % sys.version_info[:3])";
    let version = run_with_timeout(&python, &["-c", probe], Duration::from_secs(10))
        .ok()
        .filter(|(ok, _, _)| *ok)
        .map(|(_, stdout, _)| stdout.trim().to_string());
    let parsed: Option<(u32, u32)> = version.as_deref().and_then(|text| {
        let mut parts = text.split('.').map(|part| part.parse::<u32>().ok());
        Some((parts.next()??, parts.next()??))
    });
    let available = parsed.is_some_and(|version| version >= (3, 11));
    let detail = match (&version, available) {
        (Some(version), true) => format!("{} ({version})", python.display()),
        (Some(version), false) => format!("{} is {version}; commands need Python 3.11+ (set core.python)", python.display()),
        (None, _) => format!("{} could not be run; set core.python", python.display()),
    };
    Check { name: "Python", available, required: true, detail }
}

/// Host and port of an LM Studio base URL; port 1234 and 127.0.0.1 by default.
fn host_port(base_url: &str) -> (String, u16) {
    let rest = base_url.split_once("://").map(|(_, rest)| rest).unwrap_or(base_url);
    let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
    let authority = authority.rsplit('@').next().unwrap_or("");
    let (host, port) = if let Some(stripped) = authority.strip_prefix('[') {
        let (host, tail) = stripped.split_once(']').unwrap_or((stripped, ""));
        (host.to_string(), tail.strip_prefix(':').and_then(|port| port.parse().ok()))
    } else {
        match authority.rsplit_once(':') {
            Some((host, port)) => (host.to_string(), port.parse().ok()),
            None => (authority.to_string(), None),
        }
    };
    let host = if host.is_empty() { "127.0.0.1".to_string() } else { host };
    (host, port.unwrap_or(1234))
}

fn lm_studio_server(base_url: &str) -> (bool, String) {
    let (host, port) = host_port(base_url);
    let addresses: Vec<_> = match (host.as_str(), port).to_socket_addrs() {
        Ok(addresses) => addresses.collect(),
        Err(error) => return (false, format!("not listening: {error}")),
    };
    let mut last = String::from("no address");
    for address in addresses {
        match TcpStream::connect_timeout(&address, Duration::from_millis(150)) {
            Ok(_) => return (true, format!("listening at {host}:{port}")),
            Err(error) => last = error.to_string(),
        }
    }
    (false, format!("not listening: {last}"))
}

fn executable_dir() -> Option<PathBuf> {
    env::current_exe().ok()?.parent().map(Path::to_path_buf)
}

fn display_home(path: &Path) -> String {
    match path.strip_prefix(home()) {
        Ok(rest) if !rest.as_os_str().is_empty() => format!("$HOME/{}", rest.display()),
        _ => path.display().to_string(),
    }
}

/// The installed `ul` must win over macOS' /usr/bin/ul.
fn precedes_system(entries: &[PathBuf], directory: &Path) -> bool {
    let Some(position) = entries.iter().position(|entry| entry == directory) else {
        return false;
    };
    entries.iter().position(|entry| entry == Path::new("/usr/bin")).is_none_or(|system| position < system)
}

fn bin_precedes_system(directory: &Path) -> bool {
    let entries: Vec<PathBuf> = env::var_os("PATH")
        .map(|path| env::split_paths(&path).filter(|entry| !entry.as_os_str().is_empty()).collect())
        .unwrap_or_default();
    precedes_system(&entries, directory)
}

fn fix_shell_path(directory: &Path) -> io::Result<bool> {
    let line = format!("export PATH=\"{}:$PATH\"", display_home(directory));
    let zshrc = home().join(".zshrc");
    let existing = fs::read_to_string(&zshrc).unwrap_or_default();
    if existing.contains(&line) || bin_precedes_system(directory) {
        return Ok(false);
    }
    if let Some(parent) = zshrc.parent() {
        fs::create_dir_all(parent)?;
    }
    let separator = if existing.is_empty() || existing.ends_with('\n') { "" } else { "\n" };
    let mut handle = fs::OpenOptions::new().create(true).append(true).open(&zshrc)?;
    write!(handle, "{separator}\n# Unlaw CLI (managed by `unlaw doctor --fix`)\n{line}\n")?;
    Ok(true)
}

fn apply_fixes() -> Result<Vec<String>, String> {
    let mut changes = Vec::new();
    let io_error = |error: io::Error| error.to_string();
    ensure_layout().map_err(io_error)?;
    if let Some(directory) = executable_dir() {
        if fix_shell_path(&directory).map_err(io_error)? {
            changes.push(format!("Added {} before system commands in ~/.zshrc", display_home(&directory)));
        }
    }
    if shell::install_zsh_integration(&home().join(".zshrc")).map_err(io_error)? {
        changes.push("Installed current-shell integration in ~/.zshrc".into());
    }
    if config::materialize().map_err(|error: ConfigError| error.0)? {
        changes.push("Added current defaults and removed deprecated storage settings in config.toml".into());
    }
    let config = config::load().map_err(|error| error.0)?;
    let storage = config.storage_root();
    for parts in STORAGE_SUBDIRECTORIES {
        let path = parts.iter().fold(storage.clone(), |path, part| path.join(part));
        if !path.exists() {
            fs::create_dir_all(&path).map_err(io_error)?;
            changes.push(format!("Created {}", path.display()));
        }
    }
    let legacy_log = config_dir().join("recording.log");
    let new_log = storage.join("runtime").join("recording.log");
    if legacy_log.is_file() && !new_log.exists() {
        if fs::rename(&legacy_log, &new_log).is_err() {
            fs::copy(&legacy_log, &new_log).and_then(|_| fs::remove_file(&legacy_log)).map_err(io_error)?;
        }
        changes.push(format!("Moved {} to {}", legacy_log.display(), new_log.display()));
    }
    Ok(changes)
}

fn doctor_checks() -> Vec<Check> {
    let root = ensure_layout().unwrap_or_else(|_| config_dir());
    let (config, config_ok, config_detail) = match config::load() {
        Ok(config) => (Some(config), true, config_file().display().to_string()),
        Err(error) => (None, false, error.0),
    };
    let fallback = Config { data: config::defaults() };
    let effective = config.as_ref().unwrap_or(&fallback);
    let storage = if config_ok { effective.storage_root() } else { config_dir().join("data") };
    let harness = which(&effective.string("mac.executable"));
    let todo_file = crate::util::expand_user(&effective.string("todo.vault_path")).join(effective.string("todo.file"));
    let base_url = effective.string("lm.base_url");
    let unlaw_bin = executable_dir();

    // The slow probes run in parallel.
    let (python, (permissions, permission_detail), (lm_server, lm_detail)) = thread::scope(|scope| {
        let python = scope.spawn(|| python_check(config.as_ref()));
        let permissions = scope.spawn(|| harness_permissions(harness.as_deref()));
        let lm = scope.spawn(|| lm_studio_server(&base_url));
        (python.join().unwrap(), permissions.join().unwrap(), lm.join().unwrap())
    });

    let app = |name: &'static str, path: &str| Check {
        name,
        available: Path::new(path).exists(),
        required: false,
        detail: path.into(),
    };
    vec![
        Check { name: "Unlaw", available: true, required: true, detail: format!("version {VERSION}") },
        Check { name: "Layout", available: root.is_dir(), required: true, detail: root.display().to_string() },
        Check { name: "Configuration", available: config_ok, required: true, detail: config_detail },
        Check { name: "Storage", available: storage.is_dir(), required: false, detail: storage.display().to_string() },
        python,
        tool("uv", "uv", "optional; Python falls back to venv"),
        tool("Git", "git", "needed by Git workflows and --git"),
        tool("Cargo", "cargo", "needed by `ul rust`"),
        tool("CMake", "cmake", "needed to build generated C++ projects"),
        tool("Node.js", "node", "optional; runs commands written as main.js"),
        tool("screencapture", "screencapture", "built into macOS"),
        tool("ffmpeg", "ffmpeg", "needed for camera and audio recording"),
        tool("Zed", "zed", "needed by `ul work`"),
        tool("7-Zip", "7z", "needed by `ul zip` for 7z, rar reading and AES zip"),
        tool("zstd", "zstd", "needed by `ul zip` for .tar.zst and .zst"),
        tool("RAR", "rar", "optional; needed to create .rar with `ul zip -f rar`"),
        tool("macOS Keychain", "security", "needed to store the Telegram token"),
        Check {
            name: "Unlaw PATH",
            available: unlaw_bin.as_deref().is_some_and(bin_precedes_system),
            required: false,
            detail: format!(
                "{} must precede /usr/bin because macOS also ships `ul`",
                unlaw_bin.as_deref().map(display_home).unwrap_or_else(|| "the Unlaw binary directory".into())
            ),
        },
        Check {
            name: "Obsidian TODO",
            available: todo_file.is_file(),
            required: false,
            detail: todo_file.display().to_string(),
        },
        app("Spotify", "/Applications/Spotify.app"),
        Check {
            name: "macOS Harness",
            available: harness.is_some(),
            required: false,
            detail: harness.as_ref().map(|path| path.display().to_string()).unwrap_or_else(|| "optional backend".into()),
        },
        Check { name: "macOS permissions", available: permissions, required: false, detail: permission_detail },
        app("LM Studio", "/Applications/LM Studio.app"),
        Check { name: "LM Studio local server", available: lm_server, required: false, detail: lm_detail },
    ]
}

pub fn doctor(args: &[String]) -> i32 {
    if print_if_requested("doctor", args) {
        return 0;
    }
    let flag = match args {
        [] => "",
        [flag] if ["--verbose", "--json", "--fix"].contains(&flag.as_str()) => flag.as_str(),
        _ => return usage("Usage: ul doctor [--verbose|--json|--fix]"),
    };
    if flag == "--fix" {
        match apply_fixes() {
            Ok(changes) if changes.is_empty() => println!("No automatic fixes were needed."),
            Ok(changes) => {
                for change in changes {
                    println!("FIXED  {change}");
                }
                println!("Restart the shell or run: exec zsh");
            }
            Err(error) => {
                eprintln!("unlaw doctor: {error}");
                return 1;
            }
        }
    }
    let checks = doctor_checks();
    if flag == "--json" {
        println!("{}", Json::Array(checks.iter().map(Check::json).collect()).render());
    } else {
        let verbose = matches!(flag, "--verbose" | "--fix");
        for check in &checks {
            let marker = if check.available { "✓" } else { "○" };
            let suffix = if verbose { format!("  {}", check.detail) } else { String::new() };
            println!("{:<20} {marker}{suffix}", check.name);
        }
    }
    i32::from(checks.iter().any(|check| check.required && !check.available))
}

pub fn run_template_hint(name: &str, args: &[String]) -> i32 {
    if help::wants_help(args) && args.len() == 1 {
        println!("Open the saved project in its configured app.\nUsage: ul {name}\nExample: ul {name}");
        return 0;
    }
    if !args.is_empty() {
        return usage(&format!("Usage: ul {name}"));
    }
    eprintln!(
        "unlaw: Project templates require current-shell integration. Run `ul doctor --fix`, then restart the shell or run `exec zsh`."
    );
    1
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lm_studio_addresses_are_parsed_like_urlparse() {
        assert_eq!(host_port("http://127.0.0.1:1234/v1"), ("127.0.0.1".into(), 1234));
        assert_eq!(host_port("http://localhost/v1"), ("localhost".into(), 1234));
        assert_eq!(host_port("http://[::1]:4321"), ("::1".into(), 4321));
        assert_eq!(host_port("http://user:pw@localhost:9"), ("localhost".into(), 9));
        assert_eq!(host_port("http:///v1"), ("127.0.0.1".into(), 1234));
    }

    #[test]
    fn open_and_closed_ports_are_reported() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let (up, detail) = lm_studio_server(&format!("http://127.0.0.1:{port}/v1"));
        assert!(up, "{detail}");
        assert_eq!(detail, format!("listening at 127.0.0.1:{port}"));
        let (up, detail) = lm_studio_server("http://127.0.0.1:1/v1");
        assert!(!up);
        assert!(detail.starts_with("not listening"), "{detail}");
    }

    #[test]
    fn unlaw_bin_must_come_before_usr_bin() {
        let bin = PathBuf::from("/Users/me/.local/bin");
        let paths = |items: &[&str]| items.iter().map(PathBuf::from).collect::<Vec<_>>();
        assert!(precedes_system(&paths(&["/Users/me/.local/bin", "/usr/bin"]), &bin));
        assert!(!precedes_system(&paths(&["/usr/bin", "/Users/me/.local/bin"]), &bin));
        assert!(precedes_system(&paths(&["/opt/homebrew/bin", "/Users/me/.local/bin"]), &bin));
        assert!(!precedes_system(&paths(&["/usr/bin"]), &bin));
    }

    #[test]
    fn completion_candidates_escape_colons() {
        assert_eq!(candidate("a:b", "line\nbreak"), "a\\:b:line break");
    }

    #[test]
    fn timeouts_kill_slow_programs() {
        let started = Instant::now();
        let result = run_with_timeout(Path::new("/bin/sleep"), &["5"], Duration::from_millis(200));
        assert_eq!(result.unwrap_err(), "timed out");
        assert!(started.elapsed() < Duration::from_secs(3));
        let (ok, stdout, _) = run_with_timeout(Path::new("/bin/echo"), &["hi"], Duration::from_secs(5)).unwrap();
        assert!(ok);
        assert_eq!(stdout, "hi\n");
        assert!(run_with_timeout(Path::new("/nonexistent/tool"), &[], Duration::from_secs(1)).is_err());
    }

    #[test]
    fn harness_permission_check_reports_timeouts_and_details() {
        assert_eq!(harness_permissions(None), (false, "not installed".to_string()));
        let (ok, detail) = harness_permissions(Some(Path::new("/usr/bin/false")));
        assert!(!ok);
        assert_eq!(detail, "no details");
    }
}
