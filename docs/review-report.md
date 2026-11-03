# Review report — Unlaw 3.12.1 → 3.12.2

Done in two passes on 2026-11-03, both following `docs/codex-review-prompt.md`:

1. **Codex** (one main session and eight parallel audits: capture, desk, UI,
   games + zip, core, lm, Python commands, ule). It found and fixed the items
   marked *Codex* below with regression tests. It ran out of quota before it
   wrote this report, and it left one failing test without its fix.
2. **Claude** checked Codex's unfinished tree (build, every test, its diffs) and
   fixed one regression Codex introduced and the test it left failing. It then
   continued the audit of capture, desk/Studio, the page and the CLI, fixed what
   it proved, and wrote this report.

Every fix has a regression test. Codex's notes say its tests reproduced each bug
before the fix; Claude reproduced #4 live and wrote its tests against the cases
it found. All tests use fakes: no real devices, network, Telegram or `~/.config`.

## Findings

| # | Severity | Area | File | Problem | Evidence | Status |
|---|----------|------|------|---------|----------|--------|
| 1 | critical | lm | `rust/src/builtin/lm/server.rs` | Any web page could POST to the CLI-only `/ul/job` endpoint and run local-file jobs that overwrite files. | `test_lm.test_browser_cannot_submit_local_file_jobs` | Fixed (Codex): the endpoint requires `X-Unlaw-CLI: 1` and refuses any `Origin` |
| 2 | high | agent | `src/unlawful/agent.py` | `todo_add`, `todo_done`, `schedule` and `unschedule` changed state without approval, which breaks the "every change needs approval" rule. | `test_agent_safety.test_declining_model_mutations_keeps_todo_and_schedule_unchanged` | Fixed (Codex) |
| 3 | high | agent | `src/unlawful/agent.py` | A Telegram file name like `../../x` was written outside `telegram/downloads`. | `test_agent_safety.test_received_filenames_cannot_escape_downloads` | Fixed (Codex): only the base name is used |
| 4 | high | core | `rust/src/commands.rs` | **Regression introduced by Codex's fix #5.** With `core.command_timeout` set, a command in a terminal hung on `input()` and on terminal-mode changes (SIGTTIN/SIGTTOU) until the timeout. | Live pty run: `timeout=30` hung for 6 s with no output; `test_review_core.test_timed_command_owns_the_terminal` | Fixed (Claude): the command's group takes the terminal before `exec` and Unlaw takes it back afterwards (`Foreground`) |
| 5 | high | core | `rust/src/commands.rs` | A timed-out command left its child processes running. | `test_review_core.test_command_timeout_stops_spawned_children` | Fixed (Codex): own process group, killed as a group; Ctrl-C forwarded |
| 6 | high | capture | `src/unlawful/capture.py` | A failed start, Ctrl-C during start, or a failed state write left detached recorders running with no state to stop them. | `test_failed_start_stops_spawned_recorders`, `test_failed_resume_state_write_stops_the_new_recorder` | Fixed (Codex) |
| 7 | high | capture | `capture.py` | A save that failed (for example the camera overlay) left the state stuck at `saving` with no way to retry from the page; a missing screen part dropped the camera and microphone parts. | `test_a_failed_save_keeps_the_parts_for_another_try`, `test_missing_screen_preserves_secondary_recording_and_state` | Fixed (Claude + Codex): `unsaved` phase, parts kept, `stop` retries |
| 8 | medium | capture | `capture.py` | Ctrl-C while a recording was being saved left the phase at `saving` forever. | `test_ctrl_c_while_saving_keeps_the_recording_for_another_stop` | Fixed (Claude): any interruption marks it `unsaved` |
| 9 | medium | capture | `capture.py` | `record --duration/--wait` kept timing after a recorder died (display unplugged, device gone, disk full) and only stopped at the end of the duration. | `test_a_recorder_that_dies_ends_a_timed_recording_and_saves_it` | Fixed (Claude): it saves what exists at once and says why |
| 10 | medium | capture | `capture.py` | A failed or concurrent thumbnail/preview could leave a half-written JPEG, and the cache then served it forever. | `test_a_failed_thumbnail_or_preview_is_never_cached`; live check on the Mac | Fixed (Claude): written to a temporary file and renamed |
| 11 | medium | capture | `capture.py` | Two screenshots in the same second could overwrite each other. | `test_concurrent_screenshots_never_overwrite_each_other` | Fixed (Codex): file names reserved under `screenshot.lock` |
| 12 | medium | capture | `capture.py` | A relative `--output` was stored as given, so a `stop` run from another directory saved elsewhere; a partial state file crashed with a traceback; `delete` followed an absolute symlink. | `test_relative_recording_output_keeps_the_starting_directory`, `test_partial_recording_state_is_rejected_without_a_traceback`, `test_delete_refuses_an_absolute_symlink_to_a_capture` | Fixed (Codex) |
| 13 | low | capture | `capture.py` | `ul capture last --reveal` treated `--reveal` as a file name. | `test_library_open_copy_trim_convert_thumb_and_delete` | Fixed (Claude) |
| 14 | high | desk | `src/unlawful/desk.py` | A game that stopped reading its input blocked the input request and `stop` forever (pipe full). | `test_stalled_game_input_has_a_deadline_and_can_be_stopped` | Fixed (Codex): non-blocking writes with a 1 s deadline; a stuck game is stopped |
| 15 | medium | desk | `desk.py` | A Studio timeout killed `ul capture` but left its ffmpeg running; a missing binary lost the background save's error; parallel feature probes could report "not installed". | `test_studio_timeout_stops_helper_descendants`, `test_missing_capture_binary_finishes_the_background_save_with_an_error`, `test_parallel_feature_probes_do_not_report_missing_commands` | Fixed (Codex) |
| 16 | medium | desk | `desk.py` | A damaged `pomodoro.json` crashed the timer thread; a non-ASCII token crashed `hmac.compare_digest` and dropped the connection. | `test_partial_or_corrupt_pomodoro_state_recovers_to_idle`, `test_non_ascii_tokens_are_forbidden` | Fixed (Codex) |
| 17 | medium | desk page | `src/unlawful/desk_ui.py` | Camera/microphone permission requests that resolved after leaving the Studio (or during a recording) kept the device open; overlapping requests opened two streams; the wave animation outlived its stream. | `tests/test_desk_ui.cjs` (8 cases) | Fixed (Codex): request counters, streams stopped when stale |
| 18 | medium | desk page | `desk_ui.py` | A network error disabled the record button and game input until a reload; a failed save left the button stuck in "Saving"; a recording started in the terminal was not noticed while the Studio was open. | `tests/test_desk_ui.cjs` | Fixed (Codex) |
| 19 | low | desk page | `desk_ui.py` | Box-drawing corners `┌┐└┘├┤` were drawn with the wrong edges in the Games canvas. | `test_arcade_box_corners_and_tees_connect_the_correct_edges` | Fixed (Codex) |
| 20 | medium | games | `rust/src/builtin/game/mod.rs` | A record was saved only after the end screen was dismissed, so closing the page or the terminal lost it; two processes could save at the same moment and lose a best. | `test_completed_score_is_saved_before_end_screen_is_dismissed`; `arcade.lock` | Fixed (Codex): saved first, under a lock, reread inside the lock |
| 21 | medium | zip | `rust/src/builtin/zip.rs` | An input named `-x…` was read as an option by zip/tar; a `.tar.zst` was extracted as a single stream. | `test_dash_prefixed_inputs_remain_files_for_native_tools`, `test_zstandard_tar_is_detected_by_decompressed_content` | Fixed (Codex) |
| 22 | medium | core | `rust/src/layout.rs`, `lib.rs`, `system.rs`, `skills.rs` | An unreachable `storage.root` blocked even `ul config` (no way to fix it); a seed write cut short left a truncated command; `create command` followed a dangling symlink; installing one skill target hid a stale one. | `test_review_core.*` | Fixed (Codex) |
| 23 | medium | lm | `service.rs`, `store.rs`, `openai.rs` | Memory admission ignored models still loading and split GGUF shards; two video jobs with the same prompt in the same second wrote one file. | `test_lm` (3 new), unit tests in `service.rs` | Fixed (Codex): reservations, all shards counted, output named by job id |
| 24 | medium | ule | `ule/src/document.rs`, `editor.rs`, `jobs.rs`, `app.rs`, `complete.rs` | Reload decoded invalid UTF-8 lossily (saving then corrupted the file); a conflict warning reset the mtime so `:w` silently overwrote external changes; `:w other` overwrote existing files; job shells left children; empty/newline-only files changed on save; new files ignored the umask; a paste did not replace the selection; LSP completion left the old tail. | tests in `ule/src/*.rs` (`review_*`) | Fixed (Codex) |
| 25 | low | tg | `src/unlawful/telegram.py` | `tg download` downloaded a file again when its earlier copy had been saved as `name 2.ext` or renamed to `name 3.ext`. | `test_services.test_download_skips_numbered_copies_with_the_same_name_and_size` (written by Codex, left failing) | Fixed (Claude) |
| 26 | low | config | `src/unlawful/config.py` (seeds) | A key in `config.toml` that needs quotes was written unquoted, so the file became invalid TOML. | `test_review_seed_config.test_setup_preserves_quoted_unknown_keys_as_valid_toml` | Fixed (Codex) |
| 27 | low | agent | `agent.py` | Damaged schedules (non-list `jobs`, aware dates, unknown repeat) crashed the tick; reading a text file loaded the whole file before clipping. | `test_agent_safety` (3 cases) | Fixed (Codex) |
| 28 | low | tests | `ule/src/jobs.rs` | Codex's `review_stop_kills_job_descendants` sometimes read the pid file after it was created but before it was written, and failed. | Failed once in the full run (`parse` error at jobs.rs:534) | Fixed (Claude): the pid is written via rename and the test waits for it; 8 runs in a row pass |

The previous seed hashes of `agent`, `capture`, `desk` and `tg` are in
`LEGACY_SOURCE_HASHES` ("Pre-review 3.12.1 build"), so installed copies upgrade
by themselves. The catalog is regenerated.

## Optimizations

- **Studio start** (done in 3.12.1, measured): 1.3–1.8 s → 0.8 s on a MacBook Pro M3 Pro.
  `ffmpeg -list_devices` is skipped for `default`/`none`, and the start check
  takes 0.7 s. The screen preview pauses while recording.
- **Viewer waveform** (done): it redrew up to 1200 bars at 60 fps for as long as
  the viewer was open. It now redraws only when the position, trim or size changes.
- **Not done:** `library()` calls `ffprobe` once per new file (cached after
  that). The desk calls `ul capture status` (~60 ms of Python start-up) every
  1.5 s while recording. A long-running helper would be cheaper but is not
  worth the complexity at this rate.

## Confusing behaviour / UX

- `capture.audio_device = "0"` on the owner's Mac is BlackHole, not a microphone.
  `ul capture devices` and recordings now warn; the config is unchanged.
- The Studio's microphone wave comes from the browser's own device, which is
  matched by label and can differ from the device ffmpeg records.
- The `Foreground` fix means that with `core.command_timeout`, Ctrl-C reaches
  the command through the terminal directly, the same as without a timeout.

## Not implemented (suggestions)

- `runtime/thumbs` and `runtime/waves` are never pruned. They are small, but
  entries for deleted files stay forever. A cleanup on `library()` would fix this.
- If `recording.json` is damaged while recorders run, the state is reset and
  the detached recorders keep running (screen recording until it is killed). A
  `ul capture stop --force` that finds `screencapture -v` and avfoundation
  ffmpeg processes by command line would cover this rare case.
- Segments with different stream layouts (for example one segment where the
  camera failed) are joined with `-c copy` and may play badly. Re-encoding when
  the probes differ would fix it at the cost of speed.
- Studio availability is probed once; if the first probe times out (15 s), the
  tab stays "not installed" until the desk restarts.
- `ruff check src tests` reports issues that were already there before this
  review: import order in seed sources, which the seed generator relies on, and
  older tests. No new ones were added. These were left alone on purpose, since
  a mass reformat would go against the review rules.
