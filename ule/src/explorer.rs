//! The file explorer sidebar: a tree you can open, create, rename and trash files in.

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use crate::document::display_path;
use crate::editor::{Editor, Focus};
use crate::keys::{Code, Key};
use crate::widgets::{ConfirmAction, InputAction, Prompt, PromptKind};

#[derive(Clone, Debug)]
pub struct Entry {
    pub path: PathBuf,
    pub depth: usize,
    pub dir: bool,
    pub name: String,
}

#[derive(Debug)]
pub struct Explorer {
    pub root: PathBuf,
    pub entries: Vec<Entry>,
    pub selected: usize,
    pub offset: usize,
    pub hidden: bool,
    expanded: HashSet<PathBuf>,
}

const SKIP: &[&str] = &[".git", ".DS_Store", "__pycache__", ".mypy_cache", ".ruff_cache"];

impl Explorer {
    pub fn new(root: PathBuf, hidden: bool) -> Self {
        let mut explorer =
            Explorer { root, entries: Vec::new(), selected: 0, offset: 0, hidden, expanded: HashSet::new() };
        explorer.refresh();
        explorer
    }

    pub fn refresh(&mut self) {
        let selected = self.entries.get(self.selected).map(|entry| entry.path.clone());
        self.entries.clear();
        let root = self.root.clone();
        self.add_dir(&root, 0);
        if let Some(path) = selected {
            if let Some(index) = self.entries.iter().position(|entry| entry.path == path) {
                self.selected = index;
            }
        }
        self.selected = self.selected.min(self.entries.len().saturating_sub(1));
    }

    fn add_dir(&mut self, dir: &Path, depth: usize) {
        let Ok(read) = std::fs::read_dir(dir) else {
            return;
        };
        let mut items: Vec<(bool, String, PathBuf)> = read
            .filter_map(Result::ok)
            .filter_map(|entry| {
                let name = entry.file_name().to_string_lossy().into_owned();
                if SKIP.contains(&name.as_str()) || (!self.hidden && name.starts_with('.')) {
                    return None;
                }
                let path = entry.path();
                Some((path.is_dir(), name, path))
            })
            .collect();
        // Folders first, then files, each alphabetically ignoring case.
        items.sort_by(|a, b| b.0.cmp(&a.0).then_with(|| a.1.to_lowercase().cmp(&b.1.to_lowercase())));
        for (dir, name, path) in items {
            let expanded = dir && self.expanded.contains(&path);
            self.entries.push(Entry { path: path.clone(), depth, dir, name });
            if expanded {
                self.add_dir(&path, depth + 1);
            }
        }
    }

    pub fn is_expanded(&self, path: &Path) -> bool {
        self.expanded.contains(path)
    }

    /// Expands the folders down to `path` and selects it.
    pub fn reveal(&mut self, path: &Path) {
        let Ok(relative) = path.strip_prefix(&self.root) else {
            return;
        };
        let mut current = self.root.clone();
        for part in relative.parent().map(|parent| parent.components().collect::<Vec<_>>()).unwrap_or_default() {
            current.push(part);
            self.expanded.insert(current.clone());
        }
        self.refresh();
        if let Some(index) = self.entries.iter().position(|entry| entry.path == path) {
            self.selected = index;
        }
    }

    fn toggle(&mut self, index: usize) {
        let Some(entry) = self.entries.get(index) else {
            return;
        };
        if !entry.dir {
            return;
        }
        let path = entry.path.clone();
        if !self.expanded.remove(&path) {
            self.expanded.insert(path);
        }
        self.refresh();
    }

    fn selected_dir(&self) -> PathBuf {
        match self.entries.get(self.selected) {
            Some(entry) if entry.dir => entry.path.clone(),
            Some(entry) => entry.path.parent().map_or_else(|| self.root.clone(), Path::to_path_buf),
            None => self.root.clone(),
        }
    }
}

/// Moves a file to the macOS Trash (Finder via osascript; falls back to ~/.Trash).
pub fn trash(path: &Path) -> Result<(), String> {
    let absolute = crate::document::absolute(path);
    std::fs::symlink_metadata(&absolute).map_err(|error| format!("{}: {error}", path.display()))?;
    let script = format!(
        "tell application \"Finder\" to delete POSIX file \"{}\"",
        absolute.to_string_lossy().replace('\\', "\\\\").replace('"', "\\\"")
    );
    let finder = std::process::Command::new("osascript")
        .args(["-e", &script])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status();
    if finder.is_ok_and(|status| status.success()) {
        return Ok(());
    }
    let bin = crate::config::home().join(".Trash");
    std::fs::create_dir_all(&bin).map_err(|error| error.to_string())?;
    let name = absolute.file_name().ok_or("no file name")?.to_string_lossy().into_owned();
    let mut target = bin.join(&name);
    let mut number = 2;
    while target.exists() {
        target = bin.join(format!("{name} {number}"));
        number += 1;
    }
    std::fs::rename(&absolute, &target).map_err(|error| format!("trash: {error}"))
}

pub fn key(ed: &mut Editor, key: Key) {
    let height = ed.size.1.saturating_sub(3) as usize;
    let Some(explorer) = ed.explorer.as_mut() else {
        ed.focus_area = Focus::View;
        return;
    };
    let count = explorer.entries.len();
    match (key.code, key.ctrl) {
        (Code::Char('j'), false) | (Code::Down, _) => {
            explorer.selected = (explorer.selected + 1).min(count.saturating_sub(1))
        }
        (Code::Char('k'), false) | (Code::Up, _) => explorer.selected = explorer.selected.saturating_sub(1),
        (Code::Char('g'), false) | (Code::Home, _) => explorer.selected = 0,
        (Code::Char('G'), false) | (Code::End, _) => explorer.selected = count.saturating_sub(1),
        (Code::Char('d'), true) => explorer.selected = (explorer.selected + height / 2).min(count.saturating_sub(1)),
        (Code::Char('u'), true) => explorer.selected = explorer.selected.saturating_sub(height / 2),
        (Code::Enter, _) | (Code::Char('l'), false) | (Code::Char('o'), false) | (Code::Right, _) => {
            let Some(entry) = explorer.entries.get(explorer.selected).cloned() else {
                return;
            };
            if entry.dir {
                if key.code == Code::Char('l') && explorer.is_expanded(&entry.path) {
                    explorer.selected = (explorer.selected + 1).min(count.saturating_sub(1));
                } else {
                    let index = explorer.selected;
                    explorer.toggle(index);
                }
            } else {
                ed.focus_area = Focus::View;
                if let Err(error) = ed.open(&entry.path) {
                    ed.error(error);
                }
            }
        }
        (Code::Char('h'), false) | (Code::Left, _) => {
            let Some(entry) = explorer.entries.get(explorer.selected).cloned() else {
                return;
            };
            if entry.dir && explorer.is_expanded(&entry.path) {
                let index = explorer.selected;
                explorer.toggle(index);
            } else if let Some(parent) =
                (0..explorer.selected).rev().find(|index| explorer.entries[*index].depth + 1 == entry.depth)
            {
                explorer.selected = parent;
            } else if entry.depth == 0 {
                // At the top: go up one folder.
                if let Some(parent) = explorer.root.parent().map(Path::to_path_buf) {
                    let old = explorer.root.clone();
                    explorer.root = parent;
                    explorer.expanded.insert(old.clone());
                    explorer.refresh();
                    if let Some(index) = explorer.entries.iter().position(|entry| entry.path == old) {
                        explorer.selected = index;
                    }
                }
            }
        }
        (Code::Char('.'), false) => {
            explorer.hidden = !explorer.hidden;
            explorer.refresh();
        }
        (Code::Char('R'), false) => explorer.refresh(),
        (Code::Char('C'), false) => {
            // Make the selected folder the root.
            let dir = explorer.selected_dir();
            explorer.root = dir;
            explorer.selected = 0;
            explorer.refresh();
        }
        (Code::Char('a'), false) | (Code::Char('%'), false) => {
            let dir = explorer.selected_dir();
            let start = format!("{}/", display_path(&dir));
            ed.prompt = Some(Prompt::new(
                PromptKind::Input {
                    title: "New file (end with / for a folder)".into(),
                    action: InputAction::NewFile(dir),
                },
                &start,
            ));
        }
        (Code::Char('r'), false) => {
            if let Some(entry) = explorer.entries.get(explorer.selected).cloned() {
                let start = display_path(&entry.path);
                ed.prompt = Some(Prompt::new(
                    PromptKind::Input { title: "Rename to".into(), action: InputAction::RenameFile(entry.path) },
                    &start,
                ));
            }
        }
        (Code::Char('d'), false) | (Code::Delete, _) => {
            if let Some(entry) = explorer.entries.get(explorer.selected).cloned() {
                ed.prompt = Some(Prompt::new(
                    PromptKind::Confirm {
                        question: format!("Move {} to the Trash?", display_path(&entry.path)),
                        action: ConfirmAction::DeleteFile(entry.path),
                    },
                    "",
                ));
            }
        }
        (Code::Char('y'), false) => {
            if let Some(entry) = explorer.entries.get(explorer.selected) {
                let text = entry.path.to_string_lossy().into_owned();
                crate::clipboard::set(&text);
                ed.info(format!("copied {text}"));
            }
        }
        (Code::Char('q'), false) => {
            ed.explorer = None;
            ed.focus_area = Focus::View;
        }
        _ if key.is_esc() || key == Key::ctrl('l') => ed.focus_area = Focus::View,
        (Code::Char('w'), true) => ed.focus_area = Focus::View,
        (Code::Char(' '), false) => {
            // The leader key still works from the explorer.
            ed.focus_area = Focus::View;
            crate::vim::handle_key(ed, key);
        }
        (Code::Char('?'), false) => {
            ed.popup = Some(crate::widgets::Popup::new(
                crate::widgets::PopupKind::Info,
                "Explorer",
                "j/k move · Enter/l open or expand · h collapse / parent\na new file (dir/ for a folder) · r rename · d move to Trash\ny copy path · . hidden files · C make root · R refresh\nEsc back to the editor · q close",
                false,
            ));
        }
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn trash_moves_the_link_and_keeps_its_target() {
        if let Some(link) = std::env::var_os("ULE_TEST_TRASH_LINK") {
            trash(Path::new(&link)).unwrap();
            return;
        }
        use std::os::unix::fs::{symlink, PermissionsExt};
        let root = std::env::temp_dir().join(format!("ule-trash-{}", std::process::id()));
        std::fs::create_dir_all(root.join("bin")).unwrap();
        let tool = root.join("bin/osascript");
        std::fs::write(&tool, "#!/bin/sh\nexit 1\n").unwrap();
        std::fs::set_permissions(&tool, std::fs::Permissions::from_mode(0o755)).unwrap();
        let target = root.join("target");
        let link = root.join("link");
        std::fs::write(&target, "keep me").unwrap();
        symlink(&target, &link).unwrap();
        let result = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "explorer::tests::trash_moves_the_link_and_keeps_its_target"])
            .env("ULE_TEST_TRASH_LINK", &link)
            .env("HOME", &root)
            .env("PATH", root.join("bin"))
            .output().unwrap();
        assert!(result.status.success(), "{}", String::from_utf8_lossy(&result.stderr));
        assert!(target.exists(), "trashing a link must never trash the target");
        assert!(!link.is_symlink());
        assert!(root.join(".Trash/link").is_symlink());
        std::fs::remove_dir_all(root).unwrap();
    }
}
