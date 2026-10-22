//! `ul update`: reinstall Unlaw from GitHub with `cargo install`.

use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::commands;
use crate::config;
use crate::help::print_if_requested;
use crate::util::{home, is_executable, shell_join, which};
use crate::VERSION;

pub const REPOSITORY: &str = "https://github.com/SDH4114/UnLaw.git";

fn repository() -> String {
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
    source: Source,
}

fn parse(args: &[String]) -> Result<Options, ()> {
    let mut options = Options { check: false, source: Source::Default };
    let mut rest = args.iter();
    while let Some(arg) = rest.next() {
        match arg.as_str() {
            "--check" if !options.check => options.check = true,
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
fn raw_url(repository: &str, git_ref: &str, file: &str) -> Option<String> {
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

fn check(options: &Options) -> i32 {
    let repository = repository();
    let Some(url) = raw_url(&repository, options.source.git_ref(), "Cargo.toml") else {
        eprintln!("unlaw update: --check supports only https://github.com repositories: {repository}");
        return 2;
    };
    let output = match Command::new("curl").args(["-fsSL", "--max-time", "20", &url]).output() {
        Ok(output) => output,
        Err(error) => {
            eprintln!("unlaw update: Could not run curl: {error}");
            return 1;
        }
    };
    if !output.status.success() {
        eprintln!("unlaw update: Could not fetch {url}: {}", String::from_utf8_lossy(&output.stderr).trim());
        return 1;
    }
    let Some(latest) = package_version(&String::from_utf8_lossy(&output.stdout)) else {
        eprintln!("unlaw update: {url} has no package version");
        return 1;
    };
    println!("Installed: {VERSION}");
    println!("Latest:    {latest} ({})", options.source.git_ref());
    let message = match version_key(&latest).cmp(&version_key(VERSION)) {
        std::cmp::Ordering::Greater => "Update available. Run: ul update",
        std::cmp::Ordering::Equal => "Same version number. `ul update` still installs the newest commit.",
        std::cmp::Ordering::Less => "The installed version is newer than the published one.",
    };
    println!("{message}");
    0
}

fn cargo() -> Option<PathBuf> {
    which("cargo").or_else(|| Some(home().join(".cargo/bin/cargo")).filter(|path| is_executable(path)))
}

/// Install next to the running binary when it lives in a `bin` directory
/// (`~/.local/bin`, `~/.cargo/bin`), otherwise into `~/.local`.
fn install_root() -> PathBuf {
    let exe = env::current_exe().and_then(std::fs::canonicalize).ok();
    exe.as_deref()
        .and_then(Path::parent)
        .filter(|directory| directory.file_name().is_some_and(|name| name == "bin"))
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .unwrap_or_else(|| home().join(".local"))
}

pub fn run(args: &[String]) -> i32 {
    if print_if_requested("update", args) {
        return 0;
    }
    let Ok(options) = parse(args) else {
        eprintln!("Usage: ul update [--check] [--branch <name>|--tag <name>]");
        return 2;
    };
    if options.check {
        return check(&options);
    }
    let Some(cargo) = cargo() else {
        eprintln!(
            "unlaw update: cargo was not found. Install Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
        );
        return 1;
    };
    let config = config::load().ok();
    let python = commands::python(config.as_ref());
    let root = install_root();
    let mut command = vec![
        cargo.to_string_lossy().into_owned(),
        "install".into(),
        "--locked".into(),
        "--force".into(),
        "--git".into(),
        repository(),
    ];
    match &options.source {
        Source::Default => {}
        Source::Branch(name) => command.extend(["--branch".into(), name.clone()]),
        Source::Tag(name) => command.extend(["--tag".into(), name.clone()]),
    }
    command.extend(["--root".into(), root.to_string_lossy().into_owned(), "unlaw".into()]);
    println!("Updating Unlaw {VERSION}: {}", shell_join(&command));
    let mut process = Command::new(&command[0]);
    process.args(&command[1..]);
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
        eprintln!("unlaw update: cargo install failed; the installed version was not changed.");
        return status.code().unwrap_or(1);
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

#[cfg(test)]
mod tests {
    use super::*;

    fn words(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn options_parse_strictly() {
        assert_eq!(parse(&[]), Ok(Options { check: false, source: Source::Default }));
        assert_eq!(
            parse(&words(&["--check", "--tag", "v3.0.0"])),
            Ok(Options { check: true, source: Source::Tag("v3.0.0".into()) })
        );
        assert_eq!(parse(&words(&["--branch", "dev"])).unwrap().source, Source::Branch("dev".into()));
        for bad in [&["--branch"][..], &["--branch", "--check"], &["--tag", "a", "--branch", "b"], &["--check", "--check"], &["now"]] {
            assert_eq!(parse(&words(bad)), Err(()), "{bad:?}");
        }
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
    fn versions_are_read_and_compared_numerically() {
        assert_eq!(package_version("[package]\nname = \"unlaw\"\nversion = \"2.10.0\"\n").as_deref(), Some("2.10.0"));
        assert_eq!(package_version("[dependencies]\nversion = \"1\"\n"), None);
        assert!(version_key("2.10.0") > version_key("2.9.9"));
        assert_eq!(version_key("2.1.3-beta"), vec![2, 1, 3]);
    }
}
