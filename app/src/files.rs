//! File operations of Edit's project panel (like Zed's): new file and folder, rename,
//! duplicate, move into a folder. Every operation refuses to replace anything that
//! exists: names are checked, new files are created exclusively and renames fail
//! when the target is taken. Moving to the Trash lives in the platform module.
//! Callers check the paths against `edit::Places::allowed` first.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

/// A single file or folder name the user typed.
pub fn check_name(name: &str) -> Result<&str, String> {
    if name.is_empty() || name.trim().is_empty() {
        return Err("type a name".into());
    }
    if name == "." || name == ".." {
        return Err("not a usable name".into());
    }
    if name.contains('/') || name.chars().any(char::is_control) {
        return Err("a name cannot hold / or control characters".into());
    }
    if name.len() > 255 {
        return Err("the name is too long".into());
    }
    Ok(name)
}

fn taken(path: &Path) -> String {
    format!("{} already exists", path.file_name().map(|name| name.to_string_lossy()).unwrap_or_default())
}

pub fn new_file(dir: &Path, name: &str) -> Result<PathBuf, String> {
    let path = dir.join(check_name(name)?);
    match fs::OpenOptions::new().write(true).create_new(true).open(&path) {
        Ok(_) => Ok(path),
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => Err(taken(&path)),
        Err(error) => Err(format!("could not create {}: {error}", path.display())),
    }
}

pub fn new_folder(dir: &Path, name: &str) -> Result<PathBuf, String> {
    let path = dir.join(check_name(name)?);
    match fs::create_dir(&path) {
        Ok(()) => Ok(path),
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => Err(taken(&path)),
        Err(error) => Err(format!("could not create {}: {error}", path.display())),
    }
}

/// Renames without ever replacing: macOS `renamex_np(RENAME_EXCL)` refuses a taken name
/// atomically; elsewhere the check and the rename are two steps.
fn rename_exclusive(from: &Path, to: &Path) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        use std::ffi::CString;
        use std::os::unix::ffi::OsStrExt;
        let source = CString::new(from.as_os_str().as_bytes()).map_err(|_| "bad path")?;
        let target = CString::new(to.as_os_str().as_bytes()).map_err(|_| "bad path")?;
        // SAFETY: both are valid NUL-terminated paths that outlive the call.
        let done = unsafe { libc::renamex_np(source.as_ptr(), target.as_ptr(), libc::RENAME_EXCL) };
        if done == 0 {
            return Ok(());
        }
        let error = io::Error::last_os_error();
        if error.kind() == io::ErrorKind::AlreadyExists {
            return Err(taken(to));
        }
        return Err(format!("could not move {}: {error}", from.display()));
    }
    #[allow(unreachable_code)]
    {
        if to.symlink_metadata().is_ok() {
            return Err(taken(to));
        }
        fs::rename(from, to).map_err(|error| format!("could not move {}: {error}", from.display()))
    }
}

pub fn rename(path: &Path, name: &str) -> Result<PathBuf, String> {
    let name = check_name(name)?;
    let parent = path.parent().ok_or("cannot rename this")?;
    let target = parent.join(name);
    if target == path {
        return Ok(target);
    }
    // A change of case only (macOS disks ignore case): the "other" file is this one.
    let same_file = path.file_name().map(|old| old.to_string_lossy().to_lowercase()) == Some(name.to_lowercase());
    if same_file {
        let step = parent.join(format!(".{name}.renaming"));
        rename_exclusive(path, &step)?;
        return rename_exclusive(&step, &target).map(|_| target);
    }
    rename_exclusive(path, &target).map(|_| target)
}

/// Moves `path` into the folder `dir` under the same name.
pub fn move_into(path: &Path, dir: &Path) -> Result<PathBuf, String> {
    let name = path.file_name().ok_or("cannot move this")?;
    if dir.starts_with(path) {
        return Err("a folder cannot go into itself".into());
    }
    let target = dir.join(name);
    if target == path {
        return Ok(target);
    }
    rename_exclusive(path, &target).map(|_| target)
}

/// `name copy.ext`, then `name copy 2.ext`… the first that does not exist.
pub fn free_copy_name(path: &Path) -> Result<PathBuf, String> {
    let parent = path.parent().ok_or("no folder")?;
    let name = path.file_name().ok_or("no name")?.to_string_lossy().to_string();
    let (stem, suffix) = match name.rfind('.') {
        Some(dot) if dot > 0 && !path.is_dir() => (name[..dot].to_string(), name[dot..].to_string()),
        _ => (name.clone(), String::new()),
    };
    for number in 1..10_000 {
        let copy = if number == 1 { format!("{stem} copy{suffix}") } else { format!("{stem} copy {number}{suffix}") };
        let candidate = parent.join(copy);
        if candidate.symlink_metadata().is_err() {
            return Ok(candidate);
        }
    }
    Err("no free name for the copy".into())
}

fn copy_tree(from: &Path, to: &Path) -> io::Result<()> {
    let meta = from.symlink_metadata()?;
    if meta.file_type().is_symlink() {
        // Links are copied as links, never followed.
        return std::os::unix::fs::symlink(fs::read_link(from)?, to);
    }
    if meta.is_dir() {
        fs::create_dir(to)?;
        for entry in fs::read_dir(from)? {
            let entry = entry?;
            copy_tree(&entry.path(), &to.join(entry.file_name()))?;
        }
        return fs::set_permissions(to, meta.permissions());
    }
    let mut source = fs::File::open(from)?;
    let mut target = fs::OpenOptions::new().write(true).create_new(true).open(to)?;
    io::copy(&mut source, &mut target)?;
    target.set_permissions(meta.permissions())
}

pub fn duplicate(path: &Path) -> Result<PathBuf, String> {
    let target = free_copy_name(path)?;
    match copy_tree(path, &target) {
        Ok(()) => Ok(target),
        Err(error) => {
            // A copy cut short is not left behind.
            if target.is_dir() {
                let _ = fs::remove_dir_all(&target);
            } else {
                let _ = fs::remove_file(&target);
            }
            Err(format!("could not copy {}: {error}", path.display()))
        }
    }
}

/// `path` relative to the first root that holds it (Zed's "copy relative path").
pub fn relative<'a>(path: &'a Path, roots: &[PathBuf]) -> &'a Path {
    roots.iter().find_map(|root| path.strip_prefix(root).ok()).unwrap_or(path)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sandbox(name: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!("unlaw-files-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        root.canonicalize().unwrap()
    }

    #[test]
    fn names_are_checked() {
        for bad in ["", "  ", ".", "..", "a/b", "a\nb", &"x".repeat(300)] {
            assert!(check_name(bad).is_err(), "{bad:?}");
        }
        assert_eq!(check_name("main.rs"), Ok("main.rs"));
        assert_eq!(check_name(".env.example"), Ok(".env.example"));
    }

    #[test]
    fn new_files_and_folders_never_replace() {
        let root = sandbox("new");
        let file = new_file(&root, "a.txt").unwrap();
        fs::write(&file, "keep").unwrap();
        assert!(new_file(&root, "a.txt").unwrap_err().contains("already exists"));
        assert_eq!(fs::read_to_string(&file).unwrap(), "keep");
        let folder = new_folder(&root, "src").unwrap();
        assert!(folder.is_dir());
        assert!(new_folder(&root, "src").is_err());
        assert!(new_file(&root, "a.txt/../b").is_err());
    }

    #[test]
    fn rename_and_move_refuse_a_taken_name() {
        let root = sandbox("rename");
        let a = new_file(&root, "a.txt").unwrap();
        let b = new_file(&root, "b.txt").unwrap();
        fs::write(&b, "b").unwrap();
        assert!(rename(&a, "b.txt").unwrap_err().contains("already exists"));
        assert_eq!(fs::read_to_string(&b).unwrap(), "b", "nothing replaced");
        let c = rename(&a, "c.txt").unwrap();
        assert!(c.exists() && !a.exists());
        let upper = rename(&c, "C.txt").unwrap();
        assert_eq!(upper.file_name().unwrap(), "C.txt", "a change of case works");
        let dir = new_folder(&root, "dir").unwrap();
        let moved = move_into(&b, &dir).unwrap();
        assert_eq!(moved, dir.join("b.txt"));
        assert!(move_into(&dir, &dir.join("inner")).is_err(), "not into itself");
        let other = new_file(&root, "b.txt").unwrap();
        assert!(move_into(&other, &dir).is_err(), "taken inside the folder");
    }

    #[test]
    fn duplicates_get_free_names_and_copy_folders() {
        let root = sandbox("dup");
        let file = new_file(&root, "notes.md").unwrap();
        fs::write(&file, "x").unwrap();
        assert_eq!(duplicate(&file).unwrap(), root.join("notes copy.md"));
        assert_eq!(duplicate(&file).unwrap(), root.join("notes copy 2.md"));
        let dir = new_folder(&root, "pkg").unwrap();
        fs::write(dir.join("a.rs"), "fn a() {}").unwrap();
        std::os::unix::fs::symlink("/etc", dir.join("link")).unwrap();
        let copy = duplicate(&dir).unwrap();
        assert_eq!(copy, root.join("pkg copy"));
        assert_eq!(fs::read_to_string(copy.join("a.rs")).unwrap(), "fn a() {}");
        assert!(copy.join("link").symlink_metadata().unwrap().file_type().is_symlink());
        assert_eq!(relative(&copy.join("a.rs"), std::slice::from_ref(&root)), Path::new("pkg copy/a.rs"));
    }
}
