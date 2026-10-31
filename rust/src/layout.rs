//! First-run bootstrap: directories, default config and seeded command sources.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};

use crate::assets::{RETIRED, SEEDS};
use crate::commands::entry_point;
use crate::config::{self, commands_dir, config_dir, configured_storage_root, templates_dir, write_defaults_if_missing};
use crate::features;

pub const TEMPLATE_NAMES: [&str; 5] = ["commands", "python", "rust", "cpp", "projects"];
pub const STORAGE_SUBDIRECTORIES: [&[&str]; 4] =
    [&["captures", "screenshots"], &["captures", "recordings"], &["telegram", "downloads"], &["runtime"]];

fn is_legacy_wrapper(source: &str, name: &str) -> bool {
    let import = format!("from unlawful.built_in_commands.{name}.main import main");
    let tail = "if __name__ == \"__main__\":\n    raise SystemExit(main())";
    let trimmed = source.trim();
    trimmed == format!("{import}\n\n\n{tail}") || trimmed == format!("{import}\n\n{tail}")
}

fn sha256_hex(text: &str) -> String {
    Sha256::digest(text.as_bytes()).iter().map(|byte| format!("{byte:02x}")).collect()
}

fn without_blank_lines(source: &str) -> String {
    source.lines().filter(|line| !line.trim().is_empty()).collect::<Vec<_>>().join("\n")
}

/// Only untouched sources shipped by earlier releases may be upgraded.
pub fn is_replaceable(source: &str, name: &str, hashes: &[&str]) -> bool {
    is_legacy_wrapper(source, name) || hashes.contains(&sha256_hex(source).as_str())
}

fn is_docstring(line: &str) -> bool {
    let text = line.trim();
    text.len() >= 6 && text.starts_with("\"\"\"") && text.ends_with("\"\"\"") && !text[3..text.len() - 3].contains("\"\"\"")
}

/// The code without blank lines and without the summary docstring near the top;
/// same as `normalized_source` in src/unlawful/command_sources.py.
pub fn normalized_source(source: &str) -> String {
    let lines: Vec<&str> = source.lines().filter(|line| !line.trim().is_empty()).collect();
    lines
        .iter()
        .enumerate()
        .filter(|(index, line)| !(*index < 3 && is_docstring(line)))
        .map(|(_, line)| *line)
        .collect::<Vec<_>>()
        .join("\n")
}

/// A seed that differs from an official source only in blank lines or the
/// summary docstring is untouched too; some installs got such copies.
fn is_untouched_seed(existing: &str, name: &str, seed: &str, hashes: &[&str], normalized: &[&str]) -> bool {
    if is_replaceable(existing, name, hashes) {
        return true;
    }
    let code = normalized_source(existing);
    normalized.contains(&sha256_hex(&code).as_str()) || code == normalized_source(seed)
}

/// Remove a seed's folder when it holds only an untouched official copy;
/// returns false (and keeps it) when the user changed or replaced it.
fn remove_untouched_seed(name: &str, source: &str, hashes: &[&str], normalized: &[&str]) -> io::Result<bool> {
    let directory = commands_dir().join(name);
    let script = directory.join("main.py");
    if directory.is_symlink() || script.is_symlink() {
        return Ok(false);
    }
    match fs::read_to_string(&script) {
        Ok(existing) if is_untouched_seed(&existing, name, source, hashes, normalized) => {}
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(entry_point(&directory).is_none()),
        _ => return Ok(false),
    }
    fs::remove_file(&script)?;
    let _ = fs::remove_file(directory.join(".DS_Store"));
    let _ = fs::remove_dir_all(directory.join("__pycache__"));
    // Anything else in the folder (help.txt, data) is the user's; the folder stays then.
    let _ = fs::remove_dir(&directory);
    Ok(true)
}

/// Seed the chosen features' commands and remove untouched seeds of the
/// others; returns the unchosen ones kept because they were edited.
/// `None` (an unreadable config) only upgrades seeds that already exist.
fn seed_default_commands(selection: Option<&[&str]>) -> io::Result<Vec<&'static str>> {
    let root = commands_dir();
    let mut kept = Vec::new();
    for (name, source, hashes, normalized) in SEEDS {
        let directory = root.join(name);
        let destination = directory.join("main.py");
        // A symlink is a user replacement, even if its target is an official seed.
        if directory.is_symlink() || destination.is_symlink() {
            if selection.is_some_and(|selection| !selection.contains(name)) {
                kept.push(*name);
            }
            continue;
        }
        match selection {
            Some(selection) if !selection.contains(name) => {
                if !remove_untouched_seed(name, source, hashes, normalized)? {
                    kept.push(*name);
                }
                continue;
            }
            None if !directory.exists() => continue,
            _ => {}
        }
        match fs::read_to_string(&destination) {
            Ok(existing) if existing == *source || !is_untouched_seed(&existing, name, source, hashes, normalized) => continue,
            Ok(_) => {}
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                // A command rewritten as main.sh, main.js or main stays the user's.
                if entry_point(&directory).is_some() {
                    continue;
                }
            }
            // Unreadable or non-UTF-8 files are user-owned; leave them alone.
            Err(_) => continue,
        }
        fs::create_dir_all(&directory)?;
        fs::write(&destination, source)?;
    }
    Ok(kept)
}

/// `ul reinstall`: take every official seed folder out of commands/ so the
/// next run seeds fresh copies. Untouched copies are deleted; edited ones,
/// or folders holding other files, move into `backup`. Symlinks are the
/// user's and stay. Returns the names moved into the backup.
pub fn reset_seeds(backup: &Path) -> io::Result<Vec<&'static str>> {
    let mut moved = Vec::new();
    for (name, source, hashes, normalized) in SEEDS {
        let directory = commands_dir().join(name);
        let script = directory.join("main.py");
        if directory.is_symlink() || script.is_symlink() || !directory.is_dir() {
            continue;
        }
        let only_script = fs::read_dir(&directory)?
            .flatten()
            .all(|entry| ["main.py", ".DS_Store", "__pycache__"].iter().any(|name| entry.file_name() == *name));
        let untouched = fs::read_to_string(&script).is_ok_and(|existing| is_untouched_seed(&existing, name, source, hashes, normalized));
        if only_script && untouched {
            fs::remove_dir_all(&directory)?;
        } else {
            let destination = backup.join("commands").join(name);
            fs::create_dir_all(backup.join("commands"))?;
            fs::rename(&directory, &destination)?;
            moved.push(*name);
        }
    }
    Ok(moved)
}

/// After `ul features` changed the selection.
pub fn sync_features(selection: &[&str]) -> io::Result<Vec<&'static str>> {
    seed_default_commands(Some(selection))
}

/// Remove untouched seeds of commands that are now built in, so the Rust
/// version runs; edited copies stay and keep overriding it.
fn retire_builtin_seeds() -> io::Result<()> {
    for (name, hashes, normalized) in RETIRED {
        let directory = commands_dir().join(name);
        let script = directory.join("main.py");
        if directory.is_symlink() || script.is_symlink() {
            continue;
        }
        let Ok(source) = fs::read_to_string(&script) else { continue };
        let untouched = is_replaceable(&source, name, hashes)
            || normalized.contains(&sha256_hex(&without_blank_lines(&source)).as_str())
            || normalized.contains(&sha256_hex(&normalized_source(&source)).as_str());
        if !untouched {
            continue;
        }
        fs::remove_file(&script)?;
        let _ = fs::remove_file(directory.join(".DS_Store"));
        // Bytecode the old seed left behind; regenerated if anything needs it.
        let _ = fs::remove_dir_all(directory.join("__pycache__"));
        let _ = fs::remove_dir(&directory);
    }
    Ok(())
}

pub fn ensure_storage_layout() -> io::Result<PathBuf> {
    let root = configured_storage_root();
    for parts in STORAGE_SUBDIRECTORIES {
        fs::create_dir_all(parts.iter().fold(root.clone(), |path, part| path.join(part)))?;
    }
    Ok(root)
}

/// Create everything Unlaw needs without overwriting user files.
pub fn ensure_layout() -> io::Result<PathBuf> {
    fs::create_dir_all(commands_dir())?;
    for name in TEMPLATE_NAMES {
        fs::create_dir_all(templates_dir().join(name))?;
    }
    write_defaults_if_missing()?;
    let selection = config::load().ok().map(|config| features::selected(&config));
    seed_default_commands(selection.as_deref())?;
    retire_builtin_seeds()?;
    ensure_storage_layout()?;
    Ok(config_dir())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn legacy_wrappers_and_hashes_are_replaceable() {
        let wrapper = "from unlawful.built_in_commands.work.main import main\n\nif __name__ == \"__main__\":\n    raise SystemExit(main())\n";
        assert!(is_replaceable(wrapper, "work", &[]));
        assert!(!is_replaceable(wrapper, "git", &[]));
        let digest = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824";
        assert!(is_replaceable("hello", "git", &[digest]));
        assert!(!is_replaceable("hello!", "git", &[digest]));
    }

    #[test]
    fn blank_lines_are_ignored_only_by_the_normalized_hash() {
        assert_eq!(without_blank_lines("a\n\n  \nb\n"), "a\nb");
        assert_eq!(sha256_hex(&without_blank_lines("x\n\ny")), sha256_hex(&without_blank_lines("x\ny\n\n")));
        assert!(!is_replaceable("x\n\ny", "git", &[&sha256_hex("x\ny")]), "exact matching stays exact");
    }

    #[test]
    fn copies_without_blank_lines_or_docstring_are_untouched() {
        let seed = "# header\n\"\"\"Say \\\"hi\\\".\"\"\"\nimport os\n\nprint(1)\n";
        let copy = "# header\nimport os\nprint(1)\n\n";
        assert!(is_untouched_seed(copy, "x", seed, &[], &[]));
        assert!(is_untouched_seed(copy, "x", "print(2)\n", &[], &[&sha256_hex(&normalized_source(copy))]));
        assert!(!is_untouched_seed("# header\nimport os\nprint(2)\n", "x", seed, &[], &[]), "a real edit is kept");
        assert_eq!(normalized_source(seed), "# header\nimport os\nprint(1)");
    }

    #[test]
    fn every_seed_has_a_summary_docstring() {
        for (name, source, _, _) in SEEDS {
            assert!(source.lines().nth(1).unwrap_or("").starts_with("\"\"\""), "{name}");
        }
    }
}
