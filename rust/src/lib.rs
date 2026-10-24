//! Unlaw core: dispatcher, configuration and system commands. Every other
//! command is a standalone file in `~/.config/unlaw/commands/<name>/`.

#[allow(dead_code)]
mod assets {
    include!(concat!(env!("OUT_DIR"), "/assets.rs"));
}
mod builtin;
mod commands;
mod config;
mod config_cmd;
mod help;
mod layout;
mod shell;
mod skills;
mod system;
mod update;
mod util;
mod workspace;

use std::collections::BTreeSet;
use std::env;
use std::time::Duration;

use crate::commands::RunOptions;

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
/// Short git commit of this build, or empty when it is unknown.
pub const COMMIT: &str = env!("UNLAW_COMMIT");

/// `Unlaw 3.0.0 (dd061d1)`.
pub fn version_line() -> String {
    if COMMIT.is_empty() {
        format!("Unlaw {VERSION}")
    } else {
        format!("Unlaw {VERSION} ({COMMIT})")
    }
}

const RAW_SYSTEM_COMMANDS: [&str; 6] = ["completion", "config", "doctor", "init", "update", "version"];

fn system(name: &str, args: &[String]) -> Option<i32> {
    Some(match name {
        "commands" => system::list_commands(args),
        "completion" => system::completion(args),
        "config" => config_cmd::run(args),
        "create" => system::create(args),
        "doctor" => system::doctor(args),
        "init" => system::init(args),
        "list" => system::list_all(args),
        "skills" => skills::run(args),
        "templates" => system::list_templates(args),
        "update" => update::run(args),
        "venv" => system::venv(args),
        "version" => system::version(args),
        "which" => system::which_command(args),
        _ => return None,
    })
}

pub fn expand_alias(argv: &[String], aliases: &[(String, Vec<String>)]) -> Result<Vec<String>, String> {
    let mut expanded = argv.to_vec();
    let mut visited: Vec<String> = Vec::new();
    while let Some(tokens) = expanded.first().and_then(|name| aliases.iter().find(|(alias, _)| alias == name)) {
        let name = &tokens.0;
        if visited.contains(name) {
            visited.push(name.clone());
            return Err(format!("Alias cycle: {}", visited.join(" -> ")));
        }
        visited.push(name.clone());
        expanded = tokens.1.iter().cloned().chain(expanded.into_iter().skip(1)).collect();
    }
    Ok(expanded)
}

fn hidden(name: &str, args: &[String]) -> Option<i32> {
    let usage = |text: &str| {
        eprintln!("{text}");
        2
    };
    let report = |error: &dyn std::fmt::Display| {
        eprintln!("unlaw: {error}");
        1
    };
    Some(match name {
        "_shell-init" => {
            if args != ["zsh"] {
                return Some(usage("Usage: ul _shell-init zsh"));
            }
            print!("{}", shell::ZSH_INTEGRATION);
            0
        }
        "_template-path" => {
            let [template] = args else {
                return Some(usage("Usage: ul _template-path <name>"));
            };
            if !workspace::exists(template) {
                return Some(3);
            }
            match shell::template_path(template) {
                Ok(path) => {
                    println!("{}", path.display());
                    0
                }
                Err(error) => report(&error),
            }
        }
        "_template-launch" => {
            let [template] = args else {
                return Some(usage("Usage: ul _template-launch <name>"));
            };
            let config = config::load().ok();
            match workspace::load(template).map_err(shell::ShellError::from).and_then(|t| shell::launch(&t, config.as_ref())) {
                Ok(code) => code,
                Err(error) => report(&error),
            }
        }
        "_venv-path" => {
            if !args.is_empty() {
                return Some(usage("Usage: ul _venv-path"));
            }
            let config = config::load().ok();
            let python = commands::python(config.as_ref()).unwrap_or_else(|| "python3".into());
            let result = env::current_dir()
                .map_err(|error| shell::ShellError(error.to_string()))
                .and_then(|cwd| shell::ensure_venv(&cwd, &python));
            match result {
                Ok(activation) => {
                    println!("{}", activation.display());
                    0
                }
                Err(error) => report(&error),
            }
        }
        "_complete" => system::complete(args),
        _ => return None,
    })
}

fn unknown(name: &str, aliases: &[(String, Vec<String>)]) -> i32 {
    let mut available: BTreeSet<String> = help::system_names().map(str::to_string).collect();
    available.extend(commands::discover().into_keys());
    available.extend(builtin::names().map(str::to_string));
    available.extend(aliases.iter().map(|(alias, _)| alias.clone()));
    let available: Vec<String> = available.into_iter().collect();
    let suggestions = util::close_matches(name, &available, 3, 0.55);
    eprintln!("unlaw: Unknown command: {name}");
    if suggestions.is_empty() {
        eprintln!("Run `ul commands` to see available commands.");
    } else {
        eprintln!("Did you mean: {}?", suggestions.join(", "));
    }
    2
}

pub fn main_with(argv: Vec<String>) -> i32 {
    if let Err(error) = layout::ensure_layout() {
        eprintln!("unlaw: Could not initialize configuration: {error}");
        return 1;
    }
    let mut args = argv;
    let (mut dry_run, mut verbose) = (false, false);
    while let Some(flag) = args.first() {
        match flag.as_str() {
            "--dry-run" => dry_run = true,
            "--verbose" => verbose = true,
            "--no-color" => {}
            _ => break,
        }
        args.remove(0);
    }
    if args == ["--version"] {
        println!("{}", version_line());
        return 0;
    }
    if args.len() > 1 && args[0] == "help" {
        args.remove(0);
        args.push("--help".into());
    }
    if args.is_empty() || ["-h", "--help", "help"].contains(&args[0].as_str()) {
        print!("{}", help::HELP);
        return 0;
    }

    let (name, rest) = (args[0].clone(), args[1..].to_vec());
    if let Some(code) = hidden(&name, &rest) {
        return code;
    }
    if RAW_SYSTEM_COMMANDS.contains(&name.as_str()) {
        return system(&name, &rest).unwrap_or(2);
    }
    let config = match config::load() {
        Ok(config) => config,
        Err(error) => {
            eprintln!("unlaw: {error}");
            return 2;
        }
    };
    if name != "skills" {
        skills::refresh_if_stale(&config);
    }
    if let Some(code) = system(&name, &rest) {
        if name == "create" && code == 0 {
            skills::refresh_if_stale(&config);
        }
        return code;
    }
    let aliases = config.aliases();
    let expanded = match expand_alias(&args, &aliases) {
        Ok(expanded) => expanded,
        Err(error) => {
            eprintln!("unlaw: {error}");
            return 2;
        }
    };
    let (name, rest) = (&expanded[0], &expanded[1..]);
    if let Some(code) = system(name, rest) {
        return code;
    }
    let Some(command) = commands::resolve(name) else {
        if let Some(code) = builtin::run(name, rest, &config) {
            return code;
        }
        return match workspace::discover() {
            Ok(templates) if templates.contains_key(name) => system::run_template_hint(name, rest),
            Ok(_) => unknown(name, &aliases),
            Err(error) => {
                eprintln!("unlaw: {error}");
                2
            }
        };
    };
    let timeout = config.int("core.command_timeout").max(0) as u64;
    let options = RunOptions {
        dry_run,
        verbose: verbose || config.flag("core.verbose") || config.flag("core.show_timing"),
        timeout: Duration::from_secs(timeout),
    };
    commands::run(&command, rest, &config, &options)
}

pub fn run() -> i32 {
    let argv: Vec<String> = env::args_os().skip(1).map(|arg| arg.to_string_lossy().into_owned()).collect();
    main_with(argv)
}

/// `ula` and `unlawagent`: shortcuts for `ul agent ...`.
pub fn run_agent() -> i32 {
    let argv = std::iter::once("agent".to_string()).chain(env::args_os().skip(1).map(|arg| arg.to_string_lossy().into_owned())).collect();
    main_with(argv)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn words(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn aliases_expand_and_append() {
        let aliases = vec![("c".to_string(), words(&["capture", "preset"])), ("cc".to_string(), words(&["c", "x"]))];
        assert_eq!(expand_alias(&words(&["cc", "extra"]), &aliases).unwrap(), words(&["capture", "preset", "x", "extra"]));
    }

    #[test]
    fn alias_cycles_are_errors() {
        let aliases = vec![("a".to_string(), words(&["b"])), ("b".to_string(), words(&["a"]))];
        assert_eq!(expand_alias(&words(&["a"]), &aliases).unwrap_err(), "Alias cycle: a -> b -> a");
    }
}
