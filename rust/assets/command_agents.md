# ul {{command_name}}

A user command of Unlaw (`ul`). Run it with `ul {{command_name}}`. This folder is the whole command.

## Rules
- Change only files in this folder. Do not edit Unlaw itself (its source repository, installed binaries, `ul`'s `config.toml`) or the default commands in sibling folders: an edited default command stops receiving updates, so copy it to a new name instead. Change Unlaw settings only with `ul config get|set`.
- `--help` and `-h` come first: print purpose, options, defaults, dependencies and examples, exit 0, no side effects.
- The description for `ul commands --describe` is `help.txt`, else the first docstring line of main.py (Rust: `description` in Cargo.toml; shell/JS: the first comment). Keep it one accurate line.
- Exit codes: 0 success, 1 failure, 2 wrong usage. Errors go to stderr.
- Unlaw sets UNLAW_COMMAND, UNLAW_COMMAND_DIR, UNLAW_CONFIG_DIR, UNLAW_STORAGE and UNLAW_BIN. The working directory is the caller's; do not assume it.
- Settings of this command: `config.toml` in this folder (UNLAW_COMMAND_DIR). Files it saves: `$UNLAW_STORAGE/{{command_name}}/`. Secrets: the macOS Keychain, never a file.
- Python 3.11+ standard library only. Ask the owner before adding any third-party dependency.
- Check your work: `ul commands check {{command_name}}`, `ul commands --describe`, `ul doctor`.

Full guide: `ul skills show authoring`.
