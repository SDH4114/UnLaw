// Unlaw.app pages: the palette and a command's panel. Everything shown comes
// from commands and config files, so nodes are built with textContent only,
// never innerHTML. Rust sends state with window.ul.receive(...); the page asks
// for things with window.ipc.postMessage(JSON) and never sees argv: it sends a
// command name, an action id or a button index and field values.
"use strict";
// ICONS, icon(), el(), send() and applyTheme() come from common.js.


const state = { view: "palette", items: [], warnings: [], rows: [], selected: 0, spec: null, values: {}, status: null, pinned: false, busy: false,
  // The palette's inline input: the command whose field the search bar now fills (`spec.quick` in Rust), and its error.
  quick: null, quickError: "", query: "" };

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

// A command typed with the Russian layout on ("цуферук" for weather, "еп" for tg):
// the same keys on the English layout.
const RU_KEYS = "йцукенгшщзхъфывапролджэячсмитьбюё";
const EN_KEYS = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`";
function englishKeys(text) {
  return [...text.toLowerCase()].map((ch) => { const at = RU_KEYS.indexOf(ch); return at < 0 ? ch : EN_KEYS[at]; }).join("");
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
  const swapped = words(englishKeys(queryText));
  const found = (haystack) => matches(haystack, query) || (swapped.join(" ") !== query.join(" ") && matches(haystack, swapped));
  const link = queryText.trim();
  const browser = isLink(link) ? linkTarget(items) : null;
  const rows = browser ? [{ kind: "link", item: browser, link }] : [];
  // "tg hello", "app Safari", "weather Paris": a command's name, then what to give it.
  const typed = link.match(/^(\S+)\s+(.+)$/);
  if (typed) {
    const names = [typed[1].toLowerCase(), englishKeys(typed[1])];
    const item = items.find((item) => item.quick && names.some((name) => item.name === name || item.title.toLowerCase() === name));
    if (item) rows.push({ kind: "quick", item, value: typed[2] });
  }
  const commands = [];
  const actions = [];
  // "Templates" lists the saved ones (they open by their own name too).
  const listed = (state.templates || []).length ? items.concat([TEMPLATE_ITEM]) : items;
  for (const item of listed) {
    if (!query.length || found(`${item.name} ${item.title} ${item.summary}`)) commands.push({ kind: "command", item });
    // A command whose opening runs its one action is one row, not two.
    for (const action of item.only ? [] : item.actions) {
      if (query.length && found(`${item.name} ${item.title} ${action.label}`)) actions.push({ kind: "action", item, action });
    }
  }
  const firsts = [query[0] || "", swapped[0] || ""];
  const rank = (row) => (firsts.some((first) => row.item.name.startsWith(first) || row.item.title.toLowerCase().startsWith(first)) ? 0 : 1) + (row.item.pinned ? 0 : 0.5);
  commands.sort((a, b) => rank(a) - rank(b) || a.item.title.localeCompare(b.item.title));
  // Saved templates (ul template save): typed by name, Enter opens their windows.
  const templates = query.length ? (state.templates || []).filter((template) => found(`${template.name} template`))
    .map((template) => ({ kind: "template", template, item: TEMPLATE_ITEM })) : [];
  return rows.concat(commands, templates, actions);
}

// What a template row draws with (rows read `item` for the icon and the title).
// It is also the palette's "Templates" command: Enter lists every saved template.
const TEMPLATE_ITEM = { name: "template", title: "Templates", icon: "layout", actions: [], choices: [],
  summary: "Your saved working environments (ul template save); type a name to open one" };

function renderPalette() {
  const list = document.querySelector(".list");
  const query = document.querySelector(".search input").value;
  renderChip();
  state.rows = state.history ? historyRows(query)
    : state.quick ? quickRows(state.quick, query) : paletteRows(state.items, query);
  state.selected = Math.min(state.selected, Math.max(0, state.rows.length - 1));
  // A refresh (the command list or the templates arriving) keeps where the list was
  // scrolled to: replaceChildren alone sent it to the top under the user's arrows.
  const scrolled = list.scrollTop;
  list.replaceChildren();
  if (state.quick && state.quickError) list.appendChild(el("div", { class: "quick-error", text: state.quickError }));
  if (!state.rows.length) {
    const why = state.history
      ? (state.history.error || (!state.history.loaded ? "Reading the history…" : state.history.items.length ? "Nothing matches" : "Nothing copied yet"))
      : state.items.length ? "Nothing matches" : state.warnings.length ? state.warnings[0] : "Loading commands…";
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
    } else if (row.kind === "pin") {
      title.appendChild(el("span", { text: row.value.trim() ? `Pin ${row.value.trim()} to the menu bar` : "Pin an app to the menu bar" }));
    } else if (row.kind === "template") {
      title.appendChild(el("span", { text: row.template.name }));
      title.appendChild(el("span", { class: "of", text: "  Template" }));
    } else if (row.kind === "clip") {
      const text = (row.clip.text || row.clip.name || "").replace(/\s+/g, " ").trim();
      title.appendChild(el("span", { text: text.length > 90 ? `${text.slice(0, 90)}…` : text }));
    } else if (row.kind === "fn") {
      title.appendChild(el("span", { text: row.choice ? row.choice.label : row.action.label }));
      // The text goes into this row: shown after its name (an empty required one names what it wants).
      const typed = row.choice && row.choice.field ? row.value.trim() || row.choice.default || "" : "";
      if (typed) title.appendChild(el("span", { class: "of", text: `  ${typed}` }));
    } else if (row.kind === "quick") {
      const quick = item.quick;
      title.appendChild(el("span", { text: quick.run }));
      // An empty optional input runs the plain command (Browser: the homepage).
      const typed = row.value.trim() || (quick.required ? quick.label : "");
      if (typed) title.appendChild(el("span", { class: "of", text: `  ${typed}` }));
    } else {
      title.textContent = item.title;
    }
    const tags = el("div", { class: "tags" });
    if (row.kind === "command") {
      if (item.pinned) tags.appendChild(el("span", { class: "pin", title: "In the menu bar" }));
      if (item.terminal) tags.appendChild(el("span", { text: "terminal" }));
      else if (item.open) tags.appendChild(el("span", { text: "window" }));
      else if (hasFunctions(item)) tags.appendChild(el("span", { class: "key",
        text: item.name === "clip" ? "↩ history" : item === TEMPLATE_ITEM ? `↩ ${(state.templates || []).length} templates` : item.quick ? `↩ ${item.quick.label.toLowerCase()}` : `↩ ${functionRows(item, "").length} actions` }));
      else if (item.only) tags.appendChild(el("span", { text: "open" }));
      else if (item.section) tags.appendChild(el("span", { text: "window" }));
      else if (item.panel && !item.covers) tags.appendChild(el("span", { text: "panel" }));
    }
    if (row.kind === "quick" || row.kind === "fn") tags.appendChild(el("span", { class: "key", text: "↩" }));
    const node = el("div", { class: `row ${row.kind}${index === state.selected ? " on" : ""}`, role: "option",
      "aria-selected": String(index === state.selected) },
      el("div", { class: "glyph" }, row.kind === "clip" ? icon({ image: "image", file: "file" }[row.clip.kind] || "clipboard") : commandIcon(item)),
      el("div", { class: "what" }, title, el("div", { class: "summary", text: rowSummary(row) })),
      tags);
    // Only a real move of the mouse picks a row: rows sliding under a still cursor
    // (a scroll from the arrow keys, a refresh) fire mousemove too and stole the selection.
    node.addEventListener("mousemove", (event) => {
      const known = pointer.x !== -1;
      if (event.screenX === pointer.x && event.screenY === pointer.y) return;
      pointer.x = event.screenX;
      pointer.y = event.screenY;
      // The first event after opening only says where the cursor rests.
      if (known) select(index, false);
    });
    node.addEventListener("click", () => activate(index));
    if (!["link", "clip", "template"].includes(row.kind)) node.addEventListener("contextmenu", (event) => { event.preventDefault(); select(index, false); contextMenu(event, row); });
    list.appendChild(node);
  });
  // A refreshed list keeps its place and the chosen row in view.
  list.scrollTop = scrolled;
  list.querySelectorAll(".row")[state.selected]?.scrollIntoView({ block: "nearest" });
  quickPlaceholder();
  renderFoot();
  const warn = document.querySelector(".foot .warn");
  warn.textContent = state.warnings.length ? `${state.warnings.length} problem${state.warnings.length > 1 ? "s" : ""}` : "";
  warn.title = state.warnings.join("\n");
  fitPalette();
}

const pointer = { x: -1, y: -1 };

function wrap(index) {
  const count = state.rows.length;
  return count ? (index + count) % count : 0;
}

function select(index, scroll = true) {
  if (index < 0 || index >= state.rows.length || index === state.selected) return;
  const nodes = document.querySelectorAll(".list .row");
  nodes[state.selected]?.classList.remove("on");
  nodes[state.selected]?.setAttribute("aria-selected", "false");
  state.selected = index;
  if (state.confirming) { state.confirming = null; state.quickError = ""; document.querySelector(".quick-error")?.remove(); }
  nodes[index]?.classList.add("on");
  nodes[index]?.setAttribute("aria-selected", "true");
  if (scroll) nodes[index]?.scrollIntoView({ block: "nearest" });
  quickPlaceholder();
}

function activate(index, how) {
  const row = state.rows[index];
  if (state.pinning) {
    // Open app being pinned: the typed name becomes its own menu bar item.
    const name = document.querySelector(".search input").value.trim();
    if (!name) { state.quickError = "Type the application's name, like Safari"; renderPalette(); return; }
    send({ op: "pin", name: `app:${name}` });
    leaveQuick(false);
    send({ op: "hide" });
    return;
  }
  if (!row) return;
  if (row.kind === "template") {
    send({ op: "template-launch", template: row.template.name });
    if (state.quick) leaveQuick(false);
  } else if (row.kind === "link") {
    send({ op: "submit", name: row.item.name, button: 0, values: { url: row.link } });
  } else if (row.kind === "clip") {
    send({ op: "clip-copy", id: row.clip.id });
    leaveQuick(false);
  } else if (row.kind === "fn") {
    runFunction(row);
  } else if (row.kind === "quick" && row.item.name === "clip") {
    enterHistory(row.item, row.value);
  } else if (row.kind === "quick") {
    runQuick(row.item, row.value);
  } else if (row.kind === "command" && hasFunctions(row.item) && how !== "terminal") {
    enterQuick(row.item);
  } else if (row.kind === "action") {
    if (row.action.confirm && !confirmInPalette(row)) return;
    send({ op: "action", name: row.item.name, id: row.action.id });
  } else {
    send({ op: how || "default", name: row.item.name });
  }
}

// ---------- The palette's inline input ----------
// Enter on a command that takes one typed thing (Open app, Browser, Telegram, Weather...)
// turns the search bar into that command's field, like Raycast's arguments: type, Enter, done.
// Rust (`Spec::quick`) decides which commands qualify and runs it through the panel's checks.

function takesInput(item) {
  return !!item.quick && !item.terminal && !item.open;
}

// The panel shows more than the inline input: other fields, buttons, actions or a view.
// For a one-input command (Browser, Open app) it would only repeat the search bar.
function panelAddsMore(item) {
  // Rust decides (`Spec::palette_covers`): a panel whose every part is a palette row adds nothing.
  return !item.covers;
}

// Tab, like Raycast: a command that takes one thing gets it typed in place; the
// panel opens only when it has more to offer (from the inline input, Tab again).
function tabOn(row) {
  const item = row.item;
  if (row.kind === "command" && hasFunctions(item) && !state.quick) enterQuick(item);
  else if (!hasFunctions(item) || panelAddsMore(item)) send({ op: "panel", name: item.name });
}

function rowSummary(row) {
  if (row.kind === "pin") return "Its icon sits in the menu bar; a click opens it";
  if (row.kind === "template") return row.template.path ? `Opens its windows · ${row.template.path}` : "Opens its windows";
  if (row.kind === "clip") {
    const kind = { image: "Picture", file: "File" }[row.clip.kind] || "Text";
    return [kind, clipWhen(row.clip.time)].filter(Boolean).join(" · ");
  }
  if (row.kind === "quick" && row.item.name === "clip") return "Search what you copied";
  if (row.kind === "fn" && row.action) return "No text needed";
  if (row.kind === "fn") return row.choice.field ? row.choice.input : "No text needed";
  if (row.kind === "quick") return row.item.name === "tg" ? "Send to your Telegram chat; drop a file to send it" : `ul ${row.item.name}`;
  return row.kind === "command" ? row.item.summary || `ul ${row.item.name}` : `ul ${row.item.name}`;
}

// ---------- A command's functions in the palette ----------
// Enter (or Tab) on a command lists everything it can do, so its panel is rarely needed:
// each form button (a choice spread into one row per option: Download Video, Download
// MP3...) and each action. The typed text goes into the chosen row; Rust (`Spec::choices`)
// decides the rows and only runs rows it offers.

function functionRows(item, value) {
  return [...(item.choices || []).map((choice) => ({ kind: "fn", item, choice, value })),
    ...(item.actions || []).map((action) => ({ kind: "fn", item, action, value }))];
}

// What the palette lists for a command: its functions, or (no row takes text) the ones matching it.
function quickRows(item, query) {
  if (state.pinning) return [{ kind: "pin", item, value: query }];
  if (item === TEMPLATE_ITEM) {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return (state.templates || []).filter((template) => words.every((word) => template.name.toLowerCase().includes(word)))
      .map((template) => ({ kind: "template", template, item: TEMPLATE_ITEM }));
  }
  const rows = functionRows(item, query);
  if (rows.some((row) => row.choice && row.choice.field)) return rows;
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  return rows.filter((row) => words.every((word) => (row.choice ? row.choice.label : row.action.label).toLowerCase().includes(word)));
}

function hasFunctions(item) {
  if (item === TEMPLATE_ITEM) return true;
  if (item.terminal || item.open || item.only) return false;
  if (item.name === "clip" || takesInput(item)) return true;
  // A view (awake, sys) or a part of the main window opens there; a lone action runs at once.
  return !item.view && !item.section && functionRows(item, "").length >= 2;
}

function runFunction(row) {
  const item = row.item;
  if (row.action) {
    if (row.action.confirm) { confirmInPalette(row); return; }
    send({ op: "action", name: item.name, id: row.action.id });
    leaveQuick(false);
    return;
  }
  const choice = row.choice;
  if (choice.field && choice.required && !row.value.trim() && !choice.default) {
    state.quickError = `${choice.input} is empty`;
    renderPalette();
    return;
  }
  state.lastQuick = item.name;
  state.lastValue = row.value;
  send({ op: "quick", name: item.name, value: choice.field ? row.value.trim() : "", button: choice.button, fixed: choice.fixed });
  leaveQuick(false);
}

// The search bar asks for what the chosen row wants ("Paste a YouTube link" / "lofi hip hop").
function quickPlaceholder() {
  const input = document.querySelector(".search input");
  const row = state.rows[state.selected];
  if (!input || !state.quick || state.history) return;
  const choice = row && row.choice;
  input.placeholder = choice && choice.field ? choice.default || choice.placeholder || choice.input : `Filter ${state.quick.title}`;
}

function enterQuick(item, value = "") {
  if (item.name === "clip") return enterHistory(item, value);
  const input = document.querySelector(".search input");
  state.query = input.value;
  state.quick = item;
  state.quickError = "";
  state.selected = 0;
  input.value = value;
  send({ op: "keep", on: true });
  renderPalette();
  input.focus();
}

// ---------- Clipboard history in the palette ----------
// Clipboard opens its saved items as the list (like Raycast's history): typing
// filters them, Enter copies the chosen one again by its id (Rust checks the id).

function enterHistory(item, value = "") {
  const input = document.querySelector(".search input");
  if (!state.quick) state.query = input.value;
  state.quick = item;
  state.history = { items: [], loaded: false, error: "" };
  state.quickError = "";
  state.selected = 0;
  input.value = value;
  input.placeholder = "Search the clipboard";
  send({ op: "clip-history" });
  renderPalette();
  input.focus();
}

function historyRows(query) {
  // As typed, or the same keys on the English layout (copied text can be either).
  const split = (text) => text.toLowerCase().split(/\s+/).filter(Boolean);
  const tries = [split(query), split(englishKeys(query))];
  return state.history.items
    .filter((clip) => tries.some((words) => words.every((word) => `${clip.text || ""} ${clip.name || ""}`.toLowerCase().includes(word))))
    .slice(0, 100)
    .map((clip) => ({ kind: "clip", item: state.quick, clip }));
}

function clipWhen(iso) {
  const time = new Date(iso);
  if (isNaN(time)) return "";
  const minutes = Math.round((Date.now() - time) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 24 * 60) return `${Math.round(minutes / 60)} h ago`;
  return time.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function leaveQuick(restore = true) {
  const input = document.querySelector(".search input");
  if (!state.quick) return;
  state.pinning = false;
  state.history = null;
  state.quick = null;
  state.quickError = "";
  input.value = restore ? state.query : "";
  input.placeholder = PALETTE_PLACEHOLDER;
  send({ op: "keep", on: false });
  renderPalette();
  input.focus();
}

function runQuick(item, value) {
  if (item.quick.required && !value.trim()) {
    if (state.quick) { state.quickError = `${item.quick.label} is empty`; renderPalette(); } else enterQuick(item);
    return;
  }
  state.lastQuick = item.name;
  state.lastValue = value;
  send({ op: "quick", name: item.name, value: value.trim() });
  leaveQuick(false);
}

function renderChip() {
  const chip = document.querySelector(".search .cmdchip");
  if (!chip) return;
  chip.replaceChildren();
  chip.hidden = !state.quick;
  if (state.quick) chip.append(commandIcon(state.quick), el("span", { text: state.quick.title }));
}

function renderFoot() {
  const keys = document.querySelector(".foot .keys");
  if (!keys) return;
  const key = (glyph, text) => el("span", {}, el("kbd", { text: glyph }), document.createTextNode(` ${text}`));
  keys.replaceChildren(...(state.quick
    ? [key("↩", state.history ? "copy" : "run"), key("↑↓", "choose"), panelAddsMore(state.quick) ? key("⇥", "panel") : null, key("esc", "back"), state.quick.name === "tg" ? el("span", { class: "hint", text: "or drop a file" }) : null].filter(Boolean)
    : [key("↩", "run"), key("⇥", "panel"), key("⌘↩", "terminal"), key("⌘P", "pin")]));
}

// The palette has no room for a confirm box; such actions open the panel instead.
// An action that asks first (Health check's Fix): the first Enter shows its question in
// the palette, a second Enter on the same row runs it, anything else forgets it.
function confirmInPalette(row) {
  if (state.confirming === row.action.id) {
    state.confirming = null;
    send({ op: "action", name: row.item.name, id: row.action.id, confirmed: true });
    leaveQuick(false);
    return;
  }
  state.confirming = row.action.id;
  state.quickError = `${row.action.confirm} Press Enter again to do it.`;
  renderPalette();
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
    entry(item.pinned ? "Unpin from the menu bar" : "Pin to the menu bar", item.pinned ? "unpin" : "pin"),
    entry("Shortcut and settings\u2026", "command-settings"));
  menu.style.left = `${Math.min(event.clientX, innerWidth - 220)}px`;
  menu.style.top = `${Math.min(event.clientY, innerHeight - 185)}px`;
  document.body.appendChild(menu);
}

function paletteKeys(event) {
  // Enter that confirms an input method's text (Japanese, Chinese...) is not a command.
  if (event.isComposing || event.keyCode === 229) return;
  const row = state.rows[state.selected];
  const input = document.querySelector(".search input");
  if (state.quick && (event.key === "Escape" || (event.key === "Backspace" && !input.value))) {
    if (document.querySelector(".menu")) closeMenu(); else leaveQuick();
    event.preventDefault();
    return;
  }
  if (event.key === "Escape") { if (document.querySelector(".menu")) closeMenu(); else send({ op: "hide" }); }
  // Past the last row is the first one and above the first the last, like Spotlight.
  else if (event.key === "ArrowDown" || (event.ctrlKey && event.code === "KeyN")) select(wrap(state.selected + 1));
  else if (event.key === "ArrowUp" || (event.ctrlKey && event.code === "KeyP")) select(wrap(state.selected - 1));
  else if (event.key === "Enter") activate(state.selected, event.metaKey ? "terminal" : undefined);
  else if (event.key === "Tab") { if (row && row.kind !== "template") tabOn(row); }
  else if (event.metaKey && event.code === "KeyP" && row && row.kind !== "link" && row.kind !== "template") send({ op: row.item.pinned ? "unpin" : "pin", name: row.item.name });
  else if (event.metaKey && event.code === "Comma") send({ op: "settings" });
  else return;
  event.preventDefault();
}

const PALETTE_PLACEHOLDER = "Search commands, or type: tg hello, app Safari";

// The palette is as tall as what it shows (Raycast-like), never taller than its
// normal size: one quick row is a short bar, not a window with empty space.
const PALETTE_MAX = 460;
let paletteHeight = 0;
function fitPalette() {
  requestAnimationFrame(() => {
    const list = document.querySelector(".list");
    if (!list) return;
    const last = list.lastElementChild;
    const inner = last ? last.offsetTop + last.offsetHeight + 6 : 0;
    const height = Math.min(PALETTE_MAX, Math.ceil(document.querySelector(".search").offsetHeight + inner + document.querySelector(".foot").offsetHeight + 1));
    if (Math.abs(height - paletteHeight) < 1) return;
    paletteHeight = height;
    send({ op: "resize", height });
  });
}

function buildPalette() {
  const input = el("input", { placeholder: PALETTE_PLACEHOLDER, spellcheck: "false", autocomplete: "off" });
  input.addEventListener("input", () => { state.selected = 0; state.quickError = ""; state.confirming = null; renderPalette(); });
  document.body.replaceChildren(el("div", { class: "glass" },
    dragHandle(el("div", { class: "search" }, icon("search"), el("span", { class: "cmdchip", hidden: "" }), input)),
    el("div", { class: "list", role: "listbox", "aria-label": "Commands" }),
    el("div", { class: "foot" },
      el("span", { class: "keys" }),
      el("span", { class: "grow" }),
      el("button", { class: "warn ghost", onclick: () => send({ op: "settings" }) }))));
  document.addEventListener("keydown", paletteKeys);
  document.addEventListener("click", (event) => { if (!event.target.closest(".menu")) closeMenu(); });
  renderPalette();
}

// ---------- Note ----------
// The small note in the screen's corner (Rust's `App::toast`): an icon, the title, one or
// two lines. A click opens the command's panel with the whole output when there is more.

function renderToast(message) {
  const note = el("div", { class: `glass toast ${message.ok ? "ok" : "bad"}`, role: "status" },
    el("div", { class: "toastmark" }, icon(message.ok ? "check" : "alert")),
    el("div", { class: "toasttext" },
      el("b", { text: message.title || "Unlaw" }),
      message.text ? el("span", { text: message.text }) : null),
    message.more ? el("span", { class: "toastmore", text: "Details" }) : null);
  note.addEventListener("click", () => send({ op: "toast-click" }));
  document.body.replaceChildren(note);
  requestAnimationFrame(() => send({ op: "resize", height: Math.ceil(note.getBoundingClientRect().height) + 2 }));
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

// Which buttons go in the main row and which sit next to a field of their own:
// after the first, a button whose only unshared field is a typed one gets that field's row.
function panelLayout(panel) {
  const users = {};
  panel.buttons.forEach((button, index) => (button.fields || []).forEach((id) => (users[id] = users[id] || []).push(index)));
  const typed = new Set(["text", "duration", "number", "time", "date"]);
  const main = [];
  const inline = [];
  panel.buttons.forEach((button, index) => {
    const mine = (button.fields || []).filter((id) => users[id].length === 1);
    const field = mine.length === 1 ? panel.fields.find((field) => field.id === mine[0]) : null;
    if (index > 0 && field && typed.has(field.type)) inline.push({ field, index });
    else main.push(index);
  });
  return { main, inline };
}

function renderPanel() {
  const spec = state.spec;
  if (!spec) return;
  viewClose();
  if (spec.view && VIEWS[spec.view]) { viewOpen(spec); return; }
  const parts = [];
  parts.push(dragHandle(el("div", { class: "head" },
    el("div", { class: "glyph" }, commandIcon(spec)),
    el("div", { class: "name" }, el("b", { text: spec.title }), el("span", { text: spec.summary || `ul ${spec.name}`, title: spec.summary || "" })),
    statusPill(),
    el("button", { class: "close", title: "Close (Esc)", "aria-label": "Close", onclick: () => send({ op: "hide" }) }, icon("close")))));
  if (state.problem) parts.push(el("div", { class: "problem", text: state.problem }));
  if (spec.open) parts.push(el("button", { class: "primary wide", text: `Open ${spec.title}`, onclick: () => send({ op: "open", name: spec.name }) }));
  if (spec.panel) {
    const { main, inline } = panelLayout(spec.panel);
    const own = new Set(inline.map(({ field }) => field.id));
    const fields = spec.panel.fields.filter((field) => !own.has(field.id));
    if (fields.length) parts.push(el("div", { class: "form" }, ...fields.map(fieldNode)));
    const buttons = main.map((index) => el("button", { class: index === main[0] && !spec.open ? "primary" : "",
      text: spec.panel.buttons[index].label, onclick: () => submit(index) }));
    if (buttons.length) parts.push(el("div", { class: `buttons n${Math.min(buttons.length, 3)}` }, ...buttons));
    // A button with a field of its own sits in that field's row (Search next to "Search YouTube").
    for (const { field, index } of inline) {
      const row = fieldNode(field);
      row.classList.add("inline");
      row.appendChild(el("button", { class: "go", text: spec.panel.buttons[index].label, onclick: () => submit(index) }));
      parts.push(el("div", { class: "form" }, row));
    }
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
        applyColors(message.colors);
        if (state.view === "palette") buildPalette();
        break;
      case "toast":
        renderToast(message);
        break;
      case "pin-app": {
        // Pinning Open app asks which application gets its own menu bar item.
        const item = state.items.find((entry) => entry.name === "app");
        if (item) {
          leaveQuick(false);
          enterQuick(item);
          state.pinning = true;
          const input = document.querySelector(".search input");
          input.placeholder = "Which app gets a menu bar item? Safari, Notes…";
          renderPalette();
        }
        break;
      }
      case "functions": {
        // Opened from the menu bar, a hotkey or a tile: the command's rows instead of its panel.
        const item = state.items.find((entry) => entry.name === message.name);
        if (item) { leaveQuick(false); enterQuick(item); }
        break;
      }
      case "colors":
        applyTheme(message.theme);
        applyColors(message.colors);
        break;
      case "theme":
        applyTheme(message.theme);
        break;
      case "list": {
        // The same list again (every palette open asks) changes nothing on screen.
        const same = JSON.stringify([message.items, message.warnings]) === JSON.stringify([state.items, state.warnings]);
        state.items = message.items;
        state.warnings = message.warnings;
        if (state.view === "palette" && !same) renderPalette();
        break;
      }
      case "reset": {
        const input = document.querySelector(".search input");
        closeMenu();
        state.quick = null;
        state.history = null;
        state.quickError = "";
        state.lastQuick = "";
        pointer.x = pointer.y = -1;
        if (input) { input.value = ""; input.placeholder = PALETTE_PLACEHOLDER; state.selected = 0; renderPalette(); input.focus(); }
        break;
      }
      case "quick-error": {
        // The command was not run (an empty required field, a bad value): stay and say why.
        const item = state.items.find((item) => item.quick && item.name === state.lastQuick);
        if (item && !state.quick) enterQuick(item, state.lastValue || "");
        state.quickError = message.text;
        renderPalette();
        break;
      }
      case "templates": {
        const same = JSON.stringify(message.items || []) === JSON.stringify(state.templates || []);
        state.templates = message.items || [];
        const shown = !state.quick || state.quick === TEMPLATE_ITEM;
        if (state.view === "palette" && shown && !same) renderPalette();
        break;
      }
      case "clip-history":
        if (!state.history) break;
        state.history = { items: message.items || [], loaded: true, error: message.error || "" };
        renderPalette();
        break;
      case "dropped": {
        // Full paths from Rust (a page only gets file names). One file fills the input.
        const input = document.querySelector(".search input");
        const path = message.paths[0];
        if (!path || !input) break;
        if (!state.quick) {
          const tg = state.items.find((item) => item.name === "tg" && item.quick);
          if (tg) enterQuick(tg); else break;
        }
        input.value = path;
        state.quickError = message.paths.length > 1 ? "Only the first file is used" : "";
        renderPalette();
        input.focus();
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
      case "view-query":
        viewReceive(message);
        break;
    }
  },
};

matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => send({ op: "theme" }));
send({ op: "ready" });
