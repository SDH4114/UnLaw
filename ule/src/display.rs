//! Display columns: tabs, wide (CJK, emoji) and zero-width chars, soft wrapping.

use unicode_width::UnicodeWidthChar;

/// Columns `c` takes at display column `at` (tabs reach the next tab stop).
pub fn width_at(c: char, at: usize, tab_width: usize) -> usize {
    if c == '\t' {
        tab_width - at % tab_width
    } else if (c as u32) < 0x20 || c == '\u{7f}' {
        // Control chars are drawn as ^X.
        2
    } else {
        c.width().unwrap_or(0)
    }
}

pub fn str_width(text: &str) -> usize {
    let mut width = 0;
    for c in text.chars() {
        width += width_at(c, width, 8);
    }
    width
}

/// Display column of char `col` in `line`.
pub fn col_to_display(line: &str, col: usize, tab_width: usize) -> usize {
    let mut width = 0;
    for c in line.chars().take(col) {
        width += width_at(c, width, tab_width);
    }
    width
}

/// The char at display column `target` (the last one starting at or before it).
pub fn display_to_col(line: &str, target: usize, tab_width: usize) -> usize {
    let mut width = 0;
    for (index, c) in line.chars().enumerate() {
        let next = width + width_at(c, width, tab_width);
        if next > target {
            return index;
        }
        width = next;
    }
    line.chars().count()
}

/// Where each wrapped row of `line` starts (char index), breaking at spaces when possible.
pub fn wrap_rows(line: &str, width: usize, tab_width: usize) -> Vec<usize> {
    let width = width.max(4);
    let mut rows = vec![0];
    let mut used = 0;
    let mut last_space: Option<usize> = None;
    let chars: Vec<char> = line.chars().collect();
    let mut index = 0;
    while index < chars.len() {
        let c = chars[index];
        let w = width_at(c, used, tab_width);
        if used + w > width && used > 0 {
            let start = *rows.last().unwrap_or(&0);
            // Break after the last space of this row; mid-word only when the row has none.
            let cut = match last_space {
                Some(space) if space + 1 > start && space + 1 < index => space + 1,
                _ => index,
            };
            rows.push(cut);
            used = chars[cut..index].iter().fold(0, |at, c| at + width_at(*c, at, tab_width));
            last_space = None;
            continue;
        }
        if c == ' ' {
            last_space = Some(index);
        }
        used += w;
        index += 1;
    }
    rows
}

/// Rows a line takes on screen.
pub fn line_rows(line: &str, width: usize, tab_width: usize, wrap: bool) -> usize {
    if !wrap {
        return 1;
    }
    wrap_rows(line, width, tab_width).len()
}

/// Truncates to `width` columns, adding `…` when cut.
pub fn fit(text: &str, width: usize) -> String {
    if str_width(text) <= width {
        return text.to_string();
    }
    let mut out = String::new();
    let mut used = 0;
    for c in text.chars() {
        let w = width_at(c, used, 8);
        if used + w + 1 > width {
            break;
        }
        out.push(c);
        used += w;
    }
    out.push('…');
    out
}

/// Keeps the end of a path-like text: `…/src/editor.rs`.
pub fn fit_start(text: &str, width: usize) -> String {
    if str_width(text) <= width {
        return text.to_string();
    }
    let chars: Vec<char> = text.chars().collect();
    let mut used = 1;
    let mut start = chars.len();
    while start > 0 {
        let w = width_at(chars[start - 1], 0, 8);
        if used + w > width {
            break;
        }
        used += w;
        start -= 1;
    }
    format!("…{}", chars[start..].iter().collect::<String>())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tabs_and_wide_chars() {
        assert_eq!(col_to_display("\tab", 1, 4), 4);
        assert_eq!(col_to_display("a\tb", 2, 4), 4);
        assert_eq!(col_to_display("日本", 1, 4), 2);
        assert_eq!(display_to_col("日本語", 3, 4), 1);
        assert_eq!(display_to_col("\tx", 2, 4), 0);
        assert_eq!(display_to_col("\tx", 4, 4), 1);
    }

    #[test]
    fn wraps_at_spaces() {
        let rows = wrap_rows("hello world this wraps", 10, 4);
        assert_eq!(rows, vec![0, 6, 12]);
        assert_eq!(wrap_rows("abcdefghijkl", 5, 4), vec![0, 5, 10]);
        assert_eq!(wrap_rows("", 5, 4), vec![0]);
    }

    #[test]
    fn fitting() {
        assert_eq!(fit("hello world", 6), "hello…");
        assert_eq!(fit_start("src/editor.rs", 8), "…itor.rs");
    }
}
