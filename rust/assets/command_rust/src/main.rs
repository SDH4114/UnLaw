//! Custom Unlaw command written in Rust.
//!
//! Edit this file and run `ul {{command_name}}`: Unlaw rebuilds the command
//! automatically when src/ or Cargo.toml change. Unlaw passes:
//!   UNLAW_COMMAND      command name, e.g. "{{command_name}}"
//!   UNLAW_COMMAND_DIR  this command's folder
//!   UNLAW_CONFIG_DIR   Unlaw configuration folder (config.toml lives here)
//!   UNLAW_STORAGE      resolved storage.root folder for files your command saves

use std::env;
use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = env::args().skip(1).collect();
    if matches!(args.first().map(String::as_str), Some("-h" | "--help" | "help")) {
        println!("Custom Unlaw command.");
        println!("Usage: ul {{command_name}} [arguments]");
        println!("Example: ul {{command_name}} hello");
        println!("Options: -h, --help show this help.");
        return ExitCode::SUCCESS;
    }
    println!("Command arguments: {}", args.join(" "));
    ExitCode::SUCCESS
}
