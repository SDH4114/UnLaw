// Shared by every Unlaw.app page (palette, panel, main window): icons, node
// building with textContent only (never innerHTML) and the message channel to Rust.
"use strict";

// A page error goes to the app's log (gui.log) instead of leaving a blank window.
window.addEventListener("error", (event) => {
  try { window.ipc.postMessage(JSON.stringify({ op: "log", text: `${event.message} (${event.filename}:${event.lineno})` })); } catch (_) {}
});

// localStorage may be refused on the app's own scheme: settings then last until the window closes.
const memory = {};
function stored(key, fallback) {
  try { return localStorage.getItem(key) ?? fallback; } catch (_) { return memory[key] ?? fallback; }
}
function store(key, value) {
  try { localStorage.setItem(key, value); } catch (_) { memory[key] = value; }
}

const ICONS = {
  command: ["M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z"],
  today: ["M4 6h16v14H4z", "M4 10h16", "M8 3v4M16 3v4", "M8.5 15l2 2 4-4"],
  canvas: ["M3 17c3-6 6 2 9-4s5-5 9-3", "M4 4h16v16H4z"],
  studio: ["M3 7h12v10H3z", "M15 10l6-3v10l-6-3"],
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
  pin: ["M9.5 3.5h5l-.9 5.2 3.4 3.3H7l3.4-3.3z", "M12 12v8.5"],
  close: ["M6.5 6.5l11 11M17.5 6.5l-11 11"],
  run: ["M8 5.5v13l10.5-6.5z"],
  layout: ["M3.5 5h17v14h-17z", "M10 5v14", "M10 12h10.5"],
  plus: ["M12 5v14M5 12h14"],
  pencil: ["M4 20l4-1 11-11-3-3L5 16z", "M14 7l3 3"],
  trash: ["M5 7h14", "M9 7V4.5h6V7", "M7 7l1 13h8l1-13"],
  chevron: ["M10 7l5 5-5 5"],
  check: ["M5 12.5l4.5 4.5L19 7.5"],
  alert: ["M12 3.5l9 16H3z", "M12 10v4.5M12 17.5h.01"],
};

// Readings shown by the main window's System part and the menu bar's System popover.
const GB = 1024 ** 3;
function gb(bytes) { return bytes == null ? "n/a" : (bytes / GB).toFixed(bytes >= 100 * GB ? 0 : 1) + " GB"; }
function pct(value) { return value == null ? "n/a" : Math.round(value) + "%"; }
function duration(seconds) {
  if (seconds == null) return "n/a";
  const days = Math.floor(seconds / 86400), hours = Math.floor(seconds % 86400 / 3600), minutes = Math.floor(seconds % 3600 / 60);
  return days ? `${days} d ${hours} h` : hours ? `${hours} h ${minutes} min` : `${minutes} min`;
}

function bytes(count) {
  if (count == null) return "n/a";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = count, unit = 0;
  while (value >= 1000 && unit < units.length - 1) { value /= 1000; unit++; }
  return (unit ? value.toFixed(value >= 100 ? 0 : 1) : Math.round(value)) + " " + units[unit];
}

function speed(count) { return count == null ? "n/a" : bytes(count) + "/s"; }

function watts(value) { return value == null ? "n/a" : value.toFixed(1) + " W"; }

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
    // Through CSSOM: the pages' CSP refuses style attributes.
    else if (key === "style") node.style.cssText = value;
    else if (value === null || value === undefined) continue;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child) node.appendChild(child);
  return node;
}

function send(message) {
  window.ipc.postMessage(JSON.stringify(message));
}

function applyTheme(theme) {
  const dark = theme === "dark" || (theme === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}
