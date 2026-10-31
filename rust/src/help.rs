//! Help for the dispatcher and system commands. Seeded commands keep their
//! own help in `src/unlawful/command_help.py`.

pub const HELP: &str = "Usage: ul [global-options] <command> [arguments]

Global options:
  --dry-run     Show the resolved command without running it
  --verbose     Show command source, invocation, and timing
  --no-color    Disable colored output
  --version     Show the installed version

Run `ul commands` to list available commands.
Run `ul <command> --help` or `ul help <command>` for command usage.
Run `ul create command <name>` to create one.
Run `ul create template [name]` to save the current project.
Run `ul venv` to create and activate .venv in the current Zsh.
Run `ul config show` to inspect configuration.
";

pub const SYSTEM_HELP: &[(&str, &str)] = &[
    (
        "commands",
        "List available system commands, installed commands and aliases.
Usage:
  ul commands [--verbose|--describe|--json]
  ul commands search [words...] [--list]   Browse the catalog on GitHub
  ul commands get <name>...                Download commands from the catalog
Options: --verbose includes source/path; --describe adds one-line descriptions
read from help.txt, the main.py docstring or a script's first comment (the
command is not run); --json prints structured records.
search lists every command of the catalog (catalog/ on GitHub, branch main)
with what is installed; on a terminal it opens a checklist (Space picks, Enter
downloads), --list only prints. Words filter names and descriptions.
get downloads into commands/<name>/main.py after checking its sha256. An
existing commands/<name> folder is never overwritten (delete it to download
again). A downloaded optional feature is added to core.features.
Needs curl; UNLAW_CATALOG_URL points at another catalog.
Examples:
  ul commands --describe
  ul commands search youtube
  ul commands get yt music
",
    ),
    (
        "completion",
        "Print Zsh completion code for ul and unlaw.
Usage: ul completion zsh
Completes commands with their descriptions, then subcommands and files.
Example: eval \"$(ul completion zsh)\"
",
    ),
    (
        "config",
        "Inspect or edit the Unlaw TOML configuration.
Usage:
  ul config path|show|edit|check     Print path/content, edit, or validate
  ul config get <key>               Read a dotted configuration key
  ul config set <key> <value>       Set and validate a value atomically
  ul config reset --yes             Reset defaults, preserving a backup
Values are TOML (12, true, [\"git\"]); bare text is saved as a string.
Comments and unknown keys in config.toml are preserved.
Example: ul config set storage.root ~/Downloads/unlaw
",
    ),
    (
        "create",
        "Create an editable command or save the current project as a template.
Usage:
  ul create command <name>              Create commands/<name>/main.py
  ul create command <name> --lang rust  Create a Cargo project in commands/<name>
  ul create template [name]             Prompt for project name, app and AI preference
Existing commands/templates are not overwritten. Templates come from
templates/commands/main.py and templates/commands/rust/ when present
({{command_name}} is replaced). Rust commands need cargo and are rebuilt
automatically when their sources change.
A command folder may instead contain main.sh, main.js or an executable main.
Commands receive UNLAW_COMMAND, UNLAW_COMMAND_DIR, UNLAW_CONFIG_DIR and UNLAW_STORAGE.
Examples:
  ul create command hello
  ul create command fast --lang rust
",
    ),
    (
        "doctor",
        "Check Unlaw configuration, tools and shell integration.
Usage: ul doctor [--verbose|--json|--fix]
Options: --verbose adds details; --json prints a report; --fix repairs supported issues.
Example: ul doctor --verbose
",
    ),
    (
        "edit",
        "Open files in the editor: ule (Unlaw's editor), or core.editor.
Usage: ul edit [file[:line[:col]]]...
Editor: core.editor (default \"auto\": ule when installed, then $VISUAL,
$EDITOR, then `open -t`). Set it to \"nvim\", \"zed --wait\" or \"ule\".
ul config edit uses the same editor and checks config.toml afterwards.
Examples:
  ul edit src/main.rs:42
  ul config set core.editor nvim
",
    ),
    (
        "features",
        "Choose the optional parts of Unlaw: which commands are installed.
Usage:
  ul features                    List features; [x] marks installed ones
  ul features add <name>...      Install features (and what they need)
  ul features remove <name>...   Remove features (and what needs them)
  ul features set <name>...|all|none   Install exactly these (none: core only)
  ul features choose             Pick in a checklist (Space toggles, Enter saves)
Options: --no-build saves the choice without rebuilding ul.
Always installed: ul, ule, system commands, zip, app, browser.
Seeded commands are added to or removed from the commands folder; edited
ones are never deleted. game, lm and agent's ula shortcut are built into ul,
so changing them rebuilds it with cargo (like `ul update`, same commit).
The choice is stored in core.features (default [\"all\"]: everything, also
features added by later releases).
Examples:
  ul features add yt game
  ul features remove netflix steam
  ul features set all
",
    ),
    (
        "init",
        "Initialize the Unlaw configuration and editable command sources.
Usage: ul init
Example: ul init
",
    ),
    (
        "list",
        "List saved project templates and available commands.
Usage: ul list
Example: ul list
",
    ),
    (
        "reinstall",
        "Reinstall Unlaw from scratch: the program, its settings and default commands.
Usage: ul reinstall [--yes]
Options:
  --yes, -y    Do not ask for confirmation
Shows what happens and asks first. Deletes the build cache
~/Library/Caches/unlaw/cargo-target (unless CARGO_TARGET_DIR is set), installs
the newest main from GitHub like `ul update --force`, then resets config.toml
and ule.toml to the defaults (core.features and storage.root are kept) and
installs fresh copies of the default commands. The old settings and edited
default commands go to <config>/backups/reinstall-<time>/.
Never touched: commands you wrote, templates, storage (downloads, captures,
models, agent sessions) and the Telegram token in the Keychain. If the build
fails, nothing is reset.
Dependencies: cargo (Rust), Python 3.11+ for the build, git.
Examples:
  ul reinstall
  ul reinstall --yes
",
    ),
    (
        "remove",
        "Remove Unlaw completely, or delete installed commands.
Usage:
  ul remove [--yes]               Uninstall Unlaw and delete all its files
  ul remove <command>... [--yes]  Delete commands/<command> (folder and files)
Options:
  --yes, -y    Do not ask for confirmation
Both forms list what will be deleted and wait for y; nothing can be undone.
ul remove deletes ul, unlaw, ula, unlawagent and ule from the directory that
holds the current ul, the config folder with everything in it (settings, every
command including your own, templates, storage: Telegram and YouTube downloads,
captures, converted models, agent sessions), ~/Library/Caches/unlaw, the
agent's launchd job, the shell integration block in ~/.zshrc, installed agent
skills and the Telegram token in the Keychain. Kept: models in the Hugging Face
cache, the PATH line in ~/.zshrc and a storage.root outside the config folder.
ul remove <command> deletes that command's folder; a default command is also
taken out of core.features so it is not installed again (ul features add
<command> brings it back). System commands cannot be removed; lm and game are
built into ul: ul features remove <name>.
Examples:
  ul remove todo
  ul remove hello --yes
  ul remove
",
    ),
    (
        "skills",
        "Install an Agent Skill that teaches coding agents to use ul.
Usage:
  ul skills install [--project|--path <dir>] [--claude]
  ul skills list                      Show installs and whether they are current
  ul skills show [command]            Print SKILL.md or one command's reference page
  ul skills remove [--project|--path <dir>|--all]
Options:
  (default)        ~/.agents/skills/unlaw, read by Codex and other agents
  --project        ./.agents/skills/unlaw in the current directory
  --path <dir>     <dir>/unlaw
  --claude         Also link it where Claude Code looks (~/.claude/skills/unlaw,
                   or ./.claude/skills/unlaw with --project)
SKILL.md tells agents to discover commands live (`ul commands --describe`,
`ul <command> --help`), so new commands work without reinstalling. The
reference/ snapshot is regenerated automatically after `ul update`, new or
changed commands. Only files the skill created are ever removed; existing
folders it did not create are never overwritten.
Examples:
  ul skills install --claude
  ul skills install --project
  ul skills show todo
",
    ),
    (
        "templates",
        "List saved project templates.
Usage: ul templates
Example: ul templates
",
    ),
    (
        "update",
        "Download and install the newest Unlaw from GitHub.
Usage: ul update [--check] [--force] [--branch <name>|--tag <name>]
Options:
  --check            Compare the installed version and commit with GitHub; installs nothing
  --force            Reinstall even when the installed commit is the newest
  --branch <name>    Install from a branch instead of main
  --tag <name>       Install a tagged release
Runs `cargo install --locked --force --git https://github.com/SDH4114/UnLaw.git
unlaw ule` (ul, ula and the ule editor) into the directory that holds the current
ul (default ~/.local/bin), unless that commit is already installed. Builds share
~/Library/Caches/unlaw/cargo-target, so later updates only rebuild what changed.
Dependencies: cargo (Rust), Python 3.11+ for the build, git (and curl for --check).
Your config, edited commands and data are never touched; unchanged default
commands are upgraded on the next run. UNLAW_UPDATE_REPOSITORY selects a fork.
Examples:
  ul update --check
  ul update
  ul update --tag v2.2.0
",
    ),
    (
        "venv",
        "Create and activate .venv in the current project's Zsh shell.
Usage: ul venv
Requires current-shell integration: ul doctor --fix, then restart Zsh.
Uses core.python (default auto: newest python3.x on PATH).
Example: ul venv
",
    ),
    (
        "version",
        "Show the installed Unlaw version and the commit it was built from.
Usage: ul version
Example: ul version
",
    ),
    (
        "which",
        "Print the source path of an installed command.
Usage: ul which <command>
Example: ul which yt
",
    ),
];

pub fn system_help(name: &str) -> &'static str {
    SYSTEM_HELP.iter().find(|(command, _)| *command == name).map(|(_, text)| *text).unwrap_or("")
}

pub fn system_summary(name: &str) -> &'static str {
    system_help(name).lines().next().unwrap_or("")
}

pub fn is_system(name: &str) -> bool {
    SYSTEM_HELP.iter().any(|(command, _)| *command == name)
}

pub fn system_names() -> impl Iterator<Item = &'static str> {
    SYSTEM_HELP.iter().map(|(name, _)| *name)
}

pub fn wants_help(args: &[String]) -> bool {
    matches!(args.first().map(String::as_str), Some("-h" | "--help" | "help"))
}

/// Print system help when requested; returns true if it did.
pub fn print_if_requested(name: &str, args: &[String]) -> bool {
    if wants_help(args) {
        print!("{}", system_help(name));
        true
    } else {
        false
    }
}
