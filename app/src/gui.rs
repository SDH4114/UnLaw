//! The window shell of Unlaw.app: menu bar items, global hotkeys, the palette
//! and panel windows (glass, one web page each) and page windows for commands
//! that serve one (desk). Every command runs through `ul`; this file only
//! decides what to run and shows the result.

use std::borrow::Cow;
use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Child;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, SystemTime};

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

use crate::platform;

const PAGE: &str = include_str!("../ui/index.html");
const CSS: &str = include_str!("../ui/app.css");
const JS: &str = include_str!("../ui/app.js");
const PALETTE_SIZE: (f64, f64) = (680.0, 460.0);
const PANEL_WIDTH: f64 = 360.0;
const ACTION_TIMEOUT: Duration = Duration::from_secs(3600);
const STATUS_TIMEOUT: Duration = Duration::from_secs(10);
const LIST_TIMEOUT: Duration = Duration::from_secs(15);
const SERVE_WAIT: Duration = Duration::from_secs(25);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
enum View {
    Palette,
    Panel,
}

impl View {
    fn name(self) -> &'static str {
        match self {
            View::Palette => "palette",
            View::Panel => "panel",
        }
    }
}

enum UserEvent {
    Loaded(Result<Vec<Record>, String>),
    Status { name: String, generation: u64, text: StatusText },
    Finished { name: String, label: String, outcome: Outcome, in_panel: bool },
    Served { name: String, result: Result<(Child, String), String> },
    Ipc(View, String),
    Tray(TrayIconEvent),
    Menu(MenuEvent),
    Hotkey(GlobalHotKeyEvent),
    SettingsChanged,
}

/// Where a run was started: a panel shows the result itself, everything else
/// gets a notification.
#[derive(Clone, Copy, PartialEq)]
enum From {
    Panel,
    Elsewhere,
}

struct Page {
    window: Window,
    _webview: WebView,
    child: Child,
}

struct Glass {
    window: Window,
    webview: WebView,
    ready: bool,
    /// Messages sent before the page loaded; delivered once it says ready.
    pending: Vec<Json>,
}

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
    panel: Glass,
    panel_for: Option<String>,
    pages: HashMap<String, Page>,
    opening: Vec<String>,
    main_tray: Option<TrayIcon>,
    trays: Vec<(String, TrayIcon)>,
    menu_ids: HashMap<MenuId, &'static str>,
    hotkeys: Option<GlobalHotKeyManager>,
    registered: Vec<(HotKey, HotkeyJob)>,
}

fn content(path: &str) -> Option<(&'static str, &'static str)> {
    match path {
        "/" | "/index.html" => Some((PAGE, "text/html; charset=utf-8")),
        "/app.css" => Some((CSS, "text/css; charset=utf-8")),
        "/app.js" => Some((JS, "text/javascript; charset=utf-8")),
        _ => None,
    }
}

fn serve_asset(request: Request<Vec<u8>>) -> Response<Cow<'static, [u8]>> {
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
        View::Panel => LogicalSize::new(PANEL_WIDTH, 300.0),
    };
    let window = WindowBuilder::new()
        .with_title(if view == View::Palette { "Unlaw" } else { "Unlaw panel" })
        .with_decorations(false)
        .with_transparent(true)
        .with_resizable(false)
        .with_always_on_top(true)
        .with_visible(false)
        .with_inner_size(size)
        .build(target)
        .expect("a window");
    let ipc = proxy.clone();
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
        .with_accept_first_mouse(true)
        .build(&window)
        .expect("a web view");
    // After the web view: wry makes its own content view, which would drop a
    // blur view added before it.
    #[cfg(target_os = "macos")]
    {
        use window_vibrancy::{apply_vibrancy, NSVisualEffectMaterial, NSVisualEffectState};
        let material =
            if view == View::Palette { NSVisualEffectMaterial::HudWindow } else { NSVisualEffectMaterial::Popover };
        if let Err(error) = apply_vibrancy(&window, material, Some(NSVisualEffectState::Active), Some(14.0)) {
            eprintln!("ul-app: no glass for the {}: {error}", view.name());
        }
    }
    Glass { window, webview, ready: false, pending: Vec::new() }
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

fn settings_text() -> String {
    fs::read_to_string(settings::path()).unwrap_or_else(|_| settings::DEFAULT.to_string())
}

fn write_settings(text: &str) -> Result<(), String> {
    let path = settings::path();
    if let Some(folder) = path.parent() {
        fs::create_dir_all(folder).map_err(|error| error.to_string())?;
    }
    let temporary = path.with_file_name(format!(".app.toml.{}", std::process::id()));
    fs::write(&temporary, text).and_then(|_| fs::rename(&temporary, &path)).map_err(|error| {
        let _ = fs::remove_file(&temporary);
        error.to_string()
    })
}

fn modified(path: &Path) -> Option<SystemTime> {
    fs::metadata(path).and_then(|meta| meta.modified()).ok()
}

impl App {
    fn send(&mut self, view: View, message: Json) {
        let glass = match view {
            View::Palette => &mut self.palette,
            View::Panel => &mut self.panel,
        };
        if glass.ready {
            let _ = glass.webview.evaluate_script(&format!("window.ul.receive({message})"));
        } else if glass.pending.len() < 64 {
            glass.pending.push(message);
        }
    }

    fn theme(&self) -> &'static str {
        self.settings.theme.name()
    }

    fn load_settings(&mut self) {
        let (settings, warnings) = settings::parse(&settings_text());
        self.settings = settings;
        self.warnings = warnings;
        let window_theme = match self.settings.theme {
            Theme::Auto => None,
            Theme::Light => Some(WindowTheme::Light),
            Theme::Dark => Some(WindowTheme::Dark),
        };
        self.palette.window.set_theme(window_theme);
        self.panel.window.set_theme(window_theme);
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
        all.extend(self.list_error.clone());
        all.extend(self.specs.values().filter_map(|(_, problem)| problem.clone()));
        if self.ul.is_none() {
            all.push("The ul command line was not found: install it (ul gui install) or set UNLAW_BIN.".into());
        }
        all
    }

    fn list_json(&self) -> Json {
        let items: Vec<Json> = self
            .specs
            .values()
            .map(|(spec, _)| {
                let mut item = spec::to_json(spec);
                item["pinned"] = json!(self.settings.menubar.contains(&spec.name));
                item["panel"] = json!(spec.panel.is_some());
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
        self.send(View::Palette, self.list_json());
        self.rebuild_trays();
        self.restart_status();
        // UNLAW_APP_SHOW=<command>: open its panel once, to look at it while
        // working on the app (synthetic key presses take the focus away).
        if let Some(name) = std::env::var("UNLAW_APP_SHOW").ok().filter(|name| self.specs.contains_key(name)) {
            std::env::remove_var("UNLAW_APP_SHOW");
            self.show_panel(&name, None);
        }
    }

    // ---------- menu bar ----------

    fn rebuild_trays(&mut self) {
        // New status items appear to the left of older ones, so the rightmost
        // (UL) is made first and the pinned ones from the last to the first.
        self.trays.clear();
        if self.main_tray.is_none() {
            let menu = Menu::new();
            let mut ids = HashMap::new();
            let palette_label = match &self.settings.palette {
                Some(hotkey) => format!("Command palette  {hotkey}"),
                None => "Command palette".into(),
            };
            for (label, job) in [(palette_label.as_str(), "palette"), ("Settings…", "settings"), ("Reload", "reload")]
            {
                let item = MenuItem::new(label, true, None);
                ids.insert(item.id().clone(), job);
                let _ = menu.append(&item);
            }
            let _ = menu.append(&PredefinedMenuItem::separator());
            let _ = menu.append(&MenuItem::new(format!("Unlaw {}", env!("CARGO_PKG_VERSION")), false, None));
            let quit = MenuItem::new("Quit Unlaw", true, None);
            ids.insert(quit.id().clone(), "quit");
            let _ = menu.append(&quit);
            self.menu_ids = ids;
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
            let Some((spec, _)) = self.specs.get(name) else { continue };
            let title = self.statuses.get(name).map(|status| status.text.clone()).unwrap_or_default();
            let tray = TrayIconBuilder::new()
                .with_id(format!("cmd:{name}"))
                .with_tooltip(&spec.title)
                .with_title(&title)
                .with_menu_on_left_click(false)
                .with_menu_on_right_click(false)
                .build();
            if let Ok(tray) = tray {
                #[cfg(target_os = "macos")]
                platform::set_symbol(&tray, &spec.icon);
                self.trays.push((name.clone(), tray));
            }
        }
    }

    fn restart_status(&mut self) {
        let generation = self.generation.fetch_add(1, Ordering::SeqCst) + 1;
        if !self.settings.show_status {
            return;
        }
        let Some(ul) = self.ul.clone() else { return };
        for name in &self.settings.menubar {
            let Some((Spec { status: Some(status), .. }, _)) = self.specs.get(name) else { continue };
            let (name, status, ul, proxy, current) =
                (name.clone(), status.clone(), ul.clone(), self.proxy.clone(), self.generation.clone());
            thread::spawn(move || {
                let argv: Vec<String> = std::iter::once(name.clone()).chain(status.args.iter().cloned()).collect();
                while current.load(Ordering::SeqCst) == generation {
                    let outcome = runner::run(&ul, &argv, STATUS_TIMEOUT);
                    let mut text = template::status_text(&status, &outcome.stdout);
                    if !outcome.ok() && text.text.is_empty() {
                        text = StatusText { text: "–".into(), state: Some("warn".into()) };
                    }
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
        if let Some((_, tray)) = self.trays.iter().find(|(pinned, _)| *pinned == name) {
            tray.set_title(Some(&text.text));
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
        let TrayIconEvent::Click { id, rect, button, button_state: MouseButtonState::Up, .. } = event else { return };
        let Some(name) = id.0.strip_prefix("cmd:").map(str::to_string) else { return };
        let Some((spec, _)) = self.specs.get(&name) else { return };
        let opens = spec.open.is_some() && button == MouseButton::Left;
        if self.panel.window.is_visible() && self.panel_for.as_deref() == Some(&name) {
            self.panel.window.set_visible(false);
            return;
        }
        if opens {
            self.open_page(&name);
        } else {
            let anchor = (rect.position, rect.size);
            self.show_panel(&name, Some(anchor));
        }
    }

    fn on_menu(&mut self, event: MenuEvent, target: &EventLoopWindowTarget<UserEvent>, control: &mut ControlFlow) {
        let _ = target;
        match self.menu_ids.get(&event.id).copied() {
            Some("palette") => self.show_palette(),
            Some("settings") => self.open_settings(),
            Some("reload") => {
                self.load_settings();
                self.register_hotkeys();
                self.reload_commands();
            }
            Some("quit") => {
                self.shutdown();
                *control = ControlFlow::Exit;
            }
            _ => {}
        }
    }

    // ---------- hotkeys ----------

    fn register_hotkeys(&mut self) {
        let Some(manager) = &self.hotkeys else { return };
        for (hotkey, _) in self.registered.drain(..) {
            let _ = manager.unregister(hotkey);
        }
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
                    self.warnings.push(warning);
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
            HotkeyJob::Command(name, target) => {
                let (name, target) = (name.clone(), target.clone());
                match target {
                    Target::Panel => self.show_panel(&name, None),
                    Target::Open => self.open_page(&name),
                    Target::Run => self.run(&name, Vec::new(), &name, From::Elsewhere),
                    Target::Action(id) => self.run_action(&name, &id, From::Elsewhere),
                }
            }
        }
    }

    // ---------- windows ----------

    fn show_palette(&mut self) {
        self.panel.window.set_visible(false);
        let window = &self.palette.window;
        if let Some(screen) = screen_under_cursor(window) {
            let x = screen.x + (screen.width - PALETTE_SIZE.0) / 2.0;
            window.set_outer_position(LogicalPosition::new(x, screen.y + screen.height * 0.2));
        }
        window.set_visible(true);
        window.set_focus();
        self.send(View::Palette, json!({"type": "reset"}));
        // New or removed commands since the last look; ul answers in ~10 ms.
        self.reload_commands();
    }

    fn show_panel(&mut self, name: &str, anchor: Option<(PhysicalPosition<f64>, PhysicalSize<u32>)>) {
        let Some((spec, problem)) = self.specs.get(name).cloned() else { return };
        self.palette.window.set_visible(false);
        self.panel_for = Some(name.to_string());
        let window = &self.panel.window;
        if let Some(screen) = screen_under_cursor(window) {
            let (x, y) = match anchor {
                // The menu bar item's rect, in pixels of the screen it is on.
                Some((position, size)) => {
                    let center = (position.x + size.width as f64 / 2.0) / screen.scale;
                    (center - PANEL_WIDTH / 2.0, (position.y + size.height as f64) / screen.scale + 6.0)
                }
                None => (screen.x + (screen.width - PANEL_WIDTH) / 2.0, screen.y + screen.height * 0.22),
            };
            let x = x.clamp(screen.x + 8.0, screen.x + screen.width - PANEL_WIDTH - 8.0);
            window.set_outer_position(LogicalPosition::new(x, y));
        }
        let status = self.statuses.get(name).map(|status| json!({"text": status.text, "state": status.state}));
        self.send(
            View::Panel,
            json!({"type": "panel", "spec": spec::to_json(&spec), "status": status,
                   "pinned": self.settings.menubar.contains(&spec.name), "problem": problem}),
        );
        self.panel.window.set_visible(true);
        self.panel.window.set_focus();
    }

    fn open_page(&mut self, name: &str) {
        if let Some(page) = self.pages.get(name) {
            page.window.set_visible(true);
            page.window.set_focus();
            return;
        }
        let (Some(ul), Some((spec, _))) = (self.ul.clone(), self.specs.get(name)) else { return };
        let Some(open) = &spec.open else { return };
        if self.opening.iter().any(|item| item == name) {
            return;
        }
        self.opening.push(name.to_string());
        self.palette.window.set_visible(false);
        self.panel.window.set_visible(false);
        let argv: Vec<String> = std::iter::once(name.to_string()).chain(open.args.iter().cloned()).collect();
        let (proxy, name) = (self.proxy.clone(), name.to_string());
        thread::spawn(move || {
            let result = runner::serve(&ul, &argv, SERVE_WAIT);
            let _ = proxy.send_event(UserEvent::Served { name, result });
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
                platform::notify(&title, &format!("Could not open: {error}"));
                return;
            }
        };
        let origin: String = url.splitn(4, '/').take(3).collect::<Vec<_>>().join("/");
        let window = WindowBuilder::new()
            .with_title(&title)
            .with_inner_size(LogicalSize::new(1280.0, 820.0))
            .with_min_inner_size(LogicalSize::new(640.0, 420.0))
            .build(target);
        let window = match window {
            Ok(window) => window,
            Err(error) => {
                runner::stop_group(&mut child, Duration::from_secs(3));
                platform::notify(&title, &error.to_string());
                return;
            }
        };
        let same_origin = origin.clone();
        // The page is the command's own; links to other sites open in the browser.
        let webview = WebViewBuilder::new()
            .with_url(&url)
            .with_navigation_handler(move |next| {
                let inside =
                    next == same_origin || next.starts_with(&format!("{same_origin}/")) || next.starts_with("about:");
                if !inside {
                    platform::open_link(&next);
                }
                inside
            })
            .with_new_window_req_handler(|next, _| {
                platform::open_link(&next);
                wry::NewWindowResponse::Deny
            })
            .build(&window);
        match webview {
            Ok(webview) => {
                window.set_focus();
                self.pages.insert(name, Page { window, _webview: webview, child });
            }
            Err(error) => {
                runner::stop_group(&mut child, Duration::from_secs(3));
                platform::notify(&title, &error.to_string());
            }
        }
    }

    fn close_page(&mut self, id: WindowId) {
        let Some(name) = self.pages.iter().find(|(_, page)| page.window.id() == id).map(|(name, _)| name.clone())
        else {
            return;
        };
        if let Some(mut page) = self.pages.remove(&name) {
            runner::stop_group(&mut page.child, Duration::from_secs(5));
        }
    }

    fn open_settings(&mut self) {
        let path = settings::path();
        if !path.exists() {
            if let Err(error) = write_settings(settings::DEFAULT) {
                platform::notify("Unlaw", &format!("Could not create {}: {error}", path.display()));
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
        let argv: Vec<String> = std::iter::once(name.to_string()).chain(args).collect();
        let (proxy, name, label) = (self.proxy.clone(), name.to_string(), format!("{title}: {label}"));
        thread::spawn(move || {
            let outcome = runner::run(&ul, &argv, ACTION_TIMEOUT);
            let _ = proxy.send_event(UserEvent::Finished { name, label, outcome, in_panel: from == From::Panel });
        });
    }

    fn run_action(&mut self, name: &str, id: &str, from: From) {
        let Some((spec, _)) = self.specs.get(name) else { return };
        let Some(action) = spec.actions.iter().find(|action| action.id == id).cloned() else { return };
        self.run(name, action.args, &action.label, from);
    }

    fn on_finished(&mut self, name: String, label: String, outcome: Outcome, in_panel: bool) {
        let text = outcome.summary(if in_panel { 40 } else { 3 });
        if in_panel && self.panel.window.is_visible() && self.panel_for.as_deref() == Some(&name) {
            self.send(View::Panel, json!({"type": "result", "name": name, "ok": outcome.ok(), "text": text}));
        } else {
            let text = if outcome.ok() { text } else { format!("Failed: {text}") };
            platform::notify(&label, &text);
        }
        // A command that changed something often changes its status too.
        if self.settings.menubar.contains(&name) {
            self.restart_status();
        }
    }

    fn terminal(&mut self, name: &str, args: Vec<String>) {
        let Some(ul) = self.ul.clone() else { return };
        self.palette.window.set_visible(false);
        self.panel.window.set_visible(false);
        let argv: Vec<String> = std::iter::once(name.to_string()).chain(args).collect();
        if let Err(error) = platform::open_terminal(&ul, &argv) {
            platform::notify("Unlaw", &error);
        }
    }

    fn set_pinned(&mut self, name: &str, pinned: bool) {
        let text = settings_text();
        let changed = if pinned { settings::pin(&text, name) } else { settings::unpin(&text, name) };
        match changed.and_then(|text| write_settings(&text)) {
            Ok(()) => {
                self.load_settings();
                self.rebuild_trays();
                self.restart_status();
                self.send(View::Palette, self.list_json());
                self.send(View::Panel, json!({"type": "pinned", "name": name, "pinned": pinned}));
            }
            Err(error) => platform::notify("Unlaw", &format!("Could not change app.toml: {error}")),
        }
    }

    fn on_ipc(&mut self, view: View, body: String) {
        debug(&format!("{} says {body}", view.name()));
        let Ok(message) = serde_json::from_str::<Json>(&body) else { return };
        let op = message["op"].as_str().unwrap_or("");
        let name = message["name"].as_str().unwrap_or("").to_string();
        let from = if view == View::Panel { From::Panel } else { From::Elsewhere };
        if !name.is_empty() && !self.specs.contains_key(&name) {
            return;
        }
        match op {
            "ready" => {
                let glass = if view == View::Palette { &mut self.palette } else { &mut self.panel };
                glass.ready = true;
                let pending = std::mem::take(&mut glass.pending);
                self.send(view, json!({"type": "init", "view": view.name(), "theme": self.theme()}));
                if view == View::Palette {
                    let list = self.list_json();
                    self.send(view, list);
                }
                for message in pending.into_iter().filter(|message| message["type"] != "list") {
                    self.send(view, message);
                }
            }
            "theme" => self.send(view, json!({"type": "theme", "theme": self.theme()})),
            "hide" => match view {
                View::Palette => self.palette.window.set_visible(false),
                View::Panel => self.panel.window.set_visible(false),
            },
            "settings" => self.open_settings(),
            "resize" if view == View::Panel => {
                let height = message["height"].as_f64().unwrap_or(300.0).clamp(120.0, 720.0);
                self.panel.window.set_inner_size(LogicalSize::new(PANEL_WIDTH, height));
            }
            "default" => {
                let Some((spec, _)) = self.specs.get(&name) else { return };
                if spec.terminal {
                    self.terminal(&name, Vec::new());
                } else if spec.open.is_some() {
                    self.open_page(&name);
                } else if spec.panel.is_some() || !spec.actions.is_empty() {
                    self.show_panel(&name, None);
                } else {
                    self.run(&name, Vec::new(), "Run", from);
                }
            }
            "run" => self.run(&name, Vec::new(), "Run", from),
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
                let argv =
                    spec::values_from(&message["values"], &spec).and_then(|values| args::expand(&button.args, &values));
                match argv {
                    Ok(argv) => self.run(&name, argv, &button.label, from),
                    Err(error) => {
                        self.send(View::Panel, json!({"type": "result", "name": name, "ok": false, "text": error}))
                    }
                }
            }
            "panel" => self.show_panel(&name, None),
            "open" => self.open_page(&name),
            "terminal" => self.terminal(&name, Vec::new()),
            "pin" => self.set_pinned(&name, true),
            "unpin" => self.set_pinned(&name, false),
            _ => {}
        }
    }

    fn shutdown(&mut self) {
        self.generation.fetch_add(1, Ordering::SeqCst);
        for (_, mut page) in self.pages.drain() {
            runner::stop_group(&mut page.child, Duration::from_secs(5));
        }
    }
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
    let cursor = window.cursor_position().ok().map(|point| point.to_logical::<f64>(window.scale_factor()));
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
    let mut event_loop = EventLoopBuilder::<UserEvent>::with_user_event().build();
    #[cfg(target_os = "macos")]
    {
        use tao::platform::macos::{ActivationPolicy, EventLoopExtMacOS};
        // A menu bar app: no Dock icon, no app menu.
        event_loop.set_activation_policy(ActivationPolicy::Accessory);
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
                    panel: glass(target, &proxy, View::Panel),
                    panel_for: None,
                    pages: HashMap::new(),
                    opening: Vec::new(),
                    main_tray: None,
                    trays: Vec::new(),
                    menu_ids: HashMap::new(),
                    hotkeys: GlobalHotKeyManager::new().ok(),
                    registered: Vec::new(),
                };
                state.load_settings();
                state.register_hotkeys();
                state.rebuild_trays();
                state.reload_commands();
                watch_settings(proxy.clone());
                app = Some(state);
            }
            Event::UserEvent(user) => {
                let Some(state) = app.as_mut() else { return };
                match user {
                    UserEvent::Loaded(result) => state.on_loaded(result),
                    UserEvent::Status { name, generation, text } => state.on_status(name, generation, text),
                    UserEvent::Finished { name, label, outcome, in_panel } => {
                        state.on_finished(name, label, outcome, in_panel)
                    }
                    UserEvent::Served { name, result } => state.on_served(target, name, result),
                    UserEvent::Ipc(view, body) => state.on_ipc(view, body),
                    UserEvent::Tray(event) => state.on_tray(event),
                    UserEvent::Menu(event) => state.on_menu(event, target, control),
                    UserEvent::Hotkey(event) => state.on_hotkey(event),
                    UserEvent::SettingsChanged => {
                        state.load_settings();
                        state.register_hotkeys();
                        state.main_tray = None;
                        state.rebuild_trays();
                        state.restart_status();
                        state.send(View::Palette, state.list_json());
                    }
                }
            }
            Event::WindowEvent { window_id, event, .. } => {
                let Some(state) = app.as_mut() else { return };
                if matches!(event, WindowEvent::Focused(_)) {
                    let which = if window_id == state.palette.window.id() { "palette" } else if window_id == state.panel.window.id() { "panel" } else { "page" };
                    debug(&format!("{which} {event:?} visible={}", state.palette.window.is_visible()));
                }
                match event {
                    // Like Spotlight and a menu bar popover: clicking elsewhere closes them.
                    WindowEvent::Focused(false) if window_id == state.palette.window.id() => {
                        state.palette.window.set_visible(false)
                    }
                    WindowEvent::Focused(false) if window_id == state.panel.window.id() => {
                        state.panel.window.set_visible(false)
                    }
                    WindowEvent::CloseRequested => {
                        if window_id == state.palette.window.id() || window_id == state.panel.window.id() {
                            return;
                        }
                        state.close_page(window_id);
                    }
                    _ => {}
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
