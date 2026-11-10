const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const raw = fs.readFileSync(path.join(__dirname, '../src/unlawful/desk_ui.py'), 'utf8');
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
    'filter', 'helpButton', 'help', 'theme', 'search', 'toast',
  ].map(id => [id, new Element(id)]));
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
      leaveStudio, toggleCamera, toggleMeter, stopStream, start, sendGame, pollWhileBusy, drawCell,
      cv, mulberry32, toScreen, toWorld, zoomAt, fitView, roughStrokes, hitElement, hitTest, edgeCurve, hitEdge,
      nearestSide, resizeBox, handleAt, applyBox, wrapText, adaptInk, nodeColor, noteName, makeLinear, makeFreedraw,
      snapAngle, applyStyle, containedIds, groupAround, moveItems, removeItems, copyItems, pasteItems, makeHistory,
      histCommit, histUndo, histRedo, cvLoad, cvCommit, cvUndo, cvRedo, saveCanvas, pollCanvas,
      renderCanvas, cvDown, cvMove, cvUp, cvWheel, cvSetTool, cvEndEdit, cvSelect, cvGroup, cvExport, paintScene, cvPalette,
      fillable, fillTarget, applyFill, setBackground, cvBackground, canvasKey, cvStyle, cvNew, cvRename, cvChoose, CV_BY_KEY,
      floodRegion, growMask, traceMask, paintFromMask, paintContains, cutElement, eraseAt, cvBucket, cvToolClick,
      widthToSlider, sliderToWidth, cvStepWidth, cvBuildBar, cvTypedWidth};
  `, context);
  return {context, a: context.audit, listeners, timers, intervals, frames, ids,
    run: code => vm.runInContext(code, context)};
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
  h.a.studio.cam = 'Webcam';
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
  h.a.studio.mic = 'Microphone';
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
  const h = harness(), pending = deferred(), cam = stream();
  h.a.state.view = 'studio';
  h.a.studio.mode = 'camera';
  h.context.navigator.mediaDevices.getUserMedia = () => pending.promise;
  h.context.fetch = async () => response({active: true, phase: 'recording', elapsed: 0});
  const job = h.a.toggleCamera();
  await h.a.toggleRecord();
  pending.resolve(cam);
  await job;
  assert.equal(cam.track.stopped, true, 'recording must keep the camera released for ffmpeg');
  assert.equal(h.a.studio.camStream, null);
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
  const periodic = [...h.intervals.values()].find(x => x.ms === 8000);
  await periodic.fn();
  await Promise.resolve();
  assert.equal(calls, 1, 'visible Studio must poll for terminal recording changes');
  assert.equal(h.a.studio.status.active, true);
  assert.ok([...h.timers.values()].some(x => x.ms === 1500), 'an observed active recording must keep polling');
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
};
if (!tests[process.argv[2]]) throw Error('unknown UI regression');
tests[process.argv[2]]().catch(error => {console.error(error);process.exitCode = 1;});
