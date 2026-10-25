//! Vim motions and text objects as pure functions of the text.

use crate::text::{class, is_word, CharClass, Pos, Text};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Find {
    /// f: onto the char
    Forward,
    /// F
    Backward,
    /// t: before the char
    Till,
    /// T
    TillBack,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Motion {
    Left,
    Right,
    Up,
    Down,
    WordStart(bool),
    WordEnd(bool),
    WordBack(bool),
    WordEndBack(bool),
    LineStart,
    FirstNonBlank,
    LineEnd,
    LastNonBlank,
    /// gg, or line N with a count
    FileStart,
    /// G, or line N with a count
    FileEnd,
    ParagraphForward,
    ParagraphBack,
    MatchPair,
    Find(Find, char),
    RepeatFind(bool),
    ScreenTop,
    ScreenMiddle,
    ScreenBottom,
    SearchNext(bool),
    Column,
    NextLine,
    PrevLine,
    Mark(char, bool),
    SentenceForward,
    SentenceBack,
}

impl Motion {
    /// Linewise motions act on whole lines under an operator.
    pub fn linewise(self) -> bool {
        matches!(
            self,
            Motion::Up
                | Motion::Down
                | Motion::FileStart
                | Motion::FileEnd
                | Motion::ScreenTop
                | Motion::ScreenMiddle
                | Motion::ScreenBottom
                | Motion::NextLine
                | Motion::PrevLine
                | Motion::Mark(_, false)
        )
    }

    /// Inclusive motions include the char they land on.
    pub fn inclusive(self) -> bool {
        matches!(
            self,
            Motion::WordEnd(_)
                | Motion::WordEndBack(_)
                | Motion::LineEnd
                | Motion::LastNonBlank
                | Motion::MatchPair
                | Motion::Find(Find::Forward, _)
                | Motion::Find(Find::Till, _)
        )
    }

    /// Jumps go into the jump list (Ctrl-o returns).
    pub fn is_jump(self) -> bool {
        matches!(
            self,
            Motion::FileStart
                | Motion::FileEnd
                | Motion::MatchPair
                | Motion::SearchNext(_)
                | Motion::ParagraphForward
                | Motion::ParagraphBack
                | Motion::Mark(..)
                | Motion::ScreenTop
                | Motion::ScreenMiddle
                | Motion::ScreenBottom
        )
    }
}

fn big_class(c: char) -> CharClass {
    match class(c) {
        CharClass::Punct => CharClass::Word,
        other => other,
    }
}

pub fn class_of(text: &Text, pos: Pos, big: bool) -> CharClass {
    match text.char_at(pos) {
        Some(c) if big => big_class(c),
        Some(c) => class(c),
        None => CharClass::Newline,
    }
}

/// `w`: start of the next word (an empty line counts as a word).
pub fn word_start(text: &Text, pos: Pos, big: bool) -> Pos {
    let start_class = class_of(text, pos, big);
    let mut current = pos;
    // Leave the current word.
    if start_class != CharClass::Space && start_class != CharClass::Newline {
        while let Some(next) = text.next(current) {
            current = next;
            if class_of(text, current, big) != start_class {
                break;
            }
        }
    }
    // Skip blanks; stop on an empty line.
    loop {
        match class_of(text, current, big) {
            CharClass::Space => {}
            CharClass::Newline => {
                if let Some(next) = text.next(current) {
                    if text.line_len(next.line) == 0 && next.line != pos.line {
                        return next;
                    }
                    current = next;
                    continue;
                }
                return current;
            }
            _ => return current,
        }
        match text.next(current) {
            Some(next) => current = next,
            None => return current,
        }
    }
}

/// `e`: end of the current or next word.
pub fn word_end(text: &Text, pos: Pos, big: bool) -> Pos {
    let mut current = match text.next(pos) {
        Some(next) => next,
        None => return pos,
    };
    while matches!(class_of(text, current, big), CharClass::Space | CharClass::Newline) {
        match text.next(current) {
            Some(next) => current = next,
            None => return current,
        }
    }
    let word = class_of(text, current, big);
    while let Some(next) = text.next(current) {
        if class_of(text, next, big) != word {
            break;
        }
        current = next;
    }
    current
}

/// `b`: start of the current or previous word.
pub fn word_back(text: &Text, pos: Pos, big: bool) -> Pos {
    let mut current = match text.prev(pos) {
        Some(prev) => prev,
        None => return pos,
    };
    while matches!(class_of(text, current, big), CharClass::Space | CharClass::Newline) {
        if text.line_len(current.line) == 0 && current.line != pos.line {
            return current;
        }
        match text.prev(current) {
            Some(prev) => current = prev,
            None => return current,
        }
    }
    let word = class_of(text, current, big);
    while let Some(prev) = text.prev(current) {
        if class_of(text, prev, big) != word {
            break;
        }
        current = prev;
    }
    current
}

/// `ge`: end of the previous word.
pub fn word_end_back(text: &Text, pos: Pos, big: bool) -> Pos {
    let word = class_of(text, pos, big);
    let mut current = pos;
    if word != CharClass::Space && word != CharClass::Newline {
        while let Some(prev) = text.prev(current) {
            current = prev;
            if class_of(text, current, big) != word {
                break;
            }
        }
        if current == pos {
            return pos;
        }
    }
    while matches!(class_of(text, current, big), CharClass::Space | CharClass::Newline) {
        match text.prev(current) {
            Some(prev) => current = prev,
            None => return current,
        }
    }
    current
}

pub fn paragraph(text: &Text, line: usize, forward: bool) -> usize {
    let blank = |index: usize| text.line(index).trim().is_empty();
    let mut index = line;
    if forward {
        while index < text.last_line() && blank(index) {
            index += 1;
        }
        while index < text.last_line() && !blank(index) {
            index += 1;
        }
    } else {
        while index > 0 && blank(index) {
            index -= 1;
        }
        while index > 0 && !blank(index) {
            index -= 1;
        }
    }
    index
}

pub fn sentence(text: &Text, pos: Pos, forward: bool) -> Pos {
    let ends = |c: Option<char>| matches!(c, Some('.') | Some('!') | Some('?'));
    let mut current = pos;
    if forward {
        while let Some(next) = text.next(current) {
            let at_end = ends(text.char_at(current)) && matches!(text.char_at(next), Some(' ') | Some('\n'));
            current = next;
            if at_end || (text.line_len(current.line) == 0 && current.line != pos.line) {
                while matches!(text.char_at(current), Some(' ') | Some('\n')) && text.line_len(current.line) > 0 {
                    match text.next(current) {
                        Some(next) => current = next,
                        None => break,
                    }
                }
                return current;
            }
        }
        current
    } else {
        let mut seen_text = false;
        while let Some(prev) = text.prev(current) {
            let c = text.char_at(prev);
            if ends(c) && seen_text {
                return word_start(text, prev, true).max(Pos::new(prev.line, 0)).min(current);
            }
            if c.is_some_and(|c| !c.is_whitespace()) {
                seen_text = true;
            }
            current = prev;
        }
        current
    }
}

const PAIRS: [(char, char); 4] = [('(', ')'), ('[', ']'), ('{', '}'), ('<', '>')];

/// `%`: the bracket matching the one at or after the cursor on this line.
pub fn match_pair(text: &Text, pos: Pos) -> Option<Pos> {
    let line = text.line(pos.line);
    let (start_col, c) = line.chars().enumerate().skip(pos.col).find(|(_, c)| "()[]{}".contains(*c))?;
    let start = Pos::new(pos.line, start_col);
    let (open, close, forward) = PAIRS.iter().find_map(|(open, close)| {
        if c == *open {
            Some((*open, *close, true))
        } else if c == *close {
            Some((*open, *close, false))
        } else {
            None
        }
    })?;
    find_matching(text, start, open, close, forward)
}

pub fn find_matching(text: &Text, start: Pos, open: char, close: char, forward: bool) -> Option<Pos> {
    let mut depth = 0i32;
    let mut current = start;
    let mut steps = 0;
    loop {
        match text.char_at(current) {
            Some(c) if c == open => depth += if forward { 1 } else { -1 },
            Some(c) if c == close => depth += if forward { -1 } else { 1 },
            _ => {}
        }
        if depth == 0 {
            return Some(current);
        }
        steps += 1;
        if steps > 2_000_000 {
            return None;
        }
        current = if forward { text.next(current)? } else { text.prev(current)? };
    }
}

pub fn find_char(text: &Text, pos: Pos, kind: Find, target: char, count: usize) -> Option<Pos> {
    let chars: Vec<char> = text.line(pos.line).chars().collect();
    let mut col = pos.col;
    for round in 0..count {
        let forward = matches!(kind, Find::Forward | Find::Till);
        if forward {
            let from = col + 1 + usize::from(kind == Find::Till && round > 0);
            col = (from..chars.len()).find(|index| chars[*index] == target)?;
        } else {
            let to = col.saturating_sub(usize::from(kind == Find::TillBack && round > 0));
            col = (0..to).rev().find(|index| chars[*index] == target)?;
        }
    }
    let col = match kind {
        Find::Till => col.checked_sub(1)?,
        Find::TillBack => col + 1,
        _ => col,
    };
    Some(Pos::new(pos.line, col))
}

/// A text object's range: start, end (exclusive), and whether it is linewise.
pub type Range = (Pos, Pos, bool);

pub fn object(text: &Text, pos: Pos, kind: char, inner: bool, count: usize) -> Option<Range> {
    match kind {
        'w' | 'W' => Some(word_object(text, pos, kind == 'W', inner, count)),
        'p' => paragraph_object(text, pos.line, inner, count),
        'e' => {
            let end = text.end();
            Some((Pos::default(), end, true))
        }
        '(' | ')' | 'b' => bracket_object(text, pos, '(', ')', inner, count),
        '[' | ']' => bracket_object(text, pos, '[', ']', inner, count),
        '{' | '}' | 'B' => bracket_object(text, pos, '{', '}', inner, count),
        '<' | '>' => bracket_object(text, pos, '<', '>', inner, count),
        '"' | '\'' | '`' => quote_object(text, pos, kind, inner),
        'a' => argument_object(text, pos, inner),
        'l' => {
            let line = text.line(pos.line);
            let start = if inner { text.first_non_blank(pos.line) } else { 0 };
            let end = if inner { line.trim_end().chars().count() } else { line.chars().count() };
            Some((Pos::new(pos.line, start), Pos::new(pos.line, end.max(start)), false))
        }
        't' => tag_object(text, pos, inner),
        _ => None,
    }
}

fn word_object(text: &Text, pos: Pos, big: bool, inner: bool, count: usize) -> Range {
    let line: Vec<char> = text.line(pos.line).chars().collect();
    if line.is_empty() {
        return (pos, pos, false);
    }
    let col = pos.col.min(line.len() - 1);
    let class_at = |index: usize| if big { big_class(line[index]) } else { class(line[index]) };
    let mut start = col;
    let mut end = col;
    for round in 0..count {
        let kind = class_at(if round == 0 { col } else { end.min(line.len() - 1) });
        if round == 0 {
            while start > 0 && class_at(start - 1) == kind {
                start -= 1;
            }
        }
        while end < line.len() && class_at(end) == kind {
            end += 1;
        }
        if !inner || round + 1 < count {
            // `aw` takes the following blanks (or the preceding ones at the line end).
            let had_space = end < line.len() && class_at(end) == CharClass::Space;
            while end < line.len() && class_at(end) == CharClass::Space {
                end += 1;
            }
            if !inner && !had_space && round == 0 && kind != CharClass::Space {
                while start > 0 && class_at(start - 1) == CharClass::Space {
                    start -= 1;
                }
            }
        }
        if end >= line.len() {
            break;
        }
    }
    (Pos::new(pos.line, start), Pos::new(pos.line, end), false)
}

fn paragraph_object(text: &Text, line: usize, inner: bool, count: usize) -> Option<Range> {
    let blank = |index: usize| text.line(index).trim().is_empty();
    let kind = blank(line);
    let mut start = line;
    while start > 0 && blank(start - 1) == kind {
        start -= 1;
    }
    let mut end = line;
    for round in 0..count {
        let kind = if round == 0 { kind } else { blank(end + 1) };
        if round > 0 {
            end += 1;
        }
        while end < text.last_line() && blank(end + 1) == kind {
            end += 1;
        }
        if !inner {
            while end < text.last_line() && blank(end + 1) != kind && blank(end + 1) {
                end += 1;
            }
        }
        if end >= text.last_line() {
            break;
        }
    }
    Some((Pos::new(start, 0), Pos::new(end, text.line_len(end)), true))
}

fn bracket_object(text: &Text, pos: Pos, open: char, close: char, inner: bool, count: usize) -> Option<Range> {
    // The cursor may sit on either bracket.
    let mut search = pos;
    let mut start = None;
    for _ in 0..count {
        let mut depth = 0;
        let mut current = search;
        let found = loop {
            match text.char_at(current) {
                Some(c) if c == close && current != search => depth += 1,
                Some(c) if c == open => {
                    if depth == 0 {
                        break Some(current);
                    }
                    depth -= 1;
                }
                _ => {}
            }
            match text.prev(current) {
                Some(prev) => current = prev,
                None => break None,
            }
        };
        let found = found?;
        start = Some(found);
        search = text.prev(found).unwrap_or(found);
        if text.prev(found).is_none() && count > 1 {
            break;
        }
    }
    let start = start?;
    let end = find_matching(text, start, open, close, true)?;
    if !inner {
        return Some((start, text.next(end).unwrap_or(end), false));
    }
    let mut inner_start = text.next(start)?;
    let mut inner_end = end;
    // A block whose brackets sit on their own lines is linewise inside (like vim's `i{`).
    if inner_start.col == text.line_len(inner_start.line) && end.line > start.line + 1 {
        inner_start = Pos::new(start.line + 1, 0);
        if text.line(end.line)[..crate::text::byte_at(text.line(end.line), end.col)].trim().is_empty() {
            inner_end = Pos::new(end.line - 1, text.line_len(end.line - 1));
            return Some((inner_start, inner_end, true));
        }
    }
    if inner_start > inner_end {
        inner_end = inner_start;
    }
    Some((inner_start, inner_end, false))
}

fn quote_object(text: &Text, pos: Pos, quote: char, inner: bool) -> Option<Range> {
    let line: Vec<char> = text.line(pos.line).chars().collect();
    let quotes: Vec<usize> =
        (0..line.len()).filter(|index| line[*index] == quote && (*index == 0 || line[index - 1] != '\\')).collect();
    // Pair quotes left to right; pick the pair around the cursor, else the next one.
    let pairs: Vec<(usize, usize)> =
        quotes.chunks(2).filter(|pair| pair.len() == 2).map(|pair| (pair[0], pair[1])).collect();
    let (open, close) = pairs
        .iter()
        .find(|(open, close)| *open <= pos.col && pos.col <= *close)
        .or_else(|| pairs.iter().find(|(open, _)| *open > pos.col))
        .copied()?;
    if inner {
        Some((Pos::new(pos.line, open + 1), Pos::new(pos.line, close), false))
    } else {
        let mut end = close + 1;
        while end < line.len() && line[end] == ' ' {
            end += 1;
        }
        Some((Pos::new(pos.line, open), Pos::new(pos.line, end), false))
    }
}

/// `ia`/`aa`: a function argument between commas or brackets.
fn argument_object(text: &Text, pos: Pos, inner: bool) -> Option<Range> {
    let line: Vec<char> = text.line(pos.line).chars().collect();
    if line.is_empty() {
        return None;
    }
    let col = pos.col.min(line.len() - 1);
    let mut depth = 0;
    let mut start = col;
    while start > 0 {
        let c = line[start - 1];
        if ")]}".contains(c) {
            depth += 1;
        } else if "([{".contains(c) {
            if depth == 0 {
                break;
            }
            depth -= 1;
        } else if c == ',' && depth == 0 {
            break;
        }
        start -= 1;
    }
    depth = 0;
    let mut end = col;
    while end < line.len() {
        let c = line[end];
        if "([{".contains(c) {
            depth += 1;
        } else if ")]}".contains(c) {
            if depth == 0 {
                break;
            }
            depth -= 1;
        } else if c == ',' && depth == 0 {
            break;
        }
        end += 1;
    }
    let mut inner_start = start;
    while inner_start < end && line[inner_start] == ' ' {
        inner_start += 1;
    }
    let mut inner_end = end;
    while inner_end > inner_start && line[inner_end - 1] == ' ' {
        inner_end -= 1;
    }
    if inner {
        return Some((Pos::new(pos.line, inner_start), Pos::new(pos.line, inner_end), false));
    }
    if end < line.len() && line[end] == ',' {
        let mut after = end + 1;
        while after < line.len() && line[after] == ' ' {
            after += 1;
        }
        Some((Pos::new(pos.line, inner_start), Pos::new(pos.line, after), false))
    } else if start > 0 && line[start - 1] == ',' {
        Some((Pos::new(pos.line, start - 1), Pos::new(pos.line, inner_end), false))
    } else {
        Some((Pos::new(pos.line, inner_start), Pos::new(pos.line, inner_end), false))
    }
}

fn tag_object(text: &Text, pos: Pos, inner: bool) -> Option<Range> {
    // Search backwards for an opening tag whose closing tag is after the cursor.
    let mut current = pos;
    loop {
        if text.char_at(current) == Some('<') {
            let rest: String = text.line(current.line).chars().skip(current.col + 1).collect();
            let name: String = rest.chars().take_while(|c| c.is_alphanumeric() || *c == '-' || *c == ':').collect();
            if !name.is_empty() && !rest.starts_with('/') {
                let open_end = text.line(current.line).chars().skip(current.col).position(|c| c == '>')?;
                let content_start = Pos::new(current.line, current.col + open_end + 1);
                let closing = format!("</{name}>");
                let mut search = content_start;
                let mut depth = 0;
                let opening = format!("<{name}");
                while let Some(found) = find_text(text, search, &['<']) {
                    let after: String = text.line(found.line).chars().skip(found.col).collect();
                    if after.starts_with(&closing) {
                        if depth == 0 {
                            if found >= pos {
                                let end_tag = Pos::new(found.line, found.col + closing.chars().count());
                                return Some(if inner {
                                    (content_start, found, false)
                                } else {
                                    (current, end_tag, false)
                                });
                            }
                            break;
                        }
                        depth -= 1;
                    } else if after.starts_with(&opening) {
                        depth += 1;
                    }
                    search = text.next(found)?;
                }
            }
        }
        current = text.prev(current)?;
    }
}

fn find_text(text: &Text, from: Pos, chars: &[char]) -> Option<Pos> {
    let mut current = from;
    loop {
        if text.char_at(current).is_some_and(|c| chars.contains(&c)) {
            return Some(current);
        }
        current = text.next(current)?;
    }
}

/// The word under (or right after) the cursor, for `*`, `K` and completion.
pub fn word_at(text: &Text, pos: Pos) -> Option<(Pos, Pos, String)> {
    let line: Vec<char> = text.line(pos.line).chars().collect();
    let mut col = pos.col.min(line.len());
    if col == line.len() || !is_word(line[col]) {
        col = (col..line.len()).find(|index| is_word(line[*index]))?;
    }
    let mut start = col;
    while start > 0 && is_word(line[start - 1]) {
        start -= 1;
    }
    let mut end = col;
    while end < line.len() && is_word(line[end]) {
        end += 1;
    }
    Some((Pos::new(pos.line, start), Pos::new(pos.line, end), line[start..end].iter().collect()))
}

/// Word chars right before `pos` (the prefix being completed).
pub fn word_before(text: &Text, pos: Pos) -> (usize, String) {
    let line: Vec<char> = text.line(pos.line).chars().collect();
    let end = pos.col.min(line.len());
    let mut start = end;
    while start > 0 && is_word(line[start - 1]) {
        start -= 1;
    }
    (start, line[start..end].iter().collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn text(content: &str) -> Text {
        Text::new(content)
    }

    #[test]
    fn word_motions() {
        let t = text("foo.bar baz\n\n  qux");
        assert_eq!(word_start(&t, Pos::new(0, 0), false), Pos::new(0, 3));
        assert_eq!(word_start(&t, Pos::new(0, 0), true), Pos::new(0, 8));
        assert_eq!(word_start(&t, Pos::new(0, 8), false), Pos::new(1, 0), "an empty line is a word");
        assert_eq!(word_start(&t, Pos::new(1, 0), false), Pos::new(2, 2));
        assert_eq!(word_end(&t, Pos::new(0, 0), false), Pos::new(0, 2));
        assert_eq!(word_end(&t, Pos::new(0, 2), false), Pos::new(0, 3));
        assert_eq!(word_back(&t, Pos::new(2, 2), false), Pos::new(1, 0));
        assert_eq!(word_back(&t, Pos::new(0, 8), false), Pos::new(0, 4));
        assert_eq!(word_end_back(&t, Pos::new(0, 8), false), Pos::new(0, 6));
    }

    #[test]
    fn find_and_match() {
        let t = text("call(a, (b), c)");
        assert_eq!(find_char(&t, Pos::new(0, 0), Find::Forward, ',', 2), Some(Pos::new(0, 11)));
        assert_eq!(find_char(&t, Pos::new(0, 0), Find::Till, '(', 1), Some(Pos::new(0, 3)));
        assert_eq!(find_char(&t, Pos::new(0, 14), Find::Backward, 'a', 1), Some(Pos::new(0, 5)));
        assert_eq!(match_pair(&t, Pos::new(0, 0)), Some(Pos::new(0, 14)));
        assert_eq!(match_pair(&t, Pos::new(0, 14)), Some(Pos::new(0, 4)));
    }

    #[test]
    fn objects() {
        let t = text("let x = foo(bar, \"baz qux\", (1));");
        assert_eq!(object(&t, Pos::new(0, 13), '(', true, 1), Some((Pos::new(0, 12), Pos::new(0, 31), false)));
        assert_eq!(object(&t, Pos::new(0, 13), '(', false, 1), Some((Pos::new(0, 11), Pos::new(0, 32), false)));
        assert_eq!(object(&t, Pos::new(0, 20), '"', true, 1), Some((Pos::new(0, 18), Pos::new(0, 25), false)));
        assert_eq!(object(&t, Pos::new(0, 4), 'w', false, 1), Some((Pos::new(0, 4), Pos::new(0, 6), false)));
        assert_eq!(object(&t, Pos::new(0, 13), 'a', true, 1), Some((Pos::new(0, 12), Pos::new(0, 15), false)));
        assert_eq!(object(&t, Pos::new(0, 13), 'a', false, 1), Some((Pos::new(0, 12), Pos::new(0, 17), false)));
        let block = text("fn a() {\n    one();\n    two();\n}");
        assert_eq!(object(&block, Pos::new(1, 4), '{', true, 1), Some((Pos::new(1, 0), Pos::new(2, 10), true)));
        let nested = text("(a (b) c)");
        assert_eq!(object(&nested, Pos::new(0, 4), '(', true, 2), Some((Pos::new(0, 1), Pos::new(0, 8), false)));
        let html = text("<div><b>hi</b></div>");
        assert_eq!(object(&html, Pos::new(0, 9), 't', true, 1), Some((Pos::new(0, 8), Pos::new(0, 10), false)));
    }

    #[test]
    fn paragraphs() {
        let t = text("a\nb\n\nc\nd");
        assert_eq!(paragraph(&t, 0, true), 2);
        assert_eq!(paragraph(&t, 4, false), 2);
        assert_eq!(object(&t, Pos::new(0, 0), 'p', true, 1), Some((Pos::new(0, 0), Pos::new(1, 1), true)));
        assert_eq!(object(&t, Pos::new(0, 0), 'p', false, 1), Some((Pos::new(0, 0), Pos::new(2, 0), true)));
    }
}
