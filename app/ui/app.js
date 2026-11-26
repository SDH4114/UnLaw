// Unlaw.app pages: the palette and a command's panel. Everything shown comes
// from commands and config files, so nodes are built with textContent only,
// never innerHTML. Rust sends state with window.ul.receive(...); the page asks
// for things with window.ipc.postMessage(JSON) and never sees argv: it sends a
// command name, an action id or a button index and field values.
"use strict";
// ICONS, icon(), el(), send() and applyTheme() come from common.js.


const state = { view: "palette", items: [], warnings: [], rows: [], selected: 0, spec: null, values: {}, status: null, pinned: false, busy: false };

// Dragging the window by its empty parts (the palette's search bar, a panel's
// header); the app remembers where it was left.
function dragHandle(node) {
  node.addEventListener("mousedown", (event) => {
    if (event.button !== 0 || event.target.closest("input, button, select, textarea, .pill")) return;
    event.preventDefault();
    send({ op: "drag" });
  });
  return node;
}


// ---------- Palette ----------

function words(text) {
  return text.toLowerCase().split(/\s+/).filter(Boolean);
}

function matches(haystack, query) {
  const text = haystack.toLowerCase();
  return query.every((word) => text.includes(word));
}

// Something typed that is a web address (with or without https://). `ul browser`
// checks it again before anything opens.
// A bare `name.ext` is a file name more often than a site, so those endings
// count as a link only with a scheme, `www.` or a path (`main.rs` stays a search).
const LINK = /^(https?:\/\/\S+|(localhost|\d{1,3}(\.\d{1,3}){3}|[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,})(:\d+)?([/?#]\S*)?)$/i;
const FILE_ENDINGS = new Set(["rs", "md", "toml", "py", "js", "ts", "tsx", "jsx", "json", "txt", "sh", "yml", "yaml", "lock",
  "cfg", "ini", "conf", "html", "css", "c", "h", "cpp", "hpp", "go", "rb", "php", "swift", "kt", "java", "zip", "tar", "gz",
  "7z", "png", "jpg", "jpeg", "gif", "svg", "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "key", "log", "csv", "env",
  "zsh", "dev", "info", "local", "bak", "tmp", "dmg", "pkg", "app", "mov", "mp3", "mp4", "wav", "sql", "db"]);

function isLink(text) {
  if (!LINK.test(text) || text === "localhost") return false;
  if (/^(https?:\/\/|www\.)/i.test(text) || /[:/?#]/.test(text)) return true;
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(text)) return true; // a bare IPv4 address
  return !FILE_ENDINGS.has(text.split(".").pop().toLowerCase());
}

// A browser command that takes a link in its panel field `url`.
function linkTarget(items) {
  return items.find((item) => item.name === "browser" && item.link);
}

// A link on top (when one was typed), commands (a name that starts with the query first), then actions.
function paletteRows(items, queryText) {
  const query = words(queryText);
  const link = queryText.trim();
  const browser = isLink(link) ? linkTarget(items) : null;
  const rows = browser ? [{ kind: "link", item: browser, link }] : [];
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
  return rows.concat(commands, actions);
}

function renderPalette() {
  const list = document.querySelector(".list");
  const query = document.querySelector(".search input").value;
  state.rows = paletteRows(state.items, query);
  state.selected = Math.min(state.selected, Math.max(0, state.rows.length - 1));
  list.replaceChildren();
  if (!state.rows.length) {
    const why = state.items.length ? "Nothing matches" : state.warnings.length ? state.warnings[0] : "Loading commands…";
    list.appendChild(el("div", { class: "empty", text: why }));
  }
  state.rows.forEach((row, index) => {
    const item = row.item;
    const title = el("div", { class: "title" });
    if (row.kind === "action") {
      title.appendChild(el("span", { text: row.action.label }));
      title.appendChild(el("span", { class: "of", text: `  ${item.title}` }));
    } else if (row.kind === "link") {
      title.appendChild(el("span", { text: "Open link" }));
      title.appendChild(el("span", { class: "of", text: `  ${row.link}` }));
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
    const node = el("div", { class: `row ${row.kind}${index === state.selected ? " on" : ""}`, role: "option",
      "aria-selected": String(index === state.selected) },
      el("div", { class: "glyph" }, icon(item.icon)),
      el("div", { class: "what" }, title, el("div", { class: "summary", text: row.kind === "command" ? item.summary || `ul ${item.name}` : `ul ${item.name}` })),
      tags);
    node.addEventListener("mousemove", () => select(index, false));
    node.addEventListener("click", () => activate(index));
    if (row.kind !== "link") node.addEventListener("contextmenu", (event) => { event.preventDefault(); select(index, false); contextMenu(event, row); });
    list.appendChild(node);
  });
  // A refreshed list keeps the chosen row in view.
  list.children[state.selected]?.scrollIntoView({ block: "nearest" });
  const warn = document.querySelector(".foot .warn");
  warn.textContent = state.warnings.length ? `${state.warnings.length} problem${state.warnings.length > 1 ? "s" : ""}` : "";
  warn.title = state.warnings.join("\n");
}

function select(index, scroll = true) {
  if (index < 0 || index >= state.rows.length || index === state.selected) return;
  const nodes = document.querySelectorAll(".list .row");
  nodes[state.selected]?.classList.remove("on");
  nodes[state.selected]?.setAttribute("aria-selected", "false");
  state.selected = index;
  nodes[index]?.classList.add("on");
  nodes[index]?.setAttribute("aria-selected", "true");
  if (scroll) nodes[index]?.scrollIntoView({ block: "nearest" });
}

function activate(index, how) {
  const row = state.rows[index];
  if (!row) return;
  if (row.kind === "link") {
    send({ op: "submit", name: row.item.name, button: 0, values: { url: row.link } });
  } else if (row.kind === "action") {
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
  // Enter that confirms an input method's text (Japanese, Chinese...) is not a command.
  if (event.isComposing || event.keyCode === 229) return;
  const row = state.rows[state.selected];
  if (event.key === "Escape") { if (document.querySelector(".menu")) closeMenu(); else send({ op: "hide" }); }
  else if (event.key === "ArrowDown" || (event.ctrlKey && event.code === "KeyN")) select(state.selected + 1);
  else if (event.key === "ArrowUp" || (event.ctrlKey && event.code === "KeyP")) select(state.selected - 1);
  else if (event.key === "Enter") activate(state.selected, event.metaKey ? "terminal" : undefined);
  else if (event.key === "Tab" && row) send({ op: "panel", name: row.item.name });
  else if (event.metaKey && event.code === "KeyP" && row && row.kind !== "link") send({ op: row.item.pinned ? "unpin" : "pin", name: row.item.name });
  else if (event.metaKey && event.code === "Comma") send({ op: "settings" });
  else return;
  event.preventDefault();
}

function buildPalette() {
  const input = el("input", { placeholder: "Search commands, or paste a link", spellcheck: "false", autocomplete: "off" });
  input.addEventListener("input", () => { state.selected = 0; renderPalette(); });
  document.body.replaceChildren(el("div", { class: "glass" },
    dragHandle(el("div", { class: "search" }, icon("search"), input)),
    el("div", { class: "list", role: "listbox", "aria-label": "Commands" }),
    el("div", { class: "foot" },
      el("span", {}, el("kbd", { text: "↩" }), document.createTextNode(" run")),
      el("span", {}, el("kbd", { text: "⇥" }), document.createTextNode(" panel")),
      el("span", {}, el("kbd", { text: "⌘↩" }), document.createTextNode(" terminal")),
      el("span", {}, el("kbd", { text: "⌘P" }), document.createTextNode(" pin")),
      el("span", { class: "grow" }),
      el("button", { class: "warn ghost", onclick: () => send({ op: "settings" }) }))));
  document.addEventListener("keydown", paletteKeys);
  document.addEventListener("click", (event) => { if (!event.target.closest(".menu")) closeMenu(); });
  renderPalette();
}

// ---------- Panel ----------

function statusPill() {
  if (!state.status || !state.status.text) return null;
  const tint = { on: " on", warn: " warn" }[state.status.state] || "";
  return el("span", { class: `pill${tint}`, text: state.status.text });
}

// One row of the form card: the label on the left, the control on the right (like System Settings).
function fieldNode(field) {
  const value = state.values[field.id];
  const set = (next) => { state.values[field.id] = next; };
  if (field.type === "toggle") {
    const toggle = el("button", { class: `switch${value ? " on" : ""}`, role: "switch", "aria-label": field.label, "aria-checked": String(!!value) });
    toggle.addEventListener("click", () => {
      set(!state.values[field.id]);
      toggle.classList.toggle("on", state.values[field.id]);
      toggle.setAttribute("aria-checked", String(state.values[field.id]));
    });
    return el("div", { class: "frow toggle" }, el("label", { text: field.label }), toggle);
  }
  if (field.type === "choice" && field.options.length <= 6) {
    const seg = el("div", { class: "seg", role: "radiogroup", "aria-label": field.label });
    for (const option of field.options) {
      const button = el("button", { text: option, class: option === value ? "on" : "", role: "radio", "aria-checked": String(option === value) });
      button.addEventListener("click", () => {
        set(option);
        for (const other of seg.children) {
          other.classList.toggle("on", other === button);
          other.setAttribute("aria-checked", String(other === button));
        }
      });
      seg.appendChild(button);
    }
    return el("div", { class: "frow stacked" }, el("label", { text: field.label }), seg);
  }
  let input;
  if (field.type === "choice") {
    input = el("select");
    for (const option of field.options) input.appendChild(el("option", { text: option, value: option }));
    input.value = value;
    input.addEventListener("change", () => set(input.value));
  } else {
    const type = { number: "number", time: "time", date: "date" }[field.type] || "text";
    input = el("input", { type, spellcheck: "false", autocomplete: "off" });
    input.placeholder = field.placeholder || (field.type === "duration" ? "25m, 1h30m" : field.required ? "Required" : "Optional");
    input.value = value;
    input.addEventListener("input", () => set(input.value));
    // Enter runs the first button that uses this field (Search for the search
    // field, Download for the link), else the first button.
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.isComposing) return;
      event.preventDefault();
      const buttons = state.spec.panel.buttons;
      const own = buttons.findIndex((button) => (button.fields || []).includes(field.id));
      submit(own >= 0 ? own : 0);
    });
  }
  input.id = `field-${field.id}`;
  const row = el("div", { class: "frow" }, el("label", { text: field.label, for: input.id }), input);
  // Clicking anywhere on the row puts the cursor in its field.
  row.addEventListener("mousedown", (event) => { if (event.target === row) { event.preventDefault(); input.focus(); } });
  return row;
}

function submit(index) {
  const spec = state.spec;
  if (state.busy || !spec.panel || !spec.panel.buttons[index]) return;
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
  viewClose();
  if (spec.view && VIEWS[spec.view]) { viewOpen(spec); return; }
  const parts = [];
  parts.push(dragHandle(el("div", { class: "head" },
    el("div", { class: "glyph" }, icon(spec.icon)),
    el("div", { class: "name" }, el("b", { text: spec.title }), el("span", { text: spec.summary || `ul ${spec.name}`, title: spec.summary || "" })),
    statusPill(),
    el("button", { class: "close", title: "Close (Esc)", "aria-label": "Close", onclick: () => send({ op: "hide" }) }, icon("close")))));
  if (state.problem) parts.push(el("div", { class: "problem", text: state.problem }));
  if (spec.open) parts.push(el("button", { class: "primary wide", text: `Open ${spec.title}`, onclick: () => send({ op: "open", name: spec.name }) }));
  if (spec.panel) {
    if (spec.panel.fields.length) parts.push(el("div", { class: "form" }, ...spec.panel.fields.map(fieldNode)));
    const buttons = spec.panel.buttons.map((button, index) =>
      el("button", { class: index === 0 && !spec.open ? "primary" : "", text: button.label, onclick: () => submit(index) }));
    parts.push(el("div", { class: `buttons n${Math.min(buttons.length, 3)}` }, ...buttons));
  }
  if (spec.actions.length) {
    parts.push(el("div", { class: "section" }, el("h4", { text: spec.panel || spec.open ? "More" : "Actions" }),
      el("div", { class: "actions" }, ...spec.actions.map((action) =>
        el("button", { onclick: () => ask(action.confirm, () => send({ op: "action", name: spec.name, id: action.id })) },
          el("span", { text: action.label }), icon("chevron"))))));
  }
  if (!spec.panel && !spec.actions.length && !spec.open) {
    parts.push(el("button", { class: "primary wide", text: spec.terminal ? "Open in the terminal" : `Run ul ${spec.name}`,
      onclick: () => send({ op: spec.terminal ? "terminal" : "run", name: spec.name }) }));
  }
  parts.push(el("div", { class: "confirm-slot" }));
  parts.push(el("div", { class: "result-slot" }));
  parts.push(el("div", { class: "tail" },
    el("code", { text: `ul ${spec.name}` }),
    el("button", { class: "ghost", onclick: () => send({ op: "terminal", name: spec.name }) }, icon("terminal"), el("span", { text: "Open in terminal" }))));
  document.body.replaceChildren(el("div", { class: "glass" }, el("div", { class: "panel" }, ...parts)));
  const first = document.querySelector(".panel .form input, .panel .form select");
  if (first) first.focus();
  setBusy(state.busy);
  resize();
}

function setBusy(busy) {
  state.busy = busy;
  for (const button of document.querySelectorAll(".panel .buttons button, .panel .actions button")) button.disabled = busy;
}

function showResult(message) {
  const slot = document.querySelector(".result-slot");
  if (!slot) return;
  const kind = message.busy ? "busy" : message.ok ? "ok" : "bad";
  const text = (message.text || (message.ok ? "Done." : "Failed.")).replace(/\s+$/, "");
  const title = { busy: text, ok: "Done", bad: "Failed" }[kind];
  const body = kind === "busy" || (kind === "ok" && text === "Done.") ? null : el("pre", { class: "result", text });
  slot.replaceChildren(el("div", { class: `outcome ${kind}`, "aria-live": "polite" },
    el("div", { class: "line" }, kind === "busy" ? el("i", { class: "spinner" }) : icon(kind === "ok" ? "check" : "alert"), el("b", { text: title }),
      kind === "busy" ? null : el("button", { class: "ghost dismiss", title: "Clear", "aria-label": "Clear", onclick: () => { slot.replaceChildren(); resize(); } }, icon("close"))),
    body));
  // Nothing starts twice while a run is going (Rust also refuses the same run).
  setBusy(!!message.busy);
  resize(!message.busy);
}

// Height always fits the panel. With `wide`, the width grows (up to the
// app's limit) until the output's longest line fits, so tables keep their columns.
function resize(wide = false) {
  requestAnimationFrame(() => {
    const panel = document.querySelector(".panel");
    if (!panel) return;
    const result = wide ? panel.querySelector(".result") : null;
    let width = null;
    if (result) {
      // The output's natural width (longest line), measured once without wrapping limits.
      result.style.width = "max-content";
      const natural = result.getBoundingClientRect().width;
      result.style.width = "";
      const sides = innerWidth - result.getBoundingClientRect().width;
      width = Math.ceil(natural + sides + 2); // Rust keeps it between the normal and the widest panel
    }
    // scrollHeight: the panel is capped at the window (100vh), so its box is never taller than now.
    const height = () => Math.ceil(panel.scrollHeight) + 2;
    send({ op: "resize", width, height: height() });
    // A new width lays the panel out again; fit the height to that.
    if (width !== null && Math.abs(width - innerWidth) >= 1) requestAnimationFrame(() => send({ op: "resize", width, height: height() }));
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
        closeMenu();
        if (input) { input.value = ""; state.selected = 0; renderPalette(); input.focus(); }
        break;
      }
      case "panel":
        state.spec = message.spec;
        state.status = message.status;
        state.pinned = message.pinned;
        state.problem = message.problem;
        state.busy = !!message.busy; // a run of this command still going
        state.values = {};
        for (const field of message.spec.panel ? message.spec.panel.fields : []) state.values[field.id] = field.default;
        renderPanel();
        break;
      case "status":
        if (state.spec && state.spec.view && message.name === state.spec.name) { viewRead(); break; }
        if (state.spec && message.name === state.spec.name) {
          state.status = message.status;
          const head = document.querySelector(".head");
          head?.querySelector(".pill")?.remove();
          const pill = statusPill();
          if (head && pill) head.appendChild(pill);
        }
        break;
      case "pinned":
        // Only the button changes: a result or an open confirm stays.
        if (state.spec && message.name === state.spec.name) {
          state.pinned = message.pinned;
          const toggle = document.querySelector(".pin-toggle");
          if (toggle) toggle.textContent = state.pinned ? "Unpin" : "Pin to menu bar";
        }
        break;
      case "result":
        if (state.spec && message.name === state.spec.name) {
          // An action of a view's command (the cup's own toggle): the view shows the new state.
          if (state.spec.view) viewRead(); else showResult(message);
        }
        break;
      case "view-stop":
        viewClose();
        break;
      case "view-data":
      case "view-done":
        viewReceive(message);
        break;
    }
  },
};

matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => send({ op: "theme" }));
send({ op: "ready" });
