"""The `ul desk` page: one HTML document with inline CSS and JS, served by desk.py.

Board text is user data, so the script builds every node with textContent and never uses innerHTML.
"""

from .studio_ui import STUDIO_CSS, STUDIO_JS

_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Desk</title>
<link rel="icon" id="favicon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22%3E%3Crect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%23fff%22/%3E%3Cpath d=%22M15 18V36a7.5 7.5 0 0 0 15 0V18M38.5 18V43.5H52.5%22 fill=%22none%22 stroke=%22%23f5a300%22 stroke-width=%227%22/%3E%3C/svg%3E" data-light="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22%3E%3Crect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%23fff%22/%3E%3Cpath d=%22M15 18V36a7.5 7.5 0 0 0 15 0V18M38.5 18V43.5H52.5%22 fill=%22none%22 stroke=%22%23f5a300%22 stroke-width=%227%22/%3E%3C/svg%3E" data-dark="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22%3E%3Crect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%230b0b0a%22/%3E%3Cpath d=%22M15 18V36a7.5 7.5 0 0 0 15 0V18M38.5 18V43.5H52.5%22 fill=%22none%22 stroke=%22%23f5a300%22 stroke-width=%227%22/%3E%3C/svg%3E">
<style>
:root {
  --bg: #fbfaf7; --panel: #ffffff; --column: #f3f1eb; --sunken: #eae7df; --text: #17150f; --muted: #77716a;
  --line: #e8e4db; --accent: #ffc21a; --accent-ink: #9a5b00; --accent-soft: #fff2c7; --on-accent: #17150f;
  --energy: #ff7a1a; --energy-ink: #c2500a; --danger: #e5484d; --ok: #2f9e5b; --warn: #d97706;
  --shadow: 0 1px 2px rgba(40,30,10,.05), 0 1px 1px rgba(40,30,10,.03);
  --lift: 0 4px 10px rgba(40,30,10,.07), 0 14px 32px rgba(40,30,10,.09);
  --radius: 10px; --r: 7px; --r-sm: 5px;
  --font: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
  --mono: "SF Mono", ui-monospace, Menlo, monospace;
  color-scheme: light;
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #0b0b0a; --panel: #171715; --column: #121211; --sunken: #1f1e1b; --text: #f5f2ea; --muted: #9b958a;
  --line: #282622; --accent: #ffc933; --accent-ink: #ffc933; --accent-soft: #3a2f10; --on-accent: #17150f;
  --energy: #ff8a33; --energy-ink: #ff9d57; --danger: #ff6b5e; --ok: #4fc581; --warn: #ffb02e;
  --shadow: 0 1px 2px rgba(0,0,0,.45);
  --lift: 0 6px 14px rgba(0,0,0,.5), 0 18px 40px rgba(0,0,0,.4);
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body { background: var(--bg); color: var(--text); font: 14px/1.45 var(--font); display: flex; flex-direction: column; -webkit-font-smoothing: antialiased; }
::selection { background: var(--accent-soft); }
button, input, select { font: inherit; color: inherit; }
button { cursor: pointer; border: 1px solid var(--line); background: var(--panel); border-radius: var(--r); padding: 5px 11px; transition: background .14s, border-color .14s, color .14s, box-shadow .14s, transform .14s; }
button:hover { border-color: var(--accent); }
button:disabled { opacity: .45; cursor: default; transform: none; }
button.primary { background: var(--accent); border-color: var(--accent); color: var(--on-accent); font-weight: 600; }
button.primary:hover { filter: brightness(1.05); }
button.ghost { border-color: transparent; background: transparent; color: var(--muted); }
button.ghost:hover { background: var(--column); color: var(--text); }
button.icon { width: 32px; height: 32px; padding: 0; display: inline-grid; place-items: center; }
button.icon svg { width: 17px; height: 17px; stroke: currentColor; fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
input, select { border: 1px solid var(--line); background: var(--panel); border-radius: var(--r); padding: 5px 10px; outline: none; transition: border-color .14s, box-shadow .14s; }
input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
input[type=range] { accent-color: var(--accent); }
:focus-visible { outline: 2px solid var(--accent-ink); outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { transition: none !important; animation: none !important; } }

header { display: flex; align-items: center; gap: 12px; padding: 8px 14px 0 16px; border-bottom: 1px solid var(--line); background: var(--panel); flex-wrap: wrap; position: relative; z-index: 5; }
header > :not(.tabs) { margin-bottom: 8px; }
.brand { display: flex; align-items: center; gap: 8px; font-weight: 680; letter-spacing: -.01em; }
.brand .mark { width: 24px; height: 24px; display: block; border-radius: 5px; box-shadow: 0 0 0 1px var(--line); }
:root[data-theme="dark"] .brand .mark.light, :root:not([data-theme="dark"]) .brand .mark.dark { display: none; }
.picker { position: relative; }
.picker .trigger { display: inline-flex; align-items: center; gap: 8px; max-width: 240px; border-color: transparent; background: transparent; font-weight: 600; padding: 4px 8px; }
.picker .trigger:hover, .picker.open .trigger { background: var(--column); }
.picker .trigger .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.picker .trigger::after { content: ""; flex: none; width: 6px; height: 6px; margin-top: -3px; border: solid var(--muted); border-width: 0 1.6px 1.6px 0; transform: rotate(45deg); transition: transform .16s; }
.picker.open .trigger::after { transform: rotate(225deg); margin-top: 3px; }
.picker .menu { position: absolute; top: calc(100% + 4px); left: 0; min-width: 280px; max-width: 380px; max-height: min(70vh, 520px); overflow-y: auto; display: none; flex-direction: column; gap: 1px; padding: 4px; background: var(--panel); border: 1px solid var(--line); border-radius: 9px; box-shadow: var(--lift); z-index: 40; }
.picker.open .menu { display: flex; }
.picker .menu button { display: flex; flex-direction: column; align-items: flex-start; border: none; background: transparent; border-radius: 5px; padding: 5px 10px; text-align: left; }
.picker .menu button:hover, .picker .menu button:focus-visible { background: var(--column); outline: none; }
.picker .menu button .label { max-width: 100%; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.picker .menu button .where { max-width: 100%; font-size: 11.5px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.picker .menu button.on { box-shadow: inset 2px 0 0 var(--accent); background: var(--column); border-radius: 0 5px 5px 0; }
.picker .menu button.on .label { font-weight: 600; }
.picker .menu button.action { color: var(--muted); }
.picker .menu button.action:hover { color: var(--text); }
.picker .menu button.action.danger:hover { color: var(--danger); }
.picker .menu .sep { height: 1px; background: var(--line); margin: 4px 0; }
.tabs { display: flex; gap: 4px; align-self: stretch; align-items: stretch; }
.tabs button { border: none; background: transparent; padding: 0 10px 8px; border-radius: 0; color: var(--muted); font-weight: 550; box-shadow: inset 0 -2px 0 transparent; }
.tabs button:hover { color: var(--text); }
.tabs button.on { color: var(--text); box-shadow: inset 0 -2px 0 var(--accent); }
.spacer { flex: 1; }
.timer { display: flex; align-items: center; gap: 8px; padding: 3px 3px 3px 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--bg); }
.timer .phase { font-size: 12px; color: var(--muted); }
.timer .clock { font: 600 15px var(--mono); min-width: 48px; text-align: right; font-variant-numeric: tabular-nums; }
.timer.work { border-color: color-mix(in srgb, var(--energy) 60%, var(--line)); }
.timer.work .clock { color: var(--energy-ink); }
.timer.short .clock, .timer.long .clock { color: var(--ok); }
.timer .bar { width: 70px; height: 4px; background: var(--sunken); border-radius: 2px; overflow: hidden; }
.timer .bar i { display: block; height: 100%; background: currentColor; width: 0; transition: width .5s linear; }
.timer.work .bar i { background: var(--energy); }
.timer.short .bar i, .timer.long .bar i { background: var(--ok); }
.timer .linked { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: var(--muted); }
.timer button { padding: 2px 10px; border-radius: 5px; }
.timer #play { background: var(--accent); color: var(--on-accent); border-color: var(--accent); font-weight: 600; }
.actions-bar { display: flex; gap: 2px; }

.toolbar { display: flex; align-items: center; gap: 10px; padding: 12px 16px 0; flex-wrap: wrap; }
.toolbar.hidden { display: none; }
.search { position: relative; }
.search input { width: 240px; padding-left: 31px; background: var(--panel); }
.search svg { position: absolute; left: 11px; top: 50%; transform: translateY(-50%); width: 15px; height: 15px; stroke: var(--muted); fill: none; stroke-width: 2; }
#filter { display: none; }
#filter.on { display: inline-flex; }
.summary { display: flex; gap: 6px; flex-wrap: wrap; }
.pill { font-size: 12px; padding: 1px 0; color: var(--muted); }
.pill + .pill { padding-left: 10px; border-left: 1px solid var(--line); }
.pill b { color: var(--text); font-weight: 600; }
.pill.late b { color: var(--danger); }
.pill.today b { color: var(--energy-ink); }

main { flex: 1; overflow: auto; }
.board { display: flex; gap: 12px; padding: 14px 16px 16px; align-items: flex-start; min-height: 100%; }
.column { background: var(--column); border-radius: var(--radius); width: 300px; flex: 0 0 300px; display: flex; flex-direction: column; max-height: calc(100vh - 140px); border: 1px solid transparent; }
.column.drop { outline: 2px dashed var(--accent); outline-offset: -2px; background: color-mix(in srgb, var(--accent-soft) 55%, var(--column)); }
.column h2 { font-size: 13px; font-weight: 650; margin: 0; padding: 11px 10px 6px 12px; display: flex; gap: 7px; align-items: center; }
.column h2::before { content: ""; flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
.column.doing h2::before { background: var(--energy); }
.column.done h2::before { background: var(--ok); }
.column h2 .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.column h2 .count { color: var(--muted); font-weight: 500; font-size: 12px; font-variant-numeric: tabular-nums; }
.column h2 button { padding: 0; width: 22px; height: 22px; line-height: 1; border: none; background: transparent; color: var(--muted); border-radius: 6px; font-size: 17px; }
.column h2 button:hover { background: var(--panel); color: var(--text); }
.cards { padding: 4px 9px; overflow-y: auto; flex: 1; min-height: 20px; }
.card { background: var(--panel); border-radius: 8px; box-shadow: var(--shadow); padding: 9px 10px; margin-bottom: 7px; display: flex; gap: 9px; align-items: flex-start; cursor: grab; position: relative; border: 1px solid var(--line); transition: border-color .12s; }
.card:hover { border-color: color-mix(in srgb, var(--text) 22%, var(--line)); }
.card.dragging { opacity: .4; }
.column.dragging { opacity: .4; }
.column h2[draggable="true"] { cursor: grab; }
.column.col-before { box-shadow: -3px 0 0 var(--accent-ink); }
.column.col-after { box-shadow: 3px 0 0 var(--accent-ink); }
.card.focus { border-color: var(--energy); box-shadow: inset 2px 0 0 var(--energy); }
.card.checked .text { color: var(--muted); text-decoration: line-through; }
.card .check { width: 18px; height: 18px; border-radius: 50%; border: 1.6px solid color-mix(in srgb, var(--muted) 70%, transparent); flex: 0 0 17px; margin-top: 1px; padding: 0; background: transparent; position: relative; }
.card .check:hover { border-color: var(--accent); background: var(--accent-soft); }
.card.checked .check { background: var(--accent); border-color: var(--accent); }
.card.checked .check::after { content: ""; position: absolute; left: 5.5px; top: 2.5px; width: 4px; height: 8px; border: solid var(--on-accent); border-width: 0 2px 2px 0; transform: rotate(45deg); }
.card .body { flex: 1; min-width: 0; word-wrap: break-word; }
.card .meta { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 5px; }
.card .details { margin-top: 4px; color: var(--muted); font-size: 12px; white-space: pre-wrap; }
.card .actions { display: none; gap: 2px; position: absolute; right: 6px; top: 6px; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; box-shadow: var(--shadow); padding: 2px; }
.card:hover .actions { display: flex; }
.card .actions button { padding: 1px 7px; font-size: 12px; border: none; background: transparent; }
.card .actions button:hover { background: var(--column); }
.card .actions button.del svg { width: 13px; height: 13px; display: block; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; }
#filter svg { width: 11px; height: 11px; stroke: currentColor; fill: none; stroke-width: 2.2; stroke-linecap: round; vertical-align: -1px; }
.card input.edit { width: 100%; }
.chip { display: inline-block; font-size: 11px; font-weight: 550; padding: 0 6px; border-radius: 4px; background: var(--accent-soft); color: var(--accent-ink); cursor: pointer; border: none; line-height: 18px; }
.chip.due { background: var(--column); color: var(--muted); cursor: default; }
.chip.today { background: color-mix(in srgb, var(--energy) 15%, transparent); color: var(--energy-ink); }
.chip.late { background: #fde2df; color: #a8291d; }
:root[data-theme="dark"] .chip.late { background: #4d1f1b; color: #ff9d93; }
.link { color: var(--accent-ink); cursor: pointer; text-decoration: underline; text-underline-offset: 2px; }
.add { padding: 6px 9px 11px; }
.add input { width: 100%; background: transparent; border-style: dashed; }
.add input:focus { background: var(--panel); border-style: solid; }
.newcol { flex: 0 0 220px; }
.newcol input { width: 100%; background: transparent; border-style: dashed; padding: 9px 12px; }
.page { max-width: 780px; margin: 0 auto; padding: 22px 16px 60px; }
.page h3 { font-size: 13px; font-weight: 650; color: var(--text); margin: 26px 0 8px; display: flex; align-items: center; gap: 8px; }
.page h3 .n { color: var(--muted); font-weight: 500; }
.page .quick { display: flex; gap: 8px; }
.page .quick input { flex: 1; padding: 9px 12px; }
.page .card { cursor: default; }
.page .where { font-size: 11px; color: var(--muted); }
.empty { color: var(--muted); padding: 8px 2px; }
.numbers { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.today-stats { margin-bottom: 14px; }
.today-stats:empty { display: none; }
.week.mini { height: auto; min-height: 64px; padding: 8px 10px; gap: 4px; }
.week.mini .bars i { width: 6px; }
.number { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); padding: 14px 16px; }
.number b { display: block; font-size: 26px; font-weight: 650; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.number span { color: var(--muted); font-size: 12px; }
.week { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; align-items: end; height: 170px; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); padding: 14px; }
.day { display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; gap: 4px; font-size: 11px; color: var(--muted); }
.day .bars { display: flex; gap: 3px; align-items: flex-end; flex: 1; }
.day .bars i { display: block; width: 12px; border-radius: 2px 2px 0 0; min-height: 2px; }
.day .bars i.f { background: var(--energy); }
.day .bars i.d { background: var(--ok); }
.legend { display: flex; gap: 14px; font-size: 12px; color: var(--muted); margin-top: 6px; }
.legend i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 5px; }
.top { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); padding: 6px 14px; }
.top div { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--line); }
.top div:last-child { border-bottom: none; }

.arcade { display: grid; grid-template-columns: 272px 1fr; gap: 14px; padding: 14px 16px 16px; height: 100%; min-height: 460px; }
.side { display: flex; flex-direction: column; gap: 10px; min-height: 0; overflow-y: auto; }
.side h4 { margin: 8px 2px 0; font-size: 12px; font-weight: 650; color: var(--muted); }
.levels { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px; background: var(--column); border-radius: 8px; padding: 2px; }
.levels button { border: none; background: transparent; border-radius: 6px; padding: 4px 0; color: var(--muted); font-weight: 550; }
.levels button:hover { color: var(--text); }
.levels button.on { background: var(--panel); box-shadow: var(--shadow), 0 0 0 1px var(--line); color: var(--text); }
.levels button.on.hard { color: var(--danger); }
.tile { display: grid; grid-template-columns: 1fr auto; gap: 2px 8px; text-align: left; padding: 10px 12px; border-radius: 8px; background: var(--panel); border: 1px solid var(--line); box-shadow: none; }
.tile:hover { border-color: color-mix(in srgb, var(--text) 22%, var(--line)); }
.tile.on { border-color: var(--accent); box-shadow: inset 2px 0 0 var(--accent); }
.tile b { font-weight: 650; }
.tile small { grid-column: 1 / -1; color: var(--muted); font-size: 12px; line-height: 1.35; }
.tile .best { font: 600 12px var(--mono); color: var(--accent-ink); align-self: center; }
.tile .best.none { color: var(--muted); font-weight: 400; }
.records { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: none; padding: 6px 10px; font-size: 12px; }
.records table { width: 100%; border-collapse: collapse; }
.records th { color: var(--muted); font-weight: 500; text-align: right; padding: 3px 0; }
.records th:first-child, .records td:first-child { text-align: left; }
.records td { text-align: right; padding: 3px 0; font-family: var(--mono); border-top: 1px solid var(--line); }
.records td:first-child { font-family: var(--font); }
.stage { display: flex; flex-direction: column; min-height: 0; min-width: 0; gap: 8px; }
.screen { flex: 1; min-height: 0; background: #0c0c0b; border-radius: var(--radius); display: grid; place-items: center; position: relative; overflow: hidden; box-shadow: inset 0 0 0 1px rgba(255,255,255,.04), var(--shadow); }
.screen canvas { display: block; cursor: crosshair; }
.screen .idle { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: #c9ccd4; text-align: center; padding: 20px; }
.screen .idle b { font: 700 22px var(--mono); letter-spacing: .3em; color: #ffc933; }
.screen .idle span { color: #8b8f98; font-size: 13px; }
.screen:fullscreen { border-radius: 0; }
.status { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.status .what { font-weight: 600; }
.status .hint { color: var(--muted); font-size: 12px; flex: 1; }
.status .live { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
.status .live.on { background: var(--ok); box-shadow: 0 0 0 3px color-mix(in srgb, var(--ok) 25%, transparent); }

#toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%) translateY(6px); background: var(--text); color: var(--bg); padding: 8px 14px; border-radius: 7px; opacity: 0; transition: opacity .2s, transform .2s; pointer-events: none; max-width: 80vw; box-shadow: var(--lift); z-index: 20; }
#toast.on { opacity: .96; transform: translateX(-50%); }
kbd { font: 11px var(--mono); border: 1px solid var(--line); border-bottom-width: 2px; border-radius: 5px; padding: 0 5px; background: var(--panel); }
#help { position: fixed; inset: 0; background: rgba(10,8,4,.4); display: none; place-items: center; z-index: 10; }
#help.on { display: grid; }
#help .sheet { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; box-shadow: var(--lift); padding: 18px 22px; width: min(460px, 92vw); }
#help h3 { margin: 0 0 10px; font-size: 15px; }
#help dl { display: grid; grid-template-columns: auto 1fr; gap: 7px 16px; margin: 0; font-size: 13px; }
#help dt { text-align: right; white-space: nowrap; }
#help dd { margin: 0; color: var(--muted); }
/*@STUDIO_CSS@*/
@media (max-width: 760px) {
  .arcade { grid-template-columns: 1fr; height: auto; }
  .screen { min-height: 360px; }
  .search input { width: 170px; }
}
.cv { display: flex; flex-direction: column; height: 100%; min-height: 420px; }
.cvbar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; padding: 6px 12px; border-bottom: 1px solid var(--line); background: var(--panel); }
.cvbar .group { display: flex; align-items: center; gap: 2px; background: var(--column); border-radius: 8px; padding: 2px; }
.cvbar .group button { border: none; background: transparent; padding: 4px 6px; border-radius: 6px; color: var(--muted); font-size: 13px; display: inline-flex; align-items: center; justify-content: center; }
.cvbar .group button svg { width: 18px; height: 18px; display: block; }
.cvbar .group button:disabled { opacity: .35; }
.cvbar .group button:hover { color: var(--text); }
.cvbar .group button.on { background: var(--accent); color: var(--on-accent); }
.cvbar .group .swatch { box-sizing: border-box; width: 18px; height: 18px; padding: 0; border-radius: 50%; margin: 0 3px; border: 2px solid var(--line); }
.cvbar .group .swatch.on { border-color: var(--accent-ink); box-shadow: 0 0 0 2px var(--accent-soft); }
.cvbar .group .swatch.custom { position: relative; display: inline-block; overflow: hidden; cursor: pointer; background: conic-gradient(#e5484d, #e8b520, #30a46c, #2aa9bd, #3a6df0, #8e4ec6, #e5484d); }
.cvbar .group .swatch.custom input { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; border: 0; padding: 0; cursor: pointer; }
.cvbar .cvname { width: 150px; font-weight: 600; border: 1px solid transparent; background: transparent; border-radius: 7px; padding: 3px 7px; color: var(--text); }
.cvbar .cvname:hover, .cvbar .cvname:focus { border-color: var(--line); background: var(--column); outline: none; }
.cvbar .group button.more { position: relative; }
.cvbar .group button.more::after { content: ""; position: absolute; right: 2px; bottom: 2px; border-style: solid; border-width: 0 0 5px 5px; border-color: transparent transparent currentColor transparent; opacity: .55; }
.cvbar .cvwidth { width: 100px; margin: 0 4px; accent-color: var(--accent); }
.cvbar .cvwidthval { width: 38px; font-size: 12px; color: var(--text); text-align: center; font-variant-numeric: tabular-nums; border: 1px solid transparent; background: transparent; border-radius: 6px; padding: 2px 3px; margin-right: 2px; }
.cvbar .cvwidthval:hover, .cvbar .cvwidthval:focus { border-color: var(--line); background: var(--panel); outline: none; }
.cvmenu { position: fixed; z-index: 30; display: none; flex-direction: column; gap: 2px; padding: 4px; background: var(--panel); border: 1px solid var(--line); border-radius: 9px; box-shadow: var(--lift); }
.cvmenu.on { display: flex; }
.cvmenu button { display: flex; align-items: center; gap: 9px; border: none; background: transparent; padding: 6px 10px; border-radius: 5px; color: var(--text); font-size: 13px; text-align: left; white-space: nowrap; }
.cvmenu button:hover { background: var(--column); }
.cvmenu button.on { background: var(--accent-soft); color: var(--accent-ink); }
.cvmenu button svg { width: 18px; height: 18px; flex: none; }
.cvmenu .num { width: 18px; text-align: center; font-weight: 700; font-size: 15px; }
.cvzoom, .cvstatus { font: 12px var(--mono); color: var(--muted); min-width: 40px; text-align: center; }
.cvstage { position: relative; flex: 1; min-height: 0; overflow: hidden; }
.cvbody { flex: 1; min-height: 0; display: flex; position: relative; }
.cvbar .cvpick { display: inline-flex; gap: 5px; align-items: center; max-width: 140px; border-color: transparent; background: var(--column); color: var(--muted); }
.cvview { display: none; position: absolute; inset: 0; z-index: 6; background: var(--bg); flex-direction: column; }
.cvview.on { display: flex; }
.cvview .head { display: flex; align-items: center; gap: 10px; padding: 8px 14px; border-bottom: 1px solid var(--line); background: var(--panel); }
.cvview .head b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cvview .head .spacer { flex: 1; }
.cvview .head button { display: inline-flex; align-items: center; gap: 5px; }
.cvview .head button svg { width: 16px; height: 16px; }
.cvview .body { flex: 1; min-height: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 14px; overflow: auto; }
.cvview .body img, .cvview .body video { max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 6px; }
.cvview .body iframe { flex: 1; width: 100%; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
.cvview .body.text { align-items: stretch; justify-content: flex-start; }
.cvview .body pre { margin: 0; white-space: pre-wrap; word-break: break-word; font: 13px/1.5 var(--mono); color: var(--text); background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }
.cvview .body .sound { display: flex; flex-direction: column; align-items: center; gap: 14px; font-weight: 600; }
.cvview .body .sound > svg { width: 64px; height: 64px; color: var(--accent-ink); }
.cvview .body .sound audio { width: min(520px, 80vw); }
.cvview .body canvas.model { flex: 1; width: 100%; min-height: 200px; cursor: grab; touch-action: none; }
.cvview .note { color: var(--muted); font-size: 12px; text-align: center; }
.cvgallery { display: none; position: absolute; inset: 0; z-index: 5; background: var(--bg); overflow: auto; padding: 14px 18px 24px; }
.cvgallery.on { display: block; }
.cvgallery .head { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.cvgallery .head .hint { color: var(--muted); font-size: 12px; }
.cvgallery .head .search { width: 220px; padding: 6px 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); color: var(--text); font: inherit; }
.cvgallery .head .search:focus { outline: none; border-color: var(--accent-ink); }
.cvgallery > .shelves > .empty { color: var(--muted); padding: 20px 4px; }
.cvgallery .head .spacer { flex: 1; }
.cvgallery .head button { display: inline-flex; align-items: center; gap: 5px; }
.cvgallery .head button svg { width: 16px; height: 16px; }
.cvgallery .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
.cvgallery .tile { position: relative; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; cursor: pointer; }
.cvgallery .tile:hover { border-color: var(--accent-ink); }
.cvgallery .tile.on { box-shadow: 0 0 0 2px var(--accent); }
.cvgallery .thumb { display: block; width: 100%; aspect-ratio: 8 / 5; background: var(--column); }
.cvgallery .meta { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; }
.cvgallery .meta .name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cvgallery .meta .when { color: var(--muted); font-size: 11px; }
.cvgallery .acts { position: absolute; top: 6px; right: 6px; display: flex; gap: 4px; }
.cvgallery .acts button { display: none; border: none; border-radius: 7px; padding: 5px; background: var(--panel); color: var(--muted); box-shadow: var(--shadow); }
.cvgallery .acts svg { width: 16px; height: 16px; display: block; }
.cvgallery .tile:hover .acts button, .cvgallery .acts .fav.on { display: block; }
.cvgallery .acts .fav.on { color: var(--energy); }
.cvgallery .acts .fav.on svg { fill: currentColor; }
.cvgallery .acts button:hover { color: var(--text); }
.cvgallery .acts .del:hover { color: #e5484d; }
.cvgallery .shelf { margin-bottom: 22px; border-radius: var(--radius); }
.cvgallery .shelf.drop { outline: 2px dashed var(--accent-ink); outline-offset: 6px; }
.cvgallery .section { display: flex; align-items: center; gap: 8px; margin: 0 0 10px; color: var(--text); }
.cvgallery .section > svg { width: 16px; height: 16px; color: var(--muted); }
.cvgallery .section.favorites > svg { color: var(--energy); fill: currentColor; }
.cvgallery .section .count { color: var(--muted); font-size: 12px; }
.cvgallery .section .mini { border: none; background: transparent; padding: 3px; color: var(--muted); display: inline-flex; }
.cvgallery .section .mini svg { width: 15px; height: 15px; }
.cvgallery .section .mini:hover { color: var(--text); }
.cvgallery .shelf .empty { color: var(--muted); font-size: 12px; padding: 18px 4px; }
.cvinline { position: absolute; inset: 0; overflow: hidden; pointer-events: none; z-index: 1; }
.cvinline iframe { position: absolute; border: 0; background: #ffffff; pointer-events: auto; box-shadow: 0 2px 10px rgba(0, 0, 0, .25); }
.cvplayers { position: absolute; width: 1px; height: 1px; overflow: hidden; opacity: 0; pointer-events: none; }
.cvlayers { display: none; width: 240px; flex: none; border-left: 1px solid var(--line); background: var(--panel); overflow: auto; font-size: 13px; }
.cvlayers.on { display: block; }
.cvlayers .head { display: flex; align-items: baseline; gap: 8px; padding: 10px 12px 6px; position: sticky; top: 0; background: var(--panel); }
.cvlayers .head .n { color: var(--muted); font-size: 11px; }
.cvlayers .head .spacer { flex: 1; }
.cvlayers .head .all { border: none; background: transparent; padding: 2px; color: var(--muted); display: inline-flex; align-self: center; }
.cvlayers .head .all svg { width: 14px; height: 14px; }
.cvlayers .head .all:hover { color: var(--text); }
.cvlayers .fold { width: 18px; flex: none; border: none; background: transparent; padding: 1px; color: var(--muted); display: inline-flex; }
.cvlayers .fold svg { width: 14px; height: 14px; }
.cvlayers .fold:hover { color: var(--text); }
.cvlayers .row.section { margin-top: 6px; color: var(--muted); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; cursor: pointer; }
.cvlayers .row.group .name { font-weight: 600; }
.cvlayers .row .count { margin-left: auto; color: var(--muted); font-size: 11px; background: var(--column); border-radius: 8px; padding: 0 6px; }
.cvlayers .row { display: flex; align-items: center; gap: 6px; padding: 4px 8px; margin: 0 4px; border-radius: 6px; cursor: default; }
.cvlayers .row:hover { background: var(--column); }
.cvlayers .row.on { background: var(--accent-soft); }
.cvlayers .row.inner { padding-left: 32px; }
.cvlayers .row.hidden .name, .cvlayers .row.hidden > svg { opacity: .4; }
.cvlayers .row > svg { width: 16px; height: 16px; flex: none; color: var(--muted); }
.cvlayers .row .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cvlayers .eye { border: none; background: transparent; padding: 2px; color: var(--muted); display: inline-flex; }
.cvlayers .eye svg { width: 16px; height: 16px; }
.cvlayers .eye:hover { color: var(--text); }
.cvlayers .empty { padding: 8px 14px; }
.cvcanvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; touch-action: none; outline: none; }
.cvedit { position: absolute; display: none; resize: none; border: 2px solid var(--accent); border-radius: 8px; background: var(--panel); color: var(--text); padding: 4px 6px; outline: none; z-index: 3; line-height: 1.3; overflow: auto; }
.cvempty { position: absolute; inset: 0; display: none; place-content: center; justify-items: center; gap: 10px; color: var(--muted); }
.cvbar .cvadd { margin-left: auto; }
.cvbar .cvadd button { gap: 5px; color: var(--text); font-weight: 600; padding: 4px 9px; }
.cvstage.dropping::after { content: "Drop files to pin them here"; position: absolute; inset: 10px; display: grid; place-items: center; border: 3px dashed var(--accent); border-radius: 14px; background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent-ink); font-weight: 700; font-size: 18px; pointer-events: none; z-index: 4; }
</style>
</head>
<body>
<header>
  <span class="brand"><svg class="mark light" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#fff"/><path d="M15 18V36a7.5 7.5 0 0 0 15 0V18M38.5 18V43.5H52.5" fill="none" stroke="#f5a300" stroke-width="7"/></svg><svg class="mark dark" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#0b0b0a"/><path d="M15 18V36a7.5 7.5 0 0 0 15 0V18M38.5 18V43.5H52.5" fill="none" stroke="#f5a300" stroke-width="7"/></svg>Desk</span>
  <div id="boards" class="picker"></div>
  <div class="tabs" id="tabs">
    <button data-view="board" class="on" title="Board (1)">Board</button>
    <button data-view="today" title="Today: tasks and focus stats (2)">Today</button>
    <button data-view="games" title="Games (3)">Games</button>
    <button data-view="studio" title="Studio: record and screenshots (4)">Studio</button>
    <button data-view="canvas" title="Canvas: whiteboard (5)">Canvas</button>
  </div>
  <span class="spacer"></span>
  <button id="recPill" class="rec-pill" title="Recording: open the Studio"></button>
  <div class="timer" id="timer">
    <span class="phase" id="phase">Ready</span>
    <span class="bar"><i id="progress"></i></span>
    <span class="clock" id="clock">25:00</span>
    <span class="linked" id="linked"></span>
    <button id="play" title="Start / pause (space)">Start</button>
    <button id="skip" class="ghost" title="Skip to the next phase">Skip</button>
    <button id="stop" class="ghost" title="Stop">Stop</button>
  </div>
  <div class="actions-bar">
    <button id="obsidian" class="ghost icon" title="Open this board in Obsidian"><svg viewBox="0 0 24 24"><path d="M14 3h7v7"/><path d="M10 14 21 3"/><path d="M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/></svg></button>
    <button id="lofi" class="ghost icon" title="Open lofi music"><svg viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg></button>
    <button id="theme" class="ghost icon" title="Light / dark"><svg viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg></button>
    <button id="helpButton" class="ghost icon" title="Keyboard shortcuts (?)"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14"/><path d="M12 17.5h.01"/></svg></button>
  </div>
</header>
<div class="toolbar" id="toolbar">
  <label class="search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input id="search" type="search" placeholder="Search cards  /"></label>
  <button id="filter" class="chip" title="Clear tag filter"></button>
  <div class="summary" id="summary"></div>
</div>
<main id="main"></main>
<div id="help"><div class="sheet">
  <h3>Keyboard shortcuts</h3>
  <dl>
    <dt><kbd>n</kbd></dt><dd>New card (Today: quick add)</dd>
    <dt><kbd>/</kbd></dt><dd>Search cards</dd>
    <dt><kbd>space</kbd></dt><dd>Start / pause the focus timer</dd>
    <dt><kbd>1</kbd> … <kbd>5</kbd></dt><dd>Board, Today (tasks and focus stats), Games, Studio, Canvas (on the Studio Record tab the digits pick scenes)</dd>
    <dt><kbd>Esc</kbd></dt><dd>Clear search and tag filter</dd>
    <dt>double-click</dt><dd>Edit a card; drag cards between columns</dd>
    <dt>Games</dt><dd>While a game runs every key goes to it: arrows/WASD, Space, P pause, Esc leaves. Mouse works as in the terminal.</dd>
    <dt>Studio</dt><dd>Record tab: <kbd>r</kbd> start (after the countdown) / stop, <kbd>p</kbd> pause / resume, <kbd>m</kbd> mark, <kbd>1</kbd> … <kbd>9</kbd> scenes. Drag a source to move it (corners and edges snap; a corner pins it), drag its yellow corner to resize, <kbd>⌥</kbd>-drag to pan inside it. Recording runs <code>ul capture</code>, so it keeps going when the page is closed; every recording becomes a project you export from the Projects tab.</dd>
    <dt>Canvas</dt><dd>Photoshop-style keys; a tool stays until you pick another. <kbd>v</kbd> select, <kbd>h</kbd> hand (or hold <kbd>space</kbd>), <kbd>n</kbd> card, <kbd>t</kbd> text, <kbd>u</kbd> shapes (<kbd>Shift</kbd>+<kbd>u</kbd> cycles rectangle, ellipse, diamond, line, arrow; also <kbd>r</kbd> <kbd>o</kbd> <kbd>l</kbd> <kbd>a</kbd>), <kbd>b</kbd> brush, <kbd>g</kbd> fill (<kbd>Alt</kbd>+click clears; open space reaching the edge of the view fills the background), <kbd>e</kbd> eraser (<kbd>Shift</kbd>+<kbd>e</kbd> switches whole object / only where it passes). Click an active eraser or shape tool again for its options (shape evenness 3 perfect, 2, 1 rougher). The fill tool floods the area of the clicked color like a paint program. <kbd>[</kbd> <kbd>]</kbd> or <kbd>-</kbd> <kbd>=</kbd> stroke width (slider 1-100; click the number to type one), <kbd>d</kbd> default color, <kbd>Cmd/Ctrl</kbd>+<kbd>G</kbd> group, <kbd>Cmd/Ctrl</kbd>+<kbd>0</kbd> fit, <kbd>Cmd/Ctrl</kbd>+<kbd>+</kbd> <kbd>-</kbd> zoom, <kbd>Del</kbd> delete, arrows nudge, <kbd>Cmd/Ctrl</kbd>+<kbd>Z</kbd> <kbd>C</kbd> <kbd>V</kbd> <kbd>D</kbd> <kbd>A</kbd>. Wheel pans, <kbd>Ctrl</kbd>+wheel or pinch zooms, double-click edits text, drag a side dot of a card to connect (let go on empty canvas for a new card). <kbd>k</kbd> thread: click a spot on one card, then on another; drag the end of a selected edge to move it. <kbd>F7</kbd> or the layers button: Layers, the eye hides a card, group or drawing, drag rows to reorder. The name left of the tools renames the file.</dd>
    <dt><kbd>?</kbd></dt><dd>This list</dd>
  </dl>
</div></div>
<div id="viewer"><div class="sheet" id="viewerSheet"></div></div>
<div id="toast"></div>
<script>
"use strict";
const params = new URLSearchParams(location.search);
if (params.get("token")) {
  sessionStorage.setItem("desk-token", params.get("token"));
  history.replaceState(null, "", location.pathname + location.hash);
}
const TOKEN = sessionStorage.getItem("desk-token") || "";
const VIEWS = ["board", "today", "games", "studio", "canvas"];
// Stats became part of Today (3.22.0): an old bookmark or saved view opens Today.
const savedView = (view) => view === "stats" ? "today" : view;
const state = { board: null, view: VIEWS.includes(savedView(location.hash.slice(1))) ? savedView(location.hash.slice(1)) : savedView(localStorage.getItem("desk-view") || "board"), query: "", tag: "", timer: null, timerAt: 0, editing: null, dragging: null, draggingColumn: null, stats: null };
if (!VIEWS.includes(state.view)) state.view = "board";
const $ = (id) => document.getElementById(id);

function h(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

let toastTimer = 0;
function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("on"), 2600);
}

async function api(method, path, body, headers) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: { "X-Desk-Token": TOKEN, "Content-Type": "application/json", ...(headers || {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch (error) {
    return { status: 0, data: { error: "Could not reach the desk: " + error.message } };
  }
  if (response.status === 304) return { status: 304 };
  let data = {};
  try { data = await response.json(); } catch (error) { data = {}; }
  return { status: response.status, data };
}

// ---- board ----
async function loadBoard(force) {
  const headers = !force && state.board ? { "If-None-Match": state.board.version } : {};
  const { status, data } = await api("GET", "/api/board", undefined, headers);
  if (status === 304) return;
  if (status !== 200) { toast(data.error || "Could not read the board"); return; }
  setBoard(data);
}

function setBoard(board) {
  state.board = board;
  document.title = board.name + " · Desk";
  if (!state.editing && !["games", "studio", "canvas"].includes(state.view)) render();
}

function findCard(board, line, hint) {
  for (const [c, column] of board.columns.entries()) {
    for (const [i, card] of column.cards.entries()) {
      if (card.line === line && (hint === undefined || c === hint)) return { column: c, index: i };
    }
  }
  return hint === undefined ? null : findCard(board, line);
}

// Sends one change; when the file changed meanwhile, finds the card again and retries once.
async function change(op, retried) {
  const request = { ...op, version: state.board.version };
  const { status, data } = await api("POST", "/api/board", request);
  if (status === 200) { setBoard(data); return true; }
  if (status === 409 && data.board) {
    const previous = state.board;
    state.board = data.board;
    if (!retried) {
      const byName = (at) => {
        const name = previous.columns[at] && previous.columns[at].name;
        return data.board.columns.findIndex((column) => column.name === name);
      };
      const again = { ...op };
      if (op.line !== undefined) {
        const found = findCard(data.board, op.line, byName(op.column));
        if (!found) { render(); toast("That card changed in the file; reloaded"); return false; }
        again.column = found.column;
        again.index = found.index;
      } else if (op.column !== undefined) {
        again.column = byName(op.column);
      }
      if (op.to_column !== undefined) again.to_column = byName(op.to_column);
      if (again.column < 0 || again.to_column < 0) { render(); toast("A column changed in the file; reloaded"); return false; }
      toast("The file changed; applied on top");
      return change(again, true);
    }
    render();
    toast("The board changed; reloaded");
    return false;
  }
  toast(data.error || "Could not save");
  if (status === 404 || status === 500) loadBoard(true);
  return false;
}

const MARKUP = /(\[\[[^\]]+\]\])|(?<![\w&/])#([^\s#\[\]{}(),.;:!?'"]+)|@\{(\d{4}-\d{2}-\d{2})\}|\u{1F4C5}\s*(\d{4}-\d{2}-\d{2})|\s*\[completion::\s*\d{4}-\d{2}-\d{2}\]/gu;

function dueChip(due) {
  if (!due) return null;
  const today = state.board.today;
  const kind = due < today ? "late" : due === today ? "today" : "";
  const label = due === today ? "today" : due === addDays(today, 1) ? "tomorrow" : due < today ? "overdue " + due.slice(5) : due.slice(5);
  return h("span", { class: "chip due " + kind, title: due, text: label });
}

function titleNodes(card) {
  const nodes = [];
  let last = 0;
  for (const match of card.title.matchAll(MARKUP)) {
    if (match.index > last) nodes.push(card.title.slice(last, match.index));
    last = match.index + match[0].length;
    if (match[1]) {
      const name = match[1].slice(2, -2).split(/[|#]/)[0];
      const label = match[1].slice(2, -2).split("|").pop();
      nodes.push(h("span", { class: "link", title: "Open in Obsidian", text: label, onclick: (event) => { event.stopPropagation(); openNote(name); } }));
    }
  }
  if (last < card.title.length) nodes.push(card.title.slice(last));
  return nodes;
}

function matches(card) {
  if (state.tag && !card.tags.includes(state.tag)) return false;
  if (!state.query) return true;
  const haystack = (card.title + " " + card.details.join(" ")).toLowerCase();
  return state.query.toLowerCase().split(/\s+/).every((word) => haystack.includes(word));
}

function cardNode(card, column, index, options) {
  const where = { line: card.line, column, index };
  const focused = state.timer && state.timer.card && state.timer.card === plain(card) && state.timer.phase !== "idle";
  const node = h("div", { class: "card" + (card.checked ? " checked" : "") + (focused ? " focus" : ""), draggable: options.drag ? "true" : null });
  if (state.editing && state.editing.line === card.line && state.editing.column === column) {
    const input = h("input", { class: "edit", value: card.title });
    const finish = async (save) => {
      if (!state.editing) return;
      state.editing = null;
      const text = input.value.trim();
      if (save && text && text !== card.title) await change({ op: "edit", text, ...where });
      else render();
    };
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") finish(true);
      if (event.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
    node.append(input);
    setTimeout(() => { input.focus(); input.select(); }, 0);
    return node;
  }
  const check = h("button", { class: "check", title: card.checked ? "Reopen" : "Done", onclick: (event) => { event.stopPropagation(); change({ op: card.checked ? "reopen" : "done", ...where }); } });
  const meta = h("div", { class: "meta" },
    card.tags.map((tag) => h("button", { class: "chip", text: "#" + tag, title: "Filter by #" + tag, onclick: (event) => { event.stopPropagation(); setTag(tag); } })),
    card.checked ? null : dueChip(card.due));
  const body = h("div", { class: "body" },
    h("div", { class: "text" }, titleNodes(card)),
    card.tags.length || card.due ? meta : null,
    card.details.length ? h("div", { class: "details", text: card.details.join("\n") }) : null,
    options.where ? h("div", { class: "where", text: options.where }) : null);
  const actions = h("div", { class: "actions" },
    card.checked ? null : h("button", { title: "Focus on this card (pomodoro)", text: "Focus", onclick: (event) => { event.stopPropagation(); timer("start", plain(card)); } }),
    h("button", { title: "Edit", text: "Edit", onclick: (event) => { event.stopPropagation(); state.editing = where; render(); } }),
    h("button", { class: "del", title: "Delete", "aria-label": "Delete", onclick: (event) => { event.stopPropagation(); if (confirm("Delete this card?\n\n" + card.title)) change({ op: "delete", ...where }); } }, svgIcon("M6 6l12 12M18 6L6 18")));
  node.append(check, body, actions);
  node.addEventListener("dblclick", () => { state.editing = where; render(); });
  if (options.drag) {
    node.addEventListener("dragstart", (event) => {
      state.dragging = where;
      node.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", card.title);
    });
    node.addEventListener("dragend", () => { state.dragging = null; node.classList.remove("dragging"); });
  }
  return node;
}

function plain(card) {
  return card.title.replace(MARKUP, (whole, link) => link ? link.slice(2, -2).split("|").pop() : "").replace(/\s+/g, " ").trim() || card.title;
}

function dropIndex(container, y) {
  const cards = [...container.querySelectorAll(".card:not(.dragging)")];
  for (const [i, card] of cards.entries()) {
    const box = card.getBoundingClientRect();
    if (y < box.top + box.height / 2) return Number(card.dataset.index ?? i);
  }
  return cards.length ? Number(cards[cards.length - 1].dataset.index) + 1 : 0;
}

function renderBoard(main) {
  const board = state.board;
  const wrap = h("div", { class: "board" });
  board.columns.forEach((column, c) => {
    const list = h("div", { class: "cards" });
    let shown = 0;
    column.cards.forEach((card, i) => {
      if (!matches(card)) return;
      const node = cardNode(card, c, i, { drag: !state.query && !state.tag });
      node.dataset.index = i;
      list.append(node);
      shown += 1;
    });
    const input = h("input", { placeholder: "+ Add a card", "data-column": c });
    input.addEventListener("keydown", async (event) => {
      if (event.key === "Enter" && input.value.trim()) {
        const text = input.value.trim();
        input.value = "";
        if (await change({ op: "add", column: c, text })) {
          const again = document.querySelector('.add input[data-column="' + c + '"]');
          if (again) again.focus();
        }
      }
      if (event.key === "Escape") input.blur();
    });
    const done = column.name === board.done_column;
    const movable = board.layer !== "reminders";
    const heading = h("h2", { draggable: movable ? "true" : null, title: movable ? "Drag to move the column" : null }, h("span", { class: "name", text: column.name, title: column.name }),
        h("span", { class: "count", text: state.query || state.tag ? shown + "/" + column.cards.length : column.cards.length }),
        h("button", { title: "Add a card to " + column.name, text: "+", onclick: () => input.focus() }));
    const node = h("section", { class: "column" + (column.doing ? " doing" : "") + (done ? " done" : "") }, heading,
      list, h("div", { class: "add" }, input));
    if (movable) {
      heading.addEventListener("dragstart", (event) => {
        state.draggingColumn = c;
        node.classList.add("dragging");
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", column.name);
        event.dataTransfer.setDragImage(node, event.offsetX, event.offsetY);
      });
      heading.addEventListener("dragend", () => {
        state.draggingColumn = null;
        node.classList.remove("dragging");
        for (const other of wrap.querySelectorAll(".column")) other.classList.remove("col-before", "col-after");
      });
    }
    // Which side of this column a dragged column lands on: the left or right half under the pointer.
    const columnSide = (event) => {
      const box = node.getBoundingClientRect();
      return event.clientX < box.left + box.width / 2 ? "before" : "after";
    };
    node.addEventListener("dragover", (event) => {
      if (state.draggingColumn != null) {
        event.preventDefault();
        const side = state.draggingColumn === c ? null : columnSide(event);
        node.classList.toggle("col-before", side === "before");
        node.classList.toggle("col-after", side === "after");
        return;
      }
      if (!state.dragging) return;
      event.preventDefault();
      node.classList.add("drop");
    });
    node.addEventListener("dragleave", (event) => {
      if (node.contains(event.relatedTarget)) return;
      node.classList.remove("drop", "col-before", "col-after");
    });
    node.addEventListener("drop", (event) => {
      event.preventDefault();
      node.classList.remove("drop", "col-before", "col-after");
      if (state.draggingColumn != null) {
        const from = state.draggingColumn;
        state.draggingColumn = null;
        let to = columnSide(event) === "before" ? c : c + 1;
        if (from < to) to -= 1;
        if (from !== to) change({ op: "move_column", column: from, name: board.columns[from].name, to_index: to });
        return;
      }
      const from = state.dragging;
      if (!from) return;
      let to = dropIndex(list, event.clientY);
      if (from.column === c && from.index < to) to -= 1;
      if (from.column === c && from.index === to) return;
      change({ op: "move", ...from, to_column: c, to_index: to });
    });
    wrap.append(node);
  });
  const newColumn = h("input", { placeholder: "+ Add a column" });
  newColumn.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && newColumn.value.trim()) change({ op: "column", name: newColumn.value.trim() });
  });
  wrap.append(h("div", { class: "newcol" }, newColumn));
  main.append(wrap);
}

function renderSummary() {
  const node = $("summary");
  node.textContent = "";
  if (!state.board) return;
  const board = state.board;
  const today = board.today;
  let open = 0, due = 0, late = 0;
  for (const column of board.columns) {
    if (column.name === board.done_column) continue;
    for (const card of column.cards) {
      if (card.checked) continue;
      open += 1;
      if (card.due && card.due < today) late += 1;
      else if (card.due === today) due += 1;
    }
  }
  const pill = (count, label, kind) => h("span", { class: "pill " + (kind || "") }, h("b", { text: count }), " " + label);
  node.append(pill(open, "open"));
  if (due) node.append(pill(due, "due today", "today"));
  if (late) node.append(pill(late, "overdue", "late"));
}

function renderToday(main) {
  const board = state.board;
  const today = board.today;
  const late = [], due = [], doing = [], soon = [];
  board.columns.forEach((column, c) => column.cards.forEach((card, i) => {
    if (card.checked || column.name === board.done_column || !matches(card)) return;
    const item = { card, c, i, where: column.name };
    if (card.due && card.due < today) late.push(item);
    else if (card.due === today) due.push(item);
    else if (column.doing) doing.push(item);
    else if (card.due && card.due <= addDays(today, 7)) soon.push(item);
  }));
  soon.sort((a, b) => a.card.due.localeCompare(b.card.due));
  const quick = h("input", { placeholder: "Add a task: text #tag @today @tomorrow @+3 @2026-12-01" });
  quick.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter" || !quick.value.trim()) return;
    const first = board.columns.findIndex((column) => column.name !== board.done_column && !column.doing);
    const text = quick.value.trim();
    quick.value = "";
    if (await change({ op: "add", column: Math.max(0, first), text })) document.querySelector(".quick input")?.focus();
  });
  const stats = h("div", { class: "today-stats" });
  const page = h("div", { class: "page" }, stats, h("div", { class: "quick" }, quick));
  drawTodayStats(stats);
  loadTodayStats(stats);
  const section = (title, items) => {
    page.append(h("h3", {}, title, h("span", { class: "n", text: items.length })));
    if (!items.length) page.append(h("div", { class: "empty", text: "Nothing here." }));
    for (const item of items) page.append(cardNode(item.card, item.c, item.i, { where: item.where }));
  };
  section("Overdue", late);
  section("Today", due);
  section("In progress", doing);
  section("Next 7 days", soon);
  const most = h("div", { class: "most-focused" });
  page.append(most);
  drawMostFocused(most);
  main.append(page);
}

// Calendar arithmetic in UTC: a local noon is the previous UTC day in UTC+13/+14.
function addDays(iso, days) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

// Focus numbers for Today come from /api/stats (pomodoro log + done dates); kept between renders so the
// page does not flicker, refreshed at most every 20 s or when the board/timer changes them.
let todayStatsAt = 0;
async function loadTodayStats(node) {
  if (Date.now() - todayStatsAt < 20000 && state.stats) return;
  todayStatsAt = Date.now();
  const { status, data } = await api("GET", "/api/stats");
  if (status !== 200) { todayStatsAt = 0; return; }
  state.stats = data;
  if (state.view !== "today" || !node.isConnected) return;
  drawTodayStats(node);
  const most = document.querySelector(".most-focused");
  if (most) drawMostFocused(most);
}

function drawTodayStats(node) {
  node.textContent = "";
  const data = state.stats;
  if (!data) return;
  const number = (value, label) => h("div", { class: "number" }, h("b", { text: value }), h("span", { text: label }));
  const most = Math.max(1, ...data.week.map((day) => Math.max(day.pomodoros, day.done)));
  const week = h("div", { class: "week mini", title: "Last 7 days: focus sessions (orange) and tasks done (green)" }, data.week.map((day) => h("div", { class: "day", title: day.date + ": " + day.pomodoros + " focus, " + day.minutes + " min, " + day.done + " done" },
    h("div", { class: "bars" }, h("i", { class: "f", style: "height:" + (day.pomodoros / most * 100) + "%" }), h("i", { class: "d", style: "height:" + (day.done / most * 100) + "%" })),
    h("span", { text: new Date(day.date + "T12:00:00").toLocaleDateString(undefined, { weekday: "narrow" }) }))));
  node.append(h("div", { class: "numbers" },
    number(Math.round(data.today.minutes), "focus min today"),
    number(data.today.done, "done today"),
    number(data.streak, "day streak"),
    week));
}

function drawMostFocused(node) {
  node.textContent = "";
  const data = state.stats;
  if (!data || !data.cards.length) return;
  node.append(h("h3", {}, "Most focused cards", h("span", { class: "n", text: data.total_pomodoros + " sessions all time" })),
    h("div", { class: "top" }, data.cards.map((item) => h("div", {}, h("span", { text: item.card }), h("span", { class: "where", text: Math.round(item.minutes) + " min" })))));
}

function render() {
  const main = $("main");
  for (const button of $("tabs").children) button.classList.toggle("on", button.dataset.view === state.view);
  $("toolbar").classList.toggle("hidden", ["games", "studio", "canvas"].includes(state.view));
  const filter = $("filter");
  filter.classList.toggle("on", Boolean(state.tag));
  filter.textContent = state.tag ? "#" + state.tag + " " : "";
  if (state.tag) filter.append(svgIcon("M6 6l12 12M18 6L6 18"));
  renderSummary();
  if (state.view === "games") { renderGames(main); return; }
  if (state.view === "studio") { renderStudio(main); return; }
  if (state.view === "canvas") { renderCanvas(main); return; }
  if (!state.board) return;
  const scroll = main.scrollLeft;
  const active = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.column : undefined;
  main.textContent = "";
  if (state.view === "today") renderToday(main);
  else renderBoard(main);
  main.scrollLeft = scroll;
  if (active !== undefined) document.querySelector('.add input[data-column="' + active + '"]')?.focus();
}

function setView(view) {
  if (view === state.view) return;
  if (state.view === "games") pauseGame();
  if (state.view === "studio") leaveStudio();
  if (state.view === "canvas") leaveCanvas();
  state.view = view;
  localStorage.setItem("desk-view", view);
  history.replaceState(null, "", location.pathname + "#" + view);
  render();
}

function setTag(tag) {
  state.tag = state.tag === tag ? "" : tag;
  render();
}

// ---- games: the Rust arcade streamed from `ul game --stream` ----
const GAME_INFO = {
  tetris: "7-bag, next and hold, ghost piece, wall kicks",
  snake: "Eat ● and bonus ★, grow and speed up",
  minesweeper: "First click is safe; lowest time wins",
  invaders: "Formation, shields, UFO, waves",
  chomp: "Maze chase with four hunters; new maze each level",
  dash: "Endless runner: jump, duck, faster and faster",
  pingpong: "Table tennis to 11: vs the bot or a friend (W/S and ↑/↓)",
  chess: "vs the bot or a friend, optional clock; click a piece, then its square",
};
const PALETTE = { red: "#ff5f57", green: "#3ed67a", yellow: "#ffd84d", blue: "#4d8dff", magenta: "#d77bff", cyan: "#4fd8e8", white: "#f4f5f7", gray: "#8b8f98", darkred: "#c0392b", darkyellow: "#c9971c", darkblue: "#3159c9", darkcyan: "#1f9aa8", boardlight: "#b58c63", boarddark: "#78563a", lastlight: "#aaa23a", lastdark: "#8a8228", selected: "#608c56", target: "#b05448", check: "#d63a3a", piecewhite: "#ffffff", pieceblack: "#000000" };
const SCREEN_BG = "#0e1014", SCREEN_FG = "#d9dce3";
const QUADRANTS = { "▘": 1, "▝": 2, "▖": 4, "▌": 5, "▞": 6, "▛": 7, "▗": 8, "▚": 9, "▐": 10, "▜": 11, "▙": 13, "▟": 14 };
const BOX = { "─": "0101", "│": "1010", "┌": "0110", "┐": "0011", "└": "1100", "┘": "1001", "├": "1110", "┤": "1011", "┬": "0111", "┴": "1101", "┼": "1111", "═": "0101", "║": "1010" };
const arcade = { info: null, level: localStorage.getItem("desk-level") || "", game: null, session: "", frame: null, queue: [], sending: false, abort: null, cell: { w: 10, h: 20, font: 16 }, grid: { rows: 30, cols: 100 }, hover: "", drawPending: false, ended: "" };

async function loadGames() {
  const { status, data } = await api("GET", "/api/games");
  if (status !== 200) return;
  arcade.info = data;
  if (!arcade.level) arcade.level = data.difficulty;
  if (state.view === "games") renderGameSide();
}

function bestText(game, level) {
  const best = game.best[level];
  return best === undefined ? null : best + (game.unit ?? (game.lower ? "s" : ""));
}

function renderGames(main) {
  if (main.querySelector(".arcade")) { renderGameSide(); fitScreen(); return; }
  main.textContent = "";
  const canvas = h("canvas", { id: "gameCanvas" });
  const idle = h("div", { class: "idle", id: "gameIdle" });
  const screen = h("div", { class: "screen", id: "gameScreen" }, canvas, idle);
  const status = h("div", { class: "status" },
    h("span", { class: "live", id: "gameLive" }),
    h("span", { class: "what", id: "gameWhat", text: "No game running" }),
    h("span", { class: "hint", id: "gameHint", text: "Keys go to the game while it runs. Esc leaves a game." }),
    h("button", { id: "gamePause", title: "Pause / resume (P)", text: "Pause", onclick: () => sendGame([{ key: "p" }]) }),
    h("button", { id: "gameAgain", title: "Start this game again", text: "Restart", onclick: () => startGame(arcade.game) }),
    h("button", { id: "gameStop", class: "ghost", title: "Stop the game", text: "Stop", onclick: stopGame }),
    h("button", { class: "ghost icon", title: "Full screen", onclick: () => screen.requestFullscreen?.() }, svgIcon("M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5")));
  main.append(h("div", { class: "arcade" }, h("aside", { class: "side", id: "gameSide" }), h("div", { class: "stage" }, screen, status)));
  canvas.addEventListener("mousedown", (event) => {
    if (!arcade.session) return;
    event.preventDefault();
    const at = cellAt(event);
    if (at) sendGame([{ click: { ...at, button: ["left", "middle", "right"][event.button] || "left" } }]);
  });
  canvas.addEventListener("mousemove", (event) => {
    if (!arcade.session) return;
    const at = cellAt(event);
    if (!at || at.y + ":" + at.x === arcade.hover) return;
    arcade.hover = at.y + ":" + at.x;
    sendGame([{ hover: at }]);
  });
  canvas.addEventListener("contextmenu", (event) => event.preventDefault());
  renderGameSide();
  updateGameStatus();
  fitScreen();
  if (!arcade.info) loadGames();
}

function svgIcon(path) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  const node = document.createElementNS("http://www.w3.org/2000/svg", "path");
  node.setAttribute("d", path);
  svg.append(node);
  return svg;
}

function renderGameSide() {
  const side = $("gameSide");
  if (!side) return;
  side.textContent = "";
  const info = arcade.info;
  if (info && !info.available) {
    side.append(h("div", { class: "empty", text: "Games are not installed in this ul. Turn on the `game` feature: ul features" }));
    return;
  }
  const level = arcade.level || "normal";
  side.append(h("h4", { text: "Difficulty" }), h("div", { class: "levels" }, ["easy", "normal", "hard"].map((name) =>
    h("button", { class: (name === level ? "on " : "") + name, text: name[0].toUpperCase() + name.slice(1), onclick: () => { arcade.level = name; localStorage.setItem("desk-level", name); renderGameSide(); } }))));
  side.append(h("h4", { text: "Games" }));
  for (const game of info ? info.games : []) {
    const best = bestText(game, level);
    side.append(h("button", { class: "tile" + (arcade.session && arcade.game === game.name ? " on" : ""), title: "Play " + game.label + " (" + level + ")", onclick: () => startGame(game.name) },
      h("b", { text: game.label }),
      h("span", { class: "best" + (best ? "" : " none"), text: best ? "best " + best : "no record" }),
      h("small", { text: GAME_INFO[game.name] || "" })));
  }
  side.append(h("button", { title: "The terminal arcade menu with every game", text: "Arcade menu", onclick: () => startGame(null) }));
  if (info) {
    side.append(h("h4", { text: "Records · shared with ul game" }));
    side.append(h("div", { class: "records" }, h("table", {},
      h("tr", {}, h("th", { text: "" }), h("th", { text: "Easy" }), h("th", { text: "Normal" }), h("th", { text: "Hard" })),
      info.games.map((game) => h("tr", {}, h("td", { text: game.label }), ["easy", "normal", "hard"].map((name) => h("td", { text: bestText(game, name) || "–" })))))));
  }
}

function updateGameStatus() {
  if (!$("gameWhat")) return;
  const running = Boolean(arcade.session);
  const label = arcade.game ? (arcade.info?.games.find((game) => game.name === arcade.game)?.label || arcade.game) + " · " + (arcade.level || "normal") : "Arcade menu";
  $("gameLive").classList.toggle("on", running);
  $("gameWhat").textContent = running ? label : "No game running";
  $("gamePause").disabled = !running;
  $("gameStop").disabled = !running;
  $("gameAgain").disabled = !running && !arcade.ended;
  const idle = $("gameIdle");
  idle.textContent = "";
  idle.style.display = running ? "none" : "flex";
  if (!running) {
    idle.append(h("b", { text: "ARCADE" }), h("span", { text: arcade.ended || "Pick a game on the left, or open the arcade menu." }));
    if (arcade.ended) idle.append(h("button", { class: "primary", text: "Play again", onclick: () => startGame(arcade.game) }));
  }
}

// The grid keeps every game playable (Expert Minesweeper needs 64x21) and fills the panel.
function fitScreen() {
  const screen = $("gameScreen"), canvas = $("gameCanvas");
  if (!screen || !canvas) return null;
  const width = screen.clientWidth - 16, height = screen.clientHeight - 16;
  if (width <= 0 || height <= 0) return null;
  const context = canvas.getContext("2d");
  context.font = "100px " + getComputedStyle(document.body).getPropertyValue("--mono");
  const ratio = context.measureText("M").width / 100;
  const lineHeight = 1.22;
  // 30 rows fill the height; the longest game hint (Tetris) needs 113 columns,
  // so a narrower panel trades font size for columns (never below 80).
  let rows = 30;
  let font = height / (rows * lineHeight);
  let cols = Math.floor(width / (font * ratio));
  if (cols < 116) {
    cols = Math.max(80, Math.min(116, Math.floor(width / (11 * ratio))));
    font = width / (cols * ratio);
    rows = Math.max(24, Math.floor(height / (font * lineHeight)));
  }
  cols = Math.min(cols, 200);
  rows = Math.min(rows, 80);
  arcade.cell = { w: font * ratio, h: font * lineHeight, font };
  const scale = window.devicePixelRatio || 1;
  canvas.width = Math.round(cols * arcade.cell.w * scale);
  canvas.height = Math.round(rows * arcade.cell.h * scale);
  canvas.style.width = cols * arcade.cell.w + "px";
  canvas.style.height = rows * arcade.cell.h + "px";
  const changed = rows !== arcade.grid.rows || cols !== arcade.grid.cols;
  arcade.grid = { rows, cols };
  if (changed && arcade.session) sendGame([{ resize: { rows, cols } }]);
  drawGame();
  return arcade.grid;
}

function cellAt(event) {
  const box = event.target.getBoundingClientRect();
  const x = Math.floor((event.clientX - box.left) / arcade.cell.w);
  const y = Math.floor((event.clientY - box.top) / arcade.cell.h);
  return x >= 0 && y >= 0 && x < arcade.grid.cols && y < arcade.grid.rows ? { y, x } : null;
}

function scheduleDraw() {
  if (arcade.drawPending) return;
  arcade.drawPending = true;
  requestAnimationFrame(() => { arcade.drawPending = false; drawGame(); });
}

// Box-drawing and block characters are painted as shapes so lines and blocks join without gaps.
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
  // Snap both edges: neighbours round the shared edge the same way, so no seams.
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
  // Quadrant blocks (chess pieces): each set quarter is a rectangle on the snapped grid.
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
  // Chess pieces (U+2654..265F) get the text-style selector: some fonts draw ♟ as a color emoji.
  const piece = char >= "\u2654" && char <= "\u265f";
  context.fillText(piece ? char + "\ufe0e" : char, x + w / 2, y + h / 2 + 1);
}

function drawGame() {
  const canvas = $("gameCanvas");
  if (!canvas) return;
  const context = canvas.getContext("2d");
  const scale = window.devicePixelRatio || 1;
  context.setTransform(scale, 0, 0, scale, 0, 0);
  context.fillStyle = SCREEN_BG;
  context.fillRect(0, 0, canvas.width, canvas.height);
  const frame = arcade.frame;
  if (!frame || !arcade.session) return;
  const { w, h: ch, font } = arcade.cell;
  const mono = getComputedStyle(document.body).getPropertyValue("--mono");
  context.textAlign = "center";
  context.textBaseline = "middle";
  frame.lines.forEach((runs, row) => {
    let column = 0;
    const y = row * ch;
    for (const [text, fgName, bgName, flags] of runs) {
      let fg = PALETTE[fgName] || SCREEN_FG, bg = PALETTE[bgName] || null;
      if (flags & 2) { const swap = fg; fg = bg || SCREEN_BG; bg = swap; }
      context.font = (flags & 1 ? "700 " : "400 ") + font + "px " + mono;
      context.globalAlpha = flags & 4 ? .55 : 1;
      const chars = [...text];
      if (bg) {
        const left = Math.round(column * w), top = Math.round(y);
        context.fillStyle = bg;
        context.fillRect(left, top, Math.round((column + chars.length) * w) - left, Math.round(y + ch) - top);
      }
      for (const char of chars) {
        if (char !== " ") drawCell(context, char, column * w, y, w, ch, fg);
        column += 1;
      }
    }
  });
  context.globalAlpha = 1;
}

function frameText() {
  return arcade.frame ? arcade.frame.lines.map((runs) => runs.map((run) => run[0]).join("")).join("\n") : "";
}

async function startGame(game) {
  if (arcade.info && !arcade.info.available) { toast("Games are not installed in this ul"); return; }
  if (state.view !== "games") setView("games");
  const grid = fitScreen() || arcade.grid;
  if (arcade.abort) arcade.abort.abort();
  const body = { game: game || null, rows: grid.rows, cols: grid.cols };
  if (game) body.level = arcade.level || "normal";
  const { status, data } = await api("POST", "/api/game/start", body);
  if (status !== 200) { toast(data.error || "Could not start the game"); return; }
  arcade.session = data.session;
  arcade.game = game;
  arcade.frame = null;
  arcade.queue = [];
  arcade.hover = "";
  arcade.ended = "";
  renderGameSide();
  updateGameStatus();
  streamGame(data.session);
}

async function streamGame(session) {
  const abort = new AbortController();
  arcade.abort = abort;
  try {
    const response = await fetch("/api/game/stream", { method: "POST", headers: { "X-Desk-Token": TOKEN, "Content-Type": "application/json" }, body: JSON.stringify({ session }), cache: "no-store", signal: abort.signal });
    if (!response.ok || !response.body) throw new Error("stream refused");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let at;
      while ((at = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, at).trim();
        buffer = buffer.slice(at + 1);
        if (!line) continue;
        const message = JSON.parse(line);
        if (message.end) continue;
        if (session === arcade.session) { arcade.frame = message; scheduleDraw(); }
      }
    }
  } catch (error) {
    if (abort.signal.aborted) return;
  }
  if (session === arcade.session) gameEnded("Game closed. Pick another one or play again.");
}

function gameEnded(message) {
  arcade.session = "";
  arcade.ended = message;
  arcade.frame = null;
  drawGame();
  updateGameStatus();
  loadGames();
}

async function sendGame(events) {
  if (!arcade.session) return;
  for (const event of events) {
    const last = arcade.queue[arcade.queue.length - 1];
    if (event.hover && last && last.hover) arcade.queue[arcade.queue.length - 1] = event;
    else arcade.queue.push(event);
  }
  if (arcade.sending) return;
  arcade.sending = true;
  while (arcade.queue.length && arcade.session) {
    const session = arcade.session;
    const batch = arcade.queue.splice(0, 64);
    const { status } = await api("POST", "/api/game/input", { session, events: batch });
    if (status === 410 && session === arcade.session) { arcade.queue = []; gameEnded("Game closed. Pick another one or play again."); }
  }
  arcade.sending = false;
}

async function stopGame() {
  const session = arcade.session;
  if (!session) return;
  if (arcade.abort) arcade.abort.abort();
  gameEnded("Stopped.");
  await api("POST", "/api/game/stop", { session });
}

// Leaving the tab or the window pauses a running game instead of losing it.
function pauseGame() {
  if (arcade.session && arcade.frame && !frameText().includes("PAUSED") && arcade.game) sendGame([{ key: "p" }]);
}

const GAME_KEYS = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Enter: "enter", Escape: "esc", Backspace: "backspace" };
function gameKey(event) {
  if (state.view !== "games" || !arcade.session || event.metaKey || event.ctrlKey || event.altKey) return false;
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) return false;
  const key = GAME_KEYS[event.key] || (event.key.length === 1 ? event.key : null);
  if (!key) return false;
  event.preventDefault();
  sendGame([{ key }]);
  return true;
}

// Key releases let two players hold keys at once (Ping Pong); games that did not ask ignore them.
document.addEventListener("keyup", (event) => {
  if (state.view !== "games" || !arcade.session || event.metaKey || event.ctrlKey || event.altKey) return;
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) return;
  const key = GAME_KEYS[event.key] || (event.key.length === 1 ? event.key : null);
  if (key) sendGame([{ release: key }]);
});

let resizeTimer = 0;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (state.view === "games") fitScreen(); }, 150); });
document.addEventListener("fullscreenchange", () => setTimeout(fitScreen, 60));

/*@STUDIO_JS@*/
// ---- boards ----
const REMINDERS = "reminders:";
let boardsDir = "";
// One flat menu that always opens below its button: a native <select> on macOS
// opens around the chosen item, so boards above it needed scrolling up.
const boardsMenu = { trigger: null, menu: null };

function boardLabel(path) {
  return { name: path.split("/").pop().replace(/\.md$/i, ""), where: path.split("/").slice(-2, -1)[0] || "" };
}

function boardItem(label, where, current, pick, kind) {
  return h("button", { type: "button", role: "menuitem", class: [kind, current ? "on" : ""].filter(Boolean).join(" ") || null, "aria-current": current ? "true" : null,
    onclick: () => { closeBoards(true); pick(); } },
    h("span", { class: "label", text: label }), where ? h("span", { class: "where", text: where }) : null);
}

function boardsOpen() { return Boolean(boardsMenu.menu && $("boards").classList.contains("open")); }

function openBoards() {
  $("boards").classList.add("open");
  boardsMenu.trigger.setAttribute("aria-expanded", "true");
  const items = [...boardsMenu.menu.querySelectorAll("button")];
  (items.find((item) => item.classList.contains("on")) || items[0])?.focus();
}

function closeBoards(refocus) {
  if (!boardsOpen()) return;
  $("boards").classList.remove("open");
  boardsMenu.trigger.setAttribute("aria-expanded", "false");
  if (refocus) boardsMenu.trigger.focus();
}

async function loadBoards() {
  const { status, data } = await api("GET", "/api/boards");
  if (status !== 200) return;
  boardsDir = data.boards_dir || "";
  const recent = (data.recent || []).length || data.current === REMINDERS ? data.recent || [] : [data.current].filter(Boolean);
  const paths = [...recent, ...(data.boards || []).filter((path) => !recent.includes(path))];
  const shown = data.current === REMINDERS ? { name: "Reminders" } : data.current ? boardLabel(data.current) : { name: "Boards" };
  const wasOpen = boardsOpen();
  const trigger = h("button", { type: "button", class: "trigger", title: "Boards", "aria-haspopup": "menu", "aria-expanded": "false",
    onclick: () => (boardsOpen() ? closeBoards(false) : openBoards()) }, h("span", { class: "name", text: shown.name }));
  const menu = h("div", { class: "menu", role: "menu" });
  if (data.reminders) menu.append(boardItem("Reminders", "Apple Reminders · lists as columns", data.current === REMINDERS, () => switchBoard(REMINDERS), "reminders"));
  for (const path of paths) {
    const label = boardLabel(path);
    menu.append(boardItem(label.name, label.where, path === data.current, () => switchBoard(path)));
  }
  menu.append(h("div", { class: "sep" }), boardItem("New board…", "", false, newBoard, "action"), boardItem("Open another board…", "", false, openOtherBoard, "action"));
  if (data.current && data.current !== REMINDERS) menu.append(boardItem("Delete this board…", shown.name + " goes to the Trash", false, () => deleteBoard(data.current, shown.name), "action danger"));
  const root = $("boards");
  root.textContent = "";
  root.append(trigger, menu);
  boardsMenu.trigger = trigger;
  boardsMenu.menu = menu;
  if (wasOpen) openBoards();
}

async function switchBoard(path, create) {
  const { status, data } = await api("POST", "/api/boards", { path, create: Boolean(create) });
  if (status === 200) { state.tag = ""; setBoard(data); loadBoards(); toast("Opened " + data.name); return; }
  if (status === 404 && data.missing && !create && (/\.md$/i.test(path) || !path.includes("/")) && confirm("No board at\n" + path + "\n\nCreate a new board there?")) return switchBoard(path, true);
  toast(data.error || "Could not open that board");
  loadBoards();
}

// New/Open show the macOS save/open dialog (through the server); without osascript the page asks for a name or path.
async function chooseBoard(create) {
  closeBoards(false);
  const { status, data } = await api("POST", "/api/boards/choose", { create });
  if (status !== 200) { toast(data.error || "Could not show the file dialog"); return null; }
  return data;
}

async function newBoard() {
  const data = await chooseBoard(true);
  if (!data) return;
  if (data.path) return switchBoard(data.path, true);
  if (!data.unavailable) return;
  const name = prompt("Name of the new board. It is saved in\n" + boardsDir + "\n(desk.boards_dir; a full path to a .md file works too)", "");
  if (name && name.trim()) switchBoard(name.trim(), true);
}

// The file goes to the Trash (the server refuses the default board); the next board opens.
async function deleteBoard(path, name) {
  closeBoards(false);
  if (!confirm("Move the board \"" + name + "\" to the Trash?\n\n" + path)) return;
  const { status, data } = await api("POST", "/api/boards/delete", { path });
  if (status !== 200) { toast(data.error || "Could not delete the board"); return; }
  state.tag = "";
  setBoard(data);
  loadBoards();
  toast("Moved " + name + " to the Trash");
}

async function openOtherBoard() {
  const data = await chooseBoard(false);
  if (!data) return;
  if (data.path) return switchBoard(data.path);
  if (!data.unavailable) return;
  const path = prompt("Path to a Kanban board (.md), or the name of a board in " + boardsDir + ". A missing file can be created.", "~/");
  if (path && path.trim()) switchBoard(path.trim());
}

$("boards").addEventListener("keydown", (event) => {
  if (!boardsOpen()) return;
  const items = [...boardsMenu.menu.querySelectorAll("button")];
  const at = items.indexOf(document.activeElement);
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    const step = event.key === "ArrowDown" ? 1 : -1;
    items[at < 0 ? (step > 0 ? 0 : items.length - 1) : (at + step + items.length) % items.length]?.focus();
  } else if (event.key === "Home" || event.key === "End") {
    event.preventDefault();
    items[event.key === "Home" ? 0 : items.length - 1]?.focus();
  } else if (event.key === "Escape" || event.key === "Tab") {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); }
    closeBoards(event.key === "Escape");
  }
});
document.addEventListener("pointerdown", (event) => {
  if (boardsOpen() && !$("boards").contains(event.target)) closeBoards(false);
});

async function openNote(name) {
  const { data } = await api("POST", "/api/obsidian", name ? { note: name } : {});
  if (!data.ok) toast(name ? "Note not found next to the board: " + name : "Could not open Obsidian");
}

// ---- pomodoro ----
async function loadTimer() {
  const { status, data } = await api("GET", "/api/pomodoro");
  if (status === 200) { state.timer = data; state.timerAt = Date.now(); drawTimer(); }
}

async function timer(action, card) {
  const body = { action };
  if (card !== undefined) body.card = card;
  const { status, data } = await api("POST", "/api/pomodoro", body);
  if (status !== 200) { toast(data.error || "Timer error"); return; }
  const linkedBefore = state.timer && state.timer.card;
  state.timer = data;
  state.timerAt = Date.now();
  drawTimer();
  if (card && card !== linkedBefore) toast("Focus: " + card);
  if (state.board && !["games", "studio", "canvas"].includes(state.view)) { todayStatsAt = 0; render(); }
}

function remaining() {
  const t = state.timer;
  if (!t) return 0;
  return t.running ? Math.max(0, t.remaining - (Date.now() - state.timerAt) / 1000) : t.remaining;
}

// A running clock counts whole seconds that have passed (format() rounds up for countdowns).
function clockText(seconds) {
  const s = Math.floor(Math.max(0, seconds));
  return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
}

function format(seconds) {
  const s = Math.ceil(seconds);
  return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
}

function drawTimer() {
  const t = state.timer;
  if (!t) return;
  const left = remaining();
  $("timer").className = "timer " + t.phase;
  $("phase").textContent = t.label + (t.phase === "work" ? " " + (t.cycle + 1) + "/" + t.cycles : "") + " · " + t.today + " today";
  $("clock").textContent = format(left);
  $("progress").style.width = (t.phase === "idle" ? 0 : (1 - left / t.length) * 100) + "%";
  $("linked").textContent = t.card ? "· " + t.card : "";
  $("linked").title = t.card || "";
  $("play").textContent = t.phase === "idle" ? "Start" : t.paused ? "Resume" : "Pause";
  $("skip").disabled = t.phase === "idle";
  $("stop").disabled = t.phase === "idle" && !t.card;
  const name = state.board ? state.board.name : "Desk";
  document.title = t.phase === "idle" ? name + " · Desk" : format(left) + " " + (t.phase === "work" ? "Focus" : "Break") + " · " + name;
  if (t.running && left <= 0 && Date.now() - state.timerAt > 900) loadTimer();
}

function togglePlay() {
  const t = state.timer;
  if (!t || t.phase === "idle") timer("start");
  else timer(t.paused ? "resume" : "pause");
}

$("play").addEventListener("click", togglePlay);
$("skip").addEventListener("click", () => timer("skip"));
$("stop").addEventListener("click", () => timer(state.timer && state.timer.phase === "idle" ? "unlink" : "stop"));
$("obsidian").addEventListener("click", () => openNote(""));
$("lofi").addEventListener("click", async () => { const { data } = await api("POST", "/api/lofi", {}); if (!data.ok) toast("Set apps.lofi_url to a web address"); });
$("filter").addEventListener("click", () => setTag(state.tag));
$("helpButton").addEventListener("click", () => $("help").classList.toggle("on"));
$("help").addEventListener("click", (event) => { if (event.target === $("help")) $("help").classList.remove("on"); });
for (const button of $("tabs").children) button.addEventListener("click", () => setView(button.dataset.view));

// ---- canvas: JSON Canvas cards and edges plus our own drawn elements ----
// The pure helpers (geometry, hit-testing, rough strokes, edits, history) come first so the tests can call them.
// Photoshop-style keys (letters by physical key, so they work in any layout): the first one is shown in tooltips,
// the rest are aliases; Shift+U cycles the shape tools like Photoshop's tool groups.
const CV_TOOLS = { select: "vm", hand: "h", card: "n", text: "t", thread: "k", rectangle: "ur", ellipse: "o", diamond: "", line: "l", arrow: "a", freedraw: "bp", fill: "g", eraser: "e" };
const CV_LABELS = { select: "Select", hand: "Hand", card: "Card", text: "Text", thread: "Thread", rectangle: "Rectangle", ellipse: "Ellipse", diamond: "Diamond", line: "Line", arrow: "Arrow", freedraw: "Brush", fill: "Fill", eraser: "Eraser" };
const CV_BY_KEY = Object.fromEntries(Object.entries(CV_TOOLS).flatMap(([tool, keys]) => [...keys].map((key) => [key, tool])));
const CV_SHAPE_CYCLE = ["rectangle", "ellipse", "diamond", "line", "arrow"];
// 24x24 outline icons (stroke = currentColor), built with createElementNS, never innerHTML.
const CV_ICONS = {
  select: "M5 3l6.5 17.5 2.6-7.4 7.4-2.6z",
  hand: "M8 12.5V5.5a1.5 1.5 0 0 1 3 0V11 M11 10.5v-6a1.5 1.5 0 0 1 3 0V11 M14 10.5V6.5a1.5 1.5 0 0 1 3 0V14a6 6 0 0 1-6 6h-.6a6 6 0 0 1-4.7-2.3L3.8 13.6a1.6 1.6 0 0 1 2.5-2L8 13.6",
  card: "M4 4h16v11l-5 5H4z M15 20v-5h5 M8 9h8 M8 12.5h5",
  text: "M5 7V4h14v3 M12 4v16 M9 20h6",
  thread: "M3.5 6.5a2 2 0 1 0 4 0a2 2 0 1 0-4 0 M16.5 17.5a2 2 0 1 0 4 0a2 2 0 1 0-4 0 M7 8c3 9 7 2 10 8",
  audio: "M9 18V5l12-2v13 M3 18a3 3 0 1 0 6 0a3 3 0 1 0-6 0 M15 16a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
  trash: "M4 7h16 M9 7V4h6v3 M6 7l1 13h10l1-13 M10 11v5 M14 11v5",
  gallery: "M4 4h7v7H4z M13 4h7v7h-7z M4 13h7v7H4z M13 13h7v7h-7z",
  close: "M6 6l12 12 M18 6L6 18",
  chevron: "M9 6l6 6-6 6",
  chevronDown: "M6 9l6 6 6-6",
  star: "M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.8L12 16.8l-5.2 2.8 1-5.8-4.3-4.1 5.9-.8z",
  back: "M15 18l-6-6 6-6",
  edit: "M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17z M14 7l3 3",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1 M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  layers: "M12 3l9 5-9 5-9-5z M3 12.5l9 5 9-5 M3 16.5l9 5 9-5",
  eye: "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z M9 12a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
  eyeOff: "M3 3l18 18 M10.6 5.1A10.6 10.6 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.1 3.9 M6.6 6.6A17 17 0 0 0 2 12s3.6 7 10 7a10 10 0 0 0 5.4-1.6 M9.9 9.9a3 3 0 0 0 4.2 4.2",
  rectangle: "M4 6h16v12H4z",
  ellipse: "M3 12a9 7 0 1 0 18 0a9 7 0 1 0-18 0",
  diamond: "M12 3l9 9-9 9-9-9z",
  line: "M5 19L19 5",
  arrow: "M5 19L19 5 M10 5h9v9",
  freedraw: "M4 20l4-1L19 8a2.1 2.1 0 0 0-3-3L5 16z M14 7l3 3",
  fill: "M11 3l8 8-7 7-8-8z M4 10h15 M20 15.5s1.8 2.2 1.8 3.2a1.8 1.8 0 0 1-3.6 0c0-1 1.8-3.2 1.8-3.2z",
  eraser: "M7 20h13 M3.8 15.8L13.5 6a2 2 0 0 1 2.9 0l2.6 2.6a2 2 0 0 1 0 2.9L11.5 19H7z M9 10.5l5.5 5.5",
  filled: "M4 6h16v12H4z M4 10l4-4 M4 15l9-9 M7 18l12-12 M13 18l7-7",
  undo: "M9 14L4 9l5-5 M4 9h10.5a5.5 5.5 0 0 1 0 11H11",
  redo: "M15 14l5-5-5-5 M20 9H9.5a5.5 5.5 0 0 0 0 11H13",
  group: "M3 7V3h4 M17 3h4v4 M21 17v4h-4 M7 21H3v-4 M8 8h8v8H8z",
  fit: "M4 9V4h5 M15 4h5v5 M20 15v5h-5 M9 20H4v-5",
  export: "M12 4v11 M7 10l5 5 5-5 M5 20h14",
  plus: "M12 5v14 M5 12h14",
  pin: "M9 3.5h6 M10 3.5l-.6 6L6.5 13h11l-2.9-3.5-.6-6 M12 13v8",
  attach: "M20.5 11.5l-8.4 8.4a5 5 0 0 1-7.1-7.1l8.4-8.4a3.3 3.3 0 0 1 4.7 4.7l-8.4 8.4a1.7 1.7 0 0 1-2.4-2.4l7.7-7.7",
  folder: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  erasePart: "M7 11a5 5 0 1 0 10 0a5 5 0 1 0-10 0 M3 20.5h18",
  rough3: "M5 5h14v14H5z",
  rough2: "M5 5.5c4.5-1 9 .8 14-.5 M19 5c-.9 4.6.8 9.2 0 14 M19.2 19c-4.8.8-9.4-1-14.2 0 M5 19c.8-4.6-.9-9.2 0-13.5",
  rough1: "M4.5 6c4-2.4 10 1.6 15-1.2 M18.6 4.2c-2 5.2 2.1 9.6-.3 15.3 M20 18.6c-5.3 2-10-1.8-15.6.4 M5.2 20c1.9-4.8-2.2-9.6.6-15.4",
};
const CV_INK = ["#1d1d1f", "#e5484d", "#f08c3a", "#e8b520", "#30a46c", "#3a6df0", "#8e4ec6", "#f2f2f5"];
const CV_MIN_WIDTH = 1, CV_MAX_WIDTH = 100;
// Evenness levels of the shape tools' menu: 3 is a perfect shape, 1 the roughest; the stored value is roughness.
const CV_ROUGH_LEVELS = [{ level: 3, rough: 0, label: "Perfect" }, { level: 2, rough: 1, label: "A little uneven" }, { level: 1, rough: 2, label: "More uneven" }];
const CV_ERASERS = [{ mode: "object", icon: "eraser", label: "Whole object" }, { mode: "part", icon: "erasePart", label: "Only where it passes" }];
const CV_FILL_TOLERANCE = 40;
const CV_PREFS = "desk-canvas-tools";
const CV_PRESETS = { "1": "#e5484d", "2": "#f08c3a", "3": "#e8b520", "4": "#30a46c", "5": "#2aa9bd", "6": "#8e4ec6" };
const CV_FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif';
const CV_MONO = '"SF Mono", ui-monospace, Menlo, monospace';
const CV_HAND = '"Bradley Hand", "Marker Felt", "Comic Sans MS", cursive';
const CV_MIN_ZOOM = 0.1, CV_MAX_ZOOM = 4, CV_HISTORY = 100, CV_MIN_BOX = 8;
const CV_SIDES = { top: [0, -1], right: [1, 0], bottom: [0, 1], left: [-1, 0] };
const CV_SIDE_NAMES = Object.keys(CV_SIDES);
const CV_SHAPES = new Set(["rectangle", "ellipse", "diamond", "line", "arrow", "freedraw", "text", "paint"]);
const CV_HEX = /^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/;

// Detective board look (unlaw.look = "cork"): cork, paper notes, photos and red thread between push pins.
const CV_CORK = { light: "#b8875a", dark: "#5e4128" };
const CV_PAPER = "#fff1a6";
const CV_THREAD = "#c1121f";
const CV_PINS = ["#d62828", "#1d6fd8", "#2b9348", "#f4a300", "#7b2cbf", "#e5e5e5"];
const CV_IMAGE_FILE = /\.(png|jpe?g|gif|webp|ico)$/i;
const CV_CANVAS_FILE = /\.canvas$/i;
// Quick Look draws plain text as dark text on a dark page when macOS is in dark mode: these stay a paper sheet.
const CV_PLAIN_FILE = /\.(txt|text|log|csv|tsv|json|jsonl|ya?ml|toml|ini|cfg|conf|xml|html?|css|js|mjs|cjs|ts|tsx|jsx|py|rs|c|h|cc|cpp|hpp|m|swift|go|java|kt|rb|php|sh|zsh|bash|fish|sql|lua|r|jl|tex|srt|vtt)$/i;
const CV_MAX_UPLOAD = 256 * 1024 * 1024;
const CV_PLAYED = "#f5a524";
const cvNum = (value, fallback) => (typeof value === "number" && Number.isFinite(value) ? value : fallback);
const cvClone = (value) => JSON.parse(JSON.stringify(value));
const cvId = () => Array.from({ length: 16 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
const cvSeed = () => Math.floor(Math.random() * 2147483647);
const cvBackground = (doc) => (doc && doc.unlaw && typeof doc.unlaw.background === "string" && CV_HEX.test(doc.unlaw.background) ? doc.unlaw.background : null);

function nodeColor(color) {
  if (typeof color !== "string") return null;
  if (Object.prototype.hasOwnProperty.call(CV_PRESETS, color)) return CV_PRESETS[color];
  return CV_HEX.test(color) ? color : null;
}

function luminance(color) {
  if (typeof color !== "string" || !CV_HEX.test(color)) return null;
  let hex = color.slice(1);
  if (hex.length === 3) hex = hex.split("").map((c) => c + c).join("");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// Stored ink never changes with the theme; only what is painted does, so near-black stays visible on dark.
function adaptInk(color, dark) {
  const light = luminance(color);
  if (light === null) return dark ? "#ececee" : "#1d1d1f";
  if (dark && light < 0.18) return "#ececee";
  if (!dark && light > 0.88) return "#1d1d1f";
  return color;
}

function noteName(file) {
  return typeof file === "string" && /\.md$/i.test(file) ? file.split("/").pop().replace(/\.md$/i, "") : null;
}

// Small seeded PRNG (mulberry32): the same seed always draws the same wobble.
function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---- detective board geometry: a tilt per card from its id, one pin per card, thread from pin to pin ----
const cvCork = (doc) => Boolean(doc && doc.unlaw && typeof doc.unlaw === "object" && doc.unlaw.look === "cork");
function setLook(doc, cork) {
  if (cvCork(doc) === cork) return false;
  if (cork) { ensureElements(doc); doc.unlaw.look = "cork"; } else delete doc.unlaw.look;
  return true;
}
// FNV-1a of the id as 0..1, so a card keeps its tilt and pin color on every redraw and machine.
function idHash(id, salt) {
  let h = 0x811c9dc5;
  for (const ch of String(salt || "") + String(id)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0;
  return h / 4294967296;
}
const nodeTilt = (node) => (node.type === "group" ? 0 : (idHash(node.id) * 2 - 1) * 0.045);
const pinColor = (node) => CV_PINS[Math.floor(idHash(node.id, "pin") * CV_PINS.length)];
// A point of a card given as fractions of its unrotated box ([0.5, 0.5] = the middle), turned with the card's
// tilt on the detective board, so a pin stays on the same spot of the paper.
function anchorPoint(node, frac, tilted) {
  const tilt = tilted ? nodeTilt(node) : 0, dx = (frac[0] - 0.5) * node.width, dy = (frac[1] - 0.5) * node.height;
  return { x: node.x + node.width / 2 + Math.cos(tilt) * dx - Math.sin(tilt) * dy, y: node.y + node.height / 2 + Math.sin(tilt) * dx + Math.cos(tilt) * dy };
}
// The inverse of anchorPoint, clamped to the card.
function fracAt(node, w, tilted) {
  const tilt = tilted ? nodeTilt(node) : 0, x = w.x - (node.x + node.width / 2), y = w.y - (node.y + node.height / 2);
  const lx = Math.cos(tilt) * x + Math.sin(tilt) * y, ly = -Math.sin(tilt) * x + Math.cos(tilt) * y;
  const part = (v, size) => Math.round(Math.max(0, Math.min(1, v / (size || 1) + 0.5)) * 10000) / 10000;
  return [part(lx, node.width), part(ly, node.height)];
}
// An edge end tied to a spot of its card (the thread tool or a dragged end): unlawFrom/unlawTo, [fx, fy] in 0..1.
// Obsidian does not know the keys and keeps using fromSide/toSide, which are set to the nearest side.
function edgeAnchor(edge, end) {
  const value = edge && edge[end === "to" ? "unlawTo" : "unlawFrom"];
  return Array.isArray(value) && value.length === 2 && value.every((n) => Number.isFinite(n) && n >= 0 && n <= 1) ? value : null;
}
function pinPoint(node, frac) {
  if (frac) return anchorPoint(node, frac, true);
  const tilt = nodeTilt(node), dy = -node.height / 2 + Math.min(14, node.height / 4);
  return { x: node.x + node.width / 2 - Math.sin(tilt) * dy, y: node.y + node.height / 2 + Math.cos(tilt) * dy };
}
// The thread hangs: a quadratic sag written as a cubic, so hit-testing and labels use the edge code as is.
function threadCurve(a, b, fa, fb) {
  return sagCurve(pinPoint(a, fa), pinPoint(b, fb));
}
function sagCurve(p0, p3) {
  const length = Math.hypot(p3.x - p0.x, p3.y - p0.y);
  const q = { x: (p0.x + p3.x) / 2, y: (p0.y + p3.y) / 2 + Math.min(90, 10 + length * 0.12) };
  return { p0, c1: { x: p0.x + (2 / 3) * (q.x - p0.x), y: p0.y + (2 / 3) * (q.y - p0.y) }, c2: { x: p3.x + (2 / 3) * (q.x - p3.x), y: p3.y + (2 / 3) * (q.y - p3.y) }, p3 };
}
function mixColor(color, other, amount) {
  const parse = (c) => { let hex = c.slice(1); if (hex.length === 3) hex = hex.split("").map((x) => x + x).join(""); return [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16)); };
  if (!CV_HEX.test(color) || !CV_HEX.test(other)) return color;
  const a = parse(color), b = parse(other);
  return "#" + a.map((v, i) => Math.round(v + (b[i] - v) * amount).toString(16).padStart(2, "0")).join("");
}
const fileExtension = (file) => { const m = /\.([A-Za-z0-9]{1,8})$/.exec(String(file || "")); return m ? m[1].toUpperCase() : "FILE"; };
// A new file card: photos keep their proportions (a frame of 10 px and a 40 px caption around them).
function fileCardSize(image) {
  if (!image || !(image.w > 0) || !(image.h > 0)) return { width: 220, height: 280 };
  const width = 280, photo = Math.max(100, Math.min(460, ((width - 20) * image.h) / image.w));
  return { width, height: Math.round(photo + 50) };
}

// ---- view transforms: screen = world * z + (x, y) ----
const toScreen = (view, x, y) => ({ x: x * view.z + view.x, y: y * view.z + view.y });
const toWorld = (view, x, y) => ({ x: (x - view.x) / view.z, y: (y - view.y) / view.z });
const clampZoom = (z) => Math.min(CV_MAX_ZOOM, Math.max(CV_MIN_ZOOM, z));

function zoomAt(view, sx, sy, factor) {
  const z = clampZoom(view.z * factor);
  const k = z / view.z;
  return { x: sx - (sx - view.x) * k, y: sy - (sy - view.y) * k, z };
}

function fitView(bounds, width, height, pad = 60) {
  if (!bounds) return { x: width / 2, y: height / 2, z: 1 };
  const z = Math.min(1.5, clampZoom(Math.min((width - 2 * pad) / Math.max(1, bounds.width), (height - 2 * pad) / Math.max(1, bounds.height))));
  return { x: width / 2 - (bounds.x + bounds.width / 2) * z, y: height / 2 - (bounds.y + bounds.height / 2) * z, z };
}

// ---- boxes and distances ----
function normRect(x0, y0, x1, y1) {
  return { x: Math.min(x0, x1), y: Math.min(y0, y1), width: Math.abs(x1 - x0), height: Math.abs(y1 - y0) };
}
function rectsIntersect(a, b) {
  return a.x <= b.x + b.width && b.x <= a.x + a.width && a.y <= b.y + b.height && b.y <= a.y + a.height;
}
function boxContains(box, x, y, pad = 0) {
  return x >= box.x - pad && x <= box.x + box.width + pad && y >= box.y - pad && y <= box.y + box.height + pad;
}
function boxInside(inner, outer) {
  return inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.width <= outer.x + outer.width && inner.y + inner.height <= outer.y + outer.height;
}
function unionBox(boxes) {
  if (!boxes.length) return null;
  const x0 = Math.min(...boxes.map((b) => b.x)), y0 = Math.min(...boxes.map((b) => b.y));
  const x1 = Math.max(...boxes.map((b) => b.x + b.width)), y1 = Math.max(...boxes.map((b) => b.y + b.height));
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}
function segDist(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay, len = dx * dx + dy * dy;
  const t = len ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len)) : 0;
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}
function polyDist(pts, x, y, closed) {
  if (!pts.length) return Infinity;
  if (pts.length === 1) return Math.hypot(x - pts[0][0], y - pts[0][1]);
  let best = Infinity;
  const count = closed ? pts.length : pts.length - 1;
  for (let i = 0; i < count; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    best = Math.min(best, segDist(x, y, a[0], a[1], b[0], b[1]));
  }
  return best;
}
function pointInPoly(pts, x, y) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

// ---- document access: lists are read defensively, but the raw objects are what gets saved ----
function cvList(doc, kind) {
  const list = kind === "n" ? doc.nodes : kind === "e" ? doc.edges : doc.unlaw && doc.unlaw.elements;
  return Array.isArray(list) ? list : [];
}
function cvLookup(doc, key) {
  const id = key.slice(2);
  return cvList(doc, key[0]).find((item) => item && item.id === id) || null;
}
const cvKey = (kind, item) => kind + ":" + item.id;
function validBox(item) {
  return Boolean(item) && typeof item === "object" && typeof item.id === "string" && Number.isFinite(item.x) && Number.isFinite(item.y) && Number.isFinite(item.width) && Number.isFinite(item.height);
}
// unlawHidden (the eye in Layers) takes a card, group or drawing out of painting and picking; `all` keeps them.
const cvHidden = (item) => Boolean(item && item.unlawHidden === true);
const docNodes = (doc, all) => cvList(doc, "n").filter((n) => validBox(n) && (all || !cvHidden(n)));
const docElements = (doc, all) => cvList(doc, "x").filter((el) => validBox(el) && CV_SHAPES.has(el.type) && (all || !cvHidden(el)));
const docEdges = (doc) => cvList(doc, "e").filter((e) => e && typeof e === "object" && typeof e.id === "string" && typeof e.fromNode === "string" && typeof e.toNode === "string");
function ensureList(doc, name) {
  if (!Array.isArray(doc[name])) doc[name] = [];
  return doc[name];
}
function ensureElements(doc) {
  if (!doc.unlaw || typeof doc.unlaw !== "object" || Array.isArray(doc.unlaw)) doc.unlaw = {};
  if (doc.unlaw.version === undefined) doc.unlaw.version = 1;
  return ensureList(doc.unlaw, "elements");
}
function sceneBounds(doc) {
  const boxes = [...docNodes(doc), ...docElements(doc)].map((item) => {
    const pad = (cvNum(item.strokeWidth, 0) || 0) / 2;
    const lift = item.type === "group" ? 28 : 0;
    return { x: item.x - pad, y: item.y - pad - lift, width: item.width + 2 * pad, height: item.height + 2 * pad + lift };
  });
  return unionBox(boxes);
}

// ---- elements: outline, hit-test, rough strokes ----
function elementPoints(el) {
  if (!Array.isArray(el.points)) return [];
  return el.points.filter((p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1])).map((p) => [el.x + p[0], el.y + p[1]]);
}

function elementOutline(el) {
  const { x, y, width, height } = el;
  if (el.type === "diamond") return [[x + width / 2, y], [x + width, y + height / 2], [x + width / 2, y + height], [x, y + height / 2]];
  if (el.type === "ellipse") {
    const out = [];
    for (let i = 0; i < 48; i++) {
      const a = (i / 48) * Math.PI * 2;
      out.push([x + width / 2 + (width / 2) * Math.cos(a), y + height / 2 + (height / 2) * Math.sin(a)]);
    }
    return out;
  }
  return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]];
}

// A world point in the element's own unrotated frame.
function localPoint(el, x, y) {
  if (!el.angle) return { x, y };
  const cx = el.x + el.width / 2, cy = el.y + el.height / 2, cos = Math.cos(-el.angle), sin = Math.sin(-el.angle);
  const dx = x - cx, dy = y - cy;
  return { x: cx + dx * cos - dy * sin, y: cy + dx * sin + dy * cos };
}

// Shapes and pen strokes that end near their start enclose an area the fill tool can paint.
function fillable(el) {
  if (el.type === "rectangle" || el.type === "ellipse" || el.type === "diamond") return true;
  if (el.type !== "freedraw") return false;
  const pts = elementPoints(el);
  if (pts.length < 3) return false;
  const [a, b] = [pts[0], pts[pts.length - 1]];
  return Math.hypot(b[0] - a[0], b[1] - a[1]) <= Math.max(12, 0.25 * Math.max(el.width, el.height));
}
const fillOutline = (el) => (el.type === "freedraw" ? elementPoints(el) : elementOutline(el));

// A paint element is an area left by the fill tool: an outer ring plus holes, filled even-odd.
function paintRings(el) {
  const rel = (ring) => (Array.isArray(ring) ? ring.filter((p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1])).map((p) => [el.x + p[0], el.y + p[1]]) : []);
  return [rel(el.points), ...(Array.isArray(el.holes) ? el.holes.map(rel) : [])].filter((ring) => ring.length >= 3);
}
function paintContains(el, x, y) {
  let inside = false;
  for (const ring of paintRings(el)) if (pointInPoly(ring, x, y)) inside = !inside;
  return inside;
}

function hitElement(el, x, y, tol) {
  ({ x, y } = localPoint(el, x, y));
  if (el.type === "text") return boxContains(el, x, y, tol);
  if (el.type === "paint") return paintContains(el, x, y);
  const reach = tol + cvNum(el.strokeWidth, 2) / 2;
  if (el.fill && fillable(el) && pointInPoly(fillOutline(el), x, y)) return true;
  if (el.type === "line" || el.type === "arrow" || el.type === "freedraw") return polyDist(elementPoints(el), x, y, false) <= reach;
  return polyDist(elementOutline(el), x, y, true) <= reach;
}

function hitGroup(node, x, y, tol) {
  if (boxContains({ x: node.x, y: node.y - 26, width: Math.min(node.width, 220), height: 26 }, x, y)) return true;
  const roomy = node.width > 2 * tol && node.height > 2 * tol;
  return boxContains(node, x, y, tol) && !(roomy && boxContains(node, x, y, -tol));
}

// ---- edges: a cubic curve leaving each node through a side ----
function sideAnchor(box, side) {
  if (side === "top") return { x: box.x + box.width / 2, y: box.y };
  if (side === "bottom") return { x: box.x + box.width / 2, y: box.y + box.height };
  if (side === "left") return { x: box.x, y: box.y + box.height / 2 };
  return { x: box.x + box.width, y: box.y + box.height / 2 };
}
function nearestSide(box, x, y) {
  const dx = (x - (box.x + box.width / 2)) / (box.width / 2 || 1), dy = (y - (box.y + box.height / 2)) / (box.height / 2 || 1);
  if (Math.abs(dx) > Math.abs(dy)) return dx > 0 ? "right" : "left";
  return dy > 0 ? "bottom" : "top";
}
function edgeCurve(a, sideA, b, sideB, p0 = sideAnchor(a, sideA), p3 = sideAnchor(b, sideB)) {
  const reach = Math.max(40, Math.min(200, Math.hypot(p3.x - p0.x, p3.y - p0.y) / 2));
  const v0 = CV_SIDES[sideA], v1 = CV_SIDES[sideB];
  return { p0, c1: { x: p0.x + v0[0] * reach, y: p0.y + v0[1] * reach }, c2: { x: p3.x + v1[0] * reach, y: p3.y + v1[1] * reach }, p3 };
}
function bezierPoint(c, t) {
  const u = 1 - t;
  const f = (a, b, d, e) => u * u * u * a + 3 * u * u * t * b + 3 * u * t * t * d + t * t * t * e;
  return { x: f(c.p0.x, c.c1.x, c.c2.x, c.p3.x), y: f(c.p0.y, c.c1.y, c.c2.y, c.p3.y) };
}
function hitEdge(curve, x, y, tol) {
  const pts = [];
  for (let i = 0; i <= 32; i++) { const p = bezierPoint(curve, i / 32); pts.push([p.x, p.y]); }
  return polyDist(pts, x, y, false) <= tol + 1;
}
function edgeCurveFor(map, edge, cork) {
  const a = map.get(edge.fromNode), b = map.get(edge.toNode);
  if (!a || !b) return null;
  const fa = edgeAnchor(edge, "from"), fb = edgeAnchor(edge, "to");
  if (cork) return threadCurve(a, b, fa, fb);
  const ca = { x: a.x + a.width / 2, y: a.y + a.height / 2 }, cb = { x: b.x + b.width / 2, y: b.y + b.height / 2 };
  const p0 = fa ? anchorPoint(a, fa, false) : undefined, p3 = fb ? anchorPoint(b, fb, false) : undefined;
  const from = p0 ? nearestSide(a, p0.x, p0.y) : CV_SIDE_NAMES.includes(edge.fromSide) ? edge.fromSide : nearestSide(a, cb.x, cb.y);
  const to = p3 ? nearestSide(b, p3.x, p3.y) : CV_SIDE_NAMES.includes(edge.toSide) ? edge.toSide : nearestSide(b, ca.x, ca.y);
  return edgeCurve(a, from, b, to, p0, p3);
}
const nodeMap = (doc) => new Map(docNodes(doc).map((n) => [n.id, n]));

// Topmost thing at a world point: drawings, cards, edges, then groups (only their label and border).
function hitTest(doc, x, y, zoom) {
  const tol = 6 / (zoom || 1);
  const elements = docElements(doc), nodes = docNodes(doc);
  for (let i = elements.length - 1; i >= 0; i--) if (hitElement(elements[i], x, y, tol)) return cvKey("x", elements[i]);
  for (let i = nodes.length - 1; i >= 0; i--) if (nodes[i].type !== "group" && boxContains(nodes[i], x, y)) return cvKey("n", nodes[i]);
  const map = nodeMap(doc);
  for (const edge of docEdges(doc).reverse()) {
    const curve = edgeCurveFor(map, edge, cvCork(doc));
    if (curve && hitEdge(curve, x, y, tol)) return cvKey("e", edge);
  }
  for (let i = nodes.length - 1; i >= 0; i--) if (nodes[i].type === "group" && hitGroup(nodes[i], x, y, tol)) return cvKey("n", nodes[i]);
  return null;
}

// What the fill tool paints at a world point: like hitTest, but the inside of an unfilled closed shape counts
// (after any drawing seen through it) and a click anywhere in a group colors the group. null = the empty background.
function fillTarget(doc, x, y, zoom) {
  const tol = 6 / (zoom || 1);
  const elements = docElements(doc), nodes = docNodes(doc);
  let hollow = null;
  for (let i = elements.length - 1; i >= 0; i--) {
    const el = elements[i], local = localPoint(el, x, y);
    if (hitElement(el, x, y, tol)) return cvKey("x", el);
    if (!hollow && fillable(el) && pointInPoly(fillOutline(el), local.x, local.y)) hollow = cvKey("x", el);
  }
  if (hollow) return hollow;
  for (let i = nodes.length - 1; i >= 0; i--) if (nodes[i].type !== "group" && boxContains(nodes[i], x, y)) return cvKey("n", nodes[i]);
  const map = nodeMap(doc);
  for (const edge of docEdges(doc).reverse()) {
    const curve = edgeCurveFor(map, edge, cvCork(doc));
    if (curve && hitEdge(curve, x, y, tol)) return cvKey("e", edge);
  }
  for (let i = nodes.length - 1; i >= 0; i--) if (nodes[i].type === "group" && (boxContains(nodes[i], x, y) || hitGroup(nodes[i], x, y, tol))) return cvKey("n", nodes[i]);
  return null;
}

// The fill tool: enclosed areas get a fill, cards, groups and edges a color, open strokes and text a new ink.
// color null clears a fill or a card color (open strokes keep their ink). Returns whether anything changed.
function applyFill(doc, key, color) {
  const item = cvLookup(doc, key);
  if (!item) return false;
  if (key[0] === "x") {
    if (item.type === "paint") {
      if (color === null) return removeItems(doc, [key]) > 0;
      if (item.fill === color && item.stroke === color) return false;
      item.fill = color;
      item.stroke = color;
      return true;
    }
    if (fillable(item)) {
      if ((item.fill || null) === color) return false;
      item.fill = color;
    } else {
      if (color === null || item.stroke === color) return false;
      item.stroke = color;
    }
    return true;
  }
  if (color === null) {
    if (!("color" in item)) return false;
    delete item.color;
    return true;
  }
  if (item.color === color) return false;
  item.color = color;
  return true;
}

function setBackground(doc, color) {
  if (cvBackground(doc) === color) return false;
  if (color === null) {
    if (!doc.unlaw || typeof doc.unlaw !== "object") return false;
    delete doc.unlaw.background;
    return true;
  }
  ensureElements(doc);
  doc.unlaw.background = color;
  return true;
}

// Two slightly different passes per shape, wobble drawn from the element's own seed.
function roughLine(rng, a, b, rough) {
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const amp = rough * Math.min(2.2, 0.6 + len / 150);
  const jitter = () => (rng() - 0.5) * 2 * amp;
  const nx = len ? -(b[1] - a[1]) / len : 0, ny = len ? (b[0] - a[0]) / len : 0;
  const bow = jitter();
  return [
    [a[0] + jitter(), a[1] + jitter()],
    [(a[0] + b[0]) / 2 + nx * bow + jitter() * 0.4, (a[1] + b[1]) / 2 + ny * bow + jitter() * 0.4],
    [b[0] + jitter(), b[1] + jitter()],
  ];
}

function roughStrokes(el) {
  if (!CV_SHAPES.has(el.type) || el.type === "text" || el.type === "paint") return [];
  const rough = Math.max(0, Math.min(2, cvNum(el.roughness, 1)));
  const rng = mulberry32(cvNum(el.seed, 1));
  const passes = rough > 0 ? 2 : 1;
  const out = [];
  if (el.type === "freedraw") {
    const pts = elementPoints(el);
    return pts.length ? [{ pts, smooth: true }] : [];
  }
  if (el.type === "line" || el.type === "arrow") {
    const pts = elementPoints(el);
    if (pts.length < 2) return pts.length ? [{ pts, smooth: false }] : [];
    for (let pass = 0; pass < passes; pass++) {
      if (!rough) { out.push({ pts, smooth: false }); continue; }
      const stroke = [];
      for (let i = 0; i < pts.length - 1; i++) {
        const seg = roughLine(rng, pts[i], pts[i + 1], rough);
        stroke.push(...(i ? seg.slice(1) : seg));
      }
      out.push({ pts: stroke, smooth: true });
    }
    return out;
  }
  const outline = elementOutline(el);
  for (let pass = 0; pass < passes; pass++) {
    if (!rough) { out.push({ pts: [...outline, outline[0]], smooth: false }); continue; }
    if (el.type === "ellipse") {
      const amp = rough * Math.min(2.2, 0.6 + (el.width + el.height) / 300), start = rng() * Math.PI * 2, steps = 40;
      const pts = [];
      for (let i = 0; i <= steps; i++) {
        const a = start + (i / steps) * Math.PI * 2;
        pts.push([el.x + el.width / 2 + (el.width / 2 + (rng() - 0.5) * 2 * amp) * Math.cos(a), el.y + el.height / 2 + (el.height / 2 + (rng() - 0.5) * 2 * amp) * Math.sin(a)]);
      }
      out.push({ pts, smooth: true });
      continue;
    }
    for (let i = 0; i < outline.length; i++) out.push({ pts: roughLine(rng, outline[i], outline[(i + 1) % outline.length], rough), smooth: true });
  }
  return out;
}

function arrowHead(from, to, size) {
  const angle = Math.atan2(to[1] - from[1], to[0] - from[0]);
  return [-0.45, 0.45].map((turn) => [to[0] - size * Math.cos(angle + turn), to[1] - size * Math.sin(angle + turn)]);
}

// ---- fill tool: flood the clicked color on a rendered snapshot, keep the area as a paint element ----
// Pixels connected (4-way) to (sx, sy) whose RGBA stays within tol of it; touches = the area reaches the image edge.
function floodRegion(data, w, h, sx, sy, tol) {
  const mask = new Uint8Array(w * h), start = sy * w + sx, k0 = start * 4;
  const r0 = data[k0], g0 = data[k0 + 1], b0 = data[k0 + 2], a0 = data[k0 + 3];
  const same = (i) => {
    const k = i * 4;
    return Math.abs(data[k] - r0) <= tol && Math.abs(data[k + 1] - g0) <= tol && Math.abs(data[k + 2] - b0) <= tol && Math.abs(data[k + 3] - a0) <= tol;
  };
  const stack = [start];
  mask[start] = 1;
  let touches = false, count = 0;
  while (stack.length) {
    const i = stack.pop(), x = i % w, y = (i - x) / w;
    count++;
    if (x === 0 || y === 0 || x === w - 1 || y === h - 1) touches = true;
    if (x > 0 && !mask[i - 1] && same(i - 1)) { mask[i - 1] = 1; stack.push(i - 1); }
    if (x < w - 1 && !mask[i + 1] && same(i + 1)) { mask[i + 1] = 1; stack.push(i + 1); }
    if (y > 0 && !mask[i - w] && same(i - w)) { mask[i - w] = 1; stack.push(i - w); }
    if (y < h - 1 && !mask[i + w] && same(i + w)) { mask[i + w] = 1; stack.push(i + w); }
  }
  return { mask, touches, count };
}

// One pixel wider on every side, so the area slips under antialiased edges instead of leaving a light seam.
function growMask(mask, w, h) {
  const out = new Uint8Array(mask);
  for (let i = 0; i < mask.length; i++) {
    if (!mask[i]) continue;
    const x = i % w;
    if (x > 0) out[i - 1] = 1;
    if (x < w - 1) out[i + 1] = 1;
    if (i >= w) out[i - w] = 1;
    if (i < mask.length - w) out[i + w] = 1;
  }
  return out;
}

// Closed rings of pixel corners around a mask (outer border and holes). Where two pixels touch only at a corner
// the walk turns right, around the pixel it came along. Even-odd filling only needs the set of edges anyway.
function traceMask(mask, w, h) {
  const W = w + 1, next = new Map();
  const add = (x0, y0, x1, y1) => {
    const key = y0 * W + x0;
    if (!next.has(key)) next.set(key, []);
    next.get(key).push([x1, y1]);
  };
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      if (!mask[i]) continue;
      if (y === 0 || !mask[i - w]) add(x, y, x + 1, y);
      if (x === w - 1 || !mask[i + 1]) add(x + 1, y, x + 1, y + 1);
      if (y === h - 1 || !mask[i + w]) add(x + 1, y + 1, x, y + 1);
      if (x === 0 || !mask[i - 1]) add(x, y + 1, x, y);
    }
  }
  const rings = [];
  for (const [key, list] of next) {
    while (list.length) {
      const sx = key % W, sy = (key - sx) / W, ring = [[sx, sy]];
      let px = sx, py = sy, [cx, cy] = list.pop();
      while (cx !== sx || cy !== sy) {
        ring.push([cx, cy]);
        const out = next.get(cy * W + cx);
        if (!out || !out.length) break;
        let pick = 0;
        if (out.length > 1) {
          const dx = cx - px, dy = cy - py;
          pick = Math.max(0, out.findIndex(([nx, ny]) => dx * (ny - cy) - dy * (nx - cx) > 0));
        }
        const [nx, ny] = out.splice(pick, 1)[0];
        px = cx; py = cy; cx = nx; cy = ny;
      }
      rings.push(ring);
    }
  }
  return rings;
}

function ringArea(ring) {
  let sum = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) sum += (ring[j][0] + ring[i][0]) * (ring[j][1] - ring[i][1]);
  return Math.abs(sum) / 2;
}

// Douglas-Peucker on a closed ring: the pixel staircase becomes straight and diagonal runs.
function simplifyRing(ring, eps) {
  const n = ring.length;
  const pts = ring.filter((p, i) => {
    const a = ring[(i - 1 + n) % n], b = ring[(i + 1) % n];
    return (p[0] - a[0]) * (b[1] - p[1]) - (p[1] - a[1]) * (b[0] - p[0]) !== 0;
  });
  if (pts.length < 4) return pts;
  let far = 0, best = -1;
  pts.forEach((p, i) => { const d = Math.hypot(p[0] - pts[0][0], p[1] - pts[0][1]); if (d > best) { best = d; far = i; } });
  const rdp = (line) => {
    const keep = new Uint8Array(line.length);
    keep[0] = keep[line.length - 1] = 1;
    const stack = [[0, line.length - 1]];
    while (stack.length) {
      const [a, b] = stack.pop();
      let index = -1, dist = eps;
      for (let i = a + 1; i < b; i++) {
        const d = segDist(line[i][0], line[i][1], line[a][0], line[a][1], line[b][0], line[b][1]);
        if (d > dist) { dist = d; index = i; }
      }
      if (index >= 0) { keep[index] = 1; stack.push([a, index], [index, b]); }
    }
    return line.filter((_, i) => keep[i]);
  };
  return [...rdp(pts.slice(0, far + 1)).slice(0, -1), ...rdp([...pts.slice(far), pts[0]]).slice(0, -1)];
}

// The flooded area as a paint element in world units: rings from a snapshot drawn at view with scale k.
function paintFromMask(mask, w, h, view, k, color) {
  const traced = traceMask(mask, w, h);
  let rings = [];
  for (let eps = 0.8; eps <= 13; eps *= 2) {
    rings = traced.map((ring) => simplifyRing(ring, eps)).filter((ring) => ring.length >= 3 && ringArea(ring) >= 2);
    if (rings.reduce((sum, ring) => sum + ring.length, 0) <= 40000) break;
  }
  if (!rings.length) return null;
  const round = (v) => Math.round(v * 100) / 100;
  const world = rings.map((ring) => ring.map(([px, py]) => { const p = toWorld(view, px / k, py / k); return [p.x, p.y]; }));
  world.sort((a, b) => ringArea(b) - ringArea(a));
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const ring of world) for (const [x, y] of ring) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  const rel = (ring) => ring.map(([x, y]) => [round(x - x0), round(y - y0)]);
  return { id: cvId(), type: "paint", x: round(x0), y: round(y0), width: round(x1 - x0), height: round(y1 - y0), points: rel(world[0]), holes: world.slice(1).map(rel), stroke: color, fill: color, strokeWidth: 1 };
}

// Whether a world point lies on an element's ink (its line or text), not inside its area.
function onInk(el, x, y, tol) {
  ({ x, y } = localPoint(el, x, y));
  if (el.type === "text") return boxContains(el, x, y, tol);
  if (el.type === "paint") return false;
  const reach = tol + cvNum(el.strokeWidth, 2) / 2;
  if (el.type === "line" || el.type === "arrow" || el.type === "freedraw") return polyDist(elementPoints(el), x, y, false) <= reach;
  return polyDist(elementOutline(el), x, y, true) <= reach;
}

// ---- partial eraser: cut drawn lines where a round eraser passes ----
// The element's drawn strokes in world units (rotation applied); a rough shape keeps its wobble.
function elementStrokes(el) {
  if (el.type === "text" || el.type === "paint" || !CV_SHAPES.has(el.type)) return [];
  const strokes = roughStrokes(el).filter((stroke) => stroke.pts.length);
  if (!el.angle) return strokes;
  const cx = el.x + el.width / 2, cy = el.y + el.height / 2, cos = Math.cos(el.angle), sin = Math.sin(el.angle);
  const turn = ([x, y]) => [cx + (x - cx) * cos - (y - cy) * sin, cy + (x - cx) * sin + (y - cy) * cos];
  return strokes.map((stroke) => ({ ...stroke, pts: stroke.pts.map(turn) }));
}

function pieceOf(el, pts, type, smooth) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of pts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  const piece = cvClone(el);
  delete piece.angle;
  delete piece.holes;
  return Object.assign(piece, {
    id: cvId(), type, x: x0, y: y0, width: x1 - x0, height: y1 - y0, fill: null,
    points: pts.map(([x, y]) => [Math.round((x - x0) * 100) / 100, Math.round((y - y0) * 100) / 100]),
    roughness: type === "freedraw" && smooth ? cvNum(el.roughness, 1) : 0,
  });
}

// What is left of el after a round eraser of radius r at (x, y): null when untouched, else the pieces (maybe none).
// Shapes turn into line pieces; a filled shape keeps its fill as a paint area under them.
function cutElement(el, x, y, r) {
  const reach = r + cvNum(el.strokeWidth, 2) / 2, step = Math.max(0.5, reach / 4);
  const strokes = elementStrokes(el);
  if (!strokes.some((stroke) => polyDist(stroke.pts, x, y, false) <= reach)) return null;
  const pieces = [];
  let cut = false;
  strokes.forEach((stroke, n) => {
    const dense = [];
    stroke.pts.forEach((p, i) => {
      if (i) {
        const a = stroke.pts[i - 1];
        if (segDist(x, y, a[0], a[1], p[0], p[1]) <= reach + step) {
          const parts = Math.min(4000, Math.ceil(Math.hypot(p[0] - a[0], p[1] - a[1]) / step));
          for (let k = 1; k < parts; k++) dense.push([a[0] + ((p[0] - a[0]) * k) / parts, a[1] + ((p[1] - a[1]) * k) / parts]);
        }
      }
      dense.push(p);
    });
    const runs = [];
    let run = [];
    for (const p of dense) {
      if (Math.hypot(p[0] - x, p[1] - y) > reach) { run.push(p); continue; }
      cut = true;
      if (run.length) runs.push(run);
      run = [];
    }
    if (run.length) runs.push(run);
    const closed = dense.length > 2 && dense[0][0] === dense[dense.length - 1][0] && dense[0][1] === dense[dense.length - 1][1];
    if (closed && runs.length > 1 && runs[0][0] === dense[0] && runs[runs.length - 1].at(-1) === dense[dense.length - 1]) {
      runs[0] = [...runs.pop(), ...runs[0].slice(1)];
    }
    const lastPoint = dense[dense.length - 1];
    for (const part of runs) {
      if (part.length < 2) continue;
      if (el.type === "freedraw") { pieces.push(pieceOf(el, part, "freedraw", true)); continue; }
      const head = el.type === "arrow" && n === 0 && part[part.length - 1] === lastPoint;
      pieces.push(pieceOf(el, part, head ? "arrow" : stroke.smooth ? "freedraw" : "line", stroke.smooth));
    }
  });
  if (!cut) return null;
  if (el.fill && fillable(el)) {
    const area = elementStrokes({ ...el, roughness: 0 });
    const outline = el.type === "freedraw" ? area[0].pts : area[0].pts.slice(0, -1);
    const paint = pieceOf(el, outline, "paint", false);
    Object.assign(paint, { fill: el.fill, stroke: el.fill, strokeWidth: 1, holes: [] });
    delete paint.roughness;
    pieces.unshift(paint);
  }
  return pieces;
}

// Cuts every element the eraser touches at (x, y); returns how many changed.
function eraseAt(doc, x, y, r) {
  const list = doc.unlaw && Array.isArray(doc.unlaw.elements) ? doc.unlaw.elements : null;
  if (!list) return 0;
  let changed = 0;
  for (let i = list.length - 1; i >= 0; i--) {
    const el = list[i];
    if (!validBox(el) || !CV_SHAPES.has(el.type)) continue;
    // The pad covers half the stroke and the wobble of rough shapes, which can leave the box by a few units.
    if (!el.angle && !boxContains(el, x, y, r + cvNum(el.strokeWidth, 2) + 8)) continue;
    const pieces = cutElement(el, x, y, r);
    if (!pieces) continue;
    list.splice(i, 1, ...pieces);
    changed++;
  }
  return changed;
}

// ---- resize ----
function resizeBox(box, handle, dx, dy) {
  let x0 = box.x, y0 = box.y, x1 = box.x + box.width, y1 = box.y + box.height;
  if (handle.includes("w")) x0 = Math.min(x0 + dx, x1 - CV_MIN_BOX); else x1 = Math.max(x1 + dx, x0 + CV_MIN_BOX);
  if (handle.includes("n")) y0 = Math.min(y0 + dy, y1 - CV_MIN_BOX); else y1 = Math.max(y1 + dy, y0 + CV_MIN_BOX);
  return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
}
function handleAt(box, sx, sy, view, radius = 8) {
  const corners = { nw: [box.x, box.y], ne: [box.x + box.width, box.y], sw: [box.x, box.y + box.height], se: [box.x + box.width, box.y + box.height] };
  for (const [name, [x, y]] of Object.entries(corners)) {
    const p = toScreen(view, x, y);
    if (Math.hypot(p.x - sx, p.y - sy) <= radius) return name;
  }
  return null;
}
// Sets the box on item from the copy taken when the drag began, scaling points and font with it.
function applyBox(item, orig, box) {
  item.x = box.x; item.y = box.y; item.width = box.width; item.height = box.height;
  if (Array.isArray(orig.points)) {
    const kx = orig.width ? box.width / orig.width : 1, ky = orig.height ? box.height / orig.height : 1;
    item.points = orig.points.map((p) => (Array.isArray(p) ? [p[0] * kx, p[1] * ky] : p));
    if (Array.isArray(orig.holes)) item.holes = orig.holes.map((ring) => (Array.isArray(ring) ? ring.map((p) => (Array.isArray(p) ? [p[0] * kx, p[1] * ky] : p)) : ring));
  }
  if (typeof orig.fontSize === "number" && orig.height > 0) item.fontSize = Math.max(8, Math.min(200, Math.round(orig.fontSize * box.height / orig.height)));
}

// ---- text ----
function wrapText(measure, text, maxWidth) {
  const lines = [];
  for (const paragraph of String(text).split("\n")) {
    let line = "";
    for (const word of paragraph.split(" ")) {
      const trial = line ? line + " " + word : word;
      if (measure(trial) <= maxWidth) { line = trial; continue; }
      if (line) lines.push(line);
      let rest = word;
      while (measure(rest) > maxWidth && rest.length > 1) {
        let n = rest.length - 1;
        while (n > 1 && measure(rest.slice(0, n)) > maxWidth) n--;
        lines.push(rest.slice(0, n));
        rest = rest.slice(n);
      }
      line = rest;
    }
    lines.push(line);
  }
  return lines;
}

// ---- creating shapes ----
function cvStyleFields(style, closed) {
  return { stroke: style.stroke, fill: closed && style.fill ? style.stroke : null, strokeWidth: style.width, roughness: style.rough };
}
function makeShape(type, x0, y0, x1, y1, style, seed) {
  const box = normRect(x0, y0, x1, y1);
  return { id: cvId(), type, x: box.x, y: box.y, width: box.width, height: box.height, ...cvStyleFields(style, true), seed };
}
function makeLinear(type, x0, y0, x1, y1, style, seed) {
  const x = Math.min(x0, x1), y = Math.min(y0, y1);
  return { id: cvId(), type, x, y, width: Math.abs(x1 - x0), height: Math.abs(y1 - y0), points: [[x0 - x, y0 - y], [x1 - x, y1 - y]], ...cvStyleFields(style, false), seed };
}
function makeFreedraw(points, style, seed) {
  const x = Math.min(...points.map((p) => p[0])), y = Math.min(...points.map((p) => p[1]));
  const width = Math.max(...points.map((p) => p[0])) - x, height = Math.max(...points.map((p) => p[1])) - y;
  return { id: cvId(), type: "freedraw", x, y, width, height, points: points.map((p) => [p[0] - x, p[1] - y]), ...cvStyleFields(style, false), seed };
}
function snapAngle(dx, dy) {
  const len = Math.hypot(dx, dy);
  const step = Math.PI / 4, angle = Math.round(Math.atan2(dy, dx) / step) * step;
  return { dx: len * Math.cos(angle), dy: len * Math.sin(angle) };
}

// ---- edits: all of them mutate the loaded objects, so keys the page does not know survive ----
function applyStyle(doc, keys, patch) {
  for (const key of keys) {
    const item = cvLookup(doc, key);
    if (!item) continue;
    if (key[0] === "x") {
      if (patch.stroke !== undefined && patch.fill === undefined && item.fill && item.fill === item.stroke) item.fill = patch.stroke;
      if (patch.stroke !== undefined) item.stroke = patch.stroke;
      if (patch.fill !== undefined) item.fill = patch.fill;
      if (patch.strokeWidth !== undefined) item.strokeWidth = patch.strokeWidth;
      if (patch.roughness !== undefined) item.roughness = patch.roughness;
    } else if (patch.stroke !== undefined) {
      item.color = patch.stroke;
    }
  }
}
function moveItems(doc, keys, dx, dy) {
  for (const key of keys) {
    if (key[0] === "e") continue;
    const item = cvLookup(doc, key);
    if (!item) continue;
    item.x += dx;
    item.y += dy;
  }
}
function containedIds(doc, group) {
  const keys = [];
  for (const node of docNodes(doc, true)) if (node.id !== group.id && boxInside(node, group)) keys.push(cvKey("n", node));
  for (const el of docElements(doc, true)) if (boxInside(el, group)) keys.push(cvKey("x", el));
  return keys;
}
function groupAround(doc, keys, id) {
  const box = unionBox(keys.filter((k) => k[0] !== "e").map((k) => cvLookup(doc, k)).filter(validBox));
  if (!box) return null;
  const pad = 24;
  ensureList(doc, "nodes").unshift({ id, type: "group", label: "Group", x: box.x - pad, y: box.y - pad, width: box.width + 2 * pad, height: box.height + 2 * pad });
  return "n:" + id;
}
function removeItems(doc, keys) {
  const gone = { n: new Set(), e: new Set(), x: new Set() };
  for (const key of keys) if (gone[key[0]]) gone[key[0]].add(key.slice(2));
  let count = 0;
  const keep = (kind, list) => list.filter((item) => {
    const drop = Boolean(item) && gone[kind].has(item.id);
    if (drop) count++;
    return !drop;
  });
  if (Array.isArray(doc.nodes)) doc.nodes = keep("n", doc.nodes);
  if (Array.isArray(doc.edges)) {
    doc.edges = keep("e", doc.edges).filter((e) => !e || (!gone.n.has(e.fromNode) && !gone.n.has(e.toNode)));
  }
  if (doc.unlaw && Array.isArray(doc.unlaw.elements)) doc.unlaw.elements = keep("x", doc.unlaw.elements);
  return count;
}
function copyItems(doc, keys) {
  const nodes = [], elements = [];
  for (const key of keys) {
    const item = cvLookup(doc, key);
    if (!item) continue;
    if (key[0] === "n") nodes.push(cvClone(item));
    else if (key[0] === "x") elements.push(cvClone(item));
  }
  const ids = new Set(nodes.map((n) => n.id));
  const edges = cvList(doc, "e").filter((e) => e && ids.has(e.fromNode) && ids.has(e.toNode)).map(cvClone);
  return { nodes, edges, elements };
}
function pasteItems(doc, bundle, offset, newId) {
  const ids = new Map(), keys = [];
  for (const node of bundle.nodes) {
    const copy = cvClone(node);
    copy.id = newId();
    ids.set(node.id, copy.id);
    copy.x += offset;
    copy.y += offset;
    ensureList(doc, "nodes").push(copy);
    keys.push("n:" + copy.id);
  }
  for (const edge of bundle.edges) {
    const copy = cvClone(edge);
    copy.id = newId();
    copy.fromNode = ids.get(edge.fromNode);
    copy.toNode = ids.get(edge.toNode);
    ensureList(doc, "edges").push(copy);
    keys.push("e:" + copy.id);
  }
  for (const el of bundle.elements) {
    const copy = cvClone(el);
    copy.id = newId();
    copy.x += offset;
    copy.y += offset;
    ensureElements(doc).push(copy);
    keys.push("x:" + copy.id);
  }
  return keys;
}

// ---- history: JSON snapshots of the whole document ----
function makeHistory(cap, snapshot) { return { cap, cur: snapshot, undo: [], redo: [] }; }
function histCommit(hist, snapshot, merge) {
  if (snapshot === hist.cur) return false;
  if (!merge || !hist.undo.length) {
    hist.undo.push(hist.cur);
    if (hist.undo.length > hist.cap) hist.undo.shift();
  }
  hist.redo = [];
  hist.cur = snapshot;
  return true;
}
function histUndo(hist) {
  if (!hist.undo.length) return null;
  hist.redo.push(hist.cur);
  hist.cur = hist.undo.pop();
  return hist.cur;
}
function histRedo(hist) {
  if (!hist.redo.length) return null;
  hist.undo.push(hist.cur);
  hist.cur = hist.redo.pop();
  return hist.cur;
}

// ---- canvas state, loading and saving ----
const cv = {
  path: "", name: "", version: "", doc: null, items: [], tool: "select", view: { x: 0, y: 0, z: 1 }, sel: [],
  style: { stroke: CV_INK[0], fill: false, width: 4, rough: 1 }, hist: null, drag: null, editing: null, space: false,
  dirty: false, saving: null, saveTimer: 0, clip: null, pasted: 0, hover: null, pointer: null, lastLabel: "", lastAt: 0,
  drawPending: false, el: null, ctx: null, w: 0, h: 0, dpr: 1, ui: {}, gesture: 1, eraser: "object", cursor: null, menu: "",
  thread: null, threadAt: null, layers: false, gallery: false, viewing: null, pasteWait: 0,
  back: [], shelf: { favorites: [], groups: [] }, gallerySearch: "", playing: null, inline: null, clickTimer: 0, folded: null, ticking: false, galleryDrag: null,
};

// The eraser mode, shape evenness and width are remembered in this browser.
function cvLoadPrefs() {
  let prefs = {};
  try { prefs = JSON.parse(localStorage.getItem(CV_PREFS) || "{}") || {}; } catch { prefs = {}; }
  if (CV_ERASERS.some((e) => e.mode === prefs.eraser)) cv.eraser = prefs.eraser;
  if (CV_ROUGH_LEVELS.some((l) => l.rough === prefs.rough)) cv.style.rough = prefs.rough;
  if (Number.isInteger(prefs.width) && prefs.width >= CV_MIN_WIDTH && prefs.width <= CV_MAX_WIDTH) cv.style.width = prefs.width;
}
function cvSavePrefs() {
  try { localStorage.setItem(CV_PREFS, JSON.stringify({ eraser: cv.eraser, rough: cv.style.rough, width: cv.style.width })); } catch { /* private mode: not remembered */ }
}
cvLoadPrefs();

function cvLoad(shape) {
  if (shape.path !== cv.path) { cvStopMedia(); cvCloseInline(); cvCanvasThumbs.clear(); }
  cv.path = shape.path;
  cv.name = shape.name || "";
  cv.version = shape.version;
  const doc = shape.canvas && typeof shape.canvas === "object" && !Array.isArray(shape.canvas) ? shape.canvas : {};
  ensureList(doc, "nodes");
  ensureList(doc, "edges");
  const linked = doc.nodes.filter((node) => textToLink(node)).length;
  cv.doc = doc;
  cv.hist = makeHistory(CV_HISTORY, JSON.stringify(doc));
  cv.sel = cv.sel.filter((key) => cvLookup(doc, key));
  cv.drag = null;
  cv.hover = null;
  cv.dirty = false;
  cv.lastLabel = "";
  clearTimeout(cv.saveTimer);
  cv.saveTimer = 0;
  cvStatus("Saved");
  cvSync();
  cvDraw();
  if (linked) cvChanged(); // written back, so Obsidian sees link cards too
}

function cvStatus(text) {
  if (cv.ui.status) cv.ui.status.textContent = text;
}

function cvChanged() {
  cv.dirty = true;
  cvStatus("Unsaved");
  clearTimeout(cv.saveTimer);
  cv.saveTimer = setTimeout(saveCanvas, 800);
  cvSync();
  cvDraw();
}

// Records the document as one undo step; repeated edits with the same label inside 700 ms (arrow-key nudges) share a step.
function cvCommit(label) {
  const now = Date.now();
  const merge = Boolean(label) && label === cv.lastLabel && now - cv.lastAt < 700;
  cv.lastLabel = label || "";
  cv.lastAt = now;
  if (histCommit(cv.hist, JSON.stringify(cv.doc), merge)) cvChanged();
}

function cvRestore(snapshot) {
  cv.doc = JSON.parse(snapshot);
  cv.sel = cv.sel.filter((key) => cvLookup(cv.doc, key));
  cv.lastLabel = "";
  cvChanged();
}
function cvUndo() { const snapshot = histUndo(cv.hist); if (snapshot !== null) cvRestore(snapshot); }
function cvRedo() { const snapshot = histRedo(cv.hist); if (snapshot !== null) cvRestore(snapshot); }

async function sendCanvas() {
  const sent = cv.hist.cur;
  cvStatus("Saving…");
  const { status, data } = await api("POST", "/api/canvas", { path: cv.path, version: cv.version, canvas: cv.doc });
  if (status === 200) {
    if (typeof data.version === "string") cv.version = data.version;
    if (cv.hist.cur === sent) { cv.dirty = false; cvStatus("Saved"); }
    else cv.saveTimer = setTimeout(saveCanvas, 800);
  } else if (status === 409 && data.canvas) {
    cvLoad(data.canvas);
    toast("Canvas changed elsewhere; reloaded");
  } else {
    cvStatus("Save failed");
    toast(data.error || "Could not save the canvas");
    cv.saveTimer = setTimeout(saveCanvas, 4000);
  }
}

async function saveCanvas() {
  clearTimeout(cv.saveTimer);
  cv.saveTimer = 0;
  while (cv.saving) await cv.saving;
  if (!cv.doc || !cv.dirty) return;
  // A drag or an open editor holds changes that are not an undo step yet; they are never written half-done.
  if (cv.drag || cv.editing) { cv.saveTimer = setTimeout(saveCanvas, 300); return; }
  cv.saving = sendCanvas();
  try { await cv.saving; } finally { cv.saving = null; }
}

async function pollCanvas() {
  const idle = () => state.view === "canvas" && !document.hidden && cv.doc && !cv.drag && !cv.editing && !cv.saving && !cv.dirty;
  if (!idle()) return;
  const path = cv.path;
  const { status, data } = await api("GET", "/api/canvas?path=" + encodeURIComponent(path));
  if (status !== 200 || path !== cv.path || !idle()) return;
  if (data.version !== cv.version) { cvLoad(data); toast("Canvas updated from the file"); }
}

async function loadCanvasList() {
  const { status, data } = await api("GET", "/api/canvases");
  if (status !== 200) { toast(data.error || "Could not list the canvases"); return null; }
  cv.items = Array.isArray(data.items) ? data.items : [];
  cv.shelf = cleanShelf(data.shelf);
  cvFillPick();
  return data;
}

async function cvShow(data) {
  cvLoad(data);
  localStorage.setItem("desk-canvas", data.path);
  cvFit();
  await loadCanvasList();
}

async function cvOpen(path, create) {
  await saveCanvas();
  const { status, data } = await api("POST", "/api/canvases", { path, create });
  if (status !== 200) { toast(data.error || "Could not open the canvas"); cvFillPick(); return false; }
  await cvShow(data);
  return true;
}

// New canvas = the next free canvas-N in the canvas folder, opened at once; rename it in the name field.
async function cvNew() {
  await saveCanvas();
  const { status, data } = await api("POST", "/api/canvas/new", {});
  if (status !== 200) { toast(data.error || "Could not create a canvas"); return; }
  await cvShow(data);
}

// "Open…" shows the macOS open dialog (through the server); without it the page asks for a path.
async function cvChoose() {
  const { status, data } = await api("POST", "/api/canvas/choose", {});
  if (status !== 200) { toast(data.error || "Could not show the file dialog"); return; }
  if (data.unavailable) {
    const answer = prompt("Path or name of the canvas to open");
    if (answer && answer.trim()) await cvOpen(answer.trim(), false);
  } else if (data.path) {
    await cvOpen(data.path, false);
  }
}

async function cvRename(raw) {
  const field = cv.ui.name, name = String(raw || "").trim();
  if (!cv.path || !name || name === cv.name) { if (field) field.value = cv.name; return; }
  await saveCanvas();
  const { status, data } = await api("POST", "/api/canvas/rename", { path: cv.path, name });
  if (status !== 200) { toast(data.error || "Could not rename the canvas"); if (cv.ui.name) cv.ui.name.value = cv.name; return; }
  cv.path = data.path;
  cv.name = data.name;
  if (typeof data.version === "string" && !cv.dirty) cv.version = data.version;
  localStorage.setItem("desk-canvas", data.path);
  await loadCanvasList();
}

async function cvStart() {
  const list = await loadCanvasList();
  if (!list) return;
  let target = null;
  const read = async (query) => { const { status, data } = await api("GET", "/api/canvas" + query); return status === 200 ? data : null; };
  if (cv.path) target = await read("?path=" + encodeURIComponent(cv.path));
  if (!target && list.current) target = await read("");
  if (!target) {
    const remembered = localStorage.getItem("desk-canvas");
    const item = cv.items.find((i) => i.path === remembered) || cv.items[0];
    if (item) target = await read("?path=" + encodeURIComponent(item.path));
  }
  if (state.view !== "canvas" || !cv.el) return;
  if (target) {
    const fresh = target.path !== cv.path;
    cvLoad(target);
    if (fresh) cvFit();
  }
  cvFillPick();
  cvSync();
}

function leaveCanvas() {
  cvCancelDrag();
  cvEndEdit();
  cvCloseView();
  cvStopMedia();
  cvCloseInline();
  clearTimeout(cv.clickTimer);
  cv.gallery = false;
  cv.layerDrag = null;
  cv.thread = null;
  saveCanvas();
  cv.el = null;
  cv.ctx = null;
  cv.ui = {};
  cv.space = false;
}

// ---- painting ----
function cvPalette() {
  const css = getComputedStyle(document.documentElement);
  const get = (name) => css.getPropertyValue(name).trim();
  return { dark: document.documentElement.dataset.theme === "dark", bg: get("--bg"), panel: get("--panel"), text: get("--text"), muted: get("--muted"), line: get("--line"), accent: get("--accent-ink"), soft: get("--accent-soft") };
}

function roundPath(ctx, x, y, w, h, r) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

function strokePath(ctx, stroke) {
  const pts = stroke.pts;
  if (!pts.length) return;
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  if (!stroke.smooth || pts.length < 3) {
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  } else {
    for (let i = 1; i < pts.length - 1; i++) ctx.quadraticCurveTo(pts[i][0], pts[i][1], (pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2);
    ctx.lineTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
  }
  ctx.stroke();
}

function fillTriangle(ctx, tip, angle, size) {
  ctx.beginPath();
  ctx.moveTo(tip.x, tip.y);
  ctx.lineTo(tip.x - size * Math.cos(angle - 0.45), tip.y - size * Math.sin(angle - 0.45));
  ctx.lineTo(tip.x - size * Math.cos(angle + 0.45), tip.y - size * Math.sin(angle + 0.45));
  ctx.closePath();
  ctx.fill();
}

function paintElement(ctx, el, pal, hideText) {
  const ink = adaptInk(el.stroke, pal.dark);
  ctx.save();
  if (el.angle) {
    ctx.translate(el.x + el.width / 2, el.y + el.height / 2);
    ctx.rotate(el.angle);
    ctx.translate(-(el.x + el.width / 2), -(el.y + el.height / 2));
  }
  if (el.type === "text") {
    const size = Math.max(8, Math.min(200, cvNum(el.fontSize, 24)));
    if (!hideText) {
      ctx.font = size + "px " + CV_HAND;
      ctx.textBaseline = "top";
      ctx.fillStyle = ink;
      String(el.text || "").split("\n").forEach((line, i) => ctx.fillText(line, el.x, el.y + i * size * 1.25));
    }
    ctx.restore();
    return;
  }
  if (el.type === "paint") {
    ctx.beginPath();
    for (const ring of paintRings(el)) ring.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
    ctx.fillStyle = adaptInk(typeof el.fill === "string" ? el.fill : el.stroke, pal.dark);
    ctx.fill("evenodd");
    ctx.restore();
    return;
  }
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = ink;
  ctx.lineWidth = Math.max(CV_MIN_WIDTH, Math.min(CV_MAX_WIDTH, cvNum(el.strokeWidth, 2)));
  if (el.fill && fillable(el)) {
    ctx.fillStyle = adaptInk(el.fill, pal.dark);
    strokePathFill(ctx, fillOutline(el));
  }
  for (const stroke of roughStrokes(el)) strokePath(ctx, stroke);
  if (el.type === "arrow") {
    const pts = elementPoints(el);
    if (pts.length >= 2) {
      const size = 12 + ctx.lineWidth * 2;
      const [a, b] = arrowHead(pts[pts.length - 2], pts[pts.length - 1], size);
      ctx.beginPath();
      ctx.moveTo(a[0], a[1]);
      ctx.lineTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
      ctx.lineTo(b[0], b[1]);
      ctx.stroke();
    }
  }
  ctx.restore();
}

function strokePathFill(ctx, outline) {
  ctx.beginPath();
  outline.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
  ctx.closePath();
  ctx.fill();
}

function paintLines(ctx, node, lines, font, color, lineHeight, cursor) {
  ctx.font = font;
  ctx.fillStyle = color;
  for (const line of lines) {
    ctx.fillText(line, node.x + 12, cursor.y);
    cursor.y += lineHeight;
  }
}

function paintNode(ctx, node, pal, hideText, image) {
  const color = nodeColor(node.color);
  ctx.save();
  roundPath(ctx, node.x, node.y, node.width, node.height, 8);
  ctx.fillStyle = pal.panel;
  ctx.fill();
  if (color) { ctx.globalAlpha = 0.14; ctx.fillStyle = color; ctx.fill(); ctx.globalAlpha = 1; }
  ctx.lineWidth = color ? 2 : 1.5;
  ctx.strokeStyle = color || pal.line;
  ctx.stroke();
  if (image && node.height > 60 && node.type !== "link") {
    // A picture fills the card above a one-line caption.
    ctx.save();
    roundPath(ctx, node.x + 5, node.y + 5, node.width - 10, node.height - 38, 5);
    ctx.clip();
    drawCover(ctx, image, { x: node.x + 5, y: node.y + 5, width: node.width - 10, height: node.height - 38 }, !CV_IMAGE_FILE.test(String(node.file ?? "")));
    ctx.restore();
    if (!hideText) {
      ctx.font = "600 13px " + CV_FONT;
      ctx.textBaseline = "middle";
      ctx.fillStyle = pal.text;
      ctx.fillText(fileLabel(node.file), node.x + 10, node.y + node.height - 17, Math.max(10, node.width - 20));
    }
  } else if (!hideText) {
    ctx.beginPath();
    ctx.rect(node.x + 4, node.y + 4, node.width - 8, node.height - 8);
    ctx.clip();
    ctx.textBaseline = "top";
    const cursor = { y: node.y + 12 }, room = Math.max(10, node.width - 24);
    const wrapped = (text, font) => { ctx.font = font; return wrapText((s) => ctx.measureText(s).width, String(text).slice(0, 4000), room); };
    if (node.type === "text") {
      paintLines(ctx, node, wrapped(node.text ?? "", "15px " + CV_FONT), "15px " + CV_FONT, pal.text, 21, cursor);
    } else if (node.type === "file") {
      const file = String(node.file ?? "");
      paintLines(ctx, node, ["File"], "11px " + CV_FONT, pal.muted, 16, cursor);
      paintLines(ctx, node, wrapped(file.split("/").pop(), "600 15px " + CV_FONT), "600 15px " + CV_FONT, pal.text, 21, cursor);
      if (file.includes("/")) paintLines(ctx, node, wrapped(file, "12px " + CV_FONT), "12px " + CV_FONT, pal.muted, 17, cursor);
    } else if (node.type === "link") {
      // The site's logo on top, then the page's title and the address.
      const preview = node.unlawPreview && typeof node.unlawPreview === "object" ? node.unlawPreview : null;
      const size = Math.min(72, node.height - 96, node.width - 40);
      if (size >= 24) { paintSiteLogo(ctx, image, node.x + node.width / 2, cursor.y + 2, size, pal, linkSite(node)); cursor.y += size + 14; }
      if (preview && preview.title) paintLines(ctx, node, wrapped(String(preview.title), "600 15px " + CV_FONT), "600 15px " + CV_FONT, pal.text, 21, cursor);
      paintLines(ctx, node, wrapped(node.url ?? "", "13px " + CV_MONO), "13px " + CV_MONO, pal.accent, 18, cursor);
      if (preview && preview.description) paintLines(ctx, node, wrapped(String(preview.description), "13px " + CV_FONT), "13px " + CV_FONT, pal.muted, 18, cursor);
    } else {
      paintLines(ctx, node, [String(node.type)], "12px " + CV_FONT, pal.muted, 16, cursor);
    }
  }
  ctx.restore();
}

// A logo in a rounded white square (icons are often transparent), or the site's first letter when it has none.
function paintSiteLogo(ctx, image, cx, top, size, pal, site) {
  const x = cx - size / 2;
  ctx.save();
  roundPath(ctx, x, top, size, size, size * 0.22);
  if (image) {
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    ctx.clip();
    const pad = size * 0.1;
    drawCover(ctx, image, { x: x + pad, y: top + pad, width: size - pad * 2, height: size - pad * 2 }, true);
  } else {
    ctx.fillStyle = pal.accent;
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.font = "700 " + Math.round(size * 0.5) + "px " + CV_FONT;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText((String(site || "").replace(/^www\./, "")[0] || "?").toUpperCase(), cx, top + size / 2 + 1);
  }
  ctx.restore();
}

function linkSite(node) {
  const preview = node.unlawPreview;
  if (preview && typeof preview === "object" && preview.site) return String(preview.site);
  const found = /^https?:\/\/([^/?#:]+)/i.exec(String(node.url ?? "").trim());
  return found ? found[1] : "";
}

// A file card's caption: the file name; a linked canvas without its .canvas.
function fileLabel(file) {
  return String(file ?? "").split("/").pop().replace(CV_CANVAS_FILE, "");
}

function linkTitle(node) {
  const preview = node.unlawPreview;
  return preview && typeof preview === "object" && preview.title ? String(preview.title) : String(node.url ?? "");
}

// Video, sound and 3D cards say so: a play button or a 3D tag over the card; a linked canvas gets a tag. A card that
// plays (media from cvMediaState) shows its progress, a sound its wave.
function paintFileBadge(ctx, node, media, cork) {
  if (node.type !== "file" || node.width < 60 || node.height < 60) return;
  const kind = cvFileKind(node.file);
  if (kind === "canvas") { paintCanvasTag(ctx, node, cork); return; }
  if (kind !== "video" && kind !== "audio" && kind !== "model") return;
  if (media) paintMediaBar(ctx, node, media, cork);
  if (media && media.playing) return;
  const r = Math.min(24, node.width / 6, node.height / 6), x = node.x + node.width / 2, y = node.y + Math.max(r + 6, (node.height - 33) / 2 + 5);
  ctx.save();
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0, 0, 0, 0.55)";
  ctx.fill();
  ctx.fillStyle = "#ffffff";
  if (kind === "model") {
    ctx.font = "700 " + Math.round(r * 0.8) + "px " + CV_FONT;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("3D", x, y + 1);
  } else {
    ctx.beginPath();
    ctx.moveTo(x - r * 0.3, y - r * 0.45);
    ctx.lineTo(x + r * 0.5, y);
    ctx.lineTo(x - r * 0.3, y + r * 0.45);
    ctx.closePath();
    ctx.fill();
  }
  ctx.restore();
}

// The picture area of a file card (where a photo, a video frame or a PDF page is), unrotated.
function cvPictureBox(node, cork) {
  return cork
    ? { x: node.x + 10, y: node.y + 10, width: node.width - 20, height: Math.max(10, node.height - 50) }
    : { x: node.x + 5, y: node.y + 5, width: node.width - 10, height: node.height - 38 };
}

function paintMediaBar(ctx, node, media, cork) {
  const draw = () => {
    const box = cvPictureBox(node, cork);
    if (box.width < 30 || box.height < 30) return;
    ctx.save();
    if (media.peaks && media.peaks.length) {
      const n = media.peaks.length, gap = box.width / n, tall = Math.min(56, box.height * 0.4), base = box.y + box.height - (media.idle ? 8 : 24);
      ctx.fillStyle = "rgba(0, 0, 0, 0.35)";
      ctx.fillRect(box.x, base - tall - 6, box.width, tall + (media.idle ? 14 : 30));
      for (let i = 0; i < n; i++) {
        const tallness = Math.max(1.5, media.peaks[i] * tall);
        ctx.fillStyle = (i + 0.5) / n <= media.progress ? CV_PLAYED : "rgba(255, 255, 255, 0.8)";
        ctx.fillRect(box.x + i * gap + gap * 0.2, base - tallness, Math.max(1, gap * 0.6), tallness);
      }
    }
    if (!media.idle) {
      ctx.fillStyle = "rgba(0, 0, 0, 0.45)";
      ctx.fillRect(box.x, box.y + box.height - 18, box.width, 18);
      ctx.fillStyle = "rgba(255, 255, 255, 0.35)";
      ctx.fillRect(box.x + 8, box.y + box.height - 10, box.width - 16, 3);
      ctx.fillStyle = CV_PLAYED;
      ctx.fillRect(box.x + 8, box.y + box.height - 10, (box.width - 16) * media.progress, 3);
    }
    ctx.restore();
  };
  if (cork) tilted(ctx, node, draw); else draw();
}

function paintCanvasTag(ctx, node, cork) {
  const draw = () => {
    const box = cvPictureBox(node, cork);
    ctx.save();
    ctx.font = "700 11px " + CV_FONT;
    const label = "CANVAS \u2197", width = ctx.measureText(label).width + 14;
    roundPath(ctx, box.x + 6, box.y + 6, width, 20, 6);
    ctx.fillStyle = "rgba(0, 0, 0, 0.6)";
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.textBaseline = "middle";
    ctx.fillText(label, box.x + 13, box.y + 16.5);
    ctx.restore();
  };
  if (cork) tilted(ctx, node, draw); else draw();
}

// ---- detective board painting ----
// Photos fill their frame (cropped); a document's preview is shown whole, so its page is never cut.
function drawCover(ctx, image, box, whole) {
  const iw = image.videoWidth || image.naturalWidth || image.width || 1, ih = image.videoHeight || image.naturalHeight || image.height || 1;
  if (whole) {
    const scale = Math.min(box.width / iw, box.height / ih), w = iw * scale, h = ih * scale;
    ctx.drawImage(image, box.x + (box.width - w) / 2, box.y + (box.height - h) / 2, w, h);
    return;
  }
  const scale = Math.max(box.width / iw, box.height / ih), sw = box.width / scale, sh = box.height / scale;
  ctx.drawImage(image, (iw - sw) / 2, (ih - sh) / 2, sw, sh, box.x, box.y, box.width, box.height);
}

// One speckled tile (seeded, so it never flickers), wrapped at the edges so it repeats without seams.
const corkTiles = {};
const corkPatterns = new WeakMap();
function corkPattern(ctx, dark) {
  const key = dark ? "dark" : "light";
  if (typeof ctx.createPattern !== "function") return null;
  let cached = corkPatterns.get(ctx);
  if (cached && cached.key === key) return cached.pattern;
  if (!corkTiles[key]) {
    const tile = document.createElement("canvas"), size = 160;
    const t = tile && typeof tile.getContext === "function" ? tile.getContext("2d") : null;
    if (!t) return null;
    tile.width = tile.height = size;
    const base = CV_CORK[key], random = mulberry32(7);
    t.fillStyle = base;
    t.fillRect(0, 0, size, size);
    for (let i = 0; i < 1500; i++) {
      const x = random() * size, y = random() * size, r = 0.4 + random() * 1.7, squash = 0.45 + random() * 0.6, turn = random() * Math.PI;
      t.globalAlpha = 0.15 + random() * 0.3;
      t.fillStyle = mixColor(base, random() < 0.45 ? "#f6dcaa" : "#24120a", 0.3 + random() * 0.45);
      for (const dx of [-size, 0, size]) for (const dy of [-size, 0, size]) {
        if (x + dx < -3 || x + dx > size + 3 || y + dy < -3 || y + dy > size + 3) continue;
        t.beginPath();
        t.ellipse(x + dx, y + dy, r, r * squash, turn, 0, Math.PI * 2);
        t.fill();
      }
    }
    t.globalAlpha = 1;
    corkTiles[key] = tile;
  }
  cached = { key, pattern: ctx.createPattern(corkTiles[key], "repeat") };
  corkPatterns.set(ctx, cached);
  return cached.pattern;
}

function tilted(ctx, node, draw) {
  const tilt = nodeTilt(node), cx = node.x + node.width / 2, cy = node.y + node.height / 2;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(tilt);
  ctx.translate(-cx, -cy);
  draw();
  ctx.restore();
}

function paperShadow(ctx, on) {
  ctx.shadowColor = on ? "rgba(30, 14, 0, 0.45)" : "rgba(0, 0, 0, 0)";
  ctx.shadowBlur = on ? 12 : 0;
  ctx.shadowOffsetX = on ? 3 : 0;
  ctx.shadowOffsetY = on ? 6 : 0;
}

// Paper with the bottom right corner lifted a little.
function paperPath(ctx, x, y, w, h, curl) {
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x + w, y);
  ctx.lineTo(x + w, y + h - curl);
  ctx.quadraticCurveTo(x + w - curl * 0.15, y + h - curl * 0.15, x + w - curl, y + h);
  ctx.lineTo(x, y + h);
  ctx.closePath();
}

function paperFill(ctx, x, y, h, paper) {
  const shade = typeof ctx.createLinearGradient === "function" ? ctx.createLinearGradient(x, y, x, y + h) : null;
  if (shade && typeof shade.addColorStop === "function") {
    shade.addColorStop(0, paper);
    shade.addColorStop(1, mixColor(paper, "#000000", 0.08));
    ctx.fillStyle = shade;
  } else {
    ctx.fillStyle = paper;
  }
  ctx.fill();
}

function paperCurl(ctx, x, y, w, h, curl, paper) {
  ctx.beginPath();
  ctx.moveTo(x + w, y + h - curl);
  ctx.quadraticCurveTo(x + w - curl * 0.15, y + h - curl * 0.15, x + w - curl, y + h);
  ctx.lineTo(x + w - curl * 0.85, y + h - curl * 0.85);
  ctx.closePath();
  ctx.fillStyle = mixColor(paper, "#000000", 0.2);
  ctx.fill();
}

function handLines(ctx, node, text, top, size, color, centered) {
  const font = size + "px " + CV_HAND, room = Math.max(10, node.width - 28);
  ctx.font = font;
  ctx.fillStyle = color;
  ctx.textBaseline = "top";
  ctx.textAlign = centered ? "center" : "left";
  const lines = wrapText((s) => ctx.measureText(s).width, String(text).slice(0, 4000), room);
  let y = top;
  for (const line of lines) {
    if (y + size > node.y + node.height - 8) break;
    ctx.fillText(line, centered ? node.x + node.width / 2 : node.x + 14, y);
    y += size * 1.25;
  }
  ctx.textAlign = "left";
}

// A sticky note, a pinned photo (or document) or an index card for a link.
function paintCorkNode(ctx, node, pal, hideText, image) {
  const { x, y, width: w, height: h } = node, ink = "#2b2622";
  tilted(ctx, node, () => {
    if (node.type === "file") {
      const paper = "#fbf8f0", photo = { x: x + 10, y: y + 10, width: w - 20, height: Math.max(10, h - 50) };
      paperShadow(ctx, true);
      ctx.beginPath();
      ctx.rect(x, y, w, h);
      ctx.fillStyle = paper;
      ctx.fill();
      paperShadow(ctx, false);
      if (image) {
        const whole = !CV_IMAGE_FILE.test(String(node.file ?? ""));
        if (whole) { ctx.fillStyle = "#ece6d8"; ctx.fillRect(photo.x, photo.y, photo.width, photo.height); }
        drawCover(ctx, image, photo, whole);
      } else {
        ctx.fillStyle = "#ece6d8";
        ctx.fillRect(photo.x, photo.y, photo.width, photo.height);
        ctx.fillStyle = "#c9bfa9";
        for (let line = photo.y + 46; line < photo.y + photo.height - 10; line += 14) ctx.fillRect(photo.x + 14, line, Math.max(0, photo.width - 28) * (line % 3 ? 1 : 0.6), 3);
        const label = fileExtension(node.file);
        ctx.font = "700 15px " + CV_FONT;
        const badge = Math.min(photo.width - 20, ctx.measureText(label).width + 18);
        ctx.fillStyle = label === "PDF" ? "#c1121f" : /^DOCX?$|^PAGES$/.test(label) ? "#1d6fd8" : /^XLSX?$|^CSV$|^NUMBERS$/.test(label) ? "#2b9348" : "#6b5b45";
        ctx.fillRect(photo.x + 10, photo.y + 12, badge, 24);
        ctx.fillStyle = "#ffffff";
        ctx.textBaseline = "middle";
        ctx.fillText(label, photo.x + 19, photo.y + 24, badge - 18);
      }
      if (!hideText) {
        ctx.font = "16px " + CV_HAND;
        ctx.fillStyle = ink;
        ctx.textBaseline = "middle";
        ctx.textAlign = "center";
        ctx.fillText(fileLabel(node.file), x + w / 2, y + h - 20, Math.max(10, w - 20));
        ctx.textAlign = "left";
      }
      return;
    }
    if (node.type === "link") {
      paperShadow(ctx, true);
      ctx.beginPath();
      ctx.rect(x, y, w, h);
      ctx.fillStyle = "#fdfdf8";
      ctx.fill();
      paperShadow(ctx, false);
      ctx.fillStyle = "#e05a5a";
      ctx.fillRect(x, y + 30, w, 1.5);
      ctx.fillStyle = "#9cc3e6";
      for (let line = y + 52; line < y + h - 4; line += 22) ctx.fillRect(x, line, w, 1);
      const size = Math.min(56, h - 110, w - 40);
      if (size >= 24) paintSiteLogo(ctx, image, x + w / 2, y + 40, size, { accent: "#1d4f91" }, linkSite(node));
      if (!hideText) handLines(ctx, node, linkTitle(node) + (linkTitle(node) === String(node.url ?? "") ? "" : "\n" + String(node.url ?? "")), y + 36 + (size >= 24 ? size + 14 : 0), 16, "#1d4f91", false);
      return;
    }
    const color = nodeColor(node.color), paper = color ? mixColor(color, "#ffffff", 0.55) : CV_PAPER, curl = Math.min(22, w / 6, h / 6);
    paperShadow(ctx, true);
    paperPath(ctx, x, y, w, h, curl);
    paperFill(ctx, x, y, h, paper);
    paperShadow(ctx, false);
    paperCurl(ctx, x, y, w, h, curl, paper);
    // Text starts below the pin, where thread tied to it still passes.
    if (!hideText) handLines(ctx, node, node.type === "text" ? node.text ?? "" : String(node.type), y + 38, 19, ink, false);
  });
}

// The red thread: its shadow on the cork, a darker body, a lighter twist.
function paintThread(ctx, curve, edge, pal, selected, hideLabel) {
  const color = nodeColor(edge.color) || CV_THREAD;
  const path = (dx, dy) => {
    ctx.beginPath();
    ctx.moveTo(curve.p0.x + dx, curve.p0.y + dy);
    ctx.bezierCurveTo(curve.c1.x + dx, curve.c1.y + dy, curve.c2.x + dx, curve.c2.y + dy, curve.p3.x + dx, curve.p3.y + dy);
  };
  ctx.save();
  ctx.lineCap = "round";
  path(3, 6);
  ctx.strokeStyle = "rgba(30, 12, 0, 0.3)";
  ctx.lineWidth = 2.6;
  ctx.stroke();
  if (selected) {
    path(0, 0);
    ctx.strokeStyle = pal.accent;
    ctx.globalAlpha = 0.5;
    ctx.lineWidth = 8;
    ctx.stroke();
    ctx.globalAlpha = 1;
  }
  path(0, 0);
  ctx.strokeStyle = mixColor(color, "#000000", 0.3);
  ctx.lineWidth = 2.8;
  ctx.stroke();
  path(0, 0);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.9;
  ctx.stroke();
  ctx.setLineDash([2, 4]);
  path(0, 0);
  ctx.strokeStyle = mixColor(color, "#ffffff", 0.4);
  ctx.lineWidth = 0.8;
  ctx.stroke();
  ctx.setLineDash([]);
  if (edge.label && !hideLabel) {
    // A paper tag hanging on the thread.
    const mid = bezierPoint(curve, 0.5), text = String(edge.label).slice(0, 120);
    ctx.font = "16px " + CV_HAND;
    const width = ctx.measureText(text).width + 18;
    ctx.translate(mid.x, mid.y);
    ctx.rotate((idHash(edge.id) * 2 - 1) * 0.06);
    paperShadow(ctx, true);
    ctx.fillStyle = "#f7f1e1";
    ctx.fillRect(-width / 2, -13, width, 26);
    paperShadow(ctx, false);
    ctx.fillStyle = "#2b2622";
    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    ctx.fillText(text, 0, 1);
  }
  ctx.restore();
}

// A push pin seen from above: its shadow and needle on the cork, a round head with a cap.
function paintEndHandle(ctx, p, pal, z) {
  ctx.save();
  ctx.beginPath();
  ctx.arc(p.x, p.y, 5 / z, 0, Math.PI * 2);
  ctx.fillStyle = pal.panel || "#fff";
  ctx.fill();
  ctx.lineWidth = 2 / z;
  ctx.strokeStyle = pal.accent;
  ctx.stroke();
  ctx.restore();
}

// The thread tool between its first click and the second: a pin and thread (or a dashed line) to the pointer.
function paintThreadDraft(ctx, t, pal, cork, z) {
  ctx.save();
  if (cork) {
    const c = sagCurve(t.a, t.b);
    ctx.beginPath();
    ctx.moveTo(c.p0.x, c.p0.y);
    ctx.bezierCurveTo(c.c1.x, c.c1.y, c.c2.x, c.c2.y, c.p3.x, c.p3.y);
    ctx.strokeStyle = CV_THREAD;
    ctx.lineWidth = 2.4;
    ctx.stroke();
    ctx.restore();
    paintPin(ctx, t.a, CV_PINS[0]);
    return;
  }
  ctx.setLineDash([6 / z, 5 / z]);
  ctx.beginPath();
  ctx.moveTo(t.a.x, t.a.y);
  ctx.lineTo(t.b.x, t.b.y);
  ctx.strokeStyle = pal.accent;
  ctx.lineWidth = 2 / z;
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.arc(t.a.x, t.a.y, 4 / z, 0, Math.PI * 2);
  ctx.fillStyle = pal.accent;
  ctx.fill();
  ctx.restore();
}

function paintPin(ctx, p, color) {
  ctx.save();
  ctx.fillStyle = "rgba(25, 10, 0, 0.35)";
  ctx.beginPath();
  ctx.ellipse(p.x + 4, p.y + 6, 6.5, 5, 0.4, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "rgba(25, 10, 0, 0.4)";
  ctx.lineWidth = 1.3;
  ctx.beginPath();
  ctx.moveTo(p.x, p.y);
  ctx.lineTo(p.x + 7, p.y + 9);
  ctx.stroke();
  const head = typeof ctx.createRadialGradient === "function" ? ctx.createRadialGradient(p.x - 2.5, p.y - 2.5, 0.5, p.x, p.y, 7.5) : null;
  if (head && typeof head.addColorStop === "function") {
    head.addColorStop(0, mixColor(color, "#ffffff", 0.65));
    head.addColorStop(0.45, color);
    head.addColorStop(1, mixColor(color, "#000000", 0.45));
    ctx.fillStyle = head;
  } else {
    ctx.fillStyle = color;
  }
  ctx.beginPath();
  ctx.arc(p.x, p.y, 7, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = mixColor(color, "#ffffff", 0.25);
  ctx.beginPath();
  ctx.arc(p.x - 0.8, p.y - 0.8, 3.4, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "rgba(255, 255, 255, 0.85)";
  ctx.beginPath();
  ctx.arc(p.x - 2.2, p.y - 2.4, 1.3, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function paintVignette(ctx, w, h) {
  if (typeof ctx.createRadialGradient !== "function") return;
  const shade = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.35, w / 2, h / 2, Math.hypot(w, h) * 0.6);
  if (!shade || typeof shade.addColorStop !== "function") return;
  shade.addColorStop(0, "rgba(0, 0, 0, 0)");
  shade.addColorStop(1, "rgba(20, 8, 0, 0.32)");
  ctx.fillStyle = shade;
  ctx.fillRect(0, 0, w, h);
}

function paintGroup(ctx, node, pal, hideLabel) {
  const color = nodeColor(node.color) || pal.accent;
  ctx.save();
  roundPath(ctx, node.x, node.y, node.width, node.height, 12);
  ctx.globalAlpha = 0.06;
  ctx.fillStyle = color;
  ctx.fill();
  ctx.globalAlpha = 0.7;
  ctx.setLineDash([8, 6]);
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = color;
  ctx.stroke();
  ctx.setLineDash([]);
  if (!hideLabel && node.label) {
    ctx.globalAlpha = 1;
    ctx.font = "600 13px " + CV_FONT;
    ctx.textBaseline = "bottom";
    ctx.fillStyle = pal.text;
    ctx.fillText(String(node.label).slice(0, 80), node.x + 4, node.y - 6, Math.max(20, node.width - 8));
  }
  ctx.restore();
}

function paintEdge(ctx, curve, edge, pal, selected, hideLabel) {
  const color = selected ? pal.accent : nodeColor(edge.color) || pal.muted;
  ctx.save();
  ctx.lineWidth = selected ? 3 : 2;
  ctx.lineCap = "round";
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(curve.p0.x, curve.p0.y);
  ctx.bezierCurveTo(curve.c1.x, curve.c1.y, curve.c2.x, curve.c2.y, curve.p3.x, curve.p3.y);
  ctx.stroke();
  const toward = (from, tip) => Math.atan2(tip.y - from.y, tip.x - from.x);
  if (edge.toEnd !== "none") fillTriangle(ctx, curve.p3, toward(curve.c2, curve.p3), 12);
  if (edge.fromEnd === "arrow") fillTriangle(ctx, curve.p0, toward(curve.c1, curve.p0), 12);
  if (edge.label && !hideLabel) {
    const mid = bezierPoint(curve, 0.5), text = String(edge.label).slice(0, 120);
    ctx.font = "13px " + CV_FONT;
    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    const width = ctx.measureText(text).width + 12;
    ctx.fillStyle = pal.bg;
    roundPath(ctx, mid.x - width / 2, mid.y - 11, width, 22, 6);
    ctx.fill();
    ctx.fillStyle = pal.text;
    ctx.fillText(text, mid.x, mid.y);
  }
  ctx.restore();
}

function paintGrid(ctx, view, width, height, pal) {
  let step = 24 * view.z;
  if (step < 10) step *= 4;
  if (step < 10) return;
  ctx.fillStyle = pal.line;
  const x0 = ((view.x % step) + step) % step, y0 = ((view.y % step) + step) % step;
  for (let x = x0; x < width; x += step) for (let y = y0; y < height; y += step) ctx.fillRect(x - 0.75, y - 0.75, 1.5, 1.5);
}

function singleBox(doc, sel) {
  if (sel.length !== 1 || sel[0][0] === "e") return null;
  const item = cvLookup(doc, sel[0]);
  return validBox(item) ? item : null;
}

function paintOverlay(o) {
  const { ctx, view, pal, ui, doc } = o;
  ctx.setTransform(o.scale, 0, 0, o.scale, 0, 0);
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = pal.accent;
  for (const key of ui.sel) {
    const item = cvLookup(doc, key);
    if (key[0] === "e" || !validBox(item)) continue;
    const a = toScreen(view, item.x, item.y);
    ctx.setLineDash([5, 4]);
    ctx.strokeRect(a.x - 3, a.y - 3, item.width * view.z + 6, item.height * view.z + 6);
    ctx.setLineDash([]);
  }
  const solo = ui.tool === "select" && !ui.drag ? singleBox(doc, [...ui.sel]) : null;
  if (solo) {
    for (const [x, y] of [[solo.x, solo.y], [solo.x + solo.width, solo.y], [solo.x, solo.y + solo.height], [solo.x + solo.width, solo.y + solo.height]]) {
      const p = toScreen(view, x, y);
      ctx.fillStyle = pal.panel;
      ctx.fillRect(p.x - 4, p.y - 4, 8, 8);
      ctx.strokeRect(p.x - 4, p.y - 4, 8, 8);
    }
  }
  const handleKeys = ui.tool === "select" && (!ui.drag || ui.drag.mode === "connect") ? [ui.hover, ui.sel.size === 1 ? [...ui.sel][0] : null] : [];
  for (const key of new Set(handleKeys)) {
    const node = key && key[0] === "n" ? cvLookup(doc, key) : null;
    if (!validBox(node)) continue;
    for (const side of CV_SIDE_NAMES) {
      const anchor = sideAnchor(node, side), p = toScreen(view, anchor.x, anchor.y);
      ctx.beginPath();
      ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
      ctx.fillStyle = pal.accent;
      ctx.fill();
    }
  }
  const drag = ui.drag;
  if (drag && drag.mode === "marquee" && drag.s2) {
    const box = normRect(drag.s.x, drag.s.y, drag.s2.x, drag.s2.y);
    ctx.globalAlpha = 0.12;
    ctx.fillStyle = pal.accent;
    ctx.fillRect(box.x, box.y, box.width, box.height);
    ctx.globalAlpha = 1;
    ctx.strokeRect(box.x, box.y, box.width, box.height);
  }
  if (drag && drag.mode === "connect" && drag.s2) {
    const from = toScreen(view, sideAnchor(drag.from, drag.side).x, sideAnchor(drag.from, drag.side).y);
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(drag.s2.x, drag.s2.y);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  if (ui.eraser) {
    ctx.setLineDash([]);
    ctx.lineWidth = 1;
    ctx.strokeStyle = pal.muted;
    ctx.beginPath();
    ctx.arc(ui.eraser.x, ui.eraser.y, Math.max(2, ui.eraser.r), 0, Math.PI * 2);
    ctx.stroke();
    ctx.strokeStyle = pal.accent;
  }
  if (drag && drag.mode === "shape" && drag.tool === "card") {
    const a = toScreen(view, drag.x0, drag.y0), b = toScreen(view, drag.x1, drag.y1), box = normRect(a.x, a.y, b.x, b.y);
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(box.x, box.y, box.width, box.height);
    ctx.setLineDash([]);
  }
}

// o: {ctx, doc, view, w, h, pal, scale, ui, images, flat}; ui is null for export (no grid, handles or selection),
// images(node) gives a loaded picture of a file card or null, flat paints cork without its texture (the fill tool
// floods colors, and the speckles would stop it everywhere).
function paintScene(o) {
  const { ctx, doc, view, pal, ui } = o;
  const k = o.scale, cork = cvCork(doc), background = cvBackground(doc);
  ctx.setTransform(k, 0, 0, k, 0, 0);
  ctx.fillStyle = background || (cork ? CV_CORK[pal.dark ? "dark" : "light"] : pal.bg);
  ctx.fillRect(0, 0, o.w, o.h);
  if (ui && !cork) paintGrid(ctx, view, o.w, o.h, pal);
  ctx.setTransform(k * view.z, 0, 0, k * view.z, k * view.x, k * view.y);
  const vis = { x: -view.x / view.z - 40, y: -view.y / view.z - 40, width: o.w / view.z + 80, height: o.h / view.z + 80 };
  if (cork && !background && !o.flat) {
    const pattern = corkPattern(ctx, pal.dark);
    if (pattern) { ctx.fillStyle = pattern; ctx.fillRect(vis.x, vis.y, vis.width, vis.height); }
  }
  const editing = ui && ui.editing;
  const picture = (node) => ((node.type === "file" || node.type === "link") && o.images ? o.images(node) : null);
  const nodes = docNodes(doc), map = new Map(nodes.map((n) => [n.id, n]));
  for (const node of nodes) if (node.type === "group" && rectsIntersect(node, vis)) paintGroup(ctx, node, pal, editing === cvKey("n", node));
  const edges = docEdges(doc), selected = (edge) => Boolean(ui && ui.sel.has(cvKey("e", edge)));
  if (!cork) {
    for (const edge of edges) {
      const curve = edgeCurveFor(map, edge, false);
      if (curve) paintEdge(ctx, curve, edge, pal, selected(edge), editing === cvKey("e", edge));
    }
  }
  for (const node of nodes) {
    if (node.type === "group" || !rectsIntersect(node, vis)) continue;
    if (cork) paintCorkNode(ctx, node, pal, editing === cvKey("n", node), picture(node));
    else paintNode(ctx, node, pal, editing === cvKey("n", node), picture(node));
    paintFileBadge(ctx, node, o.media ? o.media(node) : null, cork);
  }
  if (cork) {
    // Thread goes over the paper from pin to pin; every card has its pin, a group only when thread is tied to it.
    // A thread end tied to a spot of the card gets its own pin there.
    const pinned = new Set(), spots = [];
    for (const edge of edges) {
      const curve = edgeCurveFor(map, edge, true);
      if (!curve) continue;
      paintThread(ctx, curve, edge, pal, selected(edge), editing === cvKey("e", edge));
      for (const [id, end] of [[edge.fromNode, "from"], [edge.toNode, "to"]]) {
        const spot = edgeAnchor(edge, end);
        if (spot) spots.push([map.get(id), spot]); else pinned.add(id);
      }
    }
    for (const node of nodes) {
      if ((node.type !== "group" || pinned.has(node.id)) && rectsIntersect(node, vis)) paintPin(ctx, pinPoint(node), pinColor(node));
    }
    for (const [node, spot] of spots) paintPin(ctx, pinPoint(node, spot), pinColor(node));
  }
  for (const el of docElements(doc)) if (rectsIntersect(el, vis)) paintElement(ctx, el, pal, editing === cvKey("x", el));
  if (ui && ui.draft) paintElement(ctx, ui.draft, pal, false);
  if (ui) {
    // The ends of a selected edge can be dragged to another spot of their card.
    for (const edge of edges) {
      const curve = selected(edge) && edgeCurveFor(map, edge, cork);
      if (curve) for (const p of [curve.p0, curve.p3]) paintEndHandle(ctx, p, pal, view.z);
    }
    if (ui.thread) paintThreadDraft(ctx, ui.thread, pal, cork, view.z);
  }
  if (ui && cork) { ctx.setTransform(k, 0, 0, k, 0, 0); paintVignette(ctx, o.w, o.h); }
  if (ui) paintOverlay({ ...o, ui });
}

function cvDraw() {
  if (cv.drawPending || !cv.ctx) return;
  cv.drawPending = true;
  requestAnimationFrame(() => {
    cv.drawPending = false;
    if (!cv.ctx) return;
    const pal = cvPalette();
    if (!cv.doc) {
      cv.ctx.setTransform(cv.dpr, 0, 0, cv.dpr, 0, 0);
      cv.ctx.fillStyle = pal.bg;
      cv.ctx.fillRect(0, 0, cv.w, cv.h);
      return;
    }
    const eraser = cv.tool === "eraser" && cv.eraser === "part" && cv.cursor ? { ...cv.cursor, r: cvEraserRadius() * cv.view.z } : null;
    const ui = { sel: new Set(cv.sel), hover: cv.hover, drag: cv.drag, editing: cv.editing && cv.editing.key, tool: cv.tool, draft: cvDraft(), eraser, thread: cvThreadDraft() };
    paintScene({ ctx: cv.ctx, doc: cv.doc, view: cv.view, w: cv.w, h: cv.h, pal, scale: cv.dpr, ui, images: cvImageFor, media: cvMediaState });
    cvPlaceInline();
  });
}

function cvThreadDraft() {
  const start = cv.tool === "thread" && cv.thread && cvLookup(cv.doc, "n:" + cv.thread.node);
  if (!validBox(start) || !cv.threadAt) return null;
  return { a: anchorPoint(start, cv.thread.frac, cvCork(cv.doc)), b: cv.threadAt };
}

function cvResize() {
  const el = cv.el;
  if (!el) return;
  const box = el.getBoundingClientRect();
  cv.w = Math.max(1, Math.floor(box.width));
  cv.h = Math.max(1, Math.floor(box.height));
  cv.dpr = window.devicePixelRatio || 1;
  el.width = Math.round(cv.w * cv.dpr);
  el.height = Math.round(cv.h * cv.dpr);
  cvDraw();
}

function cvZoomLabel() {
  if (cv.ui.zoom) cv.ui.zoom.textContent = Math.round(cv.view.z * 100) + "%";
}

function cvSetView(view) {
  cv.view = view;
  cvZoomLabel();
  cvDraw();
}

function cvFit() {
  if (!cv.el || !cv.doc) return;
  cvSetView(fitView(sceneBounds(cv.doc), cv.w, cv.h));
}

function cvExport() {
  const bounds = cv.doc && sceneBounds(cv.doc);
  if (!bounds) { toast("Nothing to export"); return; }
  const pad = 32, width = Math.ceil(bounds.width + pad * 2), height = Math.ceil(bounds.height + pad * 2);
  const scale = Math.max(0.25, Math.min(2, 8000 / Math.max(width, height)));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  paintScene({ ctx: canvas.getContext("2d"), doc: cv.doc, view: { x: pad - bounds.x, y: pad - bounds.y, z: 1 }, w: width, h: height, pal: cvPalette(), scale, ui: null, images: cvImageFor });
  canvas.toBlob((blob) => {
    if (!blob) { toast("Could not export the image"); return; }
    const url = URL.createObjectURL(blob);
    const link = h("a", { href: url, download: (cv.name || "canvas") + ".png" });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }, "image/png");
}

function cvIcon(name, weight) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg"), path = document.createElementNS(ns, "path");
  const attrs = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": String(weight || 1.8), "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" };
  for (const [key, value] of Object.entries(attrs)) svg.setAttribute(key, value);
  path.setAttribute("d", CV_ICONS[name] || "");
  svg.append(path);
  return svg;
}

// ---- canvas interaction ----
function cvSelect(keys) {
  cv.sel = keys;
  const only = keys.length === 1 && keys[0][0] === "x" ? cvLookup(cv.doc, keys[0]) : null;
  if (only && only.type !== "text" && only.type !== "paint") {
    cv.style = {
      stroke: typeof only.stroke === "string" ? only.stroke : cv.style.stroke,
      fill: Boolean(only.fill),
      width: cvNum(only.strokeWidth, cv.style.width),
      rough: cv.style.rough,
    };
  }
  cvSync();
  cvDraw();
}

function cvSetTool(tool) {
  cvCloseMenu();
  cv.tool = tool;
  cv.thread = null;
  cv.hover = null;
  cvSync();
  cvCursor();
  cvDraw();
}

function cvCursor() {
  if (!cv.el) return;
  const panning = cv.space || cv.tool === "hand";
  cv.el.style.cursor = panning ? (cv.drag && cv.drag.mode === "pan" ? "grabbing" : "grab") : cv.tool === "select" ? (cv.hover ? "move" : "default") : "crosshair";
}

function cvSync() {
  const ui = cv.ui;
  if (!ui.tools) return;
  cvRenderLayers();
  for (const [tool, button] of Object.entries(ui.tools)) button.classList.toggle("on", tool === cv.tool);
  CV_INK.forEach((color, i) => ui.ink[i].classList.toggle("on", color === cv.style.stroke));
  const custom = !CV_INK.includes(cv.style.stroke);
  ui.customWrap.classList.toggle("on", custom);
  ui.customWrap.style.background = custom ? cv.style.stroke : "";
  if (custom && /^#[0-9a-fA-F]{6}$/.test(cv.style.stroke) && ui.custom.value !== cv.style.stroke.toLowerCase()) ui.custom.value = cv.style.stroke.toLowerCase();
  ui.fill.classList.toggle("on", cv.style.fill);
  if (ui.cork) ui.cork.classList.toggle("on", cvCork(cv.doc));
  if (document.activeElement !== ui.width) ui.width.value = String(widthToSlider(cv.style.width));
  if (document.activeElement !== ui.widthValue) ui.widthValue.value = String(cv.style.width);
  ui.undo.disabled = !cv.hist || !cv.hist.undo.length;
  ui.redo.disabled = !cv.hist || !cv.hist.redo.length;
  cvZoomLabel();
  if (ui.empty) ui.empty.style.display = cv.doc ? "none" : "grid";
}

// Changing the style also restyles the selection.
function cvStyle(patch) {
  Object.assign(cv.style, patch);
  if (patch.width !== undefined || patch.rough !== undefined) cvSavePrefs();
  if (cv.doc && cv.sel.length) {
    applyStyle(cv.doc, cv.sel, {
      stroke: patch.stroke, strokeWidth: patch.width, roughness: patch.rough,
      fill: patch.fill !== undefined ? (cv.style.fill ? cv.style.stroke : null) : undefined,
    });
    cvCommit("style");
  }
  cvSync();
  cvDraw();
}

function cvPoint(event) {
  const box = cv.el.getBoundingClientRect();
  const s = { x: event.clientX - box.left, y: event.clientY - box.top };
  return { s, w: toWorld(cv.view, s.x, s.y) };
}

function cvDraftGeometry(d) {
  let x1 = d.x1, y1 = d.y1;
  if (d.shift) {
    const dx = x1 - d.x0, dy = y1 - d.y0;
    if (d.tool === "line" || d.tool === "arrow") {
      const snapped = snapAngle(dx, dy);
      x1 = d.x0 + snapped.dx;
      y1 = d.y0 + snapped.dy;
    } else {
      const size = Math.max(Math.abs(dx), Math.abs(dy));
      x1 = d.x0 + (dx < 0 ? -size : size);
      y1 = d.y0 + (dy < 0 ? -size : size);
    }
  }
  return { x1, y1 };
}

function cvDraft() {
  return cv.drag ? cvDraftOf(cv.drag) : null;
}

function cvDraftOf(d) {
  if (d.mode === "pen" && d.pts.length > 1) return makeFreedraw(d.pts, cv.style, d.seed);
  if (d.mode !== "shape" || d.tool === "card") return null;
  const { x1, y1 } = cvDraftGeometry(d);
  return d.tool === "line" || d.tool === "arrow" ? makeLinear(d.tool, d.x0, d.y0, x1, y1, cv.style, d.seed) : makeShape(d.tool, d.x0, d.y0, x1, y1, cv.style, d.seed);
}

function cvHoverKey(w) {
  if (cv.tool !== "select") return null;
  const nodes = docNodes(cv.doc), pad = 12 / cv.view.z;
  for (let i = nodes.length - 1; i >= 0; i--) if (nodes[i].type !== "group" && boxContains(nodes[i], w.x, w.y, pad)) return cvKey("n", nodes[i]);
  return null;
}

function cvNodeAt(w) {
  const nodes = docNodes(cv.doc);
  for (let i = nodes.length - 1; i >= 0; i--) if (nodes[i].type !== "group" && boxContains(nodes[i], w.x, w.y)) return nodes[i];
  for (let i = nodes.length - 1; i >= 0; i--) if (boxContains(nodes[i], w.x, w.y)) return nodes[i];
  return null;
}

// The four side dots of the hovered or selected card; dragging one draws an edge.
function cvSideHandle(s) {
  const keys = [cv.hover, cv.sel.length === 1 ? cv.sel[0] : null];
  for (const key of keys) {
    const node = key && key[0] === "n" ? cvLookup(cv.doc, key) : null;
    if (!validBox(node)) continue;
    for (const side of CV_SIDE_NAMES) {
      const a = sideAnchor(node, side), p = toScreen(cv.view, a.x, a.y);
      if (Math.hypot(p.x - s.x, p.y - s.y) <= 9) return { node, side };
    }
  }
  return null;
}

function cvDown(event) {
  if (!cv.doc || (event.button !== 0 && event.button !== 1)) return;
  event.preventDefault();
  const wasEditing = Boolean(cv.editing);
  if (cv.editing) cvEndEdit();
  cv.el.focus();
  if (cv.el.setPointerCapture) cv.el.setPointerCapture(event.pointerId);
  const { s, w } = cvPoint(event);
  // A PDF shown in its card closes when something else is clicked.
  if (cv.inline && hitTest(cv.doc, w.x, w.y, cv.view.z) !== "n:" + cv.inline.id) cvCloseInline();
  if (event.button === 1 || cv.tool === "hand" || cv.space) { cv.drag = { mode: "pan", s, view: { ...cv.view } }; cvCursor(); return; }
  if (cv.tool === "select") { cvDownSelect(event, s, w); return; }
  // The tool stays active, so the click that closes a card or text editor only closes it.
  if (wasEditing && (cv.tool === "text" || cv.tool === "card" || cv.tool === "thread")) return;
  if (cv.tool === "fill") { cvBucket(w, s, event.altKey); return; }
  if (cv.tool === "eraser") { cv.drag = { mode: "erase", removed: 0, last: null }; cvErase(w); return; }
  if (cv.tool === "thread") { cvThreadClick(w); return; }
  if (cv.sel.length) cvSelect([]);
  if (cv.tool === "freedraw") { cv.drag = { mode: "pen", pts: [[w.x, w.y]], seed: cvSeed() }; return; }
  if (cv.tool === "text") {
    const key = hitTest(cv.doc, w.x, w.y, cv.view.z), item = key && key[0] === "x" ? cvLookup(cv.doc, key) : null;
    if (item && item.type === "text") { cvSelect([key]); cvStartEdit(key); return; }
    cvNewText(w);
    return;
  }
  cv.drag = { mode: "shape", tool: cv.tool, x0: w.x, y0: w.y, x1: w.x, y1: w.y, shift: event.shiftKey, seed: cvSeed() };
}

function cvDownSelect(event, s, w) {
  const solo = singleBox(cv.doc, cv.sel);
  const handle = solo && handleAt(solo, s.x, s.y, cv.view);
  if (handle) { cv.drag = { mode: "resize", handle, key: cv.sel[0], orig: cvClone(solo), start: w, moved: false }; return; }
  const end = cvEdgeEndAt(s);
  if (end) { cv.drag = { mode: "anchor", key: end.key, end: end.end, moved: false }; return; }
  const side = cvSideHandle(s);
  if (side) { cv.drag = { mode: "connect", from: side.node, side: side.side, s, s2: null }; return; }
  const key = hitTest(cv.doc, w.x, w.y, cv.view.z);
  if (!key) {
    if (!event.shiftKey) cvSelect([]);
    cv.drag = { mode: "marquee", s, s2: null, w, base: event.shiftKey ? cv.sel.slice() : [] };
    return;
  }
  if (event.shiftKey) {
    if (cv.sel.includes(key)) { cvSelect(cv.sel.filter((k) => k !== key)); return; }
    cvSelect([...cv.sel, key]);
  } else if (!cv.sel.includes(key)) {
    cvSelect([key]);
  }
  const keys = new Set(cv.sel.filter((k) => k[0] !== "e"));
  for (const k of cv.sel) {
    const item = cvLookup(cv.doc, k);
    if (k[0] === "n" && item && item.type === "group") for (const inner of containedIds(cv.doc, item)) keys.add(inner);
  }
  cv.drag = { mode: "move", keys: [...keys], s, last: w, armed: false, key };
}

function cvMove(event) {
  if (!cv.doc) return;
  const { s, w } = cvPoint(event);
  const d = cv.drag;
  if (cv.tool === "eraser" && cv.eraser === "part") { cv.cursor = s; cvDraw(); }
  if (cv.tool === "thread") { cv.threadAt = w; if (cv.thread) cvDraw(); }
  if (!d) {
    const key = cvHoverKey(w);
    if (key !== cv.hover) { cv.hover = key; cvCursor(); cvDraw(); }
    return;
  }
  if (d.mode === "pan") {
    cvSetView({ ...d.view, x: d.view.x + s.x - d.s.x, y: d.view.y + s.y - d.s.y });
    return;
  }
  if (d.mode === "move") {
    if (!d.armed) {
      if (Math.hypot(s.x - d.s.x, s.y - d.s.y) < 3) return;
      d.armed = true;
    }
    moveItems(cv.doc, d.keys, w.x - d.last.x, w.y - d.last.y);
    d.last = w;
  } else if (d.mode === "resize") {
    const item = cvLookup(cv.doc, d.key);
    if (!item) return;
    applyBox(item, d.orig, resizeBox(d.orig, d.handle, w.x - d.start.x, w.y - d.start.y));
    d.moved = true;
  } else if (d.mode === "anchor") {
    if (cvMoveEnd(d, w)) d.moved = true;
  } else if (d.mode === "marquee" || d.mode === "connect") {
    d.s2 = s;
    d.w2 = w;
  } else if (d.mode === "shape") {
    d.x1 = w.x;
    d.y1 = w.y;
    d.shift = event.shiftKey;
  } else if (d.mode === "pen") {
    const last = d.pts[d.pts.length - 1];
    if (Math.hypot(w.x - last[0], w.y - last[1]) * cv.view.z > 1.5) d.pts.push([w.x, w.y]);
  } else if (d.mode === "erase") {
    cvErase(w);
  }
  cvDraw();
}

function cvUp(event) {
  const d = cv.drag;
  if (!d) return;
  cv.drag = null;
  const { w } = cvPoint(event);
  if (d.mode === "move") {
    if (d.armed) cvCommit("move");
    else if (!event.shiftKey) cvClickCard(d.key, w);
  } else if (d.mode === "resize") {
    if (d.moved) cvCommit("resize");
  } else if (d.mode === "anchor") {
    if (d.moved) cvCommit("thread end");
  } else if (d.mode === "marquee") {
    const box = normRect(d.w.x, d.w.y, w.x, w.y), picked = [];
    for (const node of docNodes(cv.doc)) if (node.type === "group" ? boxInside(node, box) : rectsIntersect(node, box)) picked.push(cvKey("n", node));
    for (const el of docElements(cv.doc)) if (rectsIntersect(el, box)) picked.push(cvKey("x", el));
    cvSelect([...new Set([...d.base, ...picked])]);
  } else if (d.mode === "connect") {
    cvFinishConnect(d, w);
  } else if (d.mode === "shape") {
    d.x1 = w.x;
    d.y1 = w.y;
    d.shift = event.shiftKey;
    cvFinishShape(d);
  } else if (d.mode === "pen") {
    if (d.pts.length > 1) {
      ensureElements(cv.doc).push(makeFreedraw(d.pts, cv.style, d.seed));
      cvCommit("draw");
    }
  } else if (d.mode === "erase") {
    if (d.removed) cvCommit("erase");
  }
  cvCursor();
  cvDraw();
}

function cvCancelDrag() {
  if (!cv.drag) return;
  const mode = cv.drag.mode;
  cv.drag = null;
  if ((mode === "move" || mode === "resize" || mode === "erase" || mode === "anchor") && cv.hist) cv.doc = JSON.parse(cv.hist.cur);
  cv.sel = cv.doc ? cv.sel.filter((key) => cvLookup(cv.doc, key)) : [];
  cvCursor();
  cvDraw();
}

function cvFinishShape(d) {
  const { x1, y1 } = cvDraftGeometry(d);
  const big = Math.hypot(x1 - d.x0, y1 - d.y0) * cv.view.z >= 4;
  if (d.tool === "card") {
    const box = big ? normRect(d.x0, d.y0, x1, y1) : { x: d.x0, y: d.y0, width: 260, height: 120 };
    const node = { id: cvId(), type: "text", text: "", x: box.x, y: box.y, width: Math.max(80, box.width), height: Math.max(48, box.height) };
    ensureList(cv.doc, "nodes").push(node);
    cvSelect([cvKey("n", node)]);
    cvStartEdit(cvKey("n", node));
    return;
  }
  if (!big) return;
  const el = cvDraftOf(d);
  if (!el) return;
  ensureElements(cv.doc).push(el);
  cvSelect([cvKey("x", el)]);
  cvCommit("draw");
}

function cvNewText(w) {
  const size = 24;
  const el = { id: cvId(), type: "text", x: w.x, y: w.y, width: 10, height: size * 1.25, stroke: cv.style.stroke, fill: null, strokeWidth: cv.style.width, roughness: cv.style.rough, seed: cvSeed(), text: "", fontSize: size };
  ensureElements(cv.doc).push(el);
  cvSelect([cvKey("x", el)]);
  cvStartEdit(cvKey("x", el));
}

// The scene as pixels, drawn like the screen without grid or selection; null where no canvas can be made.
function cvSnapshot() {
  if (!cv.doc || !cv.w || !cv.h) return null;
  const canvas = document.createElement("canvas");
  if (!canvas || typeof canvas.getContext !== "function") return null;
  const k = Math.min(2, cv.dpr || 1), w = Math.round(cv.w * k), h = Math.round(cv.h * k);
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  paintScene({ ctx, doc: cv.doc, view: cv.view, w: cv.w, h: cv.h, pal: cvPalette(), scale: k, ui: null, images: cvImageFor, flat: true });
  const image = ctx.getImageData(0, 0, w, h);
  return image && image.data ? { data: image.data, w, h, k } : null;
}

// Like a paint program: the area of the clicked color, bounded by anything else, gets the color as a paint element.
// Cards, groups and edges take the color, a click on a line or text recolors it, and an area that runs out of
// the view falls back to filling the shape under it or the background. Alt+click clears instead.
function cvBucket(w, s, clear) {
  const color = clear ? null : cv.style.stroke;
  const tol = 6 / cv.view.z;
  const key = fillTarget(cv.doc, w.x, w.y, cv.view.z), item = key && cvLookup(cv.doc, key);
  if (key && key[0] !== "x") { if (applyFill(cv.doc, key, color)) cvCommit("fill"); return; }
  if (item && onInk(item, w.x, w.y, tol)) {
    if (color !== null && item.stroke !== color) { item.stroke = color; cvCommit("fill"); }
    return;
  }
  if (color !== null && !(item && item.type === "paint" && item.fill === color)) {
    const shot = cvSnapshot();
    const px = shot && Math.floor(s.x * shot.k), py = shot && Math.floor(s.y * shot.k);
    if (shot && px >= 0 && py >= 0 && px < shot.w && py < shot.h) {
      const region = floodRegion(shot.data, shot.w, shot.h, px, py, CV_FILL_TOLERANCE);
      const paint = !region.touches && paintFromMask(growMask(region.mask, shot.w, shot.h), shot.w, shot.h, cv.view, shot.k, color);
      if (paint) {
        const list = ensureElements(cv.doc), at = item ? list.indexOf(item) : -1;
        // Above a filled shape it was poured into, under an empty outline so the line stays on top.
        list.splice(at < 0 ? 0 : item.fill ? at + 1 : at, 0, paint);
        cvCommit("fill");
        return;
      }
    }
  }
  if (key ? applyFill(cv.doc, key, color) : setBackground(cv.doc, color)) cvCommit("fill");
}

// Released on another card: an edge to it. Released on empty canvas (after a real drag): a new card there,
// connected and open for typing, like Obsidian.
// On a detective board the thread is tied where it was pulled from (that side's dot, not the pin on top) and where
// it was let go on the other card; a new card gets it on the side facing the first one.
const CV_SIDE_SPOTS = { top: [0.5, 0], right: [1, 0.5], bottom: [0.5, 1], left: [0, 0.5] };
function cvFinishConnect(d, w) {
  const target = cvNodeAt(w), cork = cvCork(cv.doc);
  if (target && target.id === d.from.id) return;
  const spots = (to) => (cork ? { unlawFrom: CV_SIDE_SPOTS[d.side].slice(), unlawTo: to } : {});
  if (!target) {
    if (!d.s2 || Math.hypot(d.s2.x - d.s.x, d.s2.y - d.s.y) < 24) return;
    const card = cvNewCardAt(w), c = { x: d.from.x + d.from.width / 2, y: d.from.y + d.from.height / 2 }, side = nearestSide(card, c.x, c.y);
    ensureList(cv.doc, "edges").push({ id: cvId(), fromNode: d.from.id, fromSide: d.side, toNode: card.id, toSide: side, toEnd: "arrow", ...spots(CV_SIDE_SPOTS[side].slice()) });
    cvSelect([cvKey("n", card)]);
    // Like the card tool: the card, the edge and the typed text become one undo step when the editor closes.
    cvStartEdit(cvKey("n", card));
    if (!cv.editing) cvCommit("connect");
    return;
  }
  const edge = { id: cvId(), fromNode: d.from.id, fromSide: d.side, toNode: target.id, toSide: nearestSide(target, w.x, w.y), toEnd: "arrow", ...spots(fracAt(target, w, cork)) };
  ensureList(cv.doc, "edges").push(edge);
  cvSelect([cvKey("e", edge)]);
  cvCommit("connect");
}

function cvNewCardAt(w) {
  const node = { id: cvId(), type: "text", text: "", x: Math.round(w.x - 130), y: Math.round(w.y - 60), width: 260, height: 120 };
  ensureList(cv.doc, "nodes").push(node);
  return node;
}

// Thread tool: the first click pins the start on a card at that spot, the second ends it on another card's
// spot, or on empty canvas makes a new card there. Esc or another tool drops a started thread.
function cvThreadClick(w) {
  const cork = cvCork(cv.doc), node = cvNodeAt(w);
  const start = cv.thread && cvLookup(cv.doc, "n:" + cv.thread.node);
  if (!validBox(start)) {
    cv.thread = node ? { node: node.id, frac: fracAt(node, w, cork) } : null;
    cv.threadAt = w;
    if (!node) toast("Click the spot on a card where the thread starts");
    cvDraw();
    return;
  }
  const from = cv.thread.frac;
  cv.thread = null;
  if (node && node.id === start.id) { cvDraw(); return; }
  const a = anchorPoint(start, from, cork), target = node || cvNewCardAt(w);
  const edge = { id: cvId(), fromNode: start.id, fromSide: nearestSide(start, a.x, a.y), toNode: target.id, toSide: nearestSide(target, a.x, a.y), toEnd: "arrow", unlawFrom: from };
  if (node) {
    edge.unlawTo = fracAt(node, w, cork);
    const b = anchorPoint(node, edge.unlawTo, cork);
    edge.toSide = nearestSide(node, b.x, b.y);
  }
  ensureList(cv.doc, "edges").push(edge);
  cvSelect([cvKey(node ? "e" : "n", node ? edge : target)]);
  if (!node) cvStartEdit(cvKey("n", target));
  if (!cv.editing) cvCommit("thread");
}

// An end of the single selected edge under the pointer (screen point), as {key, end}.
function cvEdgeEndAt(s) {
  if (cv.sel.length !== 1 || cv.sel[0][0] !== "e") return null;
  const edge = cvLookup(cv.doc, cv.sel[0]), curve = edge && edgeCurveFor(nodeMap(cv.doc), edge, cvCork(cv.doc));
  if (!curve) return null;
  for (const [p, end] of [[curve.p0, "from"], [curve.p3, "to"]]) {
    const at = toScreen(cv.view, p.x, p.y);
    if (Math.hypot(at.x - s.x, at.y - s.y) <= 9) return { key: cv.sel[0], end };
  }
  return null;
}

function cvMoveEnd(d, w) {
  const edge = cvLookup(cv.doc, d.key), node = edge && cvLookup(cv.doc, "n:" + (d.end === "from" ? edge.fromNode : edge.toNode));
  if (!validBox(node)) return false;
  const cork = cvCork(cv.doc), frac = fracAt(node, w, cork), p = anchorPoint(node, frac, cork);
  edge[d.end === "from" ? "unlawFrom" : "unlawTo"] = frac;
  edge[d.end === "from" ? "fromSide" : "toSide"] = nearestSide(node, p.x, p.y);
  return true;
}

function cvEraserRadius() {
  return Math.max(cv.style.width / 2, 8 / cv.view.z);
}

function cvErase(w) {
  const d = cv.drag;
  if (d && cv.eraser === "part") {
    const r = cvEraserRadius(), from = d.last || w;
    const steps = Math.min(200, Math.max(1, Math.ceil(Math.hypot(w.x - from.x, w.y - from.y) / Math.max(0.5, r / 2))));
    let changed = 0;
    for (let i = 1; i <= steps; i++) changed += eraseAt(cv.doc, from.x + ((w.x - from.x) * i) / steps, from.y + ((w.y - from.y) * i) / steps, r);
    d.last = w;
    if (changed) {
      d.removed += changed;
      cv.sel = cv.sel.filter((k) => cvLookup(cv.doc, k));
      cvDraw();
    }
    return;
  }
  const key = hitTest(cv.doc, w.x, w.y, cv.view.z);
  if (!key || !cv.drag) return;
  if (removeItems(cv.doc, [key])) {
    cv.drag.removed++;
    cv.sel = cv.sel.filter((k) => cvLookup(cv.doc, k));
    cvDraw();
  }
}

// One click works the card in place: a video or sound plays (a click on its bar seeks), a PDF opens in the card,
// a site opens inside the desk, a linked canvas opens. Two clicks open it whole: the viewer, or a site in a new tab.
// The single click waits CV_DOUBLE_MS so a double click never does both.
const CV_DOUBLE_MS = 230;
function cvClickCard(key, w) {
  const node = cv.doc && key[0] === "n" ? cvLookup(cv.doc, key) : null;
  if (!node || (node.type !== "file" && node.type !== "link")) return;
  clearTimeout(cv.clickTimer);
  cv.clickTimer = setTimeout(() => { cv.clickTimer = 0; cvCardAction(key, w); }, CV_DOUBLE_MS);
}
function cvCardAction(key, w) {
  const node = cv.doc && cvLookup(cv.doc, key);
  if (!node) return;
  if (node.type === "link") {
    // A site that refuses to be shown inside other pages would be an empty frame: it opens in a tab instead.
    if (node.unlawPreview && node.unlawPreview.frameable === false) cvOpenInApp(node); else cvView(key);
    return;
  }
  const kind = cvFileKind(node.file);
  if (kind === "canvas") cvFollowLink(node);
  else if (kind === "video" || kind === "audio") cvTogglePlay(node, w);
  else if (kind === "pdf") cvOpenInline(node);
}
function cvCardDouble(key) {
  clearTimeout(cv.clickTimer);
  cv.clickTimer = 0;
  const node = cv.doc && cvLookup(cv.doc, key);
  if (!node) return;
  if (node.type === "link") { cvOpenInApp(node); return; }
  if (cvFileKind(node.file) === "canvas") { cvFollowLink(node); return; }
  cvStopMedia();
  cvCloseInline();
  cvView(key);
}

// ---- cards that play in place: one video or sound at a time, drawn on the canvas from a hidden media element ----
const CV_WAVE_LIMIT = 60 * 1024 * 1024;
const cvWaves = new Map(); // canvas path + file -> peaks 0..1 (null while loading or when it cannot be read)
function cvMediaState(node) {
  if (node.type !== "file") return null;
  const p = cv.playing, file = String(node.file ?? "");
  if (!p || p.id !== node.id || p.path !== cv.path) {
    const peaks = cvWaves.get(cv.path + "\n" + file);
    return peaks ? { kind: "audio", playing: false, progress: 0, peaks, idle: true } : null;
  }
  const m = p.media, duration = Number.isFinite(m.duration) && m.duration > 0 ? m.duration : 0;
  return { kind: p.kind, playing: !m.paused && !m.ended, progress: duration ? Math.min(1, m.currentTime / duration) : 0, peaks: cvWaves.get(p.path + "\n" + p.file) || null, idle: false };
}
function cvTogglePlay(node, w) {
  const file = String(node.file ?? ""), kind = cvFileKind(file), p = cv.playing;
  if (p && p.id === node.id && p.path === cv.path) {
    const m = p.media, box = cvPictureBox(node, cvCork(cv.doc));
    if (w && Number.isFinite(m.duration) && m.duration > 0 && w.y >= box.y + box.height - 22 && w.y <= box.y + box.height + 2) {
      m.currentTime = Math.max(0, Math.min(1, (w.x - box.x) / box.width)) * m.duration;
    } else if (m.paused || m.ended) {
      cvPlay(m);
    } else {
      m.pause();
    }
    cvDraw();
    return;
  }
  cvStopMedia();
  if (typeof document.createElement !== "function") return;
  const media = document.createElement(kind === "video" ? "video" : "audio");
  media.preload = "auto";
  media.playsInline = true;
  media.src = cvMediaUrl(cv.path, file, "&raw=1");
  for (const type of ["loadeddata", "pause", "ended", "seeked"]) media.addEventListener(type, () => cvDraw());
  media.addEventListener("error", () => { if (cv.playing && cv.playing.media === media) toast("Could not play " + file.split("/").pop()); });
  if (cv.ui.players) cv.ui.players.append(media);
  cv.playing = { id: node.id, path: cv.path, file, kind, media };
  cvPlay(media);
  if (kind === "audio") cvLoadWave(cv.path, file);
}
function cvPlay(media) {
  const started = media.play();
  // Stopping a sound that is still starting rejects play() with AbortError: nothing to report then.
  if (started && typeof started.catch === "function") started.catch((error) => { if (error && error.name !== "AbortError") toast("Could not play: " + error.message); });
  cvTick();
}
// Redraws while something plays; stops by itself when it pauses, ends, or its card or canvas is gone.
function cvTick() {
  if (cv.ticking) return;
  cv.ticking = true;
  const step = () => {
    const p = cv.playing;
    if (p && (p.path !== cv.path || !cv.doc || !cvLookup(cv.doc, "n:" + p.id))) { cv.ticking = false; cvStopMedia(); return; }
    if (!p || !cv.ctx || p.media.paused || p.media.ended) { cv.ticking = false; cvDraw(); return; }
    cvDraw();
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
function cvStopMedia() {
  const p = cv.playing;
  if (!p) return;
  cv.playing = null;
  p.media.pause();
  if (typeof p.media.removeAttribute === "function") p.media.removeAttribute("src");
  if (typeof p.media.load === "function") p.media.load(); // lets the browser drop the download
  if (typeof p.media.remove === "function") p.media.remove();
  cvDraw();
}
async function cvLoadWave(path, file) {
  const key = path + "\n" + file;
  if (cvWaves.has(key) || typeof AudioContext !== "function") return;
  cvWaves.set(key, null);
  try {
    const response = await fetch(cvMediaUrl(path, file, "&raw=1"), { cache: "force-cache" });
    if (!response.ok || Number(response.headers.get("Content-Length") || 0) > CV_WAVE_LIMIT) return;
    const buffer = await response.arrayBuffer();
    if (buffer.byteLength > CV_WAVE_LIMIT) return;
    const context = new AudioContext();
    try {
      const sound = await context.decodeAudioData(buffer);
      cvWaves.set(key, cvPeaks(sound.getChannelData(0), 160));
    } finally {
      context.close();
    }
    cvDraw();
  } catch {
    // No wave for this sound: the progress bar alone.
  }
}
function cvPeaks(samples, count) {
  // Every sample of a slice would be millions for a song: about 256 of them are enough for its loudest point.
  const peaks = [], step = Math.max(1, Math.floor(samples.length / count)), stride = Math.max(1, Math.floor(step / 256));
  for (let i = 0; i < count; i++) {
    let top = 0;
    for (let j = i * step, end = Math.min(samples.length, (i + 1) * step); j < end; j += stride) top = Math.max(top, Math.abs(samples[j]));
    peaks.push(top);
  }
  const loudest = Math.max(0.01, ...peaks);
  return peaks.map((peak) => peak / loudest);
}

// ---- a PDF read inside its card: a live frame over the card's picture, moved and turned with it ----
function cvOpenInline(node) {
  if (cv.inline && cv.inline.id === node.id && cv.inline.path === cv.path) return;
  cvCloseInline();
  const layer = cv.ui.inline;
  if (!layer) return;
  const file = String(node.file ?? ""), frame = h("iframe", { src: cvMediaUrl(cv.path, file, "&raw=1") + "#view=FitH", title: file.split("/").pop() });
  layer.append(frame);
  cv.inline = { id: node.id, path: cv.path, frame };
  cvPlaceInline();
}
function cvCloseInline() {
  const inline = cv.inline;
  if (!inline) return;
  cv.inline = null;
  if (typeof inline.frame.remove === "function") inline.frame.remove();
}
function cvPlaceInline() {
  const inline = cv.inline;
  if (!inline) return;
  const node = inline.path === cv.path && cv.doc ? cvLookup(cv.doc, "n:" + inline.id) : null;
  if (!node || cvHidden(node)) { cvCloseInline(); return; }
  const cork = cvCork(cv.doc), box = cvPictureBox(node, cork), z = cv.view.z, at = toScreen(cv.view, box.x, box.y);
  const origin = (node.x + node.width / 2 - box.x) * z + "px " + (node.y + node.height / 2 - box.y) * z + "px";
  Object.assign(inline.frame.style, {
    left: at.x + "px", top: at.y + "px", width: box.width * z + "px", height: box.height * z + "px",
    transformOrigin: origin, transform: cork ? "rotate(" + nodeTilt(node) + "rad)" : "",
  });
}

// ---- links between canvases: a file card naming a .canvas opens it; Back returns ----
// A card's path is relative to its canvas's folder (like attachments) or absolute for a canvas elsewhere.
function canvasLinkPath(from, file) {
  const name = String(file ?? ""), joined = name.startsWith("/") ? name : String(from || "").replace(/\/[^/]*$/, "") + "/" + name, parts = [];
  for (const part of joined.split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") parts.pop(); else parts.push(part);
  }
  return "/" + parts.join("/");
}
function canvasLinkFile(from, target) {
  const folder = String(from || "").replace(/\/[^/]*$/, "") + "/";
  return target.startsWith(folder) ? target.slice(folder.length) : target;
}
async function cvFollowLink(node) {
  const from = cv.path, target = canvasLinkPath(from, node.file);
  if (!from || target === from) return;
  if (await cvOpen(target, false)) {
    cv.back = [...cv.back, from].slice(-30);
    cvFillPick();
  }
}
async function cvGoBack() {
  const from = cv.back[cv.back.length - 1];
  if (!from) return;
  cv.back = cv.back.slice(0, -1);
  await cvOpen(from, false);
  cvFillPick();
}
function cvAddCanvasLink(item) {
  if (!cv.doc || !cv.path || item.path === cv.path) return;
  const center = toWorld(cv.view, cv.w / 2, cv.h / 2);
  const node = { id: cvId(), type: "file", file: canvasLinkFile(cv.path, item.path), x: Math.round(center.x - 150), y: Math.round(center.y - 110), width: 300, height: 220 };
  ensureList(cv.doc, "nodes").push(node);
  cvToggleGallery(false);
  cvSelect([cvKey("n", node)]);
  cvCommit("canvas link");
  toast("\u201c" + item.name + "\u201d is linked: click the card to open it");
}
// Another canvas as a picture for its card, read without switching to it (cleared when the open canvas changes).
const cvCanvasThumbs = new Map();
function cvCanvasThumb(path) {
  let entry = cvCanvasThumbs.get(path);
  if (!entry) {
    entry = { image: null };
    cvCanvasThumbs.set(path, entry);
    cvMakeCanvasThumb(path, entry);
  }
  return entry.image;
}
async function cvMakeCanvasThumb(path, entry) {
  if (typeof document.createElement !== "function") return;
  const { status, data } = await api("GET", "/api/canvas/peek?path=" + encodeURIComponent(path));
  if (status !== 200 || !data.canvas || cvCanvasThumbs.get(path) !== entry) return;
  const picture = document.createElement("canvas"), width = 240, height = 150;
  const ctx = picture.getContext && picture.getContext("2d");
  if (!ctx) return;
  picture.width = width * 2;
  picture.height = height * 2;
  paintScene({ ctx, doc: data.canvas, view: fitView(sceneBounds(data.canvas), width, height, 12), w: width, h: height, pal: cvPalette(), scale: 2, ui: null, images: null, flat: true });
  entry.image = picture;
  cvDraw();
}

// A text card holding only a web address (or a title line above one) is a link card.
function urlCardText(text) {
  const lines = String(text ?? "").split("\n").map((line) => line.trim()).filter(Boolean);
  if (!lines.length || lines.length > 2 || !cvHttpUrl(lines[lines.length - 1])) return null;
  if (lines.length === 2 && (lines[0].length > 200 || cvHttpUrl(lines[0]))) return null;
  return { url: lines[lines.length - 1], title: lines.length === 2 ? lines[0] : "" };
}
function textToLink(node) {
  const found = node && typeof node === "object" && node.type === "text" ? urlCardText(node.text) : null;
  if (!found) return false;
  node.type = "link";
  node.url = found.url;
  delete node.text;
  if (found.title) node.unlawPreview = { title: found.title, description: "", site: "", image: null };
  return true;
}

// Pictures of file cards: the file itself for images, a Quick Look thumbnail for anything else (PDF, documents).
// Loaded once per canvas and file; a failed one is not asked again, so the card stays a plain document.
const cvImages = new Map();
function cvImageFor(node) {
  if (node.type === "link") {
    // Cards from before logos (no icon key) ask once for the site's logo.
    const preview = node.unlawPreview && typeof node.unlawPreview === "object" ? node.unlawPreview : null;
    if (!preview || !("icon" in preview)) cvFetchPreview(node, true);
    return preview && typeof preview.icon === "string" && preview.icon ? cvImageFor({ file: preview.icon }) : null;
  }
  const file = String(node.file ?? ""), p = cv.playing;
  if (p && p.kind === "video" && p.id === node.id && p.path === cv.path && p.media.readyState >= 2) return p.media;
  if (CV_CANVAS_FILE.test(file)) return cv.path ? cvCanvasThumb(canvasLinkPath(cv.path, file)) : null;
  if (!file || !cv.path || noteName(file) || CV_PLAIN_FILE.test(file) || typeof Image !== "function") return null;
  if (CV_MODEL.test(file)) {
    const still = cvStills.get(cv.path + "\n" + file);
    if (still && still.image) return still.image;
    if (!still && typeof document.createElement === "function") cvModelStill(cv.path, file);
  }
  const key = cv.path + "\n" + file;
  let entry = cvImages.get(key);
  if (!entry) {
    const image = new Image();
    entry = { image, ok: false };
    image.onload = () => { entry.ok = true; cvDraw(); };
    image.src = "/media/canvas?t=" + encodeURIComponent(TOKEN) + "&path=" + encodeURIComponent(cv.path) + "&file=" + encodeURIComponent(file) + (CV_IMAGE_FILE.test(file) ? "" : "&thumb=1");
    cvImages.set(key, entry);
  }
  return entry.ok ? entry.image : null;
}

function cvLocalImageSize(file) {
  return new Promise((resolve) => {
    if (typeof Image !== "function" || !/^image\//.test(file.type || "") || typeof URL.createObjectURL !== "function") { resolve(null); return; }
    const url = URL.createObjectURL(file), image = new Image();
    const done = (size) => { URL.revokeObjectURL(url); resolve(size); };
    image.onload = () => done({ w: image.naturalWidth, h: image.naturalHeight });
    image.onerror = () => done(null);
    image.src = url;
  });
}

// Copy files next to the canvas (attachments/) and pin a card for each at `at` (world point; default: view center).
async function cvAddFiles(files, at) {
  const list = Array.from(files || []).slice(0, 30);
  if (!list.length) return;
  if (!cv.doc || !cv.path) { toast("Open or create a canvas first"); return; }
  const path = cv.path;
  const center = at || toWorld(cv.view, cv.w / 2, cv.h / 2);
  const added = [];
  for (const [i, file] of list.entries()) {
    if (file.size > CV_MAX_UPLOAD) { toast(file.name + " is larger than 256 MB"); continue; }
    cvStatus("Adding " + file.name + "…");
    let response, data = {};
    try {
      response = await fetch("/api/canvas/upload?path=" + encodeURIComponent(path) + "&name=" + encodeURIComponent(file.name || "file"), {
        method: "POST", headers: { "X-Desk-Token": TOKEN, "Content-Type": "application/octet-stream" }, body: file, cache: "no-store",
      });
      data = await response.json().catch(() => ({}));
    } catch (error) {
      toast("Could not reach the desk: " + error.message);
      continue;
    }
    if (!response.ok || typeof data.file !== "string") { toast(data.error || "Could not add " + file.name); continue; }
    if (cv.path !== path || !cv.doc) { toast(file.name + " was saved next to the other canvas"); continue; }
    const size = fileCardSize(await cvLocalImageSize(file));
    const node = { id: cvId(), type: "file", file: data.file, x: Math.round(center.x - size.width / 2 + i * 36), y: Math.round(center.y - size.height / 2 + i * 36), ...size };
    ensureList(cv.doc, "nodes").push(node);
    added.push(cvKey("n", node));
  }
  cvStatus("");
  if (added.length) {
    cvSelect(added);
    cvCommit("add files");
  }
}

const cvHasFiles = (event) => Boolean(event.dataTransfer && Array.from(event.dataTransfer.types || []).includes("Files"));

function cvToggleCork() {
  if (!cv.doc) return;
  if (setLook(cv.doc, !cvCork(cv.doc))) { cvCommit("look"); cvSync(); }
}

function cvDouble(event) {
  if (!cv.doc || cv.tool !== "select") return;
  const { w } = cvPoint(event);
  const key = hitTest(cv.doc, w.x, w.y, cv.view.z), item = key && key[0] === "n" ? cvLookup(cv.doc, key) : null;
  if (item && (item.type === "file" || item.type === "link")) { cvCardDouble(key); return; }
  if (key) { cvSelect([key]); cvStartEdit(key); }
}

function cvWheel(event) {
  event.preventDefault();
  if (!cv.doc) return;
  const box = cv.el.getBoundingClientRect(), unit = event.deltaMode === 1 ? 16 : 1;
  if (event.ctrlKey || event.metaKey) {
    cvSetView(zoomAt(cv.view, event.clientX - box.left, event.clientY - box.top, Math.exp(-event.deltaY * unit * (event.deltaMode === 1 ? 0.05 : 0.01))));
  } else {
    cvSetView({ ...cv.view, x: cv.view.x - event.deltaX * unit, y: cv.view.y - event.deltaY * unit });
  }
}

// ---- text editing: one floating textarea on top of the card, label or text ----
function cvMeasure(font) {
  if (cv.ctx) return (text) => { cv.ctx.font = font; return cv.ctx.measureText(text).width; };
  return (text) => text.length * parseFloat(font) * 0.55;
}

function cvStartEdit(key) {
  const item = cvLookup(cv.doc, key);
  if (!item || !cv.el || !cv.ui.editor) return;
  cvEndEdit();
  let box, text, font = "15px " + CV_FONT;
  if (key[0] === "e") {
    const curve = edgeCurveFor(nodeMap(cv.doc), item, cvCork(cv.doc));
    if (!curve) return;
    const mid = bezierPoint(curve, 0.5);
    box = { x: mid.x - 80, y: mid.y - 14, width: 160, height: 28 };
    text = item.label ?? "";
  } else if (key[0] === "x") {
    if (item.type !== "text") return;
    box = item;
    text = item.text ?? "";
    font = cvNum(item.fontSize, 24) + "px " + CV_HAND;
  } else if (item.type === "group") {
    box = { x: item.x, y: item.y - 30, width: Math.min(item.width, 260), height: 28 };
    text = item.label ?? "";
  } else if (item.type === "text") {
    box = item;
    text = item.text ?? "";
  } else {
    return;
  }
  cv.editing = { key };
  const z = cv.view.z, at = toScreen(cv.view, box.x, box.y), editor = cv.ui.editor;
  editor.value = String(text);
  Object.assign(editor.style, {
    display: "block", left: at.x + "px", top: at.y + "px", width: Math.max(box.width * z, 140) + "px", height: Math.max(box.height * z, 30) + "px",
    font: font.replace(/^[\d.]+px/, (px) => parseFloat(px) * z + "px"), color: key[0] === "x" ? adaptInk(item.stroke, cvPalette().dark) : "",
  });
  editor.focus();
  editor.select();
  cvDraw();
}

function cvEndEdit() {
  const editing = cv.editing;
  if (!editing) return;
  cv.editing = null;
  const editor = cv.ui.editor, value = editor ? editor.value : "";
  if (editor) editor.style.display = "none";
  const item = cv.doc && cvLookup(cv.doc, editing.key);
  if (item) {
    const kind = editing.key[0];
    if (kind === "e") {
      if (value) item.label = value; else delete item.label;
    } else if (kind === "x") {
      if (!value.trim()) {
        removeItems(cv.doc, [editing.key]);
        cv.sel = cv.sel.filter((key) => key !== editing.key);
      } else {
        item.text = value;
        const size = cvNum(item.fontSize, 24), measure = cvMeasure(size + "px " + CV_HAND), lines = value.split("\n");
        item.width = Math.max(10, ...lines.map((line) => measure(line)));
        item.height = lines.length * size * 1.25;
      }
    } else if (item.type === "group") {
      item.label = value;
    } else {
      item.text = value;
      if (textToLink(item)) cvFetchPreview(item);
    }
    cvCommit("text");
  }
  if (cv.el) cv.el.focus();
  cvDraw();
}

// ---- the viewer: a file or link card opened inside the page, so nothing has to leave the desk ----
const CV_VIDEO = /\.(mp4|m4v|mov|webm)$/i, CV_AUDIO = /\.(mp3|m4a|aac|wav|flac|ogg|opus)$/i, CV_PDF = /\.pdf$/i;
const CV_DOC = /\.(docx|doc|rtf|odt)$/i, CV_MODEL = /\.(glb|gltf|obj|stl)$/i, CV_NOTE = /\.(md|markdown)$/i;
const CV_TEXT_LIMIT = 2 * 1024 * 1024, CV_MODEL_LIMIT = 200 * 1024 * 1024, CV_STILL_LIMIT = 30 * 1024 * 1024;
function cvFileKind(file) {
  const name = String(file || "");
  if (CV_IMAGE_FILE.test(name)) return "image";
  if (CV_CANVAS_FILE.test(name)) return "canvas";
  if (CV_VIDEO.test(name)) return "video";
  if (CV_AUDIO.test(name)) return "audio";
  if (CV_PDF.test(name)) return "pdf";
  if (CV_DOC.test(name)) return "doc";
  if (CV_MODEL.test(name)) return "model";
  if (CV_NOTE.test(name) || CV_PLAIN_FILE.test(name)) return "text";
  return "other";
}
const cvMediaUrl = (path, file, extra) => "/media/canvas?t=" + encodeURIComponent(TOKEN) + "&path=" + encodeURIComponent(path) + "&file=" + encodeURIComponent(file) + (extra || "");
const cvHttpUrl = (url) => /^https?:\/\/[^\s]+$/i.test(String(url || "").trim());

function cvCloseView() {
  const viewing = cv.viewing, panel = cv.ui.view;
  if (!viewing) return;
  cv.viewing = null;
  if (viewing.stop) viewing.stop();
  if (!panel) return;
  for (const media of panel.querySelectorAll("video, audio")) media.pause();
  panel.textContent = "";
  panel.classList.remove("on");
  if (cv.el) cv.el.focus();
}

async function cvOpenInApp(node) {
  if (node.type === "link") {
    // Only web addresses: a canvas from someone else may carry javascript:, file: or app links.
    if (!cvHttpUrl(node.url)) { toast("Only http and https links open from the canvas"); return; }
    window.open(String(node.url).trim(), "_blank", "noopener,noreferrer");
    return;
  }
  const name = noteName(node.file);
  if (name) { openNote(name); return; }
  const { data } = await api("POST", "/api/canvas/open-file", { path: cv.path, file: String(node.file ?? "") });
  if (!data.ok) toast(data.error || "Could not open " + String(node.file ?? "").split("/").pop());
  else if (data.revealed) toast("Shown in Finder: files that would run a program are never opened from the canvas");
}

function cvView(key) {
  const node = cv.doc && cvLookup(cv.doc, key), panel = cv.ui.view;
  if (!node || !panel || (node.type !== "file" && node.type !== "link")) return false;
  cvCloseView();
  const path = cv.path, file = String(node.file ?? ""), kind = node.type === "link" ? "link" : cvFileKind(file);
  const title = node.type === "link" ? (node.unlawPreview && node.unlawPreview.title) || String(node.url || "") : file.split("/").pop();
  const outside = node.type === "link" ? "Open in browser" : noteName(file) ? "Open in Obsidian" : "Open in app";
  const openButton = h("button", { title: outside }, cvIcon(node.type === "link" ? "link" : "export"), outside);
  openButton.addEventListener("click", () => cvOpenInApp(node));
  const close = h("button", { class: "x", title: "Close (Esc)", "aria-label": "Close" }, cvIcon("close"));
  close.addEventListener("click", cvCloseView);
  const body = h("div", { class: "body " + kind });
  panel.textContent = "";
  panel.append(h("div", { class: "head" }, h("b", { text: title }), h("span", { class: "spacer" }), openButton, close), body);
  panel.classList.add("on");
  cv.viewing = { key, stop: null };
  const url = (extra) => cvMediaUrl(path, file, extra);
  if (kind === "image") body.append(h("img", { src: url(""), alt: title }));
  else if (kind === "video") body.append(h("video", { src: url("&raw=1"), controls: "", autoplay: "", playsinline: "" }));
  else if (kind === "audio") body.append(h("div", { class: "sound" }, cvIcon("audio"), h("span", { text: title }), h("audio", { src: url("&raw=1"), controls: "", autoplay: "" })));
  else if (kind === "pdf") body.append(h("iframe", { src: url("&raw=1"), title }));
  else if (kind === "doc") body.append(h("iframe", { src: url("&doc=1"), sandbox: "", title }));
  else if (kind === "text") cvShowText(body, url("&raw=1"));
  else if (kind === "model") cvShowModel(body, url("&raw=1"), file);
  else if (kind === "link") cvShowLink(body, node);
  else body.append(h("img", { src: url("&thumb=1"), alt: title }), h("div", { class: "note", text: "No live view for this kind of file in the page: Quick Look's picture of it. " + outside + " shows it whole." }));
  return true;
}

async function cvShowText(body, src) {
  let text = "";
  try {
    const response = await fetch(src, { cache: "no-store" });
    if (!response.ok) throw Error(String(response.status));
    text = await response.text();
  } catch (error) {
    body.append(h("div", { class: "note", text: "Could not read the file: " + error.message }));
    return;
  }
  const cut = text.length > CV_TEXT_LIMIT;
  body.append(h("pre", { text: cut ? text.slice(0, CV_TEXT_LIMIT) : text }));
  if (cut) body.append(h("div", { class: "note", text: "Only the first 2 MB are shown." }));
}

function cvShowLink(body, node) {
  const preview = node.unlawPreview && typeof node.unlawPreview === "object" ? node.unlawPreview : null;
  if (!cvHttpUrl(node.url)) { body.append(h("div", { class: "note", text: "This card has no web address." })); return; }
  // allow-same-origin here is the site's own origin, never the desk's; no top navigation, so it cannot take the tab.
  body.append(h("iframe", { src: String(node.url).trim(), sandbox: "allow-scripts allow-same-origin allow-forms allow-popups", referrerpolicy: "no-referrer", title: (preview && preview.title) || "Page" }));
  body.append(h("div", { class: "note", text: "Empty? Some sites (Google, GitHub, banks) refuse to be shown inside other pages: use Open in browser." }));
  if (!preview) cvFetchPreview(node);
}

// The page's title, description and picture for a link card, fetched once by the desk (public sites only).
// Cards whose preview is being fetched, by canvas and id (kept out of the node, which autosave writes to the file).
const cvPreviewing = new Set();
const cvPreviewTried = new Set(); // cards whose logo was asked for by drawing: asked once per page, even when it failed
async function cvFetchPreview(node, again) {
  const path = cv.path, busy = path + "\n" + node.id;
  if (!cvHttpUrl(node.url) || !path || cvPreviewing.has(busy) || (again && cvPreviewTried.has(busy))) return;
  cvPreviewTried.add(busy);
  cvPreviewing.add(busy);
  let answer;
  try {
    answer = await api("POST", "/api/canvas/link-preview", { path, url: String(node.url).trim() });
  } finally {
    cvPreviewing.delete(busy); // a lost connection must not block this card's preview for good
  }
  const { status, data } = answer;
  if (status !== 200 || cv.path !== path || !cv.doc) return;
  const live = cvLookup(cv.doc, cvKey("n", node));
  if (!live) return;
  live.unlawPreview = {
    title: String(data.title || ""), description: String(data.description || ""), site: String(data.site || ""),
    image: typeof data.image === "string" ? data.image : null, icon: typeof data.icon === "string" ? data.icon : null, frameable: data.frameable !== false,
  };
  cvCommit("link preview");
}

// A link pasted on the canvas becomes a link card with the page's preview.
function cvPasteText(text) {
  const found = urlCardText(text);
  if (!cv.doc || !found) return false;
  const center = toWorld(cv.view, cv.w / 2, cv.h / 2);
  const node = { id: cvId(), type: "link", url: found.url, x: Math.round(center.x - 160), y: Math.round(center.y - 120), width: 320, height: 240 };
  ensureList(cv.doc, "nodes").push(node);
  cvSelect([cvKey("n", node)]);
  cvCommit("paste link");
  cvFetchPreview(node);
  return true;
}

// ---- 3D: GLB/glTF, OBJ and STL parsed here and drawn with WebGL (no library): flat triangles with their colors ----
const CV_MAX_TRIANGLES = 3000000;
function meshFromTriangles(positions, colors) {
  const count = positions.length / 9;
  if (count > CV_MAX_TRIANGLES) throw Error("more than 3 million triangles");
  const normals = new Float32Array(positions.length);
  for (let t = 0; t < count; t++) {
    const o = t * 9, ax = positions[o + 3] - positions[o], ay = positions[o + 4] - positions[o + 1], az = positions[o + 5] - positions[o + 2];
    const bx = positions[o + 6] - positions[o], by = positions[o + 7] - positions[o + 1], bz = positions[o + 8] - positions[o + 2];
    let nx = ay * bz - az * by, ny = az * bx - ax * bz, nz = ax * by - ay * bx;
    const len = Math.hypot(nx, ny, nz) || 1;
    nx /= len; ny /= len; nz /= len;
    for (let v = 0; v < 3; v++) { normals[o + v * 3] = nx; normals[o + v * 3 + 1] = ny; normals[o + v * 3 + 2] = nz; }
  }
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < positions.length; i += 3) for (let k = 0; k < 3; k++) { min[k] = Math.min(min[k], positions[i + k]); max[k] = Math.max(max[k], positions[i + k]); }
  if (!count || !min.every(Number.isFinite)) throw Error("no triangles");
  return { positions, normals, colors: colors || null, count, min, max };
}
function parseSTL(buffer) {
  const view = new DataView(buffer);
  const triangles = buffer.byteLength >= 84 ? view.getUint32(80, true) : 0;
  // Binary when the size fits the count (some exporters add a few trailing bytes) and it does not start like ASCII.
  const ascii = /^\s*solid[\s\S]*facet/.test(new TextDecoder().decode(buffer.slice(0, 512)));
  if (triangles > 0 && buffer.byteLength >= 84 + triangles * 50 && (buffer.byteLength === 84 + triangles * 50 || !ascii)) {
    if (triangles > CV_MAX_TRIANGLES) throw Error("more than 3 million triangles");
    const positions = new Float32Array(triangles * 9);
    for (let t = 0; t < triangles; t++) for (let k = 0; k < 9; k++) positions[t * 9 + k] = view.getFloat32(84 + t * 50 + 12 + k * 4, true);
    return meshFromTriangles(positions);
  }
  const text = new TextDecoder().decode(buffer), points = [];
  for (const match of text.matchAll(/vertex\s+(\S+)\s+(\S+)\s+(\S+)/g)) points.push(+match[1], +match[2], +match[3]);
  return meshFromTriangles(new Float32Array(points.length - (points.length % 9)).map((_, i) => points[i]));
}
function parseOBJ(text) {
  const vertices = [], out = [];
  const at = (token) => {
    const index = parseInt(token.split("/")[0], 10);
    const i = index < 0 ? vertices.length / 3 + index : index - 1;
    return i >= 0 && i < vertices.length / 3 ? i : -1;
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (line.startsWith("v ")) { const p = line.split(/\s+/); vertices.push(+p[1], +p[2], +p[3]); }
    else if (line.startsWith("f ")) {
      const face = line.split(/\s+/).slice(1).map(at);
      if (face.some((i) => i < 0)) continue;
      for (let k = 1; k + 1 < face.length; k++) for (const i of [face[0], face[k], face[k + 1]]) out.push(vertices[i * 3], vertices[i * 3 + 1], vertices[i * 3 + 2]);
      if (out.length / 9 > CV_MAX_TRIANGLES) throw Error("more than 3 million triangles");
    }
  }
  return meshFromTriangles(new Float32Array(out));
}
// glTF 2.0: the default scene's meshes with their node transforms and base colors (textures are not read).
async function parseGLTF(buffer, loadBuffer) {
  const view = new DataView(buffer);
  let json, bin = null;
  if (buffer.byteLength >= 12 && view.getUint32(0, true) === 0x46546c67) {
    let offset = 12;
    while (offset + 8 <= buffer.byteLength) {
      const length = view.getUint32(offset, true), type = view.getUint32(offset + 4, true), chunk = buffer.slice(offset + 8, offset + 8 + length);
      if (type === 0x4e4f534a) json = JSON.parse(new TextDecoder().decode(chunk));
      else if (type === 0x004e4942) bin = chunk;
      offset += 8 + length;
    }
  } else {
    json = JSON.parse(new TextDecoder().decode(buffer));
  }
  if (!json || !Array.isArray(json.meshes)) throw Error("not a glTF model");
  const buffers = [];
  for (const [i, b] of (json.buffers || []).entries()) {
    if (!b.uri) buffers.push(bin);
    else if (/^data:/.test(b.uri)) buffers.push(Uint8Array.from(atob(b.uri.split(",")[1] || ""), (c) => c.charCodeAt(0)).buffer);
    else buffers.push(await loadBuffer(b.uri, i));
  }
  const SIZES = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 };
  const read = (index) => {
    const acc = json.accessors[index], bv = acc && json.bufferViews[acc.bufferView], data = bv && buffers[bv.buffer];
    if (!bv) throw Error("sparse or empty accessors are not supported");
    if (!data) throw Error("a buffer of the model is missing");
    const size = SIZES[acc.type], ctor = { 5126: Float32Array, 5125: Uint32Array, 5123: Uint16Array, 5121: Uint8Array }[acc.componentType];
    if (!ctor) throw Error("unsupported accessor type");
    const stride = bv.byteStride || size * ctor.BYTES_PER_ELEMENT, base = (bv.byteOffset || 0) + (acc.byteOffset || 0), dv = new DataView(data), out = new Float64Array(acc.count * size);
    const get = { 5126: (o) => dv.getFloat32(o, true), 5125: (o) => dv.getUint32(o, true), 5123: (o) => dv.getUint16(o, true), 5121: (o) => dv.getUint8(o) }[acc.componentType];
    for (let i = 0; i < acc.count; i++) for (let k = 0; k < size; k++) out[i * size + k] = get(base + i * stride + k * ctor.BYTES_PER_ELEMENT);
    return out;
  };
  const local = (node) => {
    if (Array.isArray(node.matrix) && node.matrix.length === 16) return node.matrix;
    const [x, y, z, w] = node.rotation || [0, 0, 0, 1], [sx, sy, sz] = node.scale || [1, 1, 1], [tx, ty, tz] = node.translation || [0, 0, 0];
    return [(1 - 2 * (y * y + z * z)) * sx, 2 * (x * y + z * w) * sx, 2 * (x * z - y * w) * sx, 0,
      2 * (x * y - z * w) * sy, (1 - 2 * (x * x + z * z)) * sy, 2 * (y * z + x * w) * sy, 0,
      2 * (x * z + y * w) * sz, 2 * (y * z - x * w) * sz, (1 - 2 * (x * x + y * y)) * sz, 0, tx, ty, tz, 1];
  };
  const positions = [], colors = [];
  const addMesh = (mesh, m) => {
    for (const prim of mesh.primitives || []) {
      if ((prim.mode ?? 4) !== 4 || prim.attributes.POSITION === undefined) continue;
      const p = read(prim.attributes.POSITION), idx = prim.indices !== undefined ? read(prim.indices) : null;
      const material = (json.materials || [])[prim.material], f = (material && material.pbrMetallicRoughness && material.pbrMetallicRoughness.baseColorFactor) || [0.78, 0.78, 0.8, 1];
      const total = idx ? idx.length : p.length / 3;
      for (let i = 0; i < total; i++) {
        const v = idx ? idx[i] : i, x = p[v * 3], y = p[v * 3 + 1], z = p[v * 3 + 2];
        positions.push(m[0] * x + m[4] * y + m[8] * z + m[12], m[1] * x + m[5] * y + m[9] * z + m[13], m[2] * x + m[6] * y + m[10] * z + m[14]);
        colors.push(f[0], f[1], f[2]);
      }
      if (positions.length / 9 > CV_MAX_TRIANGLES) throw Error("more than 3 million triangles");
    }
  };
  const visit = (index, parent, depth) => {
    const node = json.nodes[index];
    if (!node || depth > 64) return;
    const m = mat4Multiply(parent, local(node));
    if (node.mesh !== undefined && json.meshes[node.mesh]) addMesh(json.meshes[node.mesh], m);
    for (const child of node.children || []) visit(child, m, depth + 1);
  };
  const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  const scene = (json.scenes || [])[json.scene || 0];
  if (scene && Array.isArray(json.nodes)) for (const root of scene.nodes || []) visit(root, identity, 0);
  else json.meshes.forEach((mesh) => addMesh(mesh, identity));
  return meshFromTriangles(new Float32Array(positions), new Float32Array(colors));
}
async function cvLoadModel(src, file, limit = CV_MODEL_LIMIT, path = cv.path) {
  const response = await fetch(src, { cache: "no-store" });
  if (!response.ok) throw Error("could not read the model (" + response.status + ")");
  if (Number(response.headers.get("Content-Length")) > limit) throw Error("the model is larger than " + Math.round(limit / 1048576) + " MB");
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength > limit) throw Error("the model is larger than " + Math.round(limit / 1048576) + " MB");
  if (/\.stl$/i.test(file)) return parseSTL(buffer);
  if (/\.obj$/i.test(file)) return parseOBJ(new TextDecoder().decode(buffer));
  const folder = file.includes("/") ? file.slice(0, file.lastIndexOf("/") + 1) : "";
  return parseGLTF(buffer, async (uri) => {
    const next = await fetch(cvMediaUrl(path, folder + decodeURIComponent(uri), "&raw=1"), { cache: "no-store" });
    if (!next.ok) throw Error("missing " + uri);
    return next.arrayBuffer();
  });
}
// Column-major 4x4 helpers for the camera.
function mat4Perspective(fov, aspect, near, far) {
  const f = 1 / Math.tan(fov / 2), nf = 1 / (near - far);
  return [f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0];
}
function mat4LookAt(eye, center, up) {
  let zx = eye[0] - center[0], zy = eye[1] - center[1], zz = eye[2] - center[2];
  let len = Math.hypot(zx, zy, zz) || 1; zx /= len; zy /= len; zz /= len;
  let xx = up[1] * zz - up[2] * zy, xy = up[2] * zx - up[0] * zz, xz = up[0] * zy - up[1] * zx;
  len = Math.hypot(xx, xy, xz) || 1; xx /= len; xy /= len; xz /= len;
  const yx = zy * xz - zz * xy, yy = zz * xx - zx * xz, yz = zx * xy - zy * xx;
  return [xx, yx, zx, 0, xy, yy, zy, 0, xz, yz, zz, 0, -(xx * eye[0] + xy * eye[1] + xz * eye[2]), -(yx * eye[0] + yy * eye[1] + yz * eye[2]), -(zx * eye[0] + zy * eye[1] + zz * eye[2]), 1];
}
function mat4Multiply(a, b) {
  const r = new Array(16).fill(0);
  for (let c = 0; c < 4; c++) for (let row = 0; row < 4; row++) for (let k = 0; k < 4; k++) r[c * 4 + row] += a[k * 4 + row] * b[c * 4 + k];
  return r;
}
// An orbit camera around the model's middle: drag turns it, the wheel zooms, Shift-drag moves it, double-click resets.
function makeModelView(canvas, mesh) {
  const gl = canvas.getContext("webgl", { antialias: true, preserveDrawingBuffer: true });
  if (!gl) throw Error("WebGL is off in this browser");
  const shader = (type, source) => { const s = gl.createShader(type); gl.shaderSource(s, source); gl.compileShader(s); return s; };
  const program = gl.createProgram();
  gl.attachShader(program, shader(gl.VERTEX_SHADER, "attribute vec3 p;attribute vec3 n;attribute vec3 c;uniform mat4 m;varying vec3 vn;varying vec3 vc;void main(){gl_Position=m*vec4(p,1.0);vn=n;vc=c;}"));
  gl.attachShader(program, shader(gl.FRAGMENT_SHADER, "precision mediump float;varying vec3 vn;varying vec3 vc;void main(){vec3 n=normalize(vn);float l=0.35+0.55*abs(dot(n,normalize(vec3(0.4,0.8,0.6))))+0.2*abs(dot(n,normalize(vec3(-0.6,-0.2,-0.7))));gl_FragColor=vec4(vc*l,1.0);}"));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw Error("WebGL could not build its shader: " + (gl.getProgramInfoLog(program) || "unknown error"));
  gl.useProgram(program);
  const attribute = (name, data) => {
    const buffer = gl.createBuffer(), at = gl.getAttribLocation(program, name);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(at);
    gl.vertexAttribPointer(at, 3, gl.FLOAT, false, 0, 0);
  };
  attribute("p", mesh.positions);
  attribute("n", mesh.normals);
  attribute("c", mesh.colors || new Float32Array(mesh.positions.length).fill(0.78));
  const where = gl.getUniformLocation(program, "m");
  const center = [0, 1, 2].map((k) => (mesh.min[k] + mesh.max[k]) / 2), radius = Math.max(1e-6, Math.hypot(...[0, 1, 2].map((k) => mesh.max[k] - mesh.min[k])) / 2);
  const start = { yaw: 0.6, pitch: 0.35, distance: radius * 2.6, pan: [0, 0, 0] };
  const cam = { ...start, pan: [0, 0, 0] };
  const draw = () => {
    const w = canvas.width, h = canvas.height;
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    const target = center.map((v, k) => v + cam.pan[k]);
    const eye = [target[0] + cam.distance * Math.cos(cam.pitch) * Math.sin(cam.yaw), target[1] + cam.distance * Math.sin(cam.pitch), target[2] + cam.distance * Math.cos(cam.pitch) * Math.cos(cam.yaw)];
    const matrix = mat4Multiply(mat4Perspective(0.8, w / Math.max(1, h), radius / 100, radius * 100), mat4LookAt(eye, target, [0, 1, 0]));
    gl.uniformMatrix4fv(where, false, new Float32Array(matrix));
    gl.drawArrays(gl.TRIANGLES, 0, mesh.count * 3);
  };
  let drag = null;
  const down = (event) => { drag = { x: event.clientX, y: event.clientY, pan: event.shiftKey || event.button === 2 }; canvas.setPointerCapture && canvas.setPointerCapture(event.pointerId); };
  const move = (event) => {
    if (!drag) return;
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    drag.x = event.clientX; drag.y = event.clientY;
    if (drag.pan) {
      const step = cam.distance / 600;
      cam.pan[0] -= Math.cos(cam.yaw) * dx * step; cam.pan[2] += Math.sin(cam.yaw) * dx * step; cam.pan[1] += dy * step;
    } else {
      cam.yaw -= dx * 0.01;
      cam.pitch = Math.max(-1.5, Math.min(1.5, cam.pitch + dy * 0.01));
    }
    draw();
  };
  const up = () => { drag = null; };
  const wheel = (event) => { event.preventDefault(); cam.distance = Math.max(radius * 0.2, Math.min(radius * 40, cam.distance * Math.exp(event.deltaY * 0.0015))); draw(); };
  const reset = () => { Object.assign(cam, start, { pan: [0, 0, 0] }); draw(); };
  canvas.addEventListener("pointerdown", down);
  canvas.addEventListener("pointermove", move);
  canvas.addEventListener("pointerup", up);
  canvas.addEventListener("wheel", wheel, { passive: false });
  canvas.addEventListener("dblclick", reset);
  canvas.addEventListener("contextmenu", (event) => event.preventDefault());
  return { draw, stop: () => { const lose = gl.getExtension("WEBGL_lose_context"); if (lose) lose.loseContext(); } };
}
async function cvShowModel(body, src, file) {
  const canvas = h("canvas", { class: "model" }), note = h("div", { class: "note", text: "Loading the model…" });
  body.append(canvas, note);
  try {
    const mesh = await cvLoadModel(src, file);
    if (!canvas.isConnected) return;
    const box = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(box.width * dpr));
    canvas.height = Math.max(1, Math.round(box.height * dpr));
    const viewer = makeModelView(canvas, mesh);
    viewer.draw();
    if (cv.viewing) cv.viewing.stop = viewer.stop;
    note.textContent = mesh.count.toLocaleString() + " triangles · drag to turn, wheel to zoom, Shift-drag to move, double-click to reset";
  } catch (error) {
    note.textContent = "Could not show the model: " + error.message;
  }
}
// A 3D card shows the model itself: drawn once into a picture (in memory, per file), after the Quick Look one.
const cvStills = new Map();
async function cvModelStill(path, file) {
  const key = path + "\n" + file;
  if (cvStills.has(key)) return;
  const entry = { image: null };
  cvStills.set(key, entry);
  try {
    const canvas = document.createElement("canvas");
    canvas.width = 640; canvas.height = 480;
    const mesh = await cvLoadModel(cvMediaUrl(path, file, "&raw=1"), file, CV_STILL_LIMIT, path);
    const viewer = makeModelView(canvas, mesh);
    try {
      viewer.draw();
      const image = new Image();
      image.onload = () => { entry.image = image; cvDraw(); };
      image.src = canvas.toDataURL("image/png");
    } finally {
      viewer.stop(); // the picture is taken; the WebGL context is given back at once (browsers keep only ~16)
    }
  } catch {
    entry.failed = true;
  }
}

// ---- layers: like Photoshop's panel, topmost first (drawings over cards, cards over groups, as painted) ----
const CV_LAYERS_PREF = "desk-canvas-layers";
const CV_MAX_LAYER_ROWS = 500;
function layerName(key, item) {
  const clip = (text) => { const t = String(text || "").replace(/\s+/g, " ").trim(); return t.length > 40 ? t.slice(0, 39) + "\u2026" : t; };
  if (key[0] === "x") return item.type === "text" ? clip(item.text) || "Text" : item.type === "paint" ? "Fill" : CV_LABELS[item.type] || item.type;
  if (item.type === "group") return clip(item.label) || "Group";
  if (item.type === "file") return clip(fileLabel(item.file)) || "File";
  if (item.type === "link") return clip(item.url) || "Link";
  return clip(item.text) || "Empty card";
}
function layerIcon(row) {
  const type = row.item.type;
  if (row.key[0] === "x") return type === "paint" ? "fill" : CV_ICONS[type] ? type : "rectangle";
  return { group: "group", file: "attach", link: "link" }[type] || "card";
}
// Rows topmost first: the drawings and the cards outside groups under their own headings, then each group with the
// cards inside the smallest group around them, like layers inside a folder. `folded` holds the keys of headings and
// groups shown closed (one row with the name and a count).
function layerRows(doc, folded = new Set()) {
  const rows = [], elements = docElements(doc, true), nodes = docNodes(doc, true);
  const folder = (head, items) => {
    const shut = folded.has(head.key);
    rows.push({ ...head, depth: 0, count: items.length, folded: shut });
    if (!shut) for (const item of items) rows.push({ ...item, depth: 1 });
  };
  const topFirst = (list, kind) => list.slice().reverse().map((item) => ({ key: cvKey(kind, item), item }));
  if (elements.length) folder({ key: "sec:drawings", section: true, name: "Drawings" }, topFirst(elements, "x"));
  const groups = nodes.filter((n) => n.type === "group"), cards = nodes.filter((n) => n.type !== "group"), owner = new Map();
  for (const card of cards) {
    let best = null;
    for (const group of groups) if (boxInside(card, group) && (!best || group.width * group.height < best.width * best.height)) best = group;
    if (best) owner.set(card.id, best.id);
  }
  const loose = cards.filter((card) => !owner.has(card.id));
  if (loose.length) folder({ key: "sec:cards", section: true, name: groups.length ? "Cards outside groups" : "Cards" }, topFirst(loose, "n"));
  for (let i = groups.length - 1; i >= 0; i--) {
    folder({ key: cvKey("n", groups[i]), item: groups[i] }, topFirst(cards.filter((card) => owner.get(card.id) === groups[i].id), "n"));
  }
  return rows;
}
// Which headings and groups are folded, per canvas, in this browser (localStorage; the file never changes).
const CV_FOLDED_PREF = "desk-canvas-folded";
function cvReadFolded() {
  try {
    const all = JSON.parse(localStorage.getItem(CV_FOLDED_PREF) || "{}");
    return all && typeof all === "object" && !Array.isArray(all) ? all : {};
  } catch {
    return {};
  }
}
function cvFolded() {
  if (!cv.folded || cv.folded.path !== cv.path) {
    const keys = cvReadFolded()[cv.path];
    cv.folded = { path: cv.path, keys: new Set(Array.isArray(keys) ? keys.filter((key) => typeof key === "string") : []) };
  }
  return cv.folded.keys;
}
function cvSaveFolded() {
  const all = cvReadFolded(), keys = cvFolded();
  delete all[cv.path]; // written last again, so the oldest canvases are the ones forgotten past 50
  if (keys.size) all[cv.path] = [...keys].slice(0, 500);
  const paths = Object.keys(all);
  for (const old of paths.slice(0, Math.max(0, paths.length - 50))) delete all[old];
  try { localStorage.setItem(CV_FOLDED_PREF, JSON.stringify(all)); } catch { /* private mode: not remembered */ }
}
function cvToggleFold(key) {
  const keys = cvFolded();
  if (keys.has(key)) keys.delete(key); else keys.add(key);
  cvSaveFolded();
  cvRenderLayers();
}
// Fold or open every heading and group at once.
function cvFoldAll(fold) {
  const keys = cvFolded();
  keys.clear();
  if (fold && cv.doc) for (const row of layerRows(cv.doc)) if (row.depth === 0 && row.count) keys.add(row.key);
  cvSaveFolded();
  cvRenderLayers();
}
// The eye: hidden things are kept in the file (unlawHidden) but not painted, picked, filled or exported.
// A group takes everything inside it along.
function cvToggleHidden(key) {
  const item = cv.doc && cvLookup(cv.doc, key);
  if (!item) return;
  const hide = !cvHidden(item);
  const keys = [key, ...(key[0] === "n" && item.type === "group" ? containedIds(cv.doc, item) : [])];
  for (const k of keys) {
    const it = cvLookup(cv.doc, k);
    if (!it) continue;
    if (hide) it.unlawHidden = true; else delete it.unlawHidden;
  }
  if (hide) cv.sel = cv.sel.filter((k) => !keys.includes(k));
  cvCommit(hide ? "hide" : "show");
}
// Dropping a row on another of the same kind puts it at that place in the drawing order.
function cvReorderLayer(from, to) {
  if (!cv.doc || from === to || from[0] !== to[0] || from[0] === "e") return;
  const list = cvList(cv.doc, from[0]), a = list.indexOf(cvLookup(cv.doc, from)), b = list.indexOf(cvLookup(cv.doc, to));
  if (a < 0 || b < 0) return;
  list.splice(b, 0, ...list.splice(a, 1));
  cvCommit("order");
}
function cvToggleLayers() {
  cv.layers = !cv.layers;
  localStorage.setItem(CV_LAYERS_PREF, cv.layers ? "1" : "0");
  cvRenderLayers();
  cvResize();
}
function cvFoldArrow(row) {
  if (!row.count) return h("span", { class: "fold" });
  const arrow = h("button", { class: "fold", title: row.folded ? "Open" : "Fold", "aria-label": row.folded ? "Open" : "Fold", "aria-expanded": row.folded ? "false" : "true" }, cvIcon(row.folded ? "chevron" : "chevronDown"));
  arrow.addEventListener("click", (event) => { event.stopPropagation(); cvToggleFold(row.key); });
  return arrow;
}
function cvLayerRow(row) {
  if (row.section) {
    const node = h("div", { class: "row section" }, cvFoldArrow(row), h("span", { class: "name", text: row.name }), h("span", { class: "count", text: String(row.count) }));
    node.addEventListener("click", () => cvToggleFold(row.key));
    return node;
  }
  const hidden = cvHidden(row.item), picked = cv.sel.includes(row.key), group = row.item.type === "group";
  const eye = h("button", { class: "eye", title: hidden ? "Show" : "Hide", "aria-label": hidden ? "Show" : "Hide" }, cvIcon(hidden ? "eyeOff" : "eye"));
  eye.addEventListener("click", (event) => { event.stopPropagation(); cvToggleHidden(row.key); });
  const node = h("div", { class: "row" + (hidden ? " hidden" : "") + (picked ? " on" : "") + (row.depth ? " inner" : "") + (group ? " group" : ""), draggable: "true", title: "Click to select (Shift adds); drag onto another row to change the order" },
    group ? cvFoldArrow(row) : null, eye, cvIcon(layerIcon(row)), h("span", { class: "name", text: layerName(row.key, row.item) }),
    group && row.folded ? h("span", { class: "count", text: String(row.count) }) : null);
  node.addEventListener("click", (event) => {
    if (hidden) return;
    cvSelect(event.shiftKey ? [...new Set([...cv.sel, row.key])] : [row.key]);
  });
  node.addEventListener("dragstart", (event) => { cv.layerDrag = row.key; event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", row.key); });
  node.addEventListener("dragover", (event) => { if (cv.layerDrag && cv.layerDrag[0] === row.key[0]) event.preventDefault(); });
  node.addEventListener("drop", (event) => {
    event.preventDefault();
    const from = cv.layerDrag;
    cv.layerDrag = null;
    if (from) cvReorderLayer(from, row.key);
  });
  node.addEventListener("dragend", () => { cv.layerDrag = null; });
  return node;
}
function cvRenderLayers() {
  const panel = cv.ui.layers;
  if (!panel) return;
  panel.classList.toggle("on", cv.layers);
  if (cv.ui.layersButton) cv.ui.layersButton.classList.toggle("on", cv.layers);
  if (!cv.layers) return;
  panel.textContent = "";
  const foldAll = h("button", { class: "all", title: "Fold every group" }, cvIcon("chevron"));
  foldAll.addEventListener("click", () => cvFoldAll(true));
  const openAll = h("button", { class: "all", title: "Open every group" }, cvIcon("chevronDown"));
  openAll.addEventListener("click", () => cvFoldAll(false));
  panel.append(h("div", { class: "head" }, h("b", { text: "Layers" }), h("span", { class: "n", text: "topmost first" }), h("span", { class: "spacer" }), foldAll, openAll));
  if (!cv.doc) return;
  const rows = layerRows(cv.doc, cvFolded()), list = h("div", { class: "list" });
  for (const row of rows.slice(0, CV_MAX_LAYER_ROWS)) list.append(cvLayerRow(row));
  if (rows.length > CV_MAX_LAYER_ROWS) list.append(h("div", { class: "empty", text: rows.length - CV_MAX_LAYER_ROWS + " more not listed" }));
  if (!rows.length) list.append(h("div", { class: "empty", text: "Nothing on this canvas yet." }));
  panel.append(list);
}

// ---- actions ----
function cvDelete() {
  if (!cv.sel.length) return;
  removeItems(cv.doc, cv.sel);
  cv.sel = [];
  cvCommit("delete");
  cvSync();
}

function cvGroup() {
  if (!cv.doc || !cv.sel.length) { toast("Select something to group"); return; }
  const key = groupAround(cv.doc, cv.sel, cvId());
  if (!key) { toast("Select a card or drawing to group"); return; }
  cvSelect([key]);
  cvCommit("group");
}

function cvCopy() {
  if (!cv.sel.length) return;
  cv.clip = copyItems(cv.doc, cv.sel);
  cv.pasted = 0;
}

function cvPaste(bundle) {
  if (!bundle || !(bundle.nodes.length + bundle.elements.length)) return;
  cv.pasted++;
  cvSelect(pasteItems(cv.doc, bundle, 20 * cv.pasted, cvId));
  cvCommit("paste");
}

function cvDuplicate() {
  if (!cv.sel.length) return;
  cv.pasted = 0;
  cvPaste(copyItems(cv.doc, cv.sel));
  cv.pasted = 0;
}

function cvNudge(dx, dy) {
  const keys = new Set(cv.sel.filter((k) => k[0] !== "e"));
  for (const k of cv.sel) {
    const item = cvLookup(cv.doc, k);
    if (k[0] === "n" && item && item.type === "group") for (const inner of containedIds(cv.doc, item)) keys.add(inner);
  }
  if (!keys.size) return;
  moveItems(cv.doc, [...keys], dx, dy);
  cvCommit("nudge");
}

function cvSelectAll() {
  cvSelect([...docNodes(cv.doc).map((n) => cvKey("n", n)), ...docEdges(cv.doc).map((e) => cvKey("e", e)), ...docElements(cv.doc).map((el) => cvKey("x", el))]);
}

const CV_ARROWS = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };

// Returns true when the key was a canvas shortcut; the page's own keys never run in this view.
function cvZoomBy(factor) {
  cvSetView(zoomAt(cv.view, cv.w / 2, cv.h / 2, factor));
}

// The slider is logarithmic: fine steps among thin lines, big ones toward 100.
const widthToSlider = (width) => Math.round((Math.log(Math.max(CV_MIN_WIDTH, Math.min(CV_MAX_WIDTH, width))) / Math.log(CV_MAX_WIDTH)) * 1000);
const sliderToWidth = (value) => Math.max(CV_MIN_WIDTH, Math.min(CV_MAX_WIDTH, Math.round(Math.exp((value / 1000) * Math.log(CV_MAX_WIDTH)))));

// A width typed by hand: digits only, kept within 1-100; anything else puts the current width back.
function cvTypedWidth(text) {
  const value = Number.parseInt(String(text).trim(), 10);
  if (Number.isFinite(value) && /^\s*\d+\s*$/.test(String(text))) {
    const width = Math.max(CV_MIN_WIDTH, Math.min(CV_MAX_WIDTH, value));
    if (width !== cv.style.width) cvStyle({ width });
  }
  cvSync();
}

// [ and ] (or - and =) like Photoshop's brush size: 1 below 10, 5 below 50, then 10.
function cvStepWidth(dir) {
  const w = cv.style.width, step = (dir > 0 ? w >= 50 : w > 50) ? 10 : (dir > 0 ? w >= 10 : w > 10) ? 5 : 1;
  const next = Math.max(CV_MIN_WIDTH, Math.min(CV_MAX_WIDTH, w + dir * step));
  if (next !== w) cvStyle({ width: next });
}

function cvSetEraser(mode) {
  cv.eraser = mode;
  cvSavePrefs();
  cvSetTool("eraser");
}

// The bubble under an active tool's button: eraser mode, or how even the shapes are drawn.
function cvMenuItems(tool) {
  if (tool === "eraser") return CV_ERASERS.map((e) => ({ icon: e.icon, label: e.label, on: cv.eraser === e.mode, pick: () => cvSetEraser(e.mode) }));
  if (CV_SHAPE_CYCLE.includes(tool)) {
    return CV_ROUGH_LEVELS.map((l) => ({ num: String(l.level), label: l.label, on: cv.style.rough === l.rough, pick: () => { cvStyle({ rough: l.rough }); cvCloseMenu(); } }));
  }
  return null;
}

function cvOpenMenu(tool) {
  const menu = cv.ui.menu, items = cvMenuItems(tool);
  if (!menu || !items) return;
  menu.textContent = "";
  for (const item of items) {
    const button = h("button", { class: item.on ? "on" : "" }, item.icon ? cvIcon(item.icon) : h("span", { class: "num", text: item.num }), h("span", { text: item.label }));
    button.addEventListener("click", () => { item.pick(); cvCloseMenu(); });
    menu.append(button);
  }
  const anchor = cv.ui.tools[tool], box = anchor && anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : { left: 0, bottom: 0 };
  menu.style.left = Math.round(box.left) + "px";
  menu.style.top = Math.round(box.bottom + 6) + "px";
  menu.classList.add("on");
  cv.menu = tool;
}

function cvCloseMenu() {
  if (!cv.menu) return;
  cv.menu = "";
  if (cv.ui.menu) cv.ui.menu.classList.remove("on");
}

// A click on the active tool's button opens its menu; on another tool it switches.
function cvToolClick(tool) {
  if (cv.tool === tool && cvMenuItems(tool)) {
    if (cv.menu === tool) cvCloseMenu(); else cvOpenMenu(tool);
    return;
  }
  cvSetTool(tool);
}

function canvasKey(event) {
  if (event.key === "Escape" && cv.menu) { cvCloseMenu(); return true; }
  if (event.key === "Escape" && cv.viewing) { cvCloseView(); return true; }
  if (event.key === "Escape" && cv.inline) { cvCloseInline(); return true; }
  if (event.key === "Escape" && cv.gallery) { cvToggleGallery(false); return true; }
  if (cv.viewing || cv.gallery) return false;
  if (!cv.doc) return false;
  const key = event.key, mod = event.metaKey || event.ctrlKey;
  // Physical keys, so the shortcuts also work with a Russian (or any) keyboard layout.
  const code = event.code || "", physical = code.startsWith("Key") ? code.slice(3).toLowerCase() : code.startsWith("Digit") ? code.slice(5) : "";
  if (key === " " && !mod) { event.preventDefault(); cv.space = true; cvCursor(); return true; }
  if (code === "F7" || key === "F7") { event.preventDefault(); cvToggleLayers(); return true; }
  if (key === "Escape") {
    if ($("help").classList.contains("on")) return false;
    if (cv.thread) { cv.thread = null; cvDraw(); return true; }
    if (cv.drag) { cvCancelDrag(); return true; }
    if (cv.sel.length) { cvSelect([]); return true; }
    if (cv.tool !== "select") { cvSetTool("select"); return true; }
    return false;
  }
  if (mod) {
    if (code === "Equal" || code === "NumpadAdd" || code === "Minus" || code === "NumpadSubtract") {
      event.preventDefault();
      cvZoomBy(code === "Equal" || code === "NumpadAdd" ? 1.25 : 0.8);
      return true;
    }
    const letter = physical || (key.length === 1 ? key.toLowerCase() : "");
    if (!letter || !"zyacvdg0".includes(letter)) return false;
    if (letter !== "v") event.preventDefault();
    if (letter === "z") { if (event.shiftKey) cvRedo(); else cvUndo(); }
    else if (letter === "y") cvRedo();
    else if (letter === "a") cvSelectAll();
    else if (letter === "c") cvCopy();
    else if (letter === "v") {
      // The browser's paste event follows the key when the clipboard has text: a link there becomes a link card;
      // otherwise the canvas's own copied items are pasted.
      clearTimeout(cv.pasteWait);
      cv.pasteWait = setTimeout(() => { cv.pasteWait = 0; cvPaste(cv.clip); }, 80);
      return true;
    }
    else if (letter === "g") cvGroup();
    else if (letter === "0") cvFit();
    else cvDuplicate();
    return true;
  }
  if (event.altKey) return false;
  if (key === "Delete" || key === "Backspace") { event.preventDefault(); cvDelete(); return true; }
  if (CV_ARROWS[key]) {
    if (!cv.sel.length) return false;
    event.preventDefault();
    const step = event.shiftKey ? 10 : 1;
    cvNudge(CV_ARROWS[key][0] * step, CV_ARROWS[key][1] * step);
    return true;
  }
  if (code === "BracketLeft" || code === "BracketRight") { cvStepWidth(code === "BracketLeft" ? -1 : 1); return true; }
  if (code === "Minus" || code === "Equal" || code === "NumpadSubtract" || code === "NumpadAdd") { cvStepWidth(code === "Minus" || code === "NumpadSubtract" ? -1 : 1); return true; }
  const letter = physical || (key.length === 1 ? key.toLowerCase() : "");
  if (letter === "e" && event.shiftKey) {
    const mode = cv.eraser === "part" ? "object" : "part";
    cvSetEraser(mode);
    toast("Eraser: " + CV_ERASERS.find((e) => e.mode === mode).label.toLowerCase());
    return true;
  }
  if (letter === "u" && event.shiftKey) {
    const at = CV_SHAPE_CYCLE.indexOf(cv.tool);
    cvSetTool(CV_SHAPE_CYCLE[(at + 1) % CV_SHAPE_CYCLE.length]);
    return true;
  }
  if (CV_BY_KEY[letter]) { cvSetTool(CV_BY_KEY[letter]); return true; }
  if (letter === "d") { cvStyle({ stroke: CV_INK[0] }); return true; }
  if (letter === "f") { cvFit(); return true; }
  return false;
}

// ---- toolbar and view ----
function cvFillPick() {
  if (cv.gallery) cvRenderGallery();
  if (cv.ui.back) {
    cv.ui.back.style.display = cv.back.length ? "" : "none";
    cv.ui.back.title = cv.back.length ? "Back to " + cv.back[cv.back.length - 1].split("/").pop().replace(CV_CANVAS_FILE, "") : "Back";
  }
  const field = cv.ui.name;
  if (field) {
    if (document.activeElement !== field) field.value = cv.name;
    field.disabled = !cv.path;
  }
}

// ---- the canvas gallery: every canvas as a thumbnail, open with a click, delete to the Trash, drop to import ----
const cvThumbs = new Map(); // path -> {modified, shape} read through /api/canvas/peek (does not switch canvases)
function cvToggleGallery(open) {
  cv.gallery = typeof open === "boolean" ? open : !cv.gallery;
  if (cv.gallery) loadCanvasList();
  cvRenderGallery();
  if (cv.gallery && cv.ui.gallerySearch && typeof cv.ui.gallerySearch.focus === "function") cv.ui.gallerySearch.focus();
}
// The gallery's favorites and groups are a list of paths on the server (canvases.json); the files never move.
function cleanShelf(raw) {
  const paths = (list) => (Array.isArray(list) ? list.filter((path) => typeof path === "string") : []);
  const groups = raw && Array.isArray(raw.groups) ? raw.groups.filter((group) => group && typeof group.name === "string").map((group) => ({ name: group.name, paths: paths(group.paths) })) : [];
  return { favorites: paths(raw && raw.favorites), groups };
}
function shelfFavorite(shelf, path) {
  const on = shelf.favorites.includes(path);
  return { ...shelf, favorites: on ? shelf.favorites.filter((item) => item !== path) : [...shelf.favorites, path] };
}
// Into the group named `name` (out of any other), or out of every group with null.
function shelfMove(shelf, path, name) {
  return { ...shelf, groups: shelf.groups.map((group) => ({ name: group.name, paths: [...group.paths.filter((item) => item !== path), ...(group.name === name ? [path] : [])] })) };
}
const shelfName = (name) => String(name ?? "").replace(/\s+/g, " ").trim();
function shelfAddGroup(shelf, name) {
  const clean = shelfName(name);
  if (!clean || clean.length > 80 || shelf.groups.some((group) => group.name.toLowerCase() === clean.toLowerCase())) return null;
  return { ...shelf, groups: [...shelf.groups, { name: clean, paths: [] }] };
}
function shelfRenameGroup(shelf, from, to) {
  const clean = shelfName(to);
  if (!clean || clean.length > 80 || shelf.groups.some((group) => group.name !== from && group.name.toLowerCase() === clean.toLowerCase())) return null;
  return { ...shelf, groups: shelf.groups.map((group) => (group.name === from ? { ...group, name: clean } : group)) };
}
function shelfRemoveGroup(shelf, name) {
  return { ...shelf, groups: shelf.groups.filter((group) => group.name !== name) };
}
// Favorites first (they also stay in their group), then each group, then the canvases in no group. A search keeps
// the canvases whose name holds every word of it (case ignored) and drops the sections it leaves empty.
function galleryMatch(item, search) {
  const name = String(item.name ?? "").toLowerCase();
  return String(search ?? "").toLowerCase().split(/\s+/).filter(Boolean).every((word) => name.includes(word));
}
function gallerySections(items, shelf, search = "") {
  const sections = shelfSections(items, shelf);
  if (!String(search).trim()) return sections;
  return sections.map((section) => ({ ...section, items: section.items.filter((item) => galleryMatch(item, search)) })).filter((section) => section.items.length);
}
function shelfSections(items, shelf) {
  const byPath = new Map(items.map((item) => [item.path, item])), grouped = new Set(), sections = [];
  const pick = (paths) => paths.map((path) => byPath.get(path)).filter(Boolean);
  const favorites = pick(shelf.favorites);
  if (favorites.length) sections.push({ kind: "favorites", name: "Favorites", items: favorites });
  for (const group of shelf.groups) {
    group.paths.forEach((path) => grouped.add(path));
    sections.push({ kind: "group", name: group.name, items: pick(group.paths) });
  }
  sections.push({ kind: "other", name: shelf.groups.length ? "Not in a group" : "All canvases", items: items.filter((item) => !grouped.has(item.path)) });
  return sections;
}
async function cvSaveShelf(next) {
  if (!next) return false;
  cv.shelf = next;
  cvRenderGallery();
  const { status, data } = await api("POST", "/api/canvas/shelf", { shelf: next });
  if (status !== 200) { toast(data.error || "Could not save the gallery"); await loadCanvasList(); return false; }
  if (Array.isArray(data.items)) cv.items = data.items;
  cv.shelf = cleanShelf(data.shelf);
  cvRenderGallery();
  return true;
}
function cvNewGroup() {
  const name = prompt("Name of the new group");
  if (name === null) return;
  const next = shelfAddGroup(cv.shelf, name);
  if (!next) { toast("A group needs a name of its own (up to 80 characters)"); return; }
  cvSaveShelf(next);
}
function cvGallerySection(section) {
  const button = (icon, title, run) => {
    const b = h("button", { class: "mini", title, "aria-label": title }, cvIcon(icon));
    b.addEventListener("click", (event) => { event.stopPropagation(); run(); });
    return b;
  };
  const tools = section.kind === "group" ? [
    button("edit", "Rename the group", () => {
      const name = prompt("New name of the group", section.name);
      if (name === null || shelfName(name) === section.name) return;
      const next = shelfRenameGroup(cv.shelf, section.name, name);
      if (!next) toast("That name is empty or taken"); else cvSaveShelf(next);
    }),
    button("trash", "Remove the group (its canvases stay)", () => {
      if (confirm("Remove the group \u201c" + section.name + "\u201d?\nIts canvases stay where they are.")) cvSaveShelf(shelfRemoveGroup(cv.shelf, section.name));
    }),
  ] : [];
  const icon = section.kind === "favorites" ? "star" : section.kind === "group" ? "folder" : "gallery";
  const head = h("div", { class: "section " + section.kind }, cvIcon(icon), h("b", { text: section.name }), h("span", { class: "count", text: String(section.items.length) }), ...tools);
  const grid = h("div", { class: "grid" });
  for (const item of section.items) grid.append(cvGalleryTile(item));
  if (!section.items.length) grid.append(h("div", { class: "empty", text: section.kind === "group" ? "Drag canvases here." : "No canvases yet: make one with New, or drop a .canvas file here." }));
  const box = h("div", { class: "shelf" }, head, grid);
  // Dropping a tile on a group puts the canvas in it; on "Not in a group", takes it out.
  if (section.kind !== "favorites") {
    box.addEventListener("dragover", (event) => { if (cv.galleryDrag) { event.preventDefault(); box.classList.add("drop"); } });
    box.addEventListener("dragleave", (event) => { if (!box.contains(event.relatedTarget)) box.classList.remove("drop"); });
    box.addEventListener("drop", (event) => {
      box.classList.remove("drop");
      const path = cv.galleryDrag;
      cv.galleryDrag = null;
      if (!path) return;
      event.preventDefault();
      event.stopPropagation();
      cvSaveShelf(shelfMove(cv.shelf, path, section.kind === "group" ? section.name : null));
    });
  }
  return box;
}
function cvRenderGallery() {
  const panel = cv.ui.gallery;
  if (!panel) return;
  panel.classList.toggle("on", Boolean(cv.gallery));
  if (cv.ui.pick) cv.ui.pick.classList.toggle("on", Boolean(cv.gallery));
  if (!cv.gallery) return;
  // The search field survives a redraw (typing would lose focus otherwise): only the sections are rebuilt.
  if (!cv.ui.gallerySearch) {
    const field = h("input", { class: "search", type: "search", placeholder: "Search by name", spellcheck: "false", "aria-label": "Search canvases by name" });
    field.addEventListener("input", () => { cv.gallerySearch = field.value; cvRenderShelves(); });
    field.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && field.value) { event.stopPropagation(); event.preventDefault(); field.value = ""; cv.gallerySearch = ""; cvRenderShelves(); }
      else if (event.key === "Enter") { const first = cv.ui.galleryList && cv.ui.galleryList.querySelector && cv.ui.galleryList.querySelector(".tile"); if (first) first.click(); }
    });
    cv.ui.gallerySearch = field;
  }
  const search = cv.ui.gallerySearch;
  search.value = cv.gallerySearch;
  panel.textContent = "";
  const button = (icon, text, run, title) => {
    const b = h("button", { title: title || text }, cvIcon(icon), text);
    b.addEventListener("click", run);
    return b;
  };
  panel.append(h("div", { class: "head" },
    h("b", { text: "Canvases" }),
    search,
    h("span", { class: "hint", text: "Click to open \u00b7 drag a canvas onto a group \u00b7 drop a .canvas file here to import it" }),
    h("span", { class: "spacer" }),
    button("folder", "New group", cvNewGroup, "A group in this gallery; the files stay where they are"),
    button("plus", "New", () => { cvToggleGallery(false); cvNew(); }),
    button("folder", "Open file\u2026", () => { cvToggleGallery(false); cvChoose(); }, "Open a .canvas file anywhere on the Mac"),
    button("close", "", () => cvToggleGallery(false), "Close (Esc)")));
  cv.ui.galleryList = h("div", { class: "shelves" });
  panel.append(cv.ui.galleryList);
  cvRenderShelves();
}
function cvRenderShelves() {
  const list = cv.ui.galleryList;
  if (!list) return;
  list.textContent = "";
  const items = cv.items.some((item) => item.path === cv.path) || !cv.path ? cv.items : [{ path: cv.path, name: cv.name || cv.path }, ...cv.items];
  const sections = gallerySections(items, cv.shelf, cv.gallerySearch);
  for (const section of sections) list.append(cvGallerySection(section));
  if (!sections.length) list.append(h("div", { class: "empty", text: "No canvas is named like \u201c" + cv.gallerySearch.trim() + "\u201d." }));
}
function cvGalleryTile(item) {
  const thumb = h("canvas", { class: "thumb", width: "480", height: "300" });
  const when = Number.isFinite(item.modified) ? new Date(item.modified * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "";
  const action = (icon, cls, title, run) => {
    const b = h("button", { class: cls, title, "aria-label": title + ": " + item.name }, cvIcon(icon));
    b.addEventListener("click", (event) => { event.stopPropagation(); run(); });
    return b;
  };
  const favorite = cv.shelf.favorites.includes(item.path);
  const actions = h("div", { class: "acts" },
    action("star", "fav" + (favorite ? " on" : ""), favorite ? "Remove from favorites" : "Add to favorites", () => cvSaveShelf(shelfFavorite(cv.shelf, item.path))),
    cv.doc && cv.path && item.path !== cv.path ? action("link", "lnk", "Put a link to this canvas on the open one", () => cvAddCanvasLink(item)) : null,
    action("trash", "del", "Move to the Trash", () => cvDeleteCanvas(item)));
  const tile = h("div", { class: "tile" + (item.path === cv.path ? " on" : ""), title: item.path, draggable: "true" },
    thumb, h("div", { class: "meta" }, h("span", { class: "name", text: item.name }), h("span", { class: "when", text: when })), actions);
  tile.addEventListener("click", async () => { cvToggleGallery(false); if (item.path !== cv.path) await cvOpen(item.path, false); });
  tile.addEventListener("dragstart", (event) => { cv.galleryDrag = item.path; event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", item.name); });
  tile.addEventListener("dragend", () => { cv.galleryDrag = null; });
  cvDrawThumb(thumb, item);
  return tile;
}
async function cvDrawThumb(canvas, item) {
  let cached = cvThumbs.get(item.path);
  if (!cached || cached.modified !== item.modified) {
    const { status, data } = await api("GET", "/api/canvas/peek?path=" + encodeURIComponent(item.path));
    if (status !== 200) return;
    cached = { modified: item.modified, shape: data };
    cvThumbs.set(item.path, cached);
  }
  const ctx = canvas.getContext && canvas.getContext("2d");
  if (!ctx) return;
  const doc = item.path === cv.path && cv.doc ? cv.doc : cached.shape.canvas, width = 240, height = 150;
  paintScene({ ctx, doc, view: fitView(sceneBounds(doc), width, height, 12), w: width, h: height, pal: cvPalette(), scale: 2, ui: null, images: null, flat: true });
}
async function cvDeleteCanvas(item) {
  if (!confirm("Move \u201c" + item.name + "\u201d to the Trash?\nIts attached files stay in the folder.")) return;
  const open = item.path === cv.path;
  // A save on its way would write the file again after it went to the Trash.
  while (cv.saving) await cv.saving;
  const { status, data } = await api("POST", "/api/canvas/delete", { path: item.path });
  if (status !== 200) { toast(data.error || "Could not delete the canvas"); return; }
  if (open) { clearTimeout(cv.saveTimer); cv.saveTimer = 0; cv.dirty = false; }
  cvThumbs.delete(item.path);
  cv.items = Array.isArray(data.items) ? data.items : [];
  if (data.shelf) cv.shelf = cleanShelf(data.shelf);
  toast("\u201c" + item.name + "\u201d is in the Trash");
  if (open) {
    cv.doc = null; cv.path = ""; cv.name = ""; cv.version = ""; cv.sel = []; cv.hist = null;
    localStorage.setItem("desk-canvas", "");
    const next = data.current || (cv.items[0] && cv.items[0].path);
    if (next) await cvOpen(next, false);
    cvSync();
    cvDraw();
  }
  cvFillPick();
}
// A .canvas file dropped on the page: the browser gives only its contents, so it becomes a new canvas in the
// canvas folder. Files it names by relative path are not copied along.
async function cvImportCanvas(file) {
  let canvas;
  try { canvas = JSON.parse(await file.text()); } catch { toast(file.name + " is not a canvas file"); return false; }
  await saveCanvas();
  const { status, data } = await api("POST", "/api/canvas/import", { name: file.name, canvas });
  if (status !== 200) { toast(data.error || "Could not import " + file.name); return false; }
  cvToggleGallery(false);
  await cvShow(data);
  toast("Opened " + file.name + " as \u201c" + data.name + "\u201d in the canvas folder");
  return true;
}
const cvIsCanvasFile = (file) => /\.canvas$/i.test(String(file && file.name || ""));
async function cvDropFiles(files, at) {
  const list = Array.from(files || []), canvases = list.filter(cvIsCanvasFile), others = list.filter((file) => !cvIsCanvasFile(file));
  for (const file of canvases.slice(0, 5)) await cvImportCanvas(file);
  if (others.length) await cvAddFiles(others, canvases.length ? null : at);
}

function cvBuildBar() {
  const ui = { tools: {}, ink: [] };
  const press = (button, action) => () => { action(); button.blur(); };
  const iconButton = (icon, title, run, weight) => {
    const button = h("button", { title, "aria-label": title }, cvIcon(icon, weight));
    button.addEventListener("click", press(button, run));
    return button;
  };
  const toolButtons = Object.keys(CV_TOOLS).map((tool) => {
    const keys = CV_TOOLS[tool], shape = CV_SHAPE_CYCLE.includes(tool);
    const hint = [keys ? keys[0].toUpperCase() : "", shape ? "Shift+U cycles shapes" : ""].filter(Boolean).join("; ");
    const extra = tool === "thread" ? ". Click a spot on a card, then a spot on another card (on empty canvas: a new card)" : tool === "fill" ? ". Floods the clicked color; Alt+click clears" : tool === "eraser" ? ". Click again: whole object or only where it passes (Shift+E)" : shape ? ". Click again: how even" : "";
    const button = iconButton(tool, CV_LABELS[tool] + (hint ? " (" + hint + ")" : "") + extra, () => cvToolClick(tool));
    if (tool === "eraser" || shape) button.classList.add("more");
    ui.tools[tool] = button;
    return button;
  });
  const swatches = CV_INK.map((color) => {
    const button = h("button", { class: "swatch", title: color, style: "background:" + color });
    button.addEventListener("click", press(button, () => cvStyle({ stroke: color })));
    ui.ink.push(button);
    return button;
  });
  ui.custom = h("input", { type: "color", value: "#3a6df0", "aria-label": "Any color" });
  ui.custom.addEventListener("input", () => cvStyle({ stroke: ui.custom.value.toLowerCase() }));
  ui.customWrap = h("label", { class: "swatch custom", title: "Any color\u2026" }, ui.custom);
  ui.fill = iconButton("filled", "Draw shapes filled with the color", () => cvStyle({ fill: !cv.style.fill }));
  ui.width = h("input", { class: "cvwidth", type: "range", min: "0", max: "1000", step: "1", title: "Stroke width, 1-100 ([ ] or - = step)", "aria-label": "Stroke width" });
  ui.width.addEventListener("input", () => cvStyle({ width: sliderToWidth(Number(ui.width.value)) }));
  ui.width.addEventListener("change", () => ui.width.blur());
  // The number next to the slider is a field: type an exact width, Enter applies, Escape cancels.
  ui.widthValue = h("input", { class: "cvwidthval", type: "text", inputmode: "numeric", maxlength: "3", spellcheck: "false", title: "Stroke width: type 1-100, Enter applies", "aria-label": "Stroke width in pixels" });
  ui.widthValue.addEventListener("focus", () => ui.widthValue.select && ui.widthValue.select());
  ui.widthValue.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); ui.widthValue.blur(); }
    else if (event.key === "Escape") { ui.widthValue.value = String(cv.style.width); ui.widthValue.blur(); }
  });
  ui.widthValue.addEventListener("blur", () => cvTypedWidth(ui.widthValue.value));
  ui.menu = h("div", { class: "cvmenu" });
  ui.undo = iconButton("undo", "Undo (Cmd/Ctrl+Z)", cvUndo);
  ui.redo = iconButton("redo", "Redo (Shift+Cmd/Ctrl+Z)", cvRedo);
  ui.name = h("input", { class: "cvname", type: "text", spellcheck: "false", title: "Canvas name: click to rename", "aria-label": "Canvas name" });
  ui.name.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); ui.name.blur(); }
    else if (event.key === "Escape") { ui.name.value = cv.name; ui.name.blur(); }
  });
  ui.name.addEventListener("blur", () => cvRename(ui.name.value));
  ui.back = iconButton("back", "Back", cvGoBack);
  ui.back.style.display = "none";
  ui.pick = h("button", { class: "cvpick", title: "All canvases: open, favorites, groups, links, delete, drop a .canvas file to import" }, cvIcon("gallery"), "Canvases");
  ui.pick.addEventListener("click", press(ui.pick, cvToggleGallery));
  ui.zoom = h("span", { class: "cvzoom", title: "Zoom" });
  ui.layersButton = iconButton("layers", "Layers: every card, group and drawing; the eye hides one (F7)", cvToggleLayers);
  ui.cork = iconButton("pin", "Detective board: cork, paper notes, photos and red thread between pins", cvToggleCork);
  ui.files = h("input", { type: "file", multiple: true, style: "display:none", "aria-hidden": "true" });
  ui.files.addEventListener("change", () => { const picked = Array.from(ui.files.files || []); ui.files.value = ""; cvAddFiles(picked); });
  ui.add = h("button", { title: "Add files: pictures, PDF, documents, anything (or drop them on the canvas)", "aria-label": "Add files" }, cvIcon("attach"), "Add");
  ui.add.addEventListener("click", press(ui.add, () => ui.files.click()));
  ui.status = h("span", { class: "cvstatus" });
  ui.root = h("div", { class: "cvbar" },
    ui.name,
    h("div", { class: "group" }, ui.back, ui.pick, iconButton("plus", "New canvas (canvas-1, canvas-2, \u2026)", cvNew), iconButton("folder", "Open a canvas file\u2026", cvChoose)),
    h("div", { class: "group" }, toolButtons),
    h("div", { class: "group" }, swatches, ui.customWrap),
    h("div", { class: "group" }, ui.fill, ui.width, ui.widthValue),
    h("div", { class: "group" }, iconButton("group", "Group the selection (Cmd/Ctrl+G)", cvGroup), ui.undo, ui.redo),
    h("div", { class: "group" }, iconButton("fit", "Fit everything in view (Cmd/Ctrl+0)", cvFit), ui.zoom),
    h("div", { class: "group" }, ui.layersButton, ui.cork, iconButton("export", "Export the canvas as a PNG image", cvExport)),
    ui.status,
    h("div", { class: "group cvadd" }, ui.add, ui.files));
  return ui;
}

function renderCanvas(main) {
  if (main.querySelector(".cv")) { cvResize(); return; }
  main.textContent = "";
  const ui = cvBuildBar();
  const canvas = h("canvas", { class: "cvcanvas", tabindex: "0" });
  ui.editor = h("textarea", { class: "cvedit", spellcheck: "false" });
  ui.empty = h("div", { class: "cvempty" }, h("div", { text: "No canvas yet" }), h("button", { class: "primary", text: "New canvas", onclick: cvNew }));
  ui.inline = h("div", { class: "cvinline" });
  ui.players = h("div", { class: "cvplayers", "aria-hidden": "true" });
  const stage = h("div", { class: "cvstage" }, canvas, ui.inline, ui.players, ui.editor, ui.empty);
  ui.layers = h("div", { class: "cvlayers" });
  cv.layers = localStorage.getItem(CV_LAYERS_PREF) === "1";
  ui.gallery = h("div", { class: "cvgallery" });
  ui.view = h("div", { class: "cvview" });
  main.append(h("div", { class: "cv" }, ui.root, h("div", { class: "cvbody" }, stage, ui.layers, ui.gallery, ui.view), ui.menu));
  ui.gallery.addEventListener("dragover", (event) => { if (cvHasFiles(event)) { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; } });
  ui.gallery.addEventListener("drop", (event) => {
    if (!cvHasFiles(event)) return;
    event.preventDefault();
    const files = Array.from(event.dataTransfer.files || []).filter(cvIsCanvasFile);
    if (!files.length) { toast("Drop .canvas files here; other files go onto an open canvas"); return; }
    cvDropFiles(files);
  });
  // Files dragged in from Finder (or the desktop) are pinned where they are dropped.
  stage.addEventListener("dragover", (event) => {
    if (!cvHasFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    stage.classList.add("dropping");
  });
  stage.addEventListener("dragleave", (event) => { if (!stage.contains(event.relatedTarget)) stage.classList.remove("dropping"); });
  stage.addEventListener("drop", (event) => {
    stage.classList.remove("dropping");
    if (!cvHasFiles(event)) return;
    event.preventDefault();
    cvDropFiles(event.dataTransfer.files, cvPoint(event).w);
  });
  cv.el = canvas;
  cv.ctx = canvas.getContext("2d");
  cv.ui = ui;
  canvas.addEventListener("pointerdown", cvDown);
  canvas.addEventListener("pointermove", cvMove);
  canvas.addEventListener("pointerup", cvUp);
  canvas.addEventListener("pointercancel", cvCancelDrag);
  canvas.addEventListener("pointerleave", () => { if (cv.cursor) { cv.cursor = null; cvDraw(); } });
  canvas.addEventListener("dblclick", cvDouble);
  canvas.addEventListener("contextmenu", (event) => event.preventDefault());
  canvas.addEventListener("wheel", cvWheel, { passive: false });
  canvas.addEventListener("gesturestart", (event) => { event.preventDefault(); cv.gesture = cv.view.z; });
  canvas.addEventListener("gesturechange", (event) => {
    event.preventDefault();
    const box = canvas.getBoundingClientRect();
    cvSetView(zoomAt(cv.view, event.clientX - box.left, event.clientY - box.top, (cv.gesture * event.scale) / cv.view.z));
  });
  ui.editor.addEventListener("blur", cvEndEdit);
  cvResize();
  cvSync();
  cvCursor();
  cvFillPick();
  cvStart();
}

window.addEventListener("resize", () => { if (state.view === "canvas") cvResize(); });
document.addEventListener("keyup", (event) => { if (event.key === " " && cv.space) { cv.space = false; cvCursor(); } });
// A press anywhere outside the open tool menu (and its button) closes it.
document.addEventListener("pointerdown", (event) => {
  if (!cv.menu || !cv.ui.menu) return;
  const button = cv.ui.tools[cv.menu];
  if (cv.ui.menu.contains(event.target) || (button && button.contains(event.target))) return;
  cvCloseMenu();
}, true);
document.addEventListener("visibilitychange", () => { if (document.hidden && state.view === "canvas") saveCanvas(); });
// A file dropped beside the canvas must not make the browser leave the page to show it.
for (const type of ["dragover", "drop"]) document.addEventListener(type, (event) => { if (state.view === "canvas" && cvHasFiles(event)) event.preventDefault(); });
$("theme").addEventListener("click", () => { if (state.view === "canvas") cvDraw(); });
document.addEventListener("paste", (event) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement || {}).tagName || "");
  if (state.view !== "canvas" || typing || !cv.doc || cv.viewing || cv.gallery) return;
  const text = event.clipboardData ? event.clipboardData.getData("text/plain") : "";
  if (!cvHttpUrl(text)) return;
  event.preventDefault();
  clearTimeout(cv.pasteWait);
  cv.pasteWait = 0;
  cvPasteText(text);
});

// ---- theme, search, keys ----
function applyTheme(theme) {
  const dark = theme ? theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  // The tab icon follows the page theme, which can differ from the system one.
  const icon = $("favicon");
  if (icon) icon.href = icon.dataset[dark ? "dark" : "light"];
}
applyTheme(localStorage.getItem("desk-theme"));
$("theme").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("desk-theme", next);
  applyTheme(next);
});

$("search").addEventListener("input", (event) => { state.query = event.target.value.trim(); render(); });

document.addEventListener("keydown", (event) => {
  // The open boards menu owns the keyboard (its own handler moves focus and closes it).
  if (boardsOpen()) { if (event.key === "Escape") closeBoards(true); return; }
  if (gameKey(event)) return;
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
  if (state.view === "canvas" && !typing && canvasKey(event)) return;
  // Studio has its own ⌘Z, Esc, arrows and Delete, so it goes before the page-wide keys.
  if (state.view === "studio" && studioKeydown(event)) return;
  if (event.key === "Escape") {
    $("help").classList.remove("on");
    closeViewer();
    if (typing) document.activeElement.blur();
    if (state.query || state.tag) { state.query = ""; state.tag = ""; $("search").value = ""; render(); }
    return;
  }
  if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.key === "?") { $("help").classList.toggle("on"); return; }
  if (state.view === "canvas") {
    if (event.key >= "1" && event.key <= "5") setView(VIEWS[Number(event.key) - 1]);
    return;
  }
  if (event.key === "/") { event.preventDefault(); if (state.view === "games") setView("board"); $("search").focus(); }
  else if (event.key === "n") {
    event.preventDefault();
    if (state.view === "today") document.querySelector(".quick input")?.focus();
    else { if (state.view !== "board") setView("board"); document.querySelector(".add input")?.focus(); }
  }
  else if (event.key === " ") { event.preventDefault(); togglePlay(); }
  else if (event.key >= "1" && event.key <= "5") setView(VIEWS[Number(event.key) - 1]);
});

// ---- start ----
async function start() {
  if (!TOKEN) { document.body.textContent = "Open the desk with `ul desk`: this page needs its token."; return; }
  await Promise.all([loadBoard(true), loadBoards(), loadTimer(), loadGames(), loadStudioInfo()]);
  render();
  setInterval(() => { if (!document.hidden && !state.dragging && state.draggingColumn == null && !state.editing && !["games", "studio", "canvas"].includes(state.view)) loadBoard(false); }, 2000);
  setInterval(pollCanvas, 3000);
  setInterval(() => { if (!document.hidden) loadTimer(); }, 10000);
  setInterval(() => { if (!document.hidden && state.view === "games" && arcade.session) loadGames(); }, 5000);
  setInterval(drawTimer, 500);
  setInterval(drawRecording, 250);
  scheduleStudioPoll();
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { if (state.view === "games") pauseGame(); return; }
    loadBoard(false);
    loadTimer();
    scheduleStudioPoll(true);
  });
}
start();
</script>
</body>
</html>
"""
PAGE = _PAGE.replace("/*@STUDIO_CSS@*/\n", STUDIO_CSS).replace("/*@STUDIO_JS@*/\n", STUDIO_JS)
