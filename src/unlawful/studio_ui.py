"""The Studio tab of the `ul desk` page: its CSS and JS, injected into desk_ui.PAGE.

Device names, project names and texts are user data, so nodes are built with textContent, never innerHTML.
Recording, projects and export all go through `ul capture ... --json` on the server (desk.py `Studio`);
the page only edits the shared setup (storage.root/studio/setup.json) and shows what capture reports.
"""

from __future__ import annotations

STUDIO_CSS = r""".studio { display: flex; flex-direction: column; gap: 10px; padding: 12px 16px 18px; min-height: 100%; }
.sthead { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sthead .seg { display: flex; gap: 2px; background: var(--column); border: 1px solid var(--line); border-radius: 8px; padding: 2px; }
.sthead .seg button { border: none; background: transparent; padding: 3px 11px; border-radius: 6px; color: var(--muted); font-weight: 550; }
.sthead .seg button.on { background: var(--panel); color: var(--text); box-shadow: var(--shadow), 0 0 0 1px var(--line); }
.sthead .seg button:disabled { opacity: .45; }
.sthead .fmt button.on { color: var(--accent-ink); box-shadow: 0 0 0 1px var(--accent); }
.sthead .lbl { color: var(--muted); font-size: 12px; }
.recgrid { display: grid; grid-template-columns: 230px minmax(0, 1fr) 270px; gap: 12px; align-items: start; }
.pane { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 9px 10px 10px; margin-bottom: 10px; box-shadow: var(--shadow); }
.pane h5 { margin: 0 0 7px; font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 650; display: flex; align-items: center; gap: 6px; }
.pane h5 .add { margin-left: auto; border: none; background: transparent; padding: 0 2px; color: var(--accent-ink); text-transform: none; letter-spacing: 0; font-size: 12px; font-weight: 600; }
.pane .prow { display: flex; align-items: center; gap: 7px; margin: 6px 0; font-size: 12.5px; }
.pane .prow > .lbl { color: var(--muted); width: 74px; flex: none; font-size: 12px; }
.pane .prow select, .pane .prow input[type=text], .pane .prow input[type=number] { flex: 1; min-width: 0; padding: 3px 7px; font-size: 12.5px; }
.pane .prow input[type=range] { flex: 1; min-width: 0; }
.pane .prow input[type=color] { width: 26px; height: 22px; padding: 0; border-radius: 5px; }
.pane .prow .val { color: var(--muted); font: 11.5px var(--mono); min-width: 38px; text-align: right; }
.pane .note { color: var(--muted); font-size: 11.5px; margin: 4px 0 0; }
.scenes { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.scn { position: relative; border-radius: 6px; border: 1px solid var(--line); background: var(--sunken); overflow: hidden; padding: 0; aspect-ratio: 16 / 10; text-align: left; }
.scn.on { box-shadow: 0 0 0 2px var(--accent); border-color: var(--accent); }
.scn .mini { position: absolute; border-radius: 2px; background: var(--muted); opacity: .45; }
.scn .mini.camera { background: var(--accent); opacity: .8; }
.scn .mini.image, .scn .mini.text { background: var(--energy); opacity: .7; }
.scn kbd { position: absolute; right: 3px; top: 3px; font-size: 10px; }
.scn span { position: absolute; left: 5px; bottom: 3px; right: 4px; font-size: 10.5px; font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.srcs .src { display: flex; align-items: center; gap: 7px; width: 100%; border: none; background: transparent; padding: 5px 6px; border-radius: 6px; text-align: left; font-size: 12.5px; }
.srcs .src:hover { background: var(--column); }
.srcs .src.on { background: var(--sunken); box-shadow: inset 2px 0 0 var(--accent); }
.srcs .src.off { color: var(--muted); }
.srcs .src .ico { width: 16px; text-align: center; color: var(--muted); }
.srcs .src .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.srcs .src .eye { border: none; background: transparent; padding: 0 3px; color: var(--muted); font-size: 12px; }
.srcs .src .eye.hidden { opacity: .4; }
.stmenu { position: absolute; z-index: 20; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--lift); padding: 4px; display: flex; flex-direction: column; gap: 2px; min-width: 150px; }
.stmenu button { border: none; background: transparent; text-align: left; padding: 5px 9px; border-radius: 5px; font-size: 12.5px; }
.stmenu button:hover { background: var(--column); }
.stmenu label { display: flex; align-items: center; gap: 6px; padding: 4px 9px; font-size: 12px; color: var(--muted); }
.centre { min-width: 0; }
.banner { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; background: color-mix(in srgb, var(--danger) 12%, var(--panel)); border: 1px solid color-mix(in srgb, var(--danger) 45%, var(--line)); color: var(--text); border-radius: var(--r); padding: 8px 10px; margin-bottom: 8px; font-size: 12.5px; }
.banner b { color: var(--danger); }
.stage { position: relative; margin: 0 auto; border-radius: 8px; overflow: hidden; background: var(--sunken); box-shadow: var(--shadow); user-select: none; touch-action: none; }
.stage .bg { position: absolute; inset: -8%; width: 116%; height: 116%; object-fit: cover; filter: blur(18px) brightness(.8); }
.stage .ph { position: absolute; overflow: hidden; cursor: grab; box-sizing: border-box; }
.stage .ph > img, .stage .ph > video { width: 100%; height: 100%; display: block; pointer-events: none; }
.stage .ph.sel { outline: 2px solid var(--accent); outline-offset: -1px; }
.stage .ph .camph { width: 100%; height: 100%; display: grid; place-items: center; background: var(--column); color: var(--muted); font-size: 12px; text-align: center; }
.stage .handle { position: absolute; width: 11px; height: 11px; background: var(--accent); border: 2px solid var(--on-accent); border-radius: 3px; z-index: 4; cursor: nwse-resize; }
.stage .handle.top-right, .stage .handle.bottom-left { cursor: nesw-resize; }
.stage .float { position: absolute; z-index: 5; display: flex; gap: 4px; align-items: center; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 3px 5px; box-shadow: var(--lift); }
.shapes { display: flex; gap: 3px; }
.shapes button, .corners button { width: 24px; height: 24px; padding: 0; display: grid; place-items: center; border-radius: 5px; font-size: 12px; }
.shapes button.on, .corners button.on { border-color: var(--accent); color: var(--accent-ink); }
.shapes button i { display: block; background: var(--muted); }
.shapes button.on i { background: var(--accent); }
.corners { display: flex; gap: 3px; }
.stage .badge { position: absolute; right: 8px; top: 8px; z-index: 6; background: var(--panel); color: var(--danger); font: 700 11px var(--mono); padding: 2px 7px; border-radius: 5px; display: none; box-shadow: var(--shadow); }
.stage .badge.on { display: block; }
.stage .badge.paused { color: var(--muted); }
.stage .count { position: absolute; inset: 0; z-index: 7; display: grid; place-items: center; background: color-mix(in srgb, var(--bg) 55%, transparent); font: 700 96px var(--mono); color: var(--accent-ink); }
.stage .empty { position: absolute; inset: 0; display: grid; place-items: center; color: var(--muted); font-size: 12.5px; text-align: center; padding: 20px; }
.sthint { color: var(--muted); font-size: 11.5px; text-align: center; margin: 5px 0 0; }
.recbar { display: flex; align-items: center; gap: 10px; margin: 10px 0; flex-wrap: wrap; position: relative; }
.recbtn { width: 46px; height: 46px; border-radius: 50%; border: 3px solid var(--text); background: var(--panel); display: grid; place-items: center; padding: 0; flex: none; }
.recbtn i { width: 22px; height: 22px; border-radius: 50%; background: var(--danger); transition: border-radius .15s, width .15s, height .15s; }
.recbtn.on i { width: 18px; height: 18px; border-radius: 4px; }
.recbtn:hover { border-color: var(--danger); }
.recclock { font: 600 21px var(--mono); letter-spacing: .02em; }
.recclock.live { color: var(--danger); }
.recbar .pill { display: inline-flex; gap: 6px; align-items: center; border-radius: 999px; padding: 4px 10px; font-size: 12.5px; }
.recbar .info { margin-left: auto; text-align: right; color: var(--muted); font-size: 11.5px; line-height: 1.45; }
.recstate { color: var(--muted); font-size: 12px; }
.warns { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }
.warns div { display: flex; align-items: center; gap: 8px; border-radius: var(--r-sm); padding: 5px 9px; font-size: 12.5px; background: color-mix(in srgb, var(--warn) 14%, var(--panel)); border: 1px solid color-mix(in srgb, var(--warn) 40%, var(--line)); }
.warns div button { margin-left: auto; padding: 2px 9px; }
.meter { flex: 1; height: 7px; border-radius: 4px; background: var(--sunken); overflow: hidden; min-width: 40px; }
.meter i { display: block; height: 100%; width: 0; background: linear-gradient(90deg, var(--ok) 0 60%, var(--warn) 60% 85%, var(--danger) 85%); background-size: var(--full, 100px) 100%; transition: width .08s linear; }
.tag { font-size: 10px; color: var(--muted); border: 1px solid var(--line); border-radius: 3px; padding: 0 3px; }
.projbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.projbar .levels { grid-template-columns: repeat(3, auto); }
.projbar .levels button { padding: 3px 12px; }
.library { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.item { background: var(--panel); border-radius: 8px; box-shadow: var(--shadow); overflow: hidden; cursor: pointer; border: 1px solid var(--line); text-align: left; padding: 0; display: flex; flex-direction: column; }
.item:hover { border-color: var(--accent); box-shadow: var(--lift); }
.item .pic { aspect-ratio: 16 / 10; background: var(--sunken); display: grid; place-items: center; color: var(--muted); position: relative; }
.item .pic img { width: 100%; height: 100%; object-fit: cover; }
.item .pic .len { position: absolute; right: 6px; bottom: 6px; background: var(--panel); color: var(--text); font: 11px var(--mono); padding: 1px 6px; border-radius: 5px; }
.item .pic .state { position: absolute; left: 6px; top: 6px; background: var(--panel); color: var(--text); font-size: 10.5px; font-weight: 650; padding: 1px 6px; border-radius: 5px; }
.item .pic .state.incomplete { color: var(--danger); }
.item .pic svg { width: 34px; height: 34px; stroke: var(--muted); fill: none; stroke-width: 1.6; }
.item .cap { padding: 7px 9px 8px; font-size: 12px; }
.item .cap b { display: block; font-weight: 550; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item .cap span { color: var(--muted); }
.projpage { display: grid; grid-template-columns: minmax(0, 1fr) 290px; gap: 12px; align-items: start; }
.projpage .player { display: flex; align-items: center; gap: 8px; margin: 8px 0; }
.projpage .player input[type=range] { flex: 1; }
.projpage .scenelist { display: flex; flex-direction: column; gap: 3px; font-size: 12px; }
.projpage .scenelist div { display: flex; gap: 8px; }
.projpage .scenelist .t { font-family: var(--mono); color: var(--muted); width: 48px; }
.progress { height: 6px; border-radius: 3px; background: var(--sunken); overflow: hidden; margin: 6px 0; }
.progress i { display: block; height: 100%; width: 0; background: var(--accent); transition: width .3s; }
.rec-pill { display: none; border: none; background: color-mix(in srgb, var(--danger) 12%, transparent); color: var(--danger); font: 600 12px var(--mono); border-radius: 999px; padding: 4px 10px; }
.rec-pill.on { display: inline-flex; gap: 6px; align-items: center; }
.rec-pill.on::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--danger); animation: blink 1.2s infinite; }
.rec-pill.paused::before { animation: none; background: var(--muted); }
@keyframes blink { 50% { opacity: .25; } }
#viewer { position: fixed; inset: 0; background: rgba(10,8,4,.6); display: none; place-items: center; z-index: 12; }
#viewer.on { display: grid; }
#viewer .sheet { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; box-shadow: var(--lift); width: min(1100px, 94vw); max-height: 94vh; overflow: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
#viewer .media { background: #0c0c0b; border-radius: 12px; display: grid; place-items: center; min-height: 120px; }
#viewer .media video, #viewer .media img { max-width: 100%; max-height: 66vh; display: block; }
#viewer .media audio { width: 90%; margin: 30px 0; }
#viewer .top { display: flex; align-items: center; gap: 10px; background: none; box-shadow: none; padding: 0; }
#viewer .top b { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#viewer .tools { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
#viewer .tools .sep { width: 1px; height: 22px; background: var(--line); margin: 0 4px; }
#viewer .tools .mark { font: 12px var(--mono); color: var(--muted); }
#viewer canvas.filewave { width: 100%; height: 96px; display: block; cursor: pointer; background: #0c0c0b; border-radius: 12px; }
#viewer .export { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px 12px; }
#viewer .export label { display: grid; gap: 3px; font-size: 12px; color: var(--muted); }
#viewer .export label.check { display: flex; align-items: center; gap: 7px; color: var(--text); }
@media (max-width: 1180px) { .recgrid { grid-template-columns: 210px minmax(0, 1fr); } .recgrid > .right { grid-column: 1 / -1; display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; } }
@media (max-width: 860px) { .recgrid, .projpage { grid-template-columns: 1fr; } .recgrid > .right { display: block; } }
"""

STUDIO_JS = r"""// ---- studio: Record (scenes, sources, live preview) and Projects, all through `ul capture` ----
const studio = { info: null, setup: null, devices: null, modes: {}, doctor: null, status: { active: false }, statusAt: 0, shown: 0, starting: 0, saving: false,
  tab: localStorage.getItem("studio-tab") === "projects" ? "projects" : "record", selected: "camera", library: [], projects: [], filter: localStorage.getItem("studio-filter") || "projects",
  camStream: null, camVideo: null, micStream: null, audio: null, analyser: null, sampler: 0, levels: [], screenUrl: "", screenFailed: false, previewTimer: 0,
  drag: null, saveTimer: 0, counting: 0, countTimer: 0, countdownDone: null, menu: null, delay: 0, clipboard: false,
  item: null, trim: { from: null, to: null }, project: null, projectCanvas: "16:9", projectTimer: 0, player: null, projectsLoaded: false, libraryLoaded: false, exportJob: null, exportTimer: 0 };
const media = (path, name) => path + "?t=" + encodeURIComponent(TOKEN) + (name ? "&name=" + encodeURIComponent(name) : "");

// ---- studio geometry: the same numbers as capture_project.py (apply_shape, pin) and capture_export.py (placement_px) ----
const STUDIO_RATIOS = { "16:9": [16, 9], "9:16": [9, 16], "1:1": [1, 1], "4:5": [4, 5] };
const STUDIO_FORMATS = [["16:9", "16:9"], ["9:16", "9:16"], ["1:1", "1:1"], ["4:5", "4:5"], ["source", "As recorded"]];
const STUDIO_SHAPES = { circle: [1, 1, 0.5], square: [1, 1, 0], rounded: [1, 1, 0.18], wide: [16, 9, 0], tall: [9, 16, 0] };
const STUDIO_ANCHORS = [["top-left", "↖"], ["top-right", "↗"], ["bottom-left", "↙"], ["bottom-right", "↘"]];
const SNAP = 0.02, MIN_BOX = 0.04;
const studioClone = (value) => JSON.parse(JSON.stringify(value));
// Python's round(): halves go to the even neighbour, so page and export agree on pixels.
function roundHalfEven(value) {
  const rounded = Math.round(value);
  return Math.abs(value % 1) === 0.5 && rounded % 2 !== 0 ? rounded - 1 : rounded;
}
const evenPx = (value) => Math.max(2, roundHalfEven(value / 2) * 2);

function pinPlacement(item, anchor) {
  const out = studioClone(item);
  out.anchor = anchor || null;
  if (!anchor) return out;
  const [, , width, height] = out.box;
  out.box = [anchor.endsWith("left") ? 0 : 1 - width, anchor.startsWith("top") ? 0 : 1 - height, width, height];
  return out;
}

function applyShape(item, shape, canvas) {
  const out = studioClone(item);
  if (!STUDIO_SHAPES[shape] || !STUDIO_RATIOS[canvas]) return out;
  const [shapeWidth, shapeHeight, radius] = STUDIO_SHAPES[shape];
  const [canvasWidth, canvasHeight] = STUDIO_RATIOS[canvas];
  const [x, y] = out.box;
  let width = out.box[2];
  let height = width * (canvasWidth / canvasHeight) * (shapeHeight / shapeWidth);
  if (height > 1) { width = width / height; height = 1; }
  out.box = [x, y, width, height];
  out.radius = radius;
  if (out.anchor) return pinPlacement(out, out.anchor);
  out.box = [Math.min(Math.max(x, 0), 1 - width), Math.min(Math.max(y, 0), 1 - height), width, height];
  return out;
}

// The shape preset a placement matches (box aspect in pixels and radius), or null.
function shapeOf(item, canvas) {
  if (!item || !STUDIO_RATIOS[canvas]) return null;
  const [canvasWidth, canvasHeight] = STUDIO_RATIOS[canvas];
  const aspect = (item.box[2] * canvasWidth) / (item.box[3] * canvasHeight);
  for (const [name, [w, h, radius]] of Object.entries(STUDIO_SHAPES)) {
    if (Math.abs(aspect - w / h) < 0.02 && Math.abs(item.radius - radius) < 0.005) return name;
  }
  return null;
}

function placementPx(item, width, height) {
  const [x, y, w, h] = item.box;
  return { x: roundHalfEven(x * width), y: roundHalfEven(y * height), w: evenPx(w * width), h: evenPx(h * height) };
}

// After a drag: near a corner the box is pinned there (anchor), near an edge it sits flush on it.
function snapPlacement(item, canvas) {
  const out = studioClone(item);
  let [x, y, width, height] = out.box;
  const near = (a, b) => Math.abs(a - b) <= SNAP;
  const left = near(x, 0), right = near(x + width, 1), top = near(y, 0), bottom = near(y + height, 1);
  if ((left || right) && (top || bottom)) return pinPlacement(out, (top ? "top" : "bottom") + "-" + (left ? "left" : "right"));
  if (left) x = 0; else if (right) x = 1 - width;
  if (top) y = 0; else if (bottom) y = 1 - height;
  out.box = [x, y, width, height];
  out.anchor = null;
  return out;
}

// Dragging inside a `cover` box pans what it shows: the picture follows the pointer.
function moveFocus(item, dx, dy) {
  const out = studioClone(item);
  const clamp = (value) => Math.min(1, Math.max(0, value));
  out.focus = [clamp(out.focus[0] - dx), clamp(out.focus[1] - dy)];
  return out;
}

// Resize from one corner; the opposite corner stays, and a pinned box stays pinned.
function resizePlacement(item, corner, dx, dy, keepAspect) {
  const out = studioClone(item);
  const [x, y, width, height] = out.box;
  const right = corner.endsWith("right"), bottom = corner.startsWith("bottom");
  let newWidth = Math.max(MIN_BOX, width + (right ? dx : -dx));
  let newHeight = keepAspect ? newWidth * (height / width) : Math.max(MIN_BOX, height + (bottom ? dy : -dy));
  if (newWidth > 1) { if (keepAspect) newHeight /= newWidth; newWidth = 1; }
  if (newHeight > 1) { if (keepAspect) newWidth /= newHeight; newHeight = 1; }
  out.box = [right ? x : x + width - newWidth, bottom ? y : y + height - newHeight, newWidth, newHeight];
  return out.anchor ? pinPlacement(out, out.anchor) : out;
}

// R record/stop, P pause, M mark, 1-9 scenes (by key position, so every keyboard layout works).
function studioKey(code, current) {
  if (current.typing) return null;
  if (code === "KeyR") return current.active ? "stop" : "record";
  if (code === "KeyP") return "pause";
  if (code === "KeyM") return "mark";
  const digit = /^Digit([1-9])$/.exec(code);
  if (digit) {
    const scene = (current.scenes || [])[Number(digit[1]) - 1];
    return scene ? "scene:" + scene : null;
  }
  return null;
}

// Status polling: never while the page is hidden; every second while a recording runs on the Studio tab,
// every 5 s otherwise (the REC pill also shows recordings started from the terminal).
function studioPollDelay(visible, recording, onStudio) {
  if (!visible) return null;
  return recording && onStudio ? 1000 : 5000;
}

function countdownSteps(n) { return Array.from({ length: Math.max(0, n) }, (_, index) => n - index); }

// ---- studio data ----
function cameraSource() { return studio.setup ? studio.setup.sources.find((item) => item.kind === "camera") || null : null; }
function screenSource() { return studio.setup ? studio.setup.sources.find((item) => item.kind === "screen") || null : null; }
// The layout being edited: the studio setup on the Record tab, or the open project (saved to that project).
function studioDoc() { return studio.project || studio.setup; }
function sourceById(id) { const doc = studioDoc(); return doc ? doc.sources.find((item) => item.id === id) || null : null; }
function currentCanvas() { return studio.project ? studio.projectCanvas : studio.setup ? studio.setup.canvas : "16:9"; }
function currentScene() {
  if (studio.project) return sceneAt(studio.project, studio.player ? studio.player.t : 0);
  return (studio.status.active && studio.status.scene) || (studio.setup ? studio.setup.scene : "screen-camera");
}
function currentLayout() {
  const doc = studioDoc();
  const layouts = doc && doc.layouts[currentCanvas()];
  return layouts ? layouts[currentScene()] || null : null;
}
function placementOf(id) { const layout = currentLayout(); return layout ? layout.placements[id] || null : null; }
function recordingNow() { return Boolean(studio.starting || (studio.status.active && studio.status.phase === "recording")); }
function sourceName(source) {
  if (source.kind === "screen") return "Screen";
  if (source.kind === "camera") return "Camera";
  if (source.kind === "text") return "Text “" + source.text + "”";
  return source.asset;
}
const SOURCE_ICONS = { screen: "▣", camera: "◉", image: "▤", text: "T" };
const CAMERA_MB = { max: 90, high: 45, light: 22 };
const MIC_MB = { flac: 3, wav: 6, m4a: 2 };
// screencapture has no bitrate option; ~25-70 MB per minute was measured, so the middle is shown.
function megabytesPerMinute(setup) {
  if (!setup) return 0;
  const camera = setup.sources.find((item) => item.kind === "camera");
  return 45 + (camera && camera.enabled ? CAMERA_MB[camera.quality] || 0 : 0) + (setup.audio.mic.enabled ? MIC_MB[setup.audio.mic.format] || 0 : 0);
}
function gigabytes(bytes) { return bytes === null || bytes === undefined ? "" : (bytes / 1e9).toFixed(bytes > 1e11 ? 0 : 1) + " GB"; }

async function loadStudioInfo() {
  const { status, data } = await api("GET", "/api/studio");
  if (status !== 200) return;
  studio.info = data;
  if (data.available) { loadRecordStatus(); loadSetup(); scheduleStudioPoll(); }
}

async function loadSetup() {
  const { status, data } = await api("GET", "/api/studio/setup");
  if (status !== 200) { toast(data.error || "Could not read the studio setup"); return; }
  for (const warning of data.warnings || []) toast(warning);
  delete data.warnings;
  studio.setup = data;
  if (!sourceById(studio.selected)) studio.selected = data.sources[0].id;
}

async function loadDevices() {
  const { status, data } = await api("GET", "/api/studio/devices");
  if (status !== 200) { toast(data.error || "Could not list devices"); return; }
  studio.devices = data;
  if (state.view === "studio") { renderSound(); renderProps(); updateRecordControls(); }
}

async function loadDoctor() {
  const { status, data } = await api("GET", "/api/studio/doctor");
  if (status !== 200) return;
  studio.doctor = data;
  renderBanner();
}

// Edits go to the shared setup file half a second after the last change.
function saveSetupSoon() {
  clearTimeout(studio.saveTimer);
  studio.saveTimer = setTimeout(flushSetup, 500);
}

async function flushSetup() {
  clearTimeout(studio.saveTimer);
  studio.saveTimer = 0;
  if (!studio.setup) return;
  const { status, data } = await api("POST", "/api/studio/setup", studio.setup);
  if (status === 200) return;
  toast(data.error || "Could not save the studio setup");
  await loadSetup();
  if (state.view === "studio") renderStudioBody();
}

function edited(...parts) {
  if (studio.project) saveProjectSoon();
  else saveSetupSoon();
  for (const part of parts) part();
}

// ---- recording state ----
let studioPollTimer = 0;
function scheduleStudioPoll(soon) {
  clearTimeout(studioPollTimer);
  studioPollTimer = 0;
  if (!studio.info || !studio.info.available) return;
  const busy = Boolean(studio.status.active || studio.saving || studio.starting);
  const delay = studioPollDelay(!document.hidden, busy, state.view === "studio");
  if (delay === null) return;
  studioPollTimer = setTimeout(async () => {
    studioPollTimer = 0;
    if (document.hidden) return;
    await loadRecordStatus();
    scheduleStudioPoll();
  }, soon ? 300 : delay);
}

async function loadRecordStatus() {
  const { status, data } = await api("GET", "/api/studio/status");
  if (status !== 200) return;
  const was = studio.status;
  studio.status = data;
  studio.statusAt = Date.now();
  if (studio.saving && data.saving_done) {
    studio.saving = false;
    if (data.saving_done.error) toast(data.saving_done.error);
    else recordingSaved(data.saving_done);
  }
  if (!data.active) for (const item of studio.levels) item.live = false;
  drawRecording();
  if (state.view === "studio") {
    updateRecordControls();
    if (Boolean(was.active) !== Boolean(data.active) || was.scene !== data.scene) { renderScenes(); drawStage(); renderProps(); }
  }
}

function recordingSaved(done) {
  if (done.export_error) toast("Saved, but the export failed: " + done.export_error);
  else toast("Saved " + String(done.saved || done.project || "").split("/").pop());
  studio.projectsLoaded = false;
  if (state.view === "studio" && done.project && done.saved === done.project) openProject(done.project, true);
  else if (state.view === "studio" && studio.tab === "projects") loadProjects();
}

function recordElapsed() {
  const s = studio.status;
  if (studio.starting) return (Date.now() - studio.starting) / 1000;
  if (!s.active) return 0;
  const value = s.elapsed + (s.phase === "recording" ? (Date.now() - studio.statusAt) / 1000 : 0);
  // Polls arrive a little late; never let the clock step backwards while recording.
  if (s.phase === "recording") studio.shown = Math.max(studio.shown, value);
  else studio.shown = value;
  return studio.shown;
}

function drawRecording() {
  const s = studio.status, pill = $("recPill");
  const active = s.active || studio.saving || Boolean(studio.starting);
  pill.className = "rec-pill" + (active ? " on" : "") + (s.paused ? " paused" : "");
  pill.textContent = studio.saving || s.phase === "saving" ? "Saving…" : active ? (s.paused ? "Paused " : "REC ") + clockText(recordElapsed()) : "";
  const clock = $("recClock");
  if (clock) {
    clock.textContent = clockText(recordElapsed());
    clock.classList.toggle("live", recordingNow());
  }
  const badge = $("stageBadge");
  if (badge) {
    badge.className = "badge" + (active && !studio.saving ? " on" : "") + (s.paused ? " paused" : "");
    badge.textContent = s.paused ? "❚❚ PAUSED " + clockText(recordElapsed()) : "● REC " + clockText(recordElapsed());
  }
  drawMeter();
}

// Countdown before a recording: the page waits, then calls record (R again cancels).
function runCountdown(seconds) {
  return new Promise((resolve) => {
    studio.counting = seconds;
    studio.countdownDone = resolve;
    drawCountdown();
    const tick = () => {
      if (!studio.counting) return;
      studio.counting -= 1;
      drawCountdown();
      if (studio.counting <= 0) { studio.countdownDone = null; resolve(true); }
      else studio.countTimer = setTimeout(tick, 1000);
    };
    studio.countTimer = setTimeout(tick, 1000);
  });
}

function cancelCountdown() {
  clearTimeout(studio.countTimer);
  studio.counting = 0;
  const done = studio.countdownDone;
  studio.countdownDone = null;
  drawCountdown();
  if (done) done(false);
}

function drawCountdown() {
  const stage = $("stage");
  if (!stage) return;
  let node = $("countdown");
  if (!studio.counting) { if (node) node.remove(); return; }
  if (!node) { node = h("div", { class: "count", id: "countdown" }); stage.append(node); }
  node.textContent = String(studio.counting);
}

async function toggleRecord() {
  if (studio.counting) { cancelCountdown(); return; }
  if (studio.saving || studio.starting) return;
  if (studio.status.active) {
    studio.saving = true;
    for (const item of studio.levels) item.live = false;
    updateRecordControls();
    const { status, data } = await api("POST", "/api/studio/stop", {});
    if (status !== 200) { studio.saving = false; toast(data.error || "Could not stop"); }
    updateRecordControls();
    scheduleStudioPoll(true);
    return;
  }
  const seconds = studio.setup ? studio.setup.countdown : 0;
  if (seconds > 0 && !(await runCountdown(seconds))) return;
  if (studio.status.active || studio.starting || studio.saving) return;
  // The recording copies the saved setup, so a pending edit is saved first.
  if (studio.saveTimer) await flushSetup();
  const body = studio.setup ? { scene: studio.setup.scene, canvas: studio.setup.canvas } : {};
  // Show the recording at once; the server's clock replaces this one when it answers.
  studio.starting = Date.now();
  studio.shown = 0;
  studio.levels = [];
  updateRecordControls();
  const { status, data } = await api("POST", "/api/studio/record", body);
  studio.starting = 0;
  if (status !== 200) {
    toast(data.error || "Could not start recording");
    if (/permission/i.test(data.error || "")) loadDoctor();
    await loadRecordStatus();
    updateRecordControls();
    return;
  }
  for (const warning of data.warnings || []) toast(warning);
  studio.status = data;
  studio.statusAt = Date.now();
  updateRecordControls();
  drawStage();
  scheduleStudioPoll();
}

async function pauseRecord() {
  if (!studio.status.active || studio.saving) return;
  const { status, data } = await api("POST", studio.status.paused ? "/api/studio/resume" : "/api/studio/pause", {});
  if (status !== 200) { toast(data.error || "Could not pause"); return; }
  studio.status = data;
  studio.statusAt = Date.now();
  updateRecordControls();
}

async function addMark() {
  if (!studio.status.active) return;
  const { status, data } = await api("POST", "/api/studio/mark", {});
  if (status !== 200) { toast(data.error || "Could not add a mark"); return; }
  toast("Mark at " + clockText(data.mark ? data.mark.t : recordElapsed()));
}

async function forceStop() {
  if (!confirm("Kill the stuck recorder? Its track is lost; the other tracks are kept.")) return;
  studio.saving = true;
  updateRecordControls();
  const { status, data } = await api("POST", "/api/studio/stop", { force: true });
  if (status !== 200) { studio.saving = false; toast(data.error || "Could not stop"); }
  scheduleStudioPoll(true);
}

async function selectScene(id) {
  if (!studio.setup || !studio.setup.scenes.some((item) => item.id === id)) return;
  studio.setup.scene = id;
  saveSetupSoon();
  if (studio.status.active) {
    const { status, data } = await api("POST", "/api/studio/scene", { scene: id });
    if (status !== 200) toast(data.error || "Could not switch the scene");
    else { studio.status = data; studio.statusAt = Date.now(); }
  }
  renderScenes();
  drawStage();
  renderProps();
}

function studioKeydown(event) {
  if (state.view !== "studio" || studio.tab !== "record" || !studio.info || !studio.info.available || studio.project) return false;
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test((document.activeElement && document.activeElement.tagName) || "");
  const action = studioKey(event.code, { active: Boolean(studio.status.active), typing, scenes: studio.setup ? studio.setup.scenes.map((item) => item.id) : [] });
  if (!action) return false;
  event.preventDefault();
  if (action === "record" || action === "stop") toggleRecord();
  else if (action === "pause") pauseRecord();
  else if (action === "mark") addMark();
  else selectScene(action.slice(6));
  return true;
}

// ---- browser camera and microphone (preview only; the recording itself is ul capture) ----
function leaveStudio() {
  clearTimeout(studio.previewTimer);
  studio.previewTimer = 0;
  cancelCountdown();
  stopStream("camStream");
  stopStream("micStream");
  closeStudioMenu();
  closeViewer();
  if (studio.projectTimer) flushProject();
  stopProjectPlayer();
  studio.project = null;
}

function stopStream(key) {
  const request = key === "camStream" ? "camRequest" : "micRequest";
  studio[request] = (studio[request] || 0) + 1;
  if (studio[key]) { studio[key].getTracks().forEach((track) => track.stop()); studio[key] = null; }
  if (key === "camStream" && studio.camVideo) studio.camVideo.srcObject = null;
  if (key === "micStream") {
    clearInterval(studio.sampler);
    studio.analyser = null;
    if (studio.audio) { studio.audio.close(); studio.audio = null; }
  }
}

async function toggleCamera() {
  if (studio.camStream) { stopStream("camStream"); drawStage(); return; }
  if (state.view !== "studio") return;
  const request = studio.camRequest = (studio.camRequest || 0) + 1;
  const current = () => request === studio.camRequest && state.view === "studio";
  const wanted = (cameraSource() || {}).device || "default";
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: true });
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    if (wanted !== "default") {
      // Labels are only visible after the first permission; the device is matched by its name.
      const found = (await navigator.mediaDevices.enumerateDevices()).find((item) => item.kind === "videoinput" && item.label === wanted);
      if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
      if (found) { stream.getTracks().forEach((track) => track.stop()); stream = await navigator.mediaDevices.getUserMedia({ video: { deviceId: { exact: found.deviceId } } }); }
    }
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    studio.camStream = stream;
  } catch (error) { if (stream) stream.getTracks().forEach((track) => track.stop()); toast("The browser could not open the camera: " + error.message); }
  drawStage();
}

function ensureCamera() {
  const camera = cameraSource();
  if (camera && camera.enabled && !studio.camStream && localStorage.getItem("studio-campreview") !== "off" && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) toggleCamera();
}

async function toggleMeter() {
  if (studio.micStream) { stopStream("micStream"); renderSound(); return; }
  if (state.view !== "studio") return;
  const request = studio.micRequest = (studio.micRequest || 0) + 1;
  const current = () => request === studio.micRequest && state.view === "studio";
  const wanted = studio.setup ? studio.setup.audio.mic.device : "default";
  try {
    const constraints = { audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } };
    if (wanted && wanted !== "default") {
      // Device labels are only visible after the first permission.
      await navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => stream.getTracks().forEach((track) => track.stop()));
      if (!current()) return;
      const found = (await navigator.mediaDevices.enumerateDevices()).find((item) => item.kind === "audioinput" && item.label.includes(wanted));
      if (!current()) return;
      if (found) constraints.audio.deviceId = { exact: found.deviceId };
    }
    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    studio.micStream = stream;
  } catch (error) { toast("The browser could not open the microphone: " + error.message); return; }
  studio.audio = new AudioContext();
  studio.analyser = studio.audio.createAnalyser();
  studio.analyser.fftSize = 2048;
  studio.audio.createMediaStreamSource(studio.micStream).connect(studio.analyser);
  const samples = new Float32Array(studio.analyser.fftSize);
  studio.sampler = setInterval(() => {
    if (!studio.analyser) return;
    studio.analyser.getFloatTimeDomainData(samples);
    let peak = 0;
    for (const value of samples) peak = Math.max(peak, Math.abs(value));
    studio.levels.push({ v: dbLevel(20 * Math.log10(Math.max(peak, 1e-5))), live: recordingNow() });
    if (studio.levels.length > 600) studio.levels.splice(0, 300);
  }, 50);
  renderSound();
  const stream = studio.micStream;
  const loop = () => { if (studio.micStream !== stream) return; drawMeter(); requestAnimationFrame(loop); };
  loop();
}

const dbLevel = (db) => Math.min(1, Math.max(0, (db + 60) / 60));
function drawMeter() {
  const meter = $("micMeter");
  if (!meter) return;
  const s = studio.status;
  let level = 0;
  if (s.active && typeof s.level_db === "number") level = dbLevel(s.level_db);
  else if (studio.micStream && studio.levels.length) level = studio.levels[studio.levels.length - 1].v;
  meter.firstChild.style.width = Math.round(level * 100) + "%";
}

// ---- screen preview: a snapshot every second (every 3 s while recording, so the recording stays smooth) ----
function startPreview() {
  clearTimeout(studio.previewTimer);
  const screen = screenSource();
  if (!screen || state.view !== "studio" || studio.tab !== "record") return;
  const again = (ms) => { studio.previewTimer = setTimeout(startPreview, ms); };
  if (document.hidden) { again(1000); return; }
  const url = media("/media/preview") + "&display=" + screen.display + "&_=" + Date.now();
  const image = new Image();
  image.onload = () => {
    studio.screenUrl = url;
    if (studio.screenFailed) { studio.screenFailed = false; drawStage(); }
    for (const node of document.querySelectorAll("img.screen")) node.src = url;
    again(studio.status.active ? 3000 : 1000);
  };
  image.onerror = () => {
    if (!studio.screenFailed) { studio.screenFailed = true; loadDoctor(); drawStage(); }
    again(5000);
  };
  image.src = url;
}

// ---- rendering ----
function renderStudio(main) {
  if (!studio.info) { main.textContent = ""; main.append(h("div", { class: "page" }, h("div", { class: "empty", text: "Loading…" }))); loadStudioInfo().then(() => state.view === "studio" && render()); return; }
  if (!studio.info.available) {
    main.textContent = "";
    main.append(h("div", { class: "page" }, h("h3", { text: "Studio" }), h("div", { class: "empty", text: "The capture command is not installed in this ul. Turn on the `capture` feature with: ul features" })));
    return;
  }
  if (main.querySelector(".studio")) return;
  main.textContent = "";
  main.append(h("div", { class: "studio", id: "studioRoot" }));
  renderStudioBody();
  if (!studio.setup) loadSetup().then(() => state.view === "studio" && renderStudioBody());
  if (!studio.devices) loadDevices();
  loadDoctor();
  loadRecordStatus();
  scheduleStudioPoll();
}

function setStudioTab(tab) {
  if (tab === studio.tab && !studio.project) return;
  studio.tab = tab;
  localStorage.setItem("studio-tab", tab);
  if (tab !== "record") { clearTimeout(studio.previewTimer); stopStream("camStream"); stopStream("micStream"); }
  if (studio.projectTimer) flushProject();
  stopProjectPlayer();
  studio.project = null;
  renderStudioBody();
}

function renderStudioBody() {
  const root = $("studioRoot");
  if (!root) return;
  root.textContent = "";
  const tabs = h("div", { class: "seg" },
    h("button", { class: studio.tab === "record" ? "on" : "", text: "Record", onclick: () => setStudioTab("record") }),
    h("button", { class: studio.tab === "projects" ? "on" : "", text: "Projects", onclick: () => setStudioTab("projects") }),
    h("button", { text: "Edit", disabled: true, title: "Editing (timeline, cuts, subtitles) is coming soon" }));
  const head = h("div", { class: "sthead" }, tabs, h("span", { class: "spacer" }));
  if (studio.tab === "record" && studio.setup) {
    head.append(h("span", { class: "lbl", text: "Format" }), h("div", { class: "seg fmt" }, STUDIO_FORMATS.map(([value, label]) =>
      h("button", { class: currentCanvas() === value ? "on" : "", text: label, title: value === "source" ? "The screen as recorded, no composition" : "Layout for " + value, onclick: () => { studio.setup.canvas = value; edited(renderStudioBody); } }))));
  }
  root.append(head);
  if (studio.tab === "projects") { root.append(h("div", { id: "studioProjects" })); renderProjects(); return; }
  if (!studio.setup) { root.append(h("div", { class: "empty", text: "Loading the studio setup…" })); return; }
  root.append(h("div", { class: "recgrid" },
    h("div", { class: "left" }, h("div", { class: "pane", id: "scenesPane" }), h("div", { class: "pane srcs", id: "sourcesPane" })),
    h("div", { class: "centre" },
      h("div", { id: "permBanner" }),
      h("div", { class: "stage", id: "stage" }),
      h("div", { class: "sthint", id: "stageHint" }),
      h("div", { class: "recbar", id: "recBar" }),
      h("div", { class: "warns", id: "warnStrip" }),
      h("div", { class: "pane", id: "soundPane" })),
    h("div", { class: "right" }, h("div", { class: "pane", id: "propsPane" }), h("div", { class: "pane", id: "outputPane" }))));
  renderScenes();
  renderSources();
  renderBanner();
  drawStage();
  renderRecBar();
  renderSound();
  renderProps();
  renderOutput();
  updateRecordControls();
  startPreview();
  ensureCamera();
}

function permissionBanner(doctor) {
  if (!doctor || doctor.screen !== false) return null;
  const app = doctor.app || "the app that runs ul";
  return h("div", { class: "banner" },
    h("b", { text: "No screen recording permission." }),
    h("span", { text: "Give " + app + " Screen Recording permission in System Settings › Privacy & Security, then quit and reopen " + app + ". Camera and microphone still record." }),
    h("button", { text: "Open System Settings", onclick: () => openSettings("screen") }),
    h("button", { class: "ghost", text: "Check again", onclick: loadDoctor }));
}

function renderBanner() {
  const box = $("permBanner");
  if (!box) return;
  box.textContent = "";
  const banner = permissionBanner(studio.doctor);
  if (banner) box.append(banner);
}

async function openSettings(kind) {
  const { status, data } = await api("POST", "/api/studio/open-settings", { kind });
  if (status !== 200) { toast(data.error || "Could not open System Settings"); return; }
  studio.doctor = data;
  renderBanner();
}

function renderScenes() {
  const box = $("scenesPane");
  if (!box || !studio.setup) return;
  box.textContent = "";
  const canvas = currentCanvas() === "source" ? "16:9" : currentCanvas();
  const [rw, rh] = STUDIO_RATIOS[canvas];
  box.append(h("h5", {}, "Scenes", h("button", { class: "add", text: "+ scene", title: "Add a scene (at most 9)", onclick: addScene })));
  const grid = h("div", { class: "scenes" });
  studio.setup.scenes.forEach((scene, index) => {
    const layout = (studio.setup.layouts[canvas] || {})[scene.id];
    const thumb = h("button", { class: "scn" + (scene.id === currentScene() ? " on" : ""), title: scene.name + " (" + (index + 1) + ") · double-click to rename", onclick: () => selectScene(scene.id), ondblclick: () => renameScene(scene.id) });
    thumb.style.aspectRatio = rw + " / " + rh;
    for (const source of studio.setup.sources) {
      const item = layout && layout.placements[source.id];
      if (!item || !item.visible) continue;
      const mini = h("i", { class: "mini " + source.kind });
      Object.assign(mini.style, { left: item.box[0] * 100 + "%", top: item.box[1] * 100 + "%", width: item.box[2] * 100 + "%", height: item.box[3] * 100 + "%" });
      if (item.radius) mini.style.borderRadius = item.radius >= 0.5 ? "50%" : "3px";
      thumb.append(mini);
    }
    thumb.append(h("kbd", { text: String(index + 1) }), h("span", { text: scene.name }));
    grid.append(thumb);
  });
  box.append(grid);
}

function addScene() {
  const setup = studio.setup;
  if (setup.scenes.length >= 9) { toast("A studio has at most 9 scenes (keys 1-9)"); return; }
  let number = setup.scenes.length + 1;
  while (setup.scenes.some((item) => item.id === "scene-" + number)) number += 1;
  const id = "scene-" + number, from = currentScene();
  setup.scenes.push({ id, name: "Scene " + number });
  for (const canvas of Object.keys(setup.layouts)) {
    const source = setup.layouts[canvas][from];
    if (source) setup.layouts[canvas][id] = studioClone(source);
  }
  setup.scene = id;
  edited(renderScenes, drawStage, renderProps);
}

function renameScene(id) {
  const setup = studio.setup, scene = setup.scenes.find((item) => item.id === id);
  if (!scene) return;
  const name = prompt("Scene name (empty to delete the scene)", scene.name);
  if (name === null) return;
  if (!name.trim()) {
    if (setup.scenes.length < 2 || studio.status.active) { toast(studio.status.active ? "Scenes cannot be deleted while recording" : "The last scene stays"); return; }
    if (!confirm("Delete the scene “" + scene.name + "”?")) return;
    setup.scenes = setup.scenes.filter((item) => item.id !== id);
    for (const layouts of Object.values(setup.layouts)) delete layouts[id];
    if (setup.scene === id) setup.scene = setup.scenes[0].id;
  } else scene.name = name.trim().slice(0, 40);
  edited(renderScenes, drawStage);
}

function renderSources() {
  const box = $("sourcesPane");
  if (!box || !studio.setup) return;
  box.textContent = "";
  box.append(h("h5", {}, "Sources", h("button", { class: "add", text: "+ source", onclick: (event) => openSourceMenu(event.currentTarget) })));
  for (const source of studio.setup.sources) {
    const item = placementOf(source.id);
    const visible = Boolean(item && item.visible);
    const eye = h("button", { class: "eye" + (visible ? "" : " hidden"), text: visible ? "👁" : "◌", title: visible ? "Hide in this scene" : "Show in this scene", onclick: (event) => { event.stopPropagation(); toggleVisible(source.id); } });
    const off = (source.kind === "camera" && !source.enabled) || (source.kind !== "screen" && source.kind !== "camera" && !source.enabled);
    box.append(h("div", { class: "src" + (source.id === studio.selected ? " on" : "") + (off ? " off" : ""), role: "button", tabindex: "0", onclick: () => selectSource(source.id) },
      h("span", { class: "ico", text: SOURCE_ICONS[source.kind] }), h("span", { class: "name", text: sourceName(source) + (off ? " (off)" : "") }), eye));
  }
}

function selectSource(id) {
  studio.selected = id;
  renderSources();
  drawStage();
  renderProps();
}

function toggleVisible(id) {
  const layout = currentLayout();
  if (!layout) return;
  if (!layout.placements[id]) layout.placements[id] = defaultPlacement(sourceById(id), currentCanvas());
  else layout.placements[id].visible = !layout.placements[id].visible;
  edited(renderSources, renderScenes, drawStage, renderProps);
}

function defaultPlacement(source, canvas, aspect) {
  const item = { visible: true, box: [0, 0, 1, 1], fit: "cover", focus: [0.5, 0.5], radius: 0, border: { width: 0, color: "#ffc933" }, shadow: false, mirror: false, anchor: null };
  if (source.kind === "screen") { item.fit = "contain"; return item; }
  if (source.kind === "camera") { item.mirror = true; return applyShape({ ...item, box: [0, 0, 0.24, 0.24], anchor: "bottom-left" }, "wide", canvas); }
  const [cw, ch] = STUDIO_RATIOS[canvas] || [16, 9];
  const width = 0.2, height = Math.min(1, (width * cw) / ch / (aspect || 1));
  item.fit = "contain";
  return pinPlacement({ ...item, box: [0, 0, width, height] }, "top-right");
}

function closeStudioMenu() {
  if (studio.menu) { studio.menu.remove(); studio.menu = null; }
}

function openStudioMenu(anchor, items) {
  closeStudioMenu();
  const box = anchor.getBoundingClientRect();
  const menu = h("div", { class: "stmenu" }, items);
  Object.assign(menu.style, { position: "fixed", left: Math.round(box.left) + "px", top: Math.round(box.bottom + 4) + "px" });
  document.body.append(menu);
  studio.menu = menu;
  setTimeout(() => document.addEventListener("pointerdown", function away(event) {
    if (studio.menu === menu && !menu.contains(event.target)) closeStudioMenu();
    document.removeEventListener("pointerdown", away);
  }), 0);
}

function openSourceMenu(anchor) {
  if (studio.setup.sources.length >= 12) { toast("A studio has at most 12 sources"); return; }
  openStudioMenu(anchor, [
    h("button", { text: "Image…", onclick: () => { closeStudioMenu(); pickImage(); } }),
    h("button", { text: "Text", onclick: () => { closeStudioMenu(); addTextSource(); } }),
  ]);
}

function freeSourceId(prefix) {
  let number = 1;
  while (sourceById(prefix + "-" + number)) number += 1;
  return prefix + "-" + number;
}

async function uploadAsset(name, blob) {
  let response;
  try {
    response = await fetch("/api/studio/asset?name=" + encodeURIComponent(name), { method: "POST", headers: { "X-Desk-Token": TOKEN }, body: blob });
  } catch (error) { toast("Could not reach the desk: " + error.message); return null; }
  let data = {};
  try { data = await response.json(); } catch (error) { data = {}; }
  if (response.status !== 200) { toast(data.error || "Upload failed"); return null; }
  return data.asset;
}

function imageSize(url) {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve([image.naturalWidth || 1, image.naturalHeight || 1]);
    image.onerror = () => resolve([1, 1]);
    image.src = url;
  });
}

function addSourceWithPlacement(source, aspect) {
  studio.setup.sources.push(source);
  for (const [canvas, scenes] of Object.entries(studio.setup.layouts)) {
    for (const [scene, layout] of Object.entries(scenes)) {
      const item = defaultPlacement(source, canvas, aspect);
      item.visible = canvas === currentCanvas() && scene === currentScene();
      layout.placements[source.id] = item;
    }
  }
  studio.selected = source.id;
  edited(renderSources, renderScenes, drawStage, renderProps);
}

function pickImage() {
  const input = h("input", { type: "file", accept: "image/png,image/jpeg" });
  input.addEventListener("change", async () => {
    const file = input.files && input.files[0];
    if (!file) return;
    if (file.size > 50 * 1024 * 1024) { toast("An image can be at most 50 MB"); return; }
    const asset = await uploadAsset(file.name, file);
    if (!asset) return;
    const local = URL.createObjectURL(file);
    const [width, height] = await imageSize(local);
    URL.revokeObjectURL(local);
    addSourceWithPlacement({ id: freeSourceId("img"), kind: "image", enabled: true, asset }, width / height);
  });
  input.click();
}

const TEXT_FONTS = [["-apple-system, Helvetica, sans-serif", "System"], ["Georgia, serif", "Georgia"], ["Menlo, monospace", "Menlo"], ["'Avenir Next', sans-serif", "Avenir Next"], ["'Helvetica Neue', sans-serif", "Helvetica Neue"]];

// Text sources are pictures: the page draws the text into a PNG and uploads it (ffmpeg here has no drawtext).
async function renderTextAsset(source) {
  const scale = 2, padding = Math.round(source.size * 0.35);
  const measure = document.createElement("canvas").getContext("2d");
  const font = "600 " + source.size * scale + "px " + source.font;
  measure.font = font;
  const lines = source.text.split("\n");
  const width = Math.ceil(Math.max(...lines.map((line) => measure.measureText(line).width)) + padding * 2 * scale);
  const lineHeight = Math.round(source.size * 1.25 * scale);
  const height = lineHeight * lines.length + padding * 2 * scale;
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(2, width);
  canvas.height = Math.max(2, height);
  const context = canvas.getContext("2d");
  if (source.background) {
    context.fillStyle = source.background;
    context.beginPath();
    context.roundRect(0, 0, canvas.width, canvas.height, Math.round(padding * scale * 0.8));
    context.fill();
  }
  context.font = font;
  context.fillStyle = source.color;
  context.textBaseline = "middle";
  lines.forEach((line, index) => context.fillText(line, padding * scale, padding * scale + lineHeight * (index + 0.5)));
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) { toast("Could not draw the text"); return null; }
  const asset = await uploadAsset("text " + source.id + ".png", blob);
  return asset ? { asset, aspect: canvas.width / canvas.height } : null;
}

async function addTextSource() {
  const source = { id: freeSourceId("text"), kind: "text", enabled: true, asset: "", text: "Subscribe", font: TEXT_FONTS[0][0], size: 64, color: "#ffffff", background: "#000000" };
  const drawn = await renderTextAsset(source);
  if (!drawn) return;
  source.asset = drawn.asset;
  addSourceWithPlacement(source, drawn.aspect);
}

function removeSource(id) {
  const source = sourceById(id);
  if (!source || source.kind === "screen" || source.kind === "camera") return;
  studio.setup.sources = studio.setup.sources.filter((item) => item.id !== id);
  for (const scenes of Object.values(studio.setup.layouts)) for (const layout of Object.values(scenes)) delete layout.placements[id];
  studio.selected = studio.setup.sources[0].id;
  edited(renderSources, renderScenes, drawStage, renderProps);
}

function stageRatio() {
  const canvas = currentCanvas();
  if (STUDIO_RATIOS[canvas]) return STUDIO_RATIOS[canvas][0] / STUDIO_RATIOS[canvas][1];
  if (studio.project) {
    const info = ((studio.project.segments[0] || {}).info || {}).screen;
    return info && info.width && info.height ? info.width / info.height : 16 / 10;
  }
  const display = displayInfo();
  const pixels = display && /(\d+)\s*x\s*(\d+)/.exec(display.pixels || "");
  return pixels ? Number(pixels[1]) / Number(pixels[2]) : 16 / 10;
}

function displayInfo() {
  const screen = screenSource();
  return studio.devices && screen ? studio.devices.displays.find((item) => item.number === screen.display) || null : null;
}

// The preview draws every visible source with the box, fit, focus, radius, border, shadow and mirror the export uses.
function drawStage() {
  const stage = $("stage");
  if (!stage || !studio.setup) return;
  const ratio = stageRatio();
  stage.style.aspectRatio = String(ratio);
  stage.style.width = "min(100%, calc(58vh * " + ratio.toFixed(4) + "))";
  stage.textContent = "";
  const canvas = currentCanvas();
  const layout = currentLayout();
  const width = stage.clientWidth || 640, height = width / ratio;
  const scale = Math.min(width, height) / 1080;
  const items = [];
  if (canvas === "source") {
    const screen = studioDoc().sources.find((source) => source.kind === "screen");
    if (screen) items.push([screen, { visible: true, box: [0, 0, 1, 1], fit: "contain", focus: [0.5, 0.5], radius: 0, border: { width: 0, color: "#000000" }, shadow: false, mirror: false, anchor: null }]);
    stage.style.background = "#000000";
  } else if (studio.project) {
    const [background, placed] = projectPlacements(studio.project, currentScene(), canvas);
    stage.style.background = background.kind === "color" ? background.color : "#000000";
    items.push(...placed);
  } else if (layout) {
    const background = layout.background;
    stage.style.background = background.kind === "color" ? background.color : "#000000";
    if (background.kind === "blur" && studio.screenUrl) stage.append(h("img", { class: "bg screen", src: studio.screenUrl, alt: "" }));
    for (const source of studio.setup.sources) {
      const item = layout.placements[source.id];
      if (item && item.visible) items.push([source, item]);
    }
  }
  if (!items.length) stage.append(h("div", { class: "empty", text: "Nothing is visible in this scene. Show a source with its eye on the left." }));
  for (const [source, item] of items) stage.append(stageNode(source, item, width, height, scale, canvas !== "source"));
  stage.append(h("span", { class: "badge", id: "stageBadge" }));
  const selected = items.find(([source]) => source.id === studio.selected);
  if (selected && selected[0].kind === "camera" && canvas !== "source") stage.append(cameraToolbar(selected[1]));
  const hint = $("stageHint");
  if (hint) hint.textContent = canvas === "source" ? "As recorded: the screen exactly as captured, no layout." : "Drag to move (corners and edges snap) · drag the yellow corner to resize · ⌥-drag inside to pan · click the camera for shapes";
  if (studio.project) { resumePlayer(); return; }
  drawCountdown();
  drawRecording();
}

function stageNode(source, item, width, height, scale, editable) {
  const px = placementPx(item, width, height);
  const node = h("div", { class: "ph" + (editable && source.id === studio.selected ? " sel" : "") });
  Object.assign(node.style, { left: item.box[0] * 100 + "%", top: item.box[1] * 100 + "%", width: item.box[2] * 100 + "%", height: item.box[3] * 100 + "%" });
  node.style.borderRadius = Math.round(item.radius * Math.min(px.w, px.h)) + "px";
  if (item.border.width) node.style.border = Math.max(1, Math.round(item.border.width * scale)) + "px solid " + item.border.color;
  if (item.shadow) node.style.boxShadow = "0 " + Math.round(8 * scale) + "px " + Math.round(28 * scale) + "px rgba(0,0,0,.55)";
  const fitStyle = (child) => {
    child.style.objectFit = item.fit;
    child.style.objectPosition = item.focus[0] * 100 + "% " + item.focus[1] * 100 + "%";
    // The camera's <video> is reused across redraws, so the transform is always set (or cleared).
    child.style.transform = item.mirror ? "scaleX(-1)" : "";
    return child;
  };
  const player = studio.project && studio.player;
  if (player && (source.kind === "screen" || source.kind === "camera")) {
    node.append(fitStyle(player[source.kind]));
  } else if (player) {
    node.append(fitStyle(h("img", { src: projectMedia(studio.project.path, "assets/" + source.asset), alt: "" })));
  } else if (source.kind === "screen") {
    if (studio.screenUrl && !studio.screenFailed) node.append(fitStyle(h("img", { class: "screen", src: studio.screenUrl, alt: "" })));
    else node.append(h("div", { class: "camph", text: studio.screenFailed ? "No screen preview (see above)" : "Screen " + source.display }));
  } else if (source.kind === "camera") {
    if (studio.camStream) {
      if (!studio.camVideo) { studio.camVideo = h("video", { autoplay: true, playsinline: true }); studio.camVideo.muted = true; }
      if (studio.camVideo.srcObject !== studio.camStream) studio.camVideo.srcObject = studio.camStream;
      node.append(fitStyle(studio.camVideo));
      const playing = studio.camVideo.play && studio.camVideo.play();
      if (playing && playing.catch) playing.catch(() => {});
    } else node.append(h("div", { class: "camph", text: source.enabled ? "Camera" : "Camera (off)" }));
  } else {
    node.append(fitStyle(h("img", { src: media("/media/asset", source.asset), alt: "" })));
  }
  if (!editable) return node;
  node.addEventListener("pointerdown", (event) => startStageDrag(event, source.id, event.altKey ? "focus" : "move"));
  if (source.id === studio.selected) {
    const corner = item.anchor ? { "top-left": "bottom-right", "top-right": "bottom-left", "bottom-left": "top-right", "bottom-right": "top-left" }[item.anchor] : "bottom-right";
    const handle = h("i", { class: "handle " + corner });
    Object.assign(handle.style, { [corner.endsWith("right") ? "right" : "left"]: "-1px", [corner.startsWith("bottom") ? "bottom" : "top"]: "-1px" });
    handle.addEventListener("pointerdown", (event) => { event.stopPropagation(); startStageDrag(event, source.id, "resize:" + corner); });
    node.append(handle);
  }
  return node;
}

function startStageDrag(event, id, mode) {
  if (event.button !== 0) return;
  event.preventDefault();
  if (studio.selected !== id) { studio.selected = id; renderSources(); renderProps(); }
  const stage = $("stage"), layout = currentLayout();
  if (!stage || !layout || !layout.placements[id]) return;
  const start = studioClone(layout.placements[id]);
  const rect = stage.getBoundingClientRect();
  const node = event.currentTarget.classList.contains("handle") ? event.currentTarget.parentNode : event.currentTarget;
  const source = sourceById(id);
  const move = (e) => {
    const dx = (e.clientX - event.clientX) / rect.width, dy = (e.clientY - event.clientY) / rect.height;
    let next;
    if (mode === "move") next = { ...studioClone(start), box: [start.box[0] + dx, start.box[1] + dy, start.box[2], start.box[3]], anchor: null };
    else if (mode === "focus") next = moveFocus(start, dx / start.box[2], dy / start.box[3]);
    else next = resizePlacement(start, mode.slice(7), dx, dy, source.kind !== "screen");
    layout.placements[id] = next;
    Object.assign(node.style, { left: next.box[0] * 100 + "%", top: next.box[1] * 100 + "%", width: next.box[2] * 100 + "%", height: next.box[3] * 100 + "%" });
    const child = node.querySelector("img, video");
    if (child && mode === "focus") child.style.objectPosition = next.focus[0] * 100 + "% " + next.focus[1] * 100 + "%";
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    if (mode === "move") layout.placements[id] = snapPlacement(layout.placements[id], currentCanvas());
    const changed = JSON.stringify(start) !== JSON.stringify(layout.placements[id]);
    if (changed) edited(drawStage, renderScenes, renderProps);
    else drawStage();
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
}

function shapeButtons(item, onpick) {
  const current = shapeOf(item, currentCanvas());
  const sizes = { circle: [12, 12, "50%"], square: [12, 12, "0"], rounded: [12, 12, "4px"], wide: [16, 9, "0"], tall: [9, 16, "0"] };
  return h("div", { class: "shapes" }, Object.keys(STUDIO_SHAPES).map((shape) => {
    const mark = h("i");
    Object.assign(mark.style, { width: sizes[shape][0] + "px", height: sizes[shape][1] + "px", borderRadius: sizes[shape][2] });
    return h("button", { class: current === shape ? "on" : "", title: shape[0].toUpperCase() + shape.slice(1), onclick: () => onpick(shape) }, mark);
  }));
}

function cornerButtons(item, onpick) {
  return h("div", { class: "corners" }, STUDIO_ANCHORS.map(([anchor, arrow]) =>
    h("button", { class: item.anchor === anchor ? "on" : "", text: arrow, title: "Pin to the " + anchor.replace("-", " ") + " corner", onclick: () => onpick(anchor) })));
}

function changePlacement(id, change) {
  const layout = currentLayout();
  if (!layout || !layout.placements[id]) return;
  layout.placements[id] = change(layout.placements[id]);
  edited(drawStage, renderScenes, renderProps);
}

function cameraToolbar(item) {
  const id = studioDoc().sources.find((source) => source.kind === "camera").id;
  const bar = h("div", { class: "float" },
    shapeButtons(item, (shape) => changePlacement(id, (p) => applyShape(p, shape, currentCanvas()))),
    cornerButtons(item, (anchor) => changePlacement(id, (p) => pinPlacement(p, anchor))));
  bar.addEventListener("pointerdown", (event) => event.stopPropagation());
  const right = item.box[0] + item.box[2];
  if (right < 0.62) Object.assign(bar.style, { left: "calc(" + right * 100 + "% + 6px)", bottom: "8px" });
  else Object.assign(bar.style, { right: "calc(" + (1 - item.box[0]) * 100 + "% + 6px)", bottom: "8px" });
  return bar;
}

function renderRecBar() {
  const box = $("recBar");
  if (!box) return;
  box.textContent = "";
  box.append(
    h("button", { class: "recbtn", id: "recButton", title: "Start / stop recording (R)", onclick: toggleRecord }, h("i")),
    h("span", { class: "recclock", id: "recClock", text: "00:00" }),
    h("button", { class: "pill", id: "recPause", title: "Pause / resume (P)", onclick: pauseRecord }, "❚❚ Pause ", h("kbd", { text: "P" })),
    h("button", { class: "pill", id: "recMark", title: "Add a mark at this moment (M)", onclick: addMark }, "⚑ Mark ", h("kbd", { text: "M" })),
    h("button", { class: "pill", title: "Take a screenshot", onclick: (event) => openShotMenu(event.currentTarget) }, "Screenshot ▾"),
    h("span", { class: "recstate", id: "recState" }),
    h("span", { class: "info", id: "recInfo" }));
}

function openShotMenu(anchor) {
  const delay = h("select", {}, [["0", "No delay"], ["3", "3 s delay"], ["5", "5 s delay"], ["10", "10 s delay"]].map(([value, label]) => h("option", { value, text: label, selected: String(studio.delay) === value })));
  delay.addEventListener("change", () => { studio.delay = Number(delay.value); });
  const clip = h("input", { type: "checkbox" });
  clip.checked = studio.clipboard;
  clip.addEventListener("change", () => { studio.clipboard = clip.checked; });
  openStudioMenu(anchor, [
    ...["screen", "area", "window"].map((kind) => h("button", { text: kind[0].toUpperCase() + kind.slice(1), onclick: () => { closeStudioMenu(); takeShot(kind); } })),
    h("label", {}, delay), h("label", {}, clip, "Copy to the clipboard"),
  ]);
}

function updateRecordControls() {
  const s = studio.status;
  const button = $("recButton");
  if (!button) return;
  const active = Boolean(s.active || studio.starting);
  button.classList.toggle("on", active);
  const pause = $("recPause");
  pause.disabled = !s.active || studio.saving || s.phase === "saving" || Boolean(studio.starting);
  pause.firstChild.textContent = s.paused ? "▶ Resume " : "❚❚ Pause ";
  $("recMark").disabled = !s.active || Boolean(studio.starting);
  $("recState").textContent = studio.counting ? "Starting in " + studio.counting + "…" : studio.starting ? "Starting…" : studio.saving || s.phase === "saving" ? "Saving…" : s.phase === "interrupted" ? "A recorder stopped; press stop to save the rest" : s.phase === "unsaved" ? "Not saved; press stop to try again" : s.phase === "stuck" ? "A recorder hangs" : s.active ? (s.paused ? "Paused" : "Recording") : "Ready";
  const display = displayInfo();
  const free = s.free_bytes;
  $("recInfo").textContent = "";
  $("recInfo").append(
    h("div", { text: (display ? display.pixels.replace(/\s*x\s*/, "×") + " · " : "") + "60 fps" }),
    h("div", { text: (free ? "free " + gigabytes(free) + " · " : "") + "≈ " + megabytesPerMinute(studio.setup) + " MB/min" }));
  renderWarnings();
  drawRecording();
}

function renderWarnings() {
  const box = $("warnStrip");
  if (!box) return;
  box.textContent = "";
  const s = studio.status;
  for (const warning of s.warnings || []) box.append(h("div", { text: "⚠ " + warning }));
  if ((s.stuck && s.stuck.length) || s.phase === "stuck") {
    box.append(h("div", {}, "⚠ " + ((s.stuck || []).join(", ") || "A recorder") + " does not stop. Stop again to retry, or kill it (its track is lost).",
      h("button", { text: "Force stop", onclick: forceStop })));
  }
}

function prow(label, ...controls) { return h("div", { class: "prow" }, h("span", { class: "lbl", text: label }), ...controls); }
function studioSelect(options, value, onchange) {
  const node = h("select", {}, options.map(([v, label]) => h("option", { value: v, text: label, selected: v === value })));
  node.addEventListener("change", () => onchange(node.value));
  return node;
}
function studioCheck(value, onchange, label) {
  const input = h("input", { type: "checkbox" });
  input.checked = Boolean(value);
  input.addEventListener("change", () => onchange(input.checked));
  return label ? h("label", { class: "check" }, input, " " + label) : input;
}
function studioRange(min, max, step, value, oninput, shown) {
  const input = h("input", { type: "range", min, max, step, value });
  const val = h("span", { class: "val", text: shown(value) });
  input.addEventListener("input", () => { val.textContent = shown(Number(input.value)); oninput(Number(input.value), false); });
  input.addEventListener("change", () => oninput(Number(input.value), true));
  return [input, val];
}

function renderSound() {
  const box = $("soundPane");
  if (!box || !studio.setup) return;
  box.textContent = "";
  const audio = studio.setup.audio, devices = studio.devices;
  const mics = [["default", "Default microphone"], ...(devices ? devices.microphones.map((item) => [item.name, item.name + (item.virtual ? " (virtual)" : "")]) : []), ["", "No microphone"]];
  if (audio.mic.enabled && !mics.some(([value]) => value === audio.mic.device)) mics.splice(1, 0, [audio.mic.device, audio.mic.device]);
  box.append(h("h5", {}, "Sound"));
  box.append(prow("Microphone", studioSelect(mics, audio.mic.enabled ? audio.mic.device : "", (value) => {
    audio.mic.enabled = value !== "";
    if (value) audio.mic.device = value;
    const chosen = devices && devices.microphones.find((item) => item.name === value);
    if (chosen && chosen.virtual) toast(value + " is virtual: it carries app audio, not your voice");
    if (studio.micStream) { stopStream("micStream"); toggleMeter(); }
    edited(renderSound, updateRecordControls);
  }), h("div", { class: "meter", id: "micMeter" }, h("i")),
    studio.status.active ? null : h("button", { class: "ghost", text: studio.micStream ? "Stop test" : "Test", title: "Show the level in the browser (the recording uses ul capture)", onclick: toggleMeter })));
  box.append(prow("Mic volume", ...studioRange(0, 200, 5, Math.round(audio.mic.volume * 100), (value, done) => { audio.mic.volume = value / 100; if (done) saveSetupSoon(); }, (v) => v + "%"),
    studioCheck(audio.mic.muted, (value) => { audio.mic.muted = value; saveSetupSoon(); }, "mute")));
  box.append(prow("Mac sound", studioCheck(audio.system.enabled, (value) => { audio.system.enabled = value; saveSetupSoon(); }, "record the sound of the Mac")));
  box.append(prow("Mac volume", ...studioRange(0, 200, 5, Math.round(audio.system.volume * 100), (value, done) => { audio.system.volume = value / 100; if (done) saveSetupSoon(); }, (v) => v + "%"),
    studioCheck(audio.system.muted, (value) => { audio.system.muted = value; saveSetupSoon(); }, "mute")));
  box.append(h("p", { class: "note", text: "Volumes and mute apply when a project is exported." }));
  drawMeter();
}

function placementControls(source, item) {
  const id = source.id, canvas = currentCanvas();
  const nodes = [prow("Visible", studioCheck(item.visible, (value) => changePlacement(id, (p) => ({ ...p, visible: value })), "in this scene"))];
  nodes.push(prow("Fit", studioSelect([["cover", "Fill (crop)"], ["contain", "Whole picture"]], item.fit, (value) => changePlacement(id, (p) => ({ ...p, fit: value })))));
  if (source.kind !== "screen") nodes.push(prow("Shape", shapeButtons(item, (shape) => changePlacement(id, (p) => applyShape(p, shape, canvas)))));
  nodes.push(prow("Size", ...studioRange(4, 100, 1, Math.round(item.box[2] * 100), (value, done) => {
    if (!done) return;
    changePlacement(id, (p) => {
      let width = value / 100, height = p.box[3] * (width / p.box[2]);
      if (height > 1) { width /= height; height = 1; }
      const next = { ...studioClone(p), box: [Math.min(p.box[0], 1 - width), Math.min(p.box[1], 1 - height), width, height] };
      return next.anchor ? pinPlacement(next, next.anchor) : next;
    });
  }, (v) => v + "%")));
  nodes.push(prow("Corner", cornerButtons(item, (anchor) => changePlacement(id, (p) => pinPlacement(p, anchor))),
    item.anchor ? h("button", { class: "ghost", text: "free", title: "Unpin", onclick: () => changePlacement(id, (p) => pinPlacement(p, null)) }) : null));
  const color = h("input", { type: "color", value: item.border.color });
  color.addEventListener("change", () => changePlacement(id, (p) => ({ ...p, border: { ...p.border, color: color.value } })));
  nodes.push(prow("Border", color, ...studioRange(0, 40, 1, item.border.width, (value, done) => { if (done) changePlacement(id, (p) => ({ ...p, border: { ...p.border, width: value } })); }, (v) => v + " px")));
  nodes.push(prow("Radius", ...studioRange(0, 50, 1, Math.round(item.radius * 100), (value, done) => { if (done) changePlacement(id, (p) => ({ ...p, radius: value / 100 })); }, (v) => v + "%")));
  nodes.push(prow("Effects", studioCheck(item.shadow, (value) => changePlacement(id, (p) => ({ ...p, shadow: value })), "shadow"),
    studioCheck(item.mirror, (value) => changePlacement(id, (p) => ({ ...p, mirror: value })), "mirror")));
  return nodes;
}

function renderProps() {
  if (studio.project) { renderProjectProps(); return; }
  const box = $("propsPane");
  if (!box || !studio.setup) return;
  box.textContent = "";
  const source = sourceById(studio.selected) || studio.setup.sources[0];
  const devices = studio.devices;
  box.append(h("h5", { text: sourceName(source) }));
  const recording = Boolean(studio.status.active);
  if (source.kind === "camera") {
    box.append(prow("Record", studioCheck(source.enabled, (value) => { source.enabled = value; if (value) ensureCamera(); else stopStream("camStream"); edited(renderSources, drawStage, renderProps, updateRecordControls); }, "the camera")));
    const cams = [["default", "Default camera"], ...(devices ? devices.cameras.map((name) => [name, name]) : [])];
    if (!cams.some(([value]) => value === source.device)) cams.push([source.device, source.device]);
    const device = studioSelect(cams, source.device, (value) => { source.device = value; source.mode = "auto"; if (studio.camStream) { stopStream("camStream"); toggleCamera(); } edited(renderProps); });
    device.disabled = recording;
    box.append(prow("Device", device));
    const name = source.device === "default" ? (devices && devices.cameras[0]) || "" : source.device;
    const modes = [["auto", "Best (auto)"], ...(studio.modes[name] || []).map((mode) => [mode.width + "x" + mode.height + "@" + mode.max_fps, mode.width + "×" + mode.height + " · " + Math.round(Number(mode.max_fps)) + " fps"])];
    if (!modes.some(([value]) => value === source.mode)) modes.push([source.mode, source.mode]);
    const mode = studioSelect(modes, source.mode, (value) => { source.mode = value; edited(); });
    mode.disabled = recording;
    box.append(prow("Mode", mode, h("button", { class: "ghost", text: "↻", title: "Read the camera's modes (the camera light turns on for a moment)", disabled: recording || !name, onclick: () => loadCameraModes(name) })));
    box.append(prow("Preview", studioCheck(localStorage.getItem("studio-campreview") !== "off", (value) => { localStorage.setItem("studio-campreview", value ? "on" : "off"); if (value) ensureCamera(); else { stopStream("camStream"); drawStage(); } }, "live camera in this page")));
  } else if (source.kind === "screen") {
    const displays = devices ? devices.displays.map((item) => [String(item.number), item.number + " · " + item.name + " " + item.pixels.replace(/\s*x\s*/, "×")]) : [[String(source.display), String(source.display)]];
    const display = studioSelect(displays, String(source.display), (value) => { source.display = Number(value); studio.screenUrl = ""; edited(drawStage, updateRecordControls, startPreview); });
    display.disabled = recording;
    box.append(prow("Display", display));
    const area = h("input", { type: "text", value: source.area || "", placeholder: "Whole display, or X,Y,W,H in points" });
    area.disabled = recording;
    area.addEventListener("change", () => {
      const value = area.value.replace(/\s+/g, "");
      if (value && !/^\d{1,5},\d{1,5},[1-9]\d{0,4},[1-9]\d{0,4}$/.test(value)) { toast("Area is X,Y,WIDTH,HEIGHT in points, e.g. 0,0,1280,720"); area.value = source.area || ""; return; }
      source.area = value || null;
      edited();
    });
    box.append(prow("Area", area));
    box.append(prow("Show", studioCheck(source.clicks, (value) => { source.clicks = value; edited(); }, "clicks")));
  } else if (source.kind === "text") {
    const text = h("input", { type: "text", value: source.text, maxlength: "500" });
    const font = studioSelect(TEXT_FONTS.some(([value]) => value === source.font) ? TEXT_FONTS : [...TEXT_FONTS, [source.font, source.font]], source.font, () => {});
    const size = h("input", { type: "number", min: "8", max: "400", value: String(source.size) });
    const color = h("input", { type: "color", value: source.color });
    const back = h("input", { type: "color", value: source.background || "#000000" });
    const backOn = studioCheck(Boolean(source.background), () => {});
    box.append(prow("Text", text), prow("Font", font), prow("Size", size), prow("Colours", color, backOn, back));
    box.append(prow("", h("button", { text: "Apply", onclick: async () => {
      const value = text.value.trim(), points = Number(size.value);
      if (!value) { toast("The text is empty"); return; }
      if (!Number.isInteger(points) || points < 8 || points > 400) { toast("Size is 8-400"); return; }
      const next = { ...source, text: value.slice(0, 500), font: font.value, size: points, color: color.value, background: backOn.checked ? back.value : null };
      const drawn = await renderTextAsset(next);
      if (!drawn) return;
      Object.assign(source, next, { asset: drawn.asset });
      edited(renderSources, drawStage, renderProps);
    } })));
  } else {
    box.append(prow("File", h("span", { text: source.asset })));
  }
  if (source.kind === "image" || source.kind === "text") {
    box.append(prow("Use", studioCheck(source.enabled, (value) => { source.enabled = value; edited(renderSources, drawStage); }, "in recordings"), h("button", { class: "ghost", text: "Remove", onclick: () => removeSource(source.id) })));
  }
  const item = placementOf(source.id);
  if (currentCanvas() === "source") box.append(h("p", { class: "note", text: "“As recorded” has no layout; pick a format to place sources." }));
  else if (item) box.append(...placementControls(source, item));
  else box.append(h("p", { class: "note", text: "Not in this scene. Use the eye on the left to show it." }));
}

async function loadCameraModes(name) {
  toast("Reading the modes of " + name + "…");
  const { status, data } = await api("GET", "/api/studio/camera-modes?device=" + encodeURIComponent(name));
  if (status !== 200) { toast(data.error || "Could not read the camera modes"); return; }
  Object.assign(studio.modes, data.modes || {});
  renderProps();
}

function renderOutput() {
  const box = $("outputPane");
  if (!box || !studio.setup) return;
  box.textContent = "";
  const camera = cameraSource(), mic = studio.setup.audio.mic;
  box.append(h("h5", { text: "Recording files" }));
  if (camera) box.append(prow("Camera", studioSelect([["max", "Max · 1080p · ~90 MB/min"], ["high", "High · 1080p · ~45 MB/min"], ["light", "Light · 720p · ~22 MB/min"]], camera.quality, (value) => { camera.quality = value; edited(renderOutput, updateRecordControls); })));
  box.append(prow("Microphone", studioSelect([["flac", "FLAC lossless · ~3 MB/min"], ["wav", "WAV lossless · ~6 MB/min"], ["m4a", "M4A (AAC) · ~2 MB/min"]], mic.format, (value) => { mic.format = value; edited(renderOutput, updateRecordControls); })));
  box.append(prow("Countdown", studioSelect([["0", "None"], ["3", "3 seconds"], ["5", "5 seconds"], ["10", "10 seconds"]], String(studio.setup.countdown), (value) => { studio.setup.countdown = Number(value); edited(); })));
  box.append(h("p", { class: "note", text: "This setup ≈ " + megabytesPerMinute(studio.setup) + " MB per minute (the screen alone is ~25-70 MB/min, depending on what moves). Export chooses the format, size and fps." }));
}

const ICONS = { audio: "M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zm12-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0z" };
function sizeText(bytes) { return bytes > 1e9 ? (bytes / 1e9).toFixed(1) + " GB" : bytes > 1e6 ? (bytes / 1e6).toFixed(1) + " MB" : Math.max(1, Math.round(bytes / 1e3)) + " KB"; }

async function takeShot(kind) {
  const screen = screenSource();
  const body = { kind, display: screen ? screen.display : 1, delay: studio.delay, clipboard: studio.clipboard };
  if (kind !== "screen") toast("Select on the Mac: drag an area or click a window (Esc cancels)");
  else if (studio.delay) toast("Screenshot in " + studio.delay + " s");
  const { status, data } = await api("POST", "/api/studio/shot", body);
  if (status !== 200) { toast(data.error || "Screenshot failed"); return; }
  if (data.clipboard) { toast("Copied to the clipboard"); return; }
  toast("Saved " + data.saved.split("/").pop());
  studio.libraryLoaded = false;
}

// ---- projects tab ----
const projectMedia = (path, file) => "/media/project?t=" + encodeURIComponent(TOKEN) + "&path=" + encodeURIComponent(path) + "&file=" + encodeURIComponent(file);
const PROJECT_TRACKS = ["screen", "camera", "mic"];

// Global project time -> the segment file that plays it and the time inside that segment.
function projectClock(project, t) {
  const segments = project.segments || [];
  if (!segments.length) return { segment: -1, local: 0 };
  const at = Math.max(0, t);
  let start = 0;
  for (let index = 0; index < segments.length; index++) {
    const length = segments[index].duration;
    if (at < start + length || index === segments.length - 1) return { segment: index, local: Math.min(length, Math.max(0, at - start)) };
    start += length;
  }
  return { segment: -1, local: 0 };
}

function segmentStart(project, index) {
  let start = 0;
  for (let i = 0; i < index; i++) start += project.segments[i].duration;
  return start;
}

// The scene shown at a moment: the last scene event at or before it (marks change nothing).
function sceneAt(project, t) {
  let scene = project.scenes && project.scenes.length ? project.scenes[0].id : "screen";
  let first = true;
  for (const event of project.events || []) {
    if (!event.scene) continue;
    if (first || event.t <= t + 1e-9) scene = event.scene;
    first = false;
    if (event.t > t + 1e-9) break;
  }
  return scene;
}

function sceneName(id) {
  const doc = studioDoc();
  const scene = doc && doc.scenes.find((item) => item.id === id);
  return scene ? scene.name : id;
}

// What a project shows in a scene, like capture_project.effective_placements: sources that were not recorded
// are skipped, and a scene left with only the screen uses the `screen` scene's layout.
function projectPlacements(project, scene, canvas) {
  const tracks = new Set();
  for (const segment of project.segments) for (const track of Object.keys(segment.files || {})) tracks.add(track);
  const available = new Set(project.sources.filter((source) => source.enabled && (source.kind === "image" || source.kind === "text" || tracks.has(source.kind))).map((source) => source.id));
  const layouts = project.layouts[canvas] || {};
  const pick = (name) => {
    const layout = layouts[name];
    if (!layout) return [{ kind: "color", color: "#000000" }, [], false];
    const chosen = [];
    let dropped = false;
    for (const source of project.sources) {
      const item = layout.placements[source.id];
      if (!item || !item.visible) continue;
      if (available.has(source.id)) chosen.push([source, item]);
      else dropped = true;
    }
    return [layout.background, chosen, dropped];
  };
  let [background, chosen, dropped] = pick(scene);
  const onlyScreen = chosen.length === 1 && chosen[0][0].id === "screen";
  if (scene !== "screen" && (!chosen.length || (onlyScreen && dropped)) && layouts.screen) [background, chosen] = pick("screen");
  return [background, chosen];
}

// ---- project player: the screen video is the clock; camera and microphone follow their `starts` ----
function makePlayer() {
  const screen = h("video", { playsinline: true, preload: "auto" });
  const camera = h("video", { playsinline: true, preload: "auto" });
  camera.muted = true;
  const mic = h("audio", { preload: "auto" });
  return { screen, camera, mic, segment: -1, t: 0, playing: false, timer: 0 };
}

function stopProjectPlayer() {
  const player = studio.player;
  if (!player) return;
  clearInterval(player.timer);
  for (const track of PROJECT_TRACKS) {
    const node = player[track];
    if (node.pause) node.pause();
    if (node.removeAttribute) node.removeAttribute("src");
  }
  studio.player = null;
}

function clockTrack(segment) { return PROJECT_TRACKS.find((track) => segment.files && segment.files[track]) || null; }
function playMedia(node) { const playing = node.play && node.play(); if (playing && playing.catch) playing.catch(() => {}); }
function setMediaTime(node, value) {
  if (node.readyState >= 1) node.currentTime = value;
  else node.addEventListener("loadedmetadata", () => { node.currentTime = value; }, { once: true });
}

function seekProject(t) {
  const project = studio.project, player = studio.player;
  if (!project || !player) return;
  const { segment, local } = projectClock(project, t);
  if (segment < 0) return;
  const before = currentScene();
  const part = project.segments[segment], starts = part.starts || {};
  if (segment !== player.segment) {
    player.segment = segment;
    for (const track of PROJECT_TRACKS) {
      const file = part.files && part.files[track];
      if (file) player[track].src = projectMedia(project.path, file);
      else { if (player[track].pause) player[track].pause(); if (player[track].removeAttribute) player[track].removeAttribute("src"); }
    }
  }
  player.t = segmentStart(project, segment) + local;
  for (const track of PROJECT_TRACKS) if (part.files && part.files[track]) setMediaTime(player[track], Math.max(0, local - (starts[track] || 0)));
  resumePlayer();
  drawPlayerClock();
  if (currentScene() !== before) { drawStage(); renderProjectProps(); }
}

function resumePlayer() {
  const player = studio.player;
  if (!player || !player.playing || !studio.project) return;
  const part = studio.project.segments[player.segment];
  if (part) for (const track of PROJECT_TRACKS) if (part.files && part.files[track]) playMedia(player[track]);
}

function toggleProjectPlay() {
  const player = studio.player;
  if (!player) return;
  player.playing = !player.playing;
  if (player.playing) {
    if (player.t >= studio.project.duration - 0.05) seekProject(0);
    resumePlayer();
  } else for (const track of PROJECT_TRACKS) if (player[track].pause) player[track].pause();
  drawPlayerClock();
}

function syncPlayer() {
  const project = studio.project, player = studio.player;
  if (!project || !player || player.segment < 0) return;
  const part = project.segments[player.segment], clock = clockTrack(part);
  if (!clock) return;
  const starts = part.starts || {};
  const local = (player[clock].currentTime || 0) + (starts[clock] || 0);
  const before = currentScene();
  player.t = segmentStart(project, player.segment) + Math.min(local, part.duration);
  if (player.playing) {
    for (const track of PROJECT_TRACKS) {
      if (track === clock || !part.files[track]) continue;
      const node = player[track], wanted = local - (starts[track] || 0);
      if (wanted < 0) { if (!node.paused) node.pause(); continue; }
      if (Math.abs(node.currentTime - wanted) > 0.25) node.currentTime = wanted;
      if (node.paused && !node.ended) playMedia(node);
    }
    if (player[clock].ended || local >= part.duration - 0.03) {
      if (player.segment + 1 < project.segments.length) seekProject(segmentStart(project, player.segment + 1));
      else { player.playing = false; for (const track of PROJECT_TRACKS) if (player[track].pause) player[track].pause(); }
    }
  }
  drawPlayerClock();
  if (currentScene() !== before) { drawStage(); renderProjectProps(); }
}

function drawPlayerClock() {
  const player = studio.player, project = studio.project;
  if (!player || !project) return;
  const time = $("projTime"), seek = $("projSeek"), play = $("projPlay");
  if (time) time.textContent = clockText(player.t) + " / " + clockText(project.duration);
  if (seek && document.activeElement !== seek) seek.value = String(player.t);
  if (play) play.textContent = player.playing ? "❚❚" : "▶";
}

// ---- projects list ----
async function loadLibrary() {
  studio.libraryLoaded = true;
  const { status, data } = await api("GET", "/api/studio/library");
  if (status !== 200) return;
  studio.library = Array.isArray(data) ? data : [];
  if (state.view === "studio" && studio.tab === "projects" && !studio.project) renderProjects();
}

async function loadProjects() {
  studio.projectsLoaded = true;
  const { status, data } = await api("GET", "/api/studio/projects");
  if (status !== 200) { toast(data.error || "Could not list the projects"); return; }
  studio.projects = Array.isArray(data) ? data : [];
  if (state.view === "studio" && studio.tab === "projects" && !studio.project) renderProjects();
}

function exportLabel(path) {
  const found = /\s(16x9|9x16|1x1|4x5|source)(?:\s\d+)?\.(\w+)$/.exec(path);
  return found ? found[1].replace("x", ":") + " " + found[2].toUpperCase() : String(path).split(".").pop().toUpperCase();
}

function renderProjects() {
  const box = $("studioProjects");
  if (!box) return;
  if (studio.project) { renderProjectPage(box); return; }
  box.textContent = "";
  const filters = h("div", { class: "levels", id: "libFilters" }, [["projects", "Projects"], ["exports", "Exports"], ["screenshots", "Screenshots"]].map(([value, label]) =>
    h("button", { class: studio.filter === value ? "on" : "", text: label, onclick: () => { studio.filter = value; localStorage.setItem("studio-filter", value); renderProjects(); } })));
  box.append(h("div", { class: "projbar" }, filters, h("span", { class: "spacer" }),
    h("button", { text: "Open project…", title: "Open a project folder from anywhere (a moved or copied project)", onclick: openProjectDialog }),
    h("button", { class: "ghost", text: "Refresh", onclick: () => { loadProjects(); loadLibrary(); } })));
  const grid = h("div", { class: "library", id: "library" });
  box.append(grid);
  if (studio.filter === "projects") {
    if (!studio.projectsLoaded) loadProjects();
    if (!studio.projects.length) { grid.append(h("div", { class: "empty", text: "No projects yet. Every recording becomes one." })); return; }
    for (const item of studio.projects.slice(0, 200)) grid.append(projectCard(item));
    return;
  }
  if (!studio.libraryLoaded) loadLibrary();
  renderLibrary(grid);
}

function projectCard(item) {
  const pic = h("div", { class: "pic" });
  if (item.tracks.includes("screen") || item.tracks.includes("camera")) pic.append(h("img", { src: media("/media/thumb") + "&path=" + encodeURIComponent(item.path), alt: "", loading: "lazy" }));
  else pic.append(svgIcon(ICONS.audio));
  pic.append(h("span", { class: "len", text: clockText(item.duration) }));
  if (item.state !== "ready") pic.append(h("span", { class: "state " + item.state, text: item.state, title: (item.problems || []).join("\n") }));
  const formats = item.exports.map(exportLabel);
  const when = new Date(item.created).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  return h("button", { class: "item", title: item.path, onclick: () => openProject(item.path) }, pic,
    h("div", { class: "cap" }, h("b", { text: item.name }), h("span", { text: when + " · " + sizeText(item.size) + " · " + (formats.length ? formats.join(", ") : "not exported") })));
}

async function openProjectDialog() {
  const { status, data } = await api("POST", "/api/studio/open-project", {});
  if (status !== 200) { toast(data.error || "Could not open the project"); return; }
  if (data.unavailable) { toast("The folder dialog needs macOS (osascript)"); return; }
  if (!data.path) return;
  studio.projectsLoaded = false;
  await openProject(data.path);
}

// ---- one project: synced preview, timeline, layout edits saved to the project, export ----
async function openProject(path, withExport) {
  const { status, data } = await api("GET", "/api/studio/project?path=" + encodeURIComponent(path));
  if (status !== 200) { toast(data.error || "Could not open the project"); return; }
  if (studio.projectTimer) await flushProject();
  stopProjectPlayer();
  studio.tab = "projects";
  localStorage.setItem("studio-tab", "projects");
  clearTimeout(studio.previewTimer);
  stopStream("camStream");
  stopStream("micStream");
  delete data.warnings;
  studio.project = data;
  studio.projectCanvas = STUDIO_RATIOS[data.export.canvas] ? data.export.canvas : "16:9";
  const shown = projectPlacements(data, sceneAt(data, 0), studio.projectCanvas)[1];
  studio.selected = shown.length ? shown[shown.length - 1][0].id : data.sources[0].id;
  studio.player = makePlayer();
  studio.player.timer = setInterval(syncPlayer, 200);
  if (state.view === "studio") renderStudioBody();
  seekProject(0);
  if (withExport) renderExportDialog(data);
}

async function closeProject() {
  if (studio.projectTimer) await flushProject();
  stopProjectPlayer();
  studio.project = null;
  studio.projectsLoaded = false;
  renderStudioBody();
}

function saveProjectSoon() {
  clearTimeout(studio.projectTimer);
  studio.projectTimer = setTimeout(flushProject, 500);
}

async function flushProject() {
  clearTimeout(studio.projectTimer);
  studio.projectTimer = 0;
  const project = studio.project;
  if (!project) return;
  // Only project.json keys go back; capture keeps what was recorded (segments, exports, ...) from disk.
  const body = {};
  for (const [key, value] of Object.entries(project)) if (!["path", "size", "warnings"].includes(key)) body[key] = value;
  const { status, data } = await api("POST", "/api/studio/project", { path: project.path, project: body });
  if (status !== 200) toast(data.error || "Could not save the project");
}

async function projectAction(action) {
  const project = studio.project;
  if (!project) return;
  if (action === "delete" && !confirm("Move the project “" + project.name + "” to the Trash? Exported videos stay.")) return;
  const { status, data } = await api("POST", "/api/studio/action", { action, path: project.path });
  if (status !== 200) { toast(data.error || "Failed"); return; }
  if (action !== "delete") return;
  toast("Moved to the Trash");
  clearTimeout(studio.projectTimer);
  studio.projectTimer = 0;
  stopProjectPlayer();
  studio.project = null;
  studio.projects = studio.projects.filter((item) => item.path !== project.path);
  if (state.view === "studio") renderStudioBody();
}

function renderProjectPage(box) {
  const project = studio.project;
  box.textContent = "";
  const meta = [clockText(project.duration), project.state, sizeText(project.size || 0)].join(" · ");
  box.append(h("div", { class: "projbar" },
    h("button", { class: "ghost", text: "← Projects", onclick: closeProject }),
    h("b", { text: project.name }), h("span", { class: "where", text: meta }), h("span", { class: "spacer" }),
    h("div", { class: "seg fmt" }, STUDIO_FORMATS.map(([value, label]) =>
      h("button", { class: studio.projectCanvas === value ? "on" : "", text: label, onclick: () => { studio.projectCanvas = value; renderProjectPage(box); } }))),
    h("button", { class: "primary", text: "Export…", onclick: () => renderExportDialog(project) }),
    h("button", { text: "Show in Finder", onclick: () => projectAction("reveal") }),
    h("button", { class: "ghost", text: "Move to Trash", onclick: () => projectAction("delete") })));
  if (project.problems.length) box.append(h("div", { class: "warns" }, project.problems.map((problem) => h("div", { text: "⚠ " + problem }))));
  const seek = h("input", { type: "range", id: "projSeek", min: "0", max: String(project.duration), step: "0.01", value: "0" });
  seek.addEventListener("input", () => seekProject(Number(seek.value)));
  const timeline = h("div", { class: "scenelist" });
  for (const event of project.events) {
    if (!event.scene && !("mark" in event)) continue;
    timeline.append(h("div", { role: "button", tabindex: "0", style: "cursor:pointer", onclick: () => seekProject(event.t) },
      h("span", { class: "t", text: clockText(event.t) }), h("span", { text: event.scene ? sceneName(event.scene) : "⚑ " + (event.mark || "mark") })));
  }
  const exports = h("div", { class: "scenelist" }, project.exports.length ? project.exports.map((item) => {
    const name = String(item.path).split("/").pop();
    return h("div", { role: "button", tabindex: "0", style: "cursor:pointer", title: "Show in Finder", onclick: () => revealExport(name) }, h("span", { text: name }));
  }) : h("div", { class: "where", text: "Not exported yet." }));
  box.append(h("div", { class: "projpage" },
    h("div", { class: "centre" },
      h("div", { class: "stage", id: "stage" }),
      h("div", { class: "player" }, h("button", { id: "projPlay", text: "▶", onclick: toggleProjectPlay }), seek, h("span", { class: "where", id: "projTime" })),
      h("div", { class: "sthint", id: "stageHint" })),
    h("div", { class: "right" },
      h("div", { class: "pane" }, h("h5", { text: "Timeline" }), timeline),
      h("div", { class: "pane", id: "propsPane" }),
      h("div", { class: "pane" }, h("h5", { text: "Exports" }), exports))));
  drawStage();
  drawPlayerClock();
  renderProjectProps();
}

function renderProjectProps() {
  const box = $("propsPane");
  if (!box || !studio.project) return;
  box.textContent = "";
  box.append(h("h5", { text: "Layout · " + sceneName(currentScene()) + " · " + currentCanvas() }));
  if (currentCanvas() === "source") { box.append(h("p", { class: "note", text: "“As recorded” is the screen as captured; pick a format to change the layout." })); return; }
  const shown = projectPlacements(studio.project, currentScene(), currentCanvas())[1].map(([source]) => source);
  if (!shown.length) { box.append(h("p", { class: "note", text: "Nothing of this project is visible in this scene." })); return; }
  if (!shown.some((source) => source.id === studio.selected)) studio.selected = shown[shown.length - 1].id;
  box.append(prow("Source", studioSelect(shown.map((source) => [source.id, sourceName(source)]), studio.selected, (value) => { studio.selected = value; drawStage(); renderProjectProps(); })));
  const source = sourceById(studio.selected), item = placementOf(studio.selected);
  if (source && item) box.append(...placementControls(source, item));
  else box.append(h("p", { class: "note", text: "Shown through the Screen scene's layout; edit it while that scene plays." }));
  box.append(h("p", { class: "note", text: "Saved to this project only; the studio setup stays as it is." }));
}

async function revealExport(name) {
  const { status, data } = await api("POST", "/api/studio/action", { action: "reveal", name });
  if (status !== 200) toast(data.error || "Not in the recordings folder");
}

// ---- export dialog ----
const EXPORT_DEFAULTS = { canvas: "16:9", height: 1440, fps: 60, codec: "h264", quality: "high", container: "mov", normalize: true, delete_sources: false };

// Pre-fill: this project's last export, else the last settings used anywhere (setup.export), like capture's export_settings.
function exportDefaults(project, setup) {
  const values = { ...EXPORT_DEFAULTS };
  for (const layer of [(setup && setup.export) || {}, (project && project.export) || {}]) {
    for (const key of Object.keys(EXPORT_DEFAULTS)) if (key in layer) values[key] = layer[key];
  }
  if (project && project.mode === "camera" && !(project.export && "height" in project.export)) values.height = 1080;
  values.delete_sources = false;
  return values;
}

function exportHeightFor(canvas, mode) { return canvas === "16:9" && mode !== "camera" ? 1440 : 1080; }

function renderExportDialog(project) {
  const sheet = $("viewerSheet");
  if (!sheet) return;
  studio.item = null;
  sheet.textContent = "";
  const values = exportDefaults(project, studio.setup);
  const audioOnly = project.mode === "audio";
  const field = (label, control) => h("label", {}, label, control);
  const tick = (label, key) => {
    const input = h("input", { type: "checkbox" });
    input.checked = values[key];
    input.addEventListener("change", () => { values[key] = input.checked; });
    return h("label", { class: "check" }, input, label);
  };
  sheet.append(h("div", { class: "top" }, h("b", { text: "Export " + project.name }), h("button", { class: "ghost", text: "Close", onclick: closeViewer })));
  const form = h("div", { class: "export" });
  if (!audioOnly) {
    const height = studioSelect([["1080", "1080p"], ["1440", "1440p"], ["2160", "2160p (4K)"]], String(values.height), (value) => { values.height = Number(value); });
    height.disabled = values.canvas === "source";
    form.append(
      field("Format", studioSelect(STUDIO_FORMATS, values.canvas, (value) => {
        values.canvas = value;
        values.height = exportHeightFor(value, project.mode);
        height.value = String(values.height);
        height.disabled = value === "source";
      })),
      field("Size (short side)", height),
      field("Frame rate", studioSelect([["60", "60 fps"], ["30", "30 fps"]], String(values.fps), (value) => { values.fps = Number(value); })),
      field("Codec", studioSelect([["h264", "H.264 (plays everywhere)"], ["hevc", "HEVC (smaller files)"]], values.codec, (value) => { values.codec = value; })),
      field("Quality", studioSelect([["high", "High"], ["max", "Max (1.5× bitrate)"]], values.quality, (value) => { values.quality = value; })),
      field("File", studioSelect([["mov", "MOV"], ["mp4", "MP4"]], values.container, (value) => { values.container = value; })));
  }
  form.append(tick("Loudness to −14 LUFS", "normalize"), tick("Delete the recorded tracks after a successful export", "delete_sources"));
  sheet.append(form);
  sheet.append(h("p", { class: "where", text: audioOnly ? "Saved to captures/recordings in the audio format of capture.audio_format." : "Saved to captures/recordings as “" + project.name + " 16x9.mov” (the format in the name), never over another file. 10 minutes of 1440p60 take about 5 minutes; “As recorded” takes seconds." }));
  sheet.append(h("div", { class: "progress" }, h("i", { id: "exportBar" })), h("div", { class: "where", id: "exportState" }));
  sheet.append(h("div", { class: "tools" }, h("button", { class: "primary", text: "Export", onclick: () => startExport(project, values) })));
  $("viewer").classList.add("on");
  if (studio.exportJob && ["queued", "running"].includes(studio.exportJob.phase)) pollExport();
}

async function startExport(project, values) {
  if (values.delete_sources && !confirm("Delete the recorded tracks of “" + project.name + "” after the export? Only the exported file stays.")) return;
  const body = project.mode === "audio"
    ? { path: project.path, normalize: values.normalize, delete_sources: values.delete_sources }
    : { path: project.path, canvas: values.canvas, height: values.height, fps: values.fps, codec: values.codec, quality: values.quality, format: values.container, normalize: values.normalize, delete_sources: values.delete_sources };
  drawExportState({ phase: "queued", percent: 0 });
  const { status, data } = await api("POST", "/api/studio/export", body);
  if (status !== 200) { drawExportState({ phase: "failed", error: data.error || "the export did not start" }); return; }
  await pollExport();
}

// One export runs at a time (capture keeps the queue); the page follows it every second until it ends.
async function pollExport() {
  clearTimeout(studio.exportTimer);
  studio.exportTimer = 0;
  const { status, data } = await api("GET", "/api/studio/export/status");
  if (status !== 200) { drawExportState({ phase: "failed", error: data.error || "no export status" }); return; }
  drawExportState(data);
  if (data.phase === "queued" || data.phase === "running") studio.exportTimer = setTimeout(pollExport, 1000);
  else if (data.phase === "done") { studio.projectsLoaded = false; studio.libraryLoaded = false; }
}

function drawExportState(job) {
  studio.exportJob = job;
  const bar = $("exportBar"), node = $("exportState");
  if (bar) bar.style.width = (job.phase === "done" ? 100 : Math.max(0, Math.min(100, Number(job.percent) || 0))) + "%";
  if (!node) return;
  node.textContent = "";
  const name = String(job.output || "").split("/").pop();
  const left = Number(job.eta) > 90 ? Math.round(job.eta / 60) + " min" : Math.round(Number(job.eta) || 0) + " s";
  if (job.phase === "queued") node.append("Waiting for the export to start…");
  else if (job.phase === "running") node.append("Exporting… " + Math.round(Number(job.percent) || 0) + "%" + (job.eta ? " · about " + left + " left" : ""));
  else if (job.phase === "done") node.append("Saved " + name + " ", h("button", { class: "ghost", text: "Show in Finder", onclick: () => revealExport(name) }));
  else if (job.phase === "failed") node.append("Export failed: " + (job.error || "unknown error"));
}

function renderLibrary(box) {
  box = box || $("library");
  if (!box) return;
  box.textContent = "";
  const kinds = { exports: ["video", "audio"], screenshots: ["image"] }[studio.filter] || ["video", "audio"];
  const items = studio.library.filter((item) => kinds.includes(item.kind));
  if (!items.length) { box.append(h("div", { class: "empty", text: "Nothing here yet." })); return; }
  for (const item of items.slice(0, 120)) {
    const pic = h("div", { class: "pic" });
    if (item.kind === "audio") pic.append(svgIcon(ICONS.audio));
    else pic.append(h("img", { src: media("/media/thumb", item.name), alt: "", loading: "lazy" }));
    if (item.duration) pic.append(h("span", { class: "len", text: format(item.duration) }));
    const when = new Date(item.modified).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    box.append(h("button", { class: "item", title: item.name, onclick: () => openViewer(item) }, pic,
      h("div", { class: "cap" }, h("b", { text: item.name }), h("span", { text: when + " · " + sizeText(item.size) }))));
  }
}

function fitCanvas(canvas) {
  const scale = window.devicePixelRatio || 1;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (canvas.width !== Math.round(width * scale) || canvas.height !== Math.round(height * scale)) {
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
  }
  const context = canvas.getContext("2d");
  context.setTransform(scale, 0, 0, scale, 0, 0);
  context.clearRect(0, 0, width, height);
  return [context, width, height];
}

function bars(context, x, height, value, width, color) {
  const tall = Math.max(2, value * (height - 8));
  context.fillStyle = color;
  context.beginPath();
  context.roundRect(x, (height - tall) / 2, width, tall, width / 2);
  context.fill();
}

function openViewer(item) {
  studio.item = item;
  studio.trim = { from: null, to: null };
  const sheet = $("viewerSheet");
  sheet.textContent = "";
  const source = media("/media/file", item.name);
  const player = item.kind === "video" ? h("video", { controls: true, src: source, preload: "metadata" }) : item.kind === "audio" ? h("audio", { controls: true, src: source, preload: "metadata" }) : h("img", { src: source, alt: item.name });
  const meta = [item.duration ? format(item.duration) : "", sizeText(item.size), new Date(item.modified).toLocaleString()].filter(Boolean).join(" · ");
  sheet.append(h("div", { class: "top" }, h("b", { text: item.name }), h("span", { class: "where", text: meta }), h("button", { class: "ghost", text: "Close", onclick: closeViewer })));
  sheet.append(h("div", { class: "media" }, player));
  if (item.kind !== "image") {
    const canvas = h("canvas", { class: "filewave", title: "Click to jump there" });
    sheet.append(canvas);
    fileWave(item, player, canvas);
  }
  const act = (action, extra) => async () => {
    const { status, data } = await api("POST", "/api/studio/action", { action, name: item.name, ...(extra || {}) });
    if (status !== 200) { toast(data.error || "Failed"); return null; }
    return data;
  };
  const tools = h("div", { class: "tools" },
    h("button", { text: item.kind === "image" ? "Open in Preview" : "Open in QuickTime", onclick: act("open") }),
    h("button", { text: "Show in Finder", onclick: act("reveal") }),
    item.kind === "image" ? h("button", { text: "Copy", onclick: async () => { if (await act("copy")()) toast("Copied to the clipboard"); } }) : null);
  if (item.kind !== "image") {
    const mark = h("span", { class: "mark", text: "trim: start – end" });
    const show = () => { mark.textContent = "trim: " + (studio.trim.from === null ? "start" : format(studio.trim.from)) + " – " + (studio.trim.to === null ? "end" : format(studio.trim.to)); };
    const convert = studioSelect((item.kind === "video" ? [["mp4", "MP4"], ["mov", "MOV"], ["gif", "GIF"], ["m4a", "Audio M4A"], ["mp3", "Audio MP3"]] : [["mp3", "MP3"], ["m4a", "M4A"], ["wav", "WAV"]]).filter(([value]) => !item.name.toLowerCase().endsWith("." + value)), "", () => {});
    tools.append(h("span", { class: "sep" }),
      h("button", { text: "Set start", title: "Trim from the player position", onclick: () => { studio.trim.from = player.currentTime; show(); } }),
      h("button", { text: "Set end", onclick: () => { studio.trim.to = player.currentTime; show(); } }),
      mark,
      h("button", { text: "Save trimmed", onclick: async () => {
        const extra = {};
        if (studio.trim.from !== null) extra.from = studio.trim.from;
        if (studio.trim.to !== null) extra.to = studio.trim.to;
        if (!Object.keys(extra).length) { toast("Set a start or an end first"); return; }
        toast("Trimming…");
        const data = await act("trim", extra)();
        if (data) { toast("Saved " + data.saved.split("/").pop()); loadLibrary(); }
      } }),
      h("span", { class: "sep" }), convert,
      h("button", { text: "Convert", onclick: async () => {
        toast("Converting…");
        const data = await act("convert", { to: convert.value })();
        if (data) { toast("Saved " + data.saved.split("/").pop()); loadLibrary(); }
      } }));
  }
  tools.append(h("span", { class: "spacer", style: "flex:1" }), h("button", { class: "ghost", text: "Move to Trash", onclick: async () => {
    if (!confirm("Move " + item.name + " to the Trash?")) return;
    if (await act("delete")()) { closeViewer(); toast("Moved to the Trash"); loadLibrary(); }
  } }));
  sheet.append(tools);
  $("viewer").classList.add("on");
}

async function fileWave(item, player, canvas) {
  const count = Math.max(60, Math.min(1200, Math.floor((canvas.clientWidth || 900) / 4)));
  const { status, data } = await api("GET", "/api/studio/wave?name=" + encodeURIComponent(item.name) + "&bars=" + count);
  if (status !== 200 || studio.item !== item) { if (status !== 200) canvas.remove(); return; }
  const peaks = data.peaks;
  const total = () => (Number.isFinite(player.duration) && player.duration > 0 ? player.duration : data.duration) || 1;
  canvas.addEventListener("click", (event) => {
    const box = canvas.getBoundingClientRect();
    player.currentTime = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)) * total();
  });
  let drawn = "";
  const draw = () => {
    if (!canvas.isConnected) return;
    // Redraw only when something visible changed: an open, paused viewer costs nothing.
    const key = [player.currentTime, studio.trim.from, studio.trim.to, canvas.clientWidth, canvas.clientHeight, window.devicePixelRatio].join();
    if (key === drawn) { requestAnimationFrame(draw); return; }
    drawn = key;
    const [context, width, height] = fitCanvas(canvas);
    const step = width / peaks.length, at = player.currentTime / total();
    const from = studio.trim.from === null ? null : studio.trim.from / total();
    const to = studio.trim.to === null ? null : studio.trim.to / total();
    if (from !== null || to !== null) {
      context.fillStyle = "rgba(107,147,255,.16)";
      context.fillRect((from ?? 0) * width, 0, ((to ?? 1) - (from ?? 0)) * width, height);
    }
    peaks.forEach((value, index) => bars(context, index * step + 0.5, height, value, Math.max(1, step - 1.5), index / peaks.length < at ? "#ff453a" : "#8e8e93"));
    context.fillStyle = "#f2f2f7";
    context.fillRect(at * width - 1, 0, 2, height);
    requestAnimationFrame(draw);
  };
  draw();
}

function closeViewer() {
  const viewer = $("viewer");
  if (!viewer.classList.contains("on")) return;
  viewer.classList.remove("on");
  for (const node of viewer.querySelectorAll("video, audio")) node.pause();
  $("viewerSheet").textContent = "";
  studio.item = null;
}
$("viewer").addEventListener("click", (event) => { if (event.target === $("viewer")) closeViewer(); });
$("recPill").addEventListener("click", () => { if (state.view !== "studio") setView("studio"); });
window.addEventListener("resize", () => { if (state.view === "studio" && studio.tab === "record") drawStage(); });

"""
