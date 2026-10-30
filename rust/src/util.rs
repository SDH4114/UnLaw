//! Small helpers shared by the core: atomic writes, PATH lookup, quoting,
//! JSON rendering and difflib-compatible suggestions.

use std::env;
use std::ffi::OsStr;
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

/// Write through a temporary file in the same directory, fsync, then rename.
pub fn atomic_write(destination: &Path, text: &str, prefix: &str) -> io::Result<()> {
    static COUNTER: AtomicU32 = AtomicU32::new(0);
    let directory = destination.parent().unwrap_or(Path::new("."));
    fs::create_dir_all(directory)?;
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.subsec_nanos()).unwrap_or(0);
    let (temporary, mut handle) = loop {
        let candidate = directory.join(format!(
            "{prefix}{}-{nanos}-{}.tmp",
            std::process::id(),
            COUNTER.fetch_add(1, Ordering::Relaxed)
        ));
        match OpenOptions::new().write(true).create_new(true).open(&candidate) {
            Ok(handle) => break (candidate, handle),
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        }
    };
    let result = (|| {
        handle.write_all(text.as_bytes())?;
        handle.sync_all()?;
        fs::rename(&temporary, destination)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

/// Create `destination` atomically, failing if it already exists.
pub fn create_new_atomic(destination: &Path, text: &str, prefix: &str) -> io::Result<()> {
    let directory = destination.parent().unwrap_or(Path::new("."));
    fs::create_dir_all(directory)?;
    let temporary = directory.join(format!("{prefix}{}.tmp", std::process::id()));
    let mut handle = OpenOptions::new().write(true).create_new(true).open(&temporary)?;
    let result = (|| {
        handle.write_all(text.as_bytes())?;
        handle.sync_all()?;
        // A hard link fails when the destination exists, so a concurrent
        // writer can never be overwritten.
        fs::hard_link(&temporary, destination)
    })();
    let _ = fs::remove_file(&temporary);
    result
}

pub fn is_executable(path: &Path) -> bool {
    fs::metadata(path).map(|meta| meta.is_file() && meta.permissions().mode() & 0o111 != 0).unwrap_or(false)
}

/// `shutil.which`: absolute or relative paths are checked directly.
pub fn which(name: &str) -> Option<PathBuf> {
    if name.is_empty() {
        return None;
    }
    if name.contains('/') {
        let path = PathBuf::from(name);
        return is_executable(&path).then_some(path);
    }
    let path = env::var_os("PATH")?;
    env::split_paths(&path).map(|dir| dir.join(name)).find(|candidate| is_executable(candidate))
}

pub fn home() -> PathBuf {
    env::var_os("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("/"))
}

pub fn expand_user(path: &str) -> PathBuf {
    if path == "~" {
        home()
    } else if let Some(rest) = path.strip_prefix("~/") {
        home().join(rest)
    } else {
        PathBuf::from(path)
    }
}

/// Python's `shlex.quote`.
pub fn shell_quote(word: &str) -> String {
    let safe = |c: char| c.is_ascii_alphanumeric() || "@%+=:,./-_".contains(c);
    if !word.is_empty() && word.chars().all(safe) {
        word.to_string()
    } else {
        format!("'{}'", word.replace('\'', "'\"'\"'"))
    }
}

pub fn shell_join<I, S>(words: I) -> String
where
    I: IntoIterator<Item = S>,
    S: AsRef<OsStr>,
{
    words
        .into_iter()
        .map(|word| shell_quote(&word.as_ref().to_string_lossy()))
        .collect::<Vec<_>>()
        .join(" ")
}

/// Minimal JSON value with Python `json.dumps(indent=2, ensure_ascii=False)` output.
pub enum Json {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
    Array(Vec<Json>),
    Object(Vec<(String, Json)>),
}

impl Json {
    pub fn str(text: impl Into<String>) -> Json {
        Json::Str(text.into())
    }

    pub fn render(&self) -> String {
        let mut out = String::new();
        self.write(&mut out, 0);
        out
    }

    fn write(&self, out: &mut String, depth: usize) {
        let pad = |out: &mut String, depth: usize| out.push_str(&"  ".repeat(depth));
        match self {
            Json::Null => out.push_str("null"),
            Json::Bool(value) => out.push_str(if *value { "true" } else { "false" }),
            Json::Int(value) => out.push_str(&value.to_string()),
            Json::Float(value) => out.push_str(&python_float(*value)),
            Json::Str(value) => json_string(value, out),
            Json::Array(items) if items.is_empty() => out.push_str("[]"),
            Json::Object(items) if items.is_empty() => out.push_str("{}"),
            Json::Array(items) => {
                out.push_str("[\n");
                for (index, item) in items.iter().enumerate() {
                    pad(out, depth + 1);
                    item.write(out, depth + 1);
                    out.push_str(if index + 1 < items.len() { ",\n" } else { "\n" });
                }
                pad(out, depth);
                out.push(']');
            }
            Json::Object(items) => {
                out.push_str("{\n");
                for (index, (key, item)) in items.iter().enumerate() {
                    pad(out, depth + 1);
                    json_string(key, out);
                    out.push_str(": ");
                    item.write(out, depth + 1);
                    out.push_str(if index + 1 < items.len() { ",\n" } else { "\n" });
                }
                pad(out, depth);
                out.push('}');
            }
        }
    }
}

fn json_string(text: &str, out: &mut String) {
    out.push('"');
    for c in text.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{08}' => out.push_str("\\b"),
            '\u{0c}' => out.push_str("\\f"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
}

/// Python's `repr(float)` for ordinary values: `2.0`, `0.7`.
pub fn python_float(value: f64) -> String {
    if value.is_finite() {
        format!("{value:?}")
    } else if value.is_nan() {
        "NaN".into()
    } else if value > 0.0 {
        "Infinity".into()
    } else {
        "-Infinity".into()
    }
}

/// `difflib.SequenceMatcher(None, a, b).ratio()`.
fn ratio(a: &[char], b: &[char]) -> f64 {
    fn matches(a: &[char], b: &[char]) -> usize {
        let (mut best_i, mut best_j, mut best) = (0, 0, 0);
        let mut previous = vec![0usize; b.len() + 1];
        for (i, left) in a.iter().enumerate() {
            let mut current = vec![0usize; b.len() + 1];
            for (j, right) in b.iter().enumerate() {
                if left == right {
                    current[j + 1] = previous[j] + 1;
                    if current[j + 1] > best {
                        best = current[j + 1];
                        best_i = i + 1 - best;
                        best_j = j + 1 - best;
                    }
                }
            }
            previous = current;
        }
        if best == 0 {
            return 0;
        }
        best + matches(&a[..best_i], &b[..best_j]) + matches(&a[best_i + best..], &b[best_j + best..])
    }
    let total = a.len() + b.len();
    if total == 0 {
        return 1.0;
    }
    2.0 * matches(a, b) as f64 / total as f64
}

/// `difflib.get_close_matches(word, possibilities, n, cutoff)`.
pub fn close_matches(word: &str, possibilities: &[String], n: usize, cutoff: f64) -> Vec<String> {
    let target: Vec<char> = word.chars().collect();
    let mut scored: Vec<(f64, &String)> = possibilities
        .iter()
        .map(|candidate| (ratio(&candidate.chars().collect::<Vec<_>>(), &target), candidate))
        .filter(|(score, _)| *score >= cutoff)
        .collect();
    scored.sort_by(|left, right| right.0.total_cmp(&left.0).then_with(|| right.1.cmp(left.1)));
    scored.into_iter().take(n).map(|(_, name)| name.clone()).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quoting_matches_shlex() {
        assert_eq!(shell_quote("plain-word"), "plain-word");
        assert_eq!(shell_quote(""), "''");
        assert_eq!(shell_quote("it's"), "'it'\"'\"'s'");
        assert_eq!(shell_join(["python3", "/a b/main.py"]), "python3 '/a b/main.py'");
    }

    #[test]
    fn suggestions_match_difflib() {
        let names: Vec<String> = ["git", "gpt", "game", "zip"].iter().map(|s| s.to_string()).collect();
        assert_eq!(close_matches("gti", &names, 3, 0.55), vec!["gpt", "git"]);
        assert!(close_matches("nothing", &names, 3, 0.55).is_empty());
    }

    #[test]
    fn json_matches_python_indent() {
        let value = Json::Object(vec![
            ("name".into(), Json::str("a\"b")),
            ("list".into(), Json::Array(vec![Json::Int(1), Json::Float(2.0)])),
            ("empty".into(), Json::Array(vec![])),
        ]);
        assert_eq!(value.render(), "{\n  \"name\": \"a\\\"b\",\n  \"list\": [\n    1,\n    2.0\n  ],\n  \"empty\": []\n}");
    }

    fn scratch(name: &str) -> PathBuf {
        let directory = env::temp_dir().join(format!("unlaw-util-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&directory);
        fs::create_dir_all(&directory).unwrap();
        directory
    }

    #[test]
    fn atomic_writes_replace_and_leave_no_temporaries() {
        let directory = scratch("atomic");
        let target = directory.join("nested/config.toml");
        atomic_write(&target, "one", ".config.").unwrap();
        atomic_write(&target, "two", ".config.").unwrap();
        assert_eq!(fs::read_to_string(&target).unwrap(), "two");
        assert_eq!(fs::read_dir(target.parent().unwrap()).unwrap().count(), 1);
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn create_new_atomic_never_overwrites() {
        let directory = scratch("create");
        let target = directory.join("demo.toml");
        create_new_atomic(&target, "first", ".demo.").unwrap();
        let error = create_new_atomic(&target, "second", ".demo.").unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::AlreadyExists);
        assert_eq!(fs::read_to_string(&target).unwrap(), "first");
        assert_eq!(fs::read_dir(&directory).unwrap().count(), 1);
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn create_new_atomic_does_not_truncate_a_temporary_symlink() {
        let directory = scratch("symlink");
        let victim = directory.join("victim");
        fs::write(&victim, "private data").unwrap();
        let temporary = directory.join(format!(".new.{}.tmp", std::process::id()));
        std::os::unix::fs::symlink(&victim, &temporary).unwrap();
        let _ = create_new_atomic(&directory.join("new"), "replacement", ".new.");
        assert_eq!(fs::read_to_string(victim).unwrap(), "private data");
        assert!(temporary.is_symlink());
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn which_checks_paths_and_executable_bits() {
        let directory = scratch("which");
        let tool = directory.join("tool");
        fs::write(&tool, "#!/bin/sh\n").unwrap();
        assert_eq!(which(tool.to_str().unwrap()), None);
        fs::set_permissions(&tool, fs::Permissions::from_mode(0o755)).unwrap();
        assert_eq!(which(tool.to_str().unwrap()), Some(tool.clone()));
        assert_eq!(which(""), None);
        assert!(which("sh").is_some());
        assert!(!is_executable(&directory));
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn user_paths_expand_only_a_leading_tilde() {
        assert_eq!(expand_user("~"), home());
        assert_eq!(expand_user("~/a"), home().join("a"));
        assert_eq!(expand_user("/x/~/a"), PathBuf::from("/x/~/a"));
        assert_eq!(expand_user("~other"), PathBuf::from("~other"));
    }

    #[test]
    fn json_escapes_control_characters_like_python() {
        let text = Json::str("a\\b\n\r\t\u{08}\u{0c}\u{01}é").render();
        assert_eq!(text, "\"a\\\\b\\n\\r\\t\\b\\f\\u0001é\"");
        assert_eq!(Json::Null.render(), "null");
        assert_eq!(Json::Object(vec![]).render(), "{}");
        assert_eq!(python_float(f64::NAN), "NaN");
        assert_eq!(python_float(f64::INFINITY), "Infinity");
        assert_eq!(python_float(f64::NEG_INFINITY), "-Infinity");
        assert_eq!(python_float(0.7), "0.7");
    }

    #[test]
    fn ratio_matches_difflib_edge_cases() {
        assert_eq!(ratio(&[], &[]), 1.0);
        let chars = |s: &str| s.chars().collect::<Vec<_>>();
        assert_eq!(ratio(&chars("abc"), &chars("xyz")), 0.0);
        assert!((ratio(&chars("commands"), &chars("comands")) - 0.9333).abs() < 0.001);
        let names: Vec<String> = ["commands", "completion", "config"].iter().map(|s| s.to_string()).collect();
        assert_eq!(close_matches("comands", &names, 1, 0.55), vec!["commands"]);
    }
}
