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
  image: ["M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z", "M8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z", "M20 15l-5-5L5 20"],
  file: ["M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z", "M14 3v5h5"],
  sun: ["M12 16.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9z", "M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"],
  cloudsun: ["M9 4.5v1.3M3.8 9.7h1.3M5.3 6l.9.9M12.7 6l-.9.9", "M6.6 11.2A3.6 3.6 0 0 1 12.4 8", "M8.5 19.5h9a3.5 3.5 0 0 0 .4-7 5.2 5.2 0 0 0-10-.6 3.9 3.9 0 0 0 .6 7.6z"],
  rain: ["M7 15h10a4 4 0 0 0 .5-7.97A6 6 0 0 0 6.1 6.1 4.5 4.5 0 0 0 7 15z", "M8 18l-1 2.5M12 18l-1 2.5M16 18l-1 2.5"],
  snow: ["M7 14.5h10a4 4 0 0 0 .5-7.97A6 6 0 0 0 6.1 5.6 4.5 4.5 0 0 0 7 14.5z", "M8 18h.01M12 18h.01M16 18h.01M10 21h.01M14 21h.01"],
  fog: ["M7 12h10a4 4 0 0 0 .5-7.97A6 6 0 0 0 6.1 3.1", "M4 15.5h16M6 19h12"],
  storm: ["M7 15h10a4 4 0 0 0 .5-7.97A6 6 0 0 0 6.1 6.1 4.5 4.5 0 0 0 7 15z", "M12.5 15l-2 3.5h3l-2 3.5"],
  music: ["M9 18V6l11-2v12", "M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM17 19a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"],
  play: ["M3 6h18v12H3z", "M10 9.5v5l4.5-2.5z"],
  camera: ["M4 8h3l2-3h6l2 3h3v11H4z", "M12 16.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"],
  record: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"],
  download: ["M12 4v11", "M7.5 10.5 12 15l4.5-4.5", "M5 20h14"],
  git: ["M6 3v12", "M6 21a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM18 9a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z", "M18 9a9 9 0 0 1-9 9"],
  terminal: ["M3 5h18v14H3z", "M7 10l3 2.5L7 15M12.5 15H17"],
  folder: ["M3 6h6l2 2h10v11H3z"],
  folderPlus: ["M3 6h6l2 2h10v11H3z", "M12 11v5M9.5 13.5h5"],
  filePlus: ["M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z", "M14 3v5h5", "M12 11v6M9 14h6"],
  collapse: ["M7 9l5-5 5 5", "M7 15l5 5 5-5"],
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
  sidebar: ["M4 5h16v14H4z", "M9.5 5v14", "M6 8.5h1.5M6 11h1.5"],
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

// Logos for commands that open a service (spec.rs BRANDS): one-colour marks in the
// (ChatGPT, Claude, Obsidian, Steam and Spotify are the Simple Icons marks, simpleicons.org, CC0)
// line icons' colour (currentColor): filled with even-odd cut-outs, or drawn in lines.
const BRANDS = {
  youtube: "M6 5h12a4 4 0 0 1 4 4v6a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V9a4 4 0 0 1 4-4zM10 8.8v6.4l5.6-3.2z",
  netflix: "M6 3h3.4l5.2 13V3H18v18h-3.4L9.4 8v13H6z",
  telegram: "M2.6 11.2l17.6-7c.9-.3 1.6.2 1.3 1.5l-3 14c-.2 1-.8 1.2-1.6.8l-4.6-3.4-2.2 2.1c-.3.3-.5.5-1 .5l.3-4.7 8.6-7.8c.4-.3-.1-.5-.6-.2L7.3 13.7 2.7 12.3c-1-.3-1-1 .2-1.4z",
  spotify: { fill: "M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z" },
  chatgpt: { fill: "M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z" },
  claude: { fill: "m4.7144 15.9555 4.7174-2.6471.079-.2307-.079-.1275h-.2307l-.7893-.0486-2.6956-.0729-2.3375-.0971-2.2646-.1214-.5707-.1215-.5343-.7042.0546-.3522.4797-.3218.686.0608 1.5179.1032 2.2767.1578 1.6514.0972 2.4468.255h.3886l.0546-.1579-.1336-.0971-.1032-.0972L6.973 9.8356l-2.55-1.6879-1.3356-.9714-.7225-.4918-.3643-.4614-.1578-1.0078.6557-.7225.8803.0607.2246.0607.8925.686 1.9064 1.4754 2.4893 1.8336.3643.3035.1457-.1032.0182-.0728-.164-.2733-1.3539-2.4467-1.445-2.4893-.6435-1.032-.17-.6194c-.0607-.255-.1032-.4674-.1032-.7285L6.287.1335 6.6997 0l.9957.1336.419.3642.6192 1.4147 1.0018 2.2282 1.5543 3.0296.4553.8985.2429.8318.091.255h.1579v-.1457l.1275-1.706.2368-2.0947.2307-2.6957.0789-.7589.3764-.9107.7468-.4918.5828.2793.4797.686-.0668.4433-.2853 1.8517-.5586 2.9021-.3643 1.9429h.2125l.2429-.2429.9835-1.3053 1.6514-2.0643.7286-.8196.85-.9046.5464-.4311h1.0321l.759 1.1293-.34 1.1657-1.0625 1.3478-.8804 1.1414-1.2628 1.7-.7893 1.36.0729.1093.1882-.0183 2.8535-.607 1.5421-.2794 1.8396-.3157.8318.3886.091.3946-.3278.8075-1.967.4857-2.3072.4614-3.4364.8136-.0425.0304.0486.0607 1.5482.1457.6618.0364h1.621l3.0175.2247.7892.522.4736.6376-.079.4857-1.2142.6193-1.6393-.3886-3.825-.9107-1.3113-.3279h-.1822v.1093l1.0929 1.0686 2.0035 1.8092 2.5075 2.3314.1275.5768-.3218.4554-.34-.0486-2.2039-1.6575-.85-.7468-1.9246-1.621h-.1275v.17l.4432.6496 2.3436 3.5214.1214 1.0807-.17.3521-.6071.2125-.6679-.1214-1.3721-1.9246L14.38 17.959l-1.1414-1.9428-.1397.079-.674 7.2552-.3156.3703-.7286.2793-.6071-.4614-.3218-.7468.3218-1.4753.3886-1.9246.3157-1.53.2853-1.9004.17-.6314-.0121-.0425-.1397.0182-1.4328 1.9672-2.1796 2.9446-1.7243 1.8456-.4128.164-.7164-.3704.0667-.6618.4008-.5889 2.386-3.0357 1.4389-1.882.929-1.0868-.0062-.1579h-.0546l-6.3385 4.1164-1.1293.1457-.4857-.4554.0608-.7467.2307-.2429 1.9064-1.3114Z" },
  steam: { fill: "M11.979 0C5.678 0 .511 4.86.022 11.037l6.432 2.658c.545-.371 1.203-.59 1.912-.59.063 0 .125.004.188.006l2.861-4.142V8.91c0-2.495 2.028-4.524 4.524-4.524 2.494 0 4.524 2.031 4.524 4.527s-2.03 4.525-4.524 4.525h-.105l-4.076 2.911c0 .052.004.105.004.159 0 1.875-1.515 3.396-3.39 3.396-1.635 0-3.016-1.173-3.331-2.727L.436 15.27C1.862 20.307 6.486 24 11.979 24c6.627 0 11.999-5.373 11.999-12S18.605 0 11.979 0zM7.54 18.21l-1.473-.61c.262.543.714.999 1.314 1.25 1.297.539 2.793-.076 3.332-1.375.263-.63.264-1.319.005-1.949s-.75-1.121-1.377-1.383c-.624-.26-1.29-.249-1.878-.03l1.523.63c.956.4 1.409 1.5 1.009 2.455-.397.957-1.497 1.41-2.454 1.012H7.54zm11.415-9.303c0-1.662-1.353-3.015-3.015-3.015-1.665 0-3.015 1.353-3.015 3.015 0 1.665 1.35 3.015 3.015 3.015 1.663 0 3.015-1.35 3.015-3.015zm-5.273-.005c0-1.252 1.013-2.266 2.265-2.266 1.249 0 2.266 1.014 2.266 2.266 0 1.251-1.017 2.265-2.266 2.265-1.253 0-2.265-1.014-2.265-2.265z" },
  obsidian: { fill: "M19.355 18.538a68.967 68.959 0 0 0 1.858-2.954.81.81 0 0 0-.062-.9c-.516-.685-1.504-2.075-2.042-3.362-.553-1.321-.636-3.375-.64-4.377a1.707 1.707 0 0 0-.358-1.05l-3.198-4.064a3.744 3.744 0 0 1-.076.543c-.106.503-.307 1.004-.536 1.5-.134.29-.29.6-.446.914l-.31.626c-.516 1.068-.997 2.227-1.132 3.59-.124 1.26.046 2.73.815 4.481.128.011.257.025.386.044a6.363 6.363 0 0 1 3.326 1.505c.916.79 1.744 1.922 2.415 3.5zM8.199 22.569c.073.012.146.02.22.02.78.024 2.095.092 3.16.29.87.16 2.593.64 4.01 1.055 1.083.316 2.198-.548 2.355-1.664.114-.814.33-1.735.725-2.58l-.01.005c-.67-1.87-1.522-3.078-2.416-3.849a5.295 5.295 0 0 0-2.778-1.257c-1.54-.216-2.952.19-3.84.45.532 2.218.368 4.829-1.425 7.531zM5.533 9.938c-.023.1-.056.197-.098.29L2.82 16.059a1.602 1.602 0 0 0 .313 1.772l4.116 4.24c2.103-3.101 1.796-6.02.836-8.3-.728-1.73-1.832-3.081-2.55-3.831zM9.32 14.01c.615-.183 1.606-.465 2.745-.534-.683-1.725-.848-3.233-.716-4.577.154-1.552.7-2.847 1.235-3.95.113-.235.223-.454.328-.664.149-.297.288-.577.419-.86.217-.47.379-.885.46-1.27.08-.38.08-.72-.014-1.043-.095-.325-.297-.675-.68-1.06a1.6 1.6 0 0 0-1.475.36l-4.95 4.452a1.602 1.602 0 0 0-.513.952l-.427 2.83c.672.59 2.328 2.316 3.335 4.711.09.21.175.43.253.653z" },
  minecraft: "M3 3h18v18H3zM6 7v3h4V7zM14 7v3h4V7zM10 10v3H8v5h2v-2h4v2h2v-5h-2v-3z",
};

function brandLogo(name) {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon brand");
  const mark = BRANDS[name];
  const path = document.createElementNS(SVG, "path");
  // A string is a filled shape with even-odd cut-outs, { fill } a filled shape as drawn
  // (Simple Icons paths, CC0), { stroke } lines like the other icons.
  path.setAttribute("d", typeof mark === "string" ? mark : mark.fill || mark.stroke);
  if (typeof mark === "string") path.setAttribute("fill-rule", "evenodd");
  else if (mark.stroke) path.setAttribute("class", "line");
  svg.appendChild(path);
  return svg;
}

// A command's picture: its brand's mark when it has one, else the line icon.
function commandIcon(item) {
  if (item.brand && BRANDS[item.brand]) return brandLogo(item.brand);
  // An application pinned from Open app: that app's own icon.
  if (item.app_icon) {
    const image = el("img", { class: "logo", alt: "", src: `ulapp://localhost/appicon/${encodeURIComponent(item.app_icon)}.png` });
    image.addEventListener("error", () => image.replaceWith(icon(item.icon)));
    return image;
  }
  return icon(item.icon);
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

// The editor theme's colors on every window (look.colors = "editor"): the app's own CSS
// variables are set from them; without colors the stylesheet's amber look comes back.
const COLOR_VARS = ["--tint", "--raise", "--raise-2", "--hover", "--select", "--text", "--muted", "--line", "--accent", "--accent-ink",
  "--accent-soft", "--accent-soft-2", "--accent-line", "--ring", "--second", "--page"];

function alpha(hex, amount) {
  const value = parseInt(hex.slice(1), 16);
  return `rgba(${value >> 16 & 255}, ${value >> 8 & 255}, ${value & 255}, ${amount})`;
}

function applyColors(colors) {
  const root = document.documentElement;
  if (!colors || !/^#[0-9a-f]{6}$/i.test(colors.bg || "") || !/^#[0-9a-f]{6}$/i.test(colors.fg || "")) {
    for (const name of COLOR_VARS) root.style.removeProperty(name);
    root.classList.remove("editor-colors");
    return;
  }
  const hex = (value, fallback) => (/^#[0-9a-f]{6}$/i.test(value || "") ? value : fallback);
  const { bg, fg } = colors;
  const accent = hex(colors.accent, fg);
  const panel = hex(colors.panel, bg);
  const vars = {
    "--page": bg, "--tint": alpha(bg, 0.86), "--raise": alpha(panel, 0.78), "--raise-2": panel,
    "--hover": alpha(fg, 0.07), "--select": alpha(fg, 0.1), "--text": fg, "--muted": alpha(fg, 0.62),
    "--line": alpha(fg, 0.1), "--accent": accent, "--accent-ink": accent, "--accent-soft": alpha(accent, 0.16),
    "--accent-soft-2": alpha(accent, 0.26), "--accent-line": alpha(accent, 0.45), "--ring": alpha(fg, 0.2), "--second": accent,
  };
  for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value);
  root.classList.add("editor-colors");
  root.classList.toggle("dark", !!colors.dark);
}

function applyTheme(theme) {
  const dark = theme === "dark" || (theme === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}
