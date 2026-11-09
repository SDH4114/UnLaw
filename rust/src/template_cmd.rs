//! `ul template ...` and launching a template (`ul <name>`): opens apps with
//! `open -a`, then hands placement, Ghostty tabs/splits, browser windows and
//! focus mode to `desktop.js` in one `osascript` run.

use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::io::{self, BufRead, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use serde_json::{json, Value as JsonValue};

use crate::checklist::{self, Entry};
use crate::config::{self, Config};
use crate::help::print_if_requested;
use crate::util::atomic_write;
use crate::workspace::{self, printable, tilde, Frame, Kind, Pane, Tab, Template, Window, BROWSER, TERMINAL_APP};

const SCRIPT: &str = include_str!("desktop.js");
/// Seconds to wait for each window before placing it.
const WINDOW_WAIT: u64 = 10;

// ---------------------------------------------------------------- osascript

fn osascript(request: &JsonValue) -> Result<JsonValue, String> {
    let mut child = Command::new("osascript")
        .args(["-l", "JavaScript", "-e", SCRIPT])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("could not run osascript: {error}"))?;
    // The request (links, commands) goes through stdin, never argv.
    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(request.to_string().as_bytes()).map_err(|error| format!("osascript: {error}"))?;
    }
    let output = child.wait_with_output().map_err(|error| format!("osascript: {error}"))?;
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if !output.status.success() {
        if stderr.contains("-1743") {
            return Err(
                "macOS refused automation. Allow your terminal in System Settings > Privacy & Security > Automation.".into()
            );
        }
        return Err(format!("osascript failed: {}", if stderr.is_empty() { "no details" } else { &stderr }));
    }
    serde_json::from_slice(&output.stdout).map_err(|error| format!("unexpected answer from osascript: {error}"))
}

const ACCESSIBILITY_HINT: &str =
    "Allow your terminal in System Settings > Privacy & Security > Accessibility, then run it again.";

// ---------------------------------------------------------------- state

/// Ghostty and browser windows a template opened, so a second run reuses them.
fn state_file(config: Option<&Config>) -> PathBuf {
    let root = match config {
        Some(config) => config.storage_root(),
        None => config::configured_storage_root(),
    };
    root.join("runtime").join("templates.json")
}

/// template name -> window index -> `{id, pid, spec}`.
type State = serde_json::Map<String, JsonValue>;

fn read_state(path: &Path) -> State {
    fs::read_to_string(path).ok().and_then(|text| serde_json::from_str(&text).ok()).unwrap_or_default()
}

fn write_state(path: &Path, state: &State) {
    if let Ok(text) = serde_json::to_string_pretty(state) {
        if let Err(error) = atomic_write(path, &format!("{text}\n"), ".templates.") {
            eprintln!("unlaw: could not remember the template's windows: {error}");
        }
    }
}

/// What a window was opened from: a remembered window is reused only while the
/// template still asks for the same thing (an edited template opens a new one).
fn spec_of(window: &JsonValue) -> String {
    let spec = json!([window["kind"], window["app"], window["tabs"], window["urls"]]);
    crate::util::sha256_hex(spec.to_string())[..16].to_string()
}

// ---------------------------------------------------------------- plan

pub struct LaunchOptions {
    pub focus: Option<bool>,
    pub dry_run: bool,
}

pub fn parse_launch_flags(args: &[String]) -> Option<LaunchOptions> {
    let mut options = LaunchOptions { focus: None, dry_run: false };
    for arg in args {
        match arg.as_str() {
            "--focus" => options.focus = Some(true),
            "--no-focus" => options.focus = Some(false),
            "--dry-run" => options.dry_run = true,
            _ => return None,
        }
    }
    Some(options)
}

pub const LAUNCH_FLAGS: &str = "[--focus|--no-focus] [--dry-run]";

#[derive(Debug)]
struct Step {
    index: usize,
    window: Window,
    app: String,
    /// What `open -a` gets: an absolute path or a URL.
    target: Option<String>,
    panes: Vec<Vec<PanePlan>>,
}

/// A pane's folder, command and split direction.
type PanePlan = (PathBuf, Option<String>, Option<String>);

fn existing(path: PathBuf, what: &str) -> Result<PathBuf, String> {
    if path.exists() {
        Ok(path)
    } else {
        Err(format!("{what} does not exist: {}", path.display()))
    }
}

fn plan(template: &Template, config: Option<&Config>) -> Result<Vec<Step>, String> {
    if !template.path.is_dir() {
        return Err(format!("Saved project directory does not exist: {}", template.path.display()));
    }
    let mut steps = Vec::new();
    for (index, window) in template.windows.iter().enumerate() {
        let mut app = window.app.clone();
        if template.legacy && app == "Zed" {
            app = config.map(|config| config.string("apps.editor")).filter(|editor| !editor.is_empty()).unwrap_or(app);
        }
        let target = match &window.open {
            None => None,
            Some(open) if workspace::is_url(open) => Some(open.clone()),
            Some(open) => Some(
                existing(workspace::resolve_path(open, &template.path), &format!("window {} ({app}): open", index + 1))?
                    .to_string_lossy()
                    .into_owned(),
            ),
        };
        let mut panes = Vec::new();
        for (number, tab) in window.tabs.iter().enumerate() {
            let mut list = Vec::new();
            for pane in &tab.panes {
                let dir = match &pane.dir {
                    Some(dir) => existing(workspace::resolve_path(dir, &template.path), &format!("window {}, tab {}: folder", index + 1, number + 1))?,
                    None => template.path.clone(),
                };
                if !dir.is_dir() {
                    return Err(format!("window {}, tab {}: not a folder: {}", index + 1, number + 1, dir.display()));
                }
                list.push((dir, pane.run.clone(), pane.split.clone()));
            }
            panes.push(list);
        }
        steps.push(Step { index, window: window.clone(), app, target, panes });
    }
    Ok(steps)
}

fn frame_json(frame: &Option<Frame>) -> JsonValue {
    match frame {
        Some(frame) => json!([frame.x, frame.y, frame.w, frame.h]),
        None => JsonValue::Null,
    }
}

// ---------------------------------------------------------------- describe

fn short_url(url: &str) -> &str {
    let rest = url.split_once("://").map_or(url, |(_, rest)| rest);
    rest.trim_end_matches('/')
}

fn pane_text(pane: &Pane) -> String {
    let what = pane.run.clone().unwrap_or_else(|| "shell".into());
    match &pane.split {
        Some(split) => format!("{what} ({split})"),
        None => what,
    }
}

fn window_details(window: &Window) -> String {
    match window.kind() {
        Kind::Terminal => window
            .tabs
            .iter()
            .enumerate()
            .map(|(number, tab)| {
                let folder = tab.panes[0].dir.as_deref().map(|dir| format!(" in {dir}")).unwrap_or_default();
                format!("tab {}{folder}: {}", number + 1, tab.panes.iter().map(pane_text).collect::<Vec<_>>().join(" | "))
            })
            .collect::<Vec<_>>()
            .join("; "),
        Kind::Browser if window.urls.is_empty() => "default browser".into(),
        Kind::Browser => window.urls.iter().map(|url| short_url(url)).collect::<Vec<_>>().join(", "),
        Kind::App => window
            .open
            .as_deref()
            .map(|open| if Path::new(open).is_absolute() { format!("opens {}", tilde(Path::new(open))) } else { format!("opens {open}") })
            .unwrap_or_default(),
    }
}

fn place_text(window: &Window) -> String {
    let frame = window.frame.as_ref().map_or_else(|| "as is".to_string(), Frame::describe);
    if window.screen == 1 {
        frame
    } else {
        format!("{frame}, screen {}", window.screen)
    }
}

pub fn describe(template: &Template) -> String {
    printable_lines(&describe_raw(template))
}

/// Control characters of every line made visible (newlines kept).
fn printable_lines(text: &str) -> String {
    text.split_inclusive('\n').map(|line| match line.strip_suffix('\n') {
        Some(body) => format!("{}\n", printable(body)),
        None => printable(line),
    }).collect()
}

fn describe_raw(template: &Template) -> String {
    let mut text = format!(
        "{}  {}  focus {}{}\n",
        template.name,
        tilde(&template.path),
        if template.focus { "on" } else { "off" },
        if template.legacy { "  (old format: re-save with `ul template save`)" } else { "" }
    );
    if template.windows.is_empty() {
        text.push_str("  (no windows: only changes the folder)\n");
    }
    let width = template.windows.iter().map(|window| window.app.chars().count()).max().unwrap_or(0);
    let place = template.windows.iter().map(|window| place_text(window).chars().count()).max().unwrap_or(0);
    for (index, window) in template.windows.iter().enumerate() {
        let line = format!("  {}  {:<width$}  {:<place$}  {}", index + 1, window.app, place_text(window), window_details(window));
        text.push_str(line.trim_end());
        text.push('\n');
    }
    text
}

// ---------------------------------------------------------------- launch

fn open_app(app: &str, target: Option<&str>) -> Result<(), String> {
    let mut command = Command::new("open");
    command.args(["-a", app]);
    if let Some(target) = target {
        command.arg(target);
    }
    match command.status() {
        Ok(status) if status.success() => Ok(()),
        Ok(status) => Err(format!("open -a failed (exit {})", status.code().unwrap_or(1))),
        Err(error) => Err(format!("could not run open: {error}")),
    }
}

pub fn launch(template: &Template, config: Option<&Config>, options: &LaunchOptions) -> i32 {
    let steps = match plan(template, config) {
        Ok(steps) => steps,
        Err(error) => {
            eprintln!("unlaw: {error}");
            return 1;
        }
    };
    let focus = options.focus.unwrap_or(template.focus);
    if options.dry_run {
        print!("{}", describe(&Template { focus, ..template.clone() }));
        return 0;
    }
    let mut outcomes: Vec<(bool, Vec<String>)> = steps.iter().map(|_| (true, Vec::new())).collect();
    for step in &steps {
        if step.window.kind() == Kind::App {
            if let Err(error) = open_app(&step.app, step.target.as_deref()) {
                outcomes[step.index] = (false, vec![error]);
            }
        }
    }
    let needs_script = focus || steps.iter().any(|step| step.window.frame.is_some() || step.window.kind() != Kind::App);
    let state_path = state_file(config);
    let mut state = read_state(&state_path);
    if needs_script {
        let remembered = state.get(&template.name).cloned().unwrap_or_default();
        let mut windows: Vec<JsonValue> = steps
            .iter()
            .filter(|step| outcomes[step.index].0)
            .map(|step| {
                let kind = match step.window.kind() {
                    Kind::App => "app",
                    Kind::Terminal => "terminal",
                    Kind::Browser => "browser",
                };
                let tabs: Vec<JsonValue> = step
                    .panes
                    .iter()
                    .map(|panes| {
                        JsonValue::Array(
                            panes.iter().map(|(dir, run, split)| json!({"dir": dir.to_string_lossy(), "run": run, "split": split})).collect(),
                        )
                    })
                    .collect();
                json!({
                    "index": step.index,
                    "kind": kind,
                    "app": step.app,
                    "open": step.target,
                    "frame": frame_json(&step.window.frame),
                    "screen": step.window.screen,
                    "urls": step.window.urls,
                    "tabs": tabs,
                })
            })
            .collect();
        for window in &mut windows {
            let saved = &remembered[window["index"].to_string().as_str()];
            if saved["spec"].as_str() == Some(spec_of(window).as_str()) {
                window["state"] = json!({"id": saved["id"], "pid": saved["pid"]});
            }
        }
        let specs: BTreeMap<String, String> = windows.iter().map(|window| (window["index"].to_string(), spec_of(window))).collect();
        // A window the script never answers for counts as failed, not as done.
        for window in &windows {
            if let Some(index) = window["index"].as_u64() {
                outcomes[index as usize] = (false, vec!["no answer from osascript".into()]);
            }
        }
        let request = json!({"mode": "apply", "plan": {"focus": focus, "wait": WINDOW_WAIT, "windows": windows}});
        match osascript(&request) {
            Ok(answer) => {
                let trusted = answer["trusted"].as_bool().unwrap_or(true);
                let mut ids = serde_json::Map::new();
                for result in answer["results"].as_array().into_iter().flatten() {
                    let Some(index) = result["index"].as_u64().map(|index| index as usize).filter(|index| *index < outcomes.len()) else {
                        continue;
                    };
                    let notes: Vec<String> = result["notes"].as_array().into_iter().flatten().filter_map(|note| note.as_str().map(str::to_string)).collect();
                    outcomes[index] = (result["ok"].as_bool().unwrap_or(false), notes);
                    let saved = &result["state"];
                    if let (Some(id), Some(spec)) = (saved["id"].as_str(), specs.get(&index.to_string())) {
                        ids.insert(index.to_string(), json!({"id": id, "pid": saved["pid"], "spec": spec}));
                    }
                }
                state.insert(template.name.clone(), JsonValue::Object(ids));
                write_state(&state_path, &state);
                if !trusted && steps.iter().any(|step| step.window.frame.is_some()) {
                    eprintln!("unlaw: windows were opened but not placed. {ACCESSIBILITY_HINT}");
                }
            }
            Err(error) => {
                // Only windows handed to the script are affected; plain apps it was
                // asked about (focus mode) did open.
                for window in &windows {
                    let Some(index) = window["index"].as_u64().map(|index| index as usize) else { continue };
                    let step = &steps[index];
                    let scripted = step.window.kind() != Kind::App || step.window.frame.is_some();
                    outcomes[index] = if scripted { (false, vec![error.clone()]) } else { (true, Vec::new()) };
                }
                if focus && steps.iter().all(|step| step.window.kind() == Kind::App && step.window.frame.is_none()) {
                    eprintln!("unlaw: focus mode failed: {error}");
                    return 1;
                }
            }
        }
    }
    let width = steps.iter().map(|step| step.app.chars().count()).max().unwrap_or(0);
    for step in &steps {
        let (ok, notes) = &outcomes[step.index];
        let line = format!("{} {:<width$}  {}", if *ok { "✓" } else { "!" }, step.app, notes.join("; "));
        if *ok {
            println!("{}", line.trim_end());
        } else {
            eprintln!("{}", line.trim_end());
        }
    }
    i32::from(outcomes.iter().any(|(ok, _)| !ok))
}

// ---------------------------------------------------------------- save

struct Candidate {
    window: Window,
    title: String,
    /// The browser's tabs could not be read (not scriptable): ask for links.
    ask_urls: bool,
    on: bool,
}

/// A window frame in global points -> its display (1-based) and fractions of that display's usable area.
fn relative_frame(frame: [f64; 4], screens: &[([f64; 4], [f64; 4])]) -> (u32, Frame) {
    let (cx, cy) = (frame[0] + frame[2] / 2.0, frame[1] + frame[3] / 2.0);
    let inside = |r: &[f64; 4]| cx >= r[0] && cx < r[0] + r[2] && cy >= r[1] && cy < r[1] + r[3];
    let index = screens.iter().position(|(full, _)| inside(full)).unwrap_or(0);
    let Some((_, visible)) = screens.get(index) else {
        return (1, Frame { x: 0.0, y: 0.0, w: 1.0, h: 1.0 });
    };
    let [vx, vy, vw, vh] = *visible;
    let clamp = |value: f64| (value.clamp(0.0, 1.0) * 1000.0).round() / 1000.0;
    // A window parked off the display keeps at least 1% of it, so the frame stays valid.
    let x = clamp((frame[0] - vx) / vw).min(0.99);
    let y = clamp((frame[1] - vy) / vh).min(0.99);
    let w = clamp(frame[2] / vw).min(1.0 - x).max(0.01);
    let h = clamp(frame[3] / vh).min(1.0 - y).max(0.01);
    (index as u32 + 1, Frame { x, y, w, h })
}

fn rect(value: &JsonValue) -> Option<[f64; 4]> {
    let list: Vec<f64> = value.as_array()?.iter().filter_map(JsonValue::as_f64).collect();
    list.try_into().ok()
}

/// Snapshot text a template may keep: no control characters (the file would be refused).
fn clean(text: &str) -> bool {
    !text.is_empty() && !text.chars().any(char::is_control)
}

fn candidates(snapshot: &JsonValue, cwd: &Path) -> Vec<Candidate> {
    let screens: Vec<([f64; 4], [f64; 4])> = snapshot["screens"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|screen| Some((rect(&screen["frame"])?, rect(&screen["visible"])?)))
        .collect();
    let mut found = Vec::new();
    for app in snapshot["apps"].as_array().into_iter().flatten() {
        let name = app["name"].as_str().unwrap_or_default();
        if name.is_empty() || name.chars().any(char::is_control) {
            continue;
        }
        let browser = app["browser"].as_bool().unwrap_or(false);
        let terminal = app["bundle"].as_str() == Some("com.mitchellh.ghostty");
        for raw in app["windows"].as_array().into_iter().flatten() {
            let Some(frame) = rect(&raw["frame"]) else { continue };
            let (screen, frame) = relative_frame(frame, &screens);
            let mut window = Window { frame: Some(frame), screen, ..Window::app(name) };
            let mut ask_urls = false;
            let mut on = false;
            if browser {
                window.app = BROWSER.into();
                match raw["urls"].as_array() {
                    Some(urls) => window.urls = urls.iter().filter_map(JsonValue::as_str).filter(|url| clean(url) && (url.starts_with("http://") || url.starts_with("https://"))).map(str::to_string).collect(),
                    None => ask_urls = true,
                }
            } else if terminal && raw["tabs"].is_array() {
                window.app = TERMINAL_APP.into();
                for tab in raw["tabs"].as_array().into_iter().flatten() {
                    let dirs: Vec<&str> =
                        tab.as_array().into_iter().flatten().filter_map(JsonValue::as_str).filter(|dir| clean(dir)).collect();
                    if dirs.is_empty() {
                        continue;
                    }
                    on |= dirs.iter().any(|dir| Path::new(dir) == cwd);
                    let panes = dirs
                        .iter()
                        .enumerate()
                        .map(|(at, dir)| Pane { dir: Some(tilde(Path::new(dir))), run: None, split: (at > 0).then(|| "right".to_string()) })
                        .collect();
                    window.tabs.push(Tab { panes });
                }
            } else if let Some(document) = raw["document"].as_str().filter(|document| clean(document)) {
                window.open = Some(document.to_string());
            }
            found.push(Candidate { window, title: raw["title"].as_str().unwrap_or_default().to_string(), ask_urls, on });
        }
    }
    found
}

struct Cancelled;

fn prompt(text: &str) -> Result<String, Cancelled> {
    print!("{text}");
    let _ = io::stdout().flush();
    let mut line = String::new();
    match io::stdin().lock().read_line(&mut line) {
        Ok(0) | Err(_) => Err(Cancelled),
        Ok(_) => Ok(line.trim().to_string()),
    }
}

fn yes_no(text: &str, default: bool) -> Result<bool, Cancelled> {
    loop {
        match prompt(text)?.to_lowercase().as_str() {
            "" => return Ok(default),
            "y" | "yes" | "д" | "да" => return Ok(true),
            "n" | "no" | "н" | "нет" => return Ok(false),
            _ => eprintln!("Please answer y or n."),
        }
    }
}

/// Numbers chosen on a line: `1 3`, `1,3`, `all`, `none`, or Enter for the defaults.
fn pick_numbers(text: &str, count: usize, defaults: &[bool]) -> Result<Vec<bool>, String> {
    let text = text.trim().to_lowercase();
    match text.as_str() {
        "" => return Ok(defaults.to_vec()),
        "all" | "a" => return Ok(vec![true; count]),
        "none" | "-" => return Ok(vec![false; count]),
        _ => {}
    }
    let mut chosen = vec![false; count];
    for word in text.split(|c: char| c == ',' || c.is_whitespace()).filter(|word| !word.is_empty()) {
        match word.parse::<usize>() {
            Ok(number) if (1..=count).contains(&number) => chosen[number - 1] = true,
            _ => return Err(format!("Not a number from 1 to {count}: {word}")),
        }
    }
    Ok(chosen)
}

/// A checklist on a terminal, numbered lines otherwise (scripts and tests).
fn choose(title: &str, items: &[(String, String, String)], defaults: &[bool], line_prompt: &str) -> Result<Vec<bool>, Cancelled> {
    if items.is_empty() {
        return Ok(Vec::new());
    }
    if checklist::interactive() {
        let mut entries: Vec<Entry> = items
            .iter()
            .zip(defaults)
            .map(|((group, name, summary), on)| Entry { group: group.clone(), name: name.clone(), summary: summary.clone(), on: *on, locked: None })
            .collect();
        return match checklist::pick(title, &[], &mut entries, &checklist::flip) {
            Ok(true) => Ok(entries.iter().map(|entry| entry.on).collect()),
            _ => Err(Cancelled),
        };
    }
    println!("{title}");
    let group_width = items.iter().map(|(group, _, _)| group.chars().count()).max().unwrap_or(0);
    let name_width = items.iter().map(|(_, name, _)| name.chars().count()).max().unwrap_or(0);
    for (index, ((group, name, summary), on)) in items.iter().zip(defaults).enumerate() {
        let label = if group.is_empty() { format!("{name:<name_width$}") } else { format!("{group:<group_width$}  {name:<name_width$}") };
        let line = format!("  {:>2}. [{}] {label}  {summary}", index + 1, if *on { "x" } else { " " });
        println!("{}", line.trim_end());
    }
    loop {
        let answer = prompt(line_prompt)?;
        match pick_numbers(&answer, items.len(), defaults) {
            Ok(chosen) => return Ok(chosen),
            Err(error) => eprintln!("{error}"),
        }
    }
}

fn clip(text: &str, width: usize) -> String {
    if text.chars().count() <= width {
        text.to_string()
    } else {
        format!("{}…", text.chars().take(width - 1).collect::<String>())
    }
}

fn ask_run(label: &str) -> Result<Option<String>, Cancelled> {
    loop {
        let answer = prompt(&format!("  {label} runs [Enter = shell, c = claude, x = codex, or a command] > "))?;
        match answer.as_str() {
            "" => return Ok(None),
            "c" => return Ok(Some("claude".into())),
            "x" => return Ok(Some("codex".into())),
            command if !clean(command) => eprintln!("One line without control characters, please."),
            command => return Ok(Some(command.to_string())),
        }
    }
}

fn ask_links() -> Result<Vec<String>, Cancelled> {
    loop {
        let answer = prompt("  Links for the browser window (space separated, Enter = none) > ")?;
        let links: Vec<String> = answer.split_whitespace().map(str::to_string).collect();
        if let Some(bad) = links.iter().find(|link| !clean(link) || (!link.starts_with("https://") && !link.starts_with("http://"))) {
            eprintln!("Not an http(s) link: {}", printable(bad));
            continue;
        }
        return Ok(links);
    }
}

/// A template file named like a system, built-in or installed command or an
/// alias (copied in by hand) must never take `ul <name>` over from it.
pub fn shadows_command(name: &str) -> bool {
    crate::help::is_system(name)
        || crate::builtin::is_builtin(name)
        || crate::commands::resolve(name).is_some()
        || config::load().ok().is_some_and(|config| config.alias(name).is_some())
}

fn name_taken(name: &str, config: &Config) -> bool {
    crate::help::is_system(name)
        || crate::builtin::is_builtin(name)
        || crate::commands::resolve(name).is_some()
        || config.alias(name).is_some()
}

fn save(args: &[String]) -> i32 {
    let mut force = false;
    let mut name = None;
    for arg in args {
        match arg.as_str() {
            "--force" | "-f" => force = true,
            other if name.is_none() && !other.starts_with('-') => name = Some(other.to_string()),
            _ => return usage("Usage: ul template save [name] [--force]"),
        }
    }
    let cancelled = || {
        eprintln!("unlaw template: Cancelled.");
        1
    };
    let fail = |error: &dyn std::fmt::Display| {
        eprintln!("unlaw template: {error}");
        2
    };
    let name = match name {
        Some(name) => name,
        None => match prompt("Name of template > ") {
            Ok(name) => name,
            Err(Cancelled) => return cancelled(),
        },
    };
    if let Err(error) = workspace::validate_name(&name) {
        return fail(&error);
    }
    let config = match config::load() {
        Ok(config) => config,
        Err(error) => return fail(&error),
    };
    if name_taken(&name, &config) {
        eprintln!("unlaw template: Name already in use: {name}");
        return 1;
    }
    let manifest = match workspace::manifest_path(&name) {
        Ok(path) => path,
        Err(error) => return fail(&error),
    };
    if manifest.exists() && !force {
        match yes_no(&format!("Template '{name}' exists. Replace it? [y/N] > "), false) {
            Ok(true) => {}
            Ok(false) | Err(Cancelled) => return cancelled(),
        }
    }
    let cwd = match env::current_dir() {
        Ok(cwd) => cwd,
        Err(error) => return fail(&error),
    };
    let snapshot = match osascript(&json!({"mode": "snapshot"})) {
        Ok(snapshot) => snapshot,
        Err(error) => {
            eprintln!("unlaw template: could not read the windows: {error}");
            return 1;
        }
    };
    if snapshot["trusted"].as_bool() != Some(true) {
        eprintln!("unlaw template: reading windows needs the Accessibility permission. {ACCESSIBILITY_HINT}");
        return 1;
    }
    match build_from_snapshot(&name, &snapshot, &cwd) {
        Ok(Some(template)) => {
            let text = workspace::render(&template);
            if let Err(error) = atomic_write(&manifest, &text, &format!(".{name}.")) {
                return fail(&error);
            }
            println!("Saved template '{name}': {}", tilde(&manifest));
            println!("Run it with: ul {name}   Change it: ul template edit {name}");
            0
        }
        Ok(None) | Err(Cancelled) => cancelled(),
    }
}

fn build_from_snapshot(name: &str, snapshot: &JsonValue, cwd: &Path) -> Result<Option<Template>, Cancelled> {
    let mut found = candidates(snapshot, cwd);
    if found.is_empty() {
        println!("No open windows were found; the template will only change the folder.");
    }
    let items: Vec<(String, String, String)> = found
        .iter()
        .map(|candidate| {
            let detail = window_details(&candidate.window);
            let detail = if detail.is_empty() { candidate.title.clone() } else { detail };
            (printable(&candidate.window.app), place_text(&candidate.window), clip(&printable(&detail), 60))
        })
        .collect();
    let defaults: Vec<bool> = found.iter().map(|candidate| candidate.on).collect();
    let chosen = choose(
        "Windows for the template (only the ones you mark are saved)",
        &items,
        &defaults,
        "Include which windows? Numbers (1 3), all, none; Enter = the marked ones > ",
    )?;
    let mut windows = Vec::new();
    for (mut candidate, keep) in found.drain(..).zip(chosen) {
        if !keep {
            continue;
        }
        let window = &mut candidate.window;
        match window.kind() {
            Kind::Browser if candidate.ask_urls => {
                println!("The default browser does not share its tabs.");
                window.urls = ask_links()?;
            }
            Kind::Browser if !window.urls.is_empty() => {
                let items: Vec<(String, String, String)> =
                    window.urls.iter().map(|url| (String::new(), clip(&printable(short_url(url)), 70), String::new())).collect();
                let all = vec![true; items.len()];
                let keep = choose("Sites to open", &items, &all, "Which sites? Numbers, all, none; Enter = all > ")?;
                window.urls = window.urls.iter().zip(keep).filter(|(_, keep)| *keep).map(|(url, _)| url.clone()).collect();
            }
            Kind::Terminal => {
                println!("Ghostty window ({}):", place_text(window));
                for (number, tab) in window.tabs.iter_mut().enumerate() {
                    for (at, pane) in tab.panes.iter_mut().enumerate() {
                        let folder = printable(pane.dir.as_deref().unwrap_or_default());
                        pane.run = ask_run(&format!("tab {}, pane {} ({folder})", number + 1, at + 1))?;
                    }
                }
            }
            _ => {}
        }
        windows.push(candidate.window);
    }
    let default_path = tilde(cwd);
    let path = loop {
        let answer = prompt(&format!("Project folder (ul {name} goes there) [{default_path}] > "))?;
        let path = if answer.is_empty() { cwd.to_path_buf() } else { workspace::resolve_path(&answer, cwd) };
        if path.is_dir() {
            break path;
        }
        eprintln!("Not a folder: {}", path.display());
    };
    let focus = yes_no("Hide other apps when it starts (focus mode)? [y/N] > ", false)?;
    let template = Template { name: name.into(), path, focus, windows, legacy: false };
    println!();
    print!("{}", describe(&template));
    if yes_no("Save? [Y/n] > ", true)? {
        Ok(Some(template))
    } else {
        Ok(None)
    }
}

// ---------------------------------------------------------------- edit, show, rm, list

fn edit(args: &[String]) -> i32 {
    let [name] = args else {
        return usage("Usage: ul template edit <name>");
    };
    let fail = |error: &dyn std::fmt::Display| {
        eprintln!("unlaw template: {error}");
        2
    };
    if let Err(error) = workspace::validate_name(name) {
        return fail(&error);
    }
    let config = match config::load() {
        Ok(config) => config,
        Err(error) => return fail(&error),
    };
    let manifest = match workspace::manifest_path(name) {
        Ok(path) => path,
        Err(error) => return fail(&error),
    };
    if !manifest.exists() {
        if name_taken(name, &config) {
            eprintln!("unlaw template: Name already in use: {name}");
            return 1;
        }
        let cwd = match env::current_dir() {
            Ok(cwd) => cwd,
            Err(error) => return fail(&error),
        };
        if let Err(error) = crate::util::create_new_atomic(&manifest, &workspace::starter(name, &cwd), &format!(".{name}.")) {
            return fail(&error);
        }
        println!("Created {} from a starter; change it and save.", tilde(&manifest));
    }
    let (words, _) = crate::editor::resolve(Some(&config));
    let Some((program, rest)) = words.split_first() else {
        return fail(&"No editor configured (core.editor)");
    };
    match Command::new(program).args(rest).arg(&manifest).status() {
        Ok(status) if status.success() => {}
        Ok(status) => return status.code().unwrap_or(1),
        Err(error) => return fail(&format!("could not run {program}: {error}")),
    }
    match workspace::load(name) {
        Ok(template) => {
            print!("{}", describe(&template));
            0
        }
        Err(error) => {
            eprintln!("unlaw template: {error}");
            eprintln!("Fix it with: ul template edit {name}");
            1
        }
    }
}

fn show(args: &[String]) -> i32 {
    let [name] = args else {
        return usage("Usage: ul template show <name>");
    };
    match workspace::load(name) {
        Ok(template) => {
            print!("{}", describe(&template));
            0
        }
        Err(error) => {
            eprintln!("unlaw template: {error}");
            1
        }
    }
}

fn remove(args: &[String]) -> i32 {
    let (mut name, mut yes) = (None, false);
    for arg in args {
        match arg.as_str() {
            "--yes" | "-y" => yes = true,
            other if name.is_none() && !other.starts_with('-') => name = Some(other),
            _ => return usage("Usage: ul template rm <name> [--yes]"),
        }
    }
    let Some(name) = name else {
        return usage("Usage: ul template rm <name> [--yes]");
    };
    if !workspace::exists(name) {
        eprintln!("unlaw template: No template named {name}");
        return 1;
    }
    let Ok(manifest) = workspace::manifest_path(name) else {
        return 1;
    };
    if !yes {
        match yes_no(&format!("Delete template '{name}' ({})? [y/N] > ", tilde(&manifest)), false) {
            Ok(true) => {}
            _ => {
                eprintln!("unlaw template: Cancelled.");
                return 1;
            }
        }
    }
    match fs::remove_file(&manifest) {
        Ok(()) => {
            let config = config::load().ok();
            let state_path = state_file(config.as_ref());
            let mut state = read_state(&state_path);
            if state.remove(name).is_some() {
                write_state(&state_path, &state);
            }
            println!("Deleted template '{name}'.");
            0
        }
        Err(error) => {
            eprintln!("unlaw template: {error}");
            1
        }
    }
}

pub fn list(args: &[String]) -> i32 {
    if !args.is_empty() {
        return usage("Usage: ul templates");
    }
    match workspace::discover() {
        Ok(templates) => {
            let width = templates.keys().map(|name| name.chars().count()).max().unwrap_or(0);
            for (name, template) in &templates {
                let apps: Vec<&str> = template.windows.iter().map(|window| window.app.as_str()).collect();
                let line = format!("{name:<width$}  {}  {}", tilde(&template.path), apps.join(", "));
                println!("{}", printable(line.trim_end()));
            }
            0
        }
        Err(error) => {
            eprintln!("unlaw templates: {error}");
            2
        }
    }
}

fn usage(text: &str) -> i32 {
    eprintln!("{text}");
    2
}

pub fn run(args: &[String]) -> i32 {
    if print_if_requested("template", args) {
        return 0;
    }
    let rest = args.get(1..).unwrap_or(&[]);
    match args.first().map(String::as_str) {
        Some("save") => save(rest),
        Some("edit") => edit(rest),
        Some("show") => show(rest),
        Some("rm" | "remove") => remove(rest),
        Some("list") => list(rest),
        _ => usage("Usage: ul template save|edit|show|rm|list ..."),
    }
}

/// `ul create template [name]` (the old entry point) is `ul template save`.
pub fn create(args: &[String]) -> i32 {
    if args.len() > 1 {
        return usage("Usage: ul create template [name]");
    }
    save(args)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn numbers_pick_entries() {
        let defaults = [true, false, false];
        assert_eq!(pick_numbers("", 3, &defaults).unwrap(), defaults);
        assert_eq!(pick_numbers("1, 3", 3, &defaults).unwrap(), [true, false, true]);
        assert_eq!(pick_numbers("all", 3, &defaults).unwrap(), [true; 3]);
        assert_eq!(pick_numbers("none", 3, &defaults).unwrap(), [false; 3]);
        assert!(pick_numbers("4", 3, &defaults).is_err());
        assert!(pick_numbers("x", 3, &defaults).is_err());
    }

    #[test]
    fn frames_become_fractions_of_their_display() {
        let screens = [([0.0, 0.0, 1800.0, 1169.0], [0.0, 39.0, 1725.0, 1130.0]), ([-2560.0, -711.0, 2560.0, 1440.0], [-2560.0, -711.0, 2560.0, 1440.0])];
        let (screen, frame) = relative_frame([0.0, 39.0, 862.5, 1130.0], &screens);
        assert_eq!((screen, frame.preset_name()), (1, Some("left")));
        let (screen, frame) = relative_frame([-2560.0, -711.0, 2560.0, 1440.0], &screens);
        assert_eq!((screen, frame.preset_name()), (2, Some("full")));
        // A window hanging off the edge is clamped onto the display.
        let (_, frame) = relative_frame([1500.0, 39.0, 600.0, 2000.0], &screens);
        assert!(frame.x + frame.w <= 1.0 && frame.y + frame.h <= 1.0);
    }

    #[test]
    fn missing_folders_stop_the_plan_before_anything_opens() {
        let gone = Template { name: "gone".into(), path: "/nonexistent/project".into(), focus: false, windows: vec![], legacy: false };
        assert!(plan(&gone, None).unwrap_err().contains("does not exist"));
        let pane = Pane { dir: Some("/nonexistent/pane".into()), run: None, split: None };
        let terminal = Window { tabs: vec![Tab { panes: vec![pane] }], ..Window::app(TERMINAL_APP) };
        let template = Template { name: "t".into(), path: "/tmp".into(), focus: false, windows: vec![terminal], legacy: false };
        assert!(plan(&template, None).unwrap_err().contains("tab 1: folder does not exist"));
        let opener = Window { open: Some("/nonexistent/file".into()), ..Window::app("Zed") };
        let template = Template { windows: vec![opener], ..template };
        assert!(plan(&template, None).unwrap_err().contains("window 1 (Zed): open does not exist"));
    }

    #[test]
    fn describe_lists_every_window() {
        let template = workspace::parse("demo", "version = 2\npath = \"/tmp\"\n[[window]]\napp = \"Ghostty\"\nframe = \"right\"\n[[window.tab]]\npanes = [{ run = \"claude\" }, { split = \"down\" }]\n[[window]]\napp = \"browser\"\nurls = [\"https://example.com/\"]\nscreen = 2\n").unwrap();
        let text = describe(&template);
        assert!(text.contains("Ghostty  right"), "{text}");
        assert!(text.contains("tab 1: claude | shell (down)"), "{text}");
        assert!(text.contains("as is, screen 2  example.com"), "{text}");
    }

    #[test]
    fn launch_flags() {
        let flags = |items: &[&str]| parse_launch_flags(&items.iter().map(|s| s.to_string()).collect::<Vec<_>>());
        assert_eq!(flags(&["--focus"]).unwrap().focus, Some(true));
        assert!(flags(&["--no-focus", "--dry-run"]).is_some_and(|o| o.focus == Some(false) && o.dry_run));
        assert!(flags(&["extra"]).is_none());
    }
}
