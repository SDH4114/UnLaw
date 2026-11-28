"use strict";
// Edit's page viewer for PDF and pictures: page thumbnails on the left, the pages in a
// column, a page number to jump to, zoom, and drawing on the pages like the desk canvas
// (pen, marker, text, sticky notes and red thread between them).
//
// Pages are PNGs `ul doc render` draws with PDFKit (cached by size), asked for only as
// they come near the screen, a batch per request. Drawings never touch the file: they
// are saved beside Unlaw's data (`edit-ink-save`, one JSON per file) in PDF points, so
// they stay in place at every zoom.

const PV_TOOLS = [
  { id: "hand", key: "KeyV", label: "Select and move (V)", glyph: "hand" },
  { id: "pen", key: "KeyP", label: "Pen (P)", glyph: "pen" },
  { id: "marker", key: "KeyM", label: "Marker (M)", glyph: "marker" },
  { id: "text", key: "KeyT", label: "Text (T)", glyph: "text" },
  { id: "sticky", key: "KeyS", label: "Sticky note (S)", glyph: "sticky" },
  { id: "thread", key: "KeyL", label: "Thread: click one place, then another (L)", glyph: "thread" },
  { id: "eraser", key: "KeyE", label: "Eraser (E)", glyph: "eraser" },
];
const PV_GLYPHS = {
  hand: ["M8 13V5.5a1.5 1.5 0 0 1 3 0V12", "M11 11.5v-7a1.5 1.5 0 0 1 3 0v7", "M14 11.5V6a1.5 1.5 0 0 1 3 0v8.5a6 6 0 0 1-6 6h-.5a6 6 0 0 1-4.6-2.2L3.6 15a1.5 1.5 0 0 1 2.2-2L8 15"],
  pen: ["M4 20l4-1 11-11-3-3L5 16z", "M14 7l3 3"],
  marker: ["M9 15l-4 4h6l2-2", "M9 15l7-10 4 3-7 10z"],
  text: ["M5 6V4h14v2", "M12 4v16", "M9 20h6"],
  sticky: ["M5 4h14v10l-6 6H5z", "M13 20v-6h6"],
  thread: ["M5 7c4 9 10 9 14 0", "M5 7m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0", "M19 7m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0"],
  eraser: ["M8 20h12", "M5 15l9-9 5 5-9 9H8z", "M10 10l5 5"],
  undo: ["M9 14L4 9l5-5", "M4 9h10a6 6 0 0 1 0 12h-3"],
  redo: ["M15 14l5-5-5-5", "M20 9H10a6 6 0 0 0 0 12h3"],
  thumbs: ["M4 4h6v7H4zM4 14h6v6H4z", "M14 4h6v16h-6z"],
  minus: ["M5 12h14"],
  plus: ["M12 5v14M5 12h14"],
  fit: ["M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"],
  more: ["M6 12h.01M12 12h.01M18 12h.01"],
  textview: ["M6 3h9l4 4v14H6z", "M9 11h7M9 14h7M9 17h4"],
  openapp: ["M14 4h6v6", "M20 4l-9 9", "M18 14v6H4V6h6"],
  finder: ["M3 6h6l2 2h10v11H3z", "M12 11.5a2 2 0 1 0 0 4"],
};
const PV_COLORS = ["#e5484d", "#f5a524", "#ffd60a", "#30a46c", "#0091ff", "#8e4ec6", "#1d1d1f", "#ffffff"];
const PV_STICKY = "#ffe27a";
const PV_THREAD = "#d1242f";
const PV_THUMB_WIDTH = 240;
const PV_BATCH = 6;
const PV_THUMB_BATCH = 24;

function pvIcon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon");
  for (const d of PV_GLYPHS[name] || []) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    svg.appendChild(path);
  }
  return svg;
}

// The viewer state of one open file (kept on the viewer, so a tab switch keeps the place).
function pvState(viewer) {
  if (!viewer.pv) {
    const tools = (() => { try { return JSON.parse(stored("edit-pv-tools", "{}")) || {}; } catch (_) { return {}; } })();
    viewer.pv = {
      pages: null, error: "", zoom: 1, fit: true, current: 1, scroll: 0, thumbs: stored("edit-pv-thumbs", "1") !== "0",
      tool: "hand", color: tools.color || PV_COLORS[0], width: Number(tools.width) || 3,
      ink: null, undo: [], redo: [], urls: {}, thumbUrls: {}, asked: new Set(), thumbAsked: new Set(),
      selected: null, threadPull: null, node: null, saveTimer: 0,
    };
    if (viewer.info.kind === "pdf") send({ op: "edit-pages", path: viewer.path });
    send({ op: "edit-ink-load", path: viewer.path });
  }
  return viewer.pv;
}

function pvIsPicture(viewer) { return viewer.info.kind === "image" || /\.svg$/i.test(viewer.name); }

// ---------- building ----------

function pvNode(viewer) {
  const pv = pvState(viewer);
  if (pv.node) { requestAnimationFrame(() => { pv.node.querySelector(".ppages").scrollTop = pv.scroll; pvLayout(viewer); }); return pv.node; }
  const button = (glyph, title, run, extra) => el("button", { class: "ghost icon" + (extra ? " " + extra : ""), title, "aria-label": title, onclick: run }, pvIcon(glyph));
  const pageBox = el("input", { class: "pnum", inputmode: "numeric", "aria-label": "Page", value: "1" });
  pageBox.addEventListener("keydown", (event) => {
    event.stopPropagation();
    if (event.key === "Enter") { pvGo(viewer, Number(pageBox.value) || 1); pageBox.blur(); }
    if (event.key === "Escape") { pageBox.value = String(pv.current); pageBox.blur(); }
  });
  pageBox.addEventListener("focus", () => pageBox.select());
  const tools = el("div", { class: "ptoolgroup" }, ...PV_TOOLS.map((tool) => {
    const node = button(tool.glyph, tool.label, () => pvTool(viewer, tool.id), "ptool");
    node.dataset.tool = tool.id;
    return node;
  }));
  // Color and width live in one button (a swatch) with a small popover, so the bar is one
  // steady row: nothing in it changes size while you work.
  const style = el("button", { class: "ghost icon pstylebtn", title: "Color and width", "aria-label": "Color and width",
    onclick: (event) => { event.stopPropagation(); pvStylePopover(viewer); } }, el("span", { class: "pswatch" }));
  const group = (...children) => el("div", { class: "pgroup" }, ...children);
  const bar = el("div", { class: "ptools" },
    group(button("thumbs", "Page thumbnails", () => { pv.thumbs = !pv.thumbs; store("edit-pv-thumbs", pv.thumbs ? "1" : "0"); pvChrome(viewer); pvLayout(viewer); }, "pthumbsbtn"),
      el("div", { class: "pgo" }, pageBox, el("span", { class: "pcount", text: "/ …" }))),
    group(button("minus", "Smaller (-)", () => pvZoom(viewer, pv.zoom / 1.2)),
      el("button", { class: "ghost pzoom", title: "Fit the width (0)", onclick: () => { pv.fit = true; pvLayout(viewer); }, text: "100%" }),
      button("plus", "Bigger (+)", () => pvZoom(viewer, pv.zoom * 1.2))),
    group(tools, el("span", { class: "pdiv" }), style),
    group(button("undo", "Undo (⌘Z)", () => pvUndo(viewer, false)), button("redo", "Redo (⇧⌘Z)", () => pvUndo(viewer, true))),
    el("div", { class: "grow" }),
    el("div", { class: "pgroup pmore" }, button("more", "More", (event) => { event.stopPropagation(); pvMoreMenu(viewer, event.currentTarget); })));
  const thumbs = el("div", { class: "pthumbs" });
  const pages = el("div", { class: "ppages" });
  pages.addEventListener("scroll", () => { pv.scroll = pages.scrollTop; pvScrolled(viewer); }, { passive: true });
  // Pinch on the trackpad (WebKit's gesture events, or wheel with Ctrl as other engines send
  // it) and Ctrl/⌘ + mouse wheel zoom around the pointer.
  let pinching = false;
  pages.addEventListener("wheel", (event) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    // WebKit may report the same pinch as both gesture and Ctrl+wheel events: count it once.
    if (pinching) return;
    const step = Math.max(-0.5, Math.min(0.5, -event.deltaY * (event.deltaMode === 1 ? 0.05 : 0.0025)));
    pvZoomAt(viewer, pv.zoom * Math.exp(step), event.clientX, event.clientY);
  }, { passive: false });
  let pinchFrom = 1;
  pages.addEventListener("gesturestart", (event) => { event.preventDefault(); pinchFrom = pv.zoom; pinching = true; });
  pages.addEventListener("gesturechange", (event) => {
    event.preventDefault();
    pvZoomAt(viewer, pinchFrom * event.scale, event.clientX, event.clientY);
  });
  pages.addEventListener("gestureend", (event) => { event.preventDefault(); pinching = false; });
  thumbs.addEventListener("scroll", () => pvAskThumbs(viewer), { passive: true });
  const node = el("div", { class: "pdfview", tabindex: "0" }, bar, el("div", { class: "pmain" }, thumbs, pages));
  node.addEventListener("keydown", (event) => pvKey(viewer, event));
  pv.node = node;
  new ResizeObserver(() => { if (pv.fit && node.isConnected) pvLayout(viewer); }).observe(pages);
  pvChrome(viewer);
  pvBuild(viewer);
  return node;
}

// The color and width popover under the swatch button; a click outside closes it.
function pvStylePopover(viewer) {
  const pv = viewer.pv;
  const old = pv.node.querySelector(".pstyle");
  if (old) { old.remove(); return; }
  const button = pv.node.querySelector(".pstylebtn");
  const value = el("span", { class: "pwidthvalue", text: pv.width + " pt" });
  const width = el("input", { type: "range", min: "1", max: "24", value: String(pv.width), class: "pwidth", "aria-label": "Line width" });
  width.addEventListener("input", () => { pv.width = Number(width.value); value.textContent = pv.width + " pt"; pvRemember(pv); pvChrome(viewer); });
  const swatches = el("div", { class: "pcolors" }, ...PV_COLORS.map((color) => {
    const dot = el("button", { class: "pcolor" + (color === pv.color ? " on" : ""), title: color, "aria-label": "Color " + color,
      onclick: () => { pvColor(viewer, color); for (const item of swatches.children) item.classList.toggle("on", item === dot); } });
    dot.style.background = color;
    return dot;
  }));
  const box = el("div", { class: "pstyle" }, swatches, el("div", { class: "pwidthrow" }, width, value));
  pv.node.appendChild(box);
  const at = button.getBoundingClientRect(), host = pv.node.getBoundingClientRect();
  box.style.left = Math.max(8, Math.min(at.left - host.left - 8, host.width - box.offsetWidth - 8)) + "px";
  box.style.top = at.bottom - host.top + 6 + "px";
  setTimeout(() => document.addEventListener("mousedown", function away(event) {
    if (!box.contains(event.target) && !button.contains(event.target)) box.remove();
    if (!box.isConnected || !box.contains(event.target)) document.removeEventListener("mousedown", away, true);
  }, true));
}

// The rarely used actions, so the bar fits a narrow pane.
function pvMoreMenu(viewer, button) {
  closeTreeMenu();
  const item = (label, keys, run) => el("button", { class: "emi", onclick: () => { closeTreeMenu(); run(); } },
    el("span", { text: label }), keys ? el("kbd", { text: keys }) : null);
  const parts = [
    item("Fit the width", "⌘0", () => { viewer.pv.fit = true; pvLayout(viewer); }),
    item(viewer.pv.thumbs ? "Hide page thumbnails" : "Show page thumbnails", "", () => {
      viewer.pv.thumbs = !viewer.pv.thumbs; store("edit-pv-thumbs", viewer.pv.thumbs ? "1" : "0"); pvChrome(viewer); pvLayout(viewer);
    }),
    el("hr"),
  ];
  if (viewer.info.kind === "pdf") parts.push(item("Text view (select and search text)", "", () => { viewer.pv.native = true; drawPane(); }));
  parts.push(item("Open in its app", "", () => send({ op: "edit-open-app", path: viewer.path })),
    item("Show in Finder", "⌥⌘R", () => send({ op: "edit-reveal", path: viewer.path })));
  const menu = el("div", { class: "emenu", role: "menu" }, ...parts);
  ($(".edit") || document.body).appendChild(menu);
  const at = button.getBoundingClientRect();
  menu.style.left = Math.max(6, Math.min(at.right - menu.offsetWidth, innerWidth - menu.offsetWidth - 6)) + "px";
  menu.style.top = at.bottom + 6 + "px";
  setTimeout(() => document.addEventListener("mousedown", function away(click) {
    if (!menu.contains(click.target)) closeTreeMenu();
    document.removeEventListener("mousedown", away, true);
  }, true));
}

function pvRemember(pv) { store("edit-pv-tools", JSON.stringify({ color: pv.color, width: pv.width })); }

// Toolbar state: the chosen tool and color, the thumbnails strip, the page count.
function pvChrome(viewer) {
  const pv = viewer.pv;
  const node = pv.node;
  if (!node) return;
  for (const button of node.querySelectorAll(".ptool")) button.classList.toggle("on", button.dataset.tool === pv.tool);
  const swatch = node.querySelector(".pswatch");
  swatch.style.background = pv.color;
  swatch.style.setProperty("--w", Math.max(4, Math.min(14, 3 + pv.width / 2)) + "px");
  node.querySelector(".pthumbsbtn").classList.toggle("on", pv.thumbs);
  node.querySelector(".pthumbs").hidden = !pv.thumbs || !pv.pages || pv.pages.length < 2;
  node.querySelector(".pcount").textContent = "/ " + (pv.pages ? pv.pages.length : "…");
  // Kept in place (not hidden) so nothing next to it moves when the page count arrives.
  node.querySelector(".pgo").style.visibility = pv.pages && pv.pages.length > 1 ? "" : "hidden";
  node.querySelector(".pzoom").textContent = Math.round(pv.zoom * 100) + "%";
  node.querySelector(".ppages").dataset.tool = pv.tool;
}

// The page boxes (sized from the page sizes, so scrolling is right before any picture arrives).
function pvBuild(viewer) {
  const pv = viewer.pv;
  const pages = pv.node.querySelector(".ppages");
  const thumbs = pv.node.querySelector(".pthumbs");
  if (pv.error) { pages.replaceChildren(el("div", { class: "note", text: pv.error })); return; }
  if (!pv.pages) {
    if (pvIsPicture(viewer)) {
      // A picture is one page; its size comes from the picture itself.
      const probe = new Image();
      probe.onload = () => { pv.pages = [[probe.naturalWidth, probe.naturalHeight]]; pvBuild(viewer); pvChrome(viewer); };
      probe.onerror = () => {
        if (viewer.picture) probe.src = viewer.picture;
        else { pv.waitPicture = true; send({ op: "edit-render", path: viewer.path, width: 1600 }); }
      };
      probe.src = viewer.picture || rawUrl(viewer.path);
    }
    pages.replaceChildren(el("div", { class: "note", text: "Reading pages…" }));
    return;
  }
  pages.replaceChildren(...pv.pages.map((size, index) => {
    const number = index + 1;
    const image = el("img", { alt: "", draggable: "false" });
    const canvas = el("canvas", { class: "pink" });
    const page = el("div", { class: "ppage" }, image, canvas, el("span", { class: "plabel", text: String(number) }));
    page.dataset.page = String(number);
    pvPointer(viewer, canvas, number);
    return page;
  }));
  thumbs.replaceChildren(...pv.pages.map((size, index) => {
    const number = index + 1;
    const image = el("img", { alt: "", draggable: "false" });
    const box = el("div", { class: "pthumbimg" }, image, el("canvas"));
    box.style.aspectRatio = `${size[0]} / ${size[1]}`;
    const item = el("button", { class: "pthumb", title: "Page " + number, onclick: () => pvGo(viewer, number) }, box, el("span", { text: String(number) }));
    item.dataset.page = String(number);
    return item;
  }));
  pvChrome(viewer);
  pvLayout(viewer);
  requestAnimationFrame(() => pvDrawAll(viewer));
  if (pv.scroll) pages.scrollTop = pv.scroll;
}

// Sizes every page for the zoom (fit = the widest page fills the column).
// `placed`: the caller puts the scroll position itself (zoom around the pointer).
function pvLayout(viewer, placed) {
  const pv = viewer.pv;
  if (!pv || !pv.node || !pv.pages) return;
  const pages = pv.node.querySelector(".ppages");
  const widest = Math.max(...pv.pages.map((size) => size[0]));
  if (pv.fit && pages.clientWidth > 0) pv.zoom = Math.max(0.1, Math.min(8, (pages.clientWidth - 60) / widest));
  const keep = pvAnchor(viewer);
  for (const page of pages.querySelectorAll(".ppage")) {
    const [w, h] = pv.pages[Number(page.dataset.page) - 1];
    page.style.width = Math.round(w * pv.zoom) + "px";
    page.style.height = Math.round(h * pv.zoom) + "px";
  }
  for (const canvas of pages.querySelectorAll("canvas.pink")) pvDraw(viewer, Number(canvas.parentNode.dataset.page));
  if (keep && !placed) pvGo(viewer, keep.page, keep.offset, true);
  pvChrome(viewer);
  if (!placed) pvScrolled(viewer);
}

// Where the top of the view is (page and fraction), so a zoom keeps the same place.
function pvAnchor(viewer) {
  const pages = viewer.pv.node.querySelector(".ppages");
  for (const page of pages.querySelectorAll(".ppage")) {
    if (page.offsetTop + page.offsetHeight > pages.scrollTop) {
      return { page: Number(page.dataset.page), offset: (pages.scrollTop - page.offsetTop) / Math.max(1, page.offsetHeight) };
    }
  }
  return null;
}

function pvGo(viewer, number, offset = 0, instant = false) {
  const pv = viewer.pv;
  if (!pv.pages) return;
  number = Math.max(1, Math.min(pv.pages.length, Math.round(number)));
  const pages = pv.node.querySelector(".ppages");
  const page = pages.querySelector(`.ppage[data-page="${number}"]`);
  if (!page) return;
  pages.scrollTo({ top: page.offsetTop - 16 + offset * page.offsetHeight, behavior: instant ? "instant" : "smooth" });
  pv.current = number;
  pvMarkCurrent(viewer);
}

function pvZoom(viewer, zoom) {
  const pages = viewer.pv.node && viewer.pv.node.querySelector(".ppages");
  if (!pages) return;
  const box = pages.getBoundingClientRect();
  pvZoomAt(viewer, zoom, box.left + box.width / 2, box.top + box.height / 3);
}

// Zoom keeping the spot under (x, y) (window coordinates) where it is, as Preview does.
function pvZoomAt(viewer, zoom, x, y) {
  const pv = viewer.pv;
  const pages = pv.node && pv.node.querySelector(".ppages");
  if (!pages || !pv.pages) return;
  zoom = Math.max(0.1, Math.min(8, zoom));
  if (Math.abs(zoom - pv.zoom) < 0.0005) return;
  const box = pages.getBoundingClientRect();
  const viewX = x - box.left, viewY = y - box.top;
  // The spot as (page, fraction of that page) before the change.
  let spot = null;
  for (const page of pages.querySelectorAll(".ppage")) {
    const rect = page.getBoundingClientRect();
    if (y >= rect.top - 9 && y <= rect.bottom + 9) {
      spot = { page, fx: (x - rect.left) / rect.width, fy: (y - rect.top) / rect.height };
      break;
    }
  }
  pv.fit = false;
  pv.zoom = zoom;
  pvLayout(viewer, true);
  if (spot) {
    // Measured on screen after the new sizes (offsetTop counts from another box), then the
    // view is scrolled by the difference so that spot is back under the pointer.
    const rect = spot.page.getBoundingClientRect();
    pages.scrollLeft += rect.left + spot.fx * rect.width - (box.left + viewX);
    pages.scrollTop += rect.top + spot.fy * rect.height - (box.top + viewY);
  }
  pv.scroll = pages.scrollTop;
  pvScrolled(viewer);
}

// ⌘+ ⌘− ⌘0 (and ⌘=), ⌘Z ⇧⌘Z while a page viewer is shown, wherever the focus is (not while
// typing in a field); true when it was one of them.
function pvZoomKey(event) {
  if (!(event.metaKey || event.ctrlKey) || event.altKey) return false;
  const viewer = edit.viewers.find((item) => item.path === edit.showing);
  if (!viewer || !viewer.pv || !viewer.pv.node || !viewer.pv.node.isConnected || viewer.pv.native) return false;
  const typing = event.target && event.target.closest && event.target.closest("input, textarea, select");
  if (event.code === "KeyZ" && !typing) pvUndo(viewer, event.shiftKey);
  else if (event.code === "Equal" || event.code === "NumpadAdd") pvZoom(viewer, viewer.pv.zoom * 1.2);
  else if (event.code === "Minus" || event.code === "NumpadSubtract") pvZoom(viewer, viewer.pv.zoom / 1.2);
  else if (event.code === "Digit0" || event.code === "Numpad0") { viewer.pv.fit = true; pvLayout(viewer); }
  else return false;
  event.preventDefault();
  event.stopPropagation();
  return true;
}

// ---------- pictures of the pages ----------

// Render widths go in steps, so a small zoom change reuses the pictures already drawn.
function pvRenderWidth(viewer, size) {
  const want = size[0] * viewer.pv.zoom * (window.devicePixelRatio || 1);
  return Math.max(200, Math.min(4000, Math.ceil(want / 200) * 200));
}

function pvScrolled(viewer) {
  const pv = viewer.pv;
  if (!pv.pages || !pv.node) return;
  const pages = pv.node.querySelector(".ppages");
  const top = pages.scrollTop, bottom = top + pages.clientHeight, middle = top + pages.clientHeight / 3;
  const near = [];
  let current = pv.current;
  for (const page of pages.querySelectorAll(".ppage")) {
    const start = page.offsetTop, end = start + page.offsetHeight;
    if (end > top - 1200 && start < bottom + 1200) near.push(Number(page.dataset.page));
    if (start <= middle && end > middle) current = Number(page.dataset.page);
  }
  if (current !== pv.current) { pv.current = current; pvMarkCurrent(viewer); }
  if (pvIsPicture(viewer)) { pvShowPicture(viewer); return; }
  // A pinch changes the width every frame: ask for pictures once it settles (the ones shown
  // meanwhile are stretched).
  clearTimeout(pv.askTimer);
  pv.askTimer = setTimeout(() => pvAskPages(viewer, near), 120);
  pvAskThumbs(viewer);
}

function pvAskPages(viewer, near) {
  const pv = viewer.pv;
  if (!pv.pages || !pv.node) return;
  const missing = near.filter((number) => {
    const width = pvRenderWidth(viewer, pv.pages[number - 1]);
    const key = width + ":" + number;
    if (pv.urls[key]) { pvSetImage(viewer, number, pv.urls[key]); return false; }
    return !pv.asked.has(key);
  });
  for (let index = 0; index < missing.length; index += PV_BATCH) {
    const run = missing.slice(index, index + PV_BATCH);
    const width = pvRenderWidth(viewer, pv.pages[run[0] - 1]);
    for (const number of run) pv.asked.add(width + ":" + number);
    send({ op: "edit-render", path: viewer.path, page: run[0], to: run[run.length - 1], width, tag: "p" + width });
  }
}

function pvShowPicture(viewer) {
  const source = viewer.picture || rawUrl(viewer.path);
  const image = viewer.pv.node.querySelector('.ppage[data-page="1"] img');
  if (image && image.getAttribute("src") !== source) image.src = source;
}

function pvAskThumbs(viewer) {
  const pv = viewer.pv;
  if (!pv.pages || !pv.thumbs || pv.pages.length < 2 || pvIsPicture(viewer)) return;
  const strip = pv.node.querySelector(".pthumbs");
  const top = strip.scrollTop - 600, bottom = strip.scrollTop + strip.clientHeight + 600;
  const wanted = [];
  for (const item of strip.querySelectorAll(".pthumb")) {
    if (item.offsetTop + item.offsetHeight < top || item.offsetTop > bottom) continue;
    const number = Number(item.dataset.page);
    if (!pv.thumbUrls[number] && !pv.thumbAsked.has(number)) wanted.push(number);
  }
  for (let index = 0; index < wanted.length; index += PV_THUMB_BATCH) {
    const run = wanted.slice(index, index + PV_THUMB_BATCH);
    for (const number of run) pv.thumbAsked.add(number);
    send({ op: "edit-render", path: viewer.path, page: run[0], to: run[run.length - 1], width: PV_THUMB_WIDTH, tag: "t" });
  }
}

function pvSetImage(viewer, number, url) {
  const image = viewer.pv.node && viewer.pv.node.querySelector(`.ppage[data-page="${number}"] img`);
  if (image && image.getAttribute("src") !== url) image.src = url;
}

function pvMarkCurrent(viewer) {
  const pv = viewer.pv;
  const node = pv.node;
  if (!node) return;
  const box = node.querySelector(".pnum");
  if (document.activeElement !== box) box.value = String(pv.current);
  for (const item of node.querySelectorAll(".pthumb.on")) item.classList.remove("on");
  const item = node.querySelector(`.pthumb[data-page="${pv.current}"]`);
  if (item) { item.classList.add("on"); item.scrollIntoView({ block: "nearest" }); }
}

// Answers of `ul doc` for this viewer (pages, pictures, drawings); false when not ours.
function pvReceive(message) {
  const viewer = edit.viewers.find((item) => item.path === message.path);
  if (!viewer || !viewer.pv) return false;
  const pv = viewer.pv;
  if (message.type === "edit-pages") {
    if (message.error) pv.error = "Could not read the pages: " + message.error;
    else pv.pages = message.result.sizes.map((size) => [Number(size[0]) || 612, Number(size[1]) || 792]);
    if (pv.node) pvBuild(viewer);
    return true;
  }
  if (message.type === "edit-ink") {
    pv.ink = message.ink && message.ink.pages ? message.ink : { version: 1, pages: {} };
    if (pv.node && pv.pages) for (let number = 1; number <= pv.pages.length; number += 1) pvDraw(viewer, number);
    return true;
  }
  if (message.type === "edit-render" && pvIsPicture(viewer) && pv.waitPicture) {
    pv.waitPicture = false;
    if (message.error) { pv.error = "No preview: " + message.error; pvBuild(viewer); return true; }
    viewer.picture = "ulapp://localhost/edit/cache/" + message.result.png.split("/").pop();
    pvBuild(viewer);
    return true;
  }
  if (message.type !== "edit-render" || typeof message.tag !== "string") return false;
  if (message.error) { showEditError(`${viewer.name}: ${message.error}`); return true; }
  for (const item of message.result.pngs || []) {
    const url = "ulapp://localhost/edit/cache/" + item.png.split("/").pop();
    if (message.tag === "t") {
      pv.thumbUrls[item.page] = url;
      const image = pv.node && pv.node.querySelector(`.pthumb[data-page="${item.page}"] img`);
      if (image) image.src = url;
    } else {
      pv.urls[message.tag.slice(1) + ":" + item.page] = url;
      // Only when it is the width the page wants now (a zoom may have moved on).
      if (pv.pages && pvRenderWidth(viewer, pv.pages[item.page - 1]) === Number(message.tag.slice(1))) pvSetImage(viewer, item.page, url);
      else if (!pv.node.querySelector(`.ppage[data-page="${item.page}"] img`).getAttribute("src")) pvSetImage(viewer, item.page, url);
    }
  }
  return true;
}

// ---------- drawings ----------

function pvItems(viewer, number, create) {
  const pv = viewer.pv;
  if (!pv.ink) pv.ink = { version: 1, pages: {} };
  const key = String(number);
  if (!pv.ink.pages[key] && create) pv.ink.pages[key] = [];
  return pv.ink.pages[key] || [];
}

function pvChange(viewer, change) {
  const pv = viewer.pv;
  pv.undo.push(JSON.stringify(pv.ink || { version: 1, pages: {} }));
  if (pv.undo.length > 200) pv.undo.shift();
  pv.redo = [];
  change();
  for (const [key, items] of Object.entries(pv.ink.pages)) if (!items.length) delete pv.ink.pages[key];
  pvSave(viewer);
}

function pvSave(viewer) {
  const pv = viewer.pv;
  clearTimeout(pv.saveTimer);
  pv.saveTimer = setTimeout(() => send({ op: "edit-ink-save", path: viewer.path, ink: pv.ink }), 500);
}

function pvUndo(viewer, again) {
  const pv = viewer.pv;
  const from = again ? pv.redo : pv.undo, to = again ? pv.undo : pv.redo;
  if (!from.length) return;
  to.push(JSON.stringify(pv.ink));
  pv.ink = JSON.parse(from.pop());
  pv.selected = null;
  pvSave(viewer);
  pvDrawAll(viewer);
}

function pvDrawAll(viewer) {
  if (viewer.pv.pages) for (let number = 1; number <= viewer.pv.pages.length; number += 1) pvDraw(viewer, number);
}

function pvTool(viewer, tool) {
  const pv = viewer.pv;
  pv.tool = tool;
  pv.threadPull = null;
  pv.selected = null;
  pvChrome(viewer);
  pvDrawAll(viewer);
  pv.node.focus();
}

function pvColor(viewer, color) {
  const pv = viewer.pv;
  pv.color = color;
  pvRemember(pv);
  if (pv.selected) {
    const item = pvItems(viewer, pv.selected.page)[pv.selected.index];
    if (item) pvChange(viewer, () => { item.color = color; });
    pvDraw(viewer, pv.selected.page);
  }
  if (pv.tool === "hand" || pv.tool === "eraser") pv.tool = "pen";
  pvChrome(viewer);
}

function pvCanvas(viewer, number) {
  return viewer.pv.node && viewer.pv.node.querySelector(`.ppage[data-page="${number}"] canvas`);
}

function pvStickyById(items, id) { return items.find((item) => item.kind === "sticky" && item.id === id); }

// A thread end: a point, or a spot on a sticky (`{id, fx, fy}`, fractions of its box, so the
// thread stays tied there when the sticky moves; without fx/fy: its top pin).
function pvEnd(items, end) {
  if (Array.isArray(end)) return { x: end[0], y: end[1] };
  const sticky = end && pvStickyById(items, end.id);
  if (!sticky) return null;
  const fx = Number.isFinite(end.fx) ? Math.max(0, Math.min(1, end.fx)) : 0.5;
  const fy = Number.isFinite(end.fy) ? Math.max(0, Math.min(1, end.fy)) : 10 / sticky.h;
  return { x: sticky.x + fx * sticky.w, y: sticky.y + fy * sticky.h };
}

const PV_SNAP = 14;

// Where a thread end lands at `point`: on a pin already there (another thread's end or a
// sticky's pin, so threads share it), else on the sticky under it, else on the point itself.
// `skip` is the thread being changed (its own ends never attract it).
function pvSnap(viewer, items, point, skip) {
  const reach = PV_SNAP / viewer.pv.zoom;
  let best = null, distance = reach;
  const consider = (at, end) => {
    const gap = Math.hypot(at.x - point.x, at.y - point.y);
    if (gap <= distance) { distance = gap; best = end; }
  };
  for (const item of items) {
    if (item.kind === "sticky") consider({ x: item.x + item.w / 2, y: item.y + 10 }, { id: item.id });
    if (item.kind !== "thread" || item === skip) continue;
    for (const end of [item.from, item.to]) {
      const at = pvEnd(items, end);
      if (at) consider(at, Array.isArray(end) ? [at.x, at.y] : { ...end });
    }
  }
  if (best) return best;
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (item.kind === "sticky" && point.x >= item.x && point.x <= item.x + item.w && point.y >= item.y && point.y <= item.y + item.h) {
      const round = (value) => Math.round(value * 1000) / 1000;
      return { id: item.id, fx: round((point.x - item.x) / item.w), fy: round((point.y - item.y) / item.h) };
    }
  }
  return [Math.round(point.x * 10) / 10, Math.round(point.y * 10) / 10];
}

function pvSameEnd(items, a, b) {
  const one = pvEnd(items, a), two = pvEnd(items, b);
  return one && two && Math.hypot(one.x - two.x, one.y - two.y) < 1;
}

// The end of a thread near `point` that can be dragged: any end of the selected thread,
// and loose (point) ends of the others.
function pvEndAt(viewer, number, point) {
  const pv = viewer.pv;
  const items = pvItems(viewer, number, false);
  const reach = 10 / pv.zoom;
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (item.kind !== "thread") continue;
    const chosen = pv.selected && pv.selected.page === number && pv.selected.index === index;
    for (const which of ["from", "to"]) {
      if (!chosen && !Array.isArray(item[which])) continue;
      const at = pvEnd(items, item[which]);
      if (at && Math.hypot(at.x - point.x, at.y - point.y) <= reach) return { item, index, which };
    }
  }
  return null;
}

// Sagging string between two points, like thread on a cork board.
function pvThreadCurve(a, b) {
  const length = Math.hypot(b.x - a.x, b.y - a.y);
  return { a, b, c: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 + Math.min(80, length * 0.18) } };
}

function pvWrap(ctx, text, width) {
  const lines = [];
  for (const paragraph of String(text || "").split("\n")) {
    let line = "";
    for (const word of paragraph.split(" ")) {
      const next = line ? line + " " + word : word;
      if (ctx.measureText(next).width > width && line) { lines.push(line); line = word; } else line = next;
    }
    lines.push(line);
  }
  return lines;
}

function pvDraw(viewer, number) {
  const pv = viewer.pv;
  pvPaint(viewer, number, pvCanvas(viewer, number), pv.zoom, true);
  // The thumbnail shows the drawings too.
  const thumb = pv.node && pv.node.querySelector(`.pthumb[data-page="${number}"] canvas`);
  if (thumb && pv.pages && thumb.parentNode.clientWidth) pvPaint(viewer, number, thumb, thumb.parentNode.clientWidth / pv.pages[number - 1][0], false);
}

function pvPaint(viewer, number, canvas, zoom, live) {
  const pv = viewer.pv;
  if (!canvas || !pv.pages) return;
  const [w, h] = pv.pages[number - 1];
  const ratio = window.devicePixelRatio || 1;
  const width = Math.round(w * zoom * ratio), height = Math.round(h * zoom * ratio);
  if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.setTransform(zoom * ratio, 0, 0, zoom * ratio, 0, 0);
  const items = pvItems(viewer, number, false);
  const selected = live && pv.selected && pv.selected.page === number ? pv.selected.index : -1;
  const pins = [];
  items.forEach((item, index) => {
    ctx.save();
    if (item.kind === "pen" || item.kind === "marker") {
      ctx.strokeStyle = item.color || PV_COLORS[0];
      ctx.lineWidth = item.width || 3;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      if (item.kind === "marker") ctx.globalAlpha = 0.35;
      ctx.beginPath();
      (item.points || []).forEach(([x, y], at) => (at ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      if ((item.points || []).length === 1) ctx.lineTo(item.points[0][0] + 0.1, item.points[0][1]);
      ctx.stroke();
    } else if (item.kind === "text") {
      ctx.fillStyle = item.color || "#1d1d1f";
      ctx.font = `${item.size || 16}px -apple-system, system-ui, sans-serif`;
      ctx.textBaseline = "top";
      pvWrap(ctx, item.text, 10000).forEach((line, at) => ctx.fillText(line, item.x, item.y + at * (item.size || 16) * 1.25));
    } else if (item.kind === "sticky") {
      ctx.shadowColor = "rgba(0,0,0,.25)";
      ctx.shadowBlur = 8;
      ctx.shadowOffsetY = 3;
      ctx.fillStyle = item.color || PV_STICKY;
      ctx.fillRect(item.x, item.y, item.w, item.h);
      ctx.shadowColor = "transparent";
      ctx.fillStyle = "#2b2b2b";
      ctx.font = "13px -apple-system, system-ui, sans-serif";
      ctx.textBaseline = "top";
      ctx.beginPath();
      ctx.rect(item.x, item.y, item.w, item.h);
      ctx.clip();
      pvWrap(ctx, item.text, item.w - 16).forEach((line, at) => ctx.fillText(line, item.x + 8, item.y + 18 + at * 16));
    } else if (item.kind === "thread") {
      const a = pvEnd(items, item.from), b = pvEnd(items, item.to);
      if (a && b) {
        const curve = pvThreadCurve(a, b);
        ctx.strokeStyle = item.color || PV_THREAD;
        ctx.lineWidth = 2;
        ctx.shadowColor = "rgba(0,0,0,.3)";
        ctx.shadowOffsetY = 1.5;
        ctx.shadowBlur = 2;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.quadraticCurveTo(curve.c.x, curve.c.y, b.x, b.y);
        ctx.stroke();
        pins.push(a, b);
      }
    }
    ctx.restore();
    if (index === selected) {
      const box = pvBounds(ctx, items, item);
      if (box) {
        ctx.save();
        ctx.strokeStyle = "#0091ff";
        ctx.lineWidth = 1.5 / zoom;
        ctx.setLineDash([4 / zoom, 3 / zoom]);
        ctx.strokeRect(box.x - 4, box.y - 4, box.w + 8, box.h + 8);
        ctx.restore();
      }
    }
  });
  // Stickies get a pin too, even without thread; pins go over everything, one per spot.
  for (const item of items) if (item.kind === "sticky") pins.push({ x: item.x + item.w / 2, y: item.y + 10 });
  const drawn = [];
  for (const pin of pins) {
    if (drawn.some((other) => Math.hypot(other.x - pin.x, other.y - pin.y) < 1)) continue;
    drawn.push(pin);
    pvPin(ctx, pin);
  }
  if (!live) return;
  // The chosen thread shows its ends as handles (drag one to tie it elsewhere).
  const chosen = selected >= 0 && items[selected] && items[selected].kind === "thread" ? items[selected] : null;
  if (chosen) for (const end of [chosen.from, chosen.to]) { const at = pvEnd(items, end); if (at) pvHandle(ctx, at, zoom); }
  // While a thread is being pulled: where it would land (a sticky lights up).
  const pull = pv.threadPull && pv.threadPull.page === number ? pv.threadPull : null;
  if (pull) {
    const a = pvEnd(items, pull.start);
    const target = pull.hover ? pvSnap(viewer, items, pull.hover, null) : null;
    const b = target && pvEnd(items, target);
    if (a && b) {
      if (!Array.isArray(target)) {
        const sticky = pvStickyById(items, target.id);
        if (sticky) {
          ctx.save();
          ctx.strokeStyle = PV_THREAD;
          ctx.lineWidth = 2 / zoom;
          ctx.setLineDash([5 / zoom, 4 / zoom]);
          ctx.strokeRect(sticky.x - 3, sticky.y - 3, sticky.w + 6, sticky.h + 6);
          ctx.restore();
        }
      }
      const curve = pvThreadCurve(a, b);
      ctx.save();
      ctx.strokeStyle = PV_THREAD;
      ctx.globalAlpha = 0.7;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.quadraticCurveTo(curve.c.x, curve.c.y, b.x, b.y);
      ctx.stroke();
      ctx.restore();
      pvPin(ctx, a);
      pvPin(ctx, b);
    }
  }
}

function pvHandle(ctx, at, zoom) {
  ctx.save();
  ctx.fillStyle = "#ffffff";
  ctx.strokeStyle = "#0091ff";
  ctx.lineWidth = 2 / zoom;
  ctx.beginPath();
  ctx.arc(at.x, at.y, 7 / zoom, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function pvPin(ctx, at) {
  ctx.save();
  ctx.fillStyle = "#c62828";
  ctx.shadowColor = "rgba(0,0,0,.35)";
  ctx.shadowBlur = 3;
  ctx.shadowOffsetY = 1.5;
  ctx.beginPath();
  ctx.arc(at.x, at.y, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowColor = "transparent";
  ctx.fillStyle = "rgba(255,255,255,.7)";
  ctx.beginPath();
  ctx.arc(at.x - 1.5, at.y - 1.5, 1.6, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

// The box an item covers (page points), for hit tests and the selection frame.
function pvBounds(ctx, items, item) {
  if (item.kind === "sticky") return { x: item.x, y: item.y, w: item.w, h: item.h };
  if (item.kind === "text") {
    ctx.save();
    ctx.font = `${item.size || 16}px -apple-system, system-ui, sans-serif`;
    const lines = pvWrap(ctx, item.text, 10000);
    const width = Math.max(8, ...lines.map((line) => ctx.measureText(line).width));
    ctx.restore();
    return { x: item.x, y: item.y, w: width, h: lines.length * (item.size || 16) * 1.25 };
  }
  let points = item.points || [];
  if (item.kind === "thread") {
    const a = pvEnd(items, item.from), b = pvEnd(items, item.to);
    if (!a || !b) return null;
    const curve = pvThreadCurve(a, b);
    points = [[a.x, a.y], [curve.c.x, (curve.c.y + a.y) / 2], [b.x, b.y]];
  }
  if (!points.length) return null;
  const xs = points.map((point) => point[0]), ys = points.map((point) => point[1]);
  const pad = (item.width || 2) / 2;
  return { x: Math.min(...xs) - pad, y: Math.min(...ys) - pad, w: Math.max(...xs) - Math.min(...xs) + pad * 2, h: Math.max(...ys) - Math.min(...ys) + pad * 2 };
}

function pvNearSegment(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const t = dx || dy ? Math.max(0, Math.min(1, ((p.x - a[0]) * dx + (p.y - a[1]) * dy) / (dx * dx + dy * dy))) : 0;
  return Math.hypot(p.x - (a[0] + t * dx), p.y - (a[1] + t * dy));
}

// The topmost item under a point (index), or -1.
function pvHit(viewer, number, point) {
  const items = pvItems(viewer, number, false);
  const slack = 6 / viewer.pv.zoom;
  const ctx = pvCanvas(viewer, number).getContext("2d");
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (item.kind === "pen" || item.kind === "marker") {
      const points = item.points || [];
      const reach = (item.width || 3) / 2 + slack;
      for (let at = 0; at < points.length; at += 1) {
        if (pvNearSegment(point, points[at], points[Math.min(at + 1, points.length - 1)]) <= reach) return index;
      }
    } else if (item.kind === "thread") {
      const a = pvEnd(items, item.from), b = pvEnd(items, item.to);
      if (!a || !b) continue;
      const curve = pvThreadCurve(a, b);
      let last = [a.x, a.y];
      for (let step = 1; step <= 24; step += 1) {
        const t = step / 24;
        const x = (1 - t) * (1 - t) * a.x + 2 * (1 - t) * t * curve.c.x + t * t * b.x;
        const y = (1 - t) * (1 - t) * a.y + 2 * (1 - t) * t * curve.c.y + t * t * b.y;
        if (pvNearSegment(point, last, [x, y]) <= slack + 2) return index;
        last = [x, y];
      }
    } else {
      const box = pvBounds(ctx, items, item);
      if (box && point.x >= box.x - slack && point.x <= box.x + box.w + slack && point.y >= box.y - slack && point.y <= box.y + box.h + slack) return index;
    }
  }
  return -1;
}

function pvPoint(viewer, canvas, event) {
  const rect = canvas.getBoundingClientRect();
  return { x: (event.clientX - rect.left) / viewer.pv.zoom, y: (event.clientY - rect.top) / viewer.pv.zoom };
}

let pvNextId = 0;
function pvId() { pvNextId += 1; return Date.now().toString(36) + pvNextId.toString(36); }

function pvPointer(viewer, canvas, number) {
  let drag = null;
  canvas.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    const pv = viewer.pv;
    pv.node.focus({ preventScroll: true });
    const point = pvPoint(viewer, canvas, event);
    const items = pvItems(viewer, number, false);
    const hit = pvHit(viewer, number, point);
    if (pv.tool === "pen" || pv.tool === "marker") {
      const item = { kind: pv.tool, color: pv.color, width: pv.tool === "marker" ? Math.max(10, pv.width * 4) : pv.width, points: [[point.x, point.y]] };
      pv.undo.push(JSON.stringify(pv.ink || { version: 1, pages: {} }));
      pv.redo = [];
      pvItems(viewer, number, true).push(item);
      drag = { kind: "stroke", item };
    } else if (pv.tool === "eraser") {
      pv.undo.push(JSON.stringify(pv.ink || { version: 1, pages: {} }));
      pv.redo = [];
      drag = { kind: "erase", erased: false };
      drag.erased = pvErase(viewer, number, point) || drag.erased;
    } else if (pv.tool === "text" || pv.tool === "sticky") {
      if (hit >= 0 && (items[hit].kind === pv.tool)) { pvEditText(viewer, number, hit); return; }
      let index = 0;
      pvChange(viewer, () => {
        const list = pvItems(viewer, number, true);
        list.push(pv.tool === "text"
          ? { kind: "text", x: point.x, y: point.y - 8, text: "", color: pv.color, size: 16 }
          : { kind: "sticky", id: pvId(), x: point.x - 80, y: point.y - 20, w: 170, h: 120, text: "", color: PV_STICKY });
        index = list.length - 1;
      });
      pvDraw(viewer, number);
      pvEditText(viewer, number, index, true);
      return;
    } else if (pv.tool === "thread") {
      // Drag from one place to another, or click one and then the other. Each thread is its
      // own: nothing chains on by itself.
      if (pv.threadPull && pv.threadPull.page === number && pv.threadPull.clicked) {
        pvFinishThread(viewer, number, point);
        return;
      }
      pv.threadPull = { page: number, start: pvSnap(viewer, items, point, null), from: point, hover: point, clicked: false };
      drag = { kind: "thread" };
      pvDraw(viewer, number);
    } else {
      const grip = pvEndAt(viewer, number, point);
      if (grip) {
        pv.undo.push(JSON.stringify(pv.ink));
        pv.redo = [];
        pv.selected = { page: number, index: grip.index };
        drag = { kind: "end", grip, moved: false };
        canvas.setPointerCapture(event.pointerId);
        event.preventDefault();
        return;
      }
      pv.selected = hit >= 0 ? { page: number, index: hit } : null;
      pvDrawAll(viewer);
      if (hit >= 0) {
        pv.undo.push(JSON.stringify(pv.ink));
        pv.redo = [];
        drag = { kind: "move", item: items[hit], from: point, moved: false };
      }
    }
    canvas.setPointerCapture(event.pointerId);
    event.preventDefault();
  });
  canvas.addEventListener("pointermove", (event) => {
    const pv = viewer.pv;
    const point = pvPoint(viewer, canvas, event);
    if (pv.tool === "thread" && pv.threadPull && pv.threadPull.page === number) { pv.threadPull.hover = point; pvDraw(viewer, number); }
    if (!drag) {
      if (pv.tool === "hand") canvas.style.cursor = pvEndAt(viewer, number, point) ? "grab" : pvHit(viewer, number, point) >= 0 ? "move" : "";
      return;
    }
    if (drag.kind === "end") {
      drag.moved = true;
      drag.grip.item[drag.grip.which] = [point.x, point.y];
      pv.threadPull = null;
      pvDraw(viewer, number);
      return;
    }
    if (drag.kind === "stroke") { drag.item.points.push([Math.round(point.x * 10) / 10, Math.round(point.y * 10) / 10]); pvDraw(viewer, number); }
    else if (drag.kind === "erase") { drag.erased = pvErase(viewer, number, point) || drag.erased; }
    else if (drag.kind === "move") {
      const dx = point.x - drag.from.x, dy = point.y - drag.from.y;
      drag.from = point;
      drag.moved = true;
      pvMove(drag.item, dx, dy);
      pvDraw(viewer, number);
    }
  });
  const end = (event) => {
    if (!drag) return;
    const pv = viewer.pv;
    if (drag.kind === "thread") {
      drag = null;
      const pull = pv.threadPull;
      if (!pull) return;
      const point = pvPoint(viewer, canvas, event);
      // A short press is a click: the thread waits for the second click.
      if (Math.hypot(point.x - pull.from.x, point.y - pull.from.y) * pv.zoom < 6) { pull.clicked = true; return; }
      pvFinishThread(viewer, number, point);
      return;
    }
    if (drag.kind === "end") {
      const { item, which } = drag.grip;
      const items = pvItems(viewer, number, false);
      if (drag.moved) {
        item[which] = pvSnap(viewer, items, pvEnd(items, item[which]), item);
        const other = which === "from" ? item.to : item.from;
        if (pvSameEnd(items, item[which], other)) items.splice(items.indexOf(item), 1);
        pvSave(viewer);
      } else pv.undo.pop();
      drag = null;
      pvDraw(viewer, number);
      return;
    }
    if (drag.kind === "stroke" || (drag.kind === "move" && drag.moved) || (drag.kind === "erase" && drag.erased)) pvSave(viewer);
    else pv.undo.pop();
    drag = null;
  };
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);
  canvas.addEventListener("dblclick", (event) => {
    const point = pvPoint(viewer, canvas, event);
    const hit = pvHit(viewer, number, point);
    const item = hit >= 0 && pvItems(viewer, number, false)[hit];
    if (item && (item.kind === "text" || item.kind === "sticky")) pvEditText(viewer, number, hit);
  });
}

// The second end of the thread being pulled; a thread from a spot to itself is dropped.
function pvFinishThread(viewer, number, point) {
  const pv = viewer.pv;
  const pull = pv.threadPull;
  pv.threadPull = null;
  if (!pull) return;
  const items = pvItems(viewer, number, false);
  const to = pvSnap(viewer, items, point, null);
  if (!pvSameEnd(items, pull.start, to)) {
    pvChange(viewer, () => pvItems(viewer, number, true).push({ kind: "thread", from: pull.start, to, color: PV_THREAD }));
  }
  pvDraw(viewer, number);
}

function pvMove(item, dx, dy) {
  if (item.points) item.points = item.points.map(([x, y]) => [x + dx, y + dy]);
  if (typeof item.x === "number") { item.x += dx; item.y += dy; }
  if (item.kind === "thread") {
    if (Array.isArray(item.from)) item.from = [item.from[0] + dx, item.from[1] + dy];
    if (Array.isArray(item.to)) item.to = [item.to[0] + dx, item.to[1] + dy];
  }
}

// Erasing a sticky also drops the threads tied to it.
function pvErase(viewer, number, point) {
  const hit = pvHit(viewer, number, point);
  if (hit < 0) return false;
  const items = pvItems(viewer, number, false);
  const [gone] = items.splice(hit, 1);
  if (gone.kind === "sticky") {
    for (let index = items.length - 1; index >= 0; index -= 1) {
      const item = items[index];
      if (item.kind === "thread" && ((item.from && item.from.id === gone.id) || (item.to && item.to.id === gone.id))) items.splice(index, 1);
    }
  }
  viewer.pv.selected = null;
  pvDraw(viewer, number);
  return true;
}

// A text or sticky is typed in a field over the page; empty text removes it.
function pvEditText(viewer, number, index, fresh) {
  const pv = viewer.pv;
  const page = pv.node.querySelector(`.ppage[data-page="${number}"]`);
  const items = pvItems(viewer, number, false);
  const item = items[index];
  if (!page || !item) return;
  page.querySelector("textarea.pedit")?.blur();
  const field = el("textarea", { class: "pedit" + (item.kind === "sticky" ? " sticky" : ""), spellcheck: "false" });
  field.value = item.text || "";
  const zoom = pv.zoom;
  field.style.left = item.x * zoom + "px";
  field.style.top = item.y * zoom + "px";
  if (item.kind === "sticky") {
    field.style.width = item.w * zoom + "px";
    field.style.height = item.h * zoom + "px";
    field.style.fontSize = 13 * zoom + "px";
    field.style.paddingTop = 18 * zoom + "px";
    field.style.lineHeight = 16 * zoom + "px";
    field.style.background = item.color || PV_STICKY;
  } else {
    field.style.fontSize = (item.size || 16) * zoom + "px";
    field.style.color = item.color || "#1d1d1f";
    field.style.minWidth = 160 * zoom + "px";
  }
  const before = item.text || "";
  const hidden = item.text;
  item.text = "";
  pvDraw(viewer, number);
  item.text = hidden;
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    const text = field.value.replace(/\s+$/, "");
    field.remove();
    if (text === before && !fresh) { pvDraw(viewer, number); return; }
    const apply = () => {
      const list = pvItems(viewer, number, true);
      const at = list.indexOf(item);
      if (!text && at >= 0) list.splice(at, 1);
      else item.text = text;
    };
    if (fresh) {
      // Adding it already took one undo step: the text belongs to the same step.
      apply();
      if (!text) pv.undo.pop();
      for (const [key, list] of Object.entries(pv.ink.pages)) if (!list.length) delete pv.ink.pages[key];
      pvSave(viewer);
    } else pvChange(viewer, apply);
    pv.selected = null;
    pvDraw(viewer, number);
    pv.node.focus({ preventScroll: true });
  };
  field.addEventListener("keydown", (event) => {
    event.stopPropagation();
    if (event.key === "Escape" || (event.key === "Enter" && (event.metaKey || item.kind === "text") && !event.shiftKey)) { event.preventDefault(); finish(); }
  });
  field.addEventListener("blur", finish);
  page.appendChild(field);
  requestAnimationFrame(() => { field.focus(); field.select(); });
}

function pvKey(viewer, event) {
  if (event.target.closest("textarea, input")) return;
  const pv = viewer.pv;
  if (pvZoomKey(event)) return;
  const meta = event.metaKey || event.ctrlKey;
  let handled = true;
  if (meta && event.code === "KeyZ") pvUndo(viewer, event.shiftKey);
  else if (meta) handled = false;
  else if ((event.key === "Backspace" || event.key === "Delete") && pv.selected) {
    const { page, index } = pv.selected;
    pvChange(viewer, () => pvItems(viewer, page, false).splice(index, 1));
    pv.selected = null;
    pvDraw(viewer, page);
  } else if (event.key === "Escape") {
    if (pv.threadPull) pv.threadPull = null;
    else if (pv.tool !== "hand") pv.tool = "hand";
    pv.selected = null;
    pvChrome(viewer);
    pvDrawAll(viewer);
  } else if (event.code === "Minus") pvZoom(viewer, pv.zoom / 1.2);
  else if (event.code === "Equal") pvZoom(viewer, pv.zoom * 1.2);
  else if (event.code === "Digit0") { pv.fit = true; pvLayout(viewer); }
  else if (event.key === "PageDown" || (event.key === "ArrowRight" && pv.tool === "hand")) pvGo(viewer, pv.current + 1);
  else if (event.key === "PageUp" || (event.key === "ArrowLeft" && pv.tool === "hand")) pvGo(viewer, pv.current - 1);
  else if (event.key === "Home") pvGo(viewer, 1);
  else if (event.key === "End" && pv.pages) pvGo(viewer, pv.pages.length);
  else {
    const tool = PV_TOOLS.find((item) => item.key === event.code);
    if (tool) pvTool(viewer, tool.id);
    else handled = false;
  }
  if (handled) { event.preventDefault(); event.stopPropagation(); }
}
