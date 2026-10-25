//! Editing operations shared by vim keys, commands and the LSP: operators,
//! typing (auto-indent, auto-pairs), comments, joins, puts, line moves.

use crate::display::{col_to_display, display_to_col};
use crate::editor::{Editor, Mode, VisualKind};
use crate::text::{char_len, Pos};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Op {
    Delete,
    Change,
    Yank,
    Indent,
    Dedent,
    Lower,
    Upper,
    Toggle,
    Comment,
}

const PAIRS: [(char, char); 6] = [('(', ')'), ('[', ']'), ('{', '}'), ('"', '"'), ('\'', '\''), ('`', '`')];

/// Commits the open undo step of the current document at the cursor.
pub fn commit(ed: &mut Editor) {
    let cursor = ed.cursor();
    ed.doc_mut().commit(cursor);
}

/// The range a linewise operation removes, so that no empty line is left behind.
fn line_span(ed: &Editor, first: usize, last: usize) -> (Pos, Pos) {
    let text = &ed.doc().text;
    if last < text.last_line() {
        (Pos::new(first, 0), Pos::new(last + 1, 0))
    } else if first > 0 {
        (Pos::new(first - 1, text.line_len(first - 1)), Pos::new(last, text.line_len(last)))
    } else {
        (Pos::new(0, 0), Pos::new(last, text.line_len(last)))
    }
}

pub fn lines_text(ed: &Editor, first: usize, last: usize) -> String {
    let mut out = String::new();
    for line in first..=last {
        out.push_str(ed.doc().text.line(line));
        out.push('\n');
    }
    out
}

/// Applies an operator over `start..end` (exclusive end; linewise covers whole lines).
pub fn operator(ed: &mut Editor, op: Op, start: Pos, end: Pos, linewise: bool, register: Option<char>) {
    let (start, end) = (start.min(end), start.max(end));
    let cursor = ed.cursor();
    match op {
        Op::Yank => {
            let text = if linewise { lines_text(ed, start.line, end.line) } else { ed.doc().text.slice(start, end) };
            ed.set_register(register, text, linewise, true);
            let target = if linewise { Pos::new(start.line, cursor.col) } else { start };
            if linewise && cursor.line >= start.line && cursor.line <= end.line {
                // `yj` keeps the cursor; `yk` moves it up like vim.
                ed.set_cursor(Pos::new(start.line.min(cursor.line), cursor.col));
            } else {
                ed.set_cursor(target.min(cursor));
            }
        }
        Op::Delete => {
            if linewise {
                let text = lines_text(ed, start.line, end.line);
                ed.set_register(register, text, true, false);
                let (from, to) = line_span(ed, start.line, end.line);
                ed.doc_mut().remove(from, to, cursor);
                let line = start.line.min(ed.doc().text.last_line());
                let col = ed.doc().text.first_non_blank(line);
                ed.set_cursor(Pos::new(line, col));
            } else {
                let text = ed.doc().text.slice(start, end);
                ed.set_register(register, text, false, false);
                ed.doc_mut().remove(start, end, cursor);
                ed.set_cursor(start);
            }
        }
        Op::Change => {
            if linewise {
                let text = lines_text(ed, start.line, end.line);
                ed.set_register(register, text, true, false);
                let indent = ed.doc().text.indent_of(start.line).to_string();
                let last = end.line;
                let len = ed.doc().text.line_len(last);
                ed.doc_mut().replace(Pos::new(start.line, 0), Pos::new(last, len), &indent, cursor);
                ed.mode = Mode::Insert;
                ed.view_mut().cursor = Pos::new(start.line, char_len(&indent));
            } else {
                let text = ed.doc().text.slice(start, end);
                ed.set_register(register, text, false, false);
                ed.doc_mut().remove(start, end, cursor);
                ed.mode = Mode::Insert;
                ed.view_mut().cursor = start;
            }
        }
        Op::Indent | Op::Dedent => {
            shift_lines(ed, start.line, end.line, op == Op::Indent, 1);
            let col = ed.doc().text.first_non_blank(start.line);
            ed.set_cursor(Pos::new(start.line, col));
        }
        Op::Lower | Op::Upper | Op::Toggle => {
            let (from, to) = if linewise {
                (Pos::new(start.line, 0), Pos::new(end.line, ed.doc().text.line_len(end.line)))
            } else {
                (start, end)
            };
            let text = ed.doc().text.slice(from, to);
            let changed: String = match op {
                Op::Lower => text.to_lowercase(),
                Op::Upper => text.to_uppercase(),
                _ => text
                    .chars()
                    .map(|c| {
                        if c.is_uppercase() {
                            c.to_lowercase().next().unwrap_or(c)
                        } else {
                            c.to_uppercase().next().unwrap_or(c)
                        }
                    })
                    .collect(),
            };
            if changed != text {
                ed.doc_mut().replace(from, to, &changed, cursor);
            }
            ed.set_cursor(from);
        }
        Op::Comment => {
            toggle_comment(ed, start.line, end.line);
            ed.set_cursor(Pos::new(start.line, cursor.col));
        }
    }
}

/// Block (rectangular) operators for visual block mode.
pub fn block_operator(ed: &mut Editor, op: Op, anchor: Pos, cursor: Pos, register: Option<char>) {
    let tab = ed.tab_width(ed.doc());
    let (first, last) = (anchor.line.min(cursor.line), anchor.line.max(cursor.line));
    let left_line = ed.doc().text.line(anchor.line).to_string();
    let right_line = ed.doc().text.line(cursor.line).to_string();
    let a = col_to_display(&left_line, anchor.col, tab);
    let b = col_to_display(&right_line, cursor.col, tab);
    let (left, right) = (a.min(b), a.max(b) + 1);
    let mut pieces = Vec::new();
    let position = ed.cursor();
    for line in first..=last {
        let text = ed.doc().text.line(line).to_string();
        let from = display_to_col(&text, left, tab).min(char_len(&text));
        let to = display_to_col(&text, right, tab).min(char_len(&text));
        let from_pos = Pos::new(line, from);
        let to_pos = Pos::new(line, to.max(from));
        pieces.push(ed.doc().text.slice(from_pos, to_pos));
        match op {
            Op::Delete | Op::Change => {
                ed.doc_mut().remove(from_pos, to_pos, position);
            }
            Op::Lower | Op::Upper | Op::Toggle => {
                let piece = pieces.last().cloned().unwrap_or_default();
                let changed = match op {
                    Op::Lower => piece.to_lowercase(),
                    Op::Upper => piece.to_uppercase(),
                    _ => piece
                        .chars()
                        .map(|c| {
                            if c.is_uppercase() {
                                c.to_lowercase().next().unwrap_or(c)
                            } else {
                                c.to_uppercase().next().unwrap_or(c)
                            }
                        })
                        .collect(),
                };
                ed.doc_mut().replace(from_pos, to_pos, &changed, position);
            }
            _ => {}
        }
    }
    match op {
        Op::Indent | Op::Dedent => shift_lines(ed, first, last, op == Op::Indent, 1),
        Op::Comment => toggle_comment(ed, first, last),
        Op::Yank | Op::Delete | Op::Change => {
            ed.set_register(register, pieces.join("\n"), false, op == Op::Yank);
        }
        _ => {}
    }
    let line_text = ed.doc().text.line(first).to_string();
    let col = display_to_col(&line_text, left, tab).min(char_len(&line_text));
    ed.set_cursor(Pos::new(first, col));
    if op == Op::Change {
        start_block_insert(ed, first, last, left, false);
    }
}

/// `I`/`A`/`c` in block mode: type on the first line, copied to the others on Esc.
pub fn start_block_insert(ed: &mut Editor, first: usize, last: usize, column: usize, append: bool) {
    let tab = ed.tab_width(ed.doc());
    let text = ed.doc().text.line(first).to_string();
    let mut col = display_to_col(&text, column, tab);
    if append {
        col = (col).min(char_len(&text));
    }
    ed.mode = Mode::Insert;
    ed.view_mut().cursor = Pos::new(first, col.min(char_len(&text)));
    ed.vim.block_insert = Some((first, last, column, Pos::new(first, col.min(char_len(&text)))));
}

pub fn finish_block_insert(ed: &mut Editor) {
    let Some((first, last, column, start)) = ed.vim.block_insert.take() else {
        return;
    };
    let cursor = ed.cursor();
    if cursor.line != first || cursor.col < start.col {
        return;
    }
    let typed = ed.doc().text.slice(start, cursor);
    if typed.is_empty() || typed.contains('\n') {
        return;
    }
    let tab = ed.tab_width(ed.doc());
    for line in first + 1..=last {
        let text = ed.doc().text.line(line).to_string();
        let width = col_to_display(&text, char_len(&text), tab);
        let pad = column.saturating_sub(width);
        let col = display_to_col(&text, column, tab).min(char_len(&text));
        let insert = format!("{}{}", " ".repeat(pad), typed);
        ed.doc_mut().insert(Pos::new(line, col), &insert, cursor);
    }
}

pub fn shift_lines(ed: &mut Editor, first: usize, last: usize, indent: bool, times: usize) {
    let unit = ed.indent_unit(ed.doc());
    let tab = ed.tab_width(ed.doc());
    let cursor = ed.cursor();
    for line in first..=last.min(ed.doc().text.last_line()) {
        for _ in 0..times {
            let text = ed.doc().text.line(line).to_string();
            if indent {
                if !text.trim().is_empty() {
                    ed.doc_mut().insert(Pos::new(line, 0), &unit, cursor);
                }
            } else {
                // Remove up to one unit of leading whitespace (a tab counts as tab_width).
                let unit_width = if unit == "\t" { tab } else { unit.len() };
                let mut width = 0;
                let mut count = 0;
                for c in text.chars() {
                    match c {
                        ' ' if width < unit_width => width += 1,
                        '\t' if width < unit_width => width += tab,
                        _ => break,
                    }
                    count += 1;
                }
                if count > 0 {
                    ed.doc_mut().remove(Pos::new(line, 0), Pos::new(line, count), cursor);
                }
            }
        }
    }
}

/// Comments or uncomments lines with the language's line comment (or block comment).
pub fn toggle_comment(ed: &mut Editor, first: usize, last: usize) {
    let lang = ed.doc().lang.and_then(|index| ed.languages.get(index));
    let (prefix, suffix) = match lang {
        Some(lang) if lang.comment.is_some() => (lang.comment.clone().unwrap_or_default(), String::new()),
        Some(lang) if lang.block_comment.is_some() => {
            let (open, close) = lang.block_comment.clone().unwrap_or_default();
            (open, close)
        }
        _ => ("#".to_string(), String::new()),
    };
    let cursor = ed.cursor();
    let lines: Vec<(usize, String)> = (first..=last.min(ed.doc().text.last_line()))
        .map(|line| (line, ed.doc().text.line(line).to_string()))
        .collect();
    let content: Vec<&(usize, String)> = lines.iter().filter(|(_, text)| !text.trim().is_empty()).collect();
    if content.is_empty() {
        return;
    }
    let commented = content.iter().all(|(_, text)| {
        let trimmed = text.trim_start();
        trimmed.starts_with(prefix.as_str()) && (suffix.is_empty() || trimmed.trim_end().ends_with(suffix.as_str()))
    });
    let indent = content.iter().map(|(_, text)| char_len(text) - char_len(text.trim_start())).min().unwrap_or(0);
    for (line, text) in content {
        if commented {
            let lead = char_len(text) - char_len(text.trim_start());
            let after = text.trim_start()[prefix.len()..].to_string();
            let remove = char_len(&prefix) + usize::from(after.starts_with(' '));
            if !suffix.is_empty() {
                let trimmed_len = char_len(text.trim_end());
                let mut start = trimmed_len - char_len(&suffix);
                if start > 0 && text.chars().nth(start - 1) == Some(' ') {
                    start -= 1;
                }
                ed.doc_mut().remove(Pos::new(*line, start), Pos::new(*line, trimmed_len), cursor);
            }
            ed.doc_mut().remove(Pos::new(*line, lead), Pos::new(*line, lead + remove), cursor);
        } else {
            if !suffix.is_empty() {
                let len = char_len(text.trim_end());
                ed.doc_mut().insert(Pos::new(*line, len), &format!(" {suffix}"), cursor);
            }
            ed.doc_mut().insert(Pos::new(*line, indent), &format!("{prefix} "), cursor);
        }
    }
}

/// `J` / `gJ`: joins `count` lines (at least two) starting at the cursor's.
pub fn join_lines(ed: &mut Editor, first: usize, count: usize, spaces: bool) {
    let cursor = ed.cursor();
    let last = (first + count.max(2) - 1).min(ed.doc().text.last_line());
    let mut col = cursor.col;
    for _ in first..last {
        let current = ed.doc().text.line(first).to_string();
        let next = ed.doc().text.line(first + 1).to_string();
        let len = char_len(&current);
        let lead = if spaces { char_len(&next) - char_len(next.trim_start()) } else { 0 };
        let rest = &next.trim_start();
        let separator =
            if !spaces || rest.is_empty() || current.ends_with(' ') || rest.starts_with(')') || current.is_empty() {
                ""
            } else {
                " "
            };
        let trimmed_current = if spaces { char_len(current.trim_end()) } else { len };
        ed.doc_mut().replace(Pos::new(first, trimmed_current), Pos::new(first + 1, lead), separator, cursor);
        col = trimmed_current;
    }
    ed.set_cursor(Pos::new(first, col));
}

/// p / P: puts a register after/before the cursor `count` times.
pub fn put(ed: &mut Editor, register: Option<char>, after: bool, count: usize, cursor_after: bool) {
    let Some(reg) = ed.get_register(register) else {
        ed.error("nothing to paste");
        return;
    };
    let cursor = ed.cursor();
    let count = count.max(1);
    if reg.linewise {
        let mut text = reg.text.clone();
        if !text.ends_with('\n') {
            text.push('\n');
        }
        let text = text.repeat(count);
        let line = if after { cursor.line + 1 } else { cursor.line };
        let inserted_lines = text.matches('\n').count();
        if line > ed.doc().text.last_line() {
            // After the last line: start with a newline instead of ending with one.
            let end = Pos::new(ed.doc().text.last_line(), ed.doc().text.line_len(ed.doc().text.last_line()));
            let body = text.strip_suffix('\n').unwrap_or(&text);
            ed.doc_mut().insert(end, &format!("\n{body}"), cursor);
        } else {
            ed.doc_mut().insert(Pos::new(line, 0), &text, cursor);
        }
        let target = if cursor_after { (line + inserted_lines).min(ed.doc().text.last_line()) } else { line };
        let col = if cursor_after { 0 } else { ed.doc().text.first_non_blank(target) };
        ed.set_cursor(Pos::new(target, col));
    } else {
        let text = reg.text.repeat(count);
        let len = ed.doc().text.line_len(cursor.line);
        let at = if after && len > 0 { Pos::new(cursor.line, (cursor.col + 1).min(len)) } else { cursor };
        let end = ed.doc_mut().insert(at, &text, cursor);
        let target = if cursor_after {
            end
        } else if text.contains('\n') {
            at
        } else {
            Pos::new(end.line, end.col.saturating_sub(1))
        };
        ed.set_cursor(target);
    }
}

/// Visual p/P: replaces the selection with a register.
pub fn put_over_selection(ed: &mut Editor, register: Option<char>, keep_register: bool) {
    let Some((start, end, kind)) = ed.selection() else {
        return;
    };
    let Some(reg) = ed.get_register(register) else {
        ed.error("nothing to paste");
        return;
    };
    ed.mode = Mode::Normal;
    let linewise = kind == VisualKind::Line;
    let cursor = ed.cursor();
    let (from, to) = if linewise {
        (Pos::new(start.line, 0), Pos::new(end.line, ed.doc().text.line_len(end.line)))
    } else {
        (start, ed.doc().text.next(end).unwrap_or(ed.doc().text.end()))
    };
    let replaced = ed.doc().text.slice(from, to);
    let mut text = reg.text.clone();
    if linewise || reg.linewise {
        text = text.strip_suffix('\n').unwrap_or(&text).to_string();
        if !linewise {
            text = format!("\n{text}\n");
        }
    }
    ed.doc_mut().replace(from, to, &text, cursor);
    if !keep_register {
        ed.set_register(None, if linewise { format!("{replaced}\n") } else { replaced }, linewise, false);
    }
    ed.set_cursor(from);
}

/// Inserts typed text at the cursor in insert mode, with auto-pairs and smart dedent.
pub fn type_char(ed: &mut Editor, c: char) {
    let cursor = ed.cursor();
    let line = ed.doc().text.line(cursor.line).to_string();
    let chars: Vec<char> = line.chars().collect();
    let next = chars.get(cursor.col).copied();
    let prev = if cursor.col > 0 { chars.get(cursor.col - 1).copied() } else { None };
    if ed.mode == Mode::Replace {
        if cursor.col < chars.len() {
            ed.doc_mut().replace(cursor, Pos::new(cursor.line, cursor.col + 1), &c.to_string(), cursor);
        } else {
            ed.doc_mut().insert(cursor, &c.to_string(), cursor);
        }
        ed.view_mut().cursor = Pos::new(cursor.line, cursor.col + 1);
        return;
    }
    if ed.options.auto_pairs && !ed.vim.replaying_any() {
        // Typing the closer that is already there just steps over it.
        let closer = PAIRS.iter().any(|(_, close)| *close == c);
        if closer && next == Some(c) {
            ed.view_mut().cursor = Pos::new(cursor.line, cursor.col + 1);
            return;
        }
        if let Some((open, close)) = PAIRS.iter().find(|(open, _)| *open == c) {
            let quote = open == close;
            let next_ok = next.is_none_or(|n| n.is_whitespace() || ")]}>,;:".contains(n));
            let prev_word = prev.is_some_and(|p| p.is_alphanumeric() || p == '_');
            let in_string_or_comment = in_string_or_comment(ed, cursor);
            let allow = next_ok && !(quote && (prev_word || prev == Some(c) || in_string_or_comment));
            // Rust lifetimes and English apostrophes: no pair for ' after a word or '&'.
            let rusty = c == '\'' && (prev == Some('&') || prev == Some('<') || is_lang(ed, "rust"));
            if allow && !rusty {
                ed.doc_mut().insert(cursor, &format!("{open}{close}"), cursor);
                ed.view_mut().cursor = Pos::new(cursor.line, cursor.col + 1);
                return;
            }
        }
    }
    ed.doc_mut().insert(cursor, &c.to_string(), cursor);
    ed.view_mut().cursor = Pos::new(cursor.line, cursor.col + 1);
    // A closing bracket typed on an otherwise blank line lines up with its opener.
    if ed.options.auto_indent && "}])".contains(c) && line[..crate::text::byte_at(&line, cursor.col)].trim().is_empty()
    {
        let open = match c {
            '}' => '{',
            ']' => '[',
            _ => '(',
        };
        let here = Pos::new(cursor.line, cursor.col);
        if let Some(opener) = crate::motion::find_matching(&ed.doc().text, here, open, c, false) {
            let indent = ed.doc().text.indent_of(opener.line).to_string();
            let current = ed.doc().text.indent_of(cursor.line).to_string();
            if indent != current {
                let cur = ed.cursor();
                ed.doc_mut().replace(Pos::new(cursor.line, 0), Pos::new(cursor.line, char_len(&current)), &indent, cur);
                ed.view_mut().cursor = Pos::new(cursor.line, char_len(&indent) + 1);
            }
        }
    }
}

fn is_lang(ed: &Editor, name: &str) -> bool {
    ed.doc().lang.and_then(|index| ed.languages.get(index)).is_some_and(|lang| lang.name == name)
}

fn in_string_or_comment(ed: &mut Editor, cursor: Pos) -> bool {
    let languages = &ed.languages;
    let id = ed.views[&ed.focus].doc;
    let doc = ed.docs.get_mut(&id).expect("document");
    let spans = doc.spans(cursor.line, languages);
    spans.iter().any(|span| {
        span.start < cursor.col
            && cursor.col < span.end
            && (span.class == "syntax.string" || span.class == "syntax.comment")
    })
}

/// Enter in insert mode: keeps indentation, indents after openers, opens `{|}` blocks.
pub fn newline(ed: &mut Editor) {
    let cursor = ed.cursor();
    let line = ed.doc().text.line(cursor.line).to_string();
    let chars: Vec<char> = line.chars().collect();
    let before: String = chars[..cursor.col.min(chars.len())].iter().collect();
    let after: String = chars[cursor.col.min(chars.len())..].iter().collect();
    if !ed.options.auto_indent {
        ed.doc_mut().insert(cursor, "\n", cursor);
        ed.view_mut().cursor = Pos::new(cursor.line + 1, 0);
        return;
    }
    let indent = ed.doc().text.indent_of(cursor.line).to_string();
    let unit = ed.indent_unit(ed.doc());
    let trimmed = before.trim_end();
    let lang = ed.doc().lang.and_then(|index| ed.languages.get(index));
    let extra = trimmed.ends_with(['{', '[', '('])
        || lang.is_some_and(|lang| {
            lang.indent_after.iter().any(|end| trimmed.ends_with(end.as_str()))
                && !trimmed.trim_start().starts_with('#')
        });
    let between = matches!(
        (trimmed.chars().last(), after.trim_start().chars().next()),
        (Some('{'), Some('}')) | (Some('['), Some(']')) | (Some('('), Some(')'))
    );
    // Trailing spaces before the cursor are dropped (a whitespace-only line ends up empty).
    let cut = char_len(before.trim_end());
    let rest = after.trim_start();
    let removed_lead = char_len(&after) - char_len(rest);
    let new_indent = if extra { format!("{indent}{unit}") } else { indent.clone() };
    let text = if between { format!("\n{new_indent}\n{indent}") } else { format!("\n{new_indent}") };
    ed.doc_mut().replace(Pos::new(cursor.line, cut), Pos::new(cursor.line, cursor.col + removed_lead), &text, cursor);
    ed.view_mut().cursor = Pos::new(cursor.line + 1, char_len(&new_indent));
}

/// o / O: opens a line below/above with the right indentation.
pub fn open_line(ed: &mut Editor, below: bool) {
    let cursor = ed.cursor();
    let line = ed.doc().text.line(cursor.line).to_string();
    let indent = ed.doc().text.indent_of(cursor.line).to_string();
    let unit = ed.indent_unit(ed.doc());
    let lang = ed.doc().lang.and_then(|index| ed.languages.get(index));
    let trimmed = line.trim_end();
    let extra = below
        && ed.options.auto_indent
        && (trimmed.ends_with(['{', '[', '('])
            || lang.is_some_and(|lang| lang.indent_after.iter().any(|end| trimmed.ends_with(end.as_str()))));
    let new_indent = if !ed.options.auto_indent {
        String::new()
    } else if extra {
        format!("{indent}{unit}")
    } else {
        indent
    };
    ed.mode = Mode::Insert;
    if below {
        let end = Pos::new(cursor.line, char_len(&line));
        ed.doc_mut().insert(end, &format!("\n{new_indent}"), cursor);
        ed.view_mut().cursor = Pos::new(cursor.line + 1, char_len(&new_indent));
    } else {
        ed.doc_mut().insert(Pos::new(cursor.line, 0), &format!("{new_indent}\n"), cursor);
        ed.view_mut().cursor = Pos::new(cursor.line, char_len(&new_indent));
    }
}

/// Backspace in insert mode: removes pairs, unindents to the previous stop, joins lines.
pub fn backspace(ed: &mut Editor) {
    let cursor = ed.cursor();
    if cursor.col == 0 {
        if cursor.line > 0 {
            let len = ed.doc().text.line_len(cursor.line - 1);
            ed.doc_mut().remove(Pos::new(cursor.line - 1, len), cursor, cursor);
            ed.view_mut().cursor = Pos::new(cursor.line - 1, len);
        }
        return;
    }
    let line = ed.doc().text.line(cursor.line).to_string();
    let chars: Vec<char> = line.chars().collect();
    let prev = chars[cursor.col - 1];
    let next = chars.get(cursor.col).copied();
    if ed.options.auto_pairs && PAIRS.iter().any(|(open, close)| *open == prev && Some(*close) == next) {
        ed.doc_mut().remove(Pos::new(cursor.line, cursor.col - 1), Pos::new(cursor.line, cursor.col + 1), cursor);
        ed.view_mut().cursor = Pos::new(cursor.line, cursor.col - 1);
        return;
    }
    let before: String = chars[..cursor.col].iter().collect();
    let unit = ed.indent_unit(ed.doc());
    if before.chars().all(|c| c == ' ') && unit != "\t" && !before.is_empty() {
        let width = unit.len().max(1);
        let target = (cursor.col - 1) / width * width;
        ed.doc_mut().remove(Pos::new(cursor.line, target), cursor, cursor);
        ed.view_mut().cursor = Pos::new(cursor.line, target);
        return;
    }
    ed.doc_mut().remove(Pos::new(cursor.line, cursor.col - 1), cursor, cursor);
    ed.view_mut().cursor = Pos::new(cursor.line, cursor.col - 1);
}

pub fn delete_word_back(ed: &mut Editor) {
    let cursor = ed.cursor();
    if cursor.col == 0 {
        backspace(ed);
        return;
    }
    let chars: Vec<char> = ed.doc().text.line(cursor.line).chars().collect();
    let mut start = cursor.col;
    while start > 0 && chars[start - 1].is_whitespace() {
        start -= 1;
    }
    let word = |c: char| c.is_alphanumeric() || c == '_';
    if start > 0 && word(chars[start - 1]) {
        while start > 0 && word(chars[start - 1]) {
            start -= 1;
        }
    } else {
        while start > 0 && !word(chars[start - 1]) && !chars[start - 1].is_whitespace() {
            start -= 1;
        }
    }
    ed.doc_mut().remove(Pos::new(cursor.line, start), cursor, cursor);
    ed.view_mut().cursor = Pos::new(cursor.line, start);
}

pub fn delete_to_line_start(ed: &mut Editor) {
    let cursor = ed.cursor();
    let indent = ed.doc().text.first_non_blank(cursor.line);
    let start = if cursor.col > indent { indent } else { 0 };
    ed.doc_mut().remove(Pos::new(cursor.line, start), cursor, cursor);
    ed.view_mut().cursor = Pos::new(cursor.line, start);
}

/// Tab in insert mode: one indent unit (spaces up to the next stop, or a tab).
pub fn insert_tab(ed: &mut Editor) {
    let unit = ed.indent_unit(ed.doc());
    let cursor = ed.cursor();
    let text = if unit == "\t" {
        "\t".to_string()
    } else {
        let width = unit.len().max(1);
        let tab = ed.tab_width(ed.doc());
        let column = col_to_display(ed.doc().text.line(cursor.line), cursor.col, tab);
        " ".repeat(width - column % width)
    };
    let end = ed.doc_mut().insert(cursor, &text, cursor);
    ed.view_mut().cursor = end;
}

/// Ctrl-a / Ctrl-x: adds to the number at or after the cursor.
pub fn increment(ed: &mut Editor, delta: i64) {
    let cursor = ed.cursor();
    let chars: Vec<char> = ed.doc().text.line(cursor.line).chars().collect();
    let mut start = cursor.col.min(chars.len());
    // Back up to the start of a number the cursor is inside.
    while start > 0 && chars[start - 1].is_ascii_hexdigit() && chars[start].is_ascii_hexdigit() {
        start -= 1;
    }
    let Some(first_digit) = (start..chars.len()).find(|index| chars[*index].is_ascii_digit()) else {
        ed.error("no number on this line");
        return;
    };
    let mut begin = first_digit;
    let hex = chars.get(begin) == Some(&'0') && matches!(chars.get(begin + 1), Some('x') | Some('X'));
    let mut end = if hex { begin + 2 } else { begin };
    while end < chars.len() && (if hex { chars[end].is_ascii_hexdigit() } else { chars[end].is_ascii_digit() }) {
        end += 1;
    }
    let negative = !hex && begin > 0 && chars[begin - 1] == '-' && (begin < 2 || !chars[begin - 2].is_alphanumeric());
    if negative {
        begin -= 1;
    }
    let text: String = chars[begin..end].iter().collect();
    let replacement = if hex {
        let digits = &text[2..];
        let value = i64::from_str_radix(digits, 16).unwrap_or(0).wrapping_add(delta);
        let upper = digits.chars().any(|c| c.is_ascii_uppercase());
        let formatted = if upper { format!("{:X}", value.max(0)) } else { format!("{:x}", value.max(0)) };
        format!("{}{:0>width$}", &text[..2], formatted, width = digits.len())
    } else {
        let value = text.parse::<i64>().unwrap_or(0).wrapping_add(delta);
        let digits = text.trim_start_matches('-');
        if digits.len() > 1 && digits.starts_with('0') {
            let sign = if value < 0 { "-" } else { "" };
            format!("{sign}{:0>width$}", value.abs(), width = digits.len())
        } else {
            value.to_string()
        }
    };
    let from = Pos::new(cursor.line, begin);
    let end_pos = ed.doc_mut().replace(from, Pos::new(cursor.line, end), &replacement, cursor);
    ed.set_cursor(Pos::new(cursor.line, end_pos.col.saturating_sub(1)));
}

/// Alt-j / Alt-k: moves lines `first..=last` one line down or up.
pub fn move_lines(ed: &mut Editor, first: usize, last: usize, down: bool) -> bool {
    let text_last = ed.doc().text.last_line();
    if (down && last >= text_last) || (!down && first == 0) {
        return false;
    }
    let cursor = ed.cursor();
    let block = lines_text(ed, first, last);
    let block = block.strip_suffix('\n').unwrap_or(&block).to_string();
    if down {
        let below = ed.doc().text.line(last + 1).to_string();
        let end = Pos::new(last + 1, char_len(&below));
        ed.doc_mut().replace(Pos::new(first, 0), end, &format!("{below}\n{block}"), cursor);
    } else {
        let above = ed.doc().text.line(first - 1).to_string();
        let end = Pos::new(last, ed.doc().text.line_len(last));
        ed.doc_mut().replace(Pos::new(first - 1, 0), end, &format!("{block}\n{above}"), cursor);
    }
    true
}

/// Replaces text without touching the cursor's undo position; used for LSP edits.
pub fn apply_edits(ed: &mut Editor, doc: usize, mut edits: Vec<(Pos, Pos, String)>) {
    edits.sort_by_key(|edit| std::cmp::Reverse(edit.0));
    let cursor = ed.views.values().find(|view| view.doc == doc).map_or(Pos::default(), |view| view.cursor);
    let Some(document) = ed.docs.get_mut(&doc) else {
        return;
    };
    document.commit(cursor);
    for (start, end, text) in edits {
        document.replace(start, end, &text, cursor);
    }
    document.commit(cursor);
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Config;

    pub fn editor(text: &str) -> Editor {
        crate::clipboard::disable();
        let mut ed = Editor::new(Config::default());
        ed.options.clipboard = false;
        ed.doc_mut().set_content(text);
        ed
    }

    #[test]
    fn comments_toggle() {
        let mut ed = editor("fn a() {\n    one();\n\n    two();\n}");
        let lang = ed.languages.by_name("rust");
        ed.doc_mut().set_language(lang);
        toggle_comment(&mut ed, 1, 3);
        assert_eq!(ed.doc().text.to_string_lf(), "fn a() {\n    // one();\n\n    // two();\n}");
        toggle_comment(&mut ed, 1, 3);
        assert_eq!(ed.doc().text.to_string_lf(), "fn a() {\n    one();\n\n    two();\n}");
    }

    #[test]
    fn newline_indents_and_opens_blocks() {
        let mut ed = editor("fn a() {}");
        ed.mode = Mode::Insert;
        ed.view_mut().cursor = Pos::new(0, 8);
        newline(&mut ed);
        assert_eq!(ed.doc().text.to_string_lf(), "fn a() {\n    \n}");
        assert_eq!(ed.cursor(), Pos::new(1, 4));
    }

    #[test]
    fn auto_pairs_and_step_over() {
        let mut ed = editor("");
        ed.mode = Mode::Insert;
        type_char(&mut ed, '(');
        type_char(&mut ed, 'x');
        type_char(&mut ed, ')');
        assert_eq!(ed.doc().text.line(0), "(x)");
        assert_eq!(ed.cursor(), Pos::new(0, 3));
        backspace(&mut ed);
        assert_eq!(ed.doc().text.line(0), "(x");
    }

    #[test]
    fn increments_numbers() {
        let mut ed = editor("x = 9; y = 0x0f; z = -3");
        increment(&mut ed, 1);
        assert_eq!(ed.doc().text.line(0), "x = 10; y = 0x0f; z = -3");
        ed.set_cursor(Pos::new(0, 12));
        increment(&mut ed, 1);
        assert_eq!(ed.doc().text.line(0), "x = 10; y = 0x10; z = -3");
        ed.set_cursor(Pos::new(0, 22));
        increment(&mut ed, 5);
        assert_eq!(ed.doc().text.line(0), "x = 10; y = 0x10; z = 2");
    }

    #[test]
    fn joins_and_moves_lines() {
        let mut ed = editor("a\n    b\nc");
        join_lines(&mut ed, 0, 2, true);
        assert_eq!(ed.doc().text.to_string_lf(), "a b\nc");
        assert!(move_lines(&mut ed, 0, 0, true));
        assert_eq!(ed.doc().text.to_string_lf(), "c\na b");
    }
}
