//! ule.toml: options, key bindings, user themes and language overrides.

use std::env;
use std::fs;
use std::path::PathBuf;

use toml_edit::{DocumentMut, Item, Table, Value};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LineNumbers {
    Absolute,
    Relative,
    Off,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FormatOnSave {
    /// Only when the project has the formatter's config file (rustfmt.toml, .prettierrc, ...).
    Auto,
    Always,
    Never,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Bufferline {
    Always,
    Multiple,
    Never,
}

#[derive(Clone, Debug)]
pub struct Options {
    pub theme: String,
    pub line_numbers: LineNumbers,
    pub cursorline: bool,
    pub scrolloff: usize,
    pub tab_width: usize,
    pub expand_tab: bool,
    /// None: the language decides (Markdown and text wrap, code does not).
    pub wrap: Option<bool>,
    pub auto_pairs: bool,
    pub auto_indent: bool,
    pub auto_save: bool,
    pub auto_reload: bool,
    pub format_on_save: FormatOnSave,
    pub trim_trailing_whitespace: bool,
    pub final_newline: bool,
    pub clipboard: bool,
    pub mouse: bool,
    pub indent_guides: bool,
    pub inline_diagnostics: bool,
    pub bufferline: Bufferline,
    pub whichkey: bool,
    pub timeout: u64,
    pub leader: String,
    pub auto_complete: bool,
    pub ignorecase: bool,
    pub smartcase: bool,
    pub rulers: Vec<usize>,
    pub show_whitespace: bool,
    pub lsp: bool,
    pub true_color: Option<bool>,
    pub cursor_shape: bool,
    pub hidden_files: bool,
    pub explorer_width: usize,
    pub panel_height: usize,
    pub restore_cursor: bool,
    pub color_column: bool,
    pub incsearch: bool,
    pub hlsearch: bool,
}

impl Default for Options {
    fn default() -> Self {
        Options {
            theme: "unlaw".into(),
            line_numbers: LineNumbers::Relative,
            cursorline: true,
            scrolloff: 5,
            tab_width: 4,
            expand_tab: true,
            wrap: None,
            auto_pairs: true,
            auto_indent: true,
            auto_save: false,
            auto_reload: true,
            format_on_save: FormatOnSave::Auto,
            trim_trailing_whitespace: true,
            final_newline: true,
            clipboard: true,
            mouse: true,
            indent_guides: true,
            inline_diagnostics: true,
            bufferline: Bufferline::Multiple,
            whichkey: true,
            timeout: 1000,
            leader: "<space>".into(),
            auto_complete: true,
            ignorecase: true,
            smartcase: true,
            rulers: Vec::new(),
            show_whitespace: false,
            lsp: true,
            true_color: None,
            cursor_shape: true,
            hidden_files: false,
            explorer_width: 30,
            panel_height: 12,
            restore_cursor: true,
            color_column: false,
            incsearch: true,
            hlsearch: true,
        }
    }
}

/// Every option `:set` and ule.toml know, with a one-line description.
pub const OPTIONS: &[(&str, &str)] = &[
    ("theme", "color theme: unlaw (terminal colors), onedark, gruvbox, catppuccin, tokyonight, light"),
    ("line_numbers", "relative, absolute or off"),
    ("cursorline", "highlight the cursor's line"),
    ("scrolloff", "lines kept visible above and below the cursor"),
    ("tab_width", "columns per tab"),
    ("expand_tab", "Tab inserts spaces (the file's own style wins when detected)"),
    ("wrap", "wrap long lines (default: Markdown and text only)"),
    ("auto_pairs", "insert closing brackets and quotes"),
    ("auto_indent", "keep and adjust indentation on new lines"),
    ("auto_save", "save modified files when ule loses focus"),
    ("auto_reload", "reload files changed outside ule when they have no unsaved edits"),
    ("format_on_save", "auto (only when the project has a formatter config), always or never"),
    ("trim_trailing_whitespace", "strip spaces at line ends when saving"),
    ("final_newline", "make sure files end with a newline"),
    ("clipboard", "yank and paste use the macOS clipboard"),
    ("mouse", "click, drag to select, scroll"),
    ("indent_guides", "thin lines at each indent level"),
    ("inline_diagnostics", "show LSP messages at line ends"),
    ("bufferline", "open files across the top: always, multiple or never"),
    ("whichkey", "show the possible next keys after a prefix like <space>"),
    ("timeout", "ms to wait for the rest of a key sequence"),
    ("leader", "the leader key"),
    ("auto_complete", "completion menu while typing"),
    ("ignorecase", "search ignores case"),
    ("smartcase", "...unless the pattern has capitals"),
    ("rulers", "columns to mark, e.g. [80, 100]"),
    ("show_whitespace", "draw tabs and trailing spaces"),
    ("lsp", "start language servers"),
    ("true_color", "24-bit colors (default: from COLORTERM)"),
    ("cursor_shape", "bar cursor in insert mode"),
    ("hidden_files", "pickers and the explorer show dotfiles"),
    ("explorer_width", "width of the file explorer"),
    ("panel_height", "height of the output panel"),
    ("restore_cursor", "reopen files where you left them"),
    ("incsearch", "jump to matches while typing a search"),
    ("hlsearch", "highlight all search matches"),
];

fn parse_bool(value: &str) -> Option<bool> {
    match value {
        "true" | "yes" | "on" | "1" => Some(true),
        "false" | "no" | "off" | "0" => Some(false),
        _ => None,
    }
}

impl Options {
    /// Sets one option from text (`:set name=value`); returns an error message.
    pub fn set(&mut self, name: &str, value: &str) -> Result<(), String> {
        let number = || value.parse::<usize>().map_err(|_| format!("{name} needs a number"));
        let boolean = || parse_bool(value).ok_or_else(|| format!("{name} is true or false"));
        match name {
            "theme" => self.theme = value.to_string(),
            "line_numbers" | "number" | "nu" => {
                self.line_numbers = match value {
                    "relative" | "rel" => LineNumbers::Relative,
                    "absolute" | "abs" | "true" => LineNumbers::Absolute,
                    "off" | "none" | "false" => LineNumbers::Off,
                    _ => return Err("line_numbers is relative, absolute or off".into()),
                }
            }
            "cursorline" | "cul" => self.cursorline = boolean()?,
            "scrolloff" | "so" => self.scrolloff = number()?,
            "tab_width" | "tabstop" | "ts" | "shiftwidth" | "sw" => self.tab_width = number()?.clamp(1, 16),
            "expand_tab" | "expandtab" | "et" => self.expand_tab = boolean()?,
            "wrap" => self.wrap = if value == "auto" { None } else { Some(boolean()?) },
            "auto_pairs" => self.auto_pairs = boolean()?,
            "auto_indent" | "autoindent" | "ai" => self.auto_indent = boolean()?,
            "auto_save" => self.auto_save = boolean()?,
            "auto_reload" | "autoread" => self.auto_reload = boolean()?,
            "format_on_save" => {
                self.format_on_save = match value {
                    "auto" => FormatOnSave::Auto,
                    "always" | "true" => FormatOnSave::Always,
                    "never" | "false" => FormatOnSave::Never,
                    _ => return Err("format_on_save is auto, always or never".into()),
                }
            }
            "trim_trailing_whitespace" => self.trim_trailing_whitespace = boolean()?,
            "final_newline" => self.final_newline = boolean()?,
            "clipboard" => self.clipboard = boolean()?,
            "mouse" => self.mouse = boolean()?,
            "indent_guides" => self.indent_guides = boolean()?,
            "inline_diagnostics" => self.inline_diagnostics = boolean()?,
            "bufferline" => {
                self.bufferline = match value {
                    "always" | "true" => Bufferline::Always,
                    "multiple" => Bufferline::Multiple,
                    "never" | "false" => Bufferline::Never,
                    _ => return Err("bufferline is always, multiple or never".into()),
                }
            }
            "whichkey" => self.whichkey = boolean()?,
            "timeout" | "timeoutlen" => self.timeout = number()? as u64,
            "leader" => self.leader = value.to_string(),
            "auto_complete" => self.auto_complete = boolean()?,
            "ignorecase" | "ic" => self.ignorecase = boolean()?,
            "smartcase" | "scs" => self.smartcase = boolean()?,
            "rulers" | "colorcolumn" | "cc" => {
                self.rulers = value
                    .trim_matches(|c| c == '[' || c == ']')
                    .split(',')
                    .map(str::trim)
                    .filter(|part| !part.is_empty())
                    .map(|part| part.parse::<usize>().map_err(|_| "rulers are column numbers".to_string()))
                    .collect::<Result<_, _>>()?
            }
            "show_whitespace" | "list" => self.show_whitespace = boolean()?,
            "lsp" => self.lsp = boolean()?,
            "true_color" | "termguicolors" => self.true_color = Some(boolean()?),
            "cursor_shape" => self.cursor_shape = boolean()?,
            "hidden_files" => self.hidden_files = boolean()?,
            "explorer_width" => self.explorer_width = number()?.clamp(12, 80),
            "panel_height" => self.panel_height = number()?.clamp(3, 60),
            "restore_cursor" => self.restore_cursor = boolean()?,
            "incsearch" | "is" => self.incsearch = boolean()?,
            "hlsearch" | "hls" => self.hlsearch = boolean()?,
            _ => return Err(format!("unknown option {name:?} (:help options)")),
        }
        Ok(())
    }

    /// `:set wrap!` and `:set nowrap` for booleans.
    pub fn toggle(&mut self, name: &str) -> Result<bool, String> {
        let current = self.get(name).ok_or_else(|| format!("unknown option {name:?}"))?;
        let next = match current.as_str() {
            "true" => "false",
            "false" => "true",
            "auto" if name == "wrap" => "true",
            _ => return Err(format!("{name} is not on/off")),
        };
        self.set(name, next)?;
        Ok(next == "true")
    }

    pub fn get(&self, name: &str) -> Option<String> {
        Some(match name {
            "theme" => self.theme.clone(),
            "line_numbers" | "number" | "nu" => match self.line_numbers {
                LineNumbers::Absolute => "absolute",
                LineNumbers::Relative => "relative",
                LineNumbers::Off => "off",
            }
            .into(),
            "cursorline" | "cul" => self.cursorline.to_string(),
            "scrolloff" | "so" => self.scrolloff.to_string(),
            "tab_width" | "tabstop" | "ts" | "shiftwidth" | "sw" => self.tab_width.to_string(),
            "expand_tab" | "expandtab" | "et" => self.expand_tab.to_string(),
            "wrap" => self.wrap.map_or("auto".into(), |wrap| wrap.to_string()),
            "auto_pairs" => self.auto_pairs.to_string(),
            "auto_indent" | "autoindent" | "ai" => self.auto_indent.to_string(),
            "auto_save" => self.auto_save.to_string(),
            "auto_reload" | "autoread" => self.auto_reload.to_string(),
            "format_on_save" => match self.format_on_save {
                FormatOnSave::Auto => "auto",
                FormatOnSave::Always => "always",
                FormatOnSave::Never => "never",
            }
            .into(),
            "trim_trailing_whitespace" => self.trim_trailing_whitespace.to_string(),
            "final_newline" => self.final_newline.to_string(),
            "clipboard" => self.clipboard.to_string(),
            "mouse" => self.mouse.to_string(),
            "indent_guides" => self.indent_guides.to_string(),
            "inline_diagnostics" => self.inline_diagnostics.to_string(),
            "bufferline" => match self.bufferline {
                Bufferline::Always => "always",
                Bufferline::Multiple => "multiple",
                Bufferline::Never => "never",
            }
            .into(),
            "whichkey" => self.whichkey.to_string(),
            "timeout" | "timeoutlen" => self.timeout.to_string(),
            "leader" => self.leader.clone(),
            "auto_complete" => self.auto_complete.to_string(),
            "ignorecase" | "ic" => self.ignorecase.to_string(),
            "smartcase" | "scs" => self.smartcase.to_string(),
            "rulers" | "colorcolumn" | "cc" => {
                format!("[{}]", self.rulers.iter().map(usize::to_string).collect::<Vec<_>>().join(", "))
            }
            "show_whitespace" | "list" => self.show_whitespace.to_string(),
            "lsp" => self.lsp.to_string(),
            "true_color" | "termguicolors" => self.true_color.map_or("auto".into(), |value| value.to_string()),
            "cursor_shape" => self.cursor_shape.to_string(),
            "hidden_files" => self.hidden_files.to_string(),
            "explorer_width" => self.explorer_width.to_string(),
            "panel_height" => self.panel_height.to_string(),
            "restore_cursor" => self.restore_cursor.to_string(),
            "incsearch" | "is" => self.incsearch.to_string(),
            "hlsearch" | "hls" => self.hlsearch.to_string(),
            _ => return None,
        })
    }
}

/// A binding's target: a named command (with args), an ex command line, or other keys.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Action {
    Command(String, Vec<String>),
    Ex(String),
    Keys(String),
    Nop,
}

#[derive(Clone, Debug, Default)]
pub struct UserKeys {
    /// (mode, keys as written, actions, description)
    pub bindings: Vec<(String, String, Vec<Action>, String)>,
}

#[derive(Debug, Default)]
pub struct Config {
    pub path: Option<PathBuf>,
    pub options: Options,
    pub keys: UserKeys,
    pub themes: Option<Table>,
    pub languages: Option<Table>,
    pub errors: Vec<String>,
}

pub fn config_dir() -> PathBuf {
    if let Some(dir) = env::var_os("XDG_CONFIG_HOME").filter(|value| !value.is_empty()) {
        return PathBuf::from(dir).join("unlaw");
    }
    home().join(".config").join("unlaw")
}

pub fn home() -> PathBuf {
    env::var_os("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("/"))
}

pub fn config_path() -> PathBuf {
    if let Some(path) = env::var_os("ULE_CONFIG").filter(|value| !value.is_empty()) {
        return PathBuf::from(path);
    }
    config_dir().join("ule.toml")
}

/// Where ule keeps history and cursor positions: `<storage.root>/ule` of the Unlaw config.
pub fn state_dir() -> PathBuf {
    let dir = config_dir();
    let mut root = PathBuf::from("data");
    if let Ok(text) = fs::read_to_string(dir.join("config.toml")) {
        if let Ok(document) = text.parse::<DocumentMut>() {
            if let Some(value) = document.get("storage").and_then(|storage| storage.get("root")).and_then(Item::as_str)
            {
                if !value.trim().is_empty() {
                    root = PathBuf::from(value.trim());
                }
            }
        }
    }
    let root = if let Some(rest) = root.to_str().and_then(|text| text.strip_prefix("~/")) {
        home().join(rest)
    } else if root.is_absolute() {
        root
    } else {
        dir.join(root)
    };
    root.join("ule")
}

/// A binding's value: "command arg", ":ex command", "keys", or a list of those.
pub fn parse_action(text: &str, commands: &[&str]) -> Action {
    let trimmed = text.trim();
    if trimmed.is_empty() || trimmed == "nop" {
        return Action::Nop;
    }
    if let Some(ex) = trimmed.strip_prefix(':') {
        return Action::Ex(ex.to_string());
    }
    let mut words = trimmed.split_whitespace();
    if let Some(first) = words.next() {
        if commands.contains(&first) {
            return Action::Command(first.to_string(), words.map(str::to_string).collect());
        }
    }
    Action::Keys(text.to_string())
}

fn value_text(value: &Value) -> Option<String> {
    match value {
        Value::String(text) => Some(text.value().clone()),
        Value::Integer(number) => Some(number.value().to_string()),
        Value::Boolean(flag) => Some(flag.value().to_string()),
        Value::Array(items) => Some(format!("[{}]", items.iter().filter_map(value_text).collect::<Vec<_>>().join(","))),
        _ => None,
    }
}

impl Config {
    pub fn load(commands: &[&str]) -> Config {
        let path = config_path();
        match fs::read_to_string(&path) {
            Ok(text) => {
                let mut config = Config::parse(&text, commands);
                config.path = Some(path);
                config
            }
            Err(_) => Config { path: Some(path), ..Config::default() },
        }
    }

    pub fn parse(text: &str, commands: &[&str]) -> Config {
        let mut config = Config::default();
        let document = match text.parse::<DocumentMut>() {
            Ok(document) => document,
            Err(error) => {
                config.errors.push(format!("ule.toml: {}", error.to_string().lines().next().unwrap_or("parse error")));
                return config;
            }
        };
        for (key, item) in document.iter() {
            match key {
                "theme" => match item.as_str() {
                    Some(theme) => config.options.theme = theme.to_string(),
                    None => config.errors.push("theme must be a string".into()),
                },
                "editor" => {
                    let Some(table) = item.as_table_like() else {
                        config.errors.push("[editor] must be a table".into());
                        continue;
                    };
                    for (name, value) in table.iter() {
                        let Some(text) = value.as_value().and_then(value_text) else {
                            config.errors.push(format!("editor.{name}: unsupported value"));
                            continue;
                        };
                        if let Err(error) = config.options.set(name, &text) {
                            config.errors.push(format!("editor.{name}: {error}"));
                        }
                    }
                }
                "keys" => {
                    let Some(modes) = item.as_table_like() else {
                        config.errors.push("[keys] must hold [keys.normal], [keys.insert], [keys.visual]".into());
                        continue;
                    };
                    for (mode, table) in modes.iter() {
                        if !matches!(mode, "normal" | "insert" | "visual" | "all") {
                            config.errors.push(format!("keys.{mode}: modes are normal, insert, visual, all"));
                            continue;
                        }
                        let Some(table) = table.as_table_like() else {
                            config.errors.push(format!("keys.{mode} must be a table"));
                            continue;
                        };
                        for (keys, value) in table.iter() {
                            let actions: Vec<Action> = match value.as_value() {
                                Some(Value::String(text)) => vec![parse_action(text.value(), commands)],
                                Some(Value::Array(items)) => items
                                    .iter()
                                    .filter_map(|item| item.as_str())
                                    .map(|text| parse_action(text, commands))
                                    .collect(),
                                _ => {
                                    config.errors.push(format!("keys.{mode}.{keys}: a string or a list of strings"));
                                    continue;
                                }
                            };
                            let description = match value.as_value() {
                                Some(Value::String(text)) => text.value().clone(),
                                _ => "custom".into(),
                            };
                            config.keys.bindings.push((mode.to_string(), keys.to_string(), actions, description));
                        }
                    }
                }
                "themes" => config.themes = item.as_table().cloned(),
                "languages" => config.languages = item.as_table().cloned(),
                other => config.errors.push(format!("ule.toml: unknown section or key {other:?}")),
            }
        }
        config
    }
}

/// A commented starting point, written by `:config` when ule.toml does not exist yet.
pub const TEMPLATE: &str = r##"# ule settings. Changes apply after :config-reload (or restarting ule).
# Every key is optional; the defaults are shown commented out.

# theme = "unlaw"          # unlaw (terminal colors), onedark, gruvbox, catppuccin, tokyonight, light

[editor]
# line_numbers = "relative" # relative, absolute, off
# cursorline = true
# scrolloff = 5
# tab_width = 4
# expand_tab = true
# wrap = "auto"             # true/false; auto = Markdown and text wrap
# auto_pairs = true
# auto_indent = true
# auto_save = false         # save when ule loses focus
# auto_reload = true        # pick up changes other programs (or agents) make
# format_on_save = "auto"   # auto: only when the project has rustfmt.toml, .prettierrc, ...
# trim_trailing_whitespace = true
# clipboard = true          # y/p use the macOS clipboard
# mouse = true
# indent_guides = true
# inline_diagnostics = true
# bufferline = "multiple"   # always, multiple, never
# whichkey = true
# timeout = 1000
# leader = "<space>"
# auto_complete = true
# rulers = [100]
# show_whitespace = false
# lsp = true
# hidden_files = false
# explorer_width = 30
# panel_height = 12

# Key bindings: a command name (see :commands), ":ex command", or keys.
# Lists run in order. "nop" removes a default binding.
[keys.normal]
# "<C-s>" = "save"
# "<leader>t" = ":run cargo test"
# "H" = "^"
# "<leader>ww" = ["save", ":ul git \"wip\""]

[keys.insert]
# "jk" = "normal_mode"

[keys.visual]

# Your own theme, based on a built-in one:
# [themes.mine]
# inherits = "onedark"
# "syntax.keyword" = { fg = "#ff79c6", modifiers = ["bold"] }

# Language overrides or new languages (keys as in :help languages):
# [languages.python]
# run = "uv run {file}"
# lsp = [["ruff", "server"], ["basedpyright-langserver", "--stdio"]]
"##;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_options_keys_and_reports_errors() {
        let config = Config::parse(
            "theme = \"gruvbox\"\n[editor]\ntab_width = 2\nwrap = true\nrulers = [80, 100]\nbogus = 1\n[keys.normal]\n\"<C-s>\" = \"save\"\n\"H\" = \"^\"\n\"<leader>t\" = \":run cargo test\"\n[keys.insert]\n\"jk\" = \"normal_mode\"\n",
            &["save", "normal_mode"],
        );
        assert_eq!(config.options.theme, "gruvbox");
        assert_eq!(config.options.tab_width, 2);
        assert_eq!(config.options.wrap, Some(true));
        assert_eq!(config.options.rulers, vec![80, 100]);
        assert_eq!(config.errors.len(), 1, "{:?}", config.errors);
        let actions: Vec<&Action> = config.keys.bindings.iter().map(|binding| &binding.2[0]).collect();
        assert_eq!(actions[0], &Action::Command("save".into(), vec![]));
        assert_eq!(actions[1], &Action::Keys("^".into()));
        assert_eq!(actions[2], &Action::Ex("run cargo test".into()));
        assert_eq!(config.keys.bindings[3].0, "insert");
    }

    #[test]
    fn template_parses_cleanly() {
        let config = Config::parse(TEMPLATE, &[]);
        assert!(config.errors.is_empty(), "{:?}", config.errors);
    }

    #[test]
    fn set_and_toggle() {
        let mut options = Options::default();
        options.set("ts", "2").unwrap();
        assert_eq!(options.tab_width, 2);
        assert!(options.toggle("wrap").unwrap());
        assert!(!options.toggle("wrap").unwrap());
        assert!(options.set("line_numbers", "weird").is_err());
        for (name, _) in OPTIONS {
            assert!(options.get(name).is_some(), "{name}");
        }
    }
}
