//! Insert-mode completion: words from open buffers right away, language-server
//! items when they arrive; snippets are expanded to plain text with the cursor
//! at the first placeholder.

use std::collections::HashSet;

use crate::editor::{Editor, Mode};
use crate::motion::word_before;
use crate::text::{char_len, Pos};
use crate::widgets::{Completion, CompletionItem};

/// Words of at least three chars from open documents (current one first).
fn words(ed: &Editor, prefix: &str, skip: Pos) -> Vec<CompletionItem> {
    let mut seen = HashSet::new();
    let mut items = Vec::new();
    let current = ed.view().doc;
    let mut docs: Vec<&crate::document::Document> =
        ed.docs.values().filter(|doc| doc.kind != crate::document::DocKind::Output).collect();
    docs.sort_by_key(|doc| doc.id != current);
    let first = prefix.chars().next().map(|c| c.to_lowercase().collect::<String>());
    for doc in docs {
        for (number, line) in doc.text.lines().enumerate().take(20_000) {
            let mut start = None;
            let chars: Vec<char> = line.chars().collect();
            for (index, c) in chars.iter().copied().chain(std::iter::once(' ')).enumerate() {
                let word = c.is_alphanumeric() || c == '_';
                match (word, start) {
                    (true, None) => start = Some(index),
                    (false, Some(begin)) => {
                        start = None;
                        if doc.id == current && number == skip.line && begin <= skip.col && skip.col <= index {
                            continue;
                        }
                        if index - begin < 3 {
                            continue;
                        }
                        let text: String = chars[begin..index].iter().collect();
                        if text.chars().next().is_some_and(|c| c.is_ascii_digit()) {
                            continue;
                        }
                        if let Some(first) = &first {
                            if !text.to_lowercase().starts_with(first.as_str()) {
                                continue;
                            }
                        }
                        if seen.insert(text.clone()) {
                            items.push(CompletionItem {
                                label: text.clone(),
                                kind: "word".into(),
                                insert: text,
                                ..CompletionItem::default()
                            });
                        }
                    }
                    _ => {}
                }
                if items.len() > 3000 {
                    return items;
                }
            }
        }
    }
    items
}

fn show(ed: &mut Editor, items: Vec<CompletionItem>, start: Pos, from_lsp: bool) {
    let doc = ed.view().doc;
    let mut completion = Completion { doc, items, shown: Vec::new(), selected: None, start, from_lsp, offset: 0 };
    let cursor = ed.cursor();
    let prefix = ed.doc().text.slice(start, cursor);
    if completion.filter(&prefix) {
        if let Some(index) = completion.items.iter().position(|item| item.preselect) {
            if let Some(shown) = completion.shown.iter().position(|shown| *shown == index) {
                completion.selected = Some(shown);
            }
        }
        ed.completion = Some(completion);
    } else {
        ed.completion = None;
    }
}

/// Opens completion at the cursor: buffer words now, the LSP's items when they come.
pub fn trigger(ed: &mut Editor, manual: bool) {
    if !matches!(ed.mode, Mode::Insert) {
        return;
    }
    let cursor = ed.cursor();
    let (start_col, prefix) = word_before(&ed.doc().text, cursor);
    let start = Pos::new(cursor.line, start_col);
    let asked_lsp = crate::lsp::request_completion(ed);
    if manual || !asked_lsp {
        let items = words(ed, &prefix, cursor);
        show(ed, items, start, false);
    }
}

pub fn after_typing(ed: &mut Editor, c: char) {
    let word_char = c.is_alphanumeric() || c == '_';
    if ed.completion.is_some() {
        if word_char {
            refilter(ed);
            // Ask the server again when its list was incomplete or nothing is left.
            if ed.completion.is_none() || ed.lsp.completion_incomplete {
                if ed.completion.is_none() {
                    trigger(ed, false);
                } else {
                    crate::lsp::request_completion(ed);
                }
            }
            return;
        }
        ed.completion = None;
    }
    if crate::lsp::is_trigger_char(ed, c) {
        crate::lsp::request_completion(ed);
        return;
    }
    if word_char {
        let cursor = ed.cursor();
        let (_, prefix) = word_before(&ed.doc().text, cursor);
        if char_len(&prefix) >= 2 {
            trigger(ed, false);
        }
    }
}

pub fn refilter(ed: &mut Editor) {
    let Some(completion) = ed.completion.as_ref() else {
        return;
    };
    let cursor = ed.cursor();
    if completion.doc != ed.view().doc || cursor.line != completion.start.line || cursor.col < completion.start.col {
        ed.completion = None;
        return;
    }
    let prefix = ed.doc().text.slice(completion.start, cursor);
    if prefix.chars().any(|c| !(c.is_alphanumeric() || c == '_')) {
        ed.completion = None;
        return;
    }
    let mut completion = ed.completion.take().expect("completion");
    if completion.filter(&prefix) {
        ed.completion = Some(completion);
    }
}

/// Items from the language server for the request made at `start`.
pub fn on_lsp_items(ed: &mut Editor, doc: usize, items: Vec<CompletionItem>) {
    if !matches!(ed.mode, Mode::Insert) || ed.view().doc != doc {
        return;
    }
    let cursor = ed.cursor();
    let (start_col, prefix) = word_before(&ed.doc().text, cursor);
    let start = Pos::new(cursor.line, start_col);
    // Keep buffer words the server did not offer, after its items.
    let mut merged = items;
    let known: HashSet<String> = merged.iter().map(|item| item.label.clone()).collect();
    if char_len(&prefix) >= 2 {
        for (index, word) in words(ed, &prefix, cursor).into_iter().enumerate() {
            if !known.contains(&word.label) {
                let mut word = word;
                word.sort = format!("~{index:05}");
                merged.push(word);
            }
        }
    }
    let selected = ed.completion.as_ref().and_then(|completion| completion.selected);
    show(ed, merged, start, true);
    if let (Some(completion), Some(selected)) = (ed.completion.as_mut(), selected) {
        completion.selected = Some(selected.min(completion.shown.len().saturating_sub(1)));
    }
}

/// `$1`, `${2:name}`, `$0` → plain text, and the char offset of the first stop.
pub fn expand_snippet(snippet: &str) -> (String, Option<usize>) {
    let chars: Vec<char> = snippet.chars().collect();
    let mut out = String::new();
    let mut first_stop: Option<(u32, usize)> = None;
    let mut index = 0;
    let note = |number: u32, at: usize, first: &mut Option<(u32, usize)>| {
        // $0 is the final position; any numbered stop wins over it.
        let rank = if number == 0 { u32::MAX } else { number };
        if first.is_none_or(|(best, _)| rank < best) {
            *first = Some((rank, at));
        }
    };
    while index < chars.len() {
        let c = chars[index];
        if c == '\\' && index + 1 < chars.len() {
            out.push(chars[index + 1]);
            index += 2;
            continue;
        }
        if c == '$' && index + 1 < chars.len() {
            if chars[index + 1].is_ascii_digit() {
                let digits: String = chars[index + 1..].iter().take_while(|c| c.is_ascii_digit()).collect();
                note(digits.parse().unwrap_or(0), char_len(&out), &mut first_stop);
                index += 1 + digits.len();
                continue;
            }
            if chars[index + 1] == '{' {
                // ${1:default} or ${1|a,b|}
                let mut depth = 1;
                let mut end = index + 2;
                while end < chars.len() && depth > 0 {
                    match chars[end] {
                        '{' => depth += 1,
                        '}' => depth -= 1,
                        _ => {}
                    }
                    end += 1;
                }
                let inner: String = chars[index + 2..end.saturating_sub(1)].iter().collect();
                let digits: String = inner.chars().take_while(|c| c.is_ascii_digit()).collect();
                let rest = &inner[digits.len()..];
                note(digits.parse().unwrap_or(0), char_len(&out), &mut first_stop);
                if let Some(default) = rest.strip_prefix(':') {
                    out.push_str(&expand_snippet(default).0);
                } else if let Some(choices) = rest.strip_prefix('|') {
                    out.push_str(choices.trim_end_matches('|').split(',').next().unwrap_or(""));
                }
                index = end;
                continue;
            }
        }
        out.push(c);
        index += 1;
    }
    (out, first_stop.map(|(_, at)| at))
}

pub fn accept(ed: &mut Editor) {
    let Some(completion) = ed.completion.take() else {
        return;
    };
    let Some(item) = completion.selected_item().cloned() else {
        return;
    };
    let cursor = ed.cursor();
    let (start, raw) = match &item.edit {
        Some((start, _end, text)) => (*start, text.clone()),
        None => (completion.start, if item.insert.is_empty() { item.label.clone() } else { item.insert.clone() }),
    };
    let start = if start.line == cursor.line && start.col <= cursor.col { start } else { completion.start };
    let (text, stop) = if raw.contains('$') { expand_snippet(&raw) } else { (raw, None) };
    // Keep the indentation of the line for multi-line snippets.
    let indent = ed.doc().text.indent_of(cursor.line).to_string();
    let text = text.replace('\n', &format!("\n{indent}"));
    let end = ed.doc_mut().replace(start, cursor, &text, cursor);
    let target = match stop {
        Some(offset) => {
            let before: String = text.chars().take(offset).collect();
            crate::text::end_of(start, &before)
        }
        None => end,
    };
    ed.view_mut().cursor = target;
    if !item.additional.is_empty() {
        // Auto-imports and the like: other places of the file, applied bottom-up.
        let mut edits = item.additional.clone();
        edits.sort_by_key(|edit| std::cmp::Reverse(edit.0));
        let mut cursor = ed.cursor();
        for (from, to, text) in edits {
            let added = text.matches('\n').count() as isize - (to.line - from.line) as isize;
            ed.doc_mut().replace(from, to, &text, cursor);
            if from.line < cursor.line {
                cursor.line = (cursor.line as isize + added).max(0) as usize;
            }
        }
        ed.view_mut().cursor = cursor;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn snippets() {
        assert_eq!(expand_snippet("println!(\"$1\")$0"), ("println!(\"\")".into(), Some(10)));
        assert_eq!(expand_snippet("fn ${1:name}(${2:args})"), ("fn name(args)".into(), Some(3)));
        assert_eq!(expand_snippet("a\\$b"), ("a$b".into(), None));
        assert_eq!(expand_snippet("${1|one,two|}"), ("one".into(), Some(0)));
    }
}
