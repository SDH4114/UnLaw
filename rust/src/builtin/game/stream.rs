//! `ul game --stream`: the same games over JSON lines, so `ul desk` can show
//! them in the browser.
//!
//! Input, one object per line on stdin:
//! `{"key":"up"}` (up/down/left/right/enter/esc or one character),
//! `{"click":{"y":3,"x":9,"button":"left"}}`, `{"hover":{"y":3,"x":9}}`,
//! `{"resize":{"rows":40,"cols":120}}`.
//! Output, one frame per line on stdout, only when the picture changed:
//! `{"rows":R,"cols":C,"lines":[[["text","fg","bg",flags],...],...]}` where
//! flags is 1 bold + 2 reverse + 4 dim. Closing stdin ends the game.

use std::io::{self, BufRead, Read, Write};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use super::{Button, Color, Input, Key, Screen, Style};

/// Rows/columns a browser may ask for; games explain when it is too small.
pub const MIN_SIZE: (i32, i32) = (10, 20);
pub const MAX_SIZE: (i32, i32) = (200, 400);
/// Longest stdin line kept; longer ones are dropped so a client cannot grow memory without bound.
const MAX_LINE: usize = 64 * 1024;

#[derive(Clone, Copy, Debug, PartialEq)]
enum Message {
    Input(Input),
    Resize(i32, i32),
}

pub fn clamp_size(rows: i32, cols: i32) -> (i32, i32) {
    (
        rows.clamp(MIN_SIZE.0, MAX_SIZE.0),
        cols.clamp(MIN_SIZE.1, MAX_SIZE.1),
    )
}

/// `"40x120"` → (rows, cols), clamped.
pub fn parse_size(text: &str) -> Option<(i32, i32)> {
    let (rows, cols) = text.split_once('x')?;
    Some(clamp_size(
        rows.trim().parse().ok()?,
        cols.trim().parse().ok()?,
    ))
}

fn coordinate(value: &Value, name: &str) -> Option<i32> {
    i32::try_from(value.get(name)?.as_i64()?).ok()
}

/// One stdin line → a message; anything malformed is ignored.
fn parse(line: &str) -> Option<Message> {
    let value: Value = serde_json::from_str(line).ok()?;
    if let Some(key) = value.get("key").and_then(Value::as_str) {
        let key = match key {
            "up" => Key::Up,
            "down" => Key::Down,
            "left" => Key::Left,
            "right" => Key::Right,
            "enter" => Key::Enter,
            "esc" => Key::Esc,
            other => {
                let mut characters = other.chars();
                match (characters.next(), characters.next()) {
                    (Some(character), None) if !character.is_control() => Key::Char(character),
                    _ => return None,
                }
            }
        };
        return Some(Message::Input(Input::Key(key)));
    }
    if let Some(click) = value.get("click") {
        let button = match click
            .get("button")
            .and_then(Value::as_str)
            .unwrap_or("left")
        {
            "left" => Button::Left,
            "right" => Button::Right,
            "middle" => Button::Middle,
            _ => return None,
        };
        return Some(Message::Input(Input::Click {
            y: coordinate(click, "y")?,
            x: coordinate(click, "x")?,
            button,
        }));
    }
    if let Some(hover) = value.get("hover") {
        return Some(Message::Input(Input::Hover {
            y: coordinate(hover, "y")?,
            x: coordinate(hover, "x")?,
        }));
    }
    if let Some(resize) = value.get("resize") {
        let (rows, cols) = clamp_size(coordinate(resize, "rows")?, coordinate(resize, "cols")?);
        return Some(Message::Resize(rows, cols));
    }
    None
}

fn color_name(color: Color) -> &'static str {
    match color {
        Color::Default => "",
        Color::Red => "red",
        Color::Green => "green",
        Color::Yellow => "yellow",
        Color::Blue => "blue",
        Color::Magenta => "magenta",
        Color::Cyan => "cyan",
        Color::White => "white",
        Color::Gray => "gray",
        Color::DarkRed => "darkred",
        Color::DarkYellow => "darkyellow",
        Color::DarkBlue => "darkblue",
        Color::DarkCyan => "darkcyan",
    }
}

#[derive(Clone, Copy, PartialEq)]
struct Cell {
    text: char,
    style: Style,
}

const BLANK: Cell = Cell {
    text: ' ',
    style: Style::PLAIN,
};

/// A frame as one JSON line: each row is a list of same-style runs.
fn encode(frame: &[Vec<Cell>], rows: i32, cols: i32) -> String {
    let lines: Vec<Value> = frame
        .iter()
        .map(|row| {
            let mut runs: Vec<Value> = Vec::new();
            let mut text = String::new();
            let mut current: Option<Style> = None;
            let flush = |text: &mut String, style: Option<Style>, runs: &mut Vec<Value>| {
                if let Some(style) = style.filter(|_| !text.is_empty()) {
                    let flags = u8::from(style.bold)
                        | u8::from(style.reverse) << 1
                        | u8::from(style.dim) << 2;
                    runs.push(json!([
                        std::mem::take(text),
                        color_name(style.fg),
                        color_name(style.bg),
                        flags
                    ]));
                }
            };
            for cell in row {
                if current != Some(cell.style) {
                    flush(&mut text, current, &mut runs);
                    current = Some(cell.style);
                }
                text.push(cell.text);
            }
            flush(&mut text, current, &mut runs);
            Value::Array(runs)
        })
        .collect();
    json!({ "rows": rows, "cols": cols, "lines": lines }).to_string()
}

pub struct Stream<W: Write> {
    frame: Vec<Vec<Cell>>,
    size: (i32, i32),
    last: String,
    started: Instant,
    messages: Receiver<Message>,
    out: W,
}

/// Discards input up to and including the next newline (or the end of input).
fn skip_line<R: BufRead>(input: &mut R) -> io::Result<()> {
    loop {
        let available = input.fill_buf()?;
        if available.is_empty() {
            return Ok(());
        }
        match available.iter().position(|byte| *byte == b'\n') {
            Some(index) => {
                input.consume(index + 1);
                return Ok(());
            }
            None => {
                let length = available.len();
                input.consume(length);
            }
        }
    }
}

impl<W: Write> Stream<W> {
    /// Reads `input` on its own thread so `input(timeout)` can wait with a deadline.
    pub fn new<R: BufRead + Send + 'static>(input: R, out: W, size: (i32, i32)) -> Stream<W> {
        let (sender, messages) = mpsc::channel();
        std::thread::spawn(move || {
            let mut input = input;
            let mut buffer = Vec::new();
            loop {
                buffer.clear();
                // Read at most one byte over the cap, so memory stays bounded whatever the client sends.
                match input.by_ref().take(MAX_LINE as u64 + 1).read_until(b'\n', &mut buffer) {
                    Ok(0) | Err(_) => break,
                    Ok(_) => {}
                }
                if buffer.last() == Some(&b'\n') {
                    buffer.pop();
                } else if buffer.len() > MAX_LINE {
                    // Too long: drop it up to the next newline.
                    if skip_line(&mut input).is_err() {
                        break;
                    }
                    continue;
                }
                let Ok(line) = std::str::from_utf8(&buffer) else { break };
                if let Some(message) = parse(line.trim_end_matches('\r')) {
                    if sender.send(message).is_err() {
                        break;
                    }
                }
            }
        });
        let mut stream = Stream {
            frame: Vec::new(),
            size: clamp_size(size.0, size.1),
            last: String::new(),
            started: Instant::now(),
            messages,
            out,
        };
        stream.clear();
        stream
    }
}

impl<W: Write> Screen for Stream<W> {
    fn size(&self) -> (i32, i32) {
        self.size
    }

    fn clear(&mut self) {
        let (rows, cols) = self.size;
        self.frame = vec![vec![BLANK; cols as usize]; rows as usize];
    }

    fn put(&mut self, y: i32, x: i32, text: &str, style: Style) {
        let Some(row) = usize::try_from(y).ok().and_then(|y| self.frame.get_mut(y)) else {
            return;
        };
        for (offset, character) in text.chars().enumerate() {
            let column = x + offset as i32;
            if let Some(cell) = usize::try_from(column)
                .ok()
                .and_then(|column| row.get_mut(column))
            {
                *cell = Cell {
                    text: character,
                    style,
                };
            }
        }
    }

    fn dim_all(&mut self) {
        for cell in self.frame.iter_mut().flatten() {
            if cell.text != ' ' {
                cell.style.dim = true;
            }
        }
    }

    fn present(&mut self) -> io::Result<()> {
        let line = encode(&self.frame, self.size.0, self.size.1);
        if line == self.last {
            return Ok(());
        }
        writeln!(self.out, "{line}")?;
        self.out.flush()?;
        self.last = line;
        Ok(())
    }

    fn input(&mut self, timeout: Option<Duration>) -> io::Result<Option<Input>> {
        let message = match timeout {
            Some(timeout) => match self.messages.recv_timeout(timeout) {
                Ok(message) => message,
                Err(RecvTimeoutError::Timeout) => return Ok(None),
                Err(RecvTimeoutError::Disconnected) => {
                    return Err(io::Error::new(io::ErrorKind::Interrupted, "input closed"))
                }
            },
            None => self
                .messages
                .recv()
                .map_err(|_| io::Error::new(io::ErrorKind::Interrupted, "input closed"))?,
        };
        match message {
            Message::Input(input) => Ok(Some(input)),
            Message::Resize(rows, cols) => {
                // Like a terminal resize: the next draw fills the new grid.
                self.size = (rows, cols);
                self.clear();
                self.last.clear();
                Ok(None)
            }
        }
    }

    fn now(&self) -> f64 {
        self.started.elapsed().as_secs_f64()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_keys_mouse_and_resize() {
        assert_eq!(
            parse(r#"{"key":"up"}"#),
            Some(Message::Input(Input::Key(Key::Up)))
        );
        assert_eq!(
            parse(r#"{"key":"esc"}"#),
            Some(Message::Input(Input::Key(Key::Esc)))
        );
        assert_eq!(
            parse(r#"{"key":"W"}"#),
            Some(Message::Input(Input::Key(Key::Char('W'))))
        );
        assert_eq!(
            parse(r#"{"key":" "}"#),
            Some(Message::Input(Input::Key(Key::Char(' '))))
        );
        assert_eq!(parse(r#"{"key":"ab"}"#), None);
        assert_eq!(parse(r#"{"key":"\u0003"}"#), None);
        assert_eq!(
            parse(r#"{"click":{"y":3,"x":9,"button":"right"}}"#),
            Some(Message::Input(Input::Click {
                y: 3,
                x: 9,
                button: Button::Right
            }))
        );
        assert_eq!(
            parse(r#"{"click":{"y":3,"x":9}}"#),
            Some(Message::Input(Input::Click {
                y: 3,
                x: 9,
                button: Button::Left
            }))
        );
        assert_eq!(parse(r#"{"click":{"y":3,"x":9,"button":"side"}}"#), None);
        assert_eq!(
            parse(r#"{"hover":{"y":1,"x":2}}"#),
            Some(Message::Input(Input::Hover { y: 1, x: 2 }))
        );
        assert_eq!(
            parse(r#"{"resize":{"rows":5,"cols":9999}}"#),
            Some(Message::Resize(10, 400))
        );
        assert_eq!(parse("not json"), None);
        assert_eq!(parse(r#"{"other":1}"#), None);
        assert_eq!(parse_size("40x120"), Some((40, 120)));
        assert_eq!(parse_size("1x1"), Some((10, 20)));
        assert_eq!(parse_size("40"), None);
    }

    #[test]
    fn frames_are_runs_sent_only_when_changed() {
        let mut stream = Stream::new(io::Cursor::new(Vec::new()), Vec::new(), (10, 20));
        stream.put(0, 0, "ab", Style::fg(Color::Red).bold());
        stream.put(0, 2, "c", Style::PLAIN.reverse());
        stream.present().unwrap();
        stream.present().unwrap();
        let text = String::from_utf8(stream.out.clone()).unwrap();
        assert_eq!(
            text.lines().count(),
            1,
            "an unchanged frame is not sent again"
        );
        let frame: Value = serde_json::from_str(text.lines().next().unwrap()).unwrap();
        assert_eq!(frame["rows"], 10);
        assert_eq!(frame["cols"], 20);
        assert_eq!(frame["lines"][0][0], json!(["ab", "red", "", 1]));
        assert_eq!(frame["lines"][0][1], json!(["c", "", "", 2]));
        assert_eq!(frame["lines"][0][2][0].as_str().unwrap().len(), 17);
        assert_eq!(frame["lines"].as_array().unwrap().len(), 10);
    }

    #[test]
    fn overlong_input_lines_are_dropped() {
        // A valid message padded past the cap is dropped; the next short line still arrives.
        let padding = " ".repeat(MAX_LINE + 10);
        let mut bytes = format!("{{\"key\":\"x\"{padding}}}\n{{\"key\":\"q\"}}\n").into_bytes();
        bytes.extend(format!("{{\"key\":\"y\"{padding}}}").into_bytes());
        let mut stream = Stream::new(io::Cursor::new(bytes), Vec::new(), (24, 80));
        assert_eq!(
            stream.input(None).unwrap(),
            Some(Input::Key(Key::Char('q')))
        );
        // The unterminated oversized tail is dropped too, then stdin is over.
        let error = stream.input(Some(Duration::from_secs(5))).unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::Interrupted);
    }

    #[test]
    fn input_waits_resizes_and_ends_with_stdin() {
        let input =
            io::Cursor::new(b"{\"key\":\"q\"}\n{\"resize\":{\"rows\":30,\"cols\":90}}\n".to_vec());
        let mut stream = Stream::new(input, Vec::new(), (24, 80));
        assert_eq!(
            stream.input(None).unwrap(),
            Some(Input::Key(Key::Char('q')))
        );
        assert_eq!(stream.input(None).unwrap(), None);
        assert_eq!(stream.size(), (30, 90));
        let error = stream.input(Some(Duration::from_secs(5))).unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::Interrupted);
    }
}
