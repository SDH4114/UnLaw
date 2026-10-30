//! A terminal checklist: ↑/↓ (or j/k) move, Space toggles, `a` toggles all,
//! Enter confirms, Esc/q cancels. Used by `ul features choose` and
//! `ul commands search`.

use std::io::{self, IsTerminal, Write};

use crossterm::event::{self, Event, KeyCode, KeyEvent, KeyEventKind, KeyModifiers};
use crossterm::{cursor, execute, queue, style, terminal};

pub struct Entry {
    pub group: String,
    pub name: String,
    pub summary: String,
    pub on: bool,
    /// Shown with a fixed mark and never toggled (for example: already installed).
    pub locked: Option<&'static str>,
}

pub fn interactive() -> bool {
    io::stdin().is_terminal() && io::stdout().is_terminal()
}

/// Flip one unlocked entry.
pub fn flip(entries: &mut [Entry], index: usize) {
    if entries[index].locked.is_none() {
        entries[index].on = !entries[index].on;
    }
}

/// Run the checklist; `Ok(false)` when cancelled. `toggle` changes the
/// entries for Space (so callers can keep requirements consistent).
pub fn pick(title: &str, header: &[String], entries: &mut [Entry], toggle: &dyn Fn(&mut [Entry], usize)) -> io::Result<bool> {
    if entries.is_empty() {
        return Ok(true);
    }
    let mut stdout = io::stdout();
    terminal::enable_raw_mode()?;
    execute!(stdout, terminal::EnterAlternateScreen, cursor::Hide)?;
    let result = run(&mut stdout, title, header, entries, toggle);
    let _ = execute!(stdout, cursor::Show, terminal::LeaveAlternateScreen);
    let _ = terminal::disable_raw_mode();
    result
}

fn run(out: &mut io::Stdout, title: &str, header: &[String], entries: &mut [Entry], toggle: &dyn Fn(&mut [Entry], usize)) -> io::Result<bool> {
    let mut at = 0;
    loop {
        draw(out, title, header, entries, at)?;
        let Event::Key(KeyEvent { code, modifiers, kind, .. }) = event::read()? else { continue };
        if kind == KeyEventKind::Release {
            continue;
        }
        match code {
            KeyCode::Up | KeyCode::Char('k') => at = (at + entries.len() - 1) % entries.len(),
            KeyCode::Down | KeyCode::Char('j') => at = (at + 1) % entries.len(),
            KeyCode::Char(' ') => toggle(entries, at),
            KeyCode::Char('a') => {
                let all = !entries.iter().filter(|entry| entry.locked.is_none()).all(|entry| entry.on);
                entries.iter_mut().filter(|entry| entry.locked.is_none()).for_each(|entry| entry.on = all);
            }
            KeyCode::Enter => return Ok(true),
            KeyCode::Esc | KeyCode::Char('q') => return Ok(false),
            KeyCode::Char('c') if modifiers.contains(KeyModifiers::CONTROL) => return Ok(false),
            _ => {}
        }
    }
}

const HINT: &str = "↑/↓ move · Space toggle · a all/none · Enter confirm · Esc cancel";

/// The lines of the list and the line of the cursor; separate from drawing for tests.
pub fn lines(title: &str, header: &[String], entries: &[Entry], at: usize) -> (Vec<(String, bool)>, usize) {
    let mut lines: Vec<(String, bool)> = vec![(title.to_string(), false), (HINT.to_string(), false)];
    lines.extend(header.iter().map(|line| (line.clone(), false)));
    let width = entries.iter().map(|entry| entry.name.chars().count()).max().unwrap_or(0);
    let (mut cursor_line, mut group) = (0, "");
    for (index, entry) in entries.iter().enumerate() {
        if entry.group != group {
            group = &entry.group;
            lines.push((String::new(), false));
            lines.push((group.to_string(), false));
        }
        if index == at {
            cursor_line = lines.len();
        }
        let mark = match entry.locked {
            Some(mark) => mark.to_string(),
            None if entry.on => "[x]".into(),
            None => "[ ]".into(),
        };
        let pointer = if index == at { ">" } else { " " };
        lines.push((format!("{pointer} {mark} {:<width$}  {}", entry.name, entry.summary), index == at));
    }
    (lines, cursor_line)
}

fn draw(out: &mut io::Stdout, title: &str, header: &[String], entries: &[Entry], at: usize) -> io::Result<()> {
    let (lines, cursor_line) = lines(title, header, entries, at);
    let (width, height) = terminal::size()?;
    // Some terminals report 0x0.
    let width = if width == 0 { 100 } else { width as usize };
    let height = if height == 0 { 40 } else { (height as usize).max(5) };
    let top = cursor_line.saturating_sub(height - 2).min(lines.len().saturating_sub(height));
    queue!(out, terminal::Clear(terminal::ClearType::All))?;
    for (row, (text, current)) in lines.iter().skip(top).take(height).enumerate() {
        let text: String = text.chars().take(width).collect();
        queue!(out, cursor::MoveTo(0, row as u16))?;
        if *current {
            queue!(out, style::SetAttribute(style::Attribute::Reverse), style::Print(text), style::SetAttribute(style::Attribute::Reset))?;
        } else {
            queue!(out, style::Print(text))?;
        }
    }
    out.flush()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(group: &str, name: &str, locked: Option<&'static str>) -> Entry {
        Entry { group: group.into(), name: name.into(), summary: format!("about {name}"), on: false, locked }
    }

    #[test]
    fn lines_group_entries_and_mark_the_cursor() {
        let mut entries = vec![entry("A", "one", None), entry("A", "two", Some("[•]")), entry("B", "three", None)];
        entries[0].on = true;
        let (lines, at) = lines("Title", &["Core".into()], &entries, 2);
        let text: Vec<&str> = lines.iter().map(|(line, _)| line.as_str()).collect();
        assert_eq!(text[2..], ["Core", "", "A", "  [x] one    about one", "  [•] two    about two", "", "B", "> [ ] three  about three"]);
        assert_eq!(at, lines.len() - 1);
        assert!(lines[at].1);
    }

    #[test]
    fn locked_entries_never_flip() {
        let mut entries = vec![entry("A", "one", Some("[•]")), entry("A", "two", None)];
        flip(&mut entries, 0);
        flip(&mut entries, 1);
        assert!(!entries[0].on && entries[1].on);
    }
}
