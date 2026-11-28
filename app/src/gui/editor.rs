//! The Edit part of the main window: a file tree of the folders the user added, the
//! editor `ule --stream` for text and code (one process for every open file, its
//! frames relayed to the page like the arcade's), and viewers for everything else
//! through `ul doc` (kind, version, pictures). Path rules and the editor's input
//! whitelist live in `unlaw_app::edit`.

use std::io::{BufRead, BufReader, Read, Seek, SeekFrom, Write};
use std::os::unix::process::CommandExt;
use std::process::{ChildStdin, Command, Stdio};
use std::sync::atomic::AtomicBool;
use std::sync::{Mutex, OnceLock};

use unlaw_app::edit::{self, Places};
use unlaw_app::files;
use unlaw_app::term;

use super::*;

/// How long `ul doc` may take (drawing a PDF page or a Quick Look picture).
const DOC_TIMEOUT: Duration = Duration::from_secs(20);
/// Raw files served to the page (images, PDF, sound, video): larger ones are refused.
const MAX_SERVED: u64 = 1 << 30;
/// How long ule gets to keep unsaved buffers as recovery copies when it is stopped.
const ULE_GRACE: Duration = Duration::from_secs(5);

/// The places as the protocol handler sees them (it runs on WebKit's thread).
fn access() -> &'static Mutex<Places> {
    static ACCESS: OnceLock<Mutex<Places>> = OnceLock::new();
    ACCESS.get_or_init(|| Mutex::new(Places::default()))
}

fn places_path() -> PathBuf {
    settings::config_dir().join("edit.json")
}

/// ule's own settings file (`ule/src/config.rs` reads the same place).
fn ule_toml_path() -> PathBuf {
    settings::config_dir().join("ule.toml")
}

/// Theme files, icons and file types the user adds: beside ule.toml in Unlaw's config folder.
fn themes_dir() -> PathBuf {
    settings::config_dir().join("themes")
}

fn icons_dir() -> PathBuf {
    settings::config_dir().join("icons")
}

fn file_types_path() -> PathBuf {
    settings::config_dir().join("filetypes.toml")
}

/// The running `ule --stream`.
pub(super) struct UleRun {
    id: u64,
    stdin: Option<ChildStdin>,
    child: Child,
    /// Some buffer has unsaved changes (from the last frame): then hiding the window
    /// keeps the editor running instead of stopping it.
    dirty: Arc<AtomicBool>,
    /// The files open in it (from the last frame), opened again when it restarts.
    files: Arc<Mutex<Vec<String>>>,
}

#[derive(Default)]
pub(super) struct EditState {
    places: Places,
    loaded: bool,
    ule: Option<UleRun>,
    next_ule: u64,
    /// Files the editor had open when it was stopped for being idle.
    reopen: Vec<String>,
    /// The terminal's sessions (tabs of the page, by its number): folder and running command.
    terms: HashMap<u64, TermSession>,
    next_term: u64,
    term_size: (u16, u16),
}

#[derive(Default)]
pub(super) struct TermSession {
    run: Option<TermRun>,
    cwd: Option<PathBuf>,
}

pub(super) struct TermRun {
    id: u64,
    child: Child,
    master: fs::File,
}

/// Results of the Edit part's background work.
pub(super) enum EditEvent {
    /// A folder or file picked in the macOS dialog (None: cancelled).
    Chosen {
        folder: bool,
        path: Option<PathBuf>,
    },
    /// The project panel's three buttons: a place for a new file, a place and name for a new
    /// project folder, or a file or folder to take into the project.
    Asked {
        ask: Ask,
        path: PathBuf,
    },
    /// ule ended by itself; `error` when it never drew.
    UleEnded {
        id: u64,
        error: Option<String>,
    },
    /// Output of the terminal's command, and its end (the pty closed).
    TermOutput {
        session: u64,
        id: u64,
        text: String,
    },
    TermEnded {
        session: u64,
        id: u64,
    },
}

#[derive(Debug, Clone, Copy)]
pub(super) enum Ask {
    NewFile,
    NewProject,
    Pick,
}

/// Save dialogs (`choose file name`) for the new file and the new project folder, run by
/// osascript off the UI thread; "take into the project" is the native open panel
/// (`platform::choose_file_or_folder`), which takes files and folders at once.
fn dialog(ask: Ask) -> Option<PathBuf> {
    let mut command = Command::new("/usr/bin/osascript");
    match ask {
        Ask::NewFile => command.args(["-e", "POSIX path of (choose file name with prompt \"Where should the new file go?\" default name \"untitled.txt\")"]),
        Ask::NewProject => command.args(["-e", "POSIX path of (choose file name with prompt \"Name and place of the new project folder\" default name \"New Project\")"]),
        Ask::Pick => return None,
    };
    let output = command.stdin(Stdio::null()).output().ok().filter(|output| output.status.success())?;
    let text = String::from_utf8_lossy(&output.stdout).trim().trim_end_matches('/').to_string();
    (!text.is_empty()).then(|| PathBuf::from(text))
}

pub(super) fn ule_path(ul: Option<&Path>) -> Option<PathBuf> {
    ule_binary(ul)
}

fn ule_binary(ul: Option<&Path>) -> Option<PathBuf> {
    let beside = ul.and_then(|ul| ul.parent().map(|folder| folder.join("ule")));
    let on_path = std::env::var_os("PATH")
        .map(|path| std::env::split_paths(&path).map(|folder| folder.join("ule")).collect::<Vec<_>>())
        .unwrap_or_default();
    beside
        .into_iter()
        .chain([settings::home().join(".local/bin/ule")])
        .chain(on_path)
        .find(|path| fs::metadata(path).is_ok_and(|meta| meta.is_file()))
}

/// Files `open` would run instead of showing: those are only revealed in Finder.
fn runnable(path: &Path) -> bool {
    const RUNNABLE: &[&str] = &[
        "app",
        "command",
        "tool",
        "sh",
        "zsh",
        "bash",
        "csh",
        "workflow",
        "terminal",
        "pkg",
        "mpkg",
        "scpt",
        "applescript",
        "jar",
        "py",
        "rb",
        "pl",
        "action",
        "prefpane",
        "webloc",
        "inetloc",
        "fileloc",
    ];
    let suffix = path.extension().map(|suffix| suffix.to_string_lossy().to_lowercase()).unwrap_or_default();
    if RUNNABLE.contains(&suffix.as_str()) {
        return true;
    }
    use std::os::unix::fs::PermissionsExt;
    fs::metadata(path).is_ok_and(|meta| meta.is_file() && meta.permissions().mode() & 0o111 != 0)
}

fn served_kind(path: &Path) -> Option<&'static str> {
    let suffix = path.extension()?.to_string_lossy().to_lowercase();
    Some(match suffix.as_str() {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "webp" => "image/webp",
        "heic" | "heif" => "image/heic",
        "tif" | "tiff" => "image/tiff",
        "bmp" => "image/bmp",
        "svg" => "image/svg+xml",
        "pdf" => "application/pdf",
        "mp4" | "m4v" => "video/mp4",
        "mov" => "video/quicktime",
        "mp3" => "audio/mpeg",
        "m4a" | "aac" => "audio/mp4",
        "wav" => "audio/wav",
        "flac" => "audio/flac",
        _ => return None,
    })
}

fn not_found() -> Response<Cow<'static, [u8]>> {
    Response::builder()
        .status(404)
        .body(Cow::Borrowed(&b""[..]))
        .unwrap_or_else(|_| Response::new(Cow::Borrowed(&b""[..])))
}

fn query_value(query: &str, key: &str) -> Option<String> {
    query.split('&').find_map(|pair| {
        let (name, value) = pair.split_once('=')?;
        (name == key).then(|| percent_decoded(&value.replace('+', " "))).flatten()
    })
}

/// `ulapp://localhost/edit/raw?path=...` (a file Edit may open, with byte ranges so
/// video seeks) and `/edit/cache/<hex>.png` (a picture `ul doc render` made).
pub(super) fn serve_edit(request: &Request<Vec<u8>>) -> Response<Cow<'static, [u8]>> {
    let uri = request.uri();
    if let Some(name) = uri.path().strip_prefix("/edit/cache/") {
        let (stem, suffix) = name.split_once('.').unwrap_or(("", ""));
        if suffix != "png" || stem.len() != 24 || !stem.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return not_found();
        }
        let path = home::storage_root().join("doc").join("cache").join(name);
        return match fs::read(path) {
            Ok(bytes) => Response::builder()
                .header(CONTENT_TYPE, "image/png")
                .body(Cow::Owned(bytes))
                .unwrap_or_else(|_| not_found()),
            Err(_) => not_found(),
        };
    }
    // A picture from the user's icons folder (`/edit/icon/<name>.svg|png`), for file types.
    if let Some(name) = uri.path().strip_prefix("/edit/icon/") {
        // The page names the icon (`vue`); the file is vue.svg, else vue.png.
        if !edit::icon_name_ok(name) {
            return not_found();
        }
        let Some((path, kind)) = [("svg", "image/svg+xml"), ("png", "image/png")]
            .iter()
            .map(|(suffix, kind)| (icons_dir().join(format!("{name}.{suffix}")), *kind))
            .find(|(path, _)| path.symlink_metadata().is_ok_and(|meta| meta.is_file() && meta.len() <= 1 << 20))
        else {
            return not_found();
        };
        return match fs::read(path) {
            // Shown only as <img>, where an SVG runs no script; the CSP says so too.
            Ok(bytes) => Response::builder()
                .header(CONTENT_TYPE, kind)
                .header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; sandbox")
                .header("X-Content-Type-Options", "nosniff")
                .body(Cow::Owned(bytes))
                .unwrap_or_else(|_| not_found()),
            Err(_) => not_found(),
        };
    }
    if uri.path() != "/edit/raw" {
        return not_found();
    }
    let Some(raw) = uri.query().and_then(|query| query_value(query, "path")) else { return not_found() };
    let allowed = access().lock().ok().and_then(|places| places.allowed(&raw, &settings::home()).ok());
    let Some(path) = allowed else { return not_found() };
    let Some(kind) = served_kind(&path) else { return not_found() };
    let Ok(mut file) = fs::File::open(&path) else { return not_found() };
    let size = file.metadata().map(|meta| meta.len()).unwrap_or(0);
    if size > MAX_SERVED {
        return not_found();
    }
    let range = request
        .headers()
        .get("range")
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("bytes="))
        .and_then(|value| value.split_once('-'))
        .and_then(|(start, end)| {
            let start: u64 = start.parse().ok()?;
            let end: u64 = if end.is_empty() { size.saturating_sub(1) } else { end.parse().ok()? };
            (start <= end && end < size).then_some((start, end.min(start + (8 << 20))))
        });
    let builder = Response::builder()
        .header(CONTENT_TYPE, kind)
        .header("X-Content-Type-Options", "nosniff")
        .header("Accept-Ranges", "bytes");
    // An SVG opened on its own must not run its scripts (a PDF in a sandbox is refused
    // by WebKit, and pictures, sound and video run nothing).
    let builder = if kind == "image/svg+xml" { builder.header("Content-Security-Policy", "sandbox") } else { builder };
    match range {
        Some((start, end)) => {
            let mut bytes = vec![0; (end - start + 1) as usize];
            if file.seek(SeekFrom::Start(start)).and_then(|_| file.read_exact(&mut bytes)).is_err() {
                return not_found();
            }
            builder
                .status(206)
                .header("Content-Range", format!("bytes {start}-{end}/{size}"))
                .body(Cow::Owned(bytes))
                .unwrap_or_else(|_| not_found())
        }
        None => {
            let mut bytes = Vec::with_capacity(size as usize);
            if file.read_to_end(&mut bytes).is_err() {
                return not_found();
            }
            builder.body(Cow::Owned(bytes)).unwrap_or_else(|_| not_found())
        }
    }
}

impl App {
    fn load_places(&mut self) {
        if self.edit.loaded {
            return;
        }
        self.edit.loaded = true;
        self.edit.places = Places::parse(&fs::read_to_string(places_path()).unwrap_or_default());
        self.share_places();
    }

    fn share_places(&self) {
        if let Ok(mut shared) = access().lock() {
            *shared = self.edit.places.clone();
        }
    }

    fn save_places(&self) {
        self.share_places();
        let text = format!("{:#}\n", self.edit.places.to_json());
        let path = places_path();
        let temporary = path.with_extension("json.tmp");
        let written = fs::write(&temporary, text).and_then(|_| fs::rename(&temporary, &path));
        if let Err(error) = written {
            eprintln!("ul-app: could not save {}: {error}", path.display());
        }
    }

    fn send_places(&mut self) {
        let list = |paths: &[PathBuf]| -> Vec<Json> {
            paths
                .iter()
                .map(|path| {
                    let name = path.file_name().map(|name| name.to_string_lossy().to_string()).unwrap_or_default();
                    json!({"path": path.display().to_string(), "name": name, "exists": path.exists()})
                })
                .collect()
        };
        let ule_toml = fs::read_to_string(ule_toml_path()).unwrap_or_default();
        let prefs = edit::ule_prefs(&ule_toml);
        let (types, type_warnings) = edit::file_types(&fs::read_to_string(file_types_path()).unwrap_or_default());
        let theme_files = edit::theme_files(&themes_dir());
        self.send(
            View::Home,
            json!({"type": "edit-places", "roots": list(&self.edit.places.roots),
                   "recent": list(&self.edit.places.recent), "running": self.edit.ule.is_some() || !self.edit.reopen.is_empty(),
                   "home": settings::home().display().to_string(),
                   "editing": prefs.editing, "theme": prefs.theme, "themes": edit::ule_themes(&ule_toml, &theme_files),
                   "theme_files": theme_files, "types": types, "icons": edit::icon_names(&icons_dir()),
                   "type_warnings": type_warnings, "config": settings::config_dir().display().to_string()}),
        );
    }

    /// Keys (vim/standard) and theme: written to ule.toml (the terminal ule reads them too)
    /// and passed to the running editor at once.
    fn set_ule_prefs(&mut self, editing: Option<&str>, theme: Option<&str>) {
        let path = ule_toml_path();
        let text = match fs::read_to_string(&path) {
            Ok(text) => text,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => String::new(),
            Err(error) => return self.edit_error(format!("could not read {}: {error}", path.display())),
        };
        let saved = edit::with_ule_prefs(&text, editing, theme, &edit::theme_files(&themes_dir())).and_then(|saved| {
            let temporary = path.with_extension("toml.tmp");
            fs::write(&temporary, saved)
                .and_then(|_| fs::rename(&temporary, &path))
                .map_err(|error| format!("could not save {}: {error}", path.display()))
        });
        if let Err(error) = saved {
            return self.edit_error(error);
        }
        let mut lines = String::new();
        for (name, value) in [("editing", editing), ("theme", theme)] {
            if let Some(value) = value {
                lines.push_str(&json!({"set": {"name": name, "value": value}}).to_string());
                lines.push('\n');
            }
        }
        if let Some(stdin) = self.edit.ule.as_mut().and_then(|run| run.stdin.as_mut()) {
            let _ = stdin.write_all(lines.as_bytes()).and_then(|_| stdin.flush());
        }
        self.send_places();
        self.refresh_colors();
    }

    fn allowed(&self, raw: &str) -> Result<PathBuf, String> {
        self.edit.places.allowed(raw, &settings::home())
    }

    fn edit_error(&mut self, text: impl Into<String>) {
        self.send(View::Home, json!({"type": "edit-error", "text": text.into()}));
    }

    /// The macOS open dialog, off the UI thread (osascript returns the POSIX path).
    fn choose(&self, folder: bool) {
        let proxy = self.proxy.clone();
        thread::spawn(move || {
            let script = if folder {
                "POSIX path of (choose folder with prompt \"Add a folder to Edit\")"
            } else {
                "POSIX path of (choose file with prompt \"Open a file in Edit\")"
            };
            let output = Command::new("/usr/bin/osascript").args(["-e", script]).stdin(Stdio::null()).output();
            let path = output
                .ok()
                .filter(|output| output.status.success())
                .map(|output| String::from_utf8_lossy(&output.stdout).trim().trim_end_matches('/').to_string())
                .filter(|text| !text.is_empty())
                .map(PathBuf::from);
            let _ = proxy.send_event(UserEvent::Edit(EditEvent::Chosen { folder, path }));
        });
    }

    fn ask(&mut self, ask: Ask) {
        if let Ask::Pick = ask {
            if let Some(path) =
                platform::choose_file_or_folder("Choose a folder to add to the project, or a file to open")
            {
                self.asked(ask, path);
            }
            return;
        }
        let proxy = self.proxy.clone();
        thread::spawn(move || {
            if let Some(path) = dialog(ask) {
                let _ = proxy.send_event(UserEvent::Edit(EditEvent::Asked { ask, path }));
            }
        });
    }

    /// What the project panel's dialogs answered: never replaces anything that exists.
    fn asked(&mut self, ask: Ask, path: PathBuf) {
        let (Some(parent), Some(name)) =
            (path.parent(), path.file_name().map(|name| name.to_string_lossy().to_string()))
        else {
            return;
        };
        if let Some(reason) = parent.canonicalize().ok().and_then(|real| edit::denied(&real, &settings::home())) {
            return self.edit_error(reason);
        }
        match ask {
            Ask::NewFile => match files::new_file(parent, &name) {
                Ok(made) => self.open_given(made),
                Err(error) => self.edit_error(error),
            },
            Ask::NewProject => match files::new_folder(parent, &name) {
                Ok(made) => self.on_edit_event(EditEvent::Chosen { folder: true, path: Some(made) }),
                Err(error) => self.edit_error(error),
            },
            Ask::Pick => {
                let folder = path.is_dir();
                self.on_edit_event(EditEvent::Chosen { folder, path: Some(path) });
            }
        }
    }

    pub(super) fn on_edit_event(&mut self, event: EditEvent) {
        match event {
            EditEvent::Asked { ask, path } => self.asked(ask, path),
            EditEvent::TermOutput { session, id, text } => {
                self.send(View::Home, json!({"type": "term-output", "session": session, "id": id, "text": text}));
            }
            EditEvent::TermEnded { session, id } => {
                let Some(state) = self.edit.terms.get_mut(&session) else { return };
                if state.run.as_ref().map(|run| run.id) != Some(id) {
                    return;
                }
                let Some(mut run) = state.run.take() else { return };
                let code = run.child.try_wait().ok().flatten().and_then(|status| status.code());
                if code.is_none() {
                    // The pty closed but the shell has not been reaped yet: reap it off the UI thread.
                    thread::spawn(move || drop(run.child.wait()));
                }
                self.send(View::Home, json!({"type": "term-exit", "session": session, "id": id, "code": code}));
            }
            EditEvent::Chosen { path: None, .. } => {}
            EditEvent::Chosen { folder: true, path: Some(path) } => {
                if let Some(reason) = path.canonicalize().ok().and_then(|real| edit::denied(&real, &settings::home())) {
                    self.edit_error(reason);
                    return;
                }
                self.edit.places.add_root(path.clone());
                self.save_places();
                self.send_places();
                self.send(View::Home, json!({"type": "edit-expand", "path": path.display().to_string()}));
            }
            EditEvent::Chosen { folder: false, path: Some(path) } => self.open_given(path),
            EditEvent::UleEnded { id, error } => {
                if self.edit.ule.as_ref().map(|run| run.id) != Some(id) {
                    return;
                }
                if let Some(run) = self.edit.ule.take() {
                    stop_ule(run);
                }
                self.send(View::Home, json!({"type": "ule-ended", "id": id, "error": error}));
            }
        }
    }

    /// A file the user gave the app (dialog, drop): it becomes reachable and opens.
    fn open_given(&mut self, path: PathBuf) {
        if let Some(reason) = path.canonicalize().ok().and_then(|real| edit::denied(&real, &settings::home())) {
            self.edit_error(reason);
            return;
        }
        if !path.is_file() {
            self.edit_error(format!("{} is not a file", path.display()));
            return;
        }
        self.edit.places.touch(path.clone());
        self.save_places();
        self.send_places();
        self.send(View::Home, json!({"type": "edit-open", "path": path.display().to_string()}));
    }

    /// Files dropped on the main window while Edit is shown.
    pub(super) fn on_home_dropped(&mut self, paths: Vec<PathBuf>) {
        self.load_places();
        for path in paths.into_iter().take(16) {
            if path.is_dir() {
                self.on_edit_event(EditEvent::Chosen { folder: true, path: Some(path) });
            } else {
                self.open_given(path);
            }
        }
    }

    /// `ul doc <argv> --json` off the UI thread; its answer goes to the page as `kind`.
    fn doc(&mut self, kind: &'static str, path: &Path, argv: Vec<String>, tag: Json) {
        let Some(ul) = self.ul.clone() else {
            self.edit_error("ul was not found");
            return;
        };
        let proxy = self.proxy.clone();
        let shown = path.display().to_string();
        thread::spawn(move || {
            let outcome = runner::run_capped(&ul, &argv, DOC_TIMEOUT, 1 << 20);
            let answer = serde_json::from_str::<Json>(outcome.stdout.trim()).ok().filter(|_| outcome.ok());
            let message = match answer {
                Some(answer) => json!({"type": kind, "path": shown, "result": answer, "tag": tag}),
                None => {
                    let text = runner::strip_ansi(outcome.stderr.trim());
                    let text = if text.contains("Unknown command") || text.contains("unknown command") {
                        "Edit needs the doc command: ul features add doc".to_string()
                    } else if outcome.timed_out {
                        "it took too long".to_string()
                    } else if text.is_empty() {
                        "ul doc failed".to_string()
                    } else {
                        text.trim_start_matches("unlaw doc: ").lines().next().unwrap_or("").to_string()
                    };
                    json!({"type": kind, "path": shown, "error": text, "tag": tag})
                }
            };
            let _ = proxy.send_event(UserEvent::Home(message));
        });
    }

    /// Page requests of the Edit part; true when `op` was one of them.
    pub(super) fn on_edit_op(&mut self, op: &str, message: &Json) -> bool {
        if op.starts_with("term-") {
            self.on_term_op(op, message);
            return true;
        }
        if !op.starts_with("edit-") && !op.starts_with("ule-") {
            return false;
        }
        self.load_places();
        let path_of = |key: &str| message[key].as_str().unwrap_or("").to_string();
        match op {
            "edit-places" => self.send_places(),
            // A theme file was saved, or ule's theme changed: the windows follow.
            "edit-colors" => self.refresh_colors(),
            "edit-new-theme" => self.new_theme(&path_of("name"), &path_of("base")),
            "edit-config-file" => self.config_file(&path_of("what")),
            "edit-prefs" => {
                let editing = message["editing"].as_str().map(str::to_string);
                let theme = message["theme"].as_str().map(str::to_string);
                self.set_ule_prefs(editing.as_deref(), theme.as_deref());
            }
            "edit-add-folder" => self.choose(true),
            "edit-open-dialog" => self.choose(false),
            "edit-new-file-dialog" => self.ask(Ask::NewFile),
            "edit-new-project-dialog" => self.ask(Ask::NewProject),
            "edit-pick-dialog" => self.ask(Ask::Pick),
            "edit-remove-folder" => {
                if let Ok(path) = edit::plain_absolute(&path_of("path")) {
                    self.edit.places.remove_root(&path);
                    self.save_places();
                }
                self.send_places();
            }
            "edit-forget" => {
                if let Ok(path) = edit::plain_absolute(&path_of("path")) {
                    self.edit.places.forget(&path);
                    self.save_places();
                }
                self.send_places();
            }
            "edit-list" => {
                let answer = self.allowed(&path_of("path")).and_then(|folder| edit::list_folder(&folder));
                match answer {
                    Ok(listed) => self.send(View::Home, json!({"type": "edit-list", "list": listed})),
                    Err(error) => self.edit_error(error),
                }
            }
            "edit-info" => match self.allowed(&path_of("path")) {
                Ok(path) => {
                    self.edit.places.touch(path.clone());
                    self.save_places();
                    self.send_places();
                    let argv =
                        vec!["doc".into(), "info".into(), "--json".into(), "--".into(), path.display().to_string()];
                    self.doc("edit-info", &path, argv, Json::Null);
                }
                Err(error) => self.edit_error(error),
            },
            "edit-render" => match self.allowed(&path_of("path")) {
                Ok(path) => {
                    let width = message["width"].as_u64().unwrap_or(1200).clamp(64, 4096);
                    let page = message["page"].as_u64().unwrap_or(1).clamp(1, 100_000);
                    let mut argv = vec![
                        "doc".into(),
                        "render".into(),
                        "--width".into(),
                        width.to_string(),
                        "--page".into(),
                        page.to_string(),
                    ];
                    if let Some(last) = message["to"].as_u64() {
                        argv.extend(["--to".into(), last.clamp(page, page + 499).to_string()]);
                    }
                    argv.extend(["--json".into(), "--".into(), path.display().to_string()]);
                    // The page tells its own requests apart (thumbnails, pages) by this tag.
                    let tag = match &message["tag"] {
                        Json::String(text) if text.len() <= 64 => Json::String(text.clone()),
                        _ => Json::Null,
                    };
                    self.doc("edit-render", &path, argv, tag);
                }
                Err(error) => self.edit_error(error),
            },
            "edit-reveal" | "edit-open-app" => match self.allowed(&path_of("path")) {
                Ok(path) => {
                    let reveal = op == "edit-reveal" || runnable(&path);
                    let mut command = Command::new("/usr/bin/open");
                    if reveal {
                        command.arg("-R");
                    }
                    let spawned = command.arg("--").arg(&path).stdin(Stdio::null()).spawn();
                    match spawned {
                        Ok(mut child) => {
                            thread::spawn(move || child.wait());
                        }
                        Err(error) => self.edit_error(format!("could not open it: {error}")),
                    }
                }
                Err(error) => self.edit_error(error),
            },
            "edit-pages" => match self.allowed(&path_of("path")) {
                Ok(path) => {
                    let argv =
                        vec!["doc".into(), "pages".into(), "--json".into(), "--".into(), path.display().to_string()];
                    self.doc("edit-pages", &path, argv, Json::Null);
                }
                Err(error) => self.edit_error(error),
            },
            "edit-ink-load" => match self.allowed(&path_of("path")) {
                Ok(path) => {
                    let file = ink_dir().join(edit::ink_name(&path));
                    let ink = fs::read_to_string(&file)
                        .ok()
                        .and_then(|text| serde_json::from_str::<Json>(&text).ok())
                        .filter(|ink| edit::check_ink(ink).is_ok())
                        .unwrap_or(Json::Null);
                    self.send(View::Home, json!({"type": "edit-ink", "path": path.display().to_string(), "ink": ink}));
                }
                Err(error) => self.edit_error(error),
            },
            "edit-ink-save" => match self.allowed(&path_of("path")) {
                Ok(path) => {
                    let ink = &message["ink"];
                    let saved = edit::check_ink(ink).and_then(|()| {
                        let dir = ink_dir();
                        fs::create_dir_all(&dir).map_err(|error| error.to_string())?;
                        let mut stored = ink.clone();
                        stored["path"] = json!(path.display().to_string());
                        let target = dir.join(edit::ink_name(&path));
                        let temporary = dir.join(format!(".{}.tmp", edit::ink_name(&path)));
                        fs::write(&temporary, stored.to_string()).map_err(|error| error.to_string())?;
                        fs::rename(&temporary, &target).map_err(|error| error.to_string())
                    });
                    if let Err(error) = saved {
                        self.edit_error(format!("drawings not saved: {error}"));
                    }
                }
                Err(error) => self.edit_error(error),
            },
            "edit-new" | "edit-rename" | "edit-duplicate" | "edit-trash" | "edit-move" => self.file_op(op, message),
            "edit-copy-path" => match self.allowed(&path_of("path")) {
                Ok(path) => {
                    let roots: Vec<PathBuf> =
                        self.edit.places.roots.iter().filter_map(|root| root.canonicalize().ok()).collect();
                    let shown = if message["relative"] == true { files::relative(&path, &roots) } else { &path };
                    match copy_text(&shown.display().to_string()) {
                        Ok(()) => self.send(View::Home, json!({"type": "edit-note", "text": "Path copied"})),
                        Err(error) => self.edit_error(error),
                    }
                }
                Err(error) => self.edit_error(error),
            },
            "edit-terminal" => match self.allowed(&path_of("path")) {
                Ok(path) => {
                    let dir = if path.is_dir() { path } else { path.parent().map(Path::to_path_buf).unwrap_or(path) };
                    thread::spawn(move || open_terminal_at(&dir));
                }
                Err(error) => self.edit_error(error),
            },
            "ule-start" => {
                let rows = message["rows"].as_u64().unwrap_or(40).clamp(5, 400);
                let cols = message["cols"].as_u64().unwrap_or(120).clamp(20, 800);
                let light = message["theme"].as_str() == Some("light");
                self.start_ule(rows, cols, light);
            }
            "ule-input" => self.ule_input(message),
            _ => return false,
        }
        true
    }

    /// "New theme…": `<config>/themes/<name>.toml` starting from `base`, opened in Edit.
    fn new_theme(&mut self, name: &str, base: &str) {
        if !edit::icon_name_ok(name) {
            return self.edit_error("a theme name has letters, digits, - and _ only");
        }
        let ule_toml = fs::read_to_string(ule_toml_path()).unwrap_or_default();
        let known = edit::ule_themes(&ule_toml, &edit::theme_files(&themes_dir()));
        if known.iter().any(|theme| theme == name) {
            return self.edit_error(format!("there is a theme named {name} already"));
        }
        let base = if known.iter().any(|theme| theme == base) { base } else { "onedark" };
        let made = fs::create_dir_all(themes_dir())
            .map_err(|error| error.to_string())
            .and_then(|()| files::new_file(&themes_dir(), &format!("{name}.toml")))
            .and_then(|path| {
                fs::write(&path, edit::new_theme_text(base)).map(|()| path).map_err(|error| error.to_string())
            });
        match made {
            Ok(path) => self.open_in_edit(path),
            Err(error) => self.edit_error(format!("could not make the theme: {error}")),
        }
    }

    /// Settings > Editor: filetypes.toml opens in Edit (made from the template when missing);
    /// the icons and themes folders open in Finder, where pictures are dropped.
    fn config_file(&mut self, what: &str) {
        match what {
            "filetypes" => {
                let path = file_types_path();
                if !path.exists() {
                    if let Err(error) = files::new_file(&settings::config_dir(), "filetypes.toml")
                        .and_then(|path| fs::write(path, edit::FILE_TYPES_TEMPLATE).map_err(|error| error.to_string()))
                    {
                        return self.edit_error(format!("could not make filetypes.toml: {error}"));
                    }
                }
                self.open_in_edit(path);
            }
            "icons" | "themes" => {
                let dir = if what == "icons" { icons_dir() } else { themes_dir() };
                if let Err(error) = fs::create_dir_all(&dir) {
                    return self.edit_error(format!("could not make {}: {error}", dir.display()));
                }
                let _ =
                    Command::new("/usr/bin/open").arg("--").arg(&dir).stdin(Stdio::null()).spawn().map(|mut child| {
                        thread::spawn(move || child.wait());
                    });
            }
            _ => {}
        }
    }

    /// A file of Unlaw's config shown in Edit: it joins the recent files (so it may open).
    fn open_in_edit(&mut self, path: PathBuf) {
        let path = path.canonicalize().unwrap_or(path);
        self.edit.places.touch(path.clone());
        self.save_places();
        self.send_places();
        self.send(View::Home, json!({"type": "edit-open", "path": path.display().to_string()}));
    }

    /// New file or folder, rename, duplicate, Trash, move: the project panel's menu.
    /// Paths are checked like every other; a root itself is never renamed, moved or trashed
    /// (it is taken off the list instead). The page is told which folders to list again.
    fn file_op(&mut self, op: &str, message: &Json) {
        let text = |key: &str| message[key].as_str().unwrap_or("").to_string();
        let path = match self.allowed(&text(if op == "edit-new" { "dir" } else { "path" })) {
            Ok(path) => path,
            Err(error) => return self.edit_error(error),
        };
        let is_root =
            self.edit.places.roots.iter().filter_map(|root| root.canonicalize().ok()).any(|root| root == path);
        if is_root && op != "edit-new" {
            return self.edit_error("a project folder itself is not changed here: take it off the list with ×");
        }
        let parent = path.parent().map(Path::to_path_buf).unwrap_or_else(|| path.clone());
        let result = match op {
            "edit-new" if !path.is_dir() => Err("new files go into a folder".to_string()),
            "edit-new" if message["folder"] == true => files::new_folder(&path, &text("name")),
            "edit-new" => files::new_file(&path, &text("name")),
            "edit-rename" => files::rename(&path, &text("name")),
            "edit-duplicate" => files::duplicate(&path),
            "edit-trash" => platform::move_to_trash(&path).map(|_| path.clone()),
            _ => match self.allowed(&text("dir")) {
                Ok(dir) if dir.is_dir() => files::move_into(&path, &dir),
                Ok(_) => Err("drop it on a folder".to_string()),
                Err(error) => Err(error),
            },
        };
        match result {
            Ok(done) => {
                let mut dirs = vec![parent.display().to_string()];
                if let Some(folder) = done.parent() {
                    dirs.push(folder.display().to_string());
                }
                if op == "edit-new" {
                    dirs.push(path.display().to_string());
                }
                if op != "edit-trash" && done.is_file() {
                    self.edit.places.touch(done.clone());
                    self.save_places();
                }
                self.send(
                    View::Home,
                    json!({"type": "edit-changed", "op": op, "from": path.display().to_string(),
                           "path": done.display().to_string(), "dir": done.is_dir(), "dirs": dirs}),
                );
            }
            Err(error) => self.edit_error(error),
        }
    }

    fn ule_input(&mut self, message: &Json) {
        let Some(run) = self.edit.ule.as_ref().filter(|run| Some(run.id) == message["id"].as_u64()) else {
            return;
        };
        let _ = run;
        let mut lines = String::new();
        let mut opened = Vec::new();
        for event in message["events"].as_array().into_iter().flatten().take(256) {
            match edit::ule_event(event, &|raw| self.allowed(raw)) {
                Ok(line) => {
                    if let Some(path) = line["open"]["path"].as_str() {
                        opened.push(PathBuf::from(path));
                    }
                    lines.push_str(&line.to_string());
                    lines.push('\n');
                }
                Err(error) => debug(&format!("edit: dropped an editor event: {error}")),
            }
        }
        for path in opened {
            self.edit.places.touch(path);
        }
        if !lines.is_empty() {
            self.save_places();
        }
        if let Some(stdin) = self.edit.ule.as_mut().and_then(|run| run.stdin.as_mut()) {
            let _ = stdin.write_all(lines.as_bytes()).and_then(|_| stdin.flush());
        }
    }

    /// One ule for the whole part: a page loaded again gets the running one back.
    fn start_ule(&mut self, rows: u64, cols: u64, light: bool) {
        if let Some(run) = self.edit.ule.as_mut() {
            let id = run.id;
            let size = json!({"resize": {"rows": rows, "cols": cols}});
            let theme = json!({"theme": if light { "light" } else { "dark" }});
            if let Some(stdin) = run.stdin.as_mut() {
                let _ = writeln!(stdin, "{size}\n{theme}\n{}", json!({"redraw": true})).and_then(|_| stdin.flush());
            }
            self.send(View::Home, json!({"type": "ule-started", "id": id}));
            return;
        }
        self.edit.next_ule += 1;
        let id = self.edit.next_ule;
        let Some(ule) = ule_binary(self.ul.as_deref()) else {
            self.send(
                View::Home,
                json!({"type": "ule-ended", "id": id, "error": "The editor ule was not found (it installs with Unlaw)."}),
            );
            return;
        };
        let mut command = Command::new(&ule);
        command.args(["--stream", "--size", &format!("{rows}x{cols}")]);
        if light {
            command.arg("--light");
        }
        if let Some(ul) = &self.ul {
            command.env("ULE_UL", ul);
        }
        let spawned = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .env("UNLAW_APP", "1")
            .current_dir(settings::home())
            .process_group(0)
            .spawn();
        let mut child = match spawned {
            Ok(child) => child,
            Err(error) => {
                self.send(
                    View::Home,
                    json!({"type": "ule-ended", "id": id, "error": format!("Could not start ule: {error}")}),
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
                let _ = stderr.by_ref().take(16384).read_to_string(&mut text);
                if let Ok(mut kept) = errors.lock() {
                    *kept = runner::strip_ansi(text.trim());
                }
            });
        }
        let dirty = Arc::new(AtomicBool::new(false));
        let files = Arc::new(Mutex::new(Vec::new()));
        if let Some(stdout) = stdout {
            let (proxy, dirty, files) = (self.proxy.clone(), dirty.clone(), files.clone());
            thread::spawn(move || {
                let mut reader = BufReader::new(stdout);
                let mut line = Vec::new();
                let mut frames = 0u64;
                while matches!(reader.read_until(b'\n', &mut line), Ok(read) if read > 0) {
                    if let Ok(frame) = serde_json::from_slice::<Json>(&line) {
                        if frame.get("lines").is_some() {
                            frames += 1;
                            let modified = frame["buffers"]
                                .as_array()
                                .is_some_and(|list| list.iter().any(|buffer| buffer["modified"] == true));
                            dirty.store(modified, Ordering::SeqCst);
                            if let Ok(mut kept) = files.lock() {
                                *kept = frame["buffers"]
                                    .as_array()
                                    .into_iter()
                                    .flatten()
                                    .filter_map(|buffer| buffer["path"].as_str().map(str::to_string))
                                    .collect();
                            }
                            if proxy
                                .send_event(UserEvent::Home(json!({"type": "ule-frame", "id": id, "frame": frame})))
                                .is_err()
                            {
                                return;
                            }
                        }
                    }
                    line.clear();
                }
                thread::sleep(Duration::from_millis(200));
                let error = errors.lock().map(|text| text.clone()).unwrap_or_default();
                let error = (frames == 0 || !error.is_empty()).then_some(error).filter(|text| !text.is_empty());
                let _ = proxy.send_event(UserEvent::Edit(EditEvent::UleEnded { id, error }));
            });
        }
        let mut run = UleRun { id, stdin, child, dirty, files };
        // The files it had open before it was stopped for being idle.
        let reopen = std::mem::take(&mut self.edit.reopen);
        if let Some(stdin) = run.stdin.as_mut() {
            for path in reopen.iter().filter_map(|path| self.allowed(path).ok()) {
                let _ = writeln!(stdin, "{}", json!({"open": {"path": path.display().to_string()}}));
            }
            let _ = stdin.flush();
        }
        self.edit.ule = Some(run);
        self.send(View::Home, json!({"type": "ule-started", "id": id}));
    }

    /// The main window's page was unloaded (hidden for a while): an editor with nothing
    /// unsaved stops, its files open again when Edit starts it next; one with unsaved
    /// changes keeps running until the app quits.
    pub(super) fn edit_hidden(&mut self) {
        let idle = self.edit.ule.as_ref().is_some_and(|run| !run.dirty.load(Ordering::SeqCst));
        if idle {
            if let Some(run) = self.edit.ule.take() {
                self.edit.reopen = run.files.lock().map(|files| files.clone()).unwrap_or_default();
                stop_ule(run);
            }
        }
    }

    /// For shutdown: the editor's process with its stdin closed (it then keeps unsaved
    /// buffers as recovery copies and exits; the group is stopped after a grace).
    pub(super) fn edit_children(&mut self) -> Vec<Child> {
        let terminal: Vec<Child> =
            self.edit.terms.drain().filter_map(|(_, state)| state.run.map(|run| run.child)).collect();
        self.edit
            .ule
            .take()
            .map(|mut run| {
                run.stdin.take();
                run.child
            })
            .into_iter()
            .chain(terminal)
            .collect()
    }

    /// The terminal under the editor, one session per tab of the page (`session`):
    /// `term-run` (a command line, or input for the one running), `term-input` (raw keys:
    /// Ctrl-C, Ctrl-D), `term-run-file`, `term-resize`, `term-stop`, `term-cwd`, `term-close`.
    fn on_term_op(&mut self, op: &str, message: &Json) {
        let size = |key: &str, fallback: u16| {
            message[key].as_u64().map(|value| value.clamp(2, 1000) as u16).unwrap_or(fallback)
        };
        let Some(session) = message["session"].as_u64() else { return };
        if message.get("cols").is_some() {
            self.edit.term_size = (size("cols", 80), size("rows", 24));
            let (cols, rows) = self.edit.term_size;
            for state in self.edit.terms.values() {
                if let Some(run) = &state.run {
                    term::resize(&run.master, cols, rows);
                }
            }
        }
        if op == "term-close" {
            if let Some(run) = self.edit.terms.remove(&session).and_then(|state| state.run) {
                let mut child = run.child;
                thread::spawn(move || runner::stop_group(&mut child, Duration::from_secs(3)));
            }
            return;
        }
        if self.edit.terms.len() >= 32 && !self.edit.terms.contains_key(&session) {
            return self.term_note(session, "too many terminals: close some first");
        }
        let text = message["text"].as_str().unwrap_or("");
        let state = self.edit.terms.entry(session).or_default();
        match op {
            "term-cwd" => self.send_term_cwd(session),
            "term-input" => {
                if let Some(run) = state.run.as_mut() {
                    let _ = run.master.write_all(text.as_bytes());
                }
            }
            "term-stop" => {
                if let Some(run) = &state.run {
                    // SAFETY: signals the session the command leads (setsid made pgid = pid).
                    unsafe { libc::kill(-(run.child.id() as i32), libc::SIGHUP) };
                }
            }
            "term-run" => {
                if let Some(run) = state.run.as_mut() {
                    let _ = run.master.write_all(format!("{text}\r").as_bytes());
                    return;
                }
                let line = text.trim();
                if line.is_empty() {
                    return;
                }
                if line == "cd" || line.starts_with("cd ") {
                    let cwd = self.term_cwd(session);
                    match term::cd_target(&cwd, &line[2..], &settings::home()) {
                        Ok(dir) => {
                            self.edit.terms.entry(session).or_default().cwd = Some(dir);
                            self.send_term_cwd(session);
                        }
                        Err(error) => self.term_note(session, &error),
                    }
                    return;
                }
                let cwd = self.term_cwd(session);
                self.start_term(session, line, &cwd);
            }
            "term-run-file" => {
                let busy = state.run.is_some();
                let file = match self.allowed(message["path"].as_str().unwrap_or("")) {
                    Ok(file) => file,
                    Err(error) => return self.term_note(session, &error),
                };
                let Some((dir, line)) = term::run_line(&file) else {
                    return self.term_note(
                        session,
                        "this kind of file has no run command (Python, Rust, C, C++, Go, JavaScript, shell, Ruby, Swift, Java... or an executable)",
                    );
                };
                if busy {
                    return self.term_note(
                        session,
                        "a command is still running here: stop it (Ctrl-C) or open another terminal",
                    );
                }
                self.edit.terms.entry(session).or_default().cwd = Some(dir.clone());
                self.send_term_cwd(session);
                self.start_term(session, &line, &dir);
            }
            _ => {}
        }
    }

    fn term_cwd(&self, session: u64) -> PathBuf {
        let own = self.edit.terms.get(&session).and_then(|state| state.cwd.clone());
        let cwd = own.or_else(|| self.edit.places.roots.iter().find(|root| root.is_dir()).cloned());
        cwd.filter(|dir| dir.is_dir()).unwrap_or_else(settings::home)
    }

    fn send_term_cwd(&mut self, session: u64) {
        let cwd = self.term_cwd(session);
        let home = settings::home();
        let shown = match cwd.strip_prefix(&home) {
            Ok(rest) if rest.as_os_str().is_empty() => "~".to_string(),
            Ok(rest) => format!("~/{}", rest.display()),
            Err(_) => cwd.display().to_string(),
        };
        let running = self.edit.terms.get(&session).is_some_and(|state| state.run.is_some());
        self.send(
            View::Home,
            json!({"type": "term-cwd", "session": session, "path": cwd.display().to_string(), "shown": shown,
                   "running": running}),
        );
    }

    fn term_note(&mut self, session: u64, text: &str) {
        self.send(View::Home, json!({"type": "term-note", "session": session, "text": text}));
    }

    fn start_term(&mut self, session: u64, line: &str, cwd: &Path) {
        let (cols, rows) = self.edit.term_size;
        let pty = match term::spawn(line, cwd, cols.max(20), rows.max(4)) {
            Ok(pty) => pty,
            Err(error) => return self.term_note(session, &format!("could not start the shell: {error}")),
        };
        self.edit.next_term += 1;
        let id = self.edit.next_term;
        let reader = pty.master.try_clone();
        self.edit.terms.entry(session).or_default().run = Some(TermRun { id, child: pty.child, master: pty.master });
        self.send(View::Home, json!({"type": "term-start", "session": session, "id": id, "line": line}));
        let proxy = self.proxy.clone();
        let Ok(mut reader) = reader else { return };
        thread::spawn(move || {
            let mut pending = Vec::new();
            let mut buffer = [0u8; 16384];
            loop {
                match reader.read(&mut buffer) {
                    // 0, or EIO once every holder of the terminal closed it: the command is done.
                    Ok(0) | Err(_) => break,
                    Ok(count) => {
                        pending.extend_from_slice(&buffer[..count]);
                        let text = term::take_text(&mut pending);
                        if !text.is_empty() {
                            let _ = proxy.send_event(UserEvent::Edit(EditEvent::TermOutput { session, id, text }));
                        }
                    }
                }
            }
            let _ = proxy.send_event(UserEvent::Edit(EditEvent::TermEnded { session, id }));
        });
    }
}

/// Closing stdin ends ule after it kept unsaved work; the group goes after a grace.
fn stop_ule(mut run: UleRun) {
    run.stdin.take();
    thread::spawn(move || {
        let deadline = Instant::now() + ULE_GRACE;
        while Instant::now() < deadline {
            if matches!(run.child.try_wait(), Ok(Some(_))) {
                return;
            }
            thread::sleep(Duration::from_millis(50));
        }
        runner::stop_group(&mut run.child, Duration::from_secs(2));
    });
}

/// Drawings on PDF pages and pictures live beside Unlaw's data, never in the file itself.
fn ink_dir() -> PathBuf {
    super::home::storage_root().join("edit").join("ink")
}

/// pbcopy, the text on stdin.
fn copy_text(text: &str) -> Result<(), String> {
    let mut child = Command::new("/usr/bin/pbcopy")
        .stdin(Stdio::piped())
        .spawn()
        .map_err(|error| format!("could not copy: {error}"))?;
    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(text.as_bytes()).map_err(|error| format!("could not copy: {error}"))?;
    }
    child.wait().map_err(|error| format!("could not copy: {error}"))?;
    Ok(())
}

/// A terminal window in `dir`: Ghostty with its working-directory option, else Terminal.
fn open_terminal_at(dir: &Path) {
    let ghostty = ["/Applications/Ghostty.app", "~/Applications/Ghostty.app"]
        .iter()
        .map(|place| PathBuf::from(place.replacen('~', &settings::home().display().to_string(), 1)))
        .find(|place| place.exists());
    if let Some(app) = ghostty {
        let flag = format!("--working-directory={}", dir.display());
        let opened =
            Command::new("/usr/bin/open").arg("-na").arg(&app).args(["--args", &flag]).stdin(Stdio::null()).status();
        if opened.is_ok_and(|status| status.success()) {
            return;
        }
    }
    let _ = Command::new("/usr/bin/open").args(["-a", "Terminal"]).arg(dir).stdin(Stdio::null()).status();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn runnable_files_are_only_revealed() {
        assert!(runnable(Path::new("/tmp/Installer.pkg")));
        assert!(runnable(Path::new("/tmp/script.SH")));
        assert!(!runnable(Path::new("/tmp/does-not-exist.pdf")));
    }

    #[test]
    fn served_files_have_their_types_and_text_is_not_served() {
        assert_eq!(served_kind(Path::new("/a/b.PDF")), Some("application/pdf"));
        assert_eq!(served_kind(Path::new("/a/b.heic")), Some("image/heic"));
        assert_eq!(served_kind(Path::new("/a/b.html")), None);
        assert_eq!(served_kind(Path::new("/a/b")), None);
        assert_eq!(query_value("x=1&path=%2Ftmp%2Fa%20b.png", "path").as_deref(), Some("/tmp/a b.png"));
    }
}
