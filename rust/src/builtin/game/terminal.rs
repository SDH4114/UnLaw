//! The real terminal: raw mode, alternate screen, mouse capture and a
//! double-buffered diff renderer. Games draw into a back buffer; `present`
//! compares it with what the terminal already shows and writes only the cells
//! that changed, in one write wrapped in a synchronized update.

use std::collections::VecDeque;
use std::io::{self, Write};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use crossterm::event::{
    self, Event, KeyCode, KeyEventKind, KeyModifiers, KeyboardEnhancementFlags, MouseButton,
    MouseEventKind,
};
use crossterm::{cursor, execute, terminal};

use super::{Button, Color, Input, Key, Screen, Style};

#[derive(Clone, Copy, PartialEq)]
struct Cell {
    text: char,
    style: Style,
}

const BLANK: Cell = Cell {
    text: ' ',
    style: Style::PLAIN,
};

/// A space only shows its background and reverse video; everything else about its style is
/// invisible, so it is stored canonically and never causes a pointless style change.
fn canonical(text: char, style: Style) -> Cell {
    if text == ' ' && style.bg == Color::Default && !style.reverse {
        BLANK
    } else {
        Cell { text, style }
    }
}

type Rgb = (u8, u8, u8);

/// (ANSI SGR code for the 16-color fallback, truecolor RGB). White and Gray stay on the
/// terminal's own palette in both modes so they keep their contrast on light and dark themes.
fn palette(color: Color) -> Option<(u8, Option<Rgb>)> {
    Some(match color {
        Color::Default => return None,
        Color::Red => (91, Some((247, 118, 142))),
        Color::Green => (92, Some((158, 206, 106))),
        Color::Yellow => (93, Some((240, 196, 108))),
        Color::Blue => (94, Some((122, 162, 247))),
        Color::Magenta => (95, Some((187, 154, 247))),
        Color::Cyan => (96, Some((125, 207, 255))),
        Color::White => (97, None),
        Color::Gray => (37, None),
        Color::DarkRed => (31, Some((205, 72, 96))),
        Color::DarkYellow => (33, Some((226, 140, 64))),
        Color::DarkBlue => (34, Some((64, 100, 214))),
        Color::DarkCyan => (36, Some((42, 161, 152))),
        // Chess: mid-tone squares so both white and black pieces stand out.
        Color::BoardLight => (37, Some((181, 140, 99))),
        Color::BoardDark => (90, Some((120, 86, 58))),
        Color::LastLight => (93, Some((170, 162, 58))),
        Color::LastDark => (33, Some((138, 130, 40))),
        Color::Selected => (32, Some((96, 140, 86))),
        Color::Target => (31, Some((176, 84, 72))),
        Color::Check => (91, Some((214, 58, 58))),
        Color::PieceWhite => (97, Some((255, 255, 255))),
        Color::PieceBlack => (30, Some((0, 0, 0))),
    })
}

fn param(out: &mut String, text: &str) {
    if !out.is_empty() {
        out.push(';');
    }
    out.push_str(text);
}

fn color_params(out: &mut String, color: Color, background: bool, truecolor: bool) {
    let Some((ansi, rgb)) = palette(color) else {
        param(out, if background { "49" } else { "39" });
        return;
    };
    match rgb.filter(|_| truecolor) {
        Some((r, g, b)) => param(
            out,
            &format!("{};2;{r};{g};{b}", if background { 48 } else { 38 }),
        ),
        None => param(
            out,
            &(ansi as u32 + if background { 10 } else { 0 }).to_string(),
        ),
    }
}

/// The shortest SGR sequence that turns `from` into `to` (nothing when equal).
fn style_change(out: &mut Vec<u8>, from: Style, to: Style, truecolor: bool) {
    if from == to {
        return;
    }
    let reset = (from.bold && !to.bold) || (from.dim && !to.dim) || (from.reverse && !to.reverse);
    let base = if reset { Style::PLAIN } else { from };
    let mut params = String::new();
    if reset {
        param(&mut params, "0");
    }
    if to.bold && !base.bold {
        param(&mut params, "1");
    }
    if to.dim && !base.dim {
        param(&mut params, "2");
    }
    if to.reverse && !base.reverse {
        param(&mut params, "7");
    }
    if to.fg != base.fg {
        color_params(&mut params, to.fg, false, truecolor);
    }
    if to.bg != base.bg {
        color_params(&mut params, to.bg, true, truecolor);
    }
    if !params.is_empty() {
        out.extend_from_slice(format!("\x1b[{params}m").as_bytes());
    }
}

/// The two buffers and the diff. Knows nothing about the real terminal, so it is testable
/// by rendering into a `Vec<u8>`.
pub struct Renderer {
    width: usize,
    height: usize,
    back: Vec<Cell>,
    front: Vec<Cell>,
    /// A copy of the back buffer taken by `save_frame` (the picture under an overlay).
    saved: Option<Vec<Cell>>,
    /// The terminal content is unknown (start, resize, failed write): clear it and draw everything.
    repaint: bool,
    truecolor: bool,
    scratch: Vec<u8>,
}

impl Renderer {
    pub fn new(height: usize, width: usize, truecolor: bool) -> Renderer {
        Renderer {
            width,
            height,
            back: vec![BLANK; width * height],
            front: vec![BLANK; width * height],
            saved: None,
            repaint: true,
            truecolor,
            scratch: Vec::new(),
        }
    }

    pub fn size(&self) -> (i32, i32) {
        (self.height as i32, self.width as i32)
    }

    pub fn clear(&mut self) {
        self.back.fill(BLANK);
    }

    pub fn put(&mut self, y: i32, x: i32, text: &str, style: Style) {
        let Some(row) = usize::try_from(y).ok().filter(|row| *row < self.height) else {
            return;
        };
        for (offset, character) in text.chars().enumerate() {
            if let Some(column) = usize::try_from(x + offset as i32)
                .ok()
                .filter(|column| *column < self.width)
            {
                self.back[row * self.width + column] = canonical(character, style);
            }
        }
    }

    /// Fade everything drawn so far (the backdrop of an overlay).
    pub fn dim_all(&mut self) {
        for cell in &mut self.back {
            if cell.text != ' ' {
                cell.style.dim = true;
            }
        }
    }

    /// Keep a copy of the picture so far, and bring it back later.
    pub fn save_frame(&mut self) {
        self.saved = Some(self.back.clone());
    }

    pub fn load_frame(&mut self) {
        if let Some(saved) = &self.saved {
            self.back.clone_from(saved);
        }
    }

    /// Resize keeping what was drawn (cropped or padded), and redraw the whole screen next time.
    pub fn resize(&mut self, height: usize, width: usize) {
        let remap = |cells: &[Cell], old_width: usize, old_height: usize| {
            let mut grid = vec![BLANK; width * height];
            for y in 0..height.min(old_height) {
                for x in 0..width.min(old_width) {
                    grid[y * width + x] = cells[y * old_width + x];
                }
            }
            grid
        };
        self.saved = self.saved.as_deref().map(|saved| remap(saved, self.width, self.height));
        self.back = remap(&self.back, self.width, self.height);
        self.front = vec![BLANK; width * height];
        self.width = width;
        self.height = height;
        self.repaint = true;
    }

    /// Write what changed since the last call as one synchronized update; returns the bytes
    /// written (0 for an unchanged picture).
    pub fn render<W: Write>(&mut self, out: &mut W) -> io::Result<usize> {
        if !self.repaint && self.back == self.front {
            return Ok(0);
        }
        let mut buffer = std::mem::take(&mut self.scratch);
        buffer.clear();
        buffer.extend_from_slice(b"\x1b[?2026h");
        if self.repaint {
            buffer.extend_from_slice(b"\x1b[0m\x1b[2J");
            self.front.fill(BLANK);
            self.repaint = false;
        }
        let mut style = Style::PLAIN;
        let mut cursor: Option<(usize, usize)> = None;
        let mut utf8 = [0u8; 4];
        for y in 0..self.height {
            for x in 0..self.width {
                let index = y * self.width + x;
                let cell = self.back[index];
                if cell == self.front[index] {
                    continue;
                }
                match cursor {
                    Some((row, column)) if row == y && column == x => {}
                    Some((row, column)) if row == y && column < x => match x - column {
                        1 => buffer.extend_from_slice(b"\x1b[C"),
                        gap => buffer.extend_from_slice(format!("\x1b[{gap}C").as_bytes()),
                    },
                    _ => buffer.extend_from_slice(format!("\x1b[{};{}H", y + 1, x + 1).as_bytes()),
                }
                style_change(&mut buffer, style, cell.style, self.truecolor);
                style = cell.style;
                buffer.extend_from_slice(cell.text.encode_utf8(&mut utf8).as_bytes());
                self.front[index] = cell;
                // After the last column the cursor waits to wrap; its position is not x + 1.
                cursor = (x + 1 < self.width).then_some((y, x + 1));
            }
        }
        if style != Style::PLAIN {
            buffer.extend_from_slice(b"\x1b[0m");
        }
        buffer.extend_from_slice(b"\x1b[?2026l");
        let result = out.write_all(&buffer).and_then(|()| out.flush());
        let written = buffer.len();
        self.scratch = buffer;
        if result.is_err() {
            // Unknown what reached the terminal: draw everything next time.
            self.repaint = true;
        }
        result.map(|()| written)
    }
}

/// Everything that undoes `Terminal::open`; plain bytes so a signal handler can write it.
const LEAVE: &[u8] = b"\x1b[0m\x1b[?1006l\x1b[?1015l\x1b[?1003l\x1b[?1002l\x1b[?1000l\x1b[?2026l\x1b[?25h\x1b[?1049l";
const POP_KEYBOARD: &[u8] = b"\x1b[<1u";

static ACTIVE: AtomicBool = AtomicBool::new(false);
static KEYBOARD: AtomicBool = AtomicBool::new(false);
static ORIGINAL: OnceLock<libc::termios> = OnceLock::new();

/// Leave the alternate screen, mouse capture and raw mode. Idempotent and safe to call from a
/// signal handler or a panic hook (only `write` and `tcsetattr`).
fn restore() {
    if !ACTIVE.swap(false, Ordering::SeqCst) {
        return;
    }
    unsafe {
        if KEYBOARD.swap(false, Ordering::SeqCst) {
            libc::write(1, POP_KEYBOARD.as_ptr().cast(), POP_KEYBOARD.len());
        }
        libc::write(1, LEAVE.as_ptr().cast(), LEAVE.len());
        if let Some(original) = ORIGINAL.get() {
            libc::tcsetattr(0, libc::TCSANOW, original);
        }
    }
}

extern "C" fn on_signal(signal: libc::c_int) {
    restore();
    unsafe { libc::_exit(128 + signal) }
}

const SIGNALS: [libc::c_int; 3] = [libc::SIGINT, libc::SIGTERM, libc::SIGHUP];

/// Only ask the terminal about the kitty keyboard protocol where it is likely to answer:
/// crossterm waits up to two seconds when a terminal ignores the query.
fn keyboard_protocol_likely() -> bool {
    let term = std::env::var("TERM").unwrap_or_default();
    let program = std::env::var("TERM_PROGRAM").unwrap_or_default().to_ascii_lowercase();
    term.contains("kitty") || term.contains("ghostty") || matches!(program.as_str(), "ghostty" | "wezterm" | "kitty")
}

fn truecolor_supported() -> bool {
    std::env::var("COLORTERM")
        .is_ok_and(|value| matches!(value.to_ascii_lowercase().as_str(), "truecolor" | "24bit"))
}

pub struct Terminal {
    renderer: Renderer,
    /// Events read ahead while merging hover floods.
    pending: VecDeque<Event>,
    started: Instant,
    out: io::Stdout,
    /// A game asked for key releases (`Screen::set_releases`).
    releases: bool,
}

impl Terminal {
    pub fn open() -> io::Result<Terminal> {
        let mut original: libc::termios = unsafe { std::mem::zeroed() };
        if unsafe { libc::tcgetattr(0, &mut original) } == 0 {
            let _ = ORIGINAL.set(original);
        }
        terminal::enable_raw_mode()?;
        let mut out = io::stdout();
        ACTIVE.store(true, Ordering::SeqCst);
        if let Err(error) = execute!(
            out,
            terminal::EnterAlternateScreen,
            cursor::Hide,
            event::EnableMouseCapture
        ) {
            restore();
            let _ = terminal::disable_raw_mode();
            return Err(error);
        }
        // Disambiguated escape codes make Esc arrive at once and Ctrl combinations unambiguous;
        // key events stay presses only. Terminals that do not answer the query keep legacy keys.
        if keyboard_protocol_likely()
            && terminal::supports_keyboard_enhancement().unwrap_or(false)
            && execute!(
                out,
                event::PushKeyboardEnhancementFlags(
                    KeyboardEnhancementFlags::DISAMBIGUATE_ESCAPE_CODES
                        | KeyboardEnhancementFlags::REPORT_EVENT_TYPES
                )
            )
            .is_ok()
        {
            KEYBOARD.store(true, Ordering::SeqCst);
        }
        let previous = std::panic::take_hook();
        std::panic::set_hook(Box::new(move |info| {
            // Back to the normal screen first, so the message is readable.
            restore();
            previous(info);
        }));
        for signal in SIGNALS {
            unsafe { libc::signal(signal, on_signal as extern "C" fn(libc::c_int) as libc::sighandler_t) };
        }
        let (rows, columns) = Terminal::measure();
        Ok(Terminal {
            renderer: Renderer::new(rows, columns, truecolor_supported()),
            pending: VecDeque::new(),
            started: Instant::now(),
            out,
            releases: false,
        })
    }

    fn measure() -> (usize, usize) {
        // Some pseudo-terminals report 0x0; assume the classic 80x24 then.
        let (columns, rows) = terminal::size()
            .ok()
            .filter(|(columns, rows)| *columns > 0 && *rows > 0)
            .unwrap_or((80, 24));
        (rows as usize, columns as usize)
    }

    fn next_event(&mut self, wait: Duration) -> io::Result<Option<Event>> {
        if let Some(event) = self.pending.pop_front() {
            return Ok(Some(event));
        }
        if event::poll(wait)? {
            return event::read().map(Some);
        }
        Ok(None)
    }

    /// A pointer flood only matters by its last position: swallow the queued moves and keep
    /// whatever else was behind them.
    fn latest_hover(&mut self, mut hover: (i32, i32)) -> io::Result<(i32, i32)> {
        loop {
            if self.pending.is_empty() {
                if !event::poll(Duration::ZERO)? {
                    return Ok(hover);
                }
                let event = event::read()?;
                self.pending.push_back(event);
            }
            match self.pending.front().and_then(hovered) {
                Some(newer) => {
                    hover = newer;
                    self.pending.pop_front();
                }
                None => return Ok(hover),
            }
        }
    }
}

fn hovered(event: &Event) -> Option<(i32, i32)> {
    match event {
        Event::Mouse(mouse)
            if matches!(mouse.kind, MouseEventKind::Moved | MouseEventKind::Drag(_)) =>
        {
            Some((mouse.row as i32, mouse.column as i32))
        }
        _ => None,
    }
}

impl Drop for Terminal {
    fn drop(&mut self) {
        for signal in SIGNALS {
            unsafe { libc::signal(signal, libc::SIG_DFL) };
        }
        let _ = terminal::disable_raw_mode();
        restore();
        let _ = self.out.flush();
    }
}

impl Screen for Terminal {
    fn size(&self) -> (i32, i32) {
        self.renderer.size()
    }

    fn clear(&mut self) {
        self.renderer.clear();
    }

    fn put(&mut self, y: i32, x: i32, text: &str, style: Style) {
        self.renderer.put(y, x, text, style);
    }

    fn dim_all(&mut self) {
        self.renderer.dim_all();
    }

    fn save_frame(&mut self) {
        self.renderer.save_frame();
    }

    fn load_frame(&mut self) {
        self.renderer.load_frame();
    }

    fn present(&mut self) -> io::Result<()> {
        self.renderer.render(&mut self.out).map(|_| ())
    }

    fn input(&mut self, timeout: Option<Duration>) -> io::Result<Option<Input>> {
        let deadline = timeout.map(|timeout| Instant::now() + timeout);
        loop {
            let wait = deadline
                .map(|deadline| deadline.saturating_duration_since(Instant::now()))
                .unwrap_or(Duration::from_secs(3600));
            let Some(event) = self.next_event(wait)? else {
                if deadline.is_some() {
                    return Ok(None);
                }
                continue;
            };
            let mapped = match event {
                Event::Resize(..) => {
                    let (rows, columns) = Terminal::measure();
                    self.renderer.resize(rows, columns);
                    return Ok(None);
                }
                Event::Key(key) => {
                    // Releases are reported by the keyboard protocol but only passed on to a game that asked.
                    let release = key.kind == KeyEventKind::Release;
                    if release && !self.releases {
                        continue;
                    }
                    if !release
                        && key.modifiers.contains(KeyModifiers::CONTROL)
                        && key.code == KeyCode::Char('c')
                    {
                        return Err(io::Error::new(io::ErrorKind::Interrupted, "interrupted"));
                    }
                    let key = match key.code {
                        KeyCode::Up => Key::Up,
                        KeyCode::Down => Key::Down,
                        KeyCode::Left => Key::Left,
                        KeyCode::Right => Key::Right,
                        KeyCode::Enter => Key::Enter,
                        KeyCode::Esc => Key::Esc,
                        KeyCode::Backspace => Key::Backspace,
                        KeyCode::Char(character) => Key::Char(character),
                        _ => continue,
                    };
                    if release { Input::Release(key) } else { Input::Key(key) }
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
                        MouseEventKind::Moved | MouseEventKind::Drag(_) => {
                            let (y, x) = self.latest_hover((y, x))?;
                            Input::Hover { y, x }
                        }
                        _ => continue,
                    }
                }
                _ => continue,
            };
            return Ok(Some(mapped));
        }
    }

    fn set_releases(&mut self, on: bool) -> bool {
        // Only the kitty keyboard protocol reports releases; legacy terminals send presses only.
        self.releases = on && KEYBOARD.load(Ordering::SeqCst);
        self.releases
    }

    fn now(&self) -> f64 {
        self.started.elapsed().as_secs_f64()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn red() -> Style {
        Style::fg(Color::Red)
    }

    fn draw_sample(renderer: &mut Renderer) {
        renderer.clear();
        renderer.put(1, 2, "hello", red());
        renderer.put(3, 0, "world", Style::fg(Color::Green).bold());
    }

    fn text(bytes: &[u8]) -> String {
        String::from_utf8_lossy(bytes).replace('\x1b', "<E>")
    }

    #[test]
    fn the_first_frame_clears_and_draws_inside_one_synchronized_update() {
        let mut renderer = Renderer::new(5, 20, false);
        draw_sample(&mut renderer);
        let mut out = Vec::new();
        let written = renderer.render(&mut out).unwrap();
        assert_eq!(written, out.len());
        let shown = text(&out);
        assert!(shown.starts_with("<E>[?2026h"), "{shown}");
        assert!(shown.ends_with("<E>[?2026l"), "{shown}");
        assert!(shown.contains("<E>[2J"), "{shown}");
        assert!(
            shown.contains("hello") && shown.contains("world"),
            "{shown}"
        );
    }

    #[test]
    fn an_unchanged_frame_writes_nothing() {
        let mut renderer = Renderer::new(5, 20, false);
        draw_sample(&mut renderer);
        renderer.render(&mut Vec::new()).unwrap();
        draw_sample(&mut renderer);
        let mut out = Vec::new();
        assert_eq!(renderer.render(&mut out).unwrap(), 0);
        assert!(out.is_empty());
    }

    #[test]
    fn one_changed_cell_writes_only_that_cell() {
        let mut renderer = Renderer::new(5, 20, false);
        draw_sample(&mut renderer);
        renderer.render(&mut Vec::new()).unwrap();
        draw_sample(&mut renderer);
        renderer.put(1, 4, "L", red());
        let mut out = Vec::new();
        renderer.render(&mut out).unwrap();
        // Row 2, column 5 (1-based): one move, one letter, one reset.
        assert_eq!(text(&out), "<E>[?2026h<E>[2;5H<E>[91mL<E>[0m<E>[?2026l");
    }

    #[test]
    fn neighbouring_cells_share_one_style_change_and_one_move() {
        let mut renderer = Renderer::new(3, 20, false);
        renderer.render(&mut Vec::new()).unwrap();
        renderer.put(0, 0, "abc", red());
        renderer.put(0, 6, "z", red());
        let mut out = Vec::new();
        renderer.render(&mut out).unwrap();
        // "abc" under one SGR, then a forward jump of 3 (not a full reposition) and no second SGR.
        assert_eq!(
            text(&out),
            "<E>[?2026h<E>[1;1H<E>[91mabc<E>[3Cz<E>[0m<E>[?2026l"
        );
    }

    #[test]
    fn a_style_is_only_reset_when_an_attribute_must_be_turned_off() {
        let mut out = Vec::new();
        style_change(&mut out, Style::PLAIN, Style::fg(Color::Red).bold(), false);
        assert_eq!(text(&out), "<E>[1;91m");
        out.clear();
        style_change(
            &mut out,
            Style::fg(Color::Red).bold(),
            Style::fg(Color::Green).bold(),
            false,
        );
        assert_eq!(text(&out), "<E>[92m", "only the color changes");
        out.clear();
        style_change(
            &mut out,
            Style::fg(Color::Red).bold(),
            Style::fg(Color::Red),
            false,
        );
        assert_eq!(text(&out), "<E>[0;91m", "bold off needs a reset");
        out.clear();
        style_change(
            &mut out,
            Style::fg(Color::Green).on(Color::Blue),
            Style::PLAIN,
            false,
        );
        assert_eq!(text(&out), "<E>[39;49m");
    }

    #[test]
    fn truecolor_uses_rgb_for_hues_and_keeps_white_and_gray_on_the_theme() {
        let mut out = Vec::new();
        style_change(
            &mut out,
            Style::PLAIN,
            Style::fg(Color::Cyan).on(Color::DarkBlue),
            true,
        );
        assert_eq!(text(&out), "<E>[38;2;125;207;255;48;2;64;100;214m");
        out.clear();
        style_change(&mut out, Style::PLAIN, Style::fg(Color::White), true);
        assert_eq!(text(&out), "<E>[97m");
        out.clear();
        style_change(&mut out, Style::PLAIN, Style::fg(Color::Cyan), false);
        assert_eq!(text(&out), "<E>[96m", "16 colors without truecolor");
    }

    #[test]
    fn spaces_do_not_remember_an_invisible_style() {
        let mut renderer = Renderer::new(2, 10, false);
        renderer.put(0, 0, "x", red());
        renderer.render(&mut Vec::new()).unwrap();
        // A red bold space looks like a plain one: no output for it.
        renderer.put(0, 1, " ", red().bold());
        let mut out = Vec::new();
        assert_eq!(renderer.render(&mut out).unwrap(), 0, "{}", text(&out));
        // A background does show on a space.
        renderer.put(0, 1, " ", Style::PLAIN.on(Color::Blue));
        renderer.render(&mut out).unwrap();
        assert!(text(&out).contains("104m"), "{}", text(&out));
    }

    #[test]
    fn the_last_column_does_not_assume_a_cursor_position() {
        let mut renderer = Renderer::new(2, 4, false);
        renderer.render(&mut Vec::new()).unwrap();
        renderer.put(0, 3, "a", Style::PLAIN);
        renderer.put(1, 0, "b", Style::PLAIN);
        let mut out = Vec::new();
        renderer.render(&mut out).unwrap();
        assert_eq!(text(&out), "<E>[?2026h<E>[1;4Ha<E>[2;1Hb<E>[?2026l");
    }

    #[test]
    fn resize_keeps_the_picture_and_repaints_everything() {
        let mut renderer = Renderer::new(5, 20, false);
        draw_sample(&mut renderer);
        renderer.render(&mut Vec::new()).unwrap();
        renderer.resize(4, 10);
        assert_eq!(renderer.size(), (4, 10));
        let mut out = Vec::new();
        renderer.render(&mut out).unwrap();
        let shown = text(&out);
        assert!(
            shown.contains("<E>[2J") && shown.contains("hello") && shown.contains("world"),
            "{shown}"
        );
        renderer.resize(2, 3);
        out.clear();
        renderer.render(&mut out).unwrap();
        assert!(
            text(&out).contains("<E>[2J"),
            "cropping still repaints from scratch"
        );
    }

    #[test]
    fn a_saved_frame_comes_back_after_an_overlay_and_a_resize() {
        let mut renderer = Renderer::new(4, 20, false);
        renderer.put(0, 0, "board", red());
        renderer.save_frame();
        renderer.put(1, 0, "overlay", Style::PLAIN);
        renderer.resize(3, 10);
        renderer.load_frame();
        let mut out = Vec::new();
        renderer.render(&mut out).unwrap();
        let shown = text(&out);
        assert!(shown.contains("board") && !shown.contains("overlay"), "{shown}");
    }

    #[test]
    fn dimming_fades_content_but_not_blank_space() {
        let render = |dim_after: bool| {
            let mut renderer = Renderer::new(2, 10, false);
            if dim_after {
                renderer.put(0, 0, "a", Style::fg(Color::Red));
                renderer.dim_all();
            } else {
                renderer.put(0, 0, "a", Style::fg(Color::Red).dim());
            }
            let mut out = Vec::new();
            renderer.render(&mut out).unwrap();
            out
        };
        assert_eq!(render(true), render(false));
        let mut blank = Renderer::new(2, 10, false);
        blank.render(&mut Vec::new()).unwrap();
        blank.dim_all();
        assert_eq!(blank.render(&mut Vec::new()).unwrap(), 0);
    }

    #[test]
    fn a_failed_write_forces_a_full_repaint() {
        struct Broken;
        impl Write for Broken {
            fn write(&mut self, _: &[u8]) -> io::Result<usize> {
                Err(io::ErrorKind::BrokenPipe.into())
            }
            fn flush(&mut self) -> io::Result<()> {
                Ok(())
            }
        }
        let mut renderer = Renderer::new(3, 10, false);
        draw_sample(&mut renderer);
        assert!(renderer.render(&mut Broken).is_err());
        let mut out = Vec::new();
        assert!(renderer.render(&mut out).unwrap() > 0);
        assert!(text(&out).contains("<E>[2J"));
    }

    /// A `Screen` over the renderer, to run real games through the diff output.
    struct Headless {
        renderer: Renderer,
        frames: Vec<usize>,
        clock: f64,
        script: VecDeque<Option<Input>>,
    }

    impl Screen for Headless {
        fn size(&self) -> (i32, i32) {
            self.renderer.size()
        }
        fn clear(&mut self) {
            self.renderer.clear();
        }
        fn put(&mut self, y: i32, x: i32, text: &str, style: Style) {
            self.renderer.put(y, x, text, style);
        }
        fn dim_all(&mut self) {
            self.renderer.dim_all();
        }
        fn present(&mut self) -> io::Result<()> {
            let written = self.renderer.render(&mut Vec::new())?;
            self.frames.push(written);
            Ok(())
        }
        fn input(&mut self, timeout: Option<Duration>) -> io::Result<Option<Input>> {
            match self.script.pop_front() {
                Some(Some(input)) => {
                    self.clock += 0.6;
                    Ok(Some(input))
                }
                Some(None) => {
                    self.clock += timeout.map_or(1.0, |timeout| timeout.as_secs_f64());
                    Ok(None)
                }
                None => {
                    self.clock += 0.6;
                    Ok(Some(Input::Key(Key::Esc)))
                }
            }
        }
        fn now(&self) -> f64 {
            self.clock
        }
    }

    #[test]
    fn a_running_tetris_frame_is_a_small_diff() {
        let mut screen = Headless {
            renderer: Renderer::new(30, 100, true),
            frames: Vec::new(),
            clock: 0.0,
            script: std::iter::repeat_n(None, 120).collect(),
        };
        let mut rng = super::super::Rng::constant(0);
        super::super::tetris::play(
            &mut screen,
            super::super::Level::Normal,
            &mut rng,
            None,
            None,
        )
        .unwrap();
        let first = screen.frames[0];
        // 30x100 = 3000 cells; a steady frame only moves the falling piece and the HUD.
        let steady: Vec<usize> = screen.frames[2..100].to_vec();
        println!("tetris first frame {first} bytes, largest steady frame {:?} bytes, non-empty {}", steady.iter().max(), steady.iter().filter(|b| **b > 0).count());
        assert!(first > 1000);
        assert!(steady.iter().all(|bytes| *bytes < 300), "{steady:?}");
    }
}
