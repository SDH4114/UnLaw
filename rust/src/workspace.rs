//! Saved templates: `templates/projects/<name>.toml`. A template is a working
//! environment: a project folder (the shell `cd`s there) and windows to open
//! and place: apps, Ghostty windows with tabs and splits, browser sites.
//!
//! Version 2 (`version = 2`) is the current format; the original three-field
//! format (`path`, `app`, `ai`) is still read and launched as before.

use std::collections::BTreeMap;
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};

use toml_edit::{DocumentMut, Item, Table, Value};

use crate::config::templates_dir;
use crate::util::{expand_user, home, Json};

#[derive(Debug)]
pub struct TemplateError(pub String);

impl fmt::Display for TemplateError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

pub type Result<T> = std::result::Result<T, TemplateError>;

#[derive(Clone, Debug, PartialEq)]
pub struct Template {
    pub name: String,
    /// Project folder, absolute (`~` already expanded).
    pub path: PathBuf,
    /// Hide every other app on launch (`--focus` / `--no-focus` override it).
    pub focus: bool,
    pub windows: Vec<Window>,
    /// Read from the original `path`/`app`/`ai` format.
    pub legacy: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Window {
    /// An app name for `open -a`, or `browser` for the default browser.
    pub app: String,
    /// Folder, file or URL handed to the app; relative paths start at the project folder.
    pub open: Option<String>,
    pub frame: Option<Frame>,
    /// 1 = the main display.
    pub screen: u32,
    /// Ghostty only: tabs with split panes.
    pub tabs: Vec<Tab>,
    /// `browser` only.
    pub urls: Vec<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Tab {
    pub panes: Vec<Pane>,
}

#[derive(Clone, Debug, PartialEq, Default)]
pub struct Pane {
    /// Working directory; relative paths start at the project folder, default is the folder itself.
    pub dir: Option<String>,
    /// Typed into the shell after it starts, so the pane stays a shell when the command exits.
    pub run: Option<String>,
    /// How this pane splits off the previous one (`right`, `down`, `left`, `up`); not for the first pane.
    pub split: Option<String>,
}

/// A rectangle in fractions of the display's usable area (menu bar and Dock excluded).
#[derive(Clone, Debug, PartialEq)]
pub struct Frame {
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    App,
    Terminal,
    Browser,
}

pub const BROWSER: &str = "browser";
pub const TERMINAL_APP: &str = "Ghostty";
pub const SPLITS: [&str; 4] = ["right", "down", "left", "up"];
const LEGACY_APPS: [&str; 2] = ["obsidian", "zed"];

pub const PRESETS: &[(&str, [f64; 4])] = &[
    ("full", [0.0, 0.0, 1.0, 1.0]),
    ("left", [0.0, 0.0, 0.5, 1.0]),
    ("right", [0.5, 0.0, 0.5, 1.0]),
    ("top", [0.0, 0.0, 1.0, 0.5]),
    ("bottom", [0.0, 0.5, 1.0, 0.5]),
    ("top-left", [0.0, 0.0, 0.5, 0.5]),
    ("top-right", [0.5, 0.0, 0.5, 0.5]),
    ("bottom-left", [0.0, 0.5, 0.5, 0.5]),
    ("bottom-right", [0.5, 0.5, 0.5, 0.5]),
    ("left-third", [0.0, 0.0, 1.0 / 3.0, 1.0]),
    ("center-third", [1.0 / 3.0, 0.0, 1.0 / 3.0, 1.0]),
    ("right-third", [2.0 / 3.0, 0.0, 1.0 / 3.0, 1.0]),
    ("left-two-thirds", [0.0, 0.0, 2.0 / 3.0, 1.0]),
    ("right-two-thirds", [1.0 / 3.0, 0.0, 2.0 / 3.0, 1.0]),
    ("center", [0.15, 0.1, 0.7, 0.8]),
];

impl Frame {
    pub fn preset(name: &str) -> Option<Frame> {
        PRESETS.iter().find(|(preset, _)| *preset == name).map(|(_, [x, y, w, h])| Frame { x: *x, y: *y, w: *w, h: *h })
    }

    /// The preset this frame matches within half a percent, if any.
    pub fn preset_name(&self) -> Option<&'static str> {
        let close = |a: f64, b: f64| (a - b).abs() <= 0.005;
        PRESETS
            .iter()
            .find(|(_, [x, y, w, h])| close(self.x, *x) && close(self.y, *y) && close(self.w, *w) && close(self.h, *h))
            .map(|(name, _)| *name)
    }

    fn valid(&self) -> bool {
        let unit = |value: f64| (0.0..=1.0).contains(&value);
        unit(self.x) && unit(self.y) && self.w > 0.0 && self.h > 0.0 && self.x + self.w <= 1.001 && self.y + self.h <= 1.001
    }

    /// `"left"` or `[0.1, 0.0, 0.5, 1.0]` for the TOML file.
    pub fn toml(&self) -> String {
        match self.preset_name() {
            Some(name) => Json::str(name).render(),
            None => format!("[{}, {}, {}, {}]", round(self.x), round(self.y), round(self.w), round(self.h)),
        }
    }

    pub fn describe(&self) -> String {
        match self.preset_name() {
            Some(name) => name.to_string(),
            None => format!("{}x{}% at {},{}%", pct(self.w), pct(self.h), pct(self.x), pct(self.y)),
        }
    }
}

fn round(value: f64) -> String {
    let rounded = (value * 1000.0).round() / 1000.0;
    format!("{rounded:?}")
}

fn pct(value: f64) -> String {
    format!("{}", (value * 100.0).round() as i64)
}

impl Window {
    pub fn kind(&self) -> Kind {
        if self.app == BROWSER {
            Kind::Browser
        } else if !self.tabs.is_empty() {
            Kind::Terminal
        } else {
            Kind::App
        }
    }

    pub fn app(app: &str) -> Window {
        Window { app: app.into(), open: None, frame: None, screen: 1, tabs: Vec::new(), urls: Vec::new() }
    }
}

/// `^[a-z][a-z0-9_-]*$`, shared with command names.
pub fn valid_name(name: &str) -> bool {
    let mut chars = name.chars();
    matches!(chars.next(), Some('a'..='z'))
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_' || c == '-')
}

pub fn validate_name(name: &str) -> Result<()> {
    if valid_name(name) {
        Ok(())
    } else {
        Err(TemplateError(
            "Invalid template name: use a lowercase letter followed by lowercase letters, numbers, '-' or '_'.".into(),
        ))
    }
}

pub fn templates_projects_dir() -> PathBuf {
    templates_dir().join("projects")
}

pub fn manifest_path(name: &str) -> Result<PathBuf> {
    validate_name(name)?;
    Ok(templates_projects_dir().join(format!("{name}.toml")))
}

fn invalid(name: &str, detail: &str) -> TemplateError {
    TemplateError(format!("Invalid template {name}: {detail}"))
}

/// A path from a template: `~` expanded, relative paths joined to `base`.
pub fn resolve_path(raw: &str, base: &Path) -> PathBuf {
    let expanded = expand_user(raw);
    let joined = if expanded.is_absolute() { expanded } else { base.join(expanded) };
    // `components` drops `.` parts, so `open = "."` is the folder itself.
    joined.components().collect()
}

/// `/Users/me/x` -> `~/x`, for files and messages.
pub fn tilde(path: &Path) -> String {
    let home = home();
    match path.strip_prefix(&home) {
        Ok(rest) if rest.as_os_str().is_empty() => "~".into(),
        Ok(rest) => format!("~/{}", rest.display()),
        Err(_) => path.display().to_string(),
    }
}

/// Text for the terminal: control characters (escape sequences from window
/// titles, file names or a shared template) are shown as `\u{..}`, never sent.
pub fn printable(text: &str) -> String {
    text.chars().map(|c| if c.is_control() { c.escape_unicode().to_string() } else { c.to_string() }).collect()
}

pub fn is_url(text: &str) -> bool {
    text.split_once("://").is_some_and(|(scheme, _)| {
        scheme.starts_with(|c: char| c.is_ascii_alphabetic()) && scheme.chars().all(|c| c.is_ascii_alphanumeric() || "+-.".contains(c))
    })
}

fn unknown_keys<'a>(keys: impl Iterator<Item = &'a str>, allowed: &[&str]) -> Vec<String> {
    let mut unknown: Vec<String> = keys.filter(|key| !allowed.contains(key)).map(str::to_string).collect();
    unknown.sort();
    unknown
}

fn from_document(name: &str, document: &DocumentMut) -> Result<Template> {
    if document.contains_key("version") {
        from_v2(name, document)
    } else {
        from_v1(name, document)
    }
}

fn from_v1(name: &str, document: &DocumentMut) -> Result<Template> {
    const FIELDS: [&str; 3] = ["ai", "app", "path"];
    let unknown = unknown_keys(document.iter().map(|(key, _)| key), &FIELDS);
    if !unknown.is_empty() {
        return Err(invalid(name, &format!("unknown fields: {}", unknown.join(", "))));
    }
    let missing: Vec<&str> = FIELDS.iter().copied().filter(|field| !document.contains_key(field)).collect();
    if !missing.is_empty() {
        return Err(invalid(name, &format!("missing fields: {}", missing.join(", "))));
    }
    let path = document["path"].as_str().filter(|path| Path::new(path).is_absolute());
    let Some(path) = path else {
        return Err(invalid(name, "path must be absolute"));
    };
    let app = document["app"].as_str().filter(|app| LEGACY_APPS.contains(app));
    let Some(app) = app else {
        return Err(invalid(name, "app must be zed or obsidian"));
    };
    let Some(ai) = document["ai"].as_bool() else {
        return Err(invalid(name, "ai must be true or false"));
    };
    let mut main = Window::app(if app == "zed" { "Zed" } else { "Obsidian" });
    main.open = Some(path.to_string());
    let mut windows = vec![main];
    if ai {
        windows.push(Window::app("ChatGPT"));
    }
    Ok(Template { name: name.into(), path: path.into(), focus: false, windows, legacy: true })
}

fn string_field(table: &dyn TableLike, key: &str, name: &str, place: &str) -> Result<Option<String>> {
    match table.get_item(key) {
        None => Ok(None),
        Some(item) => match item.as_str() {
            Some(text) if text.chars().any(char::is_control) => {
                Err(invalid(name, &format!("{place}: {key} must not contain control characters")))
            }
            Some(text) if !text.trim().is_empty() => Ok(Some(text.to_string())),
            _ => Err(invalid(name, &format!("{place}: {key} must be a non-empty string"))),
        },
    }
}

/// Tables and inline tables read the same way.
trait TableLike {
    fn get_item(&self, key: &str) -> Option<Item>;
    fn key_names(&self) -> Vec<String>;
}

impl TableLike for Table {
    fn get_item(&self, key: &str) -> Option<Item> {
        self.get(key).cloned()
    }
    fn key_names(&self) -> Vec<String> {
        self.iter().map(|(key, _)| key.to_string()).collect()
    }
}

impl TableLike for toml_edit::InlineTable {
    fn get_item(&self, key: &str) -> Option<Item> {
        self.get(key).map(|value| Item::Value(value.clone()))
    }
    fn key_names(&self) -> Vec<String> {
        self.iter().map(|(key, _)| key.to_string()).collect()
    }
}

fn check_keys(table: &dyn TableLike, allowed: &[&str], name: &str, place: &str) -> Result<()> {
    let names = table.key_names();
    let unknown = unknown_keys(names.iter().map(String::as_str), allowed);
    if unknown.is_empty() {
        Ok(())
    } else {
        Err(invalid(name, &format!("{place}: unknown fields: {}", unknown.join(", "))))
    }
}

fn number(value: &Value) -> Option<f64> {
    value.as_float().or_else(|| value.as_integer().map(|n| n as f64))
}

fn parse_frame(item: &Item, name: &str, place: &str) -> Result<Frame> {
    let bad = || {
        let presets: Vec<&str> = PRESETS.iter().map(|(preset, _)| *preset).collect();
        invalid(
            name,
            &format!("{place}: frame must be one of {} or [x, y, width, height] fractions of the screen (0..1)", presets.join(", ")),
        )
    };
    if let Some(preset) = item.as_str() {
        return Frame::preset(preset).ok_or_else(bad);
    }
    let Some(array) = item.as_array() else {
        return Err(bad());
    };
    let numbers: Vec<f64> = array.iter().filter_map(number).collect();
    let [x, y, w, h] = numbers[..] else {
        return Err(bad());
    };
    if array.len() != 4 {
        return Err(bad());
    }
    let frame = Frame { x, y, w, h };
    if frame.valid() {
        Ok(frame)
    } else {
        Err(bad())
    }
}

fn parse_pane(value: &Value, first: bool, name: &str, place: &str) -> Result<Pane> {
    let Some(table) = value.as_inline_table() else {
        return Err(invalid(name, &format!("{place}: each pane must be {{ dir = ..., run = ..., split = ... }}")));
    };
    check_keys(table, &["dir", "run", "split"], name, place)?;
    let pane = Pane {
        dir: string_field(table, "dir", name, place)?,
        run: string_field(table, "run", name, place)?,
        split: string_field(table, "split", name, place)?,
    };
    if let Some(split) = &pane.split {
        if first {
            return Err(invalid(name, &format!("{place}: the first pane of a tab has no split")));
        }
        if !SPLITS.contains(&split.as_str()) {
            return Err(invalid(name, &format!("{place}: split must be right, down, left or up")));
        }
    }
    Ok(pane)
}

fn parse_window(table: &Table, index: usize, name: &str) -> Result<Window> {
    let place = format!("window {}", index + 1);
    check_keys(table, &["app", "frame", "open", "screen", "tab", "urls"], name, &place)?;
    let Some(app) = string_field(table, "app", name, &place)? else {
        return Err(invalid(name, &format!("{place}: app is missing")));
    };
    let mut window = Window::app(&app);
    window.open = string_field(table, "open", name, &place)?;
    if let Some(frame) = table.get("frame") {
        window.frame = Some(parse_frame(frame, name, &place)?);
    }
    if let Some(screen) = table.get("screen") {
        window.screen = screen
            .as_integer()
            .filter(|screen| (1..=16).contains(screen))
            .ok_or_else(|| invalid(name, &format!("{place}: screen must be a display number from 1")))? as u32;
    }
    if let Some(urls) = table.get("urls") {
        if app != BROWSER {
            return Err(invalid(name, &format!("{place}: urls belong to app = \"browser\"")));
        }
        let array = urls.as_array().ok_or_else(|| invalid(name, &format!("{place}: urls must be a list of links")))?;
        for url in array.iter() {
            match url.as_str() {
                Some(url) if url.chars().any(char::is_control) => {
                    return Err(invalid(name, &format!("{place}: urls must not contain control characters")))
                }
                Some(url) if url.starts_with("https://") || url.starts_with("http://") => window.urls.push(url.to_string()),
                _ => return Err(invalid(name, &format!("{place}: urls must be http:// or https:// links"))),
            }
        }
    }
    if let Some(tabs) = table.get("tab") {
        if !app.eq_ignore_ascii_case(TERMINAL_APP) {
            return Err(invalid(name, &format!("{place}: tabs are only supported for app = \"Ghostty\"")));
        }
        let tabs = tabs.as_array_of_tables().ok_or_else(|| invalid(name, &format!("{place}: use [[window.tab]] for tabs")))?;
        for (number, tab) in tabs.iter().enumerate() {
            let place = format!("{place}, tab {}", number + 1);
            check_keys(tab, &["panes"], name, &place)?;
            let panes = tab
                .get("panes")
                .and_then(Item::as_array)
                .filter(|panes| !panes.is_empty())
                .ok_or_else(|| invalid(name, &format!("{place}: panes must be a non-empty list")))?;
            let panes = panes
                .iter()
                .enumerate()
                .map(|(at, pane)| parse_pane(pane, at == 0, name, &format!("{place}, pane {}", at + 1)))
                .collect::<Result<Vec<Pane>>>()?;
            window.tabs.push(Tab { panes });
        }
    }
    if app == BROWSER && window.open.is_some() {
        return Err(invalid(name, &format!("{place}: a browser window uses urls, not open")));
    }
    Ok(window)
}

fn from_v2(name: &str, document: &DocumentMut) -> Result<Template> {
    let unknown = unknown_keys(document.iter().map(|(key, _)| key), &["focus", "path", "version", "window"]);
    if !unknown.is_empty() {
        return Err(invalid(name, &format!("unknown fields: {}", unknown.join(", "))));
    }
    if document["version"].as_integer() != Some(2) {
        return Err(invalid(name, "version must be 2"));
    }
    let Some(raw) = document.get("path").and_then(Item::as_str) else {
        return Err(invalid(name, "path is missing"));
    };
    if raw.chars().any(char::is_control) {
        return Err(invalid(name, "path must not contain control characters"));
    }
    let path = expand_user(raw);
    if !path.is_absolute() {
        return Err(invalid(name, "path must be absolute or start with ~"));
    }
    let focus = match document.get("focus") {
        None => false,
        Some(item) => item.as_bool().ok_or_else(|| invalid(name, "focus must be true or false"))?,
    };
    let windows = match document.get("window") {
        None => Vec::new(),
        Some(item) => {
            let tables = item.as_array_of_tables().ok_or_else(|| invalid(name, "use [[window]] for windows"))?;
            tables.iter().enumerate().map(|(index, table)| parse_window(table, index, name)).collect::<Result<_>>()?
        }
    };
    Ok(Template { name: name.into(), path, focus, windows, legacy: false })
}

pub fn parse(name: &str, text: &str) -> Result<Template> {
    let document: DocumentMut =
        text.parse().map_err(|error: toml_edit::TomlError| TemplateError(format!("Could not read template {name}: {}", error.to_string().trim_end())))?;
    from_document(name, &document)
}

pub fn load(name: &str) -> Result<Template> {
    read_template(name, &manifest_path(name)?)
}

fn read_template(name: &str, path: &Path) -> Result<Template> {
    let text = fs::read_to_string(path).map_err(|error| TemplateError(format!("Could not read template {name}: {error}")))?;
    parse(name, &text)
}

pub fn exists(name: &str) -> bool {
    valid_name(name) && templates_projects_dir().join(format!("{name}.toml")).is_file()
}

/// All valid saved templates; an invalid one is skipped with a warning so it
/// cannot break `ul <unknown>`, `ul list` or `ul templates` (`load` stays strict).
pub fn discover() -> Result<BTreeMap<String, Template>> {
    discover_in(&templates_projects_dir())
}

fn discover_in(directory: &Path) -> Result<BTreeMap<String, Template>> {
    let mut found = BTreeMap::new();
    let Ok(entries) = fs::read_dir(directory) else {
        return Ok(found);
    };
    let mut names: Vec<String> = entries
        .flatten()
        .filter_map(|entry| entry.file_name().to_str()?.strip_suffix(".toml").map(str::to_string))
        .filter(|stem| !stem.is_empty())
        .collect();
    names.sort();
    for name in names {
        let loaded = validate_name(&name).and_then(|_| read_template(&name, &directory.join(format!("{name}.toml"))));
        match loaded {
            Ok(template) => {
                found.insert(name, template);
            }
            Err(error) => eprintln!("unlaw: skipping template {name}: {error}"),
        }
    }
    Ok(found)
}

fn path_text(raw: &str) -> String {
    let path = Path::new(raw);
    if path.is_absolute() {
        tilde(path)
    } else {
        raw.to_string()
    }
}

/// The version 2 file for a template, with paths under the home folder written as `~/...`.
pub fn render(template: &Template) -> String {
    let quote = |text: &str| Json::str(text).render().replace('\u{7f}', "\\u007f");
    let mut text = format!(
        "# Unlaw template '{}'. Run: ul {}   Edit: ul template edit {}\n# Frames: a preset (left, right, full, top-left, left-third, ...) or [x, y, width, height]\n# in fractions of the screen; screen 1 is the main display.\nversion = 2\npath = {}\nfocus = {}\n",
        template.name,
        template.name,
        template.name,
        quote(&tilde(&template.path)),
        template.focus
    );
    for window in &template.windows {
        text.push_str(&format!("\n[[window]]\napp = {}\n", quote(&window.app)));
        if let Some(open) = &window.open {
            text.push_str(&format!("open = {}\n", quote(&if is_url(open) { open.clone() } else { path_text(open) })));
        }
        if let Some(frame) = &window.frame {
            text.push_str(&format!("frame = {}\n", frame.toml()));
        }
        if window.screen != 1 {
            text.push_str(&format!("screen = {}\n", window.screen));
        }
        if !window.urls.is_empty() {
            text.push_str("urls = [\n");
            for url in &window.urls {
                text.push_str(&format!("  {},\n", quote(url)));
            }
            text.push_str("]\n");
        }
        for tab in &window.tabs {
            text.push_str("\n[[window.tab]]\npanes = [\n");
            for pane in &tab.panes {
                let mut fields = Vec::new();
                if let Some(dir) = &pane.dir {
                    fields.push(format!("dir = {}", quote(&path_text(dir))));
                }
                if let Some(run) = &pane.run {
                    fields.push(format!("run = {}", quote(run)));
                }
                if let Some(split) = &pane.split {
                    fields.push(format!("split = {}", quote(split)));
                }
                text.push_str(&format!("  {{ {} }},\n", fields.join(", ")));
            }
            text.push_str("]\n");
        }
    }
    text
}

/// A starter file for `ul template edit <new name>`.
pub fn starter(name: &str, path: &Path) -> String {
    let folder = tilde(path);
    let template = Template {
        name: name.into(),
        path: path.into(),
        focus: false,
        windows: vec![
            Window { open: Some(path.to_string_lossy().into_owned()), frame: Frame::preset("left"), ..Window::app("Zed") },
            Window {
                frame: Frame::preset("right"),
                tabs: vec![Tab {
                    panes: vec![
                        Pane { dir: Some(folder.clone()), run: Some("claude".into()), split: None },
                        Pane { dir: Some(folder), run: None, split: Some("down".into()) },
                    ],
                }],
                ..Window::app(TERMINAL_APP)
            },
        ],
        legacy: false,
    };
    render(&template)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse_ok(text: &str) -> Template {
        parse("demo", text).unwrap()
    }

    fn error(text: &str) -> String {
        parse("demo", text).unwrap_err().0
    }

    #[test]
    fn names_follow_the_command_pattern() {
        assert!(valid_name("hear-me_2"));
        assert!(!valid_name("Bad Name"));
        assert!(!valid_name("2fast"));
        assert!(!valid_name(""));
        assert!(manifest_path("../x").is_err());
        assert!(!exists("Bad Name"));
    }

    #[test]
    fn version_one_files_are_strict_and_become_windows() {
        let template = parse_ok("path = \"/tmp\"\napp = \"zed\"\nai = true\n");
        assert!(template.legacy);
        assert_eq!(template.windows.iter().map(|w| w.app.as_str()).collect::<Vec<_>>(), ["Zed", "ChatGPT"]);
        assert_eq!(template.windows[0].open.as_deref(), Some("/tmp"));
        assert!(error("path = \"/tmp\"\napp = \"zed\"\nai = true\nextra = 1\n").contains("unknown"));
        assert!(error("path = \"/tmp\"\napp = \"zed\"\n").contains("missing fields: ai"));
        assert!(error("path = \"tmp\"\napp = \"zed\"\nai = true\n").contains("absolute"));
        assert!(error("path = \"/tmp\"\napp = \"code\"\nai = true\n").contains("app"));
        assert!(error("path = \"/tmp\"\napp = \"zed\"\nai = \"yes\"\n").contains("ai"));
    }

    const FULL: &str = r#"
version = 2
path = "~/proj"
focus = true

[[window]]
app = "Zed"
open = "src"
frame = "left"
screen = 2

[[window]]
app = "Ghostty"
frame = [0.5, 0, 0.5, 1]

[[window.tab]]
panes = [
  { dir = "~/proj", run = "claude" },
  { split = "down" },
]

[[window.tab]]
panes = [{ run = "cargo watch -x test" }]

[[window]]
app = "browser"
urls = ["https://example.com", "http://localhost:8000"]
"#;

    #[test]
    fn version_two_reads_every_field() {
        let template = parse_ok(FULL);
        assert_eq!(template.path, home().join("proj"));
        assert!(template.focus && !template.legacy);
        let [zed, ghostty, browser] = &template.windows[..] else { panic!("three windows") };
        assert_eq!((zed.kind(), zed.screen, zed.open.as_deref()), (Kind::App, 2, Some("src")));
        assert_eq!(zed.frame, Frame::preset("left"));
        assert_eq!(ghostty.kind(), Kind::Terminal);
        assert_eq!(ghostty.frame.as_ref().unwrap().preset_name(), Some("right"));
        assert_eq!(ghostty.tabs.len(), 2);
        assert_eq!(ghostty.tabs[0].panes[1], Pane { dir: None, run: None, split: Some("down".into()) });
        assert_eq!(browser.kind(), Kind::Browser);
        assert_eq!(browser.urls.len(), 2);
    }

    #[test]
    fn render_round_trips() {
        let template = parse_ok(FULL);
        let again = parse_ok(&render(&template));
        assert_eq!(again, Template { name: "demo".into(), ..template });
        assert!(render(&again).contains("path = \"~/proj\""));
        assert!(render(&again).contains("frame = \"right\""));
        // DEL is escaped (TOML forbids it raw), so the file reads and names the problem.
        let odd = Template { path: PathBuf::from("/tmp/a\u{7f}b"), ..again.clone() };
        assert!(!render(&odd).contains('\u{7f}'));
        assert!(parse("demo", &render(&odd)).unwrap_err().0.contains("control characters"));
        let starter = parse_ok(&starter("demo", &home().join("x")));
        assert_eq!(starter.windows.len(), 2);
    }

    #[test]
    fn version_two_is_strict() {
        let base = "version = 2\npath = \"/tmp\"\n";
        let with = |rest: &str| error(&format!("{base}{rest}"));
        assert!(error("version = 3\npath = \"/tmp\"\n").contains("version must be 2"));
        assert!(error("version = 2\npath = \"rel\"\n").contains("absolute"));
        assert!(error("version = 2\n").contains("path is missing"));
        assert!(with("color = 1\n").contains("unknown fields: color"));
        assert!(with("focus = \"y\"\n").contains("focus"));
        assert!(with("[[window]]\nopen = \"x\"\n").contains("app is missing"));
        assert!(with("[[window]]\napp = \"Zed\"\nsize = 1\n").contains("window 1: unknown fields: size"));
        assert!(with("[[window]]\napp = \"Zed\"\nframe = \"middle\"\n").contains("frame must be one of"));
        assert!(with("[[window]]\napp = \"Zed\"\nframe = [0.6, 0, 0.6, 1]\n").contains("frame"));
        assert!(with("[[window]]\napp = \"Zed\"\nframe = [0, 0, 1]\n").contains("frame"));
        assert!(with("[[window]]\napp = \"Zed\"\nscreen = 0\n").contains("screen"));
        assert!(with("[[window]]\napp = \"Zed\"\nurls = [\"https://a\"]\n").contains("browser"));
        assert!(with("[[window]]\napp = \"browser\"\nurls = [\"file:///etc\"]\n").contains("http"));
        assert!(with("[[window]]\napp = \"browser\"\nopen = \"x\"\n").contains("urls, not open"));
        assert!(with("[[window]]\napp = \"Zed\"\n[[window.tab]]\npanes = [{}]\n").contains("only supported"));
        assert!(with("[[window]]\napp = \"Ghostty\"\n[[window.tab]]\npanes = []\n").contains("non-empty"));
        assert!(with("[[window]]\napp = \"Ghostty\"\n[[window.tab]]\npanes = [{ split = \"down\" }]\n").contains("first pane"));
        assert!(with("[[window]]\napp = \"Ghostty\"\n[[window.tab]]\npanes = [{}, { split = \"diagonal\" }]\n").contains("split must be"));
        assert!(with("[[window]]\napp = \"Ghostty\"\n[[window.tab]]\npanes = [{ cmd = \"x\" }]\n").contains("unknown fields: cmd"));
        assert!(with("[[window]]\napp = \"Ghostty\"\n[[window.tab]]\npanes = [{ run = \"a\\nb\" }]\n").contains("control characters"));
        assert!(with("[[window]]\napp = \"Ghostty\"\n[[window.tab]]\npanes = [{ run = \"x\\u001b[2K\" }]\n").contains("control characters"));
        assert!(with("[[window]]\napp = \"Z\\u001bed\"\n").contains("control characters"));
        assert!(with("[[window]]\napp = \"browser\"\nurls = [\"https://a/\\u0007\"]\n").contains("control characters"));
        assert!(error("version = 2\npath = \"/tmp/\\u001b\"\n").contains("control characters"));
        assert!(with("[[window]]\napp = \"Ghostty\"\n[[window.tab]]\npanes = [{ dir = \"\" }]\n").contains("non-empty"));
    }

    #[test]
    fn frames_match_presets_and_render_numbers_otherwise() {
        assert_eq!(Frame { x: 0.501, y: 0.0, w: 0.499, h: 1.0 }.preset_name(), Some("right"));
        let odd = Frame { x: 0.1, y: 0.05, w: 0.4, h: 0.9 };
        assert_eq!(odd.toml(), "[0.1, 0.05, 0.4, 0.9]");
        assert_eq!(odd.describe(), "40x90% at 10,5%");
    }

    #[test]
    fn paths_and_urls() {
        assert_eq!(resolve_path("src", Path::new("/p")), PathBuf::from("/p/src"));
        assert_eq!(resolve_path(".", Path::new("/p")), PathBuf::from("/p"));
        assert_eq!(resolve_path("/abs", Path::new("/p")), PathBuf::from("/abs"));
        assert_eq!(resolve_path("~/x", Path::new("/p")), home().join("x"));
        assert_eq!(tilde(&home().join("a/b")), "~/a/b");
        assert!(is_url("https://x") && is_url("obsidian://open?vault=a") && !is_url("/tmp/a") && !is_url("://x"));
        assert!(!is_url("-n://x") && !is_url("+a://x") && !is_url("1a://x"));
        assert_eq!(printable("a\u{1b}[2Kb"), "a\\u{1b}[2Kb");
    }

    #[test]
    fn discovery_skips_invalid_templates_but_load_stays_strict() {
        let directory = std::env::temp_dir().join(format!("unlaw-workspace-discover-{}", std::process::id()));
        let _ = fs::remove_dir_all(&directory);
        fs::create_dir_all(&directory).unwrap();
        fs::write(directory.join("good.toml"), "path = \"/tmp\"\napp = \"zed\"\nai = true\n").unwrap();
        fs::write(directory.join("new.toml"), "version = 2\npath = \"/tmp\"\n").unwrap();
        fs::write(directory.join("broken.toml"), "path = \n").unwrap();
        fs::write(directory.join("wrong.toml"), "path = \"/tmp\"\n").unwrap();
        let found = discover_in(&directory).unwrap();
        assert_eq!(found.keys().collect::<Vec<_>>(), ["good", "new"]);
        fs::remove_dir_all(directory).unwrap();
    }
}
