//! The text of a document: a vector of lines, positions in characters.
//!
//! Lines never contain '\n'. A position's `col` counts chars, so every
//! operation converts to bytes at the edge. Files of a few hundred thousand
//! lines stay fast because edits only touch the lines they change.

use std::cmp::Ordering;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]
pub struct Pos {
    pub line: usize,
    pub col: usize,
}

impl Pos {
    pub const fn new(line: usize, col: usize) -> Self {
        Pos { line, col }
    }
}

impl PartialOrd for Pos {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for Pos {
    fn cmp(&self, other: &Self) -> Ordering {
        (self.line, self.col).cmp(&(other.line, other.col))
    }
}

/// Byte offset of char `col` in `line` (the end when `col` is past it).
pub fn byte_at(line: &str, col: usize) -> usize {
    line.char_indices().nth(col).map_or(line.len(), |(index, _)| index)
}

pub fn char_len(text: &str) -> usize {
    text.chars().count()
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CharClass {
    Space,
    Word,
    Punct,
    Newline,
}

pub fn is_word(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
}

pub fn class(c: char) -> CharClass {
    if c == '\n' {
        CharClass::Newline
    } else if c.is_whitespace() {
        CharClass::Space
    } else if is_word(c) {
        CharClass::Word
    } else {
        CharClass::Punct
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Text {
    lines: Vec<String>,
}

impl Default for Text {
    fn default() -> Self {
        Text { lines: vec![String::new()] }
    }
}

impl Text {
    pub fn new(content: &str) -> Self {
        let mut lines: Vec<String> = content.split('\n').map(str::to_string).collect();
        if lines.is_empty() {
            lines.push(String::new());
        }
        Text { lines }
    }

    pub fn len_lines(&self) -> usize {
        self.lines.len()
    }

    pub fn line(&self, index: usize) -> &str {
        self.lines.get(index).map_or("", String::as_str)
    }

    pub fn lines(&self) -> impl Iterator<Item = &str> {
        self.lines.iter().map(String::as_str)
    }

    pub fn line_len(&self, index: usize) -> usize {
        char_len(self.line(index))
    }

    pub fn last_line(&self) -> usize {
        self.lines.len() - 1
    }

    pub fn end(&self) -> Pos {
        Pos::new(self.last_line(), self.line_len(self.last_line()))
    }

    pub fn is_empty(&self) -> bool {
        self.lines.len() == 1 && self.lines[0].is_empty()
    }

    /// Joined with '\n'; the caller adds the file's final newline and line endings.
    pub fn to_string_lf(&self) -> String {
        self.lines.join("\n")
    }

    pub fn byte_len(&self) -> usize {
        self.lines.iter().map(|line| line.len() + 1).sum::<usize>() - 1
    }

    /// A position moved inside the text (the column may sit at the line end).
    pub fn clamp(&self, pos: Pos) -> Pos {
        let line = pos.line.min(self.last_line());
        Pos::new(line, pos.col.min(self.line_len(line)))
    }

    /// The char at `pos`; a line end reads as '\n' (None at the very end).
    pub fn char_at(&self, pos: Pos) -> Option<char> {
        let line = self.lines.get(pos.line)?;
        match line.chars().nth(pos.col) {
            Some(c) => Some(c),
            None if pos.line < self.last_line() => Some('\n'),
            None => None,
        }
    }

    /// The next position, stepping over line ends; None at the end.
    pub fn next(&self, pos: Pos) -> Option<Pos> {
        if pos.col < self.line_len(pos.line) {
            Some(Pos::new(pos.line, pos.col + 1))
        } else if pos.line < self.last_line() {
            Some(Pos::new(pos.line + 1, 0))
        } else {
            None
        }
    }

    pub fn prev(&self, pos: Pos) -> Option<Pos> {
        if pos.col > 0 {
            Some(Pos::new(pos.line, pos.col - 1))
        } else if pos.line > 0 {
            Some(Pos::new(pos.line - 1, self.line_len(pos.line - 1)))
        } else {
            None
        }
    }

    pub fn slice(&self, start: Pos, end: Pos) -> String {
        let (start, end) = (self.clamp(start.min(end)), self.clamp(start.max(end)));
        if start.line == end.line {
            let line = self.line(start.line);
            return line[byte_at(line, start.col)..byte_at(line, end.col)].to_string();
        }
        let first = self.line(start.line);
        let mut out = first[byte_at(first, start.col)..].to_string();
        for index in start.line + 1..end.line {
            out.push('\n');
            out.push_str(self.line(index));
        }
        out.push('\n');
        let last = self.line(end.line);
        out.push_str(&last[..byte_at(last, end.col)]);
        out
    }

    /// Inserts `text` at `pos`; returns the position right after it.
    pub fn insert(&mut self, pos: Pos, text: &str) -> Pos {
        let pos = self.clamp(pos);
        let line = &mut self.lines[pos.line];
        let split = byte_at(line, pos.col);
        let tail = line.split_off(split);
        let mut parts = text.split('\n');
        line.push_str(parts.next().unwrap_or(""));
        let mut end = Pos::new(pos.line, pos.col + char_len(text.split('\n').next().unwrap_or("")));
        let rest: Vec<String> = parts.map(str::to_string).collect();
        if rest.is_empty() {
            self.lines[pos.line].push_str(&tail);
            return end;
        }
        let count = rest.len();
        end = Pos::new(pos.line + count, char_len(&rest[count - 1]));
        let mut rest = rest;
        rest[count - 1].push_str(&tail);
        self.lines.splice(pos.line + 1..pos.line + 1, rest);
        end
    }

    /// Removes `start..end` and returns what was there.
    pub fn remove(&mut self, start: Pos, end: Pos) -> String {
        let (start, end) = (self.clamp(start.min(end)), self.clamp(start.max(end)));
        if start == end {
            return String::new();
        }
        let removed = self.slice(start, end);
        if start.line == end.line {
            let line = &mut self.lines[start.line];
            let (from, to) = (byte_at(line, start.col), byte_at(line, end.col));
            line.replace_range(from..to, "");
            return removed;
        }
        let last = &self.lines[end.line];
        let tail = last[byte_at(last, end.col)..].to_string();
        let first = &mut self.lines[start.line];
        let cut = byte_at(first, start.col);
        first.truncate(cut);
        first.push_str(&tail);
        self.lines.drain(start.line + 1..=end.line);
        removed
    }

    /// Leading whitespace of a line.
    pub fn indent_of(&self, line: usize) -> &str {
        let text = self.line(line);
        &text[..text.len() - text.trim_start().len()]
    }

    pub fn first_non_blank(&self, line: usize) -> usize {
        char_len(self.indent_of(line))
    }
}

/// One replacement: at `start`, `removed` was replaced with `inserted`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Change {
    pub start: Pos,
    pub removed: String,
    pub inserted: String,
}

/// End of `text` inserted at `start`.
pub fn end_of(start: Pos, text: &str) -> Pos {
    let lines = text.split('\n').count() - 1;
    let last = text.rsplit('\n').next().unwrap_or("");
    if lines == 0 {
        Pos::new(start.line, start.col + char_len(last))
    } else {
        Pos::new(start.line + lines, char_len(last))
    }
}

#[derive(Clone, Debug, Default)]
pub struct Revision {
    pub id: u64,
    pub changes: Vec<Change>,
    pub cursor_before: Pos,
    pub cursor_after: Pos,
}

/// Undo history as revisions of changes; a revision is one undo step.
#[derive(Debug, Default)]
pub struct History {
    undo: Vec<Revision>,
    redo: Vec<Revision>,
    pending: Option<Revision>,
    next_id: u64,
}

impl History {
    pub fn record(&mut self, change: Change, cursor: Pos) {
        let pending = self.pending.get_or_insert_with(|| Revision { cursor_before: cursor, ..Revision::default() });
        // Typing a word records one change per char; merge them into one.
        if let Some(last) = pending.changes.last_mut() {
            if change.removed.is_empty()
                && last.removed.is_empty()
                && end_of(last.start, &last.inserted) == change.start
            {
                last.inserted.push_str(&change.inserted);
                return;
            }
        }
        pending.changes.push(change);
    }

    /// Closes the open revision; returns true when it changed anything.
    pub fn commit(&mut self, cursor: Pos) -> bool {
        match self.pending.take() {
            Some(mut revision) if !revision.changes.is_empty() => {
                self.next_id += 1;
                revision.id = self.next_id;
                revision.cursor_after = cursor;
                self.undo.push(revision);
                self.redo.clear();
                true
            }
            _ => false,
        }
    }

    pub fn has_pending(&self) -> bool {
        self.pending.as_ref().is_some_and(|revision| !revision.changes.is_empty())
    }

    pub fn pop_undo(&mut self) -> Option<Revision> {
        let revision = self.undo.pop()?;
        self.redo.push(revision.clone());
        Some(revision)
    }

    pub fn pop_redo(&mut self) -> Option<Revision> {
        let revision = self.redo.pop()?;
        self.undo.push(revision.clone());
        Some(revision)
    }

    /// Id of the revision the text is at; 0 for the original text.
    pub fn current_id(&self) -> u64 {
        self.undo.last().map_or(0, |revision| revision.id)
    }

    pub fn clear(&mut self) {
        *self = History::default();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn insert_and_remove_across_lines() {
        let mut text = Text::new("hello\nworld");
        let end = text.insert(Pos::new(0, 5), " there\nbig");
        assert_eq!(end, Pos::new(1, 3));
        assert_eq!(text.to_string_lf(), "hello there\nbig\nworld");
        let removed = text.remove(Pos::new(0, 5), Pos::new(2, 0));
        assert_eq!(removed, " there\nbig\n");
        assert_eq!(text.to_string_lf(), "helloworld");
    }

    #[test]
    fn unicode_positions_are_chars() {
        let mut text = Text::new("привет");
        text.insert(Pos::new(0, 3), "-");
        assert_eq!(text.line(0), "при-вет");
        assert_eq!(text.char_at(Pos::new(0, 4)), Some('в'));
        assert_eq!(text.slice(Pos::new(0, 0), Pos::new(0, 3)), "при");
    }

    #[test]
    fn next_and_prev_cross_line_ends() {
        let text = Text::new("ab\nc");
        assert_eq!(text.next(Pos::new(0, 2)), Some(Pos::new(1, 0)));
        assert_eq!(text.prev(Pos::new(1, 0)), Some(Pos::new(0, 2)));
        assert_eq!(text.char_at(Pos::new(0, 2)), Some('\n'));
        assert_eq!(text.next(Pos::new(1, 1)), None);
    }

    #[test]
    fn typing_merges_into_one_change() {
        let mut history = History::default();
        history.record(Change { start: Pos::new(0, 0), removed: String::new(), inserted: "a".into() }, Pos::default());
        history.record(Change { start: Pos::new(0, 1), removed: String::new(), inserted: "b".into() }, Pos::default());
        assert!(history.commit(Pos::new(0, 2)));
        let revision = history.pop_undo().unwrap();
        assert_eq!(revision.changes.len(), 1);
        assert_eq!(revision.changes[0].inserted, "ab");
    }

    #[test]
    fn end_of_multiline_text() {
        assert_eq!(end_of(Pos::new(2, 3), "ab"), Pos::new(2, 5));
        assert_eq!(end_of(Pos::new(2, 3), "ab\ncd"), Pos::new(3, 2));
    }
}
