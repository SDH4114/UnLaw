// Unlaw.app pages: the palette and a command's panel. Everything shown comes
// from commands and config files, so nodes are built with textContent only,
// never innerHTML. Rust sends state with window.ul.receive(...); the page asks
// for things with window.ipc.postMessage(JSON) and never sees argv: it sends a
// command name, an action id or a button index and field values.
"use strict";

const ICONS = {
  command: ["M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z"],
  cup: ["M4 9h13v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5z", "M17 11h1.5a2.5 2.5 0 0 1 0 5H17", "M8 3v3M12 3v3"],
  cpu: ["M7 7h10v10H7z", "M10 10h4v4h-4z", "M9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4"],
  board: ["M4 5h16v14H4z", "M9.5 5v14M14.5 5v14"],
  clock: ["M12 21a8 8 0 1 0 0-16 8 8 0 0 0 0 16z", "M12 9v4l2.5 2", "M10 2h4"],
  clipboard: ["M9 4h6v3H9z", "M9 5.5H6v15h12v-15h-3", "M9 12h6M9 16h4"],
  cloud: ["M7 18h10a4 4 0 0 0 .5-7.97A6 6 0 0 0 6.1 9.1 4.5 4.5 0 0 0 7 18z"],
  music: ["M9 18V6l11-2v12", "M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM17 19a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"],
  play: ["M3 6h18v12H3z", "M10 9.5v5l4.5-2.5z"],
  camera: ["M4 8h3l2-3h6l2 3h3v11H4z", "M12 16.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"],
  record: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"],
  download: ["M12 4v11", "M7.5 10.5 12 15l4.5-4.5", "M5 20h14"],
  git: ["M6 3v12", "M6 21a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM18 9a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z", "M18 9a9 9 0 0 1-9 9"],
  terminal: ["M3 5h18v14H3z", "M7 10l3 2.5L7 15M12.5 15H17"],
  folder: ["M3 6h6l2 2h10v11H3z"],
  code: ["M9 7l-5 5 5 5M15 7l5 5-5 5"],
  chat: ["M4 5h16v11H9l-5 4z"],
  spark: ["M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z", "M19 16l.7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7z"],
  game: ["M6 9h12a4 4 0 0 1 4 4v1a4 4 0 0 1-7 2.6L14 15h-4l-1 1.6A4 4 0 0 1 2 14v-1a4 4 0 0 1 4-4z", "M7 12v3M5.5 13.5h3M15.5 13h.01M17.5 14.5h.01"],
  archive: ["M3 5h18v4H3z", "M5 9v10h14V9", "M10 13h4"],
  globe: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M3 12h18M12 3c2.5 2.6 3.7 5.6 3.7 9s-1.2 6.4-3.7 9c-2.5-2.6-3.7-5.6-3.7-9S9.5 5.6 12 3z"],
  app: ["M5 5h6v6H5zM13 5h6v6h-6zM5 13h6v6H5zM13 13h6v6h-6z"],
  bolt: ["M13 2 4 14h7l-1 8 9-12h-7z"],
  gear: ["M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z", "M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"],
  search: ["M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4"],
  open: ["M14 4h6v6", "M20 4l-9 9", "M18 14v6H4V6h6"],
};

const SVG = "http://www.w3.org/2000/svg";

function icon(name) {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon");
  for (const d of ICONS[name] || ICONS.command) {
    const path = document.createElementNS(SVG, "path");
    path.setAttribute("d", d);
    svg.appendChild(path);
  }
  return svg;
}

function el(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child) node.appendChild(child);
  return node;
}

function send(message) {
  window.ipc.postMessage(JSON.stringify(message));
}

const state = { view: "palette", items: [], warnings: [], rows: [], selected: 0, spec: null, values: {}, status: null, pinned: false };

function applyTheme(theme) {
  const dark = theme === "dark" || (theme === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

// ---------- Palette ----------

function words(text) {
  return text.toLowerCase().split(/\s+/).filter(Boolean);
}

function matches(haystack, query) {
  const text = haystack.toLowerCase();
  return query.every((word) => text.includes(word));
}

// Commands first (a name that starts with the query on top), then actions.
function paletteRows(items, queryText) {
  const query = words(queryText);
  const commands = [];
  const actions = [];
  for (const item of items) {
    if (!query.length || matches(`${item.name} ${item.title} ${item.summary}`, query)) commands.push({ kind: "command", item });
    for (const action of item.actions) {
      if (query.length && matches(`${item.name} ${item.title} ${action.label}`, query)) actions.push({ kind: "action", item, action });
    }
  }
  const first = query[0] || "";
  const rank = (row) => (row.item.name.startsWith(first) || row.item.title.toLowerCase().startsWith(first) ? 0 : 1) + (row.item.pinned ? 0 : 0.5);
  commands.sort((a, b) => rank(a) - rank(b) || a.item.title.localeCompare(b.item.title));
  return commands.concat(actions);
}

function renderPalette() {
  const list = document.querySelector(".list");
  const query = document.querySelector(".search input").value;
  state.rows = paletteRows(state.items, query);
  state.selected = Math.min(state.selected, Math.max(0, state.rows.length - 1));
  list.replaceChildren();
  if (!state.rows.length) {
    list.appendChild(el("div", { class: "empty", text: state.items.length ? "Nothing matches" : "Loading commands…" }));
  }
  state.rows.forEach((row, index) => {
    const item = row.item;
    const title = el("div", { class: "title" });
    if (row.kind === "action") {
      title.appendChild(el("span", { text: row.action.label }));
      title.appendChild(el("span", { class: "of", text: `  ${item.title}` }));
    } else {
      title.textContent = item.title;
    }
    const tags = el("div", { class: "tags" });
    if (row.kind === "command") {
      if (item.pinned) tags.appendChild(el("span", { class: "pin", title: "In the menu bar" }));
      if (item.terminal) tags.appendChild(el("span", { text: "terminal" }));
      else if (item.open) tags.appendChild(el("span", { text: "window" }));
      else if (item.panel || item.actions.length) tags.appendChild(el("span", { text: "panel" }));
    }
    const node = el("div", { class: `row ${row.kind}${index === state.selected ? " on" : ""}` },
      el("div", { class: "glyph" }, icon(item.icon)),
      el("div", { class: "what" }, title, el("div", { class: "summary", text: row.kind === "action" ? `ul ${item.name}` : item.summary || `ul ${item.name}` })),
      tags);
    node.addEventListener("mousemove", () => select(index, false));
    node.addEventListener("click", () => activate(index));
    node.addEventListener("contextmenu", (event) => { event.preventDefault(); select(index, false); contextMenu(event, row); });
    list.appendChild(node);
  });
  const warn = document.querySelector(".foot .warn");
  warn.textContent = state.warnings.length ? `${state.warnings.length} problem${state.warnings.length > 1 ? "s" : ""}` : "";
  warn.title = state.warnings.join("\n");
}

function select(index, scroll = true) {
  if (index < 0 || index >= state.rows.length || index === state.selected) return;
  const nodes = document.querySelectorAll(".list .row");
  nodes[state.selected]?.classList.remove("on");
  state.selected = index;
  nodes[index]?.classList.add("on");
  if (scroll) nodes[index]?.scrollIntoView({ block: "nearest" });
}

function activate(index, how) {
  const row = state.rows[index];
  if (!row) return;
  if (row.kind === "action") {
    if (row.action.confirm && !confirmInPalette(row)) return;
    send({ op: "action", name: row.item.name, id: row.action.id });
  } else {
    send({ op: how || "default", name: row.item.name });
  }
}

// The palette has no room for a confirm box; such actions open the panel instead.
function confirmInPalette(row) {
  send({ op: "panel", name: row.item.name });
  return false;
}

function closeMenu() {
  document.querySelector(".menu")?.remove();
}

function contextMenu(event, row) {
  closeMenu();
  const item = row.item;
  const entry = (label, op) => el("button", { text: label, onclick: () => { closeMenu(); send({ op, name: item.name }); } });
  const menu = el("div", { class: "menu" },
    entry("Open panel", "panel"),
    item.open ? entry("Open window", "open") : null,
    entry("Run in terminal", "terminal"),
    entry(item.pinned ? "Unpin from the menu bar" : "Pin to the menu bar", item.pinned ? "unpin" : "pin"));
  menu.style.left = `${Math.min(event.clientX, innerWidth - 200)}px`;
  menu.style.top = `${Math.min(event.clientY, innerHeight - 150)}px`;
  document.body.appendChild(menu);
}

function paletteKeys(event) {
  const row = state.rows[state.selected];
  if (event.key === "Escape") { if (document.querySelector(".menu")) closeMenu(); else send({ op: "hide" }); }
  else if (event.key === "ArrowDown" || (event.ctrlKey && event.key === "n")) select(state.selected + 1);
  else if (event.key === "ArrowUp" || (event.ctrlKey && event.key === "p")) select(state.selected - 1);
  else if (event.key === "Enter") activate(state.selected, event.metaKey ? "terminal" : undefined);
  else if (event.key === "Tab" && row) send({ op: "panel", name: row.item.name });
  else if (event.metaKey && event.key.toLowerCase() === "p" && row) send({ op: row.item.pinned ? "unpin" : "pin", name: row.item.name });
  else if (event.metaKey && event.key === ",") send({ op: "settings" });
  else return;
  event.preventDefault();
}

function buildPalette() {
  const input = el("input", { placeholder: "Search commands and actions", spellcheck: "false", autocomplete: "off" });
  input.addEventListener("input", () => { state.selected = 0; renderPalette(); });
  document.body.replaceChildren(el("div", { class: "glass" },
    el("div", { class: "search" }, icon("search"), input),
    el("div", { class: "list" }),
    el("div", { class: "foot" },
      el("span", {}, el("kbd", { text: "↩" }), document.createTextNode(" run")),
      el("span", {}, el("kbd", { text: "⇥" }), document.createTextNode(" panel")),
      el("span", {}, el("kbd", { text: "⌘↩" }), document.createTextNode(" terminal")),
      el("span", {}, el("kbd", { text: "⌘P" }), document.createTextNode(" pin")),
      el("span", { class: "grow" }),
      el("span", { class: "warn", onclick: () => send({ op: "settings" }) }))));
  document.addEventListener("keydown", paletteKeys);
  document.addEventListener("click", (event) => { if (!event.target.closest(".menu")) closeMenu(); });
  renderPalette();
}

// ---------- Panel ----------

function statusPill() {
  if (!state.status || !state.status.text) return null;
  return el("span", { class: `pill ${state.status.state || ""}`, text: state.status.text });
}

function fieldNode(field) {
  const value = state.values[field.id];
  const set = (next) => { state.values[field.id] = next; };
  if (field.type === "toggle") {
    const toggle = el("button", { class: `switch${value ? " on" : ""}`, role: "switch", "aria-label": field.label });
    toggle.addEventListener("click", () => { set(!state.values[field.id]); toggle.classList.toggle("on", state.values[field.id]); });
    return el("div", { class: "field toggle" }, el("label", { text: field.label }), toggle);
  }
  let input;
  if (field.type === "choice" && field.options.length <= 6) {
    input = el("div", { class: "seg" });
    for (const option of field.options) {
      const button = el("button", { text: option, class: option === value ? "on" : "" });
      button.addEventListener("click", () => {
        set(option);
        for (const other of input.children) other.classList.toggle("on", other === button);
      });
      input.appendChild(button);
    }
  } else if (field.type === "choice") {
    input = el("select");
    for (const option of field.options) input.appendChild(el("option", { text: option, value: option }));
    input.value = value;
    input.addEventListener("change", () => set(input.value));
  } else {
    const type = { number: "number", time: "time", date: "date" }[field.type] || "text";
    input = el("input", { type, spellcheck: "false", autocomplete: "off" });
    if (field.placeholder) input.placeholder = field.placeholder;
    else if (field.type === "duration") input.placeholder = "25m, 1h30m, 90s";
    input.value = value;
    input.addEventListener("input", () => set(input.value));
    input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); submit(0); } });
  }
  return el("div", { class: "field" }, el("label", { text: field.label }), input);
}

function submit(index) {
  const spec = state.spec;
  if (!spec.panel || !spec.panel.buttons[index]) return;
  const button = spec.panel.buttons[index];
  ask(button.confirm, () => send({ op: "submit", name: spec.name, button: index, values: state.values }));
}

// A confirm box inside the panel; nothing runs until it is answered.
function ask(question, then) {
  if (!question) return then();
  const box = document.querySelector(".confirm-slot");
  box.replaceChildren(el("div", { class: "confirm" },
    el("span", { text: question }),
    el("button", { class: "ghost", text: "Cancel", onclick: () => { box.replaceChildren(); resize(); } }),
    el("button", { class: "primary", text: "Yes", onclick: () => { box.replaceChildren(); then(); } })));
  resize();
}

function renderPanel() {
  const spec = state.spec;
  if (!spec) return;
  const parts = [];
  parts.push(el("div", { class: "head" },
    el("div", { class: "glyph" }, icon(spec.icon)),
    el("div", { class: "name" }, el("b", { text: spec.title }), el("span", { text: spec.summary || `ul ${spec.name}` })),
    statusPill()));
  if (state.problem) parts.push(el("div", { class: "problem", text: state.problem }));
  if (spec.open) parts.push(el("button", { class: "primary", text: `Open ${spec.title}`, onclick: () => send({ op: "open", name: spec.name }) }));
  if (spec.panel) {
    for (const field of spec.panel.fields) parts.push(fieldNode(field));
    parts.push(el("div", { class: "buttons" }, ...spec.panel.buttons.map((button, index) =>
      el("button", { class: index === 0 && !spec.open ? "primary" : "", text: button.label, onclick: () => submit(index) }))));
  }
  if (spec.actions.length) {
    if (spec.panel || spec.open) parts.push(el("div", { class: "rule" }));
    parts.push(el("div", { class: "actions" }, ...spec.actions.map((action) =>
      el("button", { onclick: () => ask(action.confirm, () => send({ op: "action", name: spec.name, id: action.id })) }, icon("bolt"), el("span", { text: action.label })))));
  }
  if (!spec.panel && !spec.actions.length && !spec.open) {
    parts.push(el("button", { class: "primary", text: spec.terminal ? "Open in the terminal" : `Run ul ${spec.name}`,
      onclick: () => send({ op: spec.terminal ? "terminal" : "run", name: spec.name }) }));
  }
  parts.push(el("div", { class: "confirm-slot" }));
  parts.push(el("div", { class: "result-slot" }));
  parts.push(el("div", { class: "tail" },
    el("button", { class: "ghost", text: "Run in terminal", onclick: () => send({ op: "terminal", name: spec.name }) }),
    el("button", { class: "ghost", text: state.pinned ? "Unpin" : "Pin to menu bar", onclick: () => send({ op: state.pinned ? "unpin" : "pin", name: spec.name }) })));
  document.body.replaceChildren(el("div", { class: "glass" }, el("div", { class: "panel" }, ...parts)));
  const first = document.querySelector('.panel input[type="text"], .panel input[type="number"]');
  if (first) first.focus();
  resize();
}

function showResult(message) {
  const slot = document.querySelector(".result-slot");
  if (!slot) return;
  const kind = message.busy ? " busy" : message.ok ? "" : " bad";
  slot.replaceChildren(el("div", { class: `result${kind}`, text: message.text || (message.ok ? "Done." : "Failed.") }));
  resize();
}

function resize() {
  requestAnimationFrame(() => {
    const panel = document.querySelector(".panel");
    if (panel) send({ op: "resize", height: Math.ceil(panel.getBoundingClientRect().height) + 2 });
  });
}

document.addEventListener("keydown", (event) => {
  if (state.view === "panel" && event.key === "Escape") { event.preventDefault(); send({ op: "hide" }); }
});

// ---------- Messages from Rust ----------

window.ul = {
  receive(message) {
    switch (message.type) {
      case "init":
        state.view = message.view;
        applyTheme(message.theme);
        if (state.view === "palette") buildPalette();
        break;
      case "theme":
        applyTheme(message.theme);
        break;
      case "list":
        state.items = message.items;
        state.warnings = message.warnings;
        if (state.view === "palette") renderPalette();
        break;
      case "reset": {
        const input = document.querySelector(".search input");
        if (input) { input.value = ""; state.selected = 0; renderPalette(); input.focus(); }
        break;
      }
      case "panel":
        state.spec = message.spec;
        state.status = message.status;
        state.pinned = message.pinned;
        state.problem = message.problem;
        state.values = {};
        for (const field of message.spec.panel ? message.spec.panel.fields : []) state.values[field.id] = field.default;
        renderPanel();
        break;
      case "status":
        if (state.spec && message.name === state.spec.name) {
          state.status = message.status;
          const head = document.querySelector(".head");
          head?.querySelector(".pill")?.remove();
          const pill = statusPill();
          if (head && pill) head.appendChild(pill);
        }
        break;
      case "pinned":
        if (state.spec && message.name === state.spec.name) { state.pinned = message.pinned; renderPanel(); }
        break;
      case "result":
        if (state.spec && message.name === state.spec.name) showResult(message);
        break;
    }
  },
};

matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => send({ op: "theme" }));
send({ op: "ready" });
