//! Fuzzy pickers: files, grep, buffers, recent files, commands, key bindings,
//! themes, languages, ul commands, LSP locations and symbols, diagnostics.

use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;

use crate::document::display_path;
use crate::editor::{Editor, Event};
use crate::keys::{Code, Key};
use crate::text::Pos;
use crate::widgets::LineEdit;

static GENERATION: AtomicU64 = AtomicU64::new(1);

#[derive(Clone, Debug)]
pub enum Data {
    File(PathBuf),
    Location(PathBuf, Pos),
    Buffer(usize),
    Command(String),
    Theme(String),
    Language(usize),
    Ul(String),
    Keys(String),
    CodeAction(serde_json::Value, usize),
    Line(usize),
}

#[derive(Clone, Debug)]
pub struct Item {
    pub label: String,
    pub detail: String,
    pub data: Data,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Files,
    Grep,
    Static,
}

#[derive(Clone, Debug)]
pub struct Picker {
    pub title: String,
    pub kind: Kind,
    pub input: LineEdit,
    pub items: Vec<Item>,
    /// (item index, match positions in the label)
    pub matches: Vec<(usize, Vec<usize>)>,
    pub selected: usize,
    pub offset: usize,
    pub generation: u64,
    pub loading: bool,
    pub preview: bool,
    /// The theme active before a theme picker previewed others.
    pub restore_theme: Option<String>,
    /// The previewed file's lines, read once per selection.
    pub cache: Option<(PathBuf, Vec<String>)>,
    last_query: String,
}

impl Picker {
    pub fn new(title: &str, kind: Kind, items: Vec<Item>) -> Self {
        let mut picker = Picker {
            title: title.to_string(),
            kind,
            input: LineEdit::default(),
            items,
            matches: Vec::new(),
            selected: 0,
            offset: 0,
            generation: GENERATION.fetch_add(1, Ordering::Relaxed),
            loading: false,
            preview: true,
            restore_theme: None,
            cache: None,
            last_query: String::from("\u{0}"),
        };
        picker.filter();
        picker
    }

    pub fn filter(&mut self) {
        let query = self.input.text.clone();
        if self.kind == Kind::Grep {
            // Grep results are already filtered by ripgrep; keep their order.
            self.matches = (0..self.items.len()).map(|index| (index, Vec::new())).collect();
        } else if query.trim().is_empty() {
            self.matches = (0..self.items.len()).map(|index| (index, Vec::new())).collect();
        } else {
            let mut scored: Vec<(i64, usize, Vec<usize>)> = self
                .items
                .iter()
                .enumerate()
                .filter_map(|(index, item)| {
                    crate::fuzzy::score(&query, &item.label).map(|(score, positions)| (score, index, positions))
                })
                .collect();
            scored.sort_by(|a, b| b.0.cmp(&a.0).then(a.1.cmp(&b.1)));
            self.matches = scored.into_iter().map(|(_, index, positions)| (index, positions)).collect();
        }
        if query != self.last_query {
            self.selected = 0;
            self.offset = 0;
        }
        self.last_query = query;
        self.selected = self.selected.min(self.matches.len().saturating_sub(1));
    }

    pub fn current(&self) -> Option<&Item> {
        self.matches.get(self.selected).map(|(index, _)| &self.items[*index])
    }
}

fn open(ed: &mut Editor, picker: Picker) {
    if let Some(previous) = ed.picker.take() {
        ed.last_picker = Some(previous);
    }
    ed.picker = Some(picker);
}

/// The project root: the nearest folder with .git above the current file or the cwd.
pub fn project_root(ed: &Editor) -> PathBuf {
    let start = ed.cwd.clone();
    let mut dir = start.as_path();
    loop {
        if dir.join(".git").exists() {
            return dir.to_path_buf();
        }
        match dir.parent() {
            Some(parent) => dir = parent,
            None => return start,
        }
    }
}

const SKIP_DIRS: &[&str] = &[
    "node_modules",
    "target",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    ".next",
    ".cache",
    ".DS_Store",
    ".idea",
    ".tox",
];

fn walk(root: &Path, hidden: bool, out: &mut Vec<PathBuf>, limit: usize) {
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = std::fs::read_dir(&dir) else {
            continue;
        };
        let mut entries: Vec<_> = entries.filter_map(Result::ok).collect();
        entries.sort_by_key(|entry| entry.file_name());
        for entry in entries {
            let name = entry.file_name().to_string_lossy().into_owned();
            if (!hidden && name.starts_with('.')) || SKIP_DIRS.contains(&name.as_str()) {
                continue;
            }
            let Ok(kind) = entry.file_type() else {
                continue;
            };
            if kind.is_dir() {
                stack.push(entry.path());
            } else {
                out.push(entry.path());
                if out.len() >= limit {
                    return;
                }
            }
        }
    }
}

/// Files of the project: `git ls-files` when in a repository (respects .gitignore), else a walk.
fn list_files(root: &Path, hidden: bool, changed_only: bool) -> Vec<PathBuf> {
    if root.join(".git").exists() || changed_only {
        let args: &[&str] = if changed_only {
            &["status", "--porcelain", "--untracked-files=all"]
        } else {
            &["ls-files", "--cached", "--others", "--exclude-standard"]
        };
        if let Ok(output) = Command::new("git").args(args).current_dir(root).stderr(Stdio::null()).output() {
            if output.status.success() {
                let text = String::from_utf8_lossy(&output.stdout);
                let mut files: Vec<PathBuf> = text
                    .lines()
                    .map(|line| {
                        if changed_only {
                            line.get(3..).unwrap_or("").rsplit(" -> ").next().unwrap_or("")
                        } else {
                            line
                        }
                    })
                    .filter(|line| !line.is_empty())
                    .filter(|line| {
                        hidden || changed_only || !line.split('/').any(|part| part.starts_with('.') && part.len() > 1)
                    })
                    .map(|line| root.join(line.trim_matches('"')))
                    .filter(|path| changed_only || path.is_file())
                    .collect();
                files.dedup();
                return files;
            }
        }
    }
    let mut files = Vec::new();
    walk(root, hidden, &mut files, 100_000);
    files
}

pub fn open_files(ed: &mut Editor, changed_only: bool) {
    let root = project_root(ed);
    let title = if changed_only { "Changed files" } else { "Files" };
    let mut picker = Picker::new(title, Kind::Files, Vec::new());
    picker.loading = true;
    let generation = picker.generation;
    let tx = ed.tx.clone();
    let hidden = ed.options.hidden_files;
    thread::spawn(move || {
        let files = list_files(&root, hidden, changed_only);
        let _ = tx.send(Event::Files(generation, files, true));
    });
    open(ed, picker);
}

pub fn open_recent(ed: &mut Editor) {
    let items: Vec<Item> = ed
        .persisted
        .recent
        .iter()
        .rev()
        .map(PathBuf::from)
        .filter(|path| path.exists())
        .map(|path| Item { label: display_path(&path), detail: String::new(), data: Data::File(path) })
        .collect();
    open(ed, Picker::new("Recent files", Kind::Static, items));
}

pub fn open_buffers(ed: &mut Editor) {
    let current = ed.view().doc;
    let mut items: Vec<Item> = ed
        .buffers
        .iter()
        .enumerate()
        .map(|(index, id)| {
            let doc = &ed.docs[id];
            let flag = if doc.modified() { " [+]" } else { "" };
            Item {
                label: format!("{} {}{flag}", index + 1, doc.title()),
                detail: ed.language_name(doc),
                data: Data::Buffer(*id),
            }
        })
        .collect();
    // The current buffer goes last so Enter on the first item switches to another one.
    if let Some(position) = items.iter().position(|item| matches!(item.data, Data::Buffer(id) if id == current)) {
        let item = items.remove(position);
        items.push(item);
    }
    open(ed, Picker::new("Buffers", Kind::Static, items));
}

pub fn open_commands(ed: &mut Editor) {
    let mut items: Vec<Item> = crate::commands::COMMANDS
        .iter()
        .map(|(name, description)| Item {
            label: format!("{name} — {description}"),
            detail: String::new(),
            data: Data::Command(name.to_string()),
        })
        .collect();
    // Show the key for each command where there is one.
    let bindings = ed.keymap.all();
    for item in &mut items {
        if let Data::Command(name) = &item.data {
            if let Some(binding) = ed
                .keymap
                .normal
                .iter()
                .find(|binding| matches!(binding.actions.first(), Some(crate::config::Action::Command(command, _)) if command == name))
            {
                item.detail = crate::keys::notation(&binding.keys).replace(&crate::keys::notation(&ed.keymap.leader), "␣");
            }
        }
    }
    let _ = bindings;
    open(ed, Picker::new("Commands", Kind::Static, items));
}

pub fn open_keymaps(ed: &mut Editor) {
    let leader = crate::keys::notation(&ed.keymap.leader);
    let mut items: Vec<Item> = ed
        .keymap
        .all()
        .into_iter()
        .map(|(mode, keys, description)| Item {
            label: format!("{keys:<16} {description}"),
            detail: mode.to_string(),
            data: Data::Keys(keys.replace("<leader>", &leader)),
        })
        .collect();
    for (keys, description) in crate::standard::KEYS {
        items.push(Item { label: format!("{keys:<16} {description}"), detail: "standard".into(), data: Data::Keys(String::new()) });
    }
    for (keys, description) in crate::help::VIM_KEYS {
        items.push(Item {
            label: format!("{keys:<16} {description}"),
            detail: "vim".into(),
            data: Data::Keys(String::new()),
        });
    }
    open(ed, Picker::new("Key bindings", Kind::Static, items));
}

pub fn open_themes(ed: &mut Editor) {
    let current = ed.theme.name.clone();
    let mut names = ed.themes.names();
    names.sort();
    let items: Vec<Item> = names
        .into_iter()
        .map(|name| Item {
            label: name.clone(),
            detail: if name == current { "current".into() } else { String::new() },
            data: Data::Theme(name),
        })
        .collect();
    let mut picker = Picker::new("Themes (preview while moving)", Kind::Static, items);
    picker.restore_theme = Some(current);
    picker.preview = false;
    open(ed, picker);
}

pub fn open_languages(ed: &mut Editor) {
    let items: Vec<Item> = ed
        .languages
        .list
        .iter()
        .enumerate()
        .map(|(index, lang)| Item {
            label: lang.name.clone(),
            detail: lang.extensions.join(" "),
            data: Data::Language(index),
        })
        .collect();
    let mut picker = Picker::new("Language", Kind::Static, items);
    picker.preview = false;
    open(ed, picker);
}

pub fn open_ul(ed: &mut Editor) {
    if ed.ul_commands.is_empty() {
        ed.ul_commands = crate::ul::commands();
    }
    if ed.ul_commands.is_empty() {
        ed.error("ul was not found (ULE_UL or ul on PATH)");
        return;
    }
    let items: Vec<Item> = ed
        .ul_commands
        .iter()
        .map(|(name, description)| Item {
            label: format!("{name:<12} {description}"),
            detail: String::new(),
            data: Data::Ul(name.clone()),
        })
        .collect();
    open(ed, Picker::new("ul commands (Enter: arguments, Ctrl-Enter: run in the terminal)", Kind::Static, items));
}

pub fn open_locations(ed: &mut Editor, title: &str, locations: Vec<(PathBuf, Pos, String)>) {
    let items: Vec<Item> = locations
        .into_iter()
        .map(|(path, pos, text)| Item {
            label: format!("{}:{}:{}  {}", display_path(&path), pos.line + 1, pos.col + 1, text.trim()),
            detail: String::new(),
            data: Data::Location(path, pos),
        })
        .collect();
    open(ed, Picker::new(title, Kind::Static, items));
}

pub fn open_lines(ed: &mut Editor, title: &str, lines: Vec<(usize, String)>) {
    let items: Vec<Item> = lines
        .into_iter()
        .map(|(line, text)| Item {
            label: format!("{:>5}  {}", line + 1, text.trim_end()),
            detail: String::new(),
            data: Data::Line(line),
        })
        .collect();
    open(ed, Picker::new(title, Kind::Static, items));
}

pub fn open_items(ed: &mut Editor, title: &str, items: Vec<Item>) {
    open(ed, Picker::new(title, Kind::Static, items));
}

pub fn open_diagnostics(ed: &mut Editor) {
    let mut items = Vec::new();
    let mut docs: Vec<&crate::document::Document> = ed.docs.values().collect();
    docs.sort_by_key(|doc| doc.title());
    let current = ed.view().doc;
    docs.sort_by_key(|doc| doc.id != current);
    for doc in docs {
        let Some(path) = &doc.path else {
            continue;
        };
        let mut diagnostics = doc.diagnostics.clone();
        diagnostics.sort_by_key(|diagnostic| (diagnostic.severity, diagnostic.start));
        for diagnostic in diagnostics {
            let level = match diagnostic.severity {
                1 => "error",
                2 => "warning",
                3 => "info",
                _ => "hint",
            };
            items.push(Item {
                label: format!(
                    "{}:{}  {}",
                    doc.file_name(),
                    diagnostic.start.line + 1,
                    diagnostic.message.lines().next().unwrap_or("")
                ),
                detail: level.into(),
                data: Data::Location(path.clone(), diagnostic.start),
            });
        }
    }
    if items.is_empty() {
        ed.info("no diagnostics");
        return;
    }
    open(ed, Picker::new("Diagnostics", Kind::Static, items));
}

pub fn open_grep(ed: &mut Editor, query: &str) {
    let mut picker = Picker::new("Grep (regex; smart case)", Kind::Grep, Vec::new());
    picker.input.set(query);
    open(ed, picker);
    refresh(ed);
}

/// Called after the query changes: re-filters, or restarts the grep search.
pub fn refresh(ed: &mut Editor) {
    let Some(picker) = ed.picker.as_mut() else {
        return;
    };
    if picker.kind != Kind::Grep {
        picker.filter();
        return;
    }
    let query = picker.input.text.clone();
    picker.generation = GENERATION.fetch_add(1, Ordering::Relaxed);
    picker.items.clear();
    picker.filter();
    if query.chars().count() < 2 {
        picker.loading = false;
        return;
    }
    picker.loading = true;
    let generation = picker.generation;
    let root = project_root(ed);
    let tx = ed.tx.clone();
    let hidden = ed.options.hidden_files;
    thread::spawn(move || grep(&root, &query, hidden, generation, &tx));
}

fn grep(root: &Path, query: &str, hidden: bool, generation: u64, tx: &std::sync::mpsc::Sender<Event>) {
    let send = |hits: Vec<(PathBuf, usize, usize, String)>, done: bool| {
        let _ = tx.send(Event::Grep(generation, hits, done));
    };
    let rg = Command::new("rg")
        .args(["--vimgrep", "--smart-case", "--max-columns", "300", "--max-count", "200", "--no-heading"])
        .args(if hidden { vec!["--hidden"] } else { vec![] })
        .arg("--")
        .arg(query)
        .current_dir(root)
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn();
    if let Ok(mut child) = rg {
        use std::io::BufRead;
        let stdout = child.stdout.take().expect("piped stdout");
        let mut batch = Vec::new();
        let mut total = 0;
        for line in std::io::BufReader::new(stdout).lines().map_while(Result::ok) {
            // A newer search started: stop this one.
            if GENERATION.load(Ordering::Relaxed) > generation + 1 {
                let _ = child.kill();
                break;
            }
            if let Some(hit) = parse_vimgrep(root, &line) {
                batch.push(hit);
                total += 1;
            }
            if batch.len() >= 200 {
                send(std::mem::take(&mut batch), false);
            }
            if total >= 5000 {
                let _ = child.kill();
                break;
            }
        }
        let _ = child.wait();
        send(batch, true);
        return;
    }
    // No ripgrep: search the project's files here.
    let regex = match regex::RegexBuilder::new(query).case_insensitive(!query.chars().any(char::is_uppercase)).build() {
        Ok(regex) => regex,
        Err(_) => match regex::RegexBuilder::new(&regex::escape(query)).case_insensitive(true).build() {
            Ok(regex) => regex,
            Err(_) => return send(Vec::new(), true),
        },
    };
    let mut hits = Vec::new();
    for path in list_files(root, hidden, false) {
        let Ok(text) = std::fs::read_to_string(&path) else {
            continue;
        };
        for (number, line) in text.lines().enumerate() {
            if let Some(found) = regex.find(line) {
                let col = line[..found.start()].chars().count();
                hits.push((path.clone(), number, col, line.chars().take(300).collect()));
                if hits.len() >= 2000 {
                    return send(hits, true);
                }
            }
        }
        if hits.len() >= 200 {
            send(std::mem::take(&mut hits), false);
        }
    }
    send(hits, true);
}

fn parse_vimgrep(root: &Path, line: &str) -> Option<(PathBuf, usize, usize, String)> {
    let mut parts = line.splitn(4, ':');
    let path = parts.next()?;
    let number = parts.next()?.parse::<usize>().ok()?;
    let column = parts.next()?.parse::<usize>().ok()?;
    let text = parts.next().unwrap_or("").to_string();
    // ripgrep reports byte columns; convert to chars.
    let col = text.get(..column.saturating_sub(1)).map_or(column.saturating_sub(1), |prefix| prefix.chars().count());
    Some((root.join(path), number.saturating_sub(1), col, text))
}

/// Results from the background threads.
pub fn on_event(ed: &mut Editor, event: Event) {
    let Some(picker) = ed.picker.as_mut() else {
        return;
    };
    match event {
        Event::Files(generation, files, done) if generation == picker.generation => {
            let root = std::env::current_dir().unwrap_or_default();
            picker.items.extend(files.into_iter().map(|path| {
                let label = path
                    .strip_prefix(&root)
                    .map_or_else(|_| display_path(&path), |relative| relative.display().to_string());
                Item { label, detail: String::new(), data: Data::File(path) }
            }));
            picker.loading = !done;
            picker.filter();
        }
        Event::Grep(generation, hits, done) if generation == picker.generation => {
            let root = std::env::current_dir().unwrap_or_default();
            picker.items.extend(hits.into_iter().map(|(path, line, col, text)| {
                let name = path
                    .strip_prefix(&root)
                    .map_or_else(|_| display_path(&path), |relative| relative.display().to_string());
                Item {
                    label: format!("{name}:{}  {}", line + 1, text.trim()),
                    detail: String::new(),
                    data: Data::Location(path, Pos::new(line, col)),
                }
            }));
            picker.loading = !done;
            picker.filter();
        }
        _ => {}
    }
}

pub fn key(ed: &mut Editor, key: Key) {
    let Some(picker) = ed.picker.as_mut() else {
        return;
    };
    let visible = (ed.size.1 as usize).saturating_sub(8).max(3) * 3 / 4;
    match (key.code, key.ctrl) {
        _ if key.is_esc() => {
            let picker = ed.picker.take();
            if let Some(theme) = picker.as_ref().and_then(|picker| picker.restore_theme.clone()) {
                let _ = crate::ex::apply_theme(ed, &theme);
            }
            ed.last_picker = picker;
            return;
        }
        (Code::Enter, _) => {
            let item = picker.current().cloned();
            let ctrl = key.ctrl || key.alt;
            let picker = ed.picker.take();
            ed.last_picker = picker;
            if let Some(item) = item {
                if let Err(error) = select(ed, item, ctrl) {
                    ed.error(error);
                }
            }
            return;
        }
        (Code::Down, _) | (Code::Char('n'), true) | (Code::Char('j'), true) | (Code::Tab, false) => {
            if !picker.matches.is_empty() {
                picker.selected = (picker.selected + 1) % picker.matches.len();
            }
        }
        (Code::Up, _) | (Code::Char('p'), true) | (Code::Char('k'), true) | (Code::BackTab, _) => {
            if !picker.matches.is_empty() {
                picker.selected = (picker.selected + picker.matches.len() - 1) % picker.matches.len();
            }
        }
        (Code::PageDown, _) | (Code::Char('d'), true) => {
            picker.selected = (picker.selected + visible).min(picker.matches.len().saturating_sub(1));
        }
        (Code::PageUp, _) | (Code::Char('u'), true) if key.code == Code::PageUp || picker.input.text.is_empty() => {
            picker.selected = picker.selected.saturating_sub(visible);
        }
        (Code::Char('t'), true) => picker.preview = !picker.preview,
        (Code::Char('v'), true) | (Code::Char('s'), true) => {
            // Open in a split.
            let vertical = key.code == Code::Char('v');
            let item = picker.current().cloned();
            let picker = ed.picker.take();
            ed.last_picker = picker;
            if let Some(item) = item {
                ed.split(vertical);
                if let Err(error) = select(ed, item, false) {
                    ed.error(error);
                }
            }
            return;
        }
        _ => {
            if picker.input.handle(key) {
                refresh(ed);
            }
        }
    }
    // Theme previews follow the selection.
    if let Some(picker) = ed.picker.as_ref() {
        if picker.restore_theme.is_some() {
            if let Some(Data::Theme(name)) = picker.current().map(|item| item.data.clone()) {
                let _ = crate::ex::apply_theme(ed, &name);
            }
        }
    }
}

pub fn paste(ed: &mut Editor, text: &str) {
    if let Some(picker) = ed.picker.as_mut() {
        picker.input.insert(text.lines().next().unwrap_or(""));
    }
    refresh(ed);
}

fn goto_location(ed: &mut Editor, path: &Path, pos: Pos) -> Result<(), String> {
    ed.push_jump();
    ed.open(path)?;
    ed.set_cursor(pos);
    ed.align_cursor('z');
    Ok(())
}

fn select(ed: &mut Editor, item: Item, alternate: bool) -> Result<(), String> {
    match item.data {
        Data::File(path) => {
            ed.push_jump();
            ed.open(&path)?;
        }
        Data::Location(path, pos) => goto_location(ed, &path, pos)?,
        Data::Line(line) => {
            ed.push_jump();
            let col = ed.doc().text.first_non_blank(line);
            ed.set_cursor(Pos::new(line, col));
            ed.align_cursor('z');
        }
        Data::Buffer(id) => ed.show_doc(id),
        Data::Command(name) => crate::commands::run(ed, &name, &[], None, None)?,
        Data::Theme(name) => {
            crate::ex::apply_theme(ed, &name)?;
            ed.info(format!("theme {name} (theme = \"{name}\" in ule.toml keeps it)"));
        }
        Data::Language(index) => {
            let doc = ed.view().doc;
            ed.lsp_close(doc);
            ed.doc_mut().set_language(Some(index));
            ed.lsp_open(doc);
        }
        Data::Ul(name) => {
            if alternate {
                crate::ul::run(ed, &name, true)?;
            } else {
                ed.prompt = Some(crate::widgets::Prompt::new(
                    crate::widgets::PromptKind::Input {
                        title: format!("ul {name}"),
                        action: crate::widgets::InputAction::UlArgs(name),
                    },
                    "",
                ));
            }
        }
        Data::Keys(keys) => {
            if !keys.is_empty() {
                ed.info(format!("keys: {keys}"));
            }
        }
        Data::CodeAction(action, client) => crate::lsp::apply_code_action(ed, client, action)?,
    }
    Ok(())
}

/// Lines to preview for the selected item: (path for highlighting, first line, highlighted line).
pub fn preview_target(item: &Item, ed: &Editor) -> Option<(PathBuf, usize, Option<usize>)> {
    match &item.data {
        Data::File(path) => Some((path.clone(), 0, None)),
        Data::Location(path, pos) => Some((path.clone(), pos.line, Some(pos.line))),
        Data::Buffer(id) => ed.docs.get(id).and_then(|doc| doc.path.clone()).map(|path| (path, 0, None)),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn vimgrep_lines() {
        let root = Path::new("/p");
        assert_eq!(
            parse_vimgrep(root, "src/a.rs:12:5:    let x = 1;"),
            Some((PathBuf::from("/p/src/a.rs"), 11, 4, "    let x = 1;".into()))
        );
        assert_eq!(parse_vimgrep(root, "a:b"), None);
    }

    #[test]
    fn filters_by_fuzzy_score() {
        let items = ["src/editor.rs", "src/render.rs", "README.md"]
            .iter()
            .map(|name| Item { label: name.to_string(), detail: String::new(), data: Data::File(PathBuf::from(name)) })
            .collect();
        let mut picker = Picker::new("t", Kind::Static, items);
        assert_eq!(picker.matches.len(), 3);
        picker.input.set("rend");
        picker.filter();
        assert_eq!(picker.current().map(|item| item.label.as_str()), Some("src/render.rs"));
    }
}
