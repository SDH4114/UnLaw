//! `ul-app`: Unlaw.app's program. Normally started by the app bundle or its
//! LaunchAgent (`ul gui install`); `--check` validates the app's files.

mod gui;
mod platform;

use std::time::Duration;

use unlaw_app::{runner, settings, spec};

const HELP: &str = "Unlaw.app: menu bar items, global hotkeys and a command palette for ul.
Usage: ul-app            Run the app (usually started by Unlaw.app; see `ul gui`)
       ul-app --check    Check app.toml and every command's app.toml, exit 1 on problems
       ul-app --version
Settings: <config dir>/app.toml (`ul gui config`); a command's look in the app:
commands/<name>/app.toml (`ul skills show app-integration`).
";

fn check() -> i32 {
    let mut problems = Vec::new();
    match std::fs::read_to_string(settings::path()) {
        Ok(text) => problems.extend(settings::parse(&text).1),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => problems.push(format!("{}: {error}", settings::path().display())),
    }
    match runner::find_ul() {
        None => problems.push("ul was not found (PATH, ~/.local/bin or UNLAW_BIN)".into()),
        Some(ul) => {
            let outcome = runner::run(&ul, &["commands".into(), "--json".into()], Duration::from_secs(30));
            match spec::parse_records(&outcome.stdout) {
                Ok(records) if outcome.ok() => problems.extend(spec::check_all(&records)),
                Ok(_) => problems.push(format!("ul commands --json: {}", outcome.summary(3))),
                Err(error) => problems.push(error),
            }
        }
    }
    if problems.is_empty() {
        println!("App settings and command app.toml files are valid.");
        0
    } else {
        for problem in &problems {
            eprintln!("ul-app: {problem}");
        }
        1
    }
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let code = match args.iter().map(String::as_str).collect::<Vec<_>>().as_slice() {
        ["-h" | "--help"] => {
            print!("{HELP}");
            0
        }
        ["--version"] => {
            println!("Unlaw.app {}", env!("CARGO_PKG_VERSION"));
            0
        }
        ["--check"] => check(),
        // Finder passes -psn_... to apps started by double click on old macOS.
        [] => gui::run(),
        [first, ..] if first.starts_with("-psn_") => gui::run(),
        _ => {
            eprint!("{HELP}");
            2
        }
    };
    std::process::exit(code);
}
