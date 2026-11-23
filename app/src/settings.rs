//! `<config dir>/app.toml`: settings of the app alone (hotkeys, pinned items,
//! look). Everything shared with the terminal (storage, apps, desk, awake...)
//! stays in config.toml, which the app reads through `ul config get`. A
//! mistake never stops the app: it is a warning and that entry is skipped.

use std::path::PathBuf;

use toml_edit::{Array, DocumentMut, Item, Value as Toml};

use crate::hotkey::{self, Hotkey};

pub const FILE: &str = "app.toml";

pub const DEFAULT: &str = r#"# Unlaw.app settings (ul gui config). Shared settings (storage.root, apps.*, desk.*,
# awake and timer defaults) stay in config.toml; the app reads them from there.

[hotkeys]
# Opens the command palette. Modifiers: ctrl, alt (option), shift, cmd.
palette = "ctrl+space"

# More hotkeys: one [[hotkey]] each.
# command = a command name; action = "panel" (default: its form or menu),
# "open" (its page window), "run" (run it), or an action id from its app.toml.
# [[hotkey]]
# keys = "ctrl+alt+a"
# command = "awake"
# action = "2h"

[menubar]
# Commands shown in the menu bar, left to right; the UL menu is always there.
# Right-click a command in the palette to pin or unpin it.
items = ["sys", "awake", "desk"]
# Live text (time left, CPU...) next to each pinned item that has a status.
show_status = true

[look]
# auto, light or dark.
theme = "auto"
"#;

#[derive(Clone, Debug, PartialEq)]
pub enum Target {
    Panel,
    Open,
    Run,
    Action(String),
}

#[derive(Clone, Debug, PartialEq)]
pub struct Binding {
    pub hotkey: Hotkey,
    pub command: String,
    pub target: Target,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Theme {
    Auto,
    Light,
    Dark,
}

impl Theme {
    pub fn name(self) -> &'static str {
        match self {
            Theme::Auto => "auto",
            Theme::Light => "light",
            Theme::Dark => "dark",
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Settings {
    pub palette: Option<Hotkey>,
    pub bindings: Vec<Binding>,
    pub menubar: Vec<String>,
    pub show_status: bool,
    pub theme: Theme,
}

pub fn path() -> PathBuf {
    config_dir().join(FILE)
}

/// Same rule as the core: `$XDG_CONFIG_HOME/unlaw`, else `~/.config/unlaw`.
pub fn config_dir() -> PathBuf {
    match std::env::var_os("XDG_CONFIG_HOME").filter(|value| !value.is_empty()) {
        Some(base) => PathBuf::from(base).join("unlaw"),
        None => home().join(".config").join("unlaw"),
    }
}

pub fn home() -> PathBuf {
    std::env::var_os("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("/"))
}

fn command_name_ok(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 64
        && !name.starts_with(['-', '.', '_'])
        && name.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.')
}

/// Settings and the warnings about what was skipped.
pub fn parse(text: &str) -> (Settings, Vec<String>) {
    let mut warnings = Vec::new();
    let (defaults, _) = parse_document(&DEFAULT.parse().expect("the default settings parse"), &mut Vec::new());
    let document: DocumentMut = match text.parse() {
        Ok(document) => document,
        Err(error) => {
            let error: toml_edit::TomlError = error;
            warnings.push(format!("{FILE}: {} (using the defaults)", error.message()));
            return (defaults, warnings);
        }
    };
    let (settings, _) = parse_document(&document, &mut warnings);
    (settings, warnings)
}

fn parse_document(document: &DocumentMut, warnings: &mut Vec<String>) -> (Settings, ()) {
    // Missing keys keep their defaults; `palette = ""` turns the palette key off.
    let mut settings = Settings {
        palette: hotkey::parse("ctrl+space").ok(),
        bindings: Vec::new(),
        menubar: ["sys", "awake", "desk"].map(String::from).to_vec(),
        show_status: true,
        theme: Theme::Auto,
    };
    for (key, _) in document.iter() {
        if !["hotkeys", "hotkey", "menubar", "look"].contains(&key) {
            warnings.push(format!("{FILE}: unknown setting {key}"));
        }
    }
    if let Some(table) = document.get("hotkeys").and_then(Item::as_table) {
        for (key, item) in table.iter() {
            match (key, item.as_str()) {
                ("palette", Some("")) => settings.palette = None,
                ("palette", Some(text)) => match hotkey::parse(text) {
                    Ok(key) => settings.palette = Some(key),
                    Err(error) => {
                        settings.palette = None;
                        warnings.push(format!("{FILE}: hotkeys.palette: {error}"));
                    }
                },
                ("palette", None) => warnings.push(format!("{FILE}: hotkeys.palette must be text")),
                (other, _) => warnings.push(format!("{FILE}: unknown setting hotkeys.{other}")),
            }
        }
    }
    if let Some(array) = document.get("hotkey").and_then(Item::as_array_of_tables) {
        for (index, table) in array.iter().enumerate() {
            let what = format!("{FILE}: hotkey[{}]", index + 1);
            let get = |key: &str| table.get(key).and_then(Item::as_str).map(str::to_string);
            if let Some((key, _)) = table.iter().find(|(key, _)| !["keys", "command", "action"].contains(key)) {
                warnings.push(format!("{what}: unknown key {key}"));
                continue;
            }
            let (Some(keys), Some(command)) = (get("keys"), get("command")) else {
                warnings.push(format!("{what}: needs keys and command"));
                continue;
            };
            if !command_name_ok(&command) {
                warnings.push(format!("{what}: {command:?} is not a command name"));
                continue;
            }
            let target = match get("action").as_deref() {
                None | Some("panel") => Target::Panel,
                Some("open") => Target::Open,
                Some("run") => Target::Run,
                Some(id) => Target::Action(id.to_string()),
            };
            match hotkey::parse(&keys) {
                Ok(hotkey)
                    if settings.palette.as_ref() == Some(&hotkey)
                        || settings.bindings.iter().any(|binding| binding.hotkey == hotkey) =>
                {
                    warnings.push(format!("{what}: {keys} is already used"));
                }
                Ok(hotkey) => settings.bindings.push(Binding { hotkey, command, target }),
                Err(error) => warnings.push(format!("{what}: {error}")),
            }
        }
    } else if document.contains_key("hotkey") {
        warnings.push(format!("{FILE}: hotkey must be written as [[hotkey]] tables"));
    }
    if let Some(table) = document.get("menubar").and_then(Item::as_table) {
        for (key, item) in table.iter() {
            match key {
                "items" => match item.as_array() {
                    Some(items) => {
                        settings.menubar.clear();
                        for value in items.iter() {
                            match value.as_str() {
                                Some(name) if command_name_ok(name) => {
                                    if !settings.menubar.iter().any(|item| item == name) {
                                        settings.menubar.push(name.to_string());
                                    }
                                }
                                _ => warnings.push(format!("{FILE}: menubar.items: {value} is not a command name")),
                            }
                        }
                    }
                    None => warnings.push(format!("{FILE}: menubar.items must be a list of names")),
                },
                "show_status" => match item.as_bool() {
                    Some(on) => settings.show_status = on,
                    None => warnings.push(format!("{FILE}: menubar.show_status must be true or false")),
                },
                other => warnings.push(format!("{FILE}: unknown setting menubar.{other}")),
            }
        }
    }
    if let Some(table) = document.get("look").and_then(Item::as_table) {
        for (key, item) in table.iter() {
            match (key, item.as_str()) {
                ("theme", Some("auto")) => settings.theme = Theme::Auto,
                ("theme", Some("light")) => settings.theme = Theme::Light,
                ("theme", Some("dark")) => settings.theme = Theme::Dark,
                ("theme", _) => warnings.push(format!("{FILE}: look.theme must be auto, light or dark")),
                (other, _) => warnings.push(format!("{FILE}: unknown setting look.{other}")),
            }
        }
    }
    (settings, ())
}

fn items_array(document: &mut DocumentMut) -> Result<&mut Array, String> {
    let menubar = document.entry("menubar").or_insert(toml_edit::table());
    let menubar = menubar.as_table_mut().ok_or("menubar is not a table")?;
    let items = menubar.entry("items").or_insert(toml_edit::value(Array::new()));
    items.as_array_mut().ok_or_else(|| "menubar.items is not a list".to_string())
}

/// Add `name` to the menu bar, keeping comments and everything else.
pub fn pin(text: &str, name: &str) -> Result<String, String> {
    if !command_name_ok(name) {
        return Err(format!("{name:?} is not a command name"));
    }
    let mut document: DocumentMut = text.parse().map_err(|error: toml_edit::TomlError| error.message().to_string())?;
    let items = items_array(&mut document)?;
    if !items.iter().any(|item| item.as_str() == Some(name)) {
        items.push(name);
    }
    Ok(document.to_string())
}

/// Take `name` off the menu bar.
pub fn unpin(text: &str, name: &str) -> Result<String, String> {
    let mut document: DocumentMut = text.parse().map_err(|error: toml_edit::TomlError| error.message().to_string())?;
    let items = items_array(&mut document)?;
    items.retain(|item: &Toml| item.as_str() != Some(name));
    Ok(document.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_parse_cleanly() {
        let (settings, warnings) = parse(DEFAULT);
        assert!(warnings.is_empty(), "{warnings:?}");
        assert_eq!(settings.palette, Some(hotkey::parse("ctrl+space").unwrap()));
        assert_eq!(settings.menubar, vec!["sys", "awake", "desk"]);
        assert_eq!(settings.theme, Theme::Auto);
    }

    #[test]
    fn mistakes_are_warnings_and_the_rest_works() {
        let text = r#"
[hotkeys]
palette = "ctrl+nonsense"
[[hotkey]]
keys = "ctrl+alt+a"
command = "awake"
action = "2h"
[[hotkey]]
keys = "ctrl+alt+a"
command = "sys"
[[hotkey]]
keys = "q"
command = "desk"
[[hotkey]]
keys = "ctrl+alt+d"
command = "../x"
[[hotkey]]
keys = "ctrl+alt+e"
[menubar]
items = ["sys", "sys", 3, "-x"]
show_status = "yes"
[look]
theme = "pink"
[other]
"#;
        let (settings, warnings) = parse(text);
        assert_eq!(settings.palette, None);
        assert_eq!(settings.bindings.len(), 1);
        assert_eq!(settings.bindings[0].target, Target::Action("2h".into()));
        assert_eq!(settings.menubar, vec!["sys"]);
        assert!(settings.show_status);
        let all = warnings.join("\n");
        for part in [
            "palette",
            "already used",
            "a modifier",
            "not a command name",
            "needs keys",
            "show_status",
            "theme",
            "unknown setting other",
        ] {
            assert!(all.contains(part), "missing {part:?} in {all}");
        }
    }

    #[test]
    fn a_broken_file_falls_back_to_defaults() {
        let (settings, warnings) = parse("[hotkeys\n");
        assert_eq!(settings.menubar, vec!["sys", "awake", "desk"]);
        assert!(warnings[0].contains("using the defaults"));
    }

    #[test]
    fn pin_and_unpin_keep_comments() {
        let pinned = pin(DEFAULT, "timer").unwrap();
        assert!(pinned.contains("# Opens the command palette"));
        assert_eq!(parse(&pinned).0.menubar, vec!["sys", "awake", "desk", "timer"]);
        assert_eq!(pin(&pinned, "timer").unwrap(), pinned, "pinning twice changes nothing");
        let unpinned = unpin(&pinned, "awake").unwrap();
        assert_eq!(parse(&unpinned).0.menubar, vec!["sys", "desk", "timer"]);
        assert_eq!(parse(&pin("", "sys").unwrap()).0.menubar, vec!["sys"]);
        assert!(pin(DEFAULT, "a b").is_err());
    }
}
