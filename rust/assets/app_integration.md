# Commands in Unlaw.app (menu bar, palette, hotkeys)

Unlaw.app (`ul gui`) runs the same commands as the terminal. Every command appears in the
palette (default hotkey Ctrl+Space) and can be pinned to the menu bar with no extra work:
it then has a "Run" action and "Run in terminal". To give it a better face, put an
`app.toml` next to its entry file (`commands/<name>/app.toml`). Nothing in Unlaw itself
changes, and the app never runs a command to find out what it is: it only reads this file.

The app runs your command exactly like `ul <name> <args>` (same config, aliases and
timeouts), with stdin closed and `UNLAW_APP=1` in the environment. A command that asks
questions or draws a terminal UI must say `terminal = true`.

```toml
# commands/<name>/app.toml (every key is optional)
title = "Awake"                # default: the command name
icon = "cup"                   # an icon of the app (list below); default "command"
summary = "Keep the Mac awake" # default: the command's description
terminal = false               # true: prompts or TUI, so the app opens it in your terminal

[[action]]                     # entries in the palette and in the menu bar item's menu
id = "2h"
label = "Keep awake 2 h"
args = ["2h"]                  # runs `ul <name> 2h`
# confirm = "Really?"          # ask before running

[panel]                        # a form, shown when the command is opened
[[panel.field]]
id = "time"
type = "choice"                # choice | toggle | text | number | duration | time | date
label = "For"
options = ["30m", "1h", "2h"]  # choice only
default = "1h"                 # toggle: true/false
[[panel.field]]
id = "screen"
type = "toggle"
label = "Screen on"
default = true
[[panel.button]]
label = "Start"
args = ["{time}", "{screen?:--no-display}"]

[status]                       # live text in the menu bar while the command is pinned
args = ["status", "--json"]    # what to run
every = 15                     # seconds, at least 2
text = "{remaining_seconds|clock}"
when = "active"                # if this JSON value is false/empty/null, show `otherwise`
otherwise = "off"

[open]                         # the command serves a page (like `ul desk`)
args = ["--no-open"]           # the app shows the first http://127.0.0.1 or http://localhost
                               # URL the command prints in its own window, and stops the
                               # command when the window's app quits
```

## Placeholders in `args`

Field values reach the command only through placeholders; each argument stays one
argument (spaces, quotes and dashes are passed as they are, never through a shell).

| Write | Becomes |
|---|---|
| `{time}` | the field's value |
| `{lid?--lid}` | `--lid` when the field is on/non-empty, else nothing |
| `{screen?:--no-display}` | nothing when on, `--no-display` when off |
| `{a?yes:no}` | `yes` or `no` |
| `--at={time}` | text around a placeholder is kept |
| `{{` `}}` | literal braces |

An argument that ends up empty is left out, so optional fields simply disappear.

## Status text

Without `text`, the status is the `"text"` key of a JSON object the command prints, or
its first line. With `text`, `{path}` takes a value from the JSON output (`cpu.usage_percent`,
`items.0.name`) and a filter may follow: `|int` (rounded), `|pct` (rounded, with %),
`|clock` (seconds as `1:24` or `12:05`), `|gb` (bytes as `12.3 GB`). A JSON key `"state"`
(`on`, `off`, `warn`) tints the item. Keep it short: at most 40 characters are shown.

## Icons

`command`, `cup`, `cpu`, `board`, `clock`, `clipboard`, `cloud`, `music`, `play`,
`camera`, `record`, `download`, `git`, `terminal`, `folder`, `code`, `chat`, `spark`,
`game`, `archive`, `globe`, `app`, `bolt`, `gear`.

## Checking

`ul-app --check` (or `ul config check`, which runs it) validates the app settings and
every `app.toml`; a broken file only disables that command's extras in the app.
