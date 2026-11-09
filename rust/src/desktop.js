// Unlaw templates: the macOS side. Run as `osascript -l JavaScript -e <this>`;
// one JSON request on stdin, one JSON answer as the result. Coordinates are
// global points with the origin at the top-left of the main display (the
// System Events convention).
ObjC.import('AppKit');
ObjC.import('ApplicationServices');

const SE = Application('System Events');

function readStdin() {
  const data = $.NSFileHandle.fileHandleWithStandardInput.readDataToEndOfFile;
  return ObjC.unwrap($.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding));
}

function screens() {
  const list = $.NSScreen.screens;
  const mainHeight = list.objectAtIndex(0).frame.size.height;
  const out = [];
  for (let i = 0; i < list.count; i++) {
    const s = list.objectAtIndex(i);
    const flip = (r) => [r.origin.x, mainHeight - (r.origin.y + r.size.height), r.size.width, r.size.height];
    out.push({ frame: flip(s.frame), visible: flip(s.visibleFrame) });
  }
  return out;
}

function defaultBrowser() {
  const url = $.NSWorkspace.sharedWorkspace.URLForApplicationToOpenURL($.NSURL.URLWithString('https://example.com'));
  if (!url || url.isNil()) return null;
  const bundle = $.NSBundle.bundleWithURL(url);
  const path = ObjC.unwrap(url.path);
  return { path, bundle: ObjC.unwrap(bundle.bundleIdentifier), name: appName(path) };
}

function appName(path) {
  return path.replace(/\/$/, '').split('/').pop().replace(/\.app$/, '');
}

function appPath(bundle) {
  const url = $.NSWorkspace.sharedWorkspace.URLForApplicationWithBundleIdentifier(bundle);
  return url && !url.isNil() ? ObjC.unwrap(url.path) : null;
}

// An app name as `open -a` takes it -> its bundle id.
function bundleFor(name) {
  const path = ObjC.unwrap($.NSWorkspace.sharedWorkspace.fullPathForApplication(name));
  if (!path) return null;
  return ObjC.unwrap($.NSBundle.bundleWithPath(path).bundleIdentifier);
}

function attr(win, name) {
  try { return win.attributes.byName(name).value(); } catch (e) { return null; }
}

function standardWindows(proc) {
  let wins = [];
  try { wins = proc.windows(); } catch (e) { return []; }
  return wins.filter((w) => {
    try { return w.subrole() === 'AXStandardWindow' && attr(w, 'AXMinimized') !== true; } catch (e) { return false; }
  });
}

function processFor(bundle) {
  const found = SE.applicationProcesses.whose({ bundleIdentifier: bundle })();
  return found.length ? found[0] : null;
}

function scriptableTabs(bundle) {
  try {
    const app = Application(bundle);
    return app.windows().map((w) => ({ id: String(w.id()), title: w.name(), urls: w.tabs().map((t) => t.url()).filter((u) => u) }));
  } catch (e) {
    return null;
  }
}

function filePath(document) {
  if (!document || typeof document !== 'string') return null;
  const url = $.NSURL.URLWithString(document);
  if (!url || url.isNil() || !url.isFileURL) return null;
  return ObjC.unwrap(url.path);
}

function snapshot() {
  const trusted = $.AXIsProcessTrusted();
  const result = { trusted, screens: screens(), browser: defaultBrowser(), apps: [] };
  if (!trusted) return result;
  const browser = result.browser;
  for (const proc of SE.applicationProcesses.whose({ backgroundOnly: false })()) {
    let bundle;
    try { bundle = proc.bundleIdentifier(); } catch (e) { continue; }
    if (!bundle) continue;
    const wins = standardWindows(proc);
    if (!wins.length) continue;
    const path = appPath(bundle);
    const app = { name: path ? appName(path) : proc.name(), bundle, windows: [] };
    let ghostty = null;
    if (bundle === 'com.mitchellh.ghostty') {
      try {
        ghostty = Application(bundle).windows().map((w) => ({
          id: String(w.id()),
          title: w.name(),
          tabs: w.tabs().map((t) => t.terminals().map((term) => term.workingDirectory())),
        }));
      } catch (e) { ghostty = null; }
    }
    let tabs = null;
    if (browser && bundle === browser.bundle) {
      app.browser = true;
      tabs = scriptableTabs(bundle);
      browser.scriptable = tabs !== null;
    }
    wins.forEach((w, index) => {
      const title = w.name() || '';
      const pos = w.position(), size = w.size();
      const entry = { title, frame: [pos[0], pos[1], size[0], size[1]], document: filePath(attr(w, 'AXDocument')) };
      const match = (list) => list && (list.find((item) => item.title === title) || list[index]);
      if (ghostty) {
        const g = match(ghostty);
        if (g) entry.tabs = g.tabs;
      }
      if (tabs) {
        const b = match(tabs);
        if (b) entry.urls = b.urls;
      }
      app.windows.push(entry);
    });
    result.apps.push(app);
  }
  return result;
}

function delay_(seconds) { delay(seconds); }

// With a `prefer` hint only a matching window is returned, so another window
// of the same app (another Zed project, a user's browser window) is never moved.
function waitForWindow(bundle, seconds, prefer) {
  const until = Date.now() + seconds * 1000;
  while (Date.now() < until) {
    const proc = processFor(bundle);
    if (proc) {
      const wins = standardWindows(proc);
      if (prefer) {
        const hit = wins.find((w) => { try { return prefer(w); } catch (e) { return false; } });
        if (hit) return hit;
      } else if (wins.length) {
        return wins[0];
      }
    }
    delay_(0.2);
  }
  return null;
}

function pidOf(bundle) {
  const proc = processFor(bundle);
  try { return proc ? proc.unixId() : null; } catch (e) { return null; }
}

// A remembered window counts only in the same app process: browser window ids
// restart from 1 after a relaunch and could name an unrelated window.
function remembered(item, bundle) {
  return item.state && item.state.id && item.state.pid && item.state.pid === pidOf(bundle) ? item.state.id : null;
}

function place(win, frame, screenNumber, allScreens) {
  if (!frame) return null;
  let note = null;
  let screen = allScreens[screenNumber - 1];
  if (!screen) {
    screen = allScreens[0];
    note = 'screen ' + screenNumber + ' is not connected, used the main one';
  }
  const [vx, vy, vw, vh] = screen.visible;
  const x = Math.round(vx + frame[0] * vw), y = Math.round(vy + frame[1] * vh);
  const w = Math.round(frame[2] * vw), h = Math.round(frame[3] * vh);
  // Size first: a window touching the right edge of a display cannot be made
  // narrower (measured with Ghostty: 650 stayed 650 at the edge, 575 elsewhere).
  // Then move it, then size and move once more for apps that clamp to the
  // display they were on.
  win.size = [w, h];
  win.position = [x, y];
  const now = win.size();
  if (now[0] !== w || now[1] !== h) {
    win.size = [w, h];
    win.position = [x, y];
  }
  return note;
}

function ghosttyConfig(pane) {
  const config = {};
  if (pane.dir) config.initialWorkingDirectory = pane.dir;
  if (pane.run) config.initialInput = pane.run + '\n';
  return config;
}

function openTerminal(item) {
  const g = Application('Ghostty');
  const known = remembered(item, 'com.mitchellh.ghostty');
  if (known) {
    const existing = g.windows().find((w) => String(w.id()) === known);
    if (existing) {
      g.activateWindow(existing);
      return { id: known, reused: true };
    }
  }
  let win = null;
  item.tabs.forEach((panes, tabIndex) => {
    let term;
    if (tabIndex === 0) {
      win = g.newWindow({ withConfiguration: ghosttyConfig(panes[0]) });
      term = win.selectedTab().focusedTerminal();
    } else {
      const tab = g.newTab({ in: win, withConfiguration: ghosttyConfig(panes[0]) });
      term = tab.focusedTerminal();
    }
    panes.slice(1).forEach((pane) => {
      term = g.split(term, { direction: pane.split || 'right', withConfiguration: ghosttyConfig(pane) });
    });
  });
  if (item.tabs.length > 1) g.selectTab(win.tabs()[0]);
  g.activateWindow(win);
  return { id: String(win.id()), reused: false };
}

function scriptable(app) {
  try { app.windows.length; app.windows().forEach((w) => w.id()); return true; } catch (e) { return false; }
}

function openBrowser(item, browser, notes) {
  const app = Application(browser.bundle);
  if (!scriptable(app)) {
    // Firefox, Zen, ...: open location is a synchronous Apple Event to the
    // default browser; the browser decides where the links open.
    const sa = Application.currentApplication();
    sa.includeStandardAdditions = true;
    item.urls.forEach((url) => sa.openLocation(url));
    if (!item.urls.length) app.activate();
    return { id: null, reused: false };
  }
  const known = remembered(item, browser.bundle);
  if (known) {
    const existing = app.windows().find((w) => String(w.id()) === known);
    if (existing) {
      existing.index = 1;
      app.activate();
      return { id: known, reused: true };
    }
  }
  app.activate();
  let win;
  if (browser.bundle === 'com.apple.Safari') {
    app.Document({ url: item.urls[0] || 'about:blank' }).make();
    win = app.windows[0];
  } else {
    win = app.Window().make();
    if (item.urls.length) win.activeTab.url = item.urls[0];
  }
  item.urls.slice(1).forEach((url) => {
    try { win.tabs.push(app.Tab({ url })); } catch (e) { notes.push('could not open ' + url); }
  });
  return { id: String(win.id()), reused: false };
}

function apply(plan) {
  const trusted = $.AXIsProcessTrusted();
  const allScreens = screens();
  const browser = defaultBrowser();
  const results = [];
  const keep = new Set(['com.mitchellh.ghostty']);
  for (const item of plan.windows) {
    const result = { index: item.index, ok: true, notes: [] };
    results.push(result);
    try {
      let bundle, prefer = null;
      if (item.kind === 'terminal' || item.kind === 'browser') {
        let opened;
        if (item.kind === 'terminal') {
          bundle = 'com.mitchellh.ghostty';
          opened = openTerminal(item);
        } else {
          if (!browser) throw new Error('no default browser');
          bundle = browser.bundle;
          opened = openBrowser(item, browser, result.notes);
        }
        if (opened.id) result.state = { id: opened.id, pid: pidOf(bundle) };
        if (opened.reused) result.notes.push('reused its window');
        // The window just created or reused is the one to place. Its title
        // changes (the shell sets the folder, a page loads), so read it fresh
        // by id on every check.
        if (opened.id) {
          const app = Application(bundle), id = opened.id;
          prefer = (w) => {
            const own = app.windows().find((x) => String(x.id()) === id);
            return own !== undefined && (w.name() || '') === (own.name() || '');
          };
        }
      } else {
        bundle = bundleFor(item.app);
        if (!bundle) throw new Error('app not found');
        if (item.open) {
          const base = item.open.replace(/\/$/, '').split('/').pop();
          prefer = (w) => (w.name() || '').includes(base) || filePath(attr(w, 'AXDocument')) === item.open;
        }
      }
      keep.add(bundle);
      if (!item.frame) continue;
      if (!trusted) {
        result.ok = false;
        result.notes.push('not placed: no Accessibility permission');
        continue;
      }
      const win = waitForWindow(bundle, plan.wait || 10, prefer);
      if (!win) {
        result.ok = false;
        result.notes.push(prefer ? 'its window was not found in ' + (plan.wait || 10) + ' s, nothing moved'
                                 : 'window did not appear in ' + (plan.wait || 10) + ' s');
        continue;
      }
      const note = place(win, item.frame, item.screen, allScreens);
      if (note) result.notes.push(note);
      try { win.actions.byName('AXRaise').perform(); } catch (e) { /* raising is cosmetic */ }
    } catch (e) {
      result.ok = false;
      result.notes.push(String(e.message || e));
    }
  }
  if (plan.focus) {
    for (const proc of SE.applicationProcesses.whose({ backgroundOnly: false, visible: true })()) {
      try {
        const bundle = proc.bundleIdentifier();
        if (!keep.has(bundle) && bundle !== 'com.apple.finder') proc.visible = false;
      } catch (e) { /* an app quitting meanwhile */ }
    }
  }
  return { trusted, results };
}

function run() {
  const request = JSON.parse(readStdin());
  const answer = request.mode === 'snapshot' ? snapshot() : apply(request.plan);
  return JSON.stringify(answer);
}
