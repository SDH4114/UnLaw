//! Commands compiled into the core. They run after user commands, so a
//! `commands/<name>/` folder still overrides them.

pub mod game;
pub mod zip;

use crate::config::Config;

pub const BUILTINS: [(&str, &str); 2] = [("game", game::HELP), ("zip", zip::HELP)];

pub fn is_builtin(name: &str) -> bool {
    BUILTINS.iter().any(|(builtin, _)| *builtin == name)
}

pub fn names() -> impl Iterator<Item = &'static str> {
    BUILTINS.iter().map(|(name, _)| *name)
}

pub fn summary(name: &str) -> &'static str {
    BUILTINS.iter().find(|(builtin, _)| *builtin == name).and_then(|(_, help)| help.lines().next()).unwrap_or("")
}

pub fn run(name: &str, args: &[String], config: &Config) -> Option<i32> {
    Some(match name {
        "game" => game::run(args, config),
        "zip" => zip::run(args, config),
        _ => return None,
    })
}
