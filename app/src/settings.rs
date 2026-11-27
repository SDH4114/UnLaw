//! `<config dir>/app.toml`: settings of the app alone (hotkeys, pinned items,
//! look). Everything shared with the terminal (storage, apps, desk, awake...)
//! stays in config.toml, which the app reads through `ul config get`. A
//! mistake never stops the app: it is a warning and that entry is skipped.

use std::path::PathBuf;

use toml_edit::{Array, DocumentMut, Item, TableLike, Value as Toml};

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
# Or template = "name" instead of command: opens that saved template's windows.
# [[hotkey]]
# keys = "ctrl+alt+a"
# command = "awake"
# action = "2h"

[menubar]
# Commands shown in the menu bar, left to right; the UL menu is always there.
# Pin or unpin with the pin on a command's tile (Commands), or right-click it in the palette.
items = ["sys", "awake", "desk"]
# What the System item shows: cpu, memory, pressure, gpu, network, battery, power.
sys = ["cpu", "memory"]
# Live text (time left, CPU...) next to each pinned item that has a status.
show_status = true

[look]
# auto, light or dark.
theme = "auto"
# Unlaw in the Dock with its main window (System, Clipboard, Games, Desk...);
# false keeps it a menu bar app only. Takes effect when the app starts again.
dock = true
"#;

#[derive(Clone, Debug, PartialEq)]
pub enum Target {
    Panel,
    Open,
    Run,
    Action(String),
    /// `template = "name"`: starts that template (`ul _template-launch name`).
    Template(String),
}

/// The `command` of a hotkey that starts a template (its `action` is the template's name
/// on the Settings page; in app.toml it is written `template = "name"`).
pub const TEMPLATE: &str = "template";

/// A template name `ul template` saves: letters, digits, `-_.`, not starting with `-` or `.`.
pub fn template_name_ok(name: &str) -> bool {
    (1..=64).contains(&name.len())
        && !name.starts_with(['-', '.'])
        && name.chars().all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.'))
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

/// The System item's readings: id, label in Settings, template over `ul sys --json`.
pub const SYS_METRICS: &[(&str, &str, &str)] = &[
    ("cpu", "CPU", "CPU {cpu.usage_percent|int}%"),
    ("memory", "Memory", "RAM {memory.used_bytes/memory.total_bytes|pct}"),
    ("pressure", "Memory pressure", "Pressure {memory.pressure_percent|int}%"),
    ("gpu", "GPU", "GPU {gpu.usage_percent|int}%"),
    ("network", "Network", "↓ {network.download_bytes_per_sec|speed}"),
    ("battery", "Battery", "{battery.percent|int}%"),
    ("power", "Power draw", "{battery.system_power_watts|int} W"),
];
pub const DEFAULT_SYS: [&str; 2] = ["cpu", "memory"];

/// The System item's text for the chosen readings, in the order of SYS_METRICS.
pub fn sys_template(chosen: &[String]) -> Option<String> {
    let parts: Vec<&str> = SYS_METRICS
        .iter()
        .filter(|(id, _, _)| chosen.iter().any(|item| item == id))
        .map(|(_, _, template)| *template)
        .collect();
    (!parts.is_empty()).then(|| parts.join(" · "))
}

/// The `ul sys` parts the chosen readings need, so the menu bar reads only those
/// (`ul sys cpu memory --json` costs a fraction of every part: no system_profiler, ps, disks).
pub fn sys_sections(chosen: &[String]) -> Vec<&'static str> {
    let mut sections = Vec::new();
    for (id, _, _) in SYS_METRICS {
        if !chosen.iter().any(|item| item == id) {
            continue;
        }
        let section = match *id {
            "memory" | "pressure" => "memory",
            "power" => "battery",
            other => other,
        };
        if !sections.contains(&section) {
            sections.push(section);
        }
    }
    sections
}

#[derive(Clone, Debug, PartialEq)]
pub struct Settings {
    pub palette: Option<Hotkey>,
    pub bindings: Vec<Binding>,
    pub menubar: Vec<String>,
    /// Readings the System item shows (ids from SYS_METRICS); empty = icon only.
    pub sys: Vec<String>,
    pub show_status: bool,
    pub theme: Theme,
    pub dock: bool,
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

/// A menu bar item that opens one application (`app:Safari`): pinned from Open app.
pub const APP_PIN: &str = "app:";

/// The application of an `app:` item: its name as `ul app` takes it.
pub fn pinned_app(item: &str) -> Option<&str> {
    item.strip_prefix(APP_PIN).filter(|name| app_name_ok(name))
}

/// An application's name: printable, no folder separators, not an option.
pub fn app_name_ok(name: &str) -> bool {
    (1..=80).contains(&name.chars().count())
        && !name.starts_with(['-', '.', ' '])
        && !name.ends_with(' ')
        && !name.contains('/')
        && !name.chars().any(char::is_control)
}

/// A command name or an `app:` item.
pub fn menubar_item_ok(item: &str) -> bool {
    command_name_ok(item) || pinned_app(item).is_some()
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

/// The menu bar items when app.toml names none.
pub const DEFAULT_MENUBAR: [&str; 3] = ["sys", "awake", "desk"];
const DEFAULT_PALETTE: &str = "ctrl+space";

/// A section as a table, also when written inline (`menubar = { items = [...] }`).
fn section<'a>(document: &'a DocumentMut, key: &str, warnings: &mut Vec<String>) -> Option<&'a dyn TableLike> {
    let item = document.get(key)?;
    let table = item.as_table_like();
    if table.is_none() {
        warnings.push(format!("{FILE}: {key} must be a table ([{key}])"));
    }
    table
}

fn parse_document(document: &DocumentMut, warnings: &mut Vec<String>) -> (Settings, ()) {
    // Missing keys keep their defaults; `palette = ""` turns the palette key off.
    let mut settings = Settings {
        palette: hotkey::parse(DEFAULT_PALETTE).ok(),
        bindings: Vec::new(),
        menubar: DEFAULT_MENUBAR.map(String::from).to_vec(),
        sys: DEFAULT_SYS.map(String::from).to_vec(),
        show_status: true,
        theme: Theme::Auto,
        dock: true,
    };
    for (key, _) in document.iter() {
        if !["hotkeys", "hotkey", "menubar", "look"].contains(&key) {
            warnings.push(format!("{FILE}: unknown setting {key}"));
        }
    }
    if let Some(table) = section(document, "hotkeys", warnings) {
        for (key, item) in table.iter() {
            match (key, item.as_str()) {
                ("palette", Some("")) => settings.palette = None,
                ("palette", Some(text)) => match hotkey::parse(text) {
                    Ok(key) => settings.palette = Some(key),
                    // A typo must not lock the user out of the app: keep the default key.
                    Err(error) => {
                        warnings.push(format!("{FILE}: hotkeys.palette: {error} (keeping {DEFAULT_PALETTE})"))
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
            if let Some((key, _)) =
                table.iter().find(|(key, _)| !["keys", "command", "action", "template"].contains(key))
            {
                warnings.push(format!("{what}: unknown key {key}"));
                continue;
            }
            if let Some(template) = get("template") {
                let Some(keys) = get("keys") else {
                    warnings.push(format!("{what}: needs keys"));
                    continue;
                };
                if !template_name_ok(&template) {
                    warnings.push(format!("{what}: {template:?} is not a template name"));
                    continue;
                }
                match hotkey::parse(&keys) {
                    Ok(hotkey)
                        if settings.palette.as_ref() == Some(&hotkey)
                            || settings.bindings.iter().any(|binding| binding.hotkey == hotkey) =>
                    {
                        warnings.push(format!("{what}: {keys} is already used"));
                    }
                    Ok(hotkey) => settings.bindings.push(Binding {
                        hotkey,
                        command: TEMPLATE.into(),
                        target: Target::Template(template),
                    }),
                    Err(error) => warnings.push(format!("{what}: {error}")),
                }
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
    if let Some(table) = section(document, "menubar", warnings) {
        for (key, item) in table.iter() {
            match key {
                "items" => match item.as_array() {
                    Some(items) => {
                        settings.menubar.clear();
                        for value in items.iter() {
                            match value.as_str() {
                                Some(name) if menubar_item_ok(name) => {
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
                "sys" => match item.as_array() {
                    Some(items) => {
                        settings.sys.clear();
                        for value in items.iter() {
                            match value.as_str() {
                                Some(id) if SYS_METRICS.iter().any(|(known, _, _)| *known == id) => {
                                    if !settings.sys.iter().any(|item| item == id) {
                                        settings.sys.push(id.to_string());
                                    }
                                }
                                _ => warnings.push(format!(
                                    "{FILE}: menubar.sys: {value} is not one of cpu, memory, pressure, gpu, network, battery, power"
                                )),
                            }
                        }
                    }
                    None => warnings.push(format!("{FILE}: menubar.sys must be a list")),
                },
                "show_status" => match item.as_bool() {
                    Some(on) => settings.show_status = on,
                    None => warnings.push(format!("{FILE}: menubar.show_status must be true or false")),
                },
                other => warnings.push(format!("{FILE}: unknown setting menubar.{other}")),
            }
        }
    }
    if let Some(table) = section(document, "look", warnings) {
        for (key, item) in table.iter() {
            if key == "dock" {
                match item.as_bool() {
                    Some(on) => settings.dock = on,
                    None => warnings.push(format!("{FILE}: look.dock must be true or false")),
                }
                continue;
            }
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

/// What the Settings page shows and sends back: plain values, no TOML.
#[derive(Clone, Debug, PartialEq)]
pub struct Form {
    pub palette: String,
    /// (keys, command, action); action is "panel", "open", "run" or an action id.
    pub hotkeys: Vec<(String, String, String)>,
    pub menubar: Vec<String>,
    pub sys: Vec<String>,
    pub show_status: bool,
    pub theme: String,
    pub dock: bool,
}

fn target_word(target: &Target) -> String {
    match target {
        Target::Panel => "panel".into(),
        Target::Open => "open".into(),
        Target::Run => "run".into(),
        Target::Action(id) | Target::Template(id) => id.clone(),
    }
}

impl Form {
    pub fn of(settings: &Settings) -> Form {
        Form {
            palette: settings.palette.as_ref().map(Hotkey::text).unwrap_or_default(),
            hotkeys: settings
                .bindings
                .iter()
                .map(|binding| (binding.hotkey.text(), binding.command.clone(), target_word(&binding.target)))
                .collect(),
            menubar: settings.menubar.clone(),
            sys: settings.sys.clone(),
            show_status: settings.show_status,
            theme: settings.theme.name().into(),
            dock: settings.dock,
        }
    }
}

/// Write a Settings page form into app.toml's text: only the keys it covers
/// change, comments and anything else stay. Refuses (and writes nothing) when
/// a value would be skipped on reading, so what the page shows is what applies.
pub fn apply(text: &str, form: &Form) -> Result<String, String> {
    let mut document: DocumentMut = text.parse().map_err(|error: toml_edit::TomlError| error.message().to_string())?;
    // An empty palette key is "off" (as `parse` reads it), not an error: a Settings save with it off used to fail.
    let palette = match form.palette.trim() {
        "" => None,
        keys => Some(hotkey::parse(keys).map_err(|error| format!("Palette key: {error}"))?),
    };
    let mut used: Vec<Hotkey> = palette.iter().cloned().collect();
    let mut tables = toml_edit::ArrayOfTables::new();
    for (index, (keys, command, action)) in form.hotkeys.iter().enumerate() {
        let what = format!("Hotkey {}", index + 1);
        let key = hotkey::parse(keys).map_err(|error| format!("{what}: {error}"))?;
        if used.contains(&key) {
            return Err(format!("{what}: {} is already used", key));
        }
        used.push(key.clone());
        if command == TEMPLATE {
            if !template_name_ok(action) {
                return Err(format!("{what}: choose a template"));
            }
            let mut table = toml_edit::Table::new();
            table.insert("keys", toml_edit::value(key.text()));
            table.insert("template", toml_edit::value(action.as_str()));
            tables.push(table);
            continue;
        }
        if !command_name_ok(command) {
            return Err(format!("{what}: choose a command"));
        }
        if action.is_empty() || action.chars().any(char::is_control) || action.len() > 64 {
            return Err(format!("{what}: choose what it does"));
        }
        let mut table = toml_edit::Table::new();
        table.insert("keys", toml_edit::value(key.text()));
        table.insert("command", toml_edit::value(command.as_str()));
        if action != "panel" {
            table.insert("action", toml_edit::value(action.as_str()));
        }
        tables.push(table);
    }
    if let Some(name) = form.menubar.iter().find(|name| !menubar_item_ok(name)) {
        return Err(format!("{name:?} is not a command name"));
    }
    if let Some(id) = form.sys.iter().find(|id| !SYS_METRICS.iter().any(|(known, _, _)| known == id)) {
        return Err(format!("{id:?} is not a System reading"));
    }
    if !["auto", "light", "dark"].contains(&form.theme.as_str()) {
        return Err("Theme must be auto, light or dark".into());
    }
    let table = |document: &mut DocumentMut, key: &str| -> Result<(), String> {
        let item = document.entry(key).or_insert(toml_edit::table());
        if item.as_table_like().is_none() {
            *item = toml_edit::table();
        }
        Ok(())
    };
    table(&mut document, "hotkeys")?;
    document["hotkeys"]["palette"] = toml_edit::value(palette.as_ref().map(Hotkey::text).unwrap_or_default());
    if tables.is_empty() {
        document.remove("hotkey");
    } else {
        document.insert("hotkey", Item::ArrayOfTables(tables));
    }
    table(&mut document, "menubar")?;
    let mut items = Array::new();
    for name in &form.menubar {
        if !items.iter().any(|item: &Toml| item.as_str() == Some(name.as_str())) {
            items.push(name.as_str());
        }
    }
    let menubar = document["menubar"].as_table_like_mut().expect("made a table above");
    match menubar.get_mut("items").and_then(Item::as_array_mut) {
        // Edit the list in place so a comment next to it survives.
        Some(existing) => {
            existing.clear();
            existing.extend(items.iter().cloned());
        }
        None => {
            menubar.insert("items", toml_edit::value(items));
        }
    }
    let mut sys = Array::new();
    for id in &form.sys {
        if !sys.iter().any(|item: &Toml| item.as_str() == Some(id.as_str())) {
            sys.push(id.as_str());
        }
    }
    document["menubar"]["sys"] = toml_edit::value(sys);
    document["menubar"]["show_status"] = toml_edit::value(form.show_status);
    table(&mut document, "look")?;
    document["look"]["theme"] = toml_edit::value(form.theme.as_str());
    document["look"]["dock"] = toml_edit::value(form.dock);
    Ok(document.to_string())
}

/// `menubar.items`, created with the default items when app.toml has none, so a
/// first pin adds to sys/awake/desk instead of replacing them.
fn items_array(document: &mut DocumentMut) -> Result<&mut Array, String> {
    let menubar = document.entry("menubar").or_insert(toml_edit::table());
    let menubar = menubar.as_table_like_mut().ok_or("menubar is not a table")?;
    let items = menubar.entry("items").or_insert(toml_edit::value(DEFAULT_MENUBAR.iter().copied().collect::<Array>()));
    items.as_array_mut().ok_or_else(|| "menubar.items is not a list".to_string())
}

/// Add `name` to the menu bar, keeping comments and everything else.
pub fn pin(text: &str, name: &str) -> Result<String, String> {
    if !menubar_item_ok(name) {
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

    fn form() -> Form {
        Form::of(&parse(DEFAULT).0)
    }

    #[test]
    fn an_application_can_be_pinned() {
        let text = pin(DEFAULT, "app:Visual Studio Code").unwrap();
        let (settings, warnings) = parse(&text);
        assert!(warnings.is_empty(), "{warnings:?}");
        assert!(settings.menubar.iter().any(|item| item == "app:Visual Studio Code"));
        assert_eq!(pinned_app("app:Safari"), Some("Safari"));
        for bad in ["app:", "app:-a", "app:../x", "app:a\nb", "app:.hidden"] {
            assert!(pin(DEFAULT, bad).is_err(), "{bad}");
        }
        assert_eq!(pinned_app("sys"), None);
    }

    #[test]
    fn the_menu_bar_reads_only_the_sys_parts_it_shows() {
        let chosen = |ids: &[&str]| ids.iter().map(|id| id.to_string()).collect::<Vec<_>>();
        assert_eq!(sys_sections(&chosen(&["cpu", "memory"])), ["cpu", "memory"]);
        assert_eq!(sys_sections(&chosen(&["pressure", "memory", "power", "battery"])), ["memory", "battery"]);
        assert_eq!(sys_sections(&chosen(&["network", "gpu"])), ["gpu", "network"]);
        assert!(sys_sections(&[]).is_empty());
    }

    #[test]
    fn the_settings_form_round_trips_and_keeps_comments() {
        let mut changed = form();
        assert_eq!(changed.palette, "ctrl+space");
        changed.palette = "Cmd+Shift+Space".into();
        changed.hotkeys =
            vec![("ctrl+alt+a".into(), "awake".into(), "2h".into()), ("f5".into(), "sys".into(), "panel".into())];
        changed.menubar = vec!["desk".into(), "sys".into(), "desk".into()];
        changed.show_status = false;
        changed.sys = vec!["power".into(), "cpu".into()];
        changed.theme = "dark".into();
        changed.dock = false;
        let text = apply(DEFAULT, &changed).unwrap();
        assert!(text.contains("# Opens the command palette."), "comments stay:\n{text}");
        let (settings, warnings) = parse(&text);
        assert!(warnings.is_empty(), "{warnings:?}");
        let back = Form::of(&settings);
        assert_eq!(back.palette, "shift+cmd+space");
        assert_eq!(
            back.hotkeys,
            vec![("ctrl+alt+a".into(), "awake".into(), "2h".into()), ("f5".into(), "sys".into(), "panel".into())]
        );
        assert_eq!(back.menubar, vec!["desk", "sys"]);
        assert_eq!(back.sys, vec!["power", "cpu"]);
        assert_eq!(
            sys_template(&back.sys).unwrap(),
            "CPU {cpu.usage_percent|int}% · {battery.system_power_watts|int} W"
        );
        assert_eq!(sys_template(&[]), None);
        assert_eq!((back.show_status, back.theme.as_str(), back.dock), (false, "dark", false));
        // Removing the last hotkey drops the [[hotkey]] tables.
        let none = apply(&text, &Form { hotkeys: Vec::new(), ..back }).unwrap();
        assert!(!none.contains("\n[[hotkey]]"), "only the commented example is left");
    }

    #[test]
    fn a_bad_settings_form_writes_nothing() {
        let bad = |change: fn(&mut Form)| {
            let mut changed = form();
            change(&mut changed);
            apply(DEFAULT, &changed).unwrap_err()
        };
        assert!(bad(|form| form.palette = "space".into()).contains("modifier"));
        // The palette key turned off ("") still saves.
        let off = parse("hotkeys = { palette = \"\" }\n");
        let text = apply("hotkeys = { palette = \"\" }\n", &Form::of(&off.0)).unwrap();
        assert_eq!(parse(&text).0.palette, None);
        // A shortcut that starts a template is written `template = "name"` and read back.
        let mut with_template = Form::of(&parse(DEFAULT).0);
        with_template.hotkeys.push(("ctrl+alt+w".into(), TEMPLATE.into(), "work".into()));
        let text = apply(DEFAULT, &with_template).unwrap();
        assert!(text.contains("template = \"work\""), "{text}");
        let (read, warnings) = parse(&text);
        assert!(warnings.is_empty(), "{warnings:?}");
        assert_eq!(read.bindings.last().unwrap().target, Target::Template("work".into()));
        with_template.hotkeys.last_mut().unwrap().2 = "../x".into();
        assert!(apply(DEFAULT, &with_template).unwrap_err().contains("choose a template"));
        assert!(bad(|form| form.hotkeys = vec![("ctrl+space".into(), "sys".into(), "panel".into())])
            .contains("already used"));
        assert!(bad(|form| form.hotkeys = vec![("ctrl+b".into(), "".into(), "panel".into())]).contains("command"));
        assert!(bad(|form| form.menubar = vec!["../x".into()]).contains("command name"));
        assert!(bad(|form| form.theme = "pink".into()).contains("Theme"));
        assert!(bad(|form| form.sys = vec!["fans".into()]).contains("System reading"));
        assert!(apply("not = [toml", &form()).is_err());
    }

    #[test]
    fn defaults_parse_cleanly() {
        let (settings, warnings) = parse(DEFAULT);
        assert!(warnings.is_empty(), "{warnings:?}");
        assert_eq!(settings.palette, Some(hotkey::parse("ctrl+space").unwrap()));
        assert_eq!(settings.menubar, vec!["sys", "awake", "desk"]);
        assert_eq!(settings.theme, Theme::Auto);
        assert!(settings.dock);
        assert!(!parse("[look]\ndock = false\n").0.dock);
        assert!(parse("[look]\ndock = 1\n").1[0].contains("look.dock"));
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
        assert_eq!(settings.palette, hotkey::parse("ctrl+space").ok(), "a typo keeps the default key");
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
    fn inline_tables_count() {
        let (settings, warnings) =
            parse("hotkeys = { palette = \"cmd+k\" }\nmenubar = { items = [\"git\"] }\nlook = { theme = \"dark\" }\n");
        assert!(warnings.is_empty(), "{warnings:?}");
        assert_eq!(settings.palette, hotkey::parse("cmd+k").ok());
        assert_eq!(settings.menubar, vec!["git"]);
        assert_eq!(settings.theme, Theme::Dark);
        assert_eq!(parse(&pin("menubar = { items = [\"git\"] }\n", "sys").unwrap()).0.menubar, vec!["git", "sys"]);
        assert!(parse("menubar = 3\n").1[0].contains("must be a table"));
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
        // Without menubar.items the defaults are kept: a first pin adds to them.
        assert_eq!(parse(&pin("", "sys").unwrap()).0.menubar, vec!["sys", "awake", "desk"]);
        assert_eq!(parse(&pin("[hotkeys]\n", "timer").unwrap()).0.menubar, vec!["sys", "awake", "desk", "timer"]);
        assert_eq!(parse(&unpin("", "sys").unwrap()).0.menubar, vec!["awake", "desk"]);
        assert!(pin(DEFAULT, "a b").is_err());
    }
}
