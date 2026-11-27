// Panels the app draws itself (`view = "..."` in a command's app.toml): Awake
// and the menu bar's System popover. The page only names what it wants
// ({op: "view-data"}) or what to do ({op: "view-act", do: ..., plain values});
// Rust checks every value and builds the argv (app/src/views.rs).
// Names here are prefixed (view*, aw*, sv*): pages share one global scope with
// app.js, common.js and the window's own properties.
"use strict";

const viewState = { name: "", view: "", timer: 0, tick: 0, data: null, error: "", note: "", busy: false };

function viewOpen(spec) {
  viewClose();
  Object.assign(viewState, { name: spec.name, view: spec.view, data: null, error: "", note: "", busy: false });
  VIEWS[spec.view].render();
  viewRead();
  // every 0: read once (the weather asks again only when searched).
  if (VIEWS[spec.view].every) viewState.timer = setInterval(viewRead, VIEWS[spec.view].every);
}

function viewClose() {
  clearInterval(viewState.timer);
  clearInterval(viewState.tick);
  viewState.timer = viewState.tick = 0;
  // A closed view must not own the keys of the next panel (← → turned a Timer panel
  // into the old System view) nor reopen with its schedule form or search held.
  viewState.view = "";
  viewState.adding = false;
  viewState.focusSearch = false;
}

function viewRead() { send({ op: "view-data", name: viewState.name }); }

function viewAct(what, values) {
  if (viewState.busy) return;
  viewState.busy = true;
  viewState.note = "";
  VIEWS[viewState.view].render();
  send(Object.assign({ op: "view-act", name: viewState.name, do: what }, values || {}));
}

// Messages for the open view (from window.ul.receive in app.js).
function viewReceive(message) {
  if (message.name !== viewState.name || !viewState.view) return;
  if (message.type === "view-data") {
    if (message.data && Object.keys(message.data).length) viewState.data = Object.assign(viewState.data || {}, message.data);
    viewState.error = message.error || "";
    // A fresh reading never redraws under a field being typed in or a schedule being added.
    if (viewHolding()) return;
  } else if (message.type === "view-done") {
    viewState.busy = false;
    viewState.note = message.ok ? "" : (message.text || "Failed.").trim();
    // A view that reads (the weather) gets its answer with the action.
    if (message.ok && message.json) viewState.data = Object.assign(viewState.data || {}, { [viewState.view]: message.json });
    else viewRead();
  } else if (message.type === "view-query") {
    // Typed in the palette ("weather Paris"): search it here.
    if (VIEWS[viewState.view].query) VIEWS[viewState.view].query(message.value || "");
    return;
  }
  VIEWS[viewState.view].render();
}

function viewHolding() {
  if (VIEWS[viewState.view].holding) return VIEWS[viewState.view].holding();
  const active = document.activeElement;
  return viewState.adding || (active && active.closest(".view") && /^(INPUT|SELECT|TEXTAREA)$/.test(active.tagName));
}

// The page fits the window: the height of what is shown, the view's own width.
function viewFit(minimum) {
  requestAnimationFrame(() => {
    const root = document.querySelector(".view");
    if (!root) return;
    const height = Math.max(minimum || 0, Math.ceil(root.getBoundingClientRect().height) + 2);
    send({ op: "resize", width: VIEWS[viewState.view].width, height, fixed: true });
  });
}

function viewSwitch(on, label, change) {
  const node = el("button", { class: `switch${on ? " on" : ""}`, role: "switch", "aria-checked": String(on), "aria-label": label });
  node.addEventListener("click", () => change(!on));
  return node;
}

function viewHead(title, sub, ...tools) {
  return dragHandle(el("div", { class: "vhead" },
    el("div", { class: "what" }, el("b", { text: title }), el("span", { text: sub })), ...tools));
}

function viewProblem() {
  const text = viewState.note || viewState.error;
  return text ? el("div", { class: "vproblem", role: "alert", text }) : null;
}

// ================= Awake =================

const AW_SPANS = [["15m", "15 min"], ["30m", "30 min"], ["1h", "1 hour"], ["2h", "2 hours"], ["4h", "4 hours"], ["8h", "8 hours"]];
const AW_DAYS = [["daily", "Every day"], ["weekdays", "Weekdays"], ["weekends", "Weekends"]];

function awPrefs() {
  return {
    display: stored("awake-display", "1") === "1",
    lid: stored("awake-lid", "0") === "1",
  };
}

function awClock(iso) {
  const date = new Date(iso);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// Two hours from now on the hour: a sensible first "until" (the last one typed is kept).
function awNextHour() {
  const date = new Date(Date.now() + 2 * 3600 * 1000);
  return `${String(date.getHours()).padStart(2, "0")}:00`;
}

function awLeft(seconds) {
  if (seconds <= 0) return "ending";
  const hours = Math.floor(seconds / 3600), minutes = Math.floor(seconds % 3600 / 60), rest = Math.floor(seconds % 60);
  if (hours) return `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

// The running session as words: what keeps the Mac awake and until when.
function awSession(status) {
  if (!status || !status.active) return { title: "Sleeping normally", sub: "Your Mac sleeps on its usual schedule." };
  const source = status.source && status.source.startsWith("schedule:") ? " · by a schedule" : "";
  if (status.kind === "command") return { title: "Awake", sub: "While a command runs (stop that command)" + source };
  if (status.kind === "pid") return { title: "Awake", sub: "While a process runs" + source };
  if (!status.ends) return { title: "Awake", sub: "Until you turn it off" + source };
  return { title: "Awake", sub: `Until ${awClock(status.ends)}` + source, ends: status.ends, started: status.started };
}

// Start with what is chosen; a running session is restarted with the same end.
function awStart(span) {
  const prefs = awPrefs();
  viewAct("start", { span, display: prefs.display, lid: prefs.lid });
}

function awOption(key, value) {
  store(key === "display" ? "awake-display" : "awake-lid", value ? "1" : "0");
  const status = viewState.data && viewState.data.status;
  // Change the running session too, keeping its end.
  if (status && status.active && status.kind !== "command" && status.kind !== "pid") {
    const prefs = awPrefs();
    if (status.ends) {
      const end = new Date(status.ends);
      if (end - Date.now() > 60000) {
        const date = `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, "0")}-${String(end.getDate()).padStart(2, "0")}`;
        const time = `${String(end.getHours()).padStart(2, "0")}:${String(end.getMinutes()).padStart(2, "0")}`;
        viewAct("until", { date, time, display: prefs.display, lid: prefs.lid });
        return;
      }
    } else {
      viewAct("start", { span: "on", display: prefs.display, lid: prefs.lid });
      return;
    }
  }
  awRender();
}

function awCup(on) {
  const svg = icon("cup");
  svg.classList.add("awcup");
  const steam = el("div", { class: "steam" }, el("i"), el("i"), el("i"));
  return el("div", { class: `awglyph${on ? " on" : ""}` }, on ? steam : null, svg);
}

function awRender() {
  const data = viewState.data || {};
  const status = data.status;
  const on = !!(status && status.active);
  const session = awSession(status);
  const fixed = on && (status.kind === "command" || status.kind === "pid");
  const prefs = awPrefs();
  const busy = viewState.busy;

  const hero = el("div", { class: `awhero${on ? " on" : ""}` },
    awCup(on),
    el("div", { class: "what" }, el("b", { text: session.title }), el("span", { class: "awsub", text: session.sub })),
    fixed ? null : viewSwitch(on, on ? "Let the Mac sleep" : "Keep the Mac awake", (next) => next ? awStart("on") : viewAct("stop")));
  dragHandle(hero);

  const parts = [hero];
  if (session.ends) {
    const total = Math.max(1, new Date(session.ends) - new Date(session.started));
    const bar = el("i");
    const left = el("span", { class: "awleft" });
    const update = () => {
      const remaining = (new Date(session.ends) - Date.now()) / 1000;
      left.textContent = awLeft(Math.max(0, remaining)) + " left";
      bar.style.width = `${Math.max(0, Math.min(100, remaining * 1000 / total * 100))}%`;
    };
    update();
    clearInterval(viewState.tick);
    viewState.tick = setInterval(update, 1000);
    parts.push(el("div", { class: "awtime" }, el("div", { class: "awbar" }, bar), left));
  } else {
    clearInterval(viewState.tick);
  }
  if (status && status.lid_restore_failed) {
    parts.push(el("div", { class: "vproblem", text: "Lid sleep could not be restored. Turn Awake off to try again." }));
  }
  const problem = viewProblem();
  if (problem) parts.push(problem);

  // Durations: one click starts (like Amphetamine's and Caffeine's menus).
  const grid = el("div", { class: "awgrid" });
  for (const [span, label] of AW_SPANS) {
    grid.appendChild(el("button", { class: "chip", text: label, disabled: busy || fixed ? "" : null, onclick: () => awStart(span) }));
  }
  grid.appendChild(el("button", { class: "chip wide", disabled: busy || fixed ? "" : null, onclick: () => awStart("on") },
    el("span", { text: "Until I turn it off" })));
  parts.push(el("div", { class: "vgroup" }, el("h4", { text: "Keep awake for" }), grid));

  const time = el("input", { type: "time", value: stored("awake-until", "") || awNextHour(), "aria-label": "Until" });
  time.addEventListener("change", () => store("awake-until", time.value));
  const go = () => {
    if (!/^\d{2}:\d{2}$/.test(time.value)) return;
    const prefs = awPrefs();
    store("awake-until", time.value);
    viewAct("until", { time: time.value, display: prefs.display, lid: prefs.lid });
  };
  time.addEventListener("keydown", (event) => { if (event.key === "Enter") go(); });
  parts.push(el("div", { class: "awuntil" }, el("label", { text: "Until" }), time,
    el("button", { class: "primary", text: "Start", disabled: busy || fixed ? "" : null, onclick: go })));

  // Options.
  const lidReady = data.lid !== false;
  const lidControl = lidReady
    ? viewSwitch(prefs.lid, "Stay awake with the lid closed", (next) => awOption("lid", next))
    : el("button", { class: "ghost small", text: "Set up…", onclick: () => send({ op: "view-terminal", name: viewState.name }) });
  parts.push(el("div", { class: "vgroup" }, el("h4", { text: "Options" }),
    el("div", { class: "vrow" }, el("div", {}, el("span", { text: "Keep the screen on" }), el("small", { text: "Off: the screen dims and sleeps on its usual timer" })),
      viewSwitch(prefs.display, "Keep the screen on", (next) => awOption("display", next))),
    el("div", { class: "vrow" }, el("div", {}, el("span", { text: "Stay awake with the lid closed" }),
      el("small", { text: lidReady ? "Needs care: a closed MacBook in a bag gets hot" : "Needs a one-time setup with your password" })), lidControl)));

  parts.push(awSchedules(data.schedules, busy));
  parts.push(el("div", { class: "vfoot", text: "Click the cup in the menu bar to switch Awake; right-click it for this panel." }));

  const root = el("div", { class: "view awake" }, ...parts);
  document.body.replaceChildren(el("div", { class: "glass" }, root));
  viewFit();
}

function awSchedules(data, busy) {
  const list = (data && data.schedules) || [];
  const group = el("div", { class: "vgroup" });
  const adding = viewState.adding;
  group.appendChild(el("div", { class: "vgrouphead" }, el("h4", { text: "Schedules" }),
    el("button", { class: "ghost small", text: adding ? "Cancel" : "Add", onclick: () => { viewState.adding = !adding; awRender(); } })));
  for (const item of list) {
    const days = item.date ? item.date : (AW_DAYS.find(([id]) => id === awDaysId(item.days)) || [, "Some days"])[1];
    const flags = [item.display ? "screen on" : "", item.lid ? "lid closed" : ""].filter(Boolean).join(", ");
    group.appendChild(el("div", { class: "vrow sched" },
      el("div", {}, el("span", { class: "mono", text: `${item.start} – ${item.end}` }), el("small", { text: [item.name, days, flags].filter(Boolean).join(" · ") })),
      el("button", { class: "ghost small", text: "Remove", disabled: busy ? "" : null, onclick: () => viewAct("schedule-rm", { id: item.id }) })));
  }
  if (!list.length && !adding) group.appendChild(el("div", { class: "vempty", text: "None. A schedule keeps the Mac awake in the same window every day." }));
  if (adding) {
    const from = el("input", { type: "time", value: "23:00", "aria-label": "From" });
    const to = el("input", { type: "time", value: "06:00", "aria-label": "To" });
    let days = "daily";
    const seg = el("div", { class: "seg" });
    for (const [id, label] of AW_DAYS) {
      const button = el("button", { text: label, class: id === days ? "on" : "" });
      button.addEventListener("click", () => { days = id; for (const other of seg.children) other.classList.toggle("on", other === button); });
      seg.appendChild(button);
    }
    group.appendChild(el("div", { class: "awadd" },
      el("div", { class: "awfromto" }, from, el("span", { text: "to" }), to), seg,
      el("button", { class: "primary", text: "Add schedule", onclick: () => {
        const prefs = awPrefs();
        viewState.adding = false;
        viewAct("schedule-add", { from: from.value, to: to.value, days, display: prefs.display, lid: false });
      } })));
  }
  return group;
}

// Schedules store days as Mon=0 numbers (or null for every day).
function awDaysId(days) {
  if (!days) return "daily";
  const text = days.join(",");
  return text === "0,1,2,3,4" ? "weekdays" : text === "5,6" ? "weekends" : "";
}

// ================= System =================

const SV_TABS = [["overview", "Overview"], ["cpu", "CPU"], ["memory", "Memory"], ["gpu", "GPU"], ["battery", "Battery"], ["network", "Network"], ["disk", "Disks"]];
const SV_HISTORY = 60;
const svHistory = { cpu: [], memory: [], gpu: [], down: [], up: [], read: [], write: [], power: [], battery: [] };
let svTab = stored("system-tab", "overview");
let svLast = null;

function svRemember(data) {
  if (data === svLast) return;
  svLast = data;
  const add = (key, value) => {
    if (value == null) return;
    svHistory[key].push(value);
    if (svHistory[key].length > SV_HISTORY) svHistory[key].shift();
  };
  const mem = data.memory || {};
  add("cpu", data.cpu && data.cpu.usage_percent);
  add("memory", mem.total_bytes ? mem.used_bytes / mem.total_bytes * 100 : null);
  add("gpu", data.gpu && data.gpu.usage_percent);
  add("down", data.network && data.network.download_bytes_per_sec);
  add("up", data.network && data.network.upload_bytes_per_sec);
  add("read", data.io && data.io.read_bytes_per_sec);
  add("write", data.io && data.io.write_bytes_per_sec);
  add("power", data.battery && data.battery.system_power_watts);
  add("battery", data.battery && data.battery.present ? data.battery.percent : null);
}

// A filled line of recent values; `auto` scales to the recent maximum (speeds, watts).
function svGraph(keys, auto, height) {
  const canvas = el("canvas", { class: "vgraph" });
  canvas.style.height = `${height || 64}px`;
  requestAnimationFrame(() => {
    const ratio = devicePixelRatio || 1, width = canvas.clientWidth, tall = canvas.clientHeight;
    if (!width) return;
    canvas.width = width * ratio;
    canvas.height = tall * ratio;
    const context = canvas.getContext("2d");
    context.scale(ratio, ratio);
    const style = getComputedStyle(document.documentElement);
    const all = keys.flatMap((key) => svHistory[key]);
    const most = auto ? Math.max(1, ...all) : 100;
    context.strokeStyle = style.getPropertyValue("--line");
    for (const fraction of [0.25, 0.5, 0.75]) {
      context.beginPath(); context.moveTo(0, Math.round(tall * fraction) + .5); context.lineTo(width, Math.round(tall * fraction) + .5); context.stroke();
    }
    const colors = [style.getPropertyValue("--accent"), style.getPropertyValue("--second")];
    keys.forEach((key, index) => {
      const values = svHistory[key];
      if (values.length < 2) return;
      const step = width / (SV_HISTORY - 1);
      const x = (at) => width - (values.length - 1 - at) * step;
      const y = (value) => tall - 1 - Math.max(0, Math.min(most, value)) / most * (tall - 4);
      context.beginPath();
      values.forEach((value, at) => at ? context.lineTo(x(at), y(value)) : context.moveTo(x(at), y(value)));
      context.strokeStyle = colors[index];
      context.lineWidth = 1.6;
      context.lineJoin = "round";
      context.stroke();
      context.lineTo(x(values.length - 1), tall); context.lineTo(x(0), tall); context.closePath();
      const fill = context.createLinearGradient(0, 0, 0, tall);
      fill.addColorStop(0, colors[index].trim() + "80");
      fill.addColorStop(1, colors[index].trim() + "00");
      context.fillStyle = fill;
      context.fill();
    });
  });
  return canvas;
}

// A ring gauge: the overview's four big numbers; a click opens that tab.
function svRing(label, value, text, tab, tone) {
  const size = 66, stroke = 6, radius = (size - stroke) / 2, round = 2 * Math.PI * radius;
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
  svg.setAttribute("class", "ring");
  const circle = (cls, dash) => {
    const node = document.createElementNS(SVG, "circle");
    node.setAttribute("cx", size / 2); node.setAttribute("cy", size / 2); node.setAttribute("r", radius);
    node.setAttribute("class", cls);
    if (dash != null) {
      node.setAttribute("stroke-dasharray", `${dash} ${round}`);
      node.setAttribute("transform", `rotate(-90 ${size / 2} ${size / 2})`);
    }
    return node;
  };
  svg.appendChild(circle("track"));
  if (value != null) svg.appendChild(circle(`fill ${tone || ""}`, Math.max(0, Math.min(100, value)) / 100 * round));
  return el("button", { class: "svring", onclick: () => svGo(tab), title: `Open ${label}` },
    el("div", { class: "ringbox" }, svg, el("b", { text })), el("span", { text: label }));
}

function svGo(tab) {
  svTab = tab;
  store("system-tab", tab);
  svRender();
}

function svStat(label, value, tone) {
  return el("div", { class: "svstat" }, el("span", { text: label }), el("b", { class: tone || "", text: value }));
}

function svRows(pairs) {
  const list = el("dl", { class: "vrows" });
  for (const [label, value] of pairs) {
    if (value === null) continue;
    list.appendChild(el("dt", { text: label }));
    list.appendChild(typeof value === "string" ? el("dd", { text: value }) : el("dd", {}, value));
  }
  return list;
}

function svProcs(list, value) {
  const table = el("div", { class: "vprocs" });
  for (const item of (list || []).slice(0, 5)) table.appendChild(el("div", {}, el("span", { text: item.name }), el("b", { text: value(item) })));
  return table;
}

function svBig(value, sub) {
  return el("div", { class: "svbig" }, el("b", { text: value }), sub ? el("span", { text: sub }) : null);
}

function svCores(cpu) {
  const list = cpu.per_core || [];
  if (!list.length) return null;
  const groups = [["P", "Performance"], ["E", "Efficiency"]].map(([kind, label]) => [label, list.filter((core) => core.kind === kind)]).filter(([, cores]) => cores.length);
  if (!groups.length) groups.push(["Cores", list]);
  return el("div", { class: "svcores" }, ...groups.map(([label, cores]) => el("div", { class: "group" },
    el("div", { class: "bars" }, ...cores.map((core) => el("i", { title: pct(core.usage_percent), style: `height:${Math.max(3, Math.min(100, core.usage_percent))}%` }))),
    el("small", { text: `${label} · ${cores.length}` }))));
}

function svBattery(battery) {
  if (!battery || !battery.present) return null;
  if (battery.charging) return "Charging";
  if (battery.plugged_in) return "On power";
  return "On battery";
}

const SV_PANES = {
  overview(data) {
    const mem = data.memory || {}, battery = data.battery || {}, net = data.network || {}, info = data.system || {};
    const used = mem.total_bytes ? mem.used_bytes / mem.total_bytes * 100 : null;
    const level = { 2: "warn", 4: "bad" }[mem.pressure_level] || "";
    const rings = el("div", { class: "svrings" },
      svRing("CPU", data.cpu && data.cpu.usage_percent, pct(data.cpu && data.cpu.usage_percent), "cpu"),
      svRing("Memory", used, pct(used), "memory", level),
      svRing("GPU", data.gpu && data.gpu.usage_percent, pct(data.gpu && data.gpu.usage_percent), "gpu"),
      battery.present ? svRing("Battery", battery.percent, pct(battery.percent), "battery", battery.percent <= 20 && !battery.plugged_in ? "bad" : battery.charging ? "ok" : "") : null);
    const root = (data.disk || [])[0];
    return [rings, el("div", { class: "svstats" },
      svStat("Download", speed(net.download_bytes_per_sec)), svStat("Upload", speed(net.upload_bytes_per_sec)),
      svStat("Mac draws", battery.system_power_watts != null ? watts(battery.system_power_watts) : "n/a"),
      svStat("Disk free", root ? gb(root.free_bytes) : "n/a"),
      svStat("Pressure", mem.pressure || "n/a", level),
      svStat("Uptime", info.uptime_seconds != null ? duration(info.uptime_seconds) : "n/a"))];
  },
  cpu(data) {
    const cpu = data.cpu || {}, top = data.top || {};
    const cores = cpu.cores ? `${cpu.cores.performance ?? "?"} performance + ${cpu.cores.efficiency ?? "?"} efficiency cores` : "";
    return [svBig(pct(cpu.usage_percent), cores), svGraph(["cpu"]), svCores(cpu),
      svRows([["User", pct(cpu.user_percent)], ["System", pct(cpu.system_percent)], ["Performance cores", pct(cpu.performance_percent)],
        ["Efficiency cores", pct(cpu.efficiency_percent)], ["Load (1, 5, 15 min)", (cpu.load_average || []).map((value) => value.toFixed(2)).join("  ") || "n/a"]]),
      el("h4", { text: "Using the most CPU" }), svProcs(top.cpu, (item) => pct(item.cpu_percent))];
  },
  memory(data) {
    const mem = data.memory || {}, top = data.top || {};
    const part = (count) => mem.total_bytes && count ? `${count / mem.total_bytes * 100}%` : "0%";
    const level = { 2: "warn", 4: "bad" }[mem.pressure_level] || "";
    return [svBig(gb(mem.used_bytes), `used of ${gb(mem.total_bytes)}`), svGraph(["memory"]),
      el("div", { class: "vstack" }, el("i", { class: "a", style: `width:${part(mem.app_bytes)}` }), el("i", { class: "b", style: `width:${part(mem.wired_bytes)}` }),
        el("i", { class: "c", style: `width:${part(mem.compressed_bytes)}` }), el("i", { class: "d", style: `width:${part(mem.cached_bytes)}` })),
      el("div", { class: "vlegend" }, el("span", { class: "a", text: `App ${gb(mem.app_bytes)}` }), el("span", { class: "b", text: `Wired ${gb(mem.wired_bytes)}` }),
        el("span", { class: "c", text: `Compressed ${gb(mem.compressed_bytes)}` }), el("span", { class: "d", text: `Cached ${gb(mem.cached_bytes)}` })),
      svRows([["Pressure", el("span", { class: level, text: (mem.pressure || "n/a") + (mem.pressure_percent != null ? ` · ${mem.pressure_percent}%` : "") })],
        ["Swap", mem.swap_total_bytes ? `${gb(mem.swap_used_bytes)} of ${gb(mem.swap_total_bytes)}` : "none"], ["Free", gb(mem.free_bytes)]]),
      el("h4", { text: "Using the most memory" }), svProcs(top.memory, (item) => gb(item.memory_bytes))];
  },
  gpu(data) {
    const gpu = data.gpu || {};
    return [svBig(pct(gpu.usage_percent), [gpu.name, gpu.cores ? `${gpu.cores} cores` : ""].filter(Boolean).join(" · ")), svGraph(["gpu"]),
      svRows([["Renderer", pct(gpu.renderer_percent)], ["Tiler", pct(gpu.tiler_percent)],
        ["Memory in use", gpu.memory_in_use_bytes != null ? gb(gpu.memory_in_use_bytes) : "n/a"]])];
  },
  battery(data) {
    const battery = data.battery;
    if (!battery || !battery.present) return [el("div", { class: "vempty", text: "This Mac has no battery." })];
    const left = battery.time_remaining_minutes != null ? duration(battery.time_remaining_minutes * 60) + (battery.charging ? " to full" : " left") : "";
    return [svBig(pct(battery.percent), [svBattery(battery), left].filter(Boolean).join(" · ")),
      el("div", { class: "vstack big" }, el("i", { class: battery.charging ? "ok" : battery.percent <= 20 ? "bad" : "a", style: `width:${battery.percent || 0}%` })),
      el("h4", { text: "What the Mac draws" }), svGraph(["power"], true, 56),
      svRows([["Now", watts(battery.system_power_watts)], ["Adapter", battery.adapter_watts ? `${battery.adapter_watts} W` : battery.plugged_in ? "n/a" : "not connected"],
        ["Condition", battery.condition || "n/a"], ["Max capacity", battery.max_capacity_percent != null ? `${battery.max_capacity_percent}% (${battery.max_capacity_mah} of ${battery.design_capacity_mah} mAh)` : "n/a"],
        ["Cycles", String(battery.cycle_count ?? "n/a")], ["Voltage", battery.voltage_v != null ? battery.voltage_v.toFixed(2) + " V" : "n/a"],
        ["Temperature", battery.temperature_c != null ? `${battery.temperature_c.toFixed(1)} °C` : null]])];
  },
  network(data) {
    const net = data.network;
    if (!net) return [el("div", { class: "vempty", text: "No network readings." })];
    return [el("div", { class: "svpair" }, svBig("↓ " + speed(net.download_bytes_per_sec), "download"), svBig("↑ " + speed(net.upload_bytes_per_sec), "upload")),
      svGraph(["down", "up"], true),
      el("div", { class: "vlegend" }, el("span", { class: "a", text: "Download" }), el("span", { class: "s", text: "Upload" })),
      svRows([["Interfaces", net.interfaces.join(", ") || "no traffic"], ["Received since start-up", bytes(net.received_bytes)], ["Sent since start-up", bytes(net.sent_bytes)]])];
  },
  disk(data) {
    const io = data.io;
    const volumes = (data.disk || []).map((disk) => el("div", { class: "svdisk" },
      el("div", { class: "label" }, el("b", { text: disk.mount === "/" ? "Macintosh HD" : disk.mount.split("/").pop() || disk.mount }), el("span", { text: `${gb(disk.free_bytes)} free of ${gb(disk.total_bytes)}` })),
      el("div", { class: "vstack" }, el("i", { class: disk.used_percent > 90 ? "bad" : "a", style: `width:${disk.used_percent || 0}%` }))));
    return [...volumes, io ? el("h4", { text: "Activity" }) : null,
      io ? el("div", { class: "svpair" }, svBig(speed(io.read_bytes_per_sec), "read"), svBig(speed(io.write_bytes_per_sec), "write")) : null,
      io ? svGraph(["read", "write"], true, 56) : null,
      io ? svRows([["Reads", `${io.read_ops_per_sec} /s`], ["Writes", `${io.write_ops_per_sec} /s`], ["Read since start-up", bytes(io.read_bytes)], ["Written since start-up", bytes(io.written_bytes)]]) : null];
  },
};

function svRender() {
  const data = viewState.data && viewState.data.sys;
  if (data) svRemember(data);
  const info = (data && data.system) || {};
  const tabs = el("div", { class: "svtabs", role: "tablist" }, ...SV_TABS.map(([id, label]) =>
    el("button", { class: id === svTab ? "on" : "", role: "tab", "aria-selected": String(id === svTab), text: label, onclick: () => svGo(id) })));
  const thermal = info.thermal && info.thermal !== "nominal" ? `thermal ${info.thermal}` : "";
  const head = viewHead(info.chip || "System", [info.model, info.os, thermal].filter(Boolean).join(" · ") || "Reading…",
    el("button", { class: "ghost small", text: "Open window", onclick: () => send({ op: "default", name: viewState.name }) }));
  const body = el("div", { class: "svbody", role: "tabpanel" });
  if (!data) body.appendChild(el("div", { class: "vempty", text: viewState.error || "Reading CPU, memory, battery and disks…" }));
  else for (const part of SV_PANES[svTab](data)) if (part) body.appendChild(part);
  const problem = viewState.error && data ? viewProblem() : null;
  document.body.replaceChildren(el("div", { class: "glass" }, el("div", { class: "view system" }, head, tabs, problem, body)));
  viewFit(430);
}

// Keyboard: ← → switch tabs, Esc closes (app.js).
document.addEventListener("keydown", (event) => {
  if (viewState.view !== "system" || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
  const index = SV_TABS.findIndex(([id]) => id === svTab);
  const next = SV_TABS[(index + (event.key === "ArrowRight" ? 1 : SV_TABS.length - 1)) % SV_TABS.length][0];
  event.preventDefault();
  svGo(next);
});

// ---------- Weather ----------
// `ul weather --json`: the default city when the panel opens, a search as the
// `forecast` action (views.rs checks the city and the days). Drawn like a phone's
// weather: the place and the temperature now, then a row per day with its range.

const WX_DAYS = [3, 7, 14];
let wxDays = Number(stored("weather-days", "7")) || 7;
let wxCity = "";

// Open-Meteo weather codes (WMO) -> an icon.
function wxIcon(code) {
  if (code == null) return "cloud";
  if (code === 0) return "sun";
  if (code <= 2) return "cloudsun";
  if (code === 3) return "cloud";
  if (code === 45 || code === 48) return "fog";
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return "snow";
  if (code >= 95) return "storm";
  return "rain";
}

function wxDegrees(value) {
  return value == null ? "–" : `${Math.round(value)}°`;
}

function wxDay(date, index) {
  if (index === 0) return "Today";
  if (index === 1) return "Tomorrow";
  const day = new Date(`${date}T12:00`);
  return isNaN(day) ? date : day.toLocaleDateString(undefined, { weekday: "short", day: "numeric" });
}

function wxClock(iso) {
  return iso && iso.includes("T") ? iso.split("T")[1].slice(0, 5) : "";
}

function wxSearch(city) {
  wxCity = city.trim();
  viewAct("forecast", { city: wxCity, days: wxDays });
}

function wxRender() {
  const data = viewState.data && viewState.data.weather;
  const place = data && data.location;
  const units = (data && data.unit_labels) || {};
  const days = el("div", { class: "seg compact", role: "radiogroup", "aria-label": "Days" }, ...WX_DAYS.map((count) =>
    el("button", { class: count === wxDays ? "on" : "", role: "radio", "aria-checked": String(count === wxDays), text: `${count} d`,
      onclick: () => { wxDays = count; store("weather-days", String(count)); wxSearch(wxCity); } })));
  const input = el("input", { type: "search", placeholder: "Search a city", spellcheck: "false", autocomplete: "off", "aria-label": "City" });
  input.value = wxCity;
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); wxSearch(input.value); }
  });
  const search = el("div", { class: "wxsearch" }, icon("search"), input, viewState.busy ? el("i", { class: "spinner" }) : null);
  const head = viewHead(place ? place.name : "Weather", place ? [place.admin1, place.country].filter(Boolean).join(", ") : "Reading the forecast…", days);
  const parts = [head, search, viewProblem()];
  if (data && data.current) {
    const now = data.current;
    parts.push(el("div", { class: "wxnow" },
      el("div", { class: "wxglyph" }, icon(wxIcon(now.weather_code))),
      el("div", { class: "wxtemp", text: wxDegrees(now.temperature) }),
      el("div", { class: "wxsay" },
        el("b", { text: now.summary || "" }),
        el("span", { text: `Feels like ${wxDegrees(now.apparent_temperature)}` }))));
    const today = (data.daily || [])[0] || {};
    parts.push(el("div", { class: "svstats" },
      svStat("Humidity", now.humidity == null ? "–" : `${now.humidity}%`),
      svStat("Wind", now.wind_speed == null ? "–" : `${Math.round(now.wind_speed)} ${units.wind_speed || ""}`),
      svStat("Sun", [wxClock(today.sunrise), wxClock(today.sunset)].filter(Boolean).join(" – ") || "–")));
  }
  const daily = (data && data.daily) || [];
  if (daily.length) {
    const lows = daily.map((day) => day.temperature_min).filter((value) => value != null);
    const highs = daily.map((day) => day.temperature_max).filter((value) => value != null);
    const low = Math.min(...lows), high = Math.max(...highs), span = Math.max(high - low, 1);
    parts.push(el("div", { class: "wxdays" }, ...daily.map((day, index) => {
      const from = day.temperature_min == null ? 0 : (day.temperature_min - low) / span * 100;
      const to = day.temperature_max == null ? 100 : (day.temperature_max - low) / span * 100;
      const rain = day.precipitation_probability;
      return el("div", { class: "wxday", title: day.summary || "" },
        el("span", { class: "name", text: wxDay(day.date, index) }),
        el("span", { class: "icon" }, icon(wxIcon(day.weather_code))),
        el("span", { class: "rain", text: rain >= 10 ? `${rain}%` : "" }),
        el("span", { class: "low", text: wxDegrees(day.temperature_min) }),
        el("span", { class: "range" }, el("i", { style: `left:${from}%;width:${Math.max(to - from, 4)}%` })),
        el("span", { class: "high", text: wxDegrees(day.temperature_max) }));
    })));
  } else if (!viewState.error && !viewState.note) {
    parts.push(el("div", { class: "vempty", text: viewState.busy ? "Looking it up…" : "Reading the forecast…" }));
  }
  document.body.replaceChildren(el("div", { class: "glass" }, el("div", { class: "view weather" }, ...parts.filter(Boolean))));
  // Keep the cursor in the field across redraws (the answer arrives while it is focused).
  if (!data || viewState.focusSearch) { input.focus(); viewState.focusSearch = false; }
  input.addEventListener("focus", () => { viewState.focusSearch = true; });
  input.addEventListener("blur", () => { viewState.focusSearch = false; });
  viewFit(220);
}

const VIEWS = {
  awake: { every: 5000, width: 340, render: awRender },
  system: { every: 2000, width: 440, render: svRender },
  // Holds a redraw only while a new city is being typed; the focused empty field must not block the answer.
  weather: { every: 0, width: 360, render: wxRender, query: wxSearch,
    holding: () => { const input = document.querySelector(".wxsearch input"); return !!input && input.value.trim() !== wxCity; } },
};
