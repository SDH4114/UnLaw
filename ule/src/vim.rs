//! Vim keys: `["x][count]operator[count]motion`, text objects, visual and
//! insert mode, `.` repeat, macros. Key bindings (keymap.rs) are checked
//! before this grammar, so they can override any of it.

use std::time::Instant;

use crate::config::Action;
use crate::display::col_to_display;
use crate::edit::{self, Op};
use crate::editor::{Editor, Mode, VisualKind};
use crate::keymap::{KeyMode, Lookup};
use crate::keys::{Code, Key};
use crate::motion::{self, Find, Motion};
use crate::text::{char_len, Pos};

#[derive(Debug, Default)]
pub struct VimState {
    pub pending: Vec<Key>,
    pub pending_since: Option<Instant>,
    pub insert_pending: Vec<Key>,
    pub last_find: Option<(Find, char)>,
    pub last_change: Option<Vec<Key>>,
    pub last_change_count: Option<usize>,
    pub recording_change: Option<Vec<Key>>,
    pub macro_recording: Option<(char, Vec<Key>)>,
    pub last_macro: Option<char>,
    pub last_recorded: Option<char>,
    pub replaying: usize,
    pub insert_repeat: Option<(usize, Vec<Key>, bool)>,
    pub insert_keys: Vec<Key>,
    pub last_insert: Option<(usize, Pos)>,
    pub block_insert: Option<(usize, usize, usize, Pos)>,
    pub insert_register: bool,
    pub last_substitute: Option<(String, String, String)>,
    pub last_ex: Option<String>,
    pub last_count_explicit: bool,
    /// A Shift-arrow selection (exclusive end, typing replaces it).
    pub select_mode: bool,
    pub select_from_insert: bool,
}

impl VimState {
    pub fn replaying_any(&self) -> bool {
        self.replaying > 0
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Target {
    Motion(Motion, Option<usize>),
    Object(char, bool, Option<usize>),
    /// dd, cc, yy...; in visual mode: the selection.
    Line(Option<usize>),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Act {
    Insert(char),
    DeleteChar(bool),
    Substitute,
    SubstituteLine,
    ChangeToEnd,
    DeleteToEnd,
    YankLine,
    ReplaceChar(char),
    ReplaceMode,
    Join(bool),
    Put(bool, bool),
    Undo,
    Redo,
    Repeat,
    ToggleCase,
    Visual(VisualKind),
    Reselect,
    Record(char),
    Play(char),
    Mark(char),
    Search(bool),
    SearchWord(bool, bool),
    Command,
    ScrollLines(isize),
    Page(isize, bool),
    Align(char),
    Increment(i64),
    Jump(bool),
    WriteQuit,
    QuitForce,
    RepeatSubstitute,
    FileInfo,
    Escape,
    SwapAnchor,
    VisualObject(char, bool),
    VisualInsert(bool),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Cmd {
    Move(Motion),
    Op(Op, Target),
    Act(Act),
}

enum Parse {
    Incomplete,
    Invalid,
    Done(Cmd),
}

fn ch(key: &Key) -> Option<char> {
    key.as_char()
}

/// Motion keys at the start of `keys`: (motion, keys used).
enum MotionParse {
    Incomplete,
    Invalid,
    Done(Motion),
}

fn parse_motion(keys: &[Key]) -> MotionParse {
    let Some(first) = keys.first() else {
        return MotionParse::Incomplete;
    };
    let motion = match (first.code, first.ctrl) {
        (Code::Left, false) | (Code::Backspace, false) | (Code::Char('h'), false) => Motion::Left,
        (Code::Right, false) | (Code::Char('l'), false) | (Code::Char(' '), false) => Motion::Right,
        (Code::Down, false) | (Code::Char('j'), false) | (Code::Char('n'), true) => Motion::Down,
        (Code::Up, false) | (Code::Char('k'), false) | (Code::Char('p'), true) => Motion::Up,
        (Code::Home, _) => Motion::LineStart,
        (Code::End, _) => Motion::LineEnd,
        (Code::Enter, false) => Motion::NextLine,
        (Code::Char(c), false) if !first.alt => match c {
            'w' => Motion::WordStart(false),
            'W' => Motion::WordStart(true),
            'e' => Motion::WordEnd(false),
            'E' => Motion::WordEnd(true),
            'b' => Motion::WordBack(false),
            'B' => Motion::WordBack(true),
            '0' => Motion::LineStart,
            '^' => Motion::FirstNonBlank,
            '$' => Motion::LineEnd,
            'G' => Motion::FileEnd,
            '}' => Motion::ParagraphForward,
            '{' => Motion::ParagraphBack,
            ')' => Motion::SentenceForward,
            '(' => Motion::SentenceBack,
            '%' => Motion::MatchPair,
            ';' => Motion::RepeatFind(false),
            ',' => Motion::RepeatFind(true),
            'H' => Motion::ScreenTop,
            'M' => Motion::ScreenMiddle,
            'L' => Motion::ScreenBottom,
            'n' => Motion::SearchNext(false),
            'N' => Motion::SearchNext(true),
            '|' => Motion::Column,
            '+' => Motion::NextLine,
            '-' => Motion::PrevLine,
            'f' | 'F' | 't' | 'T' | '\'' | '`' => {
                let Some(target) = keys.get(1) else {
                    return MotionParse::Incomplete;
                };
                let Some(target) = ch(target) else {
                    return MotionParse::Invalid;
                };
                let motion = match c {
                    'f' => Motion::Find(Find::Forward, target),
                    'F' => Motion::Find(Find::Backward, target),
                    't' => Motion::Find(Find::Till, target),
                    'T' => Motion::Find(Find::TillBack, target),
                    '\'' => Motion::Mark(target, false),
                    _ => Motion::Mark(target, true),
                };
                return MotionParse::Done(motion);
            }
            'g' => {
                let Some(second) = keys.get(1) else {
                    return MotionParse::Incomplete;
                };
                let motion = match ch(second) {
                    Some('g') => Motion::FileStart,
                    Some('e') => Motion::WordEndBack(false),
                    Some('E') => Motion::WordEndBack(true),
                    Some('_') => Motion::LastNonBlank,
                    Some('j') => Motion::Down,
                    Some('k') => Motion::Up,
                    Some('0') => Motion::LineStart,
                    Some('$') => Motion::LineEnd,
                    _ => return MotionParse::Invalid,
                };
                return MotionParse::Done(motion);
            }
            _ => return MotionParse::Invalid,
        },
        _ => return MotionParse::Invalid,
    };
    MotionParse::Done(motion)
}

fn operator_of(keys: &[Key]) -> Option<(Op, usize, Vec<char>)> {
    let first = ch(keys.first()?)?;
    let single = match first {
        'd' => Some(Op::Delete),
        'c' => Some(Op::Change),
        'y' => Some(Op::Yank),
        '>' => Some(Op::Indent),
        '<' => Some(Op::Dedent),
        _ => None,
    };
    if let Some(op) = single {
        return Some((op, 1, vec![first]));
    }
    if first == 'g' {
        let second = keys.get(1).and_then(ch)?;
        let op = match second {
            '~' => Op::Toggle,
            'u' => Op::Lower,
            'U' => Op::Upper,
            'c' => Op::Comment,
            _ => return None,
        };
        return Some((op, 2, vec!['g', second]));
    }
    None
}

fn digits(keys: &[Key], allow_zero_first: bool) -> (Option<usize>, usize) {
    let mut count: Option<usize> = None;
    let mut used = 0;
    for key in keys {
        match ch(key) {
            Some(c @ '0'..='9') if c != '0' || count.is_some() || allow_zero_first => {
                count =
                    Some(count.unwrap_or(0).saturating_mul(10).saturating_add(c as usize - '0' as usize).min(99_999));
                used += 1;
            }
            _ => break,
        }
    }
    (count, used)
}

fn parse(keys: &[Key], visual: bool) -> Parse {
    let Some(first) = keys.first() else {
        return Parse::Incomplete;
    };
    // In visual mode operators apply to the selection right away.
    if visual {
        if let Some(act) = visual_act(keys) {
            return act;
        }
    }
    if let Some((op, used, chars)) = if visual { None } else { operator_of(keys) } {
        let rest = &keys[used..];
        let (count, counted) = digits(rest, false);
        let rest = &rest[counted..];
        let Some(next) = rest.first() else {
            return Parse::Incomplete;
        };
        // dd, cc, yy, >>, <<, gcc, g~~, guu, gUU (also gugu, gUgU).
        let last = *chars.last().unwrap_or(&' ');
        if ch(next) == Some(last) && (chars.len() == 1 || rest.len() == 1) {
            return Parse::Done(Cmd::Op(op, Target::Line(count)));
        }
        if chars.len() == 2 && ch(next) == Some('g') {
            match rest.get(1).and_then(ch) {
                None => return Parse::Incomplete,
                Some(c) if c == last => return Parse::Done(Cmd::Op(op, Target::Line(count))),
                _ => {}
            }
        }
        if let Some(kind @ ('i' | 'a')) = ch(next) {
            let Some(object) = rest.get(1) else {
                return Parse::Incomplete;
            };
            return match ch(object) {
                Some(object) => Parse::Done(Cmd::Op(op, Target::Object(object, kind == 'i', count))),
                None => Parse::Invalid,
            };
        }
        return match parse_motion(rest) {
            MotionParse::Incomplete => Parse::Incomplete,
            MotionParse::Done(motion) => Parse::Done(Cmd::Op(op, Target::Motion(motion, count))),
            MotionParse::Invalid => Parse::Invalid,
        };
    }
    match parse_motion(keys) {
        MotionParse::Incomplete => return Parse::Incomplete,
        MotionParse::Done(motion) => return Parse::Done(Cmd::Move(motion)),
        MotionParse::Invalid => {}
    }
    let second = keys.get(1).and_then(ch);
    let need_second = |make: fn(char) -> Act| match keys.get(1) {
        None => Parse::Incomplete,
        Some(key) => match ch(key) {
            Some(c) => Parse::Done(Cmd::Act(make(c))),
            None if key.code == Code::Enter => Parse::Done(Cmd::Act(make('\n'))),
            None => Parse::Invalid,
        },
    };
    let act = match (first.code, first.ctrl, first.alt) {
        (Code::Esc, _, _) | (Code::Char('c'), true, false) => Act::Escape,
        (Code::Char('r'), true, false) => Act::Redo,
        (Code::Char('a'), true, false) => Act::Increment(1),
        (Code::Char('x'), true, false) => Act::Increment(-1),
        (Code::Char('o'), true, false) => Act::Jump(true),
        (Code::Char('i'), true, false) | (Code::Tab, false, false) => Act::Jump(false),
        (Code::Char('d'), true, false) => Act::Page(1, true),
        (Code::Char('u'), true, false) => Act::Page(-1, true),
        (Code::Char('f'), true, false) | (Code::PageDown, _, _) => Act::Page(1, false),
        (Code::Char('b'), true, false) | (Code::PageUp, _, _) => Act::Page(-1, false),
        (Code::Char('e'), true, false) => Act::ScrollLines(1),
        (Code::Char('y'), true, false) => Act::ScrollLines(-1),
        (Code::Char('g'), true, false) => Act::FileInfo,
        // Ctrl-Q and Alt-V also start block visual (Ctrl-V pastes with standard_keys).
        (Code::Char('v'), true, false) | (Code::Char('q'), true, false) | (Code::Char('v'), false, true) => {
            Act::Visual(VisualKind::Block)
        }
        (Code::Char('a'), false, true) => Act::Increment(1),
        (Code::Char('x'), false, true) => Act::Increment(-1),
        (Code::Insert, _, _) => Act::Insert('i'),
        (Code::Delete, _, _) => Act::DeleteChar(true),
        (Code::Char(c), false, false) => match c {
            'i' | 'a' | 'I' | 'A' | 'o' | 'O' => Act::Insert(c),
            'x' => Act::DeleteChar(true),
            'X' => Act::DeleteChar(false),
            's' => Act::Substitute,
            'S' => Act::SubstituteLine,
            'C' => Act::ChangeToEnd,
            'D' => Act::DeleteToEnd,
            'Y' => Act::YankLine,
            'r' => return need_second(Act::ReplaceChar),
            'R' => Act::ReplaceMode,
            'J' => Act::Join(true),
            'p' => Act::Put(true, false),
            'P' => Act::Put(false, false),
            'u' => Act::Undo,
            '.' => Act::Repeat,
            '~' => Act::ToggleCase,
            'v' => Act::Visual(VisualKind::Char),
            'V' => Act::Visual(VisualKind::Line),
            'q' => return need_second(Act::Record),
            '@' => return need_second(Act::Play),
            'm' => return need_second(Act::Mark),
            '/' => Act::Search(true),
            '?' => Act::Search(false),
            '*' => Act::SearchWord(true, true),
            '#' => Act::SearchWord(false, true),
            ':' => Act::Command,
            '&' => Act::RepeatSubstitute,
            'Z' => match second {
                None => return Parse::Incomplete,
                Some('Z') => Act::WriteQuit,
                Some('Q') => Act::QuitForce,
                _ => return Parse::Invalid,
            },
            'z' => match keys.get(1) {
                None => return Parse::Incomplete,
                Some(key) if key.code == Code::Enter => Act::Align('t'),
                Some(key) => match ch(key) {
                    Some('z') | Some('.') => Act::Align('z'),
                    Some('t') => Act::Align('t'),
                    Some('b') | Some('-') => Act::Align('b'),
                    _ => return Parse::Invalid,
                },
            },
            'g' => match second {
                None => return Parse::Incomplete,
                Some('J') => Act::Join(false),
                Some('v') => Act::Reselect,
                Some('i') => Act::Insert('g'),
                Some('I') => Act::Insert('0'),
                Some('p') => Act::Put(true, true),
                Some('P') => Act::Put(false, true),
                Some('*') => Act::SearchWord(true, false),
                Some('#') => Act::SearchWord(false, false),
                _ => return Parse::Invalid,
            },
            _ => return Parse::Invalid,
        },
        _ => return Parse::Invalid,
    };
    Parse::Done(Cmd::Act(act))
}

fn visual_act(keys: &[Key]) -> Option<Parse> {
    let first = keys.first()?;
    if first.ctrl || first.alt {
        return None;
    }
    let c = ch(first)?;
    let op = match c {
        'd' | 'x' => Some(Op::Delete),
        'c' | 's' => Some(Op::Change),
        'y' => Some(Op::Yank),
        '>' => Some(Op::Indent),
        '<' => Some(Op::Dedent),
        '~' => Some(Op::Toggle),
        'u' => Some(Op::Lower),
        'U' => Some(Op::Upper),
        _ => None,
    };
    if let Some(op) = op {
        return Some(Parse::Done(Cmd::Op(op, Target::Line(None))));
    }
    Some(match c {
        'o' | 'O' => Parse::Done(Cmd::Act(Act::SwapAnchor)),
        'i' | 'a' => match keys.get(1) {
            None => Parse::Incomplete,
            Some(key) => match ch(key) {
                Some(object) => Parse::Done(Cmd::Act(Act::VisualObject(object, c == 'i'))),
                None => Parse::Invalid,
            },
        },
        'I' => Parse::Done(Cmd::Act(Act::VisualInsert(false))),
        'A' => Parse::Done(Cmd::Act(Act::VisualInsert(true))),
        'J' => Parse::Done(Cmd::Act(Act::Join(true))),
        'r' => match keys.get(1).and_then(ch) {
            None => Parse::Incomplete,
            Some(r) => Parse::Done(Cmd::Act(Act::ReplaceChar(r))),
        },
        'D' | 'X' => Parse::Done(Cmd::Op(Op::Delete, Target::Object('l', false, None))),
        'C' | 'S' | 'R' => Parse::Done(Cmd::Op(Op::Change, Target::Object('l', false, None))),
        'Y' => Parse::Done(Cmd::Op(Op::Yank, Target::Object('l', false, None))),
        'g' => match keys.get(1).and_then(ch) {
            None => Parse::Incomplete,
            Some('c') => Parse::Done(Cmd::Op(Op::Comment, Target::Line(None))),
            Some('J') => Parse::Done(Cmd::Act(Act::Join(false))),
            Some('u') => Parse::Done(Cmd::Op(Op::Lower, Target::Line(None))),
            Some('U') => Parse::Done(Cmd::Op(Op::Upper, Target::Line(None))),
            Some('~') => Parse::Done(Cmd::Op(Op::Toggle, Target::Line(None))),
            _ => return None,
        },
        _ => return None,
    })
}

/// Splits `["x][count]` off the front; None while a register name is still missing.
fn prefix(keys: &[Key]) -> Option<(Option<char>, Option<usize>, usize)> {
    let mut used = 0;
    let mut register = None;
    if keys.first().and_then(ch) == Some('"') {
        let name = ch(keys.get(1)?)?;
        register = Some(name);
        used = 2;
    }
    let (count, counted) = digits(&keys[used..], false);
    Some((register, count, used + counted))
}

/// The main key entry point.
pub fn handle_key(ed: &mut Editor, key: Key) {
    ed.needs_redraw = true;
    if ed.vim.replaying == 0 {
        if let Some((_, keys)) = ed.vim.macro_recording.as_mut() {
            keys.push(key);
        }
    }
    if ed.message.is_some() && ed.message.as_ref().is_some_and(|message| message.at.elapsed().as_millis() > 100) {
        ed.message = None;
    }
    if ed.prompt.is_some() {
        crate::ex::prompt_key(ed, key);
        return;
    }
    if ed.picker.is_some() {
        crate::picker::key(ed, key);
        return;
    }
    if ed.focus_area == crate::editor::Focus::Explorer && ed.explorer.is_some() {
        crate::explorer::key(ed, key);
        return;
    }
    if ed.popup.is_some() {
        match key.code {
            Code::Esc => {
                ed.popup = None;
                return;
            }
            Code::Char('d') | Code::Char('f') if key.ctrl => {
                if let Some(popup) = ed.popup.as_mut() {
                    popup.scroll = (popup.scroll + 5).min(popup.lines.len().saturating_sub(1));
                }
                return;
            }
            Code::Char('u') | Code::Char('b') if key.ctrl => {
                if let Some(popup) = ed.popup.as_mut() {
                    popup.scroll = popup.scroll.saturating_sub(5);
                }
                return;
            }
            _ => ed.popup = None,
        }
    }
    if crate::standard::enabled(ed) && crate::standard::handle(ed, key) {
        let focus = ed.focus;
        ed.scroll_to_cursor(focus);
        return;
    }
    if ed.vim.select_mode && !matches!(ed.mode, Mode::Visual(_)) {
        ed.vim.select_mode = false;
    }
    match ed.mode {
        Mode::Insert | Mode::Replace => insert_key(ed, key),
        Mode::Normal | Mode::Visual(_) => normal_key(ed, key),
    }
    if !matches!(ed.mode, Mode::Insert | Mode::Replace) {
        ed.completion = None;
    }
    let focus = ed.focus;
    ed.scroll_to_cursor(focus);
}

fn key_mode(ed: &Editor) -> KeyMode {
    match ed.mode {
        Mode::Visual(_) => KeyMode::Visual,
        Mode::Insert | Mode::Replace => KeyMode::Insert,
        Mode::Normal => KeyMode::Normal,
    }
}

fn normal_key(ed: &mut Editor, key: Key) {
    if intercept(ed, key) {
        return;
    }
    ed.vim.pending.push(key);
    ed.vim.pending_since = Some(Instant::now());
    let keys = ed.vim.pending.clone();
    let Some((register, count, used)) = prefix(&keys) else {
        return;
    };
    let rest = &keys[used..];
    if rest.is_empty() {
        return;
    }
    match ed.keymap.lookup(key_mode(ed), rest) {
        Lookup::Exact(binding) => {
            let actions = binding.actions.clone();
            ed.vim.pending.clear();
            run_actions(ed, &actions, count, register);
            return;
        }
        Lookup::ExactAndPrefix(_) | Lookup::Prefix => {
            // Waiting: the timeout (or more keys) decides. Vim keys that are complete
            // already, like `g` motions, still need the keymap to rule out longer bindings.
            return;
        }
        Lookup::None => {}
    }
    let visual = matches!(ed.mode, Mode::Visual(_));
    match parse(rest, visual) {
        Parse::Incomplete => {}
        Parse::Invalid => {
            ed.vim.pending.clear();
        }
        Parse::Done(cmd) => {
            ed.vim.pending.clear();
            let repeat_keys: Vec<Key> = keys[..used - digits_len(&keys, register.is_some())]
                .iter()
                .copied()
                .chain(rest.iter().copied())
                .collect();
            execute(ed, cmd, register, count, repeat_keys);
        }
    }
}

/// How many keys of the prefix are count digits (they are left out of `.` repeats).
fn digits_len(keys: &[Key], has_register: bool) -> usize {
    let start = if has_register { 2 } else { 0 };
    digits(&keys[start.min(keys.len())..], false).1
}

/// Called by the main loop: runs a binding that is complete but also a prefix once the timeout passes.
pub fn tick(ed: &mut Editor) {
    let Some(since) = ed.vim.pending_since else {
        return;
    };
    if since.elapsed().as_millis() < ed.options.timeout as u128 {
        return;
    }
    if !ed.vim.insert_pending.is_empty() {
        let keys = std::mem::take(&mut ed.vim.insert_pending);
        ed.vim.pending_since = None;
        flush_insert_pending(ed, keys);
        ed.needs_redraw = true;
        return;
    }
    if ed.vim.pending.is_empty() {
        return;
    }
    let keys = ed.vim.pending.clone();
    let Some((register, count, used)) = prefix(&keys) else {
        return;
    };
    if let Lookup::ExactAndPrefix(binding) = ed.keymap.lookup(key_mode(ed), &keys[used..]) {
        let actions = binding.actions.clone();
        ed.vim.pending.clear();
        ed.vim.pending_since = None;
        run_actions(ed, &actions, count, register);
        let focus = ed.focus;
        ed.scroll_to_cursor(focus);
        ed.needs_redraw = true;
    }
}

pub fn run_actions(ed: &mut Editor, actions: &[Action], count: Option<usize>, register: Option<char>) {
    for action in actions {
        match action {
            Action::Command(name, args) => {
                if let Err(error) = crate::commands::run(ed, name, args, count, register) {
                    ed.error(error);
                }
            }
            Action::Ex(line) => crate::ex::run(ed, line),
            Action::Keys(text) => {
                let Ok(keys) = crate::keys::parse(text, &ed.keymap.leader.clone()) else {
                    ed.error(format!("bad keys {text:?}"));
                    continue;
                };
                // Mapped keys run vim's own meaning, not the mapping again (like noremap).
                ed.vim.replaying += 1;
                let saved = std::mem::take(&mut ed.keymap.normal);
                let saved_visual = std::mem::take(&mut ed.keymap.visual);
                if let Some(count) = count {
                    for c in count.to_string().chars() {
                        handle_key(ed, Key::char(c));
                    }
                }
                for key in keys {
                    handle_key(ed, key);
                }
                ed.keymap.normal = saved;
                ed.keymap.visual = saved_visual;
                ed.vim.replaying -= 1;
            }
            Action::Nop => {}
        }
    }
}

/// The range a motion covers from the cursor: (start, end exclusive, linewise).
fn motion_range(ed: &mut Editor, motion: Motion, count: usize, for_operator: bool) -> Option<(Pos, Pos, bool)> {
    let cursor = ed.cursor();
    let target = motion_target(ed, motion, count, for_operator)?;
    let linewise = motion.linewise();
    if linewise {
        return Some((Pos::new(cursor.line.min(target.line), 0), Pos::new(cursor.line.max(target.line), 0), true));
    }
    let (start, mut end) = (cursor.min(target), cursor.max(target));
    if motion.inclusive() {
        end = ed.doc().text.next(end).unwrap_or(ed.doc().text.end());
        if end.line > start.line && end.col == 0 && start.line != end.line {
            // Inclusive at a line end: stop at that line's end.
            let previous = end.line - 1;
            end = Pos::new(previous, ed.doc().text.line_len(previous));
        }
    } else if for_operator && end.line > start.line && end.col == 0 && end != start {
        // `dw` on the last word stops at the line end instead of joining lines.
        let previous = end.line - 1;
        if previous >= start.line {
            end = Pos::new(previous, ed.doc().text.line_len(previous));
        }
    }
    Some((start, end, false))
}

fn motion_target(ed: &mut Editor, motion: Motion, count: usize, for_operator: bool) -> Option<Pos> {
    let cursor = ed.cursor();
    let text = &ed.doc().text;
    let mut pos = cursor;
    let view_height = ed.view().area.h as usize;
    let scroll = ed.view().scroll;
    match motion {
        Motion::Left => pos.col = pos.col.saturating_sub(count),
        Motion::Right => {
            let len = text.line_len(pos.line);
            let max = if for_operator || matches!(ed.mode, Mode::Visual(_)) { len } else { len.saturating_sub(1) };
            pos.col = (pos.col + count).min(max);
        }
        Motion::Up => pos.line = pos.line.saturating_sub(count),
        Motion::Down => pos.line = (pos.line + count).min(text.last_line()),
        Motion::WordStart(big) => {
            for index in 0..count {
                let next = motion::word_start(text, pos, big);
                // `cw` and the last `dw` stop at the end of the line, not the next line.
                if for_operator && index + 1 == count && next.line > pos.line {
                    pos = Pos::new(pos.line, text.line_len(pos.line));
                    break;
                }
                pos = next;
            }
        }
        Motion::WordEnd(big) => {
            for _ in 0..count {
                pos = motion::word_end(text, pos, big);
            }
        }
        Motion::WordBack(big) => {
            for _ in 0..count {
                pos = motion::word_back(text, pos, big);
            }
        }
        Motion::WordEndBack(big) => {
            for _ in 0..count {
                pos = motion::word_end_back(text, pos, big);
            }
        }
        Motion::LineStart => pos.col = 0,
        Motion::FirstNonBlank => pos.col = text.first_non_blank(pos.line),
        Motion::LineEnd => {
            pos.line = (pos.line + count - 1).min(text.last_line());
            let len = text.line_len(pos.line);
            pos.col = len.saturating_sub(1);
        }
        Motion::LastNonBlank => {
            pos.line = (pos.line + count - 1).min(text.last_line());
            pos.col = char_len(text.line(pos.line).trim_end()).saturating_sub(1);
        }
        Motion::FileStart => {
            pos.line =
                if count > 1 || ed.vim.last_count_explicit { count.saturating_sub(1).min(text.last_line()) } else { 0 };
            pos.col = text.first_non_blank(pos.line);
        }
        Motion::FileEnd => {
            pos.line = if ed.vim.last_count_explicit {
                count.saturating_sub(1).min(text.last_line())
            } else {
                text.last_line()
            };
            pos.col = text.first_non_blank(pos.line);
        }
        Motion::ParagraphForward => {
            for _ in 0..count {
                pos.line = motion::paragraph(text, pos.line, true);
            }
            pos.col = 0;
            if pos.line == text.last_line() && !text.line(pos.line).trim().is_empty() {
                pos.col = text.line_len(pos.line).saturating_sub(usize::from(!for_operator));
            }
        }
        Motion::ParagraphBack => {
            for _ in 0..count {
                pos.line = motion::paragraph(text, pos.line, false);
            }
            pos.col = 0;
        }
        Motion::SentenceForward | Motion::SentenceBack => {
            for _ in 0..count {
                pos = motion::sentence(text, pos, motion == Motion::SentenceForward);
            }
        }
        Motion::MatchPair => {
            if ed.vim.last_count_explicit {
                // `50%`: to that percentage of the file.
                pos.line = (text.len_lines() * count.min(100)).div_ceil(100).saturating_sub(1);
                pos.col = text.first_non_blank(pos.line);
            } else {
                pos = motion::match_pair(text, pos)?;
            }
        }
        Motion::Find(kind, target) => {
            ed.vim.last_find = Some((kind, target));
            pos = motion::find_char(&ed.doc().text, pos, kind, target, count)?;
        }
        Motion::RepeatFind(reverse) => {
            let (kind, target) = ed.vim.last_find?;
            let kind = if reverse {
                match kind {
                    Find::Forward => Find::Backward,
                    Find::Backward => Find::Forward,
                    Find::Till => Find::TillBack,
                    Find::TillBack => Find::Till,
                }
            } else {
                kind
            };
            // `;` after `t` must not get stuck right before the same char.
            let from = match kind {
                Find::Till if text.char_at(Pos::new(pos.line, pos.col + 1)) == Some(target) => {
                    Pos::new(pos.line, pos.col + 1)
                }
                Find::TillBack if pos.col > 0 && text.char_at(Pos::new(pos.line, pos.col - 1)) == Some(target) => {
                    Pos::new(pos.line, pos.col - 1)
                }
                _ => pos,
            };
            pos = motion::find_char(text, from, kind, target, count)?;
        }
        Motion::ScreenTop | Motion::ScreenMiddle | Motion::ScreenBottom => {
            let last_visible = (scroll + view_height).saturating_sub(1).min(text.last_line());
            pos.line = match motion {
                Motion::ScreenTop => (scroll + count - 1).min(last_visible),
                Motion::ScreenMiddle => scroll + (last_visible - scroll) / 2,
                _ => last_visible.saturating_sub(count - 1).max(scroll),
            };
            pos.col = text.first_non_blank(pos.line);
        }
        Motion::SearchNext(reverse) => {
            let (_, forward) = ed.search.clone()?;
            let forward = forward != reverse;
            ed.search_regex.as_ref()?;
            for _ in 0..count {
                let (start, _, _) = ed.find_match(ed.doc(), pos, forward)?;
                pos = start;
            }
        }
        Motion::Column => {
            let line = text.line(pos.line);
            let tab = ed.tab_width(ed.doc());
            pos.col = crate::display::display_to_col(line, count.saturating_sub(1), tab);
        }
        Motion::NextLine => {
            pos.line = (pos.line + count).min(text.last_line());
            pos.col = text.first_non_blank(pos.line);
        }
        Motion::PrevLine => {
            pos.line = pos.line.saturating_sub(count);
            pos.col = text.first_non_blank(pos.line);
        }
        Motion::Mark(name, exact) => {
            let mark = match name {
                '\'' | '`' => ed.view().jumps.last().map(|(_, pos)| *pos)?,
                '.' => ed.vim.last_insert.map(|(_, pos)| pos)?,
                '<' => ed.last_visual.map(|(_, start, end, _)| start.min(end))?,
                '>' => ed.last_visual.map(|(_, start, end, _)| start.max(end))?,
                c => *ed.doc().marks.get(&c)?,
            };
            pos = ed.doc().text.clamp(mark);
            if !exact {
                pos.col = ed.doc().text.first_non_blank(pos.line);
            }
        }
    }
    Some(ed.doc().text.clamp(pos))
}

fn execute(ed: &mut Editor, cmd: Cmd, register: Option<char>, count: Option<usize>, keys: Vec<Key>) {
    ed.vim.last_count_explicit = count.is_some();
    let n = count.unwrap_or(1);
    let changes = matches!(cmd, Cmd::Op(op, _) if op != Op::Yank)
        || matches!(
            cmd,
            Cmd::Act(
                Act::Insert(_)
                    | Act::DeleteChar(_)
                    | Act::Substitute
                    | Act::SubstituteLine
                    | Act::ChangeToEnd
                    | Act::DeleteToEnd
                    | Act::ReplaceChar(_)
                    | Act::Join(_)
                    | Act::Put(..)
                    | Act::ToggleCase
                    | Act::Increment(_)
            )
        );
    let visual = matches!(ed.mode, Mode::Visual(_));
    if changes && ed.vim.replaying == 0 && !visual {
        ed.vim.recording_change = Some(keys);
        ed.vim.last_change_count = count;
    }
    match cmd {
        Cmd::Move(motion) => {
            if motion.is_jump() {
                ed.push_jump();
            }
            match motion {
                Motion::Up | Motion::Down => {
                    let delta = if motion == Motion::Up { -(n as isize) } else { n as isize };
                    ed.move_lines(delta);
                }
                Motion::LineEnd => {
                    if let Some(target) = motion_target(ed, motion, n, false) {
                        let visual = matches!(ed.mode, Mode::Visual(_));
                        ed.set_cursor(target);
                        if visual && ed.doc().text.line_len(target.line) > 0 {
                            ed.view_mut().cursor.col = ed.doc().text.line_len(target.line) - 1;
                        }
                        ed.view_mut().want_col = Some(usize::MAX);
                    }
                }
                _ => match motion_target(ed, motion, n, false) {
                    Some(target) => ed.set_cursor(target),
                    None if matches!(motion, Motion::SearchNext(_)) => {
                        ed.search_next(matches!(motion, Motion::SearchNext(true)), n);
                    }
                    None => {}
                },
            }
            if let Motion::SearchNext(reverse) = motion {
                if ed.search_regex.is_some() {
                    ed.search_status(reverse);
                }
            }
        }
        Cmd::Op(op, target) => {
            if let Mode::Visual(kind) = ed.mode {
                visual_operator(ed, op, kind, register, target);
            } else {
                normal_operator(ed, op, target, register, count);
            }
        }
        Cmd::Act(act) => act_on(ed, act, register, count),
    }
    if ed.mode == Mode::Normal || matches!(ed.mode, Mode::Visual(_)) {
        if let Some(keys) = ed.vim.recording_change.take() {
            ed.vim.last_change = Some(keys);
        }
        edit::commit(ed);
        ed.clamp_cursor();
    }
}

fn normal_operator(ed: &mut Editor, op: Op, target: Target, register: Option<char>, count: Option<usize>) {
    let n = count.unwrap_or(1);
    let cursor = ed.cursor();
    let range = match target {
        Target::Line(inner) => {
            let lines = n * inner.unwrap_or(1);
            let last = (cursor.line + lines - 1).min(ed.doc().text.last_line());
            Some((Pos::new(cursor.line, 0), Pos::new(last, 0), true))
        }
        Target::Motion(Motion::WordStart(big), inner)
            if op == Op::Change && ed.doc().text.char_at(cursor).is_some_and(|c| !c.is_whitespace()) =>
        {
            // `cw` changes to the end of the word like `ce` (vim's special case).
            let text = &ed.doc().text;
            let mut end = cursor;
            for index in 0..n * inner.unwrap_or(1) {
                let at_word_end = text.next(end).is_none_or(|next| motion::class_of(text, next, big) != motion::class_of(text, end, big));
                if !(index == 0 && at_word_end) {
                    end = motion::word_end(text, end, big);
                }
            }
            Some((cursor, text.next(end).unwrap_or(text.end()), false))
        }
        Target::Motion(motion, inner) => motion_range(ed, motion, n * inner.unwrap_or(1), true),
        Target::Object(object, kind, inner) => {
            motion::object(&ed.doc().text, cursor, object, kind, n * inner.unwrap_or(1)).map(|(start, end, linewise)| {
                if linewise {
                    (start, Pos::new(end.line, 0), true)
                } else {
                    (start, end, false)
                }
            })
        }
    };
    let Some((start, end, linewise)) = range else {
        return;
    };
    if !linewise && start == end && op != Op::Change {
        return;
    }
    edit::operator(ed, op, start, end, linewise, register);
    if op == Op::Change {
        start_insert(ed, 1);
    }
}

fn visual_operator(ed: &mut Editor, op: Op, kind: VisualKind, register: Option<char>, target: Target) {
    let anchor = ed.anchor;
    let cursor = ed.cursor();
    ed.last_visual = Some((ed.view().doc, anchor, cursor, kind));
    let (start, end) = (anchor.min(cursor), anchor.max(cursor));
    // `D`, `C`, `Y` in visual mode work on whole lines.
    let whole_lines = target == Target::Object('l', false, None);
    ed.mode = Mode::Normal;
    if kind == VisualKind::Block && !whole_lines {
        edit::block_operator(ed, op, anchor, cursor, register);
        if op == Op::Change {
            ed.mode = Mode::Insert;
        }
        return;
    }
    let linewise = kind == VisualKind::Line || whole_lines || matches!(op, Op::Indent | Op::Dedent | Op::Comment);
    let end_exclusive =
        if linewise { Pos::new(end.line, 0) } else { ed.doc().text.next(end).unwrap_or(ed.doc().text.end()) };
    let start = if linewise { Pos::new(start.line, 0) } else { start };
    edit::operator(ed, op, start, end_exclusive, linewise, register);
    if op == Op::Change {
        start_insert(ed, 1);
    }
    // `>` and `<` keep the selection so they can be repeated.
    if matches!(op, Op::Indent | Op::Dedent) && ed.vim.replaying == 0 {
        ed.mode = Mode::Visual(kind);
        ed.anchor = Pos::new(anchor.line, 0);
        let line_len = ed.doc().text.line_len(cursor.line);
        ed.view_mut().cursor = Pos::new(cursor.line, cursor.col.min(line_len.saturating_sub(1)));
    }
}

fn start_insert(ed: &mut Editor, count: usize) {
    ed.mode = Mode::Insert;
    ed.vim.insert_keys.clear();
    ed.vim.insert_repeat = if count > 1 { Some((count, Vec::new(), false)) } else { None };
    let doc = ed.view().doc;
    let cursor = ed.cursor();
    ed.vim.last_insert = Some((doc, cursor));
}

fn act_on(ed: &mut Editor, act: Act, register: Option<char>, count: Option<usize>) {
    let n = count.unwrap_or(1);
    let cursor = ed.cursor();
    match act {
        Act::Escape => {
            if matches!(ed.mode, Mode::Visual(_)) {
                exit_visual(ed);
            }
            ed.vim.recording_change = None;
        }
        Act::Insert(kind) => {
            let len = ed.doc().text.line_len(cursor.line);
            match kind {
                'i' => {}
                'a' => ed.view_mut().cursor.col = (cursor.col + 1).min(len),
                'I' => ed.view_mut().cursor.col = ed.doc().text.first_non_blank(cursor.line),
                '0' => ed.view_mut().cursor.col = 0,
                'A' => ed.view_mut().cursor.col = len,
                'g' => {
                    if let Some((doc, pos)) = ed.vim.last_insert {
                        if doc == ed.view().doc {
                            ed.view_mut().cursor = ed.doc().text.clamp(pos);
                        }
                    }
                }
                'o' | 'O' => {
                    edit::open_line(ed, kind == 'o');
                    start_insert(ed, 1);
                    if n > 1 {
                        ed.vim.insert_repeat = Some((n, Vec::new(), true));
                    }
                    return;
                }
                _ => {}
            }
            start_insert(ed, n);
        }
        Act::DeleteChar(forward) => {
            let len = ed.doc().text.line_len(cursor.line);
            if forward {
                if len == 0 {
                    return;
                }
                let end = Pos::new(cursor.line, (cursor.col + n).min(len));
                edit::operator(ed, Op::Delete, cursor, end, false, register);
            } else if cursor.col > 0 {
                let start = Pos::new(cursor.line, cursor.col.saturating_sub(n));
                edit::operator(ed, Op::Delete, start, cursor, false, register);
            }
        }
        Act::Substitute => {
            let len = ed.doc().text.line_len(cursor.line);
            let end = Pos::new(cursor.line, (cursor.col + n).min(len));
            edit::operator(ed, Op::Change, cursor, end, false, register);
            start_insert(ed, 1);
        }
        Act::SubstituteLine => {
            let last = (cursor.line + n - 1).min(ed.doc().text.last_line());
            edit::operator(ed, Op::Change, Pos::new(cursor.line, 0), Pos::new(last, 0), true, register);
            start_insert(ed, 1);
        }
        Act::ChangeToEnd | Act::DeleteToEnd => {
            let last = (cursor.line + n - 1).min(ed.doc().text.last_line());
            let end = Pos::new(last, ed.doc().text.line_len(last));
            let op = if act == Act::ChangeToEnd { Op::Change } else { Op::Delete };
            edit::operator(ed, op, cursor, end, false, register);
            if op == Op::Change {
                start_insert(ed, 1);
            } else {
                ed.clamp_cursor();
            }
        }
        Act::YankLine => {
            let last = (cursor.line + n - 1).min(ed.doc().text.last_line());
            edit::operator(ed, Op::Yank, Pos::new(cursor.line, 0), Pos::new(last, 0), true, register);
            ed.set_cursor(cursor);
        }
        Act::ReplaceChar(c) => {
            if let Some((start, end, kind)) = ed.selection() {
                ed.mode = Mode::Normal;
                let (from, to) = if kind == VisualKind::Line {
                    (Pos::new(start.line, 0), Pos::new(end.line, ed.doc().text.line_len(end.line)))
                } else {
                    (start, ed.doc().text.next(end).unwrap_or(end))
                };
                let text = ed.doc().text.slice(from, to);
                let replaced: String = text.chars().map(|x| if x == '\n' { x } else { c }).collect();
                ed.doc_mut().replace(from, to, &replaced, cursor);
                ed.set_cursor(from);
                return;
            }
            let len = ed.doc().text.line_len(cursor.line);
            if cursor.col + n > len {
                return;
            }
            let end = Pos::new(cursor.line, cursor.col + n);
            if c == '\n' {
                ed.doc_mut().replace(cursor, end, "\n", cursor);
                let indent = ed.doc().text.indent_of(cursor.line).to_string();
                ed.doc_mut().insert(Pos::new(cursor.line + 1, 0), &indent, cursor);
                ed.set_cursor(Pos::new(cursor.line + 1, char_len(&indent)));
            } else {
                ed.doc_mut().replace(cursor, end, &c.to_string().repeat(n), cursor);
                ed.set_cursor(Pos::new(cursor.line, cursor.col + n - 1));
            }
        }
        Act::ReplaceMode => {
            ed.mode = Mode::Replace;
            ed.vim.insert_keys.clear();
        }
        Act::Join(spaces) => {
            if let Some((start, end, _)) = ed.selection() {
                ed.mode = Mode::Normal;
                edit::join_lines(ed, start.line, end.line - start.line + 1, spaces);
            } else {
                edit::join_lines(ed, cursor.line, n, spaces);
            }
        }
        Act::Put(after, cursor_after) => {
            if matches!(ed.mode, Mode::Visual(_)) {
                edit::put_over_selection(ed, register, !after);
            } else {
                edit::put(ed, register, after, n, cursor_after);
            }
        }
        Act::Undo => {
            for _ in 0..n {
                match ed.doc_mut().undo(cursor) {
                    Some(pos) => ed.set_cursor(pos),
                    None => {
                        ed.info("already at the oldest change");
                        break;
                    }
                }
            }
        }
        Act::Redo => {
            for _ in 0..n {
                match ed.doc_mut().redo(cursor) {
                    Some(pos) => ed.set_cursor(pos),
                    None => {
                        ed.info("already at the newest change");
                        break;
                    }
                }
            }
        }
        Act::Repeat => repeat_change(ed, count),
        Act::ToggleCase => {
            let len = ed.doc().text.line_len(cursor.line);
            if len == 0 {
                return;
            }
            let end = Pos::new(cursor.line, (cursor.col + n).min(len));
            edit::operator(ed, Op::Toggle, cursor, end, false, None);
            ed.set_cursor(Pos::new(cursor.line, end.col.min(len - 1)));
        }
        Act::Visual(kind) => match ed.mode {
            Mode::Visual(current) if current == kind => exit_visual(ed),
            Mode::Visual(_) => ed.mode = Mode::Visual(kind),
            _ => {
                ed.mode = Mode::Visual(kind);
                ed.anchor = cursor;
            }
        },
        Act::Reselect => {
            if let Some((doc, start, end, kind)) = ed.last_visual {
                if doc == ed.view().doc {
                    ed.mode = Mode::Visual(kind);
                    ed.anchor = ed.doc().text.clamp(start);
                    ed.set_cursor(end);
                }
            }
        }
        Act::Record(name) => {
            if ed.vim.macro_recording.is_some() {
                stop_recording(ed);
            } else if name.is_ascii_alphanumeric() || name == '"' {
                ed.vim.macro_recording = Some((name, Vec::new()));
                ed.info(format!("recording @{name}"));
            }
        }
        Act::Play(name) => {
            let name = match name {
                '@' => match ed.vim.last_macro {
                    Some(name) => name,
                    None => {
                        ed.error("no macro played yet");
                        return;
                    }
                },
                ':' => {
                    if let Some(line) = ed.vim.last_ex.clone() {
                        for _ in 0..n {
                            crate::ex::run(ed, &line);
                        }
                    }
                    return;
                }
                c => c,
            };
            play_macro(ed, name, n);
        }
        Act::Mark(name) => {
            if name.is_ascii_alphabetic() {
                ed.doc_mut().marks.insert(name, cursor);
            }
        }
        Act::Search(forward) => {
            let scroll = ed.view().scroll;
            ed.prompt = Some(crate::widgets::Prompt::new(
                crate::widgets::PromptKind::Search { forward, origin: cursor, scroll },
                "",
            ));
        }
        Act::SearchWord(forward, whole) => {
            let Some((_, _, word)) = motion::word_at(&ed.doc().text, cursor) else {
                ed.error("no word under the cursor");
                return;
            };
            let pattern = if whole { format!("\\<{}\\>", regex::escape(&word)) } else { regex::escape(&word) };
            // `*` is case-sensitive only when smartcase would make it so.
            if let Err(error) = ed.set_search(&pattern, forward) {
                ed.error(error);
                return;
            }
            if let Some((start, _, _)) = motion::word_at(&ed.doc().text, cursor) {
                ed.view_mut().cursor = start;
            }
            ed.search_next(false, n);
        }
        Act::Command => {
            let text = match ed.mode {
                Mode::Visual(_) => "'<,'>".to_string(),
                _ => count
                    .map_or(String::new(), |count| if count == 1 { ".".into() } else { format!(".,.+{}", count - 1) }),
            };
            if let Mode::Visual(kind) = ed.mode {
                ed.last_visual = Some((ed.view().doc, ed.anchor, cursor, kind));
                ed.mode = Mode::Normal;
            }
            ed.prompt = Some(crate::widgets::Prompt::new(crate::widgets::PromptKind::Command, &text));
        }
        Act::ScrollLines(delta) => {
            let height = ed.view().area.h as usize;
            let last = ed.doc().text.last_line();
            let view = ed.view_mut();
            let scroll = (view.scroll as isize + delta * n as isize).clamp(0, last as isize) as usize;
            view.scroll = scroll;
            let so = ed.options.scrolloff.min(height / 2);
            let mut cursor = ed.cursor();
            if cursor.line < scroll + so {
                cursor.line = (scroll + so).min(last);
            }
            if cursor.line + so >= scroll + height {
                cursor.line = (scroll + height).saturating_sub(so + 1);
            }
            ed.set_cursor(cursor);
        }
        Act::Page(direction, half) => {
            let height = ed.view().area.h.max(2) as isize;
            let amount = if half { height / 2 } else { height - 2 };
            ed.scroll_page(direction * amount * n as isize);
        }
        Act::Align(at) => ed.align_cursor(at),
        Act::Increment(delta) => edit::increment(ed, delta * n as i64),
        Act::Jump(back) => {
            for _ in 0..n {
                ed.jump(back);
            }
        }
        Act::WriteQuit => crate::ex::run(ed, "x"),
        Act::QuitForce => crate::ex::run(ed, "q!"),
        Act::RepeatSubstitute => crate::ex::run(ed, "s"),
        Act::FileInfo => {
            let doc = ed.doc();
            let lines = doc.text.len_lines();
            let percent = (cursor.line + 1) * 100 / lines.max(1);
            let modified = if doc.modified() { " [+]" } else { "" };
            let text = format!("\"{}\"{modified} {lines} lines --{percent}%--", doc.title());
            ed.info(text);
        }
        Act::SwapAnchor => {
            let anchor = ed.anchor;
            ed.anchor = cursor;
            ed.view_mut().cursor = anchor;
        }
        Act::VisualObject(object, inner) => {
            if let Some((start, end, linewise)) = motion::object(&ed.doc().text, cursor, object, inner, n) {
                if linewise {
                    ed.mode = Mode::Visual(VisualKind::Line);
                }
                ed.anchor = start;
                let end = if linewise { end } else { ed.doc().text.prev(end).unwrap_or(end).max(start) };
                ed.view_mut().cursor = end;
            }
        }
        Act::VisualInsert(append) => {
            let Some((start, end, kind)) = ed.selection() else {
                return;
            };
            let tab = ed.tab_width(ed.doc());
            ed.last_visual = Some((ed.view().doc, ed.anchor, cursor, kind));
            ed.mode = Mode::Normal;
            if kind == VisualKind::Block {
                let a = col_to_display(ed.doc().text.line(ed.anchor.line), ed.anchor.col, tab);
                let b = col_to_display(ed.doc().text.line(cursor.line), cursor.col, tab);
                let column = if append { a.max(b) + 1 } else { a.min(b) };
                edit::start_block_insert(ed, start.line, end.line, column, append);
            } else if append {
                let target = if kind == VisualKind::Line {
                    Pos::new(end.line, ed.doc().text.line_len(end.line))
                } else {
                    ed.doc().text.next(end).unwrap_or(end)
                };
                ed.view_mut().cursor = target;
                start_insert(ed, 1);
            } else {
                let target = if kind == VisualKind::Line {
                    Pos::new(start.line, ed.doc().text.first_non_blank(start.line))
                } else {
                    start
                };
                ed.view_mut().cursor = target;
                start_insert(ed, 1);
            }
            ed.mode = Mode::Insert;
        }
    }
}

pub fn exit_visual(ed: &mut Editor) {
    ed.vim.select_mode = false;
    ed.vim.select_from_insert = false;
    if let Mode::Visual(kind) = ed.mode {
        ed.last_visual = Some((ed.view().doc, ed.anchor, ed.cursor(), kind));
    }
    ed.mode = Mode::Normal;
    ed.clamp_cursor();
}

fn repeat_change(ed: &mut Editor, count: Option<usize>) {
    let Some(keys) = ed.vim.last_change.clone() else {
        return;
    };
    let count = count.or(ed.vim.last_change_count);
    ed.vim.replaying += 1;
    let saved_complete = ed.options.auto_complete;
    ed.options.auto_complete = false;
    // Register prefix first, then the count, then the command.
    let (register_keys, rest) =
        if keys.first().and_then(ch) == Some('"') && keys.len() > 2 { keys.split_at(2) } else { keys.split_at(0) };
    for key in register_keys {
        handle_key(ed, *key);
    }
    if let Some(count) = count {
        for c in count.to_string().chars() {
            handle_key(ed, Key::char(c));
        }
    }
    for key in rest {
        handle_key(ed, *key);
    }
    if matches!(ed.mode, Mode::Insert | Mode::Replace) {
        handle_key(ed, Key::plain(Code::Esc));
    }
    ed.options.auto_complete = saved_complete;
    ed.vim.replaying -= 1;
}

pub fn play_macro(ed: &mut Editor, name: char, count: usize) {
    let keys: Vec<Key> = match ed.registers.get(&name.to_ascii_lowercase()) {
        Some(register) => match crate::keys::parse(&register.text, &[]) {
            Ok(keys) => keys,
            Err(_) => register.text.chars().map(Key::char).collect(),
        },
        None => {
            ed.error(format!("register {name} is empty"));
            return;
        }
    };
    if ed.vim.replaying > 20 {
        ed.error("macro recursion stopped");
        return;
    }
    ed.vim.last_macro = Some(name);
    ed.vim.replaying += 1;
    for _ in 0..count {
        for key in &keys {
            handle_key(ed, *key);
        }
    }
    ed.vim.replaying -= 1;
}

/// Ends a macro recording started with `q`; called when `q` is pressed while recording.
fn stop_recording(ed: &mut Editor) -> bool {
    let Some((name, mut keys)) = ed.vim.macro_recording.take() else {
        return false;
    };
    keys.pop();
    let text = crate::keys::notation(&keys);
    ed.registers.insert(name.to_ascii_lowercase(), crate::editor::Register { text, linewise: false });
    ed.vim.last_recorded = Some(name);
    ed.info(format!("recorded @{name}"));
    true
}

// --- insert mode ---------------------------------------------------------------------

fn insert_key(ed: &mut Editor, key: Key) {
    if ed.vim.replaying == 0 {
        if let Some(recording) = ed.vim.recording_change.as_mut() {
            recording.push(key);
        }
    }
    if ed.vim.insert_register {
        ed.vim.insert_register = false;
        if let Some(name) = key.as_char() {
            if let Some(register) = ed.get_register(Some(name)) {
                insert_text(ed, &register.text);
            }
        }
        return;
    }
    // Insert-mode bindings like "jk": hold keys that start one.
    if ed.vim.replaying == 0 || !ed.vim.insert_pending.is_empty() {
        let mut keys = ed.vim.insert_pending.clone();
        keys.push(key);
        match ed.keymap.lookup(KeyMode::Insert, &keys) {
            Lookup::Exact(binding) => {
                let actions = binding.actions.clone();
                ed.vim.insert_pending.clear();
                run_actions(ed, &actions, None, None);
                return;
            }
            Lookup::Prefix | Lookup::ExactAndPrefix(_) => {
                ed.vim.insert_pending = keys;
                ed.vim.pending_since = Some(Instant::now());
                return;
            }
            Lookup::None => {
                if !ed.vim.insert_pending.is_empty() {
                    let held = std::mem::take(&mut ed.vim.insert_pending);
                    flush_insert_pending(ed, held);
                }
            }
        }
    }
    insert_action(ed, key);
}

fn flush_insert_pending(ed: &mut Editor, keys: Vec<Key>) {
    for key in keys {
        insert_action(ed, key);
    }
}

fn insert_action(ed: &mut Editor, key: Key) {
    if !key.is_esc() {
        ed.vim.insert_keys.push(key);
    }
    let completion_open = ed.completion.as_ref().is_some_and(|completion| !completion.shown.is_empty());
    match (key.code, key.ctrl, key.alt) {
        _ if key.is_esc() => {
            leave_insert(ed);
            return;
        }
        (Code::Enter, false, _) => {
            if completion_open && ed.completion.as_ref().is_some_and(|completion| completion.selected.is_some()) {
                crate::complete::accept(ed);
                return;
            }
            ed.completion = None;
            edit::newline(ed);
        }
        (Code::Tab, false, false) => {
            if completion_open {
                if let Some(completion) = ed.completion.as_mut() {
                    completion.step(1);
                }
                return;
            }
            edit::insert_tab(ed);
        }
        (Code::BackTab, _, _) => {
            if completion_open {
                if let Some(completion) = ed.completion.as_mut() {
                    completion.step(-1);
                }
                return;
            }
            let line = ed.cursor().line;
            let before = ed.doc().text.line_len(line);
            edit::shift_lines(ed, line, line, false, 1);
            let after = ed.doc().text.line_len(line);
            let cursor = ed.cursor();
            ed.view_mut().cursor.col = cursor.col.saturating_sub(before - after);
        }
        (Code::Char('n'), true, false) | (Code::Down, false, false) if completion_open => {
            if let Some(completion) = ed.completion.as_mut() {
                completion.step(1);
            }
            return;
        }
        (Code::Char('p'), true, false) | (Code::Up, false, false) if completion_open => {
            if let Some(completion) = ed.completion.as_mut() {
                completion.step(-1);
            }
            return;
        }
        (Code::Char('n'), true, false) | (Code::Char('p'), true, false) => {
            crate::complete::trigger(ed, true);
            if let Some(completion) = ed.completion.as_mut() {
                completion.step(if key == Key::ctrl('n') { 1 } else { -1 });
            }
            return;
        }
        (Code::Char('y'), true, false) if completion_open => {
            if ed.completion.as_ref().is_some_and(|completion| completion.selected.is_none()) {
                if let Some(completion) = ed.completion.as_mut() {
                    completion.step(1);
                }
            }
            crate::complete::accept(ed);
            return;
        }
        (Code::Char('e'), true, false) if completion_open => {
            ed.completion = None;
            return;
        }
        (Code::Char(' '), true, false) => {
            crate::complete::trigger(ed, true);
            return;
        }
        (Code::Backspace, _, false) | (Code::Char('h'), true, false) => {
            edit::backspace(ed);
            crate::complete::refilter(ed);
            return;
        }
        (Code::Backspace, _, true) | (Code::Char('w'), true, false) => edit::delete_word_back(ed),
        (Code::Char('u'), true, false) => edit::delete_to_line_start(ed),
        (Code::Delete, _, _) => {
            let cursor = ed.cursor();
            let next = ed.doc().text.next(cursor);
            if let Some(next) = next {
                ed.doc_mut().remove(cursor, next, cursor);
            }
        }
        (Code::Char('r'), true, false) => {
            ed.vim.insert_register = true;
            return;
        }
        (Code::Char('t'), true, false) | (Code::Char('d'), true, false) => {
            let line = ed.cursor().line;
            let before = ed.doc().text.line_len(line) as isize;
            edit::shift_lines(ed, line, line, key == Key::ctrl('t'), 1);
            let after = ed.doc().text.line_len(line) as isize;
            let cursor = ed.cursor();
            ed.view_mut().cursor.col = (cursor.col as isize + after - before).max(0) as usize;
        }
        (Code::Left, _, _)
        | (Code::Right, _, _)
        | (Code::Up, _, _)
        | (Code::Down, _, _)
        | (Code::Home, _, _)
        | (Code::End, _, _) => {
            edit::commit(ed);
            ed.completion = None;
            let cursor = ed.cursor();
            let len = ed.doc().text.line_len(cursor.line);
            match key.code {
                Code::Left if key.ctrl || key.alt => {
                    let target = motion::word_back(&ed.doc().text, cursor, false);
                    ed.view_mut().cursor = target;
                }
                Code::Right if key.ctrl || key.alt => {
                    let target = motion::word_start(&ed.doc().text, cursor, false);
                    ed.view_mut().cursor = target;
                }
                Code::Left => ed.view_mut().cursor.col = cursor.col.saturating_sub(1),
                Code::Right => ed.view_mut().cursor.col = (cursor.col + 1).min(len),
                Code::Up => ed.move_lines(-1),
                Code::Down => ed.move_lines(1),
                Code::Home => ed.view_mut().cursor.col = 0,
                _ => ed.view_mut().cursor.col = len,
            }
            if !matches!(key.code, Code::Up | Code::Down) {
                ed.view_mut().want_col = None;
            }
            return;
        }
        (Code::Char(c), false, false) => {
            edit::type_char(ed, c);
            if ed.options.auto_complete && ed.vim.replaying == 0 {
                crate::complete::after_typing(ed, c);
            }
            return;
        }
        _ => return,
    }
    crate::complete::refilter(ed);
}

pub fn insert_text(ed: &mut Editor, text: &str) {
    let cursor = ed.cursor();
    let end = ed.doc_mut().insert(cursor, text, cursor);
    ed.view_mut().cursor = end;
}

pub fn leave_insert(ed: &mut Editor) {
    ed.completion = None;
    if ed.vim.block_insert.is_some() {
        edit::finish_block_insert(ed);
    }
    // `3ihi<Esc>`: type the same text count-1 more times.
    if let Some((count, _, open_line)) = ed.vim.insert_repeat.take() {
        let keys = ed.vim.insert_keys.clone();
        ed.vim.replaying += 1;
        for _ in 1..count {
            if open_line {
                edit::open_line(ed, true);
            }
            for key in &keys {
                insert_action(ed, *key);
            }
        }
        ed.vim.replaying -= 1;
    }
    let cursor = ed.cursor();
    let doc = ed.view().doc;
    ed.vim.last_insert = Some((doc, cursor));
    ed.mode = Mode::Normal;
    if ed.vim.replaying == 0 {
        if let Some(mut keys) = ed.vim.recording_change.take() {
            if !keys.last().is_some_and(Key::is_esc) {
                keys.push(Key::plain(Code::Esc));
            }
            ed.vim.last_change = Some(keys);
        }
    }
    edit::commit(ed);
    if cursor.col > 0 {
        ed.view_mut().cursor.col = cursor.col - 1;
    }
    ed.view_mut().want_col = None;
    ed.clamp_cursor();
}

/// `q` while recording stops the macro; routed here from normal mode before parsing.
pub fn intercept(ed: &mut Editor, key: Key) -> bool {
    if ed.vim.macro_recording.is_some() && ed.vim.pending.is_empty() && key == Key::char('q') && ed.mode == Mode::Normal
    {
        return stop_recording(ed);
    }
    false
}

impl Editor {
    pub fn search_status(&mut self, reverse: bool) {
        let _ = reverse;
        let Some((pattern, forward)) = self.search.clone() else {
            return;
        };
        let total = self.count_matches();
        let prefix = if forward != reverse { "/" } else { "?" };
        self.info(format!("{prefix}{pattern}  [{total} matches]"));
    }
}
