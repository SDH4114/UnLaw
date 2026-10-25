//! `ul edit`: opens files in the configured editor. `core.editor = "auto"` picks
//! ule (installed next to ul), then $VISUAL / $EDITOR, then `open -t`.

use std::env;
use std::path::PathBuf;
use std::process::Command;

use crate::config::Config;
use crate::help::print_if_requested;

fn executable(path: &std::path::Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    path.metadata().map(|meta| meta.is_file() && meta.permissions().mode() & 0o111 != 0).unwrap_or(false)
}

/// ule next to the running ul (both are installed together), then on PATH.
pub fn ule_path() -> Option<PathBuf> {
    if let Some(dir) = env::current_exe().ok().and_then(|exe| exe.parent().map(PathBuf::from)) {
        let sibling = dir.join("ule");
        if executable(&sibling) {
            return Some(sibling);
        }
    }
    env::split_paths(&env::var_os("PATH")?).map(|dir| dir.join("ule")).find(|path| executable(path))
}

/// `core.editor` straight from config.toml, for when the file has other errors
/// (`ul config edit` must open the configured editor to fix them).
fn configured_raw() -> Option<String> {
    let text = std::fs::read_to_string(crate::config::config_file()).ok()?;
    let document: toml_edit::DocumentMut = text.parse().ok()?;
    document.get("core")?.get("editor")?.as_str().map(str::to_string)
}

/// The editor command as words, and where the choice came from (for doctor).
pub fn resolve(config: Option<&Config>) -> (Vec<String>, &'static str) {
    let configured = match config {
        Some(config) => config.string("core.editor"),
        None => configured_raw().unwrap_or_default(),
    };
    let configured = configured.trim();
    if !configured.is_empty() && configured != "auto" {
        if configured == "ule" {
            if let Some(path) = ule_path() {
                return (vec![path.to_string_lossy().into_owned()], "core.editor");
            }
        }
        return (configured.split_whitespace().map(str::to_string).collect(), "core.editor");
    }
    if let Some(path) = ule_path() {
        return (vec![path.to_string_lossy().into_owned()], "ule");
    }
    for name in ["VISUAL", "EDITOR"] {
        if let Some(value) = env::var(name).ok().filter(|value| !value.trim().is_empty()) {
            return (value.split_whitespace().map(str::to_string).collect(), if name == "VISUAL" { "$VISUAL" } else { "$EDITOR" });
        }
    }
    (vec!["open".into(), "-t".into()], "open -t")
}

/// Opens `paths` in the editor and waits for it; returns its exit code.
pub fn open(paths: &[PathBuf], config: Option<&Config>) -> i32 {
    let (mut words, _) = resolve(config);
    if words.first().is_some_and(|program| program == "open") && paths.is_empty() {
        eprintln!("unlaw edit: no terminal editor found; name a file, install ule (ul update) or set core.editor");
        return 2;
    }
    words.extend(paths.iter().map(|path| path.to_string_lossy().into_owned()));
    match Command::new(&words[0]).args(&words[1..]).status() {
        Ok(status) => status.code().unwrap_or(1),
        Err(error) => {
            eprintln!("unlaw edit: could not start {}: {error}", words[0]);
            1
        }
    }
}

pub fn run(args: &[String]) -> i32 {
    if print_if_requested("edit", args) {
        return 0;
    }
    if let Some(option) = args.iter().find(|arg| arg.starts_with('-') && arg.as_str() != "-" && !arg.starts_with('+')) {
        eprintln!("unlaw edit: unknown option {option}");
        eprintln!("Usage: ul edit [file[:line]]...");
        return 2;
    }
    // Invalid config.toml must not stop you from opening an editor to fix it.
    let config = crate::config::load().ok();
    let paths: Vec<PathBuf> = args.iter().map(PathBuf::from).collect();
    open(&paths, config.as_ref())
}
