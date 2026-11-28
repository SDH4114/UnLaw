//! `editing = "standard"`: ule without modes, like VS Code or Zed.
//!
//! The editor simply stays in insert mode: typing always types, and the keys of
//! ordinary editors (`standard.rs`) select, copy and undo. vim's normal mode is
//! never left on screen: whatever ends in it (Esc, a picker, a mouse click, a
//! command) is turned back into insert mode by `settle`. The few keys that only
//! exist in normal mode get editor shortcuts here: Ctrl-P files, Ctrl-Shift-P
//! (or F1) all commands, Ctrl-Shift-F search the project, Ctrl-B the file tree,
//! Ctrl-W close the file, Ctrl-` the output panel.

use crate::config::Editing;
use crate::editor::{Editor, Mode};
use crate::keys::{Code, Key};

/// Keys shown in help.
pub const KEYS: &[(&str, &str)] = &[
    ("Ctrl-P", "find a file"),
    ("Ctrl-Shift-P / F1", "all commands"),
    ("Ctrl-Shift-F", "search in the project"),
    ("Ctrl-B / Ctrl-Shift-E", "file tree"),
    ("Ctrl-W", "close the file"),
    ("Ctrl-`", "output panel"),
    ("Ctrl-Shift-O", "symbols in this file (LSP)"),
    ("F12", "go to definition (LSP)"),
    ("Ctrl-Shift-A", "select all (Ctrl-A is the line start: Ghostty sends it for Cmd-Left)"),
    ("Ctrl-D", "select the word; again: the next match too (another cursor)"),
    ("Ctrl-Shift-L", "a cursor on every match"),
    ("Ctrl-Alt-Up / Ctrl-Alt-Down", "another cursor above / below"),
    ("Ctrl-L", "select the line (again: the next one)"),
    ("Ctrl-] / Ctrl-[", "indent / outdent"),
    ("Ctrl-Enter / Ctrl-Shift-Enter", "new line below / above"),
    ("Ctrl-J / Ctrl-T", "join lines / transpose"),
    ("Ctrl-Shift-Right / Left", "expand / shrink the selection"),
    ("F3 / Shift-F3", "next / previous match"),
    ("Esc", "close a popup or drop the selection; never leaves typing"),
];

pub fn on(ed: &Editor) -> bool {
    ed.options.editing == Editing::Standard
}

/// Normal mode never stays on screen in the standard editing mode.
pub fn settle(ed: &mut Editor) {
    if on(ed) && ed.mode == Mode::Normal && ed.vim.pending.is_empty() && ed.vim.macro_recording.is_none() {
        crate::vim::begin_insert(ed);
    }
}

/// After the editing option changed (window settings, `:set editing=`): leaving the standard
/// mode drops what only it keeps (typing, a Shift selection, other cursors), as Esc would in
/// vim, so vim starts clean in normal mode; entering it starts typing at once.
pub fn switched(ed: &mut Editor, was: Editing) {
    let now = ed.options.editing;
    if now == was {
        return;
    }
    if now == Editing::Vim {
        ed.multi.clear();
        ed.completion = None;
        ed.vim.select_mode = false;
        if matches!(ed.mode, Mode::Insert | Mode::Visual(_)) {
            crate::vim::handle_key(ed, Key::plain(Code::Esc));
        }
    }
    settle(ed);
}

/// Shortcuts of the standard mode; false = not one of them (standard.rs and vim go on).
pub fn handle(ed: &mut Editor, key: Key) -> bool {
    if !on(ed) || !ed.vim.pending.is_empty() {
        return false;
    }
    if key.code == Code::Esc && !key.ctrl && !key.alt && ed.mode == Mode::Insert {
        // vim's Esc would leave insert mode and step the cursor back one char.
        ed.completion = None;
        return true;
    }
    let command = match (key.code, key.ctrl, key.alt, key.shift) {
        (Code::Char('p'), true, false, false) => "file_picker",
        (Code::Char('p'), true, false, true) | (Code::F(1), false, false, false) => "command_palette",
        (Code::Char('f'), true, false, true) => "grep",
        (Code::Char('b'), true, false, false) | (Code::Char('e'), true, false, true) => "explorer",
        (Code::Char('w'), true, false, false) => "buffer_close",
        (Code::Char('`'), true, false, _) => "panel",
        (Code::Char('o'), true, false, true) => "symbols",
        (Code::F(12), false, false, false) => "goto_definition",
        (Code::Char('a'), true, false, true) => "select_all",
        (Code::Char('d'), true, false, false) => "select_next_occurrence",
        (Code::Char('l'), true, false, true) => "select_all_occurrences",
        (Code::Char('l'), true, false, false) => "select_line",
        (Code::Char(']'), true, false, false) => "indent",
        (Code::Char('['), true, false, false) => "outdent",
        (Code::Enter, true, false, false) => "newline_below",
        (Code::Enter, true, false, true) => "newline_above",
        (Code::Char('j'), true, false, false) => "join_lines",
        (Code::Char('t'), true, false, false) => "transpose",
        (Code::Up, true, true, false) => "add_cursor_above",
        (Code::Down, true, true, false) => "add_cursor_below",
        (Code::Right, true, false, true) => "expand_selection",
        (Code::Left, true, false, true) => "shrink_selection",
        (Code::F(3), false, false, false) => "search_next",
        (Code::F(3), false, false, true) => "search_prev",
        _ => return false,
    };
    crate::edit::commit(ed);
    ed.completion = None;
    if let Err(error) = crate::commands::run(ed, command, &[], None, None) {
        ed.error(error);
    }
    true
}
