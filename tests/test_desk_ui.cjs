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
    addEventListener() {},
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
      leaveStudio, toggleCamera, toggleMeter, stopStream, start, sendGame, pollWhileBusy, drawCell};
  `, context);
  return {context, a: context.audit, timers, intervals, frames, ids,
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
const response = data => ({status: 200, json: async () => data});
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
};
if (!tests[process.argv[2]]) throw Error('unknown UI regression');
tests[process.argv[2]]().catch(error => {console.error(error);process.exitCode = 1;});
