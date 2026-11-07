# Desk games and studio, new `ul capture` (3.11.0–3.12.2)

The review of this batch (3.12.2) and every fix it made: `docs/review-report.md`.

What changed in this batch, why, and where it lives. Written for reviewers and
for the next session; `AGENTS.md` keeps the short rules.

## 1. Games in `ul desk` (3.11.0)

Goal: every `ul game` arcade game (Tetris, Snake, Minesweeper, Space Invaders,
Chomp, Dash) playable in the browser with the same best scores as the terminal.

- **No second implementation.** The page never reimplements a game. `ul game
  --stream [--size RxC]` (`rust/src/builtin/game/stream.rs`) is a `Screen`
  implementation that speaks JSON lines instead of drawing to a terminal:
  - stdin, one object per line: `{"key":"up"}`, `{"click":{"y","x","button"}}`,
    `{"hover":{"y","x"}}`, `{"resize":{"rows","cols"}}`; malformed lines are ignored;
  - stdout: a full frame `{"rows","cols","lines":[[[text,fg,bg,flags],…],…]}`
    as same-style runs, written only when it differs from the last frame;
  - closed stdin ends the game (`Interrupted`/`BrokenPipe` exit 0).
- **Shared records.** `Scores::reload()` rereads `storage.root/runtime/arcade.toml`
  before every menu, game and record, so the terminal and the desk (separate
  processes) never overwrite each other's bests.
- **Relay** (`Arcade` in `src/unlawful/desk.py`): at most one game process per
  desk, own process group, validated game/level/size. Frames go to the page over
  `POST /api/game/stream` (fetch streaming, so the token stays in a header); one
  reader per session; a blank keep-alive line every 2 s detects a closed page,
  which kills the game. Input is batched through `/api/game/input` and
  re-serialized from a whitelist (`_game_event`). `/api/games` reads the records.
- **Page** (`src/unlawful/desk_ui.py`): canvas renderer of the cell grid;
  box-drawing characters become lines and block characters pixel-snapped
  rectangles; the grid aims at 30 rows × up to 116 columns. Leaving the tab or
  hiding the page pauses the game.
- **Design refresh:** header with board picker, tabs Board/Today/Stats/Games/Studio
  (keys 1–5), toolbar with search and summary pills, `?` help sheet.

## 2. `ul capture` rewritten (3.12.0)

Goal: screenshots, screen/camera/audio recording that any user can run without
knowing device numbers, plus pause, a library and simple edits.

- **Engine:**
  - screenshots and screen recording use macOS `screencapture`
    (`-v` video, `-D` display, `-R` rect, `-k` clicks, `-A` system audio,
    `-g` default microphone) — no BlackHole needed for the Mac's sound;
  - ffmpeg avfoundation records the camera (nv12 1280×720, 30 fps,
    `h264_videotoolbox`), audio-only recordings and any microphone that is not
    the system default. Devices are `default`, `none`, an index or a name
    (exact or unique substring), resolved from `ffmpeg -list_devices`;
  - `ul capture devices` lists displays (`system_profiler`), cameras and
    microphones and flags virtual ones (BlackHole, Teams, …).
- **Recording state:** detached recorders, `runtime/recording.json` (plan,
  segments, pids, phase) under `runtime/recording.lock` (flock). Phases:
  `recording`, `paused`, `saving`, `interrupted` (a recorder died), `unsaved`
  (saving failed; parts kept, `stop` retries).
- **Pause/resume** stop the current segment and start a new one; parts live in
  `captures/.parts/<stem>-<hash>/`.
- **Stop:** every segment is finished (camera overlay in the configured corner,
  22 % width, or the separate microphone mixed in), aligned by end time because
  all recorders stop together (`-itsoffset`), segments are joined with concat
  `-c copy`, remuxed to MP4 with `+faststart` if asked, then the parts are removed.
- **Signals:** recorders get SIGINT/SIGQUIT reset to default before exec
  (`_default_signals`): a parent that ignores Ctrl-C made `screencapture`
  unstoppable and the file was lost. Stopping escalates SIGINT (15 s) → SIGTERM
  (5 s) → SIGKILL; a pid is only signalled while `ps -o command=` still shows the
  tool, so a reused pid is never hit.
- **Start check:** the recorders must survive 0.7 s, otherwise the log tail and
  a Privacy & Security hint are reported. The clock starts when the recorders
  are spawned, not after this check.
- **Library:** `list`, `last`, `open`, `reveal`, `copy` (clipboard), `delete`
  (to `~/.Trash`, only inside the captures folders), `trim` (input seek + exact
  re-encode), `convert` (GIF with palette, MP3/M4A/WAV, MP4/MOV remux when the
  codecs allow), `thumb` (cached in `runtime/thumbs`), `preview` (display
  snapshot for the desk), `wave` (loudness bars, cached in `runtime/waves`).
- **CLI:** `ul capture` alone opens a numbered menu on a TTY; `record
  --duration N` records in the foreground with a live timer (Enter stops, `p`
  pauses, Ctrl-C saves); old one-word actions (`screenshot`, `area`, `screen`,
  `audio`, …) still work; every action has `--json` for the desk.
- **Config** (`[capture]`, validated identically in `rust/src/config.rs` and
  `src/unlawful/config.py`): `camera_device`, `audio_device` (default
  `"default"`), `screen_audio`, `system_audio`, `show_clicks`, `video_format`
  (mov/mp4), `audio_format` (m4a/mp3/wav), `overlay` (four corners).

## 3. Studio tab in `ul desk` (3.12.0–3.12.1)

Goal: an OBS-like page on top of the same recordings as the terminal.

- **Server** (`Studio` in desk.py) only runs `$UNLAW_BIN capture … --json` with
  validated arguments, so the terminal and the page share one recording and one
  library. `stop` runs in a thread (saving can take minutes) and reports through
  `/api/studio/status` → `saving_done`.
- **Routes:** GET `/api/studio`, `/status`, `/devices`, `/library`, `/wave`;
  POST `/record`, `/pause`, `/resume`, `/stop`, `/shot`, `/action`
  (open, reveal, copy, delete, trim, convert). Media for `<img>/<video>/<audio>`:
  `/media/file|thumb|preview` with the token as `?t=` (media elements cannot send
  headers), byte ranges (206/416) for seeking, and only files directly inside
  `captures/{screenshots,recordings}` (no symlinks, no `..`).
- **Page:** modes Screen / Screen + Cam / Camera / Audio, display, camera,
  microphone, system audio, clicks, format; big record button (`r`), pause (`p`);
  screenshots (screen/area/window, delay, clipboard); REC badge in the header on
  every tab; library with filters; viewer with player, open/Finder/copy,
  trim by player position, convert, Trash.
- **3.12.1 fixes (the "late and laggy" report):**
  - the button reacts at once (`Starting…`, clock running) instead of waiting
    for the server;
  - the screen preview (a full Retina screenshot + resize every 2 s) is paused
    while recording, so it no longer competes with the recorder;
  - the start check is 0.7 s instead of 1.2 s and the clock starts at spawn;
    `ffmpeg -list_devices` (0.5 s) is skipped when devices are `default`/`none`;
  - the recording clock counts whole seconds (it rounded up and ran ahead);
  - a failed save keeps the parts (`unsaved` phase) instead of losing them;
  - trim seeks on the input (fast for long files, still exact).
- **Waveforms like Voice Memos:** a live microphone wave (Web Audio analyser,
  one bar per 50 ms, red while recording, playhead) in Audio mode and as a strip
  in other modes; in the viewer a file waveform from `ul capture wave`
  (`/api/studio/wave`), coloured up to the play position, click to seek, trim
  range highlighted.

## Verification done

- `cargo test --workspace`, `cargo clippy --workspace --all-targets`,
  `cargo clippy --no-default-features --all-targets`,
  `python3 -m unittest discover -s tests` (fake screencapture/ffmpeg/ffprobe/
  sips/system_profiler on PATH; no real devices in tests).
- Live in a sandboxed HOME on a MacBook Pro M3 Pro (macOS 27): screen with
  pause/resume, screen + camera, separate microphone + MP4, audio with
  `--duration`, screenshots on the second display; Studio API and the page in
  Chromium and WebKit (playwright): record → stop → library → viewer, range
  seeking, thumbnails, trim, GIF, Trash, waveforms.

## Known limits and open questions

- One post-fix live stop failed once and never reproduced; if "nothing was
  recorded" appears, `storage.root/runtime/recording.log` has the tool output.
- The browser's microphone wave uses the browser's device, matched to the
  chosen microphone by label; it may differ if labels differ.
- `screencapture` cannot pause; pause is implemented with segments, so every
  pause costs one join on stop (stream copy, fast).
- Permissions (Screen Recording, Camera, Microphone) belong to the terminal app
  that runs `ul`/`ul desk`.
