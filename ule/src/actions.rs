//! Text actions of Zed and other code editors on top of ule's ordinary-editor keys:
//! several cursors (Cmd-D, Cmd-Shift-L, Cmd-Alt-Up/Down), select line, expand the
//! selection, indent with Cmd-]/[, new line above/below, join, change case, transpose,
//! find next/previous, jumps. Each is a named command (palette, ule.toml, the window).
//!
//! Several cursors: the primary one is ule's own cursor (and its shift-selection);
//! the others are `Editor::multi` as (anchor, head) pairs with an exclusive end, valid
//! for the document `Editor::multi_doc`. While there are others, typing, deleting,
//! moving, copying and pasting act on all of them (`key`, `type_text`); any other key
//! drops them, as Esc does.

use crate::edit;
use crate::editor::{Editor, Mode, VisualKind};
use crate::keys::{Code, Key};
use crate::standard::{self, Move};
use crate::text::{class, CharClass, Pos, Text};

pub const ACTIONS: &[(&str, &str)] = &[
    ("select_all", "select the whole file"),
    ("select_line", "select the line; again: the next line too"),
    ("indent", "indent the line or the selected lines"),
    ("outdent", "outdent the line or the selected lines"),
    ("newline_below", "start a new line below, wherever the cursor is"),
    ("newline_above", "start a new line above"),
    ("join_lines", "join the next line onto this one"),
    ("uppercase", "the selection (or word) in upper case"),
    ("lowercase", "the selection (or word) in lower case"),
    ("transpose", "swap the characters around the cursor"),
    ("expand_selection", "select the word, then inside the brackets or quotes, then with them, the line, the file"),
    ("shrink_selection", "back to the selection before the last expand"),
    ("select_next_occurrence", "select the word; again: add the next match as another cursor"),
    ("select_all_occurrences", "a cursor on every match of the selection or word"),
    ("add_cursor_above", "another cursor on the line above"),
    ("add_cursor_below", "another cursor on the line below"),
    ("single_cursor", "drop the other cursors"),
    ("search_next", "the next match of the last search"),
    ("search_prev", "the previous match of the last search"),
    ("search_selection", "search for the selection (or word)"),
    ("replace", "replace in the file (:%s with the selection)"),
    ("jump_back", "back to where the cursor was"),
    ("jump_forward", "forward again after jump_back"),
];

pub fn is(name: &str) -> bool {
    ACTIONS.iter().any(|(known, _)| *known == name)
}

// ---------- selections ----------

/// The primary selection as (anchor, head), exclusive end; anchor == head: just a cursor.
fn primary(ed: &Editor) -> (Pos, Pos) {
    let cursor = ed.cursor();
    match ed.mode {
        Mode::Visual(_) if ed.vim.select_mode => (ed.anchor, cursor),
        Mode::Visual(_) => {
            // vim's visual selection includes its last char.
            let text = &ed.doc().text;
            let after = |pos: Pos| text.next(pos).unwrap_or(text.end());
            if ed.anchor <= cursor {
                (ed.anchor, after(cursor))
            } else {
                (after(ed.anchor), cursor)
            }
        }
        _ => (cursor, cursor),
    }
}

fn set_primary(ed: &mut Editor, anchor: Pos, head: Pos) {
    let text = &ed.doc().text;
    let (anchor, head) = (text.clamp(anchor), text.clamp(head));
    if anchor == head {
        ed.vim.select_mode = false;
        ed.vim.select_from_insert = false;
        if ed.mode != Mode::Insert {
            ed.mode = Mode::Normal;
            crate::vim::begin_insert(ed);
        }
        ed.view_mut().cursor = head;
    } else {
        ed.anchor = anchor;
        ed.view_mut().cursor = head;
        ed.vim.select_mode = true;
        ed.vim.select_from_insert = true;
        ed.mode = Mode::Visual(VisualKind::Char);
    }
}

pub fn multi_active(ed: &Editor) -> bool {
    !ed.multi.is_empty() && ed.multi_doc == ed.view().doc
}

/// Every selection, the primary first.
fn all(ed: &Editor) -> Vec<(Pos, Pos)> {
    let mut sels = vec![primary(ed)];
    if multi_active(ed) {
        sels.extend(ed.multi.iter().copied());
    }
    sels
}

/// Makes `sels` the selections (the first is the primary); ones on the same spot merge.
fn store(ed: &mut Editor, sels: Vec<(Pos, Pos)>) {
    let Some(&(anchor, head)) = sels.first() else { return };
    set_primary(ed, anchor, head);
    let text = &ed.doc().text;
    let mut rest: Vec<(Pos, Pos)> = Vec::new();
    for (anchor, head) in sels.into_iter().skip(1) {
        let (anchor, head) = (text.clamp(anchor), text.clamp(head));
        if head != ed.view().cursor && !rest.iter().any(|(_, other)| *other == head) {
            rest.push((anchor, head));
        }
    }
    ed.multi = rest;
    ed.multi_doc = ed.view().doc;
}

/// Every selection of the current document, for `add_to`.
pub fn snapshot(ed: &Editor) -> (usize, Vec<(Pos, Pos)>) {
    (ed.view().doc, all(ed))
}

/// After a click moved the cursor: the earlier selections stay as other cursors.
pub fn add_to(ed: &mut Editor, (doc, before): (usize, Vec<(Pos, Pos)>)) {
    if doc != ed.view().doc {
        return;
    }
    let head = ed.cursor();
    let mut sels = vec![(head, head)];
    sels.extend(before.into_iter().filter(|(_, other)| *other != head));
    store(ed, sels);
}

pub fn clear(ed: &mut Editor) {
    ed.multi.clear();
}

/// Extra selections of this document for drawing: (start, end, head).
pub fn extra_for(ed: &Editor, doc: usize) -> Vec<(Pos, Pos, Pos)> {
    if ed.multi_doc != doc {
        return Vec::new();
    }
    ed.multi.iter().map(|(anchor, head)| ((*anchor).min(*head), (*anchor).max(*head), *head)).collect()
}

// ---------- offsets ----------

/// Char offsets of each line start.
fn starts(text: &Text) -> Vec<usize> {
    let mut starts = Vec::with_capacity(text.len_lines());
    let mut at = 0;
    for line in 0..text.len_lines() {
        starts.push(at);
        at += text.line_len(line) + 1;
    }
    starts
}

fn offset(starts: &[usize], pos: Pos) -> usize {
    starts.get(pos.line).copied().unwrap_or(0) + pos.col
}

fn pos_at(starts: &[usize], offset: usize) -> Pos {
    let line = starts.partition_point(|start| *start <= offset).saturating_sub(1);
    Pos::new(line, offset - starts[line])
}

/// Replaces (from, to) of every selection with its text, bottom first, as one undo step;
/// each cursor ends after its inserted text (`keep` = keep the replaced text selected).
fn edit_all(ed: &mut Editor, keep: bool, change: impl Fn(&Editor, (Pos, Pos)) -> (Pos, Pos, String)) {
    let sels = all(ed);
    let mut edits: Vec<(Pos, Pos, String, usize)> = sels
        .iter()
        .enumerate()
        .map(|(index, sel)| {
            let (from, to, text) = change(ed, *sel);
            (from.min(to), from.max(to), text, index)
        })
        .collect();
    edits.sort_by_key(|edit| edit.0);
    // Overlapping edits (two cursors deleting into each other) apply once.
    let mut kept: Vec<(Pos, Pos, String, usize)> = Vec::new();
    for edit in edits {
        if kept.last().is_some_and(|last| edit.0 < last.1 || (edit.0 == last.0 && edit.1 == last.1)) {
            continue;
        }
        kept.push(edit);
    }
    let before = starts(&ed.doc().text);
    let spans: Vec<(usize, usize)> =
        kept.iter().map(|(from, to, _, _)| (offset(&before, *from), offset(&before, *to))).collect();
    edit::commit(ed);
    let cursor = ed.cursor();
    for (from, to, text, _) in kept.iter().rev() {
        if from != to {
            ed.doc_mut().remove(*from, *to, cursor);
        }
        if !text.is_empty() {
            ed.doc_mut().insert(*from, text, cursor);
        }
    }
    edit::commit(ed);
    let after = starts(&ed.doc().text);
    let mut delta: isize = 0;
    let mut placed: Vec<(usize, (Pos, Pos))> = Vec::new();
    for ((from, to), (_, _, text, index)) in spans.iter().zip(&kept) {
        let start = (*from as isize + delta) as usize;
        let length = text.chars().count();
        let head = pos_at(&after, start + length);
        let anchor = if keep { pos_at(&after, start) } else { head };
        placed.push((*index, (anchor, head)));
        delta += length as isize - (to - from) as isize;
    }
    placed.sort_by_key(|(index, _)| if *index == 0 { 0 } else { 1 });
    ed.multi.clear();
    store(ed, placed.into_iter().map(|(_, sel)| sel).collect());
}

/// Text typed (or pasted) at every cursor.
pub fn type_text(ed: &mut Editor, typed: &str) {
    let pieces: Vec<&str> = typed.split('\n').collect();
    let count = all(ed).len();
    // As many pasted lines as cursors: one line each, like Zed.
    if count > 1 && pieces.len() == count {
        let order = all(ed);
        edit_all(ed, false, |_, (anchor, head)| {
            let index = order.iter().position(|sel| *sel == (anchor, head)).unwrap_or(0);
            (anchor, head, pieces[index].to_string())
        });
        return;
    }
    edit_all(ed, false, |_, (anchor, head)| (anchor, head, typed.to_string()));
}

fn moved(ed: &mut Editor, pos: Pos, movement: &Move) -> Pos {
    let text = &ed.doc().text;
    match movement {
        Move::Up => {
            if pos.line == 0 {
                Pos::default()
            } else {
                Pos::new(pos.line - 1, pos.col.min(text.line_len(pos.line - 1)))
            }
        }
        Move::Down => {
            if pos.line >= text.last_line() {
                text.end()
            } else {
                Pos::new(pos.line + 1, pos.col.min(text.line_len(pos.line + 1)))
            }
        }
        _ => {
            let saved = ed.view().cursor;
            ed.view_mut().cursor = pos;
            let to = standard::target(ed, movement);
            ed.view_mut().cursor = saved;
            to
        }
    }
}

/// Keys while there are several cursors; false = not handled here (the others are dropped).
pub fn key(ed: &mut Editor, key: Key) -> bool {
    if !multi_active(ed) {
        return false;
    }
    let plain = !key.ctrl && !key.alt;
    match key.code {
        Code::Esc => {
            clear(ed);
            return true;
        }
        Code::Char(c) if plain => {
            type_text(ed, &c.to_string());
            return true;
        }
        Code::Enter if plain => {
            edit_all(ed, false, |ed, (anchor, head)| {
                let from = anchor.min(head);
                let line = ed.doc().text.line(from.line);
                let indent: String = line.chars().take_while(|c| *c == ' ' || *c == '\t').collect();
                (anchor, head, format!("\n{indent}"))
            });
            return true;
        }
        Code::Tab if plain && !key.shift => {
            let unit = if ed.options.expand_tab { " ".repeat(ed.options.tab_width) } else { "\t".into() };
            type_text(ed, &unit);
            return true;
        }
        Code::Backspace | Code::Delete => {
            let back = key.code == Code::Backspace;
            let word = key.ctrl || key.alt;
            edit_all(ed, false, |ed, (anchor, head)| {
                if anchor != head {
                    return (anchor, head, String::new());
                }
                let text = &ed.doc().text;
                let other = match (back, word) {
                    (true, false) => text.prev(head).unwrap_or(head),
                    (false, false) => text.next(head).unwrap_or(head),
                    (true, true) => standard::word_left(ed, head),
                    (false, true) => standard::word_right(ed, head),
                };
                (other, head, String::new())
            });
            return true;
        }
        _ => {}
    }
    let movement = match (key.code, key.ctrl, key.alt) {
        (Code::Left, false, false) => Some(Move::Left),
        (Code::Right, false, false) => Some(Move::Right),
        (Code::Up, false, false) => Some(Move::Up),
        (Code::Down, false, false) => Some(Move::Down),
        (Code::Left, _, true) | (Code::Left, true, false) => Some(Move::WordLeft),
        (Code::Right, _, true) | (Code::Right, true, false) => Some(Move::WordRight),
        (Code::Home, true, _) => Some(Move::FileStart),
        (Code::End, true, _) => Some(Move::FileEnd),
        (Code::Home, false, _) => Some(Move::Home),
        (Code::End, false, _) => Some(Move::End),
        _ => None,
    };
    if let Some(movement) = movement {
        edit::commit(ed);
        let sels: Vec<(Pos, Pos)> = all(ed)
            .into_iter()
            .map(|(anchor, head)| {
                if !key.shift && anchor != head && matches!(movement, Move::Left | Move::Right) {
                    // Left/Right on a selection land on its edge.
                    let edge = if matches!(movement, Move::Left) { anchor.min(head) } else { anchor.max(head) };
                    return (edge, edge);
                }
                let to = moved(ed, head, &movement);
                if key.shift {
                    (anchor, to)
                } else {
                    (to, to)
                }
            })
            .collect();
        store(ed, sels);
        return true;
    }
    if key.ctrl && !key.alt && matches!(key.code, Code::Char('c') | Code::Char('x')) {
        let cut = key.code == Code::Char('x');
        let sels = all(ed);
        let mut ordered = sels.clone();
        ordered.sort_by_key(|(anchor, head)| (*anchor).min(*head));
        let text = &ed.doc().text;
        let pieces: Vec<String> = ordered
            .iter()
            .map(|(anchor, head)| {
                if anchor == head {
                    text.line(head.line).to_string()
                } else {
                    text.slice((*anchor).min(*head), (*anchor).max(*head))
                }
            })
            .collect();
        let joined = pieces.join("\n");
        ed.set_register(None, joined.clone(), false, true);
        ed.set_register(Some('+'), joined, false, true);
        if cut {
            edit_all(ed, false, |_, (anchor, head)| (anchor, head, String::new()));
        }
        ed.info(format!("copied from {} cursors", sels.len()));
        return true;
    }
    if key == Key::ctrl('v') {
        if let Some(register) = ed.get_register(Some('+')).or_else(|| ed.get_register(None)) {
            type_text(ed, &register.text);
        }
        return true;
    }
    // Commands that know about several cursors pass; anything else drops the others.
    let keeps = key.ctrl
        && (matches!(key.code, Code::Char('d')) && !key.alt
            || matches!(key.code, Code::Char('l')) && key.shift
            || matches!(key.code, Code::Up | Code::Down) && key.alt);
    if !keeps {
        clear(ed);
    }
    false
}

// ---------- the named actions ----------

fn word_at(ed: &Editor, pos: Pos) -> Option<(Pos, Pos)> {
    let chars: Vec<char> = ed.doc().text.line(pos.line).chars().collect();
    let is_word = |index: usize| chars.get(index).is_some_and(|c| class(*c) == CharClass::Word);
    let mut at = pos.col;
    if !is_word(at) {
        if at > 0 && is_word(at - 1) {
            at -= 1;
        } else {
            return None;
        }
    }
    let mut start = at;
    while start > 0 && is_word(start - 1) {
        start -= 1;
    }
    let mut end = at;
    while is_word(end) {
        end += 1;
    }
    Some((Pos::new(pos.line, start), Pos::new(pos.line, end)))
}

/// The selection, else the word under the cursor, as (start, end).
fn selection_or_word(ed: &Editor) -> Option<(Pos, Pos)> {
    let (anchor, head) = primary(ed);
    if anchor != head {
        return Some((anchor.min(head), anchor.max(head)));
    }
    word_at(ed, head)
}

/// Char offsets of every match of `needle` in the document.
fn matches(ed: &Editor, needle: &str) -> Vec<usize> {
    if needle.is_empty() {
        return Vec::new();
    }
    let text = &ed.doc().text;
    let whole = text.slice(Pos::default(), text.end());
    let mut found = Vec::new();
    let mut chars_before = 0;
    let mut bytes_before = 0;
    for (byte, _) in whole.match_indices(needle) {
        chars_before += whole[bytes_before..byte].chars().count();
        bytes_before = byte;
        found.push(chars_before);
    }
    found
}

fn select_next_occurrence(ed: &mut Editor) -> Result<(), String> {
    let (anchor, head) = primary(ed);
    if anchor == head {
        let (start, end) = word_at(ed, head).ok_or("no word under the cursor")?;
        ed.multi.clear();
        set_primary(ed, start, end);
        return Ok(());
    }
    let (start, end) = (anchor.min(head), anchor.max(head));
    let needle = ed.doc().text.slice(start, end);
    let length = needle.chars().count();
    let sels = all(ed);
    let lines = starts(&ed.doc().text);
    let taken: Vec<usize> = sels.iter().map(|(a, h)| offset(&lines, (*a).min(*h))).collect();
    let newest = sels.last().map(|(a, h)| offset(&lines, (*a).max(*h))).unwrap_or(0);
    let found = matches(ed, &needle);
    let next = found
        .iter()
        .copied()
        .find(|at| *at >= newest && !taken.contains(at))
        .or_else(|| found.iter().copied().find(|at| !taken.contains(at)))
        .ok_or("no other match")?;
    let mut sels = sels;
    sels.push((pos_at(&lines, next), pos_at(&lines, next + length)));
    store(ed, sels);
    Ok(())
}

fn select_all_occurrences(ed: &mut Editor) -> Result<(), String> {
    let (start, end) = selection_or_word(ed).ok_or("nothing selected and no word under the cursor")?;
    let needle = ed.doc().text.slice(start, end);
    let length = needle.chars().count();
    let lines = starts(&ed.doc().text);
    let current = offset(&lines, start);
    let mut sels: Vec<(Pos, Pos)> =
        matches(ed, &needle).into_iter().map(|at| (pos_at(&lines, at), pos_at(&lines, at + length))).collect();
    // The selection the cursor was on stays the primary one.
    if let Some(index) = sels.iter().position(|(anchor, _)| offset(&lines, *anchor) == current) {
        sels.swap(0, index);
    }
    let count = sels.len();
    store(ed, sels);
    ed.info(format!("{count} matches selected"));
    Ok(())
}

fn add_cursor(ed: &mut Editor, below: bool) {
    let mut sels = all(ed);
    let text = &ed.doc().text;
    let edge = if below { sels.iter().map(|(_, head)| *head).max() } else { sels.iter().map(|(_, head)| *head).min() };
    let Some(edge) = edge else { return };
    let line = if below {
        if edge.line >= text.last_line() {
            return;
        }
        edge.line + 1
    } else {
        if edge.line == 0 {
            return;
        }
        edge.line - 1
    };
    let col = ed.view().want_col.unwrap_or(edge.col).min(text.line_len(line));
    let at = Pos::new(line, col);
    sels.push((at, at));
    store(ed, sels);
}

fn select_line(ed: &mut Editor) {
    let (anchor, head) = primary(ed);
    let text = &ed.doc().text;
    let (start, end) = (anchor.min(head), anchor.max(head));
    let next_line = |line: usize| {
        if line < text.last_line() {
            Pos::new(line + 1, 0)
        } else {
            Pos::new(line, text.line_len(line))
        }
    };
    let whole = start.col == 0 && end.col == 0 && end.line > start.line;
    let (from, to) = if whole { (start, next_line(end.line)) } else { (Pos::new(start.line, 0), next_line(end.line)) };
    set_primary(ed, from, to);
}

fn change_case(ed: &mut Editor, upper: bool) -> Result<(), String> {
    let (start, end) = selection_or_word(ed).ok_or("nothing to change")?;
    let text = ed.doc().text.slice(start, end);
    let changed = if upper { text.to_uppercase() } else { text.to_lowercase() };
    let (anchor, head) = primary(ed);
    let keep = anchor != head;
    edit::commit(ed);
    let cursor = ed.cursor();
    ed.doc_mut().replace(start, end, &changed, cursor);
    edit::commit(ed);
    if keep {
        let lines = starts(&ed.doc().text);
        let from = offset(&lines, start);
        set_primary(ed, start, pos_at(&lines, from + changed.chars().count()));
    } else {
        set_primary(ed, head, head);
    }
    Ok(())
}

fn transpose(ed: &mut Editor) {
    let cursor = ed.cursor();
    let chars: Vec<char> = ed.doc().text.line(cursor.line).chars().collect();
    if chars.len() < 2 || cursor.col == 0 {
        return;
    }
    // At the line end the last two swap, as in macOS and Zed.
    let right = cursor.col.min(chars.len() - 1);
    let left = right - 1;
    let swapped: String = [chars[right], chars[left]].iter().collect();
    edit::commit(ed);
    ed.doc_mut().replace(Pos::new(cursor.line, left), Pos::new(cursor.line, right + 1), &swapped, cursor);
    edit::commit(ed);
    set_primary(ed, Pos::new(cursor.line, right + 1), Pos::new(cursor.line, right + 1));
}

/// The next bigger meaningful range around (start, end): word, inside the nearest
/// brackets or quotes, those with their brackets, the line, the file.
fn bigger(ed: &Editor, start: Pos, end: Pos) -> Option<(Pos, Pos)> {
    let text = &ed.doc().text;
    let mut candidates: Vec<(Pos, Pos)> = Vec::new();
    if let Some(word) = word_at(ed, start) {
        candidates.push(word);
    }
    // Brackets: walk back from the start to an opener whose partner closes after the end.
    let mut at = start;
    let mut steps = 0;
    while let Some(prev) = text.prev(at) {
        at = prev;
        steps += 1;
        if steps > 20_000 {
            break;
        }
        if let Some(c) = text.char_at(at) {
            if "([{".contains(c) {
                if let Some(close) = crate::motion::match_pair(text, at) {
                    if close >= end || text.next(close).is_some_and(|after| after > end) {
                        let inner_start = text.next(at).unwrap_or(at);
                        candidates.push((inner_start, close));
                        candidates.push((at, text.next(close).unwrap_or(close)));
                        break;
                    }
                }
            }
        }
    }
    // Quotes on the same line.
    if start.line == end.line {
        let chars: Vec<char> = text.line(start.line).chars().collect();
        for quote in ['"', '\'', '`'] {
            let before = chars[..start.col.min(chars.len())].iter().rposition(|c| *c == quote);
            let after = chars.iter().skip(end.col).position(|c| *c == quote).map(|index| index + end.col);
            if let (Some(open), Some(close)) = (before, after) {
                candidates.push((Pos::new(start.line, open + 1), Pos::new(start.line, close)));
                candidates.push((Pos::new(start.line, open), Pos::new(start.line, close + 1)));
            }
        }
    }
    candidates.push((Pos::new(start.line, 0), Pos::new(end.line, text.line_len(end.line))));
    candidates.push((Pos::default(), text.end()));
    let lines = starts(text);
    let size = |(from, to): &(Pos, Pos)| offset(&lines, *to) - offset(&lines, *from);
    candidates
        .into_iter()
        .filter(|(from, to)| *from <= start && *to >= end && (*from, *to) != (start, end))
        .min_by_key(size)
}

/// Runs one of `ACTIONS`.
pub fn run(ed: &mut Editor, name: &str) -> Result<(), String> {
    match name {
        "select_all" => {
            ed.multi.clear();
            let end = ed.doc().text.end();
            set_primary(ed, Pos::default(), end);
        }
        "select_line" => select_line(ed),
        "indent" | "outdent" => {
            let (first, last) = standard::lines_of_selection(ed);
            edit::commit(ed);
            edit::shift_lines(ed, first, last, name == "indent", 1);
            edit::commit(ed);
        }
        "newline_below" | "newline_above" => {
            ed.multi.clear();
            let line = ed.cursor().line;
            let indent: String = ed.doc().text.line(line).chars().take_while(|c| *c == ' ' || *c == '\t').collect();
            let width = indent.chars().count();
            edit::commit(ed);
            let cursor = ed.cursor();
            let at = if name == "newline_below" {
                let end = Pos::new(line, ed.doc().text.line_len(line));
                ed.doc_mut().insert(end, &format!("\n{indent}"), cursor);
                Pos::new(line + 1, width)
            } else {
                ed.doc_mut().insert(Pos::new(line, 0), &format!("{indent}\n"), cursor);
                Pos::new(line, width)
            };
            edit::commit(ed);
            set_primary(ed, at, at);
        }
        "join_lines" => {
            let (first, last) = standard::lines_of_selection(ed);
            edit::commit(ed);
            edit::join_lines(ed, first, (last - first + 1).max(2), true);
            edit::commit(ed);
            let cursor = ed.cursor();
            set_primary(ed, cursor, cursor);
        }
        "uppercase" | "lowercase" => change_case(ed, name == "uppercase")?,
        "transpose" => transpose(ed),
        "expand_selection" => {
            let (anchor, head) = primary(ed);
            let (start, end) = (anchor.min(head), anchor.max(head));
            if let Some((from, to)) = bigger(ed, start, end) {
                ed.expand_stack.push((anchor, head));
                set_primary(ed, from, to);
            }
        }
        "shrink_selection" => {
            if let Some((anchor, head)) = ed.expand_stack.pop() {
                set_primary(ed, anchor, head);
            }
        }
        "select_next_occurrence" => select_next_occurrence(ed)?,
        "select_all_occurrences" => select_all_occurrences(ed)?,
        "add_cursor_above" => add_cursor(ed, false),
        "add_cursor_below" => add_cursor(ed, true),
        "single_cursor" => clear(ed),
        "search_next" | "search_prev" => {
            ed.multi.clear();
            let (anchor, head) = primary(ed);
            if anchor != head {
                set_primary(ed, head, head);
            }
            ed.search_next(name == "search_prev", 1);
        }
        "search_selection" => {
            let (start, end) = selection_or_word(ed).ok_or("nothing to search for")?;
            let needle = ed.doc().text.slice(start, end);
            ed.set_search(&regex::escape(&needle), true)?;
            set_primary(ed, start, start);
            ed.search_next(false, 1);
        }
        "replace" => {
            let find = selection_or_word(ed).map(|(start, end)| ed.doc().text.slice(start, end)).unwrap_or_default();
            let find: String = regex::escape(&find).replace('/', "\\/");
            let find = if find.contains('\n') { String::new() } else { find };
            ed.prompt = Some(crate::widgets::Prompt::new(crate::widgets::PromptKind::Command, &format!("%s/{find}/")));
        }
        "jump_back" | "jump_forward" => {
            ed.multi.clear();
            ed.jump(name == "jump_back");
        }
        other => return Err(format!("unknown action {other:?}")),
    }
    Ok(())
}
