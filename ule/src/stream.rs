//! `ule --stream`: the editor drawn into a window instead of a terminal (Unlaw.app's Edit).
//!
//! The same editor, keys, LSP and settings as in a terminal; only the host differs. One
//! JSON object per line each way:
//!
//! stdin (the host):
//!   {"key": {"code": "a" | "Enter" | "Esc" | "Tab" | "BackTab" | "Backspace" | "Delete" | "Up" | "Down"
//!            | "Left" | "Right" | "Home" | "End" | "PageUp" | "PageDown" | "Insert" | "F1".."F12",
//!            "ctrl": bool, "alt": bool, "shift": bool}}
//!   {"paste": "text"}
//!   {"mouse": {"kind": "down" | "drag" | "up" | "scroll_up" | "scroll_down", "x": col, "y": row}}
//!   {"resize": {"rows": n, "cols": n}}
//!   {"focus": bool}                       (false = focus lost: auto_save when it is on)
//!   {"open": {"path": "/abs/file", "line": n?}}
//!   {"show": "/abs/file"}                 (bring an open buffer to the front)
//!   {"close": "/abs/file"}                (refused while it has unsaved changes)
//!   {"theme": "light" | "dark"}           (light swaps the terminal-colored `unlaw` theme for `light`)
//!   {"redraw": true}                      (a new page: send the frame again even if nothing changed)
//!
//! stdout (ule), only when something changed:
//!   {"rows", "cols", "lines": [[[x, "text", fg, bg, flags], ...], ...], "cursor": [y, x, bar] | null,
//!    "buffers": [{"path", "name", "modified", "active"}], "typing": bool}
//!   typing: keys are text now (insert mode, a prompt or picker, or a command waiting for
//!   its character like `f` or `r`); otherwise they are commands, and a host may send the
//!   key's place on a US keyboard instead of its character in another layout.
//!   fg/bg: "" (the host's default), "#rrggbb" or "a<0-255>" (an ANSI/xterm color the host maps);
//!   flags: 1 bold, 2 reverse, 4 dim, 8 italic, 16 underline, 32 undercurl, 64 crossed.
//!   A run never continues past a wide char, so x is exact for every run.
//!
//! Closed stdin, SIGTERM or SIGHUP end it like a closed terminal: unsaved buffers are kept
//! as recovery copies first. There is no terminal to hand over: `:!cmd` and `:ul!` run in
//! the output panel, `:terminal` and suspend are refused.

use std::io::{self, BufRead, Read, Write};
use std::path::PathBuf;
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::time::{Duration, Instant};

use serde_json::{json, Value as Json};

use crate::app::{self, Launch, MouseKind};
use crate::editor::Editor;
use crate::keys::{Code, Key};
use crate::render::Surface;
use crate::text::Pos;
use crate::theme::{Color, Style};

pub const MIN_ROWS: u16 = 5;
pub const MIN_COLS: u16 = 20;
pub const MAX_ROWS: u16 = 400;
pub const MAX_COLS: u16 = 800;
/// Longer input lines are dropped (a paste of 4 MB is plenty for a window).
const MAX_LINE: usize = 4 << 20;
/// At most this many frames a second, however fast keys arrive.
const FRAME_GAP: Duration = Duration::from_millis(16);

/// What the host sent, decoded and checked.
#[derive(Debug, PartialEq)]
pub enum Input {
    Key(Key),
    Paste(String),
    Mouse(MouseKind, u16, u16),
    Resize(u16, u16),
    Focus(bool),
    Open(PathBuf, Option<usize>),
    Show(PathBuf),
    Close(PathBuf),
    Theme(bool),
    /// One of the window's menu commands (`COMMANDS`), whatever mode the editor is in.
    Command(String),
    /// The project folder file search and grep start from.
    Cd(PathBuf),
    /// `:set name=value` for the options a window may change (`SETTABLE`).
    Set(String, String),
    Redraw,
    /// stdin closed: the host is gone.
    End,
}

/// Commands the window's buttons and ⌘ keys run (ule's command names).
pub const COMMANDS: &[&str] = &[
    "file_picker",
    "command_palette",
    "grep",
    "buffer_picker",
    "recent_files",
    "symbols",
    "goto_definition",
    "save",
    "save_all",
    "panel",
    "keymap_picker",
    "complete",
    "workspace_symbols",
    "diagnostics",
    "diagnostic_next",
    "diagnostic_prev",
    "references",
    "hover",
    "rename",
    "code_action",
    "new_file",
    "buffer_next",
    "buffer_prev",
    "vsplit",
];

/// Options the window's settings may change through `{"set": {...}}`.
pub const SETTABLE: &[&str] =
    &["editing", "theme", "line_numbers", "wrap", "tab_width", "auto_save", "show_whitespace"];

pub fn clamp_size(rows: u16, cols: u16) -> (u16, u16) {
    (rows.clamp(MIN_ROWS, MAX_ROWS), cols.clamp(MIN_COLS, MAX_COLS))
}

/// One input line; None for anything malformed or unknown (it is ignored).
pub fn decode(line: &str) -> Option<Input> {
    let value: Json = serde_json::from_str(line).ok()?;
    let object = value.as_object()?;
    let (name, body) = object.iter().next()?;
    let number = |value: &Json| value.as_u64().map(|number| number.min(u16::MAX as u64) as u16);
    let path = |value: &Json| {
        let text = value.as_str()?;
        let path = PathBuf::from(text);
        (path.is_absolute() && !text.contains('\0')).then_some(path)
    };
    Some(match name.as_str() {
        "key" => Input::Key(decode_key(body)?),
        "paste" => Input::Paste(body.as_str()?.to_string()),
        "mouse" => {
            let kind = match body["kind"].as_str()? {
                "down" if body["alt"].as_bool() == Some(true) => MouseKind::AddCursor,
                "down" => MouseKind::Down,
                "drag" => MouseKind::Drag,
                "up" => MouseKind::Up,
                "scroll_up" => MouseKind::ScrollUp,
                "scroll_down" => MouseKind::ScrollDown,
                _ => return None,
            };
            Input::Mouse(kind, number(&body["x"])?, number(&body["y"])?)
        }
        "resize" => {
            let (rows, cols) = clamp_size(number(&body["rows"])?, number(&body["cols"])?);
            Input::Resize(rows, cols)
        }
        "focus" => Input::Focus(body.as_bool()?),
        "open" => Input::Open(path(&body["path"])?, body["line"].as_u64().map(|line| line as usize)),
        "show" => Input::Show(path(body)?),
        "cd" => Input::Cd(path(body)?),
        "close" => Input::Close(path(body)?),
        "redraw" => Input::Redraw,
        "command" => {
            let name = body.as_str()?;
            (COMMANDS.contains(&name) || crate::actions::is(name)).then(|| Input::Command(name.to_string()))?
        }
        "set" => {
            let name = body["name"].as_str()?;
            let value = body["value"].as_str()?;
            let plain = |text: &str| {
                !text.is_empty()
                    && text.len() <= 40
                    && text.chars().all(|c| c.is_ascii_alphanumeric() || "-_".contains(c))
            };
            (SETTABLE.contains(&name) && plain(value)).then(|| Input::Set(name.to_string(), value.to_string()))?
        }
        "theme" => match body.as_str()? {
            "light" => Input::Theme(true),
            "dark" => Input::Theme(false),
            _ => return None,
        },
        _ => return None,
    })
}

fn decode_key(body: &Json) -> Option<Key> {
    let name = body["code"].as_str()?;
    let flag = |key: &str| body[key].as_bool().unwrap_or(false);
    let mut chars = name.chars();
    let code = match (chars.next(), chars.next()) {
        (Some(c), None) if !c.is_control() => Code::Char(c),
        _ => match name {
            "Esc" => Code::Esc,
            "Enter" => Code::Enter,
            "Tab" => Code::Tab,
            "BackTab" => Code::BackTab,
            "Backspace" => Code::Backspace,
            "Delete" => Code::Delete,
            "Up" => Code::Up,
            "Down" => Code::Down,
            "Left" => Code::Left,
            "Right" => Code::Right,
            "Home" => Code::Home,
            "End" => Code::End,
            "PageUp" => Code::PageUp,
            "PageDown" => Code::PageDown,
            "Insert" => Code::Insert,
            _ => Code::F(name.strip_prefix('F')?.parse::<u8>().ok().filter(|n| (1..=24).contains(n))?),
        },
    };
    let (ctrl, alt) = (flag("ctrl"), flag("alt"));
    // Same shape as Key::from_event: a letter under Ctrl is lower case with Shift as a flag,
    // a plain char carries its shift in the char itself.
    if let Code::Char(c) = code {
        let shift = ctrl && c.is_ascii_alphabetic() && (flag("shift") || c.is_ascii_uppercase());
        let c = if ctrl { c.to_ascii_lowercase() } else { c };
        return Some(Key { code: Code::Char(c), ctrl, alt, shift });
    }
    let shift = flag("shift") && code != Code::BackTab;
    Some(Key { code, ctrl, alt, shift })
}

fn color(color: Option<Color>) -> String {
    match color {
        None | Some(Color::Reset) => String::new(),
        Some(Color::Ansi(index)) => format!("a{index}"),
        Some(Color::Rgb(r, g, b)) => format!("#{r:02x}{g:02x}{b:02x}"),
    }
}

/// The theme's main colors, so the window can paint its own panels to match (Zed-like).
pub fn colors(ed: &Editor) -> Json {
    theme_colors(&ed.theme)
}

/// The colors a host window paints its own surfaces with (ule --theme-colors, frames).
pub fn theme_colors(theme: &crate::theme::Theme) -> Json {
    let text = theme.text();
    let pick = |key: &str, bg: bool| {
        let style = theme.get(key);
        color(if bg { style.bg } else { style.fg })
    };
    serde_json::json!({
        "name": theme.name,
        "bg": color(text.bg),
        "fg": color(text.fg),
        "panel": pick("ui.statusline", true),
        "line": pick("ui.cursorline", true),
        "selection": pick("ui.selection", true),
        "muted": pick("ui.linenr", false),
        "border": pick("ui.separator", false),
        "accent": pick("ui.mode.normal", true),
        "dir": pick("ui.explorer.dir", false),
    })
}

fn flags(style: &Style) -> u8 {
    [style.bold, style.reverse, style.dim, style.italic, style.underline, style.undercurl, style.crossed]
        .iter()
        .enumerate()
        .fold(0, |flags, (bit, on)| if *on { flags | 1 << bit } else { flags })
}

/// The cells as rows of style runs.
pub fn encode(surface: &Surface) -> Json {
    let mut lines = Vec::with_capacity(surface.height as usize);
    for y in 0..surface.height {
        let mut runs: Vec<Json> = Vec::new();
        let mut current: Option<(u16, String, Style)> = None;
        let close = |current: &mut Option<(u16, String, Style)>, runs: &mut Vec<Json>| {
            if let Some((x, text, style)) = current.take() {
                runs.push(json!([x, text, color(style.fg), color(style.bg), flags(&style)]));
            }
        };
        for x in 0..surface.width {
            let Some(cell) = surface.get(x, y) else { continue };
            if cell.continuation {
                // The right half of a wide char: the run already ended at it.
                continue;
            }
            match current.as_mut() {
                Some((_, text, style)) if *style == cell.style => text.push(cell.symbol),
                _ => {
                    close(&mut current, &mut runs);
                    current = Some((x, cell.symbol.to_string(), cell.style));
                }
            }
            let wide = surface.get(x + 1, y).is_some_and(|next| next.continuation);
            if wide {
                close(&mut current, &mut runs);
            }
        }
        close(&mut current, &mut runs);
        lines.push(Json::Array(runs));
    }
    let cursor = surface.cursor.map(|(x, y)| json!([y, x, surface.cursor_bar]));
    json!({"rows": surface.height, "cols": surface.width, "lines": lines, "cursor": cursor})
}

/// Whether a key typed now is text (see the protocol at the top).
fn typing(ed: &Editor) -> bool {
    use crate::editor::Mode;
    let waiting_for_char = ed.vim.pending.last().is_some_and(|key| {
        key.as_char().is_some_and(|c| ['f', 'F', 't', 'T', 'r', 'm', '\'', '`', '"', 'q', '@'].contains(&c))
    });
    matches!(ed.mode, Mode::Insert | Mode::Replace) || ed.prompt.is_some() || ed.picker.is_some() || waiting_for_char
}

fn buffers(ed: &Editor) -> Json {
    let active = ed.view().doc;
    let list: Vec<Json> = ed
        .buffers
        .iter()
        .filter_map(|id| ed.docs.get(id))
        .map(|doc| {
            json!({
                "path": doc.path.as_ref().map(|path| path.display().to_string()),
                "name": doc.file_name(),
                "modified": doc.modified(),
                "active": doc.id == active,
            })
        })
        .collect();
    Json::Array(list)
}

fn spawn_reader() -> Receiver<Input> {
    let (tx, rx) = mpsc::channel();
    std::thread::spawn(move || {
        let stdin = io::stdin();
        let mut reader = stdin.lock();
        let mut line = Vec::new();
        loop {
            line.clear();
            match reader.by_ref().take(MAX_LINE as u64 + 1).read_until(b'\n', &mut line) {
                Ok(0) | Err(_) => break,
                Ok(_) if line.len() > MAX_LINE && line.last() != Some(&b'\n') => {
                    // Too long: skip the rest of this line.
                    let mut rest = Vec::new();
                    if reader.read_until(b'\n', &mut rest).map_or(true, |read| read == 0) {
                        break;
                    }
                }
                Ok(_) => {
                    if let Some(input) = std::str::from_utf8(&line).ok().and_then(|text| decode(text.trim_end())) {
                        if tx.send(input).is_err() {
                            return;
                        }
                    }
                }
            }
        }
        let _ = tx.send(Input::End);
    });
    rx
}

/// The theme `ule.toml` asked for, and the one to show on a light window.
struct Themes {
    chosen: String,
    light: bool,
}

impl Themes {
    fn apply(&mut self, ed: &mut Editor, light: bool) {
        self.light = light;
        // Only the terminal-colored default has a light twin; a theme the user picked stays.
        let name = if light && self.chosen == "unlaw" { "light" } else { self.chosen.as_str() };
        if ed.theme.name != name {
            crate::ex::run(ed, &format!("theme {name}"));
        }
    }
}

fn handle(
    ed: &mut Editor,
    input: Input,
    anchor: &mut Option<(usize, Pos)>,
    themes: &mut Themes,
    last: &mut String,
) -> bool {
    match input {
        Input::Redraw => last.clear(),
        Input::Key(key) => app::key_input(ed, key),
        Input::Paste(text) => app::paste(ed, &text),
        Input::Mouse(kind, x, y) => app::mouse_event(ed, kind, x, y, anchor),
        Input::Resize(rows, cols) => ed.size = (cols, rows),
        Input::Focus(true) => ed.check_disk_changes(),
        Input::Focus(false) => {
            if ed.options.auto_save {
                ed.save_all_quietly();
            }
        }
        Input::Open(path, line) => match ed.open(&path) {
            Ok(_) => {
                if let Some(line) = line {
                    ed.set_cursor(Pos::new(line.saturating_sub(1), 0));
                    ed.align_cursor('z');
                }
            }
            Err(error) => ed.error(error),
        },
        Input::Show(path) => match ed.find_doc(&path) {
            Some(id) => ed.show_doc(id),
            None => ed.error(format!("{} is not open", path.display())),
        },
        Input::Close(path) => {
            if let Some(id) = ed.find_doc(&path) {
                if let Err(error) = ed.close_doc(id, false) {
                    ed.error(error);
                }
            }
        }
        Input::Theme(light) => themes.apply(ed, light),
        Input::Cd(path) => match std::env::set_current_dir(&path) {
            Ok(()) => ed.cwd = path,
            Err(error) => ed.error(format!("{}: {error}", path.display())),
        },
        Input::Command(name) => {
            if matches!(ed.mode, crate::editor::Mode::Insert | crate::editor::Mode::Replace) && !crate::modeless::on(ed)
            {
                crate::vim::leave_insert(ed);
            }
            ed.completion = None;
            if let Err(error) = crate::commands::run(ed, &name, &[], None, None) {
                ed.error(error);
            }
            crate::modeless::settle(ed);
        }
        Input::Set(name, value) if name == "theme" => {
            if let Err(error) = ed.themes.load(&value) {
                ed.error(error);
            } else {
                themes.chosen = value;
                let light = themes.light;
                themes.apply(ed, light);
            }
        }
        Input::Set(name, value) => {
            let was = ed.options.editing;
            if let Err(error) = ed.options.set(&name, &value) {
                ed.error(error);
            }
            crate::modeless::switched(ed, was);
            crate::modeless::settle(ed);
        }
        Input::End => return false,
    }
    true
}

/// What a terminal would have done; a window has none to hand over.
fn no_terminal(ed: &mut Editor) {
    if ed.suspend_requested {
        ed.suspend_requested = false;
        ed.error("ule runs in a window here: there is nothing to suspend to");
    }
    if let Some(handoff) = ed.handoff.take() {
        if handoff.wait {
            if let Err(error) = crate::jobs::run_shell(ed, &handoff.command, "[shell]") {
                ed.error(error);
            }
        } else {
            ed.error(":terminal needs a terminal: open ule in one (ul edit <file>)");
        }
    }
}

pub fn run(launch: Launch, rows: u16, cols: u16, light: bool) -> io::Result<i32> {
    let mut ed = app::prepare(&launch);
    app::catch_termination();
    let (rows, cols) = clamp_size(rows, cols);
    ed.size = (cols, rows);
    // The window draws the open files as its own tabs.
    ed.options.bufferline = crate::config::Bufferline::Never;
    let mut themes = Themes { chosen: ed.theme.name.clone(), light };
    themes.apply(&mut ed, light);
    let tx = ed.tx.clone();
    std::thread::spawn(move || {
        let _ = tx.send(crate::editor::Event::UlCommands(crate::ul::commands()));
    });
    let input = spawn_reader();
    let looped = event_loop(&mut ed, &input, &mut themes);
    // The host closed or a signal came: keep unsaved work first, like the terminal does.
    let recovered = ed.write_recovery();
    ed.remember_positions();
    ed.persisted.save();
    ed.jobs.kill_all();
    ed.lsp.shutdown();
    for (title, path) in &recovered {
        eprintln!("ule: unsaved {title} kept as {}", path.display());
    }
    looped?;
    Ok(app::terminated().map_or(0, |signal| 128 + signal))
}

fn event_loop(ed: &mut Editor, input: &Receiver<Input>, themes: &mut Themes) -> io::Result<()> {
    let mut out = io::BufWriter::with_capacity(1 << 16, io::stdout());
    let mut anchor: Option<(usize, Pos)> = None;
    let mut last = String::new();
    let mut sent = Instant::now() - FRAME_GAP;
    loop {
        if app::terminated().is_some() || ed.quit {
            return Ok(());
        }
        let mut frame = encode(&crate::ui::draw(ed));
        frame["buffers"] = buffers(ed);
        frame["typing"] = Json::Bool(typing(ed));
        frame["editing"] = Json::from(if crate::modeless::on(ed) { "standard" } else { "vim" });
        frame["theme"] = colors(ed);
        let text = frame.to_string();
        if text != last {
            let wait = FRAME_GAP.saturating_sub(sent.elapsed());
            if !wait.is_zero() {
                std::thread::sleep(wait);
            }
            out.write_all(text.as_bytes())?;
            out.write_all(b"\n")?;
            out.flush()?;
            sent = Instant::now();
            last = text;
        }
        let first = match input.recv_timeout(app::wait_time(ed)) {
            Ok(first) => Some(first),
            Err(RecvTimeoutError::Timeout) => None,
            Err(RecvTimeoutError::Disconnected) => Some(Input::End),
        };
        // Everything already waiting is handled before the next frame.
        for next in first.into_iter().chain(std::iter::from_fn(|| input.try_recv().ok())) {
            if !handle(ed, next, &mut anchor, themes, &mut last) {
                return Ok(());
            }
            if ed.quit {
                break;
            }
        }
        app::background(ed);
        no_terminal(ed);
    }
}

/// `--size 30x100`: rows x columns.
pub fn parse_size(text: &str) -> Option<(u16, u16)> {
    let (rows, cols) = text.split_once('x')?;
    Some(clamp_size(rows.parse().ok()?, cols.parse().ok()?))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn window_commands_exist() {
        let names = crate::commands::names();
        for name in COMMANDS.iter().chain(crate::actions::ACTIONS.iter().map(|(name, _)| name)) {
            assert!(names.contains(name), "{name}");
        }
    }

    #[test]
    fn keys_decode_like_terminal_keys() {
        let key = |text: &str| match decode(text) {
            Some(Input::Key(key)) => key,
            other => panic!("{text}: {other:?}"),
        };
        assert_eq!(key(r#"{"key":{"code":"a"}}"#), Key::char('a'));
        assert_eq!(key(r#"{"key":{"code":"S","ctrl":true}}"#), Key { shift: true, ..Key::ctrl('s') });
        assert_eq!(key(r#"{"key":{"code":"s","ctrl":true}}"#), Key::ctrl('s'));
        assert_eq!(key(r#"{"key":{"code":"Enter"}}"#), Key::plain(Code::Enter));
        assert_eq!(key(r#"{"key":{"code":"Tab","shift":true}}"#), Key { shift: true, ..Key::plain(Code::Tab) });
        assert_eq!(key(r#"{"key":{"code":"F5"}}"#), Key::plain(Code::F(5)));
        assert_eq!(key(r#"{"key":{"code":"é"}}"#), Key::char('é'));
        for bad in [
            r#"{"key":{"code":"F0"}}"#,
            r#"{"key":{"code":"Nope"}}"#,
            r#"{"key":{"code":"\u0007"}}"#,
            r#"{"key":{}}"#,
            r#"{"kitchen":1}"#,
            "not json",
            r#"{"open":{"path":"relative.txt"}}"#,
            r#"{"theme":"blue"}"#,
            r#"{"mouse":{"kind":"middle","x":1,"y":1}}"#,
        ] {
            assert_eq!(decode(bad), None, "{bad}");
        }
    }

    #[test]
    fn other_inputs_decode_and_sizes_are_clamped() {
        assert_eq!(decode(r#"{"resize":{"rows":2,"cols":99999}}"#), Some(Input::Resize(MIN_ROWS, MAX_COLS)));
        assert_eq!(
            decode(r#"{"mouse":{"kind":"scroll_up","x":3,"y":4}}"#),
            Some(Input::Mouse(MouseKind::ScrollUp, 3, 4))
        );
        assert_eq!(decode(r#"{"paste":"a\nb"}"#), Some(Input::Paste("a\nb".into())));
        assert_eq!(
            decode(r#"{"open":{"path":"/tmp/x.rs","line":3}}"#),
            Some(Input::Open(PathBuf::from("/tmp/x.rs"), Some(3)))
        );
        assert_eq!(decode(r#"{"theme":"light"}"#), Some(Input::Theme(true)));
        assert_eq!(parse_size("30x100"), Some((30, 100)));
        assert_eq!(parse_size("1x1"), Some((MIN_ROWS, MIN_COLS)));
        assert_eq!(parse_size("30"), None);
    }

    #[test]
    fn frames_are_runs_with_exact_columns() {
        let base = Style::default();
        let mut surface = Surface::new(8, 1, base);
        let red = Style { fg: Some(Color::Rgb(255, 0, 0)), bold: true, ..base };
        surface.text(0, 0, "ab", red, 8);
        surface.text(2, 0, "界c", base, 8);
        surface.cursor = Some((5, 0));
        surface.cursor_bar = true;
        let frame = encode(&surface);
        assert_eq!(frame["rows"], 1);
        assert_eq!(frame["cursor"], json!([0, 5, true]));
        let runs = frame["lines"][0].as_array().unwrap();
        assert_eq!(runs[0], json!([0, "ab", "#ff0000", "", 1]));
        // The wide char ends its run; the next run starts two columns later.
        assert_eq!(runs[1], json!([2, "界", "", "", 0]));
        assert_eq!(runs[2][0], 4);
        assert!(runs[2][1].as_str().unwrap().starts_with('c'));
        assert_eq!(color(Some(Color::Ansi(236))), "a236");
        let all =
            Style { reverse: true, dim: true, italic: true, underline: true, undercurl: true, crossed: true, ..red };
        assert_eq!(flags(&all), 127);
    }
}
