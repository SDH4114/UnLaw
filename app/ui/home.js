// Unlaw's main window: the parts of the app in one place. Rust runs every
// command (`ul sys --json`, `ul clip ...`, `ul game --stream`) and sends the
// results here; this page only draws them and sends back names and ids.
// Command output is data: textContent only, never innerHTML.
"use strict";

const SECTIONS = [
  { id: "commands", label: "Commands", icon: "command", key: "1" },
  { id: "templates", label: "Templates", icon: "layout", key: "2" },
  { id: "system", label: "System", icon: "cpu", key: "3" },
  { id: "clipboard", label: "Clipboard", icon: "clipboard", key: "4" },
  { id: "games", label: "Games", icon: "game", key: "5" },
  // The parts of `ul desk`, each its own item: one embedded desk page serves them.
  { id: "board", label: "Board", icon: "board", key: "6", desk: true },
  { id: "today", label: "Today", icon: "today", key: "7", desk: true },
  { id: "canvas", label: "Canvas", icon: "canvas", key: "8", desk: true },
  { id: "studio", label: "Studio", icon: "studio", key: "9", desk: true },
];

const home = { section: "commands", items: [], version: "", sys: null, sysError: "", history: { cpu: [], mem: [], gpu: [], down: [], up: [], read: [], write: [], power: [] }, clip: null, clipStatus: null, clipError: "", filter: "", chosen: -1, copied: "", desk: { state: "idle", text: "" } };

function $(selector) { return document.querySelector(selector); }

// ---------- frame ----------

function build() {
  const nav = el("nav");
  for (const section of SECTIONS) {
    nav.appendChild(el("button", { "data-section": section.id, onclick: () => go(section.id) },
      icon(section.icon), el("span", { text: section.label }), el("kbd", { text: "⌘" + section.key })));
  }
  const side = el("aside", { class: "side" },
    dragArea(el("div", { class: "lights" })),
    nav,
    el("div", { class: "grow" }),
    el("div", { class: "foot" },
      el("span", { class: "version" }),
      el("button", { class: "update", hidden: "", title: "", text: "Update", onclick: () => send({ op: "update" }) }),
      el("button", { class: "ghost", "data-section": "settings", title: "⌘,", text: "Settings", onclick: () => go("settings") })));
  const main = el("div", { class: "main" },
    dragArea(el("header", { class: "top" })),
    el("section", { class: "content" }));
  document.body.replaceChildren(el("div", { class: "app" }, side, main));
}

// GitHub has a newer Unlaw (`ul update --check --json`, asked when the window opens).
function showUpdate(answer) {
  const button = $(".foot .update");
  if (!button) return;
  button.hidden = !answer.update;
  button.title = answer.latest ? `Unlaw ${answer.latest} is out: ${answer.message}` : answer.message || "";
}

// The top strip works like a title bar: dragging moves the window, a double click
// zooms it to the screen and back (never full screen, which would make a new Space).
// The window drag starts only once the mouse moves: started on the press, the native
// drag loop swallowed the second click and a double click never arrived.
let pressed = null;

function dragArea(node) {
  node.addEventListener("mousedown", (event) => {
    if (event.button !== 0 || event.target.closest("input, button, select, textarea")) return;
    event.preventDefault();
    pressed = { x: event.screenX, y: event.screenY };
  });
  node.addEventListener("mousemove", (event) => {
    if (!pressed || !(event.buttons & 1)) { pressed = null; return; }
    if (Math.abs(event.screenX - pressed.x) + Math.abs(event.screenY - pressed.y) < 3) return;
    pressed = null;
    send({ op: "drag" });
  });
  node.addEventListener("mouseup", () => { pressed = null; });
  node.addEventListener("dblclick", (event) => {
    if (event.target.closest("input, button, select, textarea")) return;
    send({ op: "zoom" });
  });
  return node;
}

function go(section, tell = true) {
  if (section === "desk") section = "board";
  if (section !== "settings" && !SECTIONS.some((item) => item.id === section)) section = "commands";
  const changed = section !== home.section;
  if (changed && home.recording) stopRecording();
  home.section = section;
  for (const button of document.querySelectorAll(".side [data-section]")) button.classList.toggle("on", button.dataset.section === section);
  if (tell) send({ op: "section", section });
  if (changed || !$(".content").childElementCount) render();
}

function header(title, sub, ...tools) {
  $(".top").replaceChildren(el("h1", { text: title }), el("span", { class: "sub", text: sub || "" }), el("div", { class: "grow" }), ...tools);
}

function render() {
  const content = $(".content");
  const desk = isDeskPart(home.section);
  content.classList.toggle("flush", home.section === "games" || desk);
  // The desk page has its own header: it takes the whole right side.
  $(".main").classList.toggle("desk-on", desk);
  if (home.section === "commands") renderCommands();
  else if (home.section === "templates") renderTemplates();
  else if (home.section === "system") renderSystem();
  else if (home.section === "clipboard") renderClipboard();
  // Records are asked for here, not in renderGames: their answer redraws the list,
  // and asking again from there looped and replaced the buttons under the mouse.
  else if (home.section === "games") { renderGames(); send({ op: "games" }); }
  else if (desk) renderDesk();
  else if (home.section === "settings") { renderSettings(); send({ op: "settings" }); }
}

// ---------- commands ----------

function renderCommands() {
  const search = el("input", { type: "search", placeholder: "Filter commands", spellcheck: "false" });
  search.value = home.filter;
  search.addEventListener("input", () => { home.filter = search.value; drawTiles(); });
  header("Commands", "Everything ul can do from the app", search);
  $(".content").replaceChildren(el("div", { class: "tiles" }));
  drawTiles();
}

function drawTiles() {
  const box = $(".tiles");
  if (!box) return;
  const words = home.filter.toLowerCase().split(/\s+/).filter(Boolean);
  const shown = home.items.filter((item) => {
    const text = `${item.name} ${item.title} ${item.summary}`.toLowerCase();
    return words.every((word) => text.includes(word));
  });
  box.replaceChildren(...shown.map((item) => {
    // The pin sits in the tile's corner: shown on hover, kept (filled) while the command is in the menu bar.
    const pin = el("button", { class: "pin" + (item.pinned ? " on" : ""), title: item.pinned ? "Remove from the menu bar" : "Pin to the menu bar",
      "aria-label": item.pinned ? `Unpin ${item.title}` : `Pin ${item.title}`, "aria-pressed": String(!!item.pinned),
      onclick: (event) => { event.stopPropagation(); send({ op: item.pinned ? "unpin" : "pin", name: item.name }); } }, icon("pin"));
    const tile = el("div", { class: "tile", role: "button", tabindex: "0", title: `ul ${item.name}`, onclick: () => openCommand(item),
      onkeydown: (event) => { if ((event.key === "Enter" || event.key === " ") && event.target === tile) { event.preventDefault(); openCommand(item); } } },
      el("div", { class: "glyph" }, commandIcon(item)),
      el("div", { class: "what" }, el("b", { text: item.title }), el("span", { text: item.summary || `ul ${item.name}` })),
      pin);
    return tile;
  }));
  if (!shown.length) box.replaceChildren(el("div", { class: "note", text: home.items.length ? "Nothing matches." : "Reading the commands…" }));
}

function openCommand(item) {
  if (item.section) go(item.section);
  else send({ op: "default", name: item.name });
}

// ---------- templates ----------
// `ul template` working environments: Rust reads `ul template list --json` every
// few seconds while this part is open. Launching runs `ul <name>`; saving a new
// one and editing open the terminal (they ask questions there).

const KIND_ICONS = { terminal: "terminal", browser: "globe", app: "app" };

function renderTemplates() {
  header("Templates", "Working environments: one click opens a project's apps, terminals and sites, placed on the screen",
    el("button", { class: "primary", onclick: () => send({ op: "template-new" }) }, icon("plus"), el("span", { text: "Save open windows…" })));
  const content = $(".content");
  const items = home.templates;
  const parts = [];
  if (home.templateNote) {
    const note = home.templateNote;
    parts.push(el("div", { class: `tnote ${note.ok ? "ok" : "bad"}` }, icon(note.ok ? "check" : "alert"),
      el("div", {}, el("b", { text: note.title }), note.text ? el("pre", { text: note.text }) : null),
      el("button", { class: "ghost", "aria-label": "Clear", onclick: () => { home.templateNote = null; renderTemplates(); } }, icon("close"))));
  }
  if (!items) {
    parts.push(el("div", { class: "note", text: home.templatesError || "Reading your templates…" }));
  } else if (!items.length) {
    parts.push(el("div", { class: "tempty" },
      el("div", { class: "art" }, icon("layout")),
      el("b", { text: "No templates yet" }),
      el("p", { text: "Arrange the windows for a project (editor, Ghostty with its tabs, the browser), then save them as a template. Next time one click puts everything back in place." }),
      el("button", { class: "primary", onclick: () => send({ op: "template-new" }) }, icon("plus"), el("span", { text: "Save open windows…" })),
      el("small", { text: "Saving reads your windows and asks which belong; it opens in the terminal." })));
  } else {
    parts.push(el("div", { class: "tgrid" }, ...items.map(templateCard)));
  }
  content.replaceChildren(el("div", { class: "templates" }, ...parts));
}

function templateCard(item) {
  const busy = home.templateBusy === item.name;
  const confirmRm = home.templateConfirm === item.name;
  const windows = item.windows || [];
  const list = el("div", { class: "twins" }, ...windows.map((window) => el("div", { class: "twin" },
    el("span", { class: `kind ${window.kind}` }, icon(KIND_ICONS[window.kind] || "app")),
    el("div", {}, el("b", { text: window.kind === "browser" ? "Browser" : window.app }),
      el("span", { text: [window.place, window.details].filter(Boolean).join(" · ") })))));
  if (!windows.length) list.appendChild(el("div", { class: "twin" }, el("span", { class: "muted", text: "No windows: only changes the folder in the terminal." })));
  const actions = confirmRm
    ? el("div", { class: "tactions confirm" }, el("span", { text: `Delete “${item.name}”?` }),
        el("button", { class: "ghost", text: "Cancel", onclick: () => { home.templateConfirm = ""; renderTemplates(); } }),
        el("button", { class: "danger", text: "Delete", onclick: () => templateDo("template-rm", item) }))
    : el("div", { class: "tactions" },
        el("button", { class: "primary", disabled: busy ? "" : null, onclick: () => templateDo("template-run", item, false) },
          busy ? el("i", { class: "spinner" }) : icon("run"), el("span", { text: busy ? "Opening…" : "Open" })),
        el("button", { disabled: busy ? "" : null, title: "Open and hide every other app", onclick: () => templateDo("template-run", item, true) }, el("span", { text: "Focus" })),
        el("span", { class: "grow" }),
        el("button", { class: "ghost icon", title: "Edit the TOML in the terminal", "aria-label": `Edit ${item.name}`, onclick: () => send({ op: "template-edit", name: item.name }) }, icon("pencil")),
        el("button", { class: "ghost icon", title: "Delete", "aria-label": `Delete ${item.name}`, onclick: () => { home.templateConfirm = item.name; renderTemplates(); } }, icon("trash")));
  return el("div", { class: "tcard" },
    el("div", { class: "tcardhead" },
      el("div", { class: "what" }, el("b", { text: item.name }), el("code", { text: item.path })),
      item.focus ? el("span", { class: "badge", text: "focus" }) : null,
      item.legacy ? el("span", { class: "badge warn", title: "Saved in the old format: save it again for windows and tabs", text: "old format" }) : null),
    screenPreview(windows), list, actions);
}

// The windows as boxes on a small screen, one screen per display used, so the layout is seen at a glance.
function screenPreview(windows) {
  const placed = windows.filter((window) => Array.isArray(window.frame));
  if (!placed.length) return null;
  const screens = [...new Set(placed.map((window) => window.screen || 1))].sort();
  return el("div", { class: "tscreens" }, ...screens.map((screen) => el("div", { class: "tscreen", title: screens.length > 1 ? `Display ${screen}` : "" },
    ...placed.filter((window) => (window.screen || 1) === screen).map((window) => {
      const [x, y, w, h] = window.frame;
      return el("div", { class: `tbox ${window.kind}`, style: `left:${x * 100}%;top:${y * 100}%;width:${w * 100}%;height:${h * 100}%` },
        el("span", { text: window.kind === "browser" ? "Browser" : window.app }));
    }))));
}

function templateDo(op, item, focus) {
  home.templateConfirm = "";
  if (op === "template-run") home.templateBusy = item.name;
  send({ op, name: item.name, focus: !!focus });
  renderTemplates();
}

// ---------- system ----------


function renderSystem() {
  const data = home.sys;
  const info = data && data.system;
  const thermal = info && info.thermal && info.thermal !== "nominal" ? "thermal " + info.thermal : "";
  header("System", info ? [info.model, info.chip, info.os, info.uptime_seconds != null ? "up " + duration(info.uptime_seconds) : "", thermal].filter(Boolean).join(" · ") : "Live, every 2 seconds");
  const content = $(".content");
  if (!data) {
    content.replaceChildren(el("div", { class: "note", text: home.sysError || "Reading CPU, memory, disks and battery…" }));
    return;
  }
  const cards = el("div", { class: "cards" });
  const cpu = data.cpu || {};
  const cores = cpu.cores ? `${cpu.cores.performance ?? "?"}P + ${cpu.cores.efficiency ?? "?"}E cores` : "";
  cards.appendChild(card("CPU", pct(cpu.usage_percent), cores, spark("cpu"), coreBars(cpu), rows([
    ["User", pct(cpu.user_percent)], ["System", pct(cpu.system_percent)],
    ["Performance cores", pct(cpu.performance_percent)], ["Efficiency cores", pct(cpu.efficiency_percent)],
    ["Load (1, 5, 15 min)", (cpu.load_average || []).map((value) => value.toFixed(2)).join("  ") || "n/a"],
  ])));
  const mem = data.memory || {};
  const used = mem.total_bytes ? mem.used_bytes / mem.total_bytes * 100 : null;
  const part = (bytes) => mem.total_bytes && bytes ? (bytes / mem.total_bytes * 100) + "%" : "0%";
  const level = { 1: "normal", 2: "warn", 4: "critical" }[mem.pressure_level] || "normal";
  const pressure = (mem.pressure || "n/a") + (mem.pressure_percent != null ? ` · ${mem.pressure_percent}%` : "");
  cards.appendChild(card("Memory", `${gb(mem.used_bytes)}`, `of ${gb(mem.total_bytes)} · ${pct(used)}`, spark("mem"),
    el("div", { class: "bar" }, el("i", { class: "a", style: "width:" + part(mem.app_bytes) }), el("i", { class: "b", style: "width:" + part(mem.wired_bytes) }),
      el("i", { class: "c", style: "width:" + part(mem.compressed_bytes) }), el("i", { class: "d", style: "width:" + part(mem.cached_bytes) })),
    el("div", { class: "legend" }, legend("var(--accent)", "App " + gb(mem.app_bytes)), legend("#7f8ea3", "Wired " + gb(mem.wired_bytes)),
      legend("#b07fd0", "Compressed " + gb(mem.compressed_bytes)), legend("#8fb59a", "Cached " + gb(mem.cached_bytes))),
    rows([["Pressure", el("span", { class: "pressure-" + level, text: pressure })], ["Swap", mem.swap_total_bytes ? `${gb(mem.swap_used_bytes)} of ${gb(mem.swap_total_bytes)}` : "none"], ["Free", gb(mem.free_bytes)]])));
  const gpu = data.gpu || {};
  cards.appendChild(card("GPU", pct(gpu.usage_percent), gpu.cores ? `${gpu.cores} cores` : "", spark("gpu"), rows([
    ["Renderer", pct(gpu.renderer_percent)], ["Tiler", pct(gpu.tiler_percent)],
    ["Memory in use", gpu.memory_in_use_bytes != null ? gb(gpu.memory_in_use_bytes) : "n/a"], ["Name", gpu.name || "n/a"],
  ])));
  const net = data.network;
  cards.appendChild(card("Network", net ? "↓ " + speed(net.download_bytes_per_sec) : "n/a", net ? "↑ " + speed(net.upload_bytes_per_sec) : "",
    spark("down", "auto"), rows(net ? [["Interfaces", net.interfaces.join(", ") || "no traffic"], ["Received", bytes(net.received_bytes)], ["Sent", bytes(net.sent_bytes)]] : [])));
  const io = data.io;
  cards.appendChild(card("Disk activity", io ? "R " + speed(io.read_bytes_per_sec) : "n/a", io ? "W " + speed(io.write_bytes_per_sec) : "",
    spark("write", "auto"), rows(io ? [["Reads", io.read_ops_per_sec + " /s"], ["Writes", io.write_ops_per_sec + " /s"], ["Read since start-up", bytes(io.read_bytes)], ["Written since start-up", bytes(io.written_bytes)]] : [])));
  const battery = data.battery;
  if (battery && battery.present) {
    const state = battery.charging ? "charging" : battery.plugged_in ? "on power" : "on battery";
    const left = battery.time_remaining_minutes != null ? duration(battery.time_remaining_minutes * 60) + (battery.charging ? " to full" : " left") : "";
    cards.appendChild(card("Battery", pct(battery.percent), state,
      el("div", { class: "bar" }, el("i", { class: "a", style: `width:${battery.percent || 0}%` })),
      rows([["Time", left || "n/a"], ["Mac draws", watts(battery.system_power_watts)], ["Adapter", battery.adapter_watts ? battery.adapter_watts + " W" : battery.plugged_in ? "n/a" : "not connected"],
        ["Condition", battery.condition || "n/a"], ["Max capacity", pct(battery.max_capacity_percent)], ["Cycles", String(battery.cycle_count ?? "n/a")],
        ["Voltage", battery.voltage_v != null ? battery.voltage_v.toFixed(2) + " V" : "n/a"]])));
  }
  const disks = el("div");
  for (const disk of data.disk || []) {
    disks.appendChild(el("div", { class: "disk" },
      el("div", { class: "label" }, el("b", { text: disk.mount }), el("span", { text: `${gb(disk.free_bytes)} free of ${gb(disk.total_bytes)}` })),
      el("div", { class: "bar" }, el("i", { class: "a", style: `width:${disk.used_percent || 0}%` }))));
  }
  cards.appendChild(card("Disks", null, "", disks));
  const top5 = data.top || {};
  cards.appendChild(card("Top by CPU", null, top5.processes ? `${top5.processes} processes` : "", procs(top5.cpu, (item) => pct(item.cpu_percent))));
  cards.appendChild(card("Top by memory", null, "", procs(top5.memory, (item) => gb(item.memory_bytes))));
  content.replaceChildren(cards);
  for (const canvas of content.querySelectorAll("canvas.spark")) drawSpark(canvas);
}


// One thin bar per core, performance cores first, like Activity Monitor's CPU History.
function coreBars(cpu) {
  const list = cpu.per_core;
  if (!list || !list.length) return null;
  const groups = [["P", "Performance"], ["E", "Efficiency"]].map(([kind, name]) => [name, list.filter((core) => core.kind === kind)]).filter(([, cores]) => cores.length);
  if (!groups.length) groups.push(["Cores", list]);
  return el("div", { class: "corebars" }, ...groups.map(([name, cores]) => el("div", { class: "coregroup" },
    el("div", { class: "bars" }, ...cores.map((core) => el("i", { title: pct(core.usage_percent), style: `height:${Math.max(4, Math.min(100, core.usage_percent))}%` }))),
    el("small", { text: name }))));
}

function card(title, big, small, ...children) {
  const node = el("div", { class: "card" }, el("h3", { text: title }));
  if (big !== null) node.appendChild(el("div", { class: "big", text: big }, small ? el("small", { text: small }) : null));
  for (const child of children) if (child) node.appendChild(child);
  return node;
}

function rows(pairs) {
  const list = el("dl", { class: "rows" });
  for (const [label, value] of pairs) {
    list.appendChild(el("dt", { text: label }));
    list.appendChild(typeof value === "string" ? el("dd", { text: value }) : el("dd", {}, value));
  }
  return list;
}

function legend(color, text) { return el("span", { style: "--c:" + color, text }); }

function procs(list, value) {
  const table = el("table", { class: "procs" });
  for (const item of list || []) table.appendChild(el("tr", {}, el("td", { text: item.name }), el("td", { text: value(item) })));
  if (!(list || []).length) table.appendChild(el("tr", {}, el("td", { text: "n/a" })));
  return table;
}

function spark(kind, scale) { return el("canvas", { class: "spark", "data-kind": kind, "data-scale": scale || "" }); }

function drawSpark(canvas) {
  const values = home.history[canvas.dataset.kind] || [];
  const ratio = devicePixelRatio || 1;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  const style = getComputedStyle(document.documentElement);
  context.strokeStyle = style.getPropertyValue("--line");
  context.beginPath(); context.moveTo(0, height - .5); context.lineTo(width, height - .5); context.stroke();
  if (values.length < 2) return;
  const step = width / (HISTORY - 1);
  const x = (index) => width - (values.length - 1 - index) * step;
  // Percentages are drawn on 0-100; speeds on their own recent maximum.
  const top = canvas.dataset.scale === "auto" ? Math.max(...values, 1) : 100;
  const y = (value) => height - 2 - Math.max(0, Math.min(top, value)) / top * (height - 4);
  context.beginPath();
  values.forEach((value, index) => index ? context.lineTo(x(index), y(value)) : context.moveTo(x(index), y(value)));
  context.strokeStyle = style.getPropertyValue("--accent");
  context.lineWidth = 1.5;
  context.stroke();
  context.lineTo(x(values.length - 1), height); context.lineTo(x(0), height); context.closePath();
  context.fillStyle = style.getPropertyValue("--accent-soft");
  context.fill();
}

const HISTORY = 60;
function remember(kind, value) {
  if (value == null) return;
  const list = home.history[kind];
  list.push(value);
  if (list.length > HISTORY) list.shift();
}

// ---------- clipboard ----------

function renderClipboard() {
  const search = el("input", { type: "search", placeholder: "Search the history", spellcheck: "false" });
  search.value = home.clipFilter || "";
  search.addEventListener("input", () => { home.clipFilter = search.value; home.chosen = -1; drawClips(); });
  const status = home.clipStatus || {};
  const running = status.watcher === "running";
  const paused = !!status.paused;
  const state = el("span", { class: "state " + (running && !paused ? "on" : "off"), text: running ? (paused ? "Paused" : "Recording") : "Watcher off" });
  const tools = [search, state];
  if (running) tools.push(el("button", { class: "ghost", text: paused ? "Resume" : "Pause", onclick: () => clip(paused ? "resume" : "pause") }));
  tools.push(el("button", { class: running ? "ghost" : "primary", text: running ? "Turn off" : "Turn on", onclick: () => clip(running ? "off" : "on") }));
  tools.push(el("button", { class: "ghost", text: "Clear…", onclick: clearClips }));
  const kinds = el("div", { class: "seg kinds" }, ...[["all", "All"], ["text", "Text"], ["image", "Images"], ["file", "Files"]].map(([id, label]) =>
    el("button", { class: (home.clipKind || "all") === id ? "on" : "", text: label, onclick: () => { home.clipKind = id; renderClipboard(); } })));
  tools.unshift(kinds);
  // No subtitle: the bar is full; the tooltip says it.
  header("Clipboard", "", ...tools);
  $(".top h1").title = "Click an item to copy it again" + (status.max_files != null ? `; the last ${status.max_files} images and files are kept (Settings)` : "");
  if (!$(".clips")) $(".content").replaceChildren(el("div", { class: "clipask" }), el("div", { class: "clips" }));
  const ask = $(".clipask");
  ask.replaceChildren(...(home.clipConfirm ? [el("div", { class: "tnote bad", role: "alertdialog" }, icon("trash"),
    el("div", {}, el("b", { text: "Delete the whole clipboard history?" }),
      el("span", { class: "muted", text: " Texts, pictures and saved files. This cannot be undone." })),
    el("button", { class: "ghost", text: "Cancel", onclick: () => { home.clipConfirm = false; renderClipboard(); } }),
    el("button", { class: "danger", text: "Delete all", onclick: () => { home.clipConfirm = false; clip("clear"); renderClipboard(); } }))] : []));
  drawClips();
}

function clipMatches() {
  const words = (home.clipFilter || "").toLowerCase().split(/\s+/).filter(Boolean);
  const kind = home.clipKind || "all";
  return (home.clip || []).filter((item) => (kind === "all" || (item.kind || "text") === kind)
    && words.every((word) => ((item.text || "") + " " + (item.name || "")).toLowerCase().includes(word)));
}

function ago(time) {
  const then = Date.parse(time);
  if (!then) return "";
  const seconds = Math.max(0, (Date.now() - then) / 1000);
  if (seconds < 60) return "now";
  if (seconds < 3600) return Math.floor(seconds / 60) + " min";
  if (seconds < 86400) return Math.floor(seconds / 3600) + " h";
  return new Date(then).toLocaleDateString();
}

function drawClips() {
  const box = $(".clips");
  if (!box) return;
  // A note replaces the list: forget its key, or clearing a filter later finds the same key and keeps the note.
  if (home.clip === null) { delete box.dataset.key; box.replaceChildren(el("div", { class: "note", text: home.clipError || "Reading the history…" })); return; }
  const status = home.clipStatus || {};
  const items = clipMatches();
  if (!items.length) {
    delete box.dataset.key;
    const off = status.watcher && status.watcher !== "running";
    box.replaceChildren(el("div", { class: "note" },
      el("b", { text: off ? "The history is off" : (home.clip.length ? "Nothing matches" : "Nothing copied yet") }),
      el("span", { text: off ? "Turn it on and every text you copy is kept here." : "Copy some text anywhere; it shows up here within a second." }),
      off ? el("button", { class: "primary", text: "Turn on", onclick: () => clip("on") }) : null));
    return;
  }
  // Built again only when the list changed, so hovering and selection stay steady.
  const key = items.map((item) => item.id).join(",") + "|" + home.copied + "|" + home.chosen + "|" + (home.clipKind || "");
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  box.replaceChildren(...items.map((item, index) => {
    const node = el("div", { class: "clip" + (index === home.chosen ? " on" : "") + (item.id === home.copied ? " copied" : ""), onclick: (event) => {
      if (event.target.closest("button") || String(getSelection())) return;
      copyClip(item);
    } },
      clipBody(item),
      el("div", { class: "meta" },
        el("span", { text: item.id === home.copied ? "Copied" : ago(item.time) }),
        el("div", { class: "tools" },
          el("button", { class: "ghost", text: "Copy", onclick: () => copyClip(item) }),
          item.file ? el("button", { class: "ghost", text: "Show in Finder", onclick: () => send({ op: "clip", action: "reveal", file: item.file.split("/").pop() }) }) : null,
          el("button", { class: "ghost", text: "Delete", onclick: () => clip("rm", item.id) }))));
    return node;
  }));
}

// Text as text; a picture as a thumbnail served by the app (ulapp://localhost/clip/<file>); a file as its name and size.
function clipBody(item) {
  if (item.kind === "image") {
    const name = item.file.split("/").pop();
    return el("div", { class: "picture" }, el("img", { src: "clip/" + name, alt: item.text, loading: "lazy" }),
      el("div", { class: "caption" }, el("b", { text: item.text }), el("span", { text: bytes(item.size) })));
  }
  if (item.kind === "file") {
    const ext = (item.name.split(".").pop() || "").slice(0, 5).toUpperCase();
    return el("div", { class: "fileitem" }, el("div", { class: "doc", text: item.name.includes(".") ? ext : "FILE" }),
      el("div", { class: "caption" }, el("b", { text: item.name }), el("span", { text: bytes(item.size) })));
  }
  return el("div", { class: "text", text: item.text.length > 2000 ? item.text.slice(0, 2000) + "…" : item.text });
}

function copyClip(item) {
  home.copied = item.id;
  drawClips();
  clip("copy", item.id);
  setTimeout(() => { if (home.copied === item.id) { home.copied = ""; drawClips(); } }, 1400);
}

// The page's own confirmation: WKWebView without a UI delegate answers every
// window.confirm() with false at once, so "Clear…" used to do nothing.
function clearClips() {
  home.clipConfirm = true;
  renderClipboard();
}

function clip(action, id) { send({ op: "clip", action, id: id || null }); }

// ---------- games ----------

const GAMES = [
  { name: "tetris", label: "Tetris", info: "Next and hold, ghost piece" },
  { name: "snake", label: "Snake", info: "Eat, grow, speed up" },
  { name: "minesweeper", label: "Minesweeper", info: "First click is safe", unit: "s", lower: true },
  { name: "invaders", label: "Invaders", info: "Formation, shields, UFO" },
  { name: "chomp", label: "Chomp", info: "Maze chase, four hunters" },
  { name: "dash", label: "Dash", info: "Jump, duck, faster" },
  { name: "pingpong", label: "Ping Pong", info: "vs the bot or a friend" },
  { name: "chess", label: "Chess", info: "vs the bot or a friend", unit: " moves", lower: true },
];
const PALETTE = { red: "#ff5f57", green: "#3ed67a", yellow: "#ffd84d", blue: "#4d8dff", magenta: "#d77bff", cyan: "#4fd8e8", white: "#f4f5f7", gray: "#8b8f98", darkred: "#c0392b", darkyellow: "#c9971c", darkblue: "#3159c9", darkcyan: "#1f9aa8", boardlight: "#b58c63", boarddark: "#78563a", lastlight: "#aaa23a", lastdark: "#8a8228", selected: "#608c56", target: "#b05448", check: "#d63a3a", piecewhite: "#ffffff", pieceblack: "#000000" };
const SCREEN_BG = "#0e1014", SCREEN_FG = "#d9dce3";
const QUADRANTS = { "▘": 1, "▝": 2, "▖": 4, "▌": 5, "▞": 6, "▛": 7, "▗": 8, "▚": 9, "▐": 10, "▜": 11, "▙": 13, "▟": 14 };
const BOX = { "─": "0101", "│": "1010", "┌": "0110", "┐": "0011", "└": "1100", "┘": "1001", "├": "1110", "┤": "1011", "┬": "0111", "┴": "1101", "┼": "1111", "═": "0101", "║": "1010", "╭": "0110", "╮": "0011", "╰": "1100", "╯": "1001" };
const MONO = 'ui-monospace, "SF Mono", Menlo, monospace';
// The game always gets a big grid (every game fits), and the page zooms to
// the part the game draws, so a small board fills the window.
const GRID = { rows: 30, cols: 116 };
const arcade = { id: 0, game: null, level: stored("arcade-level", "normal"), frame: null, records: {}, box: null, view: null, hint: "", ended: "", hover: "" };

function renderGames() {
  header("Games", "Played right here; keys go to the game while it runs");
  const list = el("div", { class: "list" });
  const levels = el("div", { class: "seg" });
  for (const level of ["easy", "normal", "hard"]) {
    levels.appendChild(el("button", { class: level === arcade.level ? "on" : "", text: level[0].toUpperCase() + level.slice(1), onclick: () => { arcade.level = level; store("arcade-level", level); renderGames(); } }));
  }
  list.append(el("h4", { text: "Difficulty" }), levels, el("h4", { text: "Games" }));
  for (const game of GAMES) {
    const best = (arcade.records[game.name] || {})[arcade.level];
    list.appendChild(el("button", { class: "game" + (arcade.id && arcade.game === game.name ? " on" : ""), onclick: () => startGame(game.name) },
      el("b", { text: game.label }, el("span", { text: best == null ? "" : "best " + best + (game.unit || "") })),
      el("small", { text: game.info })));
  }
  list.appendChild(el("button", { class: "ghost", text: "Arcade menu", onclick: () => startGame(null) }));
  const canvas = el("canvas");
  const screen = el("div", { class: "screen" }, canvas, el("div", { class: "idle" }));
  const running = !!arcade.id;
  const label = arcade.game ? (GAMES.find((game) => game.name === arcade.game) || {}).label + " · " + arcade.level : "Arcade menu";
  const bar = el("div", { class: "bar2" },
    el("span", { class: "live" + (running ? " on" : "") }),
    el("span", { text: running ? label : "No game running" }),
    el("span", { class: "hint", text: running ? arcade.hint : "" }),
    el("button", { text: "Pause", onclick: () => gameInput([{ key: "p" }]) }),
    el("button", { text: "Restart", onclick: () => startGame(arcade.game) }),
    el("button", { class: "stop", text: "Stop", onclick: stopGame }));
  for (const button of bar.querySelectorAll("button")) button.disabled = button.textContent === "Restart" ? !running && !arcade.ended : !running;
  $(".content").replaceChildren(el("div", { class: "arcade" }, list, el("div", { class: "stage" }, screen, bar)));
  canvas.addEventListener("mousedown", (event) => { const at = cellAt(event); if (at && arcade.id) { event.preventDefault(); gameInput([{ click: { ...at, button: ["left", "middle", "right"][event.button] || "left" } }]); } });
  canvas.addEventListener("mousemove", (event) => {
    const at = cellAt(event);
    if (!at || !arcade.id || at.y + ":" + at.x === arcade.hover) return;
    arcade.hover = at.y + ":" + at.x;
    gameInput([{ hover: at }]);
  });
  canvas.addEventListener("contextmenu", (event) => event.preventDefault());
  idle();
  drawGame();
}

function idle() {
  const box = $(".arcade .idle");
  if (!box) return;
  box.style.display = arcade.id ? "none" : "flex";
  box.replaceChildren(el("b", { text: "ARCADE" }), el("span", { text: arcade.ended || "Pick a game on the left." }));
  if (arcade.ended) box.appendChild(el("button", { class: "primary", text: "Play again", onclick: () => startGame(arcade.game) }));
}

function startGame(game) {
  arcade.game = game;
  arcade.frame = null;
  arcade.box = null;
  arcade.ended = "";
  arcade.hint = "";
  send({ op: "game-start", game, level: arcade.level, rows: GRID.rows, cols: GRID.cols });
}

function stopGame() { if (arcade.id) send({ op: "game-stop", id: arcade.id }); }
function gameInput(events) { if (arcade.id) send({ op: "game-input", id: arcade.id, events }); }

// The part of the grid the game uses (its last row is the key hint, shown in
// the bar below instead); it only grows during a game, so the view is steady.
function updateBox(frame) {
  let top = Infinity, left = Infinity, bottom = -1, right = -1;
  frame.lines.forEach((runs, row) => {
    if (row === frame.lines.length - 1) return;
    let column = 0;
    for (const [text, , bg] of runs) {
      const chars = [...text];
      chars.forEach((char, index) => {
        if (char !== " " || bg) {
          top = Math.min(top, row); bottom = Math.max(bottom, row);
          left = Math.min(left, column + index); right = Math.max(right, column + index);
        }
      });
      column += chars.length;
    }
  });
  if (bottom < 0) return;
  const box = arcade.box, next = { top, left, bottom, right };
  const area = (b) => (b.bottom - b.top + 1) * (b.right - b.left + 1);
  if (!box) arcade.box = next;
  else if (top < box.top || left < box.left || bottom > box.bottom || right > box.right) {
    // Something drew outside: zoom out at once so nothing is cut off.
    arcade.box = { top: Math.min(box.top, top), left: Math.min(box.left, left), bottom: Math.max(box.bottom, bottom), right: Math.max(box.right, right) };
    arcade.smaller = null;
  } else if (area(next) < area(box) * 0.6) {
    // A smaller picture (a wide menu gave way to the board): zoom in once it
    // has stayed so for a moment (frames come only on change, hence the timer),
    // so a blinking line does not make it jump.
    arcade.smaller = next;
    clearTimeout(arcade.shrink);
    arcade.shrink = setTimeout(() => {
      if (arcade.smaller) { arcade.box = arcade.smaller; arcade.smaller = null; scheduleDraw(); }
    }, 600);
  } else arcade.smaller = null;
  const last = frame.lines[frame.lines.length - 1] || [];
  arcade.hint = last.map((run) => run[0]).join("").trim();
}

function measure() {
  const context = document.createElement("canvas").getContext("2d");
  context.font = "100px " + MONO;
  return context.measureText("M").width / 100;
}
const CELL_RATIO = measure();

function layout(canvas) {
  const box = arcade.box || { top: 0, left: 0, bottom: GRID.rows - 2, right: GRID.cols - 1 };
  const width = canvas.clientWidth, height = canvas.clientHeight;
  const cols = box.right - box.left + 3, rows = box.bottom - box.top + 3; // a cell of margin around it
  const font = Math.min(width / (cols * CELL_RATIO), height / (rows * 1.22));
  const cell = { w: font * CELL_RATIO, h: font * 1.22, font };
  const x = (width - cols * cell.w) / 2 - (box.left - 1) * cell.w;
  const y = (height - rows * cell.h) / 2 - (box.top - 1) * cell.h;
  return { cell, x, y };
}

function cellAt(event) {
  if (!arcade.view) return null;
  const rect = event.target.getBoundingClientRect();
  const { cell, x, y } = arcade.view;
  const column = Math.floor((event.clientX - rect.left - x) / cell.w), row = Math.floor((event.clientY - rect.top - y) / cell.h);
  return column >= 0 && row >= 0 && column < GRID.cols && row < GRID.rows ? { y: row, x: column } : null;
}

let drawPending = false;
function scheduleDraw() {
  if (drawPending) return;
  drawPending = true;
  requestAnimationFrame(() => { drawPending = false; drawGame(); });
}

function drawGame() {
  const canvas = $(".arcade canvas");
  if (!canvas) return;
  const ratio = devicePixelRatio || 1;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.fillStyle = SCREEN_BG;
  context.fillRect(0, 0, width, height);
  const frame = arcade.frame;
  if (!frame || !arcade.id) { arcade.view = null; return; }
  const view = layout(canvas);
  arcade.view = view;
  const { cell, x: ox, y: oy } = view;
  context.textAlign = "center";
  context.textBaseline = "middle";
  frame.lines.forEach((runs, row) => {
    if (row === frame.lines.length - 1) return;
    let column = 0;
    const y = oy + row * cell.h;
    for (const [text, fgName, bgName, flags] of runs) {
      let fg = PALETTE[fgName] || SCREEN_FG, bg = PALETTE[bgName] || null;
      if (flags & 2) { const swap = fg; fg = bg || SCREEN_BG; bg = swap; }
      context.font = (flags & 1 ? "700 " : "400 ") + cell.font + "px " + MONO;
      context.globalAlpha = flags & 4 ? .55 : 1;
      const chars = [...text];
      if (bg) {
        const left = Math.round(ox + column * cell.w), top = Math.round(y);
        context.fillStyle = bg;
        context.fillRect(left, top, Math.round(ox + (column + chars.length) * cell.w) - left, Math.round(y + cell.h) - top);
      }
      for (const char of chars) {
        if (char !== " ") drawCell(context, char, ox + column * cell.w, y, cell.w, cell.h, fg);
        column += 1;
      }
    }
  });
  context.globalAlpha = 1;
}

// Box and block characters are painted as shapes, so lines and blocks join without gaps.
function drawCell(context, char, x, y, w, h, color) {
  const box = BOX[char];
  if (box) {
    context.strokeStyle = color;
    context.lineWidth = Math.max(1, Math.round(w / 8));
    const cx = Math.round(x + w / 2) + .5, cy = Math.round(y + h / 2) + .5;
    context.beginPath();
    if (box[0] === "1") { context.moveTo(cx, y); context.lineTo(cx, cy); }
    if (box[1] === "1") { context.moveTo(cx, cy); context.lineTo(x + w, cy); }
    if (box[2] === "1") { context.moveTo(cx, cy); context.lineTo(cx, y + h); }
    if (box[3] === "1") { context.moveTo(x, cy); context.lineTo(cx, cy); }
    context.stroke();
    return;
  }
  const left = Math.round(x), top = Math.round(y), right = Math.round(x + w), bottom = Math.round(y + h);
  const shade = { "█": 1, "▓": .75, "▒": .5, "░": .25 }[char];
  if (shade) {
    const alpha = context.globalAlpha;
    context.globalAlpha = alpha * shade;
    context.fillStyle = color;
    context.fillRect(left, top, right - left, bottom - top);
    context.globalAlpha = alpha;
    return;
  }
  const quad = QUADRANTS[char];
  if (quad) {
    const midX = Math.round(x + w / 2), midY = Math.round(y + h / 2);
    context.fillStyle = color;
    if (quad & 1) context.fillRect(left, top, midX - left, midY - top);
    if (quad & 2) context.fillRect(midX, top, right - midX, midY - top);
    if (quad & 4) context.fillRect(left, midY, midX - left, bottom - midY);
    if (quad & 8) context.fillRect(midX, midY, right - midX, bottom - midY);
    return;
  }
  if (char === "▀" || char === "▄") {
    const middle = Math.round(y + h / 2);
    context.fillStyle = color;
    context.fillRect(left, char === "▀" ? top : middle, right - left, char === "▀" ? middle - top : bottom - middle);
    return;
  }
  context.fillStyle = color;
  // Chess pieces get the text-style selector: some fonts draw ♟ as a color emoji.
  const piece = char >= "♔" && char <= "♟";
  context.fillText(piece ? char + "︎" : char, x + w / 2, y + h / 2 + 1);
}

const GAME_KEYS = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Enter: "enter", Escape: "esc", Backspace: "backspace", Space: " " };
// Letters by their place on the keyboard (event.code), so WASD works on any layout.
function gameKeyName(event) {
  if (GAME_KEYS[event.key]) return GAME_KEYS[event.key];
  if (GAME_KEYS[event.code]) return GAME_KEYS[event.code];
  if (/^Key[A-Z]$/.test(event.code)) return event.shiftKey ? event.code[3] : event.code[3].toLowerCase();
  if (/^Digit\d$/.test(event.code)) return event.code[5];
  return event.key.length === 1 ? event.key : null;
}

function gameKeys(event, release) {
  if (home.section !== "games" || !arcade.id || event.metaKey || event.ctrlKey || event.altKey) return false;
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) return false;
  const key = gameKeyName(event);
  if (!key) return false;
  event.preventDefault();
  gameInput([release ? { release: key } : { key }]);
  return true;
}

// ---------- desk ----------

function isDeskPart(section) { return SECTIONS.some((item) => item.id === section && item.desk); }

function renderDesk() {
  header(SECTIONS.find((item) => item.id === home.section).label, "");
  const text = home.desk.state === "error" ? home.desk.text : "Starting the desk…";
  $(".content").replaceChildren(el("div", { class: "deskwait" }, el("div", { class: "note" },
    el("span", { text }), home.desk.state === "error" ? el("button", { text: "Try again", onclick: () => send({ op: "section", section: home.section }) }) : null)));
  deskArea();
}

// Rust lays the desk's own page over the content area: tell it where that is.
function deskArea() {
  if (!isDeskPart(home.section)) return;
  const rect = $(".main").getBoundingClientRect();
  send({ op: "desk-area", x: rect.left, y: rect.top, width: rect.width, height: rect.height });
}

// ---------- keys and messages ----------

document.addEventListener("keydown", (event) => {
  if (event.metaKey && !event.shiftKey && !event.altKey) {
    const section = SECTIONS.find((item) => item.key === event.key);
    if (section) { event.preventDefault(); go(section.id); return; }
    if (event.key === ",") { event.preventDefault(); go("settings"); return; }
  }
  if (gameKeys(event, false)) return;
  if (home.section === "clipboard" && !event.metaKey) {
    const items = clipMatches();
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      home.chosen = Math.max(0, Math.min(items.length - 1, home.chosen + (event.key === "ArrowDown" ? 1 : -1)));
      drawClips();
      $(".clip.on")?.scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter" && items[home.chosen]) {
      event.preventDefault();
      copyClip(items[home.chosen]);
    }
  }
});
document.addEventListener("keyup", (event) => { gameKeys(event, true); });

let resizeTimer = 0;
window.addEventListener("resize", () => {
  if (home.section === "games") scheduleDraw();
  if (home.section === "system") for (const canvas of document.querySelectorAll("canvas.spark")) drawSpark(canvas);
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(deskArea, 60);
});

// ---------- settings ----------
// app.toml as a form. Every change is sent at once; Rust checks it, writes the
// file (comments kept) and answers with what is stored now, or the reason it
// refused, so the page never shows a value that does not apply.

const KEY_CODES = {
  Space: "space", Enter: "enter", Tab: "tab", Backspace: "backspace", Delete: "delete",
  ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Home: "home", End: "end",
  PageUp: "pageup", PageDown: "pagedown", Comma: "comma", Period: "period", Slash: "slash",
  Semicolon: "semicolon", Quote: "quote", Minus: "minus", Equal: "equal", Backquote: "backquote",
  BracketLeft: "bracketleft", BracketRight: "bracketright", Backslash: "backslash",
};
const KEY_SIGNS = { space: "Space", enter: "↩", tab: "⇥", escape: "⎋", backspace: "⌫", delete: "⌦", up: "↑", down: "↓", left: "←", right: "→",
  home: "↖", end: "↘", pageup: "⇞", pagedown: "⇟", comma: ",", period: ".", slash: "/", semicolon: ";", quote: "'", minus: "-",
  equal: "=", backquote: "`", bracketleft: "[", bracketright: "]", backslash: "\\" };

function keyName(event) {
  const code = event.code || "";
  if (/^Key[A-Z]$/.test(code)) return code.slice(3).toLowerCase();
  if (/^Digit[0-9]$/.test(code)) return code.slice(5);
  if (/^F([1-9]|1[0-9]|20)$/.test(code)) return code.toLowerCase();
  return KEY_CODES[code] || null;
}

function shortcutText(event) {
  const key = keyName(event);
  if (!key) return null;
  return [event.ctrlKey && "ctrl", event.altKey && "alt", event.shiftKey && "shift", event.metaKey && "cmd", key].filter(Boolean).join("+");
}

function prettyKeys(text) {
  if (!text) return "None";
  const words = text.split("+");
  const key = words.pop();
  const signs = { ctrl: "⌃", alt: "⌥", shift: "⇧", cmd: "⌘" };
  return ["ctrl", "alt", "shift", "cmd"].filter((word) => words.includes(word)).map((word) => signs[word]).join("") + (KEY_SIGNS[key] || key.toUpperCase());
}

// The window hidden or left while a shortcut is recorded: stop, or the page keeps
// swallowing keys after Rust has put its own hotkeys back.
window.addEventListener("blur", () => stopRecording());

function stopRecording() {
  if (!home.recording) return;
  document.removeEventListener("keydown", home.recording.listener, true);
  home.recording.button.classList.remove("recording");
  home.recording.button.textContent = prettyKeys(home.recording.value);
  home.recording = null;
  send({ op: "recording", on: false });
}

// A button that shows a shortcut; clicked, it takes the next key combination.
function recorder(value, save) {
  const button = el("button", { class: "keys", text: prettyKeys(value) });
  button.onclick = () => {
    if (home.recording) { const same = home.recording.button === button; stopRecording(); if (same) return; }
    button.classList.add("recording");
    button.textContent = "Type the shortcut…";
    const listener = (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.key === "Escape" && !event.ctrlKey && !event.altKey && !event.metaKey) { stopRecording(); return; }
      const text = shortcutText(event);
      if (!text) return; // a modifier alone: wait for the key
      home.recording.value = text;
      stopRecording();
      save(text);
    };
    home.recording = { button, listener, value };
    document.addEventListener("keydown", listener, true);
    send({ op: "recording", on: true });
  };
  return button;
}

function prefsCopy() {
  const current = home.prefs.settings;
  return { ...current, hotkeys: current.hotkeys.map((item) => ({ ...item })), menubar: [...current.menubar], sys: [...(current.sys || [])] };
}

function savePrefs(change) {
  const next = prefsCopy();
  change(next);
  home.prefs.settings = next; // shown at once; Rust answers with the stored values
  renderSettings();
  send({ op: "settings-save", settings: next });
}

function prefRow(label, note, ...controls) {
  return el("div", { class: "prefrow" },
    el("div", { class: "preflabel" }, el("b", { text: label }), note ? el("small", { text: note }) : null),
    el("div", { class: "prefcontrols" }, ...controls));
}

function segmented(options, value, pick) {
  return el("div", { class: "seg" }, ...options.map(([id, label]) => el("button", { class: id === value ? "on" : "", text: label, onclick: () => id !== value && pick(id) })));
}

function toggle(on, change) {
  const box = el("input", { type: "checkbox", class: "switch" });
  box.checked = !!on;
  box.addEventListener("change", () => change(box.checked));
  return box;
}

function commandSelect(value, change, templates = true) {
  const select = el("select");
  select.appendChild(el("option", { value: "", text: "Choose a command" }));
  // A shortcut may open a saved template (its name is chosen in the next box).
  if (templates) select.appendChild(el("option", { value: "template", text: "A template (its windows)" }));
  for (const item of [...home.items].sort((a, b) => a.title.localeCompare(b.title))) {
    const option = el("option", { value: item.name, text: `${item.title} (ul ${item.name})` });
    select.appendChild(option);
  }
  if (value && value !== "template" && !home.items.some((item) => item.name === value)) select.appendChild(el("option", { value, text: `ul ${value} (not installed)` }));
  select.value = value || "";
  select.addEventListener("change", () => change(select.value));
  return select;
}

function actionSelect(command, value, change) {
  if (command === "template") {
    const select = el("select");
    const names = (home.templates || []).map((template) => template.name);
    if (value && !names.includes(value)) names.push(value);
    select.appendChild(el("option", { value: "", text: names.length ? "Choose a template" : "No templates yet (ul template save)" }));
    for (const name of names) select.appendChild(el("option", { value: name, text: name }));
    select.value = value || "";
    select.addEventListener("change", () => select.value && change(select.value));
    return select;
  }
  const item = home.items.find((entry) => entry.name === command);
  const choices = [["panel", item && item.section ? "Open it in Unlaw" : "Open its panel"], ["run", "Run it"]];
  if (item && item.open) choices.push(["open", "Open its page"]);
  for (const action of (item && item.actions) || []) choices.push([action.id, action.label]);
  if (value && !choices.some(([id]) => id === value)) choices.push([value, value]);
  const select = el("select");
  for (const [id, label] of choices) select.appendChild(el("option", { value: id, text: label }));
  select.value = value || "panel";
  select.addEventListener("change", () => change(select.value));
  return select;
}

function renderSettings() {
  header("Settings", "Unlaw.app: shortcuts, menu bar, look");
  const content = $(".content");
  const prefs = home.prefs;
  if (!prefs) { content.replaceChildren(el("div", { class: "note", text: "Reading the settings…" })); return; }
  const settings = prefs.settings;
  const groups = [];
  if (prefs.error) groups.push(el("div", { class: "preferror", text: "Not saved: " + prefs.error }));
  for (const warning of prefs.warnings || []) groups.push(el("div", { class: "prefwarn", text: warning }));

  const hotkeys = el("div", { class: "prefgroup" },
    prefRow("Command palette", "Search and run any command from any app", recorder(settings.palette, (keys) => savePrefs((next) => { next.palette = keys; }))));
  settings.hotkeys.forEach((binding, index) => {
    const edit = (change) => savePrefs((next) => change(next.hotkeys[index]));
    hotkeys.appendChild(prefRow("Shortcut " + (index + 1), null,
      recorder(binding.keys, (keys) => edit((item) => { item.keys = keys; })),
      commandSelect(binding.command, (name) => edit((item) => { item.command = name; item.action = name === "template" ? (home.templates || [])[0]?.name || "" : "panel"; })),
      actionSelect(binding.command, binding.action, (action) => edit((item) => { item.action = action; })),
      el("button", { class: "ghost danger", title: "Remove", text: "Remove", onclick: () => savePrefs((next) => next.hotkeys.splice(index, 1)) })));
  });
  if (home.draft) {
    // A new shortcut is kept here until it names a command (app.toml would refuse it without one).
    const draft = home.draft;
    hotkeys.appendChild(prefRow("New shortcut", "Choose the command",
      recorder(draft.keys, (keys) => { draft.keys = keys; renderSettings(); }),
      commandSelect("", (name) => {
        const first = (home.templates || [])[0];
        if (!name || (name === "template" && !first)) return;
        home.draft = null;
        savePrefs((next) => next.hotkeys.push({ keys: draft.keys, command: name, action: name === "template" ? first.name : "panel" }));
      }),
      el("button", { class: "ghost", text: "Cancel", onclick: () => { home.draft = null; renderSettings(); } })));
  } else {
    hotkeys.appendChild(el("div", { class: "prefadd" }, el("button", { class: "ghost", text: "Add a shortcut…", onclick: addShortcut })));
  }

  const pinned = el("div", { class: "pinned" });
  settings.menubar.forEach((name, index) => {
    const app = name.startsWith("app:") ? name.slice(4) : null;
    const item = app ? { name, title: app, icon: "app", app_icon: app } : home.items.find((entry) => entry.name === name);
    const move = (by) => savePrefs((next) => { const [taken] = next.menubar.splice(index, 1); next.menubar.splice(index + by, 0, taken); });
    pinned.appendChild(el("div", { class: "pin" },
      el("span", { class: "glyph" }, item ? commandIcon(item) : icon("command")),
      el("b", { text: item ? item.title : name }),
      el("small", { text: app ? `ul app ${app}` : item ? `ul ${name}` : `ul ${name} · not installed` }),
      el("div", { class: "grow" }),
      el("button", { class: "ghost", title: "Move left", text: "←", disabled: index === 0 ? "" : null, onclick: () => move(-1) }),
      el("button", { class: "ghost", title: "Move right", text: "→", disabled: index === settings.menubar.length - 1 ? "" : null, onclick: () => move(1) }),
      el("button", { class: "ghost danger", text: "Remove", onclick: () => savePrefs((next) => next.menubar.splice(index, 1)) })));
  });
  if (!settings.menubar.length) pinned.appendChild(el("div", { class: "muted", text: "Only the UL menu." }));
  // Open app asks which application (in the palette); the menu bar takes commands, not templates.
  const adding = commandSelect("", (name) => {
    if (name === "app") send({ op: "pin", name: "app" });
    else if (name) savePrefs((next) => { if (!next.menubar.includes(name)) next.menubar.push(name); });
  }, false);
  adding.options[0].textContent = "Add to the menu bar…";
  const menubar = el("div", { class: "prefgroup" },
    el("div", { class: "prefrow column" }, el("div", { class: "preflabel" }, el("b", { text: "Shown in the menu bar" }), el("small", { text: "Left to right, next to the UL menu" })), pinned, adding),
    prefRow("Live status", "Readings next to the items that have them", toggle(settings.show_status, (on) => savePrefs((next) => { next.show_status = on; }))),
    el("div", { class: "prefrow column" },
      el("div", { class: "preflabel" }, el("b", { text: "System item shows" }), el("small", { text: "Pick the readings; none leaves only the chip icon" })),
      el("div", { class: "chips" }, ...(prefs.sys_metrics || []).map((metric) => {
        const on = (settings.sys || []).includes(metric.id);
        return el("button", { class: "chip" + (on ? " on" : ""), text: metric.label, onclick: () => savePrefs((next) => {
          next.sys = on ? next.sys.filter((id) => id !== metric.id) : [...next.sys, metric.id];
        }) });
      }))));

  const restart = prefs.running_dock !== settings.dock ? "Takes effect the next time Unlaw starts" : "Off: a menu bar app only, no window in the Dock";
  const look = el("div", { class: "prefgroup" },
    prefRow("Appearance", null, segmented([["auto", "Auto"], ["light", "Light"], ["dark", "Dark"]], settings.theme, (theme) => savePrefs((next) => { next.theme = theme; }))),
    prefRow("Show in the Dock", restart, toggle(settings.dock, (on) => savePrefs((next) => { next.dock = on; }))));

  const count = el("input", { type: "number", min: "0", max: "1000", value: String(prefs.clip_files ?? 15), class: "count" });
  const saveCount = () => {
    const value = Math.round(Number(count.value));
    if (Number.isFinite(value) && value >= 0 && value <= 1000 && value !== prefs.clip_files) send({ op: "clip-files", count: value });
  };
  count.addEventListener("change", saveCount);
  count.addEventListener("keydown", (event) => { if (event.key === "Enter") count.blur(); });
  const clipboard = el("div", { class: "prefgroup" },
    prefRow("Images and files to keep", home.prefsNote || "Pictures and copied files are saved as files; older ones are deleted (0 keeps none)", count));

  const files = el("div", { class: "prefgroup" },
    prefRow("Settings file", prefs.path, el("button", { class: "ghost", text: "Open in editor", onclick: () => send({ op: "settings-file" }) })));

  content.replaceChildren(el("div", { class: "prefs" }, ...groups,
    el("h2", { text: "Keyboard shortcuts" }), hotkeys,
    el("h2", { text: "Menu bar" }), menubar,
    el("h2", { text: "Clipboard" }), clipboard,
    el("h2", { text: "Look" }), look,
    el("h2", { text: "Advanced" }), files));
}

function addShortcut() {
  const button = recorder("", (keys) => { home.draft = { keys }; renderSettings(); });
  const box = $(".prefadd");
  if (box) box.replaceChildren(button, el("small", { class: "muted", text: "Esc cancels" }));
  button.click();
}

window.ul = {
  receive(message) {
    switch (message.type) {
      case "init":
        applyTheme(message.theme);
        home.items = message.items || [];
        home.version = message.version || "";
        build();
        $(".version").textContent = "Unlaw " + home.version;
        if (message.update) showUpdate(message.update);
        home.section = "";
        go(message.section || "commands");
        break;
      case "theme":
        applyTheme(message.theme);
        break;
      case "update":
        showUpdate(message);
        break;
      case "list":
        home.items = message.items || [];
        if (home.section === "commands") drawTiles();
        break;
      case "section":
        go(message.section, false);
        break;
      case "play":
        go("games");
        startGame(message.game || null);
        break;
      case "sys":
        if (message.data) {
          home.sys = message.data;
          home.sysError = "";
          remember("cpu", message.data.cpu && message.data.cpu.usage_percent);
          const mem = message.data.memory || {};
          remember("mem", mem.total_bytes ? mem.used_bytes / mem.total_bytes * 100 : null);
          remember("gpu", message.data.gpu && message.data.gpu.usage_percent);
          const net = message.data.network || {}, io = message.data.io || {}, battery = message.data.battery || {};
          remember("down", net.download_bytes_per_sec);
          remember("up", net.upload_bytes_per_sec);
          remember("read", io.read_bytes_per_sec);
          remember("write", io.write_bytes_per_sec);
          remember("power", battery.system_power_watts);
        } else {
          home.sysError = message.error || "ul sys failed";
        }
        if (home.section === "system") renderSystem();
        break;
      case "clip":
        if (message.items) { home.clip = message.items; home.clipError = ""; } else if (home.clip === null) home.clipError = message.error || "ul clip failed";
        if (message.status) home.clipStatus = message.status;
        if (home.section === "clipboard") renderClipboard();
        break;
      case "games":
        arcade.records = message.records || {};
        if (home.section === "games" && !arcade.id) renderGames();
        break;
      case "game-started":
        arcade.id = message.id;
        if (home.section === "games") renderGames();
        break;
      case "frame":
        if (message.id !== arcade.id) break;
        arcade.frame = message.frame;
        updateBox(message.frame);
        const hint = $(".arcade .hint");
        if (hint && hint.textContent !== arcade.hint) hint.textContent = arcade.hint;
        scheduleDraw();
        break;
      case "game-ended":
        // A game that never started carries an id the page never saw: still show why it failed.
        if (message.id !== arcade.id && !(message.error && !arcade.frame)) break;
        arcade.id = 0;
        arcade.frame = null;
        arcade.ended = message.error || "Game closed. Pick another one or play again.";
        if (home.section === "games") { renderGames(); send({ op: "games" }); }
        break;
      case "templates":
        home.templates = message.items || (message.error ? home.templates : []);
        home.templatesError = message.error || "";
        if (home.section === "templates") renderTemplates();
        if (home.section === "settings" && !home.recording) renderSettings();
        break;
      case "template-done": {
        home.templateBusy = "";
        const verb = message.op === "template-rm" ? "Deleted" : "Opened";
        home.templateNote = message.ok
          ? (message.op === "template-rm" ? { ok: true, title: `${verb} ${message.name}` } : null)
          : { ok: false, title: `${message.name}: ${message.op === "template-rm" ? "could not delete" : "some windows did not open"}`, text: message.text };
        if (home.section === "templates") renderTemplates();
        break;
      }
      case "clip-files":
        if (home.prefs) home.prefs.clip_files = message.count;
        home.prefsNote = message.error || "";
        if (home.section === "settings") renderSettings();
        break;
      case "settings":
        home.prefs = message;
        if (home.section === "settings") renderSettings();
        break;
      case "desk":
        home.desk = { state: message.state, text: message.text || "" };
        if (isDeskPart(home.section)) renderDesk();
        break;
    }
  },
};

matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => send({ op: "theme" }));
send({ op: "ready" });
