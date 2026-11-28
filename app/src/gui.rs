//! The window shell of Unlaw.app: menu bar items, global hotkeys, the palette
//! and panel windows (glass, one web page each) and page windows for commands
//! that serve one (desk). Every command runs through `ul`; this file only
//! decides what to run and shows the result.

use std::borrow::Cow;
use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Child;
use std::sync::atomic::{AtomicI32, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant, SystemTime};

use global_hotkey::hotkey::{Code, HotKey, Modifiers};
use global_hotkey::{GlobalHotKeyEvent, GlobalHotKeyManager, HotKeyState};
use serde_json::{json, Value as Json};
use tao::dpi::{LogicalPosition, LogicalSize, PhysicalPosition, PhysicalSize};
use tao::event::{Event, StartCause, WindowEvent};
use tao::event_loop::{ControlFlow, EventLoopBuilder, EventLoopProxy, EventLoopWindowTarget};
use tao::window::{Theme as WindowTheme, Window, WindowBuilder, WindowId};
use tray_icon::menu::{Menu, MenuEvent, MenuId, MenuItem, PredefinedMenuItem};
use tray_icon::{MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent};
use wry::http::{header::CONTENT_TYPE, Request, Response};
use wry::{WebView, WebViewBuilder};

use unlaw_app::args;
use unlaw_app::hotkey::Hotkey;
use unlaw_app::runner::{self, Outcome};
use unlaw_app::settings::{self, Settings, Target, Theme};
use unlaw_app::spec::{self, Record, Spec};
use unlaw_app::template::{self, StatusText};
use unlaw_app::views;

use crate::platform;

mod editor;
mod home;
use editor::{EditEvent, EditState};
use home::{HomeState, HOME_DESK};

const PAGE: &str = include_str!("../ui/index.html");
const CSS: &str = include_str!("../ui/app.css");
const JS: &str = include_str!("../ui/app.js");
const COMMON_JS: &str = include_str!("../ui/common.js");
const VIEWS_JS: &str = include_str!("../ui/views.js");
const HOME_PAGE: &str = include_str!("../ui/home.html");
const HOME_CSS: &str = include_str!("../ui/home.css");
const HOME_JS: &str = include_str!("../ui/home.js");
const EDIT_CSS: &str = include_str!("../ui/edit.css");
const EDIT_JS: &str = include_str!("../ui/edit.js");
const PDF_JS: &str = include_str!("../ui/pdf.js");
const PALETTE_SIZE: (f64, f64) = (680.0, 460.0);
const PANEL_WIDTH: f64 = 360.0;
const TOAST_WIDTH: f64 = 340.0;
/// How long a note stays (a failure a little longer: it has more to read).
const TOAST_SECONDS: (u64, u64) = (3, 6);
const PANEL_MAX_WIDTH: f64 = 760.0;

/// A panel's normal width: the app's own views are laid out for theirs.
fn panel_width(view: Option<&str>) -> f64 {
    match view {
        Some("system") => 440.0,
        Some("awake") => 340.0,
        _ => PANEL_WIDTH,
    }
}
const ACTION_TIMEOUT: Duration = Duration::from_secs(3600);
const STATUS_TIMEOUT: Duration = Duration::from_secs(10);
const LIST_TIMEOUT: Duration = Duration::from_secs(15);
const SERVE_WAIT: Duration = Duration::from_secs(25);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
enum View {
    Palette,
    Panel,
    /// The main window (Dock icon): Commands, System, Clipboard, Arcade, Desk.
    Home,
    /// A small note in the screen's top-right corner ("Copied", an error), instead of
    /// macOS notifications: one look everywhere, gone by itself, never takes the focus.
    Toast,
}

impl View {
    fn name(self) -> &'static str {
        match self {
            View::Palette => "palette",
            View::Panel => "panel",
            View::Home => "home",
            View::Toast => "toast",
        }
    }
}

enum UserEvent {
    Loaded(Result<Vec<Record>, String>),
    /// `ule --theme-colors` answered (None: no editor colors to use).
    Colors(Option<Json>),
    Status {
        name: String,
        generation: u64,
        text: StatusText,
    },
    Finished {
        name: String,
        label: String,
        argv: Vec<String>,
        outcome: Outcome,
        /// Started by a toggle click: no notification when it worked.
        quiet: bool,
        /// Started from the palette's inline input: a short answer is a notification,
        /// a long one or a failure opens the command's panel with it.
        quick: bool,
    },
    Served {
        name: String,
        result: Result<(Child, String), String>,
    },
    Ipc(View, String),
    Tray(TrayIconEvent),
    Menu(MenuEvent),
    Hotkey(GlobalHotKeyEvent),
    SettingsChanged,
    CliInstalled(Result<Vec<String>, String>),
    /// SIGTERM/SIGHUP (launchctl bootout, logout): quit like the menu's Quit.
    Terminate,
    /// A message for the main window's page.
    Home(Json),
    /// A message for the palette's page (the clipboard history it lists).
    Palette(Json),
    /// A note from a worker thread (`App::toast`).
    Toast {
        title: String,
        text: String,
        ok: bool,
    },
    /// The note's time is up (its generation: a newer note stays).
    ToastHide(u64),
    /// A view panel's reads (`views::reads`) or the end of its action.
    Panel {
        name: String,
        message: Json,
        changed: bool,
    },
    /// The main window's game ended by itself; `error` when it never drew.
    GameEnded {
        id: u64,
        error: Option<String>,
    },
    /// Files dropped on the palette (full paths, which a page never gets).
    Dropped(Vec<PathBuf>),
    /// Files dropped on the main window (for Edit).
    HomeDropped(Vec<PathBuf>),
    /// The Edit part's background work (a dialog's answer, the editor ending).
    Edit(EditEvent),
    /// A round of `ul sys --json --watch` (None: the watch ended).
    SysData {
        id: u64,
        data: Option<Json>,
    },
    /// `ul desk` for the main window is serving (or failed to start).
    DeskServed(Result<(Child, String), String>),
    /// Every few seconds: look whether the page servers are still running.
    CheckPages,
    /// A page window's main frame started loading another site.
    PageLeft {
        name: String,
        url: String,
    },
}

/// Where a run was started: a panel shows the result itself, everything else
/// gets a notification.
#[derive(Clone, Copy, PartialEq)]
enum From {
    Panel,
    Elsewhere,
    /// The menu bar item's own switch: the icon is the answer, a notification only on failure.
    Toggle,
    /// The palette's inline input (`Spec::quick`).
    Quick,
}

struct Page {
    window: Window,
    _webview: WebView,
    child: Child,
    /// The page's address, loaded again when its main frame goes to another site.
    url: String,
    /// When a link of this page last went to the browser (at most one per 2 s).
    opened: Option<Instant>,
}

struct Glass {
    window: Window,
    /// None while unloaded: the panel and the main window give their WebKit
    /// process back once hidden for a while (`unload_hidden`) and load again
    /// when shown (`ensure_page`). The palette keeps its page, so Ctrl+Space is instant.
    webview: Option<WebView>,
    ready: bool,
    /// Messages sent before the page loaded; delivered once it says ready.
    pending: Vec<Json>,
    /// Since when the window has been hidden with its page loaded.
    hidden_since: Option<Instant>,
}

/// How long a hidden panel or main window keeps its page before it is unloaded:
/// long enough that reopening it soon after is instant.
const UNLOAD_AFTER: Duration = Duration::from_secs(30);

enum HotkeyJob {
    Palette,
    Command(String, Target),
}

struct App {
    ul: Option<PathBuf>,
    proxy: EventLoopProxy<UserEvent>,
    settings: Settings,
    warnings: Vec<String>,
    records: Vec<Record>,
    specs: BTreeMap<String, (Spec, Option<String>)>,
    list_error: Option<String>,
    statuses: HashMap<String, StatusText>,
    generation: Arc<AtomicU64>,
    palette: Glass,
    /// The palette's inline input is open: it stays when another app takes the focus.
    palette_keep: bool,
    panel: Glass,
    panel_for: Option<String>,
    pages: HashMap<String, Page>,
    opening: Vec<String>,
    main_tray: Option<TrayIcon>,
    trays: Vec<(String, TrayIcon)>,
    menu_ids: HashMap<MenuId, &'static str>,
    hotkeys: Option<GlobalHotKeyManager>,
    registered: Vec<(HotKey, HotkeyJob)>,
    /// argv of runs still going: the same run is not started twice (a double click).
    running: Vec<Vec<String>>,
    /// Where the palette and the panel were dragged to (kept across starts).
    places: Places,
    /// The window being dragged now: its moves are the user's, not ours.
    dragging: Option<View>,
    /// The panel's center line (points): placement and every resize keep it.
    panel_center: f64,
    /// The next view read is the first since the panel opened (`views::reads`).
    view_first: bool,
    /// View reads on their way, so a slow `ul sys` never piles up.
    view_reading: bool,
    /// Hotkeys that could not be registered; rebuilt by `register_hotkeys` only.
    hotkey_warnings: Vec<String>,
    /// The pinned commands' descriptions the menu bar items were last built from.
    shown: Vec<(String, Option<Spec>)>,
    /// app.toml's time after the app's own last write, so the watcher skips it.
    own_write: Option<SystemTime>,
    home: Glass,
    home_state: HomeState,
    /// The Edit part: its folders, recent files and the editor process.
    edit: EditState,
    toast: Glass,
    /// The editor theme's colors every window paints with (look.colors = "editor"), if any.
    ui_colors: Option<Json>,
    /// Counts notes shown: a timer hides only its own note, not a newer one.
    toast_generation: u64,
    /// What a click on the note opens: the command's panel with the whole output.
    toast_more: Option<(String, bool, String)>,
    /// The app menu (Unlaw, Edit, View, Window) while Unlaw is in the Dock.
    app_menu: Option<Menu>,
}

fn content(path: &str) -> Option<(&'static str, &'static str)> {
    match path {
        "/" | "/index.html" => Some((PAGE, "text/html; charset=utf-8")),
        "/app.css" => Some((CSS, "text/css; charset=utf-8")),
        "/app.js" => Some((JS, "text/javascript; charset=utf-8")),
        "/common.js" => Some((COMMON_JS, "text/javascript; charset=utf-8")),
        "/views.js" => Some((VIEWS_JS, "text/javascript; charset=utf-8")),
        "/home.html" => Some((HOME_PAGE, "text/html; charset=utf-8")),
        "/home.css" => Some((HOME_CSS, "text/css; charset=utf-8")),
        "/home.js" => Some((HOME_JS, "text/javascript; charset=utf-8")),
        "/edit.css" => Some((EDIT_CSS, "text/css; charset=utf-8")),
        "/edit.js" => Some((EDIT_JS, "text/javascript; charset=utf-8")),
        "/pdf.js" => Some((PDF_JS, "text/javascript; charset=utf-8")),
        _ => None,
    }
}

/// `%20` and friends in a URL path, as UTF-8 (None when it is not).
fn percent_decoded(text: &str) -> Option<String> {
    let bytes = text.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'%' {
            let hex = text.get(index + 1..index + 3)?;
            out.push(u8::from_str_radix(hex, 16).ok()?);
            index += 3;
        } else {
            out.push(bytes[index]);
            index += 1;
        }
    }
    String::from_utf8(out).ok()
}

/// `ulapp://localhost/appicon/<Name>.png`: an installed application's icon (the
/// command tiles and palette rows of app launchers), made once and kept.
fn serve_app_icon(file: &str) -> Response<Cow<'static, [u8]>> {
    static CACHE: std::sync::Mutex<Option<HashMap<String, Option<Vec<u8>>>>> = std::sync::Mutex::new(None);
    let missing = || {
        Response::builder()
            .status(404)
            .body(Cow::Borrowed(&b""[..]))
            .unwrap_or_else(|_| Response::new(Cow::Borrowed(&b""[..])))
    };
    let Some(name) = file.strip_suffix(".png").and_then(percent_decoded).filter(|name| settings::app_name_ok(name))
    else {
        return missing();
    };
    let mut cache = CACHE.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    let cache = cache.get_or_insert_with(HashMap::new);
    #[cfg(target_os = "macos")]
    let png = cache.entry(name.clone()).or_insert_with(|| platform::app_icon_png(&name, 64.0)).clone();
    #[cfg(not(target_os = "macos"))]
    let png: Option<Vec<u8>> = None;
    match png {
        Some(png) => Response::builder()
            .header(CONTENT_TYPE, "image/png")
            .body(Cow::Owned(png))
            .unwrap_or_else(|_| Response::new(Cow::Borrowed(&b""[..]))),
        None => missing(),
    }
}

fn serve_asset(request: Request<Vec<u8>>) -> Response<Cow<'static, [u8]>> {
    if let Some(file) = request.uri().path().strip_prefix("/appicon/") {
        return serve_app_icon(file);
    }
    match content(request.uri().path()) {
        Some((body, kind)) => Response::builder()
            .header(CONTENT_TYPE, kind)
            .body(Cow::Borrowed(body.as_bytes()))
            .unwrap_or_else(|_| Response::new(Cow::Borrowed(&b""[..]))),
        None => Response::builder()
            .status(404)
            .body(Cow::Borrowed(&b""[..]))
            .unwrap_or_else(|_| Response::new(Cow::Borrowed(&b""[..]))),
    }
}

fn glass(target: &EventLoopWindowTarget<UserEvent>, proxy: &EventLoopProxy<UserEvent>, view: View) -> Glass {
    let size = match view {
        View::Palette => LogicalSize::new(PALETTE_SIZE.0, PALETTE_SIZE.1),
        View::Panel | View::Home => LogicalSize::new(PANEL_WIDTH, 300.0),
        View::Toast => LogicalSize::new(TOAST_WIDTH, 64.0),
    };
    let window = WindowBuilder::new()
        .with_title(match view {
            View::Palette => "Unlaw",
            View::Toast => "Unlaw note",
            _ => "Unlaw panel",
        })
        .with_decorations(false)
        .with_transparent(true)
        .with_resizable(false)
        .with_always_on_top(true)
        .with_visible(false)
        .with_inner_size(size)
        .build(target)
        .expect("a window");
    // Only the palette loads its page at start; the panel loads on first use.
    let webview = (view == View::Palette).then(|| page_for(&window, proxy, view));
    Glass { window, webview, ready: false, pending: Vec::new(), hidden_since: None }
}

/// The web view of a glass window, with its blur. Built after the window
/// exists and again whenever an unloaded window is shown.
fn page_for(window: &Window, proxy: &EventLoopProxy<UserEvent>, view: View) -> WebView {
    if view == View::Home {
        return home::home_webview(window, proxy);
    }
    let ipc = proxy.clone();
    let drop_proxy = proxy.clone();
    let webview = WebViewBuilder::new()
        .with_transparent(true)
        .with_custom_protocol("ulapp".into(), |_, request| serve_asset(request))
        .with_url("ulapp://localhost/index.html")
        .with_ipc_handler(move |request: Request<String>| {
            // Only our own page talks to Rust; nothing else is ever loaded here.
            if request.uri().scheme_str() == Some("ulapp") {
                let _ = ipc.send_event(UserEvent::Ipc(view, request.into_body()));
            }
        })
        .with_navigation_handler(|url| url.starts_with("ulapp://"))
        .with_new_window_req_handler(|_, _| wry::NewWindowResponse::Deny)
        .with_drag_drop_handler(move |event| match event {
            // Only the palette takes files (paths for its inline input); a drop never navigates.
            wry::DragDropEvent::Drop { paths, .. } if view == View::Palette => {
                let _ = drop_proxy.send_event(UserEvent::Dropped(paths));
                true
            }
            wry::DragDropEvent::Drop { .. } => true,
            _ => false,
        })
        .with_accept_first_mouse(true)
        .build(window)
        .expect("a web view");
    // After the web view: wry makes its own content view, which would drop a
    // blur view added before it (and a rebuilt page gets a new content view).
    #[cfg(target_os = "macos")]
    {
        use window_vibrancy::{apply_vibrancy, NSVisualEffectMaterial, NSVisualEffectState};
        let material =
            if view == View::Palette { NSVisualEffectMaterial::HudWindow } else { NSVisualEffectMaterial::Popover };
        if let Err(error) = apply_vibrancy(window, material, Some(NSVisualEffectState::Active), Some(14.0)) {
            eprintln!("ul-app: no glass for the {}: {error}", view.name());
        }
    }
    webview
}

fn code_for(key: &str) -> Option<Code> {
    let name = match key {
        k if k.len() == 1 && k.chars().all(|c| c.is_ascii_lowercase()) => format!("Key{}", k.to_ascii_uppercase()),
        k if k.len() == 1 && k.chars().all(|c| c.is_ascii_digit()) => format!("Digit{k}"),
        k if k.starts_with('f') && k.len() > 1 => format!("F{}", &k[1..]),
        "space" => "Space".into(),
        "enter" => "Enter".into(),
        "tab" => "Tab".into(),
        "escape" => "Escape".into(),
        "backspace" => "Backspace".into(),
        "delete" => "Delete".into(),
        "up" => "ArrowUp".into(),
        "down" => "ArrowDown".into(),
        "left" => "ArrowLeft".into(),
        "right" => "ArrowRight".into(),
        "home" => "Home".into(),
        "end" => "End".into(),
        "pageup" => "PageUp".into(),
        "pagedown" => "PageDown".into(),
        other => {
            let mut chars = other.chars();
            let first = chars.next()?.to_ascii_uppercase();
            let rest: String = chars.collect();
            // comma -> Comma, bracketleft -> BracketLeft, backquote -> Backquote
            let rest = rest.replace("left", "Left").replace("right", "Right");
            format!("{first}{rest}")
        }
    };
    name.parse().ok()
}

fn os_hotkey(hotkey: &Hotkey) -> Option<HotKey> {
    let mut mods = Modifiers::empty();
    for (on, flag) in [
        (hotkey.ctrl, Modifiers::CONTROL),
        (hotkey.alt, Modifiers::ALT),
        (hotkey.shift, Modifiers::SHIFT),
        (hotkey.cmd, Modifiers::META),
    ] {
        if on {
            mods |= flag;
        }
    }
    Some(HotKey::new(if mods.is_empty() { None } else { Some(mods) }, code_for(&hotkey.key)?))
}

/// app.toml as text; the default only when there is none. A file that exists
/// but cannot be read is an error, so it is never overwritten with defaults.
fn settings_text() -> Result<String, String> {
    match fs::read_to_string(settings::path()) {
        Ok(text) => Ok(text),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(settings::DEFAULT.to_string()),
        Err(error) => Err(format!("{}: {error}", settings::path().display())),
    }
}

fn write_settings(text: &str) -> Result<(), String> {
    let path = settings::path();
    // A symlinked app.toml (dotfiles) is written where it points; the link stays.
    let path = if path.is_symlink() { fs::canonicalize(&path).map_err(|error| error.to_string())? } else { path };
    if let Some(folder) = path.parent() {
        fs::create_dir_all(folder).map_err(|error| error.to_string())?;
    }
    let temporary = path.with_file_name(format!(".app.toml.{}", std::process::id()));
    fs::write(&temporary, text).and_then(|_| fs::rename(&temporary, &path)).map_err(|error| {
        let _ = fs::remove_file(&temporary);
        error.to_string()
    })
}

/// `ul <name> <status args>` once, as menu bar text.
fn read_status(ul: &Path, name: &str, status: &spec::Status) -> StatusText {
    let outcome = runner::run(ul, &command_line(name, &status.args), STATUS_TIMEOUT);
    let text = template::status_text(status, &outcome.stdout);
    if !outcome.ok() && text.text.is_empty() {
        return StatusText { text: "–".into(), state: Some("warn".into()), icon: None };
    }
    text
}

/// argv for `ul`: the command's name, then its arguments.
fn command_line(name: &str, args: &[String]) -> Vec<String> {
    std::iter::once(name.to_string()).chain(args.iter().cloned()).collect()
}

fn modified(path: &Path) -> Option<SystemTime> {
    fs::metadata(path).and_then(|meta| meta.modified()).ok()
}

impl App {
    fn glass_mut(&mut self, view: View) -> &mut Glass {
        match view {
            View::Palette => &mut self.palette,
            View::Panel => &mut self.panel,
            View::Home => &mut self.home,
            View::Toast => &mut self.toast,
        }
    }

    fn send(&mut self, view: View, message: Json) {
        let glass = self.glass_mut(view);
        match (&glass.webview, glass.ready) {
            (Some(webview), true) => {
                let _ = webview.evaluate_script(&format!("window.ul.receive({message})"));
            }
            (Some(_), false) if glass.pending.len() < 64 => glass.pending.push(message),
            // No page: it gets everything it needs in `init` when it loads again.
            _ => {}
        }
    }

    /// Loads the window's page if it was unloaded (or never loaded); call before showing it.
    fn ensure_page(&mut self, view: View) {
        let proxy = self.proxy.clone();
        let glass = self.glass_mut(view);
        glass.hidden_since = None;
        if glass.webview.is_none() {
            debug(&format!("loading the {} page", view.name()));
            glass.ready = false;
            glass.pending.clear();
            glass.webview = Some(page_for(&glass.window, &proxy, view));
            if view == View::Home {
                self.apply_zoom();
            }
        }
    }

    /// Unloads the pages of the panel and the main window hidden for
    /// `UNLOAD_AFTER`: each page is a WebKit process of 20-45 MB.
    fn unload_hidden(&mut self) {
        for view in [View::Panel, View::Home, View::Toast] {
            let glass = self.glass_mut(view);
            if glass.window.is_visible() || glass.webview.is_none() {
                glass.hidden_since = None;
                continue;
            }
            let since = *glass.hidden_since.get_or_insert_with(Instant::now);
            if since.elapsed() < UNLOAD_AFTER {
                continue;
            }
            debug(&format!("unloading the hidden {} page", view.name()));
            glass.webview = None;
            glass.ready = false;
            glass.pending.clear();
            glass.hidden_since = None;
            if view == View::Home {
                // The desk view lives in the main window's content view, which goes with the page.
                self.unload_desk();
                self.edit_hidden();
            } else {
                self.panel_for = None;
            }
        }
    }

    fn theme(&self) -> &'static str {
        match &self.ui_colors {
            Some(colors) if colors["dark"] == true => "dark",
            Some(_) => "light",
            None => self.settings.theme.name(),
        }
    }

    /// Asks ule for the colors of the editor theme (off the UI thread; ~10 ms).
    fn refresh_colors(&self) {
        let proxy = self.proxy.clone();
        if !self.settings.editor_colors {
            let _ = proxy.send_event(UserEvent::Colors(None));
            return;
        }
        let ule = editor::ule_path(self.ul.as_deref());
        thread::spawn(move || {
            let colors = ule.and_then(|ule| {
                let outcome =
                    runner::run_capped(&ule, &["--theme-colors".to_string()], Duration::from_secs(5), 1 << 16);
                serde_json::from_str::<Json>(outcome.stdout.trim()).ok().filter(|_| outcome.ok())
            });
            let _ = proxy.send_event(UserEvent::Colors(colors.as_ref().and_then(settings::editor_palette)));
        });
    }

    fn set_colors(&mut self, colors: Option<Json>) {
        if self.ui_colors == colors {
            return;
        }
        self.ui_colors = colors;
        self.window_theme();
        let message = json!({"type": "colors", "colors": self.ui_colors, "theme": self.theme()});
        for view in [View::Home, View::Palette, View::Panel, View::Toast] {
            self.send(view, message.clone());
        }
        self.desk_theme();
    }

    /// Windows take the appearance of the colors in use (dark glass under a dark theme).
    fn window_theme(&self) {
        let window_theme = match (&self.ui_colors, self.settings.theme) {
            (Some(colors), _) if colors["dark"] == true => Some(WindowTheme::Dark),
            (Some(_), _) => Some(WindowTheme::Light),
            (None, Theme::Auto) => None,
            (None, Theme::Light) => Some(WindowTheme::Light),
            (None, Theme::Dark) => Some(WindowTheme::Dark),
        };
        self.palette.window.set_theme(window_theme);
        self.panel.window.set_theme(window_theme);
        self.home.window.set_theme(window_theme);
        self.toast.window.set_theme(window_theme);
    }

    fn load_settings(&mut self) {
        match settings_text() {
            Ok(text) => {
                let (settings, warnings) = settings::parse(&text);
                self.settings = settings;
                self.warnings = warnings;
            }
            // Keep what is running; the file stays as it is.
            Err(error) => self.warnings = vec![format!("could not read {error}")],
        }
        self.window_theme();
    }

    fn reload_commands(&self) {
        let Some(ul) = self.ul.clone() else {
            let _ = self.proxy.send_event(UserEvent::Loaded(Err("ul was not found".into())));
            return;
        };
        let proxy = self.proxy.clone();
        thread::spawn(move || {
            let outcome = runner::run(&ul, &["commands".into(), "--json".into()], LIST_TIMEOUT);
            let result = if outcome.ok() {
                spec::parse_records(&outcome.stdout)
            } else {
                Err(format!("ul commands: {}", outcome.summary(3)))
            };
            let _ = proxy.send_event(UserEvent::Loaded(result));
        });
    }

    fn all_warnings(&self) -> Vec<String> {
        let mut all = self.warnings.clone();
        all.extend(self.hotkey_warnings.iter().cloned());
        all.extend(self.list_error.clone());
        all.extend(self.specs.values().filter_map(|(_, problem)| problem.clone()));
        if !self.specs.is_empty() {
            let specs: Vec<spec::Spec> = self.specs.values().map(|(spec, _)| spec.clone()).collect();
            all.extend(spec::settings_problems(&self.settings, &specs));
        }
        if self.ul.is_none() {
            all.push("The ul command line was not found: install it (ul gui install) or set UNLAW_BIN.".into());
        }
        all
    }

    /// The command list goes to the palette and the main window.
    fn send_list(&mut self) {
        let list = self.list_json();
        self.send(View::Palette, list.clone());
        self.send(View::Home, list);
    }

    fn list_json(&self) -> Json {
        let items: Vec<Json> = self
            .specs
            .values()
            .filter(|(spec, _)| spec.in_app)
            .map(|(spec, _)| {
                let mut item = spec::to_json(spec);
                item["pinned"] = json!(self.settings.menubar.contains(&spec.name));
                item["panel"] = json!(spec.panel.is_some());
                // Counts for `panelAddsMore` (Tab opens the panel only when it shows more than the inline input).
                item["fields"] = json!(spec.panel.as_ref().map_or(0, |panel| panel.fields.len()));
                item["buttons"] = json!(spec.panel.as_ref().map_or(0, |panel| panel.buttons.len()));
                // Takes a typed link (`ul browser <link>`): the palette offers "Open link".
                item["link"] =
                    json!(spec.panel.as_ref().is_some_and(|panel| panel.fields.iter().any(|field| field.id == "url")));
                item
            })
            .collect();
        json!({"type": "list", "items": items, "warnings": self.all_warnings()})
    }

    fn on_loaded(&mut self, result: Result<Vec<Record>, String>) {
        match result {
            Ok(records) => {
                self.list_error = None;
                self.specs = records.iter().map(|record| (record.name.clone(), spec::for_record(record))).collect();
                self.records = records;
            }
            Err(error) => self.list_error = Some(error),
        }
        self.send_list();
        // Every palette open reloads the list; the menu bar items and their
        // pollers are only redone when a pinned command's description changed.
        if self.pinned_specs() != self.shown {
            self.rebuild_trays();
            self.restart_status();
        }
        // UNLAW_APP_SHOW=<command>: open its panel once, to look at it while
        // working on the app (synthetic key presses take the focus away).
        if let Some(name) = std::env::var("UNLAW_APP_SHOW").ok().filter(|name| self.specs.contains_key(name)) {
            std::env::remove_var("UNLAW_APP_SHOW");
            self.show_panel(&name, None);
        }
        // UNLAW_APP_HOME=<part> (or games:<game>): open the main window at that
        // part, the same way.
        if let Ok(section) = std::env::var("UNLAW_APP_HOME") {
            std::env::remove_var("UNLAW_APP_HOME");
            match section.split_once(':') {
                Some(("games", game)) => {
                    self.show_home(Some("games"));
                    self.send(View::Home, json!({"type": "play", "game": game}));
                }
                _ => self.show_home(Some(&section)),
            }
        }
    }

    // ---------- menu bar ----------

    fn rebuild_trays(&mut self) {
        // New status items appear to the left of older ones, so the rightmost
        // (UL) is made first and the pinned ones from the last to the first.
        self.trays.clear();
        self.shown = self.pinned_specs();
        if !self.settings.show_status {
            self.statuses.clear();
        }
        if self.main_tray.is_none() {
            let menu = Menu::new();
            let mut ids = HashMap::new();
            let palette_label = match &self.settings.palette {
                Some(hotkey) => format!("Command palette  {hotkey}"),
                None => "Command palette".into(),
            };
            for (label, job) in [
                ("Open Unlaw", "home"),
                (palette_label.as_str(), "palette"),
                ("Settings…", "settings"),
                ("Reload", "reload"),
                ("Reset window positions", "reset-places"),
            ] {
                let item = MenuItem::new(label, true, None);
                ids.insert(item.id().clone(), job);
                let _ = menu.append(&item);
            }
            let _ = menu.append(&PredefinedMenuItem::separator());
            let _ = menu.append(&MenuItem::new(format!("Unlaw {}", env!("CARGO_PKG_VERSION")), false, None));
            let quit = MenuItem::new("Quit Unlaw", true, None);
            ids.insert(quit.id().clone(), "quit");
            let _ = menu.append(&quit);
            // Added to, never replaced: the app menu's ids (Quit ⌘Q, Settings ⌘,) live here too,
            // and replacing the map on a reload made ⌘Q do nothing.
            self.menu_ids.extend(ids);
            self.main_tray = TrayIconBuilder::new()
                .with_id("ul")
                .with_title("UL")
                .with_tooltip("Unlaw")
                .with_menu(Box::new(menu))
                .with_menu_on_left_click(true)
                .build()
                .ok();
        }
        for name in self.settings.menubar.clone().iter().rev() {
            // An application pinned from Open app: its own icon, a click opens it.
            if let Some(app) = settings::pinned_app(name) {
                let tray = TrayIconBuilder::new()
                    .with_id(name.as_str())
                    .with_tooltip(app)
                    .with_menu_on_left_click(false)
                    .with_menu_on_right_click(false)
                    .build();
                if let Ok(tray) = tray {
                    #[cfg(target_os = "macos")]
                    if !platform::set_app_icon(&tray, app) {
                        platform::set_symbol(&tray, "app");
                    }
                    self.trays.push((name.clone(), tray));
                }
                continue;
            }
            let Some((spec, _)) = self.specs.get(name).filter(|(spec, _)| spec.in_app) else { continue };
            let title = self.statuses.get(name).map(|status| status.text.clone()).unwrap_or_default();
            let tray = TrayIconBuilder::new()
                .with_id(format!("cmd:{name}"))
                .with_tooltip(&spec.title)
                .with_title(&title)
                .with_menu_on_left_click(false)
                .with_menu_on_right_click(false)
                .build();
            if let Ok(tray) = tray {
                let reading = self.statuses.get(name).and_then(|status| status.icon.clone());
                let icon = reading.clone().unwrap_or(spec.icon.clone());
                // ChatGPT, Telegram, Spotify...: the app's own icon in colour when it is installed.
                #[cfg(target_os = "macos")]
                if !(reading.is_none()
                    && spec.app_icon.as_deref().is_some_and(|app| platform::set_app_icon(&tray, app)))
                {
                    platform::set_symbol(&tray, &icon);
                }
                self.trays.push((name.clone(), tray));
            }
        }
    }

    fn pinned_specs(&self) -> Vec<(String, Option<Spec>)> {
        let spec = |name: &String| self.specs.get(name).map(|(spec, _)| spec.clone());
        self.settings.menubar.iter().map(|name| (name.clone(), spec(name))).collect()
    }

    /// A pinned command's status description; the System item's text comes from
    /// the readings chosen in Settings (`menubar.sys`).
    fn status_of(&self, name: &str) -> Option<spec::Status> {
        let Some((Spec { status: Some(status), in_app: true, .. }, _)) = self.specs.get(name) else { return None };
        let mut status = status.clone();
        if name == "sys" {
            // Only the parts the chosen readings use; none chosen = the icon alone, nothing to read.
            let sections = settings::sys_sections(&self.settings.sys);
            if sections.is_empty() {
                return None;
            }
            status.text = Some(settings::sys_template(&self.settings.sys).unwrap_or_default());
            status.args = sections.iter().map(|section| section.to_string()).chain(["--json".to_string()]).collect();
        }
        Some(status)
    }

    /// One status reading now (after an action of that command), next to its poller.
    fn refresh_status(&self, name: &str) {
        let Some(status) = self.status_of(name) else { return };
        let (Some(ul), true) = (self.ul.clone(), self.settings.show_status) else { return };
        let (name, proxy) = (name.to_string(), self.proxy.clone());
        let generation = self.generation.load(Ordering::SeqCst);
        thread::spawn(move || {
            let text = read_status(&ul, &name, &status);
            let _ = proxy.send_event(UserEvent::Status { name, generation, text });
        });
    }

    fn restart_status(&mut self) {
        let generation = self.generation.fetch_add(1, Ordering::SeqCst) + 1;
        if !self.settings.show_status {
            return;
        }
        let Some(ul) = self.ul.clone() else { return };
        for name in &self.settings.menubar {
            let Some(status) = self.status_of(name) else { continue };
            let (name, ul, proxy, current) = (name.clone(), ul.clone(), self.proxy.clone(), self.generation.clone());
            thread::spawn(move || {
                while current.load(Ordering::SeqCst) == generation {
                    let text = read_status(&ul, &name, &status);
                    if proxy.send_event(UserEvent::Status { name: name.clone(), generation, text }).is_err() {
                        return;
                    }
                    // Sleep in short steps so a reload stops this loop quickly.
                    for _ in 0..status.every * 4 {
                        if current.load(Ordering::SeqCst) != generation {
                            return;
                        }
                        thread::sleep(Duration::from_millis(250));
                    }
                }
            });
        }
    }

    fn on_status(&mut self, name: String, generation: u64, text: StatusText) {
        if generation != self.generation.load(Ordering::SeqCst) {
            return;
        }
        let changed = self.statuses.get(&name) != Some(&text);
        if let (true, Some((_, tray))) = (changed, self.trays.iter().find(|(pinned, _)| *pinned == name)) {
            tray.set_title(Some(&text.text));
            // A command with its app's icon keeps it unless the reading names an icon.
            let app_icon = self.specs.get(&name).and_then(|(spec, _)| spec.app_icon.clone());
            let icon = match (&text.icon, app_icon) {
                (None, Some(_)) => None,
                _ => text.icon.clone().or_else(|| self.specs.get(&name).map(|(spec, _)| spec.icon.clone())),
            };
            #[cfg(target_os = "macos")]
            if let Some(icon) = icon {
                platform::set_symbol(tray, &icon);
            }
        }
        if self.panel_for.as_deref() == Some(&name) {
            self.send(
                View::Panel,
                json!({"type": "status", "name": name, "status": {"text": text.text, "state": text.state}}),
            );
        }
        self.statuses.insert(name, text);
    }

    fn on_tray(&mut self, event: TrayIconEvent) {
        debug(&format!("tray {event:?}"));
        let TrayIconEvent::Click { id, rect, button, button_state: MouseButtonState::Up, .. } = event else { return };
        if let Some(app) = settings::pinned_app(&id.0).map(str::to_string) {
            self.run("app", vec![app], "Open", From::Elsewhere);
            return;
        }
        let Some(name) = id.0.strip_prefix("cmd:").map(str::to_string) else { return };
        let Some((spec, _)) = self.specs.get(&name) else { return };
        let opens = spec.open.is_some() && button == MouseButton::Left;
        let anchor = (rect.position, rect.size);
        if self.panel.window.is_visible() && self.panel_for.as_deref() == Some(&name) {
            self.panel.window.set_visible(false);
            return;
        }
        // Like KeepingYouAwake and Caffeine: a left click switches it, a right click opens the panel.
        // Without a status reading (statuses off) it cannot know which way to switch: the panel then.
        let state = self.statuses.get(&name).and_then(|status| status.state.clone());
        if let (Some(toggle), MouseButton::Left, Some(state)) = (spec.toggle.clone(), button, state) {
            self.run_action(&name, if state == "on" { &toggle.stop } else { &toggle.start }, From::Toggle);
            return;
        }
        // A view is the menu bar's own popover (System's tabs); the section is the big window.
        if spec.view.is_some() {
            self.show_panel(&name, Some(anchor));
            return;
        }
        if let Some(section) = spec.section.clone() {
            self.show_home(Some(&section));
            return;
        }
        if opens {
            self.open_page(&name);
        } else if let Some(id) = spec.only_action().map(|action| action.id.clone()) {
            self.run_action(&name, &id, From::Elsewhere);
        } else {
            self.open_panel(&name, Some(anchor));
        }
    }

    fn on_menu(&mut self, event: MenuEvent, target: &EventLoopWindowTarget<UserEvent>, control: &mut ControlFlow) {
        let _ = target;
        match self.menu_ids.get(&event.id).copied() {
            Some("palette") => self.show_palette(),
            Some("home") => self.show_home(None),
            Some(job) if job.starts_with("section:") => self.show_home(job.strip_prefix("section:")),
            Some(job) if job.starts_with("zoom:") => self.change_zoom(job.strip_prefix("zoom:").unwrap_or("reset")),
            Some("settings") => self.open_settings(),
            Some("reload") => {
                self.apply_settings();
                self.reload_commands();
            }
            Some("reset-places") => {
                self.places = Places::default();
                self.places.save();
            }
            Some("quit") => {
                self.shutdown();
                *control = ControlFlow::Exit;
            }
            _ => {}
        }
    }

    // ---------- hotkeys ----------

    fn pause_hotkeys(&mut self) {
        let Some(manager) = &self.hotkeys else { return };
        for (hotkey, _) in self.registered.drain(..) {
            let _ = manager.unregister(hotkey);
        }
    }

    fn register_hotkeys(&mut self) {
        let Some(manager) = &self.hotkeys else { return };
        for (hotkey, _) in self.registered.drain(..) {
            let _ = manager.unregister(hotkey);
        }
        self.hotkey_warnings.clear();
        let mut jobs: Vec<(Hotkey, HotkeyJob)> = Vec::new();
        if let Some(palette) = &self.settings.palette {
            jobs.push((palette.clone(), HotkeyJob::Palette));
        }
        for binding in &self.settings.bindings {
            jobs.push((binding.hotkey.clone(), HotkeyJob::Command(binding.command.clone(), binding.target.clone())));
        }
        for (hotkey, job) in jobs {
            let registered = os_hotkey(&hotkey)
                .ok_or_else(|| "no such key here".to_string())
                .and_then(|os| manager.register(os).map(|_| os).map_err(|error| error.to_string()));
            match registered {
                Ok(os) => self.registered.push((os, job)),
                Err(error) => {
                    let warning = format!("hotkey {hotkey}: {error} (taken by another app?)");
                    eprintln!("ul-app: {warning}");
                    self.hotkey_warnings.push(warning);
                }
            }
        }
    }

    fn on_hotkey(&mut self, event: GlobalHotKeyEvent) {
        debug(&format!("hotkey {} {:?}", event.id, event.state));
        if event.state != HotKeyState::Pressed {
            return;
        }
        let Some((_, job)) = self.registered.iter().find(|(hotkey, _)| hotkey.id() == event.id) else { return };
        match job {
            HotkeyJob::Palette => {
                if self.palette.window.is_visible() {
                    self.palette.window.set_visible(false);
                } else {
                    self.show_palette();
                }
            }
            HotkeyJob::Command(_, Target::Template(template)) => {
                let template = template.clone();
                self.launch_template(&template);
            }
            HotkeyJob::Command(name, target) => {
                let (name, target) = (name.clone(), target.clone());
                if self.specs.get(&name).is_some_and(|(spec, _)| !spec.in_app) {
                    self.toast(
                        "Unlaw",
                        &format!("ul {name} is a terminal command; run it in your terminal."),
                        false,
                        None,
                    );
                    return;
                }
                let section = self.specs.get(&name).and_then(|(spec, _)| spec.section.clone());
                match target {
                    Target::Panel if section.is_some() => self.show_home(section.as_deref()),
                    Target::Panel => match self.specs.get(&name).and_then(|(spec, _)| spec.only_action()) {
                        Some(action) => {
                            let id = action.id.clone();
                            self.run_action(&name, &id, From::Elsewhere)
                        }
                        None => self.open_panel(&name, None),
                    },
                    Target::Open => self.open_page(&name),
                    Target::Run => self.run(&name, Vec::new(), &name, From::Elsewhere),
                    Target::Action(id) => self.run_action(&name, &id, From::Elsewhere),
                    Target::Template(_) => {}
                }
            }
        }
    }

    // ---------- windows ----------

    /// The clipboard history for the palette's list (newest first, like `ul clip list`).
    fn palette_clips(&self) {
        let Some(ul) = self.ul.clone() else { return };
        let proxy = self.proxy.clone();
        thread::spawn(move || {
            let argv = ["clip", "list", "200", "--json", "--short"].map(String::from);
            let outcome = runner::run_capped(&ul, &argv, Duration::from_secs(10), runner::MAX_LIST_OUTPUT);
            let items =
                serde_json::from_str::<Json>(&outcome.stdout).ok().filter(|_| outcome.ok()).filter(Json::is_array);
            let message = match items {
                Some(items) => json!({"type": "clip-history", "items": items}),
                None => json!({"type": "clip-history", "items": [], "error": outcome.summary(3)}),
            };
            let _ = proxy.send_event(UserEvent::Palette(message));
        });
    }

    /// What the user opens (menu bar item, hotkey, tile, palette): a panel whose every
    /// part is a palette row is not shown; the palette lists the command's functions.
    fn open_panel(&mut self, name: &str, anchor: Option<(PhysicalPosition<f64>, PhysicalSize<u32>)>) {
        let Some((spec, _)) = self.specs.get(name).cloned() else { return };
        // A part of the main window (Arcade, Desk) opens there, never as a one-button panel.
        if let (None, Some(section)) = (&spec.view, spec.section.clone()) {
            self.palette.window.set_visible(false);
            self.show_home(Some(&section));
            return;
        }
        // A panel that would hold one button says nothing: do what it would do.
        if spec.view.is_none() && spec.panel.is_none() {
            if let Some(id) = spec.only_action().map(|action| action.id.clone()) {
                self.palette.window.set_visible(false);
                self.run_action(name, &id, From::Elsewhere); // ChatGPT, Lofi, Steam: open it
                return;
            }
            if spec.actions.is_empty() {
                self.run(name, Vec::new(), "Run", From::Elsewhere);
                return;
            }
        }
        if spec.palette_covers() {
            self.panel.window.set_visible(false);
            self.show_palette();
            self.send(View::Palette, json!({"type": "functions", "name": name}));
            return;
        }
        self.show_panel(name, anchor);
    }

    /// Start a template from a hotkey or the palette: `ul _template-launch`, which starts
    /// the template only (never a command of that name). A note says how it went.
    fn launch_template(&mut self, name: &str) {
        if !settings::template_name_ok(name) {
            return;
        }
        let Some(ul) = self.ul.clone() else { return };
        self.palette.window.set_visible(false);
        let (proxy, name) = (self.proxy.clone(), name.to_string());
        thread::spawn(move || {
            let outcome = runner::run(&ul, &["_template-launch".into(), name.clone()], Duration::from_secs(90));
            let text = if outcome.ok() { "Opened".to_string() } else { outcome.summary(2) };
            let _ = proxy.send_event(UserEvent::Toast { title: format!("Template {name}"), text, ok: outcome.ok() });
        });
    }

    /// Template names for the palette (it lists them as rows), read when it opens.
    fn send_templates_to_palette(&self) {
        let Some(ul) = self.ul.clone() else { return };
        let proxy = self.proxy.clone();
        thread::spawn(move || {
            let argv = ["template", "list", "--json"].map(String::from);
            let outcome = runner::run_capped(&ul, &argv, Duration::from_secs(10), runner::MAX_LIST_OUTPUT);
            let items: Vec<Json> = serde_json::from_str::<Json>(&outcome.stdout)
                .ok()
                .and_then(|list| list.as_array().cloned())
                .unwrap_or_default()
                .into_iter()
                .filter_map(|item| {
                    let name = item["name"].as_str().filter(|name| settings::template_name_ok(name))?;
                    Some(json!({"name": name, "path": item["path"], "focus": item["focus"]}))
                })
                .collect();
            let _ = proxy.send_event(UserEvent::Palette(json!({"type": "templates", "items": items})));
        });
    }

    /// The command's panel showing a run's whole output.
    fn show_panel_result(&mut self, name: &str, ok: bool, text: &str) {
        self.show_panel(name, None);
        self.send(View::Panel, json!({"type": "result", "name": name, "ok": ok, "text": text}));
    }

    /// A short note in the top-right corner of the screen under the cursor: the title,
    /// the first line of `text` (two at most), green or red. `more` = (command, ok, whole
    /// output): a click on the note opens the command's panel with all of it.
    fn toast(&mut self, title: &str, text: &str, ok: bool, more: Option<(String, String)>) {
        self.ensure_page(View::Toast);
        let lines: Vec<&str> = text.lines().map(str::trim).filter(|line| !line.is_empty()).collect();
        let shown = lines.iter().take(2).copied().collect::<Vec<_>>().join("\n");
        let longer = lines.len() > 2 || shown.chars().count() > 160;
        self.toast_more = more.filter(|_| longer || !ok).map(|(name, all)| (name, ok, all));
        self.toast_generation += 1;
        let window = &self.toast.window;
        if let Some(screen) = screen_under_cursor(window) {
            // Below the menu bar, at the right edge, where macOS shows its own notes.
            let x = screen.x + screen.width - TOAST_WIDTH - 12.0;
            window.set_outer_position(LogicalPosition::new(x, screen.y + 38.0));
        }
        self.send(
            View::Toast,
            json!({"type": "toast", "title": title, "text": shown, "ok": ok, "more": self.toast_more.is_some()}),
        );
        platform::show_without_focus(&self.toast.window);
        let (proxy, generation) = (self.proxy.clone(), self.toast_generation);
        let seconds = if ok { TOAST_SECONDS.0 } else { TOAST_SECONDS.1 } + u64::from(self.toast_more.is_some());
        thread::spawn(move || {
            thread::sleep(Duration::from_secs(seconds));
            let _ = proxy.send_event(UserEvent::ToastHide(generation));
        });
    }

    fn show_palette(&mut self) {
        self.palette_keep = false;
        self.panel.window.set_visible(false);
        self.end_drag();
        let window = &self.palette.window;
        if let Some(place) = self.places.palette.filter(|place| on_a_screen(window, *place, PALETTE_SIZE)) {
            window.set_outer_position(LogicalPosition::new(place.0, place.1));
        } else if let Some(screen) = screen_under_cursor(window) {
            let x = screen.x + (screen.width - PALETTE_SIZE.0) / 2.0;
            window.set_outer_position(LogicalPosition::new(x, screen.y + screen.height * 0.2));
        }
        window.set_visible(true);
        window.set_focus();
        self.send(View::Palette, json!({"type": "reset"}));
        // New or removed commands since the last look; ul answers in ~10 ms.
        self.reload_commands();
        self.send_templates_to_palette();
    }

    fn show_panel(&mut self, name: &str, anchor: Option<(PhysicalPosition<f64>, PhysicalSize<u32>)>) {
        let Some((spec, problem)) = self.specs.get(name).cloned() else { return };
        self.ensure_page(View::Panel);
        self.palette.window.set_visible(false);
        self.panel_for = Some(name.to_string());
        self.end_drag();
        self.view_first = true;
        let window = &self.panel.window;
        // Every panel starts at its normal width; only wide output widens it.
        let width = panel_width(spec.view.as_deref());
        let height = window.inner_size().to_logical::<f64>(window.scale_factor()).height;
        window.set_inner_size(LogicalSize::new(width, height));
        let panel_size = (width, height.max(120.0));
        // Under the menu bar item it was opened from; else where the user left it; else the screen's middle.
        // The place is kept as the panel's center line, so growing and shrinking never walks it sideways.
        let saved = self
            .places
            .panel
            .filter(|place| on_a_screen(window, (place.0 + (PANEL_WIDTH - width) / 2.0, place.1), panel_size));
        if let (None, Some(place)) = (anchor, saved) {
            self.panel_center = place.0 + PANEL_WIDTH / 2.0;
            window.set_outer_position(LogicalPosition::new(self.panel_center - width / 2.0, place.1));
        } else if let Some(screen) = screen_under_cursor(window) {
            let (center, y) = match anchor {
                // The menu bar item's rect, in pixels of the screen it is on.
                Some((position, size)) => (
                    (position.x + size.width as f64 / 2.0) / screen.scale,
                    (position.y + size.height as f64) / screen.scale + 6.0,
                ),
                None => (screen.x + screen.width / 2.0, screen.y + screen.height * 0.22),
            };
            let x = within(center - width / 2.0, screen.x + 8.0, screen.x + screen.width - width - 8.0);
            self.panel_center = x + width / 2.0;
            window.set_outer_position(LogicalPosition::new(x, y));
        }
        let status = self.statuses.get(name).map(|status| json!({"text": status.text, "state": status.state}));
        self.send(
            View::Panel,
            json!({"type": "panel", "spec": spec::to_json(&spec), "status": status,
                   "pinned": self.settings.menubar.contains(&spec.name), "problem": problem,
                   "busy": self.running.iter().any(|argv| argv.first() == Some(&spec.name))}),
        );
        self.panel.window.set_visible(true);
        self.panel.window.set_focus();
    }

    fn open_page(&mut self, name: &str) {
        if let Some(page) = self.pages.get_mut(name) {
            // A server that has quit leaves a blank window: start it again instead.
            if matches!(page.child.try_wait(), Ok(None)) {
                page.window.set_visible(true);
                page.window.set_focus();
                return;
            }
            self.pages.remove(name);
        }
        let (Some(ul), Some((spec, _))) = (self.ul.clone(), self.specs.get(name)) else { return };
        let Some(open) = &spec.open else { return };
        if self.opening.iter().any(|item| item == name) {
            return;
        }
        self.opening.push(name.to_string());
        self.palette.window.set_visible(false);
        self.panel.window.set_visible(false);
        let argv = command_line(name, &open.args);
        let (proxy, name) = (self.proxy.clone(), name.to_string());
        thread::spawn(move || {
            let result = runner::serve(&ul, &argv, SERVE_WAIT);
            // The app quit meanwhile: nobody will stop this server, so stop it here.
            if let Err(tao::event_loop::EventLoopClosed(UserEvent::Served { result: Ok((mut child, _)), .. })) =
                proxy.send_event(UserEvent::Served { name, result })
            {
                runner::stop_group(&mut child, Duration::from_secs(5));
            }
        });
    }

    fn on_served(
        &mut self,
        target: &EventLoopWindowTarget<UserEvent>,
        name: String,
        result: Result<(Child, String), String>,
    ) {
        self.opening.retain(|item| *item != name);
        let title = self.specs.get(&name).map(|(spec, _)| spec.title.clone()).unwrap_or_else(|| name.clone());
        let (mut child, url) = match result {
            Ok(served) => served,
            Err(error) => {
                self.toast(&title, &format!("Could not open: {error}"), false, None);
                return;
            }
        };
        let window = WindowBuilder::new()
            .with_title(&title)
            .with_inner_size(LogicalSize::new(1280.0, 820.0))
            .with_min_inner_size(LogicalSize::new(640.0, 420.0))
            .build(target);
        let window = match window {
            Ok(window) => window,
            Err(error) => {
                runner::stop_group(&mut child, Duration::from_secs(3));
                self.toast(&title, &error.to_string(), false, None);
                return;
            }
        };
        let webview = page_builder(&url, self.proxy.clone(), name.clone()).build(&window);
        match webview {
            Ok(webview) => {
                window.set_focus();
                self.pages.insert(name, Page { window, _webview: webview, child, url, opened: None });
            }
            Err(error) => {
                runner::stop_group(&mut child, Duration::from_secs(3));
                self.toast(&title, &error.to_string(), false, None);
            }
        }
    }

    /// The page's main frame went to another site: show that in the browser (at
    /// most once per 2 s, so a page cannot flood it with tabs) and load the page again.
    fn on_page_left(&mut self, name: &str, url: &str) {
        if name == HOME_DESK {
            self.desk_left(url);
            return;
        }
        let Some(page) = self.pages.get_mut(name) else { return };
        if page.opened.is_none_or(|last| last.elapsed() >= Duration::from_secs(2)) {
            page.opened = Some(Instant::now());
            platform::open_link(url);
        }
        let _ = page._webview.load_url(&page.url);
    }

    fn close_page(&mut self, id: WindowId) {
        let Some(name) = self.pages.iter().find(|(_, page)| page.window.id() == id).map(|(name, _)| name.clone())
        else {
            return;
        };
        if let Some(page) = self.pages.remove(&name) {
            let Page { window, _webview, mut child, .. } = page;
            drop(_webview);
            drop(window);
            // Stopping may take seconds; the menu bar and hotkeys stay live meanwhile.
            thread::spawn(move || runner::stop_group(&mut child, Duration::from_secs(5)));
        }
    }

    /// Settings live in the main window; ⌘, the menus and the palette open it there.
    fn open_settings(&mut self) {
        self.palette.window.set_visible(false);
        self.show_home(Some("settings"));
    }

    /// app.toml in the text editor, for what the Settings page does not cover.
    fn open_settings_file(&mut self) {
        let path = settings::path();
        if !path.exists() {
            if let Err(error) = write_settings(settings::DEFAULT) {
                self.toast("Unlaw", &format!("Could not create {}: {error}", path.display()), false, None);
                return;
            }
        }
        self.palette.window.set_visible(false);
        platform::open_text(&path);
    }

    // ---------- running ----------

    fn run(&mut self, name: &str, args: Vec<String>, label: &str, from: From) {
        let Some(ul) = self.ul.clone() else { return };
        let title = self.specs.get(name).map(|(spec, _)| spec.title.clone()).unwrap_or_else(|| name.to_string());
        if self.specs.get(name).is_some_and(|(spec, _)| spec.terminal) {
            self.terminal(name, args);
            return;
        }
        if from == From::Panel {
            self.send(
                View::Panel,
                json!({"type": "result", "name": name, "busy": true, "ok": true, "text": format!("{label}…")}),
            );
        } else {
            self.palette.window.set_visible(false);
        }
        let argv = command_line(name, &args);
        if self.running.contains(&argv) {
            // The same run is still going (a double click, a repeated hotkey). A panel showing
            // "label…" gets an answer now: the first run may be a quiet toggle that never reports.
            if from == From::Panel {
                self.send(View::Panel, json!({"type": "result", "name": name, "ok": true, "text": "Already running."}));
            }
            return;
        }
        self.running.push(argv.clone());
        let (proxy, name, label) = (self.proxy.clone(), name.to_string(), format!("{title}: {label}"));
        thread::spawn(move || {
            let outcome = runner::run(&ul, &argv, ACTION_TIMEOUT);
            let _ = proxy.send_event(UserEvent::Finished {
                name,
                label,
                argv,
                outcome,
                quiet: from == From::Toggle,
                quick: from == From::Quick,
            });
        });
    }

    /// The palette's inline input: `value` into the command's quick field, the
    /// other fields on their defaults, through the same checks as a panel button.
    /// A palette row of a form (`Spec::choices`): `button` + `fixed` name the row (only
    /// rows the spec offers are run), `value` is the typed text. Without `button`, the
    /// command's first input (`name text` typed in the search bar).
    fn run_quick(&mut self, name: &str, message: &Json) {
        self.palette_keep = false;
        let value = message["value"].as_str().unwrap_or("");
        let Some((spec, _)) = self.specs.get(name).cloned() else { return };
        let (Some(quick), Some(panel)) = (spec.quick(), spec.panel.as_ref()) else { return };
        if spec.view.is_some() {
            // A view (weather) searches in its own panel.
            self.palette.window.set_visible(false);
            self.show_panel(name, None);
            self.send(View::Panel, json!({"type": "view-query", "name": name, "value": value}));
            return;
        }
        let choices = spec.choices();
        let choice = match message["button"].as_u64() {
            Some(index) => {
                let fixed: Vec<(String, String)> = message["fixed"]
                    .as_object()
                    .map(|map| {
                        map.iter().map(|(id, option)| (id.clone(), option.as_str().unwrap_or("").to_string())).collect()
                    })
                    .unwrap_or_default();
                choices.iter().find(|choice| choice.button as u64 == index && choice.fixed == fixed)
            }
            None => choices.iter().find(|choice| choice.button == quick.button),
        };
        let Some(choice) = choice.cloned() else { return };
        let mut input = serde_json::Map::new();
        // Empty text keeps the field's default (the timer's 25m) instead of clearing it.
        if let (Some(field), false) = (&choice.field, value.trim().is_empty()) {
            input.insert(field.clone(), json!(value));
        }
        for (id, option) in &choice.fixed {
            input.insert(id.clone(), json!(option));
        }
        let button = &panel.buttons[choice.button];
        let argv = spec::values_from(&Json::Object(input), &spec).and_then(|values| {
            match spec::missing(panel, button, &values) {
                Some(problem) => Err(problem),
                None => args::expand(&button.args, &spec::argument_values(panel, &values)),
            }
        });
        match argv {
            Ok(argv) => self.run(name, argv, &choice.label, From::Quick),
            Err(error) => self.send(View::Palette, json!({"type": "quick-error", "text": error})),
        }
    }

    /// Dropped files go to the palette page as text for its inline input.
    fn on_dropped(&mut self, paths: Vec<PathBuf>) {
        let paths: Vec<String> = paths.iter().filter_map(|path| path.to_str().map(str::to_string)).take(16).collect();
        if !paths.is_empty() && self.palette.window.is_visible() {
            self.palette.window.set_focus();
            self.send(View::Palette, json!({"type": "dropped", "paths": paths}));
        }
    }

    fn run_action(&mut self, name: &str, id: &str, from: From) {
        let Some((spec, _)) = self.specs.get(name) else { return };
        let Some(action) = spec.actions.iter().find(|action| action.id == id).cloned() else { return };
        // Only the panel can ask; a hotkey or the menu opens it for an action that must be confirmed.
        if action.confirm.is_some() && from != From::Panel {
            self.show_panel(name, None);
            return;
        }
        self.run(name, action.args, &action.label, from);
    }

    fn on_finished(
        &mut self,
        name: String,
        label: String,
        argv: Vec<String>,
        outcome: Outcome,
        quiet: bool,
        quick: bool,
    ) {
        self.running.retain(|running| *running != argv);
        // The command's panel, when open, gets the result whoever started the run
        // (it was told the run was busy and disabled its buttons).
        let text = outcome.summary(40);
        let long = text.lines().filter(|line| !line.trim().is_empty()).count() > 2 || text.chars().count() > 160;
        if quiet && outcome.ok() {
            // The menu bar icon shows it.
        } else if self.panel.window.is_visible() && self.panel_for.as_deref() == Some(&name) {
            self.send(View::Panel, json!({"type": "result", "name": name, "ok": outcome.ok(), "text": text}));
        } else if outcome.ok() && long {
            // A table (top processes, a forecast) is read in the panel, never squeezed into a note.
            self.show_panel_result(&name, true, &text);
        } else if outcome.ok() {
            // Opening an app or a link prints nothing: a quick run then says nothing.
            if !text.trim().is_empty() || !quick {
                self.toast(&label, if text.trim().is_empty() { "Done" } else { &text }, true, None);
            }
        } else {
            let first = text.lines().find(|line| !line.trim().is_empty()).unwrap_or("Failed").to_string();
            self.toast(&label, &first, false, Some((name.clone(), text)));
        }
        // A command that changed something often changes its status too.
        if self.settings.menubar.contains(&name) {
            self.refresh_status(&name);
        }
    }

    /// The reads of the open panel's view, answered as one message (`type: view-data`).
    fn view_reads(&mut self, name: &str) {
        let Some(view) = self.specs.get(name).and_then(|(spec, _)| spec.view.clone()) else { return };
        // Only for the panel on screen; a hidden panel is told to stop its timer
        // (opening it again starts the view anew).
        if !self.panel.window.is_visible() || self.panel_for.as_deref() != Some(name) {
            self.send(View::Panel, json!({"type": "view-stop"}));
            return;
        }
        if view == "system" {
            // The shared watch pushes every round (`on_sys_data`); a popover opened while
            // it runs gets the newest round at once.
            let first = std::mem::take(&mut self.view_first);
            self.ensure_sys_feed();
            let latest = self.sys_latest();
            if let (true, Some(data)) = (first, latest) {
                self.send(
                    View::Panel,
                    json!({"type": "view-data", "name": name, "data": {"sys": data}, "error": null}),
                );
            }
            return;
        }
        if self.view_reading {
            return;
        }
        let Some(ul) = self.ul.clone() else { return };
        let reads = views::reads(&view, std::mem::take(&mut self.view_first));
        self.view_reading = true;
        let (name, proxy) = (name.to_string(), self.proxy.clone());
        thread::spawn(move || {
            let mut data = json!({});
            let mut errors = Vec::new();
            for (key, argv) in reads {
                let outcome = runner::run(&ul, &argv, Duration::from_secs(20));
                if key == "lid" {
                    data[key] = json!(outcome.ok());
                    continue;
                }
                match serde_json::from_str::<Json>(&outcome.stdout) {
                    Ok(value) if outcome.ok() => data[key] = value,
                    _ => errors.push(outcome.summary(3)),
                }
            }
            let message = json!({"type": "view-data", "name": name, "data": data, "error": errors.first()});
            let _ = proxy.send_event(UserEvent::Panel { name, message, changed: false });
        });
    }

    /// A view's button: `views::act` checks the values and builds the argv.
    fn view_act(&mut self, name: &str, message: &Json) {
        let Some(view) = self.specs.get(name).and_then(|(spec, _)| spec.view.clone()) else { return };
        let Some(ul) = self.ul.clone() else { return };
        let argv = match views::act(&view, message) {
            Ok(argv) => argv,
            Err(error) => {
                self.send(View::Panel, json!({"type": "view-done", "name": name, "ok": false, "text": error}));
                return;
            }
        };
        if self.running.contains(&argv) {
            // The view waits for an answer with its buttons off: never leave it hanging.
            self.send(View::Panel, json!({"type": "view-done", "name": name, "ok": true, "text": "Already running."}));
            return;
        }
        self.running.push(argv.clone());
        let (name, proxy) = (name.to_string(), self.proxy.clone());
        thread::spawn(move || {
            let outcome = runner::run(&ul, &argv, Duration::from_secs(60));
            // A view that reads (weather's forecast) gets the command's JSON too.
            let data = serde_json::from_str::<Json>(&outcome.stdout).ok().filter(Json::is_object);
            let message = json!({"type": "view-done", "name": name, "ok": outcome.ok(), "text": outcome.summary(6),
                "argv": argv, "json": data});
            let _ = proxy.send_event(UserEvent::Panel { name, message, changed: true });
        });
    }

    fn on_panel_data(&mut self, name: &str, message: Json, changed: bool) {
        if changed {
            if let Some(argv) = message["argv"].as_array() {
                let argv: Vec<String> = argv.iter().filter_map(|word| word.as_str().map(str::to_string)).collect();
                self.running.retain(|running| *running != argv);
            }
            if self.settings.menubar.iter().any(|item| item == name) {
                self.refresh_status(name);
            }
        } else {
            self.view_reading = false;
        }
        self.send(View::Panel, message);
    }

    fn terminal(&mut self, name: &str, args: Vec<String>) {
        let Some(ul) = self.ul.clone() else { return };
        self.palette.window.set_visible(false);
        self.panel.window.set_visible(false);
        let argv = command_line(name, &args);
        // osascript may wait for the Automation permission prompt: never on the UI thread.
        let proxy = self.proxy.clone();
        thread::spawn(move || {
            if let Err(error) = platform::open_terminal(&ul, &argv) {
                let _ = proxy.send_event(UserEvent::Toast { title: "Unlaw".into(), text: error, ok: false });
            }
        });
    }

    /// The menus at the top of the screen while Unlaw is the active Dock app:
    /// Quit goes through `shutdown` (page servers stop), Edit gives text fields
    /// copy and paste, View switches the main window's parts.
    fn build_app_menu(&mut self) {
        use tray_icon::menu::accelerator::Accelerator;
        use tray_icon::menu::Submenu;
        let item = |ids: &mut HashMap<MenuId, &'static str>, label: &str, job: &'static str, keys: Option<&str>| {
            let accelerator = keys.and_then(|keys| keys.parse::<Accelerator>().ok());
            let item = MenuItem::new(label, true, accelerator);
            ids.insert(item.id().clone(), job);
            item
        };
        let mut ids = HashMap::new();
        let menu = Menu::new();
        let app = Submenu::new("Unlaw", true);
        let _ = app.append_items(&[
            &PredefinedMenuItem::about(Some("About Unlaw"), None),
            &PredefinedMenuItem::separator(),
            &item(&mut ids, "Settings…", "settings", Some("CmdOrCtrl+Comma")),
            &item(&mut ids, "Command palette", "palette", None),
            &PredefinedMenuItem::separator(),
            &PredefinedMenuItem::hide(None),
            &PredefinedMenuItem::hide_others(None),
            &PredefinedMenuItem::show_all(None),
            &PredefinedMenuItem::separator(),
            &item(&mut ids, "Quit Unlaw", "quit", Some("CmdOrCtrl+Q")),
        ]);
        let edit = Submenu::new("Edit", true);
        let _ = edit.append_items(&[
            &PredefinedMenuItem::undo(None),
            &PredefinedMenuItem::redo(None),
            &PredefinedMenuItem::separator(),
            &PredefinedMenuItem::cut(None),
            &PredefinedMenuItem::copy(None),
            &PredefinedMenuItem::paste(None),
            &PredefinedMenuItem::select_all(None),
        ]);
        let view = Submenu::new("View", true);
        let _ = view.append_items(&[
            &item(&mut ids, "Commands", "section:commands", Some("CmdOrCtrl+1")),
            &item(&mut ids, "Templates", "section:templates", Some("CmdOrCtrl+2")),
            &item(&mut ids, "System", "section:system", Some("CmdOrCtrl+3")),
            &item(&mut ids, "Clipboard", "section:clipboard", Some("CmdOrCtrl+4")),
            &item(&mut ids, "Arcade", "section:games", Some("CmdOrCtrl+5")),
            &item(&mut ids, "Board", "section:board", Some("CmdOrCtrl+6")),
            &item(&mut ids, "Today", "section:today", Some("CmdOrCtrl+7")),
            &item(&mut ids, "Canvas", "section:canvas", Some("CmdOrCtrl+8")),
            &item(&mut ids, "Studio", "section:studio", Some("CmdOrCtrl+9")),
            &item(&mut ids, "Edit", "section:edit", Some("CmdOrCtrl+E")),
            &PredefinedMenuItem::separator(),
            &item(&mut ids, "Bigger", "zoom:in", Some("CmdOrCtrl+Equal")),
            &item(&mut ids, "Smaller", "zoom:out", Some("CmdOrCtrl+Minus")),
            &item(&mut ids, "Actual Size", "zoom:reset", Some("CmdOrCtrl+Shift+Digit0")),
        ]);
        let window = Submenu::new("Window", true);
        let _ = window.append_items(&[
            &PredefinedMenuItem::minimize(None),
            &PredefinedMenuItem::close_window(None),
            &PredefinedMenuItem::separator(),
            &item(&mut ids, "Unlaw", "home", Some("CmdOrCtrl+0")),
        ]);
        let _ = menu.append_items(&[&app, &edit, &view, &window]);
        #[cfg(target_os = "macos")]
        {
            menu.init_for_nsapp();
            window.set_as_windows_menu_for_nsapp();
        }
        self.menu_ids.extend(ids);
        self.app_menu = Some(menu);
    }

    /// app.toml read again (edited, or Reload): keys, menu bar, statuses and the
    /// open panel's Pin button all follow it.
    fn apply_settings(&mut self) {
        self.load_settings();
        self.refresh_colors();
        self.register_hotkeys();
        self.main_tray = None;
        self.rebuild_trays();
        self.restart_status();
        self.send_list();
        self.desk_theme();
        self.apply_zoom();
        if let Some(name) = self.panel_for.clone() {
            let pinned = self.settings.menubar.contains(&name);
            self.send(View::Panel, json!({"type": "pinned", "name": name, "pinned": pinned}));
        }
    }

    /// A page window whose server ended (crashed, or an update stopped it) is
    /// closed with a note instead of staying blank.
    fn check_pages(&mut self) {
        self.check_desk();
        self.unload_hidden();
        self.stop_unused_sys_feed();
        let ended: Vec<String> = self
            .pages
            .iter_mut()
            .filter_map(|(name, page)| (!matches!(page.child.try_wait(), Ok(None))).then(|| name.clone()))
            .collect();
        for name in ended {
            if let Some(page) = self.pages.remove(&name) {
                let title = self.specs.get(&name).map(|(spec, _)| spec.title.clone()).unwrap_or_else(|| name.clone());
                drop(page);
                self.toast(&title, "The page stopped; open it again from the menu bar or the palette.", false, None);
            }
        }
    }

    fn set_pinned(&mut self, name: &str, pinned: bool) {
        // Open app on the menu bar is a shortcut to one app: the palette asks which.
        if pinned && name == "app" {
            self.panel.window.set_visible(false);
            self.show_palette();
            self.send(View::Palette, json!({"type": "pin-app"}));
            return;
        }
        if pinned && settings::pinned_app(name).is_none() && self.specs.get(name).is_some_and(|(spec, _)| !spec.in_app)
        {
            return;
        }
        let changed =
            settings_text()
                .and_then(|text| if pinned { settings::pin(&text, name) } else { settings::unpin(&text, name) });
        match changed.and_then(|text| write_settings(&text)) {
            Ok(()) => {
                self.own_write = modified(&settings::path());
                self.load_settings();
                self.rebuild_trays();
                self.restart_status();
                self.send_list();
                self.send(View::Panel, json!({"type": "pinned", "name": name, "pinned": pinned}));
            }
            Err(error) => self.toast("Unlaw", &format!("Could not change app.toml: {error}"), false, None),
        }
    }

    fn on_ipc(&mut self, view: View, body: String) {
        debug(&format!("{} says {body}", view.name()));
        let Ok(message) = serde_json::from_str::<Json>(&body) else { return };
        let op = message["op"].as_str().unwrap_or("");
        if view == View::Home && (self.on_edit_op(op, &message) || self.on_home_op(op, &message)) {
            return;
        }
        let name = message["name"].as_str().unwrap_or("").to_string();
        // The palette asks too: a confirmed action there was answered with a second Enter.
        let asked = view == View::Palette && op == "action" && message["confirmed"].as_bool() == Some(true);
        let from = if view == View::Panel || asked { From::Panel } else { From::Elsewhere };
        // The page names only commands the app shows: never a terminal-only one. Ops that act
        // on a command need its name (`run` with none would have started `ul ""`).
        // `app:Safari` is an application pinned from Open app (pin/unpin only).
        let app_pin = matches!(op, "pin" | "unpin") && settings::pinned_app(&name).is_some();
        if !name.is_empty() && !app_pin && !self.specs.get(&name).is_some_and(|(spec, _)| spec.in_app) {
            return;
        }
        let needs_name = matches!(
            op,
            "run"
                | "terminal"
                | "action"
                | "submit"
                | "quick"
                | "panel"
                | "default"
                | "pin"
                | "unpin"
                | "command-settings"
        );
        if needs_name && name.is_empty() {
            return;
        }
        match op {
            "ready" if view == View::Home => {
                self.home.ready = true;
                let pending = std::mem::take(&mut self.home.pending);
                let mut init = self.list_json();
                init["type"] = json!("init");
                init["theme"] = json!(self.theme());
                init["colors"] = self.ui_colors.clone().unwrap_or(Json::Null);
                init["version"] = json!(env!("CARGO_PKG_VERSION"));
                init["update"] = self.home_state.update.clone().unwrap_or(Json::Null);
                init["section"] = json!(self.home_state.section);
                self.send(view, init);
                for message in
                    pending.into_iter().filter(|message| message["type"] != "list" && message["type"] != "section")
                {
                    self.send(view, message);
                }
            }
            "ready" => {
                let glass = self.glass_mut(view);
                glass.ready = true;
                let pending = std::mem::take(&mut glass.pending);
                self.send(
                    view,
                    json!({"type": "init", "view": view.name(), "theme": self.theme(),
                           "colors": self.ui_colors.clone().unwrap_or(Json::Null)}),
                );
                if view == View::Palette {
                    let list = self.list_json();
                    self.send(view, list);
                }
                for message in pending.into_iter().filter(|message| message["type"] != "list") {
                    self.send(view, message);
                }
            }
            "theme" => self.send(view, json!({"type": "theme", "theme": self.theme()})),
            "log" => {
                let text: String = message["text"].as_str().unwrap_or("").chars().take(400).collect();
                eprintln!("ul-app: {} page: {}", view.name(), runner::strip_ansi(&text));
            }
            "drag" if view == View::Home => {
                let _ = self.home.window.drag_window();
            }
            "drag" => {
                self.dragging = Some(view);
                let window = match view {
                    View::Palette => &self.palette.window,
                    View::Home => &self.home.window,
                    _ => &self.panel.window,
                };
                let _ = window.drag_window();
            }
            "zoom" if view == View::Home => {
                let window = &self.home.window;
                window.set_maximized(!window.is_maximized());
            }
            "hide" => {
                match view {
                    View::Palette => {
                        self.palette_keep = false;
                        self.palette.window.set_visible(false);
                    }
                    View::Panel => self.panel.window.set_visible(false),
                    View::Home => self.hide_home(),
                    View::Toast => self.toast.window.set_visible(false),
                }
                self.end_drag();
            }
            "resize" if view == View::Toast => {
                let height = message["height"].as_f64().unwrap_or(64.0).clamp(44.0, 160.0);
                let window = &self.toast.window;
                let scale = window.scale_factor();
                let top = window.outer_position().ok().map(|position| position.to_logical::<f64>(scale));
                window.set_inner_size(LogicalSize::new(TOAST_WIDTH, height));
                if let Some(top) = top {
                    window.set_outer_position(LogicalPosition::new(top.x, top.y));
                }
            }
            "toast-click" if view == View::Toast => {
                self.toast.window.set_visible(false);
                if let Some((name, ok, text)) = self.toast_more.take() {
                    self.show_panel(&name, None);
                    self.send(View::Panel, json!({"type": "result", "name": name, "ok": ok, "text": text}));
                }
            }
            "settings" => self.open_settings(),
            // Right-click in the palette: the command's sheet (shortcuts, menu bar) in the main window.
            "command-settings" => {
                self.show_home(Some("commands"));
                self.send(View::Home, json!({"type": "command-sheet", "name": name}));
            }
            "resize" if view == View::Palette => {
                // As tall as its rows; the top edge stays where it is (macOS keeps the bottom).
                let height = message["height"].as_f64().unwrap_or(PALETTE_SIZE.1).clamp(96.0, PALETTE_SIZE.1);
                let window = &self.palette.window;
                let scale = window.scale_factor();
                let top = window.outer_position().ok().map(|position| position.to_logical::<f64>(scale));
                window.set_inner_size(LogicalSize::new(PALETTE_SIZE.0, height));
                if let Some(top) = top {
                    window.set_outer_position(LogicalPosition::new(top.x, top.y));
                }
            }
            "resize" if view == View::Panel => {
                let height = message["height"].as_f64().unwrap_or(300.0).clamp(120.0, 720.0);
                let window = &self.panel.window;
                let scale = window.scale_factor();
                let old = window.inner_size().to_logical::<f64>(scale).width;
                // Wide output (a table) may widen the panel; anything else keeps the width it has.
                let width = match message["width"].as_f64() {
                    Some(width) => width.clamp(300.0, PANEL_MAX_WIDTH),
                    None => old,
                };
                let height = if message["fixed"].as_bool() == Some(true) {
                    message["height"].as_f64().unwrap_or(height).clamp(120.0, 900.0)
                } else {
                    height
                };
                // A drag is over by now; the move below is the app's, not the user's.
                self.end_drag();
                let window = &self.panel.window;
                if (width - old).abs() >= 1.0 {
                    // Grow and shrink around the center it was placed on (never from the
                    // current left edge: that walked the panel left a little every time).
                    if let (Ok(position), Some(monitor)) = (window.outer_position(), window.current_monitor()) {
                        let position = position.to_logical::<f64>(scale);
                        let (left, size) =
                            (monitor.position().to_logical::<f64>(scale), monitor.size().to_logical::<f64>(scale));
                        let x =
                            within(self.panel_center - width / 2.0, left.x + 8.0, left.x + size.width - width - 8.0);
                        window.set_outer_position(LogicalPosition::new(x, position.y));
                    }
                }
                window.set_inner_size(LogicalSize::new(width, height));
            }
            "default" => {
                let Some((spec, _)) = self.specs.get(&name) else { return };
                if let Some(section) = spec.section.clone() {
                    self.show_home(Some(&section));
                } else if spec.terminal {
                    self.terminal(&name, Vec::new());
                } else if spec.open.is_some() {
                    self.open_page(&name);
                } else if let Some(id) = spec.only_action().map(|action| action.id.clone()) {
                    self.palette.window.set_visible(false);
                    self.run_action(&name, &id, from);
                } else if spec.panel.is_some() || !spec.actions.is_empty() {
                    self.open_panel(&name, None);
                } else {
                    self.run(&name, Vec::new(), "Run", from);
                }
            }
            "run" => self.run(&name, Vec::new(), "Run", from),
            "view-data" if view == View::Panel => self.view_reads(&name),
            "view-act" if view == View::Panel => self.view_act(&name, &message),
            "view-terminal" if view == View::Panel && name == "awake" => {
                // The lid rule needs the user's password once: only a terminal can ask for it.
                self.terminal(&name, vec!["lid".into(), "setup".into()]);
            }
            "action" => {
                let id = message["id"].as_str().unwrap_or("").to_string();
                self.run_action(&name, &id, from);
            }
            "submit" => {
                let Some((spec, _)) = self.specs.get(&name).cloned() else { return };
                let index = message["button"].as_u64().unwrap_or(u64::MAX) as usize;
                let Some(button) = spec.panel.as_ref().and_then(|panel| panel.buttons.get(index)).cloned() else {
                    return;
                };
                let panel = spec.panel.as_ref().expect("a button belongs to a panel");
                let argv = spec::values_from(&message["values"], &spec).and_then(|values| {
                    match spec::missing(panel, &button, &values) {
                        Some(problem) => Err(problem),
                        None => args::expand(&button.args, &spec::argument_values(panel, &values)),
                    }
                });
                match argv {
                    Ok(argv) => self.run(&name, argv, &button.label, from),
                    Err(error) => {
                        self.send(View::Panel, json!({"type": "result", "name": name, "ok": false, "text": error}))
                    }
                }
            }
            "quick" if view == View::Palette => self.run_quick(&name, &message),
            // The palette stays on screen while its inline input waits (a file dragged from Finder).
            "clip-history" if view == View::Palette => self.palette_clips(),
            "clip-copy" if view == View::Palette => {
                // Copy a history item again by its id (checked by clip_args), then get out of the way.
                let Some(argv) = home::clip_args("copy", message["id"].as_str()) else { return };
                let Some(ul) = self.ul.clone() else { return };
                self.palette_keep = false;
                self.palette.window.set_visible(false);
                let proxy = self.proxy.clone();
                thread::spawn(move || {
                    let outcome = runner::run(&ul, &argv, Duration::from_secs(30));
                    let (text, ok) =
                        if outcome.ok() { ("Copied".to_string(), true) } else { (outcome.summary(2), false) };
                    let _ = proxy.send_event(UserEvent::Toast { title: "Clipboard".into(), text, ok });
                });
            }
            "template-launch" if view == View::Palette => {
                let template = message["template"].as_str().unwrap_or("").to_string();
                self.launch_template(&template);
            }
            "keep" if view == View::Palette => self.palette_keep = message["on"].as_bool() == Some(true),
            "panel" => self.open_panel(&name, None),
            "open" => self.open_page(&name),
            "terminal" => self.terminal(&name, Vec::new()),
            "pin" => self.set_pinned(&name, true),
            "unpin" => self.set_pinned(&name, false),
            _ => {}
        }
    }

    /// A downloaded Unlaw.app without ul on this Mac installs the command line
    /// it carries (the two halves belong together). True when it started.
    fn install_bundled_cli(&mut self) -> bool {
        if self.ul.is_some() {
            return false;
        }
        let Some(bin) = std::env::current_exe().ok().and_then(|exe| unlaw_app::setup::bundled_bin(&exe)) else {
            return false;
        };
        let target = settings::home().join(".local").join("bin");
        let proxy = self.proxy.clone();
        thread::spawn(move || {
            let result = unlaw_app::setup::install_cli(&bin, &target).map_err(|error| error.to_string());
            if result.is_ok() {
                let ul = target.join("ul");
                // PATH line and shell integration, default commands, the agent skill.
                for step in [&["doctor", "--fix"][..], &["init"], &["skills", "install"]] {
                    let argv: Vec<String> = step.iter().map(|word| word.to_string()).collect();
                    runner::run(&ul, &argv, Duration::from_secs(120));
                }
            }
            let _ = proxy.send_event(UserEvent::CliInstalled(result));
        });
        true
    }

    fn on_cli_installed(&mut self, result: Result<Vec<String>, String>) {
        match result {
            Ok(copied) => {
                self.ul = runner::find_ul();
                self.toast(
                    "Unlaw",
                    &format!(
                        "The command line is installed in ~/.local/bin ({}). Open a new terminal and run: ul",
                        copied.join(", ")
                    ),
                    true,
                    None,
                );
            }
            Err(error) => self.toast("Unlaw", &format!("Could not install the command line: {error}"), false, None),
        }
        self.reload_commands();
    }

    /// The last place of a drag is written even if it came within the 0.5 s throttle.
    fn end_drag(&mut self) {
        if self.dragging.take().is_some() {
            self.places.save();
        }
    }

    /// A move of the palette or panel during a drag the user started: remember it.
    fn on_moved(&mut self, id: WindowId) {
        let view = if id == self.palette.window.id() {
            View::Palette
        } else if id == self.panel.window.id() {
            View::Panel
        } else {
            return;
        };
        if self.dragging != Some(view) {
            return; // the app placed it
        }
        let window = if view == View::Palette { &self.palette.window } else { &self.panel.window };
        let Ok(position) = window.outer_position() else { return };
        let scale = window.scale_factor();
        let position = position.to_logical::<f64>(scale);
        match view {
            View::Palette => self.places.palette = Some((position.x, position.y)),
            View::Toast => {}
            View::Panel | View::Home => {
                // Kept as the left edge of a normal-width panel on the same center line.
                let width = window.inner_size().to_logical::<f64>(scale).width;
                self.panel_center = position.x + width / 2.0;
                self.places.panel = Some((self.panel_center - PANEL_WIDTH / 2.0, position.y));
            }
        }
        self.places.save_soon();
    }

    fn shutdown(&mut self) {
        self.places.save();
        self.generation.fetch_add(1, Ordering::SeqCst);
        // All page commands (and the main window's game and desk) stop together,
        // within one 5 s deadline.
        let mut children: Vec<Child> = self.pages.drain().map(|(_, page)| page.child).collect();
        children.extend(self.home_children());
        children.extend(self.edit_children());
        let stopping: Vec<_> = children
            .into_iter()
            .map(|mut child| thread::spawn(move || runner::stop_group(&mut child, Duration::from_secs(5))))
            .collect();
        for thread in stopping {
            let _ = thread.join();
        }
    }
}

/// Where the user dragged the palette and the panel, in points. Kept in
/// `<config>/.app-windows.json`; the menu's "Reset window positions" forgets them.
#[derive(Default)]
struct Places {
    palette: Option<(f64, f64)>,
    panel: Option<(f64, f64)>,
    saved: Option<Instant>,
}

impl Places {
    fn path() -> PathBuf {
        settings::config_dir().join(".app-windows.json")
    }

    fn load() -> Places {
        let json: Json = fs::read_to_string(Places::path())
            .ok()
            .and_then(|text| serde_json::from_str(&text).ok())
            .unwrap_or(Json::Null);
        let point = |key: &str| -> Option<(f64, f64)> {
            let pair = json.get(key)?.as_array()?;
            let (x, y) = (pair.first()?.as_f64()?, pair.get(1)?.as_f64()?);
            (x.is_finite() && y.is_finite()).then_some((x, y))
        };
        Places { palette: point("palette"), panel: point("panel"), saved: None }
    }

    fn save(&mut self) {
        self.saved = Some(Instant::now());
        let pair = |place: Option<(f64, f64)>| place.map(|(x, y)| json!([x.round(), y.round()]));
        let text = json!({"palette": pair(self.palette), "panel": pair(self.panel)}).to_string();
        let path = Places::path();
        let temporary = path.with_file_name(format!(".app-windows.json.{}", std::process::id()));
        if fs::write(&temporary, text).and_then(|_| fs::rename(&temporary, &path)).is_err() {
            let _ = fs::remove_file(&temporary);
        }
    }

    /// During a drag moves come many times a second: write at most twice a second
    /// (the last place is written again at the next show, hide or quit).
    fn save_soon(&mut self) {
        if self.saved.is_none_or(|last| last.elapsed() >= Duration::from_millis(500)) {
            self.save();
        }
    }
}

/// Whether a window of `size` at `place` is still mostly on a screen (a display
/// may have been unplugged since).
fn on_a_screen(window: &Window, place: (f64, f64), size: (f64, f64)) -> bool {
    window.available_monitors().any(|monitor| {
        let scale = monitor.scale_factor();
        let (position, area): (LogicalPosition<f64>, LogicalSize<f64>) =
            (monitor.position().to_logical(scale), monitor.size().to_logical(scale));
        let center = (place.0 + size.0 / 2.0, place.1 + 20.0);
        center.0 >= position.x
            && center.0 < position.x + area.width
            && center.1 >= position.y
            && center.1 < position.y + area.height
    })
}

/// A web view for a command's own page (desk), in a window of its own or inside
/// the main window: http(s) only, other sites in the browser, downloads saved.
fn page_builder(url: &str, proxy: EventLoopProxy<UserEvent>, page_name: String) -> WebViewBuilder<'static> {
    // wry asks the navigation handler for every frame, iframes included (the
    // desk canvas frames other sites), so it has no side effects: it only
    // refuses schemes other than the page's own and http(s). Whether the page
    // itself went elsewhere is told by the page-load handler, which sees the
    // main frame only; that link opens in the browser and the page comes back.
    let inside = page_origin(url);
    let note = proxy.clone();
    WebViewBuilder::new()
        .with_url(url)
        .with_navigation_handler(|next| {
            next.starts_with("http://") || next.starts_with("https://") || next == "about:blank"
        })
        .with_on_page_load_handler(move |event, now| {
            let ours =
                now == inside || now.starts_with(&format!("{inside}/")) || now.starts_with(&format!("{inside}?"));
            if matches!(event, wry::PageLoadEvent::Started) && !ours && !now.starts_with("about:") {
                let _ = proxy.send_event(UserEvent::PageLeft { name: page_name.clone(), url: now });
            }
        })
        // Downloads (the canvas PNG export, a board file) go to ~/Downloads under a
        // free name, like Safari; wry picks the name, this only checks it stays there.
        .with_download_started_handler(|_, path| {
            let downloads = settings::home().join("Downloads");
            path.parent() == Some(downloads.as_path())
        })
        .with_download_completed_handler(move |_, _, ok| {
            let text = if ok { "Saved to Downloads." } else { "The download failed." };
            let _ = note.send_event(UserEvent::Toast { title: "Download".into(), text: text.into(), ok });
        })
        .with_new_window_req_handler(|next, _| {
            // Only from a click (WebKit asks for a user gesture to open a window).
            platform::open_link(&next);
            wry::NewWindowResponse::Deny
        })
}

/// scheme://host:port of a page address, without path, query or fragment
/// (`http://127.0.0.1:8765?t=1` -> `http://127.0.0.1:8765`).
fn page_origin(url: &str) -> String {
    let start = url.find("://").map_or(0, |at| at + 3);
    let end = url[start..].find(['/', '?', '#']).map_or(url.len(), |at| start + at);
    url[..end].to_string()
}

/// `value` kept between `low` and `high`; when the room is too small (a narrow
/// screen) `low` wins, where `f64::clamp` would panic.
fn within(value: f64, low: f64, high: f64) -> f64 {
    value.min(high).max(low)
}

/// A screen's frame in points (logical pixels), with its scale.
struct Screen {
    x: f64,
    y: f64,
    width: f64,
    height: f64,
    scale: f64,
}

/// The screen the pointer is on (Spotlight opens there too), else the main one.
fn screen_under_cursor(window: &Window) -> Option<Screen> {
    // Compared in points: the cursor comes in this window's pixels, each
    // monitor in its own, and the two screens may have different scales.
    // tao gives the cursor in points times the primary display's scale (not this
    // window's, which is that of whatever screen it last sat on).
    let primary = window.primary_monitor().map_or(1.0, |monitor| monitor.scale_factor());
    let cursor = window.cursor_position().ok().map(|point| point.to_logical::<f64>(primary));
    let monitor = window
        .available_monitors()
        .find(|monitor| {
            let Some(point) = cursor else { return false };
            let scale = monitor.scale_factor();
            let (position, size): (LogicalPosition<f64>, LogicalSize<f64>) =
                (monitor.position().to_logical(scale), monitor.size().to_logical(scale));
            point.x >= position.x
                && point.y >= position.y
                && point.x < position.x + size.width
                && point.y < position.y + size.height
        })
        .or_else(|| window.primary_monitor())?;
    let scale = monitor.scale_factor();
    let position: LogicalPosition<f64> = monitor.position().to_logical(scale);
    let size: LogicalSize<f64> = monitor.size().to_logical(scale);
    debug(&format!("cursor {cursor:?} screen {position:?} {size:?} x{scale}"));
    Some(Screen { x: position.x, y: position.y, width: size.width, height: size.height, scale })
}

/// `UNLAW_APP_DEBUG=1`: what the app receives, on stderr (the LaunchAgent's log).
fn debug(text: &str) {
    if std::env::var_os("UNLAW_APP_DEBUG").is_some() {
        eprintln!("ul-app: {text}");
    }
}

fn watch_settings(proxy: EventLoopProxy<UserEvent>) {
    thread::spawn(move || {
        let path = settings::path();
        let mut last = modified(&path);
        loop {
            thread::sleep(Duration::from_secs(2));
            if proxy.send_event(UserEvent::CheckPages).is_err() {
                return;
            }
            let now = modified(&path);
            if now != last {
                last = now;
                if proxy.send_event(UserEvent::SettingsChanged).is_err() {
                    return;
                }
            }
        }
    });
}

static SIGNAL_PIPE: AtomicI32 = AtomicI32::new(-1);

extern "C" fn on_signal(_: libc::c_int) {
    let fd = SIGNAL_PIPE.load(Ordering::Relaxed);
    if fd >= 0 {
        // SAFETY: write(2) is async-signal-safe; one byte wakes the reader thread.
        unsafe { libc::write(fd, b"x".as_ptr().cast(), 1) };
    }
}

/// SIGTERM and SIGHUP (launchctl bootout on `ul gui install|stop`, logout) quit
/// through the event loop, so page commands such as `ul desk` are stopped
/// instead of left running. A handler (not a blocked mask) keeps children's
/// signals untouched.
fn watch_signals(proxy: EventLoopProxy<UserEvent>) {
    let mut fds = [0; 2];
    // SAFETY: pipe(2) fills the two descriptors; sigaction installs a handler that only writes.
    unsafe {
        if libc::pipe(fds.as_mut_ptr()) != 0 {
            return;
        }
        libc::fcntl(fds[0], libc::F_SETFD, libc::FD_CLOEXEC);
        libc::fcntl(fds[1], libc::F_SETFD, libc::FD_CLOEXEC);
        SIGNAL_PIPE.store(fds[1], Ordering::Relaxed);
        for signal in [libc::SIGTERM, libc::SIGHUP] {
            let mut action: libc::sigaction = std::mem::zeroed();
            action.sa_sigaction = on_signal as *const () as usize;
            action.sa_flags = libc::SA_RESTART;
            libc::sigemptyset(&mut action.sa_mask);
            libc::sigaction(signal, &action, std::ptr::null_mut());
        }
    }
    let read_end = fds[0];
    thread::spawn(move || {
        let mut byte = [0u8; 1];
        // SAFETY: reading one byte from our own pipe.
        while unsafe { libc::read(read_end, byte.as_mut_ptr().cast(), 1) } == 1 {
            if proxy.send_event(UserEvent::Terminate).is_err() {
                return;
            }
        }
    });
}

/// One running app per user: the lock lives as long as the process.
fn single_instance() -> Option<fs::File> {
    let folder = settings::config_dir();
    let _ = fs::create_dir_all(&folder);
    let file = fs::OpenOptions::new().create(true).truncate(false).write(true).open(folder.join(".gui.lock")).ok()?;
    use std::os::fd::AsRawFd;
    // SAFETY: flock on a file descriptor we own.
    let locked = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } == 0;
    locked.then_some(file)
}

pub fn run() -> i32 {
    let Some(_lock) = single_instance() else {
        eprintln!("ul-app: Unlaw.app is already running.");
        return 0;
    };
    // The login job sets UNLAW_BIN and the installer's PATH; opened from the
    // Dock or Finder the app has neither, so it takes the login shell's PATH.
    let opened_by_user = std::env::var_os("UNLAW_BIN").is_none();
    if opened_by_user {
        runner::adopt_login_path();
    }
    let mut event_loop = EventLoopBuilder::<UserEvent>::with_user_event().build();
    // In the Dock with an app menu and the main window (look.dock, default), or
    // a menu bar app only. Read once: changing it needs a restart.
    let dock = settings::parse(&settings_text().unwrap_or_default()).0.dock;
    #[cfg(target_os = "macos")]
    {
        use tao::platform::macos::{ActivationPolicy, EventLoopExtMacOS};
        // Started at login it waits in the menu bar; opened by the user (Dock,
        // Finder, Spotlight) it comes up in the Dock with its window.
        let regular = dock && opened_by_user;
        event_loop.set_activation_policy(if regular { ActivationPolicy::Regular } else { ActivationPolicy::Accessory });
    }
    let proxy = event_loop.create_proxy();
    for (kind, sender) in [("tray", proxy.clone()), ("menu", proxy.clone()), ("hotkey", proxy.clone())] {
        match kind {
            "tray" => TrayIconEvent::set_event_handler(Some(move |event| {
                let _ = sender.send_event(UserEvent::Tray(event));
            })),
            "menu" => MenuEvent::set_event_handler(Some(move |event| {
                let _ = sender.send_event(UserEvent::Menu(event));
            })),
            _ => GlobalHotKeyEvent::set_event_handler(Some(move |event| {
                let _ = sender.send_event(UserEvent::Hotkey(event));
            })),
        }
    }
    let mut app: Option<App> = None;
    event_loop.run(move |event, target, control| {
        *control = ControlFlow::Wait;
        match event {
            Event::NewEvents(StartCause::Init) => {
                let mut state = App {
                    ul: runner::find_ul(),
                    proxy: proxy.clone(),
                    settings: settings::parse(settings::DEFAULT).0,
                    warnings: Vec::new(),
                    records: Vec::new(),
                    specs: BTreeMap::new(),
                    list_error: None,
                    statuses: HashMap::new(),
                    generation: Arc::new(AtomicU64::new(0)),
                    palette: glass(target, &proxy, View::Palette),
                    palette_keep: false,
                    panel: glass(target, &proxy, View::Panel),
                    panel_for: None,
                    pages: HashMap::new(),
                    opening: Vec::new(),
                    main_tray: None,
                    trays: Vec::new(),
                    menu_ids: HashMap::new(),
                    hotkeys: GlobalHotKeyManager::new().ok(),
                    registered: Vec::new(),
                    running: Vec::new(),
                    hotkey_warnings: Vec::new(),
                    places: Places::load(),
                    dragging: None,
                    panel_center: 0.0,
                    view_first: true,
                    view_reading: false,
                    shown: Vec::new(),
                    own_write: None,
                    home: home::home_window(target),
                    home_state: HomeState::new(dock),
                    edit: EditState::default(),
                    app_menu: None,
                    toast: glass(target, &proxy, View::Toast),
                    ui_colors: None,
                    toast_generation: 0,
                    toast_more: None,
                };
                if dock {
                    state.build_app_menu();
                    platform::pages_first_for_shortcuts();
                }
                state.load_settings();
                state.refresh_colors();
                state.register_hotkeys();
                state.rebuild_trays();
                if !state.install_bundled_cli() {
                    state.reload_commands();
                }
                watch_settings(proxy.clone());
                watch_signals(proxy.clone());
                if dock && opened_by_user && std::env::var_os("UNLAW_APP_HOME").is_none() {
                    state.show_home(None);
                }
                app = Some(state);
            }
            Event::UserEvent(user) => {
                let Some(state) = app.as_mut() else { return };
                match user {
                    UserEvent::Loaded(result) => state.on_loaded(result),
                    UserEvent::Colors(colors) => state.set_colors(colors),
                    UserEvent::Status { name, generation, text } => state.on_status(name, generation, text),
                    UserEvent::Finished { name, label, argv, outcome, quiet, quick } => {
                        state.on_finished(name, label, argv, outcome, quiet, quick)
                    }
                    UserEvent::Dropped(paths) => state.on_dropped(paths),
                    UserEvent::HomeDropped(paths) => {
                        if state.home_state.section == "edit" {
                            state.on_home_dropped(paths);
                        }
                    }
                    UserEvent::Edit(event) => state.on_edit_event(event),
                    UserEvent::Served { name, result } => state.on_served(target, name, result),
                    UserEvent::PageLeft { name, url } => state.on_page_left(&name, &url),
                    UserEvent::Home(message) => {
                        // Kept for a page loaded again later (`init` carries it).
                        if message["type"] == "update" {
                            state.home_state.update = Some(message.clone());
                        }
                        state.send(View::Home, message)
                    }
                    UserEvent::Palette(message) => state.send(View::Palette, message),
                    UserEvent::Toast { title, text, ok } => state.toast(&title, &text, ok, None),
                    UserEvent::ToastHide(generation) => {
                        if generation == state.toast_generation {
                            state.toast.window.set_visible(false);
                        }
                    }
                    UserEvent::Panel { name, message, changed } => state.on_panel_data(&name, message, changed),
                    UserEvent::SysData { id, data } => state.on_sys_data(id, data),
                    UserEvent::GameEnded { id, error } => state.on_game_ended(id, error),
                    UserEvent::DeskServed(result) => state.on_desk_served(result),
                    UserEvent::Ipc(view, body) => state.on_ipc(view, body),
                    UserEvent::Tray(event) => state.on_tray(event),
                    UserEvent::Menu(event) => state.on_menu(event, target, control),
                    UserEvent::Hotkey(event) => state.on_hotkey(event),
                    UserEvent::CliInstalled(result) => state.on_cli_installed(result),
                    UserEvent::Terminate => {
                        state.shutdown();
                        *control = ControlFlow::Exit;
                    }
                    // The app's own pin/unpin already applied this write.
                    UserEvent::SettingsChanged
                        if state.own_write.is_some() && state.own_write == modified(&settings::path()) => {}
                    UserEvent::SettingsChanged => state.apply_settings(),
                    UserEvent::CheckPages => state.check_pages(),
                }
            }
            Event::WindowEvent { window_id, event, .. } => {
                let Some(state) = app.as_mut() else { return };
                if matches!(event, WindowEvent::Focused(_)) {
                    let which = if window_id == state.palette.window.id() {
                        "palette"
                    } else if window_id == state.panel.window.id() {
                        "panel"
                    } else {
                        "page"
                    };
                    debug(&format!("{which} {event:?} visible={}", state.palette.window.is_visible()));
                }
                match event {
                    WindowEvent::Moved(_) => state.on_moved(window_id),
                    // Like Spotlight and a menu bar popover: clicking elsewhere closes them.
                    WindowEvent::Focused(false) if window_id == state.palette.window.id() && !state.palette_keep => {
                        state.palette.window.set_visible(false);
                        state.end_drag();
                    }
                    WindowEvent::Focused(false) if window_id == state.panel.window.id() => {
                        state.panel.window.set_visible(false);
                        state.end_drag();
                    }
                    WindowEvent::CloseRequested if window_id == state.home.window.id() => state.hide_home(),
                    WindowEvent::CloseRequested => {
                        if window_id == state.palette.window.id() || window_id == state.panel.window.id() {
                            return;
                        }
                        state.close_page(window_id);
                    }
                    _ => {}
                }
            }
            Event::Reopen { .. } => {
                if let Some(state) = app.as_mut() {
                    state.show_home(None);
                }
            }
            Event::LoopDestroyed => {
                if let Some(state) = app.as_mut() {
                    state.shutdown();
                }
            }
            _ => {}
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn origins_stop_before_path_and_query() {
        assert_eq!(page_origin("http://127.0.0.1:8765?t=1"), "http://127.0.0.1:8765");
        assert_eq!(page_origin("http://localhost:3000/a/b#x"), "http://localhost:3000");
        assert_eq!(page_origin("http://127.0.0.1:8765"), "http://127.0.0.1:8765");
    }
}
