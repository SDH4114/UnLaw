# Creating or changing commands and templates

Read this before you write or edit anything for Unlaw. The rules in "Hard rules" are not optional.

## Hard rules

1. Create a new command only with `ul create command <name>` (`--lang rust` for Rust). Never make the folder or files by hand: the scaffold has the right entry point, `--help`, description, `AGENTS.md` and `CLAUDE.md`.
2. Work only inside `commands/<name>/` of the command you were asked about (path below). Never edit the Unlaw source repository, the installed binaries (`ul`, `unlaw`, `ula`, `ule`), the core, or anything outside that folder and your own templates.
3. Never edit `config.toml` by hand. Use `ul config get <key>` and `ul config set <key> <value>`.
4. Never edit a default command (`git`, `yt`, `desk`, ...; `ul features list` names them). An edited default stops receiving updates and `ul reinstall` moves it to a backup. To change one, copy its folder to a new name and edit the copy.
5. Never use the name of a system command, a built-in, a default command (current or retired) or an alias. `ul create command` refuses them; choose another name such as `my-<name>`.
6. Ask the owner before installing any third-party dependency (pip, npm, brew, cargo crates). Python commands use Python 3.11+ and the standard library.
7. Verify before you say it is done: `ul commands check <name>` (runs `ul <name> --help` with no stdin and a timeout; reports the exit code, a Usage line and the description; it fails while the scaffold text "Custom Unlaw command." is left in the docstring or help; a Rust command is built first, outside the timeout), `ul <name> --help`, `ul commands --describe` (your line is there), `ul doctor`.

## Where a command lives

`${XDG_CONFIG_HOME:-~/.config}/unlaw/commands/<name>/` (`ul config path` prints `config.toml`, which sits in the config directory). `<name>` starts with a lowercase letter and holds lowercase letters, digits, `-` and `_`. `ul <name> args...` runs it.

The first file that exists is the entry point, checked in this order:

1. `main.py` (run with Python 3.11+: `UNLAW_PYTHON`, else `core.python`, else the newest `python3.x`)
2. `main.sh` (`/bin/sh main.sh` unless it is executable)
3. `main.js` (`node main.js`)
4. `Cargo.toml` (a Rust project; Unlaw builds it into `target/release/main` and rebuilds when `src/` or `Cargo.toml` change)
5. `main` (an executable file)

Other files in the folder (`AGENTS.md`, `CLAUDE.md`, `help.txt`, `config.toml`, data) are yours and never touched by Unlaw. A symlinked folder works and is treated as yours.

## What Unlaw gives the command

Environment variables:

- `UNLAW_COMMAND`: the command name
- `UNLAW_COMMAND_DIR`: the command's folder
- `UNLAW_CONFIG_DIR`: Unlaw's configuration folder (read-only for you)
- `UNLAW_STORAGE`: the resolved `storage.root`, the place for files the command saves
- `UNLAW_BIN`: absolute path of the running `ul`, to call other commands (`"$UNLAW_BIN" config get storage.root`)

The working directory is where the user ran `ul`. Arguments are passed as typed. With `core.command_timeout` above zero Unlaw kills a command that runs longer.

## Required behaviour

- `--help` and `-h` come first, before any side effect (no files, no network, no prompts). Exit 0 and print the purpose, every action and option, defaults, dependencies and examples, starting with a `Usage: ul <name> ...` line. Keep it accurate whenever behaviour changes.
- Exit codes: 0 success, 1 failure, 2 wrong usage (unknown option, missing argument; print `Usage:` to stderr). Errors go to stderr.
- Description for `ul commands --describe`, shell completion and this skill: the first line of `help.txt` if the file exists, else the first docstring line of `main.py`, the `description` in `Cargo.toml`, or the first comment of a shell or JavaScript script. Unlaw never runs the command to read it. Keep it to one accurate line.
- Keep secrets out of the folder, argv, logs and any `config.toml`. Store tokens in the macOS Keychain (`security add-generic-password` / `find-generic-password`).

## Settings and data (one convention)

- Settings of this command: `config.toml` in the command folder (`$UNLAW_COMMAND_DIR/config.toml`), read by the command itself (Python: `tomllib`). Do not add a `[<name>]` table to Unlaw's own `config.toml`: `ul reinstall` resets that file to defaults and moves your tables to a backup. The command folder survives updates, `ul features` changes and `ul reinstall`. Document each setting in `--help`.
- Files the command saves: `$UNLAW_STORAGE/<name>/` (create it on first use). Do not write into the command folder, the config directory or the user's home.
- Cached or temporary data that can be rebuilt goes in `$UNLAW_STORAGE/<name>/cache/` so it can be deleted safely.

## What survives an update

`ul update`, `ul init`, `ul features add|remove|none|all`, `ul commands get` and `ul reinstall` never modify a command you created, its `AGENTS.md`/`CLAUDE.md`, `config.toml` or data, nor your templates. Default commands that you did not edit are replaced by newer versions; edited ones are kept and stop updating. A new Unlaw release may add a default command with a name you already used: your folder is kept as it is, but `ul reinstall` then moves it to `backups/reinstall-<time>/commands/<name>` and seeds the default. This is why you must not use names of default commands.

## Creating a Rust command

`ul create command <name> --lang rust` writes a Cargo project (binary `main`, no dependencies) and builds it once; it needs `cargo`. Edit `src/main.rs`; `ul <name>` rebuilds on change. Keep the `description` line in `Cargo.toml` accurate.

## Templates

There are three different things called templates.

1. Working environments (apps, windows, terminal tabs, sites): `ul template save [name]` snapshots the open windows after asking what to keep; `ul template edit <name>` edits the TOML (creates a starter if missing); `ul template show <name>`, `ul template rm <name>`, `ul templates` list them. The file is `templates/projects/<name>.toml`, version 2: `path`, `focus`, `[[window]]` (`app`, `open`, `frame`, `screen`, `urls`) and `[[window.tab]]` with `panes = [{ dir, run, split }]`. Unknown keys and control characters are refused. Run `ul template --help` for the full format. Start one with `ul <name>`. The name follows the command rules and cannot equal a system, built-in or installed command or an alias. Prefer `ul template edit` over writing the file yourself, then check it with `ul template show <name>` and `ul <name> --dry-run`.
2. Starting files for new commands: `templates/commands/main.py` (Python), `templates/commands/AGENTS.md` and `templates/commands/rust/` (a Cargo project with `Cargo.toml`). `{{command_name}}` is replaced by the new name. They override the built-in scaffold for `ul create command`.
3. Starting files for new projects made by `ul py`, `ul rust`, `ul cpp`: `templates/python/`, `templates/rust/`, `templates/cpp/` override generated files of the same path.

All of them live in `${XDG_CONFIG_HOME:-~/.config}/unlaw/templates/` and are yours: Unlaw never overwrites them.

## Checklist for a new command

1. `ul create command <name>` (check the name is accepted).
2. Edit `commands/<name>/main.py`: replace the docstring summary, fill in `HELP`, keep `--help` first.
3. Put settings in `config.toml` there and data under `$UNLAW_STORAGE/<name>/`.
4. Run `ul commands check <name>`, `ul <name>` with real arguments, a wrong option (expect exit 2), `ul commands --describe`.
5. Tell the owner what the command does, which files it writes and which dependencies it needs.
