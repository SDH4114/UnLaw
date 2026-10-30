//! Commands compiled into the core. They run after user commands, so a
//! `commands/<name>/` folder still overrides them.

pub mod apps;
#[cfg(feature = "game")]
pub mod game;
#[cfg(feature = "lm")]
pub mod lm;
pub mod zip;

use crate::config::Config;

pub const BUILTINS: &[(&str, &str)] = &[
    ("app", apps::APP_HELP),
    ("browser", apps::BROWSER_HELP),
    #[cfg(feature = "game")]
    ("game", game::HELP),
    #[cfg(feature = "lm")]
    ("lm", lm::HELP),
    ("zip", zip::HELP),
];

pub fn is_builtin(name: &str) -> bool {
    BUILTINS.iter().any(|(builtin, _)| *builtin == name)
}

pub fn names() -> impl Iterator<Item = &'static str> {
    BUILTINS.iter().map(|(name, _)| *name)
}

pub fn summary(name: &str) -> &'static str {
    BUILTINS.iter().find(|(builtin, _)| *builtin == name).and_then(|(_, help)| help.lines().next()).unwrap_or("")
}

pub fn help(name: &str) -> &'static str {
    BUILTINS.iter().find(|(builtin, _)| *builtin == name).map(|(_, help)| *help).unwrap_or("")
}

pub fn run(name: &str, args: &[String], config: &Config) -> Option<i32> {
    Some(match name {
        "app" => apps::app(args),
        "browser" => apps::browser(args, config),
        #[cfg(feature = "game")]
        "game" => game::run(args, config),
        #[cfg(feature = "lm")]
        "lm" => lm::run(args, config),
        "zip" => zip::run(args, config),
        _ => return None,
    })
}

/// `ul doctor`'s local model rows; without the lm feature they say how to add it.
pub fn lm_server_status(port: u16) -> (bool, String) {
    #[cfg(feature = "lm")]
    return lm::server_status(port);
    #[cfg(not(feature = "lm"))]
    {
        let _ = port;
        (false, "not installed (ul features add lm)".into())
    }
}

pub fn lm_engine_status(storage: &std::path::Path) -> (bool, String) {
    #[cfg(feature = "lm")]
    return lm::engine_status(storage);
    #[cfg(not(feature = "lm"))]
    {
        let _ = storage;
        (false, "not installed (ul features add lm)".into())
    }
}
