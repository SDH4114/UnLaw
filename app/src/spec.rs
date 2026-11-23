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
    ("game", include_str!("../defaults/game.toml")),
    ("git", include_str!("../defaults/git.toml")),
    ("gpt", include_str!("../defaults/gpt.toml")),
    ("lm", include_str!("../defaults/lm.toml")),
    ("lofi", include_str!("../defaults/lofi.toml")),
    ("mac", include_str!("../defaults/mac.toml")),
    ("minecraft", include_str!("../defaults/minecraft.toml")),
    ("music", include_str!("../defaults/music.toml")),
    ("netflix", include_str!("../defaults/netflix.toml")),
    ("obsidian", include_str!("../defaults/obsidian.toml")),
    ("py", include_str!("../defaults/py.toml")),
    ("rust", include_str!("../defaults/rust.toml")),
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
    pub default: Value,
    pub placeholder: Option<String>,
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
    pub summary: String,
    pub terminal: bool,
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
    let placeholder = reader.string("placeholder")?;
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
    if let (FieldKind::Choice, Value::Text(text)) = (kind, &default) {
        if !options.contains(text) {
            return Err(format!("{what}.default {text:?} is not one of its options"));
        }
    }
    Ok(Field { id, kind, label, options, default, placeholder })
}

/// An action without a panel has no values: braces must be written `{{`.
fn fixed_args(what: &str, args: &[String]) -> Result<(), String> {
    let ids = args::ids(args).map_err(|error| format!("{what}: {error}"))?;
    match ids.first() {
        Some(id) => Err(format!("{what}: {{{id}}} needs a panel field; outside a panel write {{{{ for a brace")),
        None => Ok(()),
    }
}

/// Parse an `app.toml` for command `name`.
pub fn parse(name: &str, text: &str) -> Result<Spec, String> {
    let document: DocumentMut = text.parse().map_err(|error: toml_edit::TomlError| error.message().to_string())?;
    let mut top = Reader::new("app", document.as_table());
    let title = top.string("title")?.unwrap_or_else(|| name.to_string());
    let icon = top.string("icon")?.unwrap_or_else(|| "command".into());
    if !ICONS.contains(&icon.as_str()) {
        return Err(format!("icon {icon:?} is not one of: {}", ICONS.join(", ")));
    }
    let summary = top.string("summary")?.unwrap_or_default();
    let terminal = top.bool("terminal")?.unwrap_or(false);
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
            reader.done()?;
            Some(Status { args, every: every as u64, text, when, otherwise })
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
        summary,
        terminal,
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
        summary: summary.to_string(),
        terminal: false,
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
    let mut spec = shipped(&record.name)
        .and_then(|text| parse(&record.name, text).ok())
        .unwrap_or_else(|| plain(&record.name, &record.summary));
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

/// The panel's starting values.
pub fn defaults(panel: &Panel) -> BTreeMap<String, Value> {
    panel.fields.iter().map(|field| (field.id.clone(), field.default.clone())).collect()
}

fn action_json(action: &Action) -> Json {
    json!({"id": action.id, "label": action.label, "confirm": action.confirm})
}

/// What the page needs to draw a command (no argument templates: the page sends
/// back field values and a button index, Rust builds argv).
pub fn to_json(spec: &Spec) -> Json {
    json!({
        "name": spec.name,
        "title": spec.title,
        "icon": spec.icon,
        "summary": spec.summary,
        "terminal": spec.terminal,
        "actions": spec.actions.iter().map(action_json).collect::<Vec<_>>(),
        "panel": spec.panel.as_ref().map(|panel| json!({
            "fields": panel.fields.iter().map(|field| json!({
                "id": field.id,
                "type": field.kind.name(),
                "label": field.label,
                "options": field.options,
                "placeholder": field.placeholder,
                "default": match &field.default { Value::Bool(on) => json!(on), Value::Text(text) => json!(text) },
            })).collect::<Vec<_>>(),
            "buttons": panel.buttons.iter().map(action_json).collect::<Vec<_>>(),
        })),
        "status": spec.status.is_some(),
        "open": spec.open.is_some(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
