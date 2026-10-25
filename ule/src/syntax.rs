//! Languages (detection, comments, indent, tools) and a line-by-line highlighter.
//!
//! The highlighter is a configurable scanner rather than a grammar: every
//! line is scanned from the state the previous line ended in (inside a block
//! comment, a multi-line string, a fenced code block), so editing a line only
//! re-highlights from there on.

use std::collections::HashSet;
use std::path::Path;

use toml_edit::{DocumentMut, Item, Table};

pub const BUILTIN: &str = include_str!("../runtime/languages.toml");

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub enum Kind {
    #[default]
    Code,
    Markdown,
    Markup,
    Diff,
    GitCommit,
    Text,
}

#[derive(Clone, Debug, Default)]
pub struct Language {
    pub name: String,
    pub extensions: Vec<String>,
    pub filenames: Vec<String>,
    pub shebangs: Vec<String>,
    pub kind: Kind,
    pub comment: Option<String>,
    pub block_comment: Option<(String, String)>,
    pub nested_comments: bool,
    pub keywords: HashSet<String>,
    pub types: HashSet<String>,
    pub constants: HashSet<String>,
    pub builtins: HashSet<String>,
    pub strings: Vec<String>,
    pub multiline_strings: Vec<String>,
    pub string_prefixes: String,
    pub raw_strings: bool,
    pub lifetimes: bool,
    pub char_quote: Option<char>,
    pub macros: bool,
    pub attributes: Option<String>,
    pub decorators: bool,
    pub preprocessor: Option<String>,
    pub capitalized_types: bool,
    pub case_insensitive: bool,
    pub json_keys: bool,
    pub toml_keys: bool,
    pub yaml_keys: bool,
    pub shell_variables: bool,
    pub css: bool,
    pub indent: Option<String>,
    pub tab_width: Option<usize>,
    pub wrap: Option<bool>,
    pub indent_after: Vec<String>,
    pub lsp: Vec<Vec<String>>,
    pub roots: Vec<String>,
    pub formatter: Vec<String>,
    pub formatter_configs: Vec<String>,
    pub run: Option<String>,
}

fn strings(table: &Table, key: &str) -> Option<Vec<String>> {
    let array = table.get(key)?.as_array()?;
    Some(array.iter().filter_map(|value| value.as_str().map(str::to_string)).collect())
}

fn flag(table: &Table, key: &str) -> Option<bool> {
    table.get(key)?.as_bool()
}

fn text(table: &Table, key: &str) -> Option<String> {
    table.get(key)?.as_str().map(str::to_string)
}

impl Language {
    /// Applies the keys present in `table` over `self` (so overrides and `inherits` work).
    fn apply(&mut self, table: &Table) -> Result<(), String> {
        let set = |list: Option<Vec<String>>, target: &mut HashSet<String>| {
            if let Some(list) = list {
                *target = list.into_iter().collect();
            }
        };
        for (key, _) in table.iter() {
            const KNOWN: &[&str] = &[
                "extensions",
                "filenames",
                "shebangs",
                "kind",
                "comment",
                "block_comment",
                "nested_comments",
                "keywords",
                "types",
                "constants",
                "builtins",
                "strings",
                "multiline_strings",
                "string_prefixes",
                "raw_strings",
                "lifetimes",
                "char_quote",
                "macros",
                "attributes",
                "decorators",
                "preprocessor",
                "capitalized_types",
                "case_insensitive",
                "json_keys",
                "toml_keys",
                "yaml_keys",
                "shell_variables",
                "css",
                "indent",
                "tab_width",
                "wrap",
                "indent_after",
                "lsp",
                "roots",
                "formatter",
                "formatter_configs",
                "run",
                "inherits",
            ];
            if !KNOWN.contains(&key) {
                return Err(format!("unknown key {key:?}"));
            }
        }
        if let Some(list) = strings(table, "extensions") {
            self.extensions = list;
        }
        if let Some(list) = strings(table, "filenames") {
            self.filenames = list;
        }
        if let Some(list) = strings(table, "shebangs") {
            self.shebangs = list;
        }
        if let Some(kind) = text(table, "kind") {
            self.kind = match kind.as_str() {
                "code" => Kind::Code,
                "markdown" => Kind::Markdown,
                "markup" => Kind::Markup,
                "diff" => Kind::Diff,
                "gitcommit" => Kind::GitCommit,
                "text" => Kind::Text,
                other => return Err(format!("unknown kind {other:?}")),
            };
        }
        if let Some(comment) = table.get("comment") {
            self.comment = comment.as_str().filter(|text| !text.is_empty()).map(str::to_string);
        }
        if let Some(pair) = strings(table, "block_comment") {
            self.block_comment = match pair.as_slice() {
                [open, close] => Some((open.clone(), close.clone())),
                [] => None,
                _ => return Err("block_comment is [open, close]".into()),
            };
        }
        set(strings(table, "keywords"), &mut self.keywords);
        set(strings(table, "types"), &mut self.types);
        set(strings(table, "constants"), &mut self.constants);
        set(strings(table, "builtins"), &mut self.builtins);
        if let Some(list) = strings(table, "strings") {
            self.strings = list;
        }
        if let Some(list) = strings(table, "multiline_strings") {
            self.multiline_strings = list;
        }
        if let Some(prefixes) = text(table, "string_prefixes") {
            self.string_prefixes = prefixes;
        }
        macro_rules! flags {
            ($($name:ident),*) => {$(
                if let Some(value) = flag(table, stringify!($name)) {
                    self.$name = value;
                }
            )*};
        }
        flags!(
            nested_comments,
            raw_strings,
            lifetimes,
            macros,
            decorators,
            capitalized_types,
            case_insensitive,
            json_keys,
            toml_keys,
            yaml_keys,
            shell_variables,
            css
        );
        if let Some(quote) = text(table, "char_quote") {
            self.char_quote = quote.chars().next();
        }
        if let Some(prefix) = text(table, "attributes") {
            self.attributes = Some(prefix).filter(|text| !text.is_empty());
        }
        if let Some(prefix) = text(table, "preprocessor") {
            self.preprocessor = Some(prefix).filter(|text| !text.is_empty());
        }
        if let Some(indent) = text(table, "indent") {
            self.indent = Some(indent);
        }
        if let Some(width) = table.get("tab_width").and_then(Item::as_integer) {
            self.tab_width = Some(width.clamp(1, 16) as usize);
        }
        if let Some(wrap) = flag(table, "wrap") {
            self.wrap = Some(wrap);
        }
        if let Some(list) = strings(table, "indent_after") {
            self.indent_after = list;
        }
        if let Some(array) = table.get("lsp").and_then(Item::as_array) {
            self.lsp = array
                .iter()
                .filter_map(|value| match value {
                    toml_edit::Value::Array(words) => {
                        Some(words.iter().filter_map(|word| word.as_str().map(str::to_string)).collect::<Vec<_>>())
                    }
                    toml_edit::Value::String(word) => Some(vec![word.value().clone()]),
                    _ => None,
                })
                .filter(|words| !words.is_empty())
                .collect();
        }
        if let Some(list) = strings(table, "roots") {
            self.roots = list;
        }
        if let Some(list) = strings(table, "formatter") {
            self.formatter = list;
        }
        if let Some(list) = strings(table, "formatter_configs") {
            self.formatter_configs = list;
        }
        if let Some(run) = table.get("run") {
            self.run = run.as_str().filter(|text| !text.is_empty()).map(str::to_string);
        }
        Ok(())
    }

    pub fn is_keyword(&self, word: &str) -> bool {
        if self.case_insensitive {
            self.keywords.contains(&word.to_ascii_lowercase()) || self.keywords.contains(word)
        } else {
            self.keywords.contains(word)
        }
    }

    pub fn is_type(&self, word: &str) -> bool {
        if self.case_insensitive {
            self.types.contains(&word.to_ascii_lowercase())
        } else {
            self.types.contains(word)
        }
    }
}

#[derive(Clone, Debug, Default)]
pub struct Languages {
    pub list: Vec<Language>,
}

impl Languages {
    /// Built-in languages with `[languages.*]` from ule.toml applied; errors are reported, not fatal.
    pub fn load(user: Option<&Table>) -> (Languages, Vec<String>) {
        let mut errors = Vec::new();
        let mut tables: Vec<(String, Table)> = Vec::new();
        if let Ok(document) = BUILTIN.parse::<DocumentMut>() {
            for (name, item) in document.iter() {
                if let Some(table) = item.as_table() {
                    tables.push((name.to_string(), table.clone()));
                }
            }
        }
        let mut overrides: Vec<(String, Table)> = Vec::new();
        if let Some(user) = user {
            for (name, item) in user.iter() {
                match item.as_table() {
                    Some(table) => overrides.push((name.to_string(), table.clone())),
                    None => errors.push(format!("languages.{name} must be a table")),
                }
            }
        }
        let mut list: Vec<Language> = Vec::new();
        let build = |name: &str, list: &mut Vec<Language>, errors: &mut Vec<String>| {
            let mut language = Language { name: name.to_string(), ..Language::default() };
            let base = tables.iter().find(|(existing, _)| existing == name).map(|(_, table)| table);
            let user = overrides.iter().find(|(existing, _)| existing == name).map(|(_, table)| table);
            let parent = user
                .and_then(|table| text(table, "inherits"))
                .or_else(|| base.and_then(|table| text(table, "inherits")));
            if let Some(parent) = parent {
                if let Some(existing) = list.iter().find(|language| language.name == parent) {
                    language = Language { name: name.to_string(), ..existing.clone() };
                    language.extensions.clear();
                    language.filenames.clear();
                    language.shebangs.clear();
                } else {
                    errors.push(format!("languages.{name}: inherits unknown language {parent:?}"));
                }
            }
            for table in [base, user].into_iter().flatten() {
                if let Err(error) = language.apply(table) {
                    errors.push(format!("languages.{name}: {error}"));
                }
            }
            list.push(language);
        };
        for (name, _) in &tables {
            build(name, &mut list, &mut errors);
        }
        for (name, _) in &overrides {
            if !tables.iter().any(|(existing, _)| existing == name) {
                build(name, &mut list, &mut errors);
            }
        }
        (Languages { list }, errors)
    }

    pub fn get(&self, index: usize) -> Option<&Language> {
        self.list.get(index)
    }

    pub fn by_name(&self, name: &str) -> Option<usize> {
        let name = name.to_ascii_lowercase();
        let alias = match name.as_str() {
            "rs" => "rust",
            "py" | "python3" => "python",
            "js" | "jsx" | "node" => "javascript",
            "ts" | "tsx" => "typescript",
            "sh" | "bash" | "zsh" | "console" | "shell-session" => "shell",
            "c++" | "cc" | "cxx" | "hpp" => "cpp",
            "md" => "markdown",
            "yml" => "yaml",
            "golang" => "go",
            "cs" | "c#" => "csharp",
            "xml" | "svg" | "vue" => "html",
            "scss" | "sass" | "less" => "css",
            "makefile" => "make",
            "docker" => "dockerfile",
            "hs" => "haskell",
            "rb" => "ruby",
            "kt" => "kotlin",
            "patch" => "diff",
            other => other,
        };
        self.list.iter().position(|language| language.name == alias).or_else(|| {
            self.list.iter().position(|language| language.extensions.contains(&name))
        })
    }

    /// By file name, extension, then the shebang of the first line.
    pub fn detect(&self, path: Option<&Path>, first_line: &str) -> Option<usize> {
        if let Some(path) = path {
            let file = path.file_name().and_then(|name| name.to_str()).unwrap_or("");
            if let Some(index) =
                self.list.iter().position(|language| language.filenames.iter().any(|name| name == file))
            {
                return Some(index);
            }
            let extension =
                path.extension().and_then(|extension| extension.to_str()).unwrap_or("").to_ascii_lowercase();
            if !extension.is_empty() {
                if let Some(index) =
                    self.list.iter().position(|language| language.extensions.contains(&extension))
                {
                    return Some(index);
                }
            }
            // `.zshrc.local`, `Dockerfile.dev`
            if let Some(index) = self
                .list
                .iter()
                .position(|language| language.filenames.iter().any(|name| file.starts_with(&format!("{name}."))))
            {
                return Some(index);
            }
        }
        let shebang = first_line.strip_prefix("#!")?;
        let mut words = shebang.split_whitespace();
        let mut program = words.next()?.rsplit('/').next()?;
        if program == "env" {
            program = words.find(|word| !word.starts_with('-'))?;
        }
        let program = program.trim_end_matches(|c: char| c.is_ascii_digit() || c == '.');
        self.list.iter().position(|language| {
            language
                .shebangs
                .iter()
                .any(|name| name.trim_end_matches(|c: char| c.is_ascii_digit() || c == '.') == program)
        })
    }
}

/// Where a line starts: plain code, or inside something that spans lines.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub enum State {
    #[default]
    Normal,
    Comment(usize),
    Str {
        close: String,
        raw: bool,
    },
    Fence {
        marker: String,
        lang: Option<usize>,
        inner: Box<State>,
    },
    MarkupTag,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Span {
    pub start: usize,
    pub end: usize,
    pub class: &'static str,
}

struct Scanner<'a> {
    chars: Vec<char>,
    spans: Vec<Span>,
    lang: &'a Language,
}

impl Scanner<'_> {
    fn push(&mut self, start: usize, end: usize, class: &'static str) {
        if end > start {
            if let Some(last) = self.spans.last_mut() {
                if last.class == class && last.end == start {
                    last.end = end;
                    return;
                }
            }
            self.spans.push(Span { start, end, class });
        }
    }

    fn starts_with(&self, at: usize, text: &str) -> bool {
        text.chars().enumerate().all(|(offset, c)| self.chars.get(at + offset) == Some(&c))
    }

    /// Scans a string body from `at`; returns where it ends and whether it closed.
    fn string_body(&mut self, at: usize, close: &str, raw: bool) -> (usize, bool) {
        let mut i = at;
        let start = at;
        let mut segment = start;
        while i < self.chars.len() {
            if !raw && self.chars[i] == '\\' {
                self.push(segment, i, "syntax.string");
                let end = (i + 2).min(self.chars.len());
                self.push(i, end, "syntax.escape");
                i = end;
                segment = i;
                continue;
            }
            if self.starts_with(i, close) {
                let end = i + close.chars().count();
                self.push(segment, end, "syntax.string");
                return (end, true);
            }
            i += 1;
        }
        self.push(segment, i, "syntax.string");
        (i, false)
    }

    fn comment_body(&mut self, at: usize, depth: usize) -> (usize, usize) {
        let (open, close) = self.lang.block_comment.clone().unwrap_or_default();
        let mut depth = depth;
        let mut i = at;
        while i < self.chars.len() {
            if !close.is_empty() && self.starts_with(i, &close) {
                i += close.chars().count();
                depth -= 1;
                if depth == 0 {
                    self.push(at, i, "syntax.comment");
                    return (i, 0);
                }
                continue;
            }
            if self.lang.nested_comments && !open.is_empty() && self.starts_with(i, &open) {
                depth += 1;
                i += open.chars().count();
                continue;
            }
            i += 1;
        }
        self.push(at, i, "syntax.comment");
        (i, depth)
    }
}

fn is_ident_start(c: char) -> bool {
    c.is_alphabetic() || c == '_'
}

fn is_ident(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
}

/// Highlights one line starting in `state`; returns its spans and the state the next line starts in.
pub fn highlight(languages: &Languages, lang: &Language, line: &str, state: &State) -> (Vec<Span>, State) {
    match lang.kind {
        Kind::Markdown => markdown(languages, lang, line, state),
        Kind::Diff => (diff(line), State::Normal),
        Kind::GitCommit => (gitcommit(line), State::Normal),
        Kind::Text => (Vec::new(), State::Normal),
        Kind::Markup => markup(lang, line, state),
        Kind::Code => code(lang, line, state),
    }
}

fn diff(line: &str) -> Vec<Span> {
    let len = line.chars().count();
    let class = if line.starts_with("+++") || line.starts_with("---") || line.starts_with("diff ") {
        "syntax.heading"
    } else if line.starts_with('+') {
        "syntax.diff.plus"
    } else if line.starts_with('-') {
        "syntax.diff.minus"
    } else if line.starts_with("@@") {
        "syntax.diff.delta"
    } else {
        return Vec::new();
    };
    vec![Span { start: 0, end: len, class }]
}

fn gitcommit(line: &str) -> Vec<Span> {
    let len = line.chars().count();
    if line.starts_with('#') {
        return vec![Span { start: 0, end: len, class: "syntax.comment" }];
    }
    Vec::new()
}

fn code(lang: &Language, line: &str, state: &State) -> (Vec<Span>, State) {
    let mut scanner = Scanner { chars: line.chars().collect(), spans: Vec::new(), lang };
    let len = scanner.chars.len();
    let mut i = 0;
    match state {
        State::Comment(depth) => {
            let (end, depth) = scanner.comment_body(0, *depth);
            if depth > 0 {
                return (scanner.spans, State::Comment(depth));
            }
            i = end;
        }
        State::Str { close, raw } => {
            let (end, closed) = scanner.string_body(0, close, *raw);
            if !closed {
                return (scanner.spans, state.clone());
            }
            i = end;
        }
        _ => {}
    }
    let first = scanner.chars.iter().position(|c| !c.is_whitespace()).unwrap_or(len);
    if let Some(prefix) = &lang.preprocessor {
        if i == 0 && scanner.starts_with(first, prefix) {
            let mut end = len;
            if let Some(comment) = &lang.comment {
                if let Some(at) = (first..len).find(|at| scanner.starts_with(*at, comment)) {
                    end = at;
                }
            }
            scanner.push(first, end, "syntax.macro");
            i = end;
        }
    }
    let mut previous_word_end: Option<usize> = None;
    while i < len {
        let c = scanner.chars[i];
        if c.is_whitespace() {
            i += 1;
            continue;
        }
        if let Some(prefix) = &lang.attributes {
            if scanner.starts_with(i, prefix) || (prefix == "#[" && scanner.starts_with(i, "#![")) {
                let mut depth = 0;
                let mut end = i;
                while end < len {
                    match scanner.chars[end] {
                        '[' => depth += 1,
                        ']' => {
                            depth -= 1;
                            if depth == 0 {
                                end += 1;
                                break;
                            }
                        }
                        _ => {}
                    }
                    end += 1;
                }
                scanner.push(i, end, "syntax.attribute");
                i = end;
                continue;
            }
        }
        if let Some((open, _)) = &lang.block_comment {
            if scanner.starts_with(i, open) {
                let (end, depth) = scanner.comment_body(i + open.chars().count(), 1);
                // comment_body pushed from after the opener; color the opener too.
                scanner.push(i, i + open.chars().count(), "syntax.comment");
                scanner.spans.sort_by_key(|span| span.start);
                merge(&mut scanner.spans);
                if depth > 0 {
                    return (scanner.spans, State::Comment(depth));
                }
                i = end;
                continue;
            }
        }
        if let Some(comment) = &lang.comment {
            // `#` starts shell comments only at a word boundary (`$#`, `a#b` are not comments).
            let boundary = !lang.shell_variables || i == 0 || scanner.chars[i - 1].is_whitespace();
            if scanner.starts_with(i, comment) && boundary {
                scanner.push(i, len, "syntax.comment");
                break;
            }
        }
        if lang.decorators && c == '@' && i + 1 < len && is_ident_start(scanner.chars[i + 1]) {
            let mut end = i + 1;
            while end < len && (is_ident(scanner.chars[end]) || scanner.chars[end] == '.') {
                end += 1;
            }
            scanner.push(i, end, "syntax.attribute");
            i = end;
            continue;
        }
        if lang.shell_variables && c == '$' {
            let mut end = i + 1;
            if end < len && scanner.chars[end] == '{' {
                while end < len && scanner.chars[end] != '}' {
                    end += 1;
                }
                end = (end + 1).min(len);
            } else if end < len && (scanner.chars[end] == '(') {
                end += 1;
            } else {
                while end < len && (is_ident(scanner.chars[end]) || "@#?$!*-".contains(scanner.chars[end])) {
                    end += 1;
                    if !is_ident(scanner.chars[end - 1]) {
                        break;
                    }
                }
            }
            scanner.push(i, end, "syntax.constant");
            i = end;
            continue;
        }
        // Raw and byte strings: r"..", r#".."#, b"..", br#".."#
        if lang.raw_strings && (c == 'r' || c == 'b') {
            let mut at = i;
            if scanner.chars[at] == 'b' {
                at += 1;
            }
            let raw = at < len && scanner.chars[at] == 'r';
            if raw {
                at += 1;
            }
            let hashes = scanner.chars[at.min(len)..].iter().take_while(|c| **c == '#').count();
            if at + hashes < len && scanner.chars[at + hashes] == '"' && (raw || hashes == 0) && at > i {
                let close = format!("\"{}", "#".repeat(hashes));
                let body = at + hashes + 1;
                scanner.push(i, body, "syntax.string");
                let (end, closed) = scanner.string_body(body, &close, raw);
                if !closed {
                    return (scanner.spans, State::Str { close, raw });
                }
                i = end;
                continue;
            }
        }
        // Multi-line delimiters first (""" before ").
        let mut delimiters: Vec<(&String, bool)> = lang.multiline_strings.iter().map(|d| (d, true)).collect();
        delimiters.extend(lang.strings.iter().filter(|d| !lang.multiline_strings.contains(d)).map(|d| (d, false)));
        delimiters.sort_by_key(|(delimiter, _)| std::cmp::Reverse(delimiter.chars().count()));
        let prefix_len = if !lang.string_prefixes.is_empty() {
            scanner.chars[i..].iter().take(2).take_while(|c| lang.string_prefixes.contains(**c)).count()
        } else {
            0
        };
        let starts_word = previous_word_end != Some(i);
        let mut matched = false;
        for (delimiter, multiline) in delimiters {
            let at = if prefix_len > 0 && starts_word && scanner.starts_with(i + prefix_len, delimiter) {
                i + prefix_len
            } else if scanner.starts_with(i, delimiter) {
                i
            } else {
                continue;
            };
            let raw = scanner.chars[i..at].iter().any(|c| *c == 'r' || *c == 'R');
            let body = at + delimiter.chars().count();
            let close = if delimiter == "[[" { "]]".to_string() } else { delimiter.clone() };
            scanner.push(i, body, "syntax.string");
            let (end, closed) =
                scanner.string_body(body, &close, raw || delimiter == "[[" || delimiter == "'" && lang.shell_variables);
            if !closed {
                if multiline {
                    return (scanner.spans, State::Str { close, raw });
                }
                return (scanner.spans, State::Normal);
            }
            i = end;
            matched = true;
            break;
        }
        if matched {
            continue;
        }
        if c == '\'' && (lang.lifetimes || lang.char_quote == Some('\'')) {
            // 'a' / '\n' are chars; 'a (no closing quote) is a lifetime or label.
            let is_char = (i + 2 < len && scanner.chars[i + 2] == '\'' && scanner.chars[i + 1] != '\\')
                || (i + 1 < len && scanner.chars[i + 1] == '\\');
            if is_char {
                let (end, _) = scanner.string_body(i + 1, "'", false);
                scanner.push(i, i + 1, "syntax.string");
                scanner.spans.sort_by_key(|span| span.start);
                i = end;
                continue;
            }
            if lang.lifetimes && i + 1 < len && is_ident_start(scanner.chars[i + 1]) {
                let mut end = i + 1;
                while end < len && is_ident(scanner.chars[end]) {
                    end += 1;
                }
                scanner.push(i, end, "syntax.label");
                i = end;
                continue;
            }
        }
        if c.is_ascii_digit() || (c == '.' && i + 1 < len && scanner.chars[i + 1].is_ascii_digit() && !starts_word) {
            let mut end = i + 1;
            while end < len {
                let d = scanner.chars[end];
                let exponent_sign = (d == '-' || d == '+')
                    && matches!(scanner.chars[end - 1], 'e' | 'E')
                    && !scanner.starts_with(i, "0x");
                let decimal_point = d == '.' && end + 1 < len && scanner.chars[end + 1].is_ascii_digit();
                if d.is_ascii_alphanumeric() || d == '_' || exponent_sign || decimal_point {
                    end += 1;
                } else {
                    break;
                }
            }
            scanner.push(i, end, "syntax.number");
            i = end;
            previous_word_end = Some(end);
            continue;
        }
        if is_ident_start(c) || (lang.css && c == '-' && i + 1 < len && is_ident_start(scanner.chars[i + 1])) {
            let mut end = i + 1;
            while end < len && (is_ident(scanner.chars[end]) || (lang.css && scanner.chars[end] == '-')) {
                end += 1;
            }
            // Ruby's `defined?`, Lisp-ish names: allow a trailing ? or ! when it is a keyword.
            let word: String = scanner.chars[i..end].iter().collect();
            let next = scanner.chars.get(end).copied();
            let after_space = scanner.chars[end..].iter().find(|c| !c.is_whitespace()).copied();
            let before =
                if i > 0 { scanner.chars[..i].iter().rev().find(|c| !c.is_whitespace()).copied() } else { None };
            let class = classify(lang, &word, next, after_space, before, &scanner.chars, end);
            if class == "syntax.macro" && next == Some('!') {
                end += 1;
            }
            if !class.is_empty() {
                scanner.push(i, end, class);
            }
            i = end;
            previous_word_end = Some(end);
            continue;
        }
        if "+-*/%=<>!&|^~?:".contains(c) {
            scanner.push(i, i + 1, "syntax.operator");
        } else if "(){}[],;.".contains(c) {
            scanner.push(i, i + 1, "syntax.punctuation");
        }
        i += 1;
    }
    (scanner.spans, State::Normal)
}

fn classify(
    lang: &Language,
    word: &str,
    next: Option<char>,
    after_space: Option<char>,
    before: Option<char>,
    chars: &[char],
    end: usize,
) -> &'static str {
    if lang.json_keys && after_space == Some(':') {
        return "syntax.property";
    }
    if (lang.toml_keys || lang.yaml_keys) && before.is_none() && matches!(after_space, Some('=') | Some(':')) {
        return "syntax.property";
    }
    if lang.css && after_space == Some(':') && before != Some(':') {
        return "syntax.property";
    }
    if lang.constants.contains(word) {
        return "syntax.constant";
    }
    if lang.is_keyword(word) {
        return "syntax.keyword";
    }
    if lang.is_type(word) {
        return "syntax.type";
    }
    if lang.macros && next == Some('!') && chars.get(end + 1) != Some(&'=') {
        return "syntax.macro";
    }
    if next == Some('(') {
        if lang.builtins.contains(word) {
            return "syntax.function.builtin";
        }
        return "syntax.function";
    }
    if lang.builtins.contains(word) {
        return "syntax.function.builtin";
    }
    if before == Some('.') && lang.kind == Kind::Code {
        return "syntax.property";
    }
    let mut letters = word.chars().filter(|c| c.is_alphabetic());
    let all_caps = word.chars().count() > 1 && letters.clone().all(|c| c.is_uppercase()) && letters.next().is_some();
    if all_caps {
        return "syntax.constant";
    }
    if lang.capitalized_types && word.chars().next().is_some_and(char::is_uppercase) {
        return "syntax.type";
    }
    ""
}

fn merge(spans: &mut Vec<Span>) {
    let mut merged: Vec<Span> = Vec::with_capacity(spans.len());
    for span in spans.drain(..) {
        match merged.last_mut() {
            Some(last) if last.class == span.class && last.end >= span.start => last.end = last.end.max(span.end),
            _ => merged.push(span),
        }
    }
    *spans = merged;
}

fn markup(lang: &Language, line: &str, state: &State) -> (Vec<Span>, State) {
    let chars: Vec<char> = line.chars().collect();
    let mut spans = Vec::new();
    let len = chars.len();
    let mut i = 0;
    let mut in_tag = *state == State::MarkupTag;
    if let State::Comment(_) = state {
        let close: Vec<char> = "-->".chars().collect();
        match (0..len).find(|at| chars[*at..].starts_with(&close)) {
            Some(at) => {
                spans.push(Span { start: 0, end: at + 3, class: "syntax.comment" });
                i = at + 3;
            }
            None => return (vec![Span { start: 0, end: len, class: "syntax.comment" }], state.clone()),
        }
    }
    let _ = lang;
    while i < len {
        if !in_tag && chars[i..].starts_with(&['<', '!', '-', '-']) {
            let close: Vec<char> = "-->".chars().collect();
            match (i + 4..len).find(|at| chars[*at..].starts_with(&close)) {
                Some(at) => {
                    spans.push(Span { start: i, end: at + 3, class: "syntax.comment" });
                    i = at + 3;
                    continue;
                }
                None => {
                    spans.push(Span { start: i, end: len, class: "syntax.comment" });
                    return (spans, State::Comment(1));
                }
            }
        }
        if !in_tag && chars[i] == '<' {
            let mut end = i + 1;
            if end < len && (chars[end] == '/' || chars[end] == '!' || chars[end] == '?') {
                end += 1;
            }
            while end < len && (is_ident(chars[end]) || chars[end] == '-' || chars[end] == ':') {
                end += 1;
            }
            spans.push(Span { start: i, end, class: "syntax.tag" });
            i = end;
            in_tag = true;
            continue;
        }
        if in_tag {
            match chars[i] {
                '>' => {
                    spans.push(Span { start: i, end: i + 1, class: "syntax.tag" });
                    in_tag = false;
                    i += 1;
                }
                '/' if i + 1 < len && chars[i + 1] == '>' => {
                    spans.push(Span { start: i, end: i + 2, class: "syntax.tag" });
                    in_tag = false;
                    i += 2;
                }
                '"' | '\'' => {
                    let quote = chars[i];
                    let end = (i + 1..len).find(|at| chars[*at] == quote).map_or(len, |at| at + 1);
                    spans.push(Span { start: i, end, class: "syntax.string" });
                    i = end;
                }
                c if is_ident_start(c) => {
                    let mut end = i + 1;
                    while end < len && (is_ident(chars[end]) || chars[end] == '-' || chars[end] == ':') {
                        end += 1;
                    }
                    spans.push(Span { start: i, end, class: "syntax.attribute" });
                    i = end;
                }
                _ => i += 1,
            }
            continue;
        }
        if chars[i] == '&' {
            if let Some(end) = (i + 1..len.min(i + 10)).find(|at| chars[*at] == ';') {
                spans.push(Span { start: i, end: end + 1, class: "syntax.escape" });
                i = end + 1;
                continue;
            }
        }
        i += 1;
    }
    (spans, if in_tag { State::MarkupTag } else { State::Normal })
}

fn markdown(languages: &Languages, lang: &Language, line: &str, state: &State) -> (Vec<Span>, State) {
    let chars: Vec<char> = line.chars().collect();
    let len = chars.len();
    let trimmed = line.trim_start();
    let indent = len - trimmed.chars().count();
    if let State::Fence { marker, lang: inner_lang, inner } = state {
        if trimmed.starts_with(marker.as_str())
            && trimmed.trim_end().chars().all(|c| c == marker.chars().next().unwrap_or('`'))
        {
            return (vec![Span { start: 0, end: len, class: "syntax.punctuation" }], State::Normal);
        }
        if let Some(inner_language) = inner_lang.and_then(|index| languages.get(index)) {
            if inner_language.kind != Kind::Markdown {
                let (spans, next) = highlight(languages, inner_language, line, inner);
                return (spans, State::Fence { marker: marker.clone(), lang: *inner_lang, inner: Box::new(next) });
            }
        }
        return (vec![Span { start: 0, end: len, class: "syntax.code" }], state.clone());
    }
    if let State::Comment(_) = state {
        return match line.find("-->") {
            Some(_) => (vec![Span { start: 0, end: len, class: "syntax.comment" }], State::Normal),
            None => (vec![Span { start: 0, end: len, class: "syntax.comment" }], state.clone()),
        };
    }
    for marker in ["```", "~~~"] {
        if trimmed.starts_with(marker) {
            let fence: String = trimmed.chars().take_while(|c| *c == marker.chars().next().unwrap_or('`')).collect();
            let info = trimmed[fence.len()..].trim();
            let name = info.split(|c: char| c.is_whitespace() || c == ',' || c == '{').next().unwrap_or("");
            let inner = if name.is_empty() { None } else { languages.by_name(name.trim_start_matches('.')) };
            return (
                vec![Span { start: 0, end: len, class: "syntax.punctuation" }],
                State::Fence { marker: fence, lang: inner, inner: Box::new(State::Normal) },
            );
        }
    }
    if trimmed.starts_with("<!--") && !trimmed.contains("-->") {
        return (vec![Span { start: 0, end: len, class: "syntax.comment" }], State::Comment(1));
    }
    let _ = lang;
    let mut spans = Vec::new();
    let hashes = trimmed.chars().take_while(|c| *c == '#').count();
    if (1..=6).contains(&hashes) && trimmed.chars().nth(hashes).is_none_or(|c| c == ' ') && indent < 4 {
        spans.push(Span { start: 0, end: len, class: "syntax.heading" });
        return (spans, State::Normal);
    }
    if trimmed.starts_with('>') {
        spans.push(Span { start: 0, end: len, class: "syntax.quote" });
        return (spans, State::Normal);
    }
    if matches!(trimmed, "---" | "***" | "___") {
        spans.push(Span { start: 0, end: len, class: "syntax.punctuation" });
        return (spans, State::Normal);
    }
    let mut i = indent;
    let bullet = trimmed.starts_with("- ") || trimmed.starts_with("* ") || trimmed.starts_with("+ ");
    let digits = trimmed.chars().take_while(char::is_ascii_digit).count();
    let numbered = digits > 0 && matches!(trimmed.chars().nth(digits), Some('.') | Some(')'));
    if bullet || numbered {
        let marker_end = indent + if bullet { 1 } else { digits + 1 };
        spans.push(Span { start: indent, end: marker_end, class: "syntax.list" });
        i = marker_end;
        let rest: String = chars[i..].iter().collect();
        for task in [" [ ]", " [x]", " [X]", " [-]"] {
            if rest.starts_with(task) {
                spans.push(Span { start: i + 1, end: i + 4, class: "syntax.list" });
                i += 4;
                break;
            }
        }
    }
    while i < len {
        let c = chars[i];
        if c == '`' {
            let ticks = chars[i..].iter().take_while(|c| **c == '`').count();
            let close: Vec<char> = std::iter::repeat_n('`', ticks).collect();
            if let Some(end) = (i + ticks..len).find(|at| chars[*at..].starts_with(&close)) {
                spans.push(Span { start: i, end: end + ticks, class: "syntax.code" });
                i = end + ticks;
                continue;
            }
        }
        if (c == '*' || c == '_') && i + 1 < len && chars[i + 1] == c {
            let close = [c, c];
            if let Some(end) = (i + 2..len).find(|at| chars[*at..].starts_with(&close)) {
                spans.push(Span { start: i, end: end + 2, class: "syntax.bold" });
                i = end + 2;
                continue;
            }
        }
        let word_start = i == 0 || !is_ident(chars[i - 1]);
        if (c == '*' || (c == '_' && word_start)) && i + 1 < len && !chars[i + 1].is_whitespace() {
            if let Some(end) = (i + 1..len).find(|at| chars[*at] == c && !chars[*at - 1].is_whitespace()) {
                if end > i + 1 {
                    spans.push(Span { start: i, end: end + 1, class: "syntax.italic" });
                    i = end + 1;
                    continue;
                }
            }
        }
        if c == '[' || (c == '!' && i + 1 < len && chars[i + 1] == '[') {
            let open = if c == '!' { i + 1 } else { i };
            if let Some(close) = (open + 1..len).find(|at| chars[*at] == ']') {
                if close + 1 < len && chars[close + 1] == '(' {
                    if let Some(end) = (close + 2..len).find(|at| chars[*at] == ')') {
                        spans.push(Span { start: i, end: close + 1, class: "syntax.label" });
                        spans.push(Span { start: close + 1, end: end + 1, class: "syntax.link" });
                        i = end + 1;
                        continue;
                    }
                }
                if close + 1 < len && chars[close + 1] == '[' || chars[open + 1..close].starts_with(&['[']) {
                    spans.push(Span { start: i, end: close + 1, class: "syntax.label" });
                    i = close + 1;
                    continue;
                }
            }
        }
        if c == 'h'
            && (chars[i..].starts_with(&['h', 't', 't', 'p', ':'])
                || chars[i..].starts_with(&['h', 't', 't', 'p', 's']))
        {
            let end =
                (i..len).find(|at| chars[*at].is_whitespace() || chars[*at] == ')' || chars[*at] == '>').unwrap_or(len);
            spans.push(Span { start: i, end, class: "syntax.link" });
            i = end;
            continue;
        }
        if c == '|' {
            spans.push(Span { start: i, end: i + 1, class: "syntax.punctuation" });
        }
        i += 1;
    }
    (spans, State::Normal)
}

/// Spans for a whole text, for tests and for previews (the editor caches states per line).
pub fn highlight_lines<'a>(
    languages: &Languages,
    lang: &Language,
    lines: impl Iterator<Item = &'a str>,
) -> Vec<Vec<Span>> {
    let mut state = State::Normal;
    let mut out = Vec::new();
    for line in lines {
        let (spans, next) = highlight(languages, lang, line, &state);
        out.push(spans);
        state = next;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn langs() -> Languages {
        let (languages, errors) = Languages::load(None);
        assert!(errors.is_empty(), "{errors:?}");
        languages
    }

    fn classes(languages: &Languages, name: &str, text: &str) -> Vec<Vec<(String, &'static str)>> {
        let lang = languages.get(languages.by_name(name).unwrap()).unwrap();
        let lines: Vec<&str> = text.lines().collect();
        highlight_lines(languages, lang, lines.iter().copied())
            .into_iter()
            .zip(&lines)
            .map(|(spans, line)| {
                let chars: Vec<char> = line.chars().collect();
                spans.into_iter().map(|span| (chars[span.start..span.end].iter().collect(), span.class)).collect()
            })
            .collect()
    }

    fn has(found: &[Vec<(String, &'static str)>], text: &str, class: &str) -> bool {
        found.iter().flatten().any(|(piece, found_class)| piece == text && *found_class == class)
    }

    #[test]
    fn rust_basics() {
        let languages = langs();
        let found = classes(
            &languages,
            "rust",
            "#[derive(Debug)]\nfn main() -> Result<(), String> {\n    let s = r#\"raw \"q\"\"#; // note\n    println!(\"{}\\n\", 'x');\n    /* a\n    b */ x.len() + 0x1F\n}\nfn f<'a>(x: &'a str) {}",
        );
        assert!(has(&found, "#[derive(Debug)]", "syntax.attribute"));
        assert!(has(&found, "fn", "syntax.keyword"));
        assert!(has(&found, "main", "syntax.function"));
        assert!(has(&found, "Result", "syntax.type"));
        assert!(has(&found, "r#\"raw \"q\"\"#", "syntax.string"));
        assert!(has(&found, "// note", "syntax.comment"));
        assert!(has(&found, "println!", "syntax.macro"));
        assert!(has(&found, "\\n", "syntax.escape"));
        assert!(has(&found, "    b */", "syntax.comment"));
        assert!(has(&found, "len", "syntax.function"));
        assert!(has(&found, "0x1F", "syntax.number"));
        assert!(has(&found, "'a", "syntax.label"));
    }

    #[test]
    fn python_strings_span_lines() {
        let languages = langs();
        let found =
            classes(&languages, "python", "@cached\ndef f():\n    s = f\"\"\"a\n  b\"\"\" # c\n    return None");
        assert!(has(&found, "@cached", "syntax.attribute"));
        assert!(has(&found, "  b\"\"\"", "syntax.string"));
        assert!(has(&found, "# c", "syntax.comment"));
        assert!(has(&found, "None", "syntax.constant"));
    }

    #[test]
    fn markdown_fences_use_the_inner_language() {
        let languages = langs();
        let found =
            classes(&languages, "markdown", "# Title\nSome `code` and **bold**.\n```rust\nlet x = 1;\n```\n- [ ] task");
        assert!(has(&found, "# Title", "syntax.heading"));
        assert!(has(&found, "`code`", "syntax.code"));
        assert!(has(&found, "**bold**", "syntax.bold"));
        assert!(has(&found, "let", "syntax.keyword"));
        assert!(has(&found, "-", "syntax.list"));
    }

    #[test]
    fn detection() {
        let languages = langs();
        let name = |path: &str, first: &str| {
            languages.detect(Some(Path::new(path)), first).map(|index| languages.list[index].name.clone())
        };
        assert_eq!(name("a/main.rs", "").as_deref(), Some("rust"));
        assert_eq!(name("Makefile", "").as_deref(), Some("make"));
        assert_eq!(name("script", "#!/usr/bin/env python3").as_deref(), Some("python"));
        assert_eq!(name("run", "#!/bin/zsh").as_deref(), Some("shell"));
        assert_eq!(name(".zshrc", "").as_deref(), Some("shell"));
        assert_eq!(name("notes.weird", ""), None);
    }

    #[test]
    fn user_languages_extend_and_override() {
        let table: DocumentMut =
            "[rust]\nrun = \"cargo test\"\n[mylang]\nextensions = [\"my\"]\ncomment = \";\"\nkeywords = [\"yo\"]\n"
                .parse()
                .unwrap();
        let (languages, errors) = Languages::load(Some(table.as_table()));
        assert!(errors.is_empty(), "{errors:?}");
        let rust = &languages.list[languages.by_name("rust").unwrap()];
        assert_eq!(rust.run.as_deref(), Some("cargo test"));
        assert!(rust.keywords.contains("fn"), "the rest is kept");
        assert!(languages.detect(Some(Path::new("x.my")), "").is_some());
        let bad: DocumentMut = "[rust]\nbogus = 1\n".parse().unwrap();
        assert_eq!(Languages::load(Some(bad.as_table())).1.len(), 1);
    }
}
