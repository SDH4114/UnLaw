# Studio Recording Projects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every `ul capture` recording becomes a project folder (separate screen, camera and mic tracks plus `project.json`) that exports to 16:9, 9:16, 1:1, 4:5 or "as recorded" video, driven from a redesigned desk Studio, a curses TUI, plain CLI and a macOS menu-bar item.

**Architecture:** The capture seed grows from one module to five: a macOS backend (`capture_mac.py`), a pure data layer for setup and projects (`capture_project.py`), the ffmpeg compositor (`capture_export.py`), the TUI (`capture_tui.py`) and the CLI/recording engine (`capture.py`). The desk stays a thin layer over `ul capture … --json`; its Studio page code moves into a new desk seed module `studio_ui.py` that `desk_ui.py` injects into `PAGE`.

**Tech Stack:** Python 3.11+ stdlib (seeds), ffmpeg/ffprobe 8 (`h264_videotoolbox`, `hevc_videotoolbox`), macOS `screencapture`, `osascript -l JavaScript` (JXA), vanilla JS in the desk page, Node for page tests, Rust only for the version bump.

**Spec:** `docs/superpowers/specs/2026-11-19-studio-recording-design.md` (approved 2026-11-19). Read it with this plan; section numbers below (§) refer to it.

## Global Constraints

- Seeds: Python 3.11+ standard library only; external tools only `screencapture`, `ffmpeg`, `ffprobe`, `sips`, `system_profiler`, `osascript`, `open`, `ps`. No Swift or other compiled helpers (Windows/Linux port later).
- All macOS-specific calls live in `capture_mac.py`; other modules never name `screencapture`, `avfoundation` or `osascript`.
- Concatenated seeds share one namespace: no two capture modules (or desk modules) may define the same top-level name.
- Existing files in `src/unlawful`, `tests`, `rust/src` are patched with small Bash/python replace scripts, never rewritten through Edit/Write (the format hook would reformat the whole file). New files may use Write.
- Tests never touch real devices, real tools or the real `~/.config/unlaw`: fake executables on a restricted PATH, `HOME`/`XDG_CONFIG_HOME` patched before any in-process `unlawful` call. Dev builds run only with a temporary `XDG_CONFIG_HOME`.
- Never overwrite a file (`_free` → `name 2.ext`); every JSON write is atomic (temp file + `os.replace`).
- Desk rules: token on every API/media request, Host check, CSP, `textContent` only (never `innerHTML`), media only from validated folders, byte ranges.
- UI language English. Scene names "Screen + camera", "Screen", "Camera", "Side by side"; ids `screen-camera`, `screen`, `camera`, `side`.
- Every seed's `--help` stays static (it is printed by ul without Python, `SEED_HELP`) and must keep the substring `record [screen` (desk availability probe).
- Release: MINOR 3.21.0 in `Cargo.toml`, `ule/Cargo.toml`, `src/unlawful/__init__.py`, `Cargo.lock`.
- Git: work on `feat/studio-recording`. Commit only if Haos allows per-task commits; otherwise each task ends with its tests green and `git diff --stat` checked.

## Review Focus

1. Device names with apostrophes, spaces and non-ASCII ("Haos's Phone Microphone") must reach ffmpeg as one argv element and never be split or quoted by a shell. Test in Task 4.
2. A recorder that dies mid-recording (camera unplugged, display gone) must leave a project with the surviving tracks and `state: incomplete`, not an error with nothing saved. Test in Task 5.
3. A stop right after start (segments shorter than one frame, a pause after 0.1 s) must save and export without ffmpeg errors: zero-length intervals are dropped. Tests in Tasks 3 and 6.
4. Storage paths with spaces, Cyrillic and single quotes must survive the concat list, filtergraph file options and `-i` arguments. Test in Task 6.
5. A tampered or copied `project.json` whose files point outside the folder (`../`, absolute paths, symlinks) must be refused by every reader (CLI, export, desk media). Tests in Tasks 3 and 10.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/unlawful/capture_project.py` (new) | Constants, setup defaults/validation/load/save, placements and shapes, default layouts, project.json create/read/write/validate, timeline intervals, effective scenes, canvas sizes, bitrates. No subprocess. |
| `src/unlawful/capture_mac.py` (new) | `MacBackend`: devices, displays, camera mode probe/parse/pick, recorder argv builders, preview, permission probe, responsible app, System Settings URLs, menu-bar JXA script and argv. |
| `src/unlawful/capture_export.py` (new) | PNG masks/frames, interval and audio ffmpeg argv builders, export runner with progress, queue lock, status file, delete-sources. |
| `src/unlawful/capture_tui.py` (new) | Pure `render_frame` and `tui_action`, curses loop `run_tui`. |
| `src/unlawful/capture.py` (modify) | Recording engine v2 (projects, tracks, segments, scenes, marks, stop policy, health), CLI actions, library, shots (unchanged), v1 state wrap-up. |
| `src/unlawful/command_sources.py` (modify) | `_COMMAND_FILES["capture"]`, `_COMMAND_FILES["desk"]`, `_clean_fragment` prefixes, legacy hashes. |
| `src/unlawful/command_help.py` (modify) | `COMMAND_HELP["capture"]`. |
| `src/unlawful/desk.py` (modify) | `Studio` endpoints, project media, assets, REC status. |
| `src/unlawful/studio_ui.py` (new) | `STUDIO_CSS`, `STUDIO_JS` strings for the Studio tab. |
| `src/unlawful/desk_ui.py` (modify) | Injects `STUDIO_CSS`/`STUDIO_JS`; old Studio code removed. |
| `tests/test_capture_project.py`, `tests/test_capture_mac.py`, `tests/test_capture_export.py`, `tests/test_capture_tui.py` (new) | Unit tests. |
| `tests/test_command_paths.py`, `tests/test_desk.py`, `tests/test_desk_ui.cjs`, `tests/test_desk_ui.py` (modify) | Engine, desk API and page tests. |
| `AGENTS.md`, `README.md`, `catalog/`, versions (modify) | Docs and release. |

---

### Task 1: Seed wiring and 3.20.0 hash registration

**Files:**
- Create: `src/unlawful/capture_project.py`, `src/unlawful/capture_mac.py`, `src/unlawful/capture_export.py`, `src/unlawful/capture_tui.py`, `src/unlawful/studio_ui.py` (module docstring + `from __future__ import annotations` only)
- Modify: `src/unlawful/command_sources.py` (`_COMMAND_FILES`, `_clean_fragment`, legacy hashes)
- Test: `tests/test_core_layout.py`

**Interfaces:**
- Produces: `_COMMAND_FILES["capture"] == ("capture_project.py", "capture_mac.py", "capture_export.py", "capture_tui.py", "capture.py")`; `_COMMAND_FILES["desk"] == ("kanban.py", "reminders.py", "canvas.py", "studio_ui.py", "desk_ui.py", "desk.py")`; removed import prefixes `"from .capture_project import "`, `"from .capture_mac import "`, `"from .capture_export import "`, `"from .capture_tui import "`, `"from .studio_ui import "`.

- [ ] **Step 1: Hash the 3.20.0 seeds before anything changes**

Run (prints four hashes; keep them for Step 4):
```bash
python3 - <<'EOF'
import hashlib, sys, subprocess, pathlib
sys.path.insert(0, "src")
from unlawful.command_sources import command_source, normalized_source
for name in ("capture", "desk"):
    src = command_source(name)
    print(name, "release", hashlib.sha256(src.encode()).hexdigest(), hashlib.sha256(normalized_source(src).encode()).hexdigest())
    inst = pathlib.Path.home() / ".config/unlaw/commands" / name / "main.py"
    if inst.exists():
        print(name, "installed", hashlib.sha256(inst.read_bytes()).hexdigest())
EOF
```
Expected: two `release` lines; `installed` lines equal to the release hashes (Haos runs 3.20.0 729c0b5) or extra hashes to register too.

- [ ] **Step 2: Write the failing test** in `tests/test_core_layout.py`

```python
def test_split_seeds_are_self_contained(self) -> None:
    for name, module in (("capture", "capture_project"), ("desk", "studio_ui")):
        source = command_source(name)
        compile(source, f"{name}/main.py", "exec")
        self.assertNotIn("from .", source)
        self.assertNotIn("from unlawful", source.replace("from unlawful.command_help", ""))
    self.assertIn('"""', command_source("capture").splitlines()[0])
```

- [ ] **Step 3: Run it** — `python -m unittest tests.test_core_layout -v`. It passes before wiring and must keep passing after Step 4 and after every later task adds `from .capture_… import` lines; it is the guard for the five new prefixes.

- [ ] **Step 4: Wire the modules and register hashes**

Patch `command_sources.py`: the two tuples and the five prefixes above; append after the last legacy block:
```python
# capture and desk seeds of 3.20.0 (729c0b5, also the copies on the maintainer machine), before Studio projects.
LEGACY_SOURCE_HASHES.setdefault("capture", set()).add("<capture release hash>")
LEGACY_NORMALIZED_HASHES.setdefault("capture", set()).add("<capture normalized hash>")
LEGACY_SOURCE_HASHES.setdefault("desk", set()).add("<desk release hash>")
LEGACY_NORMALIZED_HASHES.setdefault("desk", set()).add("<desk normalized hash>")
```

- [ ] **Step 5: Verify** — `python -m unittest tests.test_core_layout tests.test_catalog -v`. Expected: core layout PASS; catalog FAIL until Task 14 regenerates it only if the seed text changed (empty modules add nothing; if it fails, run `python3 -I rust/gen_assets.py --catalog src catalog` now).

---

### Task 2: Setup model, placements, shapes, default layouts

**Files:**
- Modify: `src/unlawful/capture_project.py`
- Test: `tests/test_capture_project.py` (new; patches HOME/XDG_CONFIG_HOME in `setUp` like `ToolTestCase`)

**Interfaces:**
- Produces (all in `capture_project.py`):
  - `CANVASES = ("16:9", "9:16", "1:1", "4:5", "source")`, `RATIOS = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1), "4:5": (4, 5)}`, `HEIGHTS = (1080, 1440, 2160)`, `FPS = (30, 60)`, `CODECS = ("h264", "hevc")`, `QUALITIES = ("high", "max")`, `CAMERA_QUALITY = {"max": (1080, 12_000_000), "high": (1080, 6_000_000), "light": (720, 3_000_000)}`, `MIC_FORMATS = {"flac": ".flac", "wav": ".wav", "m4a": ".m4a"}`, `SHAPES = {"circle": (1, 1, 0.5), "square": (1, 1, 0.0), "rounded": (1, 1, 0.18), "wide": (16, 9, 0.0), "tall": (9, 16, 0.0)}`, `ANCHORS = ("top-left", "top-right", "bottom-left", "bottom-right")`, `SCENES = (("screen-camera", "Screen + camera"), ("screen", "Screen"), ("camera", "Camera"), ("side", "Side by side"))`.
  - `class ProjectError(ValueError)`.
  - `default_setup(capture_config: dict) -> dict`
  - `default_layouts() -> dict` → `{canvas: {scene_id: {"background": {...}, "placements": {source_id: placement}}}}` for the four ratio canvases.
  - `apply_shape(placement: dict, shape: str, canvas: str) -> dict` (new dict; keeps width fraction and anchor)
  - `pin(placement: dict, anchor: str | None) -> dict` (moves the box flush to the corner)
  - `validate_setup(data: object) -> dict` (raises `ProjectError`)
  - `setup_path() -> Path` (= `storage_path("studio", "setup.json")`), `load_setup() -> tuple[dict, list[str]]` (setup, warnings), `save_setup(data: dict) -> dict` (validates, atomic, under `studio/setup.lock`)
  - `canvas_size(canvas: str, height: int) -> tuple[int, int]`
  - `video_bitrate(width: int, height: int, fps: int, codec: str, quality: str) -> int`

Setup shape (JSON):
```json
{"version": 1,
 "sources": [{"id": "screen", "kind": "screen", "enabled": true, "display": 1, "area": null, "clicks": true},
             {"id": "camera", "kind": "camera", "enabled": false, "device": "default", "mode": "auto", "quality": "high"}],
 "audio": {"mic": {"enabled": true, "device": "default", "format": "flac", "volume": 1.0, "muted": false},
           "system": {"enabled": true, "volume": 1.0, "muted": false}},
 "scenes": [{"id": "screen-camera", "name": "Screen + camera"}, {"id": "screen", "name": "Screen"},
            {"id": "camera", "name": "Camera"}, {"id": "side", "name": "Side by side"}],
 "scene": "screen-camera", "canvas": "16:9", "layouts": {"...": "default_layouts()"},
 "countdown": 3, "menubar": true,
 "export": {"canvas": "16:9", "height": 1440, "fps": 60, "codec": "h264", "quality": "high",
            "container": "mov", "normalize": true, "delete_sources": false}}
```
Image/text sources: `{"id": "img-1", "kind": "image", "enabled": true, "asset": "logo.png"}`, text adds `"text", "font", "size", "color", "background"`. Placement keys exactly as spec §6.2 (`visible, box, fit, focus, radius, border{width,color}, shadow, mirror, anchor`). Max 9 scenes, max 12 sources, ids `[a-z0-9-]{1,32}`, asset names without `/` or leading `.`.

- [ ] **Step 1: Write failing tests**

```python
def test_default_layouts_follow_haos_rules(self):
    layouts = capture_project.default_layouts()
    cam = layouts["16:9"]["screen-camera"]["placements"]["camera"]
    self.assertEqual((cam["box"], cam["anchor"], cam["radius"], cam["fit"]), ([0, 0.76, 0.24, 0.24], "bottom-left", 0.0, "cover"))
    self.assertEqual(layouts["16:9"]["screen-camera"]["placements"]["screen"]["fit"], "contain")
    for canvas in ("9:16", "1:1", "4:5"):
        p = layouts[canvas]["screen-camera"]["placements"]
        self.assertEqual((p["camera"]["box"], p["screen"]["box"]), ([0, 0, 1, 0.4], [0, 0.4, 1, 0.6]))
        self.assertEqual(layouts[canvas]["screen"]["background"], {"kind": "blur"})
    self.assertEqual(layouts["16:9"]["side"]["placements"]["camera"]["box"], [2 / 3, 0, 1 / 3, 1])
    self.assertEqual(layouts["9:16"]["side"]["placements"]["camera"]["box"], [0, 0, 1, 0.5])

def test_shapes_keep_width_and_corner(self):
    wide = capture_project.default_layouts()["16:9"]["screen-camera"]["placements"]["camera"]
    circle = capture_project.apply_shape(wide, "circle", "16:9")
    self.assertAlmostEqual(circle["box"][2], 0.24)
    self.assertAlmostEqual(circle["box"][3], 0.24 * 16 / 9)   # square in pixels
    self.assertEqual((circle["radius"], circle["anchor"]), (0.5, "bottom-left"))
    self.assertAlmostEqual(circle["box"][1] + circle["box"][3], 1.0)   # still flush to the bottom

def test_canvas_sizes_and_bitrates(self):
    cs = capture_project.canvas_size
    self.assertEqual([cs("16:9", 1440), cs("9:16", 1080), cs("1:1", 1080), cs("4:5", 1080), cs("16:9", 2160), cs("9:16", 2160)],
                     [(2560, 1440), (1080, 1920), (1080, 1080), (1080, 1350), (3840, 2160), (2160, 3840)])
    vb = capture_project.video_bitrate
    self.assertEqual(vb(2560, 1440, 60, "h264", "high"), 24_330_240)
    self.assertEqual(vb(2560, 1440, 60, "h264", "max"), 36_495_360)
    self.assertEqual(vb(2560, 1440, 60, "hevc", "high"), 15_814_656)

def test_default_setup_reads_capture_config(self):
    s = capture_project.default_setup({"audio_device": "MacBook Pro Microphone", "system_audio": False, "show_clicks": False, "screen_audio": True, "camera_device": "default"})
    self.assertEqual(s["audio"]["mic"]["device"], "MacBook Pro Microphone")
    self.assertFalse(s["audio"]["system"]["enabled"])
    self.assertFalse(s["sources"][0]["clicks"])
    self.assertFalse(s["sources"][1]["enabled"], "camera off until chosen: `ul capture record` stays a screen recording")
    self.assertEqual(capture_project.validate_setup(s), s)

def test_setup_validation_refuses_bad_values(self):
    good = capture_project.default_setup({})
    for path, value in ((("canvas",), "21:9"), (("countdown",), 99), (("export", "height"), 720),
                        (("sources", 0, "id"), "../x"), (("audio", "mic", "volume"), 3.0), (("menubar",), 1)):
        bad = json.loads(json.dumps(good)); target = bad
        for key in path[:-1]: target = target[key]
        target[path[-1]] = value
        with self.subTest(path=path), self.assertRaises(capture_project.ProjectError):
            capture_project.validate_setup(bad)

def test_damaged_setup_is_moved_aside(self):
    capture_project.setup_path().parent.mkdir(parents=True)
    capture_project.setup_path().write_text("{broken")
    setup, warnings = capture_project.load_setup()
    self.assertEqual(setup["canvas"], "16:9")
    self.assertTrue(any("damaged" in w for w in warnings))
    self.assertEqual(len(list(capture_project.setup_path().parent.glob("setup.json.damaged-*"))), 1)
```

- [ ] **Step 2: Run** `python -m unittest tests.test_capture_project -v` → FAIL (names missing).
- [ ] **Step 3: Implement** the interfaces above. `canvas_size`: short side = height, long side = round(height × ratio) to the nearest even number. `video_bitrate`: `round(w*h*fps*0.11)`, × 1.5 for `max`, × 0.65 for `hevc` (apply factors before rounding). Volumes 0.0–2.0; `countdown` in {0, 3, 5, 10}; `height` in HEIGHTS; booleans must be real bools.
- [ ] **Step 4: Run** the same command → PASS.

---

### Task 3: Project files, timeline intervals, effective scenes

**Files:**
- Modify: `src/unlawful/capture_project.py`
- Test: `tests/test_capture_project.py`

**Interfaces:**
- Consumes: Task 2 names.
- Produces:
  - `PROJECT_FORMAT = "unlaw-studio-project"`, `projects_dir() -> Path` (= `storage_path("captures", "projects")`)
  - `create_project(kind: str, setup: dict, recorded: dict) -> Path` (exclusive `mkdir` of `projects_dir()/<kind>-<YYYYmmdd-HHMMSS>` with ` 2` suffix on clash; makes `media/ assets/ logs/ cache/`; copies used assets from `storage_path("studio", "assets")`; writes `project.json` with `state: "recording"`, `segments: []`, `events: [{"t": 0.0, "scene": setup["scene"]}]`)
  - `read_project(folder: Path) -> dict` (validates, raises `ProjectError`), `write_project(folder: Path, data: dict) -> None` (validates, atomic, keeps unknown keys)
  - `validate_project(data: object, folder: Path) -> dict`
  - `add_event(folder: Path, event: dict) -> dict`
  - `segment_starts(durations: dict[str, float], reference: str) -> dict[str, float]` (end alignment: `start = ref - track`, rounded to 3 decimals)
  - `timeline_intervals(project: dict, fps: int) -> list[dict]` → `[{"segment": int, "start": float, "length": float, "scene": str}]`
  - `effective_placements(project: dict, scene: str, canvas: str) -> tuple[dict, list[tuple[str, dict]]]` → (background, [(source_id, placement)] in z order, only visible and recorded sources; when only the screen remains, the `screen` scene's layout)

project.json as spec §6.3 with two decisions: `sources` is a **list** in z order (same items as setup plus recorded facts: screen `size`, `fps`; camera `device`, `mode`), and the last export settings live in `"export"`. `state` in `recording|saving|ready|incomplete`; `problems` is a list of strings.

- [ ] **Step 1: Write failing tests**

```python
def test_intervals_split_at_segments_and_scenes(self):
    project = {"segments": [{"duration": 10.0}, {"duration": 5.0}],
               "events": [{"t": 0.0, "scene": "screen-camera"}, {"t": 4.0, "scene": "camera"},
                          {"t": 4.0, "mark": "x"}, {"t": 12.0, "scene": "screen"}]}
    got = capture_project.timeline_intervals(project, 60)
    self.assertEqual(got, [
        {"segment": 0, "start": 0.0, "length": 4.0, "scene": "screen-camera"},
        {"segment": 0, "start": 4.0, "length": 6.0, "scene": "camera"},
        {"segment": 1, "start": 0.0, "length": 2.0, "scene": "camera"},
        {"segment": 1, "start": 2.0, "length": 3.0, "scene": "screen"}])

def test_intervals_round_to_frames_and_drop_empty_ones(self):
    project = {"segments": [{"duration": 1.0}, {"duration": 0.004}],
               "events": [{"t": 0.0, "scene": "screen"}, {"t": 0.5071, "scene": "camera"}, {"t": 0.5072, "scene": "screen"}]}
    got = capture_project.timeline_intervals(project, 60)
    self.assertEqual([round(i["start"] * 60, 6) % 1 for i in got], [0.0] * len(got))
    self.assertTrue(all(i["length"] >= 1 / 60 for i in got))

def test_end_alignment(self):
    self.assertEqual(capture_project.segment_starts({"screen": 10.0, "camera": 9.69, "mic": 9.06}, "screen"),
                     {"screen": 0.0, "camera": 0.31, "mic": 0.94})
    self.assertEqual(capture_project.segment_starts({"screen": 10.0, "mic": 10.2}, "screen")["mic"], -0.2)

def test_project_round_trip_keeps_unknown_keys_and_refuses_escapes(self):
    folder = capture_project.create_project("screen", capture_project.default_setup({}), {})
    data = capture_project.read_project(folder)
    data["future"] = {"x": 1}
    capture_project.write_project(folder, data)
    self.assertEqual(capture_project.read_project(folder)["future"], {"x": 1})
    for bad in ("media/../../etc/passwd", "/etc/passwd", "media/link.mp4"):
        if bad.endswith("link.mp4"):
            (folder / "media" / "link.mp4").symlink_to("/etc/hosts")
        data["segments"] = [{"duration": 1.0, "files": {"screen": bad}, "starts": {"screen": 0.0}}]
        with self.subTest(bad=bad), self.assertRaises(capture_project.ProjectError):
            capture_project.validate_project(data, folder)

def test_missing_camera_falls_back_to_the_screen_layout(self):
    folder = capture_project.create_project("screen", capture_project.default_setup({}), {})
    project = capture_project.read_project(folder)
    background, placements = capture_project.effective_placements(project, "screen-camera", "9:16")
    self.assertEqual([sid for sid, _ in placements], ["screen"])
    self.assertEqual(background, {"kind": "blur"})
```

- [ ] **Step 2: Run** `python -m unittest tests.test_capture_project -v` → FAIL.
- [ ] **Step 3: Implement.** Interval algorithm: build the global boundary list = segment starts ∪ scene-event times (marks ignored), round each to `round(t * fps) / fps`, walk segments in order, emit `[a, b)` pieces with the scene active at `a`, drop pieces with `length < 1/fps`. A file path is valid only when it is relative, has no `..` parts, resolves inside `folder`, and is not a symlink.
- [ ] **Step 4: Run** → PASS.

---

### Task 4: macOS backend

**Files:**
- Modify: `src/unlawful/capture_mac.py`, `src/unlawful/capture.py` (move `_ffmpeg_devices`, `_displays`, `devices`, `is_loopback`, `LOOPBACK_WORDS` into the backend; `capture.py` calls `backend()`)
- Test: `tests/test_capture_mac.py` (new); fixture `tests/fixtures/capture/camera-modes.txt` (the real "Supported modes" stderr recorded on 2026-11-19, spec §4)

**Interfaces:**
- Produces in `capture_mac.py`:
  - `class MacBackend:` with methods
    - `devices() -> dict` (same JSON as today's `devices()`: displays, cameras, microphones[name, virtual], ffmpeg)
    - `camera_modes(name: str, *, refresh: bool = False) -> list[dict]` (probe with `-framerate 1000`, parse, cache in `storage_path("runtime", "camera-modes.json")`)
    - `screen_argv(plan: dict, out: Path) -> list[str]`
    - `camera_argv(plan: dict, out: Path, *, nv12: bool = True) -> list[str]`
    - `mic_argv(plan: dict, out: Path) -> list[str]` (levels branch writes `mic-levels.txt` relative to the process cwd = project `logs/`)
    - `preview(display: int) -> Path` (today's `preview()` moved)
    - `permission_probe() -> dict` → `{"screen": bool}` (1x1 `screencapture -x -R0,0,1,1` into a temp file)
    - `responsible_app(pid: int | None = None) -> str | None`
    - `settings_url(kind: str) -> str` for `screen|camera|microphone`
    - `menubar_argv(unlaw_bin: str, state_file: Path) -> list[str]` (filled in Task 8)
  - `parse_modes(text: str) -> list[dict]` → `[{"width": 1920, "height": 1080, "min_fps": "15.000000", "max_fps": "30.000000"}, …]`
  - `pick_mode(modes: list[dict], quality: str, wanted: str = "auto") -> dict | None` → `{"width", "height", "fps"}` (`fps` = the device's max string)
  - `backend() -> MacBackend` (raises `CaptureError("recording is not supported on this system yet", 1)` off macOS; `CaptureError` stays in `capture.py`, so the backend raises a local `BackendError(Exception)` that `capture.py` converts)

Plan dict for argv builders: `{"display": int, "area": "x,y,w,h" | None, "clicks": bool, "system": bool, "camera": str, "mode": {"width","height","fps"}, "bitrate": int, "mic": str, "mic_format": "flac|wav|m4a"}`.

Exact argv (pinned by tests):
- screen: `["screencapture", "-v", "-x", "-D1", ("-R" + area), "-k", "-A", out]` (flags present only when set; never `-g`).
- camera: `["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-f", "avfoundation", "-pixel_format", "nv12", "-framerate", fps, "-video_size", "WxH", "-i", f"{camera}:none", "-c:v", "h264_videotoolbox", "-b:v", str(bitrate), "-g", str(round(float(fps))), "-movflags", "+frag_keyframe+empty_moov+default_base_moof", out]` (without the `-pixel_format` pair when `nv12=False`).
- mic: `[…"-f", "avfoundation", "-i", f":{mic}", "-filter_complex", "[0:a]asplit=2[rec][mon];[mon]astats=metadata=1:reset=4,ametadata=mode=print:key=lavfi.astats.Overall.Peak_level:file=mic-levels.txt,anullsink", "-map", "[rec]", *codec, out]` with codec `flac: ["-c:a", "flac"]`, `wav: ["-c:a", "pcm_s16le"]`, `m4a: ["-c:a", "aac", "-b:a", "256k", "-movflags", "+frag_keyframe+empty_moov"]`.

- [ ] **Step 1: Write failing tests**

```python
def test_modes_are_parsed_and_picked(self):
    modes = capture_mac.parse_modes((FIXTURES / "camera-modes.txt").read_text())
    self.assertIn({"width": 1920, "height": 1080, "min_fps": "15.000000", "max_fps": "30.000000"}, modes)
    self.assertEqual(capture_mac.pick_mode(modes, "high"), {"width": 1920, "height": 1080, "fps": "30.000000"})
    self.assertEqual(capture_mac.pick_mode(modes, "light"), {"width": 1280, "height": 720, "fps": "30.000000"})
    self.assertEqual(capture_mac.pick_mode([{"width": 1552, "height": 1552, "min_fps": "1", "max_fps": "30.000030"}], "high")["fps"], "30.000030")
    self.assertEqual(capture_mac.pick_mode(modes, "high", "1280x720@30"), {"width": 1280, "height": 720, "fps": "30.000000"})

def test_device_names_stay_one_argument(self):
    b = capture_mac.MacBackend()
    plan = {"display": 2, "area": None, "clicks": True, "system": True, "camera": "Haos's Phone Camera",
            "mode": {"width": 1920, "height": 1080, "fps": "30.000000"}, "bitrate": 6_000_000,
            "mic": "Haos's Phone Microphone «Ü»", "mic_format": "flac"}
    self.assertIn("Haos's Phone Camera:none", b.camera_argv(plan, Path("c.mp4")))
    self.assertIn(":Haos's Phone Microphone «Ü»", b.mic_argv(plan, Path("m.flac")))
    self.assertEqual(b.screen_argv(plan, Path("s.mov")), ["screencapture", "-v", "-x", "-D2", "-k", "-A", "s.mov"])
    self.assertNotIn("-pixel_format", b.camera_argv(plan, Path("c.mp4"), nv12=False))

def test_responsible_app_skips_python(self):
    # fake `ps` answers a chain Python.app -> zsh -> login -> Ghostty.app
    ...  # fake ps via self.tool("ps", body=...) mapping pid -> "ppid comm"
    self.assertEqual(capture_mac.MacBackend().responsible_app(500), "Ghostty")

def test_settings_urls(self):
    self.assertEqual(capture_mac.MacBackend().settings_url("screen"),
                     "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
```
(`test_responsible_app_skips_python`: the fake `ps` prints, for `-o ppid=,comm= -p N`, lines from a dict `{500: "400 /opt/homebrew/…/Python.app/Contents/MacOS/Python", 400: "300 -zsh", 300: "200 /usr/bin/login", 200: "1 /Applications/Ghostty.app/Contents/MacOS/ghostty"}`; write it fully in the test.)

- [ ] **Step 2: Run** `python -m unittest tests.test_capture_mac -v` → FAIL.
- [ ] **Step 3: Implement** the backend; keep `devices` output identical so `CaptureTests.test_devices…` (existing) still passes. The mode probe argv: `["ffmpeg", "-hide_banner", "-nostdin", "-f", "avfoundation", "-framerate", "1000", "-i", f"{name}:none", "-t", "0.1", "-f", "null", "-"]`, timeout 15 s.
- [ ] **Step 4: Run** `python -m unittest tests.test_capture_mac tests.test_command_paths -v` → PASS.
- [ ] **Step 5: Real-tool check (once, by the implementer, not in the suite)**: run `mic_argv` for 2 s with the default mic into a scratch dir; confirm `mic-levels.txt` contains `lavfi.astats.Overall.Peak_level=` lines and the FLAC plays (`ffprobe`). If the filter string fails on ffmpeg 8.1, fix the string and the test together.

---

### Task 5: Recording engine v2

**Files:**
- Modify: `src/unlawful/capture.py`, `tests/test_command_paths.py` (fakes and `CaptureTests`)

**Interfaces:**
- Consumes: Tasks 2–4.
- Produces in `capture.py`:
  - `STATE_VERSION = 2`, `STOP_GRACE = 30.0`, `TERM_GRACE = 10.0` (module constants; tests patch them small)
  - `start_recording(mode: str = "screen", *, scene: str | None = None, canvas: str | None = None, overrides: dict | None = None) -> dict` (status dict)
  - `pause_recording() -> dict`, `resume_recording() -> dict`
  - `switch_scene(scene: str) -> dict`, `add_mark(label: str = "") -> dict`
  - `stop_recording(*, force: bool = False) -> dict` → `{"active": False, "project": str, "saved": str, "elapsed": float, "state": "ready"|"incomplete", "problems": [...]}`; raises `CaptureError` with `.data = {"stuck": [...], "project": str}` when a recorder hangs and `force` is False
  - `status() -> dict` adds `project`, `scene`, `tracks`, `level_db`, `stuck`, `free_bytes`, `warnings`
  - `_wrap_legacy_state(state: dict) -> Path` (v1 → project, best effort)

`overrides` keys (CLI flags / desk legacy body): `camera: bool`, `cam`, `cam_mode`, `cam_quality`, `mic` (`"none"` disables), `mic_format`, `system_audio`, `display`, `rect`, `clicks`.

Fake tool changes (in `tests/test_command_paths.py`):
- `FAKE_SCREENCAPTURE`: with `-v` it writes its file only when it stops, like the real tool (spec §4); `FAKE_STUCK=1` ignores SIGINT and SIGTERM while recording (exits only on SIGKILL, leaving no file); `-R0,0,1,1` writes a 1-byte png (fails with `FAKE_FAIL=1`).
- `FAKE_FFMPEG`: when `-filter_complex` contains `mic-levels.txt`, append `lavfi.astats.Overall.Peak_level=-21.5` (or `=-80.0` with `FAKE_SILENT=1`) to `mic-levels.txt` in cwd every 0.1 s with `pts_time` lines; `FAKE_NO_NV12=1` exits 1 printing `Selected pixel format (nv12) is not supported by the input device.` when `-pixel_format` is in argv; remux (`-c copy` with `+faststart`) copies the input bytes; `-framerate 1000` prints the modes fixture to stderr and exits 1.
- `FAKE_FFPROBE`: duration from the env var `FAKE_DURATION_<basename-stem>` if set, else `2.5`.

- [ ] **Step 1: Rewrite the old pipeline tests to the approved behavior** (same intent, new results; list them in the task report for Haos):
  - `test_screen_recording_pauses_resumes_and_joins_the_parts` → asserts `saved` is a folder in `projects_dir()` with `media/screen-001.mp4` and `media/screen-002.mp4` (bytes `b"screen"` each), `project.json` `state == "ready"`, two segments, no `-g` in screencapture argv, mic ffmpeg argv present, state file gone.
  - `test_screen_with_camera_and_mp4` → camera argv has `-framerate 30.000000 -video_size 1920x1080` (setup `high`), `media/camera-001.mp4` exists, `--format mp4` is stored as `export.container == "mp4"`.
  - `test_a_named_or_virtual_microphone_is_recorded_separately` → still warns about BlackHole; mic argv `:BlackHole 2ch`.
  - `test_audio_and_camera_recordings`, `test_duration_records_in_the_foreground_and_saves`, `test_a_recorder_that_dies_ends_a_timed_recording_and_saves_it`, `test_ctrl_c_while_saving_keeps_the_recording_for_another_stop`, `test_missing_screen_preserves_secondary_recording_and_state` → same intent with project results.

- [ ] **Step 2: Write new failing tests**

```python
def test_scenes_and_marks_are_timestamped(self):
    self.media_tools()
    self.ok("record", "--camera")
    time.sleep(0.3); self.ok("scene", "3")
    time.sleep(0.2); self.ok("mark", "intro done")
    project = Path(json.loads(self.ok("stop", "--json"))["project"])
    events = json.loads((project / "project.json").read_text())["events"]
    self.assertEqual([e.get("scene") or e.get("mark") for e in events], ["screen-camera", "camera", "intro done"])
    self.assertTrue(0.2 <= events[1]["t"] < events[2]["t"])

def test_a_stuck_screen_recorder_is_not_killed(self):
    self.media_tools()
    with patch.object(capture, "STOP_GRACE", 0.3), patch.object(capture, "TERM_GRACE", 0.2), patch.dict(os.environ, {"FAKE_STUCK": "1"}):
        self.ok("record")
        code, out, _ = self.run_main(capture.main, ["stop", "--json"])
        self.assertEqual(code, 1)
        answer = json.loads(out)
        self.assertEqual(answer["stuck"], ["screencapture"])
        self.assertTrue(json.loads(self.ok("status", "--json"))["stuck"])
        project = json.loads((Path(answer["project"]) / "project.json").read_text())
        self.assertEqual(project["state"], "incomplete")
        self.assertTrue((Path(answer["project"]) / "media" / "mic-001.flac").exists(), "the mic track is kept")
        done = json.loads(self.ok("stop", "--force", "--json"))
    self.assertEqual(done["state"], "incomplete")
    self.assertFalse(capture.recording_state_file().exists())

def test_a_camera_that_refuses_nv12_is_retried_without_it(self):
    logs = self.media_tools()
    with patch.dict(os.environ, {"FAKE_NO_NV12": "1"}):
        self.ok("record", "--camera")
    cams = [l for l in self.lines(logs["ffmpeg"]) if ":none" in l and "-video_size" in l]
    self.assertEqual(["-pixel_format" in l for l in cams[-2:]], [True, False])

def test_status_warns_about_a_silent_microphone(self):
    self.media_tools()
    with patch.object(capture, "SILENCE_SECONDS", 0.5), patch.dict(os.environ, {"FAKE_SILENT": "1"}):
        self.ok("record")
        time.sleep(0.9)
        status = json.loads(self.ok("status", "--json"))
    self.assertLess(status["level_db"], -60)
    self.assertTrue(any("microphone is silent" in w for w in status["warnings"]))

def test_a_dying_camera_leaves_a_project_with_the_rest(self):   # Review Focus 2
    self.media_tools()
    with patch.dict(os.environ, {"FAKE_RECORDER_DIES": "0.3"}):
        self.ok("record", "--camera")
        time.sleep(0.6)
        self.assertEqual(json.loads(self.ok("status", "--json"))["phase"], "interrupted")
    result = json.loads(self.ok("stop", "--json"))
    project = json.loads((Path(result["project"]) / "project.json").read_text())
    self.assertEqual(project["state"], "incomplete")
    self.assertIn("screen", project["segments"][0]["files"])

def test_stop_right_after_start_saves(self):   # Review Focus 3
    self.media_tools()
    self.ok("record"); result = json.loads(self.ok("stop", "--json"))
    self.assertIn(result["state"], ("ready", "incomplete"))

def test_start_while_saving_answers_at_once(self):
    ...  # hold the recording lock with phase "saving" in the state file from a thread; `record` must fail within 6 s with "still saving"

def test_missing_screen_permission_stops_before_recording(self):
    self.media_tools()
    with patch.dict(os.environ, {"FAKE_FAIL": "1"}):
        code, _, error = self.run_main(capture.main, ["record"])
    self.assertEqual(code, 1)
    self.assertIn("Screen Recording permission", error)
    self.assertIn("System Settings", error)
    self.assertEqual(list(capture_project.projects_dir().glob("*")), [], "no empty project is left behind")

def test_a_version_1_state_is_wrapped_into_a_project(self):
    ...  # write a minimal valid v1 recording.json + its parts dir with 000-screen.mov; `stop --json` returns a project whose media holds that file
```
(The two `...` tests are written in full by the implementer from the sentence in their comment; they assert exactly what the comment says.)

- [ ] **Step 3: Run** `python -m unittest tests.test_command_paths -k Capture -v` → new tests FAIL.
- [ ] **Step 4: Implement** per spec §7. Key decisions:
  - Preflight: when the screen is a source, `backend().permission_probe()` runs first; a failure raises `CaptureError` naming `responsible_app()` ("Give Ghostty Screen Recording permission: System Settings > Privacy & Security > Screen Recording", plus `ul capture doctor --open screen`) before any project folder exists.
  - `record` creates the project (Task 3), writes state v2 `{version, project, mode, phase, paused, elapsed, segment_started, segments, processes, helpers, warnings, stuck, started, scene}`; recorder cwd = project `logs/`; logs go to `logs/record.log` (also keep appending to `runtime/recording.log`).
  - Track files while recording: `media/.screen-NNN.mov`, `media/.camera-NNN.mp4`, `media/mic-NNN.<ext>`; at stop: remux `.screen` → `screen-NNN.mp4` and `.camera` → `camera-NNN.mp4` with `-c copy -movflags +faststart`, delete the dot files after a successful remux; repair a WAV whose RIFF/data sizes are wrong (set them from the file size).
  - Camera nv12 refusal: if the camera process exits during the 0.7 s start check and its log tail contains `pixel format`, start it once more with `nv12=False`.
  - Stop: SIGINT recorders together, wait `max(STOP_GRACE, 0.05 * elapsed)`, SIGTERM, wait `TERM_GRACE`; alive ones → stuck (or SIGKILL with `force`). Helpers (menu bar) get SIGTERM and are never waited on.
  - Starts: `segment_starts` with reference `screen`, else `camera`, else `mic`; durations from `_probe`.
  - `SILENCE_SECONDS = 10.0`, threshold −60 dB; free-space warning below 5 GB (`shutil.disk_usage`).
  - Start uses a non-blocking lock attempt; if the lock is held and the state says `saving`, raise `CaptureError("the previous recording is still saving", 1)`; otherwise retry for up to 5 s.
  - `status()` keeps every old key and value meaning.
- [ ] **Step 5: Run** `python -m unittest tests.test_command_paths -v` → PASS.

---

### Task 6: Export

**Files:**
- Modify: `src/unlawful/capture_export.py`
- Test: `tests/test_capture_export.py` (new; uses fake ffmpeg/ffprobe from `tests/test_command_paths.py`)

**Interfaces:**
- Consumes: Tasks 2–3 (`canvas_size`, `video_bitrate`, `timeline_intervals`, `effective_placements`, `read_project`, `write_project`).
- Produces:
  - `png_gray(width: int, height: int, alpha) -> bytes`, `png_rgba(width: int, height: int, pixel) -> bytes` (zlib + struct writers)
  - `mask_png(width: int, height: int, radius_px: float) -> bytes`
  - `frame_png(width: int, height: int, radius_px: float, border_px: int, color: str, shadow: bool) -> tuple[bytes, int]` (RGBA, padding)
  - `export_settings(project: dict, setup_export: dict, overrides: dict) -> dict` (validated; overrides > project `export` > setup `export` > defaults)
  - `interval_argv(folder: Path, project: dict, interval: dict, settings: dict, out: Path, cache: Path) -> list[str]`
  - `audio_argv(folder: Path, project: dict, segment: int, settings: dict, out: Path) -> list[str] | None`
  - `export_project(folder: Path, settings: dict, output: Path | None = None, progress: Callable[[float], None] | None = None) -> Path`
  - `export_status_file() -> Path` (= `storage_path("runtime", "export.json")`), `read_export_status() -> dict`
  - `EXPORT_LOCK = "export"` (flock name)

- [ ] **Step 1: Write failing tests**

```python
def test_mask_alpha(self):
    w, h, rows = decode_png(capture_export.mask_png(100, 60, 30))   # helper in the test file
    self.assertEqual((w, h), (100, 60))
    self.assertEqual(rows[30][50], 255); self.assertEqual(rows[0][0], 0)
    self.assertTrue(all(v == 255 for row in decode_png(capture_export.mask_png(10, 6, 0))[2] for v in row))

def test_16x9_camera_and_screen_geometry(self):
    folder = make_project(screen_size=(3600, 2338), camera=True)   # helper: create_project + fake media + segments
    settings = capture_export.export_settings(read(folder), {}, {"canvas": "16:9", "height": 1440, "fps": 60})
    argv = capture_export.interval_argv(folder, read(folder), {"segment": 0, "start": 0.0, "length": 2.0, "scene": "screen-camera"}, settings, Path("o.mp4"), folder / "cache")
    graph = argv[argv.index("-filter_complex") + 1]
    self.assertIn("scale=2218:1440", graph); self.assertIn("overlay=171:0", graph)
    self.assertIn("hflip", graph); self.assertIn("overlay=0:1094", graph)
    self.assertIn("24330240", argv); self.assertIn("h264_videotoolbox", argv)
    self.assertIn("-itsoffset", argv)          # camera starts 0.31 s late (fixture starts)

def test_9x16_stack_crops_around_focus(self):
    ...  # same helper, canvas 9:16 height 1080: graph contains "1080:768" for the camera box and "1080:1152" for the screen box

def test_source_canvas_copies_the_screen(self):
    ...  # export with canvas "source": no "-filter_complex" in the video step, a concat with "-c copy"; output bytes == screen-001 + screen-002

def test_export_records_itself_and_never_overwrites(self):
    ...  # two exports of the same project/settings → "<name> 16x9.mov" and "<name> 16x9 2.mov"; project.json exports has 2 entries

def test_paths_with_spaces_cyrillic_and_quotes(self):   # Review Focus 4
    ...  # storage root "Студия 'x'" → export succeeds with fake ffmpeg; the concat list line for each chunk escapes ' as '\''

def test_a_failed_export_leaves_no_partial_file(self):
    ...  # FAKE_FFMPEG_FAIL="overlay" → CaptureError; no file in recordings; project.json unchanged (byte-equal)

def test_delete_sources_moves_the_project_to_the_trash(self):
    ...  # settings delete_sources=True → project folder now under HOME/.Trash, export file kept

def test_zero_length_segments_export(self):   # Review Focus 3
    ...  # project with a 0.004 s second segment exports one chunk only

@unittest.skipUnless(os.environ.get("UNLAW_REAL_MEDIA") == "1", "opt-in: real ffmpeg on synthetic sources")
def test_real_ffmpeg_export(self):
    ...  # lavfi testsrc2 3600x2338@60 2 s + testsrc 1920x1080@30 + sine mic; export 16:9 1440p60 and 9:16 1080; ffprobe: sizes, 60/1, duration within 0.1 s
```

- [ ] **Step 2: Run** `python -m unittest tests.test_capture_export -v` → FAIL.
- [ ] **Step 3: Implement** per spec §8:
  - Geometry: box px = `round(frac * canvas)` made even; `contain` scales the source to fit and centres it in the box; `cover` scales to fill and crops a box-sized window centred on `focus` (clamped). Radius px = `radius * min(box_w, box_h)`; border px = `round(border.width * min(canvas) / 1080)`.
  - Per source: `[n:v]` (+`hflip` if mirror) → crop/scale → `format=yuva420p` + `alphamerge` with `-loop 1 -i cache/mask-<sha1>.png` when radius > 0 → shadow/border frame PNG overlaid under/over → `overlay=x:y:eof_action=pass`. Background: `color=c=<hex>:s=WxH:r=fps` or the screen cover-scaled + `boxblur=40:2`.
  - Track timing inside an interval: input `-ss max(0, a - start)` and `-itsoffset max(0, start - a)` for that track, `-t length` on the reference input.
  - Encoder: `-c:v h264_videotoolbox|hevc_videotoolbox` (+`-tag:v hvc1`), `-b:v <video_bitrate>`, `-g <2*fps>`, `-r <fps>`, `-pix_fmt yuv420p`, BT.709 tags, `-an`, `-progress pipe:1 -nostats`; chunks → `cache/render/<n>.mp4` → concat demuxer (`-f concat -safe 0`, `-c copy`) → mux with the audio.
  - Audio per segment → `cache/audio-<n>.wav` (`amix=inputs=K:normalize=0:duration=longest`, `volume=`, `apad`, `atrim=0:<duration>`, `aformat=sample_rates=48000:channel_layouts=stereo`), concat, final AAC 256k with `loudnorm=I=-14:TP=-1:LRA=11,aresample=48000` when `normalize`.
  - Output `storage_path("captures","recordings") / f"{name} {canvas.replace(':','x')}.{container}"` through `_free`; audio-only projects: `.<capture.audio_format>`. Write to `<out>.part-<pid>` then `os.replace`; on failure delete it.
  - Progress: sum `out_time_us` over chunks / total, written to `export.json` (`{"project","phase":"queued|running|done|failed","percent","eta","output","error"}`) at most twice a second; `os.nice(10)` at export start.
- [ ] **Step 4: Run** `python -m unittest tests.test_capture_export -v` → PASS; then `UNLAW_REAL_MEDIA=1 python -m unittest tests.test_capture_export -k real -v` → PASS (implementer runs it once on this Mac).

---

### Task 7: CLI surface and help

**Files:**
- Modify: `src/unlawful/capture.py` (`main`), `src/unlawful/command_help.py` (`COMMAND_HELP["capture"]`), `tests/test_command_paths.py`

**Interfaces:**
- Consumes: Tasks 2–6.
- Produces (actions; every one supports `--json`, errors as `{"error": …}` like today):
  - `record [screen|camera|audio] [--camera] [--scene ID|N] [--canvas C] [--cam NAME] [--cam-mode WxH@FPS|auto] [--cam-quality max|high|light] [--mic NAME|--no-mic] [--mic-format flac|wav|m4a] [--system-audio|--no-system-audio] [--display N] [--rect X,Y,W,H] [--no-clicks] [--countdown N] [--duration S] [--wait] [--export] [--format F] [--output PATH]` (`--output`/`--format` imply `--export` at stop)
  - `scene N|ID`, `mark [TEXT]`, `stop [--force] [--export [export flags]]`
  - `projects`, `project NAME|PATH|last [--set-json -] [--remember]`
  - `export NAME|PATH|last [--canvas C] [--height H] [--fps F] [--codec C] [--quality Q] [--format mov|mp4] [--normalize|--no-normalize] [--delete-sources] [--output PATH] [--background]`, `export --status`
  - `setup [--set-json -] [--reset]`, `devices [--modes] [--camera NAME]`, `doctor [--open screen|camera|microphone]`
  - `delete NAME` also takes a project (folder to the Trash)
  - `--background` re-runs the same export detached (`start_new_session=True`, stdin/stdout to `/dev/null`) and prints `{"queued": true}`.

- [ ] **Step 1: Write failing tests** (extend `test_usage_and_argument_errors` cases and add):

```python
cases.update({
    ("record", "--canvas", "21:9"): "--canvas must be one of 16:9, 9:16, 1:1, 4:5, source",
    ("record", "--cam-quality", "ultra"): "--cam-quality must be max, high or light",
    ("record", "--mic-format", "ogg"): "--mic-format must be flac, wav or m4a",
    ("export",): "usage: ul capture export",
    ("export", "last", "--height", "720"): "--height must be 1080, 1440 or 2160",
    ("scene",): "usage: ul capture scene",
})

def test_projects_export_and_json_contracts(self):
    self.media_tools()
    self.ok("record"); stop = json.loads(self.ok("stop", "--json"))
    self.assertEqual(stop["saved"], stop["project"], "no export: saved is the project folder")
    listed = json.loads(self.ok("projects", "--json"))
    self.assertEqual(listed[0]["path"], stop["project"])
    out = json.loads(self.ok("export", "last", "--canvas", "source", "--format", "mp4", "--json"))
    self.assertTrue(out["saved"].endswith(" source.mp4"))
    self.assertEqual(json.loads(self.ok("export", "--status", "--json"))["phase"], "done")

def test_record_output_still_gives_a_file(self):
    self.media_tools()
    target = self.root / "talk.mov"
    self.ok("record", "--output", str(target))
    self.assertEqual(json.loads(self.ok("stop", "--json"))["saved"], str(target))

def test_setup_round_trip_and_doctor(self):
    self.media_tools()
    setup = json.loads(self.ok("setup", "--json")); setup["canvas"] = "9:16"
    with patch.object(capture.sys, "stdin", io.StringIO(json.dumps(setup))):
        self.ok("setup", "--set-json", "-")
    self.assertEqual(json.loads(self.ok("setup", "--json"))["canvas"], "9:16")
    doctor = json.loads(self.ok("doctor", "--json"))
    self.assertEqual(doctor["screen"], True)            # fake screencapture writes the 1x1 probe
    self.assertIn("app", doctor)

def test_help_is_static_and_lists_new_actions(self):
    help_text = self.ok("--help")
    for word in ("record [screen", "scene", "mark", "projects", "export", "setup", "doctor", "--canvas"):
        self.assertIn(word, help_text)
```

- [ ] **Step 2: Run** `python -m unittest tests.test_command_paths -k Capture -v` → FAIL.
- [ ] **Step 3: Implement** the dispatch and help. Help text (update `COMMAND_HELP["capture"]`) keeps today's sections and adds: Studio projects (what a project folder holds), scenes/marks, export flags with defaults (16:9 1440p60 H.264 high, loudness on, container from `capture.video_format`), setup file location, doctor, the TUI (`ul capture` in a terminal), examples (`ul capture record --camera`, `ul capture scene 3`, `ul capture export last --canvas 9:16`). Static text only.
- [ ] **Step 4: Run** `python -m unittest tests.test_command_paths tests.test_help_youtube tests.test_skills -v` → PASS.

---

### Task 8: Menu-bar control

**Files:**
- Modify: `src/unlawful/capture_mac.py` (`MENUBAR_JS`, `menubar_argv`), `src/unlawful/capture.py` (spawn/track/stop helper), `tests/test_command_paths.py`

**Interfaces:**
- Consumes: Task 5 state `helpers` list (`{"pid", "program": "osascript", "lstart"}`), `_valid_state` accepting it.
- Produces: `menubar_argv(unlaw_bin, state_file) -> ["osascript", "-l", "JavaScript", "-e", MENUBAR_JS, unlaw_bin, str(state_file)]`; `MENUBAR_JS` defines `run(argv)` that: sets accessory activation policy, creates an `NSStatusItem`, every second reads `argv[1]` (state JSON) and sets the title to `● mm:ss` / `❚❚ mm:ss`, rebuilds the menu (Stop and save · Pause/Resume · Scenes with ✓ on the current · Add mark · Open Studio) when the scene list or phase changes, runs `NSTask` with `launchPath = argv[0]` and `arguments = ["capture", action, …]` (Open Studio: `["desk"]`), and returns when the state file is gone or its `project` changed.

- [ ] **Step 1: Write failing test**

```python
def test_menubar_helper_follows_the_recording(self):
    logs = self.media_tools()
    os.environ["UNLAW_BIN"] = "/fake/ul"
    self.ok("record")
    call = self.lines(logs["osascript"])[-1].split("|")
    self.assertEqual(call[:3], ["-l", "JavaScript", "-e"])
    self.assertEqual(call[-2:], ["/fake/ul", str(capture.recording_state_file())])
    self.ok("stop")
    setup = json.loads(self.ok("setup", "--json")); setup["menubar"] = False
    with patch.object(capture.sys, "stdin", io.StringIO(json.dumps(setup))):
        self.ok("setup", "--set-json", "-")
    before = len(self.lines(logs["osascript"])); self.ok("record"); self.ok("stop")
    self.assertEqual(len(self.lines(logs["osascript"])), before)
```
(The fake `osascript` must stay alive until SIGTERM when `-l JavaScript` is passed; extend the fake accordingly.)

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (spawn only on macOS, only when `UNLAW_BIN` is set and `setup.menubar`). **Step 4: Run** `python -m unittest tests.test_command_paths -k menubar -v` → PASS.
- [ ] **Step 5: Manual check (Haos)**: during a real recording, the menu-bar item shows the clock; Stop, Pause, a scene and Add mark each work. Record the result in the task report.

---

### Task 9: Terminal UI

**Files:**
- Modify: `src/unlawful/capture_tui.py`, `src/unlawful/capture.py` (`main` with no args in a TTY → `run_tui()`; the numbered `_menu` is removed)
- Test: `tests/test_capture_tui.py` (new)

**Interfaces:**
- Consumes: `load_setup`, `save_setup`, `status`, `devices`, `start_recording`, `stop_recording`, `switch_scene`, `add_mark`, `pause_recording`, `resume_recording`, `read_export_status`.
- Produces:
  - `render_frame(model: dict, cols: int, rows: int) -> list[str]` (exactly `rows` strings, each ≤ `cols` display cells)
  - `tui_action(key: str, model: dict) -> tuple[str, ...] | None` → `("record",)`, `("stop",)`, `("pause",)`, `("scene", "<id>")`, `("mark",)`, `("canvas", "<next>")`, `("devices",)`, `("export",)`, `("quit",)`
  - `run_tui() -> int` (curses; refresh 4×/s; quitting never stops a recording)
  - model keys: `setup`, `status`, `devices`, `focus` (`"scenes"|"sources"`), `message`, `export` (status dict or None)

- [ ] **Step 1: Write failing tests**

```python
def test_frame_shows_recording(self):
    model = {"setup": capture_project.default_setup({}), "focus": "scenes", "message": "", "export": None, "devices": None,
             "status": {"active": True, "phase": "recording", "paused": False, "elapsed": 751.0, "scene": "camera",
                        "level_db": -18.0, "warnings": ["the microphone is silent"], "free_bytes": 182 * 10**9}}
    text = "\n".join(capture_tui.render_frame(model, 100, 30))
    self.assertIn("● REC 00:12:31", text)
    self.assertIn("3 ● Camera", text)
    self.assertIn("the microphone is silent", text)
    self.assertIn("182 GB free", text)
    self.assertEqual(len(capture_tui.render_frame(model, 100, 30)), 30)
    self.assertTrue(all(len(line) <= 60 for line in capture_tui.render_frame(model, 60, 20)))

def test_keys(self):
    m = {"setup": capture_project.default_setup({}), "status": {"active": False}}
    self.assertEqual(capture_tui.tui_action("r", m), ("record",))
    self.assertEqual(capture_tui.tui_action("2", m), ("scene", "screen"))
    self.assertEqual(capture_tui.tui_action("f", m), ("canvas", "9:16"))
    m["status"] = {"active": True, "paused": False}
    self.assertEqual(capture_tui.tui_action("r", m), ("stop",))
    self.assertIsNone(capture_tui.tui_action("9", m))      # no 9th scene
```

- [ ] **Step 2: Run** `python -m unittest tests.test_capture_tui -v` → FAIL. **Step 3: Implement** the layout of spec §10 (scenes panel, sources with devices, status panel with a 20-cell level bar mapping −60…0 dB, key bar; after stop an "Export now?" screen with canvas/height/fps/codec/container choices and a progress bar from `read_export_status`). **Step 4: Run** → PASS; `test_usage_and_argument_errors` (non-TTY usage) still PASS.
- [ ] **Step 5: Manual check (implementer)**: `XDG_CONFIG_HOME=$(mktemp -d) ./target/debug/ul capture` in Ghostty, 80×24 and full screen: no wrapped lines, keys work, Q leaves the recording running.

---

### Task 10: Desk backend

**Files:**
- Modify: `src/unlawful/desk.py` (`Studio`, `_media`, POST/GET routes), `tests/test_desk.py` (`DeskStudioTests`)

**Interfaces:**
- Consumes: the CLI of Task 7.
- Produces (`Studio` methods → routes):
  - `run(*args, timeout=60, stdin: str | None = None)` (new `stdin`)
  - `setup()` GET `/api/studio/setup`; `save_setup(body)` POST `/api/studio/setup` → `capture setup --set-json -`
  - `scene(body)` POST `/api/studio/scene` `{scene}`; `mark(body)` POST `/api/studio/mark` `{label}`
  - `projects()` GET `/api/studio/projects`; `project(path)` GET `/api/studio/project?path=`; `save_project(body)` POST `/api/studio/project` `{path, project}`
  - `export(body)` POST `/api/studio/export` `{path, canvas, height, fps, codec, quality, format, normalize, delete_sources}` → `capture export … --background`; `export_status()` GET `/api/studio/export/status`
  - `camera_modes(device)` GET `/api/studio/camera-modes?device=`; `doctor()` GET `/api/studio/doctor`; `open_settings(body)` POST `/api/studio/open-settings` `{kind}`
  - `add_asset(name, data)` POST `/api/studio/asset?name=` (raw body, PNG/JPEG magic only, ≤ 50 MB, exclusive free name in `storage.root/studio/assets/`) → `{asset}`
  - `open_project()` POST `/api/studio/open-project` (osascript `choose folder`, then `capture project <path> --remember --json`; `{path: null}` on Cancel, `{unavailable: true}` without osascript)
  - `record(body)` accepts `{scene?, canvas?}` plus the old keys
  - `project_file(path, file) -> Path`: `path` must be inside `projects_dir()` or listed in `studio/recent-projects.json`; `file` relative, inside `media/` or `assets/`, no symlink, resolved inside → GET `/media/project?t=&path=&file=`; `/media/thumb?path=` for projects
  - `status()` unchanged keys plus Task 5 keys

- [ ] **Step 1: Write failing tests** (in `DeskStudioTests`, `self.media()` as today):

```python
def test_setup_scene_mark_and_project_flow(self):
    self.media(); port, token = self.start()
    setup = self.call(port, token, "/api/studio/setup")[1]; setup["canvas"] = "9:16"
    self.assertEqual(self.call(port, token, "/api/studio/setup", setup)[0], 200)
    self.assertEqual(self.call(port, token, "/api/studio/record", {"scene": "screen"})[0], 200)
    self.assertEqual(self.call(port, token, "/api/studio/scene", {"scene": "camera"})[0], 200)
    self.assertEqual(self.call(port, token, "/api/studio/mark", {"label": "x"})[0], 200)
    self.call(port, token, "/api/studio/stop", {}); done = self.wait_saved(port, token)
    projects = self.call(port, token, "/api/studio/projects")[1]
    self.assertEqual(projects[0]["path"], done["project"])
    status, headers, body = self.raw(port, f"/media/project?t={token}&path={quote(done['project'])}&file=media/screen-001.mp4", {"Range": "bytes=0-2"})
    self.assertEqual((status, body), (206, b"scr"))
    self.assertEqual(self.call(port, token, "/api/studio/export", {"path": done["project"], "canvas": "source", "format": "mp4"})[0], 200)

def test_project_media_refuses_escapes(self):   # Review Focus 5
    ...  # file=media/../project.json, file=/etc/hosts, path=/tmp (not a project), a symlink in media/ → 404 each

def test_assets_only_take_images(self):
    ...  # PNG bytes → 200 {asset}; b"<script>" → 400; 51 MB → 400; same name twice → "logo 2.png"
```

- [ ] **Step 2: Run** `python -m unittest tests.test_desk -k Studio -v` → FAIL. **Step 3: Implement** with the existing validation style (`isinstance` checks, length caps, no leading `-`). **Step 4: Run** → PASS, and the old `DeskStudioTests` cases pass (update only expectations that Task 5 deliberately changed: `saving_done` now carries `project`; library entries).

---

### Task 11: Move the Studio page code into `studio_ui.py` (no behavior change)

**Files:**
- Modify: `src/unlawful/studio_ui.py`, `src/unlawful/desk_ui.py`, `tests/test_desk_ui.cjs`, `tests/test_desk_ui.py`

**Interfaces:**
- Produces: `STUDIO_CSS: str`, `STUDIO_JS: str` in `studio_ui.py`; `desk_ui.py` contains the markers `/*@STUDIO_CSS@*/` and `/*@STUDIO_JS@*/` and builds `PAGE = _PAGE.replace("/*@STUDIO_CSS@*/", STUDIO_CSS).replace("/*@STUDIO_JS@*/", STUDIO_JS)`.
- The cjs harness obtains the page with `execFileSync(process.env.PYTHON || 'python3', ['-c', 'import sys; sys.path.insert(0, "src"); from unlawful.desk_ui import PAGE; sys.stdout.write(PAGE)'], {cwd: path.join(__dirname, '..')})`; `test_desk_ui.py` passes `PYTHON=sys.executable`.

- [ ] **Step 1: Move** the `.studio…` CSS rules and the JS block from `// ---- studio:` to just before `// ---- boards ----` into `studio_ui.py` verbatim (python script cut/paste), leave the markers.
- [ ] **Step 2: Run** `python -m unittest tests.test_desk_ui tests.test_desk -v` and `python -m unittest tests.test_core_layout -v` → all PASS with no test changed except the harness loader line.

---

### Task 12: Record tab

**Files:**
- Modify: `src/unlawful/studio_ui.py`, `tests/test_desk_ui.cjs`, `tests/test_desk_ui.py`

**Interfaces:**
- Consumes: Task 10 API; Task 2 shape/anchor math (must match Python numbers).
- Produces (page functions exposed through the cjs `audit` object):
  - `applyShape(placement, shape, canvas)`, `pinPlacement(placement, anchor)` (same results as Python `apply_shape`/`pin`)
  - `placementPx(placement, width, height)` → `{x, y, w, h}` (rounded, even like the export)
  - `snapPlacement(placement, canvas)` → anchors when the box is within 2 % of a corner, else `anchor: null`
  - `moveFocus(placement, dxFrac, dyFrac)`; `resizePlacement(placement, corner, dxFrac, dyFrac, keepAspect)`
  - `studioKey(code, state)` → `"record"|"stop"|"pause"|"mark"|"scene:<id>"|null` (KeyR, KeyP, KeyM, Digit1–9; ignored in inputs)
  - `studioPollDelay(visible, recording, onStudio)` → `null` when hidden, `1000` when recording on the Studio tab, `5000` otherwise
  - `countdownSteps(n)` → e.g. `[3, 2, 1]`
  - `saveSetupSoon()` (debounced 500 ms POST `/api/studio/setup`)
  - Rendering: `renderStudio(main)`, `renderRecord()`, `renderPreview()`, `renderSources()`, `renderProps()`, `renderSound()`, `renderRecBar()`; the permission banner from `/api/studio/doctor` with an "Open System Settings" button (`/api/studio/open-settings`).

Layout and controls exactly as the approved mockup `record-layout-v2` (spec §9): format switch, scenes thumbnails with keys and "+ scene", sources list with visibility and "+ source" (image upload via `/api/studio/asset`; text: font, size, colour, background, rendered to PNG with a canvas and uploaded), preview narrower than the side panels' combined width, floating camera toolbar, sound panel, properties panel (camera device, mode list, quality, shape, size, corner, border colour/width, radius, shadow, mirror; screen display, area drawn on the preview, clicks; output: camera quality and mic type with the MB/min estimate, countdown), REC bar (REC, clock, pause, mark, screenshot menu, resolution/fps, free space + estimate), warnings strip.

- [ ] **Step 1: Port the existing Studio cjs cases** (`failed_save`, `record_network`, `camera_leave`, `camera_lookup_leave`, mic lookup cases, `studio_polling`) to the new function names, keeping each assertion's meaning (a failed save can be retried; a network error never leaves the REC button disabled; camera/mic streams never outlive the tab; polling follows the recording).
- [ ] **Step 2: Write failing cases**

```js
 async studio_shape_math() {
  const h = harness();
  const cam = {visible: true, box: [0, 0.76, 0.24, 0.24], fit: 'cover', focus: [0.5, 0.5], radius: 0, border: {width: 0, color: '#ffc933'}, shadow: false, mirror: true, anchor: 'bottom-left'};
  const circle = h.a.applyShape(cam, 'circle', '16:9');
  assert.ok(Math.abs(circle.box[3] - 0.24 * 16 / 9) < 1e-9);
  assert.ok(Math.abs(circle.box[1] + circle.box[3] - 1) < 1e-9);
  assert.deepEqual(plain(h.a.placementPx(cam, 2560, 1440)), {x: 0, y: 1094, w: 614, h: 346});
  const moved = h.a.snapPlacement({...cam, box: [0.015, 0.75, 0.24, 0.24], anchor: null}, '16:9');
  assert.equal(moved.anchor, 'bottom-left');
  assert.equal(h.a.snapPlacement({...cam, box: [0.3, 0.3, 0.24, 0.24]}, '16:9').anchor, null);
 },
 async studio_keys_and_polling() {
  const h = harness();
  assert.equal(h.a.studioKey('KeyR', {active: false}), 'record');
  assert.equal(h.a.studioKey('KeyR', {active: true}), 'stop');
  assert.equal(h.a.studioKey('Digit3', {active: true, scenes: ['screen-camera', 'screen', 'camera']}), 'scene:camera');
  assert.equal(h.a.studioPollDelay(false, true, true), null);
  assert.equal(h.a.studioPollDelay(true, true, true), 1000);
  assert.equal(h.a.studioPollDelay(true, false, false), 5000);
  assert.deepEqual(plain(h.a.countdownSteps(3)), [3, 2, 1]);
 },
 async studio_setup_save_is_debounced() { /* two edits within 500 ms → one POST with the last value */ },
 async studio_permission_banner() { /* doctor {screen:false, app:'Zed'} → banner text names Zed; the button POSTs {kind:'screen'} */ },
 async rec_pill_shows_terminal_recordings() { /* view 'board', status poll answers active → recPill text starts with 'REC ' */ },
```
(`plain` and `harness` exist in the file; the commented cases are written in full by the implementer from their comment.) Add one `test_…` method per case in `tests/test_desk_ui.py`.

- [ ] **Step 3: Run** `python -m unittest tests.test_desk_ui -v` → new cases FAIL. **Step 4: Implement.** **Step 5: Run** → PASS.
- [ ] **Step 6: Manual check (implementer, then Haos)**: `XDG_CONFIG_HOME=$(mktemp -d) ./target/debug/ul desk` → Studio: camera drag/snap/resize/shape, format switch, scene keys, recording with countdown, REC pill on the Board tab, permission banner when started from a terminal without Screen Recording.

---

### Task 13: Projects tab and export dialog

**Files:**
- Modify: `src/unlawful/studio_ui.py`, `tests/test_desk_ui.cjs`, `tests/test_desk_ui.py`

**Interfaces:**
- Consumes: Task 10 API, Task 12 preview renderer (reused with project media).
- Produces: `renderProjects()`, `openProject(path)`, `projectClock(project, t)` → `{segment, local}` mapping global time to a segment file, `exportDefaults(project, setup)` (project `export` > setup `export`), `renderExportDialog(project)`, `pollExport()` (1 s while `queued|running`); "Open project…" button → `/api/studio/open-project`; Move to Trash → `/api/studio/action` `{action: "delete", name}`.

- [ ] **Step 1: Write failing cases**

```js
 async project_clock_maps_segments() {
  const h = harness();
  const p = {segments: [{duration: 10}, {duration: 5}]};
  assert.deepEqual(plain(h.a.projectClock(p, 12.5)), {segment: 1, local: 2.5});
  assert.deepEqual(plain(h.a.projectClock(p, 99)), {segment: 1, local: 5});
 },
 async export_dialog_prefill() {
  const h = harness();
  assert.equal(h.a.exportDefaults({export: {canvas: '9:16', height: 1080}}, {export: {canvas: '16:9', height: 1440, fps: 60}}).canvas, '9:16');
  assert.equal(h.a.exportDefaults({}, {export: {canvas: '16:9', height: 1440, fps: 60}}).height, 1440);
 },
 async export_progress_polls_until_done() { /* fetch answers running 40% then done → dialog text '40%' then 'Saved', polling stops */ },
```
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** spec §9 Projects (cards: thumbnail, duration, exported formats, size, state badge; filter Projects/Exports/Screenshots; project page with synced preview where the screen video is the clock and camera/mic follow with their `starts`; per-project layout edits saved through `/api/studio/project`; Export dialog with every choice of spec §8 and "delete sources after export"). The old library viewer stays for plain files (exports, screenshots, old recordings). **Step 4: Run** → PASS.

---

### Task 14: Docs, version 3.21.0, catalog, full verification

**Files:**
- Modify: `AGENTS.md` (capture and desk bullets: projects, setup file, modules, stop policy, menu bar, permissions, Studio page module), `README.md` (capture section), `Cargo.toml`, `ule/Cargo.toml`, `src/unlawful/__init__.py`, `Cargo.lock`, `catalog/`

- [ ] **Step 1:** Set version 3.21.0 in the three files; `cargo build --workspace` updates `Cargo.lock`.
- [ ] **Step 2:** `python3 -I rust/gen_assets.py --catalog src catalog`.
- [ ] **Step 3:** Update `AGENTS.md` and `README.md` with facts from the code (commands copied from the help text).
- [ ] **Step 4: Full verification**, each must pass:
```bash
cargo test --workspace
cargo clippy --workspace --all-targets
cargo clippy --no-default-features --all-targets
python -m unittest discover -s tests -v
UNLAW_REAL_MEDIA=1 python -m unittest tests.test_capture_export -k real -v
cargo build --release --workspace
```
- [ ] **Step 5: Haos's manual checklist** (spec §12): local install (`cargo install --path . --root ~/.local --force`, `cargo install --path ule --root ~/.local --force`), real screen + camera + mic recording with scene switches and a pause, menu-bar clicks, export of every canvas, move a project folder and reopen it, the TUI. Before the install, register the hashes of the dev-build seeds that will land in `~/.config/unlaw/commands/{capture,desk}` only if their source changes again afterwards.
