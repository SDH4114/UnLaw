//! Small UI state: the one-line editor used by prompts and pickers, prompts, popups, completion.

use crate::keys::{Code, Key};
use crate::text::{byte_at, char_len, Pos};

/// A single editable line with a cursor (in chars).
#[derive(Clone, Debug, Default)]
pub struct LineEdit {
    pub text: String,
    pub cursor: usize,
}

impl LineEdit {
    pub fn new(text: &str) -> Self {
        LineEdit { text: text.to_string(), cursor: char_len(text) }
    }

    pub fn set(&mut self, text: &str) {
        self.text = text.to_string();
        self.cursor = char_len(text);
    }

    pub fn insert(&mut self, text: &str) {
        let at = byte_at(&self.text, self.cursor);
        let clean: String = text.chars().filter(|c| *c != '\n' && *c != '\r').collect();
        self.text.insert_str(at, &clean);
        self.cursor += char_len(&clean);
    }

    /// Handles an editing key; returns false for keys it does not use.
    pub fn handle(&mut self, key: Key) -> bool {
        let len = char_len(&self.text);
        match (key.code, key.ctrl, key.alt) {
            (Code::Char(c), false, false) => self.insert(&c.to_string()),
            (Code::Backspace, _, false) | (Code::Char('h'), true, false) => {
                if self.cursor > 0 {
                    let start = byte_at(&self.text, self.cursor - 1);
                    let end = byte_at(&self.text, self.cursor);
                    self.text.replace_range(start..end, "");
                    self.cursor -= 1;
                }
            }
            (Code::Delete, _, _) | (Code::Char('d'), true, false) => {
                if self.cursor < len {
                    let start = byte_at(&self.text, self.cursor);
                    let end = byte_at(&self.text, self.cursor + 1);
                    self.text.replace_range(start..end, "");
                }
            }
            (Code::Left, false, false) | (Code::Char('b'), true, false) => self.cursor = self.cursor.saturating_sub(1),
            (Code::Right, false, false) | (Code::Char('f'), true, false) => self.cursor = (self.cursor + 1).min(len),
            (Code::Home, _, _) | (Code::Char('a'), true, false) => self.cursor = 0,
            (Code::End, _, _) | (Code::Char('e'), true, false) => self.cursor = len,
            (Code::Char('u'), true, false) => {
                let end = byte_at(&self.text, self.cursor);
                self.text.replace_range(..end, "");
                self.cursor = 0;
            }
            (Code::Char('k'), true, false) => {
                let start = byte_at(&self.text, self.cursor);
                self.text.truncate(start);
            }
            (Code::Char('w'), true, false) | (Code::Backspace, _, true) => {
                let chars: Vec<char> = self.text.chars().collect();
                let mut start = self.cursor;
                while start > 0 && chars[start - 1] == ' ' {
                    start -= 1;
                }
                let word = |c: char| c.is_alphanumeric() || c == '_';
                if start > 0 && word(chars[start - 1]) {
                    while start > 0 && word(chars[start - 1]) {
                        start -= 1;
                    }
                } else {
                    start = start.saturating_sub(1);
                }
                let (from, to) = (byte_at(&self.text, start), byte_at(&self.text, self.cursor));
                self.text.replace_range(from..to, "");
                self.cursor = start;
            }
            (Code::Left, _, true) | (Code::Char('b'), false, true) | (Code::Left, true, false) => {
                let chars: Vec<char> = self.text.chars().collect();
                let mut at = self.cursor;
                while at > 0 && !chars[at - 1].is_alphanumeric() {
                    at -= 1;
                }
                while at > 0 && chars[at - 1].is_alphanumeric() {
                    at -= 1;
                }
                self.cursor = at;
            }
            (Code::Right, _, true) | (Code::Char('f'), false, true) | (Code::Right, true, false) => {
                let chars: Vec<char> = self.text.chars().collect();
                let mut at = self.cursor;
                while at < chars.len() && !chars[at].is_alphanumeric() {
                    at += 1;
                }
                while at < chars.len() && chars[at].is_alphanumeric() {
                    at += 1;
                }
                self.cursor = at;
            }
            _ => return false,
        }
        true
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum InputAction {
    LspRename,
    GitCommit,
    Ask { with_selection: Option<String> },
    AiEdit { doc: usize, start: Pos, end: Pos, version: i32, text: String },
    UlArgs(String),
    NewFile(std::path::PathBuf),
    RenameFile(std::path::PathBuf),
    Run,
    SaveAs(usize),
    Replace { pattern: String },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ConfirmAction {
    QuitAll,
    DeleteFile(std::path::PathBuf),
    CloseBuffer(usize),
    Reload(usize),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PromptKind {
    Command,
    Search { forward: bool, origin: Pos, scroll: usize },
    Input { title: String, action: InputAction },
    Confirm { question: String, action: ConfirmAction },
}

#[derive(Clone, Debug)]
pub struct Prompt {
    pub kind: PromptKind,
    pub line: LineEdit,
    /// Position in the history while browsing it with up/down (None: editing).
    pub history: Option<usize>,
    pub typed: String,
    pub completions: Vec<String>,
    pub completion: Option<usize>,
    pub completion_base: String,
}

impl Prompt {
    pub fn new(kind: PromptKind, text: &str) -> Self {
        Prompt {
            kind,
            line: LineEdit::new(text),
            history: None,
            typed: String::new(),
            completions: Vec::new(),
            completion: None,
            completion_base: String::new(),
        }
    }

    pub fn prefix(&self) -> String {
        match &self.kind {
            PromptKind::Command => ":".into(),
            PromptKind::Search { forward: true, .. } => "/".into(),
            PromptKind::Search { forward: false, .. } => "?".into(),
            PromptKind::Input { title, .. } => format!("{title}: "),
            PromptKind::Confirm { question, .. } => format!("{question} [y/N] "),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PopupKind {
    Hover,
    Info,
    Signature,
}

/// A floating box of text near the cursor (hover, diagnostics) or centered (info).
#[derive(Clone, Debug)]
pub struct Popup {
    pub kind: PopupKind,
    pub title: String,
    pub lines: Vec<String>,
    pub scroll: usize,
    pub markdown: bool,
}

impl Popup {
    pub fn new(kind: PopupKind, title: &str, text: &str, markdown: bool) -> Self {
        let mut lines: Vec<String> = text.lines().map(|line| line.trim_end().to_string()).collect();
        while lines.last().is_some_and(String::is_empty) {
            lines.pop();
        }
        while lines.first().is_some_and(String::is_empty) {
            lines.remove(0);
        }
        Popup { kind, title: title.to_string(), lines, scroll: 0, markdown }
    }
}

#[derive(Clone, Debug, Default)]
pub struct CompletionItem {
    pub label: String,
    pub kind: String,
    pub detail: String,
    pub insert: String,
    pub filter: String,
    pub sort: String,
    /// The LSP's own replacement range and text, when it gives one.
    pub edit: Option<(Pos, Pos, String)>,
    pub additional: Vec<(Pos, Pos, String)>,
    pub documentation: String,
    pub preselect: bool,
}

#[derive(Clone, Debug)]
pub struct Completion {
    pub doc: usize,
    pub items: Vec<CompletionItem>,
    pub shown: Vec<usize>,
    pub selected: Option<usize>,
    pub start: Pos,
    pub from_lsp: bool,
    pub offset: usize,
}

impl Completion {
    /// Re-filters by the prefix typed since `start`; returns false when nothing matches.
    pub fn filter(&mut self, prefix: &str) -> bool {
        let mut scored: Vec<(i64, usize)> = self
            .items
            .iter()
            .enumerate()
            .filter_map(|(index, item)| {
                let text = if item.filter.is_empty() { &item.label } else { &item.filter };
                crate::fuzzy::score(prefix, text).map(|(score, _)| (score, index))
            })
            .collect();
        scored.sort_by(|a, b| {
            b.0.cmp(&a.0)
                .then_with(|| self.items[a.1].sort.cmp(&self.items[b.1].sort))
                .then_with(|| self.items[a.1].label.len().cmp(&self.items[b.1].label.len()))
        });
        // An exact, complete word is not worth a menu.
        if scored.len() == 1 && self.items[scored[0].1].label == prefix {
            return false;
        }
        self.shown = scored.into_iter().map(|(_, index)| index).take(200).collect();
        if self.selected.is_some_and(|selected| selected >= self.shown.len()) {
            self.selected = None;
        }
        self.offset = 0;
        !self.shown.is_empty()
    }

    pub fn selected_item(&self) -> Option<&CompletionItem> {
        self.selected.and_then(|index| self.shown.get(index)).map(|index| &self.items[*index])
    }

    pub fn step(&mut self, delta: isize) {
        if self.shown.is_empty() {
            return;
        }
        let len = self.shown.len() as isize;
        self.selected = Some(match self.selected {
            None if delta > 0 => 0,
            None => (len - 1) as usize,
            Some(index) => (index as isize + delta).rem_euclid(len) as usize,
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn line_edit_keys() {
        let mut line = LineEdit::new("hello world");
        line.handle(Key::ctrl('w'));
        assert_eq!(line.text, "hello ");
        line.handle(Key::ctrl('a'));
        line.insert("¡");
        assert_eq!(line.text, "¡hello ");
        line.handle(Key::ctrl('e'));
        line.handle(Key::plain(Code::Backspace));
        assert_eq!(line.text, "¡hello");
        line.handle(Key::ctrl('u'));
        assert_eq!(line.text, "");
    }
}
