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
    el("button", { class: "ghost icon", title: "Project panel (⌘B)", "aria-label": "Project panel", onclick: toggleEditTree }, icon("sidebar")),
    el("span", { class: "project" }),
    el("div", { class: "grow" }),
    el("button", { class: "esearch", title: "Find a file (⌘P)", onclick: () => editCommand("file_picker") },
      icon("search"), el("span", { text: "Search files…" }), el("kbd", { text: "⌘P" })),
    el("div", { class: "grow" }),
    el("button", { class: "ghost icon", title: "All commands (⌘⇧P)", "aria-label": "Commands", onclick: () => editCommand("command_palette") }, icon("command")),
    el("button", { class: "ghost icon", title: "Open a file", "aria-label": "Open a file", onclick: () => send({ op: "edit-open-dialog" }) }, icon("file")),
    el("button", { class: "ghost icon", title: "Add a folder to the project", "aria-label": "Add a folder", onclick: () => send({ op: "edit-add-folder" }) }, icon("folder"))));
  const tree = el("aside", { class: "etree", tabindex: "0" });
  tree.addEventListener("keydown", treeKey);
  tree.addEventListener("contextmenu", (event) => { if (event.target === tree) treeMenu(event, null); });
  const pane = el("div", { class: "epane" },
    el("div", { class: "etabs" }),
    el("div", { class: "eerror", hidden: "" }),
    el("div", { class: "ebody" }));
  const grip = el("div", { class: "grip", title: "Drag to resize; double-click hides", ondblclick: toggleEditTree });
  const box = el("div", { class: "edit" + (treeHidden() ? " tree-hidden" : "") },
    title, el("div", { class: "ework" }, tree, grip, pane), el("div", { class: "estatus" }));
  $(".content").replaceChildren(box);
  box.style.setProperty("--tree-w", treeWidth() + "px");
  dragWidth(grip, {
    start: () => (treeHidden() ? 0 : treeWidth()),
    // Narrower than TREE_SNAP hides the project panel; wider shows it at that width.
    move: (width) => {
      const hidden = width < TREE_SNAP;
      if (hidden !== treeHidden()) { store("edit-tree-hidden", hidden ? "1" : "0"); $(".edit").classList.toggle("tree-hidden", hidden); }
      if (!hidden) $(".edit").style.setProperty("--tree-w", clampWidth(width, TREE_MIN, TREE_MAX) + "px");
    },
    end: (width) => { if (width >= TREE_SNAP) store("edit-tree-width", String(clampWidth(width, TREE_MIN, TREE_MAX))); },
  });
  applyEditTheme();
  if (!edit.places) send({ op: "edit-places" });
  drawTree();
  drawPane();
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
  send({ op: "edit-prefs", ...change });
}

// The editor theme's colors on every surface of the part (CSS variables on `.edit`).
function applyEditTheme() {
  const box = $(".edit");
  const theme = edit.ule.frame && edit.ule.frame.theme;
  if (!box) return;
  const names = ["--ed-bg", "--ed-fg", "--ed-panel", "--ed-line", "--ed-sel", "--ed-muted", "--ed-border", "--ed-accent", "--ed-dir"];
  // Only the theme's own variables: the style also holds the panel width (--tree-w).
  if (!theme) { for (const name of names) box.style.removeProperty(name); return; }
  const dark = isDark();
  const bg = uleColor(theme.bg, dark ? "#16171a" : "#ffffff");
  const fg = uleColor(theme.fg, dark ? "#e4e5e9" : "#1d1d1f");
  const vars = {
    "--ed-bg": bg, "--ed-fg": fg,
    "--ed-panel": uleColor(theme.panel, dark ? "#1f2023" : "#f4f4f5"),
    "--ed-line": uleColor(theme.line, dark ? "#232428" : "#f0f0f2"),
    "--ed-sel": uleColor(theme.selection, dark ? "#2f3440" : "#dbe4f0"),
    "--ed-muted": uleColor(theme.muted, dark ? "#7c7f88" : "#8a8d94"),
    "--ed-border": uleColor(theme.border, dark ? "#2c2d31" : "#e2e2e5"),
    "--ed-accent": uleColor(theme.accent, dark ? "#61afef" : "#0550ae"),
    "--ed-dir": uleColor(theme.dir, fg),
  };
  for (const [name, value] of Object.entries(vars)) {
    if (box.style.getPropertyValue(name) !== value) box.style.setProperty(name, value);
  }
}

const TREE_MIN = 160, TREE_MAX = 640, TREE_SNAP = 90;
function treeWidth() { return clampWidth(Number(stored("edit-tree-width", "240")) || 240, TREE_MIN, TREE_MAX); }

function treeHidden() { return stored("edit-tree-hidden", "0") === "1"; }

function toggleEditTree() {
  const hidden = !treeHidden();
  store("edit-tree-hidden", hidden ? "1" : "0");
  $(".edit")?.classList.toggle("tree-hidden", hidden);
  window.dispatchEvent(new Event("resize"));
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
  parts.push(el("div", { class: "ehead" }, el("h4", { text: "Project" }), el("div", { class: "grow" }),
    tool("filePlus", "New file (⌘N)", () => startNaming("new-file", selectedEntry())),
    tool("folderPlus", "New folder (⇧⌘N)", () => startNaming("new-folder", selectedEntry())),
    tool("collapse", "Collapse all", () => { edit.open.clear(); rememberOpen(); drawTree(); })));
  if (!places.roots.length) parts.push(el("p", { class: "muted small", text: "Add a folder to see its files here. Files dropped on the window open too." }));
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
  // Below the folders: opening a file reorders this list, and the tree must not move
  // under the mouse.
  if (places.recent.length) {
    parts.push(el("h4", { text: "Recent" }));
    for (const item of places.recent.slice(0, 8)) {
      const row = fileRow(item.path, item.name, 0);
      if (!item.exists) row.classList.add("gone");
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
  if (!entry) {
    const root = edit.places && edit.places.roots.find((item) => item.exists);
    if (!root) return;
    entry = { path: root.path, dir: true, root: true };
  }
  edit.selected = entry.path;
  closeTreeMenu();
  const item = (label, keys, run, danger) => el("button", { class: "emi" + (danger ? " danger" : ""), onclick: () => { closeTreeMenu(); run(); } },
    el("span", { text: label }), keys ? el("kbd", { text: keys }) : null);
  const line = () => el("hr");
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
  const editing = (edit.ule.frame && edit.ule.frame.editing) || places.editing || "vim";
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
    el("button", { class: "ghost keysbtn", title: "Keyboard shortcuts (⌘K ⌘S)", text: "Keys", onclick: toggleKeys }),
    el("button", { class: "ghost mode" + (editing === "vim" ? " vim" : ""),
      title: editing === "vim" ? "Vim keys (modes). Click for ordinary editor keys" : "Ordinary editor keys, no modes. Click for vim",
      text: editing === "vim" ? "Vim" : "Standard",
      onclick: () => setEditPrefs({ editing: editing === "vim" ? "standard" : "vim" }) }),
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
  const editing = (edit.ule.frame && edit.ule.frame.editing) || (edit.places && edit.places.editing) || "vim";
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
  const editing = (edit.ule.frame && edit.ule.frame.editing) || (edit.places && edit.places.editing) || "vim";
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
  const baseBg = style.getPropertyValue("--code-bg").trim() || (isDark() ? "#16171a" : "#ffffff");
  const baseFg = style.getPropertyValue("--code-fg").trim() || (isDark() ? "#e4e5e9" : "#1d1d1f");
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
