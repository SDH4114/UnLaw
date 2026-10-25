//! Background processes (run, git, ul, ul lm) streaming into output buffers,
//! jumping to `file:line` locations in their output, and terminal hand-off.

use std::collections::HashMap;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::Sender;
use std::thread;
use std::time::Instant;

use crate::document::display_path;
use crate::editor::{Editor, Event};
use crate::text::Pos;

/// A command that takes over the terminal (`:!cmd`, `:ul! game`, `:terminal`).
#[derive(Clone, Debug)]
pub struct Handoff {
    pub command: String,
    pub wait: bool,
}

#[derive(Debug)]
pub enum JobKind {
    Output,
    AiEdit { doc: usize, start: Pos, end: Pos, version: i32, original: String },
}

#[derive(Debug)]
pub struct Job {
    pub doc: usize,
    pub child: Child,
    pub title: String,
    pub started: Instant,
    pub kind: JobKind,
    pub output: String,
}

#[derive(Debug, Default)]
pub struct Jobs {
    pub running: HashMap<usize, Job>,
    next: usize,
}

impl Jobs {
    pub fn busy(&self) -> Option<&str> {
        self.running.values().next().map(|job| job.title.as_str())
    }

    pub fn kill_all(&mut self) {
        for job in self.running.values_mut() {
            let _ = job.child.kill();
        }
    }
}

/// Single-quotes for sh when needed.
pub fn quote(text: &str) -> String {
    if !text.is_empty() && text.chars().all(|c| c.is_alphanumeric() || "-_./:@%+=,".contains(c)) {
        return text.to_string();
    }
    format!("'{}'", text.replace('\'', "'\\''"))
}

pub fn shell() -> String {
    if Path::new("/bin/zsh").exists() {
        "/bin/zsh".into()
    } else {
        "/bin/sh".into()
    }
}

/// Strips ANSI escape sequences (colors, cursor moves) from process output.
pub fn strip_ansi(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut chars = text.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\u{1b}' {
            match chars.peek() {
                Some('[') => {
                    chars.next();
                    for next in chars.by_ref() {
                        if ('@'..='~').contains(&next) {
                            break;
                        }
                    }
                }
                Some(']') => {
                    // OSC: until BEL or ESC \
                    chars.next();
                    while let Some(next) = chars.next() {
                        if next == '\u{7}' {
                            break;
                        }
                        if next == '\u{1b}' {
                            chars.next();
                            break;
                        }
                    }
                }
                _ => {
                    chars.next();
                }
            }
        } else if c == '\r' {
            // Progress bars redraw with \r: keep only the last state.
            out.truncate(out.rfind('\n').map_or(0, |at| at + 1));
        } else if c != '\u{7}' {
            out.push(c);
        }
    }
    out
}

/// `path:12:5`, `path:12`, `path(12,5)` → (path, line, col), 1-based.
pub fn split_location(text: &str) -> (String, Option<usize>, Option<usize>) {
    let text = text.trim();
    if let Some(open) = text.rfind('(') {
        if text.ends_with(')') {
            let inner = &text[open + 1..text.len() - 1];
            let mut parts = inner.split(',');
            if let Some(Ok(line)) = parts.next().map(|part| part.trim().parse::<usize>()) {
                let col = parts.next().and_then(|part| part.trim().parse::<usize>().ok());
                return (text[..open].to_string(), Some(line), col);
            }
        }
    }
    let parts: Vec<&str> = text.split(':').collect();
    match parts.as_slice() {
        [path, line, col, ..] if line.parse::<usize>().is_ok() => {
            (path.to_string(), line.parse().ok(), col.parse::<usize>().ok())
        }
        [path, line] if line.parse::<usize>().is_ok() => (path.to_string(), line.parse().ok(), None),
        _ => (text.to_string(), None, None),
    }
}

/// A `file:line[:col]` in a line of compiler/test/grep output.
pub fn find_location(line: &str) -> Option<(String, usize, Option<usize>)> {
    let line = line.trim();
    // Python: File "x.py", line 12
    if let Some(start) = line.find("File \"") {
        let rest = &line[start + 6..];
        let end = rest.find('"')?;
        let path = &rest[..end];
        let number: String = rest[end..].split("line ").nth(1)?.chars().take_while(char::is_ascii_digit).collect();
        return Some((path.to_string(), number.parse().ok()?, None));
    }
    // Rust: --> src/main.rs:3:5 ; generic: path:line:col: message
    let candidate = line.trim_start_matches("-->").trim();
    for word in candidate.split_whitespace() {
        let word = word.trim_matches(|c: char| c == '\'' || c == '"' || c == '(' || c == ')' || c == ',');
        let (path, number, col) = split_location(word.trim_end_matches(':'));
        if let Some(number) = number {
            if !path.is_empty() && (path.contains('.') || path.contains('/')) && !path.contains("://") {
                return Some((path, number, col));
            }
        }
    }
    None
}

fn read_lines(reader: impl Read, job: usize, tx: Sender<Event>) {
    let mut reader = BufReader::new(reader);
    let mut buffer = Vec::new();
    loop {
        buffer.clear();
        match reader.read_until(b'\n', &mut buffer) {
            Ok(0) | Err(_) => break,
            Ok(_) => {
                let line = String::from_utf8_lossy(&buffer).trim_end_matches(['\n']).to_string();
                if tx.send(Event::JobOutput(job, strip_ansi(&line))).is_err() {
                    break;
                }
            }
        }
    }
}

/// Starts `command` with sh in `cwd`, streaming into `doc`; returns the job id.
pub fn spawn(
    ed: &mut Editor,
    title: &str,
    command: &str,
    stdin: Option<String>,
    doc: usize,
    kind: JobKind,
) -> Result<usize, String> {
    // A new run in the same buffer replaces the old one.
    let previous: Vec<usize> = ed.jobs.running.iter().filter(|(_, job)| job.doc == doc).map(|(id, _)| *id).collect();
    for id in previous {
        if let Some(mut job) = ed.jobs.running.remove(&id) {
            let _ = job.child.kill();
        }
    }
    let mut process = Command::new(shell());
    process
        .arg("-c")
        .arg(command)
        .current_dir(&ed.cwd)
        .stdin(if stdin.is_some() { Stdio::piped() } else { Stdio::null() })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env("NO_COLOR", "1")
        .env("CLICOLOR", "0")
        .env("TERM", "dumb");
    let mut child = process.spawn().map_err(|error| format!("{command}: {error}"))?;
    if let Some(input) = stdin {
        if let Some(mut pipe) = child.stdin.take() {
            thread::spawn(move || {
                let _ = pipe.write_all(input.as_bytes());
            });
        }
    }
    ed.jobs.next += 1;
    let id = ed.jobs.next;
    let stdout = child.stdout.take().expect("piped stdout");
    let stderr = child.stderr.take().expect("piped stderr");
    let tx = ed.tx.clone();
    let tx_err = ed.tx.clone();
    let err_reader = thread::spawn(move || read_lines(stderr, id, tx_err));
    thread::spawn(move || {
        read_lines(stdout, id, tx.clone());
        let _ = err_reader.join();
        let _ = tx.send(Event::JobDone(id, None));
    });
    ed.jobs
        .running
        .insert(id, Job { doc, child, title: title.to_string(), started: Instant::now(), kind, output: String::new() });
    Ok(id)
}

/// Runs a shell command into an output buffer shown in the panel.
pub fn run_shell(ed: &mut Editor, command: &str, title: &str) -> Result<(), String> {
    let doc = ed.output_doc(title);
    let place = display_path(&ed.cwd);
    let header = if place.is_empty() { format!("$ {command}") } else { format!("$ {command}    (in {place})") };
    if let Some(document) = ed.docs.get_mut(&doc) {
        document.set_content(&format!("{header}\n"));
    }
    spawn(ed, title, command, None, doc, JobKind::Output)?;
    ed.show_in_panel(doc);
    Ok(())
}

/// Runs the current file with its language's `run` command (saving first).
pub fn run_current(ed: &mut Editor, extra: &[String]) -> Result<(), String> {
    let doc = ed.doc();
    let path = doc.path.clone().ok_or("save the file first (:w name)")?;
    let lang = doc.lang.and_then(|index| ed.languages.get(index)).cloned();
    let first_line = doc.text.line(0).to_string();
    let mut command = match lang.as_ref().and_then(|lang| lang.run.clone()) {
        Some(run) => run,
        None if first_line.starts_with("#!") => "{file}".to_string(),
        None => {
            let name = lang.as_ref().map_or("this file".to_string(), |lang| lang.name.clone());
            return Err(format!("no run command for {name}: add run = \"...\" under [languages.{name}] in ule.toml"));
        }
    };
    if ed.doc().modified() {
        let id = ed.view().doc;
        let message = ed.save(id, None, false)?;
        ed.info(message);
    }
    let dir = path.parent().unwrap_or(Path::new("/")).to_path_buf();
    let stem = path.file_stem().map(|stem| stem.to_string_lossy().into_owned()).unwrap_or_default();
    let project = project_dir(&path, lang.as_ref().map(|lang| lang.roots.clone()).unwrap_or_default());
    let runs_in = project.clone().unwrap_or_else(|| ed.cwd.clone());
    // Paths inside the folder the command runs in are shown relative: `python3 app.py`.
    let shown = path.strip_prefix(&runs_in).map_or_else(|_| path.to_string_lossy().into_owned(), |relative| relative.to_string_lossy().into_owned());
    command = command
        .replace("{file}", &quote(&shown))
        .replace("{dir}", &quote(&dir.to_string_lossy()))
        .replace("{stem}", &quote(&stem));
    if !extra.is_empty() {
        command = format!("{command} {}", extra.join(" "));
    }
    // `cargo run` from anywhere inside the crate.
    let full = match &project {
        Some(dir) if dir != &ed.cwd => format!("cd {} && {command}", quote(&dir.to_string_lossy())),
        _ => command.clone(),
    };
    ed.last_run = Some(full.clone());
    run_shell(ed, &full, "[run]")
}

fn project_dir(path: &Path, roots: Vec<String>) -> Option<PathBuf> {
    if roots.is_empty() {
        return None;
    }
    let mut dir = path.parent()?;
    loop {
        if roots.iter().any(|root| dir.join(root).exists()) {
            return Some(dir.to_path_buf());
        }
        dir = dir.parent()?;
    }
}

/// Runs a command to completion and returns its output (for :r !cmd and :%!filter).
pub fn capture(command: &str, cwd: &Path, input: Option<&str>) -> Result<String, String> {
    let mut child = Command::new(shell())
        .arg("-c")
        .arg(command)
        .current_dir(cwd)
        .stdin(if input.is_some() { Stdio::piped() } else { Stdio::null() })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("{command}: {error}"))?;
    if let Some(input) = input {
        let mut pipe = child.stdin.take().expect("piped stdin");
        let input = input.to_string();
        thread::spawn(move || {
            let _ = pipe.write_all(input.as_bytes());
        });
    }
    let output = child.wait_with_output().map_err(|error| error.to_string())?;
    if !output.status.success() {
        let error = String::from_utf8_lossy(&output.stderr).trim().to_string();
        return Err(format!("{command}: exit {} {}", output.status.code().unwrap_or(-1), error));
    }
    Ok(strip_ansi(&String::from_utf8_lossy(&output.stdout)))
}

pub fn on_output(ed: &mut Editor, id: usize, line: String) {
    let Some(job) = ed.jobs.running.get_mut(&id) else {
        return;
    };
    job.output.push_str(&line);
    job.output.push('\n');
    if matches!(job.kind, JobKind::AiEdit { .. }) {
        return;
    }
    let doc = job.doc;
    let follow = ed
        .views
        .values()
        .filter(|view| view.doc == doc)
        .all(|view| view.cursor.line + 2 >= ed.docs.get(&doc).map_or(0, |doc| doc.text.len_lines()));
    if let Some(document) = ed.docs.get_mut(&doc) {
        let end = document.text.end();
        let text = if document.text.is_empty() { line } else { format!("\n{line}") };
        document.insert(end, &text, end);
        document.commit(end);
    }
    // Views at the bottom follow new output, like `tail -f`.
    if follow {
        let last = ed.docs.get(&doc).map_or(0, |doc| doc.text.last_line());
        let ids: Vec<usize> = ed.views.values().filter(|view| view.doc == doc).map(|view| view.id).collect();
        for view in ids {
            if let Some(view) = ed.views.get_mut(&view) {
                view.cursor = Pos::new(last, 0);
            }
            ed.scroll_to_cursor(view);
        }
    }
}

pub fn on_done(ed: &mut Editor, id: usize) {
    let Some(mut job) = ed.jobs.running.remove(&id) else {
        return;
    };
    let status = job.child.wait().ok();
    let code = status.and_then(|status| status.code());
    let seconds = job.started.elapsed().as_secs_f32();
    match job.kind {
        JobKind::Output => {
            let summary = match code {
                Some(0) => format!("[done in {seconds:.1}s]"),
                Some(code) => format!("[exit {code} after {seconds:.1}s]"),
                None => "[stopped]".to_string(),
            };
            if let Some(document) = ed.docs.get_mut(&job.doc) {
                let end = document.text.end();
                document.insert(end, &format!("\n{summary}"), end);
                document.commit(end);
            }
            let message = format!("{} {summary}", job.title);
            if code == Some(0) {
                ed.info(message);
            } else {
                ed.warn(message);
            }
        }
        JobKind::AiEdit { doc, start, end, version, original } => {
            let answer = crate::ul::extract_code(&job.output);
            let current = ed.docs.get(&doc).map(|doc| doc.version);
            if code != Some(0) || answer.trim().is_empty() {
                ed.error(format!("ul lm failed: {}", job.output.lines().last().unwrap_or("no output")));
                return;
            }
            if current != Some(version) {
                let output = ed.output_doc("[ai]");
                if let Some(document) = ed.docs.get_mut(&output) {
                    document.set_content(&answer);
                }
                ed.show_in_panel(output);
                ed.warn("the file changed while the model worked; the answer is in the panel");
                return;
            }
            let keep_newline = original.ends_with('\n') && !answer.ends_with('\n');
            let replacement = if keep_newline { answer.clone() } else { answer.trim_end_matches('\n').to_string() };
            let replacement = if original.ends_with('\n') && !replacement.ends_with('\n') && end.col == 0 {
                format!("{replacement}\n")
            } else {
                replacement
            };
            if let Some(document) = ed.docs.get_mut(&doc) {
                document.commit(start);
                document.replace(start, end, &replacement, start);
                document.commit(start);
            }
            ed.info(format!("AI edit applied ({seconds:.1}s) — u undoes it"));
        }
    }
}

/// `]q` / `[q` and Enter in output: the next `file:line` in the panel's output.
pub fn goto_location(ed: &mut Editor, forward: bool, count: usize) -> Result<(), String> {
    let panel = ed.panel.ok_or("no output yet")?;
    let doc = ed.views[&panel].doc;
    let mut line = ed.views[&panel].cursor.line;
    let document = &ed.docs[&doc];
    let total = document.text.len_lines();
    let mut found = None;
    let mut remaining = count;
    for _ in 0..total {
        line = if forward { (line + 1) % total } else { (line + total - 1) % total };
        if let Some(location) = find_location(document.text.line(line)) {
            remaining -= 1;
            if remaining == 0 {
                found = Some((line, location));
                break;
            }
        }
    }
    let (line, (path, number, col)) = found.ok_or("no file locations in the output")?;
    if let Some(view) = ed.views.get_mut(&panel) {
        view.cursor = Pos::new(line, 0);
    }
    ed.panel_visible = true;
    open_location(ed, &path, number, col)
}

/// Opens a location from output in the main area (not in the panel).
pub fn open_location(ed: &mut Editor, path: &str, line: usize, col: Option<usize>) -> Result<(), String> {
    let resolved = crate::commands::resolve_path(ed, path)
        .or_else(|| {
            let candidate = crate::picker::project_root(ed).join(path);
            candidate.exists().then_some(candidate)
        })
        .ok_or_else(|| format!("no file {path}"))?;
    if Some(ed.focus) == ed.panel {
        ed.focus = ed.layout.views()[0];
    }
    ed.push_jump();
    ed.open(&resolved)?;
    ed.set_cursor(Pos::new(line.saturating_sub(1), col.unwrap_or(1).saturating_sub(1)));
    ed.align_cursor('z');
    Ok(())
}

/// Enter on a line of output: opens the location on it.
pub fn open_under_cursor(ed: &mut Editor) -> bool {
    let line = ed.doc().text.line(ed.cursor().line).to_string();
    let Some((path, number, col)) = find_location(&line) else {
        return false;
    };
    if let Err(error) = open_location(ed, &path, number, col) {
        ed.error(error);
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn locations_in_output() {
        assert_eq!(find_location("  --> src/main.rs:3:5"), Some(("src/main.rs".into(), 3, Some(5))));
        assert_eq!(find_location("  File \"app.py\", line 12, in main"), Some(("app.py".into(), 12, None)));
        assert_eq!(find_location("tests/a.rs:40: assertion failed"), Some(("tests/a.rs".into(), 40, None)));
        assert_eq!(find_location("visit https://x.io:80/a"), None);
        assert_eq!(find_location("all good"), None);
        assert_eq!(split_location("a.c(10,2)"), ("a.c".into(), Some(10), Some(2)));
    }

    #[test]
    fn ansi_and_carriage_returns() {
        assert_eq!(strip_ansi("\u{1b}[31mred\u{1b}[0m ok"), "red ok");
        assert_eq!(strip_ansi("10%\r50%\r100%"), "100%");
        assert_eq!(quote("a b'c"), "'a b'\\''c'");
        assert_eq!(quote("src/main.rs"), "src/main.rs");
    }
}
