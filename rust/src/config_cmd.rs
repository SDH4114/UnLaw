//! `ul config path|show|get|set|edit|check|reset`.

use std::fs;
use std::time::{SystemTime, UNIX_EPOCH};

use crate::config::{self, config_file, ConfigError};
use crate::help::print_if_requested;

const USAGE: &str = "Usage: ul config path|show|get|set|edit|check|reset";

fn edit() -> i32 {
    let path = config_file();
    let config = config::load().ok();
    let code = crate::editor::open(&[path], config.as_ref());
    if code != 0 {
        return code;
    }
    // Report problems right away instead of on the next command.
    match config::load() {
        Ok(_) => {
            println!("config.toml is valid.");
            0
        }
        Err(error) => {
            eprintln!("unlaw config: {error}");
            1
        }
    }
}

/// Local time as `YYYYmmdd-HHMMSS-micro`, like the Python backup names.
pub(crate) fn timestamp() -> String {
    let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default();
    let seconds = now.as_secs() as libc::time_t;
    let mut parts: libc::tm = unsafe { std::mem::zeroed() };
    unsafe { libc::localtime_r(&seconds, &mut parts) };
    format!(
        "{:04}{:02}{:02}-{:02}{:02}{:02}-{:06}",
        parts.tm_year + 1900,
        parts.tm_mon + 1,
        parts.tm_mday,
        parts.tm_hour,
        parts.tm_min,
        parts.tm_sec,
        now.subsec_micros()
    )
}

fn action(name: &str, rest: &[String]) -> Result<Option<i32>, ConfigError> {
    match (name, rest) {
        ("path", []) => println!("{}", config_file().display()),
        ("show", []) => print!("{}", fs::read_to_string(config_file())?),
        ("get", [key]) => {
            let config = config::load()?;
            let value = config.get(key).ok_or_else(|| ConfigError(format!("Unknown configuration key: {key}")))?;
            println!("{}", value.display());
        }
        ("set", [key, value @ ..]) if !value.is_empty() => {
            let raw = value.join(" ");
            let item = config::parse_value(&raw);
            config::set(key, item)?;
            let shown = config::load()?.get(key).map(|value| value.display()).unwrap_or(raw);
            println!("Set {key} = {shown}");
        }
        ("edit", []) => return Ok(Some(edit())),
        ("check", []) => {
            let errors = config::read_document().map(|_| config::load().err())?;
            if let Some(error) = errors {
                for line in error.0.split("; ") {
                    eprintln!("{line}");
                }
                return Ok(Some(2));
            }
            println!("Configuration is valid: {}", config_file().display());
        }
        ("reset", rest) => {
            if rest != ["--yes"] {
                eprintln!("unlaw config: Reset requires --yes.");
                return Ok(Some(2));
            }
            let backup = config_file().with_file_name(format!("config.toml.backup-{}", timestamp()));
            fs::copy(config_file(), &backup)?;
            config::reset()?;
            println!("Configuration reset. Backup: {}", backup.display());
        }
        _ => return Ok(None),
    }
    Ok(Some(0))
}

pub fn run(args: &[String]) -> i32 {
    if print_if_requested("config", args) {
        return 0;
    }
    let Some((name, rest)) = args.split_first() else {
        println!("{USAGE}");
        return 2;
    };
    match action(name, rest) {
        Ok(Some(code)) => code,
        Ok(None) => {
            eprintln!("{USAGE}");
            2
        }
        Err(error) => {
            eprintln!("unlaw config: {error}");
            2
        }
    }
}
