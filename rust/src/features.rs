//! `ul features`: the optional parts of Unlaw. The core (system commands,
//! zip, app, browser and the ule editor) is always installed; everything here
//! is chosen at install time and stored in `core.features` (`["all"]` by
//! default, which also takes in features added by later releases).
//!
//! Seeded commands are added or removed in the config folder; `game`, `lm` and
//! the `ula` shortcuts of `agent` are cargo features, so changing them
//! rebuilds ul (`ul update`). The list lives in src/unlawful/features.py;
//! install.sh carries a copy that tests keep identical.

use std::io;
use std::sync::LazyLock;

use crate::assets::{FEATURE_CORE, FEATURE_LIST};
use crate::checklist::{self, Entry};
use crate::config::{self, Config, Value};
use crate::help::print_if_requested;
use crate::layout;
use crate::update;

pub struct Feature {
    pub name: &'static str,
    pub group: &'static str,
    pub summary: &'static str,
    /// Compiled into ul as a cargo feature of the same name.
    pub cargo: bool,
    /// Seeded into commands/<name>/.
    pub seed: bool,
    pub requires: &'static [&'static str],
}

pub const CORE: &str = FEATURE_CORE;

/// From src/unlawful/features.py, embedded by rust/gen_assets.py.
pub static FEATURES: LazyLock<Vec<Feature>> = LazyLock::new(|| {
    FEATURE_LIST
        .iter()
        .map(|&(name, group, summary, cargo, seed, requires)| Feature { name, group, summary, cargo, seed, requires })
        .collect()
});

pub fn find(name: &str) -> Option<&'static Feature> {
    FEATURES.iter().find(|feature| feature.name == name)
}

/// Whether this ul was built with a feature; seeded ones are always available.
fn in_binary(name: &str) -> bool {
    let built = [("game", cfg!(feature = "game")), ("lm", cfg!(feature = "lm")), ("agent", cfg!(feature = "agent"))];
    built.iter().all(|(feature, present)| *present || *feature != name)
}

/// The cargo features this ul was built with.
pub fn compiled() -> Vec<&'static str> {
    FEATURES.iter().filter(|feature| feature.cargo && in_binary(feature.name)).map(|feature| feature.name).collect()
}

/// The cargo features a selection needs.
pub fn cargo_features(selection: &[&str]) -> Vec<&'static str> {
    FEATURES.iter().filter(|feature| feature.cargo && selection.contains(&feature.name)).map(|feature| feature.name).collect()
}

pub fn needs_rebuild(selection: &[&str]) -> bool {
    cargo_features(selection) != compiled()
}

/// Expand `all`, add what the chosen features need; `FEATURES` order.
pub fn resolve<S: AsRef<str>>(names: &[S]) -> Vec<&'static str> {
    let all = names.iter().any(|name| name.as_ref() == "all");
    let mut chosen: Vec<&'static str> =
        FEATURES.iter().filter(|feature| all || names.iter().any(|name| name.as_ref() == feature.name)).map(|feature| feature.name).collect();
    let mut index = 0;
    while index < chosen.len() {
        for required in find(chosen[index]).map(|feature| feature.requires).unwrap_or(&[]) {
            if !chosen.contains(required) {
                chosen.push(required);
            }
        }
        index += 1;
    }
    FEATURES.iter().map(|feature| feature.name).filter(|name| chosen.contains(name)).collect()
}

fn configured(config: &Config) -> Vec<String> {
    match config.get("core.features") {
        Some(Value::Array(items)) => items.iter().filter_map(|item| if let Value::Str(text) = item { Some(text.clone()) } else { None }).collect(),
        _ => vec!["all".into()],
    }
}

pub fn selected(config: &Config) -> Vec<&'static str> {
    resolve(&configured(config))
}

/// Errors for `core.features`; same rules as `unlawful.config._feature_errors`.
pub fn config_errors(value: Option<&Value>) -> Vec<String> {
    let Some(Value::Array(items)) = value else {
        return vec!["Invalid core.features: expected an array of feature names".into()];
    };
    let mut errors = Vec::new();
    for item in items {
        match item {
            Value::Str(name) if name == "all" || find(name).is_some() => {}
            Value::Str(name) => errors.push(format!("Unknown feature in core.features: {name}")),
            _ => return vec!["Invalid core.features: expected an array of feature names".into()],
        }
    }
    errors
}

/// What `core.features` stores: `["all"]` when everything is chosen, so
/// features of later releases come along.
fn stored(selection: &[&str]) -> Vec<&'static str> {
    if selection.len() == FEATURES.len() {
        vec!["all"]
    } else {
        FEATURES.iter().map(|feature| feature.name).filter(|name| selection.contains(name)).collect()
    }
}

/// Store a selection in `core.features` without touching commands or ul.
pub fn save(selection: &[&str]) -> config::Result<()> {
    let array: toml_edit::Array = stored(selection).into_iter().collect();
    config::set("core.features", toml_edit::Item::Value(toml_edit::Value::Array(array)))
}

fn print_list(selection: &[&str]) {
    println!("Core (always installed): {CORE}");
    let width = FEATURES.iter().map(|feature| feature.name.len()).max().unwrap_or(0);
    let mut group = "";
    for feature in FEATURES.iter() {
        if feature.group != group {
            group = feature.group;
            println!("{group}");
        }
        let mark = if selection.contains(&feature.name) { "x" } else { " " };
        let note = match (selection.contains(&feature.name), in_binary(feature.name)) {
            (true, false) => "  (not built into this ul yet: run `ul update`)",
            (false, true) if feature.cargo => "  (still built in until `ul update`)",
            _ => "",
        };
        println!("  [{mark}] {:<width$}  {}{note}", feature.name, feature.summary);
    }
}

fn unknown_names<'a>(names: &[&'a str], allow_all: bool) -> Vec<&'a str> {
    names.iter().copied().filter(|name| find(name).is_none() && !(allow_all && ["all", "none"].contains(name))).collect()
}

/// The selection without `names` and everything that needs them.
fn without(selection: &[&'static str], names: &[&str]) -> Vec<&'static str> {
    let mut removed: Vec<&str> = names.to_vec();
    loop {
        let more: Vec<&str> = selection
            .iter()
            .copied()
            .filter(|name| !removed.contains(name))
            .filter(|name| find(name).is_some_and(|feature| feature.requires.iter().any(|required| removed.contains(required))))
            .collect();
        if more.is_empty() {
            break;
        }
        removed.extend(more);
    }
    selection.iter().copied().filter(|name| !removed.contains(name)).collect()
}

fn usage() -> i32 {
    eprintln!("Usage: ul features [list|add <name>...|remove <name>...|set <name>...|all|none|choose] [--no-build]");
    2
}

pub fn run(args: &[String]) -> i32 {
    if print_if_requested("features", args) {
        return 0;
    }
    let no_build = args.iter().any(|arg| arg == "--no-build");
    let words: Vec<&str> = args.iter().map(String::as_str).filter(|arg| *arg != "--no-build").collect();
    let config = match config::load() {
        Ok(config) => config,
        Err(error) => {
            eprintln!("unlaw features: {error}");
            return 2;
        }
    };
    let current = selected(&config);
    let next = match words.as_slice() {
        [] | ["list"] => {
            print_list(&current);
            return 0;
        }
        [action @ ("add" | "remove" | "set"), names @ ..] if !names.is_empty() => {
            let unknown = unknown_names(names, *action == "set");
            if !unknown.is_empty() {
                eprintln!("unlaw features: unknown feature: {} (see `ul features`)", unknown.join(", "));
                return 2;
            }
            match *action {
                "add" => resolve(&current.iter().copied().chain(names.iter().copied()).collect::<Vec<_>>()),
                "remove" => without(&current, names),
                _ => resolve(names),
            }
        }
        ["all"] => resolve(&["all"]),
        ["none"] => Vec::new(),
        ["choose"] => match choose(&current) {
            Ok(Some(next)) => next,
            Ok(None) => {
                println!("Nothing changed.");
                return 0;
            }
            Err(error) => {
                eprintln!("unlaw features: {error}");
                return 1;
            }
        },
        _ => return usage(),
    };
    apply(&current, &next, no_build)
}

fn names(list: &[&str]) -> String {
    if list.is_empty() {
        "none".into()
    } else {
        list.join(", ")
    }
}

/// Save a selection, sync the command folders and rebuild ul when needed.
pub fn apply(current: &[&str], next: &[&'static str], no_build: bool) -> i32 {
    if let Err(error) = save(next) {
        eprintln!("unlaw features: {error}");
        return 2;
    }
    let added: Vec<&str> = next.iter().copied().filter(|name| !current.contains(name)).collect();
    let removed: Vec<&str> = current.iter().copied().filter(|name| !next.contains(name)).collect();
    let kept = match layout::sync_features(next) {
        Ok(kept) => kept,
        Err(error) => {
            eprintln!("unlaw features: could not update commands: {error}");
            return 1;
        }
    };
    if added.is_empty() && removed.is_empty() {
        println!("Features unchanged: {}", names(next));
    } else {
        println!("Added: {}. Removed: {}.", names(&added), names(&removed));
    }
    for name in kept {
        println!("Kept commands/{name}: you edited it. Delete the folder to remove it.");
    }
    if !needs_rebuild(next) {
        return 0;
    }
    if no_build {
        let built = cargo_features(next);
        println!("Run `ul update` to rebuild ul with: {}.", if built.is_empty() { "the core only".to_string() } else { built.join(", ") });
        return 0;
    }
    let built = cargo_features(next);
    println!("Rebuilding ul with: {}.", if built.is_empty() { "the core only".to_string() } else { built.join(", ") });
    let code = update::rebuild();
    if code != 0 {
        eprintln!("unlaw features: the choice is saved; `ul update` builds it from the newest commit.");
    }
    code
}

/// Interactive checklist; `None` when cancelled.
fn choose(current: &[&'static str]) -> io::Result<Option<Vec<&'static str>>> {
    if !checklist::interactive() {
        return Err(io::Error::other("choose needs a terminal; use add, remove or set"));
    }
    let mut entries: Vec<Entry> = FEATURES
        .iter()
        .map(|feature| Entry {
            group: feature.group.into(),
            name: feature.name.into(),
            summary: feature.summary.into(),
            on: current.contains(&feature.name),
            locked: None,
        })
        .collect();
    if !checklist::pick("Unlaw features", &[format!("Core (always): {CORE}")], &mut entries, &toggle)? {
        return Ok(None);
    }
    let names: Vec<&str> = entries.iter().filter(|entry| entry.on).map(|entry| entry.name.as_str()).collect();
    Ok(Some(resolve(&names)))
}

/// Toggle one feature and keep requirements consistent both ways.
fn toggle(entries: &mut [Entry], index: usize) {
    checklist::flip(entries, index);
    let (on, name) = (entries[index].on, FEATURES[index].name);
    for (other, feature) in FEATURES.iter().enumerate() {
        if on && FEATURES[index].requires.contains(&feature.name) {
            entries[other].on = true;
        }
        if !on && feature.requires.contains(&name) {
            entries[other].on = false;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::assets::SEEDS;

    #[test]
    fn every_seed_is_a_feature_and_names_are_unique() {
        let seeds: Vec<&str> = FEATURES.iter().filter(|feature| feature.seed).map(|feature| feature.name).collect();
        let mut shipped: Vec<&str> = SEEDS.iter().map(|(name, ..)| *name).collect();
        let mut sorted = seeds.clone();
        sorted.sort();
        shipped.sort();
        assert_eq!(sorted, shipped);
        let mut names: Vec<&str> = FEATURES.iter().map(|feature| feature.name).collect();
        names.sort();
        names.dedup();
        assert_eq!(names.len(), FEATURES.len());
        for feature in FEATURES.iter() {
            assert!(feature.requires.iter().all(|required| find(required).is_some()), "{}", feature.name);
            assert!(!crate::help::is_system(feature.name), "{} clashes with a system command", feature.name);
        }
    }

    #[test]
    fn resolve_expands_all_and_requirements() {
        assert_eq!(resolve(&["all"]).len(), FEATURES.len());
        assert_eq!(resolve(&["agent", "yt"]), vec!["lm", "agent", "yt"]);
        assert_eq!(resolve::<&str>(&[]), Vec::<&str>::new());
        assert_eq!(resolve(&["none"]), Vec::<&str>::new());
        assert_eq!(unknown_names(&["none", "all", "yt", "x"], true), vec!["x"]);
        assert_eq!(unknown_names(&["none"], false), vec!["none"]);
        assert_eq!(cargo_features(&resolve(&["agent", "yt"])), vec!["lm", "agent"]);
    }

    #[test]
    fn removing_a_requirement_removes_what_needs_it() {
        let current = resolve(&["agent", "yt"]);
        assert_eq!(without(&current, &["lm"]), vec!["yt"]);
        assert_eq!(without(&current, &["agent"]), vec!["lm", "yt"]);
    }

    #[test]
    fn everything_is_stored_as_all() {
        assert_eq!(stored(&resolve(&["all"])), vec!["all"]);
        assert_eq!(stored(&["yt", "lm"]), vec!["lm", "yt"]);
    }

    #[test]
    fn config_errors_name_unknown_features() {
        let names = |items: &[&str]| Value::Array(items.iter().map(|item| Value::Str(item.to_string())).collect());
        assert!(config_errors(Some(&names(&["all", "yt", "game"]))).is_empty());
        assert_eq!(config_errors(Some(&names(&["zip"]))), vec!["Unknown feature in core.features: zip"]);
        assert_eq!(config_errors(Some(&Value::Str("all".into()))), vec!["Invalid core.features: expected an array of feature names"]);
        assert_eq!(config_errors(None), vec!["Invalid core.features: expected an array of feature names"]);
    }

    #[test]
    fn toggling_keeps_requirements() {
        let mut entries: Vec<Entry> = FEATURES
            .iter()
            .map(|feature| Entry { group: String::new(), name: feature.name.into(), summary: String::new(), on: false, locked: None })
            .collect();
        let agent = FEATURES.iter().position(|feature| feature.name == "agent").unwrap();
        let lm = FEATURES.iter().position(|feature| feature.name == "lm").unwrap();
        toggle(&mut entries, agent);
        assert!(entries[agent].on && entries[lm].on);
        toggle(&mut entries, lm);
        assert!(!entries[agent].on && !entries[lm].on);
    }

    #[test]
    fn this_build_reports_its_cargo_features() {
        let all = resolve(&["all"]);
        assert_eq!(needs_rebuild(&all), !(cfg!(feature = "game") && cfg!(feature = "lm") && cfg!(feature = "agent")));
    }
}
