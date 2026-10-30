//! `ul app` and `ul browser`: open a macOS application or the configured
//! homepage with `open`. Part of the core, so they are always installed.

use std::process::Command;

use crate::commands::exit_code;
use crate::config::Config;

pub const APP_HELP: &str = "Open a macOS application by name.
Usage: ul app <application>
Example: ul app \"Visual Studio Code\"
";

pub const BROWSER_HELP: &str = "Open the configured browser homepage in your default browser.
Usage: ul browser
Setting: apps.browser_url
Example: ul config set apps.browser_url \"https://duckduckgo.com/\"
";

fn is_help(args: &[String]) -> bool {
    matches!(args.first().map(String::as_str), Some("-h" | "--help" | "help"))
}

fn open(name: &str, args: &[String]) -> i32 {
    match Command::new("open").args(args).status() {
        Ok(status) => exit_code(status),
        Err(error) => {
            eprintln!("unlaw {name}: {error}");
            1
        }
    }
}

pub fn app(args: &[String]) -> i32 {
    if is_help(args) {
        print!("{APP_HELP}");
        return 0;
    }
    if args.is_empty() {
        eprintln!("Usage: ul app <application>");
        return 2;
    }
    open("app", &["-a".to_string(), args.join(" ")])
}

pub fn browser(args: &[String], config: &Config) -> i32 {
    if is_help(args) {
        print!("{BROWSER_HELP}");
        return 0;
    }
    if !args.is_empty() {
        eprintln!("Usage: ul browser");
        return 2;
    }
    open("browser", &[config.string("apps.browser_url")])
}
