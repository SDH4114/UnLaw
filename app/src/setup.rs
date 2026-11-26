//! A downloaded Unlaw.app carries the command line in `Contents/Resources/bin`
//! (scripts/make-app-zip.sh). On first start without `ul`, the app installs it
//! into ~/.local/bin, because the two halves only work together. Existing files
//! are never replaced: an installed ul is updated by `ul update`, not by the app.

use std::fs;
use std::io;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

/// The bundle's `Contents/Resources/bin`, when this ul-app runs from a bundle that has one.
pub fn bundled_bin(exe: &Path) -> Option<PathBuf> {
    let contents = exe.parent()?.parent()?;
    let bin = contents.join("Resources").join("bin");
    bin.join("ul").is_file().then_some(bin)
}

/// Copy every program from `from` into `to` that is not there yet; returns
/// the names copied. A partly written file never stays behind.
pub fn install_cli(from: &Path, to: &Path) -> io::Result<Vec<String>> {
    fs::create_dir_all(to)?;
    let mut entries: Vec<_> = fs::read_dir(from)?.flatten().collect();
    entries.sort_by_key(|entry| entry.file_name());
    let mut copied = Vec::new();
    for entry in entries {
        let name = entry.file_name().to_string_lossy().into_owned();
        let source = entry.path();
        if !source.is_file() || name.starts_with('.') {
            continue;
        }
        let target = to.join(&name);
        if target.exists() || target.is_symlink() {
            continue;
        }
        let partial = to.join(format!(".{name}.unlaw-{}", std::process::id()));
        let result = fs::copy(&source, &partial)
            .and_then(|_| fs::set_permissions(&partial, fs::Permissions::from_mode(0o755)))
            // A link, not rename: never replaces a file that appeared meanwhile.
            .and_then(|_| fs::hard_link(&partial, &target));
        let _ = fs::remove_file(&partial);
        match result {
            Ok(()) => copied.push(name),
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {}
            Err(error) => return Err(error),
        }
    }
    Ok(copied)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn copies_only_what_is_missing() {
        let root = std::env::temp_dir().join(format!("unlaw-app-setup-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        let bundle = root.join("Unlaw.app/Contents");
        let (macos, bin, target) = (bundle.join("MacOS"), bundle.join("Resources/bin"), root.join("local/bin"));
        fs::create_dir_all(&macos).unwrap();
        fs::create_dir_all(&bin).unwrap();
        fs::create_dir_all(&target).unwrap();
        assert_eq!(bundled_bin(&macos.join("ul-app")), None, "no ul in the bundle");
        for name in ["ul", "ule", "unlaw"] {
            fs::write(bin.join(name), format!("#!/bin/sh\necho {name}\n")).unwrap();
        }
        fs::write(bin.join(".DS_Store"), "x").unwrap();
        fs::write(target.join("ule"), "mine").unwrap();
        assert_eq!(bundled_bin(&macos.join("ul-app")), Some(bin.clone()));
        assert_eq!(install_cli(&bin, &target).unwrap(), vec!["ul", "unlaw"]);
        assert_eq!(fs::read_to_string(target.join("ule")).unwrap(), "mine", "never replaced");
        assert_eq!(fs::metadata(target.join("ul")).unwrap().permissions().mode() & 0o777, 0o755);
        assert!(!target.join(".DS_Store").exists());
        assert!(install_cli(&bin, &target).unwrap().is_empty(), "a second run copies nothing");
        let leftovers: Vec<_> = fs::read_dir(&target)
            .unwrap()
            .flatten()
            .filter(|e| e.file_name().to_string_lossy().starts_with('.'))
            .collect();
        assert!(leftovers.is_empty());
        fs::remove_dir_all(&root).unwrap();
    }
}
