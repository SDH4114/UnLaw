//! Keys and their vim-style notation: `a`, `<C-s>`, `<leader>f`, `<S-Tab>`.

use crossterm::event::{KeyCode, KeyEvent, KeyEventKind, KeyModifiers};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Code {
    Char(char),
    Esc,
    Enter,
    Tab,
    BackTab,
    Backspace,
    Delete,
    Up,
    Down,
    Left,
    Right,
    Home,
    End,
    PageUp,
    PageDown,
    Insert,
    F(u8),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Key {
    pub code: Code,
    pub ctrl: bool,
    pub alt: bool,
    /// Only for keys whose shifted form is not a different char (`<S-Tab>`, `<S-Up>`).
    pub shift: bool,
}

impl Key {
    pub const fn plain(code: Code) -> Self {
        Key { code, ctrl: false, alt: false, shift: false }
    }

    pub const fn char(c: char) -> Self {
        Key::plain(Code::Char(c))
    }

    pub const fn ctrl(c: char) -> Self {
        Key { code: Code::Char(c), ctrl: true, alt: false, shift: false }
    }

    pub fn as_char(&self) -> Option<char> {
        match self.code {
            Code::Char(c) if !self.ctrl && !self.alt => Some(c),
            _ => None,
        }
    }

    pub fn is_esc(&self) -> bool {
        self.code == Code::Esc || *self == Key::ctrl('[') || *self == Key::ctrl('c')
    }

    pub fn from_event(event: KeyEvent) -> Option<Key> {
        if event.kind == KeyEventKind::Release {
            return None;
        }
        let ctrl = event.modifiers.contains(KeyModifiers::CONTROL);
        let alt = event.modifiers.contains(KeyModifiers::ALT);
        let shift = event.modifiers.contains(KeyModifiers::SHIFT);
        let code = match event.code {
            KeyCode::Char(c) => {
                // Terminals report Ctrl+Shift+a as Ctrl+A; keep letters lower case under Ctrl.
                let c = if ctrl && c.is_ascii_uppercase() { c.to_ascii_lowercase() } else { c };
                return Some(Key { code: Code::Char(c), ctrl, alt, shift: false });
            }
            KeyCode::Esc => Code::Esc,
            KeyCode::Enter => Code::Enter,
            KeyCode::Tab => Code::Tab,
            KeyCode::BackTab => Code::BackTab,
            KeyCode::Backspace => Code::Backspace,
            KeyCode::Delete => Code::Delete,
            KeyCode::Up => Code::Up,
            KeyCode::Down => Code::Down,
            KeyCode::Left => Code::Left,
            KeyCode::Right => Code::Right,
            KeyCode::Home => Code::Home,
            KeyCode::End => Code::End,
            KeyCode::PageUp => Code::PageUp,
            KeyCode::PageDown => Code::PageDown,
            KeyCode::Insert => Code::Insert,
            KeyCode::F(n) => Code::F(n),
            _ => return None,
        };
        let shift = shift && code != Code::BackTab;
        Some(Key { code, ctrl, alt, shift })
    }

    pub fn notation(&self) -> String {
        let name = match self.code {
            Code::Char(' ') => "space".to_string(),
            Code::Char('<') => "lt".to_string(),
            Code::Char(c) if !self.ctrl && !self.alt && !self.shift => return c.to_string(),
            Code::Char(c) => c.to_string(),
            Code::Esc => "esc".into(),
            Code::Enter => "cr".into(),
            Code::Tab => "tab".into(),
            Code::BackTab => "s-tab".into(),
            Code::Backspace => "bs".into(),
            Code::Delete => "del".into(),
            Code::Up => "up".into(),
            Code::Down => "down".into(),
            Code::Left => "left".into(),
            Code::Right => "right".into(),
            Code::Home => "home".into(),
            Code::End => "end".into(),
            Code::PageUp => "pageup".into(),
            Code::PageDown => "pagedown".into(),
            Code::Insert => "insert".into(),
            Code::F(n) => format!("f{n}"),
        };
        let mut prefix = String::new();
        if self.ctrl {
            prefix.push_str("C-");
        }
        if self.alt {
            prefix.push_str("A-");
        }
        if self.shift {
            prefix.push_str("S-");
        }
        format!("<{prefix}{name}>")
    }
}

pub fn notation(keys: &[Key]) -> String {
    keys.iter().map(Key::notation).collect()
}

fn named(name: &str) -> Option<Code> {
    Some(match name {
        "space" => Code::Char(' '),
        "lt" => Code::Char('<'),
        "gt" => Code::Char('>'),
        "bar" => Code::Char('|'),
        "bslash" => Code::Char('\\'),
        "esc" | "escape" => Code::Esc,
        "cr" | "enter" | "return" => Code::Enter,
        "tab" => Code::Tab,
        "s-tab" => Code::BackTab,
        "bs" | "backspace" => Code::Backspace,
        "del" | "delete" => Code::Delete,
        "up" => Code::Up,
        "down" => Code::Down,
        "left" => Code::Left,
        "right" => Code::Right,
        "home" => Code::Home,
        "end" => Code::End,
        "pageup" => Code::PageUp,
        "pagedown" => Code::PageDown,
        "insert" => Code::Insert,
        _ => {
            let number = name.strip_prefix('f')?.parse::<u8>().ok()?;
            Code::F(number)
        }
    })
}

/// Parses `"<C-w>v"`, `"<leader>ff"`, `"gg"`; `<leader>` becomes `leader`.
pub fn parse(text: &str, leader: &[Key]) -> Result<Vec<Key>, String> {
    let mut keys = Vec::new();
    let mut rest = text;
    while let Some(c) = rest.chars().next() {
        if c == '<' {
            if let Some(close) = rest.find('>') {
                let inner = &rest[1..close];
                // `<<` or `< b>` are literal `<` keys, not names.
                if !inner.is_empty() && !inner.contains(['<', ' ']) {
                    if inner.eq_ignore_ascii_case("leader") {
                        keys.extend_from_slice(leader);
                    } else {
                        keys.push(parse_angle(inner).ok_or_else(|| format!("unknown key <{inner}> in {text:?}"))?);
                    }
                    rest = &rest[close + 1..];
                    continue;
                }
            }
        }
        keys.push(Key::char(c));
        rest = &rest[c.len_utf8()..];
    }
    if keys.is_empty() {
        return Err("empty key sequence".into());
    }
    Ok(keys)
}

fn parse_angle(inner: &str) -> Option<Key> {
    let lower = inner.to_ascii_lowercase();
    if let Some(code) = named(&lower) {
        return Some(Key::plain(code));
    }
    let (mut ctrl, mut alt, mut shift) = (false, false, false);
    let mut name = inner;
    loop {
        let head = name.get(..2).map(str::to_ascii_lowercase);
        match head.as_deref() {
            Some("c-") if name.len() > 2 => ctrl = true,
            Some("a-") | Some("m-") if name.len() > 2 => alt = true,
            Some("s-") if name.len() > 2 => shift = true,
            _ => break,
        }
        name = &name[2..];
    }
    let mut chars = name.chars();
    let code = match (chars.next(), chars.next()) {
        (Some(c), None) => {
            let c = if ctrl { c.to_ascii_lowercase() } else { c };
            if shift && c.is_alphabetic() {
                return Some(Key { code: Code::Char(c.to_uppercase().next().unwrap_or(c)), ctrl, alt, shift: false });
            }
            Code::Char(c)
        }
        _ => named(&name.to_ascii_lowercase())?,
    };
    if code == Code::Tab && shift && !ctrl && !alt {
        return Some(Key::plain(Code::BackTab));
    }
    Some(Key { code, ctrl, alt, shift: shift && !matches!(code, Code::Char(_)) })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_vim_notation() {
        let leader = [Key::char(' ')];
        assert_eq!(parse("gg", &leader).unwrap(), vec![Key::char('g'), Key::char('g')]);
        assert_eq!(parse("<C-w>v", &leader).unwrap(), vec![Key::ctrl('w'), Key::char('v')]);
        assert_eq!(parse("<leader>f", &leader).unwrap(), vec![Key::char(' '), Key::char('f')]);
        assert_eq!(parse("<S-Tab>", &leader).unwrap(), vec![Key::plain(Code::BackTab)]);
        assert_eq!(parse("<lt>", &leader).unwrap(), vec![Key::char('<')]);
        assert_eq!(parse("<", &leader).unwrap(), vec![Key::char('<')]);
        assert!(parse("<nope>", &leader).is_err());
        assert_eq!(parse("<<b", &leader).unwrap(), vec![Key::char('<'), Key::char('<'), Key::char('b')]);
        assert_eq!(parse("<<b<tab>", &leader).unwrap()[3], Key::plain(Code::Tab));
    }

    #[test]
    fn notation_round_trips() {
        let leader = [Key::char(' ')];
        for text in ["<C-s>", "<space>f", "<A-j>", "<cr>", "<f5>", "x", "<S-up>"] {
            let keys = parse(text, &leader).unwrap();
            assert_eq!(parse(&notation(&keys), &leader).unwrap(), keys, "{text}");
        }
    }
}
