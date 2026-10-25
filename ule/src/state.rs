//! What ule remembers between runs: cursor positions, command/search history, recent files.

use std::fs;
use std::path::{Path, PathBuf};

use serde_json::{json, Value};

use crate::text::Pos;

const MAX_POSITIONS: usize = 500;
const MAX_HISTORY: usize = 200;
const MAX_RECENT: usize = 100;

#[derive(Debug, Default)]
pub struct State {
    pub path: Option<PathBuf>,
    pub positions: Vec<(String, Pos)>,
    pub commands: Vec<String>,
    pub searches: Vec<String>,
    pub recent: Vec<String>,
}

fn strings(value: &Value, key: &str) -> Vec<String> {
    value.get(key).and_then(Value::as_array).map_or_else(Vec::new, |items| {
        items.iter().filter_map(|item| item.as_str().map(str::to_string)).collect()
    })
}

fn push_unique(list: &mut Vec<String>, item: &str, max: usize) {
    if item.is_empty() {
        return;
    }
    list.retain(|existing| existing != item);
    list.push(item.to_string());
    if list.len() > max {
        list.remove(0);
    }
}

impl State {
    pub fn load(path: PathBuf) -> State {
        let mut state = State { path: Some(path.clone()), ..State::default() };
        let Ok(text) = fs::read_to_string(&path) else {
            return state;
        };
        let Ok(value) = serde_json::from_str::<Value>(&text) else {
            return state;
        };
        state.commands = strings(&value, "commands");
        state.searches = strings(&value, "searches");
        state.recent = strings(&value, "recent");
        if let Some(items) = value.get("positions").and_then(Value::as_array) {
            for item in items {
                let path = item.get(0).and_then(Value::as_str);
                let line = item.get(1).and_then(Value::as_u64);
                let col = item.get(2).and_then(Value::as_u64);
                if let (Some(path), Some(line), Some(col)) = (path, line, col) {
                    state.positions.push((path.to_string(), Pos::new(line as usize, col as usize)));
                }
            }
        }
        state
    }

    pub fn save(&self) {
        let Some(path) = &self.path else {
            return;
        };
        let positions: Vec<Value> =
            self.positions.iter().map(|(path, pos)| json!([path, pos.line, pos.col])).collect();
        let value = json!({
            "commands": self.commands,
            "searches": self.searches,
            "recent": self.recent,
            "positions": positions,
        });
        if let Some(parent) = path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        let temporary = path.with_extension("tmp");
        if fs::write(&temporary, value.to_string()).is_ok() {
            let _ = fs::rename(&temporary, path);
        }
    }

    pub fn position(&self, path: &Path) -> Option<Pos> {
        let key = path.to_string_lossy();
        self.positions.iter().rev().find(|(existing, _)| *existing == key).map(|(_, pos)| *pos)
    }

    pub fn set_position(&mut self, path: &Path, pos: Pos) {
        let key = path.to_string_lossy().into_owned();
        self.positions.retain(|(existing, _)| *existing != key);
        self.positions.push((key, pos));
        if self.positions.len() > MAX_POSITIONS {
            self.positions.remove(0);
        }
    }

    pub fn add_command(&mut self, command: &str) {
        push_unique(&mut self.commands, command, MAX_HISTORY);
    }

    pub fn add_search(&mut self, pattern: &str) {
        push_unique(&mut self.searches, pattern, MAX_HISTORY);
    }

    pub fn add_recent(&mut self, path: &Path) {
        push_unique(&mut self.recent, &path.to_string_lossy(), MAX_RECENT);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trips() {
        let path = std::env::temp_dir().join(format!("ule-state-{}.json", std::process::id()));
        let mut state = State { path: Some(path.clone()), ..State::default() };
        state.set_position(Path::new("/a.rs"), Pos::new(3, 4));
        state.add_command("w");
        state.add_command("q");
        state.add_command("w");
        state.save();
        let loaded = State::load(path.clone());
        assert_eq!(loaded.position(Path::new("/a.rs")), Some(Pos::new(3, 4)));
        assert_eq!(loaded.commands, vec!["q", "w"]);
        let _ = fs::remove_file(path);
    }
}
