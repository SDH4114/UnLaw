# Unlaw V1 design

Unlaw is a dependency-free Python CLI for macOS. Both `unlaw` and `ul` invoke the same entry point. The core parses the first argument, handles the three system commands (`commands`, `create command`, and `doctor`), resolves a command directory, and executes its `main.py` with the remaining arguments.

Commands are resolved from `${XDG_CONFIG_HOME:-~/.config}/unlaw/commands` first and from packaged `built_in_commands` second. A user command therefore overrides a built-in without modifying installed files. A valid command is a directory containing `main.py`; no manifest or registry exists.

The built-ins are `app`, `git`, `py`, `rust`, `cpp`, and `mac`. They remain independent scripts. Project generators reject unsafe names and existing destinations. `git` automates add, commit, and push while allowing a message. `mac` delegates to the optional `macos-harness` executable and translates `see`, `key`, `type`, and `click` into its supported CLI or Python-input interface.

`doctor` performs read-only checks for Python, uv, Git, macOS Harness, Harness permissions, LM Studio, and Voice. Missing optional capabilities are informational; missing required tools make doctor fail. Tests isolate configuration with `XDG_CONFIG_HOME` and never touch the real home directory.

