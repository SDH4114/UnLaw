//! Hotkey text (`ctrl+alt+a`, `cmd+shift+space`) as written in app.toml. The
//! GUI maps a parsed hotkey to the OS's key codes; this part has no OS code.

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct Hotkey {
    pub ctrl: bool,
    pub alt: bool,
    pub shift: bool,
    pub cmd: bool,
    /// Normalized key name: `a`-`z`, `0`-`9`, `f1`-`f20` or one of `NAMED`.
    pub key: String,
}

pub const NAMED: &[&str] = &[
    "space",
    "enter",
    "tab",
    "escape",
    "backspace",
    "delete",
    "up",
    "down",
    "left",
    "right",
    "home",
    "end",
    "pageup",
    "pagedown",
    "comma",
    "period",
    "slash",
    "semicolon",
    "quote",
    "minus",
    "equal",
    "backquote",
    "bracketleft",
    "bracketright",
    "backslash",
];

fn key_name(word: &str) -> Option<String> {
    let alias = match word {
        "return" => "enter",
        "esc" => "escape",
        "," => "comma",
        "." => "period",
        "/" => "slash",
        ";" => "semicolon",
        "'" => "quote",
        "-" => "minus",
        "=" => "equal",
        "`" => "backquote",
        "[" => "bracketleft",
        "]" => "bracketright",
        "\\" => "backslash",
        other => other,
    };
    let single = alias.len() == 1 && alias.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit());
    let function = alias
        .strip_prefix('f')
        .and_then(|number| number.parse::<u8>().ok())
        .is_some_and(|number| (1..=20).contains(&number) && !alias[1..].starts_with('0'));
    (single || function || NAMED.contains(&alias)).then(|| alias.to_string())
}

pub fn parse(text: &str) -> Result<Hotkey, String> {
    let lower = text.trim().to_ascii_lowercase();
    // `ctrl++` would mean the plus key; nobody needs it and it reads badly.
    let words: Vec<&str> = lower.split('+').map(str::trim).collect();
    let (key, modifiers) =
        words.split_last().filter(|(key, _)| !key.is_empty()).ok_or_else(|| format!("{text:?} has no key"))?;
    let mut hotkey = Hotkey { ctrl: false, alt: false, shift: false, cmd: false, key: String::new() };
    for word in modifiers {
        let slot = match *word {
            "ctrl" | "control" => &mut hotkey.ctrl,
            "alt" | "option" | "opt" => &mut hotkey.alt,
            "shift" => &mut hotkey.shift,
            "cmd" | "command" | "super" | "meta" => &mut hotkey.cmd,
            other => return Err(format!("{other:?} in {text:?} is not ctrl, alt, shift or cmd")),
        };
        if *slot {
            return Err(format!("{word} twice in {text:?}"));
        }
        *slot = true;
    }
    hotkey.key = key_name(key).ok_or_else(|| format!("{key:?} in {text:?} is not a key name"))?;
    let modified = hotkey.ctrl || hotkey.alt || hotkey.cmd;
    if !modified && !hotkey.key.starts_with('f') || hotkey.key == "f" && !modified {
        return Err(format!("{text:?} needs a modifier (ctrl, alt or cmd), or use an F key"));
    }
    Ok(hotkey)
}

impl Hotkey {
    /// The app.toml spelling (`ctrl+alt+a`), which `parse` reads back.
    pub fn text(&self) -> String {
        let mut words: Vec<&str> = Vec::new();
        for (on, word) in [(self.ctrl, "ctrl"), (self.alt, "alt"), (self.shift, "shift"), (self.cmd, "cmd")] {
            if on {
                words.push(word);
            }
        }
        words.push(&self.key);
        words.join("+")
    }
}

impl std::fmt::Display for Hotkey {
    /// `⌃⌥A`, the way macOS menus show it.
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let mut out = String::new();
        for (on, sign) in [(self.ctrl, '⌃'), (self.alt, '⌥'), (self.shift, '⇧'), (self.cmd, '⌘')] {
            if on {
                out.push(sign);
            }
        }
        let key = match self.key.as_str() {
            "space" => "Space".to_string(),
            "enter" => "↩".to_string(),
            "tab" => "⇥".to_string(),
            "escape" => "⎋".to_string(),
            "up" => "↑".to_string(),
            "down" => "↓".to_string(),
            "left" => "←".to_string(),
            "right" => "→".to_string(),
            "backspace" => "⌫".to_string(),
            "delete" => "⌦".to_string(),
            "home" => "↖".to_string(),
            "end" => "↘".to_string(),
            "pageup" => "⇞".to_string(),
            "pagedown" => "⇟".to_string(),
            "comma" => ",".to_string(),
            "period" => ".".to_string(),
            "slash" => "/".to_string(),
            "semicolon" => ";".to_string(),
            "quote" => "'".to_string(),
            "minus" => "-".to_string(),
            "equal" => "=".to_string(),
            "backquote" => "`".to_string(),
            "bracketleft" => "[".to_string(),
            "bracketright" => "]".to_string(),
            "backslash" => "\\".to_string(),
            other => other.to_ascii_uppercase(),
        };
        write!(f, "{out}{key}")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn common_hotkeys() {
        let key = parse("Ctrl+Space").unwrap();
        assert!(key.ctrl && !key.alt && key.key == "space");
        assert_eq!(key.to_string(), "⌃Space");
        assert_eq!(parse("cmd + shift + k").unwrap().to_string(), "⇧⌘K");
        assert_eq!(parse("option+return").unwrap().key, "enter");
        assert_eq!(parse("ctrl+alt+/").unwrap().key, "slash");
        assert_eq!(parse("cmd+,").unwrap().to_string(), "⌘,");
        assert_eq!(parse("ctrl+backspace").unwrap().to_string(), "⌃⌫");
        assert_eq!(parse("cmd+bracketleft").unwrap().to_string(), "⌘[");
        assert_eq!(parse("f5").unwrap().to_string(), "F5");
        // Every named key shows as something short, never its spelled-out name.
        for name in NAMED {
            let shown = parse(&format!("ctrl+{name}")).unwrap().to_string();
            assert!(shown.chars().count() <= 6, "{name} shows as {shown}");
        }
        assert_eq!(parse("f5").unwrap().key, "f5");
        assert_eq!(parse("shift+f12").unwrap().key, "f12");
    }

    #[test]
    fn bad_hotkeys() {
        for (text, message) in [
            ("q", "needs a modifier"),
            ("shift+q", "needs a modifier"),
            ("f", "needs a modifier"),
            ("ctrl+", "has no key"),
            ("", "has no key"),
            ("hyper+a", "is not ctrl"),
            ("ctrl+ctrl+a", "twice"),
            ("ctrl+f21", "not a key name"),
            ("ctrl+f05", "not a key name"),
            ("ctrl+ab", "not a key name"),
        ] {
            let error = parse(text).unwrap_err();
            assert!(error.contains(message), "{text:?}: {error}");
        }
    }
}
