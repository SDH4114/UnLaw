//! `ul reinstall` and `ul remove`: reinstall Unlaw from scratch, uninstall it
//! completely, or delete single commands.

use std::env;
use std::fs;
use std::io::{self, BufRead, Write};
use std::path::Path;
use std::process::{Command, Stdio};

use crate::builtin;
use crate::config::{self, commands_dir, config_dir, config_file};
use crate::config_cmd::timestamp;
use crate::features;
use crate::help::{is_system, print_if_requested};
use crate::layout;
use crate::shell::{ZSH_BLOCK_END, ZSH_BLOCK_START};
use crate::skills;
use crate::update;
use crate::util::{home, is_executable, which};

/// What `cargo install` puts into `<root>/bin` for both packages.
const BINARIES: [&str; 5] = ["ul", "unlaw", "ula", "unlawagent", "ule"];
/// The launchd job of `ula setup` (agent.py `LABEL`).
const AGENT_LABEL: &str = "com.unlaw.agent";

/// `[y/N]` on stdin; anything but y/yes, or the end of input, is no.
fn confirm(question: &str) -> bool {
    print!("{question} [y/N] ");
    let _ = io::stdout().flush();
    let mut answer = String::new();
    if io::stdin().lock().read_line(&mut answer).unwrap_or(0) == 0 {
        println!();
        return false;
    }
    matches!(answer.trim().to_lowercase().as_str(), "y" | "yes" | "д" | "да")
}

fn remove_tree(path: &Path) -> io::Result<()> {
    let result = if path.is_symlink() || path.is_file() { fs::remove_file(path) } else { fs::remove_dir_all(path) };
    match result {
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        other => other,
    }
}

fn exists(path: &Path) -> bool {
    path.exists() || path.is_symlink()
}

fn home_relative(path: &Path) -> String {
    match path.strip_prefix(home()) {
        Ok(rest) if !rest.as_os_str().is_empty() => format!("~/{}", rest.display()),
        _ => path.display().to_string(),
    }
}

// --- ul reinstall -------------------------------------------------------------

/// `storage.root` as written in config.toml, even when the file is invalid.
fn configured_storage() -> Option<String> {
    let document = config::read_document().ok()?;
    document.get("storage")?.get("root")?.as_str().map(str::to_string)
}

/// Move config.toml and ule.toml into `backup`, write the defaults back
/// with the old `core.features` and `storage.root`, and take the default
/// commands out so the new ul seeds fresh copies.
fn reset_settings(backup: &Path) -> Result<Vec<&'static str>, String> {
    let fail = |error: io::Error| error.to_string();
    let selection = config::load().ok().map(|config| features::selected(&config));
    let storage = configured_storage();
    fs::create_dir_all(backup).map_err(fail)?;
    for file in [config_file(), config_dir().join("ule.toml")] {
        if file.is_file() {
            fs::rename(&file, backup.join(file.file_name().unwrap_or_default())).map_err(fail)?;
        }
    }
    config::reset().map_err(|error| error.0)?;
    if let Some(selection) = selection {
        features::save(&selection).map_err(|error| error.0)?;
    }
    if let Some(storage) = storage.filter(|storage| storage != "data") {
        config::set("storage.root", toml_edit::Item::Value(storage.into())).map_err(|error| error.0)?;
    }
    layout::reset_seeds(backup).map_err(fail)
}

pub fn reinstall(args: &[String]) -> i32 {
    if print_if_requested("reinstall", args) {
        return 0;
    }
    let yes = match args {
        [] => false,
        [flag] if flag == "--yes" || flag == "-y" => true,
        _ => {
            eprintln!("Usage: ul reinstall [--yes]");
            return 2;
        }
    };
    let root = update::install_root();
    let cache = update::build_cache();
    let own_cache = env::var_os("CARGO_TARGET_DIR").is_none();
    let storage = config::load().map(|config| config.storage_root()).unwrap_or_else(|_| config::configured_storage_root());
    println!("Reinstall Unlaw from scratch:");
    println!("  - build ul, ula and ule again from GitHub (main) into {}", home_relative(&root.join("bin")));
    if own_cache {
        println!("  - delete the build cache {} first", home_relative(&cache));
    }
    println!("  - reset config.toml and ule.toml to the defaults (core.features and storage.root stay)");
    println!("  - install the default commands again; edited copies are saved to the backup");
    println!("Kept: commands you wrote, templates, {} (downloads, captures, models, agent sessions), the Telegram token.", home_relative(&storage));
    if !yes && !confirm("Continue?") {
        println!("Cancelled; nothing changed.");
        return 1;
    }
    if update::cargo().is_some() && own_cache {
        if let Err(error) = remove_tree(&cache) {
            eprintln!("unlaw reinstall: Could not delete {}: {error}", cache.display());
            return 1;
        }
    }
    let code = update::install_latest();
    if code != 0 {
        eprintln!("unlaw reinstall: settings and commands were not reset.");
        return code;
    }
    let backup = config_dir().join("backups").join(format!("reinstall-{}", timestamp()));
    let moved = match reset_settings(&backup) {
        Ok(moved) => moved,
        Err(error) => {
            eprintln!("unlaw reinstall: Could not reset the settings: {error}");
            eprintln!("The old files are in {}.", backup.display());
            return 1;
        }
    };
    // The new ul seeds the default commands with its own sources.
    let installed = root.join("bin").join("ul");
    let ul = if is_executable(&installed) { installed } else { env::current_exe().unwrap_or(installed) };
    let seeded = Command::new(&ul).arg("init").stdout(Stdio::null()).status().is_ok_and(|status| status.success());
    if !seeded {
        eprintln!("unlaw reinstall: Could not set up the default commands; run: ul init");
    }
    let _ = fs::remove_dir(&backup);
    if backup.exists() {
        println!("Old settings: {}", backup.display());
    }
    if !moved.is_empty() {
        println!("Edited default commands saved there: {}", moved.join(", "));
    }
    println!("Unlaw was reinstalled from scratch.");
    if seeded {
        0
    } else {
        1
    }
}

// --- ul remove ----------------------------------------------------------------

/// The Unlaw block that `ul doctor --fix` adds to ~/.zshrc, cut out with the
/// blank line before it; `None` when there is none.
fn without_shell_block(text: &str) -> Option<String> {
    let start = text.find(ZSH_BLOCK_START)?;
    let end = text[start..].find(ZSH_BLOCK_END)? + start + ZSH_BLOCK_END.len();
    let before = &text[..start];
    let before = if before.ends_with("\n\n") { &before[..before.len() - 1] } else { before };
    let after = text[end..].strip_prefix('\n').unwrap_or(&text[end..]);
    Some(format!("{before}{after}"))
}

fn keychain_service() -> String {
    config::load().map(|config| config.string("telegram.keychain_service")).unwrap_or_default()
}

fn has_token(service: &str) -> bool {
    !service.is_empty()
        && Command::new("security")
            .args(["find-generic-password", "-a", "unlaw", "-s", service])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok_and(|status| status.success())
}

fn remove_everything(yes: bool) -> i32 {
    let root = update::install_root();
    let bin = root.join("bin");
    let binaries: Vec<&str> = BINARIES.iter().copied().filter(|name| exists(&bin.join(name))).collect();
    let configuration = config_dir();
    let storage = config::load().map(|config| config.storage_root()).unwrap_or_else(|_| config::configured_storage_root());
    let cache = home().join("Library").join("Caches").join("unlaw");
    let plist = home().join("Library").join("LaunchAgents").join(format!("{AGENT_LABEL}.plist"));
    let zshrc = home().join(".zshrc");
    let shell_block = fs::read_to_string(&zshrc).ok().and_then(|text| without_shell_block(&text));
    let skill_installs = skills::installed();
    let service = keychain_service();
    let token = has_token(&service);

    println!("This removes Unlaw completely:");
    if !binaries.is_empty() {
        println!("  - programs in {}: {}", home_relative(&bin), binaries.join(", "));
    }
    if exists(&configuration) {
        println!("  - {} with everything in it: settings, every command (also the ones you wrote),", home_relative(&configuration));
        println!("    templates and data: Telegram and YouTube downloads, captures, converted models, agent sessions");
    }
    if exists(&cache) {
        println!("  - the build cache {}", home_relative(&cache));
    }
    if exists(&plist) {
        println!("  - the agent's background job ({AGENT_LABEL})");
    }
    if shell_block.is_some() {
        println!("  - the shell integration block in ~/.zshrc");
    }
    for path in &skill_installs {
        println!("  - the agent skill {}", home_relative(path));
    }
    if token {
        println!("  - the Telegram bot token in the Keychain ({service})");
    }
    let outside = !storage.starts_with(&configuration) && storage.exists();
    print!("Kept: models in the Hugging Face cache, the PATH line in ~/.zshrc");
    if outside {
        print!(", {} (storage.root outside the config folder)", home_relative(&storage));
    }
    println!(".");
    println!("This cannot be undone.");
    if !yes && !confirm("Remove Unlaw?") {
        println!("Cancelled; nothing was removed.");
        return 1;
    }

    let mut code = 0;
    let mut report = |what: String, result: io::Result<()>| match result {
        Ok(()) => println!("Removed {what}"),
        Err(error) => {
            eprintln!("unlaw remove: Could not remove {what}: {error}");
            code = 1;
        }
    };
    if exists(&plist) {
        let domain = format!("gui/{}/{AGENT_LABEL}", unsafe { libc::getuid() });
        let _ = Command::new("launchctl").args(["bootout", &domain]).stdout(Stdio::null()).stderr(Stdio::null()).status();
        report("the agent's background job".into(), remove_tree(&plist));
    }
    if !skill_installs.is_empty() {
        report("the agent skill".into(), skills::remove_all());
    }
    if let Some(text) = shell_block {
        // fs::write follows a symlinked ~/.zshrc (dotfile managers) instead of replacing it.
        report("the shell integration from ~/.zshrc".into(), fs::write(&zshrc, text));
    }
    if token {
        let deleted = Command::new("security")
            .args(["delete-generic-password", "-a", "unlaw", "-s", &service])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .and_then(|status| if status.success() { Ok(()) } else { Err(io::Error::other(format!("security exited with {status}"))) });
        report("the Telegram token from the Keychain".into(), deleted);
    }
    if exists(&configuration) {
        report(home_relative(&configuration), remove_tree(&configuration));
    }
    if exists(&cache) {
        report(home_relative(&cache), remove_tree(&cache));
    }
    if !binaries.is_empty() {
        // cargo also forgets the packages; whatever it leaves is deleted by hand.
        if let Some(cargo) = update::cargo().or_else(|| which("cargo")) {
            for package in ["unlaw", "ule"] {
                let _ = Command::new(&cargo)
                    .args(["uninstall", "--quiet", "--root"])
                    .arg(&root)
                    .arg(package)
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .status();
            }
        }
        let result = binaries.iter().try_for_each(|name| remove_tree(&bin.join(name)));
        report(format!("{} from {}", binaries.join(", "), home_relative(&bin)), result);
    }
    if code == 0 {
        println!("Unlaw is removed. Open a new terminal so the shell forgets it.");
    }
    code
}

/// Why `name` cannot be removed with `ul remove <name>`, if it cannot.
fn not_removable(name: &str) -> Option<String> {
    if name.is_empty() || name.starts_with('-') || name.starts_with('.') || name.contains('/') {
        return Some(format!("Invalid command name: {name:?}"));
    }
    if is_system(name) || name == "help" {
        return Some(format!("{name} is a system command of Unlaw; remove the whole program with: ul remove"));
    }
    if exists(&commands_dir().join(name)) {
        return None;
    }
    Some(match (builtin::is_builtin(name), features::find(name)) {
        (true, Some(_)) => format!("{name} is built into ul; remove it with: ul features remove {name}"),
        (true, None) => format!("{name} is part of the Unlaw core and cannot be removed"),
        _ => format!("No command named {name} in {}", commands_dir().display()),
    })
}

fn remove_commands(names: &[&str], yes: bool) -> i32 {
    let mut unique: Vec<&str> = Vec::new();
    for name in names {
        if !unique.contains(name) {
            unique.push(name);
        }
    }
    let errors: Vec<String> = unique.iter().filter_map(|name| not_removable(name)).collect();
    if !errors.is_empty() {
        for error in errors {
            eprintln!("unlaw remove: {error}");
        }
        return 2;
    }
    for name in &unique {
        let directory = commands_dir().join(name);
        let kind = if directory.is_symlink() { "the link" } else { "the folder" };
        println!("Delete {kind} {} with all its files", home_relative(&directory));
    }
    if !yes && !confirm(if unique.len() == 1 { "Delete this command?" } else { "Delete these commands?" }) {
        println!("Cancelled; nothing was removed.");
        return 1;
    }
    let mut code = 0;
    for name in &unique {
        let directory = commands_dir().join(name);
        match remove_tree(&directory) {
            Ok(()) => println!("Removed {name}"),
            Err(error) => {
                eprintln!("unlaw remove: Could not remove {}: {error}", directory.display());
                code = 1;
            }
        }
    }
    // A default command that stays in core.features would be seeded again on the next run.
    let seeds: Vec<&str> = unique.iter().copied().filter(|name| features::find(name).is_some_and(|feature| feature.seed)).collect();
    if !seeds.is_empty() {
        let result = config::load().map_err(|error| error.0).and_then(|config| {
            let current = features::selected(&config);
            if seeds.iter().all(|name| !current.contains(name)) {
                return Ok(());
            }
            features::save(&features::without(&current, &seeds)).map_err(|error| error.0)
        });
        match result {
            Ok(()) => println!("Bring a default command back with: ul features add {}", seeds.join(" ")),
            Err(error) => {
                eprintln!("unlaw remove: Could not update core.features ({error}); the next run seeds it again.");
                eprintln!("Fix config.toml, then run: ul features remove {}", seeds.join(" "));
                code = 1;
            }
        }
    }
    code
}

pub fn run(args: &[String]) -> i32 {
    if print_if_requested("remove", args) {
        return 0;
    }
    let yes = args.iter().any(|arg| arg == "--yes" || arg == "-y");
    let names: Vec<&str> = args.iter().map(String::as_str).filter(|arg| *arg != "--yes" && *arg != "-y").collect();
    if names.is_empty() {
        remove_everything(yes)
    } else {
        remove_commands(&names, yes)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_shell_block_is_cut_with_its_blank_line() {
        let block = format!("{ZSH_BLOCK_START}\neval \"$(command ul _shell-init zsh)\"\n{ZSH_BLOCK_END}");
        assert_eq!(without_shell_block(&format!("export A=1\n\n{block}\nalias b=c\n")).as_deref(), Some("export A=1\nalias b=c\n"));
        assert_eq!(without_shell_block(&format!("{block}\n")).as_deref(), Some(""));
        assert_eq!(without_shell_block("export A=1\n"), None);
        assert_eq!(without_shell_block(&format!("x\n{ZSH_BLOCK_START}\nno end\n")), None);
    }
}
