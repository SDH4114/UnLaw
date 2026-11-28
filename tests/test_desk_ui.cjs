const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
// The page is assembled by Python (desk_ui.PAGE with the Studio code from studio_ui.py injected).
const raw = execFileSync(process.env.PYTHON || 'python3', ['-c', 'import sys; sys.path.insert(0, "src"); from unlawful.desk_ui import PAGE; sys.stdout.write(PAGE)'], {cwd: path.join(__dirname, '..'), encoding: 'utf8'});
const script = raw.split('<script>')[1].split('</script>')[0].replace(/start\(\);\s*$/, '');
// No browser, HTTP or operating-system media API is available in this VM.
function harness() {
  const timers = new Map(), intervals = new Map(), frames = [];
  let seq = 0;
  const listeners = {};
  class Element {
    constructor(id = '') {
      this.id = id;
      this.children = [];
      this.dataset = {};
      this.style = {};
      this.tagName = 'DIV';
      this.isConnected = true;
      this.classList = {add() {}, remove() {}, toggle() {}, contains() { return false; }};
    }
    addEventListener() {}
    querySelector() { return null; }
    querySelectorAll() { return []; }
    append(...nodes) { this.children.push(...nodes); }
    prepend(node) { this.children.unshift(node); }
    setAttribute() {}
    pause() {}
    remove() { this.isConnected = false; }
  }
  const ids = new Map([
    'boards', 'tabs', 'viewer', 'recPill', 'play', 'skip', 'stop', 'obsidian', 'lofi',
    'filter', 'helpButton', 'help', 'theme', 'search', 'toast', 'favicon',
  ].map(id => [id, new Element(id)]));
  Object.assign(ids.get('favicon').dataset, {light: 'data:light', dark: 'data:dark'});
  const document = {
    hidden: false,
    getElementById: id => ids.get(id) || null,
    createElement: () => new Element(),
    createTextNode: text => text,
    createElementNS: () => new Element(),
    querySelectorAll: () => [],
    querySelector: () => null,
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    documentElement: {dataset: {}},
    body: new Element(),
    activeElement: new Element(),
  };
  const context = vm.createContext({
    console, document, Node: Element,
    location: {search: '', hash: '', pathname: '/'},
    history: {replaceState() {}},
    URLSearchParams, AbortController, TextDecoder, URL, Date, Float32Array, Math,
    localStorage: {getItem() { return null; }, setItem() {}},
    sessionStorage: {getItem() { return 'test'; }, setItem() {}},
    matchMedia: () => ({matches: false}),
    window: {addEventListener() {}, devicePixelRatio: 1},
    navigator: {mediaDevices: {}},
    setTimeout: (fn, ms) => { const id = ++seq; timers.set(id, {fn, ms}); return id; },
    clearTimeout: id => timers.delete(id),
    setInterval: (fn, ms) => { const id = ++seq; intervals.set(id, {fn, ms}); return id; },
    clearInterval: id => intervals.delete(id),
    requestAnimationFrame: fn => frames.push(fn),
    cancelAnimationFrame() {},
    performance: {now: () => Date.now()},
    getComputedStyle: () => ({getPropertyValue: () => ''}),
    fetch: async () => { throw Error('unmocked fetch'); },
    AudioContext: class {
      createAnalyser() { return {fftSize: 2048, getFloatTimeDomainData() {}}; }
      createMediaStreamSource() { return {connect() {}}; }
      close() {}
    },
    confirm: () => true,
  });
  vm.runInContext(script + `
    globalThis.audit = {studio, state, arcade, toggleRecord, loadRecordStatus,
      leaveStudio, toggleCamera, toggleMeter, stopStream, start, sendGame, drawCell,
      applyShape, pinPlacement, placementPx, snapPlacement, moveFocus, resizePlacement, studioKey, studioPollDelay,
      parseLayout, defaultLayout, resizeLayout, swapPanels, layoutFrame, LAYOUT_PANELS,
      addWaveSample, voiceClock, wavePeaks, recordingAudio, drawVoice, releaseWaveMic,
      loadStudioInfo, loadSetup, setStudioTab, runCountdown, cancelCountdown, closeProject, rememberEdit,
      ed, editOf, defaultEdit, edLength, bladeAt, rippleDelete, liftClips, liftRange, extractRange, moveClips, trimClip, linkedIds, toggleLink, addTrack, insertMedia, videoAt, audibleClips, captionsToClips, captionAt, mergeCaption, removeSilences, soundParts, silences, snapTime, captionAssetName, joinPeaks, soundFiles, audioOnly, renderEdit, renderEditSide, editKeydown, edSeek, edEnter, edTranscribe, edLoadModels, edToggleTrack, renderProjectPage,
      countdownSteps, saveSetupSoon, permissionBanner, openSettings,
      renderStudio, renderStudioBody, renderSources, updateRecordControls, startPreview,
      startHistory, undoEdit, addScene, moveScene, removeScene, defaultPlacement, currentScene, edited, selectSource, placementOf, nudgeSelected, deleteSelected, sourceById, toggleVisible, moveSource, toggleInput, openRecordSettings, closeStudioMenu,
      projectClock, sceneAt, syncPlayer, clockTrack, exportDefaults, exportHeightFor, renderExportDialog, startExport, pollExport, renderProjects, openProject, changePlacement, projectAction,
      cv, mulberry32, toScreen, toWorld, zoomAt, fitView, roughStrokes, hitElement, hitTest, edgeCurve, hitEdge,
      nearestSide, resizeBox, handleAt, applyBox, wrapText, adaptInk, nodeColor, noteName, makeLinear, makeFreedraw,
      snapAngle, applyStyle, containedIds, groupAround, moveItems, removeItems, copyItems, pasteItems, makeHistory,
      histCommit, histUndo, histRedo, cvLoad, cvCommit, cvUndo, cvRedo, saveCanvas, pollCanvas,
      renderCanvas, cvDown, cvMove, cvUp, cvWheel, cvSetTool, cvEndEdit, cvSelect, cvGroup, cvExport, paintScene, cvPalette,
      cvDouble, cvRenameLayer, cvApplyName, curveSegs, hitEdge, moveItems, layerName, pinSpot,
      fillable, fillTarget, applyFill, setBackground, cvBackground, canvasKey, cvStyle, cvNew, cvRename, cvChoose, CV_BY_KEY,
      floodRegion, growMask, traceMask, paintFromMask, paintContains, cutElement, eraseAt, cvBucket, cvToolClick,
      widthToSlider, sliderToWidth, cvStepWidth, cvBuildBar, cvTypedWidth,
      cvCork, setLook, pinPoint, threadCurve, edgeCurveFor, nodeTilt, fileCardSize, fileExtension, mixColor, cvAddFiles, cvToggleCork, cvImageFor, bezierPoint, loadBoards, applyTheme, newBoard, openOtherBoard, renderBoard, deleteBoard,
      renderToday, VIEWS, savedView, anchorPoint, fracAt, edgeAnchor, layerRows, cvToggleHidden, cvReorderLayer, docNodes, cvRenderLayers, cvToggleGallery, cvDropFiles, cvDeleteCanvas, cvRenderGallery,
      parseSTL, parseOBJ, parseGLTF, cvFileKind, cvView, cvCloseView, cvPasteText, cvMediaUrl, mat4LookAt, mat4Perspective, mat4Multiply,
      cvToggleFold, cvFoldAll, cleanShelf, shelfFavorite, shelfMove, shelfAddGroup, shelfRenameGroup, shelfRemoveGroup, gallerySections, galleryMatch,
      canvasLinkPath, canvasLinkFile, urlCardText, textToLink, cvClickCard, cvCardDouble, cvMediaState, cvTogglePlay, cvStopMedia, cvPeaks,
      cvAddCanvasLink, cvFollowLink, cvGoBack, cvOpenInline, cvCloseInline, cvSaveShelf, cvLoad, cvPictureBox};
  `, context);
  return {context, a: context.audit, listeners, timers, intervals, frames, ids,
    run: code => vm.runInContext(code, context)};
}
// harness() plus a tiny DOM: ids, text that clears children, firstChild; enough to render whole Studio tabs.
function treeHarness() {
  const h = harness();
  const E = h.context.Node;
  Object.defineProperty(E.prototype, 'textContent', {configurable: true, get() { return this._text || ''; }, set(value) { this._text = String(value); this.children = []; }});
  Object.defineProperty(E.prototype, 'firstChild', {configurable: true, get() { return this.children.find(child => typeof child !== 'string') || null; }});
  E.prototype.setAttribute = function (key, value) { (this.attrs = this.attrs || {})[key] = value; if (key === 'id') this.id = value; };
  E.prototype.getBoundingClientRect = () => ({left: 0, top: 0, right: 640, bottom: 360, width: 640, height: 360});
  E.prototype.addEventListener = function (type, fn) { (this.on = this.on || {})[type] = fn; };
  h.context.Image = class { set src(value) { this.url = value; } };
  const main = new E('main');
  const find = (id, node = main) => {
   if (node.id === id && node.isConnected) return node;
   for (const child of node.children || []) {
    if (typeof child === 'string') continue;
    const found = find(id, child);
    if (found) return found;
   }
   return null;
  };
  const byId = h.context.document.getElementById;
  h.context.document.getElementById = id => find(id) || byId(id);
  return {...h, main, find};
}
// A recorded project as `ul capture project --json` describes it (the setup copied, one segment, a mark).
function sampleProject() {
  const setup = sampleSetup();
  setup.sources[1].enabled = true;
  return {format: 'unlaw-studio-project', version: 1, name: 'talk', path: '/p/talk', size: 100, created: '2026-11-19T22:15:00+04:00',
    mode: 'screen', state: 'ready', problems: [], duration: 5, sources: setup.sources, audio: setup.audio,
    segments: [{duration: 5, files: {screen: 'media/screen-001.mp4', camera: 'media/camera-001.mp4', mic: 'media/mic-001.flac'}, starts: {screen: 0, camera: 0.31, mic: 0.94}}],
    scenes: setup.scenes, layouts: setup.layouts, events: [{t: 0, scene: 'screen-camera'}, {t: 2, mark: 'intro done'}],
    export: setup.export, exports: []};
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
function stream() {
  const track = {stopped: false, stop() { this.stopped = true; }};
  return {track, getTracks() { return [track]; }};
}
const plain = value => JSON.parse(JSON.stringify(value));
const textOf = node => node == null ? '' : typeof node === 'string' ? node : [node.textContent || '', ...(node.children || []).map(textOf)].join(' ');
let setupJson = null;
// The default Studio setup exactly as capture writes it.
function sampleSetup() {
  if (setupJson === null) {
    setupJson = execFileSync(process.env.PYTHON || 'python3', ['-c', 'import sys, json; sys.path.insert(0, "src"); from unlawful.capture_project import default_setup; print(json.dumps(default_setup({})))'], {cwd: path.join(__dirname, '..'), encoding: 'utf8'});
  }
  return JSON.parse(setupJson);
}
const response = data => ({status: 200, json: async () => data});
function sampleShape() {
  return {path: '/c/a.canvas', name: 'a', version: 'v1', canvas: {
    extra: {keep: 1},
    nodes: [
      {id: 'n1', type: 'text', text: 'hello', x: 0, y: 0, width: 200, height: 100, color: '2', plugin: {a: 1}},
      {id: 'n2', type: 'file', file: 'notes/Idea.md', x: 400, y: 0, width: 200, height: 100, subpath: '#h'},
      {id: 'g1', type: 'group', label: 'G', x: -50, y: -50, width: 700, height: 250},
    ],
    edges: [{id: 'e1', fromNode: 'n1', toNode: 'n2', fromSide: 'right', toSide: 'left', obsidianExtra: true}],
    unlaw: {version: 1, elements: [{id: 'x1', type: 'rectangle', x: 10, y: 300, width: 100, height: 60, stroke: '#e5484d', fill: null, strokeWidth: 2, roughness: 1, seed: 7, custom: 'k'}], future: 'yes'},
  }};
}
const tests = {
 async box_edges() {
  const h = harness();
  for (const [glyph, expected] of [
   ['┌', ['down', 'right']], ['┐', ['down', 'left']],
   ['└', ['right', 'up']], ['┘', ['left', 'up']],
   ['├', ['down', 'right', 'up']], ['┤', ['down', 'left', 'up']],
  ]) {
   const edges = new Set();
   const point = (x, y) => {
    if (x === 0) edges.add('left');
    if (x === 10) edges.add('right');
    if (y === 0) edges.add('up');
    if (y === 20) edges.add('down');
   };
   h.a.drawCell({beginPath() {}, moveTo: point, lineTo: point, stroke() {}}, glyph, 0, 0, 10, 20, 'white');
   assert.deepEqual([...edges].sort(), expected, glyph + ' must connect its Unicode box edges');
  }
 },
 async camera_lookup_leave() {
  const h = harness(), devices = deferred(), cam = stream();
  h.a.state.view = 'studio';
  h.a.studio.setup = sampleSetup();
  h.a.studio.setup.sources[1].device = 'Webcam';
  let opens = 0;
  h.context.navigator.mediaDevices.getUserMedia = async () => { opens++; return cam; };
  h.context.navigator.mediaDevices.enumerateDevices = () => devices.promise;
  const job = h.a.toggleCamera();
  await Promise.resolve();
  h.a.state.view = 'board';
  h.a.leaveStudio();
  devices.resolve([{kind: 'videoinput', label: 'Webcam', deviceId: 'camera'}]);
  await job;
  assert.equal(opens, 1, 'device lookup must not reopen a camera after leaving Studio');
  assert.equal(cam.track.stopped, true);
 },
 async microphone_lookup_leave() {
  const h = harness(), devices = deferred(), mic = stream();
  h.a.state.view = 'studio';
  h.a.studio.setup = sampleSetup();
  h.a.studio.setup.audio.mic.device = 'Microphone';
  let opens = 0;
  h.context.navigator.mediaDevices.getUserMedia = async () => { opens++; return mic; };
  h.context.navigator.mediaDevices.enumerateDevices = () => devices.promise;
  const job = h.a.toggleMeter();
  await Promise.resolve();
  await Promise.resolve();
  h.a.state.view = 'board';
  h.a.leaveStudio();
  devices.resolve([{kind: 'audioinput', label: 'Microphone', deviceId: 'mic'}]);
  await job;
  assert.equal(opens, 1, 'device lookup must not reopen a microphone after leaving Studio');
  assert.equal(mic.track.stopped, true);
 },
 async failed_save() {
  const h = harness();
  h.a.studio.saving = true;
  h.a.studio.status = {active: true, phase: 'saving'};
  let calls = 0;
  h.context.fetch = async () => response({active: true, phase: 'unsaved', elapsed: 3, saving_done: {error: 'disk full'}});
  await h.a.loadRecordStatus();
  assert.equal(h.a.studio.saving, false, 'failed save must release the UI so stop can retry');
  h.context.fetch = async () => { calls++; return response({saving: true}); };
  await h.a.toggleRecord();
  assert.equal(calls, 1, 'a second stop click must reach capture');
 },
 async record_network() {
  for (const active of [false, true]) {
   const h = harness();
   h.a.state.view = 'studio';
   h.a.studio.setup = sampleSetup();
   h.a.studio.setup.countdown = 0;
   h.a.studio.status = {active, phase: active ? 'recording' : undefined};
   let calls = 0;
   h.context.fetch = async () => { calls++; throw Error('connection reset'); };
   await h.a.toggleRecord().catch(() => {});
   assert.equal(Boolean(h.a.studio.starting), false, 'a rejected request must release starting');
   assert.equal(h.a.studio.saving, false, 'a rejected request must release saving');
   const before = calls;
   await h.a.toggleRecord().catch(() => {});
   assert.ok(calls > before, 'another click must reach the server');
  }
 },
 async camera_leave() {
  const h = harness(), pending = deferred(), cam = stream();
  h.a.state.view = 'studio';
  h.context.navigator.mediaDevices.getUserMedia = () => pending.promise;
  const job = h.a.toggleCamera();
  h.a.state.view = 'board';
  h.a.leaveStudio();
  pending.resolve(cam);
  await job;
  assert.equal(cam.track.stopped, true, 'a late permission grant must release the camera');
  assert.equal(h.a.studio.camStream, null);
 },
 async camera_record() {
  const h = harness(), cam = stream();
  h.a.state.view = 'studio';
  h.a.studio.setup = sampleSetup();
  h.a.studio.setup.countdown = 0;
  h.a.studio.setup.sources[1].enabled = true;
  h.context.navigator.mediaDevices.getUserMedia = async () => cam;
  await h.a.toggleCamera();
  const sent = [];
  h.context.fetch = async (url, options) => { sent.push([url, options.body]); return response({active: true, phase: 'recording', elapsed: 0}); };
  await h.a.toggleRecord();
  assert.equal(sent[0][0], '/api/studio/record');
  assert.deepEqual(JSON.parse(sent[0][1]), {scene: 'screen-camera', canvas: '16:9'}, 'the page records the saved setup');
  assert.equal(cam.track.stopped, false, 'the live camera preview stays while recording (spec 9)');
  assert.equal(h.a.studio.camStream, cam);
  h.a.leaveStudio();
  assert.equal(cam.track.stopped, true, 'leaving the Studio still releases it');
 },
 async microphone_leave() {
  const h = harness(), pending = deferred(), mic = stream();
  h.a.state.view = 'studio';
  h.context.navigator.mediaDevices.getUserMedia = () => pending.promise;
  const job = h.a.toggleMeter();
  h.a.state.view = 'board';
  h.a.leaveStudio();
  pending.resolve(mic);
  await job;
  assert.equal(mic.track.stopped, true, 'a late permission grant must release the microphone');
  assert.equal(h.a.studio.micStream, null);
  assert.equal(h.intervals.size, 0, 'no sampler may start after leaving Studio');
  assert.equal(h.frames.length, 0, 'no animation may start after leaving Studio');
 },
 async camera_concurrent() {
  const h = harness(), first = deferred(), second = deferred(), old = stream(), current = stream();
  h.a.state.view = 'studio';
  let calls = 0;
  h.context.navigator.mediaDevices.getUserMedia = () => (++calls === 1 ? first : second).promise;
  const one = h.a.toggleCamera(), two = h.a.toggleCamera();
  second.resolve(current);
  await two;
  first.resolve(old);
  await one;
  assert.equal(old.track.stopped, true, 'superseded camera streams must be stopped');
  assert.equal(h.a.studio.camStream, current);
 },
 async microphone_concurrent() {
  const h = harness(), first = deferred(), second = deferred(), old = stream(), current = stream();
  h.a.state.view = 'studio';
  let calls = 0;
  h.context.navigator.mediaDevices.getUserMedia = () => (++calls === 1 ? first : second).promise;
  const one = h.a.toggleMeter(), two = h.a.toggleMeter();
  second.resolve(current);
  await two;
  first.resolve(old);
  await one;
  assert.equal(old.track.stopped, true, 'superseded microphone streams must be stopped');
  assert.equal(h.a.studio.micStream, current);
  assert.equal(h.intervals.size, 1, 'only the current microphone has a sampler');
 },
 async microphone_animation() {
  const h = harness();
  h.a.state.view = 'studio';
  h.context.navigator.mediaDevices.getUserMedia = async () => stream();
  await h.a.toggleMeter();
  const oldFrame = h.frames.shift();
  h.a.stopStream('micStream');
  await h.a.toggleMeter();
  assert.equal(h.frames.length, 1);
  oldFrame();
  assert.equal(h.frames.length, 1, 'the old microphone animation must not adopt the new stream');
 },
 async studio_polling() {
  const h = harness();
  h.a.state.view = 'studio';
  h.a.studio.info = {available: true};
  h.run('loadBoard=async()=>{};loadBoards=async()=>{};loadTimer=async()=>{};loadGames=async()=>{};loadStudioInfo=async()=>{};render=()=>{};');
  let calls = 0;
  h.context.fetch = async () => { calls++; return response({active: true, phase: 'recording', elapsed: 2}); };
  await h.a.start();
  const idle = [...h.timers.entries()].find(([, x]) => x.ms === 5000);
  assert.ok(idle, 'an idle Studio polls every 5 s for recordings started elsewhere');
  h.timers.delete(idle[0]);
  await idle[1].fn();
  assert.equal(calls, 1, 'visible Studio must poll for terminal recording changes');
  assert.equal(h.a.studio.status.active, true);
  assert.ok([...h.timers.values()].some(x => x.ms === 1000), 'an observed active recording polls every second on the Studio tab');
  h.context.document.hidden = true;
  const next = [...h.timers.entries()].find(([, x]) => x.ms === 1000);
  h.timers.delete(next[0]);
  await next[1].fn();
  assert.equal(calls, 1, 'a hidden page does not poll');
  assert.ok(![...h.timers.values()].some(x => x.ms === 1000 || x.ms === 5000), 'and schedules nothing until it is visible again');
 },
 async studio_record_tab_renders() {
  // The whole Record tab is built in a small DOM (ids, children, text): no exception, and the pieces are there.
  const h = treeHarness();
  const a = h.a;
  a.state.view = 'studio';
  a.studio.info = {available: true, settings: {}};
  a.studio.setup = sampleSetup();
  a.studio.setup.sources[1].enabled = true;
  a.studio.devices = {displays: [{number: 1, name: 'Color LCD', pixels: '3024 x 1964'}], cameras: ['FaceTime HD Camera'], microphones: [{name: "Haos's Phone Microphone", virtual: false}, {name: 'BlackHole 2ch', virtual: true}], ffmpeg: true};
  a.studio.doctor = {screen: false, app: 'Ghostty'};
  a.studio.status = {active: false, free_bytes: 182e9};
  h.context.fetch = async (url) => response(url.startsWith('/api/studio/doctor') ? {screen: false, app: 'Ghostty'} : url.startsWith('/api/studio/status') ? {active: false, free_bytes: 182e9} : {});
  a.renderStudio(h.main);
  const scenes = h.find('scenesPane');
  assert.equal(scenes.children[1].children.length, 4, 'four default scenes');
  assert.match(textOf(scenes), /Screen \+ camera/);
  assert.match(textOf(h.find('permBanner')), /Ghostty/);
  const stage = h.find('stage');
  assert.equal(stage.children.filter(n => /\bph\b/.test(n.className)).length, 2, 'screen and camera are drawn in the 16:9 screen-camera scene');
  const cam = stage.children.filter(n => /\bph\b/.test(n.className))[1];
  assert.deepEqual([cam.style.left, cam.style.top, cam.style.width], ['0%', '76%', '24%']);
  assert.equal(h.find('selBox').children.length, 8, 'the selected camera has eight handles (corners and edges)');
  assert.match(textOf(h.find('soundPane')), /Haos's Phone Microphone/);
  assert.match(textOf(h.find('soundPane')), /BlackHole 2ch \(virtual\)/);
  assert.match(textOf(h.find('propsPane')), /FaceTime HD Camera/);
  a.openRecordSettings(h.find('recButton'));
  assert.match(textOf(a.studio.menu), /FLAC lossless/, 'recording files are in the Settings menu');
  a.closeStudioMenu();
  assert.match(textOf(h.find('recInfo')), /3024×1964 · 60 fps/);
  assert.match(textOf(h.find('recInfo')), /free 182 GB · ≈ 93 MB\/min/);
  // Format switch: 9:16 stacks the camera on top at 40 %.
  a.studio.setup.canvas = '9:16';
  a.renderStudioBody();
  const tall = h.find('stage').children.filter(n => /\bph\b/.test(n.className));
  assert.deepEqual(tall.map(n => [n.style.top, n.style.height]), [['40%', '60%'], ['0%', '40%']], 'screen below, camera on top (z order = sources)');
  // A recording that is stuck offers the forced stop.
  a.studio.status = {active: true, phase: 'stuck', stuck: ['screencapture'], warnings: ['the microphone is silent (below -60 dB for 10 s)'], elapsed: 3, free_bytes: 2e9};
  a.updateRecordControls();
  assert.match(textOf(h.find('warnStrip')), /microphone is silent/);
  assert.match(textOf(h.find('warnStrip')), /screencapture does not stop/);
  // Text in source names stays text.
  a.studio.setup.sources.push({id: 'text-1', kind: 'text', enabled: true, asset: 'x.png', text: '<b>hi</b>', font: 'Georgia, serif', size: 64, color: '#ffffff', background: null});
  a.renderSources();
  assert.match(textOf(h.find('sourcesPane')), /Text “<b>hi<\/b>”/);
  a.studio.tab = 'projects';
  a.renderStudioBody();
  assert.ok(h.find('studioProjects'), 'the Projects tab renders');
 },
 async studio_layout_and_audio() {
  // Panels are resized by the gaps and swapped by their titles; a damaged saved layout never breaks the page.
  const h = treeHarness(), a = h.a;
  const fresh = a.defaultLayout();
  assert.deepEqual(a.parseLayout(null), fresh);
  assert.deepEqual(a.parseLayout('{nope'), fresh, 'broken JSON gives the default');
  const saved = {right: 420, bottom: 300, cols: [2, 1, 1], order: ['recBar', 'scenesPane', 'sourcesPane', 'soundPane', 'propsPane']};
  assert.equal(JSON.stringify(a.parseLayout(JSON.stringify(saved))), JSON.stringify(saved), 'a good layout comes back as saved');
  const odd = a.parseLayout(JSON.stringify({right: 5, bottom: 'x', cols: [1, -1, 1], order: ['recBar', 'recBar', 'scenesPane', 'sourcesPane', 'soundPane']}));
  assert.deepEqual(odd, fresh, 'too small, wrong types, negative shares and duplicate panels fall back');
  const layout = a.defaultLayout();
  const box = {left: 0, top: 0, right: 1400, bottom: 900, width: 1400, height: 900};
  a.resizeLayout(layout, 'right', 0, box, {x: 1000, y: 0});
  assert.equal(layout.right, 396, 'the right column follows the pointer');
  a.resizeLayout(layout, 'right', 0, box, {x: 100, y: 0});
  assert.equal(layout.right, 980, 'the preview keeps at least 420 px');
  a.resizeLayout(layout, 'bottom', 0, box, {x: 0, y: 890});
  assert.equal(layout.bottom, 110, 'the docks keep at least 110 px');
  a.resizeLayout(layout, 'col', 0, box, {x: 300, y: 0}, {left: 0, right: 600});
  assert.equal(layout.cols.slice(0, 2).join(), '1.075,1.075', 'two neighbouring docks share their width');
  a.resizeLayout(layout, 'col', 0, box, {x: 0, y: 0}, {left: 0, right: 600});
  assert.ok(layout.cols[0] > 0.2, 'a dock never shrinks away');
  assert.equal(a.swapPanels(layout, 0, 4), true);
  assert.equal(layout.order.join(), 'recBar,scenesPane,sourcesPane,soundPane,propsPane', 'the inspector and the controls swap');
  assert.equal(a.swapPanels(layout, 2, 2), false, 'dropping on itself changes nothing');
  // The saved layout is read when the Record tab is built: each panel lands in its slot.
  h.context.localStorage.getItem = (key) => key === 'studio-layout' ? JSON.stringify(saved) : null;
  a.studio.layout = null;
  a.layoutFrame(h.context.document.createElement('div'));
  assert.equal(a.studio.layout.order.join(), saved.order.join());
  const slots = a.studio.layoutNodes.slots;
  assert.equal(slots[0].children[0].id, 'recBar', 'the controls sit top right');
  assert.equal(slots[4].children[0].id, 'propsPane', 'the inspector bottom right');
  // Audio only: the microphone alone, as its own recording.
  a.state.view = 'studio';
  a.studio.setup = sampleSetup();
  a.studio.setup.countdown = 0;
  const sent = [];
  h.context.fetch = async (url, options) => { sent.push([url, options.body]); return response({active: true, mode: 'audio', phase: 'recording', elapsed: 0}); };
  await a.toggleRecord('audio');
  assert.equal(JSON.stringify(sent), JSON.stringify([['/api/studio/record', JSON.stringify({mode: 'audio'})]]));
  assert.equal(a.studioKey('KeyA', {active: false}), 'audio');
  assert.equal(a.studioKey('KeyA', {active: true}), 'stop', 'A also stops');
  assert.equal(a.studioKey('KeyA', {active: false, typing: true}), null);
 },
 async edit_model() {
  // Version 2: tracks of clips like Resolve/Premiere. The recording is linked picture + mic + Mac sound.
  const a = harness().a;
  const project = sampleProject();
  const edit = a.defaultEdit(project);
  assert.deepEqual(plain(edit.tracks.map(track => [track.id, track.kind])), [['s1', 'subtitle'], ['t1', 'text'], ['v1', 'video'], ['a1', 'audio'], ['a2', 'audio'], ['a3', 'audio']]);
  assert.deepEqual(plain(edit.clips.map(clip => [clip.track, clip.source, clip.start, clip.in, clip.out, clip.link])),
   [['v1', 'recording', 0, 0, 5, 'l1'], ['a1', 'mic', 0, 0, 5, 'l1'], ['a2', 'system', 0, 0, 5, 'l1']]);
  assert.equal(a.edLength(edit), 5);
  // Blade at 2 s cuts the three linked clips; the right halves are linked to each other, not to the left ones.
  assert.equal(a.bladeAt(edit, 2), 3);
  assert.equal(a.bladeAt(edit, 2.01), 0, 'too close to a cut');
  const right = edit.clips.filter(clip => clip.start === 2);
  assert.equal(right.length, 3);
  assert.equal(new Set(right.map(clip => clip.link)).size, 1);
  assert.notEqual(right[0].link, 'l1');
  assert.deepEqual(plain(a.linkedIds(edit, [right[0].id]).sort()), plain(right.map(clip => clip.id).sort()));
  // Ripple delete closes the gap on every unlocked track.
  assert.equal(a.rippleDelete(edit, right.map(clip => clip.id)), true);
  assert.equal(a.edLength(edit), 2);
  // Lift leaves a gap; picture and sound cut apart (Alt-click selects one clip).
  a.bladeAt(edit, 1);
  const picture = edit.clips.find(clip => clip.track === 'v1' && clip.start === 0);
  a.liftClips(edit, [picture.id]);
  assert.equal(a.videoAt(edit, 0.5), null, 'a gap is black');
  assert.ok(a.videoAt(edit, 1.5));
  assert.equal(a.audibleClips(edit).filter(clip => clip.start === 0).length, 2, 'its sound stays');
  // Moving overwrites what is under the moved clip on its track.
  const mic = edit.clips.filter(clip => clip.track === 'a1').sort((x, y) => x.start - y.start);
  assert.equal(a.moveClips(edit, [mic[0].id], 0.5, 0), true);
  const mics = edit.clips.filter(clip => clip.track === 'a1').sort((x, y) => x.start - y.start);
  assert.deepEqual(plain(mics.map(clip => [clip.start, clip.in, clip.out])), [[0.5, 0, 1], [1.5, 1.5, 2]], 'the second mic clip lost its covered part');
  assert.equal(a.moveClips(edit, [mics[0].id], -9, 0), true);
  assert.equal(edit.clips.find(clip => clip.id === mics[0].id).start, 0, 'never before 0');
  assert.equal(a.moveClips(edit, [mics[0].id], 0, -1), false, 'an audio clip cannot go onto a video track');
  assert.equal(a.moveClips(edit, [mics[0].id], 0, 2), true, 'down to another audio track');
  assert.equal(edit.clips.find(clip => clip.id === mics[0].id).track, 'a3');
  // Trims stop at the source's ends and at the neighbours.
  const fresh = a.defaultEdit(project);
  const v = fresh.clips[0];
  a.trimClip(fresh, v.id, 'end', 9, project, false);
  assert.equal(v.out, 5, 'not past the end of the recording');
  a.trimClip(fresh, v.id, 'start', 1, project, true);
  assert.deepEqual(plain(fresh.clips.map(clip => [clip.start, clip.in])), [[1, 1], [1, 1], [1, 1]], 'linked clips trim together');
  a.trimClip(fresh, v.id, 'start', -3, project, false);
  assert.deepEqual(plain([v.start, v.in]), [0, 0], 'not before the start of the recording');
  // A text clip trimmed to the left grows from its start; `in` stays 0 (a negative one made the save fail).
  const titled = a.defaultEdit(project);
  const textTrack = a.addTrack(titled, 'text');
  titled.clips.push({id: 'tx', track: textTrack.id, source: 'text', start: 2, in: 0, out: 2, link: '', text: 'hi', asset: ''});
  a.trimClip(titled, 'tx', 'start', 1, project, false);
  assert.deepEqual(plain(titled.clips.find(clip => clip.id === 'tx')).start, 1);
  assert.deepEqual(plain(['in', 'out'].map(key => titled.clips.find(clip => clip.id === 'tx')[key])), [0, 3]);
  // Cutting a range out of the middle leaves the right parts linked to each other, not to the left parts.
  const middle = a.defaultEdit(project);
  a.liftRange(middle, 1, 2);
  const lefts = middle.clips.filter(clip => clip.start === 0), rights = middle.clips.filter(clip => clip.start === 2);
  assert.equal(lefts.length, 3); assert.equal(rights.length, 3);
  assert.equal(new Set(rights.map(clip => clip.link)).size, 1, 'right parts share one link');
  assert.notEqual(rights[0].link, lefts[0].link, 'a new group');
  // Locked tracks are left alone by a range extract.
  const locked = a.defaultEdit(project);
  locked.tracks.find(track => track.id === 'a2').locked = true;
  assert.equal(a.extractRange(locked, 1, 2), true);
  assert.deepEqual(plain(locked.clips.filter(clip => clip.track === 'v1').map(clip => [clip.start, clip.in, clip.out])), [[0, 0, 1], [1, 2, 5]]);
  assert.deepEqual(plain(locked.clips.filter(clip => clip.track === 'a2').map(clip => [clip.start, clip.in, clip.out])), [[0, 0, 5]]);
  // Mute and solo decide what is heard.
  const heard = a.defaultEdit(project);
  heard.tracks.find(track => track.id === 'a2').muted = true;
  assert.deepEqual(plain(a.audibleClips(heard).map(clip => clip.source)), ['mic']);
  heard.tracks.find(track => track.id === 'a3').solo = true;
  assert.deepEqual(plain(a.audibleClips(heard)), [], 'with a solo only solo tracks play');
  // A new video track goes above the others and covers them.
  const layered = a.defaultEdit(project);
  const top = a.addTrack(layered, 'video');
  assert.equal(top.id, 'v2');
  assert.ok(layered.tracks.findIndex(track => track.id === 'v2') < layered.tracks.findIndex(track => track.id === 'v1'));
  const ids = a.insertMedia(layered, project, 'recording', 1, {video: 'v2'});
  assert.equal(ids.length, 3, 'picture, mic and Mac sound');
  assert.equal(a.videoAt(layered, 1.5).track, 'v2');
  assert.equal(a.videoAt(layered, 0.5).track, 'v1');
  // Link and unlink.
  assert.equal(a.toggleLink(layered, ids), 'unlinked');
  assert.deepEqual(plain(a.linkedIds(layered, [ids[0]])), [ids[0]]);
  assert.equal(a.toggleLink(layered, ids), 'linked');
  assert.equal(a.linkedIds(layered, [ids[0]]).length, 3);
  // Subtitles: lines of the recording clock follow the mic clips onto the timeline.
  const cut = a.defaultEdit(project);
  a.bladeAt(cut, 2); a.bladeAt(cut, 3);
  a.rippleDelete(cut, cut.clips.filter(clip => clip.start === 2).map(clip => clip.id));
  assert.equal(a.captionsToClips(cut, project, [{in: 0.5, out: 1.5, text: 'one'}, {in: 1.5, out: 3.5, text: 'two words'}, {in: 2.2, out: 2.8, text: 'gone'}]), 2);
  const subs = cut.clips.filter(clip => clip.source === 'caption').sort((x, y) => x.start - y.start);
  assert.deepEqual(plain(subs.map(clip => [clip.start, Math.round((clip.out - clip.in) * 1000) / 1000, clip.text])), [[0.5, 1, 'one'], [1.5, 1, 'two words']]);
  assert.equal(a.captionAt(cut, 2.1).text, 'two words');
  assert.equal(a.mergeCaption(cut, subs[0].id), true);
  assert.equal(cut.clips.filter(clip => clip.source === 'caption').length, 1);
  assert.equal(cut.clips.find(clip => clip.source === 'caption').text, 'one two words');
  // Remove silences: quiet 1-2 s of the recording (mic peaks at 25 a second) is extracted from every track.
  const quiet = a.defaultEdit(project);
  const peaks = Array.from({length: 125}, (_, i) => i >= 25 && i < 50 ? 0.01 : 0.6);
  const removed = a.removeSilences(quiet, project, peaks);
  assert.ok(Math.abs(removed - 0.76) < 1e-9, String(removed));  // 1.12-1.88: 0.12 s of the pause kept on each side
  assert.ok(Math.abs(a.edLength(quiet) - 4.24) < 1e-9);
  assert.equal(a.removeSilences(quiet, project, peaks), 0, 'nothing left to remove');
  // Pure helpers kept from version 1.
  assert.equal(JSON.stringify(a.silences(peaks.slice(0, 75), 25, 0.1, 0.6, 0.1)), '[[1.1,1.9]]');
  assert.equal(a.snapTime(4.03, [4, 9], 0.05), 4);
  assert.equal(a.snapTime(4.2, [4, 9], 0.05), 4.2);
  assert.notEqual(a.captionAssetName('hi', {size: 54}), a.captionAssetName('hi', {size: 56}), 'a new style draws again');
  assert.match(a.captionAssetName('hi', {}), /^cap-[0-9a-f]{16}\.png$/);
  assert.equal(JSON.stringify(a.joinPeaks([{start: 0, duration: 1, peaks: [0.2, 0.4]}, {start: 1.5, duration: 0.5, peaks: [1]}], 2, 2)), '[0.2,0.4,0,1]');
  assert.equal(JSON.stringify(a.soundFiles(project)), JSON.stringify([{file: 'media/mic-001.flac', start: 0.94, duration: 5}]));
  assert.equal(a.audioOnly(project), false);
  // Where a recording's sound sits in its files: the mic file starts 0.94 s into part 1.
  assert.deepEqual(plain(a.soundParts(project, 'mic')), [{segment: 0, begin: 0, end: 5, file: 'media/mic-001.flac', offset: 0.94}]);
  assert.deepEqual(plain(a.soundParts(project, 'system')), [{segment: 0, begin: 0, end: 5, file: 'media/screen-001.mp4', offset: 0}]);
 },
 async edit_tab_keys_and_page() {
  const h = treeHarness(), a = h.a;
  const ctx = new Proxy({}, {get: (target, key) => key in target ? target[key] : key === 'measureText' ? () => ({width: 10}) : () => {}, set: (target, key, value) => { target[key] = value; return true; }});
  h.context.Node.prototype.getContext = () => ctx;
  a.state.view = 'studio';
  a.studio.info = {available: true};
  const project = sampleProject();
  project.segments[0].files = {mic: 'media/mic-001.flac'};
  project.mode = 'audio';
  const calls = [];
  h.context.fetch = async (url, options) => {
   calls.push([url, options && options.body]);
   return response(url.includes('/wave') ? {peaks: [0.5, 0.5], duration: 5} : url.includes('speech-models') ? [{id: 'mlx/whisper', format: 'mlx', default: false}, {id: 'gguf/whisper', format: 'gguf', default: false}]
    : url.includes('transcribe') ? {captions: [{in: 3, out: 4, text: 'hello'}], language: 'en', model: 'mlx/whisper'} : url.includes('proxy') ? {state: 'done', files: {}} : {});
  };
  h.main.append(h.context.document.createElement('div'));
  const root = new h.context.Node('div'); root.id = 'studioRoot'; h.main.append(root);
  a.studio.project = project;
  a.studio.player = null;
  a.edEnter();
  assert.equal(a.studio.tab, 'edit');
  assert.ok(h.find('edTracks'), 'the timeline is drawn');
  assert.ok(h.find('edWave'), 'an audio project shows its sound, not a stage');
  assert.equal(h.find('stage'), null);
  assert.match(textOf(h.find('edHeads')), /Mic/, 'track headers name the tracks');
  assert.doesNotMatch(textOf(h.find('edHeads')), /Video 1/, 'an audio project has no picture track to show');
  const key = (code, more = {}) => a.editKeydown({code, key: code, shiftKey: false, metaKey: false, ctrlKey: false, altKey: false, ...more});
  a.edSeek(2);
  assert.equal(key('KeyB', {metaKey: true}), true);
  assert.equal(project.edit.clips.length, 2, '⌘B cuts at the playhead');
  a.ed.sel = new Set([project.edit.clips.find(clip => clip.start === 0).id]);
  assert.equal(key('Backspace', {shiftKey: true}), true);
  assert.equal(a.edLength(project.edit), 3, '⇧⌫ ripple deletes');
  a.edSeek(0.5); key('KeyI'); a.edSeek(1.5); key('KeyO');
  key('Quote');
  assert.equal(a.edLength(project.edit), 2, 'the I/O range is extracted');
  a.undoEdit(false);
  assert.equal(a.edLength(project.edit), 3, '⌘Z brings it back');
  a.ed.in = a.ed.out = null;
  a.edSeek(1);
  key('KeyB', {metaKey: true});
  a.ed.sel = new Set([project.edit.clips.find(clip => clip.start === 0).id]);
  key('Backspace');
  assert.equal(a.edLength(project.edit), 3, '⌫ lifts and leaves a gap');
  assert.equal(project.edit.clips.filter(clip => clip.source === 'mic').length, 1);
  a.undoEdit(false);
  key('KeyT');
  assert.equal(project.edit.clips.filter(clip => clip.source === 'text').length, 1, 'T adds a text');
  key('KeyB');
  assert.equal(a.ed.tool, 'blade');
  key('KeyA');
  assert.equal(a.ed.tool, 'select');
  // Subtitles use the chosen speech model.
  await a.edLoadModels();
  assert.equal(a.ed.model, 'mlx/whisper', 'the best model is chosen when none was');
  a.ed.language = 'en';
  await a.edTranscribe();
  assert.equal(project.edit.clips.filter(clip => clip.source === 'caption').length, 1);
  const sent = calls.find(([url]) => url === '/api/studio/transcribe');
  assert.deepEqual(plain(JSON.parse(sent[1])), {path: project.path, language: 'en', model: 'mlx/whisper'});
  // Track header buttons mute a track; the inspector shows a selected clip.
  const mic = project.edit.tracks.find(track => track.id === 'a1');
  a.edToggleTrack('a1', 'muted');
  assert.equal(mic.muted, true);
  a.undoEdit(false);
  assert.equal(project.edit.tracks.find(track => track.id === 'a1').muted, false, 'track changes are undoable');
  a.ed.sel = new Set([project.edit.clips.find(clip => clip.source === 'mic').id]);
  a.renderEditSide();
  assert.match(textOf(h.find('edInspect')), /Volume/);
  // The Projects page of an audio project: no format buttons, its sound instead of a stage.
  a.studio.tab = 'projects';
  const box = new h.context.Node('div'); box.id = 'studioProjects'; h.main.append(box);
  a.renderProjectPage(box);
  assert.doesNotMatch(textOf(box), /16:9/);
  assert.ok(h.find('audioWave'));
 },
 async studio_failures_and_double_clicks() {
  // A desk that does not answer is asked once, not in a loop.
  const h = treeHarness(), a = h.a;
  a.state.view = 'studio';
  let calls = 0;
  h.context.fetch = async () => { calls++; return {status: 403, json: async () => ({error: 'forbidden'})}; };
  await a.loadStudioInfo();
  assert.equal(a.studio.info.available, false);
  assert.equal(a.studio.info.error, 'forbidden');
  a.renderStudio(h.main);
  assert.equal(calls, 1, 'the failed answer is shown, not asked for again');
  assert.match(textOf(h.main), /forbidden/);
  // A setup that cannot be read shows the reason and a way to try again.
  a.studio.info = {available: true, settings: {}};
  a.studio.setup = null;
  await a.loadSetup();
  assert.equal(a.studio.setupError, 'forbidden');
  // Record pressed twice while the first request is on its way: one recording request.
  const sent = [];
  a.studio.setup = sampleSetup();
  a.studio.setup.countdown = 0;
  a.studio.status = {active: false};
  let release;
  h.context.fetch = async (url) => { sent.push(url); if (url === '/api/studio/record') await new Promise((done) => { release = done; }); return response({active: true, phase: 'recording', elapsed: 0}); };
  a.studio.saveTimer = 1;
  const first = a.toggleRecord();
  const second = a.toggleRecord();
  await new Promise((done) => setImmediate(done));
  await new Promise((done) => setImmediate(done));
  if (release) release();
  await first; await second;
  assert.equal(sent.filter((url) => url === '/api/studio/record').length, 1);
  // A countdown never starts a recording behind the user's back on another tab.
  a.studio.status = {active: false};
  a.studio.counting = 3;
  a.setStudioTab('projects');
  assert.equal(a.studio.counting, 0, 'leaving the Record tab cancels the countdown');
 },
 async studio_voice_wave() {
  // Audio only draws a Voice Memos wave: one bar per 0.08 s slice, its loudest level, never going back in time.
  const h = treeHarness(), a = h.a;
  const wave = [];
  a.addWaveSample(wave, 0.01, 0.2);
  a.addWaveSample(wave, 0.05, 0.6);
  a.addWaveSample(wave, 0.03, 0.4);
  a.addWaveSample(wave, 0.17, 0.3);
  a.addWaveSample(wave, 0.09, 0.9);
  assert.equal(JSON.stringify(wave), JSON.stringify([{i: 0, v: 0.6}, {i: 2, v: 0.3}]), 'loudest per slice; a late sample for an older slice is dropped');
  assert.equal(a.voiceClock(2.883), '00:02,88');
  assert.equal(a.voiceClock(61.5), '01:01,50');
  assert.equal(a.voiceClock(-3), '00:00,00');
  assert.equal(a.wavePeaks([{i: 0, v: 0.2}, {i: 1, v: 0.7}, {i: 3, v: 0.5}, {i: 9, v: 1}], 4, 2).join(), '0.7,0.5', 'whole recording squeezed into columns; slices past the span are left out');
  assert.equal(a.wavePeaks([], 10, 0).length, 0);
  // The wave shows while an audio recording runs (also one started from the terminal), and only then.
  a.state.view = 'studio';
  a.studio.setup = sampleSetup();
  a.studio.status = {active: true, mode: 'audio', phase: 'recording', elapsed: 1};
  assert.equal(a.recordingAudio(), true);
  a.studio.status = {active: true, mode: 'screen', phase: 'recording', elapsed: 1};
  assert.equal(a.recordingAudio(), false);
  a.studio.starting = Date.now(); a.studio.startingMode = 'audio';
  assert.equal(a.recordingAudio(), true, 'while starting, the requested mode counts');
  a.studio.starting = 0;
  // The microphone opened only for the wave is closed after the recording.
  const track = {stopped: false, stop() { this.stopped = true; }};
  a.studio.micStream = {getTracks: () => [track]};
  a.studio.waveMic = true;
  a.releaseWaveMic();
  assert.equal(track.stopped, true);
  assert.equal(a.studio.micStream, null);
  a.releaseWaveMic();
 },
 async studio_obs_editing() {
  // Scenes and sources are edited like in OBS: add, rename, order, hide, delete, nudge, and ⌘Z brings it back.
  const h = treeHarness(), a = h.a;
  a.state.view = 'studio';
  a.studio.info = {available: true, settings: {}};
  a.studio.setup = sampleSetup();
  a.startHistory(a.studio.setup);
  a.studio.devices = {displays: [{number: 1, name: 'Color LCD', pixels: '3024 x 1964'}], cameras: [], microphones: [], ffmpeg: true};
  a.studio.status = {active: false};
  h.context.fetch = async () => response({});
  a.renderStudio(h.main);
  const rows = () => h.find('scenesPane').children[1].children;
  a.addScene();
  assert.equal(a.studio.setup.scenes.length, 5, 'a scene is added');
  assert.equal(a.studio.setup.scene, a.studio.setup.scenes[1].id, 'right after the one it copies, and switched to');
  assert.equal(rows().length, 5);
  const added = a.studio.setup.scene;
  a.moveScene(added, -1);
  assert.equal(a.studio.setup.scenes[0].id, added, 'scenes move up');
  a.removeScene(added);
  assert.equal(a.studio.setup.scenes.length, 4);
  a.undoEdit(false);
  assert.equal(a.studio.setup.scenes.length, 5, '⌘Z brings the scene back');
  a.undoEdit(true);
  assert.equal(a.studio.setup.scenes.length, 4, '⇧⌘Z removes it again');
  // A text source: shown in the current scene, selected, then deleted with Delete and restored.
  a.studio.setup.sources.push({id: 'text-1', kind: 'text', enabled: true, asset: 'x.png', text: 'Hi', font: 'Georgia, serif', size: 64, color: '#ffffff', background: null});
  for (const scenes of Object.values(a.studio.setup.layouts)) for (const [scene, layout] of Object.entries(scenes)) layout.placements['text-1'] = {...a.defaultPlacement({kind: 'text'}, '16:9', 2), visible: scene === a.currentScene()};
  a.edited();
  a.selectSource('text-1');
  assert.match(textOf(h.find('propsPane')), /Transform/, 'the inspector shows the transform');
  const before = a.placementOf('text-1').box[0];
  a.nudgeSelected(10, 0);
  assert.ok(Math.abs(a.placementOf('text-1').box[0] - (before + 10 / 1920)) < 1e-9, 'arrows nudge by pixels of the 1080p frame');
  a.deleteSelected();
  assert.equal(a.sourceById('text-1'), null, 'Delete removes an image or text');
  a.undoEdit(false);
  assert.ok(a.sourceById('text-1'), '⌘Z brings it back');
  a.toggleVisible('text-1');
  assert.equal(a.placementOf('text-1').visible, false, 'the eye hides it in this scene');
  // The list shows the front first, and moving forward changes the z order.
  a.moveSource('screen', 0, a.studio.setup.sources.length - 1);
  assert.equal(a.studio.setup.sources[a.studio.setup.sources.length - 1].id, 'screen');
  assert.match(textOf(h.find('sourcesPane').children[1].children[0]), /Screen/, 'the front source is listed first');
  // Turning the microphone off closes the page's microphone at once.
  const track = {stopped: false, stop() { this.stopped = true; }};
  a.studio.micStream = {getTracks: () => [track]};
  a.toggleInput('mic');
  assert.equal(a.studio.setup.audio.mic.enabled, false);
  assert.equal(track.stopped, true, 'the browser microphone is released');
  assert.equal(a.studio.micStream, null);
  assert.match(textOf(h.find('soundPane')), /off/);
 },
 async studio_camera_turns_on_from_the_eye_and_controls() {
  // An "off" camera used to keep recording nothing while its eye showed it in the scene.
  const h = treeHarness(), a = h.a;
  a.state.view = 'studio';
  a.studio.info = {available: true, settings: {}};
  a.studio.setup = sampleSetup();
  a.startHistory(a.studio.setup);
  a.studio.devices = {displays: [{number: 1, name: 'Color LCD', pixels: '3024 x 1964'}], cameras: [{name: 'FaceTime HD Camera'}], microphones: [], ffmpeg: true};
  a.studio.status = {active: false};
  h.context.fetch = async () => response({});
  a.renderStudio(h.main);
  assert.equal(a.sourceById('camera').enabled, false, 'the default setup starts without the camera');
  if (a.placementOf('camera')) a.placementOf('camera').visible = false;
  a.toggleVisible('camera');
  assert.equal(a.sourceById('camera').enabled, true, 'showing an off camera turns it on');
  assert.equal(a.placementOf('camera').visible, true);
  assert.doesNotMatch(textOf(h.find('sourcesPane')), /\(off\)/);
  const button = h.find('recCamera');
  assert.ok(button, 'Controls has a camera button');
  assert.match(textOf(button), /Camera on/);
  button.on.click();
  assert.equal(a.sourceById('camera').enabled, false, 'the button turns it off');
  assert.match(textOf(h.find('recCamera')), /Camera off/);
  h.find('recCamera').on.click();
  assert.equal(a.sourceById('camera').enabled, true);
  assert.equal(a.placementOf('camera').visible, true, 'and on again, shown in this scene');
 },
 async studio_first_preview_shows_the_screen() {
  // The stage starts with a placeholder; the first snapshot that loads must replace it (not only update
  // <img class=screen> nodes, of which there are none yet).
  const h = treeHarness(), a = h.a;
  const images = [];
  h.context.Image = class { set src(value) { this.url = value; images.push(this); } };
  a.state.view = 'studio';
  a.studio.tab = 'record';
  a.studio.info = {available: true, settings: {}};
  a.studio.setup = sampleSetup();
  a.studio.devices = {displays: [{number: 1, name: 'Color LCD', pixels: '3024 x 1964'}], cameras: [], microphones: [], ffmpeg: true};
  a.studio.status = {active: false};
  h.context.fetch = async () => response({});
  a.renderStudio(h.main);
  const screens = () => {
   const found = [];
   const walk = (node) => { if (typeof node === 'string') return; const classes = node.className || (node.attrs && node.attrs.class) || ''; if (/\bscreen\b/.test(classes)) found.push(node); (node.children || []).forEach(walk); };
   walk(h.find('stage'));
   return found;
  };
  assert.equal(screens().length, 0, 'no snapshot yet: a placeholder');
  a.startPreview();
  assert.ok(images.length, 'a snapshot is requested');
  images[images.length - 1].onload();
  assert.equal(screens().length, 1, 'the first snapshot is drawn on the stage');
 },
 async project_player_follows_the_voice() {
  // The voice is the clock: a screen video that cannot keep up is nudged or moved, never the microphone.
  const h = harness(), a = h.a;
  a.studio.project = sampleProject();
  const media = (time) => ({currentTime: time, paused: false, ended: false, playbackRate: 1, seeks: 0, play() { this.paused = false; }, pause() { this.paused = true; }});
  const player = {screen: media(2.5), camera: media(2.63), mic: media(2.0), segment: 0, t: 0, playing: true};
  for (const node of [player.screen, player.camera, player.mic]) {
   let value = node.currentTime;
   Object.defineProperty(node, 'currentTime', {get: () => value, set: (next) => { value = next; node.seeks++; }});
  }
  a.studio.player = player;
  assert.equal(a.clockTrack(a.studio.project.segments[0]), 'mic');
  a.syncPlayer();
  assert.equal(player.mic.seeks, 0, 'the microphone is never moved');
  assert.ok(Math.abs(player.t - 2.94) < 1e-9, 'the clock is the voice: 2.0 s into a file that starts at 0.94 s');
  assert.equal(player.screen.seeks, 0, 'a small lag is caught up by playing faster');
  assert.ok(player.screen.playbackRate > 1);
  assert.equal(player.camera.seeks, 0);
  assert.equal(player.camera.playbackRate, 1, 'the camera is in time');
  player.screen.currentTime = 1.0;
  player.screen.seeks = 0;
  a.syncPlayer();
  assert.equal(player.screen.seeks, 1, 'a big lag moves the video');
  assert.ok(Math.abs(player.screen.currentTime - 2.94) < 1e-9);
  assert.equal(player.screen.playbackRate, 1);
  // Without a microphone the screen is the clock, as before.
  delete a.studio.project.segments[0].files.mic;
  assert.equal(a.clockTrack(a.studio.project.segments[0]), 'screen');
 },
 async project_clock_maps_segments() {
  const h = harness();
  const p = {segments: [{duration: 10}, {duration: 5}]};
  assert.deepEqual(plain(h.a.projectClock(p, 12.5)), {segment: 1, local: 2.5});
  assert.deepEqual(plain(h.a.projectClock(p, 99)), {segment: 1, local: 5});
  assert.deepEqual(plain(h.a.projectClock(p, 0)), {segment: 0, local: 0});
  assert.deepEqual(plain(h.a.projectClock(p, 10)), {segment: 1, local: 0}, 'a boundary belongs to the next segment');
  assert.deepEqual(plain(h.a.projectClock(p, -3)), {segment: 0, local: 0});
  assert.deepEqual(plain(h.a.projectClock({segments: []}, 3)), {segment: -1, local: 0});
  // The scene shown at a moment comes from the scene events (marks do not change it).
  const events = {events: [{t: 0, scene: 'screen-camera'}, {t: 4, scene: 'camera'}, {t: 5, mark: 'x'}, {t: 12, scene: 'screen'}]};
  assert.deepEqual([0, 3.9, 4, 6, 12, 50].map(t => h.a.sceneAt(events, t)), ['screen-camera', 'screen-camera', 'camera', 'camera', 'screen', 'screen']);
 },
 async export_dialog_prefill() {
  const h = harness();
  assert.equal(h.a.exportDefaults({export: {canvas: '9:16', height: 1080}}, {export: {canvas: '16:9', height: 1440, fps: 60}}).canvas, '9:16');
  assert.equal(h.a.exportDefaults({}, {export: {canvas: '16:9', height: 1440, fps: 60}}).height, 1440);
  assert.equal(h.a.exportDefaults({mode: 'camera', export: {canvas: '16:9'}}, {export: {height: 1440}}).height, 1080, 'a camera-only project defaults to the camera height');
  assert.equal(h.a.exportDefaults({export: {delete_sources: true}}, {export: {delete_sources: true}}).delete_sources, false, 'deleting the sources is never pre-checked');
  const all = h.a.exportDefaults({}, {});
  assert.deepEqual(plain(all), {canvas: '16:9', height: 1440, fps: 60, codec: 'h264', quality: 'high', container: 'mov', normalize: true, delete_sources: false});
  assert.equal(h.a.exportHeightFor('9:16', 'screen'), 1080, 'a new vertical format starts at 1080');
  assert.equal(h.a.exportHeightFor('16:9', 'screen'), 1440);
  assert.equal(h.a.exportHeightFor('16:9', 'camera'), 1080);
 },
 async export_progress_polls_until_done() {
  const h = treeHarness(), a = h.a;
  const sheet = new h.context.Node('viewerSheet');
  h.main.append(sheet);
  a.studio.setup = sampleSetup();
  const project = sampleProject();
  const answers = [{phase: 'running', percent: 40, eta: 12, project: project.path}, {phase: 'done', percent: 100, output: '/r/talk 16x9.mov', project: project.path}];
  const sent = [];
  h.context.fetch = async (url, options) => {
   sent.push([url, options.body ? JSON.parse(options.body) : null]);
   if (url === '/api/studio/export') return response({queued: true});
   if (url === '/api/studio/export/status') return response(answers.shift());
   return response([]);
  };
  a.renderExportDialog(project);
  assert.match(textOf(sheet), /Export talk/);
  const values = a.exportDefaults(project, a.studio.setup);
  values.canvas = '9:16';
  values.height = 1080;
  await a.startExport(project, values);
  assert.deepEqual(sent[0], ['/api/studio/export', {path: project.path, canvas: '9:16', height: 1080, fps: 60, codec: 'h264', quality: 'high', format: 'mov', normalize: true, delete_sources: false}]);
  assert.match(textOf(h.find('exportState')), /40%/);
  assert.match(textOf(h.find('exportState')), /12 s left/);
  const next = [...h.timers.entries()].find(([, x]) => x.ms === 1000);
  assert.ok(next, 'a running export is polled every second');
  h.timers.delete(next[0]);
  await next[1].fn();
  assert.match(textOf(h.find('exportState')), /Saved talk 16x9\.mov/);
  assert.ok(![...h.timers.values()].some(x => x.ms === 1000), 'polling stops when the export is done');
  // A failed export says why and stops too.
  answers.push({phase: 'failed', error: 'disk full', project: project.path});
  await a.pollExport();
  assert.match(textOf(h.find('exportState')), /Export failed: disk full/);
  assert.ok(![...h.timers.values()].some(x => x.ms === 1000));
  // An audio project exports sound only: no picture choices are sent.
  sent.length = 0;
  answers.push({phase: 'done', output: '/r/voice.m4a'});
  await a.startExport({...project, mode: 'audio'}, a.exportDefaults(project, a.studio.setup));
  assert.deepEqual(sent[0][1], {path: project.path, normalize: true, delete_sources: false});
 },
 async studio_projects_tab_renders() {
  const h = treeHarness(), a = h.a;
  a.state.view = 'studio';
  a.studio.info = {available: true, settings: {}};
  a.studio.setup = sampleSetup();
  a.studio.tab = 'projects';
  a.studio.filter = 'projects';
  a.studio.projects = [{name: 'talk', path: '/p/talk', created: '2026-11-19T22:15:00+04:00', mode: 'screen', state: 'incomplete', problems: ['the camera stopped'], duration: 754.2, size: 1.4e9, tracks: ['screen', 'mic'], exports: ['/r/talk 16x9.mov', '/r/talk 9x16.mp4'], canvas: '16:9'}];
  a.studio.library = [{name: 'shot.png', path: '/s/shot.png', kind: 'image', size: 2000, modified: '2026-11-19T22:00:00+04:00', duration: null}];
  const sent = [];
  h.context.fetch = async (url, options) => {
   sent.push([url, options && options.body ? JSON.parse(options.body) : null]);
   if (url.startsWith('/api/studio/project?')) return response(sampleProject());
   return response({ok: true});
  };
  a.renderStudio(h.main);
  const list = textOf(h.find('studioProjects'));
  assert.match(list, /talk/);
  assert.match(list, /12:34/);
  assert.match(list, /incomplete/);
  assert.match(list, /16:9 MOV/);
  assert.match(list, /9:16 MP4/);
  assert.match(list, /1\.4 GB/);
  assert.match(list, /Open project…/);
  a.studio.filter = 'screenshots';
  a.renderProjects();
  assert.match(textOf(h.find('studioProjects')), /shot\.png/);
  // A project page: preview, scenes on the timeline, layout edits saved to that project.
  await a.openProject('/p/talk');
  assert.ok(sent.some(([url]) => url === '/api/studio/project?path=' + encodeURIComponent('/p/talk')));
  const page = textOf(h.find('studioProjects'));
  assert.match(page, /Screen \+ camera/);
  assert.match(page, /intro done/);
  assert.match(page, /Export…/);
  assert.equal(h.find('stage').children.filter(n => /\bph\b/.test(n.className)).length, 2);
  sent.length = 0;
  a.changePlacement('camera', p => a.pinPlacement(p, 'top-right'));
  const save = [...h.timers.values()].filter(x => x.ms === 500).pop();
  await save.fn();
  const posted = sent.find(([url]) => url === '/api/studio/project');
  assert.ok(posted, 'layout edits on a project page go to that project');
  assert.equal(posted[1].path, '/p/talk');
  assert.equal(posted[1].project.layouts['16:9']['screen-camera'].placements.camera.anchor, 'top-right');
  assert.equal(posted[1].project.path, undefined, 'only project.json keys are sent');
  assert.equal(posted[1].project.size, undefined);
  assert.equal(a.studio.setup.layouts['16:9']['screen-camera'].placements.camera.anchor, 'bottom-left', 'the studio setup is not touched');
  assert.equal(a.studio.player.camera.style.transform, 'scaleX(-1)', 'the camera is mirrored like the export');
  a.changePlacement('camera', p => ({...p, mirror: false}));
  assert.equal(a.studio.player.camera.style.transform, '', 'the reused video element loses the mirror again');
  sent.length = 0;
  await a.projectAction('delete');
  assert.deepEqual(sent[0], ['/api/studio/action', {action: 'delete', path: '/p/talk'}]);
  assert.equal(a.studio.project, null, 'a trashed project closes');
 },
 async studio_shape_math() {
  const h = harness();
  const cam = {visible: true, box: [0, 0.76, 0.24, 0.24], fit: 'cover', focus: [0.5, 0.5], radius: 0, border: {width: 0, color: '#ffc933'}, shadow: false, mirror: true, anchor: 'bottom-left'};
  const circle = h.a.applyShape(cam, 'circle', '16:9');
  assert.ok(Math.abs(circle.box[3] - 0.24 * 16 / 9) < 1e-9);
  assert.ok(Math.abs(circle.box[1] + circle.box[3] - 1) < 1e-9);
  assert.equal(circle.radius, 0.5);
  assert.deepEqual(plain(cam.box), [0, 0.76, 0.24, 0.24], 'shapes never change the placement in place');
  assert.deepEqual(plain(h.a.placementPx(cam, 2560, 1440)), {x: 0, y: 1094, w: 614, h: 346});
  const moved = h.a.snapPlacement({...cam, box: [0.015, 0.75, 0.24, 0.24], anchor: null}, '16:9');
  assert.equal(moved.anchor, 'bottom-left');
  assert.deepEqual(plain(moved.box), [0, 0.76, 0.24, 0.24], 'a snapped box sits flush in the corner');
  assert.equal(h.a.snapPlacement({...cam, box: [0.3, 0.3, 0.24, 0.24]}, '16:9').anchor, null);
  const edge = h.a.snapPlacement({...cam, box: [0.3, 0.01, 0.24, 0.24], anchor: null}, '16:9');
  assert.deepEqual(plain(edge.box), [0.3, 0, 0.24, 0.24], 'near an edge the box snaps to it without a corner');
  const pinned = h.a.pinPlacement({...cam, box: [0.4, 0.4, 0.2, 0.3], anchor: null}, 'top-right');
  assert.ok(Math.abs(pinned.box[0] - 0.8) < 1e-9);
  assert.equal(pinned.box[1], 0);
  const bigger = h.a.resizePlacement(cam, 'top-right', 0.06, 0, true);
  assert.ok(Math.abs(bigger.box[2] - 0.30) < 1e-9 && Math.abs(bigger.box[3] - 0.30) < 1e-9, 'the preset aspect is kept');
  assert.ok(Math.abs(bigger.box[1] + bigger.box[3] - 1) < 1e-9 && bigger.box[0] === 0, 'a pinned box stays in its corner');
  const tiny = h.a.resizePlacement(cam, 'top-right', -1, 0, true);
  assert.ok(tiny.box[2] >= 0.04, 'a box never shrinks to nothing');
  assert.deepEqual(plain(h.a.moveFocus(cam, 0.1, -0.7).focus), [0.4, 1], 'focus moves against the drag and stays inside');
 },
 async studio_shape_parity() {
  // The page and the export (capture_project.apply_shape / pin) must agree on every shape and format.
  const h = harness();
  const cases = [];
  for (const canvas of ['16:9', '9:16', '1:1', '4:5']) for (const shape of ['circle', 'square', 'rounded', 'wide', 'tall']) for (const anchor of [null, 'bottom-left', 'top-right']) {
   const item = {visible: true, box: [0.3, 0.2, 0.45, 0.3], fit: 'cover', focus: [0.5, 0.5], radius: 0, border: {width: 0, color: '#ffc933'}, shadow: false, mirror: false, anchor};
   cases.push({canvas, shape, item, page: plain(h.a.applyShape(item, shape, canvas))});
  }
  const python = execFileSync(process.env.PYTHON || 'python3', ['-c', 'import sys, json; sys.path.insert(0, "src"); from unlawful.capture_project import apply_shape; cases = json.load(sys.stdin); print(json.dumps([apply_shape(c["item"], c["shape"], c["canvas"]) for c in cases]))'], {cwd: path.join(__dirname, '..'), input: JSON.stringify(cases), encoding: 'utf8'});
  JSON.parse(python).forEach((expected, index) => {
   const got = cases[index].page;
   for (let i = 0; i < 4; i++) assert.ok(Math.abs(got.box[i] - expected.box[i]) < 1e-9, JSON.stringify([cases[index].canvas, cases[index].shape, got.box, expected.box]));
   assert.equal(got.radius, expected.radius);
   assert.equal(got.anchor, expected.anchor);
  });
 },
 async studio_keys_and_polling() {
  const h = harness();
  assert.equal(h.a.studioKey('KeyR', {active: false}), 'record');
  assert.equal(h.a.studioKey('KeyR', {active: true}), 'stop');
  assert.equal(h.a.studioKey('KeyP', {active: true}), 'pause');
  assert.equal(h.a.studioKey('KeyM', {active: true}), 'mark');
  assert.equal(h.a.studioKey('Digit3', {active: true, scenes: ['screen-camera', 'screen', 'camera']}), 'scene:camera');
  assert.equal(h.a.studioKey('Digit9', {active: true, scenes: ['screen-camera']}), null, 'a missing scene is no key');
  assert.equal(h.a.studioKey('KeyR', {active: false, typing: true}), null, 'keys are ignored while typing');
  assert.equal(h.a.studioKey('KeyQ', {active: false}), null);
  assert.equal(h.a.studioPollDelay(false, true, true), null);
  assert.equal(h.a.studioPollDelay(true, true, true), 1000);
  assert.equal(h.a.studioPollDelay(true, true, false), 5000);
  assert.equal(h.a.studioPollDelay(true, false, false), 5000);
  assert.deepEqual(plain(h.a.countdownSteps(3)), [3, 2, 1]);
  assert.deepEqual(plain(h.a.countdownSteps(0)), []);
 },
 async studio_countdown_then_record() {
  const h = harness();
  h.a.state.view = 'studio';
  h.a.studio.setup = sampleSetup();
  h.a.studio.setup.countdown = 3;
  const sent = [];
  h.context.fetch = async (url, options) => { sent.push(url); return response({active: true, phase: 'recording', elapsed: 0}); };
  const job = h.a.toggleRecord();
  assert.equal(sent.length, 0, 'nothing records during the countdown');
  assert.equal(h.a.studio.counting, 3);
  for (const left of [2, 1]) {
   const tick = [...h.timers.entries()].find(([, x]) => x.ms === 1000);
   h.timers.delete(tick[0]);
   tick[1].fn();
   assert.equal(h.a.studio.counting, left);
  }
  const last = [...h.timers.entries()].find(([, x]) => x.ms === 1000);
  h.timers.delete(last[0]);
  last[1].fn();
  await job;
  assert.deepEqual(sent, ['/api/studio/record']);
  // R again during a countdown cancels it.
  h.a.studio.status = {active: false};
  sent.length = 0;
  const second = h.a.toggleRecord();
  await h.a.toggleRecord();
  await second;
  assert.equal(h.a.studio.counting, 0);
  assert.equal(sent.length, 0, 'a cancelled countdown never records');
 },
 async studio_setup_save_is_debounced() {
  const h = harness();
  h.a.studio.setup = sampleSetup();
  const sent = [];
  h.context.fetch = async (url, options) => { sent.push([url, JSON.parse(options.body)]); return response(JSON.parse(options.body)); };
  h.a.studio.setup.canvas = '9:16';
  h.a.saveSetupSoon();
  h.a.studio.setup.canvas = '1:1';
  h.a.saveSetupSoon();
  const pending = [...h.timers.values()].filter(x => x.ms === 500);
  assert.equal(pending.length, 1, 'two edits within 500 ms wait for one save');
  await pending[0].fn();
  assert.equal(sent.length, 1);
  assert.equal(sent[0][0], '/api/studio/setup');
  assert.equal(sent[0][1].canvas, '1:1', 'the last value is saved');
  // A refused setup is reported and reloaded from the server.
  h.context.fetch = async (url, options) => options && options.method === 'POST' ? {status: 400, json: async () => ({error: 'setup.countdown: bad'})} : response(sampleSetup());
  h.a.studio.setup.countdown = 99;
  h.a.saveSetupSoon();
  await [...h.timers.values()].filter(x => x.ms === 500).pop().fn();
  assert.equal(h.ids.get('toast').textContent, 'setup.countdown: bad');
  assert.equal(h.a.studio.setup.countdown, 3);
 },
 async studio_permission_banner() {
  const h = harness();
  const banner = h.a.permissionBanner({screen: false, app: 'Zed'});
  assert.match(textOf(banner), /Zed/);
  assert.match(textOf(banner), /Screen Recording/);
  assert.equal(h.a.permissionBanner({screen: true, app: 'Zed'}), null);
  assert.match(textOf(h.a.permissionBanner({screen: false, app: null})), /the app that runs ul/);
  const sent = [];
  h.context.fetch = async (url, options) => { sent.push([url, JSON.parse(options.body)]); return response({screen: false, app: 'Zed'}); };
  await h.a.openSettings('screen');
  assert.deepEqual(sent, [['/api/studio/open-settings', {kind: 'screen'}]]);
 },
 async rec_pill_shows_terminal_recordings() {
  const h = harness();
  h.a.state.view = 'board';
  h.a.studio.info = {available: true};
  h.run('loadBoard=async()=>{};loadBoards=async()=>{};loadTimer=async()=>{};loadGames=async()=>{};loadStudioInfo=async()=>{};render=()=>{};');
  h.context.fetch = async () => response({active: true, phase: 'recording', elapsed: 2, paused: false});
  await h.a.start();
  const poll = [...h.timers.entries()].find(([, x]) => x.ms === 5000);
  h.timers.delete(poll[0]);
  await poll[1].fn();
  assert.match(h.ids.get('recPill').textContent, /^REC 00:0[23]$/);
  assert.ok([...h.timers.values()].some(x => x.ms === 5000), 'off the Studio tab a recording is polled every 5 s');
 },
 async game_network() {
  const h = harness();
  h.a.arcade.session = 'session';
  h.context.fetch = async () => { throw Error('connection reset'); };
  await h.a.sendGame([{key: 'up'}]).catch(() => {});
  assert.equal(h.a.arcade.sending, false, 'input sender must recover from fetch failure');
  let calls = 0;
  h.context.fetch = async () => { calls++; return response({}); };
  await h.a.sendGame([{key: 'down'}]);
  assert.equal(calls, 1);
 },
 async canvas_prng_and_rough() {
  const h = harness(), a = h.a;
  const one = a.mulberry32(42), two = a.mulberry32(42), other = a.mulberry32(43);
  const first = [one(), one(), one()], second = [two(), two(), two()];
  assert.equal(JSON.stringify(first), JSON.stringify(second), 'same seed, same sequence');
  assert.notEqual(JSON.stringify(first), JSON.stringify([other(), other(), other()]));
  assert.ok(first.every(v => v >= 0 && v < 1));
  const rect = {id: 'r', type: 'rectangle', x: 0, y: 0, width: 100, height: 50, stroke: '#000000', fill: null, strokeWidth: 2, roughness: 1, seed: 1};
  const again = {...rect}, moved = {...rect, seed: 2};
  assert.equal(JSON.stringify(a.roughStrokes(rect)), JSON.stringify(a.roughStrokes(again)), 'strokes depend only on the element');
  assert.notEqual(JSON.stringify(a.roughStrokes(rect)), JSON.stringify(a.roughStrokes(moved)));
  const clean = plain(a.roughStrokes({...rect, roughness: 0}));
  assert.equal(clean.length, 1, 'roughness 0 draws one clean pass');
  assert.equal(clean[0].smooth, false);
  assert.equal(JSON.stringify(clean[0].pts), JSON.stringify([[0, 0], [100, 0], [100, 50], [0, 50], [0, 0]]));
  const wild = plain(a.roughStrokes({...rect, roughness: 2}));
  assert.equal(wild.length, 8, 'two passes of four edges');
  for (const s of wild) for (const [x, y] of s.pts) assert.ok(x > -8 && x < 108 && y > -8 && y < 58, 'jitter stays small');
 },
 async canvas_view_transforms() {
  const h = harness(), a = h.a;
  const view = {x: 10, y: 20, z: 1};
  const s = plain(a.toScreen({x: 5, y: -5, z: 2}, 3, 4));
  assert.equal(s.x, 11); assert.equal(s.y, 3);
  const w = plain(a.toWorld({x: 5, y: -5, z: 2}, s.x, s.y));
  assert.equal(w.x, 3); assert.equal(w.y, 4);
  const before = plain(a.toWorld(view, 300, 200));
  const zoomed = plain(a.zoomAt(view, 300, 200, 2));
  const after = plain(a.toWorld(zoomed, 300, 200));
  assert.ok(Math.abs(before.x - after.x) < 1e-9 && Math.abs(before.y - after.y) < 1e-9, 'zoom keeps the point under the cursor');
  assert.equal(a.zoomAt(view, 0, 0, 100).z, 4);
  assert.equal(a.zoomAt(view, 0, 0, 0.00001).z, 0.1);
  const fit = plain(a.fitView({x: 0, y: 0, width: 1000, height: 500}, 1000, 600));
  assert.ok(Math.abs(fit.z - 0.88) < 1e-9);
  const middle = plain(a.toScreen(fit, 500, 250));
  assert.ok(Math.abs(middle.x - 500) < 1e-6 && Math.abs(middle.y - 300) < 1e-6);
  assert.equal(a.fitView(null, 800, 600).z, 1);
 },
 async canvas_hit_testing() {
  const h = harness(), a = h.a;
  const base = {strokeWidth: 2, seed: 1, roughness: 1, stroke: '#000000', fill: null};
  const rect = {...base, id: 'r', type: 'rectangle', x: 0, y: 0, width: 100, height: 50};
  assert.equal(a.hitElement(rect, 50, 0, 4), true, 'border');
  assert.equal(a.hitElement(rect, 50, 25, 4), false, 'empty inside of an unfilled shape');
  assert.equal(a.hitElement({...rect, fill: '#ff0000'}, 50, 25, 4), true, 'filled inside');
  assert.equal(a.hitElement(rect, 200, 200, 4), false);
  const oval = {...base, id: 'o', type: 'ellipse', x: 0, y: 0, width: 100, height: 50};
  assert.equal(a.hitElement(oval, 100, 25, 4), true);
  assert.equal(a.hitElement(oval, 50, 25, 4), false);
  assert.equal(a.hitElement({...oval, fill: '#00ff00'}, 50, 25, 4), true);
  const diamond = {...base, id: 'd', type: 'diamond', x: 0, y: 0, width: 100, height: 50};
  assert.equal(a.hitElement(diamond, 50, 0, 4), true);
  assert.equal(a.hitElement(diamond, 1, 1, 4), false, 'the corner of the bounding box is outside a diamond');
  const line = {...base, id: 'l', type: 'line', x: 0, y: 0, width: 100, height: 100, points: [[0, 0], [100, 100]]};
  assert.equal(a.hitElement(line, 50, 52, 4), true);
  assert.equal(a.hitElement(line, 0, 100, 4), false);
  const text = {...base, id: 't', type: 'text', x: 10, y: 10, width: 80, height: 30, text: 'hi', fontSize: 24};
  assert.equal(a.hitElement(text, 20, 20, 2), true);
  assert.equal(a.hitElement(text, 120, 20, 2), false);
  const tall = {...rect, fill: '#ff0000', width: 100, height: 20, angle: Math.PI / 2};
  assert.equal(a.hitElement(tall, 80, 10, 1), false, 'outside once the shape is turned');
  assert.equal(a.hitElement(tall, 50, 90, 1), false);
  assert.equal(a.hitElement(tall, 50, 40, 1), true, 'inside the turned shape');
  const doc = plain(sampleShape().canvas);
  doc.unlaw.elements.push({...base, id: 'top', type: 'rectangle', x: 0, y: 0, width: 150, height: 150, fill: '#ff0000'});
  assert.equal(a.hitTest(doc, 20, 20, 1), 'x:top', 'drawings are above nodes');
  assert.equal(a.hitTest(doc, 500, 50, 1), 'n:n2', 'a node wins over the group below it');
  assert.equal(a.hitTest(doc, 300, 150, 1), null, 'the inside of a group is not part of the group');
  assert.equal(a.hitTest(doc, 300, 200, 1), 'n:g1', 'the border of a group');
  assert.equal(a.hitTest(doc, 300, 51, 1), 'e:e1', 'an edge');
  const curve = plain(a.edgeCurve({x: 0, y: 0, width: 200, height: 100}, 'right', {x: 400, y: 0, width: 200, height: 100}, 'left'));
  assert.equal(curve.p0.x, 200); assert.equal(curve.p3.x, 400);
  assert.equal(a.hitEdge(curve, 300, 50, 4), true);
  assert.equal(a.hitEdge(curve, 300, 80, 4), false);
  const box = {x: 0, y: 0, width: 200, height: 100};
  assert.equal(a.nearestSide(box, 230, 50), 'right');
  assert.equal(a.nearestSide(box, 100, -30), 'top');
  assert.equal(a.nearestSide(box, 100, 140), 'bottom');
  assert.equal(a.nearestSide(box, -20, 50), 'left');
 },
 async canvas_resize() {
  const h = harness(), a = h.a;
  const box = {x: 0, y: 0, width: 100, height: 50};
  assert.equal(JSON.stringify(plain(a.resizeBox(box, 'se', 20, 10))), JSON.stringify({x: 0, y: 0, width: 120, height: 60}));
  assert.equal(JSON.stringify(plain(a.resizeBox(box, 'nw', 30, 10))), JSON.stringify({x: 30, y: 10, width: 70, height: 40}));
  assert.equal(a.resizeBox(box, 'se', -500, 0).width, 8, 'never smaller than the minimum');
  const nw = plain(a.resizeBox(box, 'nw', 500, 0));
  assert.equal(nw.x, 92); assert.equal(nw.width, 8);
  const view = {x: 0, y: 0, z: 2};
  assert.equal(a.handleAt(box, 201, 99, view), 'se');
  assert.equal(a.handleAt(box, 1, 1, view), 'nw');
  assert.equal(a.handleAt(box, 100, 50, view), null);
  const line = {id: 'l', type: 'line', x: 0, y: 0, width: 100, height: 100, points: [[0, 0], [100, 100]], custom: 1};
  const orig = JSON.parse(JSON.stringify(line));
  a.applyBox(line, orig, {x: 10, y: 20, width: 200, height: 50});
  assert.equal(line.x, 10); assert.equal(line.width, 200);
  assert.equal(JSON.stringify(plain(line.points)), JSON.stringify([[0, 0], [200, 50]]));
  assert.equal(line.custom, 1, 'resizing keeps other keys');
  const text = {id: 't', type: 'text', x: 0, y: 0, width: 100, height: 30, fontSize: 20, text: 'a'};
  a.applyBox(text, JSON.parse(JSON.stringify(text)), {x: 0, y: 0, width: 200, height: 60});
  assert.equal(text.fontSize, 40);
 },
 async canvas_text_wrap_and_ink() {
  const h = harness(), a = h.a;
  const measure = s => s.length * 10;
  assert.equal(JSON.stringify(plain(a.wrapText(measure, 'aaaa bbbb cc', 50))), JSON.stringify(['aaaa', 'bbbb', 'cc']));
  assert.equal(JSON.stringify(plain(a.wrapText(measure, 'abcdefghij', 50))), JSON.stringify(['abcde', 'fghij']));
  assert.equal(JSON.stringify(plain(a.wrapText(measure, 'a\n\nb', 50))), JSON.stringify(['a', '', 'b']));
  assert.equal(a.adaptInk('#1d1d1f', true), '#ececee', 'near black ink is readable on dark');
  assert.equal(a.adaptInk('#1d1d1f', false), '#1d1d1f');
  assert.equal(a.adaptInk('#f2f2f5', false), '#1d1d1f', 'near white ink is readable on light');
  assert.equal(a.adaptInk('#e5484d', true), '#e5484d');
  assert.equal(a.adaptInk('url(x)', false), '#1d1d1f', 'a bad color falls back');
  assert.equal(a.nodeColor('3'), '#e8b520');
  assert.equal(a.nodeColor('#abc'), '#abc');
  assert.equal(a.nodeColor('red'), null);
  assert.equal(a.nodeColor('#12345;x'), null);
  assert.equal(a.noteName('notes/Idea.md'), 'Idea');
  assert.equal(a.noteName('Idea.MD'), 'Idea');
  assert.equal(a.noteName('pic.png'), null);
 },
 async canvas_shapes_and_styles() {
  const h = harness(), a = h.a;
  const arrow = plain(a.makeLinear('arrow', 100, 100, 50, 160, {stroke: '#e5484d', fill: null, width: 4, rough: 1}, 9));
  assert.equal(arrow.x, 50); assert.equal(arrow.y, 100); assert.equal(arrow.width, 50); assert.equal(arrow.height, 60);
  assert.equal(JSON.stringify(arrow.points), JSON.stringify([[50, 0], [0, 60]]));
  assert.equal(arrow.seed, 9); assert.equal(arrow.stroke, '#e5484d'); assert.equal(arrow.strokeWidth, 4);
  const snapped = plain(a.snapAngle(100, 10));
  assert.ok(Math.abs(snapped.dy) < 1e-9 && snapped.dx > 99);
  const diag = plain(a.snapAngle(50, 60));
  assert.ok(Math.abs(Math.abs(diag.dx) - Math.abs(diag.dy)) < 1e-9, '45 degree snap');
  const pen = plain(a.makeFreedraw([[10, 10], [20, 5], [30, 40]], {stroke: '#000000', fill: null, width: 2, rough: 1}, 3));
  assert.equal(pen.x, 10); assert.equal(pen.y, 5); assert.equal(pen.width, 20); assert.equal(pen.height, 35);
  assert.equal(JSON.stringify(pen.points), JSON.stringify([[0, 5], [10, 0], [20, 35]]));
  const doc = plain(sampleShape().canvas);
  a.applyStyle(doc, ['x:x1', 'n:n1', 'e:e1'], {stroke: '#30a46c', fill: '#30a46c', strokeWidth: 8, roughness: 0});
  const x1 = doc.unlaw.elements[0];
  assert.equal(x1.stroke, '#30a46c'); assert.equal(x1.fill, '#30a46c'); assert.equal(x1.strokeWidth, 8); assert.equal(x1.roughness, 0);
  assert.equal(doc.nodes[0].color, '#30a46c'); assert.equal(doc.edges[0].color, '#30a46c');
  assert.equal('strokeWidth' in doc.nodes[0], false, 'nodes only take the color');
  assert.equal(x1.custom, 'k');
 },
 async canvas_structure_edits() {
  const h = harness(), a = h.a;
  const doc = plain(sampleShape().canvas);
  const inside = plain(a.containedIds(doc, doc.nodes[2]));
  assert.equal(JSON.stringify(inside.sort()), JSON.stringify(['n:n1', 'n:n2']));
  const key = a.groupAround(doc, ['n:n1', 'n:n2'], 'grp');
  assert.equal(key, 'n:grp');
  const group = doc.nodes[0];
  assert.equal(group.id, 'grp'); assert.equal(group.type, 'group');
  assert.equal(group.x, -24); assert.equal(group.y, -24); assert.equal(group.width, 648); assert.equal(group.height, 148);
  assert.equal(a.groupAround(doc, ['e:e1'], 'none'), null, 'an edge alone has no box');
  a.moveItems(doc, ['n:n1', 'x:x1', 'e:e1'], 5, -5);
  const n1 = doc.nodes.find(n => n.id === 'n1');
  assert.equal(n1.x, 5); assert.equal(n1.y, -5);
  assert.equal(doc.unlaw.elements[0].x, 15);
  assert.equal('x' in doc.edges[0], false, 'edges follow their nodes and have no position');
  const removed = a.removeItems(doc, ['n:n1']);
  assert.equal(removed, 1);
  assert.equal(doc.edges.length, 0, 'edges of a deleted node go with it');
  assert.equal(doc.nodes.some(n => n.id === 'n1'), false);
  const fresh = plain(sampleShape().canvas);
  const bundle = a.copyItems(fresh, ['n:n1', 'n:n2']);
  let counter = 0;
  const keys = plain(a.pasteItems(fresh, bundle, 20, () => 'copy' + ++counter));
  assert.equal(keys.length, 3, 'two nodes and the edge between them');
  const copy = fresh.nodes.find(n => n.id === 'copy1');
  assert.equal(copy.x, 20); assert.equal(copy.plugin.a, 1, 'unknown keys survive a copy');
  assert.equal(fresh.nodes.find(n => n.id === 'n1').x, 0, 'the original stays');
  const edge = fresh.edges.find(e => e.id.startsWith('copy'));
  assert.equal(edge.fromNode, 'copy1'); assert.equal(edge.toNode, 'copy2'); assert.equal(edge.obsidianExtra, true);
 },
 async canvas_history() {
  const h = harness(), a = h.a;
  const hist = a.makeHistory(3, 's0');
  for (const s of ['s1', 's2', 's3', 's4']) assert.equal(a.histCommit(hist, s, false), true);
  assert.equal(a.histCommit(hist, 's4', false), false, 'no change, no entry');
  assert.equal(hist.undo.length, 3, 'capped');
  assert.equal(a.histUndo(hist), 's3');
  assert.equal(a.histRedo(hist), 's4');
  assert.equal(a.histRedo(hist), null);
  a.histUndo(hist);
  a.histCommit(hist, 'new', false);
  assert.equal(hist.redo.length, 0, 'a new change drops the redo line');
  const merged = a.makeHistory(10, 'a');
  a.histCommit(merged, 'b', false);
  a.histCommit(merged, 'c', true);
  assert.equal(merged.undo.length, 1, 'merged commits share one undo step');
  assert.equal(a.histUndo(merged), 'a');
  a.cvLoad(sampleShape());
  a.moveItems(a.cv.doc, ['n:n1'], 50, 0);
  a.cvCommit('move');
  assert.equal(a.cv.doc.nodes[0].x, 50);
  a.cvUndo();
  assert.equal(a.cv.doc.nodes[0].x, 0);
  assert.equal(a.cv.doc.nodes[0].plugin.a, 1, 'undo restores unknown keys too');
  a.cvRedo();
  assert.equal(a.cv.doc.nodes[0].x, 50);
  for (let i = 0; i < 150; i++) { a.moveItems(a.cv.doc, ['n:n1'], 1, 0); a.cvCommit('step' + i); }
  assert.equal(a.cv.hist.undo.length, 100);
 },
 async canvas_save_keeps_unknown_keys() {
  const h = harness(), a = h.a;
  const shape = sampleShape();
  shape.canvas.unlaw.elements.push({id: 'odd', type: 'rectangle', x: 'bad'}, {id: 'future', type: 'hologram', x: 1, y: 1, width: 2, height: 2, extra: [1]});
  a.cvLoad(shape);
  a.moveItems(a.cv.doc, ['n:n1', 'x:x1'], 10, 5);
  a.cvCommit('move');
  assert.equal(a.cv.dirty, true);
  const sent = [];
  h.context.fetch = async (path, options) => { sent.push({path, options}); return response({path: '/c/a.canvas', name: 'a', version: 'v2', canvas: {}}); };
  await a.saveCanvas();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].path, '/api/canvas');
  assert.equal(sent[0].options.method, 'POST');
  const body = JSON.parse(sent[0].options.body);
  assert.equal(body.path, '/c/a.canvas'); assert.equal(body.version, 'v1');
  const doc = body.canvas;
  assert.equal(JSON.stringify(doc.extra), JSON.stringify({keep: 1}), 'document keys');
  assert.equal(doc.nodes[0].plugin.a, 1); assert.equal(doc.nodes[0].x, 10);
  assert.equal(doc.nodes[1].subpath, '#h');
  assert.equal(doc.edges[0].obsidianExtra, true);
  assert.equal(doc.unlaw.future, 'yes');
  assert.equal(doc.unlaw.elements[0].custom, 'k'); assert.equal(doc.unlaw.elements[0].x, 20); assert.equal(doc.unlaw.elements[0].y, 305);
  assert.equal(doc.unlaw.elements.length, 3, 'malformed and unknown elements are kept untouched');
  assert.equal(doc.unlaw.elements[1].x, 'bad');
  assert.equal(doc.unlaw.elements[2].extra[0], 1);
  assert.equal(a.cv.version, 'v2'); assert.equal(a.cv.dirty, false);
  a.cvLoad({path: '/c/b.canvas', name: 'b', version: 'w', canvas: {}});
  assert.equal(Array.isArray(a.cv.doc.nodes) && Array.isArray(a.cv.doc.edges), true, 'a bare document gets node and edge lists');
  assert.equal('unlaw' in a.cv.doc, false, 'drawings are only added when something is drawn');
 },
 async canvas_save_conflict_reloads() {
  const h = harness(), a = h.a;
  a.cvLoad(sampleShape());
  a.moveItems(a.cv.doc, ['n:n1'], 10, 0);
  a.cvCommit('move');
  const fresh = sampleShape();
  fresh.version = 'v3'; fresh.canvas.nodes[0].text = 'from elsewhere';
  h.context.fetch = async () => ({status: 409, json: async () => ({error: 'changed', canvas: fresh})});
  await a.saveCanvas();
  assert.equal(a.cv.version, 'v3');
  assert.equal(a.cv.doc.nodes[0].text, 'from elsewhere');
  assert.equal(a.cv.doc.nodes[0].x, 0, 'nothing is re-applied');
  assert.equal(a.cv.dirty, false);
  assert.equal(h.ids.get('toast').textContent, 'Canvas changed elsewhere; reloaded');
  let calls = 0;
  h.context.fetch = async () => { calls++; return response({}); };
  await a.saveCanvas();
  assert.equal(calls, 0, 'nothing to save after the reload');
 },
 async canvas_save_waits_for_drag() {
  const h = harness(), a = h.a;
  a.cvLoad(sampleShape());
  a.moveItems(a.cv.doc, ['n:n1'], 10, 0);
  a.cvCommit('move');
  a.cv.drag = {mode: 'move'};
  let calls = 0;
  h.context.fetch = async () => { calls++; return response({version: 'v9'}); };
  await a.saveCanvas();
  assert.equal(calls, 0, 'a half-finished drag is never written');
  assert.equal(a.cv.dirty, true);
  a.cv.drag = null;
  await a.saveCanvas();
  assert.equal(calls, 1);
 },
 async canvas_poll() {
  const h = harness(), a = h.a;
  h.run('render=()=>{};');
  a.state.view = 'canvas';
  a.cvLoad(sampleShape());
  const reply = (version) => { const s = sampleShape(); s.version = version; s.canvas.nodes = []; return s; };
  const requests = [];
  h.context.fetch = async (path) => { requests.push(path); return response(reply('v1')); };
  await a.pollCanvas();
  assert.equal(requests.length, 1);
  assert.equal(requests[0], '/api/canvas?path=' + encodeURIComponent('/c/a.canvas'));
  assert.equal(a.cv.doc.nodes.length, 3, 'same version, nothing reloaded');
  h.context.fetch = async () => response(reply('v2'));
  a.cv.dirty = true; await a.pollCanvas(); assert.equal(a.cv.version, 'v1', 'unsaved changes are not replaced');
  a.cv.dirty = false; a.cv.drag = {mode: 'move'}; await a.pollCanvas(); assert.equal(a.cv.version, 'v1', 'not while dragging');
  a.cv.drag = null; a.cv.editing = {key: 'n:n1'}; await a.pollCanvas(); assert.equal(a.cv.version, 'v1', 'not while editing');
  a.cv.editing = null; a.state.view = 'board'; await a.pollCanvas(); assert.equal(a.cv.version, 'v1', 'not when the tab is not open');
  a.state.view = 'canvas';
  await a.pollCanvas();
  assert.equal(a.cv.version, 'v2');
  assert.equal(a.cv.doc.nodes.length, 0);
 },
 async canvas_keys_stay_in_their_view() {
  const h = harness(), a = h.a;
  h.run('render=()=>{};');
  a.cvLoad(sampleShape());
  const press = (view, event) => {
   a.state.view = view;
   const e = {metaKey: false, ctrlKey: false, altKey: false, shiftKey: false, prevented: false, preventDefault() { this.prevented = true; }, ...event};
   for (const fn of h.listeners.keydown || []) fn(e);
   return e;
  };
  press('canvas', {key: 'r'});
  assert.equal(a.cv.tool, 'rectangle');
  press('canvas', {key: 'V'});
  assert.equal(a.cv.tool, 'select');
  let fetches = 0;
  h.context.fetch = async () => { fetches++; return response({}); };
  const space = press('canvas', {key: ' '});
  assert.equal(space.prevented, true);
  assert.equal(fetches, 0, 'space pans instead of starting the timer');
  press('canvas', {key: 'n'});
  assert.equal(a.cv.tool, 'card', 'n is the card tool here, not the board quick-add');
  press('canvas', {key: '/'});
  assert.equal(a.state.view, 'canvas', 'board keys do nothing here');
  press('canvas', {key: 'v'});
  press('board', {key: 'r'});
  assert.equal(a.cv.tool, 'select', 'canvas keys do nothing on the board');
  press('board', {key: 'p'});
  assert.equal(a.cv.tool, 'select');
  h.context.document.activeElement = {tagName: 'TEXTAREA', blur() {}};
  press('canvas', {key: 'e'});
  assert.equal(a.cv.tool, 'select', 'typing is never a shortcut');
  h.context.document.activeElement = {tagName: 'DIV'};
  press('canvas', {key: 'a', metaKey: true});
  assert.equal(a.cv.sel.length, 5, 'select all: nodes, edge and drawings');
  press('canvas', {key: 'Delete'});
  assert.equal(a.cv.doc.nodes.length, 0);
  assert.equal(a.cv.doc.edges.length, 0);
  press('canvas', {key: 'z', metaKey: true});
  assert.equal(a.cv.doc.nodes.length, 3, 'undo');
  press('canvas', {key: 'z', metaKey: true, shiftKey: true});
  assert.equal(a.cv.doc.nodes.length, 0, 'redo');
  assert.equal(a.cv.sel.length, 0);
  // Board keys go by the physical key, so a Russian layout ("/" types ".", "n" types "т") works too.
  let searched = 0;
  h.ids.get('search').focus = () => { searched++; };
  const slash = press('board', {key: '.', code: 'Slash'});
  assert.equal(searched, 1, 'the / key focuses the search in any layout');
  assert.equal(slash.prevented, true);
  press('board', {key: '?', code: 'Slash', shiftKey: true});
  assert.equal(searched, 1, 'Shift+/ is the help, not the search');
  press('canvas', {key: '1'});
  assert.equal(a.state.view, 'board', 'number keys still switch tabs');
 },
 async canvas_interaction_flow() {
  const h = harness(), a = h.a;
  const ctx = new Proxy({font: '', measureText: text => ({width: String(text).length * 7})}, {
   get: (target, prop) => (prop in target ? target[prop] : () => {}),
   set: (target, prop, value) => { target[prop] = value; return true; },
  });
  const fake = tag => {
   const node = new h.context.Node();
   node.tagName = tag.toUpperCase();
   node.getBoundingClientRect = () => ({left: 0, top: 0, width: 800, height: 600});
   node.getContext = () => ctx;
   node.focus = () => {};
   node.select = () => {};
   node.click = () => { node.clicked = true; };
   node.setPointerCapture = () => {};
   node.toBlob = callback => callback(new Blob(['x']));
   return node;
  };
  h.context.document.createElement = fake;
  h.context.getComputedStyle = () => ({getPropertyValue: () => '#336699'});
  const shape = sampleShape();
  h.context.fetch = async path => {
   if (path === '/api/canvases') return response({dir: '/c', current: '/c/a.canvas', items: [{path: '/c/a.canvas', name: 'a'}]});
   if (path.startsWith('/api/canvas')) return response(shape);
   return response({});
  };
  a.state.view = 'canvas';
  const main = fake('main');
  a.renderCanvas(main);
  for (let i = 0; i < 3; i++) await new Promise(resolve => setImmediate(resolve));
  assert.equal(a.cv.path, '/c/a.canvas', 'the current canvas opens on entering the tab');
  assert.equal(a.cv.w, 800);
  a.cv.view = {x: 0, y: 0, z: 1};
  const at = (x, y, extra = {}) => ({button: 0, clientX: x, clientY: y, pointerId: 1, shiftKey: false, preventDefault() {}, ...extra});
  const drag = (from, to) => { a.cvDown(at(...from)); a.cvMove(at(...to)); a.cvUp(at(...to)); };

  a.cvSetTool('rectangle');
  drag([100, 300], [220, 380]);
  const drawn = a.cv.doc.unlaw.elements.at(-1);
  assert.equal(drawn.type, 'rectangle');
  assert.equal(drawn.width, 120); assert.equal(drawn.height, 80);
  assert.equal(typeof drawn.seed, 'number');
  assert.equal(a.cv.tool, 'rectangle', 'the tool stays until the user picks another');
  assert.equal(a.cv.sel[0], 'x:' + drawn.id);
  assert.equal(a.cv.doc.unlaw.future, 'yes', 'the drawing joined the existing unlaw object');

  drag([300, 420], [340, 460]);
  assert.equal(a.cv.doc.unlaw.elements.at(-1).type, 'rectangle', 'a second rectangle without picking the tool again');
  a.cv.doc.unlaw.elements.pop();
  a.cvDown(at(10, 10)); a.cvUp(at(11, 11));
  assert.equal(a.cv.doc.unlaw.elements.length, 2, 'a click without a drag draws nothing');

  a.cvSetTool('freedraw');
  a.cvDown(at(300, 300)); a.cvMove(at(320, 310)); a.cvMove(at(340, 305)); a.cvUp(at(340, 305));
  assert.equal(a.cv.doc.unlaw.elements.at(-1).type, 'freedraw');
  assert.equal(a.cv.tool, 'freedraw', 'the pen stays active');

  a.cvSetTool('card');
  a.cvDown(at(50, 400)); a.cvUp(at(51, 401));
  const card = a.cv.doc.nodes.at(-1);
  assert.equal(card.type, 'text'); assert.equal(card.width, 260);
  assert.ok(a.cv.editing, 'a new card opens its editor');
  a.cv.ui.editor.value = 'hello <b>there</b>';
  const undoDepth = a.cv.hist.undo.length;
  a.cvEndEdit();
  assert.equal(card.text, 'hello <b>there</b>', 'text is stored as typed');
  assert.equal(a.cv.hist.undo.length, undoDepth + 1, 'creating and typing is one step');

  assert.equal(a.cv.tool, 'card', 'the card tool stays too');
  a.cvSetTool('select');
  a.cvMove(at(100, 50));
  assert.equal(a.cv.hover, 'n:n1');
  a.cvDown(at(200, 50));
  assert.equal(a.cv.drag.mode, 'connect', 'the side dot starts an edge');
  a.cvMove(at(420, 50)); a.cvUp(at(420, 50));
  const edge = a.cv.doc.edges.at(-1);
  assert.equal(edge.fromNode, 'n1'); assert.equal(edge.fromSide, 'right');
  assert.equal(edge.toNode, 'n2'); assert.equal(edge.toSide, 'left'); assert.equal(edge.toEnd, 'arrow');

  a.cvDown(at(100, 80)); a.cvMove(at(160, 80)); a.cvUp(at(160, 80));
  assert.equal(a.cv.doc.nodes.find(n => n.id === 'n1').x, 60, 'dragging a card moves it');
  assert.equal(a.cv.doc.nodes.find(n => n.id === 'n1').plugin.a, 1);

  a.cvDown(at(-40, -80)); a.cvMove(at(700, 150)); a.cvUp(at(700, 150));
  assert.ok(a.cv.sel.includes('n:n1') && a.cv.sel.includes('n:n2'), 'a marquee selects what it touches');

  a.cvSetTool('eraser');
  const before = a.cv.doc.unlaw.elements.length;
  a.cvDown(at(160, 300)); a.cvUp(at(160, 300));
  assert.equal(a.cv.doc.unlaw.elements.length, before - 1, 'the eraser removes what it touches');

  const zoom = a.cv.view.z;
  a.cvWheel({preventDefault() {}, ctrlKey: true, deltaY: -100, deltaX: 0, deltaMode: 0, clientX: 400, clientY: 300});
  assert.ok(a.cv.view.z > zoom, 'ctrl+wheel zooms in');
  const x = a.cv.view.x;
  a.cvWheel({preventDefault() {}, ctrlKey: false, deltaY: 30, deltaX: 20, deltaMode: 0, clientX: 400, clientY: 300});
  assert.equal(a.cv.view.x, x - 20, 'plain wheel pans');

  for (const ui of [null, {sel: new Set(['n:n1', 'x:x1', 'e:e1']), hover: 'n:n2', drag: null, editing: null, tool: 'select', draft: null}]) {
   a.paintScene({ctx, doc: a.cv.doc, view: a.cv.view, w: 800, h: 600, pal: a.cvPalette(), scale: 2, ui});
  }
  a.cvSelect(['n:n1', 'n:n2']);
  a.cvGroup();
  assert.equal(a.cv.doc.nodes[0].type, 'group', 'G wraps the selection');
  a.cvExport();
  const link = h.context.document.body.children.at(-1);
  assert.equal(link.isConnected, false, 'the temporary download link is removed');
 },
 async canvas_fill_tool() {
  const h = harness(), a = h.a;
  const doc = plain(sampleShape().canvas);
  const ring = [[0, 0], [100, 0], [100, 100], [0, 100], [4, 6]];
  doc.unlaw.elements.push(
   {id: 'p1', type: 'freedraw', x: 600, y: 600, width: 100, height: 100, points: ring, stroke: '#000000', fill: null, strokeWidth: 2, roughness: 1, seed: 1},
   {id: 'p2', type: 'freedraw', x: 900, y: 900, width: 100, height: 10, points: [[0, 0], [50, 10], [100, 0]], stroke: '#000000', fill: null, strokeWidth: 2, roughness: 1, seed: 1},
  );
  assert.equal(a.fillable(doc.unlaw.elements[0]), true, 'rectangles are fillable');
  assert.equal(a.fillable(doc.unlaw.elements[1]), true, 'a pen loop is fillable');
  assert.equal(a.fillable(doc.unlaw.elements[2]), false, 'an open stroke is not');
  assert.equal(a.fillTarget(doc, 60, 330, 1), 'x:x1', 'the inside of an unfilled rectangle counts for the bucket');
  assert.equal(a.hitTest(doc, 60, 330, 1), null, 'but not for selection');
  assert.equal(a.applyFill(doc, 'x:x1', '#123456'), true);
  assert.equal(doc.unlaw.elements[0].fill, '#123456');
  assert.equal(a.applyFill(doc, 'x:x1', '#123456'), false, 'the same color again changes nothing');
  assert.equal(a.hitTest(doc, 60, 330, 1), 'x:x1', 'a filled shape is hit inside');
  assert.equal(a.fillTarget(doc, 650, 650, 1), 'x:p1');
  a.applyFill(doc, 'x:p1', '#ff0000');
  assert.equal(doc.unlaw.elements[1].fill, '#ff0000');
  a.applyFill(doc, 'x:p2', '#00ff00');
  assert.equal(doc.unlaw.elements[2].stroke, '#00ff00', 'an open stroke takes the color as ink');
  assert.equal(doc.unlaw.elements[2].fill, null);
  a.applyFill(doc, 'n:n1', '#abcdef');
  assert.equal(doc.nodes[0].color, '#abcdef', 'cards take the color');
  assert.equal(doc.nodes[0].plugin.a, 1, 'unknown keys stay');
  assert.equal(a.fillTarget(doc, 0, 180, 1), 'n:g1', 'a click anywhere inside a group colors the group');
  assert.equal(a.applyFill(doc, 'n:n1', null), true);
  assert.equal('color' in doc.nodes[0], false, 'alt+click clears a card color');
  assert.equal(a.applyFill(doc, 'x:x1', null), true);
  assert.equal(doc.unlaw.elements[0].fill, null);
  assert.equal(a.fillTarget(doc, 5000, 5000, 1), null, 'empty space is the background');
  assert.equal(a.setBackground(doc, '#fafafa'), true);
  assert.equal(a.cvBackground(doc), '#fafafa');
  assert.equal(doc.unlaw.future, 'yes');
  assert.equal(a.setBackground(doc, null), true);
  assert.equal(a.cvBackground(doc), null);
  assert.equal('background' in doc.unlaw, false);
  a.applyStyle(doc, ['x:p1'], {stroke: '#111111'});
  assert.equal(doc.unlaw.elements[1].fill, '#ff0000', 'changing the ink keeps a fill of another color');
  doc.unlaw.elements[1].fill = '#111111';
  a.applyStyle(doc, ['x:p1'], {stroke: '#222222'});
  assert.equal(doc.unlaw.elements[1].fill, '#222222', 'a fill in the old ink follows the new ink');
 },
 async canvas_keys_and_files() {
  const h = harness(), a = h.a;
  const calls = [];
  let shape = sampleShape();
  h.context.fetch = async (path, options) => {
   const body = options && options.body ? JSON.parse(options.body) : null;
   calls.push([path, body]);
   if (path === '/api/canvases' && !body) return response({dir: '/c', current: shape.path, items: [{path: shape.path, name: shape.name}]});
   if (path === '/api/canvas/new') { shape = {...sampleShape(), path: '/c/canvas-1.canvas', name: 'canvas-1', version: 'v9'}; return response(shape); }
   if (path === '/api/canvas/rename') { shape = {...shape, path: '/c/' + body.name + '.canvas', name: body.name}; return response(shape); }
   if (path === '/api/canvas/choose') return response({path: '/elsewhere/b.canvas'});
   if (path === '/api/canvases') { shape = {...sampleShape(), path: body.path, name: 'b'}; return response(shape); }
   return response(shape);
  };
  a.cvLoad(sampleShape());
  const press = (code, extra = {}) => a.canvasKey({key: '?', code, shiftKey: false, metaKey: false, ctrlKey: false, altKey: false, preventDefault() {}, ...extra});
  for (const [code, tool] of [['KeyV', 'select'], ['KeyH', 'hand'], ['KeyN', 'card'], ['KeyT', 'text'], ['KeyU', 'rectangle'], ['KeyB', 'freedraw'], ['KeyG', 'fill'], ['KeyE', 'eraser'], ['KeyP', 'freedraw'], ['KeyR', 'rectangle']]) {
   assert.equal(press(code), true);
   assert.equal(a.cv.tool, tool, code);
  }
  assert.equal(press('KeyV', {key: 'м'}), true, 'a Russian layout still reaches the V key');
  assert.equal(a.cv.tool, 'select');
  a.cv.tool = 'rectangle';
  for (const tool of ['ellipse', 'diamond', 'line', 'arrow', 'rectangle']) { press('KeyU', {shiftKey: true}); assert.equal(a.cv.tool, tool, 'Shift+U cycles the shapes'); }
  for (const [from, code, to] of [[4, 'BracketRight', 5], [10, 'BracketRight', 15], [50, 'BracketRight', 60], [100, 'BracketRight', 100],
   [60, 'BracketLeft', 50], [50, 'BracketLeft', 45], [10, 'BracketLeft', 9], [1, 'BracketLeft', 1]]) {
   a.cv.style.width = from;
   press(code);
   assert.equal(a.cv.style.width, to, code + ' from ' + from);
  }
  a.cv.style.stroke = '#e5484d';
  press('KeyD'); assert.equal(a.cv.style.stroke, '#1d1d1f', 'D restores the default color');
  a.cvSelect(['n:n1', 'n:n2']);
  assert.equal(press('KeyG', {metaKey: true}), true);
  assert.equal(a.cv.doc.nodes[0].type, 'group', 'Cmd+G groups');
  assert.equal(a.cv.tool, 'rectangle', 'Cmd+G does not pick the fill tool');
  a.cvStyle({stroke: '#0a0b0c'});
  assert.equal(a.cv.style.stroke, '#0a0b0c', 'any color can be chosen');

  await a.cvNew();
  assert.equal(a.cv.path, '/c/canvas-1.canvas', 'New canvas opens canvas-N at once');
  assert.equal(a.cv.name, 'canvas-1');
  await a.cvRename('  Ideas  ');
  assert.deepEqual(calls.find(([path]) => path === '/api/canvas/rename')[1], {path: '/c/canvas-1.canvas', name: 'Ideas'});
  assert.equal(a.cv.path, '/c/Ideas.canvas');
  assert.equal(a.cv.name, 'Ideas');
  const renames = calls.filter(([path]) => path === '/api/canvas/rename').length;
  await a.cvRename('Ideas');
  assert.equal(calls.filter(([path]) => path === '/api/canvas/rename').length, renames, 'the same name sends nothing');
  await a.cvChoose();
  assert.equal(a.cv.path, '/elsewhere/b.canvas', 'the file picked in the dialog opens');
 },

 async canvas_flood_fill() {
  const h = harness(), a = h.a;
  // A white image with a black square border from a to b and a black island from c to d inside.
  const picture = (size, a0, b0, c0, d0) => {
   const px = new Uint8ClampedArray(size * size * 4).fill(255);
   const dot = (x, y) => { const k = (y * size + x) * 4; px[k] = px[k + 1] = px[k + 2] = 0; };
   for (let i = a0; i <= b0; i++) { dot(i, a0); dot(i, b0); dot(a0, i); dot(b0, i); }
   for (let y = c0; y <= d0; y++) for (let x = c0; x <= d0; x++) dot(x, y);
   return px;
  };
  const w = 20, hgt = 20, data = picture(20, 4, 15, 8, 11);
  const inside = a.floodRegion(data, w, hgt, 6, 6, 40);
  assert.equal(inside.touches, false, 'a closed area does not reach the edge');
  assert.equal(inside.count, 100 - 16, 'only the same color, the island stays out');
  assert.equal(a.floodRegion(data, w, hgt, 1, 1, 40).touches, true, 'the open outside reaches the edge');
  assert.equal(a.traceMask(inside.mask, w, hgt).length, 2, 'outer border and one hole');
  const paint = plain(a.paintFromMask(a.growMask(inside.mask, w, hgt), w, hgt, {x: 0, y: 0, z: 1}, 1, '#30a46c'));
  assert.equal(paint.type, 'paint');
  assert.deepEqual([paint.x, paint.y, paint.width, paint.height], [4, 4, 12, 12], 'grown one pixel under the border');
  assert.equal(paint.holes.length, 1);
  assert.equal(paint.fill, '#30a46c');
  assert.equal(a.paintContains(paint, 6, 6), true);
  assert.equal(a.paintContains(paint, 9.5, 9.5), false, 'the hole stays empty');
  assert.equal(a.paintContains(paint, 2, 2), false);
  const zoomed = plain(a.paintFromMask(a.growMask(inside.mask, w, hgt), w, hgt, {x: 10, y: 0, z: 2}, 2, '#30a46c'));
  assert.deepEqual([zoomed.x, zoomed.y, zoomed.width, zoomed.height], [-4, 1, 3, 3], 'snapshot pixels map back to world units');

  // The page: a snapshot of a bigger such picture stands in for the rendered scene.
  a.cvLoad({path: '/c/a.canvas', name: 'a', version: 'v1', canvas: {nodes: [], edges: [], unlaw: {version: 1, elements: [
   {id: 'r', type: 'rectangle', x: 10, y: 10, width: 40, height: 40, stroke: '#000000', fill: null, strokeWidth: 1, roughness: 0, seed: 1},
  ]}}});
  a.cv.view = {x: 0, y: 0, z: 1};
  a.cv.w = 60; a.cv.h = 60;
  h.context.__image = picture(60, 10, 50, 26, 34);
  h.run('cvSnapshot = () => ({data: globalThis.__image, w: 60, h: 60, k: 1})');
  a.cv.style.stroke = '#e5484d';
  a.cvBucket({x: 20, y: 20}, {x: 20, y: 20}, false);
  const els = a.cv.doc.unlaw.elements;
  assert.equal(els.length, 2, 'the flooded area becomes a paint element');
  assert.equal(els[0].type, 'paint', 'under the empty outline, so the line stays on top');
  assert.equal(els[0].fill, '#e5484d');
  assert.equal(a.hitTest(a.cv.doc, 20, 20, 1), 'x:' + els[0].id, 'a paint area can be selected');
  assert.equal(a.hitTest(a.cv.doc, 30, 30, 1), null, 'the island is a hole');
  a.cvBucket({x: 1, y: 1}, {x: 1, y: 1}, false);
  assert.equal(a.cv.doc.unlaw.background, '#e5484d', 'an area running out of the view fills the background');
  a.cv.style.stroke = '#3a6df0';
  a.cvBucket({x: 10, y: 30}, {x: 10, y: 30}, false);
  assert.equal(els[1].stroke, '#3a6df0', 'a click on a line recolors the line');
  a.cvBucket({x: 20, y: 20}, {x: 20, y: 20}, true);
  assert.equal(a.cv.doc.unlaw.elements.length, 1, 'alt+click removes a paint area');
  assert.equal(a.cv.hist.undo.length > 0, true);
 },
 async canvas_partial_eraser() {
  const h = harness(), a = h.a;
  const base = {stroke: '#000000', fill: null, strokeWidth: 2, roughness: 0, seed: 1, extra: 'k'};
  const line = {...base, id: 'l', type: 'line', x: 0, y: 0, width: 100, height: 0, points: [[0, 0], [100, 0]]};
  assert.equal(a.cutElement(line, 50, 40, 5), null, 'an untouched line stays as it is');
  const pieces = plain(a.cutElement(line, 50, 0, 5));
  assert.equal(pieces.length, 2, 'the line is cut in two');
  assert.ok(pieces[0].x + pieces[0].width < 45 && pieces[1].x > 55, 'the gap is where the eraser passed');
  assert.equal(pieces[0].extra, 'k', 'unknown keys stay on the pieces');
  assert.notEqual(pieces[0].id, pieces[1].id);
  const arrow = plain(a.cutElement({...line, type: 'arrow'}, 50, 0, 5));
  assert.deepEqual(arrow.map(p => p.type), ['line', 'arrow'], 'the head stays on the piece with the end');
  assert.deepEqual(plain(a.cutElement(line, 2, 0, 5)).length, 1, 'cutting the end leaves one piece');
  assert.deepEqual(plain(a.cutElement(line, 50, 0, 80)), [], 'a big eraser leaves nothing');
  const box = {...base, id: 'b', type: 'rectangle', x: 0, y: 0, width: 100, height: 100, fill: '#ff0000'};
  const cut = plain(a.cutElement(box, 50, 0, 5));
  assert.equal(cut[0].type, 'paint', 'a filled shape keeps its fill');
  assert.equal(cut[0].fill, '#ff0000');
  assert.equal(cut.length, 2, 'the rest of a closed outline is one piece');
  assert.equal(a.hitElement(cut[1], 50, 100, 2), true);
  assert.equal(a.hitElement(cut[1], 50, 0, 2), false);
  const pen = {...base, id: 'p', type: 'freedraw', x: 0, y: 0, width: 100, height: 10, points: [[0, 0], [50, 10], [100, 0]]};
  assert.ok(plain(a.cutElement(pen, 50, 10, 4)).every(p => p.type === 'freedraw'), 'pen strokes stay pen strokes');
  assert.equal(a.cutElement({...base, id: 't', type: 'text', text: 'hi', x: 0, y: 0, width: 50, height: 20}, 10, 10, 5), null, 'text is left alone');
  const doc = {nodes: [], edges: [], unlaw: {version: 1, elements: [line, {...line, id: 'far', y: 500}]}};
  assert.equal(a.eraseAt(doc, 50, 0, 5), 1);
  assert.deepEqual(doc.unlaw.elements.map(e => e.type), ['line', 'line', 'line']);
  assert.equal(doc.unlaw.elements[2].id, 'far');

  a.cvLoad({path: '/c/a.canvas', name: 'a', version: 'v1', canvas: {nodes: [], edges: [], unlaw: {version: 1, elements: [plain(line)]}}});
  a.cv.view = {x: 0, y: 0, z: 1};
  a.cv.el = {getBoundingClientRect: () => ({left: 0, top: 0}), focus() {}, style: {}};
  a.cv.eraser = 'part';
  a.cv.tool = 'eraser';
  a.cv.style.width = 10;
  const at = (x, y) => ({button: 0, clientX: x, clientY: y, pointerId: 1, preventDefault() {}});
  a.cvDown(at(30, -20)); a.cvMove(at(30, 20)); a.cvUp(at(30, 20));
  assert.equal(a.cv.doc.unlaw.elements.length, 2, 'a drag across the line cuts it even between pointer events');
  a.cv.eraser = 'object';
  a.cvDown(at(80, 0)); a.cvUp(at(80, 0));
  assert.equal(a.cv.doc.unlaw.elements.length, 1, 'the whole-object eraser still removes what it touches');
 },
 async canvas_tool_menus_and_width() {
  const h = harness(), a = h.a;
  for (let width = 1; width <= 100; width++) assert.equal(a.sliderToWidth(a.widthToSlider(width)), width, 'every width is on the slider');
  assert.equal(a.sliderToWidth(0), 1);
  assert.equal(a.sliderToWidth(1000), 100);
  a.cv.ui = a.cvBuildBar();
  for (const [typed, width] of [['37', 37], [' 5 ', 5], ['250', 100], ['0', 1], ['abc', 1], ['12px', 1], ['', 1]]) {
   a.cvTypedWidth(typed);
   assert.equal(a.cv.style.width, width, 'typed ' + JSON.stringify(typed));
  }
  assert.equal(a.cv.ui.widthValue.value, '1', 'a bad entry shows the current width again');
  a.cv.doc = {nodes: [], edges: []};
  const key = code => a.canvasKey({key: '?', code, shiftKey: false, metaKey: false, ctrlKey: false, altKey: false, preventDefault() {}});
  a.cv.style.width = 10;
  key('Equal'); assert.equal(a.cv.style.width, 15, '= makes the line thicker');
  key('Minus'); key('Minus'); assert.equal(a.cv.style.width, 9, '- makes it thinner');
  a.cv.doc = null;
  a.cv.style.width = 4;
  const saved = [];
  h.context.localStorage.setItem = (key, value) => saved.push([key, JSON.parse(value)]);
  a.cv.ui = a.cvBuildBar();
  const menu = a.cv.ui.menu, on = new Set();
  menu.classList = {add: c => on.add(c), remove: c => on.delete(c), toggle() {}, contains: c => on.has(c)};
  for (const tool of ['eraser', 'rectangle']) a.cv.ui.tools[tool].getBoundingClientRect = () => ({left: 40, bottom: 30});
  Object.defineProperty(menu, 'textContent', {set() { menu.children = []; }});
  a.cv.tool = 'select';
  a.cvToolClick('eraser');
  assert.equal(a.cv.tool, 'eraser', 'the first click picks the tool');
  assert.equal(on.has('on'), false);
  a.cvToolClick('eraser');
  assert.equal(on.has('on'), true, 'a second click opens the bubble');
  assert.equal(menu.children.length, 2, 'whole object or only where it passes');
  assert.equal(menu.style.top, '36px');
  a.canvasKey({key: 'Escape', code: 'Escape', preventDefault() {}});
  assert.equal(on.has('on'), false, 'Escape closes the bubble');
  assert.equal(a.cv.tool, 'eraser', 'and keeps the tool');
  a.cv.doc = {nodes: [], edges: []};
  a.canvasKey({key: 'E', code: 'KeyE', shiftKey: true, metaKey: false, ctrlKey: false, altKey: false, preventDefault() {}});
  assert.equal(a.cv.eraser, 'part', 'Shift+E switches the eraser mode');
  assert.deepEqual(saved.at(-1), ['desk-canvas-tools', {eraser: 'part', rough: 1, width: 4}], 'and remembers it');
  a.cvToolClick('rectangle');
  a.cvToolClick('rectangle');
  assert.equal(menu.children.length, 3, 'shapes offer evenness 3, 2, 1');
  const levels = menu.children.map(item => item.children[0].textContent);
  assert.deepEqual(levels, ['3', '2', '1']);
  a.cvStyle({rough: 0});
  assert.equal(a.cv.style.rough, 0);
  assert.deepEqual(saved.at(-1)[1].rough, 0);
  a.cvToolClick('rectangle');
  assert.equal(on.has('on'), false, 'clicking the button again closes it');
 },
 async boards_menu_is_one_flat_list() {
  const h = harness();
  h.context.fetch = async () => response({
    reminders: true, current: '/v/work/TODO.md', boards_dir: '/c/boards',
    recent: ['/v/work/TODO.md', '/c/boards/Ideas.md'], boards: ['/c/boards/Ideas.md', '/c/boards/Games.md'],
  });
  await h.a.loadBoards();
  const [trigger, menu] = h.ids.get('boards').children;
  assert.equal(trigger.children[0].textContent, 'TODO', 'the button names the open board');
  const rows = menu.children.map(node => node.className === 'sep' ? '---' : node.children[0].textContent);
  assert.deepEqual(rows, ['Reminders', 'TODO', 'Ideas', 'Games', '---', 'New board…', 'Open another board…', 'Delete this board…'],
    'Reminders, recent and folder boards share one list without group headings, each board once');
  assert.equal(menu.children[1].className, 'on', 'the open board is marked');
  assert.equal(menu.children[1].children[1].textContent, 'work', 'with its folder under the name');
 },
 async board_dialogs() {
  const h = harness(), calls = [];
  let picked = {path: '/picked/Plan.md'};
  h.context.fetch = async (path, options) => {
    const body = options && options.body ? JSON.parse(options.body) : null;
    calls.push([path, body]);
    if (path === '/api/boards/choose') return response(picked);
    if (path === '/api/boards' && body) return {status: 400, json: async () => ({error: 'not opened in this test'})};
    return response({boards: [], recent: []});
  };
  h.context.prompt = () => { throw Error('no prompt while the dialog works'); };
  await h.a.newBoard();
  assert.deepEqual(calls[0], ['/api/boards/choose', {create: true}], 'New board asks for the save dialog');
  assert.deepEqual(calls[1], ['/api/boards', {path: '/picked/Plan.md', create: true}], 'and creates the picked file');
  calls.length = 0;
  await h.a.openOtherBoard();
  assert.deepEqual(calls[0], ['/api/boards/choose', {create: false}]);
  assert.deepEqual(calls[1], ['/api/boards', {path: '/picked/Plan.md', create: false}]);
  calls.length = 0;
  picked = {path: null};
  await h.a.newBoard();
  assert.deepEqual(calls.map(([path]) => path), ['/api/boards/choose'], 'Cancel opens nothing');
  calls.length = 0;
  picked = {unavailable: true};
  h.context.prompt = () => 'Ideas';
  await h.a.newBoard();
  assert.deepEqual(calls[1], ['/api/boards', {path: 'Ideas', create: true}], 'without the dialog the page asks for a name');
 },
 async delete_board_asks_first() {
  const h = harness(), calls = [];
  h.context.fetch = async (path, options) => {
    calls.push([path, options && options.body ? JSON.parse(options.body) : null]);
    return {status: 400, json: async () => ({error: 'the default board'})};
  };
  h.context.confirm = () => false;
  await h.a.deleteBoard('/c/boards/Work.md', 'Work');
  assert.equal(calls.length, 0, 'No in the dialog deletes nothing');
  h.context.confirm = () => true;
  await h.a.deleteBoard('/c/boards/Work.md', 'Work');
  assert.deepEqual(calls[0], ['/api/boards/delete', {path: '/c/boards/Work.md'}]);
  assert.equal(h.ids.get('toast').textContent, 'the default board', 'a refusal is shown');
 },
 async columns_move_by_dragging_the_heading() {
  const h = harness(), sent = [];
  const Element = h.context.Node;
  Element.prototype.addEventListener = function (type, fn) { (this.on = this.on || {})[type] = fn; };
  const columns = ['To do', 'Doing', 'Done'].map(name => ({name, doing: false, cards: []}));
  h.a.state.board = {version: 'v1', layer: 'file', today: '2026-11-13', done_column: 'Done', columns};
  h.context.fetch = async (path, options) => { sent.push(JSON.parse(options.body)); return {status: 400, json: async () => ({error: 'kept'})}; };
  const main = new Element();
  h.a.renderBoard(main);
  const sections = main.children[0].children.filter(node => node.tagName === 'DIV' && node.children[0] && node.children[0].on && node.children[0].on.dragstart);
  assert.equal(sections.length, 3, 'every column heading can be dragged');
  sections.forEach((node, i) => { node.getBoundingClientRect = () => ({left: i * 300, width: 300}); });
  const drag = (from, to, x) => {
    const event = {clientX: x, offsetX: 0, offsetY: 0, preventDefault() {}, dataTransfer: {setData() {}, setDragImage() {}}};
    sections[from].children[0].on.dragstart(event);
    sections[to].on.dragover(event);
    sections[to].on.drop(event);
  };
  drag(0, 2, 800);
  assert.deepEqual(sent.at(-1), {op: 'move_column', column: 0, name: 'To do', to_index: 2, version: 'v1'}, 'right half of the last column = to the end');
  drag(2, 0, 10);
  assert.deepEqual(sent.at(-1), {op: 'move_column', column: 2, name: 'Done', to_index: 0, version: 'v1'}, 'left half of the first column = to the start');
  const before = sent.length;
  drag(1, 0, 290);
  drag(1, 2, 610);
  assert.equal(sent.length, before, 'dropping next to its own place sends nothing');
  assert.equal(h.a.state.draggingColumn, null);
  h.a.state.board = {...h.a.state.board, layer: 'reminders'};
  const again = new Element();
  h.a.renderBoard(again);
  assert.equal(again.children[0].children.some(node => node.children[0] && node.children[0].on && node.children[0].on.dragstart), false,
    'Reminders lists keep their order');
 },
 async canvas_detective_board() {
  const h = harness(), a = h.a;
  const doc = plain(sampleShape().canvas);
  assert.equal(a.cvCork(doc), false);
  assert.equal(a.setLook(doc, true), true);
  assert.equal(doc.unlaw.look, 'cork');
  assert.equal(doc.unlaw.future, 'yes', 'other unlaw keys stay');
  assert.equal(a.setLook(doc, true), false, 'no change when it is already a detective board');
  // Tilt and pin come from the id: the same every time, small, and the pin sits on the paper near the top.
  const n1 = doc.nodes[0], n2 = doc.nodes[1];
  assert.equal(a.nodeTilt(n1), a.nodeTilt({...n1}));
  assert.ok(Math.abs(a.nodeTilt(n1)) <= 0.045);
  assert.equal(a.nodeTilt(doc.nodes[2]), 0, 'groups are never tilted');
  const pin = a.pinPoint(n1);
  assert.ok(pin.x > n1.x + 80 && pin.x < n1.x + 120, 'pin near the top middle');
  assert.ok(pin.y > n1.y && pin.y < n1.y + 30);
  // Thread runs pin to pin and hangs below the straight line.
  const curve = a.threadCurve(n1, n2);
  assert.deepEqual(plain(curve.p0), plain(a.pinPoint(n1)));
  assert.deepEqual(plain(curve.p3), plain(a.pinPoint(n2)));
  const mid = a.bezierPoint(curve, 0.5);
  assert.ok(mid.y > (curve.p0.y + curve.p3.y) / 2 + 20, 'the thread sags');
  const map = new Map(doc.nodes.map(n => [n.id, n]));
  assert.deepEqual(plain(a.edgeCurveFor(map, doc.edges[0], true)), plain(curve));
  assert.notDeepEqual(plain(a.edgeCurveFor(map, doc.edges[0], false)), plain(curve), 'the plain look keeps side-to-side curves');
  // Clicking the sagging thread selects the edge (the middle lies outside both cards).
  assert.equal(a.hitTest(doc, mid.x, mid.y, 1), 'e:e1');
  a.setLook(doc, false);
  assert.equal(a.cvCork(doc), false);
  assert.equal('look' in doc.unlaw, false);
  // Helpers.
  assert.deepEqual(plain(a.fileCardSize(null)), {width: 220, height: 280});
  assert.deepEqual(plain(a.fileCardSize({w: 1000, h: 500})), {width: 280, height: 180});
  assert.equal(a.fileCardSize({w: 10, h: 1000}).height, 510, 'tall pictures are capped');
  assert.equal(a.fileExtension('attachments/Brief.pdf'), 'PDF');
  assert.equal(a.fileExtension('noext'), 'FILE');
  assert.equal(a.mixColor('#000000', '#ffffff', 0.5), '#808080');
  // Painting a detective board on a recording context: pins and thread are drawn, the fill snapshot has no texture.
  const calls = [];
  const ctx = new Proxy({measureText: text => ({width: String(text).length * 7})}, {
   get: (target, prop) => (prop in target ? target[prop] : (...args) => { calls.push(prop); return prop === 'createPattern' ? 'pattern' : undefined; }),
   set: (target, prop, value) => { target[prop] = value; return true; },
  });
  h.context.document.createElement = () => ({getContext: () => ctx});
  const pal = {dark: false, bg: '#fff', panel: '#fff', text: '#000', muted: '#888', line: '#ddd', accent: '#36f', soft: '#eef'};
  a.setLook(doc, true);
  const scene = flat => { calls.length = 0; a.paintScene({ctx, doc, view: {x: 0, y: 0, z: 1}, w: 800, h: 600, pal, scale: 1, ui: null, flat}); return [...calls]; };
  const textured = scene(false);
  assert.ok(textured.includes('createPattern'), 'cork texture');
  assert.ok(textured.includes('arc'), 'push pins');
  assert.ok(textured.includes('bezierCurveTo'), 'thread');
  assert.equal(scene(true).includes('createPattern'), false, 'the fill tool sees flat cork');
 },
 async canvas_files_are_added_and_pinned() {
  const h = harness(), a = h.a;
  a.cvLoad(sampleShape());
  a.cv.w = 800; a.cv.h = 600; a.cv.view = {x: 0, y: 0, z: 1};
  const sent = [];
  h.context.fetch = async (url, options) => {
   sent.push({url, options});
   if (url.includes('name=bad.pdf')) return {ok: false, status: 400, json: async () => ({error: 'nope'})};
   const name = decodeURIComponent(/name=([^&]*)/.exec(url)[1]);
   return {ok: true, status: 200, json: async () => ({file: 'attachments/' + name, name, size: 3})};
  };
  const nodes = a.cv.doc.nodes.length, undo = a.cv.hist.undo.length;
  await a.cvAddFiles([{name: 'Brief.pdf', size: 3, type: 'application/pdf'}, {name: 'bad.pdf', size: 3}, {name: 'Doc.docx', size: 3}], {x: 100, y: 100});
  assert.equal(sent.length, 3);
  assert.ok(sent[0].url.startsWith('/api/canvas/upload?path=' + encodeURIComponent('/c/a.canvas') + '&name=Brief.pdf'));
  assert.equal(sent[0].options.headers['X-Desk-Token'], 'test');
  assert.equal(sent[0].options.method, 'POST');
  const added = a.cv.doc.nodes.slice(nodes);
  assert.deepEqual(plain(added.map(n => [n.type, n.file])), [['file', 'attachments/Brief.pdf'], ['file', 'attachments/Doc.docx']]);
  assert.equal(added[0].x, 100 - 110); assert.equal(added[0].y, 100 - 140);
  assert.ok(added[1].x > added[0].x, 'several files are fanned out');
  assert.equal(h.ids.get('toast').textContent, 'nope');
  assert.deepEqual(plain(a.cv.sel), added.map(n => 'n:' + n.id));
  assert.equal(a.cv.hist.undo.length, undo + 1, 'one undo step');
  sent.length = 0;
  await a.cvAddFiles([{name: 'huge.mov', size: 300 * 1024 * 1024}]);
  assert.equal(sent.length, 0, 'too big files are not sent');
  a.cv.doc = null;
  await a.cvAddFiles([{name: 'x.png', size: 1}]);
  assert.equal(sent.length, 0);
  assert.equal(h.ids.get('toast').textContent, 'Open or create a canvas first');
  // The detective board toggle is one undoable step.
  a.cvLoad(sampleShape());
  a.cvToggleCork();
  assert.equal(a.cvCork(a.cv.doc), true);
  a.cvUndo();
  assert.equal(a.cvCork(a.cv.doc), false);
  assert.equal(a.cvImageFor(a.cv.doc.nodes[1]), null, 'notes are never fetched as pictures');
  assert.equal(a.cvImageFor({file: 'attachments/a.txt'}), null, 'plain text stays a paper sheet');
 },
 async today_shows_tasks_and_focus_stats() {
  const h = treeHarness(), a = h.a;
  assert.deepEqual([...a.VIEWS], ['board', 'today', 'games', 'studio', 'canvas'], 'no separate Stats tab');
  assert.equal(a.savedView('stats'), 'today', 'an old saved Stats view opens Today');
  let asked = 0;
  h.context.fetch = async () => { asked++; return response({}); };
  a.state.board = {today: '2026-11-22', done_column: 'Done', columns: [{name: 'To do', cards: [{title: 'Late', text: 'Late', line: 3, due: '2026-11-20', tags: [], details: []}]}]};
  a.state.stats = {today: {pomodoros: 2, minutes: 50, done: 3}, streak: 4, total_pomodoros: 9,
    week: Array.from({length: 7}, (_, i) => ({date: '2026-11-1' + (6 + i), pomodoros: i, minutes: i * 25, done: 1})),
    cards: [{card: 'Write', minutes: 50}]};
  a.state.view = 'today';
  h.run('todayStatsAt = Date.now();');
  a.renderToday(h.main);
  const text = textOf(h.main);
  for (const needle of ['focus min today', '50', 'done today', 'day streak', 'Overdue', 'Late', 'Most focused cards', 'Write'])
    assert.ok(text.includes(needle), needle + ' is on Today');
  assert.equal(asked, 0, 'fresh stats are not fetched again on every render');
 },
 async canvas_threads_new_cards_and_layers() {
  const h = harness(), a = h.a;
  const ctx = new Proxy({font: '', measureText: text => ({width: String(text).length * 7})}, {
   get: (target, prop) => (prop in target ? target[prop] : () => {}),
   set: (target, prop, value) => { target[prop] = value; return true; },
  });
  const fake = tag => {
   const node = new h.context.Node();
   node.tagName = tag.toUpperCase();
   node.getBoundingClientRect = () => ({left: 0, top: 0, width: 800, height: 600});
   node.getContext = () => ctx;
   node.focus = () => {}; node.select = () => {}; node.setPointerCapture = () => {};
   return node;
  };
  h.context.document.createElement = fake;
  h.context.getComputedStyle = () => ({getPropertyValue: () => '#336699'});
  const shape = sampleShape();
  h.context.fetch = async path => {
   if (path === '/api/canvases') return response({dir: '/c', current: '/c/a.canvas', items: [{path: '/c/a.canvas', name: 'a'}]});
   if (path.startsWith('/api/canvas')) return response(shape);
   return response({});
  };
  a.state.view = 'canvas';
  a.renderCanvas(fake('main'));
  for (let i = 0; i < 3; i++) await new Promise(resolve => setImmediate(resolve));
  a.cv.view = {x: 0, y: 0, z: 1};
  const at = (x, y, extra = {}) => ({button: 0, clientX: x, clientY: y, pointerId: 1, shiftKey: false, preventDefault() {}, ...extra});
  const click = (x, y) => { a.cvDown(at(x, y)); a.cvUp(at(x, y)); };
  const n1 = a.cv.doc.nodes.find(n => n.id === 'n1');

  // Thread tool: from a spot on one card to a spot on another.
  a.canvasKey({key: 'k', code: 'KeyK', preventDefault() {}});
  assert.equal(a.cv.tool, 'thread', 'K picks the thread tool');
  click(50, 80);
  assert.deepEqual(plain(a.cv.thread), {node: 'n1', frac: [0.25, 0.8], points: []}, 'the first click pins the start where it was');
  a.cvMove(at(500, 20));
  click(580, 90);
  const thread = a.cv.doc.edges.at(-1);
  assert.equal(thread.toNode, 'n2');
  assert.deepEqual(plain(thread.unlawFrom), [0.25, 0.8]);
  assert.deepEqual(plain(thread.unlawTo), [0.9, 0.9]);
  assert.equal(thread.fromSide, 'bottom', 'Obsidian still gets the nearest side');
  assert.deepEqual(plain(a.cv.thread), {node: 'n2', frac: [0.9, 0.9], points: []}, 'the next thread starts where this one ended (a chain)');
  a.canvasKey({key: 'Escape', code: 'Escape', preventDefault() {}});
  assert.equal(a.cv.thread, null, 'Esc stops the chain');
  const curve = a.edgeCurveFor(new Map(a.docNodes(a.cv.doc).map(n => [n.id, n])), thread, false);
  assert.deepEqual(plain(curve.p0), {x: 50, y: 80}, 'the line starts at that spot');
  const cork = a.edgeCurveFor(new Map(a.docNodes(a.cv.doc).map(n => [n.id, n])), thread, true);
  assert.deepEqual(plain(cork.p0), plain(a.anchorPoint(n1, [0.25, 0.8], true)), 'on cork the pin turns with the card');
  const back = a.fracAt(n1, cork.p0, true);
  assert.ok(Math.abs(back[0] - 0.25) < 1e-3 && Math.abs(back[1] - 0.8) < 1e-3, 'fracAt undoes anchorPoint');
  assert.equal(a.edgeAnchor({unlawTo: [2, 0]}, 'to'), null, 'a bad spot is ignored');

  // Escape drops a started thread; a double click on empty canvas ends the thread on a new card there.
  click(100, 50);
  assert.ok(a.cv.thread);
  a.canvasKey({key: 'Escape', code: 'Escape', preventDefault() {}});
  assert.equal(a.cv.thread, null, 'Esc drops the started thread');
  assert.equal(a.cv.tool, 'thread', 'and keeps the tool');
  const edges = a.cv.doc.edges.length, nodes = a.cv.doc.nodes.length;
  click(100, 50); click(300, 500); click(300, 500); a.cvDouble(at(300, 500));
  assert.equal(a.cv.doc.nodes.length, nodes + 1, 'a new card where the thread ended');
  assert.equal('unlawPoints' in a.cv.doc.edges.at(-1), false, 'the clicks of the double click are not bends');
  const made = a.cv.doc.nodes.at(-1);
  assert.deepEqual([made.x, made.y, made.type], [170, 440, 'text']);
  assert.equal(a.cv.doc.edges.at(-1).toNode, made.id);
  assert.equal(a.cv.doc.edges.length, edges + 1);
  assert.ok(a.cv.editing, 'the new card opens for typing');
  a.cv.ui.editor.value = 'suspect';
  a.cvEndEdit();

  // Bends: clicks on the canvas pin the thread on its way; Backspace takes the last one back.
  click(100, 50); click(300, 300); click(320, 320);
  assert.deepEqual(plain(a.cv.thread.points), [[300, 300], [320, 320]], 'clicks on the canvas pin bends');
  a.canvasKey({key: 'Backspace', code: 'Backspace', preventDefault() {}});
  assert.deepEqual(plain(a.cv.thread.points), [[300, 300]], 'Backspace takes the last bend back');
  click(580, 90);
  const bent = a.cv.doc.edges.at(-1), bentMap = new Map(a.docNodes(a.cv.doc).map(n => [n.id, n]));
  assert.deepEqual(plain(bent.unlawPoints), [[300, 300]]);
  assert.equal(a.edgeCurveFor(bentMap, bent, true).segs.length, 2, 'a thread with one bend is two pieces on cork');
  assert.equal(a.edgeCurveFor(bentMap, bent, false).segs.length, 2, 'and off it');
  assert.ok(a.hitEdge(a.edgeCurveFor(bentMap, bent, false), 300, 300, 2), 'the thread passes its bend');
  a.canvasKey({key: 'Escape', code: 'Escape', preventDefault() {}});
  // One click with the thread tool removes a thread.
  const before = a.cv.doc.edges.length;
  click(200, 175);
  assert.equal(a.cv.doc.edges.length, before - 1, 'a click on a thread removes it');
  assert.ok(!a.cv.doc.edges.includes(bent));
  // A selected thread: drag a bend, drag the dot in the middle of a segment to add one, double-click to remove.
  click(100, 50); click(300, 300); click(580, 90);
  a.canvasKey({key: 'Escape', code: 'Escape', preventDefault() {}});
  const edit = a.cv.doc.edges.at(-1);
  a.cvSetTool('select');
  a.cvSelect(['e:' + edit.id]);
  a.cvDown(at(300, 300));
  assert.equal(a.cv.drag.mode, 'bend');
  a.cvMove(at(310, 280)); a.cvUp(at(310, 280));
  assert.deepEqual(plain(edit.unlawPoints), [[310, 280]], 'a bend drags');
  const ring = a.bezierPoint(a.curveSegs(a.edgeCurveFor(new Map(a.docNodes(a.cv.doc).map(n => [n.id, n])), edit, false))[1], 0.5);
  a.cvDown(at(ring.x, ring.y));
  assert.equal(a.cv.drag.insert, true, 'the ring in a segment adds a bend');
  a.cvMove(at(450, 250)); a.cvUp(at(450, 250));
  assert.deepEqual(plain(edit.unlawPoints), [[310, 280], [450, 250]]);
  a.moveItems(a.cv.doc, ['e:' + edit.id], 10, 10);
  assert.deepEqual(plain(edit.unlawPoints), [[320, 290], [460, 260]], 'bends move with their thread');
  a.cvDouble(at(320, 290));
  assert.deepEqual(plain(edit.unlawPoints), [[460, 260]], 'a double click removes a bend');
  a.cvDouble(at(460, 260));
  assert.equal('unlawPoints' in edit, false, 'the last one takes the key away');
  a.canvasKey({key: 'k', code: 'KeyK', preventDefault() {}});

  // A thread end tied right next to the card's own pin uses that pin: no second pin over the first.
  assert.equal(a.pinSpot(n1, [0.5, 0]), null, 'the top dot is the pin itself');
  assert.deepEqual(plain(a.pinSpot(n1, [0.25, 0.8])), [0.25, 0.8], 'a spot elsewhere keeps its own pin');

  // Layers can be renamed: a group's label, anything else unlawName (also the caption of a file card).
  a.cvRenameLayer('n:n2');
  assert.equal(a.cv.renaming, 'n:n2');
  assert.equal(a.cv.layers, true, 'renaming shows the Layers panel');
  a.cvApplyName('n:n2', '  Main\u0007suspect ');
  const n2 = a.cv.doc.nodes.find(n => n.id === 'n2');
  assert.equal(n2.unlawName, 'Main suspect', 'trimmed, control characters gone');
  assert.equal(a.layerName('n:n2', n2), 'Main suspect');
  a.cvApplyName('n:n2', '');
  assert.equal('unlawName' in n2, false, 'an empty name goes back to the file name');
  a.cvApplyName('n:g1', 'Case');
  assert.equal(a.cv.doc.nodes.find(n => n.id === 'g1').label, 'Case', 'a group keeps its name as its label');
  a.cv.renaming = null;
  a.cv.layers = false;

  // Dragging from a side dot onto empty canvas makes a connected card too.
  a.cvSetTool('select');
  a.cvMove(at(100, 50));
  a.cvDown(at(200, 50)); a.cvMove(at(300, 600)); a.cvUp(at(300, 600));
  const linked = a.cv.doc.nodes.at(-1), connect = a.cv.doc.edges.at(-1);
  assert.equal(a.cv.doc.nodes.length, nodes + 2);
  assert.deepEqual([linked.x, linked.y], [170, 540]);
  assert.deepEqual([connect.fromNode, connect.fromSide, connect.toNode], ['n1', 'right', linked.id]);
  assert.ok(a.cv.editing && a.cv.editing.key === 'n:' + linked.id);
  a.cvEndEdit();
  assert.equal('unlawFrom' in connect, false, 'off the detective board an edge keeps Obsidian sides only');

  // On the detective board the thread starts at the dot it was pulled from, not at the pin on top.
  a.setLook(a.cv.doc, true);
  a.cvMove(at(100, 50));
  a.cvDown(at(200, 50));
  assert.equal(a.cv.drag.mode, 'connect');
  a.cvMove(at(300, 700)); a.cvUp(at(300, 700));
  const pulled = a.cv.doc.edges.at(-1);
  assert.deepEqual(plain(pulled.unlawFrom), [1, 0.5], 'tied at the right side it was pulled from');
  assert.deepEqual(plain(pulled.unlawTo), plain({top: [0.5, 0], right: [1, 0.5], bottom: [0.5, 1], left: [0, 0.5]}[pulled.toSide]), 'and at the side of the new card facing it');
  a.cvEndEdit();
  a.setLook(a.cv.doc, false);

  // The end of a selected edge drags to another spot of its card.
  a.cvSelect(['e:' + thread.id]);
  a.cvDown(at(50, 80));
  assert.equal(a.cv.drag.mode, 'anchor');
  a.cvMove(at(150, 10)); a.cvUp(at(150, 10));
  assert.deepEqual(plain(thread.unlawFrom), [0.75, 0.1]);
  assert.equal(thread.fromSide, 'top');
  a.cvUndo();
  assert.deepEqual(plain(a.cv.doc.edges.find(e => e.id === thread.id).unlawFrom), [0.25, 0.8], 'moving an end is undoable');

  // Layers: topmost first; the eye hides a group with what is inside and brings it back.
  const rows = a.layerRows(a.cv.doc).map(row => row.key);
  assert.equal(rows[0], 'sec:drawings', 'drawings come first, under their own heading');
  assert.equal(rows[1], 'x:' + a.cv.doc.unlaw.elements.at(-1).id, 'drawings are on top');
  assert.ok(rows.indexOf('n:g1') < rows.indexOf('n:n1'), 'a card is listed under its group');
  a.cvToggleHidden('n:g1');
  const doc = a.cv.doc;
  assert.equal(doc.nodes.find(n => n.id === 'n1').unlawHidden, true, 'the group hides its cards');
  assert.ok(!a.docNodes(doc).some(n => n.id === 'n1' || n.id === 'g1'), 'hidden things are not drawn');
  assert.notEqual(a.hitTest(doc, 50, 50, 1), 'n:n1', 'nor picked');
  assert.equal(a.layerRows(doc).length, rows.length, 'but stay in the list');
  a.cvToggleHidden('n:g1');
  assert.equal('unlawHidden' in a.cv.doc.nodes.find(n => n.id === 'n1'), false, 'showing removes the key');
  a.cvToggleHidden('n:g1');
  a.cvUndo();
  assert.ok(!a.cv.doc.nodes.some(n => n.unlawHidden), 'hiding is undoable');
  const order = a.cv.doc.unlaw.elements.map(el => el.id);
  a.cvReorderLayer('x:' + order[0], 'x:' + order.at(-1));
  assert.equal(a.cv.doc.unlaw.elements.at(-1).id, order[0], 'dropping a row on the top one brings it to the front');
  a.cvReorderLayer('x:' + order[0], 'n:n1');
  assert.equal(a.cv.doc.unlaw.elements.at(-1).id, order[0], 'cards and drawings keep their own order');
  // Folding like Photoshop: a folded group or heading is one row with its name and a count.
  const shut = a.layerRows(a.cv.doc, new Set(['n:g1', 'sec:drawings']));
  const groupRow = shut.find(row => row.key === 'n:g1');
  assert.equal(groupRow.folded, true);
  assert.ok(groupRow.count >= 1, 'the folded group counts what is inside');
  assert.ok(!shut.some(row => row.key === 'n:n1'), 'its cards are not listed');
  assert.ok(!shut.some(row => row.key[0] === 'x'), 'a folded heading hides its drawings');
  assert.equal(shut.find(row => row.key === 'sec:drawings').count, a.cv.doc.unlaw.elements.length);
  a.cv.path = '/c/fold.canvas';
  a.cv.folded = null;
  const store = new Map();
  h.context.localStorage.getItem = key => (store.has(key) ? store.get(key) : null);
  h.context.localStorage.setItem = (key, value) => store.set(key, String(value));
  a.cvFoldAll(true);
  assert.deepEqual(JSON.parse(h.context.localStorage.getItem('desk-canvas-folded'))['/c/fold.canvas'].sort(), ['n:g1', 'sec:cards', 'sec:drawings'], 'folding is remembered per canvas');
  a.cvToggleFold('n:g1');
  assert.deepEqual(JSON.parse(h.context.localStorage.getItem('desk-canvas-folded'))['/c/fold.canvas'].sort(), ['sec:cards', 'sec:drawings']);
  a.cvFoldAll(false);
  assert.equal(JSON.parse(h.context.localStorage.getItem('desk-canvas-folded'))['/c/fold.canvas'], undefined);
  a.canvasKey({key: 'F7', code: 'F7', preventDefault() {}});
  assert.equal(a.cv.layers, true, 'F7 opens Layers');
  a.cvRenderLayers();
 },
 async canvas_gallery_import_and_delete() {
  const h = harness(), a = h.a;
  const ctx = new Proxy({font: '', measureText: text => ({width: String(text).length * 7})}, {
   get: (target, prop) => (prop in target ? target[prop] : () => {}),
   set: (target, prop, value) => { target[prop] = value; return true; },
  });
  const fake = tag => {
   const node = new h.context.Node();
   node.tagName = tag.toUpperCase();
   node.getBoundingClientRect = () => ({left: 0, top: 0, width: 800, height: 600});
   node.getContext = () => ctx;
   node.focus = () => {}; node.select = () => {}; node.setPointerCapture = () => {};
   return node;
  };
  h.context.document.createElement = fake;
  h.context.getComputedStyle = () => ({getPropertyValue: () => '#336699'});
  const calls = [];
  let items = [{path: '/c/a.canvas', name: 'a', modified: 1}, {path: '/c/b.canvas', name: 'b', modified: 2}];
  h.context.fetch = async (path, init = {}) => {
   const body = init.body ? JSON.parse(init.body) : null;
   calls.push([path, body]);
   if (path === '/api/canvases' && !body) return response({dir: '/c', current: '/c/a.canvas', items});
   if (path === '/api/canvas/import') return response({...sampleShape(), path: '/c/Case.canvas', name: 'Case'});
   if (path === '/api/canvas/delete') { items = items.filter(i => i.path !== body.path); return response({dir: '/c', current: '/c/b.canvas', items}); }
   if (path === '/api/canvases') return response({...sampleShape(), path: body.path, name: body.path.slice(3, -7)});
   if (path.startsWith('/api/canvas')) return response(sampleShape());
   return response({});
  };
  a.state.view = 'canvas';
  a.renderCanvas(fake('main'));
  for (let i = 0; i < 3; i++) await new Promise(resolve => setImmediate(resolve));
  a.cvToggleGallery(true);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(a.cv.gallery, true);
  assert.ok(calls.some(([path]) => path.startsWith('/api/canvas/peek?path=')), 'tiles read their canvas without switching to it');
  assert.ok(!calls.some(([path, body]) => path === '/api/canvases' && body), 'opening the gallery opens nothing');

  // A dropped .canvas is imported and opened; other files go onto the canvas as before.
  const file = {name: 'Case.canvas', size: 10, text: async () => JSON.stringify({nodes: [], edges: []})};
  await a.cvDropFiles([file]);
  const sent = calls.find(([path]) => path === '/api/canvas/import');
  assert.deepEqual(sent[1], {name: 'Case.canvas', canvas: {nodes: [], edges: []}});
  assert.equal(a.cv.path, '/c/Case.canvas', 'the imported canvas opens');
  assert.equal(a.cv.gallery, false);
  await a.cvDropFiles([{name: 'broken.canvas', size: 3, text: async () => '{no'}]);
  assert.equal(calls.filter(([path]) => path === '/api/canvas/import').length, 1, 'a file that is not JSON is never sent');

  // Deleting asks first; deleting the open canvas opens the next one.
  h.context.confirm = () => false;
  await a.cvDeleteCanvas({path: '/c/Case.canvas', name: 'Case'});
  assert.ok(!calls.some(([path]) => path === '/api/canvas/delete'), 'cancel keeps it');
  h.context.confirm = () => true;
  a.cv.path = '/c/a.canvas';
  await a.cvDeleteCanvas({path: '/c/a.canvas', name: 'a'});
  assert.deepEqual(calls.find(([path]) => path === '/api/canvas/delete')[1], {path: '/c/a.canvas'});
  assert.equal(a.cv.path, '/c/b.canvas', 'the next canvas opens');
  assert.deepEqual(a.cv.items.map(i => i.name), ['b']);
 },
 async canvas_viewer_3d_and_links() {
  const h = harness(), a = h.a;
  h.context.TextEncoder = TextEncoder;
  h.context.atob = atob;
  // STL, binary: one triangle.
  const stl = new ArrayBuffer(84 + 50), view = new DataView(stl);
  view.setUint32(80, 1, true);
  [0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0].forEach((v, i) => view.setFloat32(84 + i * 4, v, true));
  let mesh = a.parseSTL(stl);
  assert.equal(mesh.count, 1);
  assert.deepEqual([...mesh.positions], [0, 0, 0, 1, 0, 0, 0, 1, 0]);
  assert.deepEqual([...mesh.normals.slice(0, 3)], [0, 0, 1], 'flat normals from the winding');
  mesh = a.parseSTL(new TextEncoder().encode('solid x\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 2 0 0\nvertex 0 2 0\nendloop\nendfacet\nendsolid').buffer);
  assert.deepEqual(plain(mesh.max), [2, 2, 0], 'ASCII STL too');
  // OBJ: a quad (with v/vt/vn and a negative index) becomes two triangles.
  mesh = a.parseOBJ('v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1/1/1 2/2/1 3/3/1 -1/4/1\n');
  assert.equal(mesh.count, 2);
  assert.throws(() => a.parseOBJ('v 0 0 0\n'), /no triangles/);
  // glTF with an embedded buffer, a translated node and a base color.
  const positions = Buffer.from(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]).buffer);
  const gltf = {asset: {version: '2.0'}, scene: 0, scenes: [{nodes: [0]}], nodes: [{mesh: 0, translation: [10, 0, 0]}],
    meshes: [{primitives: [{attributes: {POSITION: 0}, material: 0}]}], materials: [{pbrMetallicRoughness: {baseColorFactor: [1, 0, 0, 1]}}],
    buffers: [{byteLength: 36, uri: 'data:application/octet-stream;base64,' + positions.toString('base64')}],
    bufferViews: [{buffer: 0, byteOffset: 0, byteLength: 36}], accessors: [{bufferView: 0, componentType: 5126, count: 3, type: 'VEC3'}]};
  mesh = await a.parseGLTF(new TextEncoder().encode(JSON.stringify(gltf)).buffer, async () => { throw Error('no external buffers here'); });
  assert.deepEqual([...mesh.positions.slice(0, 3)], [10, 0, 0], 'node translation applied');
  assert.deepEqual([...mesh.colors.slice(0, 3)], [1, 0, 0], 'base color kept');
  // GLB: the same JSON in a binary container with the buffer as the BIN chunk.
  const json = Buffer.from(JSON.stringify({...gltf, buffers: [{byteLength: 36}]}).padEnd(Math.ceil(JSON.stringify({...gltf, buffers: [{byteLength: 36}]}).length / 4) * 4, ' '));
  const glb = Buffer.alloc(12 + 8 + json.length + 8 + 36);
  glb.writeUInt32LE(0x46546c67, 0); glb.writeUInt32LE(2, 4); glb.writeUInt32LE(glb.length, 8);
  glb.writeUInt32LE(json.length, 12); glb.writeUInt32LE(0x4e4f534a, 16); json.copy(glb, 20);
  glb.writeUInt32LE(36, 20 + json.length); glb.writeUInt32LE(0x004e4942, 24 + json.length); positions.copy(glb, 28 + json.length);
  mesh = await a.parseGLTF(glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.length), async () => null);
  assert.equal(mesh.count, 1, 'GLB reads its BIN chunk');
  // Camera math: looking down -z from z=5 puts the origin in front.
  const m = a.mat4Multiply(a.mat4Perspective(0.8, 1, 0.1, 100), a.mat4LookAt([0, 0, 5], [0, 0, 0], [0, 1, 0]));
  const w = m[3] * 0 + m[7] * 0 + m[11] * 0 + m[15];
  assert.ok(w > 0 && Math.abs(m[12] / w) < 1e-9, 'the target projects to the middle');

  // Kinds and the viewer.
  for (const [file, kind] of [['a.PNG', 'image'], ['b.mov', 'video'], ['c.m4a', 'audio'], ['d.pdf', 'pdf'], ['e.docx', 'doc'], ['f.glb', 'model'], ['g.md', 'text'], ['h.py', 'text'], ['i.pages', 'other']])
   assert.equal(a.cvFileKind(file), kind, file);
  const tree = treeHarness(), b = tree.a;
  b.cv.doc = {nodes: [
    {id: 'v', type: 'file', file: 'attachments/clip.mov', x: 0, y: 0, width: 200, height: 200},
    {id: 'd', type: 'file', file: 'attachments/report.docx', x: 0, y: 0, width: 200, height: 200},
    {id: 'l', type: 'link', url: 'https://example.com/a', x: 0, y: 0, width: 200, height: 200, unlawPreview: {title: 'Example', site: 'example.com'}},
    {id: 'j', type: 'link', url: 'javascript:alert(1)', x: 0, y: 0, width: 200, height: 200},
  ], edges: []};
  b.cv.path = '/c/a.canvas';
  b.cv.ui.view = new tree.context.Node('view');
  const find = (node, tag) => node.tagName === tag ? node : (node.children || []).map(child => typeof child === 'string' ? null : find(child, tag)).find(Boolean) || null;
  tree.context.document.createElement = tag => { const node = new tree.context.Node(); node.tagName = tag.toUpperCase(); return node; };
  assert.equal(b.cvView('n:v'), true);
  const video = find(b.cv.ui.view, 'VIDEO');
  assert.ok(video && video.attrs.src.includes('raw=1') && video.attrs.src.includes('file=attachments%2Fclip.mov'), 'a video plays in the page');
  let paused = false;
  b.cv.ui.view.querySelectorAll = () => [{pause() { paused = true; }}];
  b.cvCloseView();
  assert.ok(paused, 'closing stops the sound');
  b.cv.ui.view.querySelectorAll = () => [];
  b.cvView('n:d');
  const doc = find(b.cv.ui.view, 'IFRAME');
  assert.equal(doc.attrs.sandbox, '', 'documents never run script');
  assert.ok(doc.attrs.src.includes('doc=1'));
  b.cvView('n:l');
  const page = find(b.cv.ui.view, 'IFRAME');
  assert.equal(page.attrs.src, 'https://example.com/a');
  assert.ok(!page.attrs.sandbox.includes('allow-top-navigation'), 'a page cannot take the tab');
  let asked = 0;
  tree.context.fetch = async () => { asked++; return response({}); };
  b.cvView('n:j');
  assert.equal(find(b.cv.ui.view, 'IFRAME'), null, 'only http(s) addresses are shown');
  assert.equal(asked, 0);

  // A pasted link becomes a link card and asks for its preview.
  const calls = [];
  tree.context.fetch = async (path, init) => { calls.push([path, JSON.parse(init.body || 'null')]); return response({title: 'Hello', description: 'D', site: 'example.org', image: null}); };
  b.cv.view = {x: 0, y: 0, z: 1}; b.cv.w = 800; b.cv.h = 600;
  b.cv.hist = {undo: [], redo: [], cur: '{}'};
  tree.run('cvCommit = () => {};');
  assert.equal(b.cvPasteText('not a link'), false);
  assert.equal(b.cvPasteText('  https://example.org/x  '), true);
  const card = b.cv.doc.nodes.at(-1);
  assert.deepEqual([card.type, card.url], ['link', 'https://example.org/x']);
  for (let i = 0; i < 3; i++) await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(calls[0], ['/api/canvas/link-preview', {path: '/c/a.canvas', url: 'https://example.org/x'}]);
  assert.equal(card.unlawPreview.title, 'Hello');
  assert.equal('unlawPreviewing' in card, false, 'no working flag is saved');
 },
 async canvas_gallery_shelf_links_and_cards_that_play() {
  const h = harness(), a = h.a;
  // Links between canvases: relative to the canvas's folder, absolute for one elsewhere.
  assert.equal(a.canvasLinkPath('/c/a.canvas', 'b.canvas'), '/c/b.canvas');
  assert.equal(a.canvasLinkPath('/c/a.canvas', './sub/../x/../b.canvas'), '/c/b.canvas');
  assert.equal(a.canvasLinkPath('/c/a.canvas', '../d/e.canvas'), '/d/e.canvas');
  assert.equal(a.canvasLinkPath('/c/a.canvas', '/z/f.canvas'), '/z/f.canvas');
  assert.equal(a.canvasLinkFile('/c/a.canvas', '/c/sub/b.canvas'), 'sub/b.canvas');
  assert.equal(a.canvasLinkFile('/c/a.canvas', '/cc/b.canvas'), '/cc/b.canvas', 'a folder with the same start is elsewhere');
  assert.equal(a.cvFileKind('x/Plan.CANVAS'), 'canvas');

  // A text card that is only a link (or a title over a link) becomes a link card.
  assert.deepEqual(plain(a.urlCardText(' https://amikolabs.com/ ')), {url: 'https://amikolabs.com/', title: ''});
  assert.deepEqual(plain(a.urlCardText('Amiko Labs\nhttps://amikolabs.com/')), {url: 'https://amikolabs.com/', title: 'Amiko Labs'});
  for (const text of ['hello', 'a\nb\nhttps://x.org', 'https://x.org\nmore words', 'javascript:alert(1)', 'https://a.org\nhttps://b.org'])
   assert.equal(a.urlCardText(text), null, text);
  const card = {id: 't', type: 'text', text: 'Site\nhttps://x.org', x: 0, y: 0, width: 10, height: 10};
  assert.equal(a.textToLink(card), true);
  assert.deepEqual([card.type, card.url, 'text' in card, card.unlawPreview.title], ['link', 'https://x.org', false, 'Site']);
  assert.equal(a.textToLink({id: 'n', type: 'text', text: 'note'}), false);

  // Favorites and groups only list paths; a canvas is in one group at most; search keeps names with every word.
  const items = [{path: '/c/plan.canvas', name: 'Plan'}, {path: '/c/case.canvas', name: 'Case notes'}, {path: '/c/x.canvas', name: 'Trip'}];
  let shelf = a.cleanShelf({favorites: ['/c/x.canvas', 5], groups: [{name: 'Work', paths: ['/c/plan.canvas']}, {name: 7}]});
  assert.deepEqual(plain(shelf), {favorites: ['/c/x.canvas'], groups: [{name: 'Work', paths: ['/c/plan.canvas']}]});
  assert.equal(a.shelfAddGroup(shelf, ' work '), null, 'names are unique, case ignored');
  shelf = a.shelfAddGroup(shelf, '  Old   cases ');
  assert.equal(shelf.groups[1].name, 'Old cases');
  shelf = a.shelfMove(shelf, '/c/plan.canvas', 'Old cases');
  assert.deepEqual(plain(shelf.groups.map(g => g.paths)), [[], ['/c/plan.canvas']], 'moving takes it out of the other group');
  shelf = a.shelfFavorite(a.shelfFavorite(shelf, '/c/case.canvas'), '/c/x.canvas');
  assert.deepEqual(plain(shelf.favorites), ['/c/case.canvas']);
  let sections = a.gallerySections(items, shelf);
  assert.deepEqual(plain(sections.map(s => [s.kind, s.name, s.items.map(i => i.name)])),
   [['favorites', 'Favorites', ['Case notes']], ['group', 'Work', []], ['group', 'Old cases', ['Plan']], ['other', 'Not in a group', ['Case notes', 'Trip']]]);
  sections = a.gallerySections(items, shelf, '  NOTES case ');
  assert.deepEqual(plain(sections.map(s => [s.kind, s.items.map(i => i.name)])), [['favorites', ['Case notes']], ['other', ['Case notes']]], 'search drops empty sections');
  assert.deepEqual(plain(a.gallerySections(items, shelf, 'zzz')), []);
  shelf = a.shelfRenameGroup(shelf, 'Old cases', 'Archive');
  assert.equal(a.shelfRenameGroup(shelf, 'Archive', 'WORK'), null);
  assert.deepEqual(plain(a.shelfRemoveGroup(shelf, 'Archive').groups.map(g => g.name)), ['Work']);
  const calls = [];
  h.context.fetch = async (url, init = {}) => {
   const body = init.body ? JSON.parse(init.body) : null;
   calls.push([url, body]);
   if (url === '/api/canvas/shelf') return response({items, shelf: body.shelf});
   if (url === '/api/canvases' && body) return response({...sampleShape(), path: body.path, name: 'x'});
   return response({items, shelf: {}});
  };
  a.cv.ui = {};
  assert.equal(await a.cvSaveShelf(shelf), true);
  assert.deepEqual(calls.at(-1), ['/api/canvas/shelf', {shelf: plain(shelf)}]);

  // Following a canvas card opens that canvas; Back returns.
  a.cvLoad(sampleShape());
  a.cv.doc.nodes.push({id: 'k', type: 'file', file: 'sub/b.canvas', x: 0, y: 0, width: 300, height: 220});
  await a.cvFollowLink(a.cv.doc.nodes.at(-1));
  assert.equal(a.cv.path, '/c/sub/b.canvas');
  assert.deepEqual(plain(a.cv.back), ['/c/a.canvas']);
  await a.cvGoBack();
  assert.equal(a.cv.path, '/c/a.canvas');
  assert.deepEqual(plain(a.cv.back), []);
  a.cv.view = {x: 0, y: 0, z: 1}; a.cv.w = 800; a.cv.h = 600;
  a.cvAddCanvasLink({path: '/c/sub/b.canvas', name: 'b'});
  assert.equal(a.cv.doc.nodes.at(-1).file, 'sub/b.canvas', 'the gallery puts a relative link on the open canvas');

  // One click works the card (after a short wait, so a double click never does both); two open it whole.
  const tree = treeHarness(), b = tree.a;
  const made = [];
  tree.context.document.createElement = tag => {
   const node = new tree.context.Node();
   node.tagName = tag.toUpperCase();
   if (tag === 'video' || tag === 'audio') {
    Object.assign(node, {paused: true, ended: false, duration: 10, currentTime: 0, readyState: 4,
     play() { this.paused = false; return Promise.resolve(); }, pause() { this.paused = true; }, load() {}, removeAttribute(key) { this.src = ''; }});
    made.push(node);
   }
   return node;
  };
  const opened = [];
  tree.context.window.open = (...args) => opened.push(args[0]);
  tree.context.fetch = async () => response({});
  b.cv.doc = {nodes: [
   {id: 'v', type: 'file', file: 'attachments/clip.mov', x: 0, y: 0, width: 200, height: 200},
   {id: 'p', type: 'file', file: 'attachments/doc.pdf', x: 300, y: 0, width: 200, height: 260},
   {id: 'l', type: 'link', url: 'https://example.com/', x: 0, y: 300, width: 200, height: 200, unlawPreview: {title: 'E', icon: null, frameable: true}},
   {id: 'g', type: 'link', url: 'https://github.com/', x: 300, y: 300, width: 200, height: 200, unlawPreview: {title: 'G', icon: null, frameable: false}},
  ], edges: []};
  b.cv.path = '/c/a.canvas';
  b.cv.view = {x: 0, y: 0, z: 1};
  b.cv.ui.view = new tree.context.Node('view');
  b.cv.ui.inline = new tree.context.Node('inline');
  b.cv.ui.players = new tree.context.Node('players');
  const fire = () => { const all = [...tree.timers.values()]; tree.timers.clear(); for (const t of all) t.fn(); };
  tree.timers.clear();
  b.cvClickCard('n:v', {x: 100, y: 50});
  assert.equal(b.cv.playing, null, 'nothing happens before the double-click wait');
  fire();
  assert.equal(b.cv.playing.id, 'v');
  const video = made[0];
  assert.ok(video.src.includes('raw=1') && !video.paused, 'the video plays in its card');
  assert.equal(b.cvMediaState(b.cv.doc.nodes[0]).playing, true);
  const box = b.cvPictureBox(b.cv.doc.nodes[0], false);
  b.cvClickCard('n:v', {x: box.x + box.width / 2, y: box.y + box.height - 8}); fire();
  assert.equal(video.currentTime, 5, 'a click on the bar seeks');
  assert.equal(video.paused, false);
  b.cvClickCard('n:v', {x: 100, y: 50}); fire();
  assert.equal(video.paused, true, 'a click elsewhere on it pauses');
  b.cvClickCard('n:v', {x: 100, y: 50});
  b.cvCardDouble('n:v');
  assert.equal(tree.timers.size, 0, 'the double click cancels the single one');
  assert.equal(b.cv.playing, null, 'and stops the card');
  assert.equal(b.cv.viewing.key, 'n:v', 'the viewer opens');
  b.cvCloseView();
  b.cvClickCard('n:p', {x: 400, y: 50}); fire();
  assert.equal(b.cv.inline.id, 'p', 'a PDF opens in its card');
  assert.equal(b.cv.ui.inline.children[0].tagName, 'IFRAME');
  b.cvCloseInline();
  assert.equal(b.cv.inline, null);
  b.cvClickCard('n:l', {x: 50, y: 350}); fire();
  assert.equal(b.cv.viewing.key, 'n:l', 'a site opens inside the desk');
  b.cvCloseView();
  b.cvClickCard('n:g', {x: 350, y: 350}); fire();
  assert.deepEqual(opened, ['https://github.com/'], 'a site that refuses frames opens in a tab instead');
  b.cvCardDouble('n:l');
  assert.deepEqual(opened, ['https://github.com/', 'https://example.com/'], 'two clicks open a site in a tab');
  assert.equal(b.cv.viewing, null);

  // Peaks for a sound's wave: loudest = 1.
  assert.deepEqual(plain(a.cvPeaks(new Float32Array([0, 0.5, 0, -0.25]), 2)), [1, 0.5]);
 },
 async favicon_follows_the_page_theme() {
  const h = harness();
  const icon = h.ids.get('favicon');
  h.a.applyTheme('dark');
  assert.equal(icon.href, 'data:dark', 'dark theme shows the dark logo in the tab');
  h.a.applyTheme('light');
  assert.equal(icon.href, 'data:light', 'light theme shows the light logo');
 },
};
if (!tests[process.argv[2]]) throw Error('unknown UI regression');
tests[process.argv[2]]().catch(error => {console.error(error);process.exitCode = 1;});
