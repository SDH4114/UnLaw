//! What a command looks like in the app: `commands/<name>/app.toml` next to its
//! entry file, else the description shipped for a default command
//! (`app/defaults/<name>.toml`), else a plain "Run" entry. A command is never
//! run to find this out. The format is documented in
//! `rust/assets/app_integration.md` (`ul skills show app-integration`).

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use serde_json::{json, Value as Json};
use toml_edit::{DocumentMut, Item, Table, Value as Toml};

use crate::args::{self, Value};

pub const FILE: &str = "app.toml";
const MAX_FILE: u64 = 64 * 1024;
const MAX_TEXT: usize = 200;
const MAX_ACTIONS: usize = 32;
const MAX_FIELDS: usize = 24;
const MAX_OPTIONS: usize = 64;
const MAX_ARGS: usize = 64;
pub const MIN_EVERY: u64 = 2;

pub const ICONS: &[&str] = &[
    "command",
    "cup",
    "cup-hot",
    "cpu",
    "board",
    "clock",
    "clipboard",
    "cloud",
    "music",
    "play",
    "camera",
    "record",
    "download",
    "git",
    "terminal",
    "folder",
    "code",
    "chat",
    "spark",
    "game",
    "archive",
    "globe",
    "app",
    "bolt",
    "gear",
];

/// Logos the pages draw themselves (common.js `BRANDS`): sites without an app.
pub const BRANDS: &[&str] =
    &["youtube", "netflix", "telegram", "spotify", "chatgpt", "claude", "steam", "obsidian", "minecraft"];

/// Descriptions of the commands Unlaw ships; a sidecar file overrides one.
pub const DEFAULTS: &[(&str, &str)] = &[
    ("agent", include_str!("../defaults/agent.toml")),
    ("app", include_str!("../defaults/app.toml")),
    ("awake", include_str!("../defaults/awake.toml")),
    ("browser", include_str!("../defaults/browser.toml")),
    ("capture", include_str!("../defaults/capture.toml")),
    ("claude", include_str!("../defaults/claude.toml")),
    ("clip", include_str!("../defaults/clip.toml")),
    ("cpp", include_str!("../defaults/cpp.toml")),
    ("desk", include_str!("../defaults/desk.toml")),
    ("doc", include_str!("../defaults/doc.toml")),
    ("doctor", include_str!("../defaults/doctor.toml")),
    ("game", include_str!("../defaults/game.toml")),
    ("git", include_str!("../defaults/git.toml")),
    ("gpt", include_str!("../defaults/gpt.toml")),
    ("lm", include_str!("../defaults/lm.toml")),
    ("lofi", include_str!("../defaults/lofi.toml")),
    ("mac", include_str!("../defaults/mac.toml")),
    ("minecraft", include_str!("../defaults/minecraft.toml")),
    ("netflix", include_str!("../defaults/netflix.toml")),
    ("obsidian", include_str!("../defaults/obsidian.toml")),
    ("py", include_str!("../defaults/py.toml")),
    ("rust", include_str!("../defaults/rust.toml")),
    ("spotify", include_str!("../defaults/spotify.toml")),
    ("steam", include_str!("../defaults/steam.toml")),
    ("sys", include_str!("../defaults/sys.toml")),
    ("tg", include_str!("../defaults/tg.toml")),
    ("timer", include_str!("../defaults/timer.toml")),
    ("weather", include_str!("../defaults/weather.toml")),
    ("work", include_str!("../defaults/work.toml")),
    ("yt", include_str!("../defaults/yt.toml")),
    ("zed", include_str!("../defaults/zed.toml")),
    ("zip", include_str!("../defaults/zip.toml")),
];

#[derive(Clone, Debug, PartialEq)]
pub enum Origin {
    File(PathBuf),
    Shipped,
    Plain,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Action {
    pub id: String,
    pub label: String,
    pub args: Vec<String>,
    pub confirm: Option<String>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum FieldKind {
    Choice,
    Toggle,
    Text,
    Number,
    Duration,
    Time,
    Date,
}

impl FieldKind {
    fn parse(text: &str) -> Option<Self> {
        Some(match text {
            "choice" => Self::Choice,
            "toggle" => Self::Toggle,
            "text" => Self::Text,
            "number" => Self::Number,
            "duration" => Self::Duration,
            "time" => Self::Time,
            "date" => Self::Date,
            _ => return None,
        })
    }

    pub fn name(self) -> &'static str {
        match self {
            Self::Choice => "choice",
            Self::Toggle => "toggle",
            Self::Text => "text",
            Self::Number => "number",
            Self::Duration => "duration",
            Self::Time => "time",
            Self::Date => "date",
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Field {
    pub id: String,
    pub kind: FieldKind,
    pub label: String,
    pub options: Vec<String>,
    /// A choice may put other words into argv than it shows: `values[i]` for
    /// `options[i]` (`"MP3"` -> `"--audio"`, `""` for nothing). Empty = the option itself.
    pub values: Vec<String>,
    pub default: Value,
    pub placeholder: Option<String>,
    /// The buttons do not run while it is empty.
    pub required: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Panel {
    pub fields: Vec<Field>,
    pub buttons: Vec<Action>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Status {
    pub args: Vec<String>,
    pub every: u64,
    pub text: Option<String>,
    pub when: Option<String>,
    pub otherwise: Option<String>,
    /// Menu bar icon while `when` holds / while it does not (names from ICONS).
    pub icon: Option<String>,
    pub otherwise_icon: Option<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Open {
    pub args: Vec<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Spec {
    pub name: String,
    pub title: String,
    pub icon: String,
    /// `app_icon = "Claude"`: the installed application's own icon instead of `icon`.
    pub app_icon: Option<String>,
    /// `brand = "youtube"`: a logo the app draws (BRANDS), for sites and missing apps.
    pub brand: Option<String>,
    pub summary: String,
    pub terminal: bool,
    /// False for `where = "terminal"`: the command is only for the terminal
    /// (it works in a folder, prints for scripts, or changes Unlaw itself), so
    /// the app neither lists nor pins it.
    pub in_app: bool,
    /// A part of the app's main window that shows this command (`section =
    /// "system"`): opening the command opens that part instead of a panel.
    pub section: Option<String>,
    /// A panel of its own instead of the form built from fields (`view =
    /// "awake"`); only the command it was made for may use it (`VIEWS`).
    pub view: Option<String>,
    /// A left click on the menu bar item runs `stop` while the status says on,
    /// else `start` (KeepingYouAwake, Caffeine); a right click opens the panel.
    pub toggle: Option<Toggle>,
    pub actions: Vec<Action>,
    pub panel: Option<Panel>,
    pub status: Option<Status>,
    pub open: Option<Open>,
    pub origin: Origin,
}

/// One line of `ul commands --json`.
#[derive(Clone, Debug, PartialEq)]
pub struct Record {
    pub name: String,
    pub source: String,
    pub path: Option<PathBuf>,
    pub summary: String,
}

pub fn parse_records(text: &str) -> Result<Vec<Record>, String> {
    let json: Json = serde_json::from_str(text).map_err(|error| format!("ul commands --json: {error}"))?;
    let items = json.as_array().ok_or("ul commands --json: not a list")?;
    Ok(items
        .iter()
        .filter_map(|item| {
            Some(Record {
                name: item.get("name")?.as_str()?.to_string(),
                source: item.get("source").and_then(Json::as_str).unwrap_or("").to_string(),
                path: item.get("path").and_then(Json::as_str).map(PathBuf::from),
                summary: item.get("summary").and_then(Json::as_str).unwrap_or("").to_string(),
            })
        })
        .collect())
}

fn text_ok(what: &str, text: &str) -> Result<String, String> {
    if text.chars().count() > MAX_TEXT {
        return Err(format!("{what} is longer than {MAX_TEXT} characters"));
    }
    if text.chars().any(char::is_control) {
        return Err(format!("{what} contains control characters"));
    }
    Ok(text.to_string())
}

fn id_ok(what: &str, text: &str) -> Result<String, String> {
    if text.is_empty() || text.len() > 32 || !text.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-') {
        return Err(format!("{what} {text:?} must be 1-32 letters, digits, _ or -"));
    }
    Ok(text.to_string())
}

/// Reads a table strictly: every key must be taken, or it is an unknown key.
struct Reader<'a> {
    what: String,
    table: &'a Table,
    taken: Vec<&'static str>,
}

impl<'a> Reader<'a> {
    fn new(what: impl Into<String>, table: &'a Table) -> Self {
        Self { what: what.into(), table, taken: Vec::new() }
    }

    fn value(&mut self, key: &'static str) -> Result<Option<&'a Toml>, String> {
        self.taken.push(key);
        match self.table.get(key) {
            None => Ok(None),
            Some(Item::Value(value)) => Ok(Some(value)),
            Some(_) => Err(format!("{}.{key} must be a value, not a table", self.what)),
        }
    }

    fn string(&mut self, key: &'static str) -> Result<Option<String>, String> {
        match self.value(key)? {
            None => Ok(None),
            Some(Toml::String(text)) => text_ok(&format!("{}.{key}", self.what), text.value()).map(Some),
            Some(_) => Err(format!("{}.{key} must be text", self.what)),
        }
    }

    fn bool(&mut self, key: &'static str) -> Result<Option<bool>, String> {
        match self.value(key)? {
            None => Ok(None),
            Some(Toml::Boolean(on)) => Ok(Some(*on.value())),
            Some(_) => Err(format!("{}.{key} must be true or false", self.what)),
        }
    }

    fn integer(&mut self, key: &'static str) -> Result<Option<i64>, String> {
        match self.value(key)? {
            None => Ok(None),
            Some(Toml::Integer(number)) => Ok(Some(*number.value())),
            Some(_) => Err(format!("{}.{key} must be a whole number", self.what)),
        }
    }

    fn strings(&mut self, key: &'static str, max: usize) -> Result<Option<Vec<String>>, String> {
        let what = format!("{}.{key}", self.what);
        match self.value(key)? {
            None => Ok(None),
            Some(Toml::Array(items)) => {
                if items.len() > max {
                    return Err(format!("{what} has more than {max} items"));
                }
                items
                    .iter()
                    .map(|item| match item {
                        Toml::String(text) => text_ok(&what, text.value()),
                        _ => Err(format!("{what} must be a list of text")),
                    })
                    .collect::<Result<Vec<_>, _>>()
                    .map(Some)
            }
            Some(_) => Err(format!("{what} must be a list of text")),
        }
    }

    fn table(&mut self, key: &'static str) -> Result<Option<&'a Table>, String> {
        self.taken.push(key);
        match self.table.get(key) {
            None => Ok(None),
            Some(Item::Table(table)) => Ok(Some(table)),
            Some(_) => Err(format!("{}.{key} must be a table ([{key}])", self.what)),
        }
    }

    fn tables(&mut self, key: &'static str, max: usize) -> Result<Vec<&'a Table>, String> {
        self.taken.push(key);
        match self.table.get(key) {
            None => Ok(Vec::new()),
            Some(Item::ArrayOfTables(array)) if array.len() <= max => Ok(array.iter().collect()),
            Some(Item::ArrayOfTables(_)) => Err(format!("{}: more than {max} [[{key}]]", self.what)),
            Some(_) => Err(format!("{}.{key} must be written as [[{key}]] tables", self.what)),
        }
    }

    fn done(self) -> Result<(), String> {
        match self.table.iter().find(|(key, _)| !self.taken.contains(key)) {
            Some((key, _)) => Err(format!("unknown key {}.{key}", self.what)),
            None => Ok(()),
        }
    }
}

fn action(what: String, table: &Table, needs_id: bool) -> Result<Action, String> {
    let mut reader = Reader::new(what.clone(), table);
    let id = match reader.string("id")? {
        // A hotkey's `action = "panel" | "open" | "run"` means those, so an action can't be named so.
        Some(id) if needs_id && ["panel", "open", "run"].contains(&id.as_str()) => {
            return Err(format!(
                "{what}.id {id:?} is reserved (panel, open and run mean the panel, the window and a plain run)"
            ))
        }
        Some(id) => id_ok(&format!("{what}.id"), &id)?,
        None if needs_id => return Err(format!("{what} needs an id")),
        None => String::new(),
    };
    let label = reader.string("label")?.ok_or_else(|| format!("{what} needs a label"))?;
    let args = reader.strings("args", MAX_ARGS)?.unwrap_or_default();
    let confirm = reader.string("confirm")?;
    reader.done()?;
    Ok(Action { id, label, args, confirm })
}

fn field(what: String, table: &Table) -> Result<Field, String> {
    let mut reader = Reader::new(what.clone(), table);
    let id = id_ok(&format!("{what}.id"), &reader.string("id")?.ok_or_else(|| format!("{what} needs an id"))?)?;
    let kind_name = reader.string("type")?.unwrap_or_else(|| "text".into());
    let kind = FieldKind::parse(&kind_name).ok_or_else(|| {
        format!("{what}.type {kind_name:?} is not one of choice, toggle, text, number, duration, time, date")
    })?;
    let label = reader.string("label")?.unwrap_or_else(|| id.clone());
    let options = reader.strings("options", MAX_OPTIONS)?.unwrap_or_default();
    let values = reader.strings("values", MAX_OPTIONS)?.unwrap_or_default();
    let placeholder = reader.string("placeholder")?;
    let required = reader.bool("required")?.unwrap_or(false);
    let default = match (kind, reader.value("default")?) {
        (FieldKind::Toggle, None) => Value::Bool(false),
        (FieldKind::Toggle, Some(Toml::Boolean(on))) => Value::Bool(*on.value()),
        (FieldKind::Toggle, Some(_)) => return Err(format!("{what}.default of a toggle must be true or false")),
        (_, None) => Value::Text(if kind == FieldKind::Choice {
            options.first().cloned().unwrap_or_default()
        } else {
            String::new()
        }),
        (_, Some(Toml::String(text))) => Value::Text(text_ok(&format!("{what}.default"), text.value())?),
        (_, Some(Toml::Integer(number))) => Value::Text(number.value().to_string()),
        (_, Some(Toml::Float(number))) => Value::Text(number.value().to_string()),
        (_, Some(_)) => return Err(format!("{what}.default must be text or a number")),
    };
    reader.done()?;
    if kind == FieldKind::Choice && options.is_empty() {
        return Err(format!("{what}: a choice needs options"));
    }
    if kind != FieldKind::Choice && !options.is_empty() {
        return Err(format!("{what}: only a choice has options"));
    }
    if !values.is_empty() && values.len() != options.len() {
        return Err(format!("{what}.values needs one value per option ({} options)", options.len()));
    }
    if let (FieldKind::Choice, Value::Text(text)) = (kind, &default) {
        if !options.contains(text) {
            return Err(format!("{what}.default {text:?} is not one of its options"));
        }
    }
    if required && kind == FieldKind::Toggle {
        return Err(format!("{what}: a toggle cannot be required"));
    }
    Ok(Field { id, kind, label, options, values, default, placeholder, required })
}

/// An action without a panel has no values: braces must be written `{{`.
fn fixed_args(what: &str, args: &[String]) -> Result<(), String> {
    let ids = args::ids(args).map_err(|error| format!("{what}: {error}"))?;
    match ids.first() {
        Some(id) => Err(format!("{what}: {{{id}}} needs a panel field; outside a panel write {{{{ for a brace")),
        None => Ok(()),
    }
}

/// The menu bar item's left click: one action to start, one to stop.
#[derive(Clone, Debug, PartialEq)]
pub struct Toggle {
    pub start: String,
    pub stop: String,
}

/// Panels drawn by the app itself, each for one command (view, command): the
/// page asks for data and actions by name and Rust builds every argv (views.rs).
pub const VIEWS: &[(&str, &str)] = &[("awake", "awake"), ("system", "sys"), ("weather", "weather")];

/// Parts of the main window a command may open (`section = "..."`).
pub const SECTIONS: &[&str] =
    &["templates", "system", "clipboard", "games", "board", "today", "canvas", "studio", "desk", "timer", "edit"];

/// Parse an `app.toml` for command `name`.
/// The palette's inline input for a command: type into the search bar and Enter
/// runs `button` with that text as `field` (the rest keep their defaults).
#[derive(Clone, Debug, PartialEq)]
pub struct Quick {
    pub button: usize,
    pub field: String,
}

/// One palette row of a form's button (`Spec::choices`).
#[derive(Clone, Debug, PartialEq)]
pub struct Choice {
    pub button: usize,
    /// The typed field the palette's text fills, if the button takes one.
    pub field: Option<String>,
    /// Choice fields set by this row: (field id, option label).
    pub fixed: Vec<(String, String)>,
    pub label: String,
}

impl Spec {
    /// The first button that takes one typed thing: its one required text-like
    /// field, else its only text-like field, while every other field it uses can
    /// run on its default. Timer -> "Timer for", Browser -> "Link", Weather -> "City".
    pub fn quick(&self) -> Option<Quick> {
        // A command with its own view takes input there; only the weather view searches with it.
        if self.view.as_deref().is_some_and(|view| view != "weather") {
            return None;
        }
        let panel = self.panel.as_ref()?;
        let typed = |field: &&Field| matches!(field.kind, FieldKind::Text | FieldKind::Duration | FieldKind::Number);
        panel.buttons.iter().enumerate().find_map(|(index, button)| {
            let used = args::ids(&button.args).ok()?;
            let fields: Vec<&Field> = panel.fields.iter().filter(|field| used.contains(&field.id)).collect();
            let texts: Vec<&Field> = fields.iter().copied().filter(typed).collect();
            let required: Vec<&Field> = texts.iter().copied().filter(|field| field.required).collect();
            let chosen = match (required.as_slice(), texts.as_slice()) {
                ([one], _) | ([], [one]) => *one,
                _ => return None,
            };
            let others_ready =
                fields.iter().all(|field| field.id == chosen.id || !field.required || field.default.truthy());
            others_ready.then(|| Quick { button: index, field: chosen.id.clone() })
        })
    }

    /// Every button of the form as palette rows, so the palette can replace the panel:
    /// the typed text goes into the row's one typed field, and a choice the button uses
    /// becomes a row per option (YouTube: Download Video, Download MP3, ...). A button
    /// that needs two typed things, or a field it cannot fill, has no row (the panel has it).
    pub fn choices(&self) -> Vec<Choice> {
        let Some(panel) = self.panel.as_ref() else { return Vec::new() };
        // A view searches with its one input (weather); its days are picked inside the view.
        if self.view.is_some() {
            return self
                .quick()
                .map(|quick| Choice {
                    button: quick.button,
                    field: Some(quick.field),
                    fixed: Vec::new(),
                    label: panel.buttons[quick.button].label.clone(),
                })
                .into_iter()
                .collect();
        }
        // A time or a date can be typed too ("Set alarm 07:30"); values_from checks it.
        let typed = |field: &&Field| {
            matches!(
                field.kind,
                FieldKind::Text | FieldKind::Duration | FieldKind::Number | FieldKind::Time | FieldKind::Date
            )
        };
        let mut rows = Vec::new();
        for (index, button) in panel.buttons.iter().enumerate() {
            let Ok(used) = args::ids(&button.args) else { continue };
            let fields: Vec<&Field> = panel.fields.iter().filter(|field| used.contains(&field.id)).collect();
            let texts: Vec<&Field> = fields.iter().copied().filter(typed).collect();
            let required: Vec<&Field> = texts.iter().copied().filter(|field| field.required).collect();
            let input = match (required.as_slice(), texts.as_slice()) {
                ([one], _) | ([], [one]) => Some(*one),
                ([], []) => None,
                _ => continue,
            };
            // One choice (2-8 options) is spread into rows; anything else runs on its default.
            let spread = fields
                .iter()
                .copied()
                .find(|field| field.kind == FieldKind::Choice && (2..=8).contains(&field.options.len()));
            let ready = fields.iter().all(|field| {
                input.is_some_and(|input| input.id == field.id)
                    || spread.is_some_and(|spread| spread.id == field.id)
                    || !field.required
                    || field.default.truthy()
            });
            if !ready {
                continue;
            }
            let field = input.map(|field| field.id.clone());
            match spread {
                Some(choice) => rows.extend(choice.options.iter().map(|option| Choice {
                    button: index,
                    field: field.clone(),
                    fixed: vec![(choice.id.clone(), option.clone())],
                    label: format!("{} {option}", button.label),
                })),
                None => rows.push(Choice { button: index, field, fixed: Vec::new(), label: button.label.clone() }),
            }
        }
        rows
    }

    /// Everything its panel offers is a palette row (`choices` + actions), so the
    /// panel is not needed: opening the command lists those rows in the palette
    /// (an action that asks first is confirmed there with a second Enter).
    /// Not for a view or a page, or a field no row fills (a toggle, a second
    /// text such as the timer's label).
    pub fn palette_covers(&self) -> bool {
        if self.view.is_some() || self.open.is_some() || self.terminal || !self.in_app {
            return false;
        }
        let Some(panel) = &self.panel else { return self.actions.len() >= 2 };
        let choices = self.choices();
        let every_button = (0..panel.buttons.len()).all(|index| choices.iter().any(|choice| choice.button == index));
        let every_field = panel.fields.iter().all(|field| {
            choices.iter().any(|choice| {
                choice.field.as_deref() == Some(field.id.as_str()) || choice.fixed.iter().any(|(id, _)| id == &field.id)
            })
        });
        every_button && every_field
    }

    /// The one thing to do when a command has no form and a single action that
    /// needs no confirmation (ChatGPT's "Open"): opening it just runs that.
    pub fn only_action(&self) -> Option<&Action> {
        match (&self.panel, self.actions.as_slice()) {
            (None, [action]) if action.confirm.is_none() => Some(action),
            _ => None,
        }
    }
}

pub fn parse(name: &str, text: &str) -> Result<Spec, String> {
    let document: DocumentMut = text.parse().map_err(|error: toml_edit::TomlError| error.message().to_string())?;
    let mut top = Reader::new("app", document.as_table());
    let title = top.string("title")?.unwrap_or_else(|| name.to_string());
    let icon = top.string("icon")?.unwrap_or_else(|| "command".into());
    if !ICONS.contains(&icon.as_str()) {
        return Err(format!("icon {icon:?} is not one of: {}", ICONS.join(", ")));
    }
    let app_icon = top.string("app_icon")?;
    if let Some(app) = app_icon.as_deref().filter(|app| !crate::settings::app_name_ok(app)) {
        return Err(format!("app_icon {app:?} is not an application name"));
    }
    let brand = top.string("brand")?;
    if let Some(brand) = brand.as_deref().filter(|brand| !BRANDS.contains(brand)) {
        return Err(format!("brand {brand:?} is not one of: {}", BRANDS.join(", ")));
    }
    let summary = top.string("summary")?.unwrap_or_default();
    let terminal = top.bool("terminal")?.unwrap_or(false);
    let in_app = match top.string("where")?.as_deref() {
        None | Some("both") => true,
        Some("terminal") => false,
        Some(other) => return Err(format!("where = {other:?} must be \"both\" or \"terminal\"")),
    };
    let section = top.string("section")?;
    if let Some(section) = &section {
        if !SECTIONS.contains(&section.as_str()) {
            return Err(format!("section {section:?} is not one of: {}", SECTIONS.join(", ")));
        }
    }
    let view = top.string("view")?;
    if let Some(view) = &view {
        match VIEWS.iter().find(|(known, _)| known == view) {
            None => {
                let names: Vec<&str> = VIEWS.iter().map(|(known, _)| *known).collect();
                return Err(format!("view {view:?} is not one of: {}", names.join(", ")));
            }
            Some((_, owner)) if *owner != name => return Err(format!("view {view:?} is only for ul {owner}")),
            Some(_) => {}
        }
    }
    let mut actions = Vec::new();
    for (index, table) in top.tables("action", MAX_ACTIONS)?.into_iter().enumerate() {
        let what = format!("action[{}]", index + 1);
        let item = action(what.clone(), table, true)?;
        fixed_args(&what, &item.args)?;
        if actions.iter().any(|other: &Action| other.id == item.id) {
            return Err(format!("{what}: the id {:?} is used twice", item.id));
        }
        actions.push(item);
    }
    let panel = match top.table("panel")? {
        None => None,
        Some(table) => {
            let mut reader = Reader::new("panel", table);
            let mut fields: Vec<Field> = Vec::new();
            for (index, table) in reader.tables("field", MAX_FIELDS)?.into_iter().enumerate() {
                let item = field(format!("panel.field[{}]", index + 1), table)?;
                if fields.iter().any(|other| other.id == item.id) {
                    return Err(format!("panel.field[{}]: the id {:?} is used twice", index + 1, item.id));
                }
                fields.push(item);
            }
            let mut buttons = Vec::new();
            for (index, table) in reader.tables("button", MAX_ACTIONS)?.into_iter().enumerate() {
                let what = format!("panel.button[{}]", index + 1);
                let item = action(what.clone(), table, false)?;
                for id in args::ids(&item.args).map_err(|error| format!("{what}: {error}"))? {
                    if !fields.iter().any(|field| field.id == id) {
                        return Err(format!("{what}: {{{id}}} names no field"));
                    }
                }
                buttons.push(item);
            }
            reader.done()?;
            if buttons.is_empty() {
                return Err("panel needs at least one [[panel.button]]".into());
            }
            Some(Panel { fields, buttons })
        }
    };
    let status = match top.table("status")? {
        None => None,
        Some(table) => {
            let mut reader = Reader::new("status", table);
            let args = reader.strings("args", MAX_ARGS)?.unwrap_or_default();
            fixed_args("status.args", &args)?;
            let every = reader.integer("every")?.unwrap_or(15);
            if every < MIN_EVERY as i64 || every > 86_400 {
                return Err(format!("status.every must be {MIN_EVERY}-86400 seconds"));
            }
            let text = reader.string("text")?;
            if let Some(template) = &text {
                crate::template::render(template, &Json::Null).map_err(|error| format!("status.text: {error}"))?;
            }
            let when = reader.string("when")?;
            let otherwise = reader.string("otherwise")?;
            let icon = reader.string("icon")?;
            let otherwise_icon = reader.string("otherwise_icon")?;
            for (key, value) in [("icon", &icon), ("otherwise_icon", &otherwise_icon)] {
                // `{current.weather_code|weather}`: chosen from the reading (checked like text).
                if let Some(template) = value.as_deref().filter(|name| name.contains('{')) {
                    crate::template::render(template, &Json::Null).map_err(|error| format!("status.{key}: {error}"))?;
                    continue;
                }
                if let Some(name) = value.as_deref().filter(|name| !ICONS.contains(name)) {
                    return Err(format!("status.{key}: unknown icon {name:?}"));
                }
            }
            reader.done()?;
            Some(Status { args, every: every as u64, text, when, otherwise, icon, otherwise_icon })
        }
    };
    let toggle = match top.table("toggle")? {
        None => None,
        Some(table) => {
            let mut reader = Reader::new("toggle", table);
            let start = reader.string("start")?.ok_or("toggle needs start (an action id)")?;
            let stop = reader.string("stop")?.ok_or("toggle needs stop (an action id)")?;
            reader.done()?;
            for id in [&start, &stop] {
                if !actions.iter().any(|action: &Action| &action.id == id) {
                    return Err(format!("toggle: no [[action]] has the id {id:?}"));
                }
            }
            if status.is_none() {
                return Err("toggle needs a [status] to know whether it is on".into());
            }
            Some(Toggle { start, stop })
        }
    };
    let open = match top.table("open")? {
        None => None,
        Some(table) => {
            let mut reader = Reader::new("open", table);
            let args = reader.strings("args", MAX_ARGS)?.unwrap_or_default();
            fixed_args("open.args", &args)?;
            reader.done()?;
            Some(Open { args })
        }
    };
    top.done()?;
    Ok(Spec {
        name: name.to_string(),
        title,
        icon,
        app_icon,
        brand,
        summary,
        terminal,
        in_app,
        section,
        view,
        toggle,
        actions,
        panel,
        status,
        open,
        origin: Origin::Shipped,
    })
}

/// The entry for a command without a description.
pub fn plain(name: &str, summary: &str) -> Spec {
    Spec {
        name: name.to_string(),
        title: name.to_string(),
        icon: "command".into(),
        app_icon: None,
        brand: None,
        summary: summary.to_string(),
        terminal: false,
        in_app: true,
        section: None,
        view: None,
        toggle: None,
        actions: Vec::new(),
        panel: None,
        status: None,
        open: None,
        origin: Origin::Plain,
    }
}

fn shipped(name: &str) -> Option<&'static str> {
    DEFAULTS.iter().find(|(shipped, _)| *shipped == name).map(|(_, text)| *text)
}

/// The sidecar file of a command whose entry file is `entry`.
pub fn sidecar(entry: &Path) -> Option<PathBuf> {
    entry.parent().map(|folder| folder.join(FILE))
}

/// A command's description and, when its own app.toml is broken, why (the
/// command then falls back to the shipped or plain entry).
pub fn for_record(record: &Record) -> (Spec, Option<String>) {
    let mut problem = None;
    if let Some(file) = record.path.as_deref().and_then(sidecar) {
        match read_file(&file) {
            Ok(None) => {}
            Ok(Some(text)) => match parse(&record.name, &text) {
                Ok(mut spec) => {
                    spec.origin = Origin::File(file);
                    if spec.summary.is_empty() {
                        spec.summary = record.summary.clone();
                    }
                    return (spec, None);
                }
                Err(error) => problem = Some(format!("{}: {error}", file.display())),
            },
            Err(error) => problem = Some(format!("{}: {error}", file.display())),
        }
    }
    let mut spec = shipped(&record.name).and_then(|text| parse(&record.name, text).ok()).unwrap_or_else(|| {
        let mut spec = plain(&record.name, &record.summary);
        // Unlaw's own commands (version, venv, config, update...) belong to the
        // terminal unless the app ships a description for one.
        spec.in_app = record.source != "system";
        spec
    });
    if spec.summary.is_empty() {
        spec.summary = record.summary.clone();
    }
    (spec, problem)
}

fn read_file(file: &Path) -> Result<Option<String>, String> {
    match fs::metadata(file) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error.to_string()),
        Ok(meta) if meta.len() > MAX_FILE => Err(format!("larger than {} KB", MAX_FILE / 1024)),
        Ok(_) => fs::read_to_string(file).map(Some).map_err(|error| error.to_string()),
    }
}

/// Check every sidecar of the given commands (`ul-app --check`).
pub fn check_all(records: &[Record]) -> Vec<String> {
    records.iter().filter_map(|record| for_record(record).1).collect()
}

/// What app.toml names that the app cannot do: a command that is not installed
/// or is terminal-only (menu bar items, hotkeys), a hotkey action id the command
/// does not have, a window for a command that has none.
pub fn settings_problems(settings: &crate::settings::Settings, specs: &[Spec]) -> Vec<String> {
    use crate::settings::Target;
    let mut problems: Vec<String> = Vec::new();
    // A menu bar item whose command is not installed (a feature left out; the
    // default items are sys, awake and desk) simply does not show: not a problem.
    let mut named = |name: &str, place: &str| -> Option<Spec> {
        let found = specs.iter().find(|spec| spec.name == name);
        let problem = match found {
            None if place == "menubar" => return None,
            None => format!("app.toml {place}: no command named `{name}`"),
            Some(spec) if !spec.in_app => {
                format!("app.toml {place}: `{name}` is a terminal command; the app does not show it")
            }
            Some(spec) => return Some(spec.clone()),
        };
        if !problems.contains(&problem) {
            problems.push(problem);
        }
        None
    };
    for name in &settings.menubar {
        named(name, "menubar");
    }
    let mut more = Vec::new();
    for binding in &settings.bindings {
        if matches!(binding.target, Target::Template(_)) {
            continue; // a template, not a command (checked when it starts)
        }
        let place = format!("hotkey {}", binding.hotkey);
        let Some(spec) = named(&binding.command, &place) else { continue };
        match &binding.target {
            Target::Action(id) if !spec.actions.iter().any(|action| &action.id == id) => {
                let ids: Vec<&str> = spec.actions.iter().map(|action| action.id.as_str()).collect();
                more.push(format!(
                    "app.toml {place}: `{}` has no action {id:?} (it has: {})",
                    spec.name,
                    ids.join(", ")
                ));
            }
            Target::Open if spec.open.is_none() => {
                more.push(format!("app.toml {place}: `{}` opens no window", spec.name))
            }
            _ => {}
        }
    }
    problems.extend(more);
    problems
}

/// The panel's starting values.
pub fn defaults(panel: &Panel) -> BTreeMap<String, Value> {
    panel.fields.iter().map(|field| (field.id.clone(), field.default.clone())).collect()
}

/// Longest text a panel field may send.
pub const MAX_VALUE: usize = 4000;

/// The values a panel page sent, checked against the panel: unknown fields are
/// ignored, a missing one keeps its default, a toggle takes only true/false.
pub fn values_from(json: &Json, spec: &Spec) -> Result<BTreeMap<String, Value>, String> {
    let panel = spec.panel.as_ref().ok_or("this command has no panel")?;
    let mut values = defaults(panel);
    let given = json.as_object().ok_or("values must be an object")?;
    for field in &panel.fields {
        let Some(value) = given.get(&field.id) else { continue };
        let value = match (field.kind, value) {
            (FieldKind::Toggle, Json::Bool(on)) => Value::Bool(*on),
            (FieldKind::Toggle, _) => return Err(format!("{}: must be on or off", field.label)),
            (_, Json::String(text)) if text.chars().count() > MAX_VALUE => {
                return Err(format!("{}: longer than {MAX_VALUE} characters", field.label))
            }
            (_, Json::String(text)) if text.chars().any(char::is_control) => {
                return Err(format!("{}: contains control characters", field.label))
            }
            (FieldKind::Choice, Json::String(text)) if !field.options.contains(text) => {
                return Err(format!("{}: {text:?} is not one of its options", field.label))
            }
            // A choice is one of its labels, never a bare number that skips the `values` mapping.
            (FieldKind::Choice, Json::String(text)) => Value::Text(text.clone()),
            (FieldKind::Choice, _) => {
                return Err(format!("{}: not a value this field takes (one of its options)", field.label))
            }
            (_, Json::String(text)) => Value::Text(checked(field, text.trim())?),
            (_, Json::Number(number)) => Value::Text(checked(field, &number.to_string())?),
            _ => return Err(format!("{}: not a value this field takes", field.label)),
        };
        values.insert(field.id.clone(), value);
    }
    Ok(values)
}

/// A typed value as its kind allows. Nothing typed may start with `-`: every value
/// is one argv element, and `-x` would be read as an option of the command (a
/// timer label `--all` after `cancel` once cancelled every timer).
fn checked(field: &Field, text: &str) -> Result<String, String> {
    if text.is_empty() {
        return Ok(String::new());
    }
    if text.starts_with('-') {
        return Err(format!("{}: cannot start with -", field.label));
    }
    let digits = |part: &str| !part.is_empty() && part.bytes().all(|byte| byte.is_ascii_digit());
    let ok = match field.kind {
        FieldKind::Number => text.split_once('.').map_or(digits(text), |(whole, part)| digits(whole) && digits(part)),
        // 25m, 1h30m, 90 (the CLI parses the rest); always starts with a digit, so never a word like `cancel`.
        FieldKind::Duration => {
            text.starts_with(|c: char| c.is_ascii_digit())
                && text.bytes().all(|byte| byte.is_ascii_alphanumeric() || byte == b':')
        }
        FieldKind::Time => text.split_once(':').is_some_and(|(hour, minute)| digits(hour) && digits(minute)),
        FieldKind::Date => {
            let parts: Vec<&str> = text.split('-').collect();
            parts.len() == 3 && parts.iter().all(|part| digits(part))
        }
        _ => true,
    };
    if ok {
        Ok(text.to_string())
    } else {
        Err(format!("{}: {text:?} is not a {}", field.label, field.kind.name()))
    }
}

/// The values as argv takes them: a choice with `values` gives the value of the
/// chosen option instead of its label.
pub fn argument_values(panel: &Panel, values: &BTreeMap<String, Value>) -> BTreeMap<String, Value> {
    let mut mapped = values.clone();
    for field in panel.fields.iter().filter(|field| !field.values.is_empty()) {
        if let Some(Value::Text(label)) = values.get(&field.id) {
            if let Some(index) = field.options.iter().position(|option| option == label) {
                mapped.insert(field.id.clone(), Value::Text(field.values[index].clone()));
            }
        }
    }
    mapped
}

/// A required field the button uses but that is empty ("Video link is empty").
/// Only the button's own fields count: Search may run while Download needs a link.
pub fn missing(panel: &Panel, button: &Action, values: &BTreeMap<String, Value>) -> Option<String> {
    let used = args::ids(&button.args).unwrap_or_default();
    panel
        .fields
        .iter()
        .find(|field| field.required && used.contains(&field.id) && !values.get(&field.id).is_some_and(Value::truthy))
        .map(|field| format!("{} is empty", field.label))
}

fn action_json(action: &Action) -> Json {
    // `fields`: which fields the button uses (Enter in a field runs its button), never the args.
    let fields = args::ids(&action.args).unwrap_or_default();
    json!({"id": action.id, "label": action.label, "confirm": action.confirm, "fields": fields})
}

/// What the page needs to draw a command (no argument templates: the page sends
/// back field values and a button index, Rust builds argv).
pub fn to_json(spec: &Spec) -> Json {
    json!({
        "name": spec.name,
        "title": spec.title,
        "icon": spec.icon,
        "app_icon": spec.app_icon,
        "brand": spec.brand,
        "summary": spec.summary,
        "terminal": spec.terminal,
        "section": spec.section,
        "view": spec.view,
        "actions": spec.actions.iter().map(action_json).collect::<Vec<_>>(),
        "panel": spec.panel.as_ref().map(|panel| json!({
            "fields": panel.fields.iter().map(|field| json!({
                "id": field.id,
                "type": field.kind.name(),
                "label": field.label,
                "options": field.options,
                "placeholder": field.placeholder,
                "required": field.required,
                "default": match &field.default { Value::Bool(on) => json!(on), Value::Text(text) => json!(text) },
            })).collect::<Vec<_>>(),
            "buttons": panel.buttons.iter().map(action_json).collect::<Vec<_>>(),
        })),
        "status": spec.status.is_some(),
        "open": spec.open.is_some(),
        // The palette's inline input (`Spec::quick`): which button and field, and how to ask.
        "quick": spec.quick().and_then(|quick| {
            let panel = spec.panel.as_ref()?;
            let field = panel.fields.iter().find(|field| field.id == quick.field)?;
            Some(json!({
                "button": quick.button,
                "field": field.id,
                "label": field.label,
                "placeholder": field.placeholder,
                "required": field.required,
                "run": panel.buttons[quick.button].label,
            }))
        }),
        "choices": spec.choices().iter().map(|choice| {
            let field = choice.field.as_ref().and_then(|id| spec.panel.as_ref()?.fields.iter().find(|field| &field.id == id));
            json!({
                "button": choice.button,
                "label": choice.label,
                "fixed": choice.fixed.iter().map(|(id, option)| (id.clone(), json!(option))).collect::<serde_json::Map<_, _>>(),
                "field": field.map(|field| field.id.clone()),
                "input": field.map(|field| field.label.clone()),
                "placeholder": field.and_then(|field| field.placeholder.clone()),
                "required": field.is_some_and(|field| field.required),
                // What an empty input runs with ("25m"); the palette shows it as the hint.
                "default": field.and_then(|field| match &field.default {
                    Value::Text(text) if !text.is_empty() => Some(text.clone()),
                    _ => None,
                }),
            })
        }).collect::<Vec<_>>(),
        "covers": spec.palette_covers(),
        // No form and one action: opening the command runs it, so the palette shows one row.
        "only": spec.only_action().is_some(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_palette_asks_for_one_typed_thing() {
        let quick = |text: &str| parse("x", text).unwrap().quick();
        // The required text field of the first button that can run with defaults.
        let timer = "[panel]\n[[panel.field]]\nid = \"dur\"\ntype = \"duration\"\nrequired = true\ndefault = \"25m\"\n\
            [[panel.field]]\nid = \"label\"\n[[panel.field]]\nid = \"clock\"\ntype = \"toggle\"\n\
            [[panel.button]]\nlabel = \"Start\"\nargs = [\"{dur}\", \"{label}\", \"{clock?--clock}\"]";
        assert_eq!(quick(timer), Some(Quick { button: 0, field: "dur".into() }));
        // The only text field, optional, next to a choice with a default.
        let weather = "[panel]\n[[panel.field]]\nid = \"city\"\n[[panel.field]]\nid = \"days\"\ntype = \"choice\"\noptions = [\"3\", \"7\"]\n\
            [[panel.button]]\nlabel = \"Show\"\nargs = [\"{city}\", \"--days\", \"{days}\"]";
        assert_eq!(quick(weather), Some(Quick { button: 0, field: "city".into() }));
        // Two optional text fields: nothing to guess.
        let two = "[panel]\n[[panel.field]]\nid = \"a\"\n[[panel.field]]\nid = \"b\"\n[[panel.button]]\nlabel = \"Go\"\nargs = [\"{a}\", \"{b}\"]";
        assert_eq!(quick(two), None);
        // Another required field without a default blocks it.
        let blocked = "[panel]\n[[panel.field]]\nid = \"a\"\nrequired = true\n[[panel.field]]\nid = \"t\"\ntype = \"time\"\nrequired = true\n\
            [[panel.button]]\nlabel = \"Go\"\nargs = [\"{a}\", \"{t}\"]";
        assert_eq!(quick(blocked), None);
        assert_eq!(quick("title = \"x\""), None);
    }

    #[test]
    fn every_button_becomes_palette_rows() {
        let labels = |name: &str| {
            let spec = parse(name, shipped(name).unwrap()).unwrap();
            spec.choices().into_iter().map(|choice| (choice.label, choice.field)).collect::<Vec<_>>()
        };
        let url = Some("url".to_string());
        assert_eq!(
            labels("yt"),
            vec![
                ("Search".to_string(), Some("query".into())),
                ("Open YouTube".into(), None),
                ("Download Video".into(), url.clone()),
                ("Download MP3".into(), url.clone()),
                ("Download Podcast".into(), url.clone()),
                ("Download Subtitles".into(), url.clone()),
                ("Download All".into(), url),
            ]
        );
        let timer = labels("timer");
        assert_eq!(timer[0], ("Start timer".into(), Some("dur".into())));
        assert_eq!(timer[1], ("Set alarm".into(), Some("at".into())));
        assert_eq!(labels("browser"), vec![("Open".to_string(), Some("url".to_string()))]);
        // A view keeps its one search row (the days are picked in the view).
        assert_eq!(labels("weather"), vec![("Show".to_string(), Some("city".to_string()))]);
        let spec = parse("yt", shipped("yt").unwrap()).unwrap();
        assert_eq!(spec.choices()[3].fixed, vec![("what".to_string(), "MP3".to_string())]);
    }

    #[test]
    fn the_palette_replaces_panels_it_fully_covers() {
        let covers = |name: &str| parse(name, shipped(name).unwrap()).unwrap().palette_covers();
        // Every button a row, every field filled by the text or a spread choice.
        assert!(covers("yt") && covers("browser") && covers("tg") && covers("capture") && covers("doctor"));
        // The timer's label and Clock toggle have no row; a view draws its own panel.
        assert!(!covers("timer"));
        assert!(!covers("awake") && !covers("weather") && !covers("sys"));
    }

    #[test]
    fn a_choice_can_put_other_words_into_argv() {
        let text = "[panel]\n[[panel.field]]\nid = \"what\"\ntype = \"choice\"\noptions = [\"Video\", \"MP3\"]\nvalues = [\"\", \"--audio\"]\n\
            [[panel.button]]\nlabel = \"Go\"\nargs = [\"download\", \"{what}\"]";
        let spec = parse("yt", text).unwrap();
        let panel = spec.panel.as_ref().unwrap();
        let values = values_from(&serde_json::json!({"what": "MP3"}), &spec).unwrap();
        let argv = args::expand(&panel.buttons[0].args, &argument_values(panel, &values)).unwrap();
        assert_eq!(argv, ["download", "--audio"]);
        let values = values_from(&serde_json::json!({"what": "Video"}), &spec).unwrap();
        assert_eq!(args::expand(&panel.buttons[0].args, &argument_values(panel, &values)).unwrap(), ["download"]);
        // The page still sends the label; anything else is refused.
        assert!(values_from(&serde_json::json!({"what": "--audio"}), &spec).is_err());
        let uneven = text.replace("values = [\"\", \"--audio\"]", "values = [\"\"]");
        assert!(parse("yt", &uneven).unwrap_err().contains("one value per option"));
    }

    #[test]
    fn a_single_plain_action_runs_at_once() {
        let one =
            parse("gpt", "title = \"ChatGPT\"\n[[action]]\nid = \"launch\"\nlabel = \"Open\"\nargs = []\n").unwrap();
        assert_eq!(one.only_action().map(|action| action.id.as_str()), Some("launch"));
        let asks = parse("x", "[[action]]\nid = \"a\"\nlabel = \"A\"\nargs = []\nconfirm = \"Sure?\"\n").unwrap();
        assert!(asks.only_action().is_none(), "a confirmation needs the panel");
        assert!(parse("awake", AWAKE).unwrap().only_action().is_none(), "a form needs the panel");
        let two = parse(
            "x",
            "[[action]]\nid = \"a\"\nlabel = \"A\"\nargs = []\n[[action]]\nid = \"b\"\nlabel = \"B\"\nargs = []\n",
        )
        .unwrap();
        assert!(two.only_action().is_none());
    }

    const AWAKE: &str = r#"
title = "Awake"
icon = "cup"
[[action]]
id = "2h"
label = "Keep awake 2 h"
args = ["2h"]
[panel]
[[panel.field]]
id = "dur"
type = "choice"
label = "For"
options = ["30m", "1h"]
default = "1h"
[[panel.field]]
id = "lid"
type = "toggle"
[[panel.button]]
label = "Start"
args = ["{dur}", "{lid?--lid}"]
[status]
args = ["status", "--json"]
every = 10
text = "{remaining_seconds|clock}"
when = "active"
otherwise = "off"
"#;

    #[test]
    fn a_full_description_parses() {
        let spec = parse("awake", AWAKE).unwrap();
        assert_eq!(spec.title, "Awake");
        assert_eq!(spec.actions[0].args, vec!["2h"]);
        let panel = spec.panel.unwrap();
        assert_eq!(panel.fields[1].default, Value::Bool(false));
        assert_eq!(panel.fields[1].label, "lid");
        assert_eq!(spec.status.unwrap().every, 10);
    }

    #[test]
    fn mistakes_are_named() {
        let cases = [
            ("titel = \"x\"", "unknown key app.titel"),
            ("icon = \"rocket\"", "is not one of"),
            ("[[action]]\nlabel = \"x\"", "needs an id"),
            ("[[action]]\nid = \"a b\"\nlabel = \"x\"", "letters, digits"),
            ("[[action]]\nid = \"a\"\nlabel = \"x\"\nargs = [\"{v}\"]", "needs a panel field"),
            ("[[action]]\nid = \"a\"\nlabel = \"x\"\n[[action]]\nid = \"a\"\nlabel = \"y\"", "used twice"),
            ("[panel]\n[[panel.field]]\nid = \"a\"", "at least one"),
            ("[panel]\n[[panel.field]]\nid = \"a\"\n[[panel.button]]\nlabel = \"Go\"\nargs = [\"{b}\"]", "names no field"),
            ("[panel]\n[[panel.field]]\nid = \"a\"\ntype = \"choice\"\n[[panel.button]]\nlabel = \"Go\"", "needs options"),
            ("[panel]\n[[panel.field]]\nid = \"a\"\ntype = \"choice\"\noptions = [\"x\"]\ndefault = \"y\"\n[[panel.button]]\nlabel = \"Go\"", "not one of its options"),
            ("[panel]\n[[panel.field]]\nid = \"a\"\ntype = \"slider\"\n[[panel.button]]\nlabel = \"Go\"", "is not one of choice"),
            ("[status]\nevery = 1", "status.every"),
            ("[status]\ntext = \"{a|nope}\"", "unknown filter"),
            ("title = \"a\\u0007\"", "control characters"),
            ("panel = 3", "must be a table"),
            ("action = 3", "[[action]]"),
            ("title = ", ""),
        ];
        for (text, message) in cases {
            let error = parse("x", text).unwrap_err();
            assert!(error.contains(message), "{text:?} gave {error:?}");
        }
    }

    #[test]
    fn caps_hold() {
        let many: String = (0..33).map(|i| format!("[[action]]\nid = \"a{i}\"\nlabel = \"x\"\n")).collect();
        assert!(parse("x", &many).unwrap_err().contains("more than 32"));
        let long = format!("title = \"{}\"", "x".repeat(201));
        assert!(parse("x", &long).unwrap_err().contains("longer than"));
    }

    #[test]
    fn every_shipped_description_parses() {
        for (name, text) in DEFAULTS {
            let spec = parse(name, text).unwrap_or_else(|error| panic!("defaults/{name}.toml: {error}"));
            assert!(!spec.title.is_empty());
        }
    }

    #[test]
    fn terminal_commands_stay_out_of_the_app() {
        let record = |name: &str, source: &str| Record {
            name: name.into(),
            source: source.into(),
            path: None,
            summary: String::new(),
        };
        // Unlaw's own commands are terminal-only unless the app describes one.
        assert!(!for_record(&record("version", "system")).0.in_app);
        assert!(!for_record(&record("venv", "system")).0.in_app);
        assert!(for_record(&record("doctor", "system")).0.in_app);
        // A user command without app.toml is in the app; shipped ones say where.
        assert!(for_record(&record("hello", "config")).0.in_app);
        for (name, in_app) in
            [("git", false), ("py", false), ("zip", false), ("lm", false), ("awake", true), ("agent", true)]
        {
            assert_eq!(for_record(&record(name, "config")).0.in_app, in_app, "{name}");
        }
        assert!(!parse("x", "where = \"terminal\"").unwrap().in_app);
        assert_eq!(parse("x", "section = \"system\"").unwrap().section.as_deref(), Some("system"));
        assert!(parse("x", "section = \"kitchen\"").unwrap_err().contains("not one of"));
        assert!(parse("x", "[[action]]\nid = \"open\"\nlabel = \"Open\"\nargs = []\n")
            .unwrap_err()
            .contains("reserved"));
        assert!(parse("x", "where = \"both\"").unwrap().in_app);
        assert!(parse("x", "where = \"app\"").unwrap_err().contains("both"));
        let specs = vec![for_record(&record("git", "config")).0, for_record(&record("awake", "config")).0];
        let (settings, warnings) = crate::settings::parse(
            "[menubar]\nitems = [\"awake\", \"git\", \"nope\"]\n\n[[hotkey]]\nkeys = \"ctrl+alt+g\"\ncommand = \"git\"\n\n\
             [[hotkey]]\nkeys = \"ctrl+alt+a\"\ncommand = \"awake\"\naction = \"3h\"\n\n[[hotkey]]\nkeys = \"ctrl+alt+b\"\ncommand = \"awake\"\naction = \"2h\"\n",
        );
        assert!(warnings.is_empty(), "{warnings:?}");
        let problems = settings_problems(&settings, &specs);
        assert_eq!(problems.len(), 3, "{problems:?} (a missing `nope` in the menu bar is fine)");
        assert!(problems[0].contains("menubar: `git` is a terminal command"));
        assert!(problems[1].contains("hotkey ⌃⌥G: `git` is a terminal command"));
        assert!(problems[2].contains("no action \"3h\" (it has: 1h, 2h, on, off)"), "2h is fine");
        let (hotkey, _) = crate::settings::parse("[[hotkey]]\nkeys = \"ctrl+alt+n\"\ncommand = \"nope\"\n");
        assert!(settings_problems(&hotkey, &specs).iter().any(|problem| problem.contains("no command named `nope`")));
    }

    #[test]
    fn a_view_belongs_to_its_command_and_a_toggle_names_actions() {
        assert_eq!(parse("awake", "view = \"awake\"").unwrap().view.as_deref(), Some("awake"));
        assert!(parse("other", "view = \"awake\"").unwrap_err().contains("only for ul awake"));
        assert!(parse("sys", "view = \"kitchen\"").unwrap_err().contains("not one of"));
        let actions = "[[action]]\nid = \"on\"\nlabel = \"On\"\nargs = [\"on\"]\n[[action]]\nid = \"off\"\nlabel = \"Off\"\nargs = [\"off\"]\n";
        let status = "[status]\nargs = [\"status\"]\n";
        let spec = parse("x", &format!("{actions}{status}[toggle]\nstart = \"on\"\nstop = \"off\"\n")).unwrap();
        assert_eq!(spec.toggle, Some(Toggle { start: "on".into(), stop: "off".into() }));
        assert!(parse("x", &format!("{actions}{status}[toggle]\nstart = \"on\"\nstop = \"nope\"\n"))
            .unwrap_err()
            .contains("nope"));
        assert!(parse("x", &format!("{actions}[toggle]\nstart = \"on\"\nstop = \"off\"\n"))
            .unwrap_err()
            .contains("[status]"));
    }
    #[test]
    fn sidecar_wins_and_a_broken_one_falls_back() {
        let folder = std::env::temp_dir().join(format!("unlaw-app-spec-{}", std::process::id()));
        let commands = folder.join("awake");
        fs::create_dir_all(&commands).unwrap();
        let record = Record {
            name: "awake".into(),
            source: "config".into(),
            path: Some(commands.join("main.py")),
            summary: "Keep awake".into(),
        };
        let (spec, problem) = for_record(&record);
        assert_eq!((spec.origin, problem), (Origin::Shipped, None));
        fs::write(commands.join(FILE), "title = \"Mine\"\n").unwrap();
        let (spec, _) = for_record(&record);
        assert_eq!(spec.title, "Mine");
        assert_eq!(spec.summary, "Keep awake");
        assert!(matches!(spec.origin, Origin::File(_)));
        fs::write(commands.join(FILE), "nonsense = [").unwrap();
        let (spec, problem) = for_record(&record);
        assert_eq!(spec.origin, Origin::Shipped);
        assert!(problem.unwrap().contains("app.toml"));
        let user = Record { name: "hello".into(), source: "config".into(), path: None, summary: "Hi".into() };
        let (spec, problem) = for_record(&user);
        assert_eq!((spec.origin, spec.summary.as_str(), problem), (Origin::Plain, "Hi", None));
        fs::remove_dir_all(&folder).unwrap();
    }

    #[test]
    fn panel_values_are_checked() {
        let spec = parse("awake", AWAKE).unwrap();
        let values = values_from(&serde_json::json!({"dur": "30m", "lid": true, "other": "x"}), &spec).unwrap();
        let panel = spec.panel.as_ref().unwrap();
        assert_eq!(args::expand(&panel.buttons[0].args, &values).unwrap(), vec!["30m", "--lid"]);
        let defaults = values_from(&serde_json::json!({}), &spec).unwrap();
        assert_eq!(args::expand(&panel.buttons[0].args, &defaults).unwrap(), vec!["1h"]);
        for (bad, message) in [
            (serde_json::json!({"dur": "99h"}), "not one of its options"),
            (serde_json::json!({"lid": "yes"}), "on or off"),
            (serde_json::json!({"dur": "a\nb"}), "control"),
            (serde_json::json!({"dur": ["1h"]}), "not a value"),
            (serde_json::json!("x"), "an object"),
        ] {
            assert!(values_from(&bad, &spec).unwrap_err().contains(message), "{bad}");
        }
        let long = serde_json::json!({"dur": "x".repeat(MAX_VALUE + 1)});
        assert!(values_from(&long, &spec).unwrap_err().contains("longer"));
        assert!(values_from(&serde_json::json!({}), &plain("x", "")).is_err());
        let shipped = |name: &str| parse(name, shipped(name).unwrap()).unwrap();
        // Typed values never become options and keep their kind's shape (the timer once ran
        // `ul timer cancel --all` from Start with dur = "cancel", label = "--all").
        let timer = shipped("timer");
        for bad in [
            serde_json::json!({"dur": "cancel"}),
            serde_json::json!({"label": "--all"}),
            serde_json::json!({"dur": "-5m"}),
            serde_json::json!({"at": "noon"}),
            serde_json::json!({"at": "-1:00"}),
        ] {
            assert!(values_from(&bad, &timer).is_err(), "{bad}");
        }
        assert!(
            values_from(&serde_json::json!({"dur": "1h30m", "at": "07:30", "label": "tea - green"}), &timer).is_ok()
        );
        assert!(
            values_from(&serde_json::json!({"days": 99}), &shipped("weather")).is_err(),
            "a choice takes a label only"
        );
        let yt = shipped("yt");
        let panel = yt.panel.as_ref().unwrap();
        let empty = values_from(&serde_json::json!({"url": "  ", "query": "lofi"}), &yt).unwrap();
        let download = panel.buttons.iter().find(|button| button.label == "Download").unwrap();
        let search = panel.buttons.iter().find(|button| button.label == "Search").unwrap();
        assert_eq!(missing(panel, download, &empty).as_deref(), Some("Video link is empty"));
        assert_eq!(missing(panel, search, &empty), None, "Search does not need the link");
        let link = values_from(&serde_json::json!({"url": "https://youtu.be/x"}), &yt).unwrap();
        assert_eq!(missing(panel, download, &link), None);
        assert!(parse("x", "[panel]\n[[panel.field]]\nid = \"on\"\ntype = \"toggle\"\nrequired = true\n[[panel.button]]\nlabel = \"Go\"\nargs = []\n").is_err());
    }

    #[test]
    fn records_parse() {
        let records = parse_records(r#"[{"name":"awake","source":"config","path":"/x/main.py","summary":"s"},{"name":"app","source":"builtin","path":null},{"bad":1}]"#).unwrap();
        assert_eq!(records.len(), 2);
        assert_eq!(records[1].path, None);
        assert!(parse_records("{").is_err());
    }

    #[test]
    fn page_json_has_no_argument_templates() {
        let json = to_json(&parse("awake", AWAKE).unwrap()).to_string();
        assert!(!json.contains("{dur}"));
        assert!(json.contains("\"type\":\"choice\""));
    }

    #[test]
    fn the_app_toml_of_ul_create_command_is_valid() {
        let text = include_str!("../../rust/assets/command_app.toml").replace("{{command_name}}", "hello");
        let spec = parse("hello", &text).unwrap();
        assert_eq!(spec.title, "hello");
        // The commented examples must also be valid once uncommented.
        let setting =
            |line: &str| line.starts_with('[') || line.split_once(" = ").is_some_and(|(key, _)| !key.contains(' '));
        let open = text
            .lines()
            .map(|line| line.strip_prefix("# ").filter(|rest| setting(rest)).unwrap_or(line))
            .collect::<Vec<_>>()
            .join("\n");
        assert!(parse("hello", &open).is_ok(), "{open}");
        assert!(open.contains("[[panel.button]]") && !open.contains("# [[action]]"), "the examples were uncommented");
    }
}
