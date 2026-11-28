// Edit: the main window's editor part. Folders the user added on the left, the open
// files across the top, and on the right either the code editor (the real `ule`,
// drawn from the frames Rust relays) or a viewer for what is not text (pictures,
// PDF, sound, video, and a Quick Look picture of the rest). Rust checks every path
// and every editor key against its own rules; this page only draws and asks.
"use strict";

const edit = {
  places: null,
  error: "",
  errorTimer: 0,
  tree: {},          // folder path -> { entries, truncated, loading }
  open: new Set(JSON.parse(stored("edit-open-folders", "[]") || "[]")),
  viewers: [],       // files shown by a viewer: { path, name, info, picture, error }
  showing: null,     // "code" or the path of a viewer
  info: {},          // path -> `ul doc info`
  ule: { id: 0, starting: false, frame: null, ended: "", queue: [], cell: null },
};

const EDIT_MONO = 'ui-monospace, "SF Mono", Menlo, monospace';
const EDIT_FONT = 13;
// The 16 terminal colors ule's default theme names, in the app's two looks.
const EDIT_ANSI = {
  dark: ["#1d1f23", "#ff6b6b", "#5fd38d", "#e5c07b", "#61afef", "#c678dd", "#56b6c2", "#d7dae0",
    "#5c6370", "#ff8787", "#7ee2a8", "#f0d08a", "#82c0ff", "#d79cf0", "#7fd1dc", "#ffffff"],
  light: ["#2b2b2e", "#c92a2a", "#2b8a3e", "#a86400", "#1c64c8", "#9c36b5", "#0b7285", "#e9e9ec",
    "#868e96", "#e03131", "#37b24d", "#c27c0e", "#3b82f6", "#ae3ec9", "#1098ad", "#ffffff"],
};
const EDIT_KEYS = { Escape: "Esc", Enter: "Enter", Tab: "Tab", Backspace: "Backspace", Delete: "Delete",
  ArrowUp: "Up", ArrowDown: "Down", ArrowLeft: "Left", ArrowRight: "Right", Home: "Home", End: "End",
  PageUp: "PageUp", PageDown: "PageDown", Insert: "Insert" };
// ⌘ shortcuts the editor answers to with its ordinary-editor keys (Ctrl in a terminal).
const EDIT_COMMAND_KEYS = { KeyZ: "z", KeyY: "y", KeyC: "c", KeyX: "x", KeyA: "a", KeyF: "f", KeyG: "g", Slash: "/" };
// ⌘ shortcuts that run an editor command in either key mode, as in Zed: [code, shift] -> command.
const EDIT_MENU_KEYS = { "KeyP": "file_picker", "KeyP+": "command_palette", "KeyF+": "grep", "KeyS": "save",
  "KeyS+": "save_all", "KeyO+": "symbols", "KeyE+": "recent_files", "KeyK+": "keymap_picker" };
// Colors of each file kind's icon in the project panel (like Zed's file icons).
const EDIT_FILE_COLORS = { rs: "#dea584", py: "#4b8bbe", js: "#e5c07b", mjs: "#e5c07b", ts: "#3178c6", tsx: "#3178c6",
  jsx: "#61dafb", json: "#cbcb41", toml: "#9c7a5b", yaml: "#cb4b16", yml: "#cb4b16", md: "#519aba", html: "#e44d26",
  css: "#563d7c", c: "#599eff", h: "#a074c4", cpp: "#f34b7d", go: "#00add8", sh: "#89e051", zsh: "#89e051",
  swift: "#f05138", sql: "#dad8d8", csv: "#89e051", pdf: "#e2574c", docx: "#2b579a", xlsx: "#217346", lock: "#8a8a8a" };
const VIEWED = new Set(["image", "pdf", "media"]);
// A key's place on a US keyboard (event.code): [plain, with Shift].
const US_KEYS = { Minus: "-_", Equal: "=+", BracketLeft: "[{", BracketRight: "]}", Backslash: "\\|", Semicolon: ";:",
  Quote: "'\"", Comma: ",<", Period: ".>", Slash: "/?", Backquote: "`~", Digit1: "1!", Digit2: "2@", Digit3: "3#",
  Digit4: "4$", Digit5: "5%", Digit6: "6^", Digit7: "7&", Digit8: "8*", Digit9: "9(", Digit0: "0)" };

// Outside typing (vim's normal and visual modes) a letter is a command: in another
// keyboard layout it is read by its place, so `dd`, `:w` and `G` work in Russian too.
// A terminal cannot do this; the window knows the physical key.
function commandChar(event) {
  const frame = edit.ule.frame;
  if (!frame || frame.typing || /^[\x20-\x7e]$/.test(event.key)) return event.key;
  const letter = /^Key([A-Z])$/.exec(event.code);
  if (letter) return event.shiftKey ? letter[1] : letter[1].toLowerCase();
  const pair = US_KEYS[event.code];
  return pair ? pair[event.shiftKey ? 1 : 0] : event.key;
}

function isDark() { return document.documentElement.classList.contains("dark"); }

// ---------- the part ----------

// Laid out like Zed: a title bar (project, file search, key mode), the project panel on
// the left, tabs over the editor, and a status bar along the bottom. Every surface takes
// its colors from the editor's theme, so the whole part changes with it.
function renderEdit() {
  header("Edit", "");
  const title = dragArea(el("div", { class: "etitle" },
    el("span", { class: "project" }),
    el("div", { class: "grow" }),
    el("button", { class: "esearch", title: "Find a file (⌘P)", onclick: () => editCommand("file_picker") },
      icon("search"), el("span", { text: "Search files…" }), el("kbd", { text: "⌘P" })),
    el("div", { class: "grow" }),
    el("button", { class: "ghost icon", title: "Run the open file in the terminal (⌘R)", "aria-label": "Run", onclick: termRunFile }, icon("run")),
    el("button", { class: "ghost icon", title: "All commands (⌘⇧P)", "aria-label": "Commands", onclick: () => editCommand("command_palette") }, icon("command"))));
  const tree = el("aside", { class: "etree", tabindex: "0" });
  tree.addEventListener("keydown", treeKey);
  // Anywhere in the panel that is not a row or a button: the panel's own menu.
  tree.addEventListener("contextmenu", (event) => { if (!event.target.closest(".erow, button, input")) treeMenu(event, null); });
  edit.treeNode = tree;
  const pane = el("div", { class: "epane" },
    el("div", { class: "etabs" }),
    el("div", { class: "eerror", hidden: "" }),
    el("div", { class: "ebody" }));
  // Docks like Zed's: left, right and bottom; the project panel and the terminal can sit in
  // any of them (dragged by their header), each dock resized by its inner edge.
  const work = el("div", { class: "ework" },
    el("div", { class: "edock", "data-dock": "left" }), dockGrip("left"),
    el("div", { class: "ecenter" }, pane, dockGrip("bottom"), el("div", { class: "edock", "data-dock": "bottom" })),
    dockGrip("right"), el("div", { class: "edock", "data-dock": "right" }));
  const box = el("div", { class: "edit" }, title, work, el("div", { class: "estatus" }));
  $(".content").replaceChildren(box);
  // The editor's grid follows its box, not only the window: the tab strip appearing with the
  // first file, an error line or a dock changing size resize it too (the last rows, ule's
  // own status line, were cut off).
  const body = pane.querySelector(".ebody");
  new ResizeObserver(() => { clearTimeout(uleResizeTimer); uleResizeTimer = setTimeout(() => { resizeUle(); scheduleUleDraw(); }, 30); }).observe(body);
  applyEditTheme();
  if (!edit.places) send({ op: "edit-places" });
  drawTree();
  drawPane();
  term.node = null;
  placePanels();
}

// File search and project search look in the first folder of the project.
function projectFolder() {
  const root = edit.places && edit.places.roots.find((item) => item.exists);
  if (!root || !edit.ule.id || edit.ule.cwd === root.path) return;
  edit.ule.cwd = root.path;
  edit.ule.queue.unshift({ cd: root.path });
  queueMicrotask(flushUle);
}

// Runs one of ule's commands (file search, all commands, save…) in either key mode.
function editCommand(name) {
  edit.showing = "code";
  uleSend({ command: name });
  drawPane();
}

function setEditPrefs(change) {
  // Shown at once: the editor's next frame confirms it (a second click before that must not
  // flip it back, which made the switch look broken).
  if (change.editing) edit.wantEditing = change.editing;
  send({ op: "edit-prefs", ...change });
  if (change.editing) { drawStatus(edit.info[currentPath()] || null); if (home.section === "settings") renderSettings(); }
}

// The key mode shown everywhere: the one just chosen until the editor says it took it.
function editingMode() {
  const frame = edit.ule.frame && edit.ule.frame.editing;
  const saved = edit.places && edit.places.editing;
  if (edit.wantEditing && (frame === edit.wantEditing || (!edit.ule.id && saved === edit.wantEditing))) edit.wantEditing = null;
  return edit.wantEditing || frame || (edit.places && edit.places.editing) || "vim";
}

function keyModeSwitch(editing) {
  const box = segmented([["vim", "Vim"], ["standard", "Standard"]], editing, (mode) => setEditPrefs({ editing: mode }));
  box.title = "Vim: modes (normal, insert, visual). Standard: type at once, like Zed or VS Code. The terminal ule follows too.";
  return box;
}

// The editor theme colors only the code (its own background and text); every other surface
// of the part uses the app's tokens, which follow the theme only with Look > Colors =
// "Editor theme". A theme without real colors (`unlaw`: terminal colors) draws on the glass.
function applyEditTheme() {
  const box = $(".edit");
  if (!box) return;
  const theme = edit.ule.frame && edit.ule.frame.theme;
  const hex = (value) => (/^#[0-9a-f]{6}$/i.test(value || "") ? value : null);
  for (const [name, value] of [["--code-bg", hex(theme && theme.bg)], ["--code-fg", hex(theme && theme.fg)]]) {
    if (value) { if (box.style.getPropertyValue(name) !== value) box.style.setProperty(name, value); }
    else box.style.removeProperty(name);
  }
}

// ---------- docks ----------
const DOCKS = ["left", "right", "bottom"];
const PANELS = { tree: "Project", term: "Terminal" };

function dockOf() {
  let saved = {};
  try { saved = JSON.parse(stored("edit-docks", "{}")) || {}; } catch { saved = {}; }
  const pick = (value, fallback) => (DOCKS.includes(value) ? value : fallback);
  return { tree: pick(saved.tree, "left"), term: pick(saved.term, "bottom") };
}

function dockSizes() {
  let saved = {};
  try { saved = JSON.parse(stored("edit-dock-size", "{}")) || {}; } catch { saved = {}; }
  const number = (value, fallback) => (Number.isFinite(value) && value > 0 ? value : fallback);
  return { left: number(saved.left, Number(stored("edit-tree-width", "240")) || 240), right: number(saved.right, 300),
    bottom: number(saved.bottom, Number(stored("edit-term-height", "240")) || 240) };
}

function clampDock(dock, size) {
  const work = $(".ework");
  const room = work ? (dock === "bottom" ? work.clientHeight - 120 : work.clientWidth - 280) : 800;
  return Math.round(Math.max(dock === "bottom" ? 90 : 150, Math.min(Math.max(150, room), size)));
}

function treeHidden() { return stored("edit-tree-hidden", "0") === "1"; }

function toggleEditTree() {
  store("edit-tree-hidden", treeHidden() ? "0" : "1");
  placePanels();
}

// Puts each shown panel in its dock; empty docks and their grips are hidden.
function placePanels() {
  const box = $(".edit");
  if (!box) return;
  const where = dockOf(), sizes = dockSizes();
  if (term.open && !term.sessions.length) termNew();
  if (term.open && !term.node) termBuild();
  const shown = { tree: !treeHidden() && edit.treeNode, term: term.open && term.node };
  for (const dock of DOCKS) {
    const holder = box.querySelector(`.edock[data-dock="${dock}"]`);
    const panels = Object.keys(PANELS).filter((id) => shown[id] && where[id] === dock).map((id) => shown[id]);
    for (const child of [...holder.children]) if (!panels.includes(child)) child.remove();
    for (const panel of panels) if (panel.parentNode !== holder) holder.appendChild(panel);
    holder.hidden = !panels.length;
    box.querySelector(`.dgrip[data-dock="${dock}"]`).hidden = !panels.length;
    holder.style[dock === "bottom" ? "height" : "width"] = clampDock(dock, sizes[dock]) + "px";
  }
  window.dispatchEvent(new Event("resize"));
}

function dockGrip(dock) {
  const grip = el("div", { class: "dgrip", "data-dock": dock, title: "Drag to resize" });
  grip.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    grip.setPointerCapture(event.pointerId);
    const sizes = dockSizes(), from = sizes[dock], x = event.clientX, y = event.clientY;
    const holder = $(`.edock[data-dock="${dock}"]`);
    document.body.classList.add(dock === "bottom" ? "resizing-v" : "resizing");
    const move = (next) => {
      const delta = dock === "left" ? next.clientX - x : dock === "right" ? x - next.clientX : y - next.clientY;
      sizes[dock] = clampDock(dock, from + delta);
      holder.style[dock === "bottom" ? "height" : "width"] = sizes[dock] + "px";
    };
    const up = () => {
      grip.removeEventListener("pointermove", move);
      document.body.classList.remove("resizing", "resizing-v");
      store("edit-dock-size", JSON.stringify(sizes));
      window.dispatchEvent(new Event("resize"));
    };
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", up, { once: true });
    grip.addEventListener("pointercancel", up, { once: true });
  });
  grip.addEventListener("dblclick", () => {
    const sizes = dockSizes();
    sizes[dock] = dock === "bottom" ? 240 : dock === "left" ? 240 : 300;
    store("edit-dock-size", JSON.stringify(sizes));
    placePanels();
  });
  return grip;
}

function movePanelTo(id, dock) {
  const where = dockOf();
  where[id] = dock;
  store("edit-docks", JSON.stringify(where));
  placePanels();
}

// Dragging a panel by its header: zones light up over the editor; letting go over one
// moves the panel there. A short press stays a click.
function panelDrag(header, id) {
  header.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.target.closest("button, input, select")) return;
    const startX = event.clientX, startY = event.clientY;
    let overlay = null, zone = null, label = null;
    const zoneAt = (x, y) => {
      const rect = $(".ework").getBoundingClientRect();
      if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) return null;
      if (x < rect.left + rect.width * 0.25) return "left";
      if (x > rect.right - rect.width * 0.25) return "right";
      if (y > rect.bottom - rect.height * 0.4) return "bottom";
      return null;
    };
    const move = (next) => {
      if (!overlay) {
        if (Math.hypot(next.clientX - startX, next.clientY - startY) < 6) return;
        overlay = el("div", { class: "edrop" }, ...DOCKS.map((dock) => el("div", { class: "edropzone", "data-dock": dock }, el("span", { text: dock[0].toUpperCase() + dock.slice(1) }))));
        $(".ework").appendChild(overlay);
        label = el("div", { class: "edraglabel", text: PANELS[id] });
        document.body.appendChild(label);
        document.body.classList.add("dragging-panel");
      }
      zone = zoneAt(next.clientX, next.clientY);
      for (const item of overlay.children) item.classList.toggle("on", item.dataset.dock === zone);
      label.style.left = next.clientX + 12 + "px";
      label.style.top = next.clientY + 12 + "px";
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      if (!overlay) return;
      overlay.remove();
      label.remove();
      document.body.classList.remove("dragging-panel");
      if (zone) movePanelTo(id, zone);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });
  header.addEventListener("contextmenu", (event) => {
    if (event.target.closest("button, input")) return;
    event.preventDefault();
    event.stopPropagation();
    closeTreeMenu();
    const here = dockOf()[id];
    const item = (label, run, off) => el("button", { class: "emi", disabled: off ? "" : null, onclick: () => { closeTreeMenu(); run(); } }, el("span", { text: label }));
    const menu = el("div", { class: "emenu", role: "menu" },
      ...DOCKS.map((dock) => item(`Move to the ${dock}`, () => movePanelTo(id, dock), dock === here)),
      el("hr"),
      item(id === "tree" ? "Hide the project panel (⌘B)" : "Hide the terminal (⌃`)", () => (id === "tree" ? toggleEditTree() : showTerminal(false))));
    openMenuAt(menu, event);
  });
}

function openMenuAt(menu, event) {
  ($(".edit") || document.body).appendChild(menu);
  menu.style.left = Math.min(event.clientX, innerWidth - menu.offsetWidth - 6) + "px";
  menu.style.top = Math.min(event.clientY, innerHeight - menu.offsetHeight - 6) + "px";
  setTimeout(() => document.addEventListener("mousedown", function away(click) {
    if (!menu.contains(click.target)) closeTreeMenu();
    document.removeEventListener("mousedown", away, true);
  }, true));
}

function showEditError(text) {
  edit.error = text;
  clearTimeout(edit.errorTimer);
  edit.errorTimer = setTimeout(() => { edit.error = ""; drawError(); }, 6000);
  drawError();
}

function drawError() {
  const box = $(".eerror");
  if (!box) return;
  box.hidden = !edit.error;
  box.classList.toggle("note", !!edit.errorIsNote);
  box.textContent = edit.error;
}

function showEditNote(text) {
  edit.errorIsNote = true;
  showEditError(text);
  edit.errorIsNote = false;
}

// ---------- the file tree ----------

function rememberOpen() { store("edit-open-folders", JSON.stringify([...edit.open].slice(-200))); }

function toggleFolder(path) {
  if (edit.open.has(path)) edit.open.delete(path);
  else { edit.open.add(path); if (!edit.tree[path]) listFolder(path); }
  rememberOpen();
  drawTree();
}

function listFolder(path) {
  edit.tree[path] = edit.tree[path] || { entries: [], loading: true };
  send({ op: "edit-list", path });
}

function drawTree() {
  const tree = $(".etree");
  if (!tree) return;
  const places = edit.places;
  if (!places) { tree.replaceChildren(el("div", { class: "note", text: "Loading…" })); return; }
  const parts = [];
  const tool = (name, title, run) => el("button", { class: "ghost tiny", title, "aria-label": title, onclick: (event) => { event.stopPropagation(); run(); } }, icon(name));
  const head = el("div", { class: "ehead", title: "Drag to move the panel; right-click for more" }, el("h4", { text: "Project" }), el("div", { class: "grow" }),
    // Each asks where first (a macOS dialog); new files and folders inside the project stay on
    // the right-click menu, ⌘N and ⇧⌘N.
    tool("filePlus", "New file: choose where it goes", () => send({ op: "edit-new-file-dialog" })),
    tool("folderPlus", "New project folder: choose its name and place", () => send({ op: "edit-new-project-dialog" })),
    tool("search", "Add a folder to the project, or open a file", () => send({ op: "edit-pick-dialog" })));
  panelDrag(head, "tree");
  parts.push(head);
  for (const root of places.roots) {
    const open = edit.open.has(root.path);
    const head = el("div", { class: "erow root" + (open ? " open" : "") + (edit.selected === root.path ? " sel" : ""), title: root.path,
      onclick: () => { edit.selected = root.path; toggleFolder(root.path); }, oncontextmenu: (event) => treeMenu(event, { path: root.path, dir: true, root: true }) },
      el("span", { class: "chev", text: open ? "▾" : "▸" }), icon("folder"), el("span", { class: "name", text: root.name || root.path }),
      el("button", { class: "ghost x", title: "Remove from the list (the folder stays)", text: "×", onclick: (event) => {
        event.stopPropagation(); send({ op: "edit-remove-folder", path: root.path });
      } }));
    dropTarget(head, root.path);
    parts.push(head);
    if (edit.naming && edit.naming.dir === root.path && edit.naming.kind !== "rename") { if (!open) toggleFolder(root.path); }
    if (open) parts.push(...folderRows(root.path, 1));
  }
  // Recent files (5), each with × to take it off; below the folders, so opening a file
  // (which reorders the list) never moves the tree under the mouse.
  const recent = (places.recent || []).slice(0, 5);
  if (recent.length) {
    parts.push(el("h4", { text: "Recent" }));
    for (const item of recent) {
      const row = fileRow(item.path, item.name, 0);
      if (!item.exists) row.classList.add("gone");
      row.appendChild(el("button", { class: "ghost x", title: "Take off the list (the file stays)", text: "×", onclick: (event) => {
        event.stopPropagation(); send({ op: "edit-forget", path: item.path });
      } }));
      parts.push(row);
    }
  }
  tree.replaceChildren(...parts);
  const naming = tree.querySelector("input.ename");
  if (naming && document.activeElement !== naming) { naming.focus(); const dot = naming.value.lastIndexOf("."); naming.setSelectionRange(0, dot > 0 ? dot : naming.value.length); }
  const project = $(".etitle .project");
  if (project) project.textContent = places.roots.length ? places.roots.map((root) => root.name).join(", ") : "No project";
}

function folderRows(path, depth) {
  const listed = edit.tree[path];
  if (!listed || listed.loading) return [el("div", { class: "erow muted", style: `padding-left:${8 + depth * 14}px`, text: "…" })];
  const rows = [];
  const naming = edit.naming;
  // A new file or folder is typed in a row at the top of its folder, as in Zed.
  if (naming && naming.kind !== "rename" && naming.dir === path) rows.push(nameRow(naming.kind === "new-folder" ? "folder" : "file", "", depth));
  for (const entry of listed.entries) {
    if (naming && naming.kind === "rename" && naming.path === entry.path) {
      rows.push(nameRow(entry.dir ? "folder" : fileIcon(entry.name), entry.name, depth));
      continue;
    }
    if (entry.dir) {
      const open = edit.open.has(entry.path);
      const row = el("div", { class: "erow dir" + (open ? " open" : "") + (edit.selected === entry.path ? " sel" : ""), style: `padding-left:${8 + depth * 14}px`, title: entry.path,
        draggable: "true", onclick: () => { edit.selected = entry.path; toggleFolder(entry.path); },
        oncontextmenu: (event) => treeMenu(event, entry) },
        ...guides(depth), el("span", { class: "chev", text: open ? "▾" : "▸" }), folderIcon(entry.name, open), el("span", { class: "name", text: entry.name }));
      dragSource(row, entry.path);
      dropTarget(row, entry.path);
      rows.push(row);
      if (open) rows.push(...folderRows(entry.path, depth + 1));
    } else {
      rows.push(fileRow(entry.path, entry.name, depth));
    }
  }
  if (listed.truncated) rows.push(el("div", { class: "erow muted", style: `padding-left:${8 + depth * 14}px`, text: "Only the first 5000 shown" }));
  return rows;
}

function fileRow(path, name, depth) {
  const active = currentPath() === path;
  const row = el("div", { class: "erow file" + (active ? " on" : "") + (edit.selected === path ? " sel" : ""), style: `padding-left:${22 + depth * 14}px`, title: path,
    draggable: "true", onclick: () => { edit.selected = path; openFile(path); },
    oncontextmenu: (event) => treeMenu(event, { path, name, dir: false }) },
    ...guides(depth), fileGlyph(name), el("span", { class: "name", text: name }));
  dragSource(row, path);
  return row;
}

// The user's file type for a name (filetypes.toml): whole names first, then the suffix.
function userType(name) {
  const types = (edit.places && edit.places.types) || {};
  const suffix = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
  return (types.names && types.names[name]) || (suffix && types.types && types.types[suffix]) || null;
}

function fileGlyph(name) {
  const own = userType(name);
  const icons = (edit.places && edit.places.icons) || [];
  let glyph;
  if (own && own.icon && icons.includes(own.icon)) {
    glyph = el("img", { class: "icon uicon", alt: "", src: "ulapp://localhost/edit/icon/" + own.icon });
    glyph.addEventListener("error", () => glyph.replaceWith(icon(fileIcon(name))));
    return glyph;
  }
  glyph = icon(own && own.icon && ICONS[own.icon] ? own.icon : fileIcon(name));
  const suffix = (name.split(".").pop() || "").toLowerCase();
  const color = (own && own.color) || EDIT_FILE_COLORS[suffix];
  if (color) glyph.style.color = color;
  return glyph;
}

function folderIcon() { return icon("folder"); }

// ---------- project panel actions (Zed's: new, rename, duplicate, Trash, move, copy path) ----------

// The row a name is typed in: Enter sends it, Esc or leaving the field cancels.
function nameRow(kind, value, depth) {
  const input = el("input", { class: "ename", value, spellcheck: "false", autocomplete: "off" });
  let done = false;
  const finish = (accept) => {
    if (done) return;
    done = true;
    const naming = edit.naming;
    edit.naming = null;
    const name = input.value.trim();
    if (accept && naming && name && name !== value) {
      if (naming.kind === "rename") send({ op: "edit-rename", path: naming.path, name });
      else send({ op: "edit-new", dir: naming.dir, name, folder: naming.kind === "new-folder" });
    }
    drawTree();
  };
  input.addEventListener("keydown", (event) => {
    event.stopPropagation();
    if (event.key === "Enter") { event.preventDefault(); finish(true); }
    else if (event.key === "Escape") { event.preventDefault(); finish(false); }
  });
  input.addEventListener("blur", () => finish(true));
  const glyph = kind === "folder" ? icon("folder") : fileGlyph(value || "x");
  return el("div", { class: "erow naming", style: `padding-left:${(kind === "folder" ? 8 : 22) + depth * 14}px` }, ...guides(depth),
    kind === "folder" ? el("span", { class: "chev" }) : "", glyph, input);
}

// Where "New file" goes: the folder itself, or the folder of a file.
function folderOf(entry) {
  if (entry.dir) return entry.path;
  return entry.path.slice(0, entry.path.lastIndexOf("/")) || "/";
}

function startNaming(kind, entry) {
  closeTreeMenu();
  if (!entry) {
    const root = edit.places && edit.places.roots.find((item) => item.exists);
    if (!root) { send({ op: "edit-add-folder" }); return; }
    entry = { path: root.path, dir: true };
  }
  if (kind === "rename") {
    if (entry.root) { showEditError("A project folder is renamed in Finder; here it can only leave the list (×)."); return; }
    if (isOpenAndChanged(entry.path)) { showEditError("Save the file first, then rename it."); return; }
    edit.naming = { kind, path: entry.path };
  } else {
    const dir = folderOf(entry);
    edit.naming = { kind, dir };
    if (!edit.open.has(dir)) { edit.open.add(dir); rememberOpen(); listFolder(dir); }
  }
  if (treeHidden()) toggleEditTree();
  drawTree();
}

function isOpenAndChanged(path) {
  return uleBuffers().some((item) => item.modified && (item.path === path || item.path.startsWith(path + "/")));
}

function trashEntry(entry) {
  closeTreeMenu();
  if (entry.root) { showEditError("A project folder is not deleted here; × takes it off the list."); return; }
  if (isOpenAndChanged(entry.path)) { showEditError("It has unsaved changes: save or close it first."); return; }
  const name = entry.path.split("/").pop();
  // WKWebView here has no confirm(): ask in the page.
  edit.confirm = { text: `Move “${name}” to the Trash?`, yes: "Move to Trash", run: () => send({ op: "edit-trash", path: entry.path }) };
  drawConfirm();
}

function drawConfirm() {
  $(".econfirm")?.remove();
  const ask = edit.confirm;
  if (!ask) return;
  const close = () => { edit.confirm = null; drawConfirm(); refocusEdit(); };
  const yes = el("button", { class: "primary", text: ask.yes, onclick: () => { const run = ask.run; close(); run(); } });
  const box = el("div", { class: "econfirm", role: "dialog" }, el("p", { text: ask.text }),
    el("div", { class: "row" }, el("button", { text: "Cancel", onclick: close }), yes));
  box.addEventListener("keydown", (event) => {
    event.stopPropagation();
    if (event.key === "Escape") close();
    if (event.key === "Enter") { event.preventDefault(); yes.click(); }
  });
  $(".ework")?.appendChild(box);
  yes.focus();
}

function refocusEdit() { if (edit.showing === "code") $(".uleinput")?.focus(); }

// A file or folder that moved or vanished: open editors follow it.
function followChange(message) {
  const { op, from, path } = message;
  const moved = op === "edit-rename" || op === "edit-move";
  for (const buffer of uleBuffers()) {
    if (!(buffer.path === from || buffer.path.startsWith(from + "/"))) continue;
    if (buffer.modified) continue;
    uleSend({ close: buffer.path });
    if (moved) uleSend({ open: { path: path + buffer.path.slice(from.length) } });
  }
  for (const viewer of [...edit.viewers]) {
    if (!(viewer.path === from || viewer.path.startsWith(from + "/"))) continue;
    if (moved) {
      const next = path + viewer.path.slice(from.length);
      if (edit.showing === viewer.path) edit.showing = next;
      viewer.path = next;
      viewer.name = next.split("/").pop();
      // Drawings are kept by path: they move with the file.
      if (viewer.pv && viewer.pv.ink && Object.keys(viewer.pv.ink.pages).length) send({ op: "edit-ink-save", path: next, ink: viewer.pv.ink });
    } else closeViewer(viewer.path);
  }
  if (edit.open.has(from)) { edit.open.delete(from); if (moved) edit.open.add(path); rememberOpen(); }
}

function dragSource(row, path) {
  row.addEventListener("dragstart", (event) => {
    edit.dragging = path;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", path);
  });
  row.addEventListener("dragend", () => { edit.dragging = null; for (const item of document.querySelectorAll(".erow.drop")) item.classList.remove("drop"); });
}

function dropTarget(row, dir) {
  const fits = () => edit.dragging && edit.dragging !== dir && !dir.startsWith(edit.dragging + "/")
    && edit.dragging.slice(0, edit.dragging.lastIndexOf("/")) !== dir;
  row.addEventListener("dragover", (event) => { if (!fits()) return; event.preventDefault(); row.classList.add("drop"); });
  row.addEventListener("dragleave", () => row.classList.remove("drop"));
  row.addEventListener("drop", (event) => {
    row.classList.remove("drop");
    if (!fits()) return;
    event.preventDefault();
    const path = edit.dragging;
    edit.dragging = null;
    if (isOpenAndChanged(path)) { showEditError("Save it first, then move it."); return; }
    send({ op: "edit-move", path, dir });
  });
}

function closeTreeMenu() { $(".emenu")?.remove(); }

function treeMenu(event, entry) {
  event.preventDefault();
  event.stopPropagation();
  closeTreeMenu();
  const item = (label, keys, run, danger) => el("button", { class: "emi" + (danger ? " danger" : ""), onclick: () => { closeTreeMenu(); run(); } },
    el("span", { text: label }), keys ? el("kbd", { text: keys }) : null);
  const line = () => el("hr");
  if (!entry) {
    // The empty part of the panel: what can be made or added, and the panel itself.
    const root = edit.places && edit.places.roots.find((place) => place.exists);
    const parts = [];
    if (root) {
      const rootEntry = { path: root.path, dir: true, root: true };
      parts.push(item(`New File in ${root.name}…`, "⌘N", () => startNaming("new-file", rootEntry)),
        item(`New Folder in ${root.name}…`, "⇧⌘N", () => startNaming("new-folder", rootEntry)), line());
    }
    parts.push(item("New File Somewhere…", "", () => send({ op: "edit-new-file-dialog" })),
      item("New Project Folder…", "", () => send({ op: "edit-new-project-dialog" })),
      item("Add a Folder or Open a File…", "", () => send({ op: "edit-pick-dialog" })), line());
    if (root) parts.push(item("Collapse All", "", () => { edit.open.clear(); rememberOpen(); drawTree(); }));
    parts.push(item("Open the Terminal", "⌃`", () => showTerminal(true)),
      item("Hide the Project Panel", "⌘B", toggleEditTree));
    openMenuAt(el("div", { class: "emenu", role: "menu" }, ...parts), event);
    return;
  }
  edit.selected = entry.path;
  const parts = [
    item("New File…", "⌘N", () => startNaming("new-file", entry)),
    item("New Folder…", "⇧⌘N", () => startNaming("new-folder", entry)),
    line(),
  ];
  if (!entry.dir) parts.push(item("Open", "↩", () => openFile(entry.path)));
  parts.push(
    item("Reveal in Finder", "⌥⌘R", () => send({ op: "edit-reveal", path: entry.path })),
    item("Open in Terminal", "", () => send({ op: "edit-terminal", path: entry.path })),
    line(),
    item("Copy Path", "⌥⌘C", () => send({ op: "edit-copy-path", path: entry.path })),
    item("Copy Relative Path", "⌥⇧⌘C", () => send({ op: "edit-copy-path", path: entry.path, relative: true })),
  );
  if (!entry.root) {
    parts.push(line(),
      item("Rename…", "F2", () => startNaming("rename", entry)),
      item("Duplicate", "⌘D", () => { closeTreeMenu(); send({ op: "edit-duplicate", path: entry.path }); }),
      item("Move to Trash", "⌘⌫", () => trashEntry(entry), true));
  } else {
    parts.push(line(), item("Collapse All", "", () => collapseUnder(entry.path)),
      item("Remove from Project", "", () => send({ op: "edit-remove-folder", path: entry.path })));
  }
  const menu = el("div", { class: "emenu", role: "menu" }, ...parts);
  ($(".edit") || document.body).appendChild(menu);
  const width = menu.offsetWidth, height = menu.offsetHeight;
  menu.style.left = Math.min(event.clientX, innerWidth - width - 6) + "px";
  menu.style.top = Math.min(event.clientY, innerHeight - height - 6) + "px";
  setTimeout(() => document.addEventListener("mousedown", function away(click) {
    if (!menu.contains(click.target)) { closeTreeMenu(); }
    document.removeEventListener("mousedown", away, true);
  }, true));
  drawTree();
}

function collapseUnder(path) {
  for (const open of [...edit.open]) if (open === path || open.startsWith(path + "/")) edit.open.delete(open);
  rememberOpen();
  drawTree();
}

// The selected row's entry, for the panel's keys.
function selectedEntry() {
  const path = edit.selected;
  if (!path || !edit.places) return null;
  const root = edit.places.roots.find((item) => item.path === path);
  if (root) return { path, dir: true, root: true };
  for (const listed of Object.values(edit.tree)) {
    const found = (listed.entries || []).find((item) => item.path === path);
    if (found) return found;
  }
  return null;
}

// Keys while the project panel has focus (Zed's project panel: arrows, Enter, F2, ⌘⌫…).
function treeKey(event) {
  if (edit.naming || event.target.closest("input")) return;
  const rows = [...document.querySelectorAll(".etree .erow[title]")];
  const paths = rows.map((row) => row.title);
  const at = paths.indexOf(edit.selected);
  const entry = selectedEntry();
  const meta = event.metaKey, alt = event.altKey, shift = event.shiftKey;
  let handled = true;
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    const next = paths[Math.max(0, Math.min(paths.length - 1, at + (event.key === "ArrowDown" ? 1 : -1)))];
    if (next) { edit.selected = next; drawTree(); $(".etree .erow.sel")?.scrollIntoView({ block: "nearest" }); }
  } else if (event.key === "ArrowRight" && entry && entry.dir) { if (!edit.open.has(entry.path)) toggleFolder(entry.path); }
  else if (event.key === "ArrowLeft" && entry) {
    if (entry.dir && edit.open.has(entry.path)) toggleFolder(entry.path);
    else { const parent = entry.path.slice(0, entry.path.lastIndexOf("/")); if (paths.includes(parent)) { edit.selected = parent; drawTree(); } }
  } else if (event.key === "Enter" && entry) { if (entry.dir) toggleFolder(entry.path); else openFile(entry.path); }
  else if (event.key === "F2" && entry) startNaming("rename", entry);
  else if (meta && event.key === "Backspace" && entry) trashEntry(entry);
  else if (meta && event.code === "KeyN") startNaming(shift ? "new-folder" : "new-file", entry);
  else if (meta && !shift && event.code === "KeyD" && entry && !entry.root) send({ op: "edit-duplicate", path: entry.path });
  else if (meta && alt && event.code === "KeyC" && entry) send({ op: "edit-copy-path", path: entry.path, relative: shift });
  else if (meta && alt && event.code === "KeyR" && entry) send({ op: "edit-reveal", path: entry.path });
  else handled = false;
  if (handled) { event.preventDefault(); event.stopPropagation(); }
}

// Zed's indent guides: one thin line per folder level.
function guides(depth) {
  const lines = [];
  for (let level = 1; level <= depth; level += 1) lines.push(el("i", { class: "guide", style: `left:${13 + (level - 1) * 14}px` }));
  return lines;
}

function fileIcon(name) {
  const suffix = (name.split(".").pop() || "").toLowerCase();
  if (/^(png|jpe?g|gif|webp|heic|heif|tiff?|bmp|svg)$/.test(suffix)) return "image";
  return "file";
}

// ---------- opening ----------

function openFile(path) {
  const viewer = edit.viewers.find((item) => item.path === path);
  if (viewer) { edit.showing = path; drawPane(); drawTree(); return; }
  const buffer = uleBuffers().find((item) => item.path === path);
  if (buffer) { uleSend({ show: path }); edit.showing = "code"; drawPane(); return; }
  send({ op: "edit-info", path });
}

function opened(path, info) {
  edit.info[path] = info;
  // filetypes.toml may say how this kind opens.
  const own = userType(info.name || path.split("/").pop());
  if (own && own.open === "app") { send({ op: "edit-open-app", path }); return; }
  if (own && own.open === "viewer") info = { ...info, text: false, kind: VIEWED.has(info.kind) ? info.kind : "other" };
  if (own && own.open === "editor") info = { ...info, text: true };
  if (info.text) {
    edit.showing = "code";
    uleSend({ open: { path } });
    drawPane();
    return;
  }
  const name = info.name || path.split("/").pop();
  const viewer = { path, name, info, picture: "", error: "" };
  edit.viewers.push(viewer);
  edit.showing = path;
  if (!VIEWED.has(info.kind) && !/\.svg$/i.test(name)) send({ op: "edit-render", path, width: 1600 });
  drawPane();
  drawTree();
}

function closeViewer(path) {
  const closing = edit.viewers.find((item) => item.path === path);
  // Drawings waiting for their save go now.
  if (closing && closing.pv && closing.pv.saveTimer) { clearTimeout(closing.pv.saveTimer); send({ op: "edit-ink-save", path, ink: closing.pv.ink }); }
  edit.viewers = edit.viewers.filter((item) => item.path !== path);
  if (edit.showing === path) edit.showing = edit.viewers.length ? edit.viewers[edit.viewers.length - 1].path : (uleBuffers().length ? "code" : null);
  drawPane();
  drawTree();
}

// ⌘W: the shown tab closes; false when there is none (then ⌘W closes the window).
function closeEditTab() {
  if (edit.showing && edit.showing !== "code" && edit.viewers.some((item) => item.path === edit.showing)) {
    closeViewer(edit.showing);
    return true;
  }
  const active = uleBuffers().find((item) => item.active && item.path);
  if (edit.showing === "code" && active) { uleSend({ close: active.path }); return true; }
  return false;
}

function currentPath() {
  if (edit.showing === "code") return (uleBuffers().find((item) => item.active) || {}).path || null;
  return edit.showing;
}

// ---------- the right side ----------

function drawPane() {
  drawTabs();
  drawError();
  const body = $(".ebody");
  if (!body) return;
  if (edit.showing === "code") { showCode(body); return; }
  hideCode();
  const viewer = edit.viewers.find((item) => item.path === edit.showing);
  if (!viewer) {
    body.replaceChildren(el("div", { class: "eempty" },
      icon("pencil"),
      el("h2", { text: "Open something to edit" }),
      el("p", { class: "muted", text: "Code and text open in ule, Unlaw's editor (the same as `ule` in a terminal, with your ule.toml). Pictures, PDF, sound and video open in a viewer." }),
      el("div", { class: "keys" },
        el("kbd", { text: "⌘P" }), el("span", { text: "Find a file" }),
        el("kbd", { text: "⌘⇧P" }), el("span", { text: "All commands" }),
        el("kbd", { text: "⌘⇧F" }), el("span", { text: "Search the project" }),
        el("kbd", { text: "⌘B" }), el("span", { text: "Project panel" })),
      el("div", { class: "buttons" },
        el("button", { class: "primary", text: "Open a file…", onclick: () => send({ op: "edit-open-dialog" }) }),
        el("button", { text: "Add a folder…", onclick: () => send({ op: "edit-add-folder" }) }))));
    drawStatus(null);
    return;
  }
  body.replaceChildren(viewerNode(viewer));
  drawStatus(viewer.info);
}

function drawTabs() {
  const tabs = $(".etabs");
  if (!tabs) return;
  const items = [];
  for (const buffer of uleBuffers()) {
    if (!buffer.path) continue;
    const on = edit.showing === "code" && buffer.active;
    items.push(el("div", { class: "etab" + (on ? " on" : ""), title: buffer.path, onclick: () => { edit.showing = "code"; uleSend({ show: buffer.path }); drawPane(); } },
      el("span", { class: "name", text: buffer.name }),
      buffer.modified ? el("i", { class: "dot", title: "Not saved" }) : null,
      el("button", { class: "ghost x", title: buffer.modified ? "Save first (⌘S), or close it in the editor with :bd!" : "Close", text: "×", onclick: (event) => {
        event.stopPropagation(); uleSend({ close: buffer.path });
      } })));
  }
  for (const viewer of edit.viewers) {
    items.push(el("div", { class: "etab" + (edit.showing === viewer.path ? " on" : ""), title: viewer.path, onclick: () => { edit.showing = viewer.path; drawPane(); drawTree(); } },
      el("span", { class: "name", text: viewer.name }),
      el("button", { class: "ghost x", title: "Close", text: "×", onclick: (event) => { event.stopPropagation(); closeViewer(viewer.path); } })));
  }
  tabs.replaceChildren(...items);
  tabs.hidden = !items.length;
}

function size(bytes) {
  if (bytes == null) return "";
  const units = ["bytes", "KB", "MB", "GB"];
  let value = bytes, unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return (unit ? value.toFixed(value < 10 ? 1 : 0) : value) + " " + units[unit];
}

// Zed's status bar: what the open file is on the left, the key mode and theme on the right.
function drawStatus(info) {
  const status = $(".estatus");
  if (!status) return;
  const places = edit.places || {};
  const editing = editingMode();
  const themes = places.themes || [];
  const chosen = places.theme || (edit.ule.frame && edit.ule.frame.theme && edit.ule.frame.theme.name) || "unlaw";
  const theme = el("select", { class: "etheme", title: "Editor theme (Edit and the terminal ule)" },
    ...(themes.length ? themes : [chosen]).map((name) => el("option", { value: name, text: name, selected: name === chosen ? "" : null })));
  theme.addEventListener("change", () => setEditPrefs({ theme: theme.value }));
  const left = info ? [el("span", { text: info.kind }), el("span", { text: size(info.size) }), el("span", { class: "path", title: info.path, text: "\u200e" + info.path + "\u200e" })] : [];
  status.replaceChildren(
    el("button", { class: "ghost icon", title: "Project panel (⌘B)", "aria-label": "Project panel", onclick: toggleEditTree }, icon("sidebar")),
    ...left,
    el("div", { class: "grow" }),
    el("button", { class: "ghost icon", title: "Terminal (⌃`)", "aria-label": "Terminal", onclick: () => showTerminal(!term.open) }, icon("terminal")),
    el("button", { class: "ghost keysbtn", title: "Keyboard shortcuts (⌘K ⌘S)", text: "Keys", onclick: toggleKeys }),
    keyModeSwitch(editing),
    theme);
}

function rawUrl(path) { return "ulapp://localhost/edit/raw?path=" + encodeURIComponent(path); }

function viewerNode(viewer) {
  const { info, path } = viewer;
  // PDF and pictures: pages with thumbnails and drawing (pdf.js); "Text view" = WebKit's own.
  if (info.kind === "pdf" && viewer.pv && viewer.pv.native) {
    return el("div", { class: "viewer" }, el("div", { class: "vtools" },
      el("button", { text: "Pages and drawing", onclick: () => { viewer.pv.native = false; drawPane(); } }),
      el("button", { class: "ghost", text: "Open in its app", onclick: () => send({ op: "edit-open-app", path }) })),
    el("div", { class: "vstage" }, el("iframe", { class: "pdf", src: rawUrl(path), title: viewer.name })));
  }
  if (info.kind === "pdf" || info.kind === "image" || /\.svg$/i.test(viewer.name)) return pvNode(viewer);
  const tools = el("div", { class: "vtools" },
    el("button", { text: "Open in its app", onclick: () => send({ op: "edit-open-app", path }) }),
    el("button", { class: "ghost", text: "Show in Finder", onclick: () => send({ op: "edit-reveal", path }) }));
  let shown;
  if (info.kind === "image" || /\.svg$/i.test(viewer.name)) {
    const image = el("img", { class: "fit", alt: viewer.name, src: rawUrl(path) });
    image.addEventListener("click", () => image.classList.toggle("fit"));
    image.addEventListener("error", () => { if (!viewer.picture) send({ op: "edit-render", path, width: 1600 }); });
    shown = viewer.picture ? el("img", { class: "fit", alt: viewer.name, src: viewer.picture }) : image;
  } else if (info.kind === "pdf") {
    shown = el("iframe", { class: "pdf", src: rawUrl(path), title: viewer.name });
  } else if (info.kind === "media") {
    const audio = /\.(mp3|m4a|wav|flac|aac)$/i.test(viewer.name);
    shown = el(audio ? "audio" : "video", { controls: "", src: rawUrl(path) });
  } else if (viewer.error) {
    shown = el("div", { class: "note", text: viewer.error });
  } else if (viewer.picture) {
    shown = el("img", { class: "fit preview", alt: viewer.name, src: viewer.picture });
  } else {
    shown = el("div", { class: "note", text: "Drawing a preview…" });
  }
  return el("div", { class: "viewer" }, tools, el("div", { class: "vstage" }, shown));
}

// ---------- the code editor (ule) ----------

function uleBuffers() { return (edit.ule.frame && edit.ule.frame.buffers) || []; }

function uleSend(event) {
  if (!edit.ule.id) {
    edit.ule.queue.push(event);
    startUle();
    return;
  }
  edit.ule.queue.push(event);
  if (edit.ule.queue.length === 1) queueMicrotask(flushUle);
}

function flushUle() {
  if (!edit.ule.id || !edit.ule.queue.length) return;
  const events = edit.ule.queue.splice(0, 256);
  send({ op: "ule-input", id: edit.ule.id, events });
  if (edit.ule.queue.length) queueMicrotask(flushUle);
}

function cellSize() {
  if (edit.ule.cell) return edit.ule.cell;
  const context = document.createElement("canvas").getContext("2d");
  context.font = `${EDIT_FONT}px ${EDIT_MONO}`;
  edit.ule.cell = { w: context.measureText("M").width, h: Math.round(EDIT_FONT * 1.45) };
  return edit.ule.cell;
}

function gridSize() {
  const body = $(".ebody");
  const cell = cellSize();
  const width = body ? body.clientWidth : 900, height = body ? body.clientHeight : 600;
  return { rows: Math.max(5, Math.min(400, Math.floor(height / cell.h))), cols: Math.max(20, Math.min(800, Math.floor(width / cell.w))) };
}

function startUle() {
  if (edit.ule.starting || edit.ule.id) return;
  edit.ule.starting = true;
  edit.ule.ended = "";
  const { rows, cols } = gridSize();
  send({ op: "ule-start", rows, cols, theme: isDark() ? "dark" : "light" });
}

let codeNodes = null;

function codeNodesMake() {
  const canvas = el("canvas", { class: "ule" });
  const input = el("textarea", { class: "uleinput", autocapitalize: "off", autocomplete: "off", spellcheck: "false", "aria-label": "Editor" });
  input.addEventListener("keydown", uleKey);
  input.addEventListener("paste", (event) => {
    event.preventDefault();
    const text = event.clipboardData && event.clipboardData.getData("text/plain");
    if (text) uleSend({ paste: text });
  });
  // Composed text (accents, other input methods) arrives here, not as keys.
  input.addEventListener("input", () => {
    const text = input.value;
    input.value = "";
    for (const char of text) uleSend({ key: { code: char } });
  });
  input.addEventListener("focus", () => uleSend({ focus: true }));
  input.addEventListener("blur", () => { if (edit.ule.id) uleSend({ focus: false }); });
  let dragging = false;
  canvas.addEventListener("mousedown", (event) => {
    event.preventDefault();
    input.focus();
    const at = uleCell(event);
    // ⌥-click adds another cursor, as in Zed.
    if (at && event.button === 0) { dragging = !event.altKey; uleSend({ mouse: { kind: "down", alt: event.altKey, ...at } }); }
  });
  canvas.addEventListener("mousemove", (event) => {
    if (!dragging || !(event.buttons & 1)) return;
    const at = uleCell(event);
    if (at) uleSend({ mouse: { kind: "drag", ...at } });
  });
  window.addEventListener("mouseup", (event) => {
    if (!dragging) return;
    dragging = false;
    const at = uleCell(event) || { x: 0, y: 0 };
    uleSend({ mouse: { kind: "up", ...at } });
  });
  let wheel = 0;
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    wheel += event.deltaY;
    const at = uleCell(event) || { x: 0, y: 0 };
    while (Math.abs(wheel) >= 40) {
      uleSend({ mouse: { kind: wheel > 0 ? "scroll_down" : "scroll_up", ...at } });
      wheel -= Math.sign(wheel) * 40;
    }
  }, { passive: false });
  return { canvas, input };
}

function showCode(body) {
  codeNodes = codeNodes || codeNodesMake();
  if (codeNodes.canvas.parentNode !== body) body.replaceChildren(codeNodes.canvas, codeNodes.input);
  if (edit.ule.ended && !edit.ule.id) {
    body.replaceChildren(el("div", { class: "eempty" }, el("h2", { text: "The editor stopped" }),
      el("p", { class: "muted", text: edit.ule.ended }),
      el("button", { class: "primary", text: "Start it again", onclick: () => { edit.ule.ended = ""; startUle(); drawPane(); } })));
    drawStatus(null);
    return;
  }
  if (!edit.ule.id) startUle();
  requestAnimationFrame(() => { codeNodes && codeNodes.input.focus(); resizeUle(); drawUle(); });
  const path = currentPath();
  drawStatus(path ? edit.info[path] || { kind: "text", path } : null);
}

function hideCode() {
  if (codeNodes && codeNodes.input === document.activeElement) codeNodes.input.blur();
}

function uleCell(event) {
  const frame = edit.ule.frame;
  if (!frame || !codeNodes) return null;
  const rect = codeNodes.canvas.getBoundingClientRect();
  const cell = cellSize();
  const x = Math.floor((event.clientX - rect.left) / cell.w), y = Math.floor((event.clientY - rect.top) / cell.h);
  if (x < 0 || y < 0) return null;
  return { x: Math.min(x, frame.cols - 1), y: Math.min(y, frame.rows - 1) };
}

// Zed's macOS key bindings, written as "mods+code" (mods in the order ctrl, alt, shift,
// cmd) -> what ule gets: a command name, or a key (`{key}`). `standard: true` entries
// are only for the standard key mode: in vim these Ctrl keys stay vim's own.
const ZED_KEYS = [
  // moving and selecting
  ["cmd+ArrowLeft", { key: { code: "Home" } }, "Line start"],
  ["cmd+ArrowRight", { key: { code: "End" } }, "Line end"],
  ["cmd+ArrowUp", { key: { code: "Home", ctrl: true } }, "File start"],
  ["cmd+ArrowDown", { key: { code: "End", ctrl: true } }, "File end"],
  ["shift+cmd+ArrowLeft", { key: { code: "Home", shift: true } }, "Select to line start"],
  ["shift+cmd+ArrowRight", { key: { code: "End", shift: true } }, "Select to line end"],
  ["shift+cmd+ArrowUp", { key: { code: "Home", ctrl: true, shift: true } }, "Select to file start"],
  ["shift+cmd+ArrowDown", { key: { code: "End", ctrl: true, shift: true } }, "Select to file end"],
  ["alt+ArrowLeft", { key: { code: "Left", alt: true } }, "Word left"],
  ["alt+ArrowRight", { key: { code: "Right", alt: true } }, "Word right"],
  ["alt+shift+ArrowLeft", { key: { code: "Left", alt: true, shift: true } }, "Select word left"],
  ["alt+shift+ArrowRight", { key: { code: "Right", alt: true, shift: true } }, "Select word right"],
  ["cmd+KeyA", "select_all", "Select all"],
  ["cmd+KeyL", "select_line", "Select line (again: one more)"],
  ["ctrl+shift+ArrowRight", "expand_selection", "Expand selection"],
  ["ctrl+shift+ArrowLeft", "shrink_selection", "Shrink selection"],
  // several cursors
  ["cmd+KeyD", "select_next_occurrence", "Select next occurrence (another cursor)"],
  ["shift+cmd+KeyL", "select_all_occurrences", "Select all occurrences"],
  ["alt+cmd+ArrowUp", "add_cursor_above", "Add cursor above"],
  ["alt+cmd+ArrowDown", "add_cursor_below", "Add cursor below"],
  // editing
  ["cmd+Backspace", { key: { code: "u", ctrl: true } }, "Delete to line start"],
  ["cmd+Delete", { key: { code: "k", ctrl: true } }, "Delete to line end"],
  ["alt+Backspace", { key: { code: "Backspace", alt: true } }, "Delete word left"],
  ["alt+Delete", { key: { code: "Delete", alt: true } }, "Delete word right"],
  ["shift+cmd+KeyK", { key: { code: "k", ctrl: true, shift: true } }, "Delete line"],
  ["cmd+Enter", "newline_below", "New line below"],
  ["shift+cmd+Enter", "newline_above", "New line above"],
  ["cmd+BracketRight", "indent", "Indent"],
  ["cmd+BracketLeft", "outdent", "Outdent"],
  ["alt+ArrowUp", { key: { code: "Up", alt: true } }, "Move line up"],
  ["alt+ArrowDown", { key: { code: "Down", alt: true } }, "Move line down"],
  ["alt+shift+ArrowUp", { key: { code: "Up", alt: true, shift: true } }, "Duplicate line up"],
  ["alt+shift+ArrowDown", { key: { code: "Down", alt: true, shift: true } }, "Duplicate line down"],
  ["shift+cmd+KeyD", { key: { code: "Down", alt: true, shift: true } }, "Duplicate selection"],
  ["cmd+Slash", { key: { code: "/", ctrl: true } }, "Toggle comment"],
  ["cmd+KeyZ", { key: { code: "z", ctrl: true } }, "Undo"],
  ["shift+cmd+KeyZ", { key: { code: "y", ctrl: true } }, "Redo"],
  ["cmd+KeyC", { key: { code: "c", ctrl: true } }, "Copy (no selection: the line)"],
  ["cmd+KeyX", { key: { code: "x", ctrl: true } }, "Cut (no selection: the line)"],
  ["cmd+KeyK cmd+KeyU", "uppercase", "Upper case"],
  ["cmd+KeyK cmd+KeyL", "lowercase", "Lower case"],
  ["ctrl+KeyT", "transpose", "Transpose characters", true],
  ["ctrl+KeyJ", "join_lines", "Join lines", true],
  ["ctrl+KeyA", { key: { code: "Home" } }, "Line start", true],
  ["ctrl+KeyE", { key: { code: "End" } }, "Line end", true],
  ["ctrl+KeyF", { key: { code: "Right" } }, "Character right", true],
  ["ctrl+KeyB", { key: { code: "Left" } }, "Character left", true],
  ["ctrl+KeyN", { key: { code: "Down" } }, "Line down", true],
  ["ctrl+KeyP", { key: { code: "Up" } }, "Line up", true],
  ["ctrl+KeyD", { key: { code: "Delete" } }, "Delete right", true],
  ["ctrl+KeyH", { key: { code: "Backspace" } }, "Delete left", true],
  ["ctrl+KeyK", { key: { code: "k", ctrl: true } }, "Cut to line end", true],
  ["ctrl+Space", "complete", "Show completions", true],
  // finding
  ["cmd+KeyF", { key: { code: "f", ctrl: true } }, "Find"],
  ["cmd+KeyG", "search_next", "Next match"],
  ["shift+cmd+KeyG", "search_prev", "Previous match"],
  ["cmd+KeyE", "search_selection", "Find the selection"],
  ["alt+cmd+KeyF", "replace", "Replace"],
  ["ctrl+KeyG", { key: { code: "g", ctrl: true } }, "Go to line", true],
  // project and code
  ["cmd+KeyP", "file_picker", "Find a file"],
  ["shift+cmd+KeyP", "command_palette", "All commands"],
  ["shift+cmd+KeyF", "grep", "Search the project"],
  ["shift+cmd+KeyO", "symbols", "Symbols in this file"],
  ["cmd+KeyT", "workspace_symbols", "Symbols in the project"],
  ["shift+cmd+KeyM", "diagnostics", "Problems"],
  ["F8", "diagnostic_next", "Next problem"],
  ["shift+F8", "diagnostic_prev", "Previous problem"],
  ["F12", "goto_definition", "Go to definition"],
  ["shift+F12", "references", "Find references"],
  ["alt+F12", "hover", "Show the docs at the cursor"],
  ["F2", "rename", "Rename symbol"],
  ["cmd+Period", "code_action", "Code actions"],
  ["ctrl+Minus", "jump_back", "Go back", true],
  ["ctrl+shift+Minus", "jump_forward", "Go forward", true],
  // files and panes
  ["cmd+KeyS", "save", "Save"],
  ["alt+cmd+KeyS", "save_all", "Save all"],
  ["cmd+KeyN", "new_file", "New file"],
  ["shift+cmd+BracketRight", "buffer_next", "Next tab"],
  ["shift+cmd+BracketLeft", "buffer_prev", "Previous tab"],
  ["ctrl+Tab", "buffer_next", "Next tab"],
  ["ctrl+shift+Tab", "buffer_prev", "Previous tab"],
  ["cmd+Backslash", "vsplit", "Split right"],
  ["cmd+KeyJ", "panel", "Output panel"],
  ["shift+cmd+KeyE", "recent_files", "Recent files"],
  ["cmd+KeyK cmd+KeyS", { page: "keys" }, "This list of keys"],
  ["alt+click", { page: "none" }, "Add a cursor where you click"],
];
const ZED_TABLE = new Map(ZED_KEYS.map(([keys, action, label, standard]) => [keys, { action, label, standard: !!standard }]));
const ZED_CHORDS = new Set(ZED_KEYS.filter(([keys]) => keys.includes(" ")).map(([keys]) => keys.split(" ")[0]));

const KEY_GLYPHS = { ctrl: "⌃", alt: "⌥", shift: "⇧", cmd: "⌘", ArrowLeft: "←", ArrowRight: "→", ArrowUp: "↑",
  ArrowDown: "↓", Backspace: "⌫", Delete: "⌦", Enter: "↩", Tab: "⇥", Space: "Space", BracketLeft: "[", BracketRight: "]",
  Slash: "/", Backslash: "\\", Period: ".", Minus: "-", click: "click" };

// "shift+cmd+KeyL cmd+KeyU" -> "⇧⌘L ⌘U".
function prettyKeys(keys) {
  return keys.split(" ").map((part) => part.split("+").map((piece) =>
    KEY_GLYPHS[piece] || piece.replace(/^Key/, "").replace(/^Digit/, "")).join("")).join(" ");
}

// The Zed keys as a list beside the editor (Keys button, ⌘K ⌘S).
function toggleKeys() {
  edit.keysOpen = !edit.keysOpen;
  drawKeys();
}

function drawKeys() {
  const work = $(".ework");
  if (!work) return;
  let panel = $(".ekeys");
  if (!edit.keysOpen) { if (panel) panel.remove(); return; }
  const editing = editingMode();
  const filter = el("input", { class: "efilter", placeholder: "Filter keys…", value: edit.keysFilter || "" });
  const list = el("div", { class: "elist" });
  const fill = () => {
    const words = filter.value.toLowerCase().split(/\s+/).filter(Boolean);
    edit.keysFilter = filter.value;
    list.replaceChildren(...ZED_KEYS.filter(([keys, , label]) => {
      const text = (label + " " + prettyKeys(keys)).toLowerCase();
      return words.every((word) => text.includes(word));
    }).map(([keys, , label, standard]) => el("div", { class: "ekey" + (standard && editing !== "standard" ? " off" : ""),
      title: standard && editing !== "standard" ? "Only with Standard keys (vim keeps its own Ctrl keys)" : "" },
      el("span", { text: label }), el("kbd", { text: prettyKeys(keys) }))));
  };
  filter.addEventListener("input", fill);
  filter.addEventListener("keydown", (event) => { if (event.key === "Escape") { edit.keysOpen = false; drawKeys(); } });
  const head = el("div", { class: "ekeyshead" }, el("b", { text: "Keys" }), el("span", { class: "muted", text: editing === "vim" ? "Vim mode" : "Standard mode" }),
    el("div", { class: "grow" }), el("button", { class: "ghost x", text: "×", title: "Close (Esc)", onclick: toggleKeys }));
  const next = el("aside", { class: "ekeys" }, head, filter, list);
  if (panel) panel.replaceWith(next); else work.appendChild(next);
  fill();
}

function keyName(event) {
  const mods = [event.ctrlKey && "ctrl", event.altKey && "alt", event.shiftKey && "shift", event.metaKey && "cmd"].filter(Boolean);
  const code = event.code === "NumpadEnter" ? "Enter" : event.code;
  return [...mods, code].join("+");
}

// A Zed binding for this key (or the second key of a ⌘K chord): true when it was used.
function zedKey(event) {
  const name = keyName(event);
  const editing = editingMode();
  if (edit.chord) {
    const first = edit.chord;
    edit.chord = null;
    const found = ZED_TABLE.get(first + " " + name);
    if (found) { runZed(found.action); return true; }
  }
  if (ZED_CHORDS.has(name)) { edit.chord = name; return true; }
  const found = ZED_TABLE.get(name);
  if (!found || (found.standard && editing !== "standard")) return false;
  runZed(found.action);
  return true;
}

function runZed(action) {
  if (action.page === "keys") { toggleKeys(); return; }
  if (action.page) return;
  if (typeof action === "string") uleSend({ command: action });
  else uleSend({ key: { ctrl: false, alt: false, shift: false, ...action.key } });
}

function uleKey(event) {
  if (event.isComposing || event.key === "Dead" || event.key === "Process") return;
  let key = null;
  if (zedKey(event)) {
    event.preventDefault();
    event.stopPropagation();
    return;
  }
  if (event.metaKey && !event.shiftKey && !event.altKey && !event.ctrlKey && event.code === "KeyW") {
    // ⌘W closes the tab, as in Zed; with no tab left the window's menu closes the window.
    if (!closeEditTab()) return;
    event.preventDefault();
    event.stopPropagation();
    return;
  }
  if (event.metaKey) {
    // ⌘V goes through the paste event; other ⌘ keys are the window's (parts, settings).
    const letter = EDIT_COMMAND_KEYS[event.code];
    if (!letter || event.altKey || event.ctrlKey) return;
    key = letter === "z" && event.shiftKey ? { code: "y", ctrl: true } : { code: letter, ctrl: true };
  } else if (EDIT_KEYS[event.key]) {
    const code = event.key === "Tab" && event.shiftKey ? "BackTab" : EDIT_KEYS[event.key];
    key = { code, ctrl: event.ctrlKey, alt: event.altKey, shift: event.shiftKey && code !== "BackTab" };
  } else if (/^F([1-9]|1[0-9]|2[0-4])$/.test(event.key)) {
    key = { code: event.key, ctrl: event.ctrlKey, alt: event.altKey, shift: event.shiftKey };
  } else if (event.ctrlKey) {
    // Ctrl combinations by the key's place, so they work in any keyboard layout.
    const named = /^Key([A-Z])$/.exec(event.code);
    const other = { Slash: "/", BracketLeft: "[", BracketRight: "]", Space: " ", Backslash: "\\", Minus: "-", Equal: "=" }[event.code];
    const code = named ? named[1].toLowerCase() : other || (/^Digit(\d)$/.exec(event.code) || [])[1];
    if (!code) return;
    key = { code, ctrl: true, alt: event.altKey, shift: event.shiftKey };
  } else if ([...event.key].length === 1) {
    // Option keeps typing its characters, as in a Mac terminal.
    key = { code: commandChar(event) };
  }
  if (!key) return;
  event.preventDefault();
  event.stopPropagation();
  uleSend({ key });
}

let uleResizeTimer = 0;
function resizeUle() {
  if (!edit.ule.id || edit.showing !== "code") return;
  const { rows, cols } = gridSize();
  const frame = edit.ule.frame;
  if (frame && frame.rows === rows && frame.cols === cols) return;
  uleSend({ resize: { rows, cols } });
}

function uleColor(name, fallback) {
  if (!name) return fallback;
  if (name[0] === "#") return name;
  const index = Number(name.slice(1));
  if (index < 16) return EDIT_ANSI[isDark() ? "dark" : "light"][index];
  if (index < 232) {
    const value = index - 16, level = (step) => (step ? 55 + step * 40 : 0);
    return `rgb(${level(Math.floor(value / 36))},${level(Math.floor(value / 6) % 6)},${level(value % 6)})`;
  }
  const gray = 8 + (index - 232) * 10;
  return `rgb(${gray},${gray},${gray})`;
}

let uleDrawPending = false;
function scheduleUleDraw() {
  if (uleDrawPending) return;
  uleDrawPending = true;
  requestAnimationFrame(() => { uleDrawPending = false; drawUle(); });
}

function drawUle() {
  const frame = edit.ule.frame;
  if (!codeNodes || edit.showing !== "code" || !codeNodes.canvas.isConnected) return;
  const canvas = codeNodes.canvas;
  const cell = cellSize();
  const ratio = devicePixelRatio || 1;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  const style = getComputedStyle(canvas);
  // The theme's own background, or (a theme of terminal colors) the window's glass.
  const baseBg = style.getPropertyValue("--code-bg").trim() || style.getPropertyValue("--page").trim() || (isDark() ? "#18181a" : "#ffffff");
  const baseFg = style.getPropertyValue("--code-fg").trim() || style.getPropertyValue("--text").trim() || (isDark() ? "#f2f2f4" : "#1d1d1f");
  context.clearRect(0, 0, width, height);
  context.fillStyle = baseBg;
  context.fillRect(0, 0, width, height);
  if (!frame) return;
  context.textBaseline = "middle";
  frame.lines.forEach((runs, row) => {
    const y = row * cell.h;
    runs.forEach((run, index) => {
      const [x, text, fgName, bgName, flags] = run;
      const next = index + 1 < runs.length ? runs[index + 1][0] : frame.cols;
      let fg = uleColor(fgName, baseFg), bg = uleColor(bgName, null);
      if (flags & 2) { const swap = fg; fg = bg || baseBg; bg = swap; }
      if (bg) {
        const left = Math.round(x * cell.w);
        context.fillStyle = bg;
        context.fillRect(left, Math.round(y), Math.round(next * cell.w) - left, Math.round(y + cell.h) - Math.round(y));
      }
      context.font = `${flags & 8 ? "italic " : ""}${flags & 1 ? "700" : "400"} ${EDIT_FONT}px ${EDIT_MONO}`;
      context.globalAlpha = flags & 4 ? 0.6 : 1;
      context.fillStyle = fg;
      let column = x;
      for (const char of text) {
        if (char !== " ") {
          if (BOX[char] || QUADRANTS[char] || "█▓▒░▀▄".includes(char)) drawCell(context, char, column * cell.w, y, cell.w, cell.h, fg);
          else context.fillText(char, column * cell.w, y + cell.h / 2 + 0.5);
        }
        column += 1;
      }
      if (flags & (16 | 32 | 64)) {
        context.strokeStyle = fg;
        context.lineWidth = 1;
        context.beginPath();
        const from = x * cell.w, to = column * cell.w;
        if (flags & 16) { context.moveTo(from, y + cell.h - 1.5); context.lineTo(to, y + cell.h - 1.5); }
        if (flags & 32) {
          for (let at = from; at < to; at += 4) context.lineTo(at, y + cell.h - (Math.floor(at / 4) % 2 ? 1 : 3));
        }
        if (flags & 64) { context.moveTo(from, y + cell.h / 2); context.lineTo(to, y + cell.h / 2); }
        context.stroke();
      }
      context.globalAlpha = 1;
    });
  });
  const cursor = frame.cursor;
  if (cursor && document.activeElement === codeNodes.input) {
    const [row, column, bar] = cursor;
    context.fillStyle = (edit.ule.frame.theme && uleColor(edit.ule.frame.theme.accent, null)) || (isDark() ? "#e9ae45" : "#9c5f00");
    if (bar) context.fillRect(Math.round(column * cell.w), row * cell.h + 1, 2, cell.h - 2);
    else {
      context.globalAlpha = 0.45;
      context.fillRect(Math.round(column * cell.w), row * cell.h, Math.ceil(cell.w), cell.h);
      context.globalAlpha = 1;
    }
  }
}

window.addEventListener("resize", () => {
  if (home.section !== "edit") return;
  clearTimeout(uleResizeTimer);
  uleResizeTimer = setTimeout(() => { resizeUle(); scheduleUleDraw(); }, 80);
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  setTimeout(() => { if (edit.ule.id) uleSend({ theme: isDark() ? "dark" : "light" }); scheduleUleDraw(); }, 50);
});

// ---------- messages from Rust ----------

function editReceive(message) {
  if (["edit-pages", "edit-ink", "edit-render"].includes(message.type) && pvReceive(message)) return true;
  if (message.type.startsWith("term-")) return termReceive(message);
  switch (message.type) {
    case "edit-places":
      edit.places = message;
      // A page loaded again while the editor kept running (unsaved files): take it back.
      if (message.running && !edit.ule.id) startUle();
      projectFolder();
      for (const root of message.roots) if (edit.open.has(root.path) && !edit.tree[root.path]) listFolder(root.path);
      if (home.section === "edit") { drawTree(); drawStatus(edit.info[currentPath()] || null); }
      if (home.section === "settings") renderSettings();
      return true;
    case "edit-list":
      edit.tree[message.list.path] = { entries: message.list.entries, truncated: message.list.truncated, loading: false };
      // Folders left open last time are listed again as their parent arrives.
      for (const entry of message.list.entries) if (entry.dir && edit.open.has(entry.path) && !edit.tree[entry.path]) listFolder(entry.path);
      if (home.section === "edit") drawTree();
      return true;
    case "edit-expand":
      edit.open.add(message.path);
      rememberOpen();
      listFolder(message.path);
      return true;
    case "edit-open":
      if (home.section !== "edit") go("edit");
      openFile(message.path);
      return true;
    case "edit-info":
      if (message.error) showEditError(`${message.path.split("/").pop()}: ${message.error}`);
      else opened(message.path, message.result);
      return true;
    case "edit-render": {
      const viewer = edit.viewers.find((item) => item.path === message.path);
      if (!viewer) return true;
      if (message.error) viewer.error = `No preview: ${message.error}`;
      else viewer.picture = "ulapp://localhost/edit/cache/" + message.result.png.split("/").pop();
      if (edit.showing === viewer.path) drawPane();
      return true;
    }
    case "edit-error":
      showEditError(message.text);
      return true;
    case "edit-note":
      showEditNote(message.text);
      return true;
    case "edit-changed":
      if (message.op !== "edit-new" && message.op !== "edit-duplicate") followChange(message);
      for (const dir of message.dirs) if (edit.tree[dir]) listFolder(dir);
      if (message.op !== "edit-trash") edit.selected = message.path;
      if (message.op === "edit-new" && !message.dir) openFile(message.path);
      if (message.op === "edit-new" && message.dir) { edit.open.add(message.path); rememberOpen(); listFolder(message.path); }
      if (home.section === "edit") drawTree();
      return true;
    case "ule-started":
      edit.ule.id = message.id;
      edit.ule.starting = false;
      edit.ule.cwd = "";
      projectFolder();
      if (edit.ule.queue.length) flushUle();
      resizeUle();
      return true;
    case "ule-frame":
      if (message.id !== edit.ule.id) return true;
      {
        const before = JSON.stringify(uleBuffers());
        const look = edit.ule.frame && JSON.stringify([edit.ule.frame.theme, edit.ule.frame.editing]);
        edit.ule.frame = message.frame;
        // The editor's theme changed (picked, or its file saved): every window follows.
        if (look && JSON.stringify(JSON.parse(look)[0]) !== JSON.stringify(message.frame.theme)) send({ op: "edit-colors" });
        if (home.section === "edit" && look !== JSON.stringify([message.frame.theme, message.frame.editing])) {
          applyEditTheme();
          drawStatus(edit.info[currentPath()] || null);
        }
        if (JSON.stringify(uleBuffers()) !== before && home.section === "edit") { drawTabs(); drawTree(); }
        // Every file closed in the editor (not its first frames, before a file opened).
        const files = uleBuffers().some((item) => item.path);
        if (files) edit.ule.hadFiles = true;
        else if (edit.ule.hadFiles && edit.showing === "code") {
          edit.ule.hadFiles = false;
          edit.showing = edit.viewers.length ? edit.viewers[edit.viewers.length - 1].path : null;
          drawPane();
        }
      }
      scheduleUleDraw();
      return true;
    case "ule-ended":
      if (message.id !== edit.ule.id && edit.ule.id) return true;
      edit.ule.id = 0;
      edit.ule.starting = false;
      edit.ule.frame = null;
      edit.ule.hadFiles = false;
      edit.ule.queue = [];
      edit.ule.ended = message.error || "";
      if (home.section === "edit") drawPane();
      return true;
  }
  return false;
}

// ---------- terminal (a dock panel, several sessions as tabs) ----------
// Command lines run one at a time per session on a pseudo-terminal in Rust (`term-*` ops,
// each with its `session`); this side draws their output: colors (SGR), carriage
// returns, erase-line and cursor steps within a line. Full-screen programs (vim, top)
// are not drawn: those belong in a real terminal.
const TERM_MAX_LINES = 5000;
const term = { open: stored("edit-term-open", "0") === "1", sessions: [], active: 0, nextSid: 1, node: null, drawQueued: false };

function termSession(sid) { return term.sessions.find((session) => session.sid === sid) || null; }
function termActive() { return termSession(term.active); }

function termNew() {
  const session = { sid: term.nextSid++, lines: [[]], row: 0, col: 0, style: {}, dirty: 0, rebuild: true, running: false, id: 0,
    cwd: "", shown: "", history: [], back: 0, pending: "", command: "", unseen: false };
  term.sessions.push(session);
  term.active = session.sid;
  send({ op: "term-cwd", session: session.sid });
  return session;
}

function termClose(sid) {
  const index = term.sessions.findIndex((session) => session.sid === sid);
  if (index < 0) return;
  send({ op: "term-close", session: sid });
  term.sessions.splice(index, 1);
  if (!term.sessions.length) { showTerminal(false); return; }
  if (term.active === sid) term.active = term.sessions[Math.max(0, index - 1)].sid;
  termShow();
}

function termSwitch(sid) {
  const session = termSession(sid);
  if (!session) return;
  term.active = sid;
  session.unseen = false;
  session.rebuild = true;
  termShow();
}

function termStyleKey(style) {
  const parts = [];
  if (style.fg) parts.push("color:" + style.fg);
  if (style.bg) parts.push("background:" + style.bg);
  if (style.bold) parts.push("font-weight:700");
  if (style.dim) parts.push("opacity:.65");
  if (style.italic) parts.push("font-style:italic");
  if (style.underline) parts.push("text-decoration:underline");
  return parts.join(";");
}

function termColor(n) { return uleColor("a" + n, null); }

function termSgr(s, params) {
  const list = params.length ? params : [0];
  for (let i = 0; i < list.length; i += 1) {
    const p = list[i], st = s.style;
    if (p === 0) { s.style = {}; continue; }
    if (p === 1) st.bold = true; else if (p === 2) st.dim = true; else if (p === 3) st.italic = true; else if (p === 4) st.underline = true;
    else if (p === 22) { st.bold = false; st.dim = false; } else if (p === 23) st.italic = false; else if (p === 24) st.underline = false;
    else if (p === 7) st.inverse = true; else if (p === 27) st.inverse = false;
    else if (p >= 30 && p <= 37) st.fg = termColor(p - 30); else if (p >= 90 && p <= 97) st.fg = termColor(p - 90 + 8);
    else if (p >= 40 && p <= 47) st.bg = termColor(p - 40); else if (p >= 100 && p <= 107) st.bg = termColor(p - 100 + 8);
    else if (p === 39) st.fg = null; else if (p === 49) st.bg = null;
    else if (p === 38 || p === 48) {
      let color = null;
      if (list[i + 1] === 5) { color = termColor(list[i + 2] || 0); i += 2; }
      else if (list[i + 1] === 2) { color = `rgb(${list[i + 2] || 0},${list[i + 3] || 0},${list[i + 4] || 0})`; i += 4; }
      if (p === 38) st.fg = color; else st.bg = color;
    }
  }
}

function termPut(s, char) {
  const line = s.lines[s.row];
  while (line.length < s.col) line.push({ ch: " ", st: "" });
  const style = s.style.inverse ? { ...s.style, fg: s.style.bg || "var(--page)", bg: s.style.fg || "var(--text)" } : s.style;
  line[s.col] = { ch: char, st: termStyleKey(style) };
  s.col += 1;
}

function termNewline(s) {
  s.row += 1;
  s.col = 0;
  if (s.row >= s.lines.length) s.lines.push([]);
  if (s.lines.length > TERM_MAX_LINES) {
    const drop = s.lines.length - TERM_MAX_LINES;
    s.lines.splice(0, drop);
    s.row -= drop;
    s.rebuild = true;
  }
}

function termWrite(s, text) {
  const first = s.row;
  const data = s.pending + text;
  s.pending = "";
  for (let i = 0; i < data.length; i += 1) {
    const c = data[i];
    if (c === "\x1b") {
      const next = data[i + 1];
      if (next === undefined) { s.pending = data.slice(i); break; }
      if (next === "[") {
        let j = i + 2;
        while (j < data.length && !/[@-~]/.test(data[j])) j += 1;
        if (j >= data.length) { s.pending = data.slice(i); break; }
        const body = data.slice(i + 2, j), final = data[j];
        const nums = body.replace(/^[?>=]/, "").split(";").filter((x) => x !== "").map(Number);
        const n = nums[0] || 0;
        if (final === "m") termSgr(s, body === "" ? [] : nums);
        else if (final === "K") {
          const line = s.lines[s.row];
          if (n === 0) line.length = Math.min(line.length, s.col);
          else if (n === 1) for (let k = 0; k < Math.min(s.col, line.length); k += 1) line[k] = { ch: " ", st: "" };
          else line.length = 0;
        } else if (final === "G") s.col = Math.max(0, (n || 1) - 1);
        else if (final === "C") s.col += n || 1;
        else if (final === "D") s.col = Math.max(0, s.col - (n || 1));
        else if (final === "A") s.row = Math.max(0, s.row - (n || 1));
        else if (final === "B") { for (let k = 0; k < (n || 1); k += 1) termNewline(s); }
        else if (final === "J" && (n === 2 || n === 3)) termClear(s);
        i = j;
        continue;
      }
      if (next === "]") {
        // OSC (window title, links): up to BEL or ESC \.
        const end = data.slice(i + 2).search(/\x07|\x1b\\/);
        if (end < 0) { s.pending = data.slice(i); break; }
        i += 2 + end + (data[i + 2 + end] === "\x07" ? 0 : 1);
        continue;
      }
      i += 1;
      continue;
    }
    if (c === "\r") s.col = 0;
    else if (c === "\n") termNewline(s);
    else if (c === "\b") s.col = Math.max(0, s.col - 1);
    else if (c === "\t") s.col = (Math.floor(s.col / 8) + 1) * 8;
    else if (c >= " ") termPut(s, c);
  }
  s.dirty = Math.min(s.dirty, first, s.row);
  if (s.sid !== term.active) { s.unseen = true; termTabs(); }
  termScheduleDraw();
}

function termClear(s) {
  s.lines = [[]];
  s.row = 0;
  s.col = 0;
  s.rebuild = true;
  termScheduleDraw();
}

function termScheduleDraw() {
  if (term.drawQueued) return;
  term.drawQueued = true;
  requestAnimationFrame(() => { term.drawQueued = false; termDraw(); });
}

function termLineNode(line) {
  const node = el("div", { class: "tline" });
  let text = "", style = null;
  const flush = () => {
    if (!text) return;
    const span = document.createElement("span");
    if (style) span.style.cssText = style;
    span.textContent = text;
    node.appendChild(span);
    text = "";
  };
  for (const cell of line) {
    if (cell.st !== style) { flush(); style = cell.st; }
    text += cell.ch;
  }
  flush();
  if (!node.childNodes.length) node.textContent = "​";
  return node;
}

function termDraw() {
  const s = termActive();
  const out = term.node && term.node.querySelector(".tout");
  if (!out || !s) return;
  const atBottom = out.scrollHeight - out.scrollTop - out.clientHeight < 24;
  if (s.rebuild) { out.replaceChildren(); s.rebuild = false; s.dirty = 0; }
  const nodes = out.children;
  for (let row = s.dirty; row < s.lines.length; row += 1) {
    const node = termLineNode(s.lines[row]);
    if (row < nodes.length) out.replaceChild(node, nodes[row]); else out.appendChild(node);
  }
  while (nodes.length > s.lines.length) out.lastChild.remove();
  s.dirty = s.lines.length - 1;
  if (atBottom || s.stick) { out.scrollTop = out.scrollHeight; s.stick = false; }
}

// A line of our own (the command that runs, notes): on its own line.
function termNote(s, text, kind) {
  if (s.col > 0 || s.lines[s.row].length) termNewline(s);
  const saved = s.style;
  s.style = kind === "cmd" ? { fg: "var(--accent-ink)", bold: true } : kind === "bad" ? { fg: "var(--danger)" } : { dim: true };
  for (const char of text) termPut(s, char);
  s.style = saved;
  s.dirty = Math.min(s.dirty, s.row);
  termNewline(s);
  s.stick = true;
  termScheduleDraw();
}

function termSize() {
  const out = term.node && term.node.querySelector(".tout");
  const cell = cellSize();
  if (!out || !out.clientWidth) return { cols: 80, rows: 24 };
  return { cols: Math.max(20, Math.floor((out.clientWidth - 24) / cell.w)), rows: Math.max(4, Math.floor(out.clientHeight / cell.h)) };
}

function termTabs() {
  const strip = term.node && term.node.querySelector(".ttabs");
  if (!strip) return;
  strip.replaceChildren(...term.sessions.map((session, index) => {
    const name = session.running ? session.command.split(/\s+/)[0] : (session.shown.split("/").pop() || "~");
    const tab = el("div", { class: "ttab" + (session.sid === term.active ? " on" : "") + (session.unseen ? " unseen" : ""),
      title: (session.running ? session.command + " — " : "") + (session.cwd || ""), onclick: () => termSwitch(session.sid) },
      session.running ? el("span", { class: "tdot" }) : null,
      el("span", { class: "tname", text: `${index + 1} ${name}` }),
      el("button", { class: "ghost x", title: "Close this terminal", text: "×", onclick: (event) => { event.stopPropagation(); termClose(session.sid); } }));
    return tab;
  }), el("button", { class: "ghost icon tnew", title: "New terminal (⌃⇧`)", "aria-label": "New terminal", onclick: () => { termNew(); termShow(); } }, icon("plus")));
}

function termPrompt() {
  const s = termActive();
  if (!term.node || !s) return;
  term.node.querySelector(".tprompt").textContent = s.running ? "›" : (s.shown || "~") + " ❯";
  term.node.querySelector(".tstop").hidden = !s.running;
  term.node.querySelector(".tinput").placeholder = s.running ? "Input for the running program (Enter sends, ⌃C stops)" : "Type a command, or Run";
}

// The active session on screen: tabs, output, prompt.
function termShow() {
  if (!term.node) return;
  const s = termActive();
  if (s) s.rebuild = true;
  termTabs();
  termDraw();
  termPrompt();
  term.node.querySelector(".tinput").focus();
}

function termRun(line) {
  const s = termActive();
  if (!s) return;
  if (!s.running && line.trim() === "clear") { termClear(s); return; }
  if (!s.running && line.trim()) { s.history.push(line); if (s.history.length > 200) s.history.shift(); }
  s.back = 0;
  send({ op: "term-run", session: s.sid, text: line, ...termSize() });
}

// Runs the file shown in the editor (saved first), in a free terminal: the active one, or
// a new one when a command still runs there.
function termRunFile() {
  const path = currentPath();
  showTerminal(true);
  let s = termActive();
  if (!path) { termNote(s, "Open a file to run it.", "bad"); return; }
  if (s.running) { s = termNew(); termShow(); }
  if (edit.showing === "code") uleSend({ command: "save_all" });
  const sid = s.sid;
  setTimeout(() => send({ op: "term-run-file", session: sid, path, ...termSize() }), edit.showing === "code" ? 200 : 0);
}

function showTerminal(open) {
  term.open = open;
  store("edit-term-open", open ? "1" : "0");
  if (open && !term.sessions.length) termNew();
  placePanels();
  if (open) { termShow(); }
  else if (codeNodes && edit.showing === "code") codeNodes.input.focus();
}

function termBuild() {
  const input = el("input", { class: "tinput", spellcheck: "false", autocomplete: "off", autocapitalize: "off", "aria-label": "Terminal input" });
  input.addEventListener("keydown", (event) => {
    if (event.metaKey) return;
    event.stopPropagation();
    const s = termActive();
    if (!s) return;
    if (event.key === "Enter") { event.preventDefault(); termRun(input.value); input.value = ""; return; }
    if (event.ctrlKey && event.code === "KeyC") {
      event.preventDefault();
      if (s.running) send({ op: "term-input", session: s.sid, text: "\x03" }); else input.value = "";
      return;
    }
    if (event.ctrlKey && event.code === "KeyD" && s.running) { event.preventDefault(); send({ op: "term-input", session: s.sid, text: "\x04" }); return; }
    if (event.ctrlKey && event.code === "KeyL") { event.preventDefault(); termClear(s); return; }
    if (event.ctrlKey && event.code === "Backquote") {
      event.preventDefault();
      if (event.shiftKey) { termNew(); termShow(); } else showTerminal(false);
      return;
    }
    if (!s.running && (event.key === "ArrowUp" || event.key === "ArrowDown") && s.history.length) {
      event.preventDefault();
      s.back = Math.max(0, Math.min(s.history.length, s.back + (event.key === "ArrowUp" ? 1 : -1)));
      input.value = s.back ? s.history[s.history.length - s.back] : "";
    }
  });
  const button = (glyph, title, run, extra) => el("button", { class: "ghost icon" + (extra ? " " + extra : ""), title, "aria-label": title, onclick: run }, icon(glyph));
  const head = el("div", { class: "thead", title: "Drag to move the panel; right-click for more" },
    el("span", { class: "ttitle", text: "Terminal" }),
    el("div", { class: "ttabs" }),
    el("div", { class: "grow" }),
    el("button", { class: "trun", title: "Run the open file (⌘R)", onclick: termRunFile }, icon("run"), el("span", { text: "Run" })),
    button("stop", "Stop the command (⌃C)", () => { const s = termActive(); if (s) send({ op: "term-input", session: s.sid, text: "\x03" }); }, "tstop"),
    button("trash", "Clear (⌃L)", () => { const s = termActive(); if (s) termClear(s); }),
    button("x", "Hide the terminal (⌃`)", () => showTerminal(false)));
  panelDrag(head, "term");
  const node = el("section", { class: "eterm", "aria-label": "Terminal" }, head,
    el("div", { class: "tout", onclick: () => { if (!getSelection().toString()) input.focus(); } }),
    el("label", { class: "tline tinputrow" }, el("span", { class: "tprompt" }), input));
  term.node = node;
  new ResizeObserver(() => {
    clearTimeout(term.resizeTimer);
    const s = termActive();
    term.resizeTimer = setTimeout(() => s && send({ op: "term-resize", session: s.sid, ...termSize() }), 80);
  }).observe(node.querySelector(".tout"));
  requestAnimationFrame(termShow);
}

function termReceive(message) {
  const s = termSession(message.session);
  if (!s) return true;
  switch (message.type) {
    case "term-output":
      if (message.id === s.id) termWrite(s, message.text);
      break;
    case "term-start":
      s.id = message.id;
      s.running = true;
      s.command = message.line;
      s.style = {};
      termNote(s, (s.shown || "~") + " ❯ " + message.line, "cmd");
      break;
    case "term-exit":
      if (message.id !== s.id) break;
      s.running = false;
      s.pending = "";
      if (message.code === null || message.code === undefined) termNote(s, "stopped");
      else if (message.code !== 0) termNote(s, "exit " + message.code, "bad");
      break;
    case "term-cwd":
      s.cwd = message.path;
      s.shown = message.shown;
      break;
    case "term-note":
      if (!term.open) showTerminal(true);
      termNote(s, message.text, "bad");
      break;
    default:
      return false;
  }
  if (s.sid === term.active) termPrompt();
  termTabs();
  return true;
}

// ⌃` shows or hides the terminal, ⌃⇧` opens another, ⌘R / F5 run the open file: before
// the editor gets the key.
document.addEventListener("keydown", (event) => {
  if (home.section !== "edit") return;
  if (event.ctrlKey && !event.metaKey && event.code === "Backquote") {
    event.preventDefault();
    event.stopPropagation();
    if (event.shiftKey) { if (!term.open) showTerminal(true); else { termNew(); termShow(); } }
    else showTerminal(!term.open);
    return;
  }
  const run = (event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey && event.code === "KeyR") || (event.key === "F5" && !event.metaKey);
  if (run) { event.preventDefault(); event.stopPropagation(); termRunFile(); }
}, true);
