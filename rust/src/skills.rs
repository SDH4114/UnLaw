//! `ul skills`: an Agent Skill that teaches coding agents (Claude Code, Codex
//! and others reading `.agents/skills`) to use `ul`. SKILL.md tells agents to
//! discover commands live, so new commands work at once; `reference/` is a
//! generated snapshot of their help that refreshes itself whenever the command
//! set or the Unlaw build changes.

use std::env;
use std::fs;
use std::io;
use std::os::unix::fs::symlink;
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::assets::SEED_HELP;
use crate::builtin;
use crate::config::{self, config_dir, Config};
use crate::help::{print_if_requested, system_help};
use crate::system::{records, Record};
use crate::util::{atomic_write, expand_user, home};

const SKILL: &str = "unlaw";
/// Present in every folder `ul skills install` wrote; nothing else is touched.
const MARKER: &str = ".unlaw-skill";
const USAGE: &str = "Usage: ul skills install|remove [--project|--path <dir>] [--claude]
       ul skills list|show [command]";

fn manifest_path() -> PathBuf {
    config_dir().join("skills.json")
}

#[derive(Clone, Debug, PartialEq)]
struct Install {
    path: PathBuf,
    links: Vec<PathBuf>,
}

#[derive(Default)]
struct Manifest {
    installs: Vec<Install>,
    fingerprint: String,
}

fn read_manifest() -> Option<Manifest> {
    let text = fs::read_to_string(manifest_path()).ok()?;
    let value: Value = serde_json::from_str(&text).ok()?;
    let paths = |item: &Value| {
        item.as_array()
            .into_iter()
            .flatten()
            .filter_map(Value::as_str)
            .map(PathBuf::from)
            .collect()
    };
    let installs = value["installs"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|item| {
            Some(Install {
                path: PathBuf::from(item["path"].as_str()?),
                links: paths(&item["links"]),
            })
        })
        .collect();
    Some(Manifest {
        installs,
        fingerprint: value["fingerprint"].as_str().unwrap_or("").to_string(),
    })
}

fn write_manifest(manifest: &Manifest) -> io::Result<()> {
    if manifest.installs.is_empty() {
        return match fs::remove_file(manifest_path()) {
            Err(error) if error.kind() != io::ErrorKind::NotFound => Err(error),
            _ => Ok(()),
        };
    }
    let installs: Vec<Value> = manifest
        .installs
        .iter()
        .map(|install| {
            json!({
                "path": install.path.to_string_lossy(),
                "links": install.links.iter().map(|link| link.to_string_lossy()).collect::<Vec<_>>(),
            })
        })
        .collect();
    let text = serde_json::to_string_pretty(
        &json!({"installs": installs, "fingerprint": manifest.fingerprint}),
    )
    .map_err(io::Error::other)?;
    atomic_write(&manifest_path(), &(text + "\n"), ".skills.")
}

fn modified(path: &Path) -> String {
    fs::metadata(path)
        .and_then(|meta| meta.modified())
        .ok()
        .and_then(|time| time.duration_since(UNIX_EPOCH).ok())
        .map(|age| format!("{}.{}", age.as_secs(), age.subsec_nanos()))
        .unwrap_or_default()
}

/// Changes when the build, the set of commands or a user command's source or
/// help.txt changes; cheap enough (one stat per command) to check on every run.
fn fingerprint(records: &[Record]) -> String {
    let mut digest = Sha256::new();
    digest.update(format!("{}\n{}\n", crate::VERSION, crate::COMMIT));
    for record in records {
        digest.update(format!("{}\t{}", record.name, record.source));
        if let Some(path) = &record.path {
            let help = path
                .parent()
                .map(|directory| directory.join("help.txt"))
                .unwrap_or_default();
            digest.update(format!("\t{}\t{}", modified(path), modified(&help)));
        }
        digest.update("\n");
    }
    digest
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn source_label(record: &Record) -> &'static str {
    match record.source {
        "config" => "command",
        other => other,
    }
}

fn reference(record: &Record) -> String {
    let name = &record.name;
    let help = match record.source {
        "system" => Some(system_help(name).to_string()),
        "builtin" => Some(builtin::help(name).to_string()),
        "config" => record
            .path
            .as_ref()
            .and_then(|path| fs::read_to_string(path.parent()?.join("help.txt")).ok())
            .filter(|text| !text.trim().is_empty())
            .or_else(|| {
                SEED_HELP
                    .iter()
                    .find(|(seed, _)| seed == name)
                    .map(|(_, text)| text.to_string())
            }),
        _ => None,
    };
    let mut page = format!("# ul {name}\n\nSource: {}.\n\n", source_label(record));
    match (record.source, help) {
        ("alias", _) => page.push_str(&format!("A user-defined alias for another command. Run `ul which {name}` to see what it runs.\n")),
        (_, Some(help)) => {
            page.push_str(&format!("```text\n{}\n```\n\n", help.trim_end()));
            page.push_str(&format!("This is a snapshot; `ul {name} --help` is authoritative.\n"));
        }
        (_, None) => {
            if let Some(summary) = &record.summary {
                page.push_str(&format!("{summary}\n\n"));
            }
            page.push_str(&format!("No help snapshot. Run `ul {name} --help` for usage.\n"));
        }
    }
    page
}

fn skill_markdown(records: &[Record]) -> String {
    let mut text = String::from(
        "---
name: unlaw
description: Use the `ul` (Unlaw) command line on this Mac. It runs the user's personal commands (TODO board, Telegram, screen capture, YouTube downloads, archives, local AI models with `ul lm`, a local agent with `ul agent`, project templates, app launchers) and manages Unlaw configuration. Use it when the user mentions ul or unlaw, or asks for one of these tasks.
---

# Unlaw (`ul`)

`ul` (also installed as `unlaw`) is a small macOS command launcher. Its commands change between versions and the user adds their own, so discover them live instead of relying on memory:

1. `ul commands --describe` lists every command with a one-line description; `ul commands --json` gives structured records (name, source, path, summary).
2. `ul <command> --help` prints full usage. Every command prints help for `--help` or `-h` before doing anything, so it is always safe to run.
3. `ul which <command>` tells whether a name is a system command, a built-in, a user command (with its path) or an alias.

## Rules

- Read `ul <command> --help` before using a command for the first time in a session; options change between releases.
- Change settings with `ul config get <key>` and `ul config set <key> <value>` (validated, atomic, keeps comments). Do not edit `config.toml` by hand. `ul config show` prints it, `ul config check` validates it.
- Ask the user before commands with outside effects: sending Telegram messages (`ul tg`), committing or pushing (`ul git`), `ul update`, deleting models (`ul lm rm`), opening apps.
- `ul doctor` diagnoses setup problems; `ul doctor --json` returns a report.
- New commands: `ul create command <name>` creates `commands/<name>/main.py` in the Unlaw config directory (`ul init` prints its location). Commands use Python 3.11+ and the standard library, and must support `--help`.
- Files Unlaw produces (captures, downloads, models) live under `ul config get storage.root`.

## Commands

",
    );
    text.push_str(&format!(
        "Snapshot for Unlaw {}; it refreshes automatically when commands change. `reference/<command>.md` holds each command's help. When this list and `ul commands` disagree, `ul commands` is right.\n\n",
        crate::version_line().trim_start_matches("Unlaw ")
    ));
    text.push_str("| Command | Source | Description |\n|---|---|---|\n");
    for record in records {
        let summary = match record.source {
            "alias" => "Alias; run `ul which` to see it".to_string(),
            _ => record
                .summary
                .clone()
                .unwrap_or_default()
                .replace('|', "\\|"),
        };
        text.push_str(&format!(
            "| `{}` | {} | {summary} |\n",
            record.name,
            source_label(record)
        ));
    }
    text
}

/// Every generated file as (path relative to the skill folder, content).
fn render(config: &Config) -> Vec<(PathBuf, String)> {
    let records = records(config, true);
    let mut files = vec![(PathBuf::from("SKILL.md"), skill_markdown(&records))];
    for record in &records {
        files.push((
            Path::new("reference").join(format!("{}.md", record.name)),
            reference(record),
        ));
    }
    files
}

fn owned(target: &Path) -> bool {
    target.join(MARKER).is_file()
}

fn write_skill(target: &Path, config: &Config) -> io::Result<()> {
    let files = render(config);
    for (relative, text) in &files {
        atomic_write(&target.join(relative), text, ".skill.")?;
    }
    // Drop pages of commands that no longer exist; reference/ is ours alone.
    if let Ok(entries) = fs::read_dir(target.join("reference")) {
        for entry in entries.flatten() {
            let path = entry.path();
            let current = files
                .iter()
                .any(|(relative, _)| target.join(relative) == path);
            if !current && path.extension().is_some_and(|extension| extension == "md") {
                fs::remove_file(&path)?;
            }
        }
    }
    atomic_write(
        &target.join(MARKER),
        "Generated by `ul skills install`; `ul skills remove` deletes it.\n",
        ".skill.",
    )
}

enum Place {
    Home,
    Project,
    Path(PathBuf),
}

struct Options {
    place: Place,
    claude: bool,
    all: bool,
}

fn parse(args: &[String], allow_all: bool) -> Result<Options, String> {
    let mut options = Options {
        place: Place::Home,
        claude: false,
        all: false,
    };
    let mut placed = false;
    let mut iter = args.iter();
    while let Some(arg) = iter.next() {
        let place = match arg.as_str() {
            "--claude" => {
                options.claude = true;
                continue;
            }
            "--all" if allow_all => {
                options.all = true;
                continue;
            }
            "--project" => Place::Project,
            "--path" => match iter.next() {
                Some(path) if !path.is_empty() => Place::Path(expand_user(path)),
                _ => return Err("--path needs a directory".into()),
            },
            other => return Err(format!("Unexpected argument {other}")),
        };
        if placed {
            return Err("Choose one of --project and --path".into());
        }
        (options.place, placed) = (place, true);
    }
    if options.all && placed {
        return Err("--all removes every install; drop --project/--path".into());
    }
    Ok(options)
}

fn absolute(path: PathBuf) -> PathBuf {
    if path.is_absolute() {
        path
    } else {
        env::current_dir()
            .map(|cwd| cwd.join(&path))
            .unwrap_or(path)
    }
}

/// The skill folder and, for `--claude`, where Claude Code looks for it.
fn locations(place: &Place) -> (PathBuf, PathBuf) {
    let cwd = || env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    match place {
        Place::Home => (
            home().join(".agents/skills").join(SKILL),
            home().join(".claude/skills").join(SKILL),
        ),
        Place::Project => (
            cwd().join(".agents/skills").join(SKILL),
            cwd().join(".claude/skills").join(SKILL),
        ),
        Place::Path(directory) => (
            absolute(directory.join(SKILL)),
            home().join(".claude/skills").join(SKILL),
        ),
    }
}

fn link_points_to(link: &Path, target: &Path) -> bool {
    match fs::read_link(link) {
        Ok(destination) => {
            let resolved = if destination.is_absolute() {
                destination
            } else {
                link.parent().unwrap_or(Path::new("/")).join(destination)
            };
            resolved.canonicalize().ok() == target.canonicalize().ok()
        }
        Err(_) => false,
    }
}

fn link_claude(link: &Path, target: &Path, place: &Place) -> Result<(), String> {
    if link_points_to(link, target) {
        return Ok(());
    }
    if fs::symlink_metadata(link).is_ok() {
        return Err(format!(
            "{} already exists and was not replaced",
            link.display()
        ));
    }
    // Relative inside a project, so the link survives moving or cloning it.
    let destination = match place {
        Place::Path(_) => target.to_path_buf(),
        Place::Home | Place::Project => PathBuf::from("../../.agents/skills").join(SKILL),
    };
    let parent = link.parent().unwrap_or(Path::new("."));
    fs::create_dir_all(parent)
        .and_then(|_| symlink(&destination, link))
        .map_err(|error| format!("Could not link {}: {error}", link.display()))
}

fn install(args: &[String], config: &Config) -> i32 {
    let options = match parse(args, false) {
        Ok(options) => options,
        Err(message) => return fail(message),
    };
    let (target, link) = locations(&options.place);
    let empty = fs::read_dir(&target)
        .map(|mut entries| entries.next().is_none())
        .unwrap_or(true);
    if target.exists() && !owned(&target) && !empty {
        return fail(format!(
            "{} exists and was not created by `ul skills`; nothing was changed",
            target.display()
        ));
    }
    if let Err(error) = write_skill(&target, config) {
        return fail(format!("Could not write {}: {error}", target.display()));
    }
    println!("Installed the unlaw skill: {}", target.display());
    let mut manifest = read_manifest().unwrap_or_default();
    let mut links = manifest
        .installs
        .iter()
        .find(|install| install.path == target)
        .map(|install| install.links.clone())
        .unwrap_or_default();
    let mut code = 0;
    if options.claude {
        match link_claude(&link, &target, &options.place) {
            Ok(()) => {
                println!("Linked for Claude Code: {}", link.display());
                if !links.contains(&link) {
                    links.push(link);
                }
            }
            Err(message) => {
                eprintln!("unlaw skills: {message}");
                code = 1;
            }
        }
    }
    manifest.installs.retain(|install| install.path != target);
    manifest.installs.push(Install {
        path: target,
        links,
    });
    manifest.fingerprint = fingerprint(&records(config, false));
    if let Err(error) = write_manifest(&manifest) {
        return fail(format!(
            "Could not save {}: {error}",
            manifest_path().display()
        ));
    }
    code
}

/// Delete only what `install` wrote; the folder stays if someone added files.
fn remove_skill(install: &Install) -> io::Result<bool> {
    for link in &install.links {
        if link_points_to(link, &install.path) {
            fs::remove_file(link)?;
        }
    }
    if !owned(&install.path) {
        return Ok(true);
    }
    for name in ["SKILL.md", MARKER] {
        let _ = fs::remove_file(install.path.join(name));
    }
    let reference = install.path.join("reference");
    if let Ok(entries) = fs::read_dir(&reference) {
        for entry in entries.flatten() {
            if entry
                .path()
                .extension()
                .is_some_and(|extension| extension == "md")
            {
                fs::remove_file(entry.path())?;
            }
        }
    }
    let _ = fs::remove_dir(&reference);
    Ok(fs::remove_dir(&install.path).is_ok())
}

/// Every skill folder `ul skills install` wrote (for `ul remove`).
pub fn installed() -> Vec<PathBuf> {
    read_manifest()
        .unwrap_or_default()
        .installs
        .into_iter()
        .map(|install| install.path)
        .collect()
}

/// Remove every install and the manifest (for `ul remove`).
pub fn remove_all() -> io::Result<()> {
    for install in read_manifest().unwrap_or_default().installs {
        remove_skill(&install)?;
    }
    write_manifest(&Manifest::default())
}

fn remove(args: &[String]) -> i32 {
    let options = match parse(args, true) {
        Ok(options) => options,
        Err(message) => return fail(message),
    };
    let mut manifest = read_manifest().unwrap_or_default();
    let (target, _) = locations(&options.place);
    let chosen: Vec<Install> = if options.all {
        manifest.installs.clone()
    } else {
        match manifest
            .installs
            .iter()
            .find(|install| install.path == target)
        {
            Some(install) => vec![install.clone()],
            None if owned(&target) => vec![Install {
                path: target.clone(),
                links: Vec::new(),
            }],
            None => return fail(format!("No skill installed at {}", target.display())),
        }
    };
    if chosen.is_empty() {
        println!("No skill installed.");
        return 0;
    }
    for install in &chosen {
        match remove_skill(install) {
            Ok(true) => println!("Removed {}", install.path.display()),
            Ok(false) => println!(
                "Removed the generated files; {} keeps files you added",
                install.path.display()
            ),
            Err(error) => {
                return fail(format!(
                    "Could not remove {}: {error}",
                    install.path.display()
                ))
            }
        }
    }
    manifest
        .installs
        .retain(|install| !chosen.contains(install));
    if let Err(error) = write_manifest(&manifest) {
        return fail(format!(
            "Could not save {}: {error}",
            manifest_path().display()
        ));
    }
    0
}

fn list(config: &Config) -> i32 {
    let installs = read_manifest()
        .map(|manifest| manifest.installs)
        .unwrap_or_default();
    if installs.is_empty() {
        println!("No skill installed. Run `ul skills install` (add --claude for Claude Code).");
        return 0;
    }
    let current = fingerprint(&records(config, false))
        == read_manifest().map(|m| m.fingerprint).unwrap_or_default();
    for install in installs {
        let state = if !owned(&install.path) {
            "missing"
        } else if current {
            "up to date"
        } else {
            "refreshes on the next run"
        };
        println!("{}  ({state})", install.path.display());
        for link in install.links {
            let ok = if link_points_to(&link, &install.path) {
                ""
            } else {
                " (broken)"
            };
            println!("  linked: {}{ok}", link.display());
        }
    }
    0
}

fn show(args: &[String], config: &Config) -> i32 {
    let files = render(config);
    let wanted = match args {
        [] => PathBuf::from("SKILL.md"),
        [name] => Path::new("reference").join(format!("{name}.md")),
        _ => return usage(),
    };
    match files.iter().find(|(path, _)| *path == wanted) {
        Some((_, text)) => {
            print!("{text}");
            0
        }
        None => fail(format!("Unknown command: {}", args[0])),
    }
}

/// Regenerate every installed skill whose snapshot no longer matches the
/// commands. Called on each run, so `ul update` and new commands need no step.
pub fn refresh_if_stale(config: &Config) {
    let Some(mut manifest) = read_manifest() else {
        return;
    };
    let current = fingerprint(&records(config, false));
    if manifest.fingerprint == current {
        return;
    }
    manifest.installs.retain(|install| owned(&install.path));
    for install in &manifest.installs {
        if let Err(error) = write_skill(&install.path, config) {
            eprintln!(
                "unlaw: Could not refresh the skill in {}: {error}",
                install.path.display()
            );
            return;
        }
    }
    manifest.fingerprint = current;
    if let Err(error) = write_manifest(&manifest) {
        eprintln!(
            "unlaw: Could not save {}: {error}",
            manifest_path().display()
        );
    }
}

fn fail(message: impl std::fmt::Display) -> i32 {
    eprintln!("unlaw skills: {message}");
    1
}

fn usage() -> i32 {
    eprintln!("{USAGE}");
    2
}

pub fn run(args: &[String]) -> i32 {
    if print_if_requested("skills", args) {
        return 0;
    }
    let config = match config::load() {
        Ok(config) => config,
        Err(error) => return fail(error),
    };
    match args.first().map(String::as_str) {
        Some("install") => install(&args[1..], &config),
        Some("remove") => remove(&args[1..]),
        Some("list") if args.len() == 1 => list(&config),
        None => list(&config),
        Some("show") => show(&args[1..], &config),
        _ => usage(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn words(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn options_parse_strictly() {
        assert!(matches!(
            parse(&words(&["--project", "--claude"]), false),
            Ok(Options {
                place: Place::Project,
                claude: true,
                ..
            })
        ));
        assert!(matches!(
            parse(&words(&["--path", "/tmp/x"]), false),
            Ok(Options {
                place: Place::Path(_),
                ..
            })
        ));
        assert!(parse(&words(&["--project", "--path", "/x"]), false).is_err());
        assert!(parse(&words(&["--path"]), false).is_err());
        assert!(
            parse(&words(&["--all"]), false).is_err(),
            "--all is only for remove"
        );
        assert!(parse(&words(&["--all", "--project"]), true).is_err());
        assert!(parse(&words(&["now"]), false).is_err());
    }

    #[test]
    fn every_seed_has_reference_help() {
        let record = Record {
            name: "todo".into(),
            source: "config",
            path: None,
            expansion: None,
            summary: None,
        };
        assert!(reference(&record).contains("ul todo"));
        assert!(reference(&record).contains("```text"));
    }

    #[test]
    fn aliases_never_expose_their_expansion() {
        let record = Record {
            name: "secret".into(),
            source: "alias",
            path: None,
            expansion: Some(vec![
                "tg".into(),
                "send".into(),
                "/Users/me/private.txt".into(),
            ]),
            summary: Some("alias -> tg send /Users/me/private.txt".into()),
        };
        assert!(!reference(&record).contains("private"));
        assert!(!skill_markdown(&[record]).contains("private"));
    }

    #[test]
    fn fingerprint_follows_the_command_set() {
        let record = |name: &str| Record {
            name: name.into(),
            source: "system",
            path: None,
            expansion: None,
            summary: None,
        };
        assert_eq!(fingerprint(&[record("a")]), fingerprint(&[record("a")]));
        assert_ne!(
            fingerprint(&[record("a")]),
            fingerprint(&[record("a"), record("b")])
        );
    }
}
