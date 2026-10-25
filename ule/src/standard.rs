//! Shortcuts of ordinary code editors on top of vim (`standard_keys = true`):
//! Ctrl-Z/Y undo/redo, Ctrl-C/X/V clipboard, Shift+arrows select, word and
//! line deletion, Alt+arrows move lines, Ctrl-F find, Ctrl-G go to line.
//!
//! Shift-selection is a "select mode": a visual selection whose end is
//! exclusive like other editors, where typing replaces the selection.
//! Bindings in ule.toml win over these keys; vim's own keys that they
//! replace moved: block visual Ctrl-Q / Alt-v, increment Alt-a / Alt-x.

use crate::edit;
use crate::editor::{Editor, Mode, VisualKind};
use crate::keymap::{KeyMode, Lookup};
use crate::keys::{Code, Key};
use crate::text::{class, CharClass, Pos};
use crate::widgets::{InputAction, Prompt, PromptKind};

/// Keys shown in help and the key picker.
pub const KEYS: &[(&str, &str)] = &[
    ("Ctrl-Z / Ctrl-Y", "undo / redo (Ctrl-Shift-Z redoes too)"),
    ("Ctrl-C / Ctrl-X", "copy / cut the selection, or the whole line without one"),
    ("Ctrl-V", "paste (a copied line goes above the cursor line)"),
    ("Ctrl-A", "select all (in insert mode: line start, like Cmd-Left)"),
    ("Shift + arrows", "select; Shift+Home/End, Ctrl/Alt+Shift+Left/Right by word"),
    ("typing on a selection", "replaces it; Backspace/Delete removes it"),
    ("Ctrl/Alt + Backspace", "delete the word on the left"),
    ("Ctrl/Alt + Delete, Alt-D", "delete the word on the right"),
    ("Cmd-Backspace (Ctrl-U)", "delete to the line start"),
    ("Ctrl-K / Ctrl-Shift-K", "delete to the line end / delete the line"),
    ("Ctrl/Alt + Left/Right", "move by word (Alt-B / Alt-F too)"),
    ("Home / End", "first char (again: column 0) / line end; Ctrl+Home/End: file"),
    ("Alt + Up/Down", "move the line or selected lines"),
    ("Alt+Shift + Up/Down", "duplicate the line or selected lines"),
    ("Tab / Shift-Tab on a selection", "indent / dedent"),
    ("Ctrl-/", "comment the line or selection"),
    ("Ctrl-F / Ctrl-G", "find / go to line"),
    ("Ctrl-S", "save"),
    ("Ctrl-Q / Alt-V, Alt-A / Alt-X", "vim's block visual and increment/decrement moved here"),
];

fn is(key: Key, code: Code, ctrl: bool, alt: bool, shift: bool) -> bool {
    key.code == code && key.ctrl == ctrl && key.alt == alt && key.shift == shift
}

/// The selection as an exclusive range: (start, end, linewise).
pub fn range(ed: &Editor) -> Option<(Pos, Pos, bool)> {
    let Mode::Visual(kind) = ed.mode else {
        return None;
    };
    let cursor = ed.cursor();
    let (start, end) = (ed.anchor.min(cursor), ed.anchor.max(cursor));
    let text = &ed.doc().text;
    if ed.vim.select_mode {
        return (start != end).then_some((start, end, false));
    }
    Some(match kind {
        VisualKind::Line => (Pos::new(start.line, 0), Pos::new(end.line, text.line_len(end.line)), true),
        _ => (start, text.next(end).unwrap_or(text.end()), false),
    })
}

fn selected_text(ed: &Editor) -> Option<(String, bool)> {
    let (start, end, linewise) = range(ed)?;
    let text = ed.doc().text.slice(start, end);
    Some(if linewise { (format!("{text}\n"), true) } else { (text, false) })
}

/// Leaves select/visual mode back to where the selection started.
fn end_selection(ed: &mut Editor) {
    let back_to_insert = ed.vim.select_mode && ed.vim.select_from_insert;
    if let Mode::Visual(kind) = ed.mode {
        ed.last_visual = Some((ed.view().doc, ed.anchor, ed.cursor(), kind));
    }
    ed.vim.select_mode = false;
    ed.vim.select_from_insert = false;
    ed.mode = if back_to_insert { Mode::Insert } else { Mode::Normal };
    ed.clamp_cursor();
}

/// Deletes the selection (if any); the cursor goes to its start, in insert mode.
fn delete_selection(ed: &mut Editor) -> bool {
    let Some((start, end, linewise)) = range(ed) else {
        return false;
    };
    let cursor = ed.cursor();
    let (start, end) = if linewise {
        // Whole lines: take the line break too.
        let last = ed.doc().text.last_line();
        if end.line < last {
            (start, Pos::new(end.line + 1, 0))
        } else if start.line > 0 {
            (Pos::new(start.line - 1, ed.doc().text.line_len(start.line - 1)), end)
        } else {
            (start, end)
        }
    } else {
        (start, end)
    };
    edit::commit(ed);
    ed.doc_mut().remove(start, end, cursor);
    ed.vim.select_mode = false;
    ed.vim.select_from_insert = false;
    ed.mode = Mode::Insert;
    ed.view_mut().cursor = ed.doc().text.clamp(start);
    true
}

fn copy(ed: &mut Editor, text: String, linewise: bool) {
    ed.set_register(None, text.clone(), linewise, true);
    // Ctrl-C always reaches the macOS clipboard, whatever `clipboard` says.
    ed.set_register(Some('+'), text, linewise, true);
}

fn paste(ed: &mut Editor) {
    let Some(register) = ed.get_register(Some('+')).or_else(|| ed.get_register(None)) else {
        ed.info("the clipboard is empty");
        return;
    };
    edit::commit(ed);
    let had_selection = matches!(ed.mode, Mode::Visual(_));
    if had_selection {
        delete_selection(ed);
    }
    let insert_after = matches!(ed.mode, Mode::Insert | Mode::Replace);
    let cursor = ed.cursor();
    if register.linewise && !had_selection {
        // A copied line goes above the cursor's line, like other editors.
        let mut text = register.text.clone();
        if !text.ends_with('\n') {
            text.push('\n');
        }
        let added = text.matches('\n').count();
        ed.doc_mut().insert(Pos::new(cursor.line, 0), &text, cursor);
        ed.view_mut().cursor = Pos::new(cursor.line + added, cursor.col);
    } else {
        let at = if !insert_after && ed.mode == Mode::Normal && ed.doc().text.line_len(cursor.line) > 0 {
            Pos::new(cursor.line, cursor.col + 1)
        } else {
            cursor
        };
        let end = ed.doc_mut().insert(at, &register.text, cursor);
        ed.view_mut().cursor = end;
        if ed.mode == Mode::Normal {
            ed.view_mut().cursor = Pos::new(end.line, end.col.saturating_sub(1));
        }
    }
    edit::commit(ed);
    ed.clamp_cursor();
}

fn word_right(ed: &Editor, pos: Pos) -> Pos {
    let text = &ed.doc().text;
    let mut current = pos;
    // Skip what is not a word, then the word: ends right after it.
    while let Some(c) = text.char_at(current) {
        if class(c) == CharClass::Word {
            break;
        }
        if c == '\n' && current != pos {
            return current;
        }
        match text.next(current) {
            Some(next) => current = next,
            None => return current,
        }
    }
    while let Some(c) = text.char_at(current) {
        if class(c) != CharClass::Word {
            break;
        }
        match text.next(current) {
            Some(next) => current = next,
            None => return text.end(),
        }
    }
    current
}

fn word_left(ed: &Editor, pos: Pos) -> Pos {
    if pos.col == 0 && pos.line > 0 {
        return Pos::new(pos.line - 1, ed.doc().text.line_len(pos.line - 1));
    }
    crate::motion::word_back(&ed.doc().text, pos, false).max(Pos::new(pos.line, 0))
}

fn smart_home(ed: &Editor, pos: Pos) -> Pos {
    let first = ed.doc().text.first_non_blank(pos.line);
    Pos::new(pos.line, if pos.col == first { 0 } else { first })
}

enum Move {
    Left,
    Right,
    Up,
    Down,
    WordLeft,
    WordRight,
    Home,
    End,
    PageUp,
    PageDown,
    FileStart,
    FileEnd,
}

fn target(ed: &mut Editor, movement: &Move) -> Pos {
    let cursor = ed.cursor();
    let text = &ed.doc().text;
    match movement {
        Move::Left => text.prev(cursor).unwrap_or(cursor),
        Move::Right => text.next(cursor).unwrap_or(cursor),
        Move::WordLeft => word_left(ed, cursor),
        Move::WordRight => word_right(ed, cursor),
        Move::Home => smart_home(ed, cursor),
        Move::End => Pos::new(cursor.line, text.line_len(cursor.line)),
        Move::FileStart => Pos::default(),
        Move::FileEnd => text.end(),
        Move::Up | Move::Down | Move::PageUp | Move::PageDown => {
            let height = ed.view().area.h.max(2) as isize - 2;
            let delta = match movement {
                Move::Up => -1,
                Move::Down => 1,
                Move::PageUp => -height,
                _ => height,
            };
            // Vertical moves keep the column; with a selection the line end is reachable.
            let mode = ed.mode;
            ed.mode = Mode::Insert;
            ed.move_lines(delta);
            ed.mode = mode;
            let moved = ed.cursor();
            ed.view_mut().cursor = cursor;
            moved
        }
    }
}

/// Shift+movement: starts or extends the selection.
fn select(ed: &mut Editor, movement: Move) {
    if !ed.vim.select_mode {
        let from_insert = matches!(ed.mode, Mode::Insert | Mode::Replace);
        if from_insert {
            edit::commit(ed);
        }
        if !matches!(ed.mode, Mode::Visual(_)) {
            ed.anchor = ed.cursor();
        }
        ed.vim.select_mode = true;
        ed.vim.select_from_insert = from_insert || ed.vim.select_from_insert;
        ed.mode = Mode::Visual(VisualKind::Char);
    }
    let want = ed.view().want_col;
    let to = target(ed, &movement);
    ed.view_mut().cursor = to;
    if matches!(movement, Move::Up | Move::Down | Move::PageUp | Move::PageDown) {
        ed.view_mut().want_col = want.or(ed.view().want_col);
    } else {
        ed.view_mut().want_col = None;
    }
    if ed.anchor == ed.cursor() {
        // Back to nothing selected.
        end_selection(ed);
    }
}

/// A plain movement in insert mode (or one that ends a shift-selection).
fn go(ed: &mut Editor, movement: Move) {
    if ed.vim.select_mode {
        let (start, end) = (ed.anchor.min(ed.cursor()), ed.anchor.max(ed.cursor()));
        end_selection(ed);
        // Left/Right on a selection land on its edge, like other editors.
        match movement {
            Move::Left | Move::Right => {
                ed.view_mut().cursor = if matches!(movement, Move::Left) { start } else { end };
                ed.clamp_cursor();
                return;
            }
            _ => {}
        }
    }
    edit::commit(ed);
    ed.completion = None;
    let want = ed.view().want_col;
    let to = target(ed, &movement);
    ed.view_mut().cursor = to;
    if matches!(movement, Move::Up | Move::Down | Move::PageUp | Move::PageDown) {
        ed.view_mut().want_col = want.or(ed.view().want_col);
    } else {
        ed.view_mut().want_col = None;
    }
    ed.clamp_cursor();
}

fn lines_of_selection(ed: &Editor) -> (usize, usize) {
    match ed.mode {
        Mode::Visual(_) => {
            let cursor = ed.cursor();
            let (start, end) = (ed.anchor.min(cursor), ed.anchor.max(cursor));
            // An exclusive end at column 0 does not take that line.
            let last =
                if ed.vim.select_mode && end.col == 0 && end.line > start.line { end.line - 1 } else { end.line };
            (start.line, last)
        }
        _ => (ed.cursor().line, ed.cursor().line),
    }
}

fn duplicate(ed: &mut Editor, down: bool) {
    let (first, last) = lines_of_selection(ed);
    let block = edit::lines_text(ed, first, last);
    let cursor = ed.cursor();
    edit::commit(ed);
    let count = last - first + 1;
    ed.doc_mut().insert(Pos::new(first, 0), &block, cursor);
    if down {
        let shift = |pos: Pos| Pos::new(pos.line + count, pos.col);
        ed.view_mut().cursor = shift(cursor);
        if matches!(ed.mode, Mode::Visual(_)) {
            ed.anchor = shift(ed.anchor);
        }
    }
    edit::commit(ed);
}

fn move_block(ed: &mut Editor, down: bool) {
    let (first, last) = lines_of_selection(ed);
    let cursor = ed.cursor();
    edit::commit(ed);
    if edit::move_lines(ed, first, last, down) {
        let shift = |pos: Pos| Pos::new(if down { pos.line + 1 } else { pos.line - 1 }, pos.col);
        ed.view_mut().cursor = shift(cursor);
        if matches!(ed.mode, Mode::Visual(_)) {
            ed.anchor = shift(ed.anchor);
        }
    }
    edit::commit(ed);
}

fn undo(ed: &mut Editor, redo: bool) {
    let insert = matches!(ed.mode, Mode::Insert | Mode::Replace);
    if matches!(ed.mode, Mode::Visual(_)) {
        end_selection(ed);
    }
    let cursor = ed.cursor();
    let result = if redo { ed.doc_mut().redo(cursor) } else { ed.doc_mut().undo(cursor) };
    match result {
        Some(pos) => {
            ed.view_mut().cursor = ed.doc().text.clamp(pos);
            if !insert {
                ed.clamp_cursor();
            }
        }
        None => ed.info(if redo { "already at the newest change" } else { "already at the oldest change" }),
    }
}

/// Handles a standard-editor key; returns false to let vim have it.
pub fn handle(ed: &mut Editor, key: Key) -> bool {
    let mode = match ed.mode {
        Mode::Visual(_) => KeyMode::Visual,
        Mode::Insert | Mode::Replace => KeyMode::Insert,
        Mode::Normal => KeyMode::Normal,
    };
    // Bindings in ule.toml (and the defaults) come first.
    if !matches!(ed.keymap.lookup(mode, &[key]), Lookup::None) {
        return false;
    }
    let insert = mode == KeyMode::Insert;
    let selecting = ed.vim.select_mode;
    // Ctrl-Y accepts a completion, as in vim.
    if insert && ed.completion.is_some() && key == Key::ctrl('y') {
        return false;
    }
    let ctrl = |c: char| is(key, Code::Char(c), true, false, false);
    // Typing over a shift-selection replaces it.
    if selecting {
        match key.code {
            Code::Char(c) if !key.ctrl && !key.alt => {
                delete_selection(ed);
                edit::type_char(ed, c);
                return true;
            }
            Code::Enter if !key.ctrl && !key.alt => {
                delete_selection(ed);
                edit::newline(ed);
                return true;
            }
            Code::Backspace | Code::Delete if !key.alt && !key.ctrl => {
                delete_selection(ed);
                return true;
            }
            Code::Esc => {
                end_selection(ed);
                return true;
            }
            _ => {}
        }
    }
    // Clipboard and history.
    if ctrl('z') {
        undo(ed, false);
        return true;
    }
    if ctrl('y') || is(key, Code::Char('z'), true, false, true) {
        undo(ed, true);
        return true;
    }
    if ctrl('c') || ctrl('x') {
        let cut = ctrl('x');
        match selected_text(ed) {
            Some((text, linewise)) => {
                copy(ed, text, linewise);
                if cut {
                    delete_selection(ed);
                    if !selecting && !ed.vim.select_from_insert {
                        // Cut from vim's visual mode ends in normal mode.
                        ed.mode = Mode::Normal;
                        ed.clamp_cursor();
                    }
                } else if !selecting {
                    end_selection(ed);
                }
            }
            None => {
                // Nothing selected: the whole line, like VS Code.
                let line = ed.cursor().line;
                let text = edit::lines_text(ed, line, line);
                copy(ed, text, true);
                if cut {
                    let cursor = ed.cursor();
                    edit::commit(ed);
                    let (from, to) = if line < ed.doc().text.last_line() {
                        (Pos::new(line, 0), Pos::new(line + 1, 0))
                    } else if line > 0 {
                        (
                            Pos::new(line - 1, ed.doc().text.line_len(line - 1)),
                            Pos::new(line, ed.doc().text.line_len(line)),
                        )
                    } else {
                        (Pos::new(0, 0), Pos::new(0, ed.doc().text.line_len(0)))
                    };
                    ed.doc_mut().remove(from, to, cursor);
                    edit::commit(ed);
                    let line = line.min(ed.doc().text.last_line());
                    let col = cursor.col.min(ed.doc().text.line_len(line));
                    ed.view_mut().cursor = Pos::new(line, col);
                    ed.clamp_cursor();
                }
                ed.info(if cut { "line cut" } else { "line copied" });
            }
        }
        return true;
    }
    if ctrl('v') {
        paste(ed);
        return true;
    }
    if ctrl('a') {
        if insert {
            go(ed, Move::Home);
        } else {
            let end = ed.doc().text.end();
            ed.anchor = Pos::default();
            ed.vim.select_mode = true;
            ed.vim.select_from_insert = false;
            ed.mode = Mode::Visual(VisualKind::Char);
            ed.view_mut().cursor = end;
        }
        return true;
    }
    if ctrl('f') {
        if matches!(ed.mode, Mode::Visual(_)) {
            end_selection(ed);
        }
        let cursor = ed.cursor();
        let scroll = ed.view().scroll;
        ed.prompt = Some(Prompt::new(PromptKind::Search { forward: true, origin: cursor, scroll }, ""));
        return true;
    }
    if ctrl('g') {
        ed.prompt =
            Some(Prompt::new(PromptKind::Input { title: "Go to line".into(), action: InputAction::GotoLine }, ""));
        return true;
    }
    if ctrl('/') || ctrl('_') {
        let (first, last) = lines_of_selection(ed);
        edit::commit(ed);
        edit::toggle_comment(ed, first, last);
        edit::commit(ed);
        return true;
    }
    // Moving and duplicating lines.
    match (key.code, key.ctrl, key.alt, key.shift) {
        (Code::Up, false, true, false) | (Code::Down, false, true, false) => {
            move_block(ed, key.code == Code::Down);
            return true;
        }
        (Code::Up, false, true, true) | (Code::Down, false, true, true) => {
            duplicate(ed, key.code == Code::Down);
            return true;
        }
        _ => {}
    }
    // Shift-selection in every mode.
    let shifted = match (key.code, key.ctrl, key.alt, key.shift) {
        (Code::Left, false, false, true) => Some(Move::Left),
        (Code::Right, false, false, true) => Some(Move::Right),
        (Code::Up, false, false, true) => Some(Move::Up),
        (Code::Down, false, false, true) => Some(Move::Down),
        (Code::Left, _, _, true) => Some(Move::WordLeft),
        (Code::Right, _, _, true) => Some(Move::WordRight),
        (Code::Home, true, _, true) => Some(Move::FileStart),
        (Code::End, true, _, true) => Some(Move::FileEnd),
        (Code::Home, false, _, true) => Some(Move::Home),
        (Code::End, false, _, true) => Some(Move::End),
        (Code::PageUp, _, _, true) => Some(Move::PageUp),
        (Code::PageDown, _, _, true) => Some(Move::PageDown),
        _ => None,
    };
    if let Some(movement) = shifted {
        select(ed, movement);
        return true;
    }
    // Tab on a selection indents it.
    if matches!(ed.mode, Mode::Visual(_)) && matches!(key.code, Code::Tab | Code::BackTab) && !key.ctrl && !key.alt {
        let (first, last) = lines_of_selection(ed);
        edit::commit(ed);
        edit::shift_lines(ed, first, last, key.code == Code::Tab, 1);
        edit::commit(ed);
        return true;
    }
    // A selection ends with plain movement keys.
    if selecting {
        let movement = match (key.code, key.ctrl || key.alt) {
            (Code::Left, false) => Some(Move::Left),
            (Code::Right, false) => Some(Move::Right),
            (Code::Up, false) => Some(Move::Up),
            (Code::Down, false) => Some(Move::Down),
            (Code::Home, false) => Some(Move::Home),
            (Code::End, false) => Some(Move::End),
            _ => None,
        };
        if let Some(movement) = movement {
            go(ed, movement);
            return true;
        }
    }
    // Ctrl+Home/End anywhere.
    if !key.shift && key.ctrl && matches!(key.code, Code::Home | Code::End) {
        if !insert {
            ed.push_jump();
        }
        let to = if key.code == Code::Home { Pos::default() } else { ed.doc().text.end() };
        ed.view_mut().cursor = to;
        ed.clamp_cursor();
        return true;
    }
    if !insert {
        // Word jumps that terminals send for Option+arrows.
        match (key.code, key.ctrl, key.alt) {
            (Code::Left, true, false) | (Code::Left, false, true) | (Code::Char('b'), false, true) => {
                let to = word_left(ed, ed.cursor());
                ed.set_cursor(to);
                return true;
            }
            (Code::Right, true, false) | (Code::Right, false, true) | (Code::Char('f'), false, true) => {
                let to = word_right(ed, ed.cursor());
                ed.set_cursor(to);
                return true;
            }
            _ => return false,
        }
    }
    // Insert mode editing keys.
    let cursor = ed.cursor();
    match (key.code, key.ctrl, key.alt, key.shift) {
        (Code::Backspace, true, false, _) => edit::delete_word_back(ed),
        (Code::Delete, true, false, _) | (Code::Delete, false, true, _) | (Code::Char('d'), false, true, false) => {
            let end = word_right(ed, cursor);
            if end > cursor {
                ed.doc_mut().remove(cursor, end, cursor);
            }
        }
        (Code::Char('k'), true, false, false) => {
            let len = ed.doc().text.line_len(cursor.line);
            if cursor.col < len {
                ed.doc_mut().remove(cursor, Pos::new(cursor.line, len), cursor);
            } else if let Some(next) = ed.doc().text.next(cursor) {
                // At the line end Ctrl-K joins the next line, like Emacs and macOS.
                ed.doc_mut().remove(cursor, next, cursor);
            }
        }
        (Code::Char('k'), true, false, true) => {
            let line = cursor.line;
            let last = ed.doc().text.last_line();
            let (from, to) = if line < last {
                (Pos::new(line, 0), Pos::new(line + 1, 0))
            } else if line > 0 {
                (Pos::new(line - 1, ed.doc().text.line_len(line - 1)), Pos::new(line, ed.doc().text.line_len(line)))
            } else {
                (Pos::new(0, 0), Pos::new(0, ed.doc().text.line_len(0)))
            };
            ed.doc_mut().remove(from, to, cursor);
            let line = line.min(ed.doc().text.last_line());
            ed.view_mut().cursor = Pos::new(line, cursor.col.min(ed.doc().text.line_len(line)));
        }
        (Code::Char('e'), true, false, false) => go(ed, Move::End),
        (Code::Left, true, false, false) | (Code::Left, false, true, false) | (Code::Char('b'), false, true, false) => {
            go(ed, Move::WordLeft)
        }
        (Code::Right, true, false, false)
        | (Code::Right, false, true, false)
        | (Code::Char('f'), false, true, false) => go(ed, Move::WordRight),
        (Code::Home, false, false, false) => go(ed, Move::Home),
        (Code::PageUp, false, false, false) => go(ed, Move::PageUp),
        (Code::PageDown, false, false, false) => go(ed, Move::PageDown),
        _ => return false,
    }
    crate::complete::refilter(ed);
    true
}

/// Turning Ctrl-C/V into clipboard keys must not trap vim users: these stay vim.
pub fn enabled(ed: &Editor) -> bool {
    ed.options.standard_keys && ed.vim.pending.is_empty() && ed.vim.insert_pending.is_empty() && !ed.vim.insert_register
}
