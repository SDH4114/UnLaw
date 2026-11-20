"""The Studio's Edit tab for `ul desk`: a timeline editor in vanilla JS (no framework, no build step).

The model is OpenCut's (tracks of clips with in/out points) and the feel is DaVinci Resolve's (blade, ripple
delete, J/K/L, I/O, snapping). The edit lives in the project's project.json under `edit`
(capture_project.validate_edit); recorded files are never changed. Captions and text are drawn here to PNG
and uploaded into the project's assets/, because the export burns them in with ffmpeg's overlay filter.
"""

EDIT_CSS = r""".editor { display: grid; grid-template-columns: 250px minmax(0, 1fr) 280px; grid-template-rows: auto minmax(200px, 1fr) 6px var(--tl, 300px);
  gap: 8px; height: calc(100vh - 150px); min-height: 560px; }
.editor .edbar { grid-column: 1 / -1; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.editor .edbar b { font-size: 13px; }
.editor .pane { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: auto; min-height: 0; }
.editor .pane h5 { margin: 0; padding: 8px 10px 6px; font-size: 10px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.editor .edmedia, .editor .edinspect { padding-bottom: 8px; }
.editor .edmedia .row, .editor .edinspect .prow { padding: 3px 10px; }
.editor .edmedia button.wide { display: flex; align-items: center; gap: 6px; width: calc(100% - 20px); margin: 3px 10px; }
.editor .caplist { display: flex; flex-direction: column; gap: 2px; padding: 0 6px; }
.editor .caplist .cap { display: grid; grid-template-columns: 54px 1fr; gap: 6px; align-items: center; padding: 3px 4px; border-radius: 5px; }
.editor .caplist .cap.on { background: color-mix(in srgb, var(--accent) 22%, transparent); }
.editor .caplist .cap span { font: 11px ui-monospace, monospace; color: var(--muted); cursor: pointer; }
.editor .caplist .cap input { width: 100%; min-width: 0; font-size: 12px; }
.editor .edview { display: flex; flex-direction: column; gap: 6px; min-height: 0; }
.editor .edview .stagebox { flex: 1; min-height: 0; position: relative; container-type: size; display: grid; place-items: center; }
.editor .stageui { display: none; }
.editor .stage { pointer-events: none; }
.editor .edview canvas.edwave { position: absolute; inset: 0; width: 100%; height: 100%; display: block; border-radius: 8px; background: var(--panel); }
.editor .edover { position: absolute; inset: 0; pointer-events: none; overflow: hidden; }
.editor .edover .ecap { position: absolute; left: 50%; transform: translateX(-50%); text-align: center; max-width: 84%; font-weight: 700; line-height: 1.2; white-space: pre-wrap; }
.editor .edover img { position: absolute; transform: translate(-50%, -50%); }
.editor .edtrans { display: flex; align-items: center; gap: 6px; }
.editor .edtrans .clock { font: 600 15px ui-monospace, monospace; min-width: 170px; }
.editor .edtl { grid-column: 1 / -1; position: relative; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.editor .edtl canvas { position: absolute; inset: 0; width: 100%; height: 100%; cursor: default; touch-action: none; }
.editor .edgutter { grid-column: 1 / -1; cursor: row-resize; border-radius: 3px; }
.editor .edgutter:hover { background: var(--line); }
.editor .edempty { grid-column: 1 / -1; }
.editor .busy { opacity: .6; pointer-events: none; }
.edpick { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.audioview { display: flex; flex-direction: column; gap: 8px; }
.audioview canvas { width: 100%; height: 280px; display: block; border-radius: 10px; background: var(--panel); border: 1px solid var(--line); }
"""

EDIT_JS = r"""// ---- Edit tab: the montage of one project (OpenCut's model, Resolve's keys) ----
const ED_RATE = 25;  // waveform bars per second of recording
const ED_LABEL = 112, ED_RULER = 24;
const ED_ROWS = [["text", 30, "Text"], ["subs", 30, "Subtitles"], ["main", 76, ""], ["music", 50, "Music & voice"]];
const CAPTION_DEFAULT = { font: "system-ui", size: 54, color: "#ffffff", outline: "#000000", box: false, position: "bottom" };
const CAPTION_FONTS = [["system-ui", "System"], ["serif", "Serif"], ["monospace", "Mono"], ["rounded", "Rounded"]];
const ED_LANGUAGES = [["", "Detect"], ["en", "English"], ["ru", "Русский"], ["az", "Azərbaycan"], ["tr", "Türkçe"], ["de", "Deutsch"], ["fr", "Français"], ["es", "Español"], ["uk", "Українська"]];
const ED_FONT_CSS = { "system-ui": "system-ui, -apple-system, sans-serif", serif: "Georgia, serif", monospace: "ui-monospace, Menlo, monospace", rounded: "ui-rounded, 'SF Pro Rounded', system-ui, sans-serif" };
const ed = { zoom: 0, scroll: 0, t: 0, playing: false, timer: 0, sel: null, in: null, out: null, snap: localStorage.getItem("edit-snap") !== "off",
  peaks: null, peaksFor: "", assetPeaks: {}, audio: {}, drag: null, busy: "", language: localStorage.getItem("edit-language") || "", lastTick: 0, drawTimer: 0, assetTimer: 0, pending: null, pendingAt: 0 };

// ---- pure model (tested in tests/test_desk_ui.cjs) ----
function round3(value) { return Math.round(value * 1000) / 1000; }
function edId(list, prefix) { let n = 1; const used = new Set(list.map((item) => item.id)); while (used.has(prefix + n)) n++; return prefix + n; }
function defaultEdit(project) {
  return { version: 1, clips: [{ id: "c1", in: 0, out: round3(project.duration) }], captions: [], caption_style: { ...CAPTION_DEFAULT }, texts: [], audio: [] };
}
function editOf(project) {
  if (!project.edit && project.duration > 0) project.edit = defaultEdit(project);
  return project.edit || null;
}
function edClips(edit) {
  let at = 0;
  return edit.clips.map((clip, index) => { const item = { ...clip, index, at }; at += clip.out - clip.in; return item; });
}
function edLength(edit) { return edit.clips.reduce((sum, clip) => sum + clip.out - clip.in, 0); }
// Output time -> recording time (the clip under it); past the end -> the end of the last clip.
function toRecording(edit, t) {
  const clips = edClips(edit);
  for (const clip of clips) if (t < clip.at + (clip.out - clip.in) - 1e-9) return { index: clip.index, t: clip.in + Math.max(0, t - clip.at) };
  const last = clips[clips.length - 1];
  return last ? { index: last.index, t: last.out } : { index: -1, t: 0 };
}
// Recording time -> output time, or null when that moment was cut away.
function toOutput(edit, t) {
  for (const clip of edClips(edit)) if (t >= clip.in - 1e-9 && t <= clip.out + 1e-9) return clip.at + t - clip.in;
  return null;
}
function bladeAt(edit, t) {
  const clips = edClips(edit);
  const clip = clips.find((item) => t > item.at + 0.02 && t < item.at + item.out - item.in - 0.02);
  if (!clip) return false;
  const cut = round3(clip.in + t - clip.at);
  edit.clips.splice(clip.index, 1, { id: clip.id, in: clip.in, out: cut }, { id: edId(edit.clips, "c"), in: cut, out: clip.out });
  return true;
}
function rippleDelete(edit, index) {
  if (edit.clips.length <= 1 || index < 0 || index >= edit.clips.length) return false;
  edit.clips.splice(index, 1);
  return true;
}
// Remove [a, b) of the output (I/O range), closing the gap.
function deleteRange(edit, a, b) {
  if (!(b - a > 0.02)) return false;
  bladeAt(edit, a);
  bladeAt(edit, b);
  const keep = edClips(edit).filter((clip) => clip.at + 1e-6 < a || clip.at >= b - 1e-6);
  if (!keep.length) return false;
  edit.clips = keep.map(({ id, in: start, out }) => ({ id, in: start, out }));
  return true;
}
// Ranges of the recording clock taken out of every clip (cutting silences).
function subtractRanges(edit, ranges) {
  const clips = [];
  for (const clip of edit.clips) {
    let pieces = [[clip.in, clip.out]];
    for (const [a, b] of ranges) {
      const next = [];
      for (const [x, y] of pieces) {
        if (b <= x || a >= y) { next.push([x, y]); continue; }
        if (a > x) next.push([x, a]);
        if (b < y) next.push([b, y]);
      }
      pieces = next;
    }
    for (const [x, y] of pieces) if (y - x >= 0.05) clips.push({ id: clips.some((item) => item.id === clip.id) ? "" : clip.id, in: round3(x), out: round3(y) });
  }
  for (const clip of clips) if (!clip.id) clip.id = edId(clips, "c");
  if (!clips.length) return false;
  edit.clips = clips;
  return true;
}
// Quiet stretches (peaks below `level` for at least `least` seconds), shrunk by `pad` on both sides.
function silences(peaks, rate, level, least, pad) {
  const found = [];
  let start = -1;
  for (let i = 0; i <= peaks.length; i++) {
    const quiet = i < peaks.length && peaks[i] < level;
    if (quiet && start < 0) start = i;
    if (!quiet && start >= 0) {
      const a = start / rate + pad, b = i / rate - pad;
      if (i / rate - start / rate >= least && b - a > 0.05) found.push([round3(a), round3(b)]);
      start = -1;
    }
  }
  return found;
}
function snapTime(t, targets, tolerance) {
  let best = t, distance = tolerance;
  for (const target of targets) if (Math.abs(target - t) < distance) { best = target; distance = Math.abs(target - t); }
  return best;
}
function edEdges(edit) {
  const edges = [0];
  for (const clip of edClips(edit)) edges.push(clip.at + clip.out - clip.in);
  for (const item of edit.texts) edges.push(item.start, item.end);
  for (const item of edit.audio) edges.push(item.start, item.start + item.out - item.in);
  return edges;
}
// Captions on the output: each line clipped to what the cuts keep (like capture_project.caption_spans).
function captionSpans(edit) {
  const spans = [];
  const clips = edClips(edit);
  for (const line of [...edit.captions].sort((a, b) => a.in - b.in)) {
    let start = null, end = null;
    for (const clip of clips) {
      const low = Math.max(line.in, clip.in), high = Math.min(line.out, clip.out);
      if (high > low) { if (start === null) start = clip.at + low - clip.in; end = clip.at + high - clip.in; }
    }
    if (start !== null && end - start > 0.02) spans.push({ id: line.id, start, end, text: line.text });
  }
  return spans;
}
function captionAt(edit, t) { return captionSpans(edit).find((span) => t >= span.start && t < span.end) || null; }
function splitCaption(edit, id, at) {
  const index = edit.captions.findIndex((line) => line.id === id);
  const line = edit.captions[index];
  if (!line || !(at > line.in + 0.05 && at < line.out - 0.05)) return false;
  const words = line.text.split(/\s+/);
  const share = Math.max(1, Math.min(words.length - 1, Math.round(words.length * (at - line.in) / (line.out - line.in))));
  const second = { id: edId(edit.captions, "s"), in: round3(at), out: line.out, text: words.slice(share).join(" ") || line.text, asset: "" };
  edit.captions.splice(index, 1, { ...line, out: round3(at), text: words.slice(0, share).join(" ") || line.text, asset: "" }, second);
  return true;
}
function mergeCaption(edit, id) {
  const sorted = [...edit.captions].sort((a, b) => a.in - b.in);
  const index = sorted.findIndex((line) => line.id === id);
  if (index < 0 || index + 1 >= sorted.length) return false;
  const next = sorted[index + 1];
  sorted[index] = { ...sorted[index], out: next.out, text: (sorted[index].text + " " + next.text).trim().slice(0, 500), asset: "" };
  sorted.splice(index + 1, 1);
  edit.captions = sorted;
  return true;
}
function captionsFrom(lines) {
  return lines.filter((line) => line.out > line.in && line.text).map((line, index) => ({ id: "s" + (index + 1), in: round3(line.in), out: round3(line.out), text: String(line.text).slice(0, 500), asset: "" }));
}
function hashText(text) {
  let a = 0x811c9dc5, b = 0x01000193;
  for (let i = 0; i < text.length; i++) { const code = text.charCodeAt(i); a = Math.imul(a ^ code, 16777619) >>> 0; b = Math.imul(b ^ code, 2246822519) >>> 0; }
  return a.toString(16).padStart(8, "0") + b.toString(16).padStart(8, "0");
}
function captionAssetName(text, style) { return "cap-" + hashText(text + "\u0000" + JSON.stringify(style)) + ".png"; }
function textAssetName(item) { return "text-" + hashText([item.text, item.color, item.background, item.font].join("\u0000")) + ".png"; }
// Recording peaks on one clock from per-part files: [{start, peaks, duration}] -> bars at ED_RATE.
function joinPeaks(parts, duration, rate) {
  const out = new Array(Math.max(1, Math.ceil(duration * rate))).fill(0);
  for (const part of parts) {
    const per = part.duration / Math.max(1, part.peaks.length);
    part.peaks.forEach((value, i) => {
      const at = Math.floor((part.start + i * per) * rate);
      if (at >= 0 && at < out.length && value > out[at]) out[at] = value;
    });
  }
  return out;
}
function soundFiles(project) {
  const files = [];
  let start = 0;
  for (const segment of project.segments) {
    const track = segment.files.mic ? "mic" : segment.files.screen && !(segment.info && segment.info.screen && segment.info.screen.audio === false) ? "screen" : null;
    if (track) files.push({ file: segment.files[track], start: start + ((segment.starts || {})[track] || 0), duration: segment.duration });
    start += segment.duration;
  }
  return files;
}
function audioOnly(project) { return !project.segments.some((segment) => segment.files.screen || segment.files.camera); }

// ---- loading ----
async function edPeaks(project) {
  if (ed.peaksFor === project.path && ed.peaks) return ed.peaks;
  ed.peaksFor = project.path;
  ed.peaks = null;
  const parts = [];
  for (const item of soundFiles(project)) {
    const bars = Math.max(10, Math.min(20000, Math.round(item.duration * ED_RATE)));
    const { status, data } = await api("GET", "/api/studio/project/wave?path=" + encodeURIComponent(project.path) + "&file=" + encodeURIComponent(item.file) + "&bars=" + bars);
    if (status === 200 && Array.isArray(data.peaks)) parts.push({ start: item.start, peaks: data.peaks, duration: data.duration || item.duration });
  }
  if (ed.peaksFor !== project.path) return null;
  ed.peaks = joinPeaks(parts, project.duration, ED_RATE);
  edDraw();
  if (typeof drawAudioView === "function") drawAudioView();
  return ed.peaks;
}
async function edAssetPeaks(project, asset) {
  if (ed.assetPeaks[asset]) return;
  ed.assetPeaks[asset] = { peaks: [], duration: 0 };
  const { status, data } = await api("GET", "/api/studio/project/wave?path=" + encodeURIComponent(project.path) + "&file=" + encodeURIComponent("assets/" + asset) + "&bars=4000");
  if (status === 200 && Array.isArray(data.peaks)) ed.assetPeaks[asset] = { peaks: data.peaks, duration: data.duration || 0 };
  edDraw();
}

// ---- opening ----
async function openEdit(path) {
  if (!studio.project || studio.project.path !== path) await openProject(path);
  if (!studio.project) return;
  edEnter();
}
function edEnter() {
  studio.tab = "edit";
  localStorage.setItem("studio-tab", "edit");
  localStorage.setItem("studio-edit-path", studio.project.path);
  const fresh = !studio.project.edit;
  editOf(studio.project);
  if (fresh && studio.project.edit) { startHistory(studio.project); saveProjectSoon(); }
  ed.t = 0; ed.sel = null; ed.in = ed.out = null; ed.zoom = 0; ed.scroll = 0;
  renderStudioBody();
}
function edLeave() {
  edPause();
  clearInterval(ed.timer);
  ed.timer = 0;
  for (const node of Object.values(ed.audio)) { node.pause(); node.removeAttribute("src"); }
  ed.audio = {};
}

// ---- changes: every one is undoable and saved ----
function edChanged(redraw) {
  rememberEdit();
  saveProjectSoon();
  edScheduleAssets();
  if (redraw === "all") renderEdit(); else { edDraw(); renderEditSide(); edOverlay(); }
}

// ---- playback on the output clock: the recording player follows the clips ----
function edSeek(t) {
  const edit = studio.project && studio.project.edit;
  if (!edit) return;
  ed.t = Math.max(0, Math.min(edLength(edit), t));
  const at = toRecording(edit, ed.t);
  if (studio.player) seekProject(at.t);
  edSyncAudio(true);
  edDraw();
  edOverlay();
  edClock();
}
function edPlay() {
  const edit = studio.project && studio.project.edit;
  if (!edit || !studio.player) return;
  if (ed.t >= edLength(edit) - 0.05) edSeek(0);
  ed.playing = true;
  studio.player.playing = true;
  ed.pending = toRecording(edit, ed.t).t;
  ed.pendingAt = performance.now();
  seekProject(ed.pending);
  ed.lastTick = performance.now();
  clearInterval(ed.timer);
  ed.timer = setInterval(edTick, 40);
  edClock();
}
function edPause() {
  ed.playing = false;
  clearInterval(ed.timer);
  ed.timer = 0;
  if (studio.player) {
    studio.player.playing = false;
    for (const track of PROJECT_TRACKS) if (studio.player[track].pause) studio.player[track].pause();
  }
  for (const node of Object.values(ed.audio)) node.pause();
  edClock();
}
function edToggle() { if (ed.playing) edPause(); else edPlay(); }
function edTick() {
  const project = studio.project, edit = project && project.edit;
  if (!edit || !ed.playing || !studio.player) return;
  syncPlayer();
  const clips = edClips(edit);
  const now = toRecording(edit, ed.t);
  const clip = clips[now.index];
  if (!clip) { edPause(); return; }
  const elapsed = (performance.now() - ed.lastTick) / 1000;
  ed.lastTick = performance.now();
  // A part without any media element (no sound recorded) has no clock of its own: time just runs.
  const media = project.segments.some((segment) => clockTrack(segment));
  let recording = media ? studio.player.t : now.t + elapsed;
  if (ed.pending !== null) {
    // Right after a jump the media elements still report the old time for a moment.
    if (Math.abs(recording - ed.pending) < 0.4 || performance.now() - ed.pendingAt > 1500) ed.pending = null;
    else recording = ed.pending;
  }
  if (recording >= clip.out - 0.03 || (media && !studio.player.playing)) {
    const next = clips[now.index + 1];
    if (!next) { ed.t = edLength(edit); edPause(); edDraw(); edOverlay(); edClock(); return; }
    ed.t = next.at;
    studio.player.playing = true;
    ed.pending = next.in;
    ed.pendingAt = performance.now();
    seekProject(next.in);
  } else ed.t = clip.at + Math.max(0, recording - clip.in);
  edSyncAudio(false);
  edFollow();
  edDraw();
  edOverlay();
  edClock();
}
function edSyncAudio(force) {
  const project = studio.project, edit = project && project.edit;
  if (!edit) return;
  const wanted = new Set();
  for (const item of edit.audio) {
    wanted.add(item.id);
    let node = ed.audio[item.id];
    if (!node) { node = h("audio", { preload: "auto" }); node.src = projectMedia(project.path, "assets/" + item.asset); ed.audio[item.id] = node; }
    const local = ed.t - item.start, length = item.out - item.in;
    if (local < 0 || local >= length) { if (!node.paused) node.pause(); continue; }
    let volume = item.volume;
    if (item.fade_in > 0 && local < item.fade_in) volume *= local / item.fade_in;
    if (item.fade_out > 0 && length - local < item.fade_out) volume *= (length - local) / item.fade_out;
    node.volume = Math.max(0, Math.min(1, volume));
    const position = item.in + local;
    if (force || Math.abs(node.currentTime - position) > 0.2) setMediaTime(node, position);
    if (ed.playing && node.paused) playMedia(node);
    if (!ed.playing && !node.paused) node.pause();
  }
  for (const [id, node] of Object.entries(ed.audio)) if (!wanted.has(id)) { node.pause(); node.removeAttribute("src"); delete ed.audio[id]; }
}
function edClock() {
  const node = $("edClock"), edit = studio.project && studio.project.edit;
  if (node && edit) node.textContent = voiceClock(ed.t) + " / " + voiceClock(edLength(edit));
  const play = $("edPlay");
  if (play) { play.textContent = ""; play.append(studioIcon(ed.playing ? "pause" : "play")); }
}

// ---- the page ----
function renderEdit() {
  const box = $("studioEdit");
  if (!box) return;
  box.textContent = "";
  const project = studio.project;
  if (!project) { edPicker(box); return; }
  const edit = editOf(project);
  if (!edit) { box.append(h("div", { class: "empty", text: "This project has nothing recorded to edit." })); return; }
  const video = !audioOnly(project);
  const height = Number(localStorage.getItem("edit-timeline")) || 300;
  const root = h("div", { class: "editor" + (ed.busy ? " busy" : ""), style: "--tl:" + height + "px" });
  root.append(h("div", { class: "edbar" },
    h("button", { class: "ghost back", onclick: () => { edLeave(); closeProject().then(() => setStudioTab("projects")); } }, studioIcon("back"), "Projects"),
    h("b", { text: project.name }), h("span", { class: "where", text: clockText(edLength(edit)) + " of " + clockText(project.duration) }),
    h("span", { class: "spacer" }),
    iconButton("undo", "Undo (⌘Z; ⇧⌘Z redoes)", () => undoEdit(false)),
    h("button", { class: ed.snap ? "on" : "", title: "Snapping to the playhead, cuts and items (N)", text: "Snap", onclick: () => { ed.snap = !ed.snap; localStorage.setItem("edit-snap", ed.snap ? "on" : "off"); renderEdit(); } }),
    h("button", { title: "Fit the whole edit (⇧Z)", text: "Fit", onclick: () => { ed.zoom = 0; edDraw(); } }),
    video ? h("div", { class: "seg fmt" }, STUDIO_FORMATS.map(([value, label]) =>
      h("button", { class: studio.projectCanvas === value ? "on" : "", text: label, onclick: () => { studio.projectCanvas = value; renderEdit(); } }))) : null,
    h("button", { class: "primary", text: ed.busy === "export" ? "Preparing…" : "Export…", onclick: edExport })));
  root.append(h("div", { class: "pane edmedia", id: "edMedia" }));
  const view = h("div", { class: "edview" });
  if (video) {
    view.append(h("div", { class: "stagebox", id: "stageBox" }, stageFrame()));
  } else {
    view.append(h("div", { class: "stagebox" }, h("canvas", { class: "edwave", id: "edWave" }), h("div", { class: "edover", id: "edOver" })));
  }
  view.append(h("div", { class: "edtrans" },
    iconButton("back", "Back 5 s (J)", () => edSeek(ed.t - 5)),
    h("button", { id: "edPlay", class: "ib", title: "Play / pause (Space, K)", "aria-label": "Play / pause", onclick: edToggle }, studioIcon("play")),
    h("span", { class: "clock", id: "edClock" }),
    h("span", { class: "where", id: "edRange" }),
    h("span", { class: "spacer" }),
    h("span", { class: "where", text: "B cut · Del ripple delete · I/O range · ←/→ frame · ↑/↓ cuts · J/K/L · N snap" })));
  root.append(view, h("div", { class: "pane edinspect", id: "edInspect" }));
  const gutter = h("div", { class: "edgutter", title: "Drag to resize the timeline" });
  gutter.addEventListener("pointerdown", (event) => {
    const startY = event.clientY, start = height;
    const move = (moved) => {
      if (moved.buttons === 0) { up(); return; }
      const next = Math.max(180, Math.min(window.innerHeight - 300, start - (moved.clientY - startY)));
      root.style.setProperty("--tl", next + "px");
      localStorage.setItem("edit-timeline", String(Math.round(next)));
      edDraw();
    };
    const up = () => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); removeEventListener("pointercancel", up); };
    addEventListener("pointermove", move); addEventListener("pointerup", up); addEventListener("pointercancel", up);
  });
  const timeline = h("canvas", { id: "edTimeline", "aria-label": "Timeline" });
  root.append(gutter, h("div", { class: "edtl", id: "edTl" }, timeline));
  box.append(root);
  edTimelineEvents(timeline);
  if (video) {
    const wrap = $("stageWrap");
    if (wrap) wrap.append(h("div", { class: "edover", id: "edOver" }));
    watchStageSize();
    drawStage();
  }
  renderEditSide();
  edPeaks(project);
  for (const item of edit.audio) edAssetPeaks(project, item.asset);
  if (!studio.projects.length && !studio.projectsLoaded) loadProjects();
  edSeek(ed.t);
  if (typeof ResizeObserver !== "undefined") {
    if (ed.observer) ed.observer.disconnect();
    ed.observer = new ResizeObserver(() => { edDraw(); edOverlay(); });
    ed.observer.observe($("edTl"));
  }
  edScheduleAssets();
}

function edPicker(box) {
  box.append(h("div", { class: "projbar" }, h("b", { text: "Pick a project to edit" })));
  const grid = h("div", { class: "library edpick" });
  box.append(grid);
  if (!studio.projectsLoaded) loadProjects().then(() => state.view === "studio" && studio.tab === "edit" && !studio.project && renderEdit());
  if (!studio.projects.length) { grid.append(h("div", { class: "empty", text: "No projects yet. Record something on the Record tab." })); return; }
  for (const item of studio.projects.slice(0, 200)) {
    const card = projectCard(item);
    card.onclick = () => openEdit(item.path);
    grid.append(card);
  }
}

function renderEditSide() { edMediaPane(); edInspector(); }

function edMediaPane() {
  const box = $("edMedia"), project = studio.project;
  if (!box || !project || !project.edit) return;
  const edit = project.edit;
  box.textContent = "";
  box.append(h("h5", { text: "Add" }));
  const file = h("input", { type: "file", accept: "audio/*,.m4a,.mp3,.wav,.flac,.aac,.aiff,.caf", style: "display:none" });
  file.addEventListener("change", () => { if (file.files[0]) edImportFile(file.files[0]); file.value = ""; });
  box.append(file,
    h("button", { class: "wide", onclick: () => file.click() }, studioIcon("audio"), "Music or sound file…"),
    h("button", { class: "wide", onclick: (event) => edVoiceMenu(event.currentTarget) }, studioIcon("mic"), "Voice-over from an audio recording…"),
    h("button", { class: "wide", onclick: edAddText }, studioIcon("text"), "Text at the playhead (T)"));
  box.append(h("h5", { text: "Subtitles" }));
  const language = studioSelect(ED_LANGUAGES, ed.language, (value) => { ed.language = value; localStorage.setItem("edit-language", value); });
  box.append(h("div", { class: "row" }, language, h("button", { text: ed.busy === "transcribe" ? "Listening…" : edit.captions.length ? "Transcribe again" : "Transcribe", disabled: Boolean(ed.busy) || null, onclick: edTranscribe })));
  if (!edit.captions.length) box.append(h("p", { class: "note", style: "padding:0 10px", text: "Speech to text on this Mac (ul lm transcribe). Lines follow your cuts." }));
  const list = h("div", { class: "caplist" });
  const spans = new Map(captionSpans(edit).map((span) => [span.id, span]));
  for (const line of [...edit.captions].sort((a, b) => a.in - b.in)) {
    const span = spans.get(line.id);
    const input = h("input", { type: "text", value: line.text, maxlength: "500" });
    input.addEventListener("change", () => { const text = input.value.replace(/[\u0000-\u001f]/g, " ").trim(); if (!text) return; line.text = text.slice(0, 500); line.asset = ""; edChanged(); });
    input.addEventListener("focus", () => { ed.sel = { kind: "caption", id: line.id }; if (span) edSeek(span.start + 0.01); edInspector(); });
    list.append(h("div", { class: "cap" + (ed.sel && ed.sel.id === line.id ? " on" : "") + (span ? "" : " cut"), title: span ? "" : "Cut away by the edit" },
      h("span", { text: span ? clockText(span.start) : "cut", onclick: () => { ed.sel = { kind: "caption", id: line.id }; if (span) edSeek(span.start + 0.01); renderEditSide(); } }), input));
  }
  box.append(list);
  box.append(h("h5", { text: "Clean up" }),
    h("button", { class: "wide", disabled: !ed.peaks || null, title: "Cut every pause longer than 0.6 s from the recording (undo with ⌘Z)", onclick: edRemoveSilences }, studioIcon("minus"), "Remove silences"));
}

function edInspector() {
  const box = $("edInspect"), project = studio.project;
  if (!box || !project || !project.edit) return;
  const edit = project.edit, sel = ed.sel;
  box.textContent = "";
  const number = (value, onchange, step, min, max) => {
    const input = h("input", { type: "number", value: String(round3(value)), step: String(step || 0.1), min: String(min ?? 0), max: max === undefined ? null : String(max) });
    input.addEventListener("change", () => { const next = Number(input.value); if (Number.isFinite(next)) onchange(next); });
    return input;
  };
  if (sel && sel.kind === "clip") {
    const clip = edit.clips.find((item) => item.id === sel.id);
    if (clip) {
      box.append(h("h5", { text: "Clip" }),
        prow("From", number(clip.in, (value) => { if (value >= 0 && value < clip.out - 0.05) { clip.in = round3(value); edChanged(); } })),
        prow("To", number(clip.out, (value) => { if (value > clip.in + 0.05 && value <= project.duration) { clip.out = round3(value); edChanged(); } })),
        prow("Length", h("span", { text: clockText(clip.out - clip.in) })),
        h("div", { class: "row" }, h("button", { text: "Cut at playhead (B)", onclick: edBlade }), h("button", { class: "ghost", text: "Delete (ripple)", onclick: edDelete })));
      return;
    }
  }
  if (sel && sel.kind === "caption") {
    const line = edit.captions.find((item) => item.id === sel.id);
    if (line) {
      const area = h("textarea", { rows: "3", maxlength: "500" });
      area.value = line.text;
      area.addEventListener("change", () => { const text = area.value.replace(/[\u0000-\u001f]/g, " ").trim(); if (text) { line.text = text; line.asset = ""; edChanged(); edMediaPane(); } });
      box.append(h("h5", { text: "Subtitle line" }), area,
        prow("Start", number(line.in, (value) => { if (value < line.out - 0.05) { line.in = round3(value); line.asset = ""; edChanged(); } })),
        prow("End", number(line.out, (value) => { if (value > line.in + 0.05) { line.out = round3(value); edChanged(); } })),
        h("div", { class: "row" },
          h("button", { text: "Split at playhead", onclick: () => { if (splitCaption(edit, line.id, toRecording(edit, ed.t).t)) edChanged("all"); else toast("Put the playhead inside the line"); } }),
          h("button", { text: "Merge with next", onclick: () => { if (mergeCaption(edit, line.id)) edChanged("all"); } }),
          h("button", { class: "ghost", text: "Delete", onclick: edDelete })));
    }
  }
  if (sel && sel.kind === "text") {
    const item = edit.texts.find((entry) => entry.id === sel.id);
    if (item) {
      const area = h("textarea", { rows: "2", maxlength: "500" });
      area.value = item.text;
      area.addEventListener("change", () => { const text = area.value.replace(/[\u0000-\u0009\u000b-\u001f]/g, " ").trim(); if (text) { item.text = text.replace(/\n/g, " "); item.asset = ""; edChanged(); } });
      const color = h("input", { type: "color", value: item.color || "#ffffff" });
      color.addEventListener("change", () => { item.color = color.value; item.asset = ""; edChanged(); });
      const back = h("input", { type: "color", value: item.background || "#000000" });
      back.addEventListener("change", () => { item.background = back.value; item.asset = ""; edChanged(); });
      const slider = (key, label) => {
        const input = h("input", { type: "range", min: key === "w" ? "0.05" : "0", max: "1", step: "0.01", value: String(item[key]) });
        input.addEventListener("input", () => { item[key] = Number(input.value); edOverlay(); });
        input.addEventListener("change", () => edChanged());
        return prow(label, input);
      };
      box.append(h("h5", { text: "Text" }), area,
        prow("Colour", color), prow("Box", back, studioCheck(Boolean(item.background), (on) => { item.background = on ? back.value : ""; item.asset = ""; edChanged(); }, "show")),
        slider("x", "Across"), slider("y", "Down"), slider("w", "Width"),
        prow("Start", number(item.start, (value) => { if (value < item.end - 0.05) { item.start = round3(value); edChanged(); } })),
        prow("End", number(item.end, (value) => { if (value > item.start + 0.05) { item.end = round3(value); edChanged(); } })),
        h("button", { class: "ghost", text: "Delete", onclick: edDelete }));
      return;
    }
  }
  if (sel && sel.kind === "audio") {
    const item = edit.audio.find((entry) => entry.id === sel.id);
    if (item) {
      box.append(h("h5", { text: item.name }),
        prow("Volume", (() => { const input = h("input", { type: "range", min: "0", max: "2", step: "0.05", value: String(item.volume) });
          input.addEventListener("change", () => { item.volume = Number(input.value); edChanged(); }); return input; })()),
        prow("Fade in", number(item.fade_in, (value) => { item.fade_in = Math.max(0, Math.min(600, value)); edChanged(); })),
        prow("Fade out", number(item.fade_out, (value) => { item.fade_out = Math.max(0, Math.min(600, value)); edChanged(); })),
        prow("Starts at", number(item.start, (value) => { item.start = Math.max(0, round3(value)); edChanged(); })),
        prow("From", number(item.in, (value) => { if (value < item.out - 0.05) { item.in = round3(Math.max(0, value)); edChanged(); } })),
        prow("To", number(item.out, (value) => { if (value > item.in + 0.05) { item.out = round3(value); edChanged(); } })),
        h("button", { class: "ghost", text: "Delete", onclick: edDelete }));
      return;
    }
  }
  if (sel && sel.kind === "caption") box.append(h("hr"));
  const style = edit.caption_style;
  const restyle = () => { for (const line of edit.captions) line.asset = ""; edChanged(); };
  const color = h("input", { type: "color", value: style.color });
  color.addEventListener("change", () => { style.color = color.value; restyle(); });
  const outline = h("input", { type: "color", value: style.outline || "#000000" });
  outline.addEventListener("change", () => { style.outline = outline.value; restyle(); });
  const size = h("input", { type: "range", min: "24", max: "120", step: "2", value: String(style.size) });
  size.addEventListener("input", () => { style.size = Number(size.value); edOverlay(); });
  size.addEventListener("change", restyle);
  box.append(h("h5", { text: "Subtitle style" }),
    prow("Font", studioSelect(CAPTION_FONTS, style.font, (value) => { style.font = value; restyle(); })),
    prow("Size", size),
    prow("Colour", color),
    prow("Outline", outline, studioCheck(Boolean(style.outline), (on) => { style.outline = on ? outline.value : ""; restyle(); }, "on")),
    prow("Box", studioCheck(style.box, (on) => { style.box = on; restyle(); }, "dark box behind")),
    prow("Place", studioSelect([["bottom", "Bottom"], ["middle", "Middle"], ["top", "Top"]], style.position, (value) => { style.position = value; restyle(); })),
    h("p", { class: "note", text: "Exports burn the subtitles in and save a .srt next to the video." }));
}

// ---- viewer overlay: the caption and texts at the playhead, as the export draws them ----
function edOverlay() {
  const box = $("edOver"), project = studio.project, edit = project && project.edit;
  if (!box || !edit) return;
  box.textContent = "";
  const frame = box.getBoundingClientRect();
  const short = Math.min(frame.width, frame.height) || 1;
  const span = captionAt(edit, ed.t);
  if (span) {
    const style = edit.caption_style, scale = short / 1080;
    const node = h("div", { class: "ecap", text: span.text });
    node.style.fontFamily = ED_FONT_CSS[style.font] || "system-ui";
    node.style.fontSize = Math.max(8, style.size * scale) + "px";
    node.style.color = style.color;
    if (style.outline) node.style.textShadow = [[-1, -1], [1, -1], [-1, 1], [1, 1], [0, 2], [2, 0], [0, -2], [-2, 0]].map(([x, y]) => x * scale * 2.5 + "px " + y * scale * 2.5 + "px 0 " + style.outline).join(",");
    if (style.box) { node.style.background = "rgba(0,0,0,.62)"; node.style.padding = "0.15em 0.5em"; node.style.borderRadius = "0.25em"; }
    const margin = Math.round(short * 0.07);
    if (style.position === "top") node.style.top = margin + "px";
    else if (style.position === "middle") { node.style.top = "50%"; node.style.transform = "translate(-50%, -50%)"; }
    else node.style.bottom = margin + "px";
    box.append(node);
  }
  for (const item of edit.texts) {
    if (!(ed.t >= item.start && ed.t < item.end) || !item.asset) continue;
    const img = h("img", { src: projectMedia(project.path, "assets/" + item.asset), alt: "" });
    img.style.left = item.x * 100 + "%";
    img.style.top = item.y * 100 + "%";
    img.style.width = item.w * frame.width + "px";
    box.append(img);
  }
  if (!$("stage")) drawAudioWave();
}

// The viewer of an audio project: the sound around the playhead, Voice Memos style.
function drawAudioWave() {
  const canvas = $("edWave"), edit = studio.project && studio.project.edit;
  if (!canvas || !edit) return;
  const box = canvas.getBoundingClientRect(), ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(2, Math.round(box.width * ratio));
  canvas.height = Math.max(2, Math.round(box.height * ratio));
  const context = canvas.getContext("2d");
  const styles = getComputedStyle(document.body);
  context.scale(ratio, ratio);
  context.clearRect(0, 0, box.width, box.height);
  const middle = box.height / 2, span = 8, pps = box.width / span;
  context.fillStyle = styles.getPropertyValue("--muted") || "#888";
  for (let x = 0; x < box.width; x += 3) {
    const t = ed.t + (x - box.width / 2) / pps;
    if (t < 0 || t > edLength(edit)) continue;
    const at = toRecording(edit, t).t;
    const value = ed.peaks ? ed.peaks[Math.floor(at * ED_RATE)] || 0 : 0;
    const height = Math.max(1.5, value * (box.height * 0.42));
    context.globalAlpha = t <= ed.t ? 1 : 0.45;
    context.fillRect(x, middle - height, 2, height * 2);
  }
  context.globalAlpha = 1;
  context.fillStyle = "#ff3b30";
  context.fillRect(Math.round(box.width / 2) - 1, 8, 2, box.height - 16);
}

// ---- timeline drawing ----
function edGeometry(canvas) {
  const edit = studio.project.edit;
  const width = canvas.clientWidth, length = Math.max(1, edLength(edit), ...edit.texts.map((item) => item.end), ...edit.audio.map((item) => item.start + item.out - item.in));
  if (!ed.zoom) { ed.zoom = Math.max(0.5, (width - ED_LABEL - 20) / length); ed.scroll = 0; }
  const rows = {};
  let y = ED_RULER;
  for (const [key, height, label] of ED_ROWS) { rows[key] = { y, height, label }; y += height + 4; }
  return { width, length, rows, x: (t) => ED_LABEL + (t - ed.scroll) * ed.zoom, t: (x) => (x - ED_LABEL) / ed.zoom + ed.scroll };
}
function edDraw() {
  cancelAnimationFrame(ed.drawTimer);
  ed.drawTimer = requestAnimationFrame(edPaint);
  if (!$("stage")) drawAudioWave();
}
function edPaint() {
  const canvas = $("edTimeline"), project = studio.project, edit = project && project.edit;
  if (!canvas || !edit) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(2, Math.round(canvas.clientWidth * ratio));
  canvas.height = Math.max(2, Math.round(canvas.clientHeight * ratio));
  const g = edGeometry(canvas), c = canvas.getContext("2d");
  const css = getComputedStyle(document.body), v = (name, fallback) => (css.getPropertyValue(name) || "").trim() || fallback;
  const ink = v("--ink", "#ddd"), muted = v("--muted", "#888"), line = v("--line", "#333"), accent = v("--accent", "#ffc933"), energy = v("--energy", "#ff8a1f");
  c.scale(ratio, ratio);
  c.clearRect(0, 0, g.width, canvas.clientHeight);
  c.font = "11px system-ui, sans-serif";
  c.textBaseline = "middle";
  // ruler
  const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
  const step = steps.find((value) => value * ed.zoom >= 70) || 600;
  c.fillStyle = muted;
  c.strokeStyle = line;
  for (let t = Math.floor(ed.scroll / step) * step; g.x(t) < g.width; t += step) {
    const x = g.x(t);
    if (x < ED_LABEL) continue;
    c.fillRect(x, 14, 1, 10);
    c.fillText(clockText(t) + (step < 1 ? "." + Math.round((t % 1) * 10) : ""), x + 3, 9);
  }
  // in/out range
  if (ed.in !== null || ed.out !== null) {
    const a = g.x(ed.in ?? 0), b = g.x(ed.out ?? edLength(edit));
    c.fillStyle = "rgba(120,170,255,.16)";
    c.fillRect(Math.max(ED_LABEL, a), 0, Math.max(0, b - Math.max(ED_LABEL, a)), canvas.clientHeight);
  }
  const label = (key, text) => { c.fillStyle = muted; c.fillText(text, 10, g.rows[key].y + g.rows[key].height / 2); };
  const selected = (kind, id) => ed.sel && ed.sel.kind === kind && ed.sel.id === id;
  const block = (x1, x2, row, fill, chosen) => {
    const left = Math.max(ED_LABEL, x1), right = Math.min(g.width, x2);
    if (right <= left) return null;
    c.fillStyle = fill;
    c.beginPath();
    c.roundRect(left, row.y + 1, right - left - 1, row.height - 2, 5);
    c.fill();
    if (chosen) { c.strokeStyle = ink; c.lineWidth = 2; c.stroke(); c.lineWidth = 1; }
    return [left, right];
  };
  // text row
  label("text", "Text");
  for (const item of edit.texts) {
    const span = block(g.x(item.start), g.x(item.end), g.rows.text, "rgba(160,120,255,.55)", selected("text", item.id));
    if (span) { c.save(); c.beginPath(); c.rect(span[0], g.rows.text.y, span[1] - span[0], g.rows.text.height); c.clip(); c.fillStyle = ink; c.fillText(item.text, span[0] + 6, g.rows.text.y + g.rows.text.height / 2); c.restore(); }
  }
  // subtitles row
  label("subs", "Subtitles");
  for (const span of captionSpans(edit)) {
    const box = block(g.x(span.start), g.x(span.end), g.rows.subs, "rgba(90,180,140,.55)", selected("caption", span.id));
    if (box) { c.save(); c.beginPath(); c.rect(box[0], g.rows.subs.y, box[1] - box[0], g.rows.subs.height); c.clip(); c.fillStyle = ink; c.fillText(span.text, box[0] + 5, g.rows.subs.y + g.rows.subs.height / 2); c.restore(); }
  }
  // the recording: clips with scenes and their sound
  const main = g.rows.main;
  label("main", audioOnly(project) ? "Recording" : "Video + sound");
  for (const clip of edClips(edit)) {
    const length = clip.out - clip.in;
    const box = block(g.x(clip.at), g.x(clip.at + length), main, "color-mix(in srgb, " + accent + " 26%, transparent)", selected("clip", clip.id));
    if (!box) continue;
    c.save();
    c.beginPath();
    c.rect(box[0], main.y, box[1] - box[0], main.height);
    c.clip();
    c.fillStyle = ink;
    c.fillText(audioOnly(project) ? clockText(clip.in) : sceneName(sceneAt(project, clip.in)) + " · " + clockText(clip.in), box[0] + 6, main.y + 11);
    if (ed.peaks) {
      c.fillStyle = accent;
      const middle = main.y + main.height * 0.62, scale = main.height * 0.3;
      for (let x = box[0]; x < box[1]; x += 2) {
        const at = clip.in + (g.t(x) - clip.at);
        const value = ed.peaks[Math.floor(at * ED_RATE)] || 0;
        const height = Math.max(0.5, value * scale);
        c.fillRect(x, middle - height, 1.5, height * 2);
      }
    }
    c.restore();
  }
  // music and voice-over
  label("music", "Music & voice");
  for (const item of edit.audio) {
    const length = item.out - item.in;
    const box = block(g.x(item.start), g.x(item.start + length), g.rows.music, "rgba(80,150,255,.35)", selected("audio", item.id));
    if (!box) continue;
    c.save(); c.beginPath(); c.rect(box[0], g.rows.music.y, box[1] - box[0], g.rows.music.height); c.clip();
    const wave = ed.assetPeaks[item.asset];
    if (wave && wave.peaks.length && wave.duration) {
      c.fillStyle = "rgba(140,190,255,.9)";
      const middle = g.rows.music.y + g.rows.music.height * 0.6, scale = g.rows.music.height * 0.32;
      for (let x = box[0]; x < box[1]; x += 2) {
        const at = item.in + (g.t(x) - item.start);
        const value = wave.peaks[Math.floor(at / wave.duration * wave.peaks.length)] || 0;
        const height = Math.max(0.5, value * scale * item.volume);
        c.fillRect(x, middle - height, 1.5, height * 2);
      }
    }
    c.fillStyle = ink;
    c.fillText(item.name, box[0] + 6, g.rows.music.y + 10);
    c.restore();
  }
  // playhead
  const x = g.x(ed.t);
  if (x >= ED_LABEL) { c.fillStyle = energy; c.fillRect(Math.round(x) - 1, 0, 2, canvas.clientHeight); c.beginPath(); c.moveTo(x - 6, 0); c.lineTo(x + 6, 0); c.lineTo(x, 9); c.fill(); }
  const range = $("edRange");
  if (range) range.textContent = ed.in !== null || ed.out !== null ? "In " + clockText(ed.in ?? 0) + " · Out " + clockText(ed.out ?? edLength(edit)) + " (Del removes the range, X clears)" : "";
}
function edFollow() {
  const canvas = $("edTimeline");
  if (!canvas || !ed.zoom) return;
  const visible = (canvas.clientWidth - ED_LABEL) / ed.zoom;
  if (ed.t > ed.scroll + visible * 0.92 || ed.t < ed.scroll) ed.scroll = Math.max(0, ed.t - visible * 0.1);
}

// ---- timeline pointer: select, trim the edges, move items, scrub ----
function edHit(g, x, y) {
  const edit = studio.project.edit;
  const row = Object.entries(g.rows).find(([, item]) => y >= item.y && y < item.y + item.height);
  if (!row || x < ED_LABEL) return { kind: y < ED_RULER ? "ruler" : "none" };
  const [key] = row, t = g.t(x), edge = 7 / ed.zoom;
  const pick = (items, start, end, kind) => {
    for (const item of items) {
      const a = start(item), b = end(item);
      if (t >= a - edge && t <= b + edge) return { kind, id: item.id, side: Math.abs(t - a) <= edge ? "start" : Math.abs(t - b) <= edge ? "end" : "body", item };
    }
    return null;
  };
  if (key === "main") return pick(edClips(edit), (clip) => clip.at, (clip) => clip.at + clip.out - clip.in, "clip") || { kind: "none" };
  if (key === "text") return pick(edit.texts, (item) => item.start, (item) => item.end, "text") || { kind: "none" };
  if (key === "music") return pick(edit.audio, (item) => item.start, (item) => item.start + item.out - item.in, "audio") || { kind: "none" };
  const spans = captionSpans(edit);
  const found = pick(spans, (span) => span.start, (span) => span.end, "caption");
  return found ? { ...found, item: edit.captions.find((line) => line.id === found.id) } : { kind: "none" };
}
function edTimelineEvents(canvas) {
  canvas.addEventListener("wheel", (event) => {
    if (!studio.project || !studio.project.edit) return;
    event.preventDefault();
    const g = edGeometry(canvas), box = canvas.getBoundingClientRect();
    if (event.ctrlKey || event.metaKey) {
      const at = g.t(event.clientX - box.left);
      ed.zoom = Math.max(0.2, Math.min(800, ed.zoom * Math.exp(-event.deltaY * 0.01)));
      ed.scroll = Math.max(0, at - (event.clientX - box.left - ED_LABEL) / ed.zoom);
    } else ed.scroll = Math.max(0, ed.scroll + (event.deltaX || event.deltaY) / ed.zoom);
    edDraw();
  }, { passive: false });
  canvas.addEventListener("pointermove", (event) => {
    if (ed.drag || !studio.project) return;
    const g = edGeometry(canvas), box = canvas.getBoundingClientRect();
    const hit = edHit(g, event.clientX - box.left, event.clientY - box.top);
    canvas.style.cursor = hit.side === "start" || hit.side === "end" ? "ew-resize" : hit.kind !== "none" && hit.kind !== "ruler" && hit.kind !== "clip" ? "grab" : "default";
  });
  canvas.addEventListener("pointerdown", (event) => {
    const project = studio.project, edit = project && project.edit;
    if (!edit || event.button !== 0) return;
    const g = edGeometry(canvas), box = canvas.getBoundingClientRect();
    const x0 = event.clientX - box.left, hit = edHit(g, x0, event.clientY - box.top);
    const before = JSON.stringify(edit);
    const targets = () => ed.snap ? [ed.t, ...edEdges(edit), ...(project.events || []).filter((item) => "mark" in item).map((item) => toOutput(edit, item.t)).filter((t) => t !== null)] : [];
    const snapped = (t) => snapTime(t, targets(), 8 / ed.zoom);
    if (hit.kind === "ruler" || hit.kind === "none") {
      ed.sel = null;
      edSeek(g.t(x0));
      renderEditSide();
    } else {
      ed.sel = { kind: hit.kind, id: hit.id };
      if (hit.side === "body" && hit.kind === "clip") edSeek(g.t(x0));
      renderEditSide();
    }
    const original = hit.item ? JSON.parse(JSON.stringify(hit.item)) : null;
    const start = g.t(x0);
    ed.drag = true;
    const move = (moved) => {
      if (moved.buttons === 0) { up(); return; }
      const t = g.t(moved.clientX - box.left), delta = t - start;
      if (hit.kind === "ruler" || hit.kind === "none" || (hit.kind === "clip" && hit.side === "body")) { edSeek(t); return; }
      const item = hit.item;
      if (hit.kind === "clip") {
        // Ripple trim: the clip's in or out moves; everything after it slides.
        if (hit.side === "start") item.in = round3(Math.max(0, Math.min(original.out - 0.05, original.in + delta)));
        else item.out = round3(Math.min(project.duration, Math.max(original.in + 0.05, original.out + delta)));
      } else if (hit.kind === "text") {
        if (hit.side === "start") item.start = round3(Math.max(0, Math.min(original.end - 0.05, snapped(original.start + delta))));
        else if (hit.side === "end") item.end = round3(Math.max(original.start + 0.05, snapped(original.end + delta)));
        else { const length = original.end - original.start; item.start = round3(Math.max(0, snapped(original.start + delta))); item.end = round3(item.start + length); }
      } else if (hit.kind === "audio") {
        if (hit.side === "start") { const shift = Math.max(-original.in, Math.min(original.out - original.in - 0.05, snapped(original.start + delta) - original.start)); item.start = round3(original.start + shift); item.in = round3(original.in + shift); }
        else if (hit.side === "end") item.out = round3(Math.max(original.in + 0.05, original.out + delta));
        else item.start = round3(Math.max(0, snapped(original.start + delta)));
      } else if (hit.kind === "caption") {
        // A line moves on the recording's clock (it stays with the words it belongs to).
        if (hit.side === "start") item.in = round3(Math.max(0, Math.min(original.out - 0.05, original.in + delta)));
        else if (hit.side === "end") item.out = round3(Math.min(project.duration, Math.max(original.in + 0.05, original.out + delta)));
        else { item.in = round3(Math.max(0, original.in + delta)); item.out = round3(item.in + original.out - original.in); }
      }
      edDraw();
      edOverlay();
    };
    const up = () => {
      removeEventListener("pointermove", move);
      removeEventListener("pointerup", up);
      removeEventListener("pointercancel", up);
      ed.drag = null;
      if (JSON.stringify(edit) !== before) edChanged();
    };
    addEventListener("pointermove", move);
    addEventListener("pointerup", up);
    addEventListener("pointercancel", up);
  });
}

// ---- actions ----
function edBlade() {
  const edit = studio.project && studio.project.edit;
  if (!edit) return;
  if (bladeAt(edit, ed.t)) { edChanged(); toast("Cut at " + clockText(ed.t)); } else toast("Move the playhead inside a clip to cut");
}
function edDelete() {
  const edit = studio.project && studio.project.edit;
  if (!edit) return;
  if (ed.in !== null || ed.out !== null) {
    if (deleteRange(edit, ed.in ?? 0, ed.out ?? edLength(edit))) { ed.t = ed.in ?? 0; ed.in = ed.out = null; edChanged("all"); edSeek(ed.t); }
    return;
  }
  const sel = ed.sel;
  if (!sel) { toast("Select something to delete, or mark a range with I and O"); return; }
  if (sel.kind === "clip") {
    const index = edit.clips.findIndex((clip) => clip.id === sel.id);
    if (!rippleDelete(edit, index)) { toast("The last clip stays"); return; }
  } else if (sel.kind === "caption") edit.captions = edit.captions.filter((line) => line.id !== sel.id);
  else if (sel.kind === "text") edit.texts = edit.texts.filter((item) => item.id !== sel.id);
  else if (sel.kind === "audio") edit.audio = edit.audio.filter((item) => item.id !== sel.id);
  ed.sel = null;
  edChanged("all");
  edSeek(ed.t);
}
function edEdgeJump(direction) {
  const edit = studio.project.edit;
  const edges = [...new Set(edEdges(edit).map(round3))].sort((a, b) => a - b);
  const next = direction > 0 ? edges.find((t) => t > ed.t + 0.01) : [...edges].reverse().find((t) => t < ed.t - 0.01);
  if (next !== undefined) edSeek(next);
}
function edRemoveSilences() {
  const project = studio.project, edit = project && project.edit;
  if (!edit || !ed.peaks) return;
  const found = silences(ed.peaks, ED_RATE, 0.12, 0.6, 0.12);
  if (!found.length) { toast("No pauses longer than 0.6 s"); return; }
  const before = edLength(edit), kept = JSON.stringify(edit.clips);
  if (!subtractRanges(edit, found)) { toast("That would cut everything"); return; }
  if (before - edLength(edit) < 0.05) { edit.clips = JSON.parse(kept); toast("No pauses longer than 0.6 s left"); return; }
  edChanged("all");
  toast("Removed " + clockText(before - edLength(edit)) + " of pauses (⌘Z brings them back)");
}
function edAddText() {
  const edit = studio.project && studio.project.edit;
  if (!edit) return;
  if (edit.texts.length >= 500) { toast("At most 500 texts"); return; }
  const item = { id: edId(edit.texts, "t"), start: round3(ed.t), end: round3(Math.min(Math.max(ed.t + 3, 1), Math.max(edLength(edit), ed.t + 3))), text: "Title", asset: "", x: 0.5, y: 0.2, w: 0.4, color: "#ffffff", background: "" };
  edit.texts.push(item);
  ed.sel = { kind: "text", id: item.id };
  edChanged();
}
async function edTranscribe() {
  const project = studio.project, edit = project && project.edit;
  if (!edit || ed.busy) return;
  if (edit.captions.length && !confirm("Replace the " + edit.captions.length + " subtitle lines with a new transcription?")) return;
  ed.busy = "transcribe";
  edMediaPane();
  toast("Listening to the recording on this Mac… (a long recording takes a few minutes)");
  const { status, data } = await api("POST", "/api/studio/transcribe", { path: project.path, language: ed.language });
  ed.busy = "";
  if (studio.project !== project) return;
  if (status !== 200) { toast(data.error || "Transcription failed"); edMediaPane(); return; }
  edit.captions = captionsFrom(data.captions || []);
  toast(edit.captions.length ? edit.captions.length + " subtitle lines" + (data.language ? " (" + data.language + ")" : "") : "No speech found");
  edChanged("all");
}
async function edImportFile(file) {
  const project = studio.project, edit = project && project.edit;
  if (!edit) return;
  if (edit.audio.length >= 200) { toast("At most 200 sound clips"); return; }
  ed.busy = "upload";
  toast("Adding " + file.name + "…");
  let response, data = {};
  try {
    response = await fetch("/api/studio/project/asset?path=" + encodeURIComponent(project.path) + "&name=" + encodeURIComponent(file.name), { method: "POST", headers: { "X-Desk-Token": TOKEN }, body: file });
    data = await response.json();
  } catch (error) { data = { error: "Could not reach the desk: " + error.message }; }
  ed.busy = "";
  if (!response || response.status !== 200) { toast(data.error || "Upload failed"); return; }
  await edAddSound(data.asset, file.name.replace(/\.[^.]+$/, ""));
}
function edVoiceMenu(anchor) {
  const project = studio.project;
  const voices = studio.projects.filter((item) => item.path !== project.path && !item.tracks.includes("screen") && !item.tracks.includes("camera") && item.tracks.includes("mic"));
  if (!voices.length) { toast("Record one with “Record audio only” (A) on the Record tab, then add it here"); return; }
  openStudioMenu(anchor, voices.slice(0, 30).map((item) => h("button", { onclick: () => { closeStudioMenu(); edVoiceOver(item); } }, studioIcon("mic"), item.name + " · " + clockText(item.duration))));
}
async function edVoiceOver(item) {
  const { status, data } = await api("GET", "/api/studio/project?path=" + encodeURIComponent(item.path));
  if (status !== 200) { toast(data.error || "Could not read that recording"); return; }
  const files = soundFiles(data);
  if (!files.length) { toast("That recording has no sound"); return; }
  const copied = await api("POST", "/api/studio/project/import", { path: studio.project.path, from: item.path, file: files[0].file });
  if (copied.status !== 200) { toast(copied.data.error || "Could not copy the voice-over"); return; }
  await edAddSound(copied.data.asset, "Voice " + item.name.replace(/^audio-/, ""));
}
async function edAddSound(asset, name) {
  const project = studio.project, edit = project.edit;
  ed.assetPeaks[asset] = null;
  delete ed.assetPeaks[asset];
  await edAssetPeaks(project, asset);
  const duration = (ed.assetPeaks[asset] && ed.assetPeaks[asset].duration) || 10;
  const item = { id: edId(edit.audio, "m"), asset, name: name.slice(0, 200) || "Sound", start: round3(ed.t), in: 0, out: round3(duration), volume: 1, fade_in: 0, fade_out: 0 };
  edit.audio.push(item);
  ed.sel = { kind: "audio", id: item.id };
  edChanged();
}

// ---- drawing captions and texts for the export (PNG into the project's assets/) ----
function edDrawText(text, options) {
  const scale = 2, size = options.size * scale;
  const measure = document.createElement("canvas").getContext("2d");
  const font = "700 " + size + "px " + (ED_FONT_CSS[options.font] || "system-ui");
  measure.font = font;
  const limit = options.wrap * scale, words = text.split(/\s+/), lines = [];
  let current = "";
  for (const word of words) {
    const next = current ? current + " " + word : word;
    if (current && measure.measureText(next).width > limit) { lines.push(current); current = word; } else current = next;
  }
  if (current) lines.push(current);
  const pad = Math.round(size * (options.box ? 0.35 : 0.18)), lineHeight = Math.round(size * 1.22), stroke = options.outline ? Math.max(2, Math.round(size * 0.12)) : 0;
  const width = Math.ceil(Math.max(...lines.map((line) => measure.measureText(line).width))) + pad * 2 + stroke * 2;
  const height = lineHeight * lines.length + pad * 2 + stroke * 2;
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(2, width);
  canvas.height = Math.max(2, height);
  const c = canvas.getContext("2d");
  if (options.box) { c.fillStyle = typeof options.box === "string" ? options.box : "rgba(0,0,0,0.62)"; c.beginPath(); c.roundRect(0, 0, canvas.width, canvas.height, Math.round(size * 0.25)); c.fill(); }
  c.font = font;
  c.textAlign = "center";
  c.textBaseline = "middle";
  c.lineJoin = "round";
  lines.forEach((line, index) => {
    const y = pad + stroke + lineHeight * (index + 0.5);
    if (stroke) { c.strokeStyle = options.outline; c.lineWidth = stroke * 2; c.strokeText(line, canvas.width / 2, y); }
    c.fillStyle = options.color;
    c.fillText(line, canvas.width / 2, y);
  });
  return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
}
async function edUpload(project, name, blob) {
  try {
    const response = await fetch("/api/studio/project/asset?path=" + encodeURIComponent(project.path) + "&name=" + encodeURIComponent(name), { method: "POST", headers: { "X-Desk-Token": TOKEN }, body: blob });
    const data = await response.json();
    return response.status === 200 ? data.asset : null;
  } catch (error) { return null; }
}
// Every caption and text has a current PNG; returns false when one could not be drawn.
async function edEnsureAssets() {
  const project = studio.project, edit = project && project.edit;
  if (!edit) return true;
  let changed = false, ok = true;
  const style = edit.caption_style;
  for (const line of edit.captions) {
    const name = captionAssetName(line.text, style);
    if (line.asset === name || (line.asset && line.asset.startsWith(name.slice(0, -4) + " "))) continue;
    const blob = await edDrawText(line.text, { size: style.size, font: style.font, color: style.color, outline: style.outline, box: style.box, wrap: 900 });
    const asset = blob && await edUpload(project, name, blob);
    if (studio.project !== project) return false;
    if (asset) { line.asset = asset; changed = true; } else ok = false;
  }
  for (const item of edit.texts) {
    const name = textAssetName(item);
    if (item.asset === name || (item.asset && item.asset.startsWith(name.slice(0, -4) + " "))) continue;
    const blob = await edDrawText(item.text, { size: 120, font: "system-ui", color: item.color || "#ffffff", outline: "", box: item.background || false, wrap: 4000 });
    const asset = blob && await edUpload(project, name, blob);
    if (studio.project !== project) return false;
    if (asset) { item.asset = asset; changed = true; } else ok = false;
  }
  if (changed) { studio.historyLast = JSON.stringify(project); saveProjectSoon(); edOverlay(); }
  return ok;
}
function edScheduleAssets() {
  clearTimeout(ed.assetTimer);
  ed.assetTimer = setTimeout(edEnsureAssets, 1200);
}
async function edExport() {
  const project = studio.project;
  if (!project || ed.busy) return;
  ed.busy = "export";
  renderEdit();
  const ok = await edEnsureAssets();
  if (studio.projectTimer) await flushProject();
  ed.busy = "";
  renderEdit();
  if (!ok) { toast("Some subtitles or texts could not be drawn; try again"); return; }
  renderExportDialog(project);
}

// ---- keys (Resolve's) ----
function editKeydown(event) {
  const edit = studio.project && studio.project.edit;
  if (!edit) return false;
  if (event.key === "Escape" && studio.menu) { closeStudioMenu(); return true; }
  const meta = event.metaKey || event.ctrlKey;
  const frame = 1 / 30;
  if (meta && (event.code === "Equal" || event.code === "Minus")) { ed.zoom = Math.max(0.2, Math.min(800, ed.zoom * (event.code === "Equal" ? 1.5 : 1 / 1.5))); edDraw(); return true; }
  if (meta && event.code === "KeyB") { edBlade(); return true; }
  if (meta || event.altKey) return false;
  switch (event.code) {
    case "Space": case "KeyK": if (event.code === "KeyK" && !ed.playing) return true; edToggle(); return true;
    case "KeyL": if (!ed.playing) edPlay(); return true;
    case "KeyJ": edSeek(ed.t - 5); return true;
    case "ArrowLeft": edSeek(ed.t - (event.shiftKey ? 1 : frame)); return true;
    case "ArrowRight": edSeek(ed.t + (event.shiftKey ? 1 : frame)); return true;
    case "ArrowUp": edEdgeJump(-1); return true;
    case "ArrowDown": edEdgeJump(1); return true;
    case "Home": edSeek(0); return true;
    case "End": edSeek(edLength(edit)); return true;
    case "KeyB": edBlade(); return true;
    case "Delete": case "Backspace": edDelete(); return true;
    case "KeyI": ed.in = round3(ed.t); if (ed.out !== null && ed.out <= ed.in) ed.out = null; edDraw(); return true;
    case "KeyO": ed.out = round3(ed.t); if (ed.in !== null && ed.in >= ed.out) ed.in = null; edDraw(); return true;
    case "KeyX": ed.in = ed.out = null; edDraw(); return true;
    case "KeyN": ed.snap = !ed.snap; localStorage.setItem("edit-snap", ed.snap ? "on" : "off"); renderEdit(); toast(ed.snap ? "Snapping on" : "Snapping off"); return true;
    case "KeyZ": if (event.shiftKey) { ed.zoom = 0; edDraw(); return true; } return false;
    case "KeyT": edAddText(); return true;
    case "Escape": ed.sel = null; renderEditSide(); edDraw(); return true;
    default: return false;
  }
}

// ---- Projects tab: an audio project shows its sound, not a video stage ----
function renderAudioProject(box) {
  const project = studio.project;
  const canvas = h("canvas", { id: "audioWave", "aria-label": "Sound of the recording" });
  canvas.addEventListener("pointerdown", (event) => {
    const rect = canvas.getBoundingClientRect();
    seekProject(Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * project.duration);
    drawAudioView();
  });
  const seek = h("input", { type: "range", id: "projSeek", min: "0", max: String(project.duration), step: "0.01", value: "0" });
  seek.addEventListener("input", () => { seekProject(Number(seek.value)); drawAudioView(); });
  box.append(h("div", { class: "audioview" }, canvas,
    h("div", { class: "player" }, h("button", { id: "projPlay", title: "Play / pause", "aria-label": "Play / pause", onclick: () => { toggleProjectPlay(); drawAudioView(); } }, studioIcon("play")), seek, h("span", { class: "where", id: "projTime" }))));
  edPeaks(project);
  clearInterval(ed.audioTimer);
  ed.audioTimer = setInterval(() => { if (!$("audioWave")) { clearInterval(ed.audioTimer); return; } if (studio.player && studio.player.playing) drawAudioView(); }, 80);
  requestAnimationFrame(drawAudioView);
}
function drawAudioView() {
  const canvas = $("audioWave"), project = studio.project;
  if (!canvas || !project) return;
  const box = canvas.getBoundingClientRect(), ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(2, Math.round(box.width * ratio));
  canvas.height = Math.max(2, Math.round(box.height * ratio));
  const c = canvas.getContext("2d"), css = getComputedStyle(document.body);
  c.scale(ratio, ratio);
  const ink = (css.getPropertyValue("--ink") || "#ddd").trim() || "#ddd", muted = (css.getPropertyValue("--muted") || "#888").trim() || "#888";
  const t = studio.player ? studio.player.t : 0, middle = box.height / 2 + 6;
  c.font = "600 12px system-ui, sans-serif";
  c.fillStyle = muted;
  c.fillText(project.name, 14, 20);
  c.font = "600 26px ui-monospace, Menlo, monospace";
  c.fillStyle = ink;
  c.textAlign = "right";
  c.fillText(voiceClock(t), box.width - 14, 30);
  c.textAlign = "left";
  const peaks = ed.peaksFor === project.path ? ed.peaks : null;
  if (!peaks) { c.fillStyle = muted; c.font = "12px system-ui"; c.fillText("Reading the sound…", 14, middle); return; }
  const columns = Math.floor((box.width - 28) / 3), span = project.duration / Math.max(1, columns);
  for (let i = 0; i < columns; i++) {
    let value = 0;
    const from = Math.floor(i * span * ED_RATE), to = Math.max(from + 1, Math.floor((i + 1) * span * ED_RATE));
    for (let j = from; j < to && j < peaks.length; j++) value = Math.max(value, peaks[j]);
    const height = Math.max(1, value * (box.height * 0.36));
    c.fillStyle = i * span <= t ? ink : muted;
    c.globalAlpha = i * span <= t ? 1 : 0.55;
    c.fillRect(14 + i * 3, middle - height, 2, height * 2);
  }
  c.globalAlpha = 1;
  c.fillStyle = "#ff3b30";
  c.fillRect(14 + (t / Math.max(0.001, project.duration)) * (box.width - 28) - 1, 44, 2, box.height - 56);
  drawPlayerClock();
}
"""
