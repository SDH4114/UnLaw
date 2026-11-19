# Studio, part 1: recording projects (design)

Status: approved by Haos on 2026-11-19. Part 2 (the editor: timeline, cuts, text,
voice-over, subtitles) gets its own design after this one ships.

## 1. Intent

Haos records tutorials and clips (screen, face, voice) for YouTube, sites,
TikTok, Reels and Shorts. Today `ul capture` and the desk Studio tab
"sometimes record, sometimes not", the camera is a fixed bubble in a corner
and the result is one flattened file. Goal: an OBS-like Studio in `ul desk`
and in the terminal, where every recording becomes a **project**: a folder
holding each source as its own file plus an instruction (`project.json`)
saying how to assemble them. A project exports to a finished video in any
format at once and opens in the desk (and later in the editor).

## 2. Goals, non-goals, anti-goals

Goals
- Recording never silently loses work; every failure is visible and logged.
- High quality: screen at native resolution and 60 fps, camera in its best
  mode, lossless microphone track, 60 fps exports up to 4K.
- Scenes and sources: switch layouts while recording (keys 1-9), camera that
  can be moved, resized and reshaped (circle, square, rounded, wide, tall),
  border, shadow, mirror; device choice for camera, microphone and display.
- Formats 16:9, 9:16, 1:1, 4:5 (+ "as recorded"), one layout per format.
- One project = separate tracks + `project.json`; export to video from the
  desk, the terminal UI and plain CLI (also for agents, with `--json`).
- Desk Studio redesigned as the approved mockup (section 9); terminal gets a
  full-screen UI with the same concepts.

Non-goals (this part)
- Timeline editing, cuts, text editing, voice-over, subtitles (part 2).
- Background blur / segmentation (needs an ML model).
- Global keyboard shortcuts (need Accessibility permission or native code);
  the menu-bar item covers control from other apps.
- Live streaming (RTMP), several displays at once, window-only capture.
- Windows/Linux backends (later port; this design keeps them possible).

Anti-goals (failure even if it "works")
- A recording lost without a message; a file overwritten.
- The desk page recording on its own instead of through `ul capture`
  (terminal and page must share one recording and one library).
- macOS-only compiled helpers (Swift etc.): Haos ports Unlaw to Windows and
  Linux later.
- Breaking existing commands, flags or JSON fields of `ul capture`.

## 3. Constraints

- Seeds are standalone Python 3.11+ stdlib; capture may be split into several
  seed modules (like desk: `SEED_FILES["capture"]` in `command_sources.py`).
- Only external tools: `screencapture`, `ffmpeg`/`ffprobe`, `sips`,
  `system_profiler`, `osascript` (macOS backend). Homebrew ffmpeg 8.1 here has
  **no `drawtext`, `subtitles` or `ass`**: text is always a PNG overlay.
- Desk rules stay: token, Host check, CSP, `textContent` only, byte-range
  media, files served only from validated folders, never overwrite.
- Tests never touch real devices or tools: fake executables on a restricted
  PATH (existing `FAKE_*` in `tests/test_command_paths.py`).
- Seed hash rules (`LEGACY_SOURCE_HASHES`, normalized hashes, catalog) apply to
  every changed seed.

## 4. What was measured (2026-11-19, this Mac, macOS 27.2, ffmpeg 8.1.2)

- `screencapture -v` records 3600x2338 at 60 fps (H.264, AAC with `-A`).
  It writes **nothing to the target path until it stops**; killing it loses
  the whole recording.
- 1 of 14 real runs (`-A -g -k`, first audio use in that session) ignored
  SIGINT for 20 s; the current code would SIGTERM/SIGKILL after 15 s and lose
  everything. Each flag alone and all later runs stopped in 0.1-0.4 s.
- Default-mic ffmpeg starts ~1 s after spawn (1.49 s of 2.5 s captured);
  screencapture ~0.25 s.
- FaceTime HD camera modes: 1920x1080, 1280x720, 640x480, 1760x1328,
  1080x1920, 1328x1760, 1552x1552, each 15-30 fps. Two ffmpeg processes can
  use the same camera at once (both files complete).
- Export speed (synthetic 3600x2338@60 screen + 1080p30 camera with a PNG
  mask, `h264_videotoolbox`): 2160p60 0.9x real time, 1440p60 1.9x, 1080x1920
  60 fps 3.2x. The bottleneck is the hardware encoder; `-hwaccel videotoolbox`
  decoding was slower than software here, `scale_vt` did not help.
- A JXA script (`osascript -l JavaScript`) can create an `NSStatusItem` and
  update its title every second. Menu clicks are not verified yet.
- No `recording.log` exists on this Mac, so Haos's earlier failures cannot be
  diagnosed from logs.

## 5. Approaches

A. **Separate tracks, assemble on export (chosen by Haos).** Each tool records
one source to its own file; scene switches are timestamps; ffmpeg composes on
export. Most reliable (a failing tool loses only its track), best quality,
layout editable after recording, preview = result. Costs export time and disk.

B. Live composition in one ffmpeg (avfoundation screen + camera + mic). File
ready at stop, but avfoundation screen capture is the legacy API, CPU-heavy at
Retina 60 fps, no Mac sound without BlackHole, scene switches cause gaps, one
crash loses everything. Rejected.

C. Own ScreenCaptureKit recorder in Swift. Rejected by Haos (Windows/Linux
port).

## 6. Concepts and data

### 6.1 Words
- **Source**: something in the picture: `screen`, `camera`, `image`, `text`
  (text = an image rendered by the desk page). Audio sources: `mic`, `system`.
- **Scene**: which sources are visible and where, per format. Defaults:
  1 `screen-camera` "Screen + camera", 2 `screen` "Screen", 3 `camera`
  "Camera", 4 `side` "Side by side". Users add/rename/delete scenes (max 9,
  keys 1-9). A placement whose source was not recorded is skipped; when only
  the screen is left in a scene, the `screen` scene's layout is used.
- **Format**: `16:9`, `9:16`, `1:1`, `4:5`, `source` (as recorded: screen
  only, no composition, instant export).
- **Setup**: the Studio's current sources, devices, scenes, layouts, audio and
  output choices. One file shared by desk, terminal UI and CLI:
  `storage.root/studio/setup.json` (atomic write under `studio/setup.lock`).
  A recording copies the setup into its project, so later setup changes never
  alter old projects. A damaged setup file is moved aside as
  `setup.json.damaged-<time>` and defaults are used, with a warning.
- **Assets**: images and rendered texts uploaded from the desk live in
  `storage.root/studio/assets/` (images only, 50 MB cap); a recording copies
  the ones its setup uses into the project's `assets/`.

### 6.2 Placement (one source in one scene in one format)
```json
{"visible": true, "box": [x, y, w, h], "fit": "cover", "focus": [0.5, 0.5],
 "radius": 0.0, "border": {"width": 0, "color": "#ffc933"},
 "shadow": false, "mirror": true, "anchor": "bottom-left"}
```
- `box` in canvas fractions (0-1). `anchor` (`top-left|top-right|bottom-left|
  bottom-right|null`) pins the box flush to that corner: resizing keeps it
  pinned; dragging away clears it.
- `fit`: `cover` (fill the box, crop around `focus`) or `contain` (whole
  source, background around it).
- `radius` as a fraction of the box's short side (0.5 on a square = circle);
  `border.width` in pixels at a 1080-pixel short side, scaled with the canvas.
- Camera shape presets set box aspect + radius: circle (1:1, 0.5), square
  (1:1, 0), rounded (1:1, 0.18), wide (16:9, 0), tall (9:16, 0).
- Z order = order of `sources` in the setup.
- Per-format background: `{"kind": "color", "color": "#000000"}` or
  `{"kind": "blur"}` (the screen, cover-scaled and blurred).

Default layouts (Haos's rules where stated, the rest my calls):
- 16:9 `screen-camera`: screen `contain` on black; camera wide (16:9),
  24 % of canvas width, `anchor: bottom-left`, no border, no radius, no shadow.
- 9:16 `screen-camera`: camera `cover` box `[0, 0, 1, 0.40]`; screen `cover`
  box `[0, 0.40, 1, 0.60]`, focus centre (drag in the preview to pan).
- 1:1 and 4:5 `screen-camera`: same stack as 9:16 (my call).
- `screen`: 16:9 contain on black; vertical formats contain on blur.
- `camera`: camera cover, full canvas.
- `side`: 16:9 screen contain in the left 2/3, camera cover in the right 1/3;
  vertical formats = the `screen-camera` stack at 50/50.

### 6.3 Project folder (the "instruction" plus tracks)
```
storage.root/captures/projects/<kind>-<YYYYmmdd-HHMMSS>/
  project.json            the instruction (below)
  media/screen-001.mp4    screen + Mac sound, segment 1 (remuxed from .mov)
  media/camera-001.mp4    camera, video only
  media/mic-001.flac      microphone (FLAC by default; WAV or M4A by choice)
  media/screen-002.mp4 …  one set per segment (after each pause)
  assets/logo.png         image/text sources used by the setup
  logs/record.log         every command run and its stderr
  logs/mic-levels.txt     microphone peaks while recording
  cache/                  masks and render chunks (safe to delete)
```
Paths inside `project.json` are relative, so a project folder can be moved or
copied to another Mac and opened from the desk.

`project.json` (version 1):
```json
{"format": "unlaw-studio-project", "version": 1,
 "name": "screen-camera-20261119-221500", "created": "2026-11-19T22:15:00+04:00",
 "duration": 754.2, "state": "ready",
 "sources": {"screen": {"kind": "screen", "display": 1, "area": null,
                        "size": [3600, 2338], "fps": 60, "clicks": true},
             "camera": {"kind": "camera", "device": "FaceTime HD Camera",
                        "mode": "1920x1080@30"},
             "mic": {"kind": "mic", "device": "MacBook Pro Microphone"},
             "system": {"kind": "system"}},
 "segments": [{"duration": 754.2,
               "files": {"screen": "media/screen-001.mp4",
                         "camera": "media/camera-001.mp4", "mic": "media/mic-001.flac"},
               "starts": {"screen": 0.0, "camera": 0.31, "mic": 0.94}}],
 "scenes": [{"id": "screen-camera", "name": "Screen + camera"}, …],
 "layouts": {"16:9": {"background": {...}, "scenes": {"screen-camera": {"screen": {...}, "camera": {...}}}}, …},
 "events": [{"t": 0.0, "scene": "screen-camera"}, {"t": 61.5, "scene": "camera"},
            {"t": 90.0, "mark": "intro done"}],
 "audio": {"mic": {"volume": 1.0, "muted": false}, "system": {"volume": 0.8, "muted": false},
           "normalize": true},
 "export": {"canvas": "16:9", "height": 1440, "fps": 60, "codec": "h264",
            "quality": "high", "container": "mov", "normalize": true},
 "exports": [{"path": "/…/recordings/screen-camera-20261119-221500 16x9.mov",
              "canvas": "16:9", "at": "…", "settings": {...}}]}
```
- `state`: `recording`, `saving`, `ready`, `incomplete` (a track is missing or
  a recorder was stuck; what exists is kept and listed in `problems`).
- `starts`: where each track begins on the segment's clock (screen = 0).
  Computed at stop by end alignment (all recorders get SIGINT together, so
  ends line up): `start = screen_duration - track_duration`; negative means
  the track started earlier and is trimmed. Part 2 can nudge these.
- Strict validation on read (types, ranges, known keys, relative paths that
  stay inside the folder); unknown keys are kept on write.

## 7. Recording engine

### 7.1 Backend layer
All platform calls live in one module (`capture_mac.py`, seeded with
capture): device and display listing, the recorder commands, preview
snapshots, the menu-bar helper. The rest (state, projects, export, CLI, TUI)
calls a small interface and never names `screencapture` or `avfoundation`.
Other platforms get "not supported on this system yet".

### 7.2 Tracks
- Screen: `screencapture -v -x -D<n> [-R<rect>] [-k] [-A] <tmp>.mov`; no
  `-g` (the microphone is its own track). After stop it is remuxed
  (`-c copy -movflags +faststart`) to `screen-NNN.mp4` so every browser can
  play it, then the `.mov` is removed.
- Camera: ffmpeg avfoundation, video only, mode from the setup or `auto`
  (1920x1080 at the highest fps the device lists, else the largest 16:9, else
  the largest), framerate passed exactly as the device lists it (e.g.
  `30.000030`), `-pixel_format nv12` with one retry without it when the device
  refuses; `h264_videotoolbox` at the chosen quality (below), keyframe every
  second, fragmented MP4 while recording (survives a kill), remuxed with
  faststart at stop.
- Mic: ffmpeg avfoundation, 48 kHz, device channels up to 2, in the chosen
  file type (below), plus a level branch (`asplit` → `astats` → `ametadata`
  print to `logs/mic-levels.txt`, ~10 values per second). An unfinished WAV
  header is repaired at stop.
- Modes: `screen` (screen + optional camera + mic + system), `camera`
  (camera + mic, scene `camera`), `audio` (mic only). All create projects.

### 7.2a Recording files (Haos: "too much, give options")
Chosen in the Output panel / TUI / `--cam-quality`, `--mic-format`, saved in
the setup:
- Camera quality: `max` 1080p 12 Mbps (~90 MB/min), `high` 1080p 6 Mbps
  (~45 MB/min, default), `light` 720p 3 Mbps (~22 MB/min).
- Microphone: `flac` lossless (~3 MB/min, default), `wav` lossless
  (~6 MB/min), `m4a` AAC 256 kbps (~2 MB/min).
- Screen: macOS `screencapture` has no bitrate or fps option; measured
  ~25-70 MB/min depending on what moves. Recording an area instead of the
  whole display makes it smaller.
- Default project ≈ 70-120 MB per minute. The page shows the estimate next to
  the free space. The export dialog can delete the sources after a successful
  export (keep only the video; off by default).

### 7.3 Device modes
`ul capture devices --modes [--camera NAME]` probes camera modes by asking
ffmpeg for an impossible framerate and parsing "Supported modes"; results are
cached in `runtime/camera-modes.json` by device name (the probe turns the
camera light on for a moment, so it runs only on demand or before a recording
whose mode is unknown).

### 7.4 State, segments, scenes
- `runtime/recording.json` becomes version 2: project path, mode, phase,
  paused, elapsed, segment_started, segments (files), processes (pid, program,
  validated as today), warnings, `stuck`. Same lock (`recording.lock`).
- Pause/resume stop and start a segment as today.
- `ul capture scene <n|id>` and `ul capture mark [text]` append an event at
  the current elapsed time (under the lock); while paused the scene applies
  from the resume point.
- Health, reported by `status`: a recorder that died → `interrupted` (saving
  keeps the rest); microphone peaks below -60 dB for 10 s while recording →
  warning "the microphone is silent"; free space below 5 GB → warning.
- Starting while an export runs is allowed (exports run at `nice 10` outside
  the recording lock). Starting while a stop is saving answers at once with
  "the previous recording is still saving" instead of waiting on the lock.

### 7.5 Stop
1. SIGINT to every recorder at once.
2. Wait while any is alive, up to `max(30 s, 5 % of the duration)`; then
   SIGTERM and 10 s more.
3. A recorder still alive is **not** killed: the project is saved with what
   exists, `state: incomplete`, the state file keeps `stuck: true`, and the
   message says which tool hangs and that `ul capture stop` retries or
   `ul capture stop --force` kills it (its track is then lost).
4. Remux, WAV repair, end alignment, `project.json` written, state removed.
5. No automatic export (Haos: the user picks format, fps and the rest when
   exporting). The desk opens the project with its Export dialog; the TUI
   asks "Export now?" and shows the same choices; plain `stop` prints the
   project and the export command. `stop --export [export flags]` and
   `record … --export` export right away (flags, else the last used
   settings). `stop --json` adds `project`; `saved` is the exported file when
   there was an export, otherwise the project folder (it used to always be a
   media file).

### 7.6 Menu-bar control (macOS)
While recording, a JXA helper (`osascript -l JavaScript`, args only, no
shell) shows "● 12:31" / "❚❚ 12:31" in the menu bar with: Stop and save,
Pause/Resume, the scenes (current checked), Add mark, Open Studio. Items run
`$UNLAW_BIN capture <action>` through `NSTask` with an argument array. It
quits when the recording ends (polls the state file each second) and is a
tracked process (program `osascript`). `setup.menubar` (default on).

### 7.7 Permissions (seen on Haos's desk, 2026-11-19)
Haos's desk on port 8766 showed "No preview … Screen Recording permission"
while a desk started from Ghostty on 8765 had it: macOS grants Screen
Recording, Camera and Microphone to the app that started `ul` (Ghostty, Zed,
VS Code, Claude…), so the same command works from one terminal and fails from
another. This is a likely cause of "sometimes it records, sometimes not".
- Preflight before every recording and in `ul capture doctor`: a 1x1-pixel
  `screencapture -R0,0,1,1` probe for the screen; for camera and microphone,
  ffmpeg's start error ("not authorized", immediate exit).
- The message names the app to fix: walk the process ancestry (`ps -o ppid`)
  to the first `*.app` and say "Give <Ghostty> Screen Recording permission",
  with a button/command that opens the right System Settings pane
  (`x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture`,
  `…Privacy_Camera`, `…Privacy_Microphone`).
- The desk shows this as a blocking banner on the Record tab instead of an
  empty preview; the record button stays usable for sources that work.

## 8. Export

- `ul capture export <project|last> [--canvas 16:9|9:16|1:1|4:5|source]
  [--height 1080|1440|2160] [--fps 60|30] [--codec h264|hevc]
  [--quality high|max] [--format mov|mp4] [--no-normalize] [--output PATH]
  [--json]`. `--format` keeps its old meaning everywhere: the container.
- The user chooses every export: canvas, height, fps, codec, quality,
  container, loudness normalisation, where to save, and whether to delete
  the sources afterwards. Desk: Export dialog; TUI: export screen; CLI:
  flags. The dialog is pre-filled with the project's last export, else the
  last settings used anywhere (`setup.export`).
- Canvas: short side = height (16:9 1440p = 2560x1440; 9:16 1080 =
  1080x1920; 1:1 = 1080x1080; 4:5 = 1080x1350). Pre-fill when nothing was
  used yet: 16:9 → 1440,
  others → 1080, 60 fps, H.264; a camera-only project defaults to 1080 (the
  camera's own height).
- Video: the global timeline (segments in order) is cut at segment boundaries
  and scene events, rounded to frames. Each interval is rendered by one
  ffmpeg run with that scene's graph: per visible source (z order) input
  seek → `hflip` (mirror) → cover crop around focus or contain scale → mask
  (`alphamerge` with a PNG) → overlay at the box; shadow and border are RGBA
  PNGs overlaid under/over the source; background is `pad`/colour or a
  blurred cover copy of the screen. Chunks use identical encoder settings and
  are joined with the concat demuxer (`-c copy`).
- Masks, borders and shadows are PNGs drawn by Python (zlib + struct, signed
  distance, anti-aliased; 0.18 s for 864x486), cached in `cache/` by
  parameters.
- Audio: per segment, system sound (from the screen file) and mic with their
  start offsets and volumes, `amix normalize=0`, stereo 48 kHz; segments
  joined; optional `loudnorm=I=-14:TP=-1` (default on); AAC 256 kbps.
- Encoder: `h264_videotoolbox` (or `hevc_videotoolbox -tag:v hvc1`), bitrate
  from pixels x fps (H.264 ~0.11 bit per pixel per frame: 2560x1440@60 ≈ 24
  Mbps, 3840x2160@60 ≈ 55 Mbps; `max` x1.5; HEVC x0.65), keyframe every 2 s,
  BT.709 tags, `+faststart`.
- `source` format: screen video stream-copied (segments concatenated), audio
  mixed and re-encoded: ready in seconds.
- Output: `storage.root/captures/recordings/<project> <16x9>.<mov|mp4>`
  (container from `--format`, else `capture.video_format`; audio-only
  projects: `.m4a`/`.mp3`/`.wav` from `capture.audio_format`), never
  overwritten (" 2"), recorded in `project.json` `exports`.
- Progress: ffmpeg `-progress`, summed over chunks, in
  `runtime/export.json` (project, percent, eta, phase) for desk, TUI and
  `ul capture export --status`. One export at a time (`export.lock`); a
  second one waits as `queued`; a failed export leaves the project untouched
  and removes partial output.
- Expected time (measured): 10 min of 16:9 1440p60 ≈ 5 min; 4K60 ≈ 11 min;
  9:16 1080p60 ≈ 3 min.

## 9. Desk Studio

Tabs: **Record**, **Projects** (library), **Edit** (part 2; shown disabled,
"coming soon"). The page stays in English like the rest of the desk; the
mockups were in Russian only for the discussion. Layout = approved mockup
`record-layout-v2`:
- Header: tabs and the format switch (16:9 / 9:16 / 1:1 / 4:5 / As recorded).
- Left: scenes as thumbnails with keys and "+ сцена"; sources list (screen,
  camera, images, texts) with visibility toggles and "+ источник" (image file
  upload, text: font, size, colour, background; rendered by the page to PNG
  and uploaded).
- Centre: a preview narrower than mockup A: screen snapshot (every 1 s idle,
  every 3 s while recording), live camera via `getUserMedia` (kept during
  recording; matched to the chosen device by label), images and texts, all
  drawn with the same boxes, radius, border and shadow as the export. Drag to
  move (snaps to corners and edges; dropping on a corner sets `anchor`),
  corner handle to resize (keeps the preset aspect), drag inside a `cover` box
  to move its focus. Clicking the camera opens the floating mini toolbar
  (shapes, corners). Below: big REC, clock, pause, mark, screenshot menu
  (screen/area/window, delay, clipboard), resolution/fps, free space, and a
  warning strip (silent mic, stuck recorder, low disk).
- Sound panel: microphone device list (virtual devices tagged), live meter
  (browser), volume and mute; Mac sound on/off, volume. Volumes go to the
  setup and apply at export.
- Right: properties of the selected source: camera (device, mode list from
  `devices --modes`, shape, size, corner, border colour/width, radius,
  shadow, mirror); screen (display, area: full or drawn on the preview,
  clicks); output (recording files: camera quality and mic file type with
  the MB/min estimate, countdown 0/3/5/10).
- Keys on the Studio tab: R start/stop, P pause, M mark, 1-9 scenes.
- Countdown overlay before start (the page waits, then calls record).
- The REC pill in the header also shows recordings started elsewhere: the
  page polls `status` every 5 s while visible, faster while recording.
- **Projects**: cards (thumbnail, duration, formats exported, size, state
  badge), filter projects / exports / screenshots; a project page with a
  synced preview (screen MP4 as the clock, camera and mic follow), format
  switch and the same layout editing as the record tab (saved to that
  project), scene list, Export panel with progress, Show in Finder, Move to
  Trash. "Open project…" picks a project folder anywhere (osascript folder
  dialog) and remembers it in `studio/recent-projects.json`.
- `POST /api/studio/record` takes `{scene?, canvas?}` and records the saved
  setup; the old body keys (`mode`, `mic`, `cam`, `display`, `system_audio`,
  `clicks`, `format`) still work as one-off overrides.
- API (all through `ul capture … --json`, validated like today):
  `GET/POST /api/studio/setup`, `POST /api/studio/scene`, `/mark`,
  `GET /api/studio/projects`, `GET/POST /api/studio/project`,
  `POST /api/studio/export`, `GET /api/studio/export/status`,
  `POST /api/studio/asset` (raw body, image only, size cap),
  `POST /api/studio/open-project`, `GET /api/studio/camera-modes`,
  `GET /media/project?t=&project=&file=` (only files inside that project's
  `media/` or `assets/`, byte ranges).

## 10. Terminal

- `ul capture` in a TTY opens a full-screen curses UI (own module, so a later
  Windows port can swap it): scenes (1-9), sources with device pickers,
  format, a status panel (REC clock, mic meter from `mic-levels.txt`, free
  space, warnings) and a key bar: R record/stop, P pause, 1-9 scene, M mark,
  F format, D devices, E export last, Q quit (the recording keeps going).
  After stop it shows export progress and the saved path (O open, F reveal).
- Plain commands stay and gain the new ones: `record` (new flags `--scene`,
  `--canvas`, `--cam-mode`, `--cam-quality`, `--mic-format`, `--countdown`,
  `--export`), `scene`,
  `mark`, `projects`, `project <name> [--json]`, `export`, `setup [--json |
  --set-json -]`, `devices --modes`, `stop --force`; `delete` also takes a
  project name (the whole folder goes to the Trash). `record --wait` and
  `--duration` keep the one-line timer, now with a mic level.
- Non-TTY `ul capture` prints usage as today.

## 11. Compatibility

- Existing actions, flags and JSON fields keep working; `shot`, `list`,
  `trim`, `convert`, `wave`, `thumb`, `preview` unchanged.
- `capture.*` config keys stay valid; they seed `setup.json` the first time
  (devices, system sound, clicks, formats). `capture.overlay` is ignored by
  the new layouts (Haos wants bottom-left by default); it stays valid so old
  configs still load.
- A version-1 `recording.json` found after an update: `status` reports it and
  `stop` stops its recorders and wraps its parts into a project (best effort:
  files found are placed as screen/camera/mic tracks).
- Old files in `captures/recordings` still appear in the library.
- Release: MINOR, 3.21.0. Seeds `capture` and `desk` change: register 3.20.0
  hashes, regenerate normalized hashes and `catalog/`.

## 12. Testing

- Unit (Python, fakes): setup and project validation; default layouts per
  format; interval splitting (segments x scene events, frame rounding); start
  offsets; the export command builder (pure function → ffmpeg argument lists,
  asserted); mask/border/shadow PNGs (size, alpha at centre and corner);
  camera mode parsing (fixture of real ffmpeg output); WAV header repair;
  state machine with fake tools (start, scene, mark, pause, resume, stop,
  stuck recorder, `--force`, died recorder, silent mic warning); v1 state
  wrap-up; CLI JSON contracts; TUI frame rendering as text (no curses);
  menu-bar helper started via fake `osascript`.
- Desk: API tests in `DeskStudioTests`; page logic in `test_desk_ui.cjs`
  (drag/snap/anchor math, format switch, countdown, keys, setup save
  debounce, REC pill polling).
- Opt-in real-tool smoke test (`UNLAW_REAL_MEDIA=1`): synthetic lavfi sources
  through the real export, checking size, fps and duration.
- Manual checklist with Haos: real screen + camera + mic recording with scene
  switches and a pause, menu-bar clicks, each format exported, project moved
  to another folder and reopened.

## 13. Decided by Haos

Approach A; recording first, editor second; projects with separate tracks and
an instruction file, export to video, open in the desk; no Swift (Windows and
Linux later); high fps and quality; movable camera with shapes; device choice
for camera, sound and display; formats for TikTok, Instagram, YouTube and
sites; 16:9 camera wide and flush in the bottom-left corner; 9:16 camera on
top at 40 %; record screen = merged mockup (three columns from A, scene
thumbnails, floating camera toolbar and device pickers from B, narrower
preview); subtitles for 16:9 and 9:16 with font and size, Whisper models with
an always-present button (part 2). After review: no automatic export, the
user chooses format, resolution, fps and the rest in an export dialog;
options for which files a recording makes (camera quality, mic type) because
~200 MB/min was too much; 1:1 and 4:5 like 9:16; the Studio page and TUI
stay in English like the rest of Unlaw (scene names "Screen + camera",
"Screen", "Camera", "Side by side"); Haos will test with a local build.

## 14. My calls (please check)

1. 1:1 and 4:5 use the 9:16 stack; `side` scene layouts as in 6.2.
2. 16:9 screen is `contain` on black (no cropping of the menu bar or dock);
   vertical screen-only scenes use a blurred background.
3. The export dialog's first pre-fill: 16:9 1440p60 H.264, loudness
   normalisation to -14 LUFS on; after that it remembers your choices.
4. (dropped: no auto export, Haos decided.)
5. Recording file defaults: camera `high` (1080p 6 Mbps), mic FLAC.
6. A stuck recorder is never killed automatically; `stop --force` does it.
7. Setup lives in `storage.root/studio/setup.json`, not in config.toml.
8. Menu-bar item on by default; no global hotkeys in this part.
9. A new recording may start while the previous one is still exporting.
10. (decided by Haos: English, see section 13.)
11. Exports use the container from `capture.video_format` (your config: mov)
    unless `--format mp4`; both upload fine to YouTube, TikTok and Instagram.

## 15. Left to the builder

Module split and names, exact JSON validation code, curses layout details,
CSS, polling intervals within the stated bounds, mask drawing code,
chunk/concat file naming in `cache/`, how the project preview switches
segment files, and the wording of messages.
