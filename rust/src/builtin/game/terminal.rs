//! The real terminal: raw mode, alternate screen, mouse capture and a frame
//! buffer that is redrawn line by line without flicker.

use std::io::{self, Write};
use std::time::{Duration, Instant};

use crossterm::event::{self, Event, KeyCode, KeyEventKind, KeyModifiers, MouseButton, MouseEventKind};
use crossterm::style::{self as term, Attribute};
use crossterm::{cursor, execute, queue, terminal};

use super::{Button, Color, Input, Key, Screen, Style};

#[derive(Clone, Copy, PartialEq)]
struct Cell {
    text: char,
    style: Style,
}

const BLANK: Cell = Cell { text: ' ', style: Style::PLAIN };

pub struct Terminal {
    frame: Vec<Vec<Cell>>,
    size: (i32, i32),
    started: Instant,
    out: io::Stdout,
}

impl Terminal {
    pub fn open() -> io::Result<Terminal> {
        terminal::enable_raw_mode()?;
        let mut out = io::stdout();
        if let Err(error) = execute!(out, terminal::EnterAlternateScreen, cursor::Hide, event::EnableMouseCapture) {
            let _ = terminal::disable_raw_mode();
            return Err(error);
        }
        let mut screen = Terminal { frame: Vec::new(), size: (0, 0), started: Instant::now(), out };
        screen.resize();
        Ok(screen)
    }

    fn resize(&mut self) {
        // Some pseudo-terminals report 0x0; assume the classic 80x24 then.
        let (columns, rows) = terminal::size().ok().filter(|(columns, rows)| *columns > 0 && *rows > 0).unwrap_or((80, 24));
        self.size = (rows as i32, columns as i32);
        self.clear();
        let _ = execute!(self.out, terminal::Clear(terminal::ClearType::All));
    }
}

impl Drop for Terminal {
    fn drop(&mut self) {
        let _ = execute!(
            self.out,
            term::SetAttribute(Attribute::Reset),
            event::DisableMouseCapture,
            cursor::Show,
            terminal::LeaveAlternateScreen
        );
        let _ = terminal::disable_raw_mode();
    }
}

fn color(color: Color) -> term::Color {
    match color {
        Color::Default => term::Color::Reset,
        Color::Red => term::Color::Red,
        Color::Green => term::Color::Green,
        Color::Yellow => term::Color::Yellow,
        Color::Blue => term::Color::Blue,
        Color::Magenta => term::Color::Magenta,
        Color::Cyan => term::Color::Cyan,
        Color::White => term::Color::White,
        Color::Gray => term::Color::Grey,
        Color::DarkRed => term::Color::DarkRed,
        Color::DarkYellow => term::Color::DarkYellow,
        Color::DarkBlue => term::Color::DarkBlue,
        Color::DarkCyan => term::Color::DarkCyan,
    }
}

impl Screen for Terminal {
    fn size(&self) -> (i32, i32) {
        self.size
    }

    fn clear(&mut self) {
        let (height, width) = self.size;
        self.frame = vec![vec![BLANK; width.max(0) as usize]; height.max(0) as usize];
    }

    fn put(&mut self, y: i32, x: i32, text: &str, style: Style) {
        let Some(row) = usize::try_from(y).ok().and_then(|y| self.frame.get_mut(y)) else { return };
        for (offset, character) in text.chars().enumerate() {
            let column = x + offset as i32;
            if let Some(cell) = usize::try_from(column).ok().and_then(|column| row.get_mut(column)) {
                *cell = Cell { text: character, style };
            }
        }
    }

    fn present(&mut self) -> io::Result<()> {
        queue!(self.out, terminal::BeginSynchronizedUpdate)?;
        for (y, row) in self.frame.iter().enumerate() {
            queue!(self.out, cursor::MoveTo(0, y as u16))?;
            let mut current: Option<Style> = None;
            let mut run = String::new();
            for cell in row {
                if current != Some(cell.style) {
                    if !run.is_empty() {
                        queue!(self.out, term::Print(std::mem::take(&mut run)))?;
                    }
                    let style = cell.style;
                    queue!(
                        self.out,
                        term::SetAttribute(Attribute::Reset),
                        term::SetForegroundColor(color(style.fg)),
                        term::SetBackgroundColor(color(style.bg))
                    )?;
                    for (enabled, attribute) in
                        [(style.bold, Attribute::Bold), (style.reverse, Attribute::Reverse), (style.dim, Attribute::Dim)]
                    {
                        if enabled {
                            queue!(self.out, term::SetAttribute(attribute))?;
                        }
                    }
                    current = Some(style);
                }
                run.push(cell.text);
            }
            queue!(self.out, term::Print(run), term::SetAttribute(Attribute::Reset))?;
        }
        queue!(self.out, terminal::EndSynchronizedUpdate)?;
        self.out.flush()
    }

    fn input(&mut self, timeout: Option<Duration>) -> io::Result<Option<Input>> {
        let deadline = timeout.map(|timeout| Instant::now() + timeout);
        loop {
            let wait = deadline.map(|deadline| deadline.saturating_duration_since(Instant::now())).unwrap_or(Duration::from_secs(3600));
            if !event::poll(wait)? {
                if deadline.is_some() {
                    return Ok(None);
                }
                continue;
            }
            let mapped = match event::read()? {
                Event::Resize(..) => {
                    self.resize();
                    return Ok(None);
                }
                Event::Key(key) if key.kind != KeyEventKind::Release => {
                    if key.modifiers.contains(KeyModifiers::CONTROL) && key.code == KeyCode::Char('c') {
                        return Err(io::Error::new(io::ErrorKind::Interrupted, "interrupted"));
                    }
                    Input::Key(match key.code {
                        KeyCode::Up => Key::Up,
                        KeyCode::Down => Key::Down,
                        KeyCode::Left => Key::Left,
                        KeyCode::Right => Key::Right,
                        KeyCode::Enter => Key::Enter,
                        KeyCode::Esc => Key::Esc,
                        KeyCode::Char(character) => Key::Char(character),
                        _ => continue,
                    })
                }
                Event::Mouse(mouse) => {
                    let (y, x) = (mouse.row as i32, mouse.column as i32);
                    match mouse.kind {
                        MouseEventKind::Down(button) => Input::Click {
                            y,
                            x,
                            button: match button {
                                MouseButton::Left => Button::Left,
                                MouseButton::Right => Button::Right,
                                MouseButton::Middle => Button::Middle,
                            },
                        },
                        MouseEventKind::Moved | MouseEventKind::Drag(_) => Input::Hover { y, x },
                        _ => continue,
                    }
                }
                _ => continue,
            };
            return Ok(Some(mapped));
        }
    }

    fn now(&self) -> f64 {
        self.started.elapsed().as_secs_f64()
    }
}
