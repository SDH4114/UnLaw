//! `ul commands search` and `ul commands get`: the command catalog on GitHub
//! (`catalog/` in the repository, written by `rust/gen_assets.py --catalog`).
//! Downloads go to `commands/<name>/main.py` and never replace an existing
//! command folder. `UNLAW_CATALOG_URL` points at another catalog (tests use a
//! file:// URL).

use std::env;
use std::fs;
use std::process::Command;

use serde_json::Value as Json;
use sha2::{Digest, Sha256};

use crate::checklist::{self, Entry};
use crate::config::{self, commands_dir};
use crate::features;
use crate::update;
use crate::util::create_new_atomic;
use crate::workspace;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Item {
    pub name: String,
    pub summary: String,
    pub sha256: String,
}

fn base_url() -> Result<String, String> {
    let base = match env::var("UNLAW_CATALOG_URL").ok().filter(|url| !url.is_empty()) {
        Some(url) => url,
        None => update::raw_url(&update::repository(), "main", "catalog/")
            .ok_or("the catalog needs a https://github.com repository (or UNLAW_CATALOG_URL)")?,
    };
    Ok(if base.ends_with('/') { base } else { format!("{base}/") })
}

fn fetch(url: &str) -> Result<Vec<u8>, String> {
    let output = Command::new("curl")
        .args(["-fsSL", "--max-time", "30", url])
        .output()
        .map_err(|error| format!("could not run curl: {error}"))?;
    if !output.status.success() {
        return Err(format!("could not fetch {url}: {}", String::from_utf8_lossy(&output.stderr).trim()));
    }
    Ok(output.stdout)
}

/// Commands listed in index.json; names that could not be command folders,
/// or that would hide a system or built-in command, are dropped.
pub fn parse_index(text: &str) -> Result<Vec<Item>, String> {
    let index: Json = serde_json::from_str(text).map_err(|error| format!("the catalog index is not valid JSON: {error}"))?;
    let commands = index.get("commands").and_then(Json::as_array).ok_or("the catalog index has no commands")?;
    let mut items: Vec<Item> = commands
        .iter()
        .filter_map(|entry| {
            let field = |key: &str| entry.get(key).and_then(Json::as_str).map(str::to_string);
            let item = Item { name: field("name")?, summary: field("summary").unwrap_or_default(), sha256: field("sha256")? };
            let reserved = crate::help::is_system(&item.name) || crate::builtin::is_builtin(&item.name);
            let hex = item.sha256.len() == 64 && item.sha256.chars().all(|c| c.is_ascii_hexdigit());
            (workspace::valid_name(&item.name) && !reserved && hex).then_some(item)
        })
        .collect();
    items.sort_by(|a, b| a.name.cmp(&b.name));
    items.dedup_by(|a, b| a.name == b.name);
    Ok(items)
}

fn load() -> Result<(String, Vec<Item>), String> {
    let base = base_url()?;
    let index = fetch(&format!("{base}index.json"))?;
    Ok((base.clone(), parse_index(&String::from_utf8_lossy(&index))?))
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes).iter().map(|byte| format!("{byte:02x}")).collect()
}

#[derive(Debug, PartialEq, Eq)]
enum Status {
    Available,
    /// The folder exists with the same main.py as the catalog.
    Current,
    /// The folder exists but differs (edited, older or newer); never replaced.
    Different,
}

fn status(item: &Item) -> Status {
    let directory = commands_dir().join(&item.name);
    if !directory.is_symlink() && !directory.exists() {
        return Status::Available;
    }
    match fs::read(directory.join("main.py")) {
        Ok(bytes) if sha256_hex(&bytes) == item.sha256 => Status::Current,
        _ => Status::Different,
    }
}

fn group(name: &str) -> &'static str {
    features::find(name).map(|feature| feature.group).unwrap_or("Other")
}

fn print_list(items: &[Item]) {
    let width = items.iter().map(|item| item.name.len()).max().unwrap_or(0);
    for item in items {
        let mark = match status(item) {
            Status::Available => "          ",
            Status::Current => "installed ",
            Status::Different => "installed*",
        };
        println!("  {mark} {:<width$}  {}", item.name, item.summary);
    }
    if items.iter().any(|item| status(item) == Status::Different) {
        println!("* your copy differs from GitHub; it is never replaced (delete the folder to download it again)");
    }
}

fn matches(item: &Item, words: &[&str]) -> bool {
    let text = format!("{} {}", item.name, item.summary).to_lowercase();
    words.iter().all(|word| text.contains(&word.to_lowercase()))
}

pub fn search(args: &[String]) -> i32 {
    if crate::help::print_if_requested("commands", args) {
        return 0;
    }
    let list_only = args.iter().any(|arg| arg == "--list");
    let words: Vec<&str> = args.iter().map(String::as_str).filter(|arg| *arg != "--list").collect();
    if let Some(flag) = words.iter().find(|word| word.starts_with('-')) {
        eprintln!("unlaw commands: unknown option {flag}");
        eprintln!("Usage: ul commands search [words...] [--list]");
        return 2;
    }
    let (_, items) = match load() {
        Ok(found) => found,
        Err(error) => {
            eprintln!("unlaw commands: {error}");
            return 1;
        }
    };
    let mut items: Vec<Item> = items.into_iter().filter(|item| matches(item, &words)).collect();
    if items.is_empty() {
        println!("No command in the catalog matches: {}", words.join(" "));
        return 0;
    }
    if list_only || !checklist::interactive() {
        print_list(&items);
        println!("Download: ul commands get <name>...");
        return 0;
    }
    items.sort_by_key(|item| (features::FEATURES.iter().position(|feature| feature.name == item.name).unwrap_or(usize::MAX), item.name.clone()));
    let mut entries: Vec<Entry> = items
        .iter()
        .map(|item| Entry {
            group: group(&item.name).into(),
            name: item.name.clone(),
            summary: item.summary.clone(),
            on: false,
            locked: match status(item) {
                Status::Available => None,
                Status::Current => Some("[•]"),
                Status::Different => Some("[*]"),
            },
        })
        .collect();
    let header = ["[•] installed · [*] installed, differs from GitHub (never replaced)".to_string()];
    match checklist::pick("Commands on GitHub: Space picks, Enter downloads", &header, &mut entries, &checklist::flip) {
        Ok(true) => {
            let chosen: Vec<String> = entries.iter().filter(|entry| entry.on).map(|entry| entry.name.clone()).collect();
            if chosen.is_empty() {
                println!("Nothing chosen.");
                return 0;
            }
            get(&chosen)
        }
        Ok(false) => {
            println!("Nothing downloaded.");
            0
        }
        Err(error) => {
            eprintln!("unlaw commands: {error}");
            1
        }
    }
}

/// Download commands that are not installed yet; existing folders stay.
pub fn get(names: &[String]) -> i32 {
    if crate::help::print_if_requested("commands", names) {
        return 0;
    }
    if names.is_empty() {
        eprintln!("Usage: ul commands get <name>...");
        return 2;
    }
    let (base, items) = match load() {
        Ok(found) => found,
        Err(error) => {
            eprintln!("unlaw commands: {error}");
            return 1;
        }
    };
    let mut code = 0;
    let mut downloaded: Vec<&str> = Vec::new();
    for name in names {
        let Some(item) = items.iter().find(|item| &item.name == name) else {
            match features::find(name) {
                Some(feature) if feature.cargo && !feature.seed => {
                    eprintln!("{name} is built into ul, not downloaded: ul features add {name}");
                }
                _ => eprintln!("{name}: not in the catalog (see ul commands search)"),
            }
            code = 2;
            continue;
        };
        if status(item) != Status::Available {
            println!("{name}: commands/{name} already exists; not overwritten");
            continue;
        }
        let bytes = match fetch(&format!("{base}{name}/main.py")) {
            Ok(bytes) => bytes,
            Err(error) => {
                eprintln!("{name}: {error}");
                code = code.max(1);
                continue;
            }
        };
        if sha256_hex(&bytes) != item.sha256 {
            eprintln!("{name}: the download does not match the catalog checksum; nothing written");
            code = code.max(1);
            continue;
        }
        let Ok(text) = String::from_utf8(bytes) else {
            eprintln!("{name}: the download is not UTF-8 text; nothing written");
            code = code.max(1);
            continue;
        };
        let directory = commands_dir().join(name);
        // Reserve the folder after downloading: a concurrent installer or user
        // may have created it since the initial status check.
        if let Err(error) = fs::create_dir(&directory) {
            eprintln!("{name}: could not create command folder (not overwritten): {error}");
            code = code.max(1);
            continue;
        }
        if let Err(error) = create_new_atomic(&directory.join("main.py"), &text, ".download.") {
            eprintln!("{name}: could not write it: {error}");
            code = code.max(1);
            continue;
        }
        println!("Downloaded {name} into commands/{name}/main.py");
        downloaded.push(name);
    }
    // A downloaded optional feature becomes part of the selection, or the next
    // run would remove it again as an unchosen seed.
    if downloaded.is_empty() {
        return code;
    }
    match config::load() {
        Ok(config) => {
            let current = features::selected(&config);
            let wanted: Vec<&str> =
                current.iter().copied().chain(downloaded.iter().copied().filter(|name| features::find(name).is_some())).collect();
            let next = features::resolve(&wanted);
            if next != current {
                if let Err(error) = features::save(&next) {
                    eprintln!("unlaw commands: could not add the downloaded features to core.features: {error}");
                    code = code.max(1);
                } else {
                    let built = features::compiled();
                    let missing: Vec<&str> = features::cargo_features(&next).into_iter().filter(|name| !built.contains(name)).collect();
                    if !missing.is_empty() {
                        println!("Run `ul update` to build what they need into ul: {}.", missing.join(", "));
                    }
                }
            }
        }
        Err(error) => {
            eprintln!("unlaw commands: {error}; add the downloaded features with `ul features add` once it is fixed");
            code = code.max(1);
        }
    }
    code
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn index_entries_are_validated() {
        let sha = "a".repeat(64);
        let text = format!(
            r#"{{"format": 1, "commands": [
                {{"name": "yt", "summary": "YouTube", "sha256": "{sha}"}},
                {{"name": "../evil", "summary": "x", "sha256": "{sha}"}},
                {{"name": "config", "summary": "system", "sha256": "{sha}"}},
                {{"name": "zip", "summary": "builtin", "sha256": "{sha}"}},
                {{"name": "bad", "summary": "x", "sha256": "123"}},
                {{"name": "git", "sha256": "{sha}"}},
                {{"name": "yt", "summary": "duplicate", "sha256": "{sha}"}}
            ]}}"#
        );
        let names: Vec<String> = parse_index(&text).unwrap().into_iter().map(|item| item.name).collect();
        assert_eq!(names, ["git", "yt"]);
        assert!(parse_index("[]").is_err());
        assert!(parse_index("not json").is_err());
    }

    #[test]
    fn search_words_match_name_and_summary() {
        let item = Item { name: "yt".into(), summary: "YouTube downloads".into(), sha256: String::new() };
        assert!(matches(&item, &[]));
        assert!(matches(&item, &["youtube"]));
        assert!(matches(&item, &["yt", "DOWN"]));
        assert!(!matches(&item, &["spotify"]));
    }
}
