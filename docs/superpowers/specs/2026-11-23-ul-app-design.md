# Unlaw App design (menu bar, hotkeys, palette)

Date: 2026-11-23. Status: draft for Haos's approval.

## Revision 2026-11-23 (before coding; supersedes the parts below where they differ)

- **Descriptions are files, not flags.** A command is never run to learn what it is
  (AGENTS.md: descriptions never come from running a command, and a user command that
  does not know `--ul-ui` could take it as an argument and act). A command describes
  itself in `commands/<name>/app.toml` next to `main.py`; shipped commands get their
  description embedded in the app (`app/defaults/<name>.toml`), which a sidecar file
  overrides. So no seed changes, no seed-hash churn, updates come with the app.
- **Status runs the command's own JSON/text mode** declared in that file
  (`[status] args = ["status", "--json"]`, `text = "{remaining_seconds|clock}"`): awake
  and sys already have `--json`, so nothing new is needed in them. Plain stdout (first
  line) and `{"text": ...}` work too, for user commands.
- **Names:** `app` is already the builtin `ul app Safari`, so the system command is
  `ul gui`, the feature `gui`, the package `unlaw-app` (folder `app/`), the binary
  `ul-app`, the LaunchAgent `com.unlaw.gui`, the bundle `Unlaw.app`.
- **Skills:** canonical `~/.agents/skills/unlaw` is read by Codex, OpenCode, Gemini CLI,
  Kimi Code and Copilot CLI (their docs); Claude Code needs the link in
  `~/.claude/skills` (Cursor and the old Kimi CLI read that one too). `ul skills install`
  links every detected agent that does not read `~/.agents/skills`; install.sh and
  `ul update` run it.
- **Config link:** `ul config check` also checks app.toml by running `ul-app --check`
  when installed (the app owns its schema; no duplicate validator in the core).

## Intent

Unlaw has been a CLI only. Haos wants a desktop app that is always running, so the
things he does many times a day take one key or one click instead of a terminal:
keeping the Mac awake, watching system stats, opening his desk. The CLI and the app are
two halves of one product: every command works in both, some exist for one side only,
and installing either half installs the other.

The key requirement is the contract for command authors (Haos, other users, AI agents):
a command is still a plain `commands/<name>/main.py` (or `.sh`, `.js`, `main`). It can
describe in its own code how it looks in the app, and works in the app correctly
without anyone touching the Unlaw core.

## Goals

1. **Menu bar.** A `UL` item with the general menu, plus any command pinned as its own
   item. Every command can be pinned, user commands included.
2. **Global hotkeys.** One opens the palette; others run a command or open its panel.
   All configurable.
3. **Palette.** Spotlight-like list of all commands and their actions, fuzzy search,
   Enter runs, Tab/→ opens the command's panel (form).
4. **Panels.** A command can declare a form (fields, toggles, presets, buttons). Example:
   awake = duration presets, "until" time, display on/off, lid, Start/Stop.
5. **Live status.** A pinned command can show text in the menu bar that refreshes
   (sys: `CPU 14% · RAM 61%`; awake: time left).
6. **Open a window.** A command can ask the app to open a page in an app window
   (desk: the board, Today, Canvas... in the app, not a browser tab).
7. **Look.** Flat, glass-like (system blur under translucent panels), Unlaw's amber
   accent, light and dark.
8. **Install linkage.** `install.sh`/`ul update` also build and install
   `/Applications/Unlaw.app`; the downloadable `.app` installs the CLI on first start.
9. **Existing commands app-ready.** Every shipped command gets a fitting app description
   (see "Existing commands").
10. **Skills for every agent.** On install and every update, the Unlaw skill (how to use
    `ul`, how to write commands and the app API, never touch the core) is placed for all
    AI agents found on the Mac.

## Non-goals (this round)

- Linux and Windows builds. The code is written so they can follow (platform bits behind
  one module), but nothing is built or tested there now.
- Updating an app-only install without a Rust toolchain (binary self-update). Until then
  `ul update` needs cargo, as today.
- Notarization/signing with an Apple Developer ID (Haos has no account).
- Rewriting desk's UI; the app only hosts the existing page.
- Performance rewrites of commands.

## Anti-goals (a failure even if it works)

- A command author has to edit Rust, the app, or a registry to get into the app.
- The app runs a command's code to find out what it is (side effects) beyond the
  documented `--ul-ui` / `--ul-status` calls.
- Command output or config text reaches the page as HTML (desk rule: textContent only).
- GUI dependencies leak into the `ul` binary.
- The app breaks or hangs because one command is slow, broken or interactive.
- Seeds stop being standalone, or an edited user command gets overwritten.

## Constraints from the project

- Rust, no Swift (memory: cross-platform plan). macOS specifics behind a backend layer.
- Core `ul` deps stay as they are: the app is a **separate crate in the workspace**
  (`app/`, binary `ul-app`), like `ule`. Same version as Unlaw (test reads root
  Cargo.toml). Cargo feature / `core.features` entry `app` (default on).
- Seed rules from AGENTS.md: changed seeds need their previous hashes in
  `LEGACY_SOURCE_HASHES`, `catalog/` regenerated, a seed's `--help` stays static, every
  new flag documented in help. The same applies to `--ul-ui`: its output must be static
  (no config/env), so it can be cached by file hash.
- Tests never touch the network, real windows, real hotkeys or real launchd.
- Unsigned app: the locally built one (cargo, no quarantine attribute) opens normally;
  the downloaded zip needs one "Open Anyway" in System Settings the first time. README
  says so; ad-hoc `codesign -s -` is applied so it runs on Apple Silicon.

## Approaches considered

1. **Rust + webview (chosen by Haos).** `tao` (windows, event loop), `wry` (WKWebView /
   WebView2 / WebKitGTK), `tray-icon` (menu bar), `global-hotkey`; system blur under a
   transparent webview (`window-vibrancy` or our own NSVisualEffectView call via objc2).
   Native menu bar items and hotkeys, every panel and the palette in HTML/CSS, one UI
   for three OSes, and desk is already a page. Cost: blur on Linux is weak; the macOS 26
   "lens" refraction is approximated, not exact.
2. **Native AppKit via objc2.** Most native look, real system glass on macOS 26, but
   every form and panel written per OS and desk still needs a webview. Rejected: the port
   would be a rewrite.
3. **Pure-Rust GPU UI (egui/iced).** No glass, still needs native calls for blur and a
   webview for desk. Rejected.

## Design

### Parts

```
app/                      crate `ul-app` (binary ul-app)
  src/main.rs             event loop (tao), single instance, login job
  src/tray.rs             menu bar items (tray-icon), status refresh scheduler
  src/hotkeys.rs          global-hotkey registration from app.toml
  src/commands.rs         list commands (`ul commands --describe --json`), fetch and
                          cache `--ul-ui`, run actions, collect results
  src/windows.rs          palette, panel and page windows (wry), IPC whitelist
  src/platform/macos.rs   blur, activation policy (no Dock icon), open URL, notify
  ui/                     palette.html, panel.html (+css/js), embedded
```

The app never runs command code itself: it calls `$UNLAW_BIN <cmd> ...` like a user
would, so dispatch, aliases, config, timeouts, user overrides all stay in `ul`.

### The app protocol (the "ul API")

Two optional flags any command may answer. A command that does not know them still
works in the app (see "Commands without a description").

**`<cmd> --ul-ui`** prints one JSON object, static, no side effects, fast (the app kills
it after 3 s and caches the answer by entry-file hash + mtime):

```json
{
  "ui": 1,
  "title": "Awake",
  "icon": "cup",                       // name from the app's built-in icon set, or "text:UL"
  "status": {"every": 15, "args": ["--ul-status"]},
  "actions": [                          // shown in the palette and the item's menu
    {"id": "2h", "label": "Keep awake 2 h", "args": ["2h"]},
    {"id": "off", "label": "Let it sleep", "args": ["off"]}
  ],
  "panel": {                            // the glass form; optional
    "fields": [
      {"id": "dur", "type": "choice", "label": "For", "options": ["30m","1h","2h","on"], "default": "1h"},
      {"id": "until", "type": "time", "label": "Until"},
      {"id": "display", "type": "toggle", "label": "Screen on", "default": true},
      {"id": "lid", "type": "toggle", "label": "Lid closed"}
    ],
    "submit": [
      {"label": "Start", "args": ["{until?until}", "{dur}", "{display?:--no-display}", "{lid?--lid}"]},
      {"label": "Stop", "args": ["off"]}
    ]
  },
  "open": null,                         // or {"args": ["--no-open", "--ul-url"]}: prints a URL to show in an app window
  "terminal": false                     // true: interactive, run it in the terminal app
}
```

Field types for v1: `choice`, `toggle`, `text`, `number`, `duration`, `time`, `date`.
Placeholders in `args` are the only way field values reach argv: each value becomes one
argv element (never split, never through a shell); `{x?a:b}` picks by truthiness; an
empty placeholder drops the element. The app validates the JSON strictly (unknown keys
refused, caps on sizes and counts) and shows a readable error instead of a panel.

**`<cmd> --ul-status`** prints one JSON line `{"text": "1:24", "tooltip": "...",
"state": "on|off|warn"}` (text ≤ 40 chars, control characters stripped). Called every
`status.every` seconds (min 2) only while the command is pinned, never two at once for
one command, killed after 10 s.

**Results.** An action runs `ul <cmd> <args>` with no TTY, stdin closed, env
`UNLAW_APP=1`. If it prints a JSON object with `"ul_result": 1` (`{"message", "level",
"open"}`), the app shows that; otherwise the last lines of stdout/stderr go into a
toast, exit code ≠ 0 = error toast with the output. `terminal: true` commands and any
command without a description that the user runs with arguments open in the terminal
(`apps.terminal`, default Ghostty if installed, else Terminal) via the existing
template/launcher code.

**Python helper.** For authors who prefer code to JSON, the app ships
`<config dir>/lib/unlaw_app.py` (refreshed on update, never edited by users) and the
dispatcher puts `<config dir>/lib` on `PYTHONPATH`. It builds the same JSON:

```python
from unlaw_app import ui, choice, toggle, time, action
if ui.wants_description():
    ui.describe(title="Awake", icon="cup", status_every=15,
                panel=[choice("dur", "For", ["30m","1h","2h","on"], "1h"), toggle("display", "Screen on", True)],
                submit=action("Start", "{dur}", "{display?:--no-display}"))
```

Shipped seeds do NOT import it (they stay standalone); they print the JSON directly.

**Commands without a description** get a default entry: title = name, description from
`ul commands --describe`, one action "Run" (no arguments; output in a toast), and
"Run in terminal…". Pinning works; the item shows the icon and the menu.

### Config: `<config dir>/app.toml`

Separate file (like `ule.toml`), so `config.toml` validators stay untouched; written with
toml_edit, comments kept; `ul app config` opens it in `ul edit`, the app reloads on
change.

The two files are linked (Haos: they must work together and pull from each other):
`config.toml` stays the source for everything shared (storage.root, apps.*, desk.*,
awake/timer defaults, core.features); app.toml holds only app settings and never
duplicates a config.toml key. The app reads config.toml through `ul config get --json`
and watches both files; commands run from the app see the same config.toml as in the
terminal. `ul config check` also validates app.toml; `ul doctor` has an App row; an
`[app]` link back: `ul config set` of a key the app shows (e.g. `desk.port`) is picked up
by the app on its next reload. Removing `app` from `core.features` stops and removes the
app; adding it installs it.

```toml
[hotkeys]
palette = "ctrl+space"
[[hotkey]]
keys = "ctrl+alt+a"
command = "awake"        # opens its panel
[[hotkey]]
keys = "ctrl+alt+d"
command = "desk"
action = "open"          # or an action id from --ul-ui, or args = ["2h"]

[menubar]
items = ["sys", "awake", "desk"]   # order left to right; "ul" is always last
show_status = true

[look]
theme = "auto"           # auto | light | dark
```

Pinning from the app (right click in the palette → "Pin to menu bar") writes
`menubar.items`. A hotkey string that cannot be registered (taken by the system) is shown
as a warning in the UL menu, the rest still work.

### UI

- **Palette**: centered borderless window, 640 px wide, blurred background, search field,
  list of commands then their actions, keyboard only (↑↓ Enter Tab Esc), ⌘, = settings.
- **Panel**: popover-like window under its menu bar item (or centered from a hotkey),
  fields from the description, primary button = first submit; live status at the top.
- **Page window**: normal window with a webview for `open` URLs (desk); one per command,
  reused.
- Look: system blur (NSVisualEffectView, material popover/HUD) under a transparent
  webview, 14 px radius, hairline border, no heavy shadows, amber `--accent` and the
  desk tokens (`--on-accent`, `--accent-ink`) so desk and the app match; SVG stroke icons,
  never emoji. Everything from commands is set with textContent.
- IPC from pages to Rust is a whitelist (`run`, `submit`, `pin`, `close`, `open`), with a
  per-window token; page windows that show desk get no IPC at all.

### Install and lifecycle

- **CLI → app**: `install.sh` and `ul update` (when `app` is in `core.features`) run a
  third `cargo install --git … ul-app` into the same root, then `ul app install` builds
  `/Applications/Unlaw.app` (Info.plist with `LSUIElement` true = no Dock icon,
  executable copied from `$root/bin/ul-app`, icon from `assets/logo.svg` via
  `sips`+`iconutil`, `codesign -s -`), writes the LaunchAgent `com.unlaw.app`
  (RunAtLoad, KeepAlive on crash only) and starts it. If `/Applications` is not
  writable, `~/Applications`.
- **App → CLI**: a release zip (`Unlaw.app` with `Contents/Resources/bin/{ul,ule,ul-rec}`,
  arm64, built by a script in the repo, published by Haos manually). On start, when
  `ul` is not on PATH and not in `~/.local/bin`, the app shows "Install the command
  line?" and copies the binaries to `~/.local/bin`, runs `ul doctor --fix` and `ul init`.
  It never overwrites a newer `ul`.
- `ul remove` and `ul features remove app` boot out `com.unlaw.app` (add it to
  `COMMAND_JOBS`) and delete the app bundle it installed (marker file inside the bundle,
  so an unrelated `Unlaw.app` is never deleted).
- System command `ul app [install|start|stop|status|config]`.

### Existing commands

Each shipped seed answers `--ul-ui` (static JSON) and, where it makes sense,
`--ul-status`:

| Command | In the app |
|---|---|
| awake | panel as above; status = time left / "off"; actions 30m, 1h, 2h, on, off |
| sys | status = `CPU x% · RAM y%` (uses a lighter one-sample path for status, CPU from the last sample); panel = summary (read-only fields, `type: "info"`) |
| desk | `open` = board page in an app window; actions add card (text field), Today, Canvas; status = cards in the current column |
| timer | panel: duration + text, Start; status = nearest timer; actions list/cancel |
| clip | palette action = recent items, Enter copies; status off by default |
| weather | status = temp + icon (every 30 min); panel = forecast |
| music, gpt, claude, obsidian, lofi, netflix, steam, minecraft, zed, work | single "Open" action |
| yt | panel: URL + format + audio/subs toggles |
| git | `terminal: true` (needs a folder and prompts) |
| capture | actions screenshot, record screen, stop; status = recording time |
| tg, agent, py, rust, cpp, mac | `terminal: true` |
| game, lm, zip, app, browser (Rust builtins) | description built into `ul` (`ul <builtin> --ul-ui`); game/lm → terminal |

Seed help documents the two flags in a "App:" line.

### Skills for every agent

`ul skills install` keeps the canonical copy in `~/.agents/skills/unlaw` and links it
into every agent's skills folder that exists (agent installed = its config folder
exists): Claude Code `~/.claude/skills`, Codex, OpenCode, Kimi and others **at paths
verified from each tool's current docs before coding** (not verified yet). Only
folders/links carrying the `.unlaw-skill` marker are written or removed. install.sh and
`ul update` run it at the end; `refresh_if_stale` keeps the content current. The skill
gains `reference/app.md` (the protocol above and the Python helper) and states plainly:
write commands in `commands/<name>/`, never edit Unlaw's sources, binaries or seeds of
other commands.

## Order of work

1. Skills for every agent (small, independent).
2. Protocol + `ul-app` skeleton: tray, palette, hotkeys, default entries, app.toml.
3. Panels, status, results; awake and sys first (Haos's daily use).
4. desk page window; remaining commands.
5. Install linkage both ways, `ul app`, remove/update, docs (README, AGENTS.md, authoring).

## Calls made by Claude (check these)

- App config in its own `app.toml`, not `config.toml`.
- Default palette hotkey `ctrl+space` (Haos's choice).
- Protocol flags `--ul-ui` / `--ul-status`, JSON on stdout, cached by file hash.
- Shipped seeds print JSON directly; the Python helper is for user commands.
- Login via LaunchAgent `com.unlaw.app`, like the other Unlaw jobs.
- Release zip is arm64 only, built and uploaded by hand.
- "Optimize all existing commands" read as: make every shipped command app-ready.

## Left to the builder

Icon set contents, exact window sizes and animations, status refresh scheduler details,
toast design, how `sys` gets a cheap status sample, the release-zip script, crate
versions (check current releases of tao/wry/tray-icon/global-hotkey and that
`global-hotkey` needs no Accessibility permission on macOS).
