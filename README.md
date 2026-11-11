# Unlaw

Unlaw is a fast personal CLI utility for macOS. Its core mechanism stays simple:
a `commands/<name>/main.py` folder automatically becomes the `ul <name>` command.

## Install and update

Install the latest version from GitHub with one command:

```bash
curl -LsSf https://raw.githubusercontent.com/SDH4114/UnLaw/main/install.sh | sh
```

The Unlaw core (dispatcher, configuration, system commands, completion, doctor)
is written in Rust and built with `cargo`; the installer sets up Rust through
rustup if it is missing. Commands in `commands/` remain plain Python files, so
Python 3.11+ is required (`brew install python`). The `ul`, `unlaw`, `ula` binaries
and the `ule` editor are installed into `~/.local/bin`; the old uv-based Unlaw is
removed automatically.

### Choosing features

The installer shows a checklist of optional features (↑/↓ move, Space toggles,
`a` selects all or none, Enter installs, `q` cancels); everything starts checked.
The core is always installed: `ul`/`unlaw`, the `ule` editor, system commands,
`ul zip`, `ul app` and `ul browser`.

| Group | Features |
|---|---|
| AI | `lm` (local models), `agent` (needs `lm`; adds `ula`), `tg`, `gpt`, `claude` |
| Media | `yt`, `music`, `lofi`, `netflix`, `capture` |
| Productivity | `desk`, `obsidian`, `work`, `timer`, `clip`, `weather` |
| Development | `git`, `py`, `rust`, `cpp`, `zed` |
| System | `awake`, `sys`, `mac`, `steam`, `minecraft` |
| Fun | `game` |

Re-running the installer on a machine that already has Unlaw is an update: it keeps
the features in `config.toml` and asks nothing (so does `ul update`). Without a
terminal (CI, scripts) everything is installed; pick features up front with
`UNLAW_FEATURES` (`all`, `none` = the core only, or names):

```bash
curl -LsSf https://raw.githubusercontent.com/SDH4114/UnLaw/main/install.sh | UNLAW_FEATURES="yt git game" sh
```

Change them later:

```bash
ul features                    # list; [x] marks installed ones
ul features add yt game        # also adds what they need (agent → lm)
ul features remove netflix     # also removes what needs it
ul features set all            # everything, also features of later releases
ul features set none           # the core only
ul features choose             # the same checklist
```

Commands are added to or removed from `~/.config/unlaw/commands/`; ones you edited
are never deleted. `game`, `lm` and `agent`'s `ula` shortcut are compiled into `ul`,
so changing them rebuilds it with cargo from the same commit (`--no-build` only saves
the choice; the next `ul update` applies it). The choice lives in `core.features`
(default `["all"]`). Running a feature that isn't installed says how to add it.

`ul commands search` shows every command of the catalog in the repository
(`catalog/`, branch `main`) and marks installed ones; Space picks, Enter downloads.
`ul commands get <name>...` does the same without the checklist. Downloads are
checked against the catalog's sha256 and go to `commands/<name>/main.py`; an existing
`commands/<name>` is never overwritten (`installed*` marks a copy that differs from
GitHub; delete the folder to download it again). A downloaded optional feature is
added to `core.features`. Needs `curl`.

Update to the latest version from GitHub:

```bash
ul update --check          # compare version and commit with GitHub without installing
ul update                  # install the newest main (skips when already up to date)
ul update --force          # reinstall even when up to date
ul update --tag v2.2.0     # a specific release; --branch <name> for a branch
```

`ul --version` shows the version and build commit (`Unlaw 3.0.0 (dd061d1)`), so an
update is visible even when the version number doesn't change. `ul update` installs
the new binaries (`ul`, `ula`, `ule`) where the current `ul` lives (`~/.local/bin`
by default) and does nothing when that commit is already installed. Builds share
`~/Library/Caches/unlaw/cargo-target`, so later updates only rebuild what changed.
Configuration, data and manually edited commands are left untouched; unmodified
standard commands are updated on the next run. Requires `cargo` and Python 3.11+;
`--check` also needs `curl`. `UNLAW_UPDATE_REPOSITORY` points to a fork.

Reinstall from scratch, uninstall, or delete a command (each lists what it does and
waits for `y`; `--yes` skips the question):

```bash
ul reinstall               # clean build of main, default settings and default commands
ul remove music            # delete commands/music (a default one also leaves core.features)
ul remove                  # uninstall Unlaw and delete its files
```

`ul reinstall` keeps your own commands, templates, storage and `core.features`; the
old `config.toml`, `ule.toml` and edited default commands go to
`~/.config/unlaw/backups/`. `ul remove` deletes the binaries, `~/.config/unlaw`
(commands, downloads, captures and all), `~/Library/Caches/unlaw`, the agent's
launchd job, the shell integration in `~/.zshrc`, agent skills and the Telegram
token; models in the Hugging Face cache stay.

From a local checkout (install and update are the same commands):

```bash
cargo install --path . --root ~/.local --force       # ul, unlaw, ula
cargo install --path ule --root ~/.local --force     # the ule editor
```

`unlaw` and `ul` are fully equivalent. Building from source and the first run
automatically create the user structure:

```text
~/.config/unlaw/
├── config.toml
├── commands/                   # all non-system commands
│   ├── desk/main.py
│   ├── yt/main.py
│   └── ...
├── data/                       # single default storage
│   ├── captures/
│   ├── runtime/
│   └── telegram/
└── templates/
    ├── commands/
    ├── python/
    ├── rust/
    ├── cpp/
    └── projects/                  # saved paths and launch settings
```

Existing configs, commands and templates are never overwritten. Old official
import wrappers are automatically replaced with full code, while manually edited
commands are kept. System commands cover configuration, diagnostics, listings,
project templates and shell integration; all other commands are created in
`commands/<name>/main.py` and are yours to edit. Each such file contains only its
own command's code and the minimal settings it needs — code from other commands is
never mixed in.

## Main commands

```bash
ul                              # help and initialization
ul init                         # show user paths
ul commands                     # all commands and aliases
ul commands --verbose           # sources and real paths
ul commands --describe          # one-line descriptions (without running commands)
ul commands --json              # machine-readable JSON
ul commands search              # the command catalog on GitHub (checklist on a terminal)
ul commands search youtube      # filter by name and description; --list only prints
ul commands get yt music        # download commands that are not installed yet
ul templates                    # saved templates (working environments)
ul list                         # templates first, then commands
ul which git                    # where a command comes from
ul create command anime         # new command
ul template save hearme         # save the open windows as a template
ul venv                         # create/activate .venv in the current shell
ul doctor --verbose             # full diagnostics
ul doctor --fix                 # safe automatic fixes
ul doctor --json                # diagnostics for scripts
ul completion zsh               # zsh completion
ul version
ul update --check              # is there a new version on GitHub
ul skills install --claude      # teach coding agents to use ul
ula                             # local AI agent: files, TODO, schedule, Telegram
```

Global options:

```bash
ul --dry-run <command> ...
ul --verbose <command> ...
ul --no-color <command> ...
ul --version
```

An unknown command gets a suggestion with the closest name. `--dry-run` shows the
exact process for a command (interpreter and path) without running it.

## Templates: working environments

A template is a working environment you start with one command. `ul <name>`
changes the current shell to the project folder and opens its windows: apps
placed on the screen, Ghostty windows with tabs and splits (each pane in its
folder, optionally running `claude`, `codex` or any command) and sites in the
default browser.

Arrange the windows the way you like, then save them:

```bash
cd ~/giti/HearMe
ul template save hearme
```

Unlaw reads every visible window and asks which ones belong to the template
(a checklist: an app you just happened to have open stays out), which browser
tabs to keep, what each Ghostty pane runs, the project folder and whether to
hide other apps on start. It shows the result before saving.

```bash
ul hearme               # go to the folder, open and place everything
ul hearme --focus       # also hide every other app (nothing is closed)
ul hearme --dry-run     # show what it would open
ul template show hearme
ul template edit hearme # the TOML file; `edit <new name>` creates a starter
ul template rm hearme
ul templates            # name, folder and apps of each template
```

The file lives in `~/.config/unlaw/templates/projects/<name>.toml`:

```toml
version = 2
path = "~/giti/HearMe"        # the shell cds here
focus = false

[[window]]
app = "Zed"
open = "~/giti/HearMe"
frame = "left"                # preset or [x, y, width, height] in 0..1
screen = 1                    # 1 = main display

[[window]]
app = "Ghostty"
frame = "right"

[[window.tab]]
panes = [
  { dir = "~/giti/HearMe", run = "claude" },
  { dir = "~/giti/HearMe", split = "down" },
]

[[window]]
app = "browser"               # the default browser
urls = ["https://github.com/SDH4114/HearMe"]
```

Presets: `full`, `left`, `right`, `top`, `bottom`, `top-left`, `top-right`,
`bottom-left`, `bottom-right`, `left-third`, `center-third`, `right-third`,
`left-two-thirds`, `right-two-thirds`, `center`. Frames are fractions of the
screen, so a template survives another display or resolution. Running a template
again reuses the Ghostty and browser windows it opened last time. `run` is typed
into the shell, so the pane stays a shell when the agent exits.

macOS asks once for Accessibility (placing and reading windows) for your
terminal and for Automation of Ghostty and the browser. Safari and Chromium
browsers share their tabs with `save`; others (Firefox, Zen) do not, so `save`
asks for the links and those browsers decide where links open. Windows in full
screen or on other Spaces are not seen by `save`. Templates in the old format
(`path`, `app`, `ai`) still work; save them again to use the new features.

Changing the directory of the current shell needs the integration once:

```bash
ul doctor --fix
exec zsh
```

## Virtual environment

```bash
cd ~/giti/HearMe
ul venv
```

If `.venv` is missing, the command creates it with `python -m venv` (interpreter
from `core.python`) and then activates it in the current Zsh. An existing valid
`.venv` is simply activated. Project templates neither save nor activate a
virtual environment.

## Configuration

```bash
ul config path
ul config show
ul config get core.command_timeout
ul config set core.command_timeout 15
ul config set aliases.g '["git"]'
ul config check
ul config edit
ul config reset --yes
```

`reset --yes` creates a timestamped backup first. Writes are atomic.
`config set` accepts TOML values; unquoted text is stored as a string.
Comments, ordering and unknown keys in `config.toml` are preserved on write.

Default configuration:

```toml
[core]
color = true
verbose = false
command_timeout = 0
show_timing = false
python = "auto"

[aliases]

[storage]
root = "data"

[git]
auto_push = true

[projects.python]
environment = "auto"
initialize_git = false

[projects.rust]
initialize_git = false

[projects.cpp]
standard = 20
initialize_git = false

[mac]
executable = "macos-harness"
timeout = 30

[todo]
vault_path = "~/aiwork/data-obsidian"
file = "TODO.md"
completed_column = "Completed"

[desk]
port = 8765              # 0 = any free port; a busy port moves to the next one
open_browser = true
sound = true

[desk.pomodoro]
work = 25                # minutes
short_break = 5
long_break = 15
cycles = 4               # focus sessions before a long break

[capture]
camera_device = "default"       # `default` = the camera macOS picks, a name, or a number
audio_device = "default"        # same for the microphone (see `ul capture devices`)
screen_audio = true             # microphone in screen recordings
system_audio = true             # sound of the Mac in screen recordings
show_clicks = true
video_format = "mov"            # mov or mp4
audio_format = "m4a"            # m4a, mp3 or wav
overlay = "bottom-right"        # camera corner in screen + camera recordings

[games]
difficulty = "normal"

[zip]
format = "zip"                  # zip, 7z, rar, tar.zst, tar.xz, tar.gz
level = "max"                   # 0–9 or store, fastest, fast, normal, max, ultra
keep_junk = false

[yt]
podcast_dir = "~/Library/Mobile Documents/com~apple~CloudDocs/Podcasts"   # ul yt download --podcast

[apps]
spotify = "Spotify"
editor = "Zed"
spotify_autoplay_delay = 2.0
browser_url = "https://duckduckgo.com/"
lofi_url = "https://lofi-engine.vercel.app/"
youtube_url = "https://www.youtube.com/"

[telegram]
chat_id = ""
api_base = "https://api.telegram.org"
keychain_service = "unlaw.telegram"

[lm]
model = "auto"
embedding_model = "auto"
stt_model = "auto"
tts_model = "auto"
image_model = "auto"
video_model = "auto"
music_model = "auto"
port = 1234
idle_minutes = 10
system_prompt = "You are a concise and practical local assistant."
temperature = 0.7
max_tokens = 4096
```

`command_timeout = 0` disables the limit. The Python environment accepts `auto`,
`uv`, `venv` or `none`. In `auto` mode uv is tried first, then the standard venv.
A relative `storage.root` is resolved against `~/.config/unlaw`; an absolute path
or a path with `~` moves the whole storage elsewhere:

```bash
ul config set storage.root '"~/Documents/UnlawData"'
```

## Aliases

An alias is an array of arguments, not a shell string. It is therefore never run
with `shell=True` and can safely be extended with user arguments:

```toml
[aliases]
g = ["git"]
gs = ["git", "status"]
newpy = ["py"]
```

```bash
ul gs
ul newpy experiment --uv --git
```

Cyclic aliases are detected and not run. System commands cannot be overridden by
an alias.

## User commands

```bash
ul create command anime
```

This creates `~/.config/unlaw/commands/anime/main.py` plus `AGENTS.md` and
`CLAUDE.md` with the rules for AI coding agents. Names of system, built-in,
default (also removed ones like `todo`) commands and aliases are refused, so a
user command never clashes with one. `ul commands check anime` runs its
`--help` with no input and a timeout and reports whether it exits 0, has a
Usage line and a description. Arguments are in
`sys.argv[1:]`, and the script's exit code is returned to the shell. A user
command can be fully rewritten by hand. Automatic updates never overwrite an
existing `main.py`.

A command is a folder with a single entry point. These are checked in order:

| File | Run with |
|---|---|
| `main.py` | Python 3.11+ from `core.python` (`auto` — the newest `python3.x` on PATH) |
| `main.sh` | `/bin/sh`, or directly via shebang if the file is executable |
| `main.js` | `node` |
| `main` | directly; any executable, e.g. a compiled Rust/C++ binary |

No SDK is needed: Unlaw passes environment variables to the command.

| Variable | Value |
|---|---|
| `UNLAW_COMMAND` | command name |
| `UNLAW_COMMAND_DIR` | command folder |
| `UNLAW_CONFIG_DIR` | Unlaw config folder (`config.toml`) |
| `UNLAW_STORAGE` | resolved `storage.root` path for the command's files |
| `UNLAW_BIN` | absolute path of the running `ul`, for calling other commands |

```sh
#!/bin/sh
# Show today's notes folder.
mkdir -p "$UNLAW_STORAGE/notes" && open "$UNLAW_STORAGE/notes"
```

The description for `ul commands --describe` and Zsh completion is read without
running the command: the first line of `help.txt` in the command folder, otherwise
the first line of the `main.py` docstring, otherwise the first `#`/`//` comment in
other scripts. `--help` inside the command itself is still required.

A command keeps its own settings in `commands/<name>/config.toml` and its data
in `$UNLAW_STORAGE/<name>/`, not in Unlaw's `config.toml` (`ul reinstall` resets
that file). Updates, `ul init`, feature changes and catalog downloads never touch
user commands or templates; `ul reinstall` moves a user folder that has a default
command's name into `backups/reinstall-<time>/`.

### Writing commands with an AI agent

Run `ul skills install --claude` once, then ask the agent for the command. The
skill's guide (`ul skills show authoring`) tells it to create the command with
`ul create command <name>`, stay inside that folder, never edit Unlaw itself, its
`config.toml` or the default commands, and verify with `ul commands check <name>`.
The `AGENTS.md` in the command folder repeats those rules for agents that work
inside it.

Your own template for new commands:

```text
~/.config/unlaw/templates/commands/main.py
~/.config/unlaw/templates/commands/AGENTS.md
~/.config/unlaw/templates/commands/rust/      # Cargo.toml + src/, {{command_name}} is substituted
```

### Rust commands

```bash
ul create command fast --lang rust
ul fast hello
```

Creates a Cargo project in `~/.config/unlaw/commands/fast/` and builds it right
away. Edit `src/main.rs` and just run `ul fast`: Unlaw rebuilds the command itself
when `src/`, `Cargo.toml` or `Cargo.lock` is newer than the binary. The description
for `ul commands --describe` comes from `description` in `Cargo.toml`. Requires
`cargo`; dependencies are added as in any Rust project (`cargo add` in the command
folder).

### Built-in Rust commands

`ul zip`, `ul app`, `ul browser`, `ul game` and `ul lm` are built into the core
(`game` and `lm` only when those features are chosen). Lookup order: system
commands → `commands/<name>/` → built-ins, so your own `commands/zip` folder still
overrides the built-in `zip`. Untouched old `commands/zip/main.py`,
`commands/game/main.py`, `commands/lm/main.py` (the LM Studio client from 3.0),
`commands/app/main.py` and `commands/browser/main.py` (Python seeds up to 3.8)
are removed automatically on update; manually edited ones stay and keep running
instead of the built-ins.

## Commands in config

All commands below (except `app`, built into the core) live at
`~/.config/unlaw/commands/<name>/main.py` when their feature is installed. They are
complete standalone sources: at runtime they don't import `unlawful` and don't
depend on the package's internal structure. The system dispatcher looks for
commands only in this folder.

### Apps

```bash
ul app Zed
ul app "Visual Studio Code"
```

### Git

```bash
ul git "fix parser"       # add, commit, push
ul git                    # add, ask for a message in the terminal, commit -m, push
ul git status
ul git pull
ul git push
ul git commit "message"  # add + commit, no push
ul git sync "message"    # pull --rebase + add + commit + push
```

Without an argument, `ul git` shows a plain one-line `Commit message:` prompt in
the current terminal and never opens a Git editor. The standard workflow always
ends with `git push` and stops at the first error.

### Python

```bash
ul py experiment
ul py experiment --uv
ul py experiment --venv
ul py experiment --no-venv
ul py experiment --uv --git
```

### Rust

```bash
ul rust amber
ul rust amber --lib
ul rust amber --bin --git
```

The project is created with Cargo. Without `--git`, Cargo gets `--vcs none`
unless `projects.rust.initialize_git` is enabled.

### C++

```bash
ul cpp engine
ul cpp engine --std 23
ul cpp engine --git
```

Creates a CMake project. Standards 11, 14, 17, 20, 23 and 26 are supported.

No generator overwrites an existing directory.

## Desk: board, today and pomodoro in the browser

`ul desk` opens the same board in the browser: drag cards between columns,
double-click to edit, check them off (they move to `todo.completed_column`), and
filter by `#tag` or search. Cards understand Obsidian Kanban markup: `#tags`,
due dates `@{2026-11-01}` (quick add: `@today`, `@tomorrow`, `@завтра`, `@+3`)
and `[[note]]` links that open in Obsidian. The Today view lists overdue cards,
cards due today, cards in a Doing column and the next seven days; Stats shows
focus sessions, finished tasks, the day streak and the cards you focused on most.

```bash
ul desk                                  # the default board (todo.vault_path + todo.file)
ul desk Work                             # <desk.boards_dir>/Work.md
ul desk ~/notes/Project.md --no-open     # any Kanban .md file
ul desk --reminders                      # Apple Reminders: lists are columns
ul desk new Plan                         # a new board: To do / Doing / Done
ul desk pomodoro start 50 --card "Write chapter 3"
ul desk pomodoro                         # status; also pause, resume, skip, stop
ul desk stats
```

### Boards from the terminal (and for AI agents)

The same boards without the page, so a person or any coding agent can read the
tasks and change them. Card numbers come from `show`; `add`/`move`/`done` take
`-b <board>` and otherwise use the default board.

```bash
ul desk list                             # default, named and recent boards; --json
ul desk show                             # columns and numbered cards
ul desk show Work --json                 # ids, titles, details, tags, due dates, version
ul desk show --reminders                 # Apple Reminders (read only here)
ul desk add "Call the bank @tomorrow"    # first column; --column "Doing"
ul desk move 3 Doing
ul desk done 3                           # checks it and moves it to the Done column
```

`ul todo` was removed in 3.17.0: `ul desk show/add/move/done` replace it. An
untouched `commands/todo` is deleted on the next run; an edited one is kept.

The Markdown file stays the source of truth: `ul desk`, the agent and Obsidian
see each change, and edits made elsewhere show up on the page within two seconds.
A change based on an old version of the file is refused and retried on top of
the new one, so nothing is overwritten. The timer lives in `storage.root/desk`,
so a reloaded tab, the terminal and the page share it; each phase ends with a
macOS notification. The server listens on 127.0.0.1 only and needs the random
token in the printed address. Keys: `n` new card, `/` search, `space` timer,
`1`–`5` views, `?` all shortcuts. Only the Python standard library is used.

**Reminders** is a separate layer that never touches your .md boards: each
Reminders list is a column, each open reminder a card. Add, edit, `@date`, drag
to another list, done and delete go straight to Reminders through EventKit; the
first use asks to allow your terminal in System Settings > Privacy & Security.

**Canvas** is a whiteboard on JSON Canvas files (`.canvas`, opened by Obsidian
Canvas too); drawings are kept in an extra top-level `unlaw` key. A bare name
means `<desk.canvas_dir>/<name>.canvas`. Photoshop-style keys work on any
keyboard layout: `v` select, `h` hand, `n` card, `t` text, `u` shapes, `b`
brush, `g` fill, `e` eraser, `[`/`]` width, `d` default color, Cmd+G group,
Cmd+0 fit.

**Games** plays the `ul game` arcade (Tetris, Snake, Minesweeper, Space Invaders,
Chomp, Dash, Ping Pong) in the page with keyboard and mouse. The desk runs `ul game --stream`, so
these are the same Rust games, and best scores are shared with the terminal in
`storage.root/runtime/arcade.toml`. Leaving the tab pauses a game.

**Studio** is a small recording studio on top of `ul capture`: record the screen
(with system audio and the microphone), the screen with the camera in a corner,
the camera or audio; pause, resume and stop; take screenshots; see a preview of
the display, the camera and the microphone level. The library plays recordings
in the page and can trim, convert (MP4, GIF, MP3, …), copy screenshots, show
files in Finder and move them to the Trash. A red REC badge in the header shows
a running recording from any tab; recordings started in the terminal appear there
too, and a recording keeps going when the page is closed.

## Screen, video and audio capture

```bash
ul capture                        # a menu: pick a screenshot or a recording
ul capture shot                   # the whole screen (PNG); also: area, window
ul capture shot area --clipboard  # select an area, copy it instead of saving
ul capture record                 # screen + system audio + microphone, in the background
ul capture record --camera        # the same with the camera in a corner
ul capture record camera          # camera + microphone
ul capture record audio --format mp3
ul capture record --duration 30   # record 30 s in the foreground, then save
ul capture pause                  # resume / stop / status
ul capture stop                   # save (joins paused parts, adds camera and microphone)
ul capture list                   # newest captures with length and size
ul capture trim last --from 0:05 --to 1:30
ul capture convert last --to gif
ul capture devices                # displays, cameras and microphones
```

Screen recordings use macOS `screencapture`, which records the sound of the Mac
without extra drivers. ffmpeg (`brew install ffmpeg`) is needed for the camera,
audio, a microphone other than the system default, pause, MP4, trim and convert.
The first run asks for Screen Recording, Camera and Microphone permissions for
the terminal. Devices are picked by name or number; `default` follows the system
choice, and `ul capture devices` warns when the microphone is a virtual device
such as BlackHole. Old one-word actions (`ul capture screenshot`, `area`,
`screen`, `audio`, …) still work. Files go to `storage.root/captures` and are
never overwritten; Telegram saves downloads to `storage.root/telegram/downloads`,
and runtime files go to `storage.root/runtime`.

## Keep the Mac awake

```bash
ul awake 2h                       # also 30m, 1h30m, 90 (minutes); at most 7 days
ul awake until 18:30              # tomorrow if it has passed; also: until 2026-12-01 09:00
ul awake on                       # no end; `ul awake off` stops it
ul awake --pid 1234               # while that process lives
ul awake --display -- make build  # screen on too; runs the command, exits with its code
ul awake                          # status (also: status --json)
```

`ul awake` runs macOS `caffeinate` (`-i -s`, plus `-d` with `--display`) in a
detached supervisor. A new session replaces the running one (not a
`-- command` session, which lives in its terminal; stop that command instead).
State is `storage.root/runtime/awake.json`.

`caffeinate` cannot keep a MacBook awake with the lid closed; `pmset -a
disablesleep 1` can, but needs root. `ul awake lid setup` installs a sudoers
rule once (`/etc/sudoers.d/unlaw-awake`) that allows exactly
`pmset -a disablesleep 0` and `1` without a password. The setup is one `sudo`
call (one password prompt) with a fixed script that gets the rule text as an
argument: root writes it to a hidden file in the same folder (a user-owned file
is never read as root), validates that file with `visudo -cf`, and only then
moves it into place. The rule names the account from the account
database, never `$USER`, and refuses names that sudoers reads as keywords
(`ALL`, other all-caps aliases). After that `--lid` sets it for the session and
restores it at the end (timeout, `off`, signal, command exit). If the process
is killed or the Mac loses power, the debt is on record before the lid is
disabled; it is repaid within 5 minutes or at the next login (a small
LaunchAgent runs `ul awake _scheduled`, which `--lid` sessions install and
which removes itself once nothing is owed) or at the next `ul awake` call. If the restore fails, `status` says lid sleep is still
disabled and `ul awake off` retries. On battery, a closed MacBook in a bag gets
hot and drains the battery (`--lid` warns). `lid remove` deletes the rule,
`lid status` checks that it really works (it runs `sudo -n pmset -a
disablesleep <current value>`, a no-op; `sudo -l` would also say yes for any
other NOPASSWD rule).

### Schedules

```bash
ul awake schedule add 23:00-06:00                       # every night; may cross midnight
ul awake schedule add 09:00-17:30 --days weekdays --display
ul awake schedule add 14:00-16:00 --date 2026-12-01 --name "backup"   # once
ul awake schedule list [--json]                         # id, window, days, flags, name, next start
ul awake schedule rm 2                                  # or --all
```

`--days` is `daily` (default), `weekdays`, `weekends` or English short names
(`mon,wed,sat`, any case); `--date` makes a one-off and excludes `--days`.
`--lid` needs the lid rule when you add the schedule (launchd cannot ask for a
password); without it `add` points you to `ul awake lid setup`.

Schedules are stored in `storage.root/runtime/awake-schedules.json`. One
LaunchAgent, `~/Library/LaunchAgents/com.unlaw.awake.plist`, runs
`ul awake _scheduled` at each window start (and when it is loaded, so a window
that is already open starts at once); it is rewritten on every `add`/`rm` and
removed with the last schedule. A scheduled session lasts until the end of the
window. It never replaces a `-- command` session and never cuts short a manual
session that ends later or has no end. `schedule rm` also stops the session
that schedule started. `ul awake off` (of a scheduled or a manual session)
during a scheduled window skips the rest of that window and any other window
open at that moment; the next day's window runs as usual. When a scheduled start replaces a shorter manual session
it keeps that session's `--display` and `--lid`. Finished one-offs are dropped.
`ul remove`, `ul remove awake` and `ul features remove awake` boot the job out
and delete the plist; they only report `/etc/sudoers.d/unlaw-awake` (remove it
with `ul awake lid remove`, or `sudo rm /etc/sudoers.d/unlaw-awake`).

A sleeping Mac is not woken at the start time: the window begins when the Mac
is awake. On wake launchd runs the missed start, which begins the session if
the window is still open. Runs are logged in `storage.root/runtime/awake.log`.

## Timers, clipboard, weather and stats

### ul timer
Countdowns and alarms that survive closing the terminal, with a macOS notification.
```bash
ul timer 25m write report     # also 30s, 1h30m, bare number = minutes (max 7 days)
ul timer at 18:30 leave       # alarm, tomorrow if the time has passed
ul timer                      # running timers (also: list --json)
ul timer cancel 2             # or --all
ul timer wait 90s tea         # count down in the terminal, Ctrl+C cancels
```
Timers are background processes, so they do not survive a logout or a restart. The next
`ul timer` command says so once on stderr ("lost" if the time had not come, "missed" if it had).
Setting: timer.sound (default true).

### ul weather
Weather from Open-Meteo (no API key).
```bash
ul config set weather.city "Baku"
ul weather                    # default city, 3 days
ul weather New York --days 7 --units imperial
ul weather --json
```
Settings: weather.city, weather.units (metric|imperial). Needs the internet.

### ul clip
`ul clip on` starts a background watcher (LaunchAgent `com.unlaw.clip`) that keeps the text you copy.
```bash
ul clip on                    # start the watcher (off stops it)
ul clip                       # history, newest first; list N, --json
ul clip search invoice        # items containing every word
ul clip copy 3                # back onto the clipboard; also show N, rm N, clear [--yes]
ul clip pause                 # ignore copies for now; resume, status
```
Text only, up to 100 KB per item, duplicates move to the top, `clip.max_items` (200) items.
Copies that apps mark concealed, transient or auto-generated (password managers) are never stored.
The history is plain text (file mode 0600) in `<storage.root>/clip/`; if `storage.root` sits in a synced
folder (iCloud, Dropbox, a vault) it syncs too. `pause` before copying secrets that an app does not mark;
`clear` also deletes the `history.json.damaged-*` copies. `clip.interval` (1 s) is the check interval.
The watcher is exempt from `core.command_timeout`. If copies stop being stored (for example macOS denies
the background helper pasteboard access), `ul clip status` shows the newest item and the watcher log
(`clip/watch.log`); macOS gives no direct way to ask whether access is denied.

### ul sys
Computer stats without root: `ul sys` shows model, chip, macOS, uptime, CPU, GPU, memory (app, wired, compressed, swap, pressure), disks, battery (charge, cycles, condition, max capacity) and the top 5 processes. `ul sys cpu|gpu|mem|disk|battery|top` shows one part, `--json` gives stable keys with numbers, `--watch [seconds]` refreshes in place (Ctrl+C to quit). A tool that is missing or fails shows as n/a. Colors only on a terminal (NO_COLOR turns them off).

### ul claude

`ul claude` opens the Claude desktop app, like `ul gpt` opens ChatGPT.

## Quick apps

```bash
ul lofi                           # open Lofi Engine
ul zed                            # open the current folder in Zed
ul netflix                        # open Netflix
ul tg                             # open Telegram
ul obsidian                       # open Obsidian
ul gpt                            # open ChatGPT
ul browser                        # open the configured start page
ul steam                          # open Steam
ul minecraft                      # open Prism Launcher
ul music
ul music "Killer Queen"           # search and play the first result in Spotify
ul work                            # Lofi Engine + current folder in Zed
ul yt                              # open the YouTube home page
ul yt "omarchy linux"             # YouTube search in the browser
ul yt download "https://youtu.be/VIDEO_ID"                 # download MOV
ul yt download "https://youtu.be/VIDEO_ID" --format mp4    # MP4
ul yt download "https://youtu.be/VIDEO_ID" --format raw    # source container/codecs
ul yt download "https://youtu.be/VIDEO_ID" --audio         # MP3
ul yt download "https://youtu.be/VIDEO_ID" --quality 1080  # up to 1080p
ul yt download "https://youtu.be/VIDEO_ID" --output ~/Downloads
ul yt --help                      # all options and examples
```

Auto-playing a Spotify result requires the Accessibility permission for the
terminal.

The `ul browser` start page is set in the config:

```bash
ul config set apps.browser_url '"https://duckduckgo.com/"'
```

## Archives

`ul zip` compresses files and folders and extracts almost any archive. Without an
action, the command figures out what to do: archives are extracted, everything
else is compressed.

```bash
ul zip project                     # project.zip next to the folder, max compression
ul zip a.png b.png notes/          # several paths → ./Archive.zip
ul zip project -f 7z               # strongest (LZMA2)
ul zip project -f rar              # RAR5 with recovery record (needs rar)
ul zip project -f zst --fast       # tar.zst: fast and dense, for backups
ul zip project -f 7z -9            # level 0–9 (or --store … --ultra)
ul zip project -p -f 7z            # AES-256 password, file names hidden too
ul zip project -o ~/Desktop/pack.7z  # format taken from the extension
ul zip project.zip                 # extract next to it
ul zip x backup.rar -o ~/Downloads # extract into a folder
ul zip x pack.zip --here           # contents directly into the destination
ul zip ls backup.7z                # list contents
ul zip test backup.7z              # integrity check
```

Creates `zip` (default), `7z`, `rar`, `tar.zst`, `tar.xz`, `tar.gz`; also reads
`rar`, `gz`, `bz2`, `xz`, `zst`, `cab`, `iso`, `cpio`, `xar`. macOS junk
(`.DS_Store`, `._*`, `__MACOSX`) is kept out of archives; `--keep-junk` keeps it.
A single-item archive extracts as that item, otherwise into a folder named after
the archive. Nothing is overwritten: a ` 2` suffix is added. The password is
prompted in the terminal and never passed in process arguments.

Levels follow the 7-Zip scale: `0` store, `1` fastest, `3` fast, `5` normal,
`7` max (default), `9` ultra. Each level maps to the format's best settings
(`-mx`, `rar -m0…5`, `xz -0…9`, `zstd -1…19` and `--ultra -22`). Measured on
68 MB of code and binaries: 7z `1/5/7/9` gives 16.7/14.1/13.8/13.8 MB, zip —
20.0/19.0/18.7/18.6 MB, Finder — 20.3 MB. If no level is given and ≥90% of the
input is already-compressed media (jpg, heic, mp4, zip…), level 1 is used: on
236 MB of HEIC, level 9 saved 0.01% in 37 s instead of 3 s.

Dependencies: `brew install sevenzip zstd`; to create `.rar` — `brew install --cask rar`.
Without 7-Zip, `zip` archives are created with the system `zip`, and extraction
goes through `bsdtar`.

## Unlaw Arcade

```bash
ul game                       # menu (mouse or keyboard)
ul game tetris
ul game snake easy
ul game minesweeper normal
ul game invaders hard
ul game chomp
ul game dash
```

The games are built into the Rust core and support keyboard and mouse. Each screen
shows a controls hint at the bottom, `P` pauses, `Esc`/`Q` quits. After game over,
Enter or a click plays again, Esc returns to the menu. Best scores are stored in
`storage.root/runtime/arcade.toml` and shown in the menu.

| Game | Like the original | Mouse |
|---|---|---|
| Tetris | 7-piece bag, Next queue, Hold (`C`), ghost piece, rotation with wall kicks (`↑`/`X`, `Z`), lock delay, level up every 10 lines, guideline gravity, combos and back-to-back | piece follows the cursor, click — hard drop, right click — rotate |
| Snake | 2-character-wide cells, turn buffer, speeds up as it grows, timed ★ bonus | click — turn toward the click |
| Minesweeper | Beginner 9×9/10, Intermediate 16×16/40, Expert 30×16/99, safe first click, chording on numbers, classic colors, timer | left — reveal or chord, right — flag |
| Space Invaders | 5×11 formation, three alien types, speeds up as they fall, only the bottom row shoots, one player bullet on screen, bunkers, UFO, lives and waves, extra life at 1500 | cannon follows the cursor, click — fire |
| Chomp | original maze chase: a new symmetric maze every level, pellets and power pellets, four hunters with their own habits (Hound chases, Fox cuts off the junction ahead, Owl goes where it heard you eat, Moth guards the power pellets), rest/hunt phases, 200→1600 combo, bonus items, extra life at 10 000 | click — turn toward the click |
| Dash | original endless runner with the mechanics of the browser offline game (a fox, not a dinosaur): auto-run on the left, fixed-height gravity jump (`Space`/`↑`/`W`/click), duck (`↓`/`S`, ~0.35 s, key repeat extends it; `↓` in the air drops fast), cacti of three sizes in groups of 1–3, birds with a wing flap at three heights (jump the low one, duck or jump the middle one, run under the high one), speed rising to a maximum with gaps that grow with it, score ≈10/s with a flash every 100 and night from 700, parallax clouds and scrolling ground | click — jump |

Difficulty: `easy` — slow start and assists (Tetris has a ghost piece and 3 pieces
in Next, the snake passes through walls, 5 lives in Invaders and Chomp); `normal` — classic;
`hard` — genuinely hard: Tetris starts at level 12 without ghost or Hold, with
garbage rising from below, the snake gets obstacles and double growth, Minesweeper
is Expert without a guaranteed opening, aliens fire nonstop and you have 2 lives, Chomp hunters are as fast as you and
fright lasts 2 s (gone from level 5), Dash starts fast with tight gaps, mixed cacti and birds from the first obstacle
(`easy`: slower, wider gaps, no high birds).
Set the default with `ul config set games.difficulty hard`.

## Telegram

```bash
ul tg                              # open the Telegram app
ul tg setup                        # token is stored in the macOS Keychain
ul tg "Message from the terminal"
ul tg send report.pdf
ul tg photo screenshot.png
ul tg video demo.mov
ul tg capture                       # latest Unlaw screenshot or recording
cat notes.txt | ul tg
ul tg last
ul tg download
ul tg status
```

The bot token is never written to `config.toml` or Git. For a private chat, first
message the bot, then enter its `chat_id` during `setup`.

## Editor (ule)

`ule` is Unlaw's own terminal code editor: vim keys, a `space` menu for everything
else, language servers, fuzzy pickers, and ul built in. `ul edit <file>` and
`ul config edit` open it (`core.editor = "auto"`: ule, then `$VISUAL`/`$EDITOR`,
then `open -t`; set `core.editor` to `nvim` or `zed --wait` to use another one).

```bash
ule                       # start screen: recent files, find, explorer
ule src/main.rs:42        # open at a line (also: ule +42 file)
ule .                     # a folder opens the file explorer
git diff | ule -          # edit text from stdin
ule --health              # language servers, formatters and tools found
```

The first five minutes:

- `i` types, `Esc` stops, `:w` saves (`Ctrl-s` too), `:q` quits; `:help` explains the rest.
- `space` opens a menu showing what comes next: `space space` find a file, `space /`
  search the project, `space ,` open buffers, `space e` explorer, `space r` run the
  file (output in the panel, `space o`), `space ?` every key binding, `space :` every command.
- Code: `gd` definition, `K` docs, `gr` references, `space ca` fixes, `space cr` rename,
  `space cf` format, `]d` next diagnostic. Completion pops up while typing (Tab/Enter).
- Vim: operators and motions with counts, text objects (`ci(`, `daw`, `dap`, `cit`),
  visual/line/block modes with block insert, `.` repeat, macros (`qa…q`, `@a`, `Q`),
  registers (`"+` is the clipboard), marks, jumps, `:s`, `:g`, `:sort`, `:normal`,
  `:%!filter`, splits (`Ctrl-w v/s/h/j/k/l`).
- ul: `space uu` picks a ul command, `:ul desk add milk` runs one into the panel,
  `:ul! game` hands over the terminal, `space gc` commits and pushes with `ul git`.
- Local AI through `ul lm` (nothing leaves the Mac): `space aa` ask, visual +
  `space ae` rewrite the selection (one undo step), `space ax` explain.
- Keys of ordinary editors work next to vim (`standard_keys = true`, `:help standard`):
  `Ctrl-Z`/`Ctrl-Y` undo/redo, `Ctrl-C`/`Ctrl-X`/`Ctrl-V` copy/cut/paste (the whole line
  when nothing is selected), Shift+arrows select and typing replaces the selection,
  `Ctrl`/`Option+Backspace` delete a word, `Cmd+Backspace` to the line start, `Ctrl-K`
  to the line end, `Ctrl-Shift-K` the line, `Option`/`Ctrl+arrows` move by word,
  `Option+Up/Down` move lines (with Shift: duplicate), `Ctrl-F` find, `Ctrl-G` go to line,
  `Ctrl-/` comment. Vim's keys they replace moved: block visual `Ctrl-Q`, increment
  `Alt-A`/`Alt-X`, suspend `space z`; `standard_keys = false` gives pure vim back.

Settings live in `~/.config/unlaw/ule.toml` (`space fc` creates it with every option
commented). Example:

```toml
theme = "onedark"          # unlaw (terminal colors), onedark, gruvbox, catppuccin, tokyonight, light

[editor]
tab_width = 4
rulers = [100]
format_on_save = "auto"    # format only when the project has rustfmt.toml, .prettierrc, ruff config...

[keys.normal]
"<leader>t" = ":run cargo test"
"H" = "^"

[keys.insert]
"jk" = "normal_mode"

[languages.python]
run = "uv run {file}"
```

Language servers start automatically when installed (rust-analyzer, basedpyright or
pyright, ruff, clangd, typescript-language-server, gopls, …); `ule --health` lists
what is missing. Files changed on disk by other programs (or agents) are reloaded
when they have no unsaved edits. History, cursor positions and recent files are kept
in `storage.root/ule`.

## Local agent

`ula` (also `unlawagent` and `ul agent`) is a personal agent on a local `ul lm`
model. It reads and searches your files, works with the TODO board, schedules
jobs and, with your approval, changes things on the Mac. Three commands:

```bash
ula                     # console: streamed answers, tool calls, approvals
ula server              # Telegram bot + schedule in this terminal (Ctrl+C stops)
ula setup               # model, Telegram, allowed ids, folders, background mode
```

The console works like [pi](https://github.com/badlogic/pi-mono) and other CLI
agents: an input box with a status line, streamed answers with Markdown, tool
calls as they run.

```text
/            command menu (↑↓ choose, Enter or Tab picks, Esc closes);
             /model and /unschedule open a second menu with models or jobs
@            file menu; the picked file or image is attached to the message
!git status  run a shell command and share its output (!! keeps it to you)
/schedule    /schedule in 10m tea · /schedule завтра 9:00 позвонить (a reminder, no model)
Enter        send · Alt+Enter or Ctrl+J: new line · ↑↓: history
Esc          stop the agent · Ctrl+C: clear the input (twice: quit) · Ctrl+D: quit
```

Approvals are a picker: Yes, Yes for this kind of action until you quit, or No
(←→ and Enter, or `y` / `a` / `n`).

```bash
ula -p "what is in ~/Downloads that is older than a month?"   # answer once, print it
git diff | ula -p "review this change"                         # piped stdin is the message
ula -c                                                         # continue the last conversation
ula -m prism-ml/Ternary-Bonsai-2-27B-mlx-2bit                 # another model for this run
```

- Only local models: `ul lm serve` on 127.0.0.1, started when needed. Small
  models (2-4B, 2-bit) often answer without calling tools; `ula setup` and
  `/model` check whether a model calls them.
- Reading, listing and searching work only inside `agent.roots` (default `~`).
  SSH keys, `.env` files, the keychain and Unlaw's config are always blocked.
- Writing, editing, moving, deleting (to the Trash), shell commands and `ul`
  commands from `agent.commands` need approval: a picker in the console, Yes/No
  buttons in Telegram. No answer within `agent.confirm_timeout` seconds means no.
- Telegram: only `telegram.chat_id` (you, full access) and `agent.allowed_ids`
  get answers; others may only chat unless `agent.users.<id>` is `"read"` or
  `"full"`. In `ula setup`, typing ids adds them, `-id` removes one, Enter keeps
  the list. Voice messages are transcribed, photos go to a vision model, Markdown
  answers arrive formatted.
- Background mode (asked in `ula setup`) keeps `ula server` running through
  launchd, also after login; a second server for the same bot is refused.
- Schedule and today's list: `/schedule`, or ask in plain words ("remind me at
  9:00 to …"). Reminders arrive in Telegram as they are, tasks are run by the
  agent; both need a running server. Done/Completed columns count as finished. `agent.digest_time = "08:30"` sends today's list
  every morning.

```bash
ul config set agent.roots '["~/giti", "~/Documents", "~/Downloads"]'
ul config set agent.users.123456789 read
```

## Agent skills

`ul skills install` writes an Agent Skill (`SKILL.md`) that teaches
coding agents (Codex, Claude Code and others) to use `ul`.

```bash
ul skills install               # ~/.agents/skills/unlaw
ul skills install --claude      # plus a link in ~/.claude/skills
ul skills install --project     # ./.agents/skills/unlaw in the current project
ul skills list
ul skills show desk             # one command's reference page
ul skills remove
```

`SKILL.md` tells agents to discover commands live (`ul commands --describe`,
`ul <command> --help`), so new commands work right away. The `reference/`
snapshot is regenerated automatically after `ul update` and whenever commands
are added, changed or removed. Folders the skill did not create are never
overwritten.

## Local models (MLX)

`ul lm` is its own local model engine for Apple Silicon, replacing LM Studio and
Ollama: it downloads any model from Hugging Face and runs it with MLX — chat,
vision, embeddings, speech recognition and synthesis, music, images and video, in
the terminal and through an API compatible with OpenAI (like LM Studio) and Ollama.

```bash
ul lm search qwen3 --mlx                       # search Hugging Face
ul lm pull prism-ml/Ternary-Bonsai-2-9B-mlx-2bit
ul lm use Bonsai-2-9B                          # default model for its type
ul lm                                          # chat: /model /image /clear /save /think
ul lm "explain this code" < main.rs            # one-off streamed answer
ul lm -i photo.jpg "what's in the photo?"      # vision models
ul lm image "bonsai in morning light" --open   # images (mflux, Bonsai Image)
ul lm video "waves at sunset" --seconds 2      # video (mlx-video: Wan 2.x, LTX-2)
ul lm speak "Hello!" -m Qwen3-TTS --play       # speech synthesis (mlx-audio)
ul lm music "lo-fi piano" --lyrics song.txt    # music (MiniMax Music 3)
ul lm transcribe voice.m4a --srt               # speech to text; any format, even .mov
ul lm embed "text to search"                   # embeddings (JSON)
ul lm convert Qwen/Qwen3-4B --bits 4           # regular model → MLX 4-bit
ul lm list | info <model> | use <model>
ul lm rm [<model>...]                          # delete models from the Mac (no name — pick from a list)
ul lm clean                                    # partial downloads, orphaned files, download cache
ul lm open [<model>|models|generated|converted|engine|logs]   # show the folder in Finder
ul lm where <...>                              # same, but print the path
ul lm serve [--ollama] [--cors]                # API on 127.0.0.1:1234 until Ctrl-C
ul lm import-lmstudio [--dry-run]              # move LM Studio downloads over
ul lm doctor [--repair]
```

Connecting your own apps after `ul lm serve`:

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:1234/v1", api_key="local")
reply = client.chat.completions.create(model="Bonsai-2-9B",
                                       messages=[{"role": "user", "content": "hello"}])
image = client.images.generate(model="bonsai-image", prompt="a fox in the snow", size="512x512")
speech = client.audio.speech.create(model="Qwen3-TTS", voice="serena", input="Hello!")
```

OpenAI API: `/v1/models`, `/v1/chat/completions` (streaming, tools, images,
`reasoning_content`), `/v1/completions`, `/v1/embeddings`,
`/v1/audio/transcriptions` (json, text, srt, verbose_json), `/v1/audio/speech`,
`/v1/images/generations`, `/v1/videos` (a job; `GET /v1/videos/{id}` and
`/content`). Ollama API: `/api/tags`, `/api/chat`, `/api/generate`,
`/api/embed`, `/api/show`, `/api/ps`; `--ollama` additionally listens on `:11434`.
The server answers only on `127.0.0.1`, rejects foreign host names (DNS rebinding
protection), sends no CORS headers without `--cors` and never reads local files on
an API request. The `model` field accepts `owner/repo`, the repository name or
part of it; without it, the default model for that type is used (`lm.model`,
`lm.image_model`, `lm.tts_model`...). If the server is running, `ul lm` in the
terminal goes through it and reuses already loaded models.

Models are stored in the standard Hugging Face cache (`HF_HUB_CACHE`,
`HF_HOME/hub` or `~/.cache/huggingface/hub`) and are visible to `hf`, transformers
and other tools. `ul lm rm` and `ul lm clean` delete through huggingface_hub itself
(like `hf cache rm` / `prune`), so files shared with other models and datasets are
not affected; a default model that gets deleted is reset to auto. The model type is
detected from the model card and files: text, vision, embedding, stt, tts, music,
image, video. GGUF runs too: chat, vision (with an `mmproj` file) and embeddings
through a pinned official llama.cpp build (downloaded automatically, 16 MB,
sha256-verified), speech recognition (Parakeet, Whisper GGUF) through
transcribe.cpp. Among several quantizations, Q4_K_M is picked (otherwise Q5_K_M,
Q6_K, Q8_0); `ul lm info` shows which one. If both MLX and GGUF versions of a model
exist, the short name picks MLX. In a repository with a dozen GGUF files, `pull`
asks you to choose one.
Bonsai (1-bit, Ternary, Bonsai-2) runs without its own launcher; Bonsai Image runs
through PrismML's mflux library in a separate engine.

Engines install themselves on first use into `storage.root/runtime/lm-engine`
via uv on Python 3.13: the core one (about 1.2 GB: mlx, mlx-lm, mlx-vlm,
mlx-embeddings, mlx-audio, mlx-whisper, mlx-video), images (mflux) and Bonsai
Image — 1.5 GB each, only when needed. Chat, helper models, images and video run
in separate processes: embeddings don't wait for a long reply, and one crashing
doesn't affect the others. A model larger than 75% of RAM is rejected before
loading; models are unloaded after `lm.idle_minutes` of inactivity. Default
sampling parameters come from the model's `generation_config.json` (the authors'
recommendations), then from `lm.temperature`. There is no cloud fallback.

## Self-repair

```bash
ul doctor --verbose
ul doctor --json
ul doctor --fix
```

`--fix` adds missing settings (comments in `config.toml` are preserved), creates
directories inside `storage.root`, moves the old runtime log, puts the `ul`
binary's folder before `/usr/bin` and installs a managed Zsh function in
`~/.zshrc`. It is needed for `ul <template>` and `ul venv`, because only a
function in the current shell can do a persistent `cd` or `source`. Run
`exec zsh` after the fix.

## Project file templates

Files from `~/.config/unlaw/templates/python`, `rust` and `cpp` are layered over
the standard project. UTF-8 files support placeholders:

```text
{{project_name}}
{{cpp_standard}}
```

Binary files are copied unchanged. Placeholders also work in file and directory
names.

## macOS Harness

Harness remains an optional backend:

```bash
ul mac see Spotify
ul mac key Spotify cmd+k
ul mac type Telegram "hello"
ul mac click Spotify 500 300
```

User commands can call the same bridge through the CLI:

```python
import subprocess

subprocess.run(["ul", "mac", "key", "Spotify", "cmd+k"], check=False)
```

The executable and timeout are set in the `[mac]` section. `doctor` checks
Harness without requesting new macOS permissions.

## Zsh completion

```bash
mkdir -p ~/.zfunc
ul completion zsh > ~/.zfunc/_ul
```

Add before `compinit` in `~/.zshrc`:

```zsh
fpath=(~/.zfunc $fpath)
autoload -Uz compinit && compinit
```

Completion shows commands with descriptions, then subcommands of `config`,
`create`, `doctor` and so on. It is served by the Rust core (`ul _complete`);
Python is not started.

## Development

```text
Cargo.toml, rust/      Rust core: dispatcher, config, system commands, doctor
rust/build.rs          embeds data from Python via rust/gen_assets.py
ule/                   the ule editor (separate crate in the same workspace)
src/unlawful/          seeded command sources, their help and DEFAULT_CONFIG
tests/                 Python command tests and black-box binary tests
```

Seeded commands, their help, legacy hashes and the default configuration are
defined once in `src/unlawful`; `cargo build` exports them into the binary, so the
build needs Python 3.11+. The version in `Cargo.toml` must match
`src/unlawful/__init__.py`, otherwise the build stops.

```bash
cargo test --workspace
cargo clippy --workspace --all-targets
python3 -m unittest discover -s tests -v   # builds target/debug/ul itself
cargo build --release --workspace
```

Unlaw 3 stays local-first: commands don't use shell strings, `ul lm` listens only
on loopback and never calls cloud models, and the Telegram token is stored in the
macOS Keychain (a `TELEGRAM_BOT_TOKEN=` line in `.env` next to `config.toml` is read
only when the Keychain has none). External apps and permissions stay explicitly
visible through `ul doctor`.

### Command help and YouTube downloads

All built-in commands support `ul <command> --help`, `-h` and `ul help <command>`. Help describes the purpose, actions, options and examples without running the command. New commands from `ul create command <name>` also get a help handler; update its text when you change the command.

For downloads, install the external tools: `brew install yt-dlp ffmpeg deno`. Unlaw stays a package without Python dependencies. By default video is saved as MOV with audio; `--format mp4` picks MP4, `--format raw` keeps YouTube's source container and codecs (including WebM) without re-encoding. This is not camera RAW. Converting to MOV/MP4 uses H.264/AAC when the format has to change and may take a while. `--quality` sets an upper bound on height (if that quality isn't available, a lower one is picked); `--audio` saves MP3 and can't be combined with `--quality` or `--format`. The default location is `storage.root/youtube`; `--output` sets another folder. `--podcast` saves a speech-friendly MP3 (mono, 64 kbps, about 29 MB per hour, with title, channel and cover tags) straight into `yt.podcast_dir`, by default `iCloud Drive/Podcasts`, so the episode appears in the Files app on iPhone. If that folder's parent does not exist (iCloud Drive is off), the command fails instead of creating a local look-alike. A single video is downloaded, including Shorts links and videos from a playlist; links to entire playlists and channels are rejected. Existing files are never overwritten.

### YouTube subtitles and full bundle

```bash
ul yt download "https://youtu.be/VIDEO_ID" --sub           # subtitles only as .md, original language
ul yt download "https://youtu.be/VIDEO_ID" --sub-lang      # same thing
ul yt download "https://youtu.be/VIDEO_ID" --sub-lang ru   # pick Russian
ul yt download "https://youtu.be/VIDEO_ID" --full          # MOV with audio + separate MP3 + .md
ul yt download "https://youtu.be/VIDEO_ID" --full --sub-lang en --format mp4 --quality 1080
```

`--sub-lang` without a value picks the original; the flag itself enables subtitle mode, except with `--full`. An unknown code lists all available languages and exits before any media is downloaded. Authored subtitles take priority over automatic ones in the chosen language. When the original language can't be determined, the command says explicitly which available language it chose. The `.md` starts with the video link, followed by the title, language, subtitle source and text. Timestamps, markup and overlapping repeats are removed; the text is not paraphrased. Automatic captions may contain recognition errors. Subtitles need only `yt-dlp`, not `ffmpeg`.

`--full` saves files side by side in `storage.root/youtube` or the `--output` folder: the video in the chosen format with audio, a separate `.mp3`, and subtitles as `.<lang>.md`. The video is downloaded from YouTube once; audio is extracted locally. The `--sub`, `--audio` and `--full` modes are mutually exclusive. If there are no subtitles or downloading them fails, `--full` keeps the media, reports an incomplete result and returns a non-zero exit code. Existing files are kept, temporary files are removed.

## License

Copyright (C) 2026 Haos

Unlaw is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version
(`GPL-3.0-or-later`). This program is distributed WITHOUT ANY WARRANTY. See
[LICENSE](LICENSE) for the full text.
