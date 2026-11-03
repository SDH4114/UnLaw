# Codex review prompt

Paste everything below the line into Codex, started in the repository root.

---

You are reviewing **Unlaw**, a macOS CLI (Rust core `ul` + standalone Python
stdlib command seeds + the `ule` editor crate). Do a deep, skeptical audit of the
whole project — old features and the new ones — and report real problems with
evidence. Do not rewrite the project.

## Read first

1. `AGENTS.md` — project rules and architecture (trust it, but if it contradicts
   the code, the code wins; report the mismatch).
2. `docs/desk-games-studio.md` — what changed most recently (desk games,
   rewritten `ul capture`, desk Studio, 3.12.1 fixes). These are the
   highest-risk areas.
3. `README.md` for user-facing behavior.

## Scope and priority

Highest priority (new, large, little real-world use yet):
- `src/unlawful/capture.py` — recording state machine (`recording.json` +
  flock), segments, pause/resume, stop/save, signal handling of detached
  recorders, ffmpeg/screencapture command lines, library actions, CLI parsing.
- `src/unlawful/desk.py` — `Arcade` and `Studio` relays, HTTP routes, token/Host
  checks, `/media/*` (ranges, path containment), threads, subprocess timeouts.
- `src/unlawful/desk_ui.py` — the page's JS (Studio, Games, board): state
  races, timers/intervals that leak, rendering cost, Web Audio usage, error paths.
- `rust/src/builtin/game/stream.rs` and `rust/src/builtin/game/mod.rs`
  (`--stream`, `Scores::reload`).

Then everything else: dispatcher and config (`rust/src`), validators that must
stay identical (`rust/src/config.rs` vs `src/unlawful/config.py`), seed
migration/legacy hashes (`command_sources.py`, `rust/src/layout.rs`), `ul update`
/ `reinstall` / `remove`, catalog, skills, `ul lm`, `ul agent`, `ule`, `ul zip`,
`yt`, `tg`, `todo`.

## What to look for

1. **Crashes and unhandled failures:** exceptions/panics on missing tools,
   permissions denied, devices unplugged mid-recording, full disk, broken or
   partial state files, killed processes, closed pipes, non-UTF-8 paths/names,
   empty or huge inputs, concurrent runs (two terminals, terminal + desk).
2. **Logic errors:** wrong state transitions (pause while saving, stop while
   starting, resume after a recorder died, `interrupted`/`unsaved` phases),
   off-by-one in time/ranges, clock drift, wrong audio/video alignment,
   files overwritten or lost, cleanup that deletes the wrong thing,
   behaviour that differs between the terminal and the desk.
3. **Security:** path traversal or symlink escapes (`/media/*`, delete, trash,
   catalog writes, agent tools), token leaks, missing Host/CSP checks, command
   injection through arguments, anything written outside the config/storage dirs.
4. **Resource leaks and performance:** zombie or orphaned processes (games,
   recorders, llama.cpp servers), threads that never end, unbounded memory
   (frames, waveforms, logs, caches), polling that costs too much, work done on
   every request that could be cached, slow paths in startup (`ul` runs often).
   For the desk Studio specifically: the user reported that recording **starts
   late and feels laggy** — find any remaining cause (server, page or recorder
   settings) and measure, don't guess.
5. **Things that are illogical or confusing for a user:** misleading messages,
   help text that does not match behaviour, defaults that surprise, missing
   `--help`/`-h`, inconsistent flags between commands.
6. **Project rules broken:** see `AGENTS.md` (seeds stay standalone, legacy
   hashes registered for changed seeds, catalog regenerated, versions in sync,
   tests never touch the network/real tools/real `~/.config`, Rust and Python
   validators identical).

## How to work

- Read the code, then **prove** each finding: a failing test, a command you ran,
  or a precise code path with line numbers. No speculative findings.
- Run the checks (all must pass before and after any change):
  ```bash
  cargo test --workspace
  cargo clippy --workspace --all-targets
  cargo clippy --no-default-features --all-targets
  python3 -m unittest discover -s tests -v
  ruff check src tests
  ```
- Never run real recordings, real Telegram, real models or the network in
  tests; use the existing fakes (`FAKE_*` tools in
  `tests/test_command_paths.py`, `tests/ulbin.py`, local fake servers). Never
  touch the real `~/.config/unlaw`: set `HOME` and `XDG_CONFIG_HOME` to a temp
  dir for any manual run.
- Core Rust files are not rustfmt-formatted: edit them without reformatting the
  whole file (only `ule/` uses rustfmt).

## Fixing

- Fix only bugs you proved, with the smallest correct change and a regression
  test for each. Do not refactor, rename or restyle working code.
- If you change a seeded command's source (`src/unlawful/*.py` that ends up in
  `commands/<name>/main.py`), first add the previous hash to
  `LEGACY_SOURCE_HASHES` in `src/unlawful/command_sources.py`, then regenerate
  the catalog: `python3 -I rust/gen_assets.py --catalog src catalog`.
- Do not bump the version, commit or push; leave that to the owner.

## Report format

Write the report to `docs/review-report.md` and summarize it in chat:

| # | Severity (critical/high/medium/low) | Area | File:line | Problem | Evidence | Status (fixed + test / not fixed + why) |

Then three short lists: **optimizations worth doing** (with measured or
estimated gain), **confusing behaviour / UX**, **suggestions you did not
implement**. Be concrete and brief; no generic advice.
