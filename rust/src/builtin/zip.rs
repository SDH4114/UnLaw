//! `ul zip`: compress with 7-Zip, zip, bsdtar, zstd or rar, and extract
//! almost any archive. Formats are detected by content; nothing is ever
//! overwritten and passwords travel over stdin, never argv.

use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::os::unix::fs::PermissionsExt;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use crate::commands::{exit_code, shield, spawn_shielded, status_shielded};
use crate::config::{Config, Value};
use crate::util::{home, which};

pub const HELP: &str = r#"Compress files and folders, or extract almost any archive.
Usage:
  ul zip <path>... [options]            Compress into one archive (default: .zip)
  ul zip <archive>...                   Extract (when every path is an archive)
  ul zip x|extract <archive>... [-o <dir>] [--here]   Extract explicitly
  ul zip c|create <path>... [options]   Compress explicitly (even an archive)
  ul zip ls <archive>                   List contents
  ul zip test <archive>                 Verify integrity
Create options:
  -f, --format zip|7z|rar|tar.zst|tar.xz|tar.gz   Also: zst, xz, gz, tgz, txz, tzst
  -o, --output <file|dir>   Archive path; its extension selects the format
  -0 ... -9, -l <level>     Compression level (default: zip.level = max = 7)
  --store|--fastest|--fast|--normal|--max|--ultra   Named levels 0, 1, 3, 5, 7, 9
  -p, --password            Ask for a password: AES-256 (7z/rar also hide file names)
  --keep-junk               Keep .DS_Store, ._*, __MACOSX, Thumbs.db, desktop.ini
Extract options:
  -o, --output <dir>        Destination (default: next to the archive)
  --here                    Put contents directly into the destination folder
  --keep-junk               Keep __MACOSX/.DS_Store found at the archive root
Behavior: a single input is archived next to itself, several inputs into
./Archive.<ext>. A one-item archive extracts as that item; otherwise into a
folder named after the archive. Existing files are never overwritten: a
" 2" suffix is added. Encrypted archives ask for their password.
Levels: 0 stores without compression (zstd/gzip use their fastest), 1-3 favor
speed, 5 is balanced, 7 gives near-best size, 9 is the slowest and smallest
(7z/zip -mx9, rar -m5, xz -9, zstd --ultra -22). If at least 90% of the input is
already-compressed media (jpg, heic, mp4, zip...) and no level is given, level 1
is used: stronger levels only cost time there.
Reads: zip, 7z, rar, tar(.gz/.bz2/.xz/.zst), gz, bz2, xz, zst, cab, iso, cpio, xar.
Settings: zip.format (zip), zip.level (max), zip.keep_junk (false).
Dependencies: 7-Zip (7z/rar reading, AES zip; falls back to zip/bsdtar),
zstd for .zst, xz for single .xz files without 7-Zip, rar for creating .rar
(brew install sevenzip zstd xz; brew install --cask rar).
Examples:
  ul zip project
  ul zip photo.png notes/ -o ~/Desktop/pack.7z
  ul zip project -f 7z -p
  ul zip project -f zst --fast
  ul zip project -f 7z -9
  ul zip project.zip
  ul zip x backup.rar -o ~/Downloads
  ul zip ls backup.7z
"#;

const FORMATS: [(&str, &str); 6] = [
    ("zip", ".zip"),
    ("7z", ".7z"),
    ("rar", ".rar"),
    ("tar.zst", ".tar.zst"),
    ("tar.xz", ".tar.xz"),
    ("tar.gz", ".tar.gz"),
];
const FORMAT_ALIASES: [(&str, &str); 7] = [
    ("zst", "tar.zst"),
    ("zstd", "tar.zst"),
    ("tzst", "tar.zst"),
    ("xz", "tar.xz"),
    ("txz", "tar.xz"),
    ("gz", "tar.gz"),
    ("tgz", "tar.gz"),
];
const EXTRA_OUTPUT_SUFFIXES: [(&str, &str); 3] = [(".tzst", "tar.zst"), (".txz", "tar.xz"), (".tgz", "tar.gz")];
/// One 0-9 scale for every format, named after the 7-Zip presets.
const LEVEL_NAMES: [(&str, u8); 6] = [("store", 0), ("fastest", 1), ("fast", 3), ("normal", 5), ("max", 7), ("ultra", 9)];
const RAR_LEVELS: [u8; 10] = [0, 1, 2, 2, 3, 3, 4, 4, 5, 5];
/// zstd has no "store": 0 is its fastest; 9 is --ultra -22 with a 128 MiB window.
const ZSTD_LEVELS: [u8; 10] = [1, 1, 3, 6, 9, 12, 15, 17, 19, 22];
/// Already-compressed media: stronger levels cost minutes for gains well under 1%.
const INCOMPRESSIBLE: [&str; 38] = [
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".avif", ".mp4", ".m4v", ".mov", ".mkv", ".webm",
    ".avi", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".zip", ".7z", ".rar", ".gz", ".tgz", ".bz2", ".xz",
    ".zst", ".dmg", ".pkg", ".ipa", ".apk", ".jar", ".docx", ".xlsx", ".pptx", ".epub", ".woff2",
];
const MEDIA_SHARE: f64 = 0.9;
/// Sorted like Python's `sorted(JUNK_NAMES)`, which the exclude flags follow.
const JUNK_NAMES: [&str; 4] = [".DS_Store", "Thumbs.db", "__MACOSX", "desktop.ini"];
const TAR_SUFFIXES: [&str; 11] =
    [".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tbz2", ".tar.xz", ".txz", ".tar.zst", ".tzst", ".tar.zstd"];
const OTHER_ARCHIVE_SUFFIXES: [&str; 15] = [
    ".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".zst", ".cab", ".iso", ".cpio", ".xar", ".lzh", ".arj", ".7z.001",
    ".zip.001",
];
const STRIPPED_SUFFIXES: [&str; 22] = [
    ".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".tbz", ".tbz2", ".xz", ".txz", ".zst", ".tzst", ".zstd",
    ".cab", ".iso", ".cpio", ".xar", ".lzh", ".arj", ".dmg", ".001",
];

type Result<T> = std::result::Result<T, String>;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Action {
    Create,
    Extract,
    List,
    Test,
}

fn action(word: &str) -> Option<Action> {
    Some(match word {
        "x" | "extract" => Action::Extract,
        "ls" => Action::List,
        "test" => Action::Test,
        "c" | "create" => Action::Create,
        _ => return None,
    })
}

fn format_suffix(format: &str) -> &'static str {
    FORMATS.iter().find(|(name, _)| *name == format).map(|(_, suffix)| *suffix).unwrap_or(".zip")
}

/// Every known output suffix, longest first.
fn output_suffixes() -> Vec<(&'static str, &'static str)> {
    let mut all: Vec<(&str, &str)> = FORMATS.iter().map(|(name, suffix)| (*suffix, *name)).collect();
    all.extend(EXTRA_OUTPUT_SUFFIXES);
    all.sort_by_key(|(suffix, _)| std::cmp::Reverse(suffix.len()));
    all
}

fn output_format(name: &str) -> Option<&'static str> {
    let lowered = name.to_ascii_lowercase();
    output_suffixes().into_iter().find(|(suffix, _)| lowered.ends_with(suffix)).map(|(_, format)| format)
}

pub fn normalize_format(value: &str) -> Result<&'static str> {
    let lowered = value.to_ascii_lowercase();
    let lowered = lowered.trim_start_matches('.');
    let lowered = FORMAT_ALIASES.iter().find(|(alias, _)| *alias == lowered).map(|(_, name)| *name).unwrap_or(lowered);
    FORMATS.iter().find(|(name, _)| *name == lowered).map(|(name, _)| *name).ok_or_else(|| {
        format!("Unknown format: {value}. Use one of: {}", FORMATS.map(|(name, _)| name).join(", "))
    })
}

pub fn parse_level(value: &str) -> Result<u8> {
    let text = value.trim().to_ascii_lowercase();
    if let Ok(number) = text.parse::<u8>() {
        if number <= 9 && text.chars().all(|c| c.is_ascii_digit()) {
            return Ok(number);
        }
    }
    LEVEL_NAMES.iter().find(|(name, _)| *name == text).map(|(_, number)| *number).ok_or_else(|| {
        format!("Invalid level: {value}. Use 0-9 or {}", LEVEL_NAMES.map(|(name, _)| name).join(", "))
    })
}

fn level_name(level: u8) -> String {
    match LEVEL_NAMES.iter().find(|(_, number)| *number == level) {
        Some((name, _)) => format!("{level} ({name})"),
        None => level.to_string(),
    }
}

fn is_junk(name: &str) -> bool {
    JUNK_NAMES.contains(&name) || name.starts_with("._")
}

fn display(path: &Path) -> String {
    let home = home();
    match path.strip_prefix(&home) {
        Ok(rest) if rest.as_os_str().is_empty() => "~".into(),
        Ok(rest) => format!("~/{}", rest.display()),
        Err(_) => path.display().to_string(),
    }
}

fn size(value: u64) -> String {
    let mut amount = value as f64;
    for unit in ["B", "KB", "MB", "GB"] {
        if amount < 1024.0 || unit == "GB" {
            return if unit == "B" { format!("{amount:.0} {unit}") } else { format!("{amount:.1} {unit}") };
        }
        amount /= 1024.0;
    }
    format!("{amount:.1} TB")
}

/// `os.path.abspath`: absolute and lexically normalised, symlinks untouched.
fn absolute(path: &Path) -> PathBuf {
    let joined = if path.is_absolute() { path.to_path_buf() } else { std::env::current_dir().unwrap_or_default().join(path) };
    let mut normal = PathBuf::from("/");
    for component in joined.components() {
        match component {
            Component::ParentDir => {
                normal.pop();
            }
            Component::Normal(part) => normal.push(part),
            Component::RootDir | Component::CurDir | Component::Prefix(_) => {}
        }
    }
    normal
}

fn expand(path: &str) -> PathBuf {
    crate::util::expand_user(path)
}

fn exists(path: &Path) -> bool {
    path.symlink_metadata().is_ok()
}

fn name_of(path: &Path) -> String {
    path.file_name().map(|name| name.to_string_lossy().into_owned()).unwrap_or_default()
}

/// `Path.suffix`: the last `.ext`, ignoring a leading dot.
fn suffix_of(name: &str) -> &str {
    match name.rfind('.') {
        Some(0) | None => "",
        Some(index) => &name[index..],
    }
}

/// The first free `name`, `name 2`, `name 3`… keeping `suffix` at the end.
fn unique(path: &Path, suffix: Option<&str>) -> PathBuf {
    if !exists(path) {
        return path.to_path_buf();
    }
    let name = name_of(path);
    let suffix = suffix.map(str::to_string).unwrap_or_else(|| {
        if path.is_dir() {
            String::new()
        } else {
            suffix_of(&name).to_string()
        }
    });
    let base = if !suffix.is_empty() && name.ends_with(&suffix) { &name[..name.len() - suffix.len()] } else { &name };
    (2..)
        .map(|number| path.with_file_name(format!("{base} {number}{suffix}")))
        .find(|candidate| !exists(candidate))
        .unwrap()
}

pub fn archive_stem(path: &Path) -> String {
    let original = name_of(path);
    let mut name = original.clone();
    loop {
        let lowered = name.to_ascii_lowercase();
        if let Some(index) = lowered.rfind(".part") {
            let digits = &lowered[index + 5..];
            if !digits.is_empty() && digits.chars().all(|c| c.is_ascii_digit()) {
                name.truncate(index);
                continue;
            }
        }
        let suffix = suffix_of(&lowered);
        if !STRIPPED_SUFFIXES.contains(&suffix) || name.len() == suffix.len() {
            return if name.is_empty() { original } else { name };
        }
        name.truncate(name.len() - suffix.len());
    }
}

fn looks_like_archive(path: &Path) -> bool {
    let name = name_of(path).to_ascii_lowercase();
    path.is_file() && TAR_SUFFIXES.iter().chain(OTHER_ARCHIVE_SUFFIXES.iter()).any(|suffix| name.ends_with(suffix))
}

fn archive_target(sources: &[PathBuf], output: Option<&str>, format: &str) -> PathBuf {
    let suffix = format_suffix(format);
    let base = match sources {
        [source] if source.is_dir() => name_of(source),
        [source] => source.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_else(|| name_of(source)),
        _ => "Archive".into(),
    };
    let target = match output {
        Some(output) => {
            let target = expand(output);
            if target.is_dir() || output.ends_with('/') {
                target.join(format!("{base}{suffix}"))
            } else if output_format(&name_of(&target)).is_none() {
                target.with_file_name(format!("{}{suffix}", name_of(&target)))
            } else {
                target
            }
        }
        None => {
            let directory = match sources {
                [source] => source.parent().map(Path::to_path_buf).unwrap_or_default(),
                _ => std::env::current_dir().unwrap_or_default(),
            };
            directory.join(format!("{base}{suffix}"))
        }
    };
    let target = absolute(&target);
    let name = name_of(&target);
    let lowered = name.to_ascii_lowercase();
    let actual = output_suffixes().into_iter().map(|(known, _)| known).find(|known| lowered.ends_with(known)).unwrap_or(suffix);
    let keep = &name[name.len().saturating_sub(actual.len())..];
    unique(&target, Some(keep))
}

/// Total input size and how much of it is already-compressed media.
fn tree_size(paths: &[PathBuf], keep_junk: bool) -> (u64, u64) {
    fn add(path: &Path, total: &mut u64, media: &mut u64) {
        let Ok(meta) = path.symlink_metadata() else { return };
        *total += meta.len();
        let lowered = name_of(path).to_ascii_lowercase();
        if INCOMPRESSIBLE.contains(&suffix_of(&lowered)) {
            *media += meta.len();
        }
    }
    fn walk(directory: &Path, keep_junk: bool, total: &mut u64, media: &mut u64) {
        let Ok(entries) = fs::read_dir(directory) else { return };
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().into_owned();
            if !keep_junk && is_junk(&name) {
                continue;
            }
            let path = entry.path();
            match entry.file_type() {
                Ok(kind) if kind.is_dir() => walk(&path, keep_junk, total, media),
                Ok(kind) if kind.is_symlink() && path.is_dir() => {}
                Ok(_) => add(&path, total, media),
                Err(_) => {}
            }
        }
    }
    let (mut total, mut media) = (0, 0);
    for path in paths {
        if path.is_symlink() || path.is_file() {
            add(path, &mut total, &mut media);
        } else {
            walk(path, keep_junk, &mut total, &mut media);
        }
    }
    (total, media)
}

fn seven_zip() -> Option<PathBuf> {
    ["7zz", "7z", "7za"].iter().find_map(|name| which(name))
}

fn is_tty(fd: i32) -> bool {
    unsafe { libc::isatty(fd) == 1 }
}

fn progress() -> String {
    if is_tty(1) { "-bsp1" } else { "-bsp0" }.into()
}

fn tar() -> String {
    which("bsdtar").or_else(|| which("tar")).map(|path| path.to_string_lossy().into_owned()).unwrap_or_else(|| "tar".into())
}

fn path_string(path: &Path) -> String {
    path.to_string_lossy().into_owned()
}

/// A fresh private directory, so 7-Zip/RAR never append to a stale partial archive.
fn private_directory(parent: &Path, prefix: &str) -> io::Result<PathBuf> {
    static COUNTER: AtomicU32 = AtomicU32::new(0);
    loop {
        let nanos = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.subsec_nanos()).unwrap_or(0);
        let candidate = parent.join(format!(
            "{prefix}{:x}{:x}{:x}",
            std::process::id(),
            nanos,
            COUNTER.fetch_add(1, Ordering::Relaxed)
        ));
        match fs::create_dir(&candidate) {
            Ok(()) => {
                fs::set_permissions(&candidate, fs::Permissions::from_mode(0o700))?;
                return Ok(candidate);
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        }
    }
}

// ------------------------------------------------------------------ passwords

static mut SAVED_TERMIOS: Option<libc::termios> = None;

extern "C" fn restore_terminal(_: libc::c_int) {
    // Only async-signal-safe calls: put echo back and leave with 130.
    unsafe {
        if let Some(saved) = *std::ptr::addr_of!(SAVED_TERMIOS) {
            libc::tcsetattr(0, libc::TCSANOW, &saved);
        }
        let _ = libc::write(2, b"\n".as_ptr().cast(), 1);
        libc::_exit(130);
    }
}

/// Read a line from the terminal on stdin with echo turned off.
fn read_hidden(prompt: &str) -> io::Result<String> {
    let mut original: libc::termios = unsafe { std::mem::zeroed() };
    if unsafe { libc::tcgetattr(0, &mut original) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let mut hidden = original;
    hidden.c_lflag &= !libc::ECHO;
    unsafe {
        SAVED_TERMIOS = Some(original);
        libc::signal(libc::SIGINT, restore_terminal as *const () as libc::sighandler_t);
        libc::tcsetattr(0, libc::TCSANOW, &hidden);
    }
    eprint!("{prompt}");
    let _ = io::stderr().flush();
    let mut line = String::new();
    let result = io::stdin().read_line(&mut line);
    unsafe {
        libc::tcsetattr(0, libc::TCSANOW, &original);
        libc::signal(libc::SIGINT, libc::SIG_DFL);
        SAVED_TERMIOS = None;
    }
    eprintln!();
    result?;
    Ok(line.trim_end_matches(['\n', '\r']).to_string())
}

fn ask_password(confirm: bool) -> Result<String> {
    if !is_tty(0) {
        return Err("A password needs an interactive terminal.".into());
    }
    let password = read_hidden("Archive password: ").map_err(|error| error.to_string())?;
    if password.is_empty() {
        return Err("Password must not be empty.".into());
    }
    if confirm && read_hidden("Repeat password: ").map_err(|error| error.to_string())? != password {
        return Err("Passwords do not match.".into());
    }
    Ok(password)
}

// ------------------------------------------------------------------- create

struct CreateOptions<'a> {
    format: &'a str,
    level: u8,
    password: bool,
    keep_junk: bool,
}

fn create_commands(
    sources: &[PathBuf],
    temporary: &Path,
    options: &CreateOptions,
    seven_zip: Option<&Path>,
) -> Result<Vec<Vec<String>>> {
    let names: Vec<String> = sources.iter().map(|source| path_string(source)).collect();
    let (format, level) = (options.format, options.level);
    if format == "zip" || format == "7z" {
        if let Some(seven) = seven_zip {
            let mut command = vec![
                path_string(seven),
                "a".into(),
                format!("-t{format}"),
                format!("-mx={level}"),
                "-bso0".into(),
                progress(),
                "-y".into(),
            ];
            if format == "zip" {
                command.push("-mcu=on".into());
            } else {
                command.extend(["-ms=on".into(), "-mmt=on".into()]);
            }
            if options.password {
                let flags: [&str; 2] = if format == "zip" { ["-p", "-mem=AES256"] } else { ["-p", "-mhe=on"] };
                command.extend(flags.map(String::from));
            }
            if !options.keep_junk {
                command.extend(JUNK_NAMES.iter().chain(["._*"].iter()).map(|pattern| format!("-xr!{pattern}")));
            }
            command.push(path_string(temporary));
            command.extend(names);
            return Ok(vec![command]);
        }
        if format == "7z" {
            return Err("7z needs 7-Zip. Install: brew install sevenzip".into());
        }
        if options.password {
            return Err("Encrypted zip needs 7-Zip for AES-256. Install: brew install sevenzip".into());
        }
        return Ok(sources
            .iter()
            .map(|source| {
                let mut command: Vec<String> =
                    ["zip", "-r", "-y", "-X", "-q"].map(String::from).into_iter().collect();
                command.extend([format!("-{level}"), path_string(temporary), name_of(source)]);
                if !options.keep_junk {
                    command.extend(
                        ["-x", "*.DS_Store", "*/._*", "._*", "*__MACOSX*", "*Thumbs.db", "*desktop.ini"].map(String::from),
                    );
                }
                command
            })
            .collect());
    }
    if format == "rar" {
        if which("rar").is_none() {
            return Err("Creating .rar needs the rar tool. Install: brew install --cask rar".into());
        }
        let mut command: Vec<String> = vec!["rar".into(), "a".into(), format!("-m{}", RAR_LEVELS[level as usize])];
        command.extend(["-ma5", "-r", "-ep1", "-rr3%", "-idq", "-y"].map(String::from));
        if options.password {
            command.push("-hp".into());
        }
        if !options.keep_junk {
            command.extend(
                ["*.DS_Store", "*/._*", "._*", "*__MACOSX", "*Thumbs.db", "*desktop.ini"].map(|pattern| format!("-x{pattern}")),
            );
        }
        command.push(path_string(temporary));
        command.extend(names);
        return Ok(vec![command]);
    }
    if options.password {
        return Err("tar formats cannot be encrypted; use --format zip, 7z or rar.".into());
    }
    let output = if format == "tar.zst" { "-".into() } else { path_string(temporary) };
    let mut tar_command = vec![tar(), "-cf".into(), output, "--no-mac-metadata".into()];
    if format == "tar.xz" {
        tar_command.extend(["-J".into(), "--options".into(), format!("xz:compression-level={level},xz:threads=0")]);
    } else if format == "tar.gz" {
        tar_command.extend(["-z".into(), "--options".into(), format!("gzip:compression-level={}", level.max(1))]);
    }
    if !options.keep_junk {
        for pattern in JUNK_NAMES.iter().chain(["._*"].iter()) {
            tar_command.extend(["--exclude".into(), pattern.to_string()]);
        }
    }
    for source in sources {
        let parent = source.parent().map(path_string).unwrap_or_else(|| "/".into());
        tar_command.extend(["-C".into(), parent, name_of(source)]);
    }
    if format == "tar.zst" {
        if which("zstd").is_none() {
            return Err("tar.zst needs zstd. Install: brew install zstd".into());
        }
        let native = ZSTD_LEVELS[level as usize];
        let mut zstd = vec!["zstd".to_string()];
        if native > 19 {
            zstd.extend(["--ultra".into(), format!("-{native}"), "--long=27".into()]);
        } else {
            zstd.push(format!("-{native}"));
        }
        zstd.extend(["-T0", "-q", "-c"].map(String::from));
        return Ok(vec![tar_command, zstd]);
    }
    Ok(vec![tar_command])
}

fn command_for(words: &[String]) -> Command {
    let mut command = Command::new(&words[0]);
    command.args(&words[1..]).env("COPYFILE_DISABLE", "1");
    command
}

fn feed(command: &mut Command, input: Option<&str>) -> io::Result<i32> {
    match input {
        None => status_shielded(command).map(exit_code),
        Some(text) => {
            let _guard = shield();
            let mut child = spawn_shielded(command.stdin(Stdio::piped()))?;
            if let Some(mut stdin) = child.stdin.take() {
                stdin.write_all(text.as_bytes())?;
            }
            child.wait().map(exit_code)
        }
    }
}

fn run_create(commands: &[Vec<String>], format: &str, temporary: &Path, sources: &[PathBuf], password: Option<&str>) -> io::Result<i32> {
    if format == "tar.zst" {
        let output = File::options().write(true).create_new(true).open(temporary)?;
        let _guard = shield();
        let mut producer = spawn_shielded(command_for(&commands[0]).stdout(Stdio::piped()))?;
        let pipe = producer.stdout.take().unwrap();
        let mut compressor = spawn_shielded(command_for(&commands[1]).stdin(pipe).stdout(output))?;
        let compressed = exit_code(compressor.wait()?);
        let archived = exit_code(producer.wait()?);
        return Ok(if archived != 0 { archived } else { compressed });
    }
    let pairs: Vec<(&Vec<String>, &PathBuf)> =
        if commands.len() > 1 { commands.iter().zip(sources).collect() } else { vec![(&commands[0], &sources[0])] };
    let input = password.map(|secret| format!("{secret}\n{secret}\n"));
    for (words, source) in pairs {
        let mut command = command_for(words);
        if words[0] == "zip" {
            command.current_dir(source.parent().unwrap_or(Path::new("/")));
        }
        let code = feed(&mut command, input.as_deref())?;
        if code != 0 {
            return Ok(code);
        }
    }
    Ok(0)
}

fn create(paths: &[String], output: Option<&str>, format: &str, level: Option<u8>, default_level: u8, password: bool, keep_junk: bool) -> Result<i32> {
    let sources: Vec<PathBuf> = paths.iter().map(|path| absolute(&expand(path))).collect();
    for source in &sources {
        if !exists(source) {
            return Err(format!("Not found: {}", display(source)));
        }
        if source.parent().is_none() {
            return Err("Refusing to archive the filesystem root.".into());
        }
    }
    let names: Vec<String> = sources.iter().map(|source| name_of(source)).collect();
    if let Some(duplicate) = names.iter().find(|name| names.iter().filter(|other| other == name).count() > 1) {
        return Err(format!("Two inputs share the name '{duplicate}'; archive them separately or rename one."));
    }
    let target = archive_target(&sources, output, format);
    for source in &sources {
        if source.is_dir() && !source.is_symlink() && target.starts_with(source) {
            return Err(format!("The archive cannot be written inside the folder being archived: {}", display(source)));
        }
    }
    let (before, media) = tree_size(&sources, keep_junk);
    let level = level.unwrap_or_else(|| {
        if default_level > 1 && before > 0 && media as f64 / before as f64 >= MEDIA_SHARE {
            eprintln!(
                "unlaw zip: {:.0}% is already-compressed media; using level 1 because stronger levels only cost time. Pass a level (e.g. -9) to override.",
                media as f64 * 100.0 / before as f64
            );
            1
        } else {
            default_level
        }
    });
    let options = CreateOptions { format, level, password, keep_junk };
    let seven = seven_zip();
    let parent = target.parent().unwrap_or(Path::new("/")).to_path_buf();
    // Fail on missing tools before asking for a password or touching the disk.
    create_commands(&sources, &parent.join(name_of(&target)), &options, seven.as_deref())?;
    let secret = if password && format != "rar" { Some(ask_password(true)?) } else { None };
    fs::create_dir_all(&parent).map_err(|error| error.to_string())?;
    let workspace = private_directory(&parent, ".unlaw-zip-").map_err(|error| error.to_string())?;
    let temporary = workspace.join(name_of(&target));
    let result = (|| -> Result<(PathBuf, f64)> {
        let commands = create_commands(&sources, &temporary, &options, seven.as_deref())?;
        let started = Instant::now();
        let code = run_create(&commands, format, &temporary, &sources, secret.as_deref()).map_err(|error| error.to_string())?;
        let elapsed = started.elapsed().as_secs_f64();
        if code == 130 {
            return Err(String::new());
        }
        if code != 0 || !temporary.is_file() {
            return Err(format!("Could not create {} (exit {}).", display(&target), if code == 0 { 1 } else { code }));
        }
        let suffix = format_suffix(format);
        let keep = name_of(&target).ends_with(suffix).then_some(suffix);
        let target = unique(&target, keep);
        fs::rename(&temporary, &target).map_err(|error| error.to_string())?;
        Ok((target, elapsed))
    })();
    let _ = fs::remove_dir_all(&workspace);
    let (target, elapsed) = match result {
        Ok(done) => done,
        Err(message) if message.is_empty() => return Ok(130),
        Err(message) => return Err(message),
    };
    let after = fs::metadata(&target).map(|meta| meta.len()).unwrap_or(0);
    let ratio = if before > 0 { format!(" ({:.0}%)", after as f64 * 100.0 / before as f64) } else { String::new() };
    let lock = if password { ", encrypted" } else { "" };
    println!(
        "Created {}  {} → {}{ratio}  level {}, {elapsed:.1}s{lock}",
        display(&target),
        size(before),
        size(after),
        level_name(level)
    );
    Ok(0)
}

// ------------------------------------------------------------------ extract

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Kind {
    Tar,
    Zip,
    SevenZip,
    Rar,
    Stream(Codec),
    Other,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Codec {
    Gz,
    Bz2,
    Xz,
    Zst,
}

impl Codec {
    fn extension(self) -> &'static str {
        match self {
            Codec::Gz => "gz",
            Codec::Bz2 => "bz2",
            Codec::Xz => "xz",
            Codec::Zst => "zst",
        }
    }

    /// The decompressor for this codec: `(program, decompress-to-stdout args, test args)`.
    fn tool(self) -> Result<(String, Vec<&'static str>, Vec<&'static str>)> {
        let named = |name: &str| which(name).map(|path| path_string(&path));
        let found = match self {
            Codec::Gz => named("gzip").map(|tool| (tool, vec!["-dc"], vec!["-t"])),
            Codec::Bz2 => named("bzip2").map(|tool| (tool, vec!["-dc"], vec!["-t"])),
            Codec::Zst => named("zstd").map(|tool| (tool, vec!["-d", "-q", "-c"], vec!["-t", "-q"])),
            Codec::Xz => named("xz")
                .map(|tool| (tool, vec!["-dc"], vec!["-t"]))
                .or_else(|| seven_zip().map(|seven| (path_string(&seven), vec!["e", "-so", "-bso0", "-bsp0"], vec!["t", "-bso0", "-bsp0"]))),
        };
        found.ok_or_else(|| match self {
            Codec::Zst => "Extracting .zst needs zstd. Install: brew install zstd".into(),
            Codec::Xz => "Extracting .xz needs xz or 7-Zip. Install: brew install xz".into(),
            other => format!("Extracting .{} needs {}.", other.extension(), if other == Codec::Gz { "gzip" } else { "bzip2" }),
        })
    }
}

fn read_head(path: &Path) -> io::Result<Vec<u8>> {
    let mut head = Vec::with_capacity(512);
    File::open(path)?.take(512).read_to_end(&mut head)?;
    Ok(head)
}

/// The first 512 decompressed bytes, or nothing if the tool is missing or fails.
fn decompressed_head(path: &Path, codec: Codec) -> Vec<u8> {
    let Ok((tool, args, _)) = codec.tool() else { return Vec::new() };
    let Ok(mut child) = Command::new(tool).args(args).arg(path).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::null()).spawn() else {
        return Vec::new();
    };
    let mut head = Vec::with_capacity(512);
    if let Some(stdout) = child.stdout.take() {
        let _ = stdout.take(512).read_to_end(&mut head);
    }
    let _ = child.kill();
    let _ = child.wait();
    head
}

fn is_ustar(head: &[u8]) -> bool {
    head.get(257..262) == Some(b"ustar")
}

fn detect(path: &Path) -> io::Result<Kind> {
    let name = name_of(path).to_ascii_lowercase();
    if TAR_SUFFIXES.iter().any(|suffix| name.ends_with(suffix)) {
        return Ok(Kind::Tar);
    }
    let head = read_head(path)?;
    if [&b"PK\x03\x04"[..], b"PK\x05\x06", b"PK\x07\x08"].iter().any(|magic| head.starts_with(magic)) {
        return Ok(Kind::Zip);
    }
    if head.starts_with(b"7z\xbc\xaf\x27\x1c") {
        return Ok(Kind::SevenZip);
    }
    if head.starts_with(b"Rar!\x1a\x07") {
        return Ok(Kind::Rar);
    }
    if is_ustar(&head) {
        return Ok(Kind::Tar);
    }
    for (magic, codec) in [(&b"\x1f\x8b"[..], Codec::Gz), (b"BZh", Codec::Bz2), (b"\xfd7zXZ\x00", Codec::Xz)] {
        if head.starts_with(magic) {
            return Ok(if is_ustar(&decompressed_head(path, codec)) { Kind::Tar } else { Kind::Stream(codec) });
        }
    }
    if head.starts_with(b"\x28\xb5\x2f\xfd") {
        return Ok(Kind::Stream(Codec::Zst));
    }
    Ok(Kind::Other)
}

fn encrypted(seven: &Path, archive: &Path) -> bool {
    let Ok(output) = Command::new(seven).args(["l", "-slt"]).arg(archive).stdin(Stdio::null()).output() else {
        return false;
    };
    let text = format!("{}{}", String::from_utf8_lossy(&output.stdout), String::from_utf8_lossy(&output.stderr));
    text.contains("Encrypted = +") || (!output.status.success() && text.to_lowercase().contains("password"))
}

/// Decompress one gz/bz2/xz/zst stream into `destination`, or only verify it.
fn decompress_stream(archive: &Path, codec: Codec, destination: Option<&Path>) -> Result<i32> {
    let (tool, extract_args, test_args) = codec.tool()?;
    let mut command = Command::new(tool);
    command.stdin(Stdio::null());
    let code = match destination {
        None => status_shielded(command.args(test_args).arg(archive)),
        Some(destination) => {
            let output = File::options().write(true).create_new(true).open(destination).map_err(|error| error.to_string())?;
            status_shielded(command.args(extract_args).arg(archive).stdout(output))
        }
    }
    .map(exit_code)
    .map_err(|error| error.to_string())?;
    Ok(match code {
        0 | 130 => code,
        _ => 1,
    })
}

fn extract_into(archive: &Path, kind: Kind, directory: &Path, password: Option<&str>) -> Result<i32> {
    if let Kind::Stream(codec) = kind {
        return decompress_stream(archive, codec, Some(&directory.join(archive_stem(archive))));
    }
    let io_error = |error: io::Error| error.to_string();
    let seven = seven_zip();
    match seven {
        Some(seven) if kind != Kind::Tar => {
            let mut command = Command::new(seven);
            command.arg("x").arg(format!("-o{}", directory.display())).args(["-aou", "-bso0"]).arg(progress()).arg(archive);
            match password {
                None => status_shielded(command.stdin(Stdio::null())).map(exit_code).map_err(io_error),
                Some(secret) => feed(&mut command, Some(&format!("{secret}\n"))).map_err(io_error),
            }
        }
        _ => status_shielded(Command::new(tar()).arg("-xf").arg(archive).arg("-C").arg(directory))
            .map(exit_code)
            .map_err(io_error),
    }
}

fn move_unique(source: &Path, destination: &Path) -> io::Result<PathBuf> {
    let target = unique(destination, None);
    fs::rename(source, &target)?;
    Ok(target)
}

fn promote(directory: &Path, parent: &Path, name: &str, here: bool, keep_junk: bool) -> Result<Vec<PathBuf>> {
    let io_error = |error: io::Error| error.to_string();
    if !keep_junk {
        for entry in fs::read_dir(directory).map_err(io_error)?.flatten() {
            if is_junk(&entry.file_name().to_string_lossy()) {
                let path = entry.path();
                if path.is_dir() && !path.is_symlink() { fs::remove_dir_all(&path) } else { fs::remove_file(&path) }.map_err(io_error)?;
            }
        }
    }
    let mut entries: Vec<PathBuf> = fs::read_dir(directory).map_err(io_error)?.flatten().map(|entry| entry.path()).collect();
    entries.sort();
    if entries.is_empty() {
        return Err("The archive is empty.".into());
    }
    if here || entries.len() == 1 {
        return entries.iter().map(|entry| move_unique(entry, &parent.join(name_of(entry))).map_err(io_error)).collect();
    }
    Ok(vec![move_unique(directory, &parent.join(name)).map_err(io_error)?])
}

fn archive_path(name: &str) -> Result<PathBuf> {
    let archive = absolute(&expand(name));
    if archive.is_file() {
        Ok(archive)
    } else {
        Err(format!("Archive not found: {}", display(&archive)))
    }
}

fn password_for(kind: Kind, archive: &Path) -> Result<Option<String>> {
    match (kind, seven_zip()) {
        (Kind::Tar | Kind::Stream(_), _) | (_, None) => Ok(None),
        (_, Some(seven)) if encrypted(&seven, archive) => ask_password(false).map(Some),
        _ => Ok(None),
    }
}

fn extract(name: &str, output: Option<&str>, here: bool, keep_junk: bool) -> Result<i32> {
    let archive = archive_path(name)?;
    let parent = match output {
        Some(output) => absolute(&expand(output)),
        None => archive.parent().unwrap_or(Path::new("/")).to_path_buf(),
    };
    fs::create_dir_all(&parent).map_err(|error| error.to_string())?;
    let kind = detect(&archive).map_err(|error| error.to_string())?;
    let password = password_for(kind, &archive)?;
    let directory = private_directory(&parent, ".unlaw-extract-").map_err(|error| error.to_string())?;
    let result = (|| {
        let code = extract_into(&archive, kind, &directory, password.as_deref())?;
        if code == 130 {
            return Err(String::new());
        }
        if code != 0 {
            return Err(format!("Could not extract {} (exit {code}).", display(&archive)));
        }
        promote(&directory, &parent, &archive_stem(&archive), here, keep_junk)
    })();
    if directory.exists() {
        let _ = fs::remove_dir_all(&directory);
    }
    let results = match result {
        Ok(results) => results,
        Err(message) if message.is_empty() => return Ok(130),
        Err(message) => return Err(message),
    };
    let shown = match results.as_slice() {
        [only] => display(only),
        many => format!("{} items in {}", many.len(), display(&parent)),
    };
    println!("Extracted {} → {shown}", name_of(&archive));
    Ok(0)
}

fn inspect(name: &str, test: bool) -> Result<i32> {
    let archive = archive_path(name)?;
    let kind = detect(&archive).map_err(|error| error.to_string())?;
    let io_error = |error: io::Error| error.to_string();
    let code = match (kind, seven_zip()) {
        (Kind::Stream(_), _) if !test => {
            println!("{}  (single compressed file)", archive_stem(&archive));
            return Ok(0);
        }
        (Kind::Stream(codec), _) => decompress_stream(&archive, codec, None)?,
        (Kind::Tar, _) | (_, None) => {
            let mut command = Command::new(tar());
            command.arg(if test { "-tf" } else { "-tvf" }).arg(&archive);
            if test {
                command.stdout(Stdio::null());
            }
            status_shielded(&mut command).map(exit_code).map_err(io_error)?
        }
        (_, Some(seven)) => {
            let password = password_for(kind, &archive)?;
            let mut command = Command::new(seven);
            command.arg(if test { "t" } else { "l" });
            if test {
                command.arg("-bso0").arg(progress());
            }
            command.arg(&archive);
            match password {
                None => status_shielded(command.stdin(Stdio::null())).map(exit_code).map_err(io_error)?,
                Some(secret) => feed(&mut command, Some(&format!("{secret}\n"))).map_err(io_error)?,
            }
        }
    };
    if code == 130 {
        return Ok(130);
    }
    if code != 0 {
        return Err(format!("{}: {} (exit {code}).", if test { "Test failed" } else { "Could not list" }, display(&archive)));
    }
    if test {
        println!("OK  {}", display(&archive));
    }
    Ok(0)
}

// --------------------------------------------------------------- arguments

#[derive(Debug, Default, PartialEq)]
struct Options {
    paths: Vec<String>,
    output: Option<String>,
    format: Option<String>,
    level: Option<String>,
    password: bool,
    keep_junk: bool,
    here: bool,
}

fn parse_options(args: &[String]) -> std::result::Result<Options, String> {
    let mut options = Options::default();
    let mut rest = args.iter();
    let mut only_paths = false;
    while let Some(arg) = rest.next() {
        if only_paths || arg == "-" || !arg.starts_with('-') {
            options.paths.push(arg.clone());
            continue;
        }
        if arg == "--" {
            only_paths = true;
            continue;
        }
        let (flag, inline) = match arg.split_once('=') {
            Some((flag, value)) if flag.starts_with("--") => (flag, Some(value.to_string())),
            _ => (arg.as_str(), None),
        };
        let mut value = |name: &str| -> std::result::Result<String, String> {
            inline.clone().or_else(|| rest.next().cloned()).ok_or_else(|| format!("argument {name}: expected one argument"))
        };
        match flag {
            "-o" | "--output" => options.output = Some(value("-o/--output")?),
            "-f" | "--format" => options.format = Some(value("-f/--format")?),
            "-l" | "--level" => options.level = Some(value("-l/--level")?),
            "-p" | "--password" => options.password = true,
            "--keep-junk" => options.keep_junk = true,
            "--here" => options.here = true,
            _ => {
                let named = flag.strip_prefix("--").and_then(|name| LEVEL_NAMES.iter().find(|(level, _)| *level == name));
                let numbered = flag.strip_prefix('-').filter(|digit| digit.len() == 1 && digit.as_bytes()[0].is_ascii_digit());
                match (named, numbered) {
                    (Some((_, number)), _) => options.level = Some(number.to_string()),
                    (_, Some(digit)) => options.level = Some(digit.to_string()),
                    _ => return Err(format!("unrecognized arguments: {arg}")),
                }
            }
        }
    }
    Ok(options)
}

struct Settings {
    format: &'static str,
    level: u8,
    keep_junk: bool,
}

fn settings(config: &Config) -> Result<Settings> {
    let format = normalize_format(&config.string("zip.format"))?;
    let level = match config.get("zip.level") {
        Some(Value::Int(number)) => parse_level(&number.to_string()),
        Some(Value::Str(text)) => parse_level(text),
        _ => parse_level("max"),
    }
    .map_err(|error| format!("zip.level: {error}"))?;
    Ok(Settings { format, level, keep_junk: config.flag("zip.keep_junk") })
}

fn dispatch(args: &[String], config: &Config) -> Result<i32> {
    let (action_word, args) = match args.first().and_then(|word| action(word)) {
        Some(action) => (Some(action), &args[1..]),
        None => (None, args),
    };
    let options = match parse_options(args) {
        Ok(options) => options,
        Err(message) => {
            eprintln!("unlaw zip: {message}");
            return Ok(2);
        }
    };
    if options.paths.is_empty() {
        eprintln!("Usage: ul zip <path>... | ul zip x <archive>... — see `ul zip --help`");
        return Ok(2);
    }
    let action = action_word.unwrap_or_else(|| {
        if options.paths.iter().all(|path| looks_like_archive(&expand(path))) {
            Action::Extract
        } else {
            Action::Create
        }
    });
    if action != Action::Create {
        let used: Vec<&str> = [
            ("--format", options.format.is_some()),
            ("a level", options.level.is_some()),
            ("--password", options.password),
        ]
        .iter()
        .filter(|(_, used)| *used)
        .map(|(flag, _)| *flag)
        .collect();
        if !used.is_empty() {
            return Err(format!("{} only applies when creating an archive.", used.join(", ")));
        }
    }
    if matches!(action, Action::List | Action::Test) && (options.output.is_some() || options.here || options.keep_junk) {
        return Err("--output, --here and --keep-junk do not apply to ls/test.".into());
    }
    if action == Action::Create && options.here {
        return Err("--here only applies when extracting.".into());
    }
    if matches!(action, Action::List | Action::Test) {
        let mut worst = 0;
        for path in &options.paths {
            worst = worst.max(inspect(path, action == Action::Test)?);
        }
        return Ok(worst);
    }
    let settings = settings(config)?;
    let keep_junk = options.keep_junk || settings.keep_junk;
    if action == Action::Extract {
        let mut worst = 0;
        for path in &options.paths {
            worst = worst.max(extract(path, options.output.as_deref(), options.here, keep_junk)?);
        }
        return Ok(worst);
    }
    let format = options.format.as_deref().map(normalize_format).transpose()?;
    let inferred = options.output.as_deref().and_then(|output| output_format(&name_of(Path::new(output))));
    if let (Some(format), Some(inferred)) = (format, inferred) {
        if format != inferred {
            return Err(format!("--format {format} conflicts with the output name {}.", options.output.as_deref().unwrap_or("")));
        }
    }
    let level = options.level.as_deref().map(parse_level).transpose()?;
    create(
        &options.paths,
        options.output.as_deref(),
        format.or(inferred).unwrap_or(settings.format),
        level,
        settings.level,
        options.password,
        keep_junk,
    )
}

pub fn run(args: &[String], config: &Config) -> i32 {
    let wants_help = args.is_empty()
        || matches!(args[0].as_str(), "-h" | "--help" | "help")
        || args.iter().any(|arg| arg == "-h" || arg == "--help");
    if wants_help {
        print!("{HELP}");
        return 0;
    }
    match dispatch(args, config) {
        Ok(code) => code,
        Err(message) => {
            eprintln!("unlaw zip: {message}");
            1
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn words(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn levels_formats_and_names() {
        let parsed: Vec<u8> = ["ultra", "max", "store", "4", " 6 "].iter().map(|v| parse_level(v).unwrap()).collect();
        assert_eq!(parsed, vec![9, 7, 0, 4, 6]);
        for bad in ["10", "huge", "-1", "true", "4.0"] {
            assert!(parse_level(bad).unwrap_err().starts_with("Invalid level"), "{bad}");
        }
        assert_eq!(level_name(7), "7 (max)");
        assert_eq!(level_name(2), "2");
        assert_eq!(normalize_format("tgz").unwrap(), "tar.gz");
        assert_eq!(normalize_format(".7Z").unwrap(), "7z");
        assert!(normalize_format("cpio").unwrap_err().contains("zip, 7z, rar, tar.zst, tar.xz, tar.gz"));
        assert_eq!(output_format("pack.TXZ"), Some("tar.xz"));
        assert_eq!(output_format("pack.tar.zst"), Some("tar.zst"));
        assert_eq!(output_format("pack"), None);
    }

    #[test]
    fn stems_drop_archive_suffixes_and_parts() {
        let stem = |name: &str| archive_stem(Path::new(name));
        assert_eq!(stem("a.tar.gz"), "a");
        assert_eq!(stem("movie.part1.rar"), "movie");
        assert_eq!(stem("log.txt.gz"), "log.txt");
        assert_eq!(stem("Backup.7Z.001"), "Backup");
        assert_eq!(stem(".zip"), ".zip");
        assert_eq!(stem("plain"), "plain");
    }

    #[test]
    fn sizes_and_paths_display_like_python() {
        assert_eq!(size(512), "512 B");
        assert_eq!(size(1536), "1.5 KB");
        assert_eq!(size(5 * 1024 * 1024 * 1024 * 1024), "5120.0 GB");
        assert_eq!(display(&home().join("x")), "~/x");
        assert_eq!(display(Path::new("/tmp/x")), "/tmp/x");
        assert_eq!(absolute(Path::new("/a/b/../c/./d")), PathBuf::from("/a/c/d"));
        assert_eq!(suffix_of(".bashrc"), "");
        assert_eq!(suffix_of("notes.md"), ".md");
    }

    #[test]
    fn options_parse_like_argparse() {
        let options = parse_options(&words(&["a", "-o", "out.7z", "-9", "b", "--keep-junk", "--format=zip"])).unwrap();
        assert_eq!(options.paths, words(&["a", "b"]));
        assert_eq!(options.output.as_deref(), Some("out.7z"));
        assert_eq!(options.level.as_deref(), Some("9"));
        assert_eq!(options.format.as_deref(), Some("zip"));
        assert!(options.keep_junk);
        assert_eq!(parse_options(&words(&["--ultra"])).unwrap().level.as_deref(), Some("9"));
        assert_eq!(parse_options(&words(&["--", "-9"])).unwrap().paths, words(&["-9"]));
        assert!(parse_options(&words(&["-o"])).unwrap_err().contains("expected one argument"));
        assert!(parse_options(&words(&["--bogus"])).unwrap_err().contains("unrecognized"));
        assert!(parse_options(&words(&["-12"])).is_err());
    }

    #[test]
    fn native_commands_for_each_format() {
        let sources = vec![PathBuf::from("/work/project")];
        let temporary = Path::new("/work/.tmp/project.x");
        let make = |format: &'static str, level: u8, password: bool, seven: Option<&Path>| {
            create_commands(&sources, temporary, &CreateOptions { format, level, password, keep_junk: false }, seven)
        };
        let seven = Some(Path::new("/bin/7z"));
        let command = &make("7z", 9, true, seven).unwrap()[0];
        assert!(command.contains(&"-mx=9".to_string()) && command.contains(&"-mhe=on".to_string()));
        assert!(command.contains(&"-xr!.DS_Store".to_string()) && command.contains(&"-xr!._*".to_string()));
        assert_eq!(&command[command.len() - 2..], &["/work/.tmp/project.x".to_string(), "/work/project".to_string()]);
        let zip = &make("zip", 0, true, seven).unwrap()[0];
        assert!(zip.contains(&"-mx=0".to_string()) && zip.contains(&"-mem=AES256".to_string()) && zip.contains(&"-mcu=on".to_string()));
        assert!(make("7z", 5, false, None).unwrap_err().contains("brew install sevenzip"));
        assert!(make("zip", 5, true, None).unwrap_err().contains("AES-256"));
        let fallback = &make("zip", 3, false, None).unwrap()[0];
        assert_eq!(&fallback[..7], &words(&["zip", "-r", "-y", "-X", "-q", "-3", "/work/.tmp/project.x"])[..]);
        assert_eq!(fallback[7], "project");
        let gz = &make("tar.gz", 0, false, seven).unwrap()[0];
        assert!(gz.contains(&"gzip:compression-level=1".to_string()));
        assert!(gz.windows(3).any(|w| w == ["-C", "/work", "project"]));
        let xz = &make("tar.xz", 9, false, seven).unwrap()[0];
        assert!(xz.contains(&"xz:compression-level=9,xz:threads=0".to_string()));
        assert!(make("tar.gz", 5, true, seven).unwrap_err().contains("cannot be encrypted"));
    }

    #[test]
    fn unique_names_keep_the_suffix() {
        let directory = std::env::temp_dir().join(format!("unlaw-zip-unique-{}", std::process::id()));
        let _ = fs::remove_dir_all(&directory);
        fs::create_dir_all(directory.join("folder")).unwrap();
        fs::write(directory.join("a.tar.gz"), "").unwrap();
        fs::write(directory.join("a 2.tar.gz"), "").unwrap();
        assert_eq!(unique(&directory.join("a.tar.gz"), Some(".tar.gz")), directory.join("a 3.tar.gz"));
        assert_eq!(unique(&directory.join("folder"), None), directory.join("folder 2"));
        assert_eq!(unique(&directory.join("free.zip"), None), directory.join("free.zip"));
        fs::remove_dir_all(directory).unwrap();
    }
}
