//! A grid of styled cells, drawn to the terminal by diffing against the previous frame.

use std::io::{self, Write};

use crossterm::cursor::{Hide, MoveTo, SetCursorStyle, Show};
use crossterm::style::{
    Attribute, Color as TermColor, Print, SetAttribute, SetBackgroundColor, SetForegroundColor, SetUnderlineColor,
};
use crossterm::{queue, terminal};

use crate::display::width_at;
use crate::theme::{to_256, Color, Style};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Cell {
    pub symbol: char,
    /// The right half of a wide char: nothing is printed for it.
    pub continuation: bool,
    pub style: Style,
}

impl Default for Cell {
    fn default() -> Self {
        Cell { symbol: ' ', continuation: false, style: Style::default() }
    }
}

#[derive(Clone, Debug)]
pub struct Surface {
    pub width: u16,
    pub height: u16,
    pub cells: Vec<Cell>,
    pub cursor: Option<(u16, u16)>,
    pub cursor_bar: bool,
}

impl Surface {
    pub fn new(width: u16, height: u16, base: Style) -> Self {
        let cell = Cell { style: base, ..Cell::default() };
        Surface { width, height, cells: vec![cell; width as usize * height as usize], cursor: None, cursor_bar: false }
    }

    fn index(&self, x: u16, y: u16) -> Option<usize> {
        (x < self.width && y < self.height).then(|| y as usize * self.width as usize + x as usize)
    }

    pub fn get(&self, x: u16, y: u16) -> Option<&Cell> {
        self.index(x, y).map(|index| &self.cells[index])
    }

    /// Draws `style` over the cell's existing style (colors replaced where set).
    pub fn style(&mut self, x: u16, y: u16, style: Style) {
        if let Some(index) = self.index(x, y) {
            let cell = &mut self.cells[index];
            cell.style = cell.style.patch(style);
        }
    }

    pub fn fill(&mut self, x: u16, y: u16, w: u16, h: u16, style: Style) {
        for row in y..(y + h).min(self.height) {
            for column in x..(x + w).min(self.width) {
                if let Some(index) = self.index(column, row) {
                    self.cells[index] = Cell { symbol: ' ', continuation: false, style };
                }
            }
        }
    }

    pub fn restyle(&mut self, x: u16, y: u16, w: u16, style: Style) {
        for column in x..(x + w).min(self.width) {
            self.style(column, y, style);
        }
    }

    /// Puts a char; returns the columns used (0 when it does not fit before `limit`).
    pub fn put_char(&mut self, x: u16, y: u16, c: char, style: Style, limit: u16) -> u16 {
        let width = width_at(c, 0, 8) as u16;
        if c == '\t' || (c as u32) < 0x20 || c == '\u{7f}' {
            // Control chars show as ^X.
            let shown = if c == '\u{7f}' { '?' } else { char::from_u32(c as u32 + 64).unwrap_or('?') };
            if x + 2 > limit {
                return 0;
            }
            let dim = Style { dim: true, ..style };
            self.set(x, y, '^', dim);
            self.set(x + 1, y, shown, dim);
            return 2;
        }
        if width == 0 {
            return 0;
        }
        if x + width > limit {
            return 0;
        }
        self.set(x, y, c, style);
        if width == 2 {
            if let Some(index) = self.index(x + 1, y) {
                self.cells[index] = Cell { symbol: ' ', continuation: true, style };
            }
        }
        width
    }

    fn set(&mut self, x: u16, y: u16, c: char, style: Style) {
        if let Some(index) = self.index(x, y) {
            // Overwriting half of a wide char clears its other half.
            if self.cells[index].continuation && x > 0 {
                if let Some(left) = self.index(x - 1, y) {
                    self.cells[left].symbol = ' ';
                }
            }
            if let Some(right) = self.index(x + 1, y) {
                if self.cells[right].continuation {
                    self.cells[right] = Cell { symbol: ' ', continuation: false, style: self.cells[right].style };
                }
            }
            self.cells[index] = Cell { symbol: c, continuation: false, style };
        }
    }

    /// Writes text from `x`; stops at `limit` columns. Returns the end column.
    pub fn text(&mut self, x: u16, y: u16, text: &str, style: Style, limit: u16) -> u16 {
        let limit = limit.min(self.width);
        let mut column = x;
        for c in text.chars() {
            if column >= limit {
                break;
            }
            let used = self.put_char(column, y, c, style, limit);
            if used == 0 && width_at(c, 0, 8) > 0 {
                break;
            }
            column += used;
        }
        column
    }
}

pub struct Terminal {
    previous: Option<Surface>,
    pub true_color: bool,
    /// Curly and colored underlines (`4:3m`, `58;...m`) only where the terminal knows them.
    pub fancy_underline: bool,
}

fn color(color: Color, true_color: bool) -> TermColor {
    match if true_color { color } else { to_256(color) } {
        Color::Reset => TermColor::Reset,
        Color::Ansi(value) => TermColor::AnsiValue(value),
        Color::Rgb(r, g, b) => TermColor::Rgb { r, g, b },
    }
}

impl Terminal {
    pub fn new(true_color: bool) -> Self {
        Terminal { previous: None, true_color, fancy_underline: true }
    }

    pub fn invalidate(&mut self) {
        self.previous = None;
    }

    fn apply_style(&self, out: &mut impl Write, style: Style) -> io::Result<()> {
        queue!(out, SetAttribute(Attribute::Reset))?;
        queue!(out, SetForegroundColor(style.fg.map_or(TermColor::Reset, |c| color(c, self.true_color))))?;
        queue!(out, SetBackgroundColor(style.bg.map_or(TermColor::Reset, |c| color(c, self.true_color))))?;
        if style.bold {
            queue!(out, SetAttribute(Attribute::Bold))?;
        }
        if style.dim {
            queue!(out, SetAttribute(Attribute::Dim))?;
        }
        if style.italic {
            queue!(out, SetAttribute(Attribute::Italic))?;
        }
        if style.undercurl && self.fancy_underline {
            queue!(out, SetAttribute(Attribute::Undercurled))?;
        } else if style.underline || style.undercurl {
            queue!(out, SetAttribute(Attribute::Underlined))?;
        }
        if let Some(underline) = style.underline_color.filter(|_| self.fancy_underline) {
            queue!(out, SetUnderlineColor(color(underline, self.true_color)))?;
        }
        if style.reverse {
            queue!(out, SetAttribute(Attribute::Reverse))?;
        }
        if style.crossed {
            queue!(out, SetAttribute(Attribute::CrossedOut))?;
        }
        Ok(())
    }

    /// Draws the cells that changed since the last frame, then places the cursor.
    pub fn draw(&mut self, surface: &Surface, out: &mut impl Write) -> io::Result<()> {
        queue!(out, Hide)?;
        let full = self
            .previous
            .as_ref()
            .is_none_or(|previous| previous.width != surface.width || previous.height != surface.height);
        if full {
            queue!(out, SetAttribute(Attribute::Reset), terminal::Clear(terminal::ClearType::All))?;
        }
        let mut current_style: Option<Style> = None;
        let mut position: Option<(u16, u16)> = None;
        for y in 0..surface.height {
            for x in 0..surface.width {
                let index = y as usize * surface.width as usize + x as usize;
                let cell = &surface.cells[index];
                if cell.continuation {
                    continue;
                }
                if !full {
                    if let Some(previous) = &self.previous {
                        let old = &previous.cells[index];
                        // A wide char's right half changing needs a redraw of the char too.
                        let right_changed = surface
                            .cells
                            .get(index + 1)
                            .zip(previous.cells.get(index + 1))
                            .is_some_and(|(new, old)| new.continuation != old.continuation);
                        if old == cell && !right_changed {
                            continue;
                        }
                    }
                }
                if position != Some((x, y)) {
                    queue!(out, MoveTo(x, y))?;
                }
                if current_style != Some(cell.style) {
                    self.apply_style(out, cell.style)?;
                    current_style = Some(cell.style);
                }
                queue!(out, Print(cell.symbol))?;
                let width = if surface.cells.get(index + 1).is_some_and(|next| next.continuation) { 2 } else { 1 };
                position = Some((x + width, y));
            }
        }
        queue!(out, SetAttribute(Attribute::Reset))?;
        if let Some((x, y)) = surface.cursor {
            let shape = if surface.cursor_bar { SetCursorStyle::SteadyBar } else { SetCursorStyle::SteadyBlock };
            queue!(out, MoveTo(x, y), shape, Show)?;
        }
        out.flush()?;
        self.previous = Some(surface.clone());
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wide_chars_take_two_cells() {
        let mut surface = Surface::new(10, 1, Style::default());
        let end = surface.text(0, 0, "a日b", Style::default(), 10);
        assert_eq!(end, 4);
        assert!(surface.get(2, 0).unwrap().continuation);
        assert_eq!(surface.get(3, 0).unwrap().symbol, 'b');
        // A wide char that does not fit is not drawn halfway.
        let end = surface.text(8, 0, "x日", Style::default(), 10);
        assert_eq!(end, 9);
    }

    #[test]
    fn diff_only_redraws_changes() {
        let mut terminal = Terminal::new(true);
        let mut surface = Surface::new(5, 1, Style::default());
        surface.text(0, 0, "hello", Style::default(), 5);
        let mut first = Vec::new();
        terminal.draw(&surface, &mut first).unwrap();
        surface.text(4, 0, "!", Style::default(), 5);
        let mut second = Vec::new();
        terminal.draw(&surface, &mut second).unwrap();
        let text = String::from_utf8_lossy(&second);
        assert!(text.contains('!'));
        assert!(!text.contains("hell"));
    }
}
