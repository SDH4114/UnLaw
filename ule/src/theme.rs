//! Colors, styles and themes (built-in `runtime/themes.toml` plus `[themes.*]` in ule.toml).

use std::collections::HashMap;

use toml_edit::{DocumentMut, Item, Table, Value};

pub const BUILTIN: &str = include_str!("../runtime/themes.toml");

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Color {
    Reset,
    Ansi(u8),
    Rgb(u8, u8, u8),
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Style {
    pub fg: Option<Color>,
    pub bg: Option<Color>,
    pub bold: bool,
    pub italic: bool,
    pub underline: bool,
    pub undercurl: bool,
    pub reverse: bool,
    pub dim: bool,
    pub crossed: bool,
    pub underline_color: Option<Color>,
}

impl Style {
    pub fn fg(color: Color) -> Self {
        Style { fg: Some(color), ..Style::default() }
    }

    /// `other` drawn over `self`: its colors win where set, modifiers add up.
    pub fn patch(self, other: Style) -> Style {
        Style {
            fg: other.fg.or(self.fg),
            bg: other.bg.or(self.bg),
            bold: self.bold || other.bold,
            italic: self.italic || other.italic,
            underline: self.underline || other.underline,
            undercurl: self.undercurl || other.undercurl,
            reverse: self.reverse || other.reverse,
            dim: self.dim || other.dim,
            crossed: self.crossed || other.crossed,
            underline_color: other.underline_color.or(self.underline_color),
        }
    }
}

const ANSI: [&str; 16] = [
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
    "bright_black",
    "bright_red",
    "bright_green",
    "bright_yellow",
    "bright_blue",
    "bright_magenta",
    "bright_cyan",
    "bright_white",
];

pub fn parse_color(text: &str, palette: &HashMap<String, String>) -> Option<Color> {
    if let Some(value) = palette.get(text) {
        if value != text {
            return parse_color(value, &HashMap::new());
        }
    }
    let lower = text.trim().to_ascii_lowercase();
    if lower == "default" || lower == "reset" || lower == "none" {
        return Some(Color::Reset);
    }
    if lower == "gray" || lower == "grey" {
        return Some(Color::Ansi(8));
    }
    if let Some(index) = ANSI.iter().position(|name| *name == lower) {
        return Some(Color::Ansi(index as u8));
    }
    if let Some(hex) = lower.strip_prefix('#') {
        if hex.len() == 6 {
            let channel = |at: usize| u8::from_str_radix(&hex[at..at + 2], 16).ok();
            return Some(Color::Rgb(channel(0)?, channel(2)?, channel(4)?));
        }
        return None;
    }
    lower.parse::<u8>().ok().map(Color::Ansi)
}

/// The nearest xterm-256 color, for terminals without truecolor.
pub fn to_256(color: Color) -> Color {
    let Color::Rgb(r, g, b) = color else {
        return color;
    };
    let level = |v: u8| if v < 48 { 0 } else if v < 115 { 1 } else { (v as u16 - 35) / 40 } as u8;
    let (lr, lg, lb) = (level(r), level(g), level(b));
    let cube = 16 + 36 * lr + 6 * lg + lb;
    let gray_level = ((r as u16 + g as u16 + b as u16) / 3) as u8;
    let gray = if gray_level > 238 { 255 } else { 232 + gray_level.saturating_sub(8) / 10 };
    let value = |l: u8| if l == 0 { 0 } else { 55 + 40 * l as i32 };
    let cube_distance = (value(lr) - r as i32).pow(2) + (value(lg) - g as i32).pow(2) + (value(lb) - b as i32).pow(2);
    let gray_value = 8 + 10 * (gray as i32 - 232);
    let gray_distance =
        (gray_value - r as i32).pow(2) + (gray_value - g as i32).pow(2) + (gray_value - b as i32).pow(2);
    Color::Ansi(if gray_distance < cube_distance { gray } else { cube })
}

#[derive(Clone, Debug)]
pub struct Theme {
    pub name: String,
    styles: HashMap<String, Style>,
}

impl Default for Theme {
    fn default() -> Self {
        Themes::new(None).load("unlaw").expect("built-in theme")
    }
}

impl Theme {
    /// `syntax.keyword.control` falls back to `syntax.keyword`, then to nothing.
    pub fn get(&self, key: &str) -> Style {
        let mut key = key;
        loop {
            if let Some(style) = self.styles.get(key) {
                return *style;
            }
            match key.rfind('.') {
                Some(dot) => key = &key[..dot],
                None => return Style::default(),
            }
        }
    }

    pub fn has(&self, key: &str) -> bool {
        self.styles.contains_key(key)
    }

    /// The base text style every other style is drawn over.
    pub fn text(&self) -> Style {
        self.get("ui.text")
    }
}

/// A theme's palette and its style entries.
type Flattened = (HashMap<String, String>, Vec<(String, Item)>);

/// Raw theme tables: built-ins plus the user's `[themes.*]`.
pub struct Themes {
    tables: Vec<(String, Table)>,
}

impl Themes {
    pub fn new(user: Option<&Table>) -> Self {
        let mut tables = Vec::new();
        if let Ok(document) = BUILTIN.parse::<DocumentMut>() {
            for (name, item) in document.iter() {
                if let Some(table) = item.as_table() {
                    tables.push((name.to_string(), table.clone()));
                }
            }
        }
        if let Some(user) = user {
            for (name, item) in user.iter() {
                if let Some(table) = item.as_table() {
                    tables.retain(|(existing, _)| existing != name);
                    tables.push((name.to_string(), table.clone()));
                }
            }
        }
        Themes { tables }
    }

    pub fn names(&self) -> Vec<String> {
        self.tables.iter().map(|(name, _)| name.clone()).collect()
    }

    fn table(&self, name: &str) -> Option<&Table> {
        self.tables.iter().find(|(existing, _)| existing == name).map(|(_, table)| table)
    }

    /// Entries of a theme after following `inherits` (parents first).
    fn flatten(&self, name: &str, depth: usize) -> Option<Flattened> {
        if depth > 8 {
            return None;
        }
        let table = self.table(name)?;
        let (mut palette, mut entries) = match table.get("inherits").and_then(Item::as_str) {
            Some(parent) => self.flatten(parent, depth + 1)?,
            None => (HashMap::new(), Vec::new()),
        };
        for (key, item) in table.iter() {
            match key {
                "inherits" => {}
                "palette" => {
                    if let Some(colors) = item.as_table_like() {
                        for (name, value) in colors.iter() {
                            if let Some(text) = value.as_str() {
                                palette.insert(name.to_string(), text.to_string());
                            }
                        }
                    }
                }
                _ => entries.push((key.to_string(), item.clone())),
            }
        }
        Some((palette, entries))
    }

    pub fn load(&self, name: &str) -> Result<Theme, String> {
        let (palette, entries) = self.flatten(name, 0).ok_or_else(|| format!("no theme named {name:?}"))?;
        let mut styles = HashMap::new();
        for (key, item) in entries {
            styles.insert(
                key.clone(),
                style_of(&item, &palette).map_err(|error| format!("theme {name}, {key}: {error}"))?,
            );
        }
        Ok(Theme { name: name.to_string(), styles })
    }
}

fn color_of(value: &Value, palette: &HashMap<String, String>) -> Result<Color, String> {
    match value {
        Value::String(text) => {
            parse_color(text.value(), palette).ok_or_else(|| format!("bad color {:?}", text.value()))
        }
        Value::Integer(number) => {
            u8::try_from(*number.value()).map(Color::Ansi).map_err(|_| format!("bad color {}", number.value()))
        }
        _ => Err("a color is a string or 0-255".into()),
    }
}

fn style_of(item: &Item, palette: &HashMap<String, String>) -> Result<Style, String> {
    if let Some(value) = item.as_value() {
        if !value.is_inline_table() {
            return Ok(Style::fg(color_of(value, palette)?));
        }
    }
    let table = item.as_table_like().ok_or("expected a color or a table")?;
    let mut style = Style::default();
    for (key, value) in table.iter() {
        let value = value.as_value().ok_or("expected a value")?;
        match key {
            "fg" => style.fg = Some(color_of(value, palette)?),
            "bg" => style.bg = Some(color_of(value, palette)?),
            "underline" => style.underline_color = Some(color_of(value, palette)?),
            "modifiers" => {
                let list = value.as_array().ok_or("modifiers is a list")?;
                for modifier in list.iter() {
                    match modifier.as_str() {
                        Some("bold") => style.bold = true,
                        Some("italic") => style.italic = true,
                        Some("underline" | "underlined") => style.underline = true,
                        Some("undercurl") => style.undercurl = true,
                        Some("reverse" | "reversed") => style.reverse = true,
                        Some("dim") => style.dim = true,
                        Some("crossed" | "strikethrough") => style.crossed = true,
                        other => return Err(format!("unknown modifier {other:?}")),
                    }
                }
            }
            other => return Err(format!("unknown style key {other:?}")),
        }
    }
    Ok(style)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_builtin_theme_loads() {
        let themes = Themes::new(None);
        for name in themes.names() {
            let theme = themes.load(&name).unwrap_or_else(|error| panic!("{error}"));
            assert!(theme.has("syntax.keyword"), "{name}");
            assert!(theme.has("ui.mode.normal"), "{name}");
        }
    }

    #[test]
    fn children_use_their_own_palette() {
        let themes = Themes::new(None);
        let gruvbox = themes.load("gruvbox").unwrap();
        assert_eq!(gruvbox.get("ui.text").bg, Some(Color::Rgb(0x28, 0x28, 0x28)));
        assert_eq!(gruvbox.get("syntax.keyword.control").fg, Some(Color::Rgb(0xfb, 0x49, 0x34)));
    }

    #[test]
    fn rgb_maps_to_the_256_palette() {
        assert_eq!(to_256(Color::Rgb(0, 0, 0)), Color::Ansi(16));
        assert_eq!(to_256(Color::Rgb(255, 255, 255)), Color::Ansi(231));
        assert_eq!(to_256(Color::Rgb(128, 128, 128)), Color::Ansi(244));
    }
}
