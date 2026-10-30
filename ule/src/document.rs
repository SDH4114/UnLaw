//! An open file (or scratch/output buffer): text, undo history, highlight cache, diagnostics.

use std::collections::HashMap;
use std::fs;
use std::io::{self, Write};
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use crate::syntax::{self, Languages, Span, State};
use crate::text::{end_of, Change, History, Pos, Text};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DocKind {
    File,
    Scratch,
    Output,
    Help,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Diagnostic {
    pub start: Pos,
    pub end: Pos,
    /// 1 error, 2 warning, 3 info, 4 hint (as in LSP).
    pub severity: u8,
    pub message: String,
    pub source: String,
}

#[derive(Debug)]
pub struct Document {
    pub id: usize,
    pub text: Text,
    pub path: Option<PathBuf>,
    pub name: String,
    pub kind: DocKind,
    pub lang: Option<usize>,
    pub history: History,
    saved_id: u64,
    saved_dirty: bool,
    pub crlf: bool,
    pub final_newline: bool,
    pub version: i32,
    pub diagnostics: Vec<Diagnostic>,
    pub mtime: Option<SystemTime>,
    pub readonly: bool,
    pub marks: HashMap<char, Pos>,
    pub last_cursor: Pos,
    /// One indent unit: detected from the file, else the language's, else the options'.
    pub indent: Option<String>,
    states: Vec<State>,
    /// `states[..valid]` are correct; edits move this back.
    valid: usize,
}

pub fn display_path(path: &Path) -> String {
    let cwd = std::env::current_dir().unwrap_or_default();
    if let Ok(relative) = path.strip_prefix(&cwd) {
        return relative.display().to_string();
    }
    let home = crate::config::home();
    if let Ok(relative) = path.strip_prefix(&home) {
        return format!("~/{}", relative.display());
    }
    path.display().to_string()
}

pub fn absolute(path: &Path) -> PathBuf {
    let path = if let Some(rest) = path.to_str().and_then(|text| text.strip_prefix("~/")) {
        crate::config::home().join(rest)
    } else {
        path.to_path_buf()
    };
    let joined = if path.is_absolute() { path } else { std::env::current_dir().unwrap_or_default().join(path) };
    // Normalize `.` and `..` without touching the disk (the file may not exist yet).
    let mut out = PathBuf::new();
    for part in joined.components() {
        match part {
            std::path::Component::ParentDir => {
                out.pop();
            }
            std::path::Component::CurDir => {}
            other => out.push(other.as_os_str()),
        }
    }
    out
}

impl Document {
    pub fn scratch(id: usize, name: &str, kind: DocKind) -> Self {
        Document {
            id,
            text: Text::default(),
            path: None,
            name: name.to_string(),
            kind,
            lang: None,
            history: History::default(),
            saved_id: 0,
            saved_dirty: false,
            crlf: false,
            final_newline: true,
            version: 0,
            diagnostics: Vec::new(),
            mtime: None,
            readonly: false,
            marks: HashMap::new(),
            last_cursor: Pos::default(),
            indent: None,
            states: vec![State::Normal],
            valid: 1,
        }
    }

    /// Opens `path`; a missing file gives an empty buffer that is created on save.
    pub fn open(id: usize, path: &Path, languages: &Languages) -> io::Result<Self> {
        let path = absolute(path);
        let mut doc = Document::scratch(id, &display_path(&path), DocKind::File);
        match fs::read(&path) {
            Ok(bytes) => {
                if bytes.iter().take(8000).any(|byte| *byte == 0) {
                    return Err(io::Error::new(io::ErrorKind::InvalidData, "binary file"));
                }
                let content = String::from_utf8(bytes)
                    .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, format!("file is not UTF-8: {error}")))?;
                doc.load(&content);
                doc.mtime = fs::metadata(&path).and_then(|meta| meta.modified()).ok();
                doc.readonly = fs::metadata(&path).map(|meta| meta.permissions().readonly()).unwrap_or(false);
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(error),
        }
        doc.lang = languages.detect(Some(&path), doc.text.line(0));
        doc.path = Some(path);
        doc.detect_indent();
        Ok(doc)
    }

    fn load(&mut self, content: &str) {
        self.crlf = content.contains("\r\n");
        let normalized = if self.crlf { content.replace("\r\n", "\n") } else { content.to_string() };
        self.final_newline = normalized.ends_with('\n') || normalized.is_empty();
        let body = normalized.strip_suffix('\n').unwrap_or(&normalized);
        self.text = Text::new(body);
        self.invalidate(0);
    }

    pub fn set_content(&mut self, content: &str) {
        self.load(content);
        self.history.clear();
        self.saved_id = 0;
        self.saved_dirty = false;
        self.version += 1;
    }

    pub fn modified(&self) -> bool {
        self.kind == DocKind::File
            && (self.history.current_id() != self.saved_id || self.history.has_pending() || self.saved_dirty)
    }

    pub fn is_empty_scratch(&self) -> bool {
        self.kind == DocKind::Scratch && self.path.is_none() && self.text.is_empty() && !self.history.has_pending()
    }

    pub fn title(&self) -> String {
        match &self.path {
            Some(path) => display_path(path),
            None => self.name.clone(),
        }
    }

    pub fn file_name(&self) -> String {
        match &self.path {
            Some(path) => {
                path.file_name().map_or_else(|| self.name.clone(), |name| name.to_string_lossy().into_owned())
            }
            None => self.name.clone(),
        }
    }

    pub fn invalidate(&mut self, line: usize) {
        self.valid = self.valid.min(line + 1).max(1);
    }

    pub fn insert(&mut self, pos: Pos, text: &str, cursor: Pos) -> Pos {
        if text.is_empty() {
            return pos;
        }
        let pos = self.text.clamp(pos);
        let end = self.text.insert(pos, text);
        self.history.record(Change { start: pos, removed: String::new(), inserted: text.to_string() }, cursor);
        self.edited(pos.line);
        end
    }

    pub fn remove(&mut self, start: Pos, end: Pos, cursor: Pos) -> String {
        let (start, end) = (self.text.clamp(start.min(end)), self.text.clamp(start.max(end)));
        if start == end {
            return String::new();
        }
        let removed = self.text.remove(start, end);
        self.history.record(Change { start, removed: removed.clone(), inserted: String::new() }, cursor);
        self.edited(start.line);
        removed
    }

    /// Replaces `start..end` with `text`; returns the end of the new text.
    pub fn replace(&mut self, start: Pos, end: Pos, text: &str, cursor: Pos) -> Pos {
        let (start, end) = (self.text.clamp(start.min(end)), self.text.clamp(start.max(end)));
        self.remove(start, end, cursor);
        self.insert(start, text, cursor)
    }

    fn edited(&mut self, line: usize) {
        self.version += 1;
        self.invalidate(line);
    }

    pub fn commit(&mut self, cursor: Pos) -> bool {
        self.history.commit(cursor)
    }

    fn apply_inverse(&mut self, changes: &[Change]) {
        for change in changes.iter().rev() {
            let end = end_of(change.start, &change.inserted);
            self.text.remove(change.start, end);
            self.text.insert(change.start, &change.removed);
            self.edited(change.start.line);
        }
    }

    fn apply_forward(&mut self, changes: &[Change]) {
        for change in changes {
            let end = end_of(change.start, &change.removed);
            self.text.remove(change.start, end);
            self.text.insert(change.start, &change.inserted);
            self.edited(change.start.line);
        }
    }

    /// Undoes one step; returns where the cursor goes.
    pub fn undo(&mut self, cursor: Pos) -> Option<Pos> {
        self.commit(cursor);
        let revision = self.history.pop_undo()?;
        self.apply_inverse(&revision.changes);
        Some(self.text.clamp(revision.changes.first().map_or(revision.cursor_before, |change| change.start)))
    }

    pub fn redo(&mut self, cursor: Pos) -> Option<Pos> {
        self.commit(cursor);
        let revision = self.history.pop_redo()?;
        self.apply_forward(&revision.changes);
        Some(self.text.clamp(revision.changes.first().map_or(revision.cursor_after, |change| change.start)))
    }

    /// The file's content as saved: line endings and the final newline restored.
    pub fn content(&self, final_newline: bool) -> String {
        let mut content = self.text.to_string_lf();
        if (self.final_newline || final_newline) && !self.text.is_empty() {
            content.push('\n');
        }
        if self.crlf {
            content = content.replace('\n', "\r\n");
        }
        content
    }

    /// Writes atomically (temporary file + rename), keeping the file's permissions.
    pub fn save_to(&mut self, path: &Path, final_newline: bool) -> io::Result<()> {
        let content = self.content(final_newline);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let permissions = fs::metadata(path).map(|meta| meta.permissions()).ok();
        let temporary = path.with_file_name(format!(
            ".{}.ule-{}",
            path.file_name().map(|name| name.to_string_lossy().into_owned()).unwrap_or_default(),
            std::process::id()
        ));
        // An existing temporary path may be a symlink or belong to another save.
        // Acquire it exclusively before entering the cleanup scope.
        let mut file = fs::OpenOptions::new().write(true).create_new(true).open(&temporary)?;
        let result = (|| {
            file.write_all(content.as_bytes())?;
            file.sync_all()?;
            if let Some(permissions) = &permissions {
                fs::set_permissions(&temporary, permissions.clone())?;
            } else {
                fs::set_permissions(&temporary, fs::Permissions::from_mode(0o644))?;
            }
            // A symlinked file keeps its link: write through to the target.
            let target = fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
            fs::rename(&temporary, &target)
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temporary);
        }
        result?;
        if final_newline {
            self.final_newline = true;
        }
        self.mark_saved();
        self.mtime = fs::metadata(path).and_then(|meta| meta.modified()).ok();
        if self.path.as_deref() != Some(path) {
            self.path = Some(path.to_path_buf());
            self.name = display_path(path);
            self.kind = DocKind::File;
        }
        Ok(())
    }

    pub fn mark_saved(&mut self) {
        self.history.commit(self.last_cursor);
        self.saved_id = self.history.current_id();
        self.saved_dirty = false;
    }

    /// After a reload or a rename the text differs from disk in a way undo cannot express.
    pub fn mark_dirty(&mut self) {
        self.saved_dirty = true;
    }

    pub fn changed_on_disk(&self) -> bool {
        let (Some(path), Some(known)) = (&self.path, self.mtime) else {
            return false;
        };
        fs::metadata(path).and_then(|meta| meta.modified()).map(|now| now != known).unwrap_or(false)
    }

    /// Rereads the file, keeping undo: the reload is one undoable change.
    pub fn reload(&mut self, cursor: Pos) -> io::Result<()> {
        let path = self.path.clone().ok_or_else(|| io::Error::other("no file"))?;
        let bytes = fs::read(&path)?;
        let content = String::from_utf8_lossy(&bytes).into_owned();
        let crlf = content.contains("\r\n");
        let normalized = if crlf { content.replace("\r\n", "\n") } else { content.clone() };
        let body = normalized.strip_suffix('\n').unwrap_or(&normalized).to_string();
        if body != self.text.to_string_lf() {
            self.commit(cursor);
            let end = self.text.end();
            self.replace(Pos::default(), end, &body, cursor);
            self.commit(cursor);
        }
        self.crlf = crlf;
        self.final_newline = normalized.ends_with('\n') || normalized.is_empty();
        self.mark_saved();
        self.mtime = fs::metadata(&path).and_then(|meta| meta.modified()).ok();
        Ok(())
    }

    pub fn detect_indent(&mut self) {
        let mut tabs = 0;
        let mut spaces: HashMap<usize, usize> = HashMap::new();
        let mut previous = 0usize;
        for line in self.text.lines().take(2000) {
            if line.trim().is_empty() {
                continue;
            }
            if line.starts_with('\t') {
                tabs += 1;
                continue;
            }
            let width = line.len() - line.trim_start_matches(' ').len();
            if width != previous {
                let delta = width.abs_diff(previous);
                if (2..=8).contains(&delta) {
                    *spaces.entry(delta).or_default() += 1;
                }
                previous = width;
            }
        }
        let best = spaces.iter().max_by_key(|(width, count)| (**count, std::cmp::Reverse(**width)));
        let space_votes: usize = spaces.values().sum();
        self.indent = if tabs > space_votes && tabs > 2 {
            Some("\t".into())
        } else {
            best.filter(|(_, count)| **count >= 2).map(|(width, _)| " ".repeat(*width))
        };
    }

    /// Spans of `line`, scanning from the last line whose start state is known.
    pub fn spans(&mut self, line: usize, languages: &Languages) -> Vec<Span> {
        let Some(lang) = self.lang.and_then(|index| languages.get(index)) else {
            return Vec::new();
        };
        if line >= self.text.len_lines() {
            return Vec::new();
        }
        if self.states.len() < self.text.len_lines() + 1 {
            self.states.resize(self.text.len_lines() + 1, State::Normal);
        }
        while self.valid <= line {
            let index = self.valid - 1;
            let (_, next) = syntax::highlight(languages, lang, self.text.line(index), &self.states[index]);
            self.states[index + 1] = next;
            self.valid += 1;
        }
        syntax::highlight(languages, lang, self.text.line(line), &self.states[line]).0
    }

    /// The state a line starts in (for "am I in a comment/string" questions).
    pub fn state_at(&mut self, line: usize, languages: &Languages) -> State {
        if line > 0 {
            self.spans(line - 1, languages);
        }
        self.states.get(line).cloned().unwrap_or_default()
    }

    pub fn set_language(&mut self, lang: Option<usize>) {
        self.lang = lang;
        self.invalidate(0);
    }

    pub fn diagnostics_on(&self, line: usize) -> impl Iterator<Item = &Diagnostic> {
        self.diagnostics.iter().filter(move |diagnostic| diagnostic.start.line <= line && line <= diagnostic.end.line)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("ule-doc-{}-{name}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        dir.join(name)
    }

    #[test]
    fn keeps_crlf_and_final_newline() {
        let path = temp("crlf.txt");
        fs::write(&path, "a\r\nb\r\n").unwrap();
        let (languages, _) = Languages::load(None);
        let mut doc = Document::open(1, &path, &languages).unwrap();
        assert_eq!(doc.text.to_string_lf(), "a\nb");
        doc.insert(Pos::new(1, 1), "c", Pos::default());
        assert!(doc.modified());
        doc.save_to(&path, true).unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), "a\r\nbc\r\n");
        assert!(!doc.modified());
    }

    #[test]
    fn undo_back_to_saved_is_unmodified() {
        let mut doc = Document::scratch(1, "x", DocKind::File);
        doc.insert(Pos::default(), "hello", Pos::default());
        doc.commit(Pos::new(0, 5));
        assert!(doc.modified());
        doc.mark_saved();
        doc.insert(Pos::new(0, 5), "!", Pos::default());
        doc.commit(Pos::new(0, 6));
        assert!(doc.modified());
        assert_eq!(doc.undo(Pos::new(0, 6)), Some(Pos::new(0, 5)));
        assert!(!doc.modified());
        assert_eq!(doc.text.line(0), "hello");
        doc.redo(Pos::new(0, 5));
        assert_eq!(doc.text.line(0), "hello!");
    }

    #[test]
    fn detects_indentation() {
        let mut doc = Document::scratch(1, "x", DocKind::File);
        doc.set_content("fn a() {\n  b();\n  if x {\n    c();\n  }\n}\n");
        doc.detect_indent();
        assert_eq!(doc.indent.as_deref(), Some("  "));
        doc.set_content("a:\n\tb\n\tc\n\td\n");
        doc.detect_indent();
        assert_eq!(doc.indent.as_deref(), Some("\t"));
    }

    #[test]
    fn invalid_utf8_is_refused_without_lossy_conversion() {
        let path = temp("invalid-utf8.txt");
        fs::write(&path, [b'a', 0xff, b'b']).unwrap();
        let (languages, _) = Languages::load(None);
        assert_eq!(Document::open(1, &path, &languages).unwrap_err().kind(), io::ErrorKind::InvalidData);
        assert_eq!(fs::read(&path).unwrap(), [b'a', 0xff, b'b']);
    }

    #[test]
    fn replacing_a_reversed_range_removes_the_whole_range() {
        let mut doc = Document::scratch(1, "x", DocKind::File);
        doc.set_content("abcdef");
        doc.replace(Pos::new(0, 4), Pos::new(0, 1), "X", Pos::default());
        assert_eq!(doc.text.to_string_lf(), "aXef");
    }

    #[test]
    fn save_does_not_follow_an_existing_temporary_symlink() {
        let path = temp("safe-save.txt");
        let victim = path.with_file_name("victim.txt");
        fs::write(&victim, "keep me").unwrap();
        let temporary = path.with_file_name(format!(".safe-save.txt.ule-{}", std::process::id()));
        std::os::unix::fs::symlink(&victim, &temporary).unwrap();
        let mut doc = Document::scratch(1, "x", DocKind::File);
        doc.set_content("new content");
        let result = doc.save_to(&path, true);
        assert_eq!(fs::read_to_string(&victim).unwrap(), "keep me");
        if result.is_ok() {
            assert_eq!(fs::read_to_string(&path).unwrap(), "new content\n");
        }
        assert!(temporary.is_symlink(), "a preexisting file belongs to someone else");
        fs::remove_file(temporary).unwrap();
    }

    #[test]
    fn binary_files_are_refused() {
        let path = temp("bin.dat");
        fs::write(&path, [0u8, 1, 2, 3]).unwrap();
        let (languages, _) = Languages::load(None);
        assert!(Document::open(1, &path, &languages).is_err());
    }
}
