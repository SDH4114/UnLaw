# Templates v2: working environments (design)

Date: 2026-11-10. Status: implemented on `feat/templates` (3.16.0).

## Goal
Describe a working environment once and start it with `ul <name>`: change the shell
to the project folder, open apps and place their windows, open Ghostty windows with
tabs and splits (each pane in its folder, optionally running claude/codex/a command),
open sites in the default browser.

## Decisions (agreed with Haos)
- Main way to create: snapshot of the open windows, then a checklist of which windows
  belong to the template (an app open by chance must stay out), which sites to keep,
  what each Ghostty pane runs, folder, focus mode. Hand-editing the TOML is the
  secondary way (`ul template edit`, starter file for new names).
- Launch with other windows: add-only by default, `--focus` / `focus = true` hides
  other apps (never closes), `--no-focus` overrides the file.
- Terminal: Ghostty with tabs and splits (Ghostty 1.4 AppleScript).
- Sites: the default browser. Safari/Chromium are scripted (tabs read by save, own
  window on launch); others (Zen, Firefox) get the links via NSWorkspace and `save`
  asks for links.
- Approach A: Rust core + one embedded JXA script (`rust/src/desktop.js`), JSON on
  stdin. Not a Python seed (two sources of truth with the shell integration), not
  macOS Harness (only `ul mac` may depend on it).
- Version 3.16.0, no other bump.

## Format
See `ul template --help` and README "Templates". Frames are fractions of the
display's usable area (presets or `[x, y, w, h]`), screen 1 = main. Old
`path`/`app`/`ai` files stay valid and launch as before.

## Errors
Missing folders stop before anything opens. A missing app, a window that never
appears, a missing display or a missing Accessibility permission are reported per
window; the others still open; exit 1. `--dry-run` only prints the plan.

## Tests
Rust unit tests (parser, presets, render round trip, plan, frame conversion, prompts)
and `tests/test_templates.py` with a fake osascript and `open`. The JXA side is
checked by hand on a real Mac.
