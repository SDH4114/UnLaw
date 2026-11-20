"""The Studio's Edit tab for `ul desk`: a track timeline in vanilla JS (no framework, no build step).

It works like DaVinci Resolve and Premiere Pro: video, audio, text and subtitle tracks the user adds and
names, linked picture and sound clips that can be cut apart (Alt-click), lift and ripple delete, a blade
tool, trims bound by the source, snapping, mute/solo/lock. The edit lives in project.json under `edit`
(capture_project.validate_edit, version 2); recorded files are never changed.

Playback: Web Audio plays every sound clip sample-exact and is the clock; the video elements follow it (a
browser that cannot decode a big screen recording in time only drops frames, the voice never stutters).
Light copies from `ul capture proxy` are played when ready. Captions and texts are drawn here to PNG and
uploaded into the project's assets/, because the export burns them in with ffmpeg's overlay filter.
"""

EDIT_CSS = r""".editor { display: grid; grid-template-columns: var(--pool, 250px) 6px minmax(260px, 1fr) 6px var(--insp, 290px);
  grid-template-rows: auto minmax(150px, 1fr) 6px var(--tl, 330px); height: calc(100vh - 150px); min-height: 560px; }
.editor .edbar { grid-column: 1 / -1; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding-bottom: 6px; }
.editor .edbar b { font-size: 13px; }
.editor .edbar .tools { display: inline-flex; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.editor .edbar .tools button { border: 0; border-radius: 0; display: inline-flex; align-items: center; gap: 4px; }
.editor .edbar .tools button.on, .editor .edbar button.on { background: var(--accent); color: var(--on-accent); }
.editor .edbar > button { display: inline-flex; align-items: center; gap: 4px; }
.editor .pane { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: auto; min-height: 0; min-width: 0; }
.editor .pane h5 { margin: 0; padding: 8px 10px 6px; font-size: 10px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.editor .edpool { grid-column: 1; grid-row: 2; padding-bottom: 8px; }
.editor .edinspect { grid-column: 5; grid-row: 2; padding-bottom: 8px; }
.editor .edinspect textarea { width: calc(100% - 20px); margin: 0 10px 6px; box-sizing: border-box; }
.editor .edview { grid-column: 3; grid-row: 2; display: flex; flex-direction: column; gap: 6px; min-height: 0; min-width: 0; }
.editor .vg { grid-row: 2; cursor: col-resize; border-radius: 3px; }
.editor .vg.left { grid-column: 2; } .editor .vg.right { grid-column: 4; }
.editor .hg { grid-column: 1 / -1; grid-row: 3; cursor: row-resize; border-radius: 3px; }
.editor .vg:hover, .editor .hg:hover { background: var(--line); }
.editor .edpool .row, .editor .edinspect .row, .editor .edinspect .prow { padding: 3px 10px; }
.editor .edinspect .row { display: flex; flex-wrap: wrap; gap: 4px; }
.editor .media { display: flex; align-items: center; gap: 8px; margin: 3px 8px; padding: 6px 8px; border: 1px solid var(--line); border-radius: 7px; cursor: grab; background: var(--bg); }
.editor .media .ico { flex: none; }
.editor .media span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.editor .media button { padding: 2px 7px; font-size: 11px; }
.editor .edpool button.wide { display: flex; align-items: center; gap: 6px; width: calc(100% - 16px); margin: 3px 8px; }
.editor .note { padding: 0 10px; font-size: 11px; color: var(--muted); }
.editor .caplist { display: flex; flex-direction: column; gap: 2px; padding: 0 6px; }
.editor .caplist .cap { display: grid; grid-template-columns: 54px 1fr; gap: 6px; align-items: center; padding: 3px 4px; border-radius: 5px; }
.editor .caplist .cap.on { background: color-mix(in srgb, var(--accent) 22%, transparent); }
.editor .caplist .cap span { font: 11px ui-monospace, monospace; color: var(--muted); cursor: pointer; }
.editor .caplist .cap input { width: 100%; min-width: 0; font-size: 12px; }
.editor .edview .stagebox { flex: 1; min-height: 0; position: relative; container-type: size; display: grid; place-items: center; }
.editor .stageui { display: none; }
.editor .stage { pointer-events: none; }
.editor .edview canvas.edwave { position: absolute; inset: 0; width: 100%; height: 100%; display: block; border-radius: 8px; background: var(--panel); }
.editor .edover { position: absolute; inset: 0; pointer-events: none; overflow: hidden; }
.editor .edover .edgap { position: absolute; inset: 0; background: #000; display: none; }
.editor .edover .ecap { position: absolute; left: 50%; transform: translateX(-50%); text-align: center; max-width: 84%; font-weight: 700; line-height: 1.2; white-space: pre-wrap; }
.editor .edover img { position: absolute; transform: translate(-50%, -50%); }
.editor .edtrans { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.editor .edtrans .clock { font: 600 15px ui-monospace, monospace; min-width: 120px; text-align: center; }
.editor .edtl { grid-column: 1 / -1; grid-row: 4; display: grid; grid-template-rows: 30px 26px minmax(0, 1fr); background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; position: relative; }
.editor .tlbar { display: flex; align-items: center; gap: 6px; padding: 0 8px; border-bottom: 1px solid var(--line); }
.editor .tlbar button { display: inline-flex; align-items: center; gap: 4px; }
.editor .tlbar .tc { font: 600 13px ui-monospace, monospace; min-width: 110px; }
.editor .tlbar input[type=range] { width: 110px; }
.editor .rulerrow { display: grid; grid-template-columns: var(--head) 1fr; border-bottom: 1px solid var(--line); }
.editor .rulerrow canvas, .editor .tlbody canvas { display: block; width: 100%; touch-action: none; }
.editor .rulerrow canvas { height: 26px; cursor: pointer; }
.editor .tlbody { display: grid; grid-template-columns: var(--head) 1fr; overflow-y: auto; overflow-x: hidden; min-height: 0; align-content: start; }
.editor .heads { border-right: 1px solid var(--line); }
.editor .trow { display: flex; align-items: center; gap: 2px; padding: 0 4px 0 8px; border-bottom: 1px solid color-mix(in srgb, var(--line) 60%, transparent); box-sizing: border-box; overflow: hidden; }
.editor .trow.on { background: color-mix(in srgb, var(--accent) 16%, transparent); }
.editor .trow .tname { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; cursor: default; }
.editor .trow .tag { font: 600 10px ui-monospace, monospace; color: var(--muted); width: 22px; }
.editor .trow button { padding: 1px 5px; font: 600 10px ui-monospace, monospace; min-width: 20px; }
.editor .trow button.solo.on { background: #e8b500; color: #000; }
.editor .trow button.mute.on { background: #e5484d; color: #fff; }
.editor .trow .ib { width: 22px; height: 22px; }
.editor .playhead { position: absolute; top: 30px; bottom: 0; width: 2px; margin-left: -1px; background: var(--energy); pointer-events: none; z-index: 2; }
.editor .playhead::before { content: ""; position: absolute; top: 0; left: -5px; border: 6px solid transparent; border-top: 8px solid var(--energy); }
.editor.busy { opacity: .7; }
.edpick { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.audioview { display: flex; flex-direction: column; gap: 8px; }
.audioview canvas { width: 100%; height: 280px; display: block; border-radius: 10px; background: var(--panel); border: 1px solid var(--line); }
"""

EDIT_JS = r"""// ---- Edit tab: tracks of clips like DaVinci Resolve and Premiere Pro ----
Object.assign(STUDIO_ICON, {
  pointer: "M5 3l14 8-6 2-2 6z",
  blade: "M6 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM6 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM8.1 8.1L20 20M8.1 15.9L20 4",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  magnet: "M6 3v9a6 6 0 0 0 12 0V3h-4v9a2 2 0 0 1-4 0V3z",
  start: "M6 5v14M18 5l-9 7 9 7z",
  end: "M18 5v14M6 5l9 7-9 7z",
  rewind: "M11 5l-8 7 8 7zM21 5l-8 7 8 7z",
  forward: "M13 5l8 7-8 7zM3 5l8 7-8 7z",
});
const ED_RATE = 25;  // waveform bars per second
const ED_HEAD = 176;
const ED_ROW = { video: 56, audio: 62, text: 30, subtitle: 30 };
const ED_FILL = { video: "#3c6fd6", audio: "#2c9a6a", text: "#8456ea", subtitle: "#178fa6" };
const ED_KIND_NAME = { video: "Video", audio: "Audio", text: "Text", subtitle: "Subtitles" };
const ED_TAG = { video: "V", audio: "A", text: "T", subtitle: "S" };
const ED_SOURCE_NAME = { recording: "Recording", mic: "Mic", system: "Mac sound" };
const CAPTION_DEFAULT = { font: "system-ui", size: 54, color: "#ffffff", outline: "#000000", box: false, position: "bottom" };
const CAPTION_FONTS = [["system-ui", "System"], ["serif", "Serif"], ["monospace", "Mono"], ["rounded", "Rounded"]];
const ED_LANGUAGES = [["", "Detect"], ["en", "English"], ["ru", "Русский"], ["az", "Azərbaycan"], ["tr", "Türkçe"], ["de", "Deutsch"], ["fr", "Français"], ["es", "Español"], ["uk", "Українська"]];
const ED_FONT_CSS = { "system-ui": "system-ui, -apple-system, sans-serif", serif: "Georgia, serif", monospace: "ui-monospace, Menlo, monospace", rounded: "ui-rounded, 'SF Pro Rounded', system-ui, sans-serif" };
const ed = { zoom: 0, scroll: 0, t: 0, playing: false, sel: new Set(), tool: "select", track: null, in: null, out: null,
  snap: localStorage.getItem("edit-snap") !== "off", linked: localStorage.getItem("edit-linked") !== "off", rows: Number(localStorage.getItem("edit-rows")) || 1,
  peaks: null, peaksFor: "", rec: {}, recFor: "", assetPeaks: {}, imported: [], busy: "",
  language: localStorage.getItem("edit-language") || "", model: localStorage.getItem("edit-model") || "", models: null,
  proxy: { state: "idle", files: {} }, proxyFor: "", proxyTimer: 0,
  ctx: null, buffers: {}, nodes: [], playT0: 0, playAt: 0, playPerf: 0, raf: 0, drawTimer: 0, assetTimer: 0, audioTimer: 0,
  drag: null, frameClip: null, frameScene: null, overlayKey: "", observer: null, warned: {} };

// ---- pure model (tested in tests/test_desk_ui.cjs; the export reads the same in capture_project.py) ----
function round3(value) { return Math.round(value * 1000) / 1000; }
function edId(list, prefix) { let n = 1; const used = new Set(list.map((item) => item.id)); while (used.has(prefix + n)) n++; return prefix + n; }
function clipEnd(clip) { return clip.start + clip.out - clip.in; }
function trackOf(edit, id) { return edit.tracks.find((track) => track.id === id) || null; }
function kindOf(edit, clip) { const track = trackOf(edit, clip.track); return track ? track.kind : ""; }
function trackLocked(edit, id) { const track = trackOf(edit, id); return !track || track.locked; }
function newTrack(id, kind, name) { return { id, kind, name, hidden: false, muted: false, solo: false, locked: false, volume: 1 }; }
function defaultTracks() {
  return [newTrack("s1", "subtitle", "Subtitles"), newTrack("t1", "text", "Text"), newTrack("v1", "video", "Video 1"),
    newTrack("a1", "audio", "Mic"), newTrack("a2", "audio", "Mac sound"), newTrack("a3", "audio", "Music")];
}
function screenHasSound(segment) { return Boolean(segment.files.screen) && !(segment.info && segment.info.screen && segment.info.screen.audio === false); }
function recordingSounds(project) {
  return { mic: project.segments.some((segment) => segment.files.mic), system: project.segments.some(screenHasSound) };
}
function audioOnly(project) { return !project.segments.some((segment) => segment.files.screen || segment.files.camera); }
function soundClip(id, track, source, start, from, to, link, more) {
  return Object.assign({ id, track, source, start, in: from, out: to, link, name: "", asset: "", volume: 1, fade_in: 0, fade_out: 0 }, more || {});
}
function defaultEdit(project) {
  const edit = { version: 2, tracks: defaultTracks(), clips: [], caption_style: { ...CAPTION_DEFAULT } };
  if (project.duration > 0) insertMedia(edit, project, "recording", 0, {});
  return edit;
}
function editOf(project) {
  if (!project.edit && project.duration > 0) project.edit = defaultEdit(project);
  return project.edit && project.edit.version === 2 ? project.edit : null;
}
function edLength(edit) { return round3(edit.clips.reduce((end, clip) => Math.max(end, clipEnd(clip)), 0)); }
function freshLink(edit, taken) {
  const used = new Set([...edit.clips.map((clip) => clip.link), ...(taken || [])]);
  let n = 1;
  while (used.has("l" + n)) n++;
  return "l" + n;
}
function linkedIds(edit, ids) {
  const links = new Set(), out = new Set(ids);
  for (const clip of edit.clips) if (out.has(clip.id) && clip.link) links.add(clip.link);
  for (const clip of edit.clips) if (clip.link && links.has(clip.link)) out.add(clip.id);
  return [...out];
}
// Split one clip at timeline time t; the right part is returned (placed after it in the list).
function splitClip(edit, clip, t) {
  const cut = round3(clip.in + t - clip.start);
  const right = { ...clip, id: edId(edit.clips, "c"), start: round3(t), in: cut };
  if ("fade_in" in clip) { right.fade_in = 0; clip.fade_out = 0; }
  clip.out = cut;
  edit.clips.splice(edit.clips.indexOf(clip) + 1, 0, right);
  return right;
}
// Cut at t: the given clips, or every clip under t on an unlocked track. Right halves of a linked group stay
// linked to each other (a cut picture and its sound still move together). Returns how many clips were cut.
function bladeAt(edit, t, ids) {
  const wanted = ids ? new Set(ids) : null;
  const hit = edit.clips.filter((clip) => (!wanted || wanted.has(clip.id)) && !trackLocked(edit, clip.track) && t > clip.start + 0.02 && t < clipEnd(clip) - 0.02);
  const links = {}, taken = [];
  for (const clip of hit) {
    const right = splitClip(edit, clip, t);
    if (clip.link) {
      if (!links[clip.link]) { links[clip.link] = freshLink(edit, taken); taken.push(links[clip.link]); }
      right.link = links[clip.link];
    }
  }
  return hit.length;
}
function liftClips(edit, ids) {
  const gone = new Set(ids), before = edit.clips.length;
  edit.clips = edit.clips.filter((clip) => !gone.has(clip.id) || trackLocked(edit, clip.track));
  return edit.clips.length < before;
}
// Make [a, b) of a track empty (overwrite): clips inside go, clips across the edges are trimmed or split.
// Returns whether anything changed.
function clearRange(edit, trackId, a, b, except) {
  let changed = false;
  for (const clip of edit.clips.filter((item) => item.track === trackId && !(except && except.has(item.id)))) {
    const start = clip.start, end = clipEnd(clip);
    if (end <= a + 1e-6 || start >= b - 1e-6) continue;
    changed = true;
    if (start >= a - 1e-6 && end <= b + 1e-6) { edit.clips.splice(edit.clips.indexOf(clip), 1); continue; }
    if (start < a && end > b) { splitClip(edit, clip, b); clip.out = round3(clip.in + a - start); continue; }
    if (start < a) clip.out = round3(clip.in + a - start);
    else { clip.in = round3(clip.in + b - start); clip.start = round3(b); }
  }
  return changed;
}
// Empty [a, b) on every unlocked track and leave the gap (Premiere's lift).
function liftRange(edit, a, b) {
  let changed = false;
  for (const track of edit.tracks) if (!track.locked && clearRange(edit, track.id, a, b, null)) changed = true;
  return changed;
}
// Take [a, b) out of every unlocked track and close the gap (Premiere's extract, Resolve's ripple).
function extractRange(edit, a, b) {
  if (!(b - a > 0.01)) return false;
  for (const track of edit.tracks) {
    if (track.locked) continue;
    clearRange(edit, track.id, a, b, null);
    for (const clip of edit.clips) if (clip.track === track.id && clip.start >= b - 1e-6) clip.start = round3(clip.start - (b - a));
  }
  return true;
}
function mergeRanges(ranges) {
  const sorted = ranges.filter(([a, b]) => b - a > 1e-6).sort((x, y) => x[0] - y[0]), out = [];
  for (const [a, b] of sorted) {
    const last = out[out.length - 1];
    if (last && a <= last[1] + 1e-6) last[1] = Math.max(last[1], b); else out.push([a, b]);
  }
  return out;
}
function rippleDelete(edit, ids) {
  const chosen = edit.clips.filter((clip) => ids.includes(clip.id) && !trackLocked(edit, clip.track));
  if (!chosen.length) return false;
  const ranges = mergeRanges(chosen.map((clip) => [clip.start, clipEnd(clip)]));
  liftClips(edit, chosen.map((clip) => clip.id));
  for (const [a, b] of ranges.reverse()) extractRange(edit, a, b);
  return true;
}
// Move clips by dt seconds and rowDelta tracks (only onto unlocked tracks of the same kind); what they land on
// is overwritten. Returns false (and changes nothing) when a clip cannot go there.
function moveClips(edit, ids, dt, rowDelta) {
  const moving = edit.clips.filter((clip) => ids.includes(clip.id) && !trackLocked(edit, clip.track));
  if (!moving.length) return false;
  const targets = new Map();
  for (const clip of moving) {
    const target = edit.tracks[edit.tracks.findIndex((track) => track.id === clip.track) + rowDelta];
    if (!target || target.kind !== kindOf(edit, clip) || target.locked) return false;
    targets.set(clip.id, target.id);
  }
  const shift = Math.max(-Math.min(...moving.map((clip) => clip.start)), dt);
  const except = new Set(moving.map((clip) => clip.id));
  for (const clip of moving) { clip.track = targets.get(clip.id); clip.start = round3(clip.start + shift); }
  for (const clip of moving) clearRange(edit, clip.track, clip.start, clipEnd(clip), except);
  return true;
}
// How far a clip's source reaches: the recording, an imported sound (once its length is known), or free.
function sourceLimit(project, clip) {
  if (clip.source === "recording" || clip.source === "mic" || clip.source === "system") return [0, project.duration];
  if (clip.source === "asset") { const known = ed.assetPeaks[clip.asset]; return [0, known && known.duration ? known.duration : Infinity]; }
  return [-Infinity, Infinity];
}
// Drag one edge of a clip (and of its linked partners at the same place) to t, stopping at the source's ends
// and at the neighbours on each track.
function trimClip(edit, id, side, t, project, linked) {
  const clip = edit.clips.find((item) => item.id === id);
  if (!clip || trackLocked(edit, clip.track)) return false;
  const edgeOf = (item) => side === "start" ? item.start : clipEnd(item);
  const edge = edgeOf(clip);
  const group = linked && clip.link ? edit.clips.filter((item) => item.link === clip.link && Math.abs(edgeOf(item) - edge) < 1e-3 && !trackLocked(edit, item.track)) : [clip];
  const members = new Set(group.map((item) => item.id));
  let low = side === "start" ? 0 : -Infinity, high = Infinity;
  for (const item of group) {
    const [min, max] = sourceLimit(project, item);
    const others = edit.clips.filter((other) => other.track === item.track && !members.has(other.id));
    if (side === "start") {
      low = Math.max(low, item.start - (item.in - min), ...others.filter((other) => clipEnd(other) <= item.start + 1e-6).map(clipEnd));
      high = Math.min(high, clipEnd(item) - 0.05);
    } else {
      low = Math.max(low, item.start + 0.05);
      high = Math.min(high, item.start + (max - item.in), ...others.filter((other) => other.start >= clipEnd(item) - 1e-6).map((other) => other.start));
    }
  }
  if (low > high) return false;
  const next = round3(Math.max(low, Math.min(high, t)));
  for (const item of group) {
    if (side === "start") { item.in = round3(item.in + next - item.start); item.start = next; } else item.out = round3(item.in + next - item.start);
  }
  return true;
}
function covering(edit, kind, t) {
  const rows = new Map(edit.tracks.map((track, index) => [track.id, index]));
  return edit.clips.filter((clip) => { const track = trackOf(edit, clip.track); return track && track.kind === kind && !track.hidden && t >= clip.start - 1e-9 && t < clipEnd(clip) - 1e-9; })
    .sort((a, b) => rows.get(a.track) - rows.get(b.track));
}
function videoAt(edit, t) { return covering(edit, "video", t)[0] || null; }  // the upper track covers the lower
function captionAt(edit, t) { return covering(edit, "subtitle", t)[0] || null; }
function textsAt(edit, t) { return covering(edit, "text", t).reverse(); }  // lower tracks first, the upper drawn over
function audibleClips(edit) {
  const audio = edit.tracks.filter((track) => track.kind === "audio");
  const solo = audio.some((track) => track.solo);
  const heard = new Set(audio.filter((track) => !track.muted && (!solo || track.solo)).map((track) => track.id));
  return edit.clips.filter((clip) => heard.has(clip.track));
}
function addTrack(edit, kind) {
  const prefix = { video: "v", audio: "a", text: "t", subtitle: "s" }[kind];
  const id = edId(edit.tracks, prefix);
  const same = edit.tracks.map((item, index) => [item, index]).filter(([item]) => item.kind === kind);
  const track = newTrack(id, kind, ED_KIND_NAME[kind] + " " + (same.length + 1));
  let at;
  if (kind === "audio") at = same.length ? same[same.length - 1][1] + 1 : edit.tracks.length;
  else if (same.length) at = same[0][1];  // a new picture, text or subtitle layer goes on top of its kind
  else at = { subtitle: 0, text: edit.tracks.filter((item) => item.kind === "subtitle").length, video: edit.tracks.filter((item) => item.kind !== "audio").length }[kind];
  edit.tracks.splice(at, 0, track);
  return track;
}
function firstTrack(edit, kind, skip) {
  return edit.tracks.find((track) => track.kind === kind && !track.locked && !(skip || []).includes(track.id)) || addTrack(edit, kind);
}
// Put media on the timeline at t (overwriting what is there): the recording as linked picture + mic + Mac
// sound, one of its parts, a text, or an imported sound. Returns the new clip ids.
function insertMedia(edit, project, kind, t, where) {
  where = where || {};
  const start = round3(Math.max(0, t)), length = round3(project.duration), added = [];
  const place = (clip) => { clearRange(edit, clip.track, clip.start, clipEnd(clip), null); edit.clips.push(clip); added.push(clip.id); };
  if (kind === "recording" || kind === "picture" || kind === "mic" || kind === "system") {
    const sounds = recordingSounds(project), link = kind === "recording" ? freshLink(edit) : "";
    if ((kind === "recording" || kind === "picture") && !audioOnly(project)) place({ id: edId(edit.clips, "c"), track: where.video || firstTrack(edit, "video").id, source: "recording", start, in: 0, out: length, link });
    let mic = null;
    if ((kind === "recording" || kind === "mic") && sounds.mic) { mic = where.mic || firstTrack(edit, "audio").id; place(soundClip(edId(edit.clips, "c"), mic, "mic", start, 0, length, link)); }
    if ((kind === "recording" || kind === "system") && sounds.system) place(soundClip(edId(edit.clips, "c"), where.system || firstTrack(edit, "audio", mic ? [mic] : []).id, "system", start, 0, length, link));
  } else if (kind === "text") {
    place({ id: edId(edit.clips, "c"), track: where.track || firstTrack(edit, "text").id, source: "text", start, in: 0, out: where.length || 3, link: "",
      text: where.text || "Title", asset: "", x: 0.5, y: 0.2, w: 0.4, color: "#ffffff", background: "" });
  } else if (kind === "asset") {
    const span = where.length || 10;
    const free = edit.tracks.find((track) => track.kind === "audio" && !track.locked && !edit.clips.some((clip) => clip.track === track.id && clipEnd(clip) > start && clip.start < start + span));
    place(soundClip(edId(edit.clips, "c"), where.track || (free || addTrack(edit, "audio")).id, "asset", start, 0, round3(span), "", { asset: where.asset, name: (where.name || "Sound").slice(0, 200) }));
  }
  return added;
}
function toggleLink(edit, ids) {
  const clips = edit.clips.filter((clip) => ids.includes(clip.id));
  if (clips.some((clip) => clip.link)) {
    const group = new Set(linkedIds(edit, ids));
    for (const clip of edit.clips) if (group.has(clip.id)) clip.link = "";
    return "unlinked";
  }
  if (clips.length < 2) return "";
  const link = freshLink(edit);
  for (const clip of clips) clip.link = link;
  return "linked";
}
// Where the recording's sound sits: per part, its file and how far into the part that file starts.
function soundParts(project, source) {
  const parts = [];
  let begin = 0;
  project.segments.forEach((segment, index) => {
    const track = source === "mic" ? "mic" : "screen";
    const file = source === "mic" ? segment.files.mic : screenHasSound(segment) ? segment.files.screen : null;
    if (file) parts.push({ segment: index, begin: round3(begin), end: round3(begin + segment.duration), file, offset: (segment.starts || {})[track] || 0 });
    begin += segment.duration;
  });
  return parts;
}
// Lines of the recording's clock -> subtitle clips, through the clips that carry the voice (mic, else picture).
function captionsToClips(edit, project, lines) {
  const voice = edit.clips.filter((clip) => clip.source === "mic");
  const carriers = voice.length ? voice : edit.clips.filter((clip) => clip.source === "recording" || clip.source === "system");
  const track = firstTrack(edit, "subtitle");
  edit.clips = edit.clips.filter((clip) => clip.track !== track.id);
  let count = 0, last = 0;
  for (const line of [...lines].sort((a, b) => a.in - b.in)) {
    const parts = carriers.map((clip) => {
      const low = Math.max(line.in, clip.in), high = Math.min(line.out, clip.out);
      return high > low ? [clip.start + low - clip.in, clip.start + high - clip.in] : null;
    }).filter(Boolean).sort((a, b) => a[0] - b[0]);
    if (!parts.length || !line.text) continue;
    const start = round3(Math.max(last, parts[0][0])), end = round3(parts[parts.length - 1][1]);
    if (end - start < 0.05) continue;
    edit.clips.push({ id: edId(edit.clips, "c"), track: track.id, source: "caption", start, in: 0, out: round3(end - start), link: "", text: String(line.text).slice(0, 500), asset: "" });
    last = end;
    count++;
  }
  return count;
}
function mergeCaption(edit, id) {
  const clip = edit.clips.find((item) => item.id === id);
  if (!clip || clip.source !== "caption") return false;
  const next = edit.clips.filter((item) => item.track === clip.track && item.start > clip.start).sort((a, b) => a.start - b.start)[0];
  if (!next) return false;
  clip.out = round3(clip.in + clipEnd(next) - clip.start);
  clip.text = (clip.text + " " + next.text).trim().slice(0, 500);
  clip.asset = "";
  edit.clips.splice(edit.clips.indexOf(next), 1);
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
// Cut every pause of the voice (recording-clock peaks of the mic) out of the timeline; returns the seconds removed.
function removeSilences(edit, project, peaks) {
  const quiet = silences(peaks, ED_RATE, 0.12, 0.6, 0.12);
  const voice = edit.clips.filter((clip) => clip.source === "mic" && !trackLocked(edit, clip.track));
  const carriers = voice.length ? voice : edit.clips.filter((clip) => clip.source === "system");
  const ranges = [];
  for (const clip of carriers) for (const [a, b] of quiet) {
    const low = Math.max(a, clip.in), high = Math.min(b, clip.out);
    if (high - low > 0.05) ranges.push([round3(clip.start + low - clip.in), round3(clip.start + high - clip.in)]);
  }
  const merged = mergeRanges(ranges);
  for (const [a, b] of [...merged].reverse()) extractRange(edit, a, b);
  return round3(merged.reduce((sum, [a, b]) => sum + b - a, 0));
}
function snapTime(t, targets, tolerance) {
  let best = t, distance = tolerance;
  for (const target of targets) if (Math.abs(target - t) < distance) { best = target; distance = Math.abs(target - t); }
  return best;
}
function edEdges(edit, except) {
  const edges = [0];
  for (const clip of edit.clips) if (!except || !except.has(clip.id)) edges.push(clip.start, clipEnd(clip));
  return edges;
}
function hashText(text) {
  let a = 0x811c9dc5, b = 0x01000193;
  for (let i = 0; i < text.length; i++) { const code = text.charCodeAt(i); a = Math.imul(a ^ code, 16777619) >>> 0; b = Math.imul(b ^ code, 2246822519) >>> 0; }
  return a.toString(16).padStart(8, "0") + b.toString(16).padStart(8, "0");
}
function captionAssetName(text, style) { return "cap-" + hashText(text + "\u0000" + JSON.stringify(style)) + ".png"; }
function textAssetName(item) { return "text-" + hashText([item.text, item.color, item.background].join("\u0000")) + ".png"; }
// Sound of several parts on one clock: [{start, peaks, duration}] -> bars at `rate`.
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
    const track = segment.files.mic ? "mic" : screenHasSound(segment) ? "screen" : null;
    if (track) files.push({ file: segment.files[track], start: start + ((segment.starts || {})[track] || 0), duration: segment.duration });
    start += segment.duration;
  }
  return files;
}
function edTimecode(t) {
  const frames = Math.max(0, Math.round(t * 30));
  const two = (n) => String(n).padStart(2, "0");
  return two(Math.floor(frames / 108000)) + ":" + two(Math.floor(frames / 1800) % 60) + ":" + two(Math.floor(frames / 30) % 60) + ":" + two(frames % 30);
}
function selIds() { if (!ed.sel || typeof ed.sel.has !== "function") ed.sel = new Set(); return [...ed.sel]; }

// ---- loading: waves, light copies, speech models ----
async function edWave(project, file, bars) {
  const { status, data } = await api("GET", "/api/studio/project/wave?path=" + encodeURIComponent(project.path) + "&file=" + encodeURIComponent(file) + "&bars=" + bars);
  return status === 200 && Array.isArray(data.peaks) ? data : null;
}
// The whole recording's sound on one clock (the Projects page of an audio project).
async function edPeaks(project) {
  if (ed.peaksFor === project.path && ed.peaks) return ed.peaks;
  ed.peaksFor = project.path;
  ed.peaks = null;
  const parts = [];
  for (const item of soundFiles(project)) {
    const wave = await edWave(project, item.file, Math.max(10, Math.min(20000, Math.round(item.duration * ED_RATE))));
    if (wave) parts.push({ start: item.start, peaks: wave.peaks, duration: wave.duration || item.duration });
  }
  if (ed.peaksFor !== project.path) return null;
  ed.peaks = joinPeaks(parts, project.duration, ED_RATE);
  drawAudioView();
  return ed.peaks;
}
// The mic and the Mac sound separately, on the recording's clock, for the audio clips' waves.
async function edRecordingPeaks(project) {
  if (ed.recFor === project.path) return;
  ed.recFor = project.path;
  ed.rec = {};
  for (const source of ["mic", "system"]) {
    const parts = [];
    for (const part of soundParts(project, source)) {
      const wave = await edWave(project, part.file, Math.max(10, Math.min(20000, Math.round((part.end - part.begin) * ED_RATE))));
      if (wave) parts.push({ start: part.begin + part.offset, peaks: wave.peaks, duration: wave.duration || part.end - part.begin });
    }
    if (ed.recFor !== project.path) return;
    if (parts.length) ed.rec[source] = joinPeaks(parts, project.duration, ED_RATE);
    edDraw();
  }
  if (studio.tab === "edit") edPool();
  if (!$("stage")) drawAudioWave();
}
async function edAssetPeaks(project, asset) {
  if (ed.assetPeaks[asset]) return;
  ed.assetPeaks[asset] = { peaks: [], duration: 0 };
  const wave = await edWave(project, "assets/" + asset, 4000);
  if (wave) ed.assetPeaks[asset] = { peaks: wave.peaks, duration: wave.duration || 0 };
  edDraw();
}
async function edProxies(project) {
  if (ed.proxyFor !== project.path) { ed.proxyFor = project.path; ed.proxy = { state: "idle", files: {} }; }
  clearTimeout(ed.proxyTimer);
  const url = "/api/studio/project/proxy?path=" + encodeURIComponent(project.path);
  let { status, data } = await api("GET", url);
  if (status === 200 && data.state !== "running" && data.state !== "done") ({ status, data } = await api("POST", "/api/studio/project/proxy", { path: project.path }));
  if (studio.project !== project || status !== 200 || !data || typeof data.state !== "string") return;
  const was = ed.proxy.state;
  ed.proxy = { state: data.state, files: data.files || {}, error: data.error || "" };
  if (data.state === "running" && studio.tab === "edit") ed.proxyTimer = setTimeout(() => edProxies(project), 1500);
  if (data.state === "done" && was !== "done") { edShowFrame(true); edLoadSounds(project); if (ed.playing) edRestartAudio(); }
  edProxyNote();
}
function edProxyNote() {
  const node = $("edProxy");
  if (!node) return;
  const state = ed.proxy.state;
  node.textContent = state === "running" ? "Preparing light copies for smooth playback…" : state === "failed" ? "Light copies failed (" + (ed.proxy.error || "unknown") + "); playing the originals" : "";
}
async function edLoadModels() {
  const { status, data } = await api("GET", "/api/studio/speech-models");
  ed.models = status === 200 && Array.isArray(data) ? data : [];
  if (!ed.models.some((item) => item.id === ed.model)) ed.model = ed.models.length ? ed.models[0].id : "";
  if (state.view === "studio" && studio.tab === "edit") edPool();
}

// ---- opening and leaving ----
async function openEdit(path) {
  if (!studio.project || studio.project.path !== path) await openProject(path);
  if (!studio.project) return;
  edEnter();
}
function edEnter() {
  const project = studio.project;
  studio.tab = "edit";
  localStorage.setItem("studio-tab", "edit");
  localStorage.setItem("studio-edit-path", project.path);
  const fresh = !project.edit;
  editOf(project);
  if (fresh && project.edit) { startHistory(project); saveProjectSoon(); }
  ed.t = 0; ed.sel = new Set(); ed.in = ed.out = null; ed.zoom = 0; ed.scroll = 0; ed.track = null; ed.frameClip = null;
  if (ed.proxyFor !== project.path) ed.imported = [];
  const player = studio.player;
  if (player) {
    // In the editor Web Audio plays every sound: the media elements only show pictures.
    clearInterval(player.timer);
    player.timer = 0;
    player.playing = false;
    for (const track of PROJECT_TRACKS) if (player[track].pause) player[track].pause();
    player.screen.muted = true;
  }
  if (!ed.ctx && typeof AudioContext !== "undefined") { try { ed.ctx = new AudioContext({ latencyHint: "interactive" }); } catch (error) { ed.ctx = null; } }
  renderStudioBody();
  edProxies(project);
  edLoadSounds(project);
  if (ed.models === null) edLoadModels();
}
function edLeave() {
  edPause();
  clearTimeout(ed.proxyTimer);
  const player = studio.player;
  if (player) {
    player.screen.muted = false;
    player.segment = -1;  // the Projects page loads its own files again
    if (!player.timer) player.timer = setInterval(syncPlayer, 200);
  }
  if (ed.observer) { ed.observer.disconnect(); ed.observer = null; }
  ed.buffers = {};
}

// ---- changes: every one is undoable and saved ----
function edChanged(redraw) {
  rememberEdit();
  saveProjectSoon();
  edScheduleAssets();
  if (ed.playing) edRestartAudio();
  if (redraw === "all") { renderEdit(); return; }
  edHeads();
  edDraw();
  renderEditSide();
  edOverlay(true);
  edShowFrame(true);
}

// ---- playback: Web Audio is the clock, the pictures follow ----
function edNow() {
  if (!ed.playing) return ed.t;
  const elapsed = ed.ctx ? ed.ctx.currentTime - ed.playAt : (performance.now() - ed.playPerf) / 1000;
  return ed.playT0 + Math.max(0, elapsed);
}
function edAudioFile(source, file) {
  const proxy = ed.proxy.files && ed.proxy.files[file];
  if (proxy && proxy.audio) return proxy.audio;
  return source === "mic" ? file : null;  // the Mac sound needs its light copy (the screen file is huge)
}
function edClipPieces(project, clip) {
  if (clip.source === "asset") return [{ url: projectMedia(project.path, "assets/" + clip.asset), start: clip.start, offset: clip.in, length: clip.out - clip.in }];
  const pieces = [];
  for (const part of soundParts(project, clip.source)) {
    const file = edAudioFile(clip.source, part.file);
    if (!file) continue;
    // The file covers [begin + offset, end] of the recording.
    const low = Math.max(clip.in, part.begin + Math.max(0, part.offset)), high = Math.min(clip.out, part.end);
    if (high - low <= 0.001) continue;
    pieces.push({ url: projectMedia(project.path, file), start: clip.start + low - clip.in, offset: low - part.begin - part.offset, length: high - low });
  }
  return pieces;
}
function edLoadBuffer(url) {
  if (ed.buffers[url] || !ed.ctx || typeof ed.ctx.decodeAudioData !== "function") return;
  ed.buffers[url] = "loading";
  fetch(url).then((response) => response.arrayBuffer()).then((bytes) => ed.ctx.decodeAudioData(bytes)).then((buffer) => {
    ed.buffers[url] = buffer;
    if (ed.playing) edRestartAudio();
  }).catch(() => { ed.buffers[url] = "failed"; });
}
function edLoadSounds(project) {
  const edit = project.edit;
  if (!edit || !ed.ctx) return;
  for (const clip of edit.clips) if (kindOf(edit, clip) === "audio") for (const piece of edClipPieces(project, clip)) edLoadBuffer(piece.url);
}
function edStopAudio() {
  for (const node of ed.nodes) { try { node.stop(); } catch (error) { /* it had already ended */ } }
  ed.nodes = [];
}
function edScheduleAudio() {
  edStopAudio();
  const project = studio.project, edit = project && project.edit, ctx = ed.ctx;
  if (!edit || !ctx || typeof ctx.createBufferSource !== "function") return;
  const t0 = ed.playT0, at0 = ed.playAt, when = (t) => at0 + (t - t0);
  let missing = false;
  for (const clip of audibleClips(edit)) {
    const track = trackOf(edit, clip.track), volume = clip.volume * track.volume, end = clipEnd(clip);
    if (end <= t0 || volume <= 0) continue;
    const gainAt = (t) => volume * Math.max(0, Math.min(1, clip.fade_in > 0 ? (t - clip.start) / clip.fade_in : 1, clip.fade_out > 0 ? (end - t) / clip.fade_out : 1));
    for (const piece of edClipPieces(project, clip)) {
      const pieceEnd = piece.start + piece.length;
      if (pieceEnd <= t0) continue;
      const buffer = ed.buffers[piece.url];
      if (!buffer || typeof buffer === "string") { if (!buffer) edLoadBuffer(piece.url); missing = true; continue; }
      const begin = Math.max(piece.start, t0);
      const source = ctx.createBufferSource(), gain = ctx.createGain();
      source.buffer = buffer;
      source.connect(gain);
      gain.connect(ctx.destination);
      gain.gain.setValueAtTime(gainAt(begin), when(begin));
      if (clip.fade_in > 0 && begin < clip.start + clip.fade_in) gain.gain.linearRampToValueAtTime(volume, when(clip.start + clip.fade_in));
      if (clip.fade_out > 0) {
        const from = Math.max(begin, end - clip.fade_out);
        gain.gain.setValueAtTime(gainAt(from), when(from));
        gain.gain.linearRampToValueAtTime(0, when(end));
      }
      source.start(when(begin), Math.max(0, piece.offset + begin - piece.start), pieceEnd - begin);
      ed.nodes.push(source);
    }
  }
  if (missing && !ed.warned.audio) { ed.warned.audio = true; toast("Some sound is still loading; it joins in a moment"); }
}
function edRestartAudio() {
  if (!ed.playing) return;
  ed.t = edNow();
  ed.playT0 = ed.t;
  ed.playAt = ed.ctx ? ed.ctx.currentTime + 0.05 : 0;
  ed.playPerf = performance.now() + 50;
  edScheduleAudio();
}
function edSeek(t) {
  const edit = studio.project && studio.project.edit;
  if (!edit) return;
  ed.t = round3(Math.max(0, Math.min(edLength(edit), t)));
  if (ed.playing) edRestartAudio();
  edShowFrame(true);
  edPlayhead();
  edOverlay();
}
function edPlay() {
  const edit = studio.project && studio.project.edit;
  if (!edit || ed.playing) return;
  if (ed.t >= edLength(edit) - 0.05) ed.t = 0;
  if (ed.ctx && ed.ctx.state === "suspended" && ed.ctx.resume) ed.ctx.resume();
  ed.playing = true;
  ed.warned.audio = false;
  ed.playT0 = ed.t;
  ed.playAt = ed.ctx ? ed.ctx.currentTime + 0.05 : 0;
  ed.playPerf = performance.now() + 50;
  edScheduleAudio();
  edShowFrame(true);
  cancelAnimationFrame(ed.raf);
  ed.raf = requestAnimationFrame(edLoop);
  edClock();
}
function edPause() {
  if (ed.playing) ed.t = round3(edNow());
  ed.playing = false;
  cancelAnimationFrame(ed.raf);
  edStopAudio();
  const player = studio.player;
  if (player) for (const track of ["screen", "camera"]) if (player[track].pause) player[track].pause();
  edShowFrame(true);
  edClock();
}
function edToggle() { if (ed.playing) edPause(); else edPlay(); }
function edLoop() {
  const edit = studio.project && studio.project.edit;
  if (!ed.playing || !edit) return;
  ed.t = edNow();
  const end = edLength(edit);
  if (ed.t >= end) { ed.t = end; edPause(); edPlayhead(); return; }
  edShowFrame(false);
  edFollow();
  edPlayhead();
  edOverlay();
  ed.raf = requestAnimationFrame(edLoop);
}
function edMediaFile(file) {
  const proxy = ed.proxy.files && ed.proxy.files[file];
  return proxy && proxy.video ? proxy.video : file;
}
// The picture at the playhead: the top visible video clip moves the screen/camera elements to its moment.
function edShowFrame(force) {
  const project = studio.project, edit = project && project.edit, player = studio.player;
  if (!edit) return;
  if (!$("stage")) { drawAudioWave(); return; }
  const clip = videoAt(edit, ed.t);
  const gap = $("edGap");
  if (gap) gap.style.display = clip ? "none" : "block";
  if (!clip || !player) {
    if (player) for (const track of ["screen", "camera"]) if (player[track].pause && !player[track].paused) player[track].pause();
    ed.frameClip = null;
    return;
  }
  const recording = clip.in + ed.t - clip.start;
  const { segment, local } = projectClock(project, recording);
  if (segment < 0) return;
  const part = project.segments[segment], starts = part.starts || {};
  const jumped = force || ed.frameClip !== clip.id || player.segment !== segment;
  player.segment = segment;
  for (const track of ["screen", "camera"]) {
    const file = part.files[track], node = player[track];
    if (file) { const url = projectMedia(project.path, edMediaFile(file)); if (node._src !== url) { node._src = url; node.src = url; } }
    else if (node._src) { node.pause(); if (node.removeAttribute) node.removeAttribute("src"); node._src = ""; }
  }
  ed.frameClip = clip.id;
  player.t = recording;
  for (const track of ["screen", "camera"]) {
    if (!part.files[track]) continue;
    const node = player[track], wanted = Math.max(0, local - (starts[track] || 0));
    if (jumped) { setMediaTime(node, wanted); node.playbackRate = 1; } else if (ed.playing) follow(node, wanted);
    if (ed.playing && node.paused && !node.ended) playMedia(node);
    if (!ed.playing && !node.paused) node.pause();
  }
  const scene = sceneAt(project, recording);
  if (scene !== ed.frameScene) { ed.frameScene = scene; drawStage(); }
}
function edClock() {
  const edit = studio.project && studio.project.edit;
  if (!edit) return;
  for (const id of ["edClock", "edTc"]) { const node = $(id); if (node) node.textContent = edTimecode(ed.t); }
  const total = $("edTotal");
  if (total) total.textContent = "/ " + edTimecode(edLength(edit));
  const play = $("edPlay");
  if (play && play._playing !== ed.playing) { play._playing = ed.playing; play.textContent = ""; play.append(studioIcon(ed.playing ? "pause" : "play")); }
}

// ---- the page ----
function edLayout() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem("edit-layout") || "{}") || {}; } catch (error) { saved = {}; }
  const pick = (value, low, high, fallback) => Number.isFinite(value) && value >= low && value <= high ? value : fallback;
  return { pool: pick(saved.pool, 160, 700, 250), insp: pick(saved.insp, 200, 700, 290), tl: pick(saved.tl, 150, 1400, 330) };
}
function renderEdit() {
  const box = $("studioEdit");
  if (!box) return;
  box.textContent = "";
  const project = studio.project;
  if (!project) { edPicker(box); return; }
  const edit = editOf(project);
  if (!edit) { box.append(h("div", { class: "empty", text: "This project has nothing recorded to edit." })); return; }
  const video = !audioOnly(project);
  const layout = edLayout();
  const root = h("div", { class: "editor" + (ed.busy ? " busy" : ""), id: "edRoot", style: "--pool:" + layout.pool + "px;--insp:" + layout.insp + "px;--tl:" + layout.tl + "px;--head:" + ED_HEAD + "px" });
  const tool = (name, icon, label, title) => h("button", { class: ed.tool === name ? "on" : "", title, onclick: () => edSetTool(name) }, studioIcon(icon), label);
  root.append(h("div", { class: "edbar" },
    h("button", { class: "ghost back", onclick: () => { edLeave(); closeProject().then(() => setStudioTab("projects")); } }, studioIcon("back"), "Projects"),
    h("b", { text: project.name }), h("span", { class: "where", id: "edLen" }),
    h("span", { class: "spacer" }),
    h("div", { class: "tools" }, tool("select", "pointer", "Select", "Selection tool (A or V)"), tool("blade", "blade", "Blade", "Blade tool: click a clip to cut it (B)")),
    h("button", { class: ed.snap ? "on" : "", title: "Snapping to the playhead and clip edges (N)", onclick: edToggleSnap }, studioIcon("magnet"), "Snap"),
    h("button", { class: ed.linked ? "on" : "", title: "Linked selection: a picture and its sound are picked together (⇧⌘L; Alt-click picks one)", onclick: edToggleLinked }, studioIcon("link"), "Linked"),
    iconButton("undo", "Undo (⌘Z; ⇧⌘Z redoes)", () => undoEdit(false)),
    video ? h("div", { class: "seg fmt" }, STUDIO_FORMATS.map(([value, label]) =>
      h("button", { class: studio.projectCanvas === value ? "on" : "", text: label, onclick: () => { studio.projectCanvas = value; ed.frameScene = null; renderEdit(); } }))) : null,
    h("button", { class: "primary", text: ed.busy === "export" ? "Preparing…" : "Export…", disabled: Boolean(ed.busy) || null, onclick: edExport })));
  root.append(h("div", { class: "pane edpool", id: "edPool" }), edGutter("left"));
  const view = h("div", { class: "edview" });
  if (video) view.append(h("div", { class: "stagebox", id: "stageBox" }, stageFrame()));
  else view.append(h("div", { class: "stagebox" }, h("canvas", { class: "edwave", id: "edWave" }), h("div", { class: "edover", id: "edOver" })));
  view.append(h("div", { class: "edtrans" },
    iconButton("start", "To the start (Home)", () => edSeek(0)),
    iconButton("rewind", "Back 5 s (J)", () => edSeek(ed.t - 5)),
    h("button", { id: "edPlay", class: "ib", title: "Play / pause (Space, K stops, L plays)", "aria-label": "Play / pause", onclick: edToggle }, studioIcon(ed.playing ? "pause" : "play")),
    iconButton("forward", "Forward 5 s", () => edSeek(ed.t + 5)),
    iconButton("end", "To the end (End)", () => edSeek(edLength(edit))),
    h("span", { class: "clock", id: "edClock" }), h("span", { class: "where", id: "edTotal" }),
    h("span", { class: "spacer" }), h("span", { class: "where", id: "edProxy" })));
  root.append(view, edGutter("right"), h("div", { class: "pane edinspect", id: "edInspect" }), edGutter("bottom"));
  root.append(edTimeline());
  box.append(root);
  if (video) {
    const wrap = $("stageWrap") || $("stageBox");
    if (wrap) wrap.append(h("div", { class: "edover", id: "edOver" }, h("div", { class: "edgap", id: "edGap" })));
    watchStageSize();
    ed.frameScene = null;
  }
  edHeads();
  renderEditSide();
  edRecordingPeaks(project);
  for (const clip of edit.clips) if (clip.source === "asset") edAssetPeaks(project, clip.asset);
  if (!studio.projects.length && !studio.projectsLoaded) loadProjects();
  edSeek(ed.t);
  edClock();
  edDraw();
  edProxyNote();
  if (typeof ResizeObserver !== "undefined") {
    if (ed.observer) ed.observer.disconnect();
    ed.observer = new ResizeObserver(() => { edDraw(); edOverlay(true); });
    ed.observer.observe($("edBody"));
  }
  edScheduleAssets();
}
// Every border is draggable; the sizes are kept for the next visit.
function edGutter(kind) {
  const node = h("div", { class: kind === "bottom" ? "hg" : "vg " + kind, title: "Drag to resize" });
  node.addEventListener("pointerdown", (event) => {
    const root = $("edRoot");
    if (!root) return;
    event.preventDefault();
    const layout = edLayout(), start = { x: event.clientX, y: event.clientY, ...layout };
    const move = (moved) => {
      if (moved.buttons === 0) { up(); return; }
      if (kind === "left") layout.pool = Math.max(160, Math.min(700, start.pool + moved.clientX - start.x));
      if (kind === "right") layout.insp = Math.max(200, Math.min(700, start.insp - (moved.clientX - start.x)));
      if (kind === "bottom") layout.tl = Math.max(150, Math.min(1400, window.innerHeight - 260, start.tl - (moved.clientY - start.y)));
      root.style.setProperty("--pool", layout.pool + "px");
      root.style.setProperty("--insp", layout.insp + "px");
      root.style.setProperty("--tl", layout.tl + "px");
      localStorage.setItem("edit-layout", JSON.stringify(layout));
      edDraw();
      edOverlay(true);
    };
    const up = () => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); removeEventListener("pointercancel", up); };
    addEventListener("pointermove", move); addEventListener("pointerup", up); addEventListener("pointercancel", up);
  });
  return node;
}
function edTimeline() {
  const rows = h("input", { type: "range", min: "0.6", max: "2", step: "0.1", value: String(ed.rows), title: "Track height" });
  rows.addEventListener("input", () => { ed.rows = Number(rows.value); localStorage.setItem("edit-rows", String(ed.rows)); edHeads(); edDraw(); });
  const zoom = (factor) => () => { ed.zoom = Math.max(0.2, Math.min(2000, (ed.zoom || 1) * factor)); edDraw(); };
  const bar = h("div", { class: "tlbar" },
    h("span", { class: "tc", id: "edTc" }),
    h("button", { title: "Add a track", onclick: (event) => edTrackMenu(event.currentTarget) }, studioIcon("plus"), "Track"),
    h("span", { class: "where", id: "edRange" }),
    h("span", { class: "spacer" }),
    h("span", { class: "lbl", text: "Height" }), rows,
    iconButton("minus", "Zoom out (⌘−, or ⌥/⌘ with the wheel)", zoom(1 / 1.5)),
    iconButton("plus", "Zoom in (⌘=)", zoom(1.5)),
    h("button", { title: "Fit the whole timeline (⇧Z)", text: "Fit", onclick: () => { ed.zoom = 0; edDraw(); } }));
  const ruler = h("canvas", { id: "edRuler", "aria-label": "Time ruler" });
  const tracks = h("canvas", { id: "edTracks", "aria-label": "Timeline tracks" });
  const body = h("div", { class: "tlbody", id: "edBody" }, h("div", { class: "heads", id: "edHeads" }), tracks);
  const node = h("div", { class: "edtl", id: "edTl" }, bar, h("div", { class: "rulerrow" }, h("div", {}), ruler), body, h("div", { class: "playhead", id: "edHead" }));
  edRulerEvents(ruler);
  edTrackEvents(tracks);
  return node;
}
function edVisibleTracks(edit) {
  const project = studio.project;
  return edit.tracks.filter((track) => !(track.kind === "video" && project && audioOnly(project)));
}
function edRowsOf(edit) {
  let y = 0;
  return edVisibleTracks(edit).map((track) => { const height = Math.round(ED_ROW[track.kind] * ed.rows); const row = { track, y, height }; y += height; return row; });
}
function edHeads() {
  const box = $("edHeads"), edit = studio.project && studio.project.edit;
  if (!box || !edit) return;
  box.textContent = "";
  for (const row of edRowsOf(edit)) {
    const track = row.track;
    const flag = (key, label, title, extra) => h("button", { class: extra + (track[key] ? " on" : ""), title, text: label, onclick: (event) => { event.stopPropagation(); edToggleTrack(track.id, key); } });
    const buttons = track.kind === "audio"
      ? [flag("muted", "M", "Mute this track", "mute"), flag("solo", "S", "Solo: hear only solo tracks", "solo")]
      : [iconButton(track.hidden ? "eyeOff" : "eye", track.hidden ? "Show this track" : "Hide this track", (event) => { event.stopPropagation(); edToggleTrack(track.id, "hidden"); }, track.hidden ? "dim" : "")];
    buttons.push(iconButton(track.locked ? "lock" : "unlock", track.locked ? "Locked: cuts, moves and ripples leave it alone" : "Lock this track", (event) => { event.stopPropagation(); edToggleTrack(track.id, "locked"); }, track.locked ? "" : "dim"));
    const same = edit.tracks.filter((item) => item.kind === track.kind), index = same.indexOf(track);
    const tag = ED_TAG[track.kind] + (track.kind === "audio" ? index + 1 : same.length - index);
    box.append(h("div", { class: "trow " + track.kind + (ed.track === track.id ? " on" : ""), style: "height:" + row.height + "px", title: "Click for its settings · double-click to rename · right-click for more",
      onclick: () => { ed.track = track.id; ed.sel = new Set(); edHeads(); edDraw(); renderEditSide(); },
      ondblclick: () => edRenameTrack(track.id), oncontextmenu: (event) => edTrackContext(event, track.id) },
      h("span", { class: "tag", text: tag }), h("span", { class: "tname", text: track.name }), ...buttons));
  }
}
function edToggleTrack(id, key) {
  const edit = studio.project && studio.project.edit, track = edit && trackOf(edit, id);
  if (!track) return;
  track[key] = !track[key];
  edChanged();
}
function cleanName(text, limit) { return String(text).replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, limit); }
function edRenameTrack(id) {
  const edit = studio.project.edit, track = trackOf(edit, id);
  const name = prompt("Track name", track.name);
  if (name === null || !cleanName(name, 60)) return;
  track.name = cleanName(name, 60);
  edChanged();
}
function edTrackMenu(anchor) {
  const edit = studio.project.edit;
  const kinds = [["video", "Video track (covers the ones below)"], ["audio", "Audio track"], ["text", "Text track"], ["subtitle", "Subtitle track"]]
    .filter(([kind]) => kind !== "video" || !audioOnly(studio.project));
  openStudioMenu(anchor, kinds.map(([kind, label]) => h("button", { onclick: () => {
    closeStudioMenu();
    if (edit.tracks.length >= 40) { toast("At most 40 tracks"); return; }
    ed.track = addTrack(edit, kind).id;
    ed.sel = new Set();
    edChanged();
  } }, studioIcon("plus"), label)));
}
function edTrackContext(event, id) {
  const edit = studio.project.edit, track = trackOf(edit, id);
  const same = edit.tracks.filter((item) => item.kind === track.kind), at = same.indexOf(track);
  const swap = (other) => { const a = edit.tracks.indexOf(track), b = edit.tracks.indexOf(other); edit.tracks[a] = other; edit.tracks[b] = track; edChanged(); };
  const used = edit.clips.filter((clip) => clip.track === id).length;
  contextMenu(event, [
    ["Rename…", () => edRenameTrack(id)],
    ["Move up", () => swap(same[at - 1]), at === 0],
    ["Move down", () => swap(same[at + 1]), at === same.length - 1],
    "-",
    ["Delete track" + (used ? " and its " + used + " clip" + (used === 1 ? "" : "s") : ""), () => {
      if (same.length === 1 && track.kind !== "audio") { toast("Keep one " + ED_KIND_NAME[track.kind].toLowerCase() + " track"); return; }
      if (used && !confirm("Delete the track “" + track.name + "” with its " + used + " clips?")) return;
      edit.clips = edit.clips.filter((clip) => clip.track !== id);
      edit.tracks = edit.tracks.filter((item) => item.id !== id);
      ed.track = null;
      edChanged();
    }],
  ]);
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
function renderEditSide() {
  edPool();
  edInspector();
  const len = $("edLen"), edit = studio.project && studio.project.edit;
  if (len && edit) len.textContent = clockText(edLength(edit));
}

// ---- media pool: what can go on the timeline ----
function edMediaItem(label, icon, payload, title) {
  const node = h("div", { class: "media", draggable: "true", title: title + " · drag it onto a track, or + puts it at the playhead" },
    studioIcon(icon), h("span", { text: label }), h("button", { text: "+", title: "Put it at the playhead", onclick: (event) => { event.stopPropagation(); edDrop(payload, ed.t, null); } }));
  node.addEventListener("dragstart", (event) => { if (event.dataTransfer) { event.dataTransfer.setData("application/x-unlaw-edit", JSON.stringify(payload)); event.dataTransfer.effectAllowed = "copy"; } });
  return node;
}
function edPool() {
  const box = $("edPool"), project = studio.project;
  if (!box || !project || !project.edit) return;
  const edit = project.edit;
  box.textContent = "";
  const sounds = recordingSounds(project);
  box.append(h("h5", { text: "Media" }));
  if (!audioOnly(project)) {
    box.append(edMediaItem("Recording (picture + sound)", "screen", { kind: "recording" }, "The recording with its scenes, mic and Mac sound, linked"));
    box.append(edMediaItem("Picture only", "scene", { kind: "picture" }, "The composed picture without sound"));
  }
  if (sounds.mic) box.append(edMediaItem("Mic", "mic", { kind: "mic" }, "The microphone of the recording"));
  if (sounds.system) box.append(edMediaItem("Mac sound", "speaker", { kind: "system" }, "The sound of the Mac (apps, video calls)"));
  const assets = new Map();
  for (const clip of edit.clips) if (clip.source === "asset" && !assets.has(clip.asset)) assets.set(clip.asset, clip.name || clip.asset);
  for (const item of ed.imported) if (!assets.has(item.asset)) assets.set(item.asset, item.name);
  for (const [asset, name] of assets) box.append(edMediaItem(name, "audio", { kind: "asset", asset, name }, "An imported sound"));
  box.append(edMediaItem("Text", "text", { kind: "text" }, "A title over the picture (T)"));
  const file = h("input", { type: "file", accept: "audio/*,.m4a,.mp3,.wav,.flac,.aac,.aiff,.caf", style: "display:none" });
  file.addEventListener("change", () => { if (file.files[0]) edImportFile(file.files[0]); file.value = ""; });
  box.append(file,
    h("button", { class: "wide", onclick: () => file.click() }, studioIcon("audio"), "Import music or a sound…"),
    h("button", { class: "wide", onclick: (event) => edVoiceMenu(event.currentTarget) }, studioIcon("mic"), "Voice-over from an audio recording…"));
  box.append(h("h5", { text: "Subtitles" }));
  const language = studioSelect(ED_LANGUAGES, ed.language, (value) => { ed.language = value; localStorage.setItem("edit-language", value); });
  const models = ed.models === null ? [["", "Looking for speech models…"]] : ed.models.length ? ed.models.map((item) => [item.id, item.id.split("/").pop() + (item.default ? " (default)" : "")]) : [["", "No speech model"]];
  const model = studioSelect(models, ed.model, (value) => { ed.model = value; localStorage.setItem("edit-model", value); });
  box.append(prow("Language", language), prow("Model", model));
  const captions = edit.clips.filter((clip) => clip.source === "caption").sort((a, b) => a.start - b.start);
  box.append(h("div", { class: "row" }, h("button", { text: ed.busy === "transcribe" ? "Listening…" : captions.length ? "Transcribe again" : "Transcribe", disabled: Boolean(ed.busy) || (ed.models !== null && !ed.models.length) || null, onclick: edTranscribe })));
  if (ed.models !== null && !ed.models.length) box.append(h("p", { class: "note", text: "Download one in a terminal: ul lm pull mlx-community/whisper-large-v3-turbo" }));
  else if (!captions.length) box.append(h("p", { class: "note", text: "Speech to text on this Mac (ul lm). The lines follow your cuts." }));
  const list = h("div", { class: "caplist" });
  for (const clip of captions.slice(0, 400)) {
    const input = h("input", { type: "text", value: clip.text, maxlength: "500" });
    input.addEventListener("change", () => { const text = cleanName(input.value, 500); if (!text) return; clip.text = text; clip.asset = ""; edChanged(); });
    input.addEventListener("focus", () => { ed.sel = new Set([clip.id]); edSeek(clip.start + 0.01); edDraw(); edInspector(); });
    list.append(h("div", { class: "cap" + (ed.sel.has(clip.id) ? " on" : "") },
      h("span", { text: clockText(clip.start), onclick: () => { ed.sel = new Set([clip.id]); edSeek(clip.start + 0.01); renderEditSide(); edDraw(); } }), input));
  }
  box.append(list);
  box.append(h("h5", { text: "Clean up" }),
    h("button", { class: "wide", disabled: (!ed.rec.mic && !ed.rec.system) || null, title: "Cut every pause of the voice longer than 0.6 s out of the timeline (⌘Z brings them back)", onclick: edRemoveSilences }, studioIcon("minus"), "Remove silences"));
}

// ---- inspector: the selected clip or track, else the subtitle style ----
function edNumber(value, onchange, step, min) {
  const input = h("input", { type: "number", value: String(round3(value)), step: String(step || 0.1), min: min === undefined ? null : String(min) });
  input.addEventListener("change", () => { const next = Number(input.value); if (Number.isFinite(next)) onchange(next); });
  return input;
}
function edVolume(value, onchange) {
  const input = h("input", { type: "range", min: "0", max: "2", step: "0.01", value: String(value) });
  const label = h("span", { class: "where", text: "" });
  const show = () => { const v = Number(input.value), db = 20 * Math.log10(v); label.textContent = v <= 0 ? "−∞ dB" : (db >= 0 ? "+" : "") + db.toFixed(1) + " dB"; };
  show();
  input.addEventListener("input", show);
  input.addEventListener("change", () => onchange(Number(input.value)));
  return [input, label];
}
function edInspector() {
  const box = $("edInspect"), project = studio.project;
  if (!box || !project || !project.edit) return;
  const edit = project.edit;
  box.textContent = "";
  const chosen = edit.clips.filter((clip) => ed.sel.has(clip.id));
  if (chosen.length > 1) {
    box.append(h("h5", { text: chosen.length + " clips" }),
      h("div", { class: "row" },
        h("button", { text: chosen.some((clip) => clip.link) ? "Unlink (⌘L)" : "Link (⌘L)", onclick: edLink }),
        h("button", { text: "Cut at playhead (⌘B)", onclick: edBladePlayhead }),
        h("button", { text: "Delete (⌫)", onclick: () => edDelete(false) }),
        h("button", { text: "Ripple delete (⇧⌫)", onclick: () => edDelete(true) })));
    return;
  }
  const clip = chosen[0];
  if (clip) {
    const kind = kindOf(edit, clip), length = clip.out - clip.in;
    const title = clip.source === "asset" ? clip.name || clip.asset : clip.source === "text" ? "Text" : clip.source === "caption" ? "Subtitle" : ED_SOURCE_NAME[clip.source];
    box.append(h("h5", { text: title + " · " + (trackOf(edit, clip.track) || {}).name }));
    if (kind === "text" || kind === "subtitle") {
      const area = h("textarea", { rows: "3", maxlength: "500" });
      area.value = clip.text;
      area.addEventListener("change", () => { const text = cleanName(area.value, 500); if (text) { clip.text = text; clip.asset = ""; edChanged(); } });
      box.append(area);
    }
    box.append(prow("Start", edNumber(clip.start, (value) => { if (moveClips(edit, [clip.id], round3(Math.max(0, value)) - clip.start, 0)) edChanged(); }, 0.1, 0)),
      prow("Length", edNumber(length, (value) => { if (value >= 0.05 && trimClip(edit, clip.id, "end", clip.start + value, project, false)) edChanged(); }, 0.1, 0.05)));
    if (kind === "video" || clip.source === "mic" || clip.source === "system" || clip.source === "asset")
      box.append(prow("Source in", edNumber(clip.in, (value) => { if (trimClip(edit, clip.id, "start", clip.start + value - clip.in, project, false)) edChanged(); }, 0.1, 0)));
    if (kind === "audio") {
      const [volume, label] = edVolume(clip.volume, (value) => { clip.volume = Math.max(0, Math.min(4, value)); edChanged(); });
      box.append(prow("Volume", volume, label),
        prow("Fade in", edNumber(clip.fade_in, (value) => { clip.fade_in = Math.max(0, Math.min(600, value)); edChanged(); }, 0.1, 0)),
        prow("Fade out", edNumber(clip.fade_out, (value) => { clip.fade_out = Math.max(0, Math.min(600, value)); edChanged(); }, 0.1, 0)));
    }
    if (kind === "text") {
      const color = h("input", { type: "color", value: clip.color || "#ffffff" });
      color.addEventListener("change", () => { clip.color = color.value; clip.asset = ""; edChanged(); });
      const back = h("input", { type: "color", value: clip.background || "#000000" });
      back.addEventListener("change", () => { clip.background = back.value; clip.asset = ""; edChanged(); });
      const slider = (key, label) => {
        const input = h("input", { type: "range", min: key === "w" ? "0.05" : "0", max: "1", step: "0.01", value: String(clip[key]) });
        input.addEventListener("input", () => { clip[key] = Number(input.value); edOverlay(true); });
        input.addEventListener("change", () => edChanged());
        return prow(label, input);
      };
      box.append(prow("Colour", color), prow("Box", back, studioCheck(Boolean(clip.background), (on) => { clip.background = on ? back.value : ""; clip.asset = ""; edChanged(); }, "show")),
        slider("x", "Across"), slider("y", "Down"), slider("w", "Width"));
    }
    if (kind === "subtitle") box.append(h("div", { class: "row" }, h("button", { text: "Merge with next", onclick: () => { if (mergeCaption(edit, clip.id)) edChanged(); } })));
    box.append(h("div", { class: "row" },
      h("button", { text: "Cut at playhead (⌘B)", onclick: edBladePlayhead }),
      h("button", { text: "Unlink (⌘L)", disabled: !clip.link || null, onclick: edLink }),
      h("button", { class: "ghost", text: "Delete (⌫)", onclick: () => edDelete(false) }),
      h("button", { class: "ghost", text: "Ripple delete (⇧⌫)", onclick: () => edDelete(true) })));
    if (kind === "subtitle") { box.append(h("hr")); edCaptionStyle(box, edit); }
    return;
  }
  const track = ed.track && trackOf(edit, ed.track);
  if (track) {
    const name = h("input", { type: "text", value: track.name, maxlength: "60" });
    name.addEventListener("change", () => { const text = cleanName(name.value, 60); if (text) { track.name = text; edChanged(); } });
    box.append(h("h5", { text: ED_KIND_NAME[track.kind] + " track" }), prow("Name", name));
    if (track.kind === "audio") {
      const [volume, label] = edVolume(track.volume, (value) => { track.volume = Math.max(0, Math.min(4, value)); edChanged(); });
      box.append(prow("Volume", volume, label), prow("Mute", studioCheck(track.muted, () => edToggleTrack(track.id, "muted"), "silent")), prow("Solo", studioCheck(track.solo, () => edToggleTrack(track.id, "solo"), "only solo tracks play")));
    } else box.append(prow("Hidden", studioCheck(track.hidden, () => edToggleTrack(track.id, "hidden"), "not shown or exported")));
    box.append(prow("Locked", studioCheck(track.locked, () => edToggleTrack(track.id, "locked"), "cuts and ripples leave it alone")));
    if (track.kind === "subtitle") { box.append(h("hr")); edCaptionStyle(box, edit); }
    return;
  }
  box.append(h("h5", { text: "Timeline" }), h("p", { class: "note", text: "Click a clip to change it, a track name for the track. Alt-click picks a picture without its sound. ⌫ deletes and leaves a gap, ⇧⌫ closes it. I and O mark a range: ' takes it out, ; leaves a gap." }));
  edCaptionStyle(box, edit);
}
function edCaptionStyle(box, edit) {
  const style = edit.caption_style;
  const restyle = () => { for (const clip of edit.clips) if (clip.source === "caption") clip.asset = ""; edChanged(); };
  const color = h("input", { type: "color", value: style.color });
  color.addEventListener("change", () => { style.color = color.value; restyle(); });
  const outline = h("input", { type: "color", value: style.outline || "#000000" });
  outline.addEventListener("change", () => { style.outline = outline.value; restyle(); });
  const size = h("input", { type: "range", min: "24", max: "120", step: "2", value: String(style.size) });
  size.addEventListener("input", () => { style.size = Number(size.value); edOverlay(true); });
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

// ---- viewer overlay: the subtitle and texts at the playhead, as the export draws them ----
function edOverlay(force) {
  const box = $("edOver"), project = studio.project, edit = project && project.edit;
  if (!box || !edit) return;
  const caption = captionAt(edit, ed.t), texts = textsAt(edit, ed.t);
  const key = [caption ? caption.id + caption.text : "", ...texts.map((item) => item.id + item.asset + item.x + item.y + item.w)].join("|");
  if (!force && key === ed.overlayKey) return;
  ed.overlayKey = key;
  for (const node of [...box.children]) if (node.id !== "edGap") node.remove();
  const frame = box.getBoundingClientRect();
  const short = Math.min(frame.width, frame.height) || 1;
  if (caption) {
    const style = edit.caption_style, scale = short / 1080;
    const node = h("div", { class: "ecap", text: caption.text });
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
  for (const item of texts) {
    if (!item.asset) continue;
    const img = h("img", { src: projectMedia(project.path, "assets/" + item.asset), alt: "" });
    img.style.left = item.x * 100 + "%";
    img.style.top = item.y * 100 + "%";
    img.style.width = item.w * frame.width + "px";
    box.append(img);
  }
}
// The viewer of an audio project: the sound around the playhead, Voice Memos style.
function edWaveAt(edit, t) {
  let loudest = 0;
  for (const clip of audibleClips(edit)) {
    if (t < clip.start || t >= clipEnd(clip)) continue;
    const at = clip.in + t - clip.start;
    let value = 0;
    if (clip.source === "asset") { const wave = ed.assetPeaks[clip.asset]; if (wave && wave.duration) value = wave.peaks[Math.floor(at / wave.duration * wave.peaks.length)] || 0; }
    else if (ed.rec[clip.source]) value = ed.rec[clip.source][Math.floor(at * ED_RATE)] || 0;
    loudest = Math.max(loudest, value * clip.volume);
  }
  return Math.min(1, loudest);
}
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
  const middle = box.height / 2, pps = box.width / 8, length = edLength(edit);
  context.fillStyle = (styles.getPropertyValue("--ink") || "").trim() || "#ddd";
  for (let x = 0; x < box.width; x += 3) {
    const t = ed.t + (x - box.width / 2) / pps;
    if (t < 0 || t > length) continue;
    const height = Math.max(1.5, edWaveAt(edit, t) * (box.height * 0.42));
    context.globalAlpha = t <= ed.t ? 1 : 0.4;
    context.fillRect(x, middle - height, 2, height * 2);
  }
  context.globalAlpha = 1;
  context.fillStyle = "#ff3b30";
  context.fillRect(Math.round(box.width / 2) - 1, 8, 2, box.height - 16);
}

// ---- timeline drawing: only when something changed; the playhead is its own element ----
function edFitZoom(canvas) {
  return Math.max(0.2, ((canvas.clientWidth || 800) - 30) / Math.max(10, edLength(studio.project.edit) * 1.04));
}
function edGeometry(canvas) {
  if (!ed.zoom) { ed.zoom = edFitZoom(canvas); ed.scroll = 0; }
  return { width: canvas.clientWidth || 800, x: (t) => (t - ed.scroll) * ed.zoom, t: (x) => x / ed.zoom + ed.scroll };
}
function edDraw() {
  cancelAnimationFrame(ed.drawTimer);
  ed.drawTimer = requestAnimationFrame(edPaint);
}
function edPaint() {
  const canvas = $("edTracks"), ruler = $("edRuler"), project = studio.project, edit = project && project.edit;
  if (!canvas || !edit) return;
  const rows = edRowsOf(edit), height = rows.reduce((sum, row) => sum + row.height, 0);
  canvas.style.height = height + "px";
  const ratio = window.devicePixelRatio || 1, g = edGeometry(canvas);
  canvas.width = Math.max(2, Math.round(g.width * ratio));
  canvas.height = Math.max(2, Math.round(height * ratio));
  const c = canvas.getContext("2d");
  const css = getComputedStyle(document.body), v = (name, fallback) => (css.getPropertyValue(name) || "").trim() || fallback;
  const ink = v("--ink", "#ddd"), muted = v("--muted", "#888"), line = v("--line", "#333"), accent = v("--accent", "#ffc933");
  c.scale(ratio, ratio);
  c.clearRect(0, 0, g.width, height);
  const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800];
  const step = steps.find((value) => value * ed.zoom >= 80) || 1800;
  rows.forEach((row, index) => { c.fillStyle = index % 2 ? "rgba(127,127,127,.06)" : "rgba(127,127,127,.02)"; c.fillRect(0, row.y, g.width, row.height); c.fillStyle = line; c.fillRect(0, row.y + row.height - 1, g.width, 1); });
  c.fillStyle = "rgba(127,127,127,.12)";
  for (let t = Math.floor(ed.scroll / step) * step; g.x(t) < g.width; t += step) c.fillRect(Math.round(g.x(t)), 0, 1, height);
  const length = edLength(edit);
  if (ed.in !== null || ed.out !== null) {
    const a = g.x(ed.in ?? 0), b = g.x(ed.out ?? length);
    c.fillStyle = "rgba(120,170,255,.14)";
    c.fillRect(a, 0, Math.max(0, b - a), height);
  }
  const heard = new Set(audibleClips(edit).map((clip) => clip.track));
  c.font = "11px system-ui, sans-serif";
  c.textBaseline = "top";
  for (const row of rows) {
    const track = row.track, dim = track.hidden || (track.kind === "audio" && !heard.has(track.id));
    for (const clip of edit.clips) {
      if (clip.track !== track.id) continue;
      const x1 = g.x(clip.start), x2 = g.x(clipEnd(clip));
      if (x2 < 0 || x1 > g.width) continue;
      const left = Math.max(-4, x1), right = Math.min(g.width + 4, x2), top = row.y + 2, h2 = row.height - 5;
      c.globalAlpha = dim ? 0.38 : 1;
      c.fillStyle = ED_FILL[track.kind];
      c.beginPath(); c.roundRect(left, top, Math.max(1, right - left - 1), h2, 4); c.fill();
      c.save(); c.beginPath(); c.rect(left, top, Math.max(0, right - left - 1), h2); c.clip();
      if (track.kind === "audio") {
        const peaks = clip.source === "asset" ? null : ed.rec[clip.source], wave = clip.source === "asset" ? ed.assetPeaks[clip.asset] : null;
        c.fillStyle = "rgba(255,255,255,.55)";
        const middle = top + h2 * 0.58, scale = h2 * 0.36 * Math.min(2, clip.volume * track.volume);
        for (let x = Math.max(0, left); x < Math.min(g.width, right); x += 2) {
          const at = clip.in + g.t(x) - clip.start;
          const value = peaks ? peaks[Math.floor(at * ED_RATE)] || 0 : wave && wave.duration ? wave.peaks[Math.floor(at / wave.duration * wave.peaks.length)] || 0 : 0;
          const bar = Math.max(0.5, value * scale);
          c.fillRect(x, middle - bar, 1.5, bar * 2);
        }
        c.strokeStyle = "rgba(255,255,255,.8)";
        if (clip.fade_in > 0) { c.beginPath(); c.moveTo(x1, top + h2); c.lineTo(g.x(clip.start + clip.fade_in), top); c.stroke(); }
        if (clip.fade_out > 0) { c.beginPath(); c.moveTo(g.x(clipEnd(clip) - clip.fade_out), top); c.lineTo(x2, top + h2); c.stroke(); }
      }
      c.fillStyle = "#fff";
      const label = clip.source === "recording" ? "Recording · " + sceneName(sceneAt(project, clip.in)) : clip.source === "asset" ? clip.name || clip.asset : clip.text || ED_SOURCE_NAME[clip.source];
      c.fillText((clip.link ? "⧉ " : "") + label, Math.max(left, 0) + 5, top + 3);
      c.restore();
      if (ed.sel.has(clip.id)) { c.globalAlpha = 1; c.strokeStyle = accent; c.lineWidth = 2; c.beginPath(); c.roundRect(left + 1, top + 1, Math.max(1, right - left - 3), h2 - 2, 4); c.stroke(); c.lineWidth = 1; }
    }
  }
  c.globalAlpha = 1;
  if (ruler) {
    ruler.width = Math.max(2, Math.round(g.width * ratio));
    ruler.height = Math.round(26 * ratio);
    const r = ruler.getContext("2d");
    r.scale(ratio, ratio);
    r.clearRect(0, 0, g.width, 26);
    r.font = "10px ui-monospace, Menlo, monospace";
    r.textBaseline = "top";
    r.fillStyle = muted;
    for (let t = Math.floor(ed.scroll / step) * step; g.x(t) < g.width; t += step) {
      const x = Math.round(g.x(t));
      if (x < 0) continue;
      r.fillRect(x, 14, 1, 12);
      r.fillText(step < 1 ? edTimecode(t) : clockText(t), x + 3, 2);
      for (let k = 1; k < 5; k++) r.fillRect(Math.round(g.x(t + step * k / 5)), 21, 1, 5);
    }
    if (ed.in !== null || ed.out !== null) { r.fillStyle = "rgba(120,170,255,.45)"; const a = g.x(ed.in ?? 0), b = g.x(ed.out ?? length); r.fillRect(a, 20, Math.max(2, b - a), 6); }
    r.fillStyle = ink;
    for (const mark of edMarks(project, edit)) { const x = g.x(mark); r.beginPath(); r.moveTo(x - 4, 14); r.lineTo(x + 4, 14); r.lineTo(x, 20); r.fill(); }
  }
  const range = $("edRange");
  if (range) range.textContent = ed.in !== null || ed.out !== null ? "In " + clockText(ed.in ?? 0) + " · Out " + clockText(ed.out ?? length) + " (' takes it out, ; leaves a gap, ⌥X clears)" : "";
  edPlayhead();
}
// Recording marks where they are on the timeline (through the clips that show them).
function edMarks(project, edit) {
  const out = [];
  for (const event of project.events || []) {
    if (!("mark" in event)) continue;
    const clip = edit.clips.find((item) => (item.source === "recording" || item.source === "mic") && event.t >= item.in && event.t < item.out);
    if (clip) out.push(clip.start + event.t - clip.in);
  }
  return out;
}
function edPlayhead() {
  const node = $("edHead"), canvas = $("edTracks");
  if (node && canvas) {
    const x = (ed.t - ed.scroll) * ed.zoom;
    node.style.display = x < 0 || x > (canvas.clientWidth || 800) ? "none" : "block";
    node.style.left = ED_HEAD + x + "px";
  }
  edClock();
}
function edFollow() {
  const canvas = $("edTracks");
  if (!canvas || !ed.zoom) return;
  const visible = (canvas.clientWidth || 800) / ed.zoom;
  if (ed.t > ed.scroll + visible * 0.94 || ed.t < ed.scroll) { ed.scroll = Math.max(0, ed.t - visible * 0.1); edDraw(); }
}

// ---- timeline pointer: select, move, trim, blade, scrub; media dropped from the pool ----
function edHit(edit, canvas, event) {
  const box = canvas.getBoundingClientRect(), x = event.clientX - box.left, y = event.clientY - box.top;
  const rows = edRowsOf(edit), index = rows.findIndex((item) => y >= item.y && y < item.y + item.height);
  const g = edGeometry(canvas), t = g.t(x);
  const row = index >= 0 ? rows[index] : null;
  if (!row) return { t, row: null, index, clip: null };
  const edge = 7 / ed.zoom;
  const near = edit.clips.filter((item) => item.track === row.track.id && t >= item.start - edge && t <= clipEnd(item) + edge);
  const clip = near.find((item) => t >= item.start && t <= clipEnd(item)) || near[0] || null;
  if (!clip) return { t, row, index, clip: null };
  let side = "body";
  if ((clipEnd(clip) - clip.start) * ed.zoom > 16) side = Math.abs(t - clip.start) <= edge ? "start" : Math.abs(t - clipEnd(clip)) <= edge ? "end" : "body";
  if (side === "body" && !(t >= clip.start && t <= clipEnd(clip))) return { t, row, index, clip: null };
  return { t, row, index, clip, side };
}
function edSnapTargets(edit, except) {
  if (!ed.snap) return [];
  return [ed.t, ...(ed.in !== null ? [ed.in] : []), ...(ed.out !== null ? [ed.out] : []), ...edEdges(edit, except), ...edMarks(studio.project, edit)];
}
function edDragLoop(onmove, onup) {
  const move = (event) => { if (event.buttons === 0) { up(); return; } onmove(event); };
  const up = () => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); removeEventListener("pointercancel", up); if (onup) onup(); };
  addEventListener("pointermove", move); addEventListener("pointerup", up); addEventListener("pointercancel", up);
}
function edRulerEvents(ruler) {
  ruler.addEventListener("pointerdown", (event) => {
    if (!studio.project || event.button !== 0) return;
    const scrub = (moved) => { const box = ruler.getBoundingClientRect(); edSeek((moved.clientX - box.left) / ed.zoom + ed.scroll); };
    scrub(event);
    edDragLoop(scrub);
  });
}
function edTrackEvents(canvas) {
  canvas.addEventListener("wheel", (event) => {
    const edit = studio.project && studio.project.edit;
    if (!edit) return;
    if (!event.ctrlKey && !event.metaKey && !event.altKey && Math.abs(event.deltaY) > Math.abs(event.deltaX) && !event.shiftKey) return;  // the wheel scrolls the tracks up and down
    event.preventDefault();
    const box = canvas.getBoundingClientRect();
    if (event.ctrlKey || event.metaKey || event.altKey) {
      const at = (event.clientX - box.left) / ed.zoom + ed.scroll;
      ed.zoom = Math.max(0.2, Math.min(2000, ed.zoom * Math.exp(-event.deltaY * 0.01)));
      ed.scroll = Math.max(0, at - (event.clientX - box.left) / ed.zoom);
    } else ed.scroll = Math.max(0, ed.scroll + (event.deltaX || event.deltaY) / ed.zoom);
    edDraw();
  }, { passive: false });
  canvas.addEventListener("pointermove", (event) => {
    if (ed.drag || !studio.project || !studio.project.edit) return;
    const hit = edHit(studio.project.edit, canvas, event);
    canvas.style.cursor = ed.tool === "blade" && hit.clip ? "crosshair" : hit.clip && hit.side !== "body" ? "ew-resize" : hit.clip ? "grab" : "default";
  });
  canvas.addEventListener("dragover", (event) => { if (event.dataTransfer && [...(event.dataTransfer.types || [])].includes("application/x-unlaw-edit")) event.preventDefault(); });
  canvas.addEventListener("drop", (event) => {
    const edit = studio.project && studio.project.edit, raw = event.dataTransfer && event.dataTransfer.getData("application/x-unlaw-edit");
    if (!edit || !raw) return;
    event.preventDefault();
    let payload;
    try { payload = JSON.parse(raw); } catch (error) { return; }
    const hit = edHit(edit, canvas, event);
    edDrop(payload, snapTime(Math.max(0, hit.t), edSnapTargets(edit), 8 / ed.zoom), hit.row ? hit.row.track : null);
  });
  canvas.addEventListener("dblclick", (event) => {
    const edit = studio.project && studio.project.edit, hit = edit && edHit(edit, canvas, event);
    const area = hit && hit.clip && (hit.clip.source === "text" || hit.clip.source === "caption") && $("edInspect") && $("edInspect").querySelector("textarea");
    if (area) area.focus();
  });
  canvas.addEventListener("contextmenu", (event) => {
    const edit = studio.project && studio.project.edit, hit = edit && edHit(edit, canvas, event);
    if (!hit || !hit.clip) return;
    if (!ed.sel.has(hit.clip.id)) { ed.sel = new Set(ed.linked && !event.altKey ? linkedIds(edit, [hit.clip.id]) : [hit.clip.id]); edDraw(); renderEditSide(); }
    const linked = selIds().some((id) => (edit.clips.find((clip) => clip.id === id) || {}).link);
    contextMenu(event, [
      ["Cut at the playhead (⌘B)", edBladePlayhead],
      ["Delete, leave a gap (⌫)", () => edDelete(false)],
      ["Ripple delete (⇧⌫)", () => edDelete(true)],
      "-",
      [linked ? "Unlink picture and sound (⌘L)" : "Link (⌘L)", edLink],
      hit.clip.source === "caption" ? ["Merge with the next line", () => { if (mergeCaption(edit, hit.clip.id)) edChanged(); }] : null,
    ]);
  });
  canvas.addEventListener("pointerdown", (event) => {
    const project = studio.project, edit = project && project.edit;
    if (!edit || event.button !== 0) return;
    const hit = edHit(edit, canvas, event);
    if (ed.tool === "blade" && hit.clip) {
      const at = snapTime(hit.t, ed.snap ? [ed.t] : [], 8 / ed.zoom);
      const ids = ed.linked && !event.altKey ? linkedIds(edit, [hit.clip.id]) : [hit.clip.id];
      if (bladeAt(edit, at, ids)) edChanged(); else toast("Too close to the clip's edge");
      return;
    }
    if (!hit.clip) {
      // An empty place: deselect and move the playhead there (drag to scrub).
      ed.sel = new Set();
      if (hit.row) ed.track = hit.row.track.id;
      edSeek(hit.t);
      edHeads(); edDraw(); renderEditSide();
      edDragLoop((moved) => { const box = canvas.getBoundingClientRect(); edSeek((moved.clientX - box.left) / ed.zoom + ed.scroll); });
      return;
    }
    const clip = hit.clip;
    const group = ed.linked && !event.altKey ? linkedIds(edit, [clip.id]) : [clip.id];
    if (event.shiftKey || event.metaKey) {
      const next = new Set(ed.sel), on = !next.has(clip.id);
      for (const id of group) if (on) next.add(id); else next.delete(id);
      ed.sel = next;
    } else if (!ed.sel.has(clip.id)) ed.sel = new Set(group);
    ed.track = null;
    edHeads(); edDraw(); renderEditSide();
    const before = JSON.stringify(edit.clips), startX = event.clientX, startY = event.clientY, startRow = hit.index;
    let moved = false;
    ed.drag = true;
    edDragLoop((pointer) => {
      if (!moved && Math.hypot(pointer.clientX - startX, pointer.clientY - startY) < 3) return;
      moved = true;
      edit.clips = JSON.parse(before);
      const delta = (pointer.clientX - startX) / ed.zoom, tolerance = 8 / ed.zoom;
      if (hit.side !== "body") {
        const edge = hit.side === "start" ? clip.start : clipEnd(clip);
        trimClip(edit, clip.id, hit.side, snapTime(edge + delta, edSnapTargets(edit, new Set(group)), tolerance), project, ed.linked && !event.altKey);
      } else {
        const ids = selIds();
        const moving = edit.clips.filter((item) => ids.includes(item.id));
        const first = Math.min(...moving.map((item) => item.start)), last = Math.max(...moving.map(clipEnd));
        const targets = edSnapTargets(edit, new Set(ids));
        let dt = delta;
        const a = snapTime(first + delta, targets, tolerance), b = snapTime(last + delta, targets, tolerance);
        if (a !== first + delta) dt = a - first; else if (b !== last + delta) dt = b - last;
        const rows = edRowsOf(edit), now = edHit(edit, canvas, pointer).index;
        const rowDelta = startRow >= 0 && now >= 0 ? edit.tracks.indexOf(rows[now].track) - edit.tracks.indexOf(rows[startRow].track) : 0;
        if (!moveClips(edit, ids, dt, rowDelta)) { edit.clips = JSON.parse(before); moveClips(edit, ids, dt, 0); }
      }
      edDraw();
      edOverlay();
    }, () => {
      ed.drag = null;
      if (JSON.stringify(edit.clips) !== before) edChanged();
      else if (!moved && clip.source !== "caption") edSeek(hit.t);
    });
  });
}
// Media from the pool onto the timeline at t (onto the given track when it fits).
function edDrop(payload, t, track) {
  const project = studio.project, edit = project && project.edit;
  if (!edit || !payload) return;
  const fits = (kind) => track && track.kind === kind && !track.locked;
  const where = {};
  if ((payload.kind === "recording" || payload.kind === "picture") && fits("video")) where.video = track.id;
  if (payload.kind === "mic" && fits("audio")) where.mic = track.id;
  if (payload.kind === "system" && fits("audio")) where.system = track.id;
  if (payload.kind === "text" && fits("text")) where.track = track.id;
  if (payload.kind === "asset") {
    Object.assign(where, { asset: payload.asset, name: payload.name, length: (ed.assetPeaks[payload.asset] && ed.assetPeaks[payload.asset].duration) || 10 });
    if (fits("audio")) where.track = track.id;
  }
  const ids = insertMedia(edit, project, payload.kind, t, where);
  if (!ids.length) { toast("Nothing to add"); return; }
  ed.sel = new Set(ids);
  edLoadSounds(project);
  edChanged();
}

// ---- actions ----
function edSetTool(tool) {
  ed.tool = tool;
  const root = $("edRoot");
  if (root && root.querySelectorAll) for (const button of root.querySelectorAll(".tools button")) button.classList.toggle("on", button.textContent === (tool === "blade" ? "Blade" : "Select"));
}
function edToggleSnap() { ed.snap = !ed.snap; localStorage.setItem("edit-snap", ed.snap ? "on" : "off"); renderEdit(); toast(ed.snap ? "Snapping on" : "Snapping off"); }
function edToggleLinked() { ed.linked = !ed.linked; localStorage.setItem("edit-linked", ed.linked ? "on" : "off"); renderEdit(); toast(ed.linked ? "Linked selection on" : "Linked selection off: picture and sound are picked apart"); }
function edBladePlayhead() {
  const edit = studio.project && studio.project.edit;
  if (!edit) return;
  const ids = selIds();
  const count = bladeAt(edit, ed.t, ids.length ? (ed.linked ? linkedIds(edit, ids) : ids) : null);
  if (count) edChanged(); else toast("Put the playhead inside a clip to cut");
}
function edDelete(ripple) {
  const edit = studio.project && studio.project.edit;
  if (!edit) return;
  if (ed.in !== null || ed.out !== null) {
    const a = ed.in ?? 0, b = ed.out ?? edLength(edit);
    if (ripple ? extractRange(edit, a, b) : liftRange(edit, a, b)) { ed.in = ed.out = null; ed.sel = new Set(); ed.t = a; edChanged(); edSeek(a); }
    return;
  }
  const ids = selIds();
  if (!ids.length) { toast("Select a clip, or mark a range with I and O"); return; }
  if (!(ripple ? rippleDelete(edit, ids) : liftClips(edit, ids))) { toast("Its track is locked"); return; }
  ed.sel = new Set();
  edChanged();
  edSeek(ed.t);
}
function edLink() {
  const edit = studio.project && studio.project.edit;
  if (!edit) return;
  const result = toggleLink(edit, selIds());
  if (!result) { toast("Select two clips or more to link them"); return; }
  if (result === "unlinked") ed.sel = new Set(selIds().slice(0, 1));
  edChanged();
  toast(result === "linked" ? "Linked: they move and cut together" : "Unlinked: picture and sound are separate now");
}
function edEdgeJump(direction) {
  const edges = [...new Set(edEdges(studio.project.edit).map(round3))].sort((a, b) => a - b);
  const next = direction > 0 ? edges.find((t) => t > ed.t + 0.01) : [...edges].reverse().find((t) => t < ed.t - 0.01);
  if (next !== undefined) edSeek(next);
}
function edRemoveSilences() {
  const project = studio.project, edit = project && project.edit;
  const peaks = ed.rec.mic || ed.rec.system;
  if (!edit || !peaks) return;
  const removed = removeSilences(edit, project, peaks);
  if (!removed) { toast("No pauses longer than 0.6 s"); return; }
  edChanged();
  toast("Removed " + clockText(removed) + " of pauses (⌘Z brings them back)");
}
function edAddText() {
  const project = studio.project, edit = project && project.edit;
  if (!edit) return;
  if (edit.clips.filter((clip) => clip.source === "text").length >= 500) { toast("At most 500 texts"); return; }
  ed.sel = new Set(insertMedia(edit, project, "text", ed.t, {}));
  edChanged();
}
async function edTranscribe() {
  const project = studio.project, edit = project && project.edit;
  if (!edit || ed.busy) return;
  const existing = edit.clips.filter((clip) => clip.source === "caption").length;
  if (existing && !confirm("Replace the " + existing + " subtitle lines with a new transcription?")) return;
  ed.busy = "transcribe";
  edPool();
  toast("Listening to the recording on this Mac… (a long recording takes a few minutes)");
  const { status, data } = await api("POST", "/api/studio/transcribe", { path: project.path, language: ed.language, model: ed.model });
  ed.busy = "";
  if (studio.project !== project) return;
  if (status !== 200) { toast(data.error || "Transcription failed"); edPool(); return; }
  const count = captionsToClips(edit, project, data.captions || []);
  toast(count ? count + " subtitle lines" + (data.language ? " (" + data.language + ")" : "") : "No speech found");
  edChanged();
}
async function edImportFile(file) {
  const project = studio.project;
  if (!project || !project.edit) return;
  toast("Adding " + file.name + "…");
  let response, data = {};
  try {
    response = await fetch("/api/studio/project/asset?path=" + encodeURIComponent(project.path) + "&name=" + encodeURIComponent(file.name), { method: "POST", headers: { "X-Desk-Token": TOKEN }, body: file });
    data = await response.json();
  } catch (error) { data = { error: "Could not reach the desk: " + error.message }; }
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
  const project = studio.project;
  delete ed.assetPeaks[asset];
  await edAssetPeaks(project, asset);
  if (studio.project !== project) return;
  ed.imported.push({ asset, name: name.slice(0, 200) || "Sound" });
  edDrop({ kind: "asset", asset, name }, ed.t, null);
}

// ---- drawing captions and texts for the export (PNG into the project's assets/) ----
function edDrawText(text, options) {
  const scale = 2, size = options.size * scale;
  const measure = document.createElement("canvas").getContext("2d");
  const font = "700 " + size + "px " + (ED_FONT_CSS[options.font] || "system-ui");
  measure.font = font;
  const limit = options.wrap * scale, lines = [];
  let current = "";
  for (const word of text.split(/\s+/)) {
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
// Every subtitle and text has a current PNG; returns false when one could not be drawn.
async function edEnsureAssets() {
  const project = studio.project, edit = project && project.edit;
  if (!edit || edit.version !== 2) return true;
  let changed = false, ok = true;
  const style = edit.caption_style;
  for (const clip of edit.clips) {
    if (clip.source !== "caption" && clip.source !== "text") continue;
    const name = clip.source === "caption" ? captionAssetName(clip.text, style) : textAssetName(clip);
    if (clip.asset === name || (clip.asset && clip.asset.startsWith(name.slice(0, -4) + " "))) continue;
    const blob = clip.source === "caption"
      ? await edDrawText(clip.text, { size: style.size, font: style.font, color: style.color, outline: style.outline, box: style.box, wrap: 900 })
      : await edDrawText(clip.text, { size: 120, font: "system-ui", color: clip.color || "#ffffff", outline: "", box: clip.background || false, wrap: 4000 });
    const asset = blob && await edUpload(project, name, blob);
    if (studio.project !== project) return false;
    if (asset) { clip.asset = asset; changed = true; } else ok = false;
  }
  if (changed) { studio.historyLast = JSON.stringify(project); saveProjectSoon(); edOverlay(true); }
  return ok;
}
function edScheduleAssets() {
  clearTimeout(ed.assetTimer);
  ed.assetTimer = setTimeout(edEnsureAssets, 1200);
}
async function edExport() {
  const project = studio.project;
  if (!project || ed.busy) return;
  edPause();
  ed.busy = "export";
  renderEdit();
  const ok = await edEnsureAssets();
  if (studio.projectTimer) await flushProject();
  ed.busy = "";
  renderEdit();
  if (!ok) { toast("Some subtitles or texts could not be drawn; try again"); return; }
  renderExportDialog(project);
}

// ---- keys: Resolve's and Premiere's where they agree ----
function editKeydown(event) {
  const edit = studio.project && studio.project.edit;
  if (!edit) return false;
  if (event.key === "Escape" && studio.menu) { closeStudioMenu(); return true; }
  const meta = event.metaKey || event.ctrlKey;
  const zoom = (factor) => { ed.zoom = Math.max(0.2, Math.min(2000, (ed.zoom || 1) * factor)); edDraw(); };
  if (meta && (event.code === "Equal" || event.code === "Minus")) { zoom(event.code === "Equal" ? 1.5 : 1 / 1.5); return true; }
  if (meta && (event.code === "KeyB" || event.code === "KeyK")) { edBladePlayhead(); return true; }
  if (meta && event.code === "KeyL") { if (event.shiftKey) edToggleLinked(); else edLink(); return true; }
  if (meta && event.code === "KeyA") { ed.sel = new Set(edit.clips.filter((clip) => !trackLocked(edit, clip.track)).map((clip) => clip.id)); edDraw(); renderEditSide(); return true; }
  if (event.altKey && event.code === "KeyX") { ed.in = ed.out = null; edDraw(); return true; }
  if (meta || event.altKey) return false;
  switch (event.code) {
    case "Space": edToggle(); return true;
    case "KeyK": if (ed.playing) edPause(); return true;
    case "KeyL": if (!ed.playing) edPlay(); return true;
    case "KeyJ": edSeek(ed.t - 5); return true;
    case "ArrowLeft": edSeek(ed.t - (event.shiftKey ? 1 : 1 / 30)); return true;
    case "ArrowRight": edSeek(ed.t + (event.shiftKey ? 1 : 1 / 30)); return true;
    case "ArrowUp": edEdgeJump(-1); return true;
    case "ArrowDown": edEdgeJump(1); return true;
    case "Home": edSeek(0); return true;
    case "End": edSeek(edLength(edit)); return true;
    case "KeyA": case "KeyV": edSetTool("select"); return true;
    case "KeyB": edSetTool("blade"); return true;
    case "Delete": edDelete(true); return true;
    case "Backspace": edDelete(event.shiftKey); return true;
    case "Quote": if (ed.in !== null || ed.out !== null) edDelete(true); return true;
    case "Semicolon": if (ed.in !== null || ed.out !== null) edDelete(false); return true;
    case "KeyI": ed.in = round3(ed.t); if (ed.out !== null && ed.out <= ed.in) ed.out = null; edDraw(); return true;
    case "KeyO": ed.out = round3(ed.t); if (ed.in !== null && ed.in >= ed.out) ed.in = null; edDraw(); return true;
    case "KeyN": edToggleSnap(); return true;
    case "KeyZ": if (event.shiftKey) { ed.zoom = 0; edDraw(); return true; } return false;
    case "Equal": zoom(1.5); return true;
    case "Minus": zoom(1 / 1.5); return true;
    case "KeyT": edAddText(); return true;
    case "Escape": ed.sel = new Set(); ed.track = null; edHeads(); renderEditSide(); edDraw(); return true;
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
  const ink = (css.getPropertyValue("--ink") || "").trim() || "#ddd", muted = (css.getPropertyValue("--muted") || "").trim() || "#888";
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
