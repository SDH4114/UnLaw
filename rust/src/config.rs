//! `config.toml`: defaults, validation and comment-preserving atomic writes.
//!
//! The defaults come from `src/unlawful/config.py` at build time. Writes edit
//! the user's document in place with `toml_edit`, so comments, ordering and
//! unknown keys survive `ul config set`.

use std::env;
use std::fmt;
use std::fs;
use std::path::PathBuf;
use std::sync::OnceLock;

use toml_edit::{DocumentMut, Item, Table, TableLike};

use crate::assets;
use crate::util::{atomic_write, expand_user, python_float, Json};

#[derive(Debug)]
pub struct ConfigError(pub String);

impl fmt::Display for ConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl From<std::io::Error> for ConfigError {
    fn from(error: std::io::Error) -> Self {
        ConfigError(error.to_string())
    }
}

pub type Result<T> = std::result::Result<T, ConfigError>;

pub fn config_dir() -> PathBuf {
    let base = match env::var("XDG_CONFIG_HOME") {
        Ok(xdg) if !xdg.is_empty() => expand_user(&xdg),
        _ => crate::util::home().join(".config"),
    };
    base.join("unlaw")
}

pub fn config_file() -> PathBuf {
    config_dir().join("config.toml")
}

pub fn commands_dir() -> PathBuf {
    config_dir().join("commands")
}

pub fn templates_dir() -> PathBuf {
    config_dir().join("templates")
}

/// A plain, ordered view of TOML data used for merging, validation and output.
#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
    Array(Vec<Value>),
    Table(Vec<(String, Value)>),
    Other(String),
}

impl Value {
    fn from_value(value: &toml_edit::Value) -> Value {
        use toml_edit::Value as V;
        match value {
            V::String(text) => Value::Str(text.value().clone()),
            V::Integer(number) => Value::Int(*number.value()),
            V::Float(number) => Value::Float(*number.value()),
            V::Boolean(flag) => Value::Bool(*flag.value()),
            V::Datetime(stamp) => Value::Other(stamp.value().to_string()),
            V::Array(items) => Value::Array(items.iter().map(Value::from_value).collect()),
            V::InlineTable(table) => Value::from_table(table),
        }
    }

    fn from_table(table: &dyn TableLike) -> Value {
        Value::Table(
            table
                .iter()
                .filter_map(|(key, item)| Value::from_item(item).map(|value| (key.to_string(), value)))
                .collect(),
        )
    }

    fn from_item(item: &Item) -> Option<Value> {
        match item {
            Item::None => None,
            Item::Value(value) => Some(Value::from_value(value)),
            Item::Table(table) => Some(Value::from_table(table)),
            Item::ArrayOfTables(tables) => Some(Value::Array(tables.iter().map(|t| Value::from_table(t)).collect())),
        }
    }

    pub fn get(&self, key: &str) -> Option<&Value> {
        match self {
            Value::Table(entries) => entries.iter().find(|(name, _)| name == key).map(|(_, value)| value),
            _ => None,
        }
    }

    pub fn lookup(&self, dotted: &str) -> Option<&Value> {
        dotted.split('.').try_fold(self, |value, part| if part.is_empty() { None } else { value.get(part) })
    }

    /// `ul config get` output: scalars as text, tables and arrays as JSON.
    pub fn display(&self) -> String {
        match self {
            Value::Bool(flag) => flag.to_string(),
            Value::Int(number) => number.to_string(),
            Value::Float(number) => python_float(*number),
            Value::Str(text) | Value::Other(text) => text.clone(),
            Value::Array(_) | Value::Table(_) => self.to_json().render(),
        }
    }

    pub fn to_json(&self) -> Json {
        match self {
            Value::Bool(flag) => Json::Bool(*flag),
            Value::Int(number) => Json::Int(*number),
            Value::Float(number) => Json::Float(*number),
            Value::Str(text) | Value::Other(text) => Json::str(text.clone()),
            Value::Array(items) => Json::Array(items.iter().map(Value::to_json).collect()),
            Value::Table(entries) => {
                Json::Object(entries.iter().map(|(key, value)| (key.clone(), value.to_json())).collect())
            }
        }
    }

    fn merge(&mut self, overlay: &Value) {
        match (self, overlay) {
            (Value::Table(base), Value::Table(entries)) => {
                for (key, value) in entries {
                    match base.iter_mut().find(|(name, _)| name == key) {
                        Some((_, existing @ Value::Table(_))) if matches!(value, Value::Table(_)) => existing.merge(value),
                        Some((_, existing)) => *existing = value.clone(),
                        None => base.push((key.clone(), value.clone())),
                    }
                }
            }
            (base, value) => *base = value.clone(),
        }
    }
}

fn defaults_document() -> &'static DocumentMut {
    static DEFAULTS: OnceLock<DocumentMut> = OnceLock::new();
    DEFAULTS.get_or_init(|| assets::DEFAULT_CONFIG_TOML.parse().expect("embedded default config is valid TOML"))
}

pub fn defaults() -> Value {
    Value::from_table(defaults_document().as_table())
}

/// The validated, defaults-merged configuration.
#[derive(Clone)]
pub struct Config {
    pub data: Value,
}

impl Config {
    pub fn get(&self, dotted: &str) -> Option<&Value> {
        self.data.lookup(dotted)
    }

    pub fn string(&self, dotted: &str) -> String {
        match self.get(dotted) {
            Some(Value::Str(text)) => text.clone(),
            _ => String::new(),
        }
    }

    pub fn int(&self, dotted: &str) -> i64 {
        match self.get(dotted) {
            Some(Value::Int(number)) => *number,
            _ => 0,
        }
    }

    pub fn flag(&self, dotted: &str) -> bool {
        matches!(self.get(dotted), Some(Value::Bool(true)))
    }

    pub fn aliases(&self) -> Vec<(String, Vec<String>)> {
        let Some(Value::Table(entries)) = self.get("aliases") else {
            return Vec::new();
        };
        entries
            .iter()
            .map(|(name, tokens)| {
                let tokens = match tokens {
                    Value::Array(items) => items
                        .iter()
                        .filter_map(|item| if let Value::Str(text) = item { Some(text.clone()) } else { None })
                        .collect(),
                    _ => Vec::new(),
                };
                (name.clone(), tokens)
            })
            .collect()
    }

    pub fn alias(&self, name: &str) -> Option<Vec<String>> {
        self.aliases().into_iter().find(|(alias, _)| alias == name).map(|(_, tokens)| tokens)
    }

    pub fn storage_root(&self) -> PathBuf {
        storage_root_from(&self.string("storage.root"))
    }
}

pub fn storage_root_from(configured: &str) -> PathBuf {
    let path = expand_user(configured);
    if path.is_absolute() {
        path
    } else {
        config_dir().join(path)
    }
}

pub fn read_document() -> Result<DocumentMut> {
    let path = config_file();
    let text = fs::read_to_string(&path).map_err(|error| ConfigError(format!("Could not read {}: {error}", path.display())))?;
    text.parse::<DocumentMut>()
        .map_err(|error| ConfigError(format!("Could not read {}: {}", path.display(), error.to_string().trim_end())))
}

fn merged(document: &DocumentMut) -> Value {
    let mut data = defaults();
    data.merge(&Value::from_table(document.as_table()));
    data
}

fn checked(document: &DocumentMut) -> Result<Config> {
    let data = merged(document);
    let errors = validate(&data);
    if errors.is_empty() {
        Ok(Config { data })
    } else {
        Err(ConfigError(errors.join("; ")))
    }
}

pub fn load() -> Result<Config> {
    checked(&read_document()?)
}

enum Kind {
    Bool,
    Int,
    Str,
    Number,
}

const CHECKS: &[(&str, Kind, &[&str])] = &[
    ("core.color", Kind::Bool, &[]),
    ("core.verbose", Kind::Bool, &[]),
    ("core.command_timeout", Kind::Int, &[]),
    ("core.show_timing", Kind::Bool, &[]),
    ("core.python", Kind::Str, &[]),
    ("core.editor", Kind::Str, &[]),
    ("storage.root", Kind::Str, &[]),
    ("git.auto_push", Kind::Bool, &[]),
    ("projects.python.environment", Kind::Str, &["auto", "none", "uv", "venv"]),
    ("projects.python.initialize_git", Kind::Bool, &[]),
    ("projects.rust.initialize_git", Kind::Bool, &[]),
    ("projects.cpp.standard", Kind::Int, &["11", "14", "17", "20", "23", "26"]),
    ("projects.cpp.initialize_git", Kind::Bool, &[]),
    ("mac.executable", Kind::Str, &[]),
    ("mac.timeout", Kind::Int, &[]),
    ("todo.vault_path", Kind::Str, &[]),
    ("todo.file", Kind::Str, &[]),
    ("todo.completed_column", Kind::Str, &[]),
    ("capture.camera_device", Kind::Str, &[]),
    ("capture.audio_device", Kind::Str, &[]),
    ("capture.screen_audio", Kind::Bool, &[]),
    ("capture.show_clicks", Kind::Bool, &[]),
    ("games.difficulty", Kind::Str, &["easy", "hard", "normal"]),
    ("zip.format", Kind::Str, &["7z", "rar", "tar.gz", "tar.xz", "tar.zst", "zip"]),
    ("zip.keep_junk", Kind::Bool, &[]),
    ("apps.spotify", Kind::Str, &[]),
    ("apps.editor", Kind::Str, &[]),
    ("apps.spotify_autoplay_delay", Kind::Number, &[]),
    ("apps.browser_url", Kind::Str, &[]),
    ("apps.lofi_url", Kind::Str, &[]),
    ("apps.youtube_url", Kind::Str, &[]),
    ("telegram.chat_id", Kind::Str, &[]),
    ("telegram.api_base", Kind::Str, &[]),
    ("telegram.keychain_service", Kind::Str, &[]),
    ("lm.model", Kind::Str, &[]),
    ("lm.embedding_model", Kind::Str, &[]),
    ("lm.stt_model", Kind::Str, &[]),
    ("lm.tts_model", Kind::Str, &[]),
    ("lm.image_model", Kind::Str, &[]),
    ("lm.video_model", Kind::Str, &[]),
    ("lm.music_model", Kind::Str, &[]),
    ("lm.port", Kind::Int, &[]),
    ("lm.idle_minutes", Kind::Int, &[]),
    ("lm.system_prompt", Kind::Str, &[]),
    ("lm.temperature", Kind::Number, &[]),
    ("lm.max_tokens", Kind::Int, &[]),
    ("agent.model", Kind::Str, &[]),
    ("agent.max_steps", Kind::Int, &[]),
    ("agent.confirm_timeout", Kind::Int, &[]),
    ("agent.digest_time", Kind::Str, &[]),
    ("agent.system_prompt", Kind::Str, &[]),
];

fn number(value: Option<&Value>) -> Option<f64> {
    match value {
        Some(Value::Int(number)) => Some(*number as f64),
        Some(Value::Float(number)) => Some(*number),
        _ => None,
    }
}

fn bare_key(name: &str) -> bool {
    !name.is_empty() && name.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
}

fn telegram_id(text: &str) -> bool {
    let digits = text.strip_prefix('-').unwrap_or(text);
    !digits.is_empty() && digits.chars().all(|c| c.is_ascii_digit())
}

fn clock(text: &str) -> bool {
    let Some((hours, minutes)) = text.split_once(':') else {
        return false;
    };
    let two_digits = |part: &str| part.len() == 2 && part.chars().all(|c| c.is_ascii_digit());
    two_digits(hours) && two_digits(minutes) && hours < "24" && minutes < "60"
}

/// List and table keys of [agent]; same rules as `unlawful.config._agent_errors`.
fn agent_errors(agent: Option<&Value>) -> Vec<String> {
    let Some(agent @ Value::Table(_)) = agent else {
        return vec!["Invalid agent: expected table".into()];
    };
    let mut errors = Vec::new();
    let non_empty = |item: &Value| matches!(item, Value::Str(text) if !text.is_empty());
    let id = |item: &Value| matches!(item, Value::Int(_)) || matches!(item, Value::Str(text) if telegram_id(text));
    for (key, message, valid) in [
        ("roots", "expected an array of non-empty strings", &non_empty as &dyn Fn(&Value) -> bool),
        ("allowed_ids", "expected an array of Telegram ids", &id),
        ("commands", "expected an array of command names", &non_empty),
    ] {
        if !matches!(agent.get(key), Some(Value::Array(items)) if items.iter().all(valid)) {
            errors.push(format!("Invalid agent.{key}: {message}"));
        }
    }
    if let Some(Value::Int(steps)) = agent.get("max_steps") {
        if !(1..=100).contains(steps) {
            errors.push("Invalid agent.max_steps: must be between 1 and 100".into());
        }
    }
    if let Some(Value::Int(timeout)) = agent.get("confirm_timeout") {
        if *timeout < 1 {
            errors.push("Invalid agent.confirm_timeout: must be greater than zero".into());
        }
    }
    if let Some(Value::Str(digest)) = agent.get("digest_time") {
        if !digest.is_empty() && !clock(digest) {
            errors.push("Invalid agent.digest_time: expected HH:MM or an empty string".into());
        }
    }
    match agent.get("users") {
        Some(Value::Table(users)) => {
            for (user, level) in users {
                let ok = telegram_id(user) && matches!(level, Value::Str(text) if ["chat", "read", "full"].contains(&text.as_str()));
                if !ok {
                    errors.push(format!("Invalid agent.users.{user}: expected \"chat\", \"read\" or \"full\""));
                }
            }
        }
        _ => errors.push("Invalid agent.users: expected table".into()),
    }
    errors
}

/// Same rules and messages as `unlawful.config.validate_config`.
pub fn validate(config: &Value) -> Vec<String> {
    let mut errors = Vec::new();
    for (dotted, kind, choices) in CHECKS {
        let Some(value) = config.lookup(dotted) else {
            errors.push(format!("Unknown configuration key: {dotted}"));
            continue;
        };
        let (ok, expected) = match kind {
            Kind::Bool => (matches!(value, Value::Bool(_)), "bool"),
            Kind::Int => (matches!(value, Value::Int(_)), "int"),
            Kind::Str => (matches!(value, Value::Str(_)), "str"),
            Kind::Number => (matches!(value, Value::Int(_) | Value::Float(_)), "int or float"),
        };
        if !ok {
            errors.push(format!("Invalid {dotted}: expected {expected}"));
            continue;
        }
        let text = match value {
            Value::Str(text) => text.clone(),
            other => other.display(),
        };
        if !choices.is_empty() && !choices.contains(&text.as_str()) {
            errors.push(format!("Invalid {dotted}: expected one of {}", choices.join(", ")));
        }
    }
    for dotted in ["core.command_timeout", "mac.timeout", "lm.idle_minutes"] {
        if let Some(Value::Int(number)) = config.lookup(dotted) {
            if *number < 0 {
                errors.push(format!("Invalid {dotted}: must be zero or greater"));
            }
        }
    }
    if let Some(temperature) = number(config.lookup("lm.temperature")) {
        if !(0.0..=2.0).contains(&temperature) {
            errors.push("Invalid lm.temperature: must be between 0 and 2".into());
        }
    }
    if let Some(Value::Int(port)) = config.lookup("lm.port") {
        if !(1..=65535).contains(port) {
            errors.push("Invalid lm.port: must be between 1 and 65535".into());
        }
    }
    if let Some(Value::Int(tokens)) = config.lookup("lm.max_tokens") {
        if *tokens < 1 {
            errors.push("Invalid lm.max_tokens: must be greater than zero".into());
        }
    }
    if let Some(delay) = number(config.lookup("apps.spotify_autoplay_delay")) {
        if delay < 0.0 {
            errors.push("Invalid apps.spotify_autoplay_delay: must be zero or greater".into());
        }
    }
    match config.lookup("zip.level") {
        None => errors.push("Unknown configuration key: zip.level".into()),
        Some(level) => {
            let ok = match level {
                Value::Int(number) => (0..=9).contains(number),
                Value::Str(name) => ["store", "fastest", "fast", "normal", "max", "ultra"].contains(&name.as_str()),
                _ => false,
            };
            if !ok {
                errors.push("Invalid zip.level: expected 0-9 or store, fastest, fast, normal, max, ultra".into());
            }
        }
    }
    errors.extend(agent_errors(config.get("agent")));
    match config.get("aliases") {
        Some(Value::Table(entries)) => {
            for (name, tokens) in entries {
                let ok = bare_key(name)
                    && matches!(tokens, Value::Array(items) if !items.is_empty()
                        && items.iter().all(|item| matches!(item, Value::Str(text) if !text.is_empty())));
                if !ok {
                    errors.push(format!("Invalid aliases.{name}: expected a non-empty array of strings"));
                }
            }
        }
        _ => errors.push("Invalid aliases: expected table".into()),
    }
    errors
}

pub fn write_document(document: &DocumentMut) -> Result<()> {
    checked(document)?;
    atomic_write(&config_file(), &document.to_string(), ".config.")?;
    Ok(())
}

/// Parse a `ul config set` value as TOML; bare text becomes a string.
pub fn parse_value(raw: &str) -> Item {
    match raw.parse::<toml_edit::Value>() {
        Ok(toml_edit::Value::InlineTable(table)) => Item::Table(table.into_table()),
        Ok(mut value) => {
            value.decor_mut().clear();
            Item::Value(value)
        }
        Err(_) => Item::Value(raw.into()),
    }
}

pub fn set(dotted: &str, item: Item) -> Result<()> {
    let parts: Vec<&str> = dotted.split('.').collect();
    if dotted.is_empty() || parts.iter().any(|part| part.is_empty()) {
        return Err(ConfigError(format!("Invalid configuration key: '{dotted}'")));
    }
    let mut document = read_document()?;
    let current = merged(&document);
    let mut table: &mut dyn TableLike = document.as_table_mut();
    for (index, part) in parts[..parts.len() - 1].iter().enumerate() {
        let prefix = parts[..=index].join(".");
        if matches!(current.lookup(&prefix), Some(value) if !matches!(value, Value::Table(_))) {
            return Err(ConfigError(format!("Configuration key is not a table: {part}")));
        }
        if table.get(part).is_none() {
            let mut child = Table::new();
            child.set_implicit(true);
            table.insert(part, Item::Table(child));
        }
        table = table
            .get_mut(part)
            .and_then(Item::as_table_like_mut)
            .ok_or_else(|| ConfigError(format!("Configuration key is not a table: {part}")))?;
    }
    table.insert(parts[parts.len() - 1], item);
    write_document(&document)
}

pub fn reset() -> Result<()> {
    atomic_write(&config_file(), assets::DEFAULT_CONFIG_TOML, ".config.")?;
    Ok(())
}

pub fn write_defaults_if_missing() -> std::io::Result<()> {
    if !config_file().exists() {
        atomic_write(&config_file(), assets::DEFAULT_CONFIG_TOML, ".config.")?;
    }
    Ok(())
}

fn fill_missing(table: &mut dyn TableLike, defaults: &dyn TableLike) {
    for (key, default) in defaults.iter() {
        match table.get_mut(key) {
            None => {
                table.insert(key, default.clone());
            }
            Some(existing) => {
                if let (Some(child), Some(default_child)) = (existing.as_table_like_mut(), default.as_table_like()) {
                    fill_missing(child, default_child);
                }
            }
        }
    }
}

/// Keys of earlier releases that nothing reads any more: per-feature storage
/// paths and the LM Studio connection that `ul lm` replaced with its own engine.
const OBSOLETE_KEYS: [(&str, &str); 5] = [
    ("capture", "screenshot_dir"),
    ("capture", "recording_dir"),
    ("telegram", "download_dir"),
    ("lm", "base_url"),
    ("lm", "timeout"),
];

/// `ul doctor --fix`: add missing defaults and drop superseded keys,
/// keeping the user's comments and layout.
pub fn materialize() -> Result<bool> {
    let mut document = read_document()?;
    checked(&document)?;
    let before = document.to_string();
    for (section, key) in OBSOLETE_KEYS {
        if let Some(table) = document.get_mut(section).and_then(Item::as_table_like_mut) {
            table.remove(key);
        }
    }
    fill_missing(document.as_table_mut(), defaults_document().as_table());
    if document.to_string() == before {
        return Ok(false);
    }
    write_document(&document)?;
    Ok(true)
}

/// Lenient read of `storage.root` used while bootstrapping, before validation.
pub fn configured_storage_root() -> PathBuf {
    let configured = read_document()
        .ok()
        .and_then(|document| document.get("storage")?.get("root")?.as_str().map(str::to_string))
        .unwrap_or_else(|| "data".into());
    storage_root_from(&configured)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_are_valid() {
        assert_eq!(validate(&defaults()), Vec::<String>::new());
    }

    #[test]
    fn invalid_values_have_python_messages() {
        let mut data = defaults();
        let user: DocumentMut = "[core]\ncommand_timeout = \"forever\"\n[games]\ndifficulty = \"brutal\"\n[aliases]\nx = []\n[lm]\nport = 70000\n"
            .parse()
            .unwrap();
        data.merge(&Value::from_table(user.as_table()));
        let errors = validate(&data);
        assert!(errors.contains(&"Invalid core.command_timeout: expected int".to_string()));
        assert!(errors.contains(&"Invalid games.difficulty: expected one of easy, hard, normal".to_string()));
        assert!(errors.contains(&"Invalid aliases.x: expected a non-empty array of strings".to_string()));
        assert!(errors.contains(&"Invalid lm.port: must be between 1 and 65535".to_string()));
    }

    #[test]
    fn values_parse_like_toml() {
        assert!(matches!(parse_value("12"), Item::Value(toml_edit::Value::Integer(_))));
        assert!(matches!(parse_value("hello world"), Item::Value(toml_edit::Value::String(_))));
        assert!(matches!(parse_value("{ g = [\"git\"] }"), Item::Table(_)));
        assert_eq!(Value::Float(2.0).display(), "2.0");
    }

    fn merged_with(user: &str) -> Value {
        let mut data = defaults();
        let document: DocumentMut = user.parse().unwrap();
        data.merge(&Value::from_table(document.as_table()));
        data
    }

    #[test]
    fn every_numeric_rule_is_checked() {
        let errors = validate(&merged_with(
            "[core]\ncommand_timeout = -1\n[mac]\ntimeout = -2\n[lm]\nidle_minutes = -3\ntemperature = 2.5\nmax_tokens = 0\n[apps]\nspotify_autoplay_delay = -0.5\n[zip]\nlevel = 10\n[projects.cpp]\nstandard = 98\n",
        ));
        for expected in [
            "Invalid core.command_timeout: must be zero or greater",
            "Invalid mac.timeout: must be zero or greater",
            "Invalid lm.idle_minutes: must be zero or greater",
            "Invalid lm.max_tokens: must be greater than zero",
            "Invalid lm.temperature: must be between 0 and 2",
            "Invalid apps.spotify_autoplay_delay: must be zero or greater",
            "Invalid zip.level: expected 0-9 or store, fastest, fast, normal, max, ultra",
            "Invalid projects.cpp.standard: expected one of 11, 14, 17, 20, 23, 26",
        ] {
            assert!(errors.contains(&expected.to_string()), "{expected} not in {errors:?}");
        }
        assert_eq!(validate(&merged_with("[lm]\ntemperature = 2\n[zip]\nlevel = 0\n")), Vec::<String>::new());
        assert_eq!(validate(&merged_with("[zip]\nlevel = \"ultra\"\n")), Vec::<String>::new());
    }

    #[test]
    fn structural_errors_are_reported() {
        let errors = validate(&merged_with("core = 5\naliases = [\"x\"]\n"));
        assert!(errors.contains(&"Unknown configuration key: core.color".to_string()), "{errors:?}");
        assert!(errors.contains(&"Invalid aliases: expected table".to_string()));
        let errors = validate(&merged_with("[zip]\nlevel = true\n[apps]\nspotify_autoplay_delay = \"soon\"\n"));
        assert!(errors.contains(&"Invalid zip.level: expected 0-9 or store, fastest, fast, normal, max, ultra".to_string()));
        assert!(errors.contains(&"Invalid apps.spotify_autoplay_delay: expected int or float".to_string()));
        let errors = validate(&merged_with("[aliases]\n\"bad key\" = [\"git\"]\nempty = [\"\"]\nnum = [1]\n"));
        assert_eq!(errors.len(), 3, "{errors:?}");
    }

    #[test]
    fn values_convert_from_every_toml_shape() {
        let data = merged_with(
            "when = 1979-05-27T07:32:00Z\ninline = { a = 1, b = [true, 2.5] }\n[[servers]]\nname = \"a\"\n[[servers]]\nname = \"b\"\n",
        );
        assert_eq!(data.lookup("when"), Some(&Value::Other("1979-05-27T07:32:00Z".into())));
        assert_eq!(data.lookup("inline.a"), Some(&Value::Int(1)));
        assert_eq!(data.lookup("inline.b").unwrap().display(), "[\n  true,\n  2.5\n]");
        assert_eq!(data.lookup("servers").unwrap().display(), "[\n  {\n    \"name\": \"a\"\n  },\n  {\n    \"name\": \"b\"\n  }\n]");
        assert_eq!(data.lookup("core..color"), None);
        assert_eq!(data.lookup("core.color.deeper"), None);
    }

    #[test]
    fn merge_replaces_scalars_and_deep_merges_tables() {
        let data = merged_with("[core]\nverbose = true\n[projects.cpp]\nstandard = 23\n");
        let config = Config { data };
        assert!(config.flag("core.verbose"));
        assert!(config.flag("core.color"));
        assert_eq!(config.int("projects.cpp.standard"), 23);
        assert!(!config.flag("projects.rust.initialize_git"));
        assert_eq!(config.string("core.missing"), "");
        assert_eq!(config.int("core.color"), 0);
        assert!(config.aliases().is_empty());
        assert_eq!(config.alias("x"), None);
    }

    #[test]
    fn storage_root_handles_relative_absolute_and_home_paths() {
        assert_eq!(storage_root_from("/abs/data"), PathBuf::from("/abs/data"));
        assert_eq!(storage_root_from("data"), config_dir().join("data"));
        assert_eq!(storage_root_from("~/stuff"), crate::util::home().join("stuff"));
    }
}
