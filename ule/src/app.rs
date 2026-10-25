//! The terminal application: setup and teardown, the event loop, mouse, suspend and hand-off.

use std::io::{self, Write};
use std::path::PathBuf;
use std::time::Duration;

use crossterm::event::{
    self, DisableBracketedPaste, DisableFocusChange, DisableMouseCapture, EnableBracketedPaste, EnableFocusChange,
    EnableMouseCapture, Event as TermEvent, KeyboardEnhancementFlags, MouseButton, MouseEventKind,
    PopKeyboardEnhancementFlags, PushKeyboardEnhancementFlags,
};
use crossterm::terminal::{self, EnterAlternateScreen, LeaveAlternateScreen};
use crossterm::{cursor, execute};

use crate::editor::{Editor, Event, Focus, Mode, VisualKind};
use crate::keys::Key;
use crate::render::Terminal;
use crate::text::Pos;

pub struct Launch {
    pub files: Vec<(PathBuf, Option<usize>, Option<usize>)>,
    pub stdin: Option<String>,
    pub readonly: bool,
    pub clean: bool,
}

fn true_color(ed: &Editor) -> bool {
    if let Some(forced) = ed.options.true_color {
        return forced;
    }
    let colorterm = std::env::var("COLORTERM").unwrap_or_default();
    if colorterm.contains("truecolor") || colorterm.contains("24bit") {
        return true;
    }
    let program = std::env::var("TERM_PROGRAM").unwrap_or_default();
    matches!(program.as_str(), "ghostty" | "iTerm.app" | "WezTerm" | "vscode" | "zed" | "WarpTerminal")
}

fn fancy_underline() -> bool {
    let program = std::env::var("TERM_PROGRAM").unwrap_or_default();
    let term = std::env::var("TERM").unwrap_or_default();
    matches!(program.as_str(), "ghostty" | "iTerm.app" | "WezTerm" | "kitty")
        || ["kitty", "ghostty", "wezterm", "foot", "alacritty"].iter().any(|name| term.contains(name))
}

struct Screen {
    enhanced: bool,
    mouse: bool,
}

impl Screen {
    fn enter(mouse: bool) -> io::Result<Screen> {
        terminal::enable_raw_mode()?;
        let mut out = io::stdout();
        execute!(out, EnterAlternateScreen, EnableBracketedPaste, EnableFocusChange)?;
        if mouse {
            execute!(out, EnableMouseCapture)?;
        }
        // Lets Esc, Ctrl-i and Tab, Ctrl-/ be told apart where the terminal supports it.
        let enhanced = matches!(terminal::supports_keyboard_enhancement(), Ok(true));
        if enhanced {
            execute!(out, PushKeyboardEnhancementFlags(KeyboardEnhancementFlags::DISAMBIGUATE_ESCAPE_CODES))?;
        }
        Ok(Screen { enhanced, mouse })
    }

    fn leave(&self) {
        let mut out = io::stdout();
        if self.enhanced {
            let _ = execute!(out, PopKeyboardEnhancementFlags);
        }
        if self.mouse {
            let _ = execute!(out, DisableMouseCapture);
        }
        let _ = execute!(
            out,
            DisableBracketedPaste,
            DisableFocusChange,
            cursor::SetCursorStyle::DefaultUserShape,
            cursor::Show,
            LeaveAlternateScreen
        );
        let _ = terminal::disable_raw_mode();
    }
}

fn restore_terminal_on_panic() {
    let default = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let mut out = io::stdout();
        let _ = execute!(
            out,
            PopKeyboardEnhancementFlags,
            DisableMouseCapture,
            DisableBracketedPaste,
            cursor::Show,
            LeaveAlternateScreen
        );
        let _ = terminal::disable_raw_mode();
        default(info);
    }));
}

/// When ule reads a file from stdin (`cmd | ule -`), keys must come from the terminal.
fn reattach_stdin() {
    // SAFETY: plain POSIX calls on file descriptors we own.
    unsafe {
        let tty = libc::open(c"/dev/tty".as_ptr(), libc::O_RDWR);
        if tty >= 0 {
            libc::dup2(tty, 0);
            libc::close(tty);
        }
    }
}

pub fn prepare(launch: &Launch) -> Editor {
    let names = crate::commands::names();
    let config = if launch.clean { crate::config::Config::default() } else { crate::config::Config::load(&names) };
    let mut ed = Editor::new(config);
    ed.persisted = crate::state::State::load(crate::config::state_dir().join("state.json"));
    if let Some(text) = &launch.stdin {
        let id = ed.scratch("[stdin]", crate::document::DocKind::Scratch);
        let doc = ed.docs.get_mut(&id).expect("document");
        doc.set_content(text);
        doc.lang = ed.languages.detect(None, text.lines().next().unwrap_or(""));
        ed.show_doc(id);
    }
    let mut first = true;
    for (path, line, col) in &launch.files {
        let opened = if path.is_dir() {
            if first {
                let _ = std::env::set_current_dir(path);
                ed.cwd = crate::document::absolute(path);
            }
            ed.open(path).map(|_| ())
        } else {
            ed.open(path).map(|_| ())
        };
        match opened {
            Ok(()) => {
                if let Some(line) = line {
                    ed.set_cursor(Pos::new(line.saturating_sub(1), col.unwrap_or(1).saturating_sub(1)));
                    ed.align_cursor('z');
                }
                if launch.readonly {
                    ed.doc_mut().readonly = true;
                }
            }
            Err(error) => ed.error(error),
        }
        first = false;
    }
    // Show the first file given (opening several leaves the last one in front).
    if launch.files.len() > 1 {
        if let Some(id) = launch.files.first().and_then(|(path, _, _)| ed.find_doc(path)) {
            ed.show_doc(id);
        }
    }
    ed
}

pub fn run(launch: Launch) -> io::Result<i32> {
    if launch.stdin.is_some() {
        reattach_stdin();
    }
    let mut ed = prepare(&launch);
    restore_terminal_on_panic();
    let mut screen = Screen::enter(ed.options.mouse)?;
    let (width, height) = terminal::size()?;
    ed.size = (width, height);
    let mut renderer = Terminal::new(true_color(&ed));
    renderer.fancy_underline = fancy_underline();
    // The ul command list for the picker and :ul completion.
    let tx = ed.tx.clone();
    std::thread::spawn(move || {
        let _ = tx.send(Event::UlCommands(crate::ul::commands()));
    });
    let mut out = io::BufWriter::with_capacity(1 << 16, io::stdout());
    let mut mouse_anchor: Option<(usize, Pos)> = None;
    loop {
        let surface = crate::ui::draw(&mut ed);
        renderer.draw(&surface, &mut out)?;
        let busy = ed.jobs.busy().is_some()
            || ed.picker.as_ref().is_some_and(|picker| picker.loading)
            || !ed.vim.pending.is_empty()
            || !ed.vim.insert_pending.is_empty()
            || ed.lsp.clients.iter().any(|client| !client.initialized || !client.progress.is_empty());
        let timeout = if busy { Duration::from_millis(80) } else { Duration::from_millis(500) };
        if event::poll(timeout)? {
            loop {
                let terminal_event = event::read()?;
                handle_terminal(&mut ed, terminal_event, &mut renderer, &mut mouse_anchor);
                if ed.quit || !event::poll(Duration::from_millis(0))? {
                    break;
                }
            }
        }
        // Background results, including any a synchronous LSP request put aside.
        for deferred in std::mem::take(&mut ed.lsp.deferred) {
            dispatch(&mut ed, deferred);
        }
        while let Ok(background) = ed.rx.try_recv() {
            dispatch(&mut ed, background);
        }
        crate::vim::tick(&mut ed);
        {
            let docs: Vec<&crate::document::Document> = ed.docs.values().collect();
            ed.lsp.sync_throttled(&docs);
        }
        if ed.suspend_requested {
            ed.suspend_requested = false;
            screen.leave();
            // SAFETY: raising a signal for our own process.
            unsafe {
                libc::raise(libc::SIGTSTP);
            }
            screen = Screen::enter(ed.options.mouse)?;
            renderer.invalidate();
            ed.check_disk_changes();
        }
        if let Some(handoff) = ed.handoff.take() {
            screen.leave();
            hand_off(&handoff);
            screen = Screen::enter(ed.options.mouse)?;
            renderer.invalidate();
            ed.check_disk_changes();
        }
        if ed.quit {
            break;
        }
    }
    ed.remember_positions();
    ed.persisted.save();
    ed.jobs.kill_all();
    ed.lsp.shutdown();
    screen.leave();
    Ok(0)
}

fn hand_off(handoff: &crate::jobs::Handoff) {
    let mut out = io::stdout();
    let _ = writeln!(out, "\r");
    let status = std::process::Command::new(crate::jobs::shell()).arg("-c").arg(&handoff.command).status();
    if handoff.wait {
        match status {
            Ok(status) if status.success() => {}
            Ok(status) => println!("\n[exit {}]", status.code().unwrap_or(-1)),
            Err(error) => println!("\n{error}"),
        }
        print!("\n[Enter: back to ule]");
        let _ = out.flush();
        let mut line = String::new();
        let _ = io::stdin().read_line(&mut line);
    }
}

pub fn dispatch(ed: &mut Editor, event: Event) {
    ed.needs_redraw = true;
    match event {
        Event::Lsp(client, message) => crate::lsp::handle(ed, client, message),
        Event::LspExit(client, reason) => crate::lsp::exited(ed, client, &reason),
        Event::JobOutput(job, line) => crate::jobs::on_output(ed, job, line),
        Event::JobDone(job, _) => crate::jobs::on_done(ed, job),
        Event::Files(..) | Event::Grep(..) => crate::picker::on_event(ed, event),
        Event::UlCommands(commands) => {
            if !commands.is_empty() {
                ed.ul_commands = commands;
            }
        }
        Event::Wake => {}
    }
}

fn handle_terminal(
    ed: &mut Editor,
    event: TermEvent,
    renderer: &mut Terminal,
    mouse_anchor: &mut Option<(usize, Pos)>,
) {
    match event {
        TermEvent::Key(key_event) => {
            if let Some(key) = Key::from_event(key_event) {
                // Output buffers: Enter opens the file:line on the cursor line.
                if key == Key::plain(crate::keys::Code::Enter)
                    && ed.mode == Mode::Normal
                    && ed.vim.pending.is_empty()
                    && ed.prompt.is_none()
                    && ed.picker.is_none()
                    && ed.focus_area == Focus::View
                    && ed.doc().kind == crate::document::DocKind::Output
                    && crate::jobs::open_under_cursor(ed)
                {
                    return;
                }
                crate::vim::handle_key(ed, key);
            }
        }
        TermEvent::Paste(text) => paste(ed, &text),
        TermEvent::Resize(width, height) => {
            ed.size = (width, height);
            renderer.invalidate();
        }
        TermEvent::FocusGained => ed.check_disk_changes(),
        TermEvent::FocusLost => {
            if ed.options.auto_save {
                ed.save_all_quietly();
            }
        }
        TermEvent::Mouse(mouse) => mouse_event(ed, mouse, mouse_anchor),
    }
}

fn paste(ed: &mut Editor, text: &str) {
    let text = text.replace("\r\n", "\n").replace('\r', "\n");
    if ed.prompt.is_some() {
        crate::ex::paste(ed, &text);
        return;
    }
    if ed.picker.is_some() {
        crate::picker::paste(ed, &text);
        return;
    }
    if let Mode::Visual(_) = ed.mode {
        crate::vim::exit_visual(ed);
    }
    let cursor = ed.cursor();
    let at = if ed.mode == Mode::Normal && ed.doc().text.line_len(cursor.line) > 0 {
        Pos::new(cursor.line, cursor.col + 1)
    } else {
        cursor
    };
    crate::edit::commit(ed);
    let end = ed.doc_mut().insert(at, &text, cursor);
    crate::edit::commit(ed);
    if ed.mode == Mode::Normal {
        ed.set_cursor(Pos::new(end.line, end.col.saturating_sub(1)));
    } else {
        ed.view_mut().cursor = end;
    }
    let focus = ed.focus;
    ed.scroll_to_cursor(focus);
}

/// The document position under a screen cell in a view, if any.
fn position_at(ed: &Editor, view_id: usize, x: u16, y: u16) -> Option<Pos> {
    let view = ed.views.get(&view_id)?;
    let doc = &ed.docs[&view.doc];
    let area = view.area;
    if y < area.y || y >= area.y + area.h {
        return None;
    }
    let tab = ed.tab_width(doc);
    let wrap = ed.wraps(doc);
    let mut row = area.y;
    let mut line = view.scroll;
    while line < doc.text.len_lines() {
        let text = doc.text.line(line);
        let starts = if wrap { crate::display::wrap_rows(text, area.w as usize, tab) } else { vec![0] };
        for (segment, start) in starts.iter().enumerate() {
            if row == y {
                let base = if wrap { crate::display::col_to_display(text, *start, tab) } else { view.hscroll };
                let target = base + x.saturating_sub(area.x) as usize;
                let mut col = crate::display::display_to_col(text, target, tab);
                if let Some(next) = starts.get(segment + 1) {
                    col = col.min(next.saturating_sub(1));
                }
                return Some(Pos::new(line, col));
            }
            row += 1;
        }
        line += 1;
    }
    Some(Pos::new(doc.text.last_line(), 0))
}

fn mouse_event(ed: &mut Editor, mouse: event::MouseEvent, anchor: &mut Option<(usize, Pos)>) {
    let (x, y) = (mouse.column, mouse.row);
    let (areas, explorer) = ed.view_areas();
    let in_view = areas.iter().find(|(_, rect)| rect.contains(x, y)).map(|(id, _)| *id);
    match mouse.kind {
        MouseEventKind::ScrollDown | MouseEventKind::ScrollUp => {
            let delta: isize = if mouse.kind == MouseEventKind::ScrollDown { 3 } else { -3 };
            if let Some(picker) = ed.picker.as_mut() {
                if !picker.matches.is_empty() {
                    let len = picker.matches.len() as isize;
                    picker.selected = (picker.selected as isize + delta.signum()).clamp(0, len - 1) as usize;
                }
                return;
            }
            if let Some(popup) = ed.popup.as_mut() {
                popup.scroll =
                    (popup.scroll as isize + delta).clamp(0, popup.lines.len().saturating_sub(1) as isize) as usize;
                return;
            }
            if explorer.is_some_and(|rect| rect.contains(x, y)) {
                if let Some(explorer) = ed.explorer.as_mut() {
                    let last = explorer.entries.len().saturating_sub(1) as isize;
                    explorer.selected = (explorer.selected as isize + delta).clamp(0, last) as usize;
                }
                return;
            }
            if let Some(id) = in_view {
                let previous = ed.focus;
                ed.focus = id;
                let last = ed.doc().text.last_line() as isize;
                let view = ed.view_mut();
                view.scroll = (view.scroll as isize + delta).clamp(0, last) as usize;
                let height = view.area.h as usize;
                let scroll = view.scroll;
                let mut cursor = view.cursor;
                let so = ed.options.scrolloff.min(height / 2);
                if cursor.line < scroll + so {
                    cursor.line = (scroll + so).min(last as usize);
                } else if cursor.line + so >= scroll + height {
                    cursor.line = (scroll + height).saturating_sub(so + 1);
                }
                if cursor != ed.cursor() {
                    ed.view_mut().cursor = cursor;
                    ed.clamp_cursor();
                }
                if previous != id && ed.mode != Mode::Normal {
                    ed.focus = previous;
                }
            }
        }
        MouseEventKind::Down(MouseButton::Left) => {
            ed.popup = None;
            if ed.picker.is_some() {
                return;
            }
            if y == 0 && ed.bufferline_visible() {
                bufferline_click(ed, x);
                return;
            }
            if let Some(rect) = explorer.filter(|rect| rect.contains(x, y)) {
                ed.focus_area = Focus::Explorer;
                if let Some(explorer) = ed.explorer.as_mut() {
                    let rows = rect.h.saturating_sub(1) as usize;
                    let offset = explorer.selected.saturating_sub(rows.saturating_sub(1));
                    let index = offset + y.saturating_sub(rect.y + 1) as usize;
                    if y > rect.y && index < explorer.entries.len() {
                        explorer.selected = index;
                        crate::explorer::key(ed, Key::plain(crate::keys::Code::Enter));
                    }
                }
                return;
            }
            let Some(id) = in_view else {
                return;
            };
            ed.focus_area = Focus::View;
            if ed.focus != id {
                if matches!(ed.mode, Mode::Visual(_)) {
                    crate::vim::exit_visual(ed);
                }
                ed.focus = id;
            }
            if let Some(pos) = position_at(ed, id, x, y) {
                if matches!(ed.mode, Mode::Visual(_)) {
                    crate::vim::exit_visual(ed);
                }
                ed.push_jump();
                ed.view_mut().cursor = ed.doc().text.clamp(pos);
                ed.view_mut().want_col = None;
                ed.clamp_cursor();
                *anchor = Some((id, ed.cursor()));
            }
        }
        MouseEventKind::Drag(MouseButton::Left) => {
            let Some((id, start)) = *anchor else {
                return;
            };
            if ed.focus != id {
                return;
            }
            if let Some(pos) = position_at(ed, id, x, y) {
                if !matches!(ed.mode, Mode::Visual(_)) {
                    if ed.mode == Mode::Insert {
                        crate::vim::leave_insert(ed);
                    }
                    ed.mode = Mode::Visual(VisualKind::Char);
                    ed.anchor = start;
                }
                let pos = ed.doc().text.clamp(pos);
                ed.view_mut().cursor = pos;
                let focus = ed.focus;
                ed.scroll_to_cursor(focus);
            }
        }
        MouseEventKind::Up(MouseButton::Left) => *anchor = None,
        _ => {}
    }
}

fn bufferline_click(ed: &mut Editor, x: u16) {
    let mut column = 0u16;
    for (index, id) in ed.buffers.clone().into_iter().enumerate() {
        let doc = &ed.docs[&id];
        let modified = if doc.modified() { " ●" } else { "" };
        let width = crate::display::str_width(&format!(" {} {}{modified} ", index + 1, doc.file_name())) as u16;
        if x >= column && x < column + width {
            ed.show_doc(id);
            return;
        }
        column += width;
    }
}
