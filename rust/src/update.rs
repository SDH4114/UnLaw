//! `ul update`: reinstall Unlaw from GitHub with `cargo install`.

use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::commands;
use crate::config;
use crate::features;
use crate::help::print_if_requested;
use crate::util::{home, is_executable, shell_join, which};
use crate::{COMMIT, VERSION};

pub const REPOSITORY: &str = "https://github.com/SDH4114/UnLaw.git";

pub(crate) fn repository() -> String {
    env::var("UNLAW_UPDATE_REPOSITORY").ok().filter(|url| !url.is_empty()).unwrap_or_else(|| REPOSITORY.into())
}

#[derive(Debug, PartialEq, Eq)]
enum Source {
    Default,
    Branch(String),
    Tag(String),
}

impl Source {
    fn git_ref(&self) -> &str {
        match self {
            Source::Default => "main",
            Source::Branch(name) | Source::Tag(name) => name,
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
struct Options {
    check: bool,
    force: bool,
    source: Source,
}

fn parse(args: &[String]) -> Result<Options, ()> {
    let mut options = Options { check: false, force: false, source: Source::Default };
    let mut rest = args.iter();
    while let Some(arg) = rest.next() {
        match arg.as_str() {
            "--check" if !options.check => options.check = true,
            "--force" if !options.force => options.force = true,
            "--branch" | "--tag" if options.source == Source::Default => {
                let name = rest.next().filter(|name| !name.is_empty() && !name.starts_with('-')).ok_or(())?;
                options.source = if arg == "--branch" { Source::Branch(name.clone()) } else { Source::Tag(name.clone()) };
            }
            _ => return Err(()),
        }
    }
    Ok(options)
}

/// `https://github.com/OWNER/REPO(.git)` → raw URL of a file at `git_ref`.
pub(crate) fn raw_url(repository: &str, git_ref: &str, file: &str) -> Option<String> {
    let path = repository.strip_prefix("https://github.com/")?.trim_end_matches('/');
    let path = path.strip_suffix(".git").unwrap_or(path);
    let (owner, repo) = path.split_once('/')?;
    (!owner.is_empty() && !repo.is_empty() && !repo.contains('/'))
        .then(|| format!("https://raw.githubusercontent.com/{owner}/{repo}/{git_ref}/{file}"))
}

/// The `version = "..."` of the `[package]` table in a Cargo.toml.
fn package_version(cargo_toml: &str) -> Option<String> {
    let document: toml_edit::DocumentMut = cargo_toml.parse().ok()?;
    document.get("package")?.get("version")?.as_str().map(str::to_string)
}

fn version_key(version: &str) -> Vec<u64> {
    version
        .split(['.', '-', '+'])
        .map_while(|part| part.parse().ok())
        .collect()
}

/// The commit a branch or tag points to on the remote, via `git ls-remote`.
fn remote_commit(repository: &str, source: &Source) -> Option<String> {
    let reference = match source {
        Source::Default => "refs/heads/main".to_string(),
        Source::Branch(name) => format!("refs/heads/{name}"),
        Source::Tag(name) => format!("refs/tags/{name}"),
    };
    let output = Command::new("git")
        .args(["ls-remote", repository, &reference, &format!("{reference}^{{}}")])
        .env("GIT_TERMINAL_PROMPT", "0")
        .stdin(std::process::Stdio::null())
        .output()
        .ok()
        .filter(|output| output.status.success())?;
    let text = String::from_utf8_lossy(&output.stdout).into_owned();
    // An annotated tag's `^{}` line names the commit; prefer it.
    let line = text.lines().find(|line| line.ends_with("^{}")).or_else(|| text.lines().next())?;
    let hash = line.split_whitespace().next()?;
    (hash.len() >= 7 && hash.chars().all(|c| c.is_ascii_hexdigit())).then(|| hash[..7].to_string())
}

fn latest_version(repository: &str, git_ref: &str) -> Result<String, (i32, String)> {
    let Some(url) = raw_url(repository, git_ref, "Cargo.toml") else {
        return Err((2, format!("--check supports only https://github.com repositories: {repository}")));
    };
    let output = Command::new("curl")
        .args(["-fsSL", "--max-time", "20", &url])
        .output()
        .map_err(|error| (1, format!("Could not run curl: {error}")))?;
    if !output.status.success() {
        return Err((1, format!("Could not fetch {url}: {}", String::from_utf8_lossy(&output.stderr).trim())));
    }
    package_version(&String::from_utf8_lossy(&output.stdout)).ok_or((1, format!("{url} has no package version")))
}

fn verdict(installed_commit: &str, latest_commit: Option<&str>, latest: &str) -> &'static str {
    let newer_version = version_key(latest) > version_key(VERSION);
    let older_version = version_key(latest) < version_key(VERSION);
    match latest_commit {
        Some(commit) if !installed_commit.is_empty() && commit == installed_commit => "Up to date.",
        _ if newer_version => "Update available: a new version. Run: ul update",
        Some(_) if !installed_commit.is_empty() && older_version => "This build is newer than the published one.",
        Some(_) if !installed_commit.is_empty() => "Update available: newer commits. Run: ul update",
        _ if older_version => "The installed version is newer than the published one.",
        _ => "Same version number; the commit is unknown. `ul update` installs the newest commit.",
    }
}

fn check(options: &Options) -> i32 {
    let repository = repository();
    let git_ref = options.source.git_ref();
    let latest = match latest_version(&repository, git_ref) {
        Ok(latest) => latest,
        Err((code, message)) => {
            eprintln!("unlaw update: {message}");
            return code;
        }
    };
    let latest_commit = remote_commit(&repository, &options.source);
    let installed = if COMMIT.is_empty() { VERSION.to_string() } else { format!("{VERSION} ({COMMIT})") };
    let published = match &latest_commit {
        Some(commit) => format!("{latest} ({commit}, {git_ref})"),
        None => format!("{latest} ({git_ref})"),
    };
    println!("Installed: {installed}");
    println!("Latest:    {published}");
    println!("{}", verdict(COMMIT, latest_commit.as_deref(), &latest));
    0
}

pub(crate) fn cargo() -> Option<PathBuf> {
    which("cargo").or_else(|| Some(home().join(".cargo/bin/cargo")).filter(|path| is_executable(path)))
}

/// Install next to the running binary when it lives in a `bin` directory
/// (`~/.local/bin`, `~/.cargo/bin`), otherwise into `~/.local`.
pub(crate) fn install_root() -> PathBuf {
    let exe = env::current_exe().and_then(std::fs::canonicalize).ok();
    exe.as_deref()
        .and_then(Path::parent)
        .filter(|directory| directory.file_name().is_some_and(|name| name == "bin"))
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .unwrap_or_else(|| home().join(".local"))
}

/// The features to build: the configured ones, or this build's when the
/// configuration cannot be read.
fn selection() -> Vec<&'static str> {
    config::load().map(|config| features::selected(&config)).unwrap_or_else(|_| features::compiled())
}

/// The shared build folder of `ul update` (unless CARGO_TARGET_DIR is set).
pub(crate) fn build_cache() -> PathBuf {
    home().join("Library").join("Caches").join("unlaw").join("cargo-target")
}

/// `cargo install` arguments for both packages; unlaw gets the chosen cargo
/// features, ule has none.
fn install_commands(cargo: &Path, root: &Path, source: &Source, rev: Option<&str>, selection: &[&str]) -> Vec<Vec<String>> {
    let package = |name: &str| {
        let mut command =
            vec![cargo.to_string_lossy().into_owned(), "install".into(), "--locked".into(), "--force".into(), "--git".into(), repository()];
        match (rev, source) {
            (Some(rev), _) => command.extend(["--rev".into(), rev.to_string()]),
            (None, Source::Default) => {}
            (None, Source::Branch(name)) => command.extend(["--branch".into(), name.clone()]),
            (None, Source::Tag(name)) => command.extend(["--tag".into(), name.clone()]),
        }
        command.extend(["--root".into(), root.to_string_lossy().into_owned()]);
        if name == "unlaw" {
            command.push("--no-default-features".into());
            let cargo_features = features::cargo_features(selection);
            if !cargo_features.is_empty() {
                command.extend(["--features".into(), cargo_features.join(",")]);
            }
        }
        command.push(name.into());
        command
    };
    vec![package("unlaw"), package("ule")]
}

fn install(source: &Source, rev: Option<&str>) -> i32 {
    let Some(cargo) = cargo() else {
        eprintln!(
            "unlaw update: cargo was not found. Install Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
        );
        return 1;
    };
    let config = config::load().ok();
    let python = commands::python(config.as_ref());
    let root = install_root();
    for command in install_commands(&cargo, &root, source, rev, &selection()) {
        println!("Updating Unlaw {VERSION}: {}", shell_join(&command));
        let mut process = Command::new(&command[0]);
        process.args(&command[1..]);
        // One build folder for both packages and every update: shared dependencies
        // compile once, and later updates rebuild only what changed.
        if env::var_os("CARGO_TARGET_DIR").is_none() {
            process.env("CARGO_TARGET_DIR", build_cache());
        }
        if let Some(python) = &python {
            process.env("UNLAW_PYTHON", python);
        }
        let status = match process.status() {
            Ok(status) => status,
            Err(error) => {
                eprintln!("unlaw update: Could not run cargo: {error}");
                return 1;
            }
        };
        if !status.success() {
            if command.last().is_some_and(|package| package == "ule") {
                eprintln!("unlaw update: unlaw was installed, but ule installation failed; run `ul update --force` to retry.");
            } else {
                eprintln!("unlaw update: cargo install failed; the installed version was not changed.");
            }
            return status.code().unwrap_or(1);
        }
    }
    let installed = root.join("bin").join("ul");
    let version = Command::new(&installed)
        .arg("--version")
        .output()
        .ok()
        .filter(|output| output.status.success())
        .map(|output| String::from_utf8_lossy(&output.stdout).trim().to_string())
        .unwrap_or_else(|| "Unlaw (unknown version)".into());
    println!("Updated to {version} in {}.", root.join("bin").display());
    println!("Unchanged default commands are upgraded on the next run; edited ones are kept.");
    0
}

/// `ul reinstall`: the newest commit of main, built again.
pub(crate) fn install_latest() -> i32 {
    install(&Source::Default, None)
}

/// Rebuild this same commit with the configured features (`ul features`), so
/// adding a feature never upgrades everything else by surprise.
pub fn rebuild() -> i32 {
    if COMMIT.is_empty() {
        println!("This build's commit is unknown; installing the newest commit of main instead.");
        return install(&Source::Default, None);
    }
    install(&Source::Default, Some(COMMIT))
}

pub fn run(args: &[String]) -> i32 {
    if print_if_requested("update", args) {
        return 0;
    }
    let Ok(options) = parse(args) else {
        eprintln!("Usage: ul update [--check] [--force] [--branch <name>|--tag <name>]");
        return 2;
    };
    if options.check {
        return check(&options);
    }
    let root = install_root();
    // Nothing to do when this build is the published commit with the chosen
    // features and ule is installed too.
    if !options.force && !COMMIT.is_empty() && root.join("bin").join("ule").is_file() && !features::needs_rebuild(&selection()) {
        if let Some(latest) = remote_commit(&repository(), &options.source) {
            if latest == COMMIT {
                println!("Unlaw {VERSION} ({COMMIT}) is up to date. `ul update --force` reinstalls anyway.");
                return 0;
            }
        }
    }
    install(&options.source, None)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn words(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn options_parse_strictly() {
        assert_eq!(parse(&[]), Ok(Options { check: false, force: false, source: Source::Default }));
        assert_eq!(
            parse(&words(&["--check", "--tag", "v3.0.0"])),
            Ok(Options { check: true, force: false, source: Source::Tag("v3.0.0".into()) })
        );
        assert_eq!(parse(&words(&["--branch", "dev"])).unwrap().source, Source::Branch("dev".into()));
        for bad in [&["--branch"][..], &["--branch", "--check"], &["--tag", "a", "--branch", "b"], &["--check", "--check"], &["now"]] {
            assert_eq!(parse(&words(bad)), Err(()), "{bad:?}");
        }
    }

    #[test]
    fn unlaw_gets_the_chosen_cargo_features_and_ule_none() {
        let commands = install_commands(Path::new("/c/cargo"), Path::new("/r"), &Source::Tag("v3".into()), None, &["lm", "agent", "yt"]);
        let unlaw = commands[0].join(" ");
        assert!(unlaw.ends_with("--root /r --no-default-features --features lm,agent unlaw"), "{unlaw}");
        assert!(unlaw.contains("--tag v3"));
        assert_eq!(commands[1].last().map(String::as_str), Some("ule"));
        assert!(!commands[1].iter().any(|arg| arg.starts_with("--features") || arg == "--no-default-features"));
        let bare = install_commands(Path::new("cargo"), Path::new("/r"), &Source::Default, Some("abc1234"), &["yt"]);
        assert!(bare[0].join(" ").ends_with("--rev abc1234 --root /r --no-default-features unlaw"), "{:?}", bare[0]);
    }

    #[test]
    fn raw_urls_come_from_github_repositories() {
        assert_eq!(
            raw_url("https://github.com/SDH4114/UnLaw.git", "main", "Cargo.toml").as_deref(),
            Some("https://raw.githubusercontent.com/SDH4114/UnLaw/main/Cargo.toml")
        );
        assert_eq!(
            raw_url("https://github.com/me/fork/", "v1", "Cargo.toml").as_deref(),
            Some("https://raw.githubusercontent.com/me/fork/v1/Cargo.toml")
        );
        assert_eq!(raw_url("https://gitlab.com/me/fork", "main", "Cargo.toml"), None);
        assert_eq!(raw_url("https://github.com/only-owner", "main", "Cargo.toml"), None);
    }

    #[test]
    fn verdicts_compare_commits_first_then_versions() {
        let newer = "99.0.0";
        assert_eq!(verdict("abc1234", Some("abc1234"), VERSION), "Up to date.");
        assert_eq!(verdict("abc1234", Some("abc1234"), newer), "Up to date.", "same commit wins");
        assert!(verdict("abc1234", Some("def5678"), VERSION).contains("newer commits"));
        assert!(verdict("abc1234", Some("def5678"), newer).contains("a new version"));
        assert!(verdict("abc1234", Some("def5678"), "0.1.0").contains("build is newer"));
        assert!(verdict("", Some("def5678"), VERSION).contains("commit is unknown"));
        assert!(verdict("", None, newer).contains("a new version"));
        assert!(verdict("abc1234", None, "0.1.0").contains("installed version is newer"));
    }

    #[test]
    fn versions_are_read_and_compared_numerically() {
        assert_eq!(package_version("[package]\nname = \"unlaw\"\nversion = \"2.10.0\"\n").as_deref(), Some("2.10.0"));
        assert_eq!(package_version("[dependencies]\nversion = \"1\"\n"), None);
        assert!(version_key("2.10.0") > version_key("2.9.9"));
        assert_eq!(version_key("2.1.3-beta"), vec![2, 1, 3]);
    }
}
