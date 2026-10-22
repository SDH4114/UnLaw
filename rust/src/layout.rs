//! First-run bootstrap: directories, default config and seeded command sources.

use std::fs;
use std::io;
use std::path::PathBuf;

use sha2::{Digest, Sha256};

use crate::assets::SEEDS;
use crate::commands::entry_point;
use crate::config::{commands_dir, config_dir, configured_storage_root, templates_dir, write_defaults_if_missing};

pub const TEMPLATE_NAMES: [&str; 5] = ["commands", "python", "rust", "cpp", "projects"];
pub const STORAGE_SUBDIRECTORIES: [&[&str]; 4] =
    [&["captures", "screenshots"], &["captures", "recordings"], &["telegram", "downloads"], &["runtime"]];

fn is_legacy_wrapper(source: &str, name: &str) -> bool {
    let import = format!("from unlawful.built_in_commands.{name}.main import main");
    let tail = "if __name__ == \"__main__\":\n    raise SystemExit(main())";
    let trimmed = source.trim();
    trimmed == format!("{import}\n\n\n{tail}") || trimmed == format!("{import}\n\n{tail}")
}

/// Only untouched sources shipped by earlier releases may be upgraded.
pub fn is_replaceable(source: &str, name: &str, hashes: &[&str]) -> bool {
    if is_legacy_wrapper(source, name) {
        return true;
    }
    let digest = Sha256::digest(source.as_bytes());
    let hex: String = digest.iter().map(|byte| format!("{byte:02x}")).collect();
    hashes.contains(&hex.as_str())
}

fn seed_default_commands() -> io::Result<()> {
    let root = commands_dir();
    for (name, source, hashes) in SEEDS {
        let directory = root.join(name);
        let destination = directory.join("main.py");
        match fs::read_to_string(&destination) {
            Ok(existing) if existing == *source || !is_replaceable(&existing, name, hashes) => continue,
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
    seed_default_commands()?;
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
    fn every_seed_has_a_summary_docstring() {
        for (name, source, _) in SEEDS {
            assert!(source.lines().nth(1).unwrap_or("").starts_with("\"\"\""), "{name}");
        }
    }
}
