//! Editor state: documents, views and their layout, mode, registers, search, messages.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::mpsc::{channel, Receiver, Sender};
use std::time::{Duration, Instant};

use regex::{Regex, RegexBuilder};

use crate::config::{Config, Options};
use crate::display::{col_to_display, display_to_col, line_rows, wrap_rows};
use crate::document::{absolute, display_path, DocKind, Document};
use crate::explorer::Explorer;
use crate::keymap::Keymap;
use crate::keys::Key;
use crate::lsp::Lsp;
use crate::picker::Picker;
use crate::state::State as Persisted;
use crate::syntax::Languages;
use crate::text::{byte_at, Pos};
use crate::theme::{Theme, Themes};
use crate::widgets::{Completion, Popup, Prompt};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Rect {
    pub x: u16,
    pub y: u16,
    pub w: u16,
    pub h: u16,
}

impl Rect {
    pub fn contains(&self, x: u16, y: u16) -> bool {
        x >= self.x && x < self.x + self.w && y >= self.y && y < self.y + self.h
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum VisualKind {
    Char,
    Line,
    Block,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    Normal,
    Insert,
    Replace,
    Visual(VisualKind),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Focus {
    View,
    Explorer,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Level {
    Info,
    Warning,
    Error,
}

#[derive(Clone, Debug)]
pub struct Message {
    pub text: String,
    pub level: Level,
    pub at: Instant,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Register {
    pub text: String,
    pub linewise: bool,
}

#[derive(Debug)]
pub struct View {
    pub id: usize,
    pub doc: usize,
    pub cursor: Pos,
    pub scroll: usize,
    pub hscroll: usize,
    /// Display column kept by j/k across short lines (usize::MAX after `$`).
    pub want_col: Option<usize>,
    pub jumps: Vec<(usize, Pos)>,
    pub jump_index: usize,
    /// The text area (without the gutter), set by the renderer.
    pub area: Rect,
    pub alternate: Option<usize>,
}

impl View {
    fn new(id: usize, doc: usize) -> Self {
        View {
            id,
            doc,
            cursor: Pos::default(),
            scroll: 0,
            hscroll: 0,
            want_col: None,
            jumps: Vec::new(),
            jump_index: 0,
            area: Rect { x: 0, y: 0, w: 80, h: 24 },
            alternate: None,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Layout {
    View(usize),
    Split { vertical: bool, children: Vec<Layout> },
}

impl Layout {
    pub fn views(&self) -> Vec<usize> {
        match self {
            Layout::View(view) => vec![*view],
            Layout::Split { children, .. } => children.iter().flat_map(Layout::views).collect(),
        }
    }

    /// Puts `new` next to `target`, joining an existing split of the same direction.
    fn split(&mut self, target: usize, new: usize, vertical: bool) -> bool {
        match self {
            Layout::View(view) if *view == target => {
                *self = Layout::Split { vertical, children: vec![Layout::View(target), Layout::View(new)] };
                true
            }
            Layout::View(_) => false,
            Layout::Split { vertical: direction, children } => {
                if *direction == vertical {
                    if let Some(index) = children.iter().position(|child| *child == Layout::View(target)) {
                        children.insert(index + 1, Layout::View(new));
                        return true;
                    }
                }
                children.iter_mut().any(|child| child.split(target, new, vertical))
            }
        }
    }

    fn remove(&mut self, target: usize) -> bool {
        let Layout::Split { children, .. } = self else {
            return false;
        };
        if let Some(index) = children.iter().position(|child| *child == Layout::View(target)) {
            children.remove(index);
        } else if !children.iter_mut().any(|child| child.remove(target)) {
            return false;
        }
        if children.len() == 1 {
            *self = children.remove(0);
        }
        true
    }

    /// Screen areas of every view (including its gutter and status line).
    pub fn areas(&self, area: Rect, out: &mut Vec<(usize, Rect)>) {
        match self {
            Layout::View(view) => out.push((*view, area)),
            Layout::Split { vertical, children } => {
                let count = children.len() as u16;
                let total = if *vertical { area.w } else { area.h };
                // Vertical splits draw a one-column separator between views.
                let gaps = if *vertical { count.saturating_sub(1) } else { 0 };
                let size = total.saturating_sub(gaps) / count.max(1);
                let mut offset = 0;
                for (index, child) in children.iter().enumerate() {
                    let last = index as u16 == count - 1;
                    let length = if last { total.saturating_sub(offset) } else { size };
                    let child_area = if *vertical {
                        Rect { x: area.x + offset, y: area.y, w: length, h: area.h }
                    } else {
                        Rect { x: area.x, y: area.y + offset, w: area.w, h: length }
                    };
                    child.areas(child_area, out);
                    offset += length + if *vertical { 1 } else { 0 };
                }
            }
        }
    }
}

/// Messages from background threads: language servers, jobs, file scans.
pub enum Event {
    Lsp(usize, serde_json::Value),
    LspExit(usize, String),
    JobOutput(usize, String),
    JobDone(usize, Option<i32>),
    Files(u64, Vec<PathBuf>, bool),
    Grep(u64, Vec<(PathBuf, usize, usize, String)>, bool),
    UlCommands(Vec<(String, String)>),
    Wake,
}

pub struct Editor {
    pub docs: HashMap<usize, Document>,
    pub buffers: Vec<usize>,
    pub views: HashMap<usize, View>,
    pub layout: Layout,
    pub focus: usize,
    pub focus_area: Focus,
    pub panel: Option<usize>,
    pub panel_visible: bool,
    pub explorer: Option<Explorer>,
    pub mode: Mode,
    pub anchor: Pos,
    pub last_visual: Option<(usize, Pos, Pos, VisualKind)>,
    pub registers: HashMap<char, Register>,
    pub clipboard_cache: Option<String>,
    pub options: Options,
    pub config: Config,
    pub keymap: Keymap,
    pub languages: Languages,
    pub themes: Themes,
    pub theme: Theme,
    pub message: Option<Message>,
    pub prompt: Option<Prompt>,
    pub picker: Option<Picker>,
    pub last_picker: Option<Picker>,
    pub popup: Option<Popup>,
    pub completion: Option<Completion>,
    pub search: Option<(String, bool)>,
    pub search_regex: Option<Regex>,
    pub hlsearch_active: bool,
    pub size: (u16, u16),
    pub quit: bool,
    pub next_id: usize,
    pub lsp: Lsp,
    pub jobs: crate::jobs::Jobs,
    pub tx: Sender<Event>,
    pub rx: Receiver<Event>,
    pub persisted: Persisted,
    pub vim: crate::vim::VimState,
    pub needs_redraw: bool,
    pub suspend_requested: bool,
    pub handoff: Option<crate::jobs::Handoff>,
    pub started: Instant,
    pub ul_commands: Vec<(String, String)>,
    pub last_run: Option<String>,
    pub cwd: PathBuf,
}

impl Editor {
    pub fn new(config: Config) -> Self {
        let (tx, rx) = channel();
        let (languages, mut errors) = Languages::load(config.languages.as_ref());
        let themes = Themes::new(config.themes.as_ref());
        let theme = match themes.load(&config.options.theme) {
            Ok(theme) => theme,
            Err(error) => {
                errors.push(error);
                Theme::default()
            }
        };
        errors.extend(config.errors.iter().cloned());
        let keymap = Keymap::build(&config);
        errors.extend(keymap.errors.iter().cloned());
        let mut editor = Editor {
            docs: HashMap::new(),
            buffers: Vec::new(),
            views: HashMap::new(),
            layout: Layout::View(0),
            focus: 0,
            focus_area: Focus::View,
            panel: None,
            panel_visible: false,
            explorer: None,
            mode: Mode::Normal,
            anchor: Pos::default(),
            last_visual: None,
            registers: HashMap::new(),
            clipboard_cache: None,
            options: config.options.clone(),
            keymap,
            config,
            languages,
            themes,
            theme,
            message: None,
            prompt: None,
            picker: None,
            last_picker: None,
            popup: None,
            completion: None,
            search: None,
            search_regex: None,
            hlsearch_active: false,
            size: (80, 24),
            quit: false,
            next_id: 1,
            lsp: Lsp::default(),
            jobs: crate::jobs::Jobs::default(),
            tx,
            rx,
            persisted: Persisted::default(),
            vim: crate::vim::VimState::default(),
            needs_redraw: true,
            suspend_requested: false,
            handoff: None,
            started: Instant::now(),
            ul_commands: Vec::new(),
            last_run: None,
            cwd: std::env::current_dir().unwrap_or_default(),
        };
        let doc = editor.new_doc_id();
        editor.docs.insert(doc, Document::scratch(doc, "[scratch]", DocKind::Scratch));
        editor.buffers.push(doc);
        let view = editor.new_doc_id();
        editor.views.insert(view, View::new(view, doc));
        editor.layout = Layout::View(view);
        editor.focus = view;
        if !errors.is_empty() {
            editor.error(format!("config: {}", errors.join("; ")));
        }
        editor
    }

    pub fn new_doc_id(&mut self) -> usize {
        self.next_id += 1;
        self.next_id
    }

    // --- access ---------------------------------------------------------

    pub fn view(&self) -> &View {
        &self.views[&self.focus]
    }

    pub fn view_mut(&mut self) -> &mut View {
        self.views.get_mut(&self.focus).expect("focused view")
    }

    pub fn doc(&self) -> &Document {
        &self.docs[&self.view().doc]
    }

    pub fn doc_mut(&mut self) -> &mut Document {
        let id = self.view().doc;
        self.docs.get_mut(&id).expect("view's document")
    }

    pub fn current(&mut self) -> (&mut View, &mut Document) {
        let view = self.views.get_mut(&self.focus).expect("focused view");
        let doc = self.docs.get_mut(&view.doc).expect("view's document");
        (view, doc)
    }

    pub fn cursor(&self) -> Pos {
        self.view().cursor
    }

    // --- messages -------------------------------------------------------

    pub fn info(&mut self, text: impl Into<String>) {
        self.message = Some(Message { text: text.into(), level: Level::Info, at: Instant::now() });
    }

    pub fn warn(&mut self, text: impl Into<String>) {
        self.message = Some(Message { text: text.into(), level: Level::Warning, at: Instant::now() });
    }

    pub fn error(&mut self, text: impl Into<String>) {
        self.message = Some(Message { text: text.into(), level: Level::Error, at: Instant::now() });
    }

    // --- options per document -----------------------------------------------

    pub fn tab_width(&self, doc: &Document) -> usize {
        doc.lang
            .and_then(|index| self.languages.get(index))
            .and_then(|lang| lang.tab_width)
            .unwrap_or(self.options.tab_width)
    }

    pub fn wraps(&self, doc: &Document) -> bool {
        if doc.kind == DocKind::Output || doc.kind == DocKind::Help {
            return self.options.wrap.unwrap_or(true);
        }
        self.options
            .wrap
            .or_else(|| doc.lang.and_then(|index| self.languages.get(index)).and_then(|lang| lang.wrap))
            .unwrap_or(false)
    }

    /// One indent unit for `doc`: the file's own style, the language's, then the options'.
    pub fn indent_unit(&self, doc: &Document) -> String {
        if let Some(indent) = &doc.indent {
            return indent.clone();
        }
        if let Some(indent) = doc.lang.and_then(|index| self.languages.get(index)).and_then(|lang| lang.indent.clone())
        {
            if indent == "\t" || self.options.expand_tab {
                return indent;
            }
        }
        if self.options.expand_tab {
            " ".repeat(self.options.tab_width)
        } else {
            "\t".into()
        }
    }

    pub fn language_name(&self, doc: &Document) -> String {
        doc.lang.and_then(|index| self.languages.get(index)).map_or("text".into(), |lang| lang.name.clone())
    }

    // --- documents ----------------------------------------------------------

    pub fn find_doc(&self, path: &Path) -> Option<usize> {
        let path = absolute(path);
        self.docs.values().find(|doc| doc.path.as_deref() == Some(path.as_path())).map(|doc| doc.id)
    }

    /// Opens (or switches to) `path` in the focused view.
    pub fn open(&mut self, path: &Path) -> Result<usize, String> {
        if path.is_dir() {
            let root = absolute(path);
            self.explorer = Some(Explorer::new(root.clone(), self.options.hidden_files));
            self.focus_area = Focus::Explorer;
            return Ok(self.view().doc);
        }
        let id = match self.find_doc(path) {
            Some(id) => id,
            None => {
                let id = self.new_doc_id();
                let doc = Document::open(id, path, &self.languages)
                    .map_err(|error| format!("{}: {error}", path.display()))?;
                let missing = doc.mtime.is_none();
                self.docs.insert(id, doc);
                self.buffers.push(id);
                if missing {
                    self.info(format!("{} [new file]", display_path(&absolute(path))));
                }
                self.lsp_open(id);
                id
            }
        };
        self.persisted.add_recent(&absolute(path));
        self.show_doc(id);
        // A single untouched scratch buffer is replaced by the first real file.
        let scratch: Vec<usize> = self
            .buffers
            .iter()
            .copied()
            .filter(|doc| *doc != id && self.docs.get(doc).is_some_and(Document::is_empty_scratch))
            .collect();
        for doc in scratch {
            if !self.views.values().any(|view| view.doc == doc) {
                self.docs.remove(&doc);
                self.buffers.retain(|existing| *existing != doc);
            }
        }
        Ok(id)
    }

    /// Shows a document in the focused view, restoring where its cursor was.
    pub fn show_doc(&mut self, id: usize) {
        if !self.docs.contains_key(&id) {
            return;
        }
        let previous = self.view().doc;
        if previous != id {
            let cursor = self.cursor();
            if let Some(doc) = self.docs.get_mut(&previous) {
                doc.last_cursor = cursor;
            }
            let restore = {
                let doc = &self.docs[&id];
                if doc.last_cursor != Pos::default() {
                    Some(doc.last_cursor)
                } else if self.options.restore_cursor {
                    doc.path.as_ref().and_then(|path| self.persisted.position(path))
                } else {
                    None
                }
            };
            let view = self.view_mut();
            view.alternate = Some(previous);
            view.doc = id;
            view.cursor = restore.unwrap_or_default();
            view.scroll = 0;
            view.hscroll = 0;
            view.want_col = None;
        }
        self.mode = Mode::Normal;
        self.clamp_cursor();
        self.center_cursor_if_offscreen();
    }

    pub fn scratch(&mut self, name: &str, kind: DocKind) -> usize {
        let id = self.new_doc_id();
        self.docs.insert(id, Document::scratch(id, name, kind));
        if kind != DocKind::Output && kind != DocKind::Help {
            self.buffers.push(id);
        }
        id
    }

    /// An output buffer by name (`[run]`, `[ul]`), created on first use.
    pub fn output_doc(&mut self, name: &str) -> usize {
        if let Some(doc) = self.docs.values().find(|doc| doc.kind == DocKind::Output && doc.name == name) {
            return doc.id;
        }
        self.scratch(name, DocKind::Output)
    }

    pub fn close_doc(&mut self, id: usize, force: bool) -> Result<(), String> {
        let Some(doc) = self.docs.get(&id) else {
            return Ok(());
        };
        if doc.modified() && !force {
            return Err(format!("{} has unsaved changes (:bd! discards them)", doc.title()));
        }
        if let Some(path) = &doc.path {
            let cursor = self.views.values().find(|view| view.doc == id).map_or(doc.last_cursor, |view| view.cursor);
            self.persisted.set_position(path, cursor);
        }
        self.lsp_close(id);
        self.buffers.retain(|existing| *existing != id);
        let replacement = self.buffers.last().copied();
        let replacement = match replacement {
            Some(other) => other,
            None => {
                let doc = self.new_doc_id();
                self.docs.insert(doc, Document::scratch(doc, "[scratch]", DocKind::Scratch));
                self.buffers.push(doc);
                doc
            }
        };
        let affected: Vec<usize> = self.views.values().filter(|view| view.doc == id).map(|view| view.id).collect();
        for view_id in affected {
            let view = self.views.get_mut(&view_id).expect("view");
            view.doc = replacement;
            view.cursor = self.docs[&replacement].last_cursor;
            view.scroll = 0;
            view.jumps.retain(|(doc, _)| *doc != id);
            view.jump_index = view.jump_index.min(view.jumps.len());
        }
        self.docs.remove(&id);
        self.clamp_cursor();
        Ok(())
    }

    pub fn cycle_buffer(&mut self, step: isize) {
        let current = self.view().doc;
        if self.buffers.is_empty() {
            return;
        }
        let index = self.buffers.iter().position(|doc| *doc == current).unwrap_or(0) as isize;
        let next = (index + step).rem_euclid(self.buffers.len() as isize) as usize;
        let doc = self.buffers[next];
        self.show_doc(doc);
    }

    // --- views and layout ---------------------------------------------------

    pub fn split(&mut self, vertical: bool) {
        let doc = self.view().doc;
        let cursor = self.cursor();
        let scroll = self.view().scroll;
        let id = self.new_doc_id();
        let mut view = View::new(id, doc);
        view.cursor = cursor;
        view.scroll = scroll;
        self.views.insert(id, view);
        if self.panel == Some(self.focus) {
            // Splitting the panel splits the main area instead.
            let target = self.layout.views()[0];
            self.layout.split(target, id, vertical);
        } else {
            self.layout.split(self.focus, id, vertical);
        }
        self.focus = id;
    }

    /// Closes the focused view; returns false when it is the last one.
    pub fn close_view(&mut self) -> bool {
        if Some(self.focus) == self.panel {
            self.panel_visible = false;
            self.focus = self.layout.views()[0];
            return true;
        }
        if self.layout.views().len() <= 1 {
            return false;
        }
        let closing = self.focus;
        self.layout.remove(closing);
        self.views.remove(&closing);
        self.focus = self.layout.views()[0];
        true
    }

    pub fn only_view(&mut self) {
        let keep = if Some(self.focus) == self.panel { self.layout.views()[0] } else { self.focus };
        for id in self.layout.views() {
            if id != keep {
                self.views.remove(&id);
            }
        }
        self.layout = Layout::View(keep);
        self.focus = keep;
    }

    /// Areas of the main views, the panel and the explorer for the current screen size.
    pub fn view_areas(&self) -> (Vec<(usize, Rect)>, Option<Rect>) {
        let (width, height) = self.size;
        let top = u16::from(self.bufferline_visible());
        let bottom = 1; // command line
        let mut area = Rect { x: 0, y: top, w: width, h: height.saturating_sub(top + bottom) };
        if self.explorer.is_some() {
            let w = (self.options.explorer_width as u16).min(width / 2);
            area.x += w + 1;
            area.w = area.w.saturating_sub(w + 1);
        }
        let mut out = Vec::new();
        if self.panel_visible {
            if let Some(panel) = self.panel {
                let h = (self.options.panel_height as u16).min(area.h / 2).max(3);
                area.h = area.h.saturating_sub(h);
                out.push((panel, Rect { x: area.x, y: area.y + area.h, w: area.w, h }));
            }
        }
        self.layout.areas(area, &mut out);
        let explorer = self.explorer.as_ref().map(|_| {
            let w = (self.options.explorer_width as u16).min(width / 2);
            Rect { x: 0, y: top, w, h: height.saturating_sub(top + bottom) }
        });
        (out, explorer)
    }

    pub fn bufferline_visible(&self) -> bool {
        match self.options.bufferline {
            crate::config::Bufferline::Always => true,
            crate::config::Bufferline::Multiple => self.buffers.len() > 1,
            crate::config::Bufferline::Never => false,
        }
    }

    /// Moves focus to the view in a direction (h, j, k, l) by screen position.
    pub fn focus_direction(&mut self, direction: char) {
        let (areas, explorer) = self.view_areas();
        let Some((_, current)) = areas.iter().find(|(id, _)| *id == self.focus) else {
            return;
        };
        if self.focus_area == Focus::Explorer {
            if direction == 'l' {
                self.focus_area = Focus::View;
            }
            return;
        }
        let (cx, cy) = (current.x as i32 + current.w as i32 / 2, current.y as i32 + current.h as i32 / 2);
        let candidates = areas.iter().filter(|(id, area)| {
            *id != self.focus
                && match direction {
                    'h' => (area.x + area.w) <= current.x,
                    'l' => area.x >= current.x + current.w,
                    'k' => (area.y + area.h) <= current.y,
                    'j' => area.y >= current.y + current.h,
                    _ => false,
                }
        });
        let best = candidates.min_by_key(|(_, area)| {
            let (x, y) = (area.x as i32 + area.w as i32 / 2, area.y as i32 + area.h as i32 / 2);
            (x - cx).abs() + (y - cy).abs()
        });
        match best {
            Some((id, _)) => self.focus = *id,
            None if direction == 'h' && explorer.is_some() => self.focus_area = Focus::Explorer,
            None => {}
        }
    }

    pub fn focus_next(&mut self) {
        let (areas, _) = self.view_areas();
        let ids: Vec<usize> = areas.iter().map(|(id, _)| *id).collect();
        if let Some(index) = ids.iter().position(|id| *id == self.focus) {
            self.focus = ids[(index + 1) % ids.len()];
        }
    }

    pub fn toggle_panel(&mut self) {
        if self.panel.is_none() {
            let doc = self.output_doc("[output]");
            let id = self.new_doc_id();
            self.views.insert(id, View::new(id, doc));
            self.panel = Some(id);
        }
        self.panel_visible = !self.panel_visible;
        if !self.panel_visible && Some(self.focus) == self.panel {
            self.focus = self.layout.views()[0];
        }
    }

    /// Shows an output document in the panel (opening it) without moving focus.
    pub fn show_in_panel(&mut self, doc: usize) {
        if self.panel.is_none() {
            let id = self.new_doc_id();
            self.views.insert(id, View::new(id, doc));
            self.panel = Some(id);
        }
        let panel = self.panel.expect("panel");
        let view = self.views.get_mut(&panel).expect("panel view");
        if view.doc != doc {
            view.doc = doc;
            view.cursor = Pos::default();
            view.scroll = 0;
        }
        self.panel_visible = true;
    }

    // --- cursor and scrolling ------------------------------------------------

    /// Keeps the cursor inside the text; normal mode cannot sit after the last char.
    pub fn clamp_cursor(&mut self) {
        let insert = matches!(self.mode, Mode::Insert | Mode::Replace);
        let visual = matches!(self.mode, Mode::Visual(_));
        let (view, doc) = self.current();
        let mut cursor = doc.text.clamp(view.cursor);
        let len = doc.text.line_len(cursor.line);
        if !insert && !visual && len > 0 && cursor.col >= len {
            cursor.col = len - 1;
        }
        view.cursor = cursor;
    }

    pub fn set_cursor(&mut self, pos: Pos) {
        self.view_mut().cursor = pos;
        self.view_mut().want_col = None;
        self.clamp_cursor();
    }

    pub fn wrap_width(&self, view: &View) -> usize {
        view.area.w.max(1) as usize
    }

    /// Scrolls the view so the cursor stays `scrolloff` lines away from the edges.
    pub fn scroll_to_cursor(&mut self, view_id: usize) {
        let Some(view) = self.views.get(&view_id) else {
            return;
        };
        let doc = &self.docs[&view.doc];
        let height = view.area.h as usize;
        if height == 0 {
            return;
        }
        let wrap = self.wraps(doc);
        let tab = self.tab_width(doc);
        let width = self.wrap_width(view);
        let so = self.options.scrolloff.min(height.saturating_sub(1) / 2);
        let cursor = view.cursor;
        let mut scroll = view.scroll.min(doc.text.last_line());
        let mut hscroll = view.hscroll;
        if cursor.line < scroll + so {
            scroll = cursor.line.saturating_sub(so);
        }
        if !wrap {
            if cursor.line + so >= scroll + height {
                scroll = (cursor.line + so + 1).saturating_sub(height);
            }
            let line = doc.text.line(cursor.line);
            let column = col_to_display(line, cursor.col, tab);
            let side = 5.min(width / 4);
            if column < hscroll + side {
                hscroll = column.saturating_sub(side);
            }
            if column + side >= hscroll + width {
                hscroll = (column + side + 1).saturating_sub(width);
            }
        } else {
            hscroll = 0;
            let rows = |line: usize| line_rows(doc.text.line(line), width, tab, true);
            let cursor_row = {
                let line = doc.text.line(cursor.line);
                let starts = wrap_rows(line, width, tab);
                starts.iter().rposition(|start| *start <= cursor.col).unwrap_or(0)
            };
            loop {
                let mut used = 0;
                for line in scroll..cursor.line {
                    used += rows(line);
                }
                used += cursor_row + 1;
                let below: usize = (cursor.line + 1..=(cursor.line + so).min(doc.text.last_line())).map(|_| 1).sum();
                if used + below <= height || scroll >= cursor.line {
                    break;
                }
                scroll += 1;
            }
        }
        let view = self.views.get_mut(&view_id).expect("view");
        view.scroll = scroll;
        view.hscroll = hscroll;
    }

    pub fn center_cursor_if_offscreen(&mut self) {
        let view = self.view();
        let height = view.area.h as usize;
        if view.cursor.line < view.scroll || view.cursor.line >= view.scroll + height {
            self.align_cursor('z');
        }
    }

    /// zz (center), zt (top), zb (bottom).
    pub fn align_cursor(&mut self, at: char) {
        let view = self.view();
        let height = view.area.h as usize;
        let line = view.cursor.line;
        let scroll = match at {
            't' => line,
            'b' => (line + 1).saturating_sub(height),
            _ => line.saturating_sub(height / 2),
        };
        self.view_mut().scroll = scroll;
    }

    /// Vertical move keeping the display column (j/k, arrows).
    pub fn move_lines(&mut self, delta: isize) {
        let tab = self.tab_width(self.doc());
        let (view, doc) = self.current();
        let line = doc.text.line(view.cursor.line);
        let want = view.want_col.unwrap_or_else(|| col_to_display(line, view.cursor.col, tab));
        let target = (view.cursor.line as isize + delta).clamp(0, doc.text.last_line() as isize) as usize;
        let target_line = doc.text.line(target);
        let col = if want == usize::MAX { doc.text.line_len(target) } else { display_to_col(target_line, want, tab) };
        view.cursor = Pos::new(target, col);
        view.want_col = Some(want);
        self.clamp_cursor();
    }

    /// Ctrl-d/u/f/b: scroll the view and the cursor together.
    pub fn scroll_page(&mut self, lines: isize) {
        let height = self.view().area.h as isize;
        let (view, doc) = self.current();
        let last = doc.text.last_line() as isize;
        let scroll = (view.scroll as isize + lines).clamp(0, (last - height / 2).max(0));
        let moved = scroll - view.scroll as isize;
        view.scroll = scroll as usize;
        let delta = if moved == 0 { lines } else { moved };
        self.move_lines(delta);
    }

    // --- jumps ------------------------------------------------------------------

    pub fn push_jump(&mut self) {
        let doc = self.view().doc;
        let cursor = self.cursor();
        let view = self.view_mut();
        view.jumps.truncate(view.jump_index);
        if view.jumps.last() != Some(&(doc, cursor)) {
            view.jumps.push((doc, cursor));
        }
        if view.jumps.len() > 100 {
            view.jumps.remove(0);
        }
        view.jump_index = view.jumps.len();
    }

    pub fn jump(&mut self, back: bool) {
        let doc = self.view().doc;
        let cursor = self.cursor();
        let view = self.view_mut();
        if back {
            if view.jump_index == 0 {
                return;
            }
            if view.jump_index == view.jumps.len() {
                view.jumps.push((doc, cursor));
            }
            view.jump_index -= 1;
        } else {
            if view.jump_index + 1 >= view.jumps.len() {
                return;
            }
            view.jump_index += 1;
        }
        let (target_doc, pos) = view.jumps[view.jump_index];
        if self.docs.contains_key(&target_doc) {
            self.show_doc(target_doc);
            self.set_cursor(pos);
            self.center_cursor_if_offscreen();
        }
    }

    // --- registers ----------------------------------------------------------------

    pub fn set_register(&mut self, name: Option<char>, text: String, linewise: bool, yank: bool) {
        let register = Register { text, linewise };
        match name {
            Some('_') => return,
            Some('+') | Some('*') => {
                crate::clipboard::set(&register.text);
                self.clipboard_cache = Some(register.text.clone());
                self.registers.insert('+', register);
                return;
            }
            Some(c) if c.is_ascii_uppercase() => {
                let lower = c.to_ascii_lowercase();
                let entry = self.registers.entry(lower).or_default();
                if entry.linewise && !entry.text.ends_with('\n') {
                    entry.text.push('\n');
                }
                entry.text.push_str(&register.text);
                entry.linewise |= register.linewise;
                return;
            }
            Some(c) if c != '"' => {
                self.registers.insert(c, register);
                return;
            }
            _ => {}
        }
        if yank {
            self.registers.insert('0', register.clone());
        } else if register.text.contains('\n') || register.linewise {
            // Deletes shift through "1 .. "9 like vim.
            for index in (1..9).rev() {
                let from = char::from_digit(index, 10).expect("digit");
                let to = char::from_digit(index + 1, 10).expect("digit");
                if let Some(previous) = self.registers.get(&from).cloned() {
                    self.registers.insert(to, previous);
                }
            }
            self.registers.insert('1', register.clone());
        } else {
            self.registers.insert('-', register.clone());
        }
        if self.options.clipboard {
            crate::clipboard::set(&register.text);
            self.clipboard_cache = Some(register.text.clone());
        }
        self.registers.insert('"', register);
    }

    pub fn get_register(&mut self, name: Option<char>) -> Option<Register> {
        let name = name.unwrap_or('"');
        let from_clipboard = |cache: &Option<String>, fallback: Option<&Register>| {
            let text = crate::clipboard::get()?;
            if cache.as_deref() == Some(text.as_str()) {
                if let Some(register) = fallback {
                    return Some(register.clone());
                }
            }
            let linewise = text.ends_with('\n');
            Some(Register { text, linewise })
        };
        match name {
            '+' | '*' => from_clipboard(&self.clipboard_cache, self.registers.get(&'+')),
            '"' if self.options.clipboard => from_clipboard(&self.clipboard_cache, self.registers.get(&'"'))
                .or_else(|| self.registers.get(&'"').cloned()),
            '%' => Some(Register { text: self.doc().title(), linewise: false }),
            '/' => self.search.as_ref().map(|(pattern, _)| Register { text: pattern.clone(), linewise: false }),
            ':' => self.persisted.commands.last().map(|text| Register { text: text.clone(), linewise: false }),
            c => self.registers.get(&c.to_ascii_lowercase()).cloned(),
        }
    }

    // --- search ---------------------------------------------------------------------

    /// Vim-flavored pattern: smartcase, `\c`/`\C`, `\<` `\>` word bounds.
    pub fn compile_search(&self, pattern: &str) -> Result<Regex, String> {
        let mut pattern = pattern.to_string();
        let mut case_insensitive =
            self.options.ignorecase && !(self.options.smartcase && pattern.chars().any(char::is_uppercase));
        if pattern.contains("\\c") {
            pattern = pattern.replace("\\c", "");
            case_insensitive = true;
        }
        if pattern.contains("\\C") {
            pattern = pattern.replace("\\C", "");
            case_insensitive = false;
        }
        let pattern = pattern.replace("\\<", "\\b").replace("\\>", "\\b");
        RegexBuilder::new(&pattern)
            .case_insensitive(case_insensitive)
            .build()
            .or_else(|_| RegexBuilder::new(&regex::escape(&pattern)).case_insensitive(case_insensitive).build())
            .map_err(|error| error.to_string())
    }

    pub fn set_search(&mut self, pattern: &str, forward: bool) -> Result<(), String> {
        let regex = self.compile_search(pattern)?;
        self.search = Some((pattern.to_string(), forward));
        self.search_regex = Some(regex);
        self.hlsearch_active = true;
        self.persisted.add_search(pattern);
        Ok(())
    }

    /// The next match after (or before) `from`, wrapping around the file.
    pub fn find_match(&self, doc: &Document, from: Pos, forward: bool) -> Option<(Pos, Pos, bool)> {
        let regex = self.search_regex.as_ref()?;
        let lines = doc.text.len_lines();
        let matches_in = |line: usize| -> Vec<(usize, usize)> {
            let text = doc.text.line(line);
            regex
                .find_iter(text)
                .filter(|found| found.end() > found.start() || text.is_empty())
                .map(|found| (text[..found.start()].chars().count(), text[..found.end()].chars().count()))
                .collect()
        };
        for step in 0..=lines {
            let line = if forward { (from.line + step) % lines } else { (from.line + lines * 2 - step) % lines };
            let wrapped = if forward { from.line + step >= lines } else { step > from.line };
            let found = matches_in(line);
            let pick = if forward {
                found.into_iter().find(|(start, _)| step > 0 || *start > from.col)
            } else {
                found.into_iter().rev().find(|(start, _)| step > 0 || *start < from.col)
            };
            if let Some((start, end)) = pick {
                return Some((Pos::new(line, start), Pos::new(line, end), wrapped));
            }
            if step > 0 && line == from.line {
                break;
            }
        }
        None
    }

    pub fn search_next(&mut self, reverse: bool, count: usize) -> bool {
        let Some((pattern, forward)) = self.search.clone() else {
            self.error("no previous search");
            return false;
        };
        if self.search_regex.is_none() {
            if let Err(error) = self.set_search(&pattern, forward) {
                self.error(error);
                return false;
            }
        }
        let forward = forward != reverse;
        let mut cursor = self.cursor();
        let mut wrapped_any = false;
        for _ in 0..count.max(1) {
            match self.find_match(self.doc(), cursor, forward) {
                Some((start, _, wrapped)) => {
                    cursor = start;
                    wrapped_any |= wrapped;
                }
                None => {
                    self.error(format!("pattern not found: {pattern}"));
                    return false;
                }
            }
        }
        self.hlsearch_active = true;
        self.push_jump();
        self.set_cursor(cursor);
        let total = self.count_matches();
        let index = self.match_index(cursor);
        let prefix = if forward { "/" } else { "?" };
        let mut text = format!("{prefix}{pattern}  [{index}/{total}]");
        if wrapped_any {
            text.push_str(if forward { "  (wrapped to top)" } else { "  (wrapped to bottom)" });
        }
        self.info(text);
        true
    }

    pub fn count_matches(&self) -> usize {
        let Some(regex) = &self.search_regex else {
            return 0;
        };
        self.doc().text.lines().map(|line| regex.find_iter(line).filter(|found| !found.is_empty()).count()).sum()
    }

    fn match_index(&self, cursor: Pos) -> usize {
        let Some(regex) = &self.search_regex else {
            return 0;
        };
        let doc = self.doc();
        let mut index = 0;
        for line in 0..=cursor.line {
            let text = doc.text.line(line);
            for found in regex.find_iter(text) {
                let col = text[..found.start()].chars().count();
                if line < cursor.line || col <= cursor.col {
                    index += 1;
                }
            }
        }
        index
    }

    // --- files ------------------------------------------------------------------------------

    /// Saves a document (to `path` if given): trims, formats, writes, tells the LSP.
    pub fn save(&mut self, id: usize, path: Option<PathBuf>, force: bool) -> Result<String, String> {
        let Some(doc) = self.docs.get(&id) else {
            return Err("no such buffer".into());
        };
        let target = match path.map(|path| absolute(&path)).or_else(|| doc.path.clone()) {
            Some(path) => path,
            None => return Err("no file name: :w <path>".into()),
        };
        if doc.readonly && !force && doc.path.as_deref() == Some(target.as_path()) {
            return Err("the file is read-only (:w! to try anyway)".into());
        }
        if !force && doc.path.as_deref() == Some(target.as_path()) && doc.changed_on_disk() {
            return Err("the file changed on disk since it was opened (:w! overwrites, :e! reloads)".into());
        }
        if self.options.trim_trailing_whitespace {
            self.trim_trailing(id);
        }
        if let Err(error) = crate::format::on_save(self, id, &target) {
            self.warn(format!("format: {error}"));
        }
        let final_newline = self.options.final_newline;
        let doc = self.docs.get_mut(&id).expect("document");
        doc.save_to(&target, final_newline).map_err(|error| format!("{}: {error}", target.display()))?;
        let lines = doc.text.len_lines();
        let bytes = doc.text.byte_len() + usize::from(doc.final_newline);
        let name = display_path(&target);
        if doc.lang.is_none() {
            doc.lang = self.languages.detect(Some(&target), doc.text.line(0));
        }
        self.lsp_saved(id);
        let mut text = format!("\"{name}\" {lines}L, {bytes}B written");
        if let Some(check) = crate::ul::check_after_save(&target) {
            text = format!("{text} · {check}");
        }
        Ok(text)
    }

    fn trim_trailing(&mut self, id: usize) {
        let cursor = self.views.values().find(|view| view.doc == id).map_or(Pos::default(), |view| view.cursor);
        let doc = self.docs.get_mut(&id).expect("document");
        if doc
            .lang
            .and_then(|index| self.languages.get(index))
            .is_some_and(|lang| lang.kind == crate::syntax::Kind::Markdown)
        {
            // Two trailing spaces are a line break in Markdown.
            return;
        }
        doc.commit(cursor);
        for line in 0..doc.text.len_lines() {
            let text = doc.text.line(line);
            let trimmed = text.trim_end_matches([' ', '\t']).chars().count();
            let len = text.chars().count();
            // Leave the line the cursor is typing on alone.
            if trimmed < len && !(line == cursor.line && matches!(self.mode, Mode::Insert)) {
                doc.remove(Pos::new(line, trimmed), Pos::new(line, len), cursor);
            }
        }
        doc.commit(cursor);
    }

    pub fn modified_docs(&self) -> Vec<String> {
        let mut names: Vec<String> = self.docs.values().filter(|doc| doc.modified()).map(Document::title).collect();
        names.sort();
        names
    }

    /// Reloads files changed by other programs; reports conflicts for modified ones.
    pub fn check_disk_changes(&mut self) {
        if !self.options.auto_reload {
            return;
        }
        let ids: Vec<usize> = self.docs.keys().copied().collect();
        for id in ids {
            let doc = &self.docs[&id];
            if doc.path.is_none() || !doc.changed_on_disk() {
                continue;
            }
            if doc.path.as_ref().is_some_and(|path| !path.exists()) {
                continue;
            }
            if doc.modified() {
                let title = doc.title();
                let doc = self.docs.get_mut(&id).expect("document");
                doc.mtime = doc
                    .path
                    .as_ref()
                    .and_then(|path| std::fs::metadata(path).ok())
                    .and_then(|meta| meta.modified().ok());
                self.warn(format!("{title} changed on disk and here; :e! takes the disk version, :w! keeps yours"));
                continue;
            }
            let cursor = self.views.values().find(|view| view.doc == id).map_or(Pos::default(), |view| view.cursor);
            let result = self.docs.get_mut(&id).expect("document").reload(cursor);
            match result {
                Ok(()) => {
                    let title = self.docs[&id].title();
                    self.info(format!("{title} reloaded (changed on disk)"));
                    self.lsp_changed_all();
                }
                Err(error) => self.error(format!("reload: {error}")),
            }
        }
        for view in self.views.values_mut() {
            let doc = &self.docs[&view.doc];
            view.cursor = doc.text.clamp(view.cursor);
        }
    }

    // --- language servers (thin wrappers so the rest needs no lsp details) -----------------

    pub fn lsp_open(&mut self, doc: usize) {
        if !self.options.lsp {
            return;
        }
        let tx = self.tx.clone();
        if let Some(document) = self.docs.get(&doc) {
            if let Some(lang) = document.lang.and_then(|index| self.languages.get(index)) {
                if let Err(error) = self.lsp.open(document, lang, tx) {
                    self.warn(error);
                }
            }
        }
    }

    pub fn lsp_close(&mut self, doc: usize) {
        if let Some(document) = self.docs.get(&doc) {
            self.lsp.close(document);
        }
    }

    pub fn lsp_saved(&mut self, doc: usize) {
        if let Some(document) = self.docs.get(&doc) {
            self.lsp.saved(document);
        }
    }

    pub fn lsp_changed_all(&mut self) {
        let docs: Vec<&Document> = self.docs.values().collect();
        self.lsp.sync(&docs);
    }

    // --- persistence -------------------------------------------------------------------

    pub fn remember_positions(&mut self) {
        let mut positions = Vec::new();
        for view in self.views.values() {
            if let Some(path) = &self.docs[&view.doc].path {
                positions.push((path.clone(), view.cursor));
            }
        }
        for doc in self.docs.values() {
            if let Some(path) = &doc.path {
                if !self.views.values().any(|view| view.doc == doc.id) && doc.last_cursor != Pos::default() {
                    positions.push((path.clone(), doc.last_cursor));
                }
            }
        }
        for (path, pos) in positions {
            self.persisted.set_position(&path, pos);
        }
    }

    /// Text of the given selection range, honoring linewise selections.
    pub fn selection(&self) -> Option<(Pos, Pos, VisualKind)> {
        let Mode::Visual(kind) = self.mode else {
            return None;
        };
        let cursor = self.cursor();
        let (start, end) = (self.anchor.min(cursor), self.anchor.max(cursor));
        Some((start, end, kind))
    }

    /// Byte offset helper for callers that hold a line.
    pub fn byte_col(line: &str, col: usize) -> usize {
        byte_at(line, col)
    }

    pub fn idle_for(&self, since: Instant) -> Duration {
        Instant::now().saturating_duration_since(since)
    }

    pub fn pending_keys(&self) -> &[Key] {
        &self.vim.pending
    }
}
