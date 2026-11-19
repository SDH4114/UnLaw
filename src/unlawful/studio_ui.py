"""The Studio tab of the `ul desk` page: its CSS and JS, injected into desk_ui.PAGE.

Device names, project names and texts are user data, so nodes are built with textContent, never innerHTML.
"""

from __future__ import annotations

STUDIO_CSS = r""".studio { display: grid; grid-template-columns: 300px 1fr; gap: 14px; padding: 14px 16px 16px; min-height: 100%; align-items: start; }
.controls { position: sticky; top: 14px; display: flex; flex-direction: column; gap: 9px; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); padding: 12px 14px 14px; }
.controls h4 { margin: 8px 0 0; font-size: 12px; font-weight: 650; color: var(--muted); }
.controls label { display: grid; gap: 3px; font-size: 12px; color: var(--muted); }
.controls label.check { display: flex; align-items: center; gap: 7px; color: var(--text); font-size: 13px; }
.controls select { width: 100%; }
.modes { grid-template-columns: repeat(2, 1fr); }
.recbox { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 12px 0 4px; }
.recbtn { width: 64px; height: 64px; border-radius: 50%; border: 3px solid var(--line); background: var(--panel); display: grid; place-items: center; padding: 0; }
.recbtn i { width: 26px; height: 26px; border-radius: 50%; background: #e5484d; transition: border-radius .15s, width .15s, height .15s; }
.recbtn.on i { width: 22px; height: 22px; border-radius: 5px; }
.recbtn:hover { border-color: #e5484d; }
.recclock { font: 600 22px var(--mono); letter-spacing: .02em; }
.recclock.live { color: #e5484d; }
.recstate { font-size: 12px; color: var(--muted); text-align: center; min-height: 16px; }
.row { display: flex; gap: 6px; flex-wrap: wrap; }
.row button { flex: 1; }
.monitor { position: relative; background: #0c0c0b; border-radius: var(--radius); aspect-ratio: 16 / 10; max-height: 58vh; width: 100%; overflow: hidden; display: grid; place-items: center; box-shadow: var(--shadow); }
.monitor img.screen { width: 100%; height: 100%; object-fit: contain; }
.monitor video.cam { position: absolute; width: 24%; border-radius: 10px; box-shadow: 0 4px 18px rgba(0,0,0,.5); background: #000; transform: scaleX(-1); }
.monitor video.cam.full { position: static; width: 100%; height: 100%; object-fit: contain; border-radius: 0; box-shadow: none; }
.monitor video.cam.bottom-right { right: 3%; bottom: 4%; } .monitor video.cam.bottom-left { left: 3%; bottom: 4%; }
.monitor video.cam.top-right { right: 3%; top: 4%; } .monitor video.cam.top-left { left: 3%; top: 4%; }
.monitor .note { color: #8b8f98; text-align: center; padding: 20px; font-size: 13px; }
.monitor .meter { width: 70%; height: 14px; border-radius: 7px; background: #23262d; overflow: hidden; }
.monitor .meter i { display: block; height: 100%; width: 0; background: linear-gradient(90deg, #3ed67a, #ffd84d 75%, #ff5f57); transition: width .06s linear; }
.monitor .badge { position: absolute; left: 12px; top: 12px; background: rgba(229,72,77,.92); color: #fff; font: 600 12px var(--mono); padding: 3px 9px; border-radius: 999px; display: none; }
.monitor .badge.on { display: block; }
.monitor .badge.paused { background: rgba(120,120,128,.9); }
.monbar { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin: 8px 0 4px; }
.monbar .hint { color: var(--muted); font-size: 12px; flex: 1; }
.libhead { display: flex; align-items: center; gap: 10px; margin: 16px 0 8px; }
.libhead h3 { margin: 0; font-size: 13px; font-weight: 650; color: var(--muted); }
.libhead .levels { grid-template-columns: repeat(4, auto); }
.libhead .levels button { padding: 3px 10px; }
.library { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 10px; }
.item { background: var(--panel); border-radius: 8px; box-shadow: var(--shadow); overflow: hidden; cursor: pointer; border: 1px solid var(--line); text-align: left; padding: 0; display: flex; flex-direction: column; }
.item:hover { border-color: var(--accent); box-shadow: var(--lift); }
.item .pic { aspect-ratio: 16 / 10; background: #15171c center / cover no-repeat; display: grid; place-items: center; color: #8b8f98; position: relative; }
.item .pic img { width: 100%; height: 100%; object-fit: cover; }
.item .pic .len { position: absolute; right: 6px; bottom: 6px; background: rgba(0,0,0,.7); color: #fff; font: 11px var(--mono); padding: 1px 6px; border-radius: 5px; }
.item .pic svg { width: 34px; height: 34px; stroke: #8b8f98; fill: none; stroke-width: 1.6; }
.item .cap { padding: 7px 9px 8px; font-size: 12px; }
.item .cap b { display: block; font-weight: 550; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item .cap span { color: var(--muted); }
.rec-pill { display: none; border: none; background: rgba(229,72,77,.12); color: #e5484d; font: 600 12px var(--mono); border-radius: 999px; padding: 4px 10px; }
.rec-pill.on { display: inline-flex; gap: 6px; align-items: center; }
.rec-pill.on::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: #e5484d; animation: blink 1.2s infinite; }
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
.voice { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: stretch; justify-content: center; gap: 10px; padding: 18px; }
.voice-clock { font: 600 34px var(--mono); color: #f2f2f7; text-align: center; letter-spacing: .02em; }
.voice .note { position: static; }
canvas.wave { width: 100%; height: 46%; display: block; }
canvas.wave.strip { position: absolute; left: 0; right: 0; bottom: 0; height: 64px; background: linear-gradient(transparent, rgba(0,0,0,.55)); }
#viewer canvas.filewave { width: 100%; height: 96px; display: block; cursor: pointer; background: #0c0c0b; border-radius: 12px; }
@media (max-width: 860px) { .studio { grid-template-columns: 1fr; } .controls { position: static; } }
"""

STUDIO_JS = r"""// ---- studio: recording, screenshots and the library through `ul capture` ----
const studio = { info: null, devices: null, status: { active: false }, statusAt: 0, library: [], filter: localStorage.getItem("studio-filter") || "all", mode: localStorage.getItem("studio-mode") || "screen", display: 1, mic: "", cam: "", system: null, clicks: null, format: "", delay: 0, clipboard: false, preview: localStorage.getItem("studio-preview") !== "off", previewBusy: false, previewTimer: 0, camStream: null, micStream: null, audio: null, saving: false, item: null, trim: { from: null, to: null }, starting: 0, shown: 0, levels: [], analyser: null, sampler: 0, wave: null };
const media = (path, name) => path + "?t=" + encodeURIComponent(TOKEN) + (name ? "&name=" + encodeURIComponent(name) : "");

async function loadStudioInfo() {
  const { status, data } = await api("GET", "/api/studio");
  if (status !== 200) return;
  studio.info = data;
  if (data.available) loadRecordStatus();
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
    else { toast("Saved " + data.saving_done.saved.split("/").pop()); loadLibrary(true); }
  }
  if (was.active && !data.active && !studio.saving) loadLibrary();
  if (!data.active) for (const item of studio.levels) item.live = false;
  drawRecording();
  if (state.view === "studio") {
    updateStudioControls();
    // Started or finished (maybe from the terminal): bring the preview back or pause it.
    if (Boolean(was.active) !== Boolean(data.active) && !studio.starting) renderMonitor();
  }
  if ((data.active || studio.saving) && !busyTimer) pollWhileBusy();
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
  const live = Boolean(studio.starting) || (s.active && s.phase === "recording");
  const active = s.active || studio.saving || Boolean(studio.starting);
  pill.className = "rec-pill" + (active ? " on" : "") + (s.paused ? " paused" : "");
  pill.textContent = studio.saving || s.phase === "saving" ? "Saving…" : active ? (s.paused ? "Paused " : "REC ") + clockText(recordElapsed()) : "";
  const clock = $("recClock");
  if (clock) {
    clock.textContent = clockText(recordElapsed());
    clock.classList.toggle("live", live);
  }
  const badge = $("monBadge");
  if (badge) {
    badge.className = "badge" + (active && !studio.saving ? " on" : "") + (s.paused ? " paused" : "");
    badge.textContent = s.paused ? "❚❚ PAUSED " + clockText(recordElapsed()) : "● REC " + clockText(recordElapsed());
  }
  const waveClock = $("waveClock");
  if (waveClock) waveClock.textContent = clockText(recordElapsed());
}

async function loadDevices() {
  const { status, data } = await api("GET", "/api/studio/devices");
  if (status !== 200) { toast(data.error || "Could not list devices"); return; }
  studio.devices = data;
  if (state.view === "studio") renderStudioControls();
}

async function loadLibrary(openNewest) {
  const { status, data } = await api("GET", "/api/studio/library");
  if (status !== 200) return;
  studio.library = data;
  if (state.view === "studio") renderLibrary();
  if (openNewest && data.length) openViewer(data[0]);
}

function leaveStudio() {
  clearTimeout(studio.previewTimer);
  stopStream("camStream");
  stopStream("micStream");
  closeViewer();
}

function stopStream(key) {
  const request = key === "camStream" ? "camRequest" : "micRequest";
  studio[request] = (studio[request] || 0) + 1;
  if (studio[key]) { studio[key].getTracks().forEach((track) => track.stop()); studio[key] = null; }
  if (key === "micStream") {
    clearInterval(studio.sampler);
    studio.analyser = null;
    if (studio.audio) { studio.audio.close(); studio.audio = null; }
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

// The live microphone: bars scroll left into a playhead, red for what is being recorded.
function drawWave() {
  const canvas = $("wave");
  if (!canvas) return;
  const [context, width, height] = fitCanvas(canvas);
  const step = 5, head = Math.round(width * (canvas.classList.contains("strip") ? 0.97 : 0.72));
  context.fillStyle = "rgba(255,255,255,.10)";
  context.fillRect(0, height / 2 - 0.5, width, 1);
  const shown = studio.levels.slice(-Math.floor(head / step));
  shown.forEach((item, index) => bars(context, head - (shown.length - index) * step, height, item.v, 3, item.live ? "#ff453a" : "#8e8e93"));
  const recording = Boolean(studio.starting || (studio.status.active && studio.status.phase === "recording"));
  context.fillStyle = recording ? "#ff453a" : "#ffc933";
  context.fillRect(head, 4, 2, height - 8);
  context.beginPath();
  context.arc(head + 1, 5, 4, 0, Math.PI * 2);
  context.fill();
}

function renderStudio(main) {
  if (!studio.info) { main.textContent = ""; main.append(h("div", { class: "page" }, h("div", { class: "empty", text: "Loading…" }))); loadStudioInfo().then(() => state.view === "studio" && render()); return; }
  if (!studio.info.available) {
    main.textContent = "";
    main.append(h("div", { class: "page" }, h("h3", { text: "Studio" }), h("div", { class: "empty", text: "The capture command is not installed in this ul. Turn on the `capture` feature with: ul features" })));
    return;
  }
  if (main.querySelector(".studio")) return;
  main.textContent = "";
  const monitor = h("div", { class: "monitor", id: "monitor" }, h("span", { class: "badge", id: "monBadge" }));
  const bar = h("div", { class: "monbar" },
    h("button", { id: "togglePreview", onclick: () => { studio.preview = !studio.preview; localStorage.setItem("studio-preview", studio.preview ? "on" : "off"); renderMonitor(); } }),
    h("button", { id: "toggleCam", onclick: toggleCamera }),
    h("button", { id: "toggleMic", onclick: toggleMeter }),
    h("span", { class: "hint", id: "monHint" }),
    h("button", { class: "ghost", text: "Devices ↻", title: "Look for cameras and microphones again", onclick: loadDevices }));
  const filters = h("div", { class: "levels", id: "libFilters" }, [["all", "All"], ["video", "Video"], ["audio", "Audio"], ["image", "Screenshots"]].map(([value, label]) =>
    h("button", { "data-filter": value, text: label, onclick: () => { studio.filter = value; localStorage.setItem("studio-filter", value); renderLibrary(); } })));
  const stage = h("section", {}, monitor, bar,
    h("div", { class: "libhead" }, h("h3", { text: "Library" }), filters, h("span", { class: "spacer" }), h("button", { class: "ghost", text: "Refresh", onclick: () => loadLibrary() })),
    h("div", { class: "library", id: "library" }));
  main.append(h("div", { class: "studio" }, h("aside", { class: "controls", id: "studioControls" }), stage));
  const settings = studio.info.settings;
  if (studio.system === null) studio.system = settings.system_audio;
  if (studio.clicks === null) studio.clicks = settings.show_clicks;
  renderStudioControls();
  renderLibrary();
  renderMonitor();
  if (!studio.devices) loadDevices();
  loadLibrary();
  loadRecordStatus();
}

function field(label, control) { return h("label", {}, label, control); }
function check(label, value, onchange) {
  const input = h("input", { type: "checkbox" });
  input.checked = value;
  input.addEventListener("change", () => onchange(input.checked));
  return h("label", { class: "check" }, input, label);
}
function select(options, value, onchange) {
  const node = h("select", {}, options.map(([v, label]) => h("option", { value: v, text: label, selected: v === value })));
  node.addEventListener("change", () => onchange(node.value));
  return node;
}

function renderStudioControls() {
  const box = $("studioControls");
  if (!box) return;
  box.textContent = "";
  const settings = studio.info.settings, devices = studio.devices;
  const screenMode = studio.mode === "screen" || studio.mode === "screen-camera";
  const cameraMode = studio.mode === "camera" || studio.mode === "screen-camera";
  box.append(h("h4", { text: "Record" }), h("div", { class: "levels modes" }, [["screen", "Screen"], ["screen-camera", "Screen + Cam"], ["camera", "Camera"], ["audio", "Audio"]].map(([value, label]) =>
    h("button", { class: value === studio.mode ? "on" : "", text: label, disabled: studio.status.active, onclick: () => { studio.mode = value; studio.format = ""; localStorage.setItem("studio-mode", value); renderStudioControls(); renderMonitor(); } }))));
  if (screenMode) {
    const displays = devices ? devices.displays.map((item) => [String(item.number), item.number + " · " + item.name]) : [["1", "1 · Main display"]];
    box.append(field("Display", select(displays, String(studio.display), (value) => { studio.display = Number(value); renderMonitor(); })));
  }
  if (cameraMode) {
    const cams = [["", "Default (" + settings.camera_device + ")"], ...(devices ? devices.cameras.map((name) => [name, name]) : [])];
    box.append(field("Camera", select(cams, studio.cam, (value) => { studio.cam = value; if (studio.camStream) { stopStream("camStream"); toggleCamera(); } })));
  }
  const mics = [["", "Default (" + settings.audio_device + ")"], ...(devices ? devices.microphones.map((item) => [item.name, item.name + (item.virtual ? " (virtual)" : "")]) : []), ...(studio.mode === "audio" ? [] : [["none", "No microphone"]])];
  box.append(field("Microphone", select(mics, studio.mic, (value) => { studio.mic = value; const chosen = devices?.microphones.find((item) => item.name === value); if (chosen?.virtual) toast(value + " is virtual: it carries app audio, not your voice"); })));
  if (screenMode) {
    box.append(check("System audio (sound of the Mac)", studio.system, (value) => { studio.system = value; }));
    box.append(check("Show clicks", studio.clicks, (value) => { studio.clicks = value; }));
  }
  const formats = studio.mode === "audio" ? [["", "Default (" + settings.audio_format + ")"], ["m4a", "M4A"], ["mp3", "MP3"], ["wav", "WAV"]] : [["", "Default (" + settings.video_format + ")"], ["mov", "MOV"], ["mp4", "MP4"]];
  box.append(field("Format", select(formats, studio.format, (value) => { studio.format = value; })));
  box.append(h("div", { class: "recbox" },
    h("button", { class: "recbtn" + (studio.status.active ? " on" : ""), id: "recButton", title: "Start / stop recording (r)", onclick: toggleRecord }, h("i")),
    h("span", { class: "recclock", id: "recClock", text: "00:00" }),
    h("div", { class: "row" },
      h("button", { id: "recPause", text: studio.status.paused ? "Resume" : "Pause", disabled: !studio.status.active || studio.saving, onclick: pauseRecord, title: "Pause / resume (p)" })),
    h("div", { class: "recstate", id: "recState" })));
  box.append(h("h4", { text: "Screenshot" }), h("div", { class: "row" },
    ["screen", "area", "window"].map((kind) => h("button", { text: kind[0].toUpperCase() + kind.slice(1), title: kind === "screen" ? "The whole display" : "Select on the Mac with the mouse", onclick: () => takeShot(kind) }))));
  box.append(field("Delay", select([["0", "No delay"], ["3", "3 s"], ["5", "5 s"], ["10", "10 s"]], String(studio.delay), (value) => { studio.delay = Number(value); })));
  box.append(check("Copy to the clipboard instead of saving", studio.clipboard, (value) => { studio.clipboard = value; }));
  updateStudioControls();
}

function updateStudioControls() {
  const s = studio.status;
  const button = $("recButton");
  if (!button) return;
  const active = Boolean(s.active || studio.starting);
  button.classList.toggle("on", active);
  $("recPause").disabled = !s.active || studio.saving || s.phase === "saving" || Boolean(studio.starting);
  $("recPause").textContent = s.paused ? "Resume" : "Pause";
  const what = s.active ? (s.camera ? "screen + camera" : s.mode) : "";
  $("recState").textContent = studio.starting ? "Starting…" : studio.saving || s.phase === "saving" ? "Saving… (adding camera and microphone)" : s.phase === "interrupted" ? "Stopped unexpectedly — press stop to save" : s.phase === "unsaved" ? "Not saved — press stop to try again" : s.active ? (s.paused ? "Paused · " : "Recording ") + what : "Ready";
  for (const node of document.querySelectorAll(".modes button")) node.disabled = active;
  drawRecording();
}

async function toggleRecord() {
  if (studio.saving || studio.starting) return;
  if (studio.status.active) {
    studio.saving = true;
    for (const item of studio.levels) item.live = false;
    updateStudioControls();
    const { status, data } = await api("POST", "/api/studio/stop", {});
    if (status !== 200) { studio.saving = false; toast(data.error || "Could not stop"); }
    pollWhileBusy();
    return;
  }
  const body = { mode: studio.mode, display: studio.display };
  if (studio.mic) body.mic = studio.mic;
  if (studio.cam && (studio.mode === "camera" || studio.mode === "screen-camera")) body.cam = studio.cam;
  if (studio.mode === "screen" || studio.mode === "screen-camera") { body.system_audio = studio.system; body.clicks = studio.clicks; }
  if (studio.format) body.format = studio.format;
  // The page's own camera preview would hold the camera; let ffmpeg have it.
  if (studio.mode !== "screen") stopStream("camStream");
  // Show the recording at once: the recorders start in well under a second,
  // and the server's clock replaces this one when it answers.
  studio.starting = Date.now();
  studio.shown = 0;
  studio.levels = [];
  updateStudioControls();
  if (studio.mode === "audio" && !studio.micStream && studio.mic !== "none") toggleMeter();
  renderMonitor();
  const { status, data } = await api("POST", "/api/studio/record", body);
  studio.starting = 0;
  if (status !== 200) { toast(data.error || "Could not start recording"); await loadRecordStatus(); renderMonitor(); return; }
  for (const warning of data.warnings || []) toast(warning);
  studio.status = data;
  studio.statusAt = Date.now();
  updateStudioControls();
  renderMonitor();
  pollWhileBusy();
}

async function pauseRecord() {
  if (!studio.status.active || studio.saving) return;
  const { status, data } = await api("POST", studio.status.paused ? "/api/studio/resume" : "/api/studio/pause", {});
  if (status !== 200) { toast(data.error || "Could not pause"); return; }
  studio.status = data;
  studio.statusAt = Date.now();
  updateStudioControls();
}

let busyTimer = 0;
function pollWhileBusy() {
  clearTimeout(busyTimer);
  busyTimer = setTimeout(async () => {
    busyTimer = 0;
    await loadRecordStatus();
    if ((studio.status.active || studio.saving) && !busyTimer) pollWhileBusy();
    else updateStudioControls();
  }, studio.saving ? 700 : 1500);
}

async function takeShot(kind) {
  const body = { kind, display: studio.display, delay: studio.delay, clipboard: studio.clipboard };
  if (kind !== "screen") toast("Select on the Mac: drag an area or click a window (Esc cancels)");
  else if (studio.delay) toast("Screenshot in " + studio.delay + " s");
  const { status, data } = await api("POST", "/api/studio/shot", body);
  if (status !== 200) { toast(data.error || "Screenshot failed"); return; }
  if (data.clipboard) { toast("Copied to the clipboard"); return; }
  toast("Saved " + data.saved.split("/").pop());
  loadLibrary(false);
}

function renderMonitor() {
  const monitor = $("monitor");
  if (!monitor) return;
  clearTimeout(studio.previewTimer);
  for (const node of [...monitor.children]) if (node.id !== "monBadge") node.remove();
  const screenMode = studio.mode === "screen" || studio.mode === "screen-camera";
  const cameraMode = studio.mode === "camera" || studio.mode === "screen-camera";
  const recording = Boolean(studio.status.active || studio.starting);
  $("togglePreview").textContent = "Screen preview: " + (studio.preview ? "on" : "off");
  $("togglePreview").style.display = screenMode ? "" : "none";
  $("toggleCam").textContent = studio.camStream ? "Hide camera" : "Show camera";
  $("toggleCam").style.display = cameraMode && !recording ? "" : "none";
  $("toggleMic").textContent = studio.micStream ? "Hide sound" : "Show sound";
  $("monHint").textContent = recording && screenMode ? "Preview paused while recording, so the recording stays smooth." : screenMode ? "The preview refreshes every 2 s; the recording itself is smooth." : studio.mode === "audio" ? "The wave shows how loud the microphone is." : "The camera preview uses the browser; it is released when recording starts.";
  if (screenMode && studio.preview) {
    // A full-screen snapshot every 2 s would compete with the recorder, so it stops while recording.
    const image = h("img", { class: "screen", alt: "" });
    image.addEventListener("error", () => { image.remove(); monitor.prepend(h("div", { class: "note", text: "No preview: give the terminal running ul desk Screen Recording permission (System Settings > Privacy & Security)." })); });
    image.addEventListener("load", () => { if (!studio.status.active && !studio.starting) studio.previewTimer = setTimeout(refresh, 2000); });
    const refresh = () => {
      if (!image.isConnected) return;
      if (state.view === "studio" && !document.hidden && !studio.status.active && !studio.starting) image.src = media("/media/preview") + "&display=" + studio.display + "&_=" + Date.now();
      else studio.previewTimer = setTimeout(refresh, 2000);
    };
    if (recording) image.style.opacity = ".35";
    monitor.append(image);
    if (studio.lastPreview && recording) image.src = studio.lastPreview;
    else refresh();
    image.addEventListener("load", () => { if (!recording) studio.lastPreview = image.src; });
  } else if (screenMode) {
    monitor.append(h("div", { class: "note", text: "Display " + studio.display + " · preview off" }));
  }
  if (cameraMode && studio.camStream && !recording) {
    const video = h("video", { class: "cam " + (studio.mode === "camera" ? "full" : studio.info.settings.overlay), autoplay: true, muted: true, playsinline: true });
    video.muted = true;
    video.srcObject = studio.camStream;
    monitor.append(video);
  } else if (studio.mode === "camera") {
    monitor.append(h("div", { class: "note", text: recording ? "Recording the camera" : "Camera · press “Show camera” for a preview" }));
  }
  if (studio.mode === "audio") {
    monitor.append(h("div", { class: "voice" },
      h("div", { class: "voice-clock", id: "waveClock", text: clockText(recordElapsed()) }),
      h("canvas", { id: "wave", class: "wave" }),
      studio.micStream ? null : h("div", { class: "note", text: "Press “Show sound” (or start recording) to see the microphone" })));
  } else if (studio.micStream) {
    monitor.append(h("canvas", { id: "wave", class: "wave strip" }));
  }
  drawWave();
}

async function toggleCamera() {
  if (studio.camStream) { stopStream("camStream"); renderMonitor(); return; }
  if (state.view !== "studio" || studio.status.active || studio.starting) return;
  const request = studio.camRequest = (studio.camRequest || 0) + 1;
  const current = () => request === studio.camRequest && state.view === "studio" && !studio.status.active && !studio.starting;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: true });
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    if (studio.cam) {
      const found = (await navigator.mediaDevices.enumerateDevices()).find((item) => item.kind === "videoinput" && item.label === studio.cam);
      if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
      if (found) { stream.getTracks().forEach((track) => track.stop()); stream = await navigator.mediaDevices.getUserMedia({ video: { deviceId: { exact: found.deviceId } } }); }
    }
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    studio.camStream = stream;
  } catch (error) { if (stream) stream.getTracks().forEach((track) => track.stop()); toast("The browser could not open the camera: " + error.message); }
  renderMonitor();
}

async function toggleMeter() {
  if (studio.micStream) { stopStream("micStream"); renderMonitor(); return; }
  if (state.view !== "studio") return;
  const request = studio.micRequest = (studio.micRequest || 0) + 1;
  const current = () => request === studio.micRequest && state.view === "studio";
  try {
    const constraints = { audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } };
    if (studio.mic && studio.mic !== "none") {
      // Device labels are only visible after the first permission.
      await navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => stream.getTracks().forEach((track) => track.stop()));
      if (!current()) return;
      const found = (await navigator.mediaDevices.enumerateDevices()).find((item) => item.kind === "audioinput" && item.label.includes(studio.mic));
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
  // Like Voice Memos: one bar per 50 ms, louder = taller, red while recording.
  studio.sampler = setInterval(() => {
    if (!studio.analyser) return;
    studio.analyser.getFloatTimeDomainData(samples);
    let sum = 0, peak = 0;
    for (const value of samples) { sum += value * value; peak = Math.max(peak, Math.abs(value)); }
    const rms = Math.sqrt(sum / samples.length);
    const db = 20 * Math.log10(Math.max(rms * 1.4, peak * 0.6, 1e-5));
    const level = Math.min(1, Math.max(0, (db + 55) / 55)) ** 1.3;
    const s = studio.status;
    studio.levels.push({ v: level, live: Boolean(studio.starting || (s.active && s.phase === "recording")) });
    if (studio.levels.length > 2400) studio.levels.splice(0, 600);
  }, 50);
  renderMonitor();
  const stream = studio.micStream;
  const loop = () => { if (studio.micStream !== stream) return; drawWave(); requestAnimationFrame(loop); };
  loop();
}

const ICONS = { audio: "M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zm12-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0z" };
function sizeText(bytes) { return bytes > 1e9 ? (bytes / 1e9).toFixed(1) + " GB" : bytes > 1e6 ? (bytes / 1e6).toFixed(1) + " MB" : Math.max(1, Math.round(bytes / 1e3)) + " KB"; }

function renderLibrary() {
  const box = $("library");
  if (!box) return;
  for (const button of $("libFilters").children) button.classList.toggle("on", button.dataset.filter === studio.filter);
  box.textContent = "";
  const items = studio.library.filter((item) => studio.filter === "all" || item.kind === studio.filter);
  if (!items.length) { box.append(h("div", { class: "empty", text: studio.library.length ? "Nothing of this kind yet." : "No captures yet. Take a screenshot or start a recording." })); return; }
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
    const convert = select((item.kind === "video" ? [["mp4", "MP4"], ["mov", "MOV"], ["gif", "GIF"], ["m4a", "Audio M4A"], ["mp3", "Audio MP3"]] : [["mp3", "MP3"], ["m4a", "M4A"], ["wav", "WAV"]]).filter(([value]) => !item.name.toLowerCase().endsWith("." + value)), "", () => {});
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
  const bars_ = Math.max(60, Math.min(1200, Math.floor((canvas.clientWidth || 900) / 4)));
  const { status, data } = await api("GET", "/api/studio/wave?name=" + encodeURIComponent(item.name) + "&bars=" + bars_);
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
$("recPill").addEventListener("click", () => setView("studio"));

"""
