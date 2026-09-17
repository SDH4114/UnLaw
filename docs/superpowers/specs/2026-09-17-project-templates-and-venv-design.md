# Project Templates and Venv Design

## Goal

Add saved project launchers called "templates" to Unlaw. A template records an
existing project's absolute path and launch preferences so `ul <template-name>`
can switch the current Zsh session to that project and open the selected apps.
Also add `ul venv`, which creates `.venv` when necessary and activates it in the
current Zsh session.

This feature does not copy project files and does not store or automatically
activate a Python environment as part of a project template.

## User flows

### Create a project template

From an existing project directory:

```console
$ cd ~/giti/HearMe
$ ul create template hearme
Open with (zed/obsidian) > zed
Add AI? (y/n) > y
Created template 'hearme' for /Users/aminmammadov/giti/HearMe
```

When the name is omitted, creation asks for it first:

```console
$ ul create template
Name of template > hearme
Open with (zed/obsidian) > zed
Add AI? (y/n) > y
Created template 'hearme' for /Users/aminmammadov/giti/HearMe
```

The path is resolved to an absolute canonical path at creation time. The
directory must exist. Names use the existing command-name rule: they start with
a lowercase letter and contain only lowercase letters, digits, `-`, or `_`.
Creation rejects names that conflict with system commands, installed commands,
aliases, or existing project templates. Existing template files are never
overwritten.

### Launch a project template

From any directory:

```console
$ ul hearme
```

The Zsh integration performs these steps in order:

1. Resolve `hearme` as a project template.
2. Change the current shell directory to its saved path using Zsh `cd`.
3. Open the saved path in Zed or Obsidian.
4. If AI is enabled, open the ChatGPT macOS application.

The command does not open another terminal, create a virtual environment, or
activate one. ChatGPT is opened in the same way as the existing `ul gpt`
command; no project files or prompt are automatically sent to it.

If the saved directory no longer exists, Unlaw reports the missing absolute
path and does not launch any app. A template invocation accepts no additional
arguments.

### Activate a virtual environment

From any directory:

```console
$ ul venv
```

If `.venv` does not exist, Unlaw creates it with the Python interpreter running
Unlaw, equivalent to:

```console
$ python -m venv .venv
```

After successful creation, or when a valid `.venv` already exists, the Zsh
integration sources `.venv/bin/activate` in the current shell. If `.venv`
exists but does not contain `bin/activate`, the command reports an error and
does not replace or modify the directory. `ul venv` accepts no arguments.

## Storage

Existing file-overlay templates remain unchanged:

```text
~/.config/unlaw/templates/commands/
~/.config/unlaw/templates/python/
~/.config/unlaw/templates/rust/
~/.config/unlaw/templates/cpp/
```

Saved project templates use a distinct subdirectory:

```text
~/.config/unlaw/templates/projects/<name>.toml
```

Each TOML file has exactly these fields:

```toml
path = "/Users/aminmammadov/giti/HearMe"
app = "zed"
ai = true
```

Allowed `app` values are `zed` and `obsidian`. Unknown keys, missing keys,
invalid value types, invalid names, and malformed TOML produce a clear error
instead of being ignored.

## Listing commands

`ul templates` prints saved project-template names in sorted order, one per
line. It prints nothing and exits successfully when none exist.

`ul commands` continues to print system, installed, and alias command names,
but never includes project-template names.

`ul list` prints both groups in this exact shape:

```text
Templates
hearme
unlaw

Commands
app
browser
cpp
```

Names inside each section are sorted. Both headings are printed even if a
section is empty.

Zsh completion includes both normal commands and saved project-template names.

## Shell integration

A standalone executable cannot change its parent shell's working directory or
activate an environment in that shell. Unlaw therefore provides generated Zsh
integration installed through `ul doctor --fix`.

The managed `.zshrc` block defines an `ul` function that delegates ordinary
commands to `command ul`. It intercepts only these two successful resolutions:

- a saved project-template name: change directory, then ask the CLI to launch
  the configured apps;
- `venv`: ask the CLI to validate or create `.venv`, then source its activation
  script.

Internal helper commands used by this function are not included in `ul
commands`, `ul list`, help, or completion. Direct executable invocation without
the shell function fails safely for template launching and `venv`, explaining
that current-shell integration is required.

`ul doctor --fix` adds or updates one clearly marked managed block without
overwriting unrelated `.zshrc` content. Repeated runs are idempotent. Existing
PATH setup remains supported.

## Application launching

Zed uses the existing configured editor from `apps.editor` and opens the saved
absolute path.

Obsidian opens the saved absolute path with the Obsidian macOS application. A
nonzero `open` result is returned as an error.

AI uses the existing ChatGPT macOS application behavior from `ul gpt`.

Application launches happen only after the shell has successfully changed to
the saved directory. If the editor launch fails, Unlaw returns its nonzero
status and does not attempt the optional AI launch.

## Architecture

`project_templates.py` remains responsible only for overlaying project files.
A new focused module owns saved project-template manifests: paths, validation,
creation, loading, discovery, and launch metadata.

The CLI keeps system-command precedence, then installed command and alias
behavior, and finally resolves a saved project-template. Conflicting names are
prevented during creation, so routing is deterministic.

Shell-specific behavior is isolated in a separate module that renders the Zsh
function and provides the internal resolve/launch/venv operations. Core storage
and validation functions remain shell-independent and unit-testable.

## Error handling

The feature returns exit status `2` for invalid usage or invalid manifest data,
and `1` for runtime failures such as a missing saved directory, failed venv
creation, invalid existing `.venv`, failed `cd`, or failed application launch.

Interactive input treats EOF and interruption as cancellation with no manifest
written. App selection repeats until `zed` or `obsidian` is entered. The AI
prompt repeats until `y` or `n` is entered.

Manifest writes are atomic: write a temporary file in the destination
directory, flush it, then replace the final path. A failed write cannot leave a
partially written template.

## Testing

Tests cover:

- named and interactive template creation;
- exact manifest contents and absolute path storage;
- name conflicts with system commands, installed commands, aliases, and
  templates;
- invalid prompt answers, EOF, and cancellation;
- sorted `templates`, unchanged `commands`, and grouped `list` output;
- missing and malformed manifests;
- missing saved directories;
- launch order and stop-on-failure behavior;
- Zed, Obsidian, and optional ChatGPT subprocess calls;
- generated Zsh integration and `doctor --fix` idempotence;
- `ul venv` creation, reuse, activation-path output, invalid `.venv`, and
  creation failure;
- complete unit suite, Ruff, build, installed CLI smoke tests, and shell syntax
  validation with `zsh -n`.

No external Python dependency is added; the implementation remains Python 3.11+
and standard-library only.
