//! The Edit part of the main window, without window code: which files the page may
//! reach, the folders and recent files it remembers (`<config>/edit.json`), and the
//! input it may send to the editor (`ule --stream`), rebuilt from a whitelist.
//!
//! The page never names a file the user did not give the app: a path is reachable
//! only inside a folder added with "Add folder…" or as a file opened with "Open…"
//! (or dropped on the window), never through a symlink that leaves them, and never
//! in the places that hold keys and logins.

use std::path::{Component, Path, PathBuf};

use serde_json::{json, Value as Json};

/// Folders and recent files kept at most.
pub const MAX_ROOTS: usize = 32;
pub const MAX_RECENT: usize = 30;
/// Entries listed per folder.
pub const MAX_ENTRIES: usize = 5000;
/// A paste larger than this is refused (ule drops longer input lines too).
pub const MAX_PASTE: usize = 4 << 20;

/// Under the home folder: keys, logins and other apps' secrets.
const DENIED_HOME: &[&str] = &[
    ".ssh",
    ".gnupg",
    ".password-store",
    ".aws",
    ".config/gh",
    ".config/op",
    ".config/gcloud",
    ".cargo/credentials",
    ".cargo/credentials.toml",
    ".claude/.credentials.json",
    ".codex/auth.json",
    ".local/share/keyrings",
    "Library/Keychains",
    "Library/Cookies",
    "Library/Messages",
    "Library/Mail",
];

/// The folders and files the user gave Edit.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Places {
    pub roots: Vec<PathBuf>,
    pub recent: Vec<PathBuf>,
}

impl Places {
    /// edit.json as written by `to_json`; anything malformed is skipped.
    pub fn parse(text: &str) -> Places {
        let value: Json = serde_json::from_str(text).unwrap_or(Json::Null);
        let paths = |key: &str, max: usize| -> Vec<PathBuf> {
            let mut list: Vec<PathBuf> = Vec::new();
            for item in value[key].as_array().into_iter().flatten() {
                if let Some(path) = item.as_str().map(PathBuf::from).filter(|path| path.is_absolute()) {
                    if !list.contains(&path) && list.len() < max {
                        list.push(path);
                    }
                }
            }
            list
        };
        Places { roots: paths("roots", MAX_ROOTS), recent: paths("recent", MAX_RECENT) }
    }

    pub fn to_json(&self) -> Json {
        let text = |paths: &[PathBuf]| paths.iter().map(|path| path.display().to_string()).collect::<Vec<_>>();
        json!({"version": 1, "roots": text(&self.roots), "recent": text(&self.recent)})
    }

    pub fn add_root(&mut self, folder: PathBuf) {
        self.roots.retain(|existing| existing != &folder);
        self.roots.insert(0, folder);
        self.roots.truncate(MAX_ROOTS);
    }

    pub fn remove_root(&mut self, folder: &Path) {
        self.roots.retain(|existing| existing != folder);
    }

    pub fn touch(&mut self, file: PathBuf) {
        self.recent.retain(|existing| existing != &file);
        self.recent.insert(0, file);
        self.recent.truncate(MAX_RECENT);
    }

    pub fn forget(&mut self, file: &Path) {
        self.recent.retain(|existing| existing != file);
    }

    /// The real path of `raw` when the page may open it: inside a root, or a file the
    /// user opened (recent), after symlinks are resolved on both sides.
    pub fn allowed(&self, raw: &str, home: &Path) -> Result<PathBuf, String> {
        let path = plain_absolute(raw)?;
        let real = path.canonicalize().map_err(|_| format!("{} does not exist", path.display()))?;
        if let Some(reason) = denied(&real, home) {
            return Err(reason);
        }
        let inside_root =
            self.roots.iter().filter_map(|root| root.canonicalize().ok()).any(|root| real.starts_with(&root));
        let opened = self.recent.iter().filter_map(|file| file.canonicalize().ok()).any(|file| file == real);
        if inside_root || opened {
            Ok(real)
        } else {
            Err(format!("{} is not in a folder added to Edit", path.display()))
        }
    }
}

/// An absolute path with no `..`, `.` or NUL, as the page must send it.
pub fn plain_absolute(raw: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(raw);
    let plain = path.components().all(|part| matches!(part, Component::RootDir | Component::Normal(_)));
    if raw.is_empty() || raw.contains('\0') || !path.is_absolute() || !plain || raw.len() > 4096 {
        return Err(format!("not a usable path: {raw:?}"));
    }
    Ok(path)
}

/// Why a resolved path is never shown, if it is one of the protected places.
pub fn denied(real: &Path, home: &Path) -> Option<String> {
    let folded = |path: &Path| path.to_string_lossy().to_lowercase();
    let real_text = folded(real);
    let home = home.canonicalize().unwrap_or_else(|_| home.to_path_buf());
    for relative in DENIED_HOME {
        let protected = folded(&home.join(relative));
        // macOS disks ignore case: compare folded, on whole components.
        if real_text == protected || real_text.starts_with(&format!("{protected}/")) {
            return Some("keys and logins are not opened in Edit".into());
        }
    }
    None
}

/// What a file type may open with (`open` in filetypes.toml).
const OPEN_WITH: &[&str] = &["editor", "viewer", "app"];

/// `<config>/filetypes.toml`: the user's own icon, color and way to open, per suffix
/// (`[types.vue]`) or whole name (`[names."Makefile"]`). Icons are names of pictures in
/// `<config>/icons` (`vue` = icons/vue.svg or .png) or of the app's own icons. Mistakes
/// are reported and skipped, the rest applies.
pub fn file_types(text: &str) -> (Json, Vec<String>) {
    let mut warnings = Vec::new();
    let mut answer = json!({"types": {}, "names": {}});
    let document = match text.parse::<toml_edit::DocumentMut>() {
        Ok(document) => document,
        Err(error) => {
            warnings.push(format!("filetypes.toml: {}", error.message()));
            return (answer, warnings);
        }
    };
    for (section, item) in document.iter() {
        if section != "types" && section != "names" {
            warnings.push(format!(
                "filetypes.toml: unknown section [{section}] (use [types.<suffix>] or [names.\"<file name>\"])"
            ));
            continue;
        }
        let Some(table) = item.as_table_like() else { continue };
        for (key, entry) in table.iter() {
            let key_ok = !key.is_empty() && key.len() <= 64 && !key.contains('/') && !key.chars().any(char::is_control);
            let Some(entry) = entry.as_table_like().filter(|_| key_ok) else {
                warnings.push(format!("filetypes.toml: [{section}.{key}] is not usable"));
                continue;
            };
            let mut kept = serde_json::Map::new();
            for (field, value) in entry.iter() {
                let text = value.as_str().unwrap_or("");
                let ok = match field {
                    "icon" => icon_name_ok(text),
                    "color" => {
                        text.len() == 7
                            && text.starts_with('#')
                            && text[1..].bytes().all(|byte| byte.is_ascii_hexdigit())
                    }
                    "open" => OPEN_WITH.contains(&text),
                    _ => false,
                };
                if ok {
                    kept.insert(field.to_string(), json!(text));
                } else {
                    warnings.push(format!("filetypes.toml: {section}.{key}.{field} is not usable"));
                }
            }
            let key = if section == "types" { key.trim_start_matches('.').to_lowercase() } else { key.to_string() };
            answer[section][key] = Json::Object(kept);
        }
    }
    (answer, warnings)
}

/// An icon name: letters, digits, `-` and `_`, as in `icons/<name>.svg`.
pub fn icon_name_ok(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 64
        && name.bytes().all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
}

/// Theme files in `dir` (`<config>/themes/<name>.toml`), by name.
pub fn theme_files(dir: &Path) -> Vec<String> {
    let mut names: Vec<String> = std::fs::read_dir(dir)
        .map(|entries| {
            entries
                .flatten()
                .filter_map(|entry| {
                    let path = entry.path();
                    let stem = path.file_stem()?.to_str()?.to_string();
                    (path.extension().is_some_and(|suffix| suffix == "toml")
                        && !stem.starts_with('.')
                        && !stem.is_empty())
                    .then_some(stem)
                })
                .collect()
        })
        .unwrap_or_default();
    names.sort();
    names
}

/// The pictures in the icons folder that can be shown: `name.svg` or `name.png`.
pub fn icon_names(dir: &Path) -> Vec<String> {
    let mut names: Vec<String> = std::fs::read_dir(dir)
        .map(|entries| {
            entries
                .flatten()
                .filter_map(|entry| {
                    let path = entry.path();
                    let suffix = path.extension()?.to_str()?.to_lowercase();
                    let stem = path.file_stem()?.to_str()?.to_string();
                    (["svg", "png"].contains(&suffix.as_str()) && icon_name_ok(&stem) && path.is_file()).then_some(stem)
                })
                .collect()
        })
        .unwrap_or_default();
    names.sort();
    names.dedup();
    names
}

/// The theme file `ul` makes for "New theme": it starts from a theme and lists what can change.
pub fn new_theme_text(base: &str) -> String {
    format!(
        "# An Unlaw theme: Edit, the terminal editor ule and (with look.colors = \"editor\") every\n\
         # window of Unlaw.app use it. Pick it in Edit's status bar or with `theme = \"<file name>\"` in\n\
         # ule.toml. Saving this file shows the change at once.\n\
         # A value is a color (\"#rrggbb\") or {{ fg = \"#..\", bg = \"#..\", modifiers = [\"bold\"] }}.\n\
         # Everything not set here comes from the theme named in `inherits`.\n\
         inherits = \"{base}\"\n\n\
         [palette]\n\
         # bg = \"#1e1f24\"\n\
         # accent = \"#e8a530\"\n\n\
         # Window and editor background and text:\n\
         # \"ui.text\" = {{ fg = \"#e4e5e9\", bg = \"bg\" }}\n\
         # Panels, the status bar (Unlaw.app's cards and side bar take it too):\n\
         # \"ui.statusline\" = {{ fg = \"#e4e5e9\", bg = \"#26272c\" }}\n\
         # The accent (buttons, the chosen item):\n\
         # \"ui.mode.normal\" = {{ fg = \"#000000\", bg = \"accent\" }}\n\
         # \"ui.selection\" = {{ bg = \"#34363d\" }}\n\
         # \"ui.cursorline\" = {{ bg = \"#24252a\" }}\n\
         # \"ui.linenr\" = \"#6b6e78\"\n\
         # \"ui.separator\" = \"#34363d\"\n\
         # \"ui.explorer.dir\" = \"#8ab4f8\"\n\
         # Code:\n\
         # \"syntax.keyword\" = \"#c678dd\"\n\
         # \"syntax.string\" = \"#98c379\"\n\
         # \"syntax.comment\" = {{ fg = \"#5c6370\", modifiers = [\"italic\"] }}\n"
    )
}

/// The filetypes.toml written when there is none yet.
pub const FILE_TYPES_TEMPLATE: &str = "\
# Your own file types in Unlaw.app's Edit.
# [types.<suffix>] for files ending in .<suffix>, [names.\"<file name>\"] for whole names.
#   icon  = a picture you put in ~/.config/unlaw/icons (vue = icons/vue.svg or vue.png),
#           or one of the app's own: file, image, folder, gear, code, music, video, book
#   color = \"#rrggbb\" for the icon
#   open  = \"editor\" (the code editor), \"viewer\" (pages, pictures, preview) or \"app\" (its own app)
#
# [types.vue]
# icon = \"vue\"
# color = \"#41b883\"
#
# [types.log]
# open = \"editor\"
#
# [names.\"Justfile\"]
# icon = \"gear\"
# color = \"#c8a26b\"
";

/// Drawings of one file: `<fnv-1a of the resolved path>.json`, so a name never carries the path.
pub fn ink_name(path: &Path) -> String {
    let mut hash: u64 = 0xcbf2_9ce4_8422_2325;
    for byte in path.to_string_lossy().as_bytes() {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x0100_0000_01b3);
    }
    format!("{hash:016x}.json")
}

/// Most bytes one file's drawings may take.
pub const MAX_INK: usize = 4 << 20;
const INK_KINDS: &[&str] = &["pen", "marker", "text", "sticky", "thread"];

/// Drawings as the page sends them: `{version: 1, pages: {"N": [item, ...]}}`, items of a known
/// kind with numbers where coordinates go; text and colors are only ever shown with textContent.
pub fn check_ink(ink: &Json) -> Result<(), String> {
    if ink.to_string().len() > MAX_INK {
        return Err("too many drawings for one file".into());
    }
    if ink["version"] != 1 {
        return Err("unknown drawings format".into());
    }
    let pages = ink["pages"].as_object().ok_or("drawings need pages")?;
    for (page, items) in pages {
        if !page.parse::<u32>().is_ok_and(|number| (1..=100_000).contains(&number)) {
            return Err(format!("not a page: {page}"));
        }
        for item in items.as_array().ok_or("a page holds a list")? {
            let kind = item["kind"].as_str().unwrap_or("");
            if !INK_KINDS.contains(&kind) {
                return Err(format!("unknown drawing kind {kind:?}"));
            }
            let numbers = |key: &str| {
                item[key].as_array().is_none_or(|list| {
                    list.iter().all(|point| {
                        point.as_array().is_some_and(|pair| pair.len() == 2 && pair.iter().all(Json::is_number))
                    })
                })
            };
            if !numbers("points") {
                return Err("points must be [x, y] pairs".into());
            }
            for key in ["x", "y", "w", "h", "width", "size"] {
                if !item[key].is_null() && !item[key].is_number() {
                    return Err(format!("{key} must be a number"));
                }
            }
            for key in ["text", "color", "id"] {
                if !item[key].is_null() && !item[key].is_string() {
                    return Err(format!("{key} must be text"));
                }
            }
            // A thread end is a point [x, y] or a sticky {id}.
            for key in ["from", "to"] {
                let end = &item[key];
                let point = end.as_array().is_some_and(|pair| pair.len() == 2 && pair.iter().all(Json::is_number));
                if !end.is_null() && !point && !end["id"].is_string() {
                    return Err(format!("{key} must be a point or a sticky"));
                }
            }
        }
    }
    Ok(())
}

/// Never listed: version control internals and Finder's notes (other dot files show, as in Zed).
const HIDDEN_NAMES: &[&str] = &[".git", ".DS_Store", ".hg", ".svn"];

/// What a folder holds, folders first, `.git` and `.DS_Store` left out; `truncated` when capped.
pub fn list_folder(folder: &Path) -> Result<Json, String> {
    let read = std::fs::read_dir(folder).map_err(|error| format!("{}: {error}", folder.display()))?;
    let mut entries: Vec<(bool, String, PathBuf)> = Vec::new();
    let mut truncated = false;
    for entry in read.flatten() {
        let name = entry.file_name().to_string_lossy().to_string();
        if HIDDEN_NAMES.contains(&name.as_str()) {
            continue;
        }
        if entries.len() >= MAX_ENTRIES {
            truncated = true;
            break;
        }
        // A symlinked folder lists as a folder; allowed() still checks where it leads.
        let is_dir = entry.path().is_dir();
        entries.push((is_dir, name, entry.path()));
    }
    entries.sort_by(|a, b| b.0.cmp(&a.0).then_with(|| a.1.to_lowercase().cmp(&b.1.to_lowercase())));
    let list: Vec<Json> = entries
        .into_iter()
        .map(|(dir, name, path)| json!({"name": name, "path": path.display().to_string(), "dir": dir}))
        .collect();
    Ok(json!({"path": folder.display().to_string(), "entries": list, "truncated": truncated}))
}

const KEY_NAMES: &[&str] = &[
    "Esc",
    "Enter",
    "Tab",
    "BackTab",
    "Backspace",
    "Delete",
    "Up",
    "Down",
    "Left",
    "Right",
    "Home",
    "End",
    "PageUp",
    "PageDown",
    "Insert",
];

/// One input line for ule, rebuilt from what the page sent; paths go through `allowed`
/// first (`check`), so the page cannot open a file it was not given.
/// Editor commands the page may run (ule's `stream::COMMANDS`).
pub const ULE_COMMANDS: &[&str] = &[
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
    // ule's text actions (`ule/src/actions.rs`), the Zed keys of the page.
    "select_all",
    "select_line",
    "indent",
    "outdent",
    "newline_below",
    "newline_above",
    "join_lines",
    "uppercase",
    "lowercase",
    "transpose",
    "expand_selection",
    "shrink_selection",
    "select_next_occurrence",
    "select_all_occurrences",
    "add_cursor_above",
    "add_cursor_below",
    "single_cursor",
    "search_next",
    "search_prev",
    "search_selection",
    "replace",
    "jump_back",
    "jump_forward",
];

pub fn ule_event(event: &Json, check: &dyn Fn(&str) -> Result<PathBuf, String>) -> Result<Json, String> {
    let flag = |value: &Json, key: &str| value.get(key).and_then(Json::as_bool).unwrap_or(false);
    let cell = |value: &Json, key: &str| value.get(key).and_then(Json::as_u64).filter(|n| *n < 1000);
    if let Some(key) = event.get("key") {
        let code = key.get("code").and_then(Json::as_str).unwrap_or("");
        let mut chars = code.chars();
        let single = matches!((chars.next(), chars.next()), (Some(c), None) if !c.is_control());
        let function = code.strip_prefix('F').and_then(|n| n.parse::<u8>().ok()).is_some_and(|n| (1..=24).contains(&n));
        if !(single || function || KEY_NAMES.contains(&code)) {
            return Err(format!("unknown key {code:?}"));
        }
        return Ok(json!({"key": {
            "code": code, "ctrl": flag(key, "ctrl"), "alt": flag(key, "alt"), "shift": flag(key, "shift"),
        }}));
    }
    if let Some(text) = event.get("paste") {
        let text = text.as_str().ok_or("paste needs text")?;
        if text.len() > MAX_PASTE {
            return Err("the pasted text is larger than 4 MB".into());
        }
        return Ok(json!({"paste": text}));
    }
    if let Some(mouse) = event.get("mouse") {
        let kind = mouse.get("kind").and_then(Json::as_str).unwrap_or("");
        if !["down", "drag", "up", "scroll_up", "scroll_down"].contains(&kind) {
            return Err(format!("unknown mouse event {kind:?}"));
        }
        let (x, y) = (cell(mouse, "x").ok_or("no x")?, cell(mouse, "y").ok_or("no y")?);
        return Ok(json!({"mouse": {"kind": kind, "x": x, "y": y, "alt": flag(mouse, "alt")}}));
    }
    if let Some(size) = event.get("resize") {
        let rows = size.get("rows").and_then(Json::as_u64).filter(|n| (5..=400).contains(n)).ok_or("bad rows")?;
        let cols = size.get("cols").and_then(Json::as_u64).filter(|n| (20..=800).contains(n)).ok_or("bad cols")?;
        return Ok(json!({"resize": {"rows": rows, "cols": cols}}));
    }
    if let Some(focus) = event.get("focus") {
        return Ok(json!({"focus": focus.as_bool().ok_or("focus is true or false")?}));
    }
    if let Some(theme) = event.get("theme") {
        let theme = theme.as_str().filter(|theme| ["light", "dark"].contains(theme)).ok_or("theme is light or dark")?;
        return Ok(json!({"theme": theme}));
    }
    if let Some(name) = event.get("command") {
        let name = name.as_str().filter(|name| ULE_COMMANDS.contains(name)).ok_or("unknown editor command")?;
        return Ok(json!({"command": name}));
    }
    if event.get("redraw").is_some() {
        return Ok(json!({"redraw": true}));
    }
    if let Some(open) = event.get("open") {
        let path = check(open.get("path").and_then(Json::as_str).unwrap_or(""))?;
        let line = open.get("line").and_then(Json::as_u64).filter(|line| *line > 0);
        return Ok(json!({"open": {"path": path.display().to_string(), "line": line}}));
    }
    // The project folder: where file search and grep look (`:cd`). Only an added folder.
    if let Some(path) = event.get("cd") {
        let path = check(path.as_str().unwrap_or(""))?;
        if !path.is_dir() {
            return Err("cd needs a folder".into());
        }
        return Ok(json!({"cd": path.display().to_string()}));
    }
    for name in ["show", "close"] {
        if let Some(path) = event.get(name) {
            let path = check(path.as_str().unwrap_or(""))?;
            return Ok(json!({name: path.display().to_string()}));
        }
    }
    Err("unknown editor event".into())
}

/// The editor's two settings the app changes, kept in ule's own `ule.toml` (`[editor]`),
/// so the terminal ule and Edit always agree.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UlePrefs {
    /// "vim" (modes) or "standard" (no modes, like VS Code or Zed).
    pub editing: String,
    pub theme: String,
}

/// Themes ule ships (`ule/runtime/themes.toml`) plus `[themes.*]` of the user's ule.toml.
/// Built-in themes, then `[themes.*]` of ule.toml, then theme files (`files`, see `theme_files`).
pub fn ule_themes(ule_toml: &str, files: &[String]) -> Vec<String> {
    let mut names: Vec<String> = include_str!("../../ule/runtime/themes.toml")
        .parse::<toml_edit::DocumentMut>()
        .map(|document| document.iter().map(|(name, _)| name.to_string()).collect())
        .unwrap_or_default();
    if let Ok(document) = ule_toml.parse::<toml_edit::DocumentMut>() {
        if let Some(themes) = document.get("themes").and_then(|item| item.as_table_like()) {
            for (name, _) in themes.iter() {
                if !names.iter().any(|known| known == name) {
                    names.push(name.to_string());
                }
            }
        }
    }
    for name in files {
        if !names.contains(name) {
            names.push(name.clone());
        }
    }
    names
}

pub fn ule_prefs(ule_toml: &str) -> UlePrefs {
    let document = ule_toml.parse::<toml_edit::DocumentMut>().ok();
    let read = |key: &str| {
        document.as_ref().and_then(|document| document.get("editor")?.get(key)?.as_str().map(str::to_string))
    };
    UlePrefs {
        editing: read("editing").filter(|value| value == "standard").unwrap_or_else(|| "vim".into()),
        theme: read("theme").unwrap_or_else(|| "unlaw".into()),
    }
}

/// ule.toml with these values set; comments and every other key stay as they are.
pub fn with_ule_prefs(
    ule_toml: &str,
    editing: Option<&str>,
    theme: Option<&str>,
    files: &[String],
) -> Result<String, String> {
    let mut document: toml_edit::DocumentMut =
        ule_toml.parse().map_err(|error: toml_edit::TomlError| format!("ule.toml: {}", error.message()))?;
    if let Some(editing) = editing {
        if !["vim", "standard"].contains(&editing) {
            return Err("keys are vim or standard".into());
        }
    }
    if let Some(theme) = theme {
        if !ule_themes(ule_toml, files).iter().any(|name| name == theme) {
            return Err(format!("ule has no theme named {theme:?}"));
        }
    }
    let editor = document.entry("editor").or_insert(toml_edit::table());
    if editor.as_table_like().is_none() {
        return Err("ule.toml: [editor] is not a table".into());
    }
    if let Some(editing) = editing {
        editor["editing"] = toml_edit::value(editing);
    }
    if let Some(theme) = theme {
        editor["theme"] = toml_edit::value(theme);
    }
    Ok(document.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn sandbox(name: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!("unlaw-edit-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        root.canonicalize().unwrap()
    }

    #[test]
    fn only_added_folders_and_opened_files_are_reachable() {
        let root = sandbox("allowed");
        let home = root.join("home");
        let project = home.join("project");
        fs::create_dir_all(project.join("src")).unwrap();
        fs::write(project.join("src/main.rs"), "fn main() {}\n").unwrap();
        fs::write(home.join("notes.md"), "# hi\n").unwrap();
        fs::write(home.join("other.txt"), "x").unwrap();
        fs::create_dir_all(home.join(".ssh")).unwrap();
        fs::write(home.join(".ssh/id_ed25519"), "secret").unwrap();
        std::os::unix::fs::symlink(home.join("other.txt"), project.join("link.txt")).unwrap();
        let mut places = Places::default();
        places.add_root(project.clone());
        places.touch(home.join("notes.md"));
        let check = |raw: &Path| places.allowed(&raw.display().to_string(), &home);
        assert_eq!(check(&project.join("src/main.rs")).unwrap(), project.join("src/main.rs"));
        assert!(check(&home.join("notes.md")).is_ok(), "an opened file");
        assert!(check(&home.join("other.txt")).is_err(), "neither in a folder nor opened");
        assert!(check(&project.join("link.txt")).is_err(), "a symlink out of the folder");
        assert!(places.allowed(&format!("{}/../other.txt", project.display()), &home).is_err(), "no ..");
        assert!(places.allowed("relative.txt", &home).is_err());
        assert!(places.allowed("", &home).is_err());
        let mut places = places.clone();
        places.add_root(home.clone());
        let check = |raw: &Path| places.allowed(&raw.display().to_string(), &home);
        assert!(check(&home.join("other.txt")).is_ok());
        assert!(check(&home.join(".ssh/id_ed25519")).is_err(), "keys stay out even inside a folder");
        assert!(places.allowed(&home.join(".SSH/id_ed25519").display().to_string(), &home).is_err(), "case ignored");
    }

    #[test]
    fn places_round_trip_and_stay_bounded() {
        let mut places = Places::default();
        for index in 0..40 {
            places.touch(PathBuf::from(format!("/tmp/file-{index}.txt")));
        }
        places.touch(PathBuf::from("/tmp/file-5.txt"));
        assert_eq!(places.recent.len(), MAX_RECENT);
        assert_eq!(places.recent[0], PathBuf::from("/tmp/file-5.txt"));
        places.add_root(PathBuf::from("/tmp/a"));
        places.add_root(PathBuf::from("/tmp/b"));
        places.add_root(PathBuf::from("/tmp/a"));
        assert_eq!(places.roots, vec![PathBuf::from("/tmp/a"), PathBuf::from("/tmp/b")]);
        let again = Places::parse(&places.to_json().to_string());
        assert_eq!(again, places);
        let messy = Places::parse(r#"{"roots": ["relative", 3, "/ok", "/ok"], "recent": "no"}"#);
        assert_eq!(messy.roots, vec![PathBuf::from("/ok")]);
        assert!(messy.recent.is_empty());
        assert_eq!(Places::parse("not json"), Places::default());
    }

    #[test]
    fn file_types_keep_what_is_usable() {
        let (types, warnings) = file_types(
            "[types.Vue]\nicon = \"vue\"\ncolor = \"#41b883\"\nopen = \"editor\"\n\
             [types.bad]\nicon = \"../x\"\ncolor = \"red\"\nopen = \"run\"\nother = 1\n\
             [names.\"Justfile\"]\nicon = \"gear\"\n[nope]\n",
        );
        assert_eq!(types["types"]["vue"], json!({"icon": "vue", "color": "#41b883", "open": "editor"}));
        assert_eq!(types["types"]["bad"], json!({}));
        assert_eq!(types["names"]["Justfile"]["icon"], "gear");
        assert_eq!(warnings.len(), 5, "{warnings:?}");
        assert!(file_types("not = = toml").1[0].contains("filetypes.toml"));
        assert!(file_types(FILE_TYPES_TEMPLATE).1.is_empty(), "the template itself is clean");
        let root = sandbox("icons");
        for name in ["vue.svg", "rust.PNG", "bad name.svg", "x.gif", ".hidden.svg"] {
            fs::write(root.join(name), "").unwrap();
        }
        assert_eq!(icon_names(&root), vec!["rust", "vue"]);
        assert!(new_theme_text("nord").contains("inherits = \"nord\""));
        assert!(new_theme_text("nord").parse::<toml_edit::DocumentMut>().is_ok());
    }

    #[test]
    fn drawings_are_checked_and_named_by_hash() {
        let good = json!({"version": 1, "pages": {"1": [
            {"kind": "pen", "color": "#ff0000", "width": 2, "points": [[1, 2], [3.5, 4]]},
            {"kind": "sticky", "id": "a", "x": 10, "y": 10, "w": 120, "h": 90, "text": "hi"},
            {"kind": "thread", "from": {"id": "a"}, "to": [50, 60]},
        ]}});
        assert_eq!(check_ink(&good), Ok(()));
        for bad in [
            json!({"version": 2, "pages": {}}),
            json!({"version": 1, "pages": {"0": []}}),
            json!({"version": 1, "pages": {"1": [{"kind": "script"}]}}),
            json!({"version": 1, "pages": {"1": [{"kind": "pen", "points": [[1, "x"]]}]}}),
            json!({"version": 1, "pages": {"1": [{"kind": "text", "x": "1"}]}}),
            json!({"version": 1, "pages": {"1": [{"kind": "text", "text": "x".repeat(MAX_INK)}]}}),
        ] {
            assert!(check_ink(&bad).is_err(), "{bad}");
        }
        let name = ink_name(Path::new("/a/b.pdf"));
        assert_eq!(name, ink_name(Path::new("/a/b.pdf")));
        assert_ne!(name, ink_name(Path::new("/a/c.pdf")));
        assert!(name.ends_with(".json") && !name.contains('/'));
    }

    #[test]
    fn folders_list_folders_first_without_git_internals() {
        let root = sandbox("list");
        fs::create_dir_all(root.join("b-folder")).unwrap();
        fs::create_dir_all(root.join(".git")).unwrap();
        fs::write(root.join("A.txt"), "").unwrap();
        fs::write(root.join("c.rs"), "").unwrap();
        fs::write(root.join(".gitignore"), "").unwrap();
        fs::write(root.join(".DS_Store"), "").unwrap();
        let listed = list_folder(&root).unwrap();
        let names: Vec<&str> =
            listed["entries"].as_array().unwrap().iter().map(|e| e["name"].as_str().unwrap()).collect();
        assert_eq!(names, vec!["b-folder", ".gitignore", "A.txt", "c.rs"], "dot files show, as in Zed");
        assert_eq!(listed["entries"][0]["dir"], true);
        assert!(list_folder(&root.join("missing")).is_err());
    }

    #[test]
    fn editor_events_are_rebuilt_from_a_whitelist() {
        let root = sandbox("events");
        fs::write(root.join("a.rs"), "").unwrap();
        let mut places = Places::default();
        places.add_root(root.clone());
        let home = root.join("home");
        let check = |raw: &str| places.allowed(raw, &home);
        let event = |value: Json| ule_event(&value, &check);
        assert_eq!(
            event(json!({"key": {"code": "s", "ctrl": true, "extra": 1}})).unwrap(),
            json!({"key": {"code": "s", "ctrl": true, "alt": false, "shift": false}})
        );
        assert!(event(json!({"key": {"code": "F5"}})).is_ok());
        for bad in [
            json!({"key": {"code": "Nope"}}),
            json!({"key": {"code": "F99"}}),
            json!({"key": {"code": "\u{7}"}}),
            json!({"mouse": {"kind": "middle", "x": 1, "y": 1}}),
            json!({"mouse": {"kind": "down", "x": 5000, "y": 1}}),
            json!({"resize": {"rows": 1, "cols": 80}}),
            json!({"theme": "blue"}),
            json!({"open": {"path": "/etc/passwd"}}),
            json!({"show": "relative.rs"}),
            json!({"paste": "x".repeat(MAX_PASTE + 1)}),
            json!({"command": "!rm -rf ~"}),
        ] {
            assert!(event(bad.clone()).is_err(), "{bad}");
        }
        let opened = event(json!({"open": {"path": root.join("a.rs").display().to_string(), "line": 3}})).unwrap();
        assert_eq!(opened["open"]["line"], 3);
        assert_eq!(event(json!({"resize": {"rows": 30, "cols": 100}})).unwrap()["resize"]["cols"], 100);
        assert_eq!(event(json!({"redraw": 1})).unwrap(), json!({"redraw": true}));
    }

    #[test]
    fn ule_prefs_live_in_ule_toml_and_keep_the_rest() {
        assert_eq!(ule_prefs(""), UlePrefs { editing: "vim".into(), theme: "unlaw".into() });
        let text = "# mine\n[editor]\ntab_width = 2 # two\n\n[themes.mine]\ninherits = \"nord\"\n";
        let saved = with_ule_prefs(text, Some("standard"), Some("mine"), &[]).unwrap();
        assert!(saved.contains("# mine") && saved.contains("tab_width = 2 # two"), "{saved}");
        assert_eq!(ule_prefs(&saved), UlePrefs { editing: "standard".into(), theme: "mine".into() });
        let saved = with_ule_prefs("", None, Some("dracula"), &[]).unwrap();
        assert_eq!(ule_prefs(&saved).theme, "dracula");
        assert!(with_ule_prefs("", Some("emacs"), None, &[]).is_err());
        assert!(with_ule_prefs("", None, Some("nope"), &[]).is_err());
        assert!(with_ule_prefs("", None, Some("mine"), &["mine".to_string()]).is_ok(), "a theme file");
        assert!(with_ule_prefs("editor = 1\n", Some("vim"), None, &[]).is_err());
        assert!(with_ule_prefs("[broken\n", Some("vim"), None, &[]).is_err(), "an unreadable file is never replaced");
        for name in ["unlaw", "onedark", "one-light", "nord", "solarized-light"] {
            assert!(ule_themes("", &[]).contains(&name.to_string()), "{name}");
        }
    }

    #[test]
    fn every_zed_key_of_the_page_is_an_allowed_editor_command() {
        let page = include_str!("../ui/edit.js");
        let start = page.find("const ZED_KEYS = [").unwrap();
        let end = start + page[start..].find("\n];").unwrap();
        let mut seen = 0;
        for line in page[start..end].lines() {
            let Some(rest) = line.trim().strip_prefix("[\"") else { continue };
            let Some((_, action)) = rest.split_once("\", ") else { continue };
            if let Some(name) = action.strip_prefix('"').and_then(|name| name.split('"').next()) {
                assert!(ULE_COMMANDS.contains(&name), "{name} is not in ULE_COMMANDS");
                seen += 1;
            }
        }
        assert!(seen > 30, "only {seen} commands found");
    }
}
