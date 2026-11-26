//! Unlaw's main window: one window in the Dock with the app's parts in a
//! sidebar (Commands, System, Clipboard, Games, Desk). Everything still runs
//! through `ul`: the System part polls `ul sys --json`, the Clipboard part
//! `ul clip ... --json`, a game is `ul game --stream` with its frames relayed
//! to the page, and the desk page is a second web view laid over the content.

use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::process::CommandExt;
use std::process::{ChildStdin, Command, Stdio};
use std::sync::Mutex;

use tao::platform::macos::WindowBuilderExtMacOS;

use super::*;

const HOME_SIZE: (f64, f64) = (1120.0, 740.0);
const SYS_EVERY: Duration = Duration::from_secs(2);
const CLIP_EVERY: Duration = Duration::from_secs(2);
const TEMPLATES_EVERY: Duration = Duration::from_secs(4);
/// Page name of the desk shown inside the main window (for `on_page_left`).
pub(super) const HOME_DESK: &str = "desk@home";
/// The parts of `ul desk` that are their own items in the sidebar; one desk
/// server and one web view serve them all, the page switches its view.
const DESK_PARTS: &[&str] = &["board", "today", "canvas", "studio"];

/// "desk" (the command's own section, and older settings) is its Board.
fn canonical(section: &str) -> &str {
    match section {
        "desk" => "board",
        other => other,
    }
}

/// The served desk address, embedded: no tabs, starting at `view`.
fn embed_url(url: &str, view: &str) -> String {
    let (base, _) = url.split_once('#').unwrap_or((url, ""));
    let joiner = if base.contains('?') { '&' } else { '?' };
    format!("{base}{joiner}embed=1#{view}")
}
const GAMES: &[&str] = &["tetris", "snake", "minesweeper", "invaders", "chomp", "dash", "pingpong", "chess"];
const LEVELS: &[&str] = &["easy", "normal", "hard"];
const CLIP_ACTIONS: &[&str] = &["copy", "rm", "clear", "on", "off", "pause", "resume"];

/// A running `ul game --stream`.
pub(super) struct GameRun {
    id: u64,
    stdin: Option<ChildStdin>,
    child: Child,
}

/// The desk page inside the main window and the `ul desk` serving it.
pub(super) struct DeskView {
    webview: WebView,
    child: Child,
    url: String,
    opened: Option<Instant>,
}

/// The main window state that lives in `App`.
#[derive(Default)]
pub(super) struct HomeState {
    pub section: String,
    /// Bumped to stop the pollers of the part shown before.
    poll: Arc<AtomicU64>,
    game: Option<GameRun>,
    next_game: u64,
    desk: Option<DeskView>,
    desk_opening: bool,
    /// Where the page's content area is, in points of the window.
    desk_area: Option<(f64, f64, f64, f64)>,
    /// look.dock as it was when the app started (a change needs a restart).
    pub dock: bool,
}

impl HomeState {
    pub(super) fn new(dock: bool) -> HomeState {
        HomeState { dock, ..HomeState::default() }
    }
}

pub(super) fn home_window(target: &EventLoopWindowTarget<UserEvent>, proxy: &EventLoopProxy<UserEvent>) -> Glass {
    let window = WindowBuilder::new()
        .with_title("Unlaw")
        .with_inner_size(LogicalSize::new(HOME_SIZE.0, HOME_SIZE.1))
        .with_min_inner_size(LogicalSize::new(780.0, 520.0))
        .with_visible(false)
        .with_transparent(true)
        .with_titlebar_transparent(true)
        .with_title_hidden(true)
        .with_fullsize_content_view(true)
        .build(target)
        .expect("a window");
    let ipc = proxy.clone();
    let webview = WebViewBuilder::new()
        .with_transparent(true)
        .with_custom_protocol("ulapp".into(), |_, request| match request.uri().path().strip_prefix("/clip/") {
            Some(name) => serve_clip_picture(name),
            None => serve_asset(request),
        })
        .with_url("ulapp://localhost/home.html")
        .with_ipc_handler(move |request: Request<String>| {
            if request.uri().scheme_str() == Some("ulapp") {
                let _ = ipc.send_event(UserEvent::Ipc(View::Home, request.into_body()));
            }
        })
        .with_navigation_handler(|url| url.starts_with("ulapp://"))
        .with_new_window_req_handler(|_, _| wry::NewWindowResponse::Deny)
        .build(&window)
        .expect("a web view");
    #[cfg(target_os = "macos")]
    {
        use window_vibrancy::{apply_vibrancy, NSVisualEffectMaterial, NSVisualEffectState};
        if let Err(error) = apply_vibrancy(
            &window,
            NSVisualEffectMaterial::Sidebar,
            Some(NSVisualEffectState::FollowsWindowActiveState),
            None,
        ) {
            eprintln!("ul-app: no glass for the main window: {error}");
        }
    }
    Glass { window, webview, ready: false, pending: Vec::new() }
}

/// clip.max_files from config.toml (15 when unset), for the Settings page.
fn clip_max_files() -> i64 {
    let text = fs::read_to_string(settings::config_dir().join("config.toml")).unwrap_or_default();
    text.parse::<toml_edit::DocumentMut>()
        .ok()
        .and_then(|document| document.get("clip")?.get("max_files")?.as_integer())
        .unwrap_or(15)
}

/// A saved picture of `ul clip` (`<storage.root>/clip/files/<16 hex><suffix>`)
/// for the Clipboard part's thumbnails; nothing else of the disk is served.
fn clip_picture_kind(name: &str) -> Option<&'static str> {
    let (stem, suffix) = name.split_once('.')?;
    if stem.len() != 16 || !stem.bytes().all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()) {
        return None;
    }
    Some(match suffix {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "webp" => "image/webp",
        "heic" => "image/heic",
        "tif" | "tiff" => "image/tiff",
        "bmp" => "image/bmp",
        _ => return None,
    })
}

fn serve_clip_picture(name: &str) -> Response<Cow<'static, [u8]>> {
    let empty = || {
        Response::builder()
            .status(404)
            .body(Cow::Borrowed(&b""[..]))
            .unwrap_or_else(|_| Response::new(Cow::Borrowed(&b""[..])))
    };
    let Some(kind) = clip_picture_kind(name) else { return empty() };
    let path = storage_root().join("clip").join("files").join(name);
    match fs::symlink_metadata(&path) {
        Ok(meta) if meta.is_file() && meta.len() <= 64 * 1024 * 1024 => match fs::read(&path) {
            Ok(bytes) => Response::builder()
                .header(CONTENT_TYPE, kind)
                .body(Cow::Owned(bytes))
                .unwrap_or_else(|_| Response::new(Cow::Borrowed(&b""[..]))),
            Err(_) => empty(),
        },
        _ => empty(),
    }
}

/// `<storage.root>` from config.toml (default `data` in the config folder).
fn storage_root() -> PathBuf {
    let config = settings::config_dir();
    let text = fs::read_to_string(config.join("config.toml")).unwrap_or_default();
    let root = text
        .parse::<toml_edit::DocumentMut>()
        .ok()
        .and_then(|document| document.get("storage")?.get("root")?.as_str().map(str::to_string))
        .unwrap_or_else(|| "data".into());
    let path = match root.strip_prefix("~/") {
        Some(rest) => settings::home().join(rest),
        None => PathBuf::from(&root),
    };
    if path.is_absolute() {
        path
    } else {
        config.join(path)
    }
}

/// Best scores from `<storage.root>/runtime/arcade.toml` (shared with `ul game`).
pub(super) fn records() -> Json {
    let text = fs::read_to_string(storage_root().join("runtime").join("arcade.toml")).unwrap_or_default();
    let mut found = serde_json::Map::new();
    if let Ok(document) = text.parse::<toml_edit::DocumentMut>() {
        for game in GAMES {
            let Some(table) = document.get(game).and_then(|item| item.as_table_like()) else { continue };
            let mut levels = serde_json::Map::new();
            for level in LEVELS {
                if let Some(value) = table.get(level).and_then(|item| item.as_integer()) {
                    levels.insert((*level).into(), json!(value));
                }
            }
            found.insert((*game).into(), Json::Object(levels));
        }
    }
    Json::Object(found)
}

/// One input line for the game, rebuilt from a whitelist (the page never
/// writes to the game's stdin directly).
pub(super) fn game_event(event: &Json) -> Option<Json> {
    let key =
        |value: &Json| value.as_str().filter(|key| !key.is_empty() && key.chars().count() <= 12).map(str::to_string);
    let cell = |value: &Json| -> Option<(i64, i64)> {
        let (y, x) = (value.get("y")?.as_i64()?, value.get("x")?.as_i64()?);
        ((0..400).contains(&y) && (0..400).contains(&x)).then_some((y, x))
    };
    if let Some(name) = event.get("key").and_then(key) {
        return Some(json!({"key": name}));
    }
    if let Some(name) = event.get("release").and_then(key) {
        return Some(json!({"release": name}));
    }
    if let Some(click) = event.get("click") {
        let (y, x) = cell(click)?;
        let button = click.get("button").and_then(Json::as_str).filter(|b| ["left", "middle", "right"].contains(b))?;
        return Some(json!({"click": {"y": y, "x": x, "button": button}}));
    }
    if let Some(hover) = event.get("hover") {
        let (y, x) = cell(hover)?;
        return Some(json!({"hover": {"y": y, "x": x}}));
    }
    None
}

/// `ul clip` arguments for a page request; None for anything else.
pub(super) fn clip_args(action: &str, id: Option<&str>) -> Option<Vec<String>> {
    if !CLIP_ACTIONS.contains(&action) {
        return None;
    }
    let mut argv = vec!["clip".to_string(), action.to_string()];
    match action {
        "copy" | "rm" => {
            let id = id.filter(|id| (6..=64).contains(&id.len()) && id.chars().all(|c| c.is_ascii_hexdigit()))?;
            argv.push(format!("@{id}"));
        }
        "clear" => argv.push("--yes".into()),
        _ => {}
    }
    Some(argv)
}

fn read_sys(ul: &Path) -> Json {
    let outcome = runner::run(ul, &["sys".into(), "--json".into()], Duration::from_secs(20));
    match serde_json::from_str::<Json>(&outcome.stdout) {
        Ok(data) if outcome.ok() => json!({"type": "sys", "data": data}),
        _ => json!({"type": "sys", "error": outcome.summary(3)}),
    }
}

fn read_templates(ul: &Path) -> Json {
    let outcome = runner::run(ul, &["template".into(), "list".into(), "--json".into()], LIST_TIMEOUT);
    match serde_json::from_str::<Json>(&outcome.stdout) {
        Ok(items) if outcome.ok() && items.is_array() => json!({"type": "templates", "items": items}),
        _ => json!({"type": "templates", "error": outcome.summary(3)}),
    }
}

/// A template name the page may send back: what `ul template` accepts as a file name.
pub(super) fn template_name(name: &str) -> Option<&str> {
    let ok = (1..=64).contains(&name.len())
        && !name.starts_with(['-', '.'])
        && name.chars().all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.'));
    ok.then_some(name)
}

fn read_clip(ul: &Path) -> Json {
    let list = runner::run(ul, &["clip".into(), "list".into(), "500".into(), "--json".into()], LIST_TIMEOUT);
    let status = runner::run(ul, &["clip".into(), "status".into(), "--json".into()], LIST_TIMEOUT);
    let items = serde_json::from_str::<Json>(&list.stdout).ok().filter(|_| list.ok()).filter(Json::is_array);
    let status = serde_json::from_str::<Json>(&status.stdout).ok().filter(|_| status.ok());
    match items {
        Some(items) => json!({"type": "clip", "items": items, "status": status}),
        None => json!({"type": "clip", "error": list.summary(3), "status": status}),
    }
}

impl App {
    pub(super) fn show_home(&mut self, section: Option<&str>) {
        self.palette.window.set_visible(false);
        self.panel.window.set_visible(false);
        if let Some(section) = section.map(canonical) {
            self.send(View::Home, json!({"type": "section", "section": section}));
            self.set_section(section);
        } else if self.home_state.section.is_empty() {
            self.set_section("commands");
        } else {
            let section = self.home_state.section.clone();
            self.set_section(&section);
        }
        #[cfg(target_os = "macos")]
        if self.home_state.dock {
            platform::set_in_dock(true);
        }
        self.home.window.set_visible(true);
        self.home.window.set_minimized(false);
        self.home.window.set_focus();
        self.place_desk();
    }

    /// The window closed (it only hides): pollers and the game stop; the desk
    /// server keeps running so the board is there at once next time.
    pub(super) fn hide_home(&mut self) {
        self.home.window.set_visible(false);
        // Closed, Unlaw leaves the Dock and stays in the menu bar; ⌘Q quits it.
        #[cfg(target_os = "macos")]
        if self.home_state.dock {
            platform::set_in_dock(false);
        }
        self.home_state.poll.fetch_add(1, Ordering::SeqCst);
        // A shortcut being recorded when the window closed must not leave the hotkeys off.
        if self.registered.is_empty() {
            self.register_hotkeys();
        }
        self.stop_game(None);
        self.place_desk();
    }

    fn set_section(&mut self, section: &str) {
        let section = canonical(section);
        let known = spec::SECTIONS.contains(&section) || section == "commands" || section == "settings";
        let section = if known { section } else { "commands" };
        self.home_state.section = section.to_string();
        self.home_state.poll.fetch_add(1, Ordering::SeqCst);
        match section {
            "system" => self.poll(read_sys, SYS_EVERY),
            "clipboard" => self.poll(read_clip, CLIP_EVERY),
            "templates" => self.poll(read_templates, TEMPLATES_EVERY),
            part if DESK_PARTS.contains(&part) => {
                if let Some(desk) = &self.home_state.desk {
                    let _ = desk
                        .webview
                        .evaluate_script(&format!("window.deskEmbedView && window.deskEmbedView({part:?})"));
                }
                self.ensure_desk();
            }
            _ => {}
        }
        self.place_desk();
    }

    /// Runs `read` now and then every `every` until the part changes.
    fn poll(&self, read: fn(&Path) -> Json, every: Duration) {
        let Some(ul) = self.ul.clone() else {
            self.send_later(json!({"type": "sys", "error": "ul was not found"}));
            return;
        };
        let generation = self.home_state.poll.clone();
        let mine = generation.load(Ordering::SeqCst);
        let proxy = self.proxy.clone();
        thread::spawn(move || loop {
            let message = read(&ul);
            if generation.load(Ordering::SeqCst) != mine || proxy.send_event(UserEvent::Home(message)).is_err() {
                return;
            }
            let until = Instant::now() + every;
            while Instant::now() < until {
                thread::sleep(Duration::from_millis(100));
                if generation.load(Ordering::SeqCst) != mine {
                    return;
                }
            }
        });
    }

    /// The Settings page: the form as app.toml has it now, its warnings, and the
    /// last save's error (the page then shows the stored values again).
    fn send_settings(&mut self, error: Option<String>) {
        let (current, warnings) = match settings_text() {
            Ok(text) => settings::parse(&text),
            Err(error) => (settings::parse("").0, vec![error]),
        };
        let form = settings::Form::of(&current);
        let hotkeys: Vec<Json> = form
            .hotkeys
            .iter()
            .map(|(keys, command, action)| json!({"keys": keys, "command": command, "action": action}))
            .collect();
        self.send(
            View::Home,
            json!({"type": "settings", "settings": {
                "palette": form.palette, "hotkeys": hotkeys, "menubar": form.menubar, "sys": form.sys,
                "show_status": form.show_status, "theme": form.theme, "dock": form.dock,
            }, "running_dock": self.home_state.dock, "warnings": warnings, "error": error,
               "path": settings::path().display().to_string(), "clip_files": clip_max_files(),
               "sys_metrics": settings::SYS_METRICS.iter().map(|(id, label, _)| json!({"id": id, "label": label})).collect::<Vec<_>>()}),
        );
    }

    fn send_later(&self, message: Json) {
        let _ = self.proxy.send_event(UserEvent::Home(message));
    }

    /// Page requests of the main window; true when `op` was one of them.
    pub(super) fn on_home_op(&mut self, op: &str, message: &Json) -> bool {
        match op {
            "section" => {
                let section = message["section"].as_str().unwrap_or("commands").to_string();
                self.set_section(&section);
            }
            "desk-area" => {
                let number = |key: &str| message[key].as_f64().filter(|value| value.is_finite());
                if let (Some(x), Some(y), Some(width), Some(height)) =
                    (number("x"), number("y"), number("width"), number("height"))
                {
                    self.home_state.desk_area = Some((x, y, width.max(0.0), height.max(0.0)));
                    self.place_desk();
                }
            }
            "clip" if message["action"] == "reveal" => {
                // Show a saved file in Finder: only a name of the clip files folder.
                let name = message["file"].as_str().unwrap_or("");
                let stem_ok = name.split_once('.').map_or(name, |(stem, _)| stem);
                let ok = stem_ok.len() == 16
                    && stem_ok.bytes().all(|byte| byte.is_ascii_hexdigit())
                    && !name.contains('/')
                    && !name.starts_with('.');
                if ok {
                    let path = storage_root().join("clip").join("files").join(name);
                    thread::spawn(move || {
                        let _ = Command::new("/usr/bin/open").arg("-R").arg(path).stdin(Stdio::null()).status();
                    });
                }
            }
            "clip" => {
                let action = message["action"].as_str().unwrap_or("");
                let Some(argv) = clip_args(action, message["id"].as_str()) else { return true };
                let Some(ul) = self.ul.clone() else { return true };
                let proxy = self.proxy.clone();
                let on_off = action == "on" || action == "off";
                thread::spawn(move || {
                    let outcome = runner::run(&ul, &argv, Duration::from_secs(30));
                    if !outcome.ok() {
                        platform::notify("Clipboard", &outcome.summary(3));
                    }
                    if on_off {
                        // The watcher needs a moment to write its first state.
                        thread::sleep(Duration::from_millis(600));
                    }
                    let _ = proxy.send_event(UserEvent::Home(read_clip(&ul)));
                });
            }
            "games" => self.send(View::Home, json!({"type": "games", "records": records()})),
            // Templates: launching and deleting run `ul` here; saving a new one and editing need
            // the terminal (the window checklist and the editor are interactive).
            "template-run" | "template-rm" => {
                let Some(name) = message["name"].as_str().and_then(template_name).map(str::to_string) else {
                    return true;
                };
                let Some(ul) = self.ul.clone() else { return true };
                let argv: Vec<String> = if op == "template-rm" {
                    vec!["template".into(), "rm".into(), name.clone(), "--yes".into()]
                } else {
                    // Open keeps the template's own `focus`; Focus asks for it.
                    let mut argv = vec![name.clone()];
                    if message["focus"].as_bool() == Some(true) {
                        argv.push("--focus".into());
                    }
                    argv
                };
                let (proxy, op) = (self.proxy.clone(), op.to_string());
                thread::spawn(move || {
                    let outcome = runner::run(&ul, &argv, Duration::from_secs(90));
                    let _ = proxy.send_event(UserEvent::Home(json!({"type": "template-done", "op": op, "name": name,
                        "ok": outcome.ok(), "text": outcome.summary(8)})));
                    let _ = proxy.send_event(UserEvent::Home(read_templates(&ul)));
                });
            }
            "template-edit" | "template-new" => {
                let name = message["name"].as_str().and_then(template_name).map(str::to_string);
                let args = match (op, name) {
                    ("template-edit", Some(name)) => vec!["edit".to_string(), name],
                    ("template-new", Some(name)) => vec!["save".to_string(), name],
                    ("template-new", None) => vec!["save".to_string()],
                    _ => return true,
                };
                self.terminal("template", args);
            }
            "settings" => self.send_settings(None),
            "settings-file" => self.open_settings_file(),
            // While the page records a new shortcut, the app's own hotkeys must not
            // fire (Ctrl+Space would open the palette instead of being recorded).
            "recording" => {
                if message["on"].as_bool() == Some(true) {
                    self.pause_hotkeys();
                } else {
                    self.register_hotkeys();
                }
            }
            "clip-files" => {
                // Unlaw's config.toml, so `ul clip` itself reads it: through `ul config set`, which validates and keeps comments.
                let Some(count) = message["count"].as_u64().filter(|count| *count <= 1000) else { return true };
                let Some(ul) = self.ul.clone() else { return true };
                let proxy = self.proxy.clone();
                thread::spawn(move || {
                    let argv = vec!["config".into(), "set".into(), "clip.max_files".into(), count.to_string()];
                    let outcome = runner::run(&ul, &argv, Duration::from_secs(15));
                    let _ = proxy.send_event(UserEvent::Home(json!({"type": "clip-files", "ok": outcome.ok(),
                        "count": clip_max_files(), "error": (!outcome.ok()).then(|| outcome.summary(3))})));
                });
            }
            "settings-save" => {
                let form = settings_form(&message["settings"]);
                let result = settings_text()
                    .and_then(|text| settings::apply(&text, &form))
                    .and_then(|text| write_settings(&text));
                match result {
                    Ok(()) => {
                        self.own_write = modified(&settings::path());
                        self.apply_settings();
                        self.send_settings(None);
                    }
                    Err(error) => self.send_settings(Some(error)),
                }
            }
            "game-start" => {
                let game = message["game"].as_str().filter(|game| GAMES.contains(game)).map(str::to_string);
                let level = message["level"].as_str().filter(|level| LEVELS.contains(level)).unwrap_or("normal");
                let rows = message["rows"].as_i64().unwrap_or(30).clamp(10, 200);
                let cols = message["cols"].as_i64().unwrap_or(116).clamp(20, 400);
                self.start_game(game.as_deref(), level, rows, cols);
            }
            "game-input" => {
                let Some(run) = self.home_state.game.as_mut().filter(|run| Some(run.id) == message["id"].as_u64())
                else {
                    return true;
                };
                let events = message["events"].as_array().map(|events| events.iter().take(64)).into_iter().flatten();
                let mut lines = String::new();
                for event in events.filter_map(game_event) {
                    lines.push_str(&event.to_string());
                    lines.push('\n');
                }
                if let Some(stdin) = run.stdin.as_mut() {
                    let _ = stdin.write_all(lines.as_bytes()).and_then(|_| stdin.flush());
                }
            }
            "game-stop" => self.stop_game(message["id"].as_u64()),
            _ => return false,
        }
        true
    }

    fn start_game(&mut self, game: Option<&str>, level: &str, rows: i64, cols: i64) {
        self.stop_game(None);
        let Some(ul) = self.ul.clone() else { return };
        let mut argv = vec!["game".to_string(), "--stream".into(), "--size".into(), format!("{rows}x{cols}")];
        if let Some(game) = game {
            argv.push(game.into());
            argv.push(level.into());
        }
        let spawned = Command::new(&ul)
            .args(&argv)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .env("UNLAW_APP", "1")
            .process_group(0)
            .spawn();
        self.home_state.next_game += 1;
        let id = self.home_state.next_game;
        let mut child = match spawned {
            Ok(child) => child,
            Err(error) => {
                self.send(
                    View::Home,
                    json!({"type": "game-ended", "id": id, "error": format!("Could not start: {error}")}),
                );
                return;
            }
        };
        let (stdout, stderr, stdin) = (child.stdout.take(), child.stderr.take(), child.stdin.take());
        let errors = Arc::new(Mutex::new(String::new()));
        if let Some(mut stderr) = stderr {
            let errors = errors.clone();
            thread::spawn(move || {
                let mut text = String::new();
                let _ = stderr.by_ref().take(8192).read_to_string(&mut text);
                if let Ok(mut kept) = errors.lock() {
                    *kept = runner::strip_ansi(text.trim());
                }
            });
        }
        let proxy = self.proxy.clone();
        if let Some(stdout) = stdout {
            thread::spawn(move || {
                let mut reader = BufReader::new(stdout);
                let mut line = Vec::new();
                let mut frames = 0u64;
                while matches!(reader.read_until(b'\n', &mut line), Ok(read) if read > 0) {
                    if let Ok(frame) = serde_json::from_slice::<Json>(&line) {
                        if frame.get("lines").is_some() {
                            frames += 1;
                            let message = json!({"type": "frame", "id": id, "frame": frame});
                            if proxy.send_event(UserEvent::Home(message)).is_err() {
                                return;
                            }
                        }
                    }
                    line.clear();
                }
                // The error text, when the game never drew (no game feature, a bad ul).
                thread::sleep(Duration::from_millis(200));
                let error = (frames == 0).then(|| errors.lock().map(|text| text.clone()).unwrap_or_default());
                let _ = proxy.send_event(UserEvent::GameEnded { id, error: error.filter(|text| !text.is_empty()) });
            });
        }
        self.home_state.game = Some(GameRun { id, stdin, child });
        self.send(View::Home, json!({"type": "game-started", "id": id}));
    }

    /// Stop the running game (only `id` when given). Closing stdin ends it; the
    /// group is stopped after a grace period off the UI thread.
    pub(super) fn stop_game(&mut self, id: Option<u64>) {
        let current = self.home_state.game.as_ref().map(|run| run.id);
        if current.is_none() || (id.is_some() && id != current) {
            return;
        }
        let Some(mut run) = self.home_state.game.take() else { return };
        run.stdin.take();
        thread::spawn(move || runner::stop_group(&mut run.child, Duration::from_secs(2)));
        self.send(View::Home, json!({"type": "game-ended", "id": run.id, "error": "Stopped."}));
    }

    pub(super) fn on_game_ended(&mut self, id: u64, error: Option<String>) {
        if self.home_state.game.as_ref().map(|run| run.id) != Some(id) {
            return;
        }
        if let Some(mut run) = self.home_state.game.take() {
            run.stdin.take();
            thread::spawn(move || runner::stop_group(&mut run.child, Duration::from_secs(2)));
        }
        self.send(View::Home, json!({"type": "game-ended", "id": id, "error": error}));
        self.send(View::Home, json!({"type": "games", "records": records()}));
    }

    fn ensure_desk(&mut self) {
        if self.home_state.desk.is_some() {
            self.send(View::Home, json!({"type": "desk", "state": "ready"}));
            return;
        }
        if self.home_state.desk_opening {
            return;
        }
        let Some(ul) = self.ul.clone() else {
            self.send(View::Home, json!({"type": "desk", "state": "error", "text": "ul was not found."}));
            return;
        };
        let args = self
            .specs
            .get("desk")
            .and_then(|(spec, _)| spec.open.as_ref().map(|open| open.args.clone()))
            .unwrap_or_else(|| vec!["--no-open".to_string()]);
        self.home_state.desk_opening = true;
        self.send(View::Home, json!({"type": "desk", "state": "starting"}));
        let proxy = self.proxy.clone();
        thread::spawn(move || {
            let result = runner::serve(&ul, &command_line("desk", &args), SERVE_WAIT);
            if let Err(tao::event_loop::EventLoopClosed(UserEvent::DeskServed(Ok((mut child, _))))) =
                proxy.send_event(UserEvent::DeskServed(result))
            {
                runner::stop_group(&mut child, Duration::from_secs(5));
            }
        });
    }

    pub(super) fn on_desk_served(&mut self, result: Result<(Child, String), String>) {
        self.home_state.desk_opening = false;
        let (mut child, url) = match result {
            Ok((child, url)) => (child, embed_url(&url, &self.home_state.section)),
            Err(error) => {
                self.send(
                    View::Home,
                    json!({"type": "desk", "state": "error", "text": format!("The desk did not start: {error}")}),
                );
                return;
            }
        };
        let (x, y, width, height) =
            self.home_state.desk_area.unwrap_or((208.0, 52.0, HOME_SIZE.0 - 208.0, HOME_SIZE.1 - 52.0));
        let built = page_builder(&url, self.proxy.clone(), HOME_DESK.into())
            .with_bounds(wry::Rect {
                position: LogicalPosition::new(x, y).into(),
                size: LogicalSize::new(width, height).into(),
            })
            .with_visible(false)
            .build_as_child(&self.home.window);
        match built {
            Ok(webview) => {
                self.home_state.desk = Some(DeskView { webview, child, url, opened: None });
                self.send(View::Home, json!({"type": "desk", "state": "ready"}));
                self.place_desk();
            }
            Err(error) => {
                runner::stop_group(&mut child, Duration::from_secs(3));
                self.send(View::Home, json!({"type": "desk", "state": "error", "text": error.to_string()}));
            }
        }
    }

    /// The desk page covers the content area while the Desk part is shown.
    pub(super) fn place_desk(&self) {
        let Some(desk) = &self.home_state.desk else { return };
        let shown = self.home.window.is_visible() && DESK_PARTS.contains(&self.home_state.section.as_str());
        if let Some((x, y, width, height)) = self.home_state.desk_area {
            let _ = desk.webview.set_bounds(wry::Rect {
                position: LogicalPosition::new(x, y).into(),
                size: LogicalSize::new(width, height).into(),
            });
        }
        let _ = desk.webview.set_visible(shown);
        if shown {
            let _ = desk.webview.focus();
        }
    }

    /// The desk page's main frame went to another site (see `on_page_left`).
    pub(super) fn desk_left(&mut self, url: &str) {
        let Some(desk) = self.home_state.desk.as_mut() else { return };
        if desk.opened.is_none_or(|last| last.elapsed() >= Duration::from_secs(2)) {
            desk.opened = Some(Instant::now());
            platform::open_link(url);
        }
        let _ = desk.webview.load_url(&desk.url);
    }

    /// The desk server ended: the part says so and offers to start it again.
    pub(super) fn check_desk(&mut self) {
        let ended = self.home_state.desk.as_mut().is_some_and(|desk| !matches!(desk.child.try_wait(), Ok(None)));
        if ended {
            self.home_state.desk = None;
            self.send(View::Home, json!({"type": "desk", "state": "error", "text": "The desk stopped."}));
        }
    }

    /// Children to stop when the app quits.
    pub(super) fn home_children(&mut self) -> Vec<Child> {
        let mut children = Vec::new();
        if let Some(mut run) = self.home_state.game.take() {
            run.stdin.take();
            children.push(run.child);
        }
        if let Some(desk) = self.home_state.desk.take() {
            drop(desk.webview);
            children.push(desk.child);
        }
        children
    }
}

/// The page's settings object as a form; anything missing or of the wrong
/// type becomes an empty value, which `settings::apply` then refuses.
fn settings_form(value: &Json) -> settings::Form {
    let text = |value: &Json| value.as_str().unwrap_or("").to_string();
    settings::Form {
        palette: text(&value["palette"]),
        hotkeys: value["hotkeys"]
            .as_array()
            .map(|list| {
                list.iter()
                    .take(64)
                    .map(|item| (text(&item["keys"]), text(&item["command"]), text(&item["action"])))
                    .collect()
            })
            .unwrap_or_default(),
        menubar: value["menubar"].as_array().map(|list| list.iter().take(64).map(text).collect()).unwrap_or_default(),
        sys: value["sys"].as_array().map(|list| list.iter().take(16).map(text).collect()).unwrap_or_default(),
        show_status: value["show_status"].as_bool().unwrap_or(true),
        theme: text(&value["theme"]),
        dock: value["dock"].as_bool().unwrap_or(true),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn template_names_are_checked() {
        assert_eq!(template_name("ul-work"), Some("ul-work"));
        for name in ["", "-x", ".hidden", "a/b", "a b", "--focus"] {
            assert_eq!(template_name(name), None, "{name}");
        }
    }

    #[test]
    fn only_saved_clip_pictures_are_served() {
        assert_eq!(clip_picture_kind("0123456789abcdef.png"), Some("image/png"));
        assert_eq!(clip_picture_kind("0123456789abcdef.jpeg"), Some("image/jpeg"));
        for name in [
            "0123456789abcdef.pdf",
            "../history.json",
            "0123456789ABCDEF.png",
            "short.png",
            "0123456789abcdef",
            "0123456789abcdeg.png",
        ] {
            assert_eq!(clip_picture_kind(name), None, "{name}");
        }
    }

    #[test]
    fn desk_parts_open_the_embedded_page_at_their_view() {
        assert_eq!(
            embed_url("http://127.0.0.1:8765/?token=abc", "canvas"),
            "http://127.0.0.1:8765/?token=abc&embed=1#canvas"
        );
        assert_eq!(embed_url("http://127.0.0.1:8765/#board", "today"), "http://127.0.0.1:8765/?embed=1#today");
        assert_eq!(canonical("desk"), "board");
        assert_eq!(canonical("canvas"), "canvas");
    }

    #[test]
    fn the_settings_page_sends_plain_values() {
        let form = settings_form(
            &json!({"palette": "ctrl+space", "hotkeys": [{"keys": "f5", "command": "sys", "action": "panel"}, {"keys": 3}],
            "menubar": ["sys", 7], "show_status": false, "theme": "dark", "dock": "yes"}),
        );
        assert_eq!(form.hotkeys[0], ("f5".into(), "sys".into(), "panel".into()));
        assert_eq!(
            form.hotkeys[1],
            (String::new(), String::new(), String::new()),
            "a wrong type is empty, so apply refuses it"
        );
        assert_eq!(form.menubar, vec!["sys".to_string(), String::new()]);
        assert!(!form.show_status && form.dock);
    }

    #[test]
    fn game_input_is_rebuilt_from_a_whitelist() {
        assert_eq!(game_event(&json!({"key": "up"})), Some(json!({"key": "up"})));
        assert_eq!(game_event(&json!({"release": " "})), Some(json!({"release": " "})));
        assert_eq!(
            game_event(&json!({"click": {"y": 3, "x": 9, "button": "right", "extra": 1}})),
            Some(json!({"click": {"y": 3, "x": 9, "button": "right"}}))
        );
        assert_eq!(game_event(&json!({"click": {"y": -1, "x": 9, "button": "left"}})), None);
        assert_eq!(game_event(&json!({"click": {"y": 1, "x": 9, "button": "evil"}})), None);
        assert_eq!(game_event(&json!({"resize": {"rows": 5000, "cols": 1}})), None, "the page cannot resize the game");
        assert_eq!(game_event(&json!({"key": "a very long key name"})), None);
    }

    #[test]
    fn clip_requests_become_fixed_arguments() {
        assert_eq!(clip_args("copy", Some("9fa8c13f250e")).unwrap(), ["clip", "copy", "@9fa8c13f250e"]);
        assert_eq!(clip_args("clear", None).unwrap(), ["clip", "clear", "--yes"]);
        assert_eq!(clip_args("on", None).unwrap(), ["clip", "on"]);
        assert_eq!(clip_args("copy", Some("../x")), None);
        assert_eq!(clip_args("copy", None), None);
        assert_eq!(clip_args("search", Some("abc123")), None);
    }
}
