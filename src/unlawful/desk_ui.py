"""The `ul desk` page: one HTML document with inline CSS and JS, served by desk.py.

Board text is user data, so the script builds every node with textContent and never uses innerHTML.
"""

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Desk</title>
<style>
:root {
  --bg: #f4f3ef; --panel: #ffffff; --column: #eae9e4; --sunken: #e2e0da; --text: #1d1d1f; --muted: #6e6e73;
  --line: #dad8d1; --accent: #3a6df0; --accent-soft: #e3eafd; --danger: #d4483b; --ok: #2f9e5b;
  --warn: #c98a12; --shadow: 0 1px 2px rgba(0,0,0,.06), 0 2px 8px rgba(0,0,0,.05);
  --lift: 0 2px 4px rgba(0,0,0,.07), 0 8px 24px rgba(0,0,0,.08);
  --radius: 12px; --font: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
  --mono: "SF Mono", ui-monospace, Menlo, monospace;
  color-scheme: light;
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #141416; --panel: #212124; --column: #1b1b1e; --sunken: #18181a; --text: #ececee; --muted: #9a9aa1;
  --line: #2f2f33; --accent: #6b93ff; --accent-soft: #263050; --danger: #ff6b5e; --ok: #4fc581;
  --warn: #f0b443; --shadow: 0 1px 2px rgba(0,0,0,.4), 0 2px 10px rgba(0,0,0,.25);
  --lift: 0 2px 6px rgba(0,0,0,.45), 0 10px 28px rgba(0,0,0,.35);
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body { background: var(--bg); color: var(--text); font: 14px/1.45 var(--font); display: flex; flex-direction: column; -webkit-font-smoothing: antialiased; }
button, input, select { font: inherit; color: inherit; }
button { cursor: pointer; border: 1px solid var(--line); background: var(--panel); border-radius: 8px; padding: 5px 10px; transition: background .12s, border-color .12s, color .12s; }
button:hover { border-color: var(--accent); }
button:disabled { opacity: .45; cursor: default; }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
button.primary:hover { filter: brightness(1.08); }
button.ghost { border-color: transparent; background: transparent; color: var(--muted); }
button.ghost:hover { background: var(--column); color: var(--text); }
button.icon { width: 32px; height: 32px; padding: 0; display: inline-grid; place-items: center; }
button.icon svg { width: 17px; height: 17px; stroke: currentColor; fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
input, select { border: 1px solid var(--line); background: var(--panel); border-radius: 8px; padding: 5px 9px; outline: none; }
input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

header { display: flex; align-items: center; gap: 12px; padding: 8px 16px; border-bottom: 1px solid var(--line); background: var(--panel); flex-wrap: wrap; position: relative; z-index: 2; }
.brand { display: flex; align-items: center; gap: 8px; font-weight: 680; letter-spacing: -.01em; }
.brand i { width: 22px; height: 22px; border-radius: 7px; background: linear-gradient(135deg, var(--accent), #8a5cf6); display: inline-block; }
#boards { max-width: 230px; border-color: transparent; background: var(--column); font-weight: 550; }
.tabs { display: flex; gap: 2px; background: var(--column); border-radius: 10px; padding: 3px; }
.tabs button { border: none; background: transparent; padding: 4px 13px; border-radius: 8px; color: var(--muted); font-weight: 550; }
.tabs button:hover { color: var(--text); }
.tabs button.on { background: var(--panel); box-shadow: var(--shadow); color: var(--text); }
.spacer { flex: 1; }
.timer { display: flex; align-items: center; gap: 8px; padding: 3px 4px 3px 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--bg); }
.timer .phase { font-size: 12px; color: var(--muted); }
.timer .clock { font: 600 15px var(--mono); min-width: 48px; text-align: right; }
.timer.work { border-color: color-mix(in srgb, var(--danger) 45%, var(--line)); }
.timer.work .clock { color: var(--danger); }
.timer.short .clock, .timer.long .clock { color: var(--ok); }
.timer .bar { width: 70px; height: 4px; background: var(--column); border-radius: 2px; overflow: hidden; }
.timer .bar i { display: block; height: 100%; background: currentColor; width: 0; transition: width .5s linear; }
.timer.work .bar i { background: var(--danger); }
.timer.short .bar i, .timer.long .bar i { background: var(--ok); }
.timer .linked { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: var(--muted); }
.timer button { padding: 2px 10px; border-radius: 999px; }
.timer #play { background: var(--text); color: var(--bg); border-color: var(--text); }
.actions-bar { display: flex; gap: 2px; }

.toolbar { display: flex; align-items: center; gap: 10px; padding: 10px 16px 0; flex-wrap: wrap; }
.toolbar.hidden { display: none; }
.search { position: relative; }
.search input { width: 240px; padding-left: 30px; background: var(--panel); }
.search svg { position: absolute; left: 9px; top: 50%; transform: translateY(-50%); width: 15px; height: 15px; stroke: var(--muted); fill: none; stroke-width: 2; }
#filter { display: none; }
#filter.on { display: inline-flex; }
.summary { display: flex; gap: 6px; flex-wrap: wrap; }
.pill { font-size: 12px; padding: 2px 9px; border-radius: 999px; background: var(--column); color: var(--muted); }
.pill b { color: var(--text); font-weight: 600; }
.pill.late b { color: var(--danger); }
.pill.today b { color: var(--warn); }

main { flex: 1; overflow: auto; }
.board { display: flex; gap: 14px; padding: 14px 16px 16px; align-items: flex-start; min-height: 100%; }
.column { background: var(--column); border-radius: var(--radius); width: 296px; flex: 0 0 296px; display: flex; flex-direction: column; max-height: calc(100vh - 128px); border-top: 3px solid transparent; }
.column.doing { border-top-color: var(--warn); }
.column.done { border-top-color: var(--ok); }
.column.drop { outline: 2px dashed var(--accent); outline-offset: -2px; }
.column h2 { font-size: 13px; font-weight: 650; margin: 0; padding: 10px 10px 6px 12px; display: flex; gap: 6px; align-items: center; }
.column h2 .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.column h2 .count { color: var(--muted); font-weight: 600; font-size: 11px; background: var(--sunken); border-radius: 999px; padding: 0 7px; line-height: 18px; }
.column h2 button { padding: 0; width: 22px; height: 22px; line-height: 1; border: none; background: transparent; color: var(--muted); border-radius: 6px; font-size: 17px; }
.column h2 button:hover { background: var(--sunken); color: var(--text); }
.cards { padding: 4px 8px; overflow-y: auto; flex: 1; min-height: 20px; }
.card { background: var(--panel); border-radius: 9px; box-shadow: var(--shadow); padding: 9px 10px; margin-bottom: 7px; display: flex; gap: 9px; align-items: flex-start; cursor: grab; position: relative; border: 1px solid transparent; transition: box-shadow .12s, transform .12s; }
.card:hover { box-shadow: var(--lift); }
.card.dragging { opacity: .4; }
.card.focus { border-color: var(--danger); box-shadow: 0 0 0 3px color-mix(in srgb, var(--danger) 18%, transparent); }
.card.checked .text { color: var(--muted); text-decoration: line-through; }
.card .check { width: 17px; height: 17px; border-radius: 50%; border: 1.5px solid var(--muted); flex: 0 0 17px; margin-top: 1px; padding: 0; background: transparent; position: relative; }
.card .check:hover { border-color: var(--ok); background: var(--accent-soft); }
.card.checked .check { background: var(--ok); border-color: var(--ok); }
.card.checked .check::after { content: ""; position: absolute; left: 5px; top: 2px; width: 4px; height: 8px; border: solid #fff; border-width: 0 2px 2px 0; transform: rotate(45deg); }
.card .body { flex: 1; min-width: 0; word-wrap: break-word; }
.card .meta { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 5px; }
.card .details { margin-top: 4px; color: var(--muted); font-size: 12px; white-space: pre-wrap; }
.card .actions { display: none; gap: 2px; position: absolute; right: 6px; top: 5px; background: var(--panel); border-radius: 7px; box-shadow: var(--shadow); padding: 2px; }
.card:hover .actions { display: flex; }
.card .actions button { padding: 1px 7px; font-size: 12px; border: none; background: transparent; }
.card .actions button:hover { background: var(--column); }
.card input.edit { width: 100%; }
.chip { display: inline-block; font-size: 11px; padding: 0 7px; border-radius: 999px; background: var(--accent-soft); color: var(--accent); cursor: pointer; border: none; line-height: 18px; }
.chip.due { background: var(--column); color: var(--muted); cursor: default; }
.chip.today { background: #fdf0d5; color: #8a5d00; }
.chip.late { background: #fde2df; color: #a8291d; }
:root[data-theme="dark"] .chip.today { background: #4a3a14; color: #f5cf7a; }
:root[data-theme="dark"] .chip.late { background: #4d1f1b; color: #ff9d93; }
.link { color: var(--accent); cursor: pointer; text-decoration: underline; text-underline-offset: 2px; }
.add { padding: 6px 8px 10px; }
.add input { width: 100%; background: transparent; border-style: dashed; }
.add input:focus { background: var(--panel); border-style: solid; }
.newcol { flex: 0 0 220px; }
.newcol input { width: 100%; background: transparent; border-style: dashed; padding: 9px 12px; }
.page { max-width: 780px; margin: 0 auto; padding: 18px 16px 60px; }
.page h3 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 26px 0 8px; display: flex; align-items: center; gap: 8px; }
.page h3 .n { background: var(--column); border-radius: 999px; padding: 0 7px; letter-spacing: 0; }
.page .quick { display: flex; gap: 8px; }
.page .quick input { flex: 1; padding: 10px 14px; border-radius: 10px; box-shadow: var(--shadow); }
.page .card { cursor: default; }
.page .where { font-size: 11px; color: var(--muted); }
.empty { color: var(--muted); padding: 8px 2px; }
.numbers { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.number { background: var(--panel); border-radius: var(--radius); box-shadow: var(--shadow); padding: 14px; }
.number b { display: block; font-size: 26px; font-weight: 650; letter-spacing: -.02em; }
.number span { color: var(--muted); font-size: 12px; }
.week { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; align-items: end; height: 160px; background: var(--panel); border-radius: var(--radius); box-shadow: var(--shadow); padding: 14px; }
.day { display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; gap: 4px; font-size: 11px; color: var(--muted); }
.day .bars { display: flex; gap: 3px; align-items: flex-end; flex: 1; }
.day .bars i { display: block; width: 12px; border-radius: 3px 3px 0 0; min-height: 2px; }
.day .bars i.f { background: var(--danger); }
.day .bars i.d { background: var(--ok); }
.legend { display: flex; gap: 14px; font-size: 12px; color: var(--muted); margin-top: 6px; }
.legend i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 5px; }
.top { background: var(--panel); border-radius: var(--radius); box-shadow: var(--shadow); padding: 6px 14px; }
.top div { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--line); }
.top div:last-child { border-bottom: none; }

.arcade { display: grid; grid-template-columns: 272px 1fr; gap: 14px; padding: 14px 16px 16px; height: 100%; min-height: 460px; }
.side { display: flex; flex-direction: column; gap: 10px; min-height: 0; overflow-y: auto; }
.side h4 { margin: 6px 2px 0; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.levels { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px; background: var(--column); border-radius: 10px; padding: 3px; }
.levels button { border: none; background: transparent; border-radius: 8px; padding: 5px 0; color: var(--muted); font-weight: 550; }
.levels button.on { background: var(--panel); box-shadow: var(--shadow); color: var(--text); }
.levels button.on.hard { color: var(--danger); }
.tile { display: grid; grid-template-columns: 1fr auto; gap: 2px 8px; text-align: left; padding: 10px 12px; border-radius: 10px; background: var(--panel); border: 1px solid transparent; box-shadow: var(--shadow); }
.tile:hover { border-color: var(--accent); }
.tile.on { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.tile b { font-weight: 650; }
.tile small { grid-column: 1 / -1; color: var(--muted); font-size: 12px; line-height: 1.35; }
.tile .best { font: 600 12px var(--mono); color: var(--warn); align-self: center; }
.tile .best.none { color: var(--muted); font-weight: 400; }
.records { background: var(--panel); border-radius: 10px; box-shadow: var(--shadow); padding: 6px 10px; font-size: 12px; }
.records table { width: 100%; border-collapse: collapse; }
.records th { color: var(--muted); font-weight: 500; text-align: right; padding: 3px 0; }
.records th:first-child, .records td:first-child { text-align: left; }
.records td { text-align: right; padding: 3px 0; font-family: var(--mono); border-top: 1px solid var(--line); }
.records td:first-child { font-family: var(--font); }
.stage { display: flex; flex-direction: column; min-height: 0; min-width: 0; gap: 8px; }
.screen { flex: 1; min-height: 0; background: #0e1014; border-radius: var(--radius); display: grid; place-items: center; position: relative; overflow: hidden; box-shadow: inset 0 0 0 1px rgba(255,255,255,.04), var(--shadow); }
.screen canvas { display: block; cursor: crosshair; }
.screen .idle { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: #c9ccd4; text-align: center; padding: 20px; }
.screen .idle b { font: 700 22px var(--mono); letter-spacing: .3em; color: #ffd84d; }
.screen .idle span { color: #8b8f98; font-size: 13px; }
.screen:fullscreen { border-radius: 0; }
.status { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.status .what { font-weight: 600; }
.status .hint { color: var(--muted); font-size: 12px; flex: 1; }
.status .live { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
.status .live.on { background: var(--ok); box-shadow: 0 0 0 3px color-mix(in srgb, var(--ok) 25%, transparent); }

#toast { position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%) translateY(6px); background: var(--text); color: var(--bg); padding: 8px 14px; border-radius: 9px; opacity: 0; transition: opacity .2s, transform .2s; pointer-events: none; max-width: 80vw; box-shadow: var(--lift); z-index: 20; }
#toast.on { opacity: .96; transform: translateX(-50%); }
kbd { font: 11px var(--mono); border: 1px solid var(--line); border-bottom-width: 2px; border-radius: 5px; padding: 0 5px; background: var(--panel); }
#help { position: fixed; inset: 0; background: rgba(0,0,0,.35); display: none; place-items: center; z-index: 10; }
#help.on { display: grid; }
#help .sheet { background: var(--panel); border-radius: 14px; box-shadow: var(--lift); padding: 18px 22px; width: min(460px, 92vw); }
#help h3 { margin: 0 0 10px; font-size: 15px; }
#help dl { display: grid; grid-template-columns: auto 1fr; gap: 7px 16px; margin: 0; font-size: 13px; }
#help dt { text-align: right; white-space: nowrap; }
#help dd { margin: 0; color: var(--muted); }
.studio { display: grid; grid-template-columns: 300px 1fr; gap: 14px; padding: 14px 16px 16px; min-height: 100%; align-items: start; }
.controls { position: sticky; top: 14px; display: flex; flex-direction: column; gap: 9px; background: var(--panel); border-radius: var(--radius); box-shadow: var(--shadow); padding: 12px 14px 14px; }
.controls h4 { margin: 6px 0 0; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.controls label { display: grid; gap: 3px; font-size: 12px; color: var(--muted); }
.controls label.check { display: flex; align-items: center; gap: 7px; color: var(--text); font-size: 13px; }
.controls select { width: 100%; }
.modes { grid-template-columns: repeat(2, 1fr); }
.recbox { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 12px 0 4px; }
.recbtn { width: 64px; height: 64px; border-radius: 50%; border: 3px solid var(--line); background: var(--panel); display: grid; place-items: center; padding: 0; }
.recbtn i { width: 26px; height: 26px; border-radius: 50%; background: #e5484d; transition: border-radius .15s, width .15s, height .15s; }
.recbtn.on i { width: 22px; height: 22px; border-radius: 5px; }
.recbtn:hover { border-color: #e5484d; }
.recclock { font: 600 22px var(--mono); letter-spacing: .02em; }
.recclock.live { color: #e5484d; }
.recstate { font-size: 12px; color: var(--muted); text-align: center; min-height: 16px; }
.row { display: flex; gap: 6px; flex-wrap: wrap; }
.row button { flex: 1; }
.monitor { position: relative; background: #0e1014; border-radius: var(--radius); aspect-ratio: 16 / 10; max-height: 58vh; width: 100%; overflow: hidden; display: grid; place-items: center; box-shadow: var(--shadow); }
.monitor img.screen { width: 100%; height: 100%; object-fit: contain; }
.monitor video.cam { position: absolute; width: 24%; border-radius: 10px; box-shadow: 0 4px 18px rgba(0,0,0,.5); background: #000; transform: scaleX(-1); }
.monitor video.cam.full { position: static; width: 100%; height: 100%; object-fit: contain; border-radius: 0; box-shadow: none; }
.monitor video.cam.bottom-right { right: 3%; bottom: 4%; } .monitor video.cam.bottom-left { left: 3%; bottom: 4%; }
.monitor video.cam.top-right { right: 3%; top: 4%; } .monitor video.cam.top-left { left: 3%; top: 4%; }
.monitor .note { color: #8b8f98; text-align: center; padding: 20px; font-size: 13px; }
.monitor .meter { width: 70%; height: 14px; border-radius: 7px; background: #23262d; overflow: hidden; }
.monitor .meter i { display: block; height: 100%; width: 0; background: linear-gradient(90deg, #3ed67a, #ffd84d 75%, #ff5f57); transition: width .06s linear; }
.monitor .badge { position: absolute; left: 12px; top: 12px; background: rgba(229,72,77,.92); color: #fff; font: 600 12px var(--mono); padding: 3px 9px; border-radius: 999px; display: none; }
.monitor .badge.on { display: block; }
.monitor .badge.paused { background: rgba(120,120,128,.9); }
.monbar { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin: 8px 0 4px; }
.monbar .hint { color: var(--muted); font-size: 12px; flex: 1; }
.libhead { display: flex; align-items: center; gap: 10px; margin: 16px 0 8px; }
.libhead h3 { margin: 0; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.libhead .levels { grid-template-columns: repeat(4, auto); }
.libhead .levels button { padding: 3px 10px; }
.library { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 10px; }
.item { background: var(--panel); border-radius: 10px; box-shadow: var(--shadow); overflow: hidden; cursor: pointer; border: 1px solid transparent; text-align: left; padding: 0; display: flex; flex-direction: column; }
.item:hover { border-color: var(--accent); box-shadow: var(--lift); }
.item .pic { aspect-ratio: 16 / 10; background: #15171c center / cover no-repeat; display: grid; place-items: center; color: #8b8f98; position: relative; }
.item .pic img { width: 100%; height: 100%; object-fit: cover; }
.item .pic .len { position: absolute; right: 6px; bottom: 6px; background: rgba(0,0,0,.7); color: #fff; font: 11px var(--mono); padding: 1px 6px; border-radius: 5px; }
.item .pic svg { width: 34px; height: 34px; stroke: #8b8f98; fill: none; stroke-width: 1.6; }
.item .cap { padding: 7px 9px 8px; font-size: 12px; }
.item .cap b { display: block; font-weight: 550; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item .cap span { color: var(--muted); }
.rec-pill { display: none; border: none; background: rgba(229,72,77,.12); color: #e5484d; font: 600 12px var(--mono); border-radius: 999px; padding: 4px 10px; }
.rec-pill.on { display: inline-flex; gap: 6px; align-items: center; }
.rec-pill.on::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: #e5484d; animation: blink 1.2s infinite; }
.rec-pill.paused::before { animation: none; background: var(--muted); }
@keyframes blink { 50% { opacity: .25; } }
#viewer { position: fixed; inset: 0; background: rgba(0,0,0,.55); display: none; place-items: center; z-index: 12; }
#viewer.on { display: grid; }
#viewer .sheet { background: var(--panel); border-radius: 14px; box-shadow: var(--lift); width: min(1100px, 94vw); max-height: 94vh; overflow: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
#viewer .media { background: #0e1014; border-radius: 10px; display: grid; place-items: center; min-height: 120px; }
#viewer .media video, #viewer .media img { max-width: 100%; max-height: 66vh; display: block; }
#viewer .media audio { width: 90%; margin: 30px 0; }
#viewer .top { display: flex; align-items: center; gap: 10px; background: none; box-shadow: none; padding: 0; }
#viewer .top b { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#viewer .tools { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
#viewer .tools .sep { width: 1px; height: 22px; background: var(--line); margin: 0 4px; }
#viewer .tools .mark { font: 12px var(--mono); color: var(--muted); }
.voice { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: stretch; justify-content: center; gap: 10px; padding: 18px; }
.voice-clock { font: 600 34px var(--mono); color: #f2f2f7; text-align: center; letter-spacing: .02em; }
.voice .note { position: static; }
canvas.wave { width: 100%; height: 46%; display: block; }
canvas.wave.strip { position: absolute; left: 0; right: 0; bottom: 0; height: 64px; background: linear-gradient(transparent, rgba(0,0,0,.55)); }
#viewer canvas.filewave { width: 100%; height: 96px; display: block; cursor: pointer; background: #0e1014; border-radius: 10px; }
@media (max-width: 860px) { .studio { grid-template-columns: 1fr; } .controls { position: static; } }
@media (max-width: 760px) {
  .arcade { grid-template-columns: 1fr; height: auto; }
  .screen { min-height: 360px; }
  .search input { width: 170px; }
}
</style>
</head>
<body>
<header>
  <span class="brand"><i></i>Desk</span>
  <select id="boards" title="Boards"></select>
  <div class="tabs" id="tabs">
    <button data-view="board" class="on" title="Board (1)">Board</button>
    <button data-view="today" title="Today (2)">Today</button>
    <button data-view="stats" title="Stats (3)">Stats</button>
    <button data-view="games" title="Games (4)">Games</button>
    <button data-view="studio" title="Studio: record and screenshots (5)">Studio</button>
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
    <dt><kbd>1</kbd> … <kbd>5</kbd></dt><dd>Board, Today, Stats, Games, Studio</dd>
    <dt><kbd>Esc</kbd></dt><dd>Clear search and tag filter</dd>
    <dt>double-click</dt><dd>Edit a card; drag cards between columns</dd>
    <dt>Games</dt><dd>While a game runs every key goes to it: arrows/WASD, Space, P pause, Esc leaves. Mouse works as in the terminal.</dd>
    <dt>Studio</dt><dd><kbd>r</kbd> start / stop recording, <kbd>p</kbd> pause / resume. Recording runs <code>ul capture</code>, so it keeps going when the page is closed.</dd>
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
const VIEWS = ["board", "today", "stats", "games", "studio"];
const state = { board: null, view: VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : localStorage.getItem("desk-view") || "board", query: "", tag: "", timer: null, timerAt: 0, editing: null, dragging: null, stats: null };
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
  if (!state.editing && !["games", "studio"].includes(state.view)) render();
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

const MARKUP = /(\[\[[^\]]+\]\])|(?<![\w&/])#([^\s#\[\]{}(),.;:!?'"]+)|@\{(\d{4}-\d{2}-\d{2})\}|📅\s*(\d{4}-\d{2}-\d{2})|\s*\[completion::\s*\d{4}-\d{2}-\d{2}\]/gu;

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
    h("button", { title: "Delete", text: "✕", onclick: (event) => { event.stopPropagation(); if (confirm("Delete this card?\n\n" + card.title)) change({ op: "delete", ...where }); } }));
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
    const node = h("section", { class: "column" + (column.doing ? " doing" : "") + (done ? " done" : "") },
      h("h2", {}, h("span", { class: "name", text: column.name, title: column.name }),
        h("span", { class: "count", text: state.query || state.tag ? shown + "/" + column.cards.length : column.cards.length }),
        h("button", { title: "Add a card to " + column.name, text: "+", onclick: () => input.focus() })),
      list, h("div", { class: "add" }, input));
    node.addEventListener("dragover", (event) => {
      if (!state.dragging) return;
      event.preventDefault();
      node.classList.add("drop");
    });
    node.addEventListener("dragleave", (event) => { if (!node.contains(event.relatedTarget)) node.classList.remove("drop"); });
    node.addEventListener("drop", (event) => {
      event.preventDefault();
      node.classList.remove("drop");
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
  const page = h("div", { class: "page" }, h("div", { class: "quick" }, quick));
  const section = (title, items) => {
    page.append(h("h3", {}, title, h("span", { class: "n", text: items.length })));
    if (!items.length) page.append(h("div", { class: "empty", text: "Nothing here." }));
    for (const item of items) page.append(cardNode(item.card, item.c, item.i, { where: item.where }));
  };
  section("Overdue", late);
  section("Today", due);
  section("In progress", doing);
  section("Next 7 days", soon);
  main.append(page);
}

function addDays(iso, days) {
  const date = new Date(iso + "T12:00:00");
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

async function renderStats(main) {
  const { status, data } = await api("GET", "/api/stats");
  if (status !== 200) { toast(data.error || "Could not load stats"); return; }
  if (state.view !== "stats") return;
  main.textContent = "";
  const page = h("div", { class: "page" });
  page.append(h("h3", { text: "Today" }), h("div", { class: "numbers" },
    h("div", { class: "number" }, h("b", { text: data.today.pomodoros }), h("span", { text: "focus sessions" })),
    h("div", { class: "number" }, h("b", { text: Math.round(data.today.minutes) }), h("span", { text: "focus minutes" })),
    h("div", { class: "number" }, h("b", { text: data.today.done }), h("span", { text: "tasks done" })),
    h("div", { class: "number" }, h("b", { text: data.streak }), h("span", { text: "day streak" }))));
  const most = Math.max(1, ...data.week.map((day) => Math.max(day.pomodoros, day.done)));
  page.append(h("h3", { text: "Last 7 days" }), h("div", { class: "week" }, data.week.map((day) => h("div", { class: "day", title: day.date + ": " + day.pomodoros + " focus, " + day.minutes + " min, " + day.done + " done" },
    h("div", { class: "bars" }, h("i", { class: "f", style: "height:" + (day.pomodoros / most * 100) + "%" }), h("i", { class: "d", style: "height:" + (day.done / most * 100) + "%" })),
    h("span", { text: new Date(day.date + "T12:00:00").toLocaleDateString(undefined, { weekday: "short" }) })))));
  page.append(h("div", { class: "legend" }, h("span", {}, h("i", { style: "background:var(--danger)" }), "focus sessions"), h("span", {}, h("i", { style: "background:var(--ok)" }), "tasks done")));
  page.append(h("h3", { text: "Most focused cards" }));
  page.append(data.cards.length
    ? h("div", { class: "top" }, data.cards.map((item) => h("div", {}, h("span", { text: item.card }), h("span", { class: "where", text: Math.round(item.minutes) + " min" }))))
    : h("div", { class: "empty", text: "Start a focus session from a card (Focus) to see time per card." }));
  page.append(h("div", { class: "where", style: "margin-top:18px", text: "All time: " + data.total_pomodoros + " focus sessions" }));
  main.append(page);
}

function render() {
  const main = $("main");
  for (const button of $("tabs").children) button.classList.toggle("on", button.dataset.view === state.view);
  $("toolbar").classList.toggle("hidden", ["games", "stats", "studio"].includes(state.view));
  const filter = $("filter");
  filter.classList.toggle("on", Boolean(state.tag));
  filter.textContent = state.tag ? "#" + state.tag + " ✕" : "";
  renderSummary();
  if (state.view === "games") { renderGames(main); return; }
  if (state.view === "studio") { renderStudio(main); return; }
  if (!state.board) return;
  if (state.view === "stats") { renderStats(main); return; }
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
};
const PALETTE = { red: "#ff5f57", green: "#3ed67a", yellow: "#ffd84d", blue: "#4d8dff", magenta: "#d77bff", cyan: "#4fd8e8", white: "#f4f5f7", gray: "#8b8f98", darkred: "#c0392b", darkyellow: "#c9971c", darkblue: "#3159c9", darkcyan: "#1f9aa8" };
const SCREEN_BG = "#0e1014", SCREEN_FG = "#d9dce3";
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
  return best === undefined ? null : game.lower ? best + "s" : String(best);
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
  if (char === "▀" || char === "▄") {
    const middle = Math.round(y + h / 2);
    context.fillStyle = color;
    context.fillRect(left, char === "▀" ? top : middle, right - left, char === "▀" ? middle - top : bottom - middle);
    return;
  }
  context.fillStyle = color;
  context.fillText(char, x + w / 2, y + h / 2 + 1);
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

const GAME_KEYS = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Enter: "enter", Escape: "esc" };
function gameKey(event) {
  if (state.view !== "games" || !arcade.session || event.metaKey || event.ctrlKey || event.altKey) return false;
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) return false;
  const key = GAME_KEYS[event.key] || (event.key.length === 1 ? event.key : null);
  if (!key) return false;
  event.preventDefault();
  sendGame([{ key }]);
  return true;
}

let resizeTimer = 0;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (state.view === "games") fitScreen(); }, 150); });
document.addEventListener("fullscreenchange", () => setTimeout(fitScreen, 60));

// ---- studio: recording, screenshots and the library through `ul capture` ----
const studio = { info: null, devices: null, status: { active: false }, statusAt: 0, library: [], filter: localStorage.getItem("studio-filter") || "all", mode: localStorage.getItem("studio-mode") || "screen", display: 1, mic: "", cam: "", system: null, clicks: null, format: "", delay: 0, clipboard: false, preview: localStorage.getItem("studio-preview") !== "off", previewBusy: false, previewTimer: 0, camStream: null, micStream: null, audio: null, saving: false, item: null, trim: { from: null, to: null }, starting: 0, shown: 0, levels: [], analyser: null, sampler: 0, wave: null };
const media = (path, name) => path + "?t=" + encodeURIComponent(TOKEN) + (name ? "&name=" + encodeURIComponent(name) : "");

async function loadStudioInfo() {
  const { status, data } = await api("GET", "/api/studio");
  if (status !== 200) return;
  studio.info = data;
  if (data.available) loadRecordStatus();
}

async function loadRecordStatus() {
  const { status, data } = await api("GET", "/api/studio/status");
  if (status !== 200) return;
  const was = studio.status;
  studio.status = data;
  studio.statusAt = Date.now();
  if (studio.saving && data.saving_done) {
    studio.saving = false;
    if (data.saving_done.error) toast(data.saving_done.error);
    else { toast("Saved " + data.saving_done.saved.split("/").pop()); loadLibrary(true); }
  }
  if (was.active && !data.active && !studio.saving) loadLibrary();
  if (!data.active) for (const item of studio.levels) item.live = false;
  drawRecording();
  if (state.view === "studio") {
    updateStudioControls();
    // Started or finished (maybe from the terminal): bring the preview back or pause it.
    if (Boolean(was.active) !== Boolean(data.active) && !studio.starting) renderMonitor();
  }
  if ((data.active || studio.saving) && !busyTimer) pollWhileBusy();
}

function recordElapsed() {
  const s = studio.status;
  if (studio.starting) return (Date.now() - studio.starting) / 1000;
  if (!s.active) return 0;
  const value = s.elapsed + (s.phase === "recording" ? (Date.now() - studio.statusAt) / 1000 : 0);
  // Polls arrive a little late; never let the clock step backwards while recording.
  if (s.phase === "recording") studio.shown = Math.max(studio.shown, value);
  else studio.shown = value;
  return studio.shown;
}

function drawRecording() {
  const s = studio.status, pill = $("recPill");
  const live = Boolean(studio.starting) || (s.active && s.phase === "recording");
  const active = s.active || studio.saving || Boolean(studio.starting);
  pill.className = "rec-pill" + (active ? " on" : "") + (s.paused ? " paused" : "");
  pill.textContent = studio.saving || s.phase === "saving" ? "Saving…" : active ? (s.paused ? "Paused " : "REC ") + clockText(recordElapsed()) : "";
  const clock = $("recClock");
  if (clock) {
    clock.textContent = clockText(recordElapsed());
    clock.classList.toggle("live", live);
  }
  const badge = $("monBadge");
  if (badge) {
    badge.className = "badge" + (active && !studio.saving ? " on" : "") + (s.paused ? " paused" : "");
    badge.textContent = s.paused ? "❚❚ PAUSED " + clockText(recordElapsed()) : "● REC " + clockText(recordElapsed());
  }
  const waveClock = $("waveClock");
  if (waveClock) waveClock.textContent = clockText(recordElapsed());
}

async function loadDevices() {
  const { status, data } = await api("GET", "/api/studio/devices");
  if (status !== 200) { toast(data.error || "Could not list devices"); return; }
  studio.devices = data;
  if (state.view === "studio") renderStudioControls();
}

async function loadLibrary(openNewest) {
  const { status, data } = await api("GET", "/api/studio/library");
  if (status !== 200) return;
  studio.library = data;
  if (state.view === "studio") renderLibrary();
  if (openNewest && data.length) openViewer(data[0]);
}

function leaveStudio() {
  clearTimeout(studio.previewTimer);
  stopStream("camStream");
  stopStream("micStream");
  closeViewer();
}

function stopStream(key) {
  const request = key === "camStream" ? "camRequest" : "micRequest";
  studio[request] = (studio[request] || 0) + 1;
  if (studio[key]) { studio[key].getTracks().forEach((track) => track.stop()); studio[key] = null; }
  if (key === "micStream") {
    clearInterval(studio.sampler);
    studio.analyser = null;
    if (studio.audio) { studio.audio.close(); studio.audio = null; }
  }
}

function fitCanvas(canvas) {
  const scale = window.devicePixelRatio || 1;
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (canvas.width !== Math.round(width * scale) || canvas.height !== Math.round(height * scale)) {
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
  }
  const context = canvas.getContext("2d");
  context.setTransform(scale, 0, 0, scale, 0, 0);
  context.clearRect(0, 0, width, height);
  return [context, width, height];
}

function bars(context, x, height, value, width, color) {
  const tall = Math.max(2, value * (height - 8));
  context.fillStyle = color;
  context.beginPath();
  context.roundRect(x, (height - tall) / 2, width, tall, width / 2);
  context.fill();
}

// The live microphone: bars scroll left into a playhead, red for what is being recorded.
function drawWave() {
  const canvas = $("wave");
  if (!canvas) return;
  const [context, width, height] = fitCanvas(canvas);
  const step = 5, head = Math.round(width * (canvas.classList.contains("strip") ? 0.97 : 0.72));
  context.fillStyle = "rgba(255,255,255,.10)";
  context.fillRect(0, height / 2 - 0.5, width, 1);
  const shown = studio.levels.slice(-Math.floor(head / step));
  shown.forEach((item, index) => bars(context, head - (shown.length - index) * step, height, item.v, 3, item.live ? "#ff453a" : "#8e8e93"));
  const recording = Boolean(studio.starting || (studio.status.active && studio.status.phase === "recording"));
  context.fillStyle = recording ? "#ff453a" : "#6b93ff";
  context.fillRect(head, 4, 2, height - 8);
  context.beginPath();
  context.arc(head + 1, 5, 4, 0, Math.PI * 2);
  context.fill();
}

function renderStudio(main) {
  if (!studio.info) { main.textContent = ""; main.append(h("div", { class: "page" }, h("div", { class: "empty", text: "Loading…" }))); loadStudioInfo().then(() => state.view === "studio" && render()); return; }
  if (!studio.info.available) {
    main.textContent = "";
    main.append(h("div", { class: "page" }, h("h3", { text: "Studio" }), h("div", { class: "empty", text: "The capture command is not installed in this ul. Turn on the `capture` feature with: ul features" })));
    return;
  }
  if (main.querySelector(".studio")) return;
  main.textContent = "";
  const monitor = h("div", { class: "monitor", id: "monitor" }, h("span", { class: "badge", id: "monBadge" }));
  const bar = h("div", { class: "monbar" },
    h("button", { id: "togglePreview", onclick: () => { studio.preview = !studio.preview; localStorage.setItem("studio-preview", studio.preview ? "on" : "off"); renderMonitor(); } }),
    h("button", { id: "toggleCam", onclick: toggleCamera }),
    h("button", { id: "toggleMic", onclick: toggleMeter }),
    h("span", { class: "hint", id: "monHint" }),
    h("button", { class: "ghost", text: "Devices ↻", title: "Look for cameras and microphones again", onclick: loadDevices }));
  const filters = h("div", { class: "levels", id: "libFilters" }, [["all", "All"], ["video", "Video"], ["audio", "Audio"], ["image", "Screenshots"]].map(([value, label]) =>
    h("button", { "data-filter": value, text: label, onclick: () => { studio.filter = value; localStorage.setItem("studio-filter", value); renderLibrary(); } })));
  const stage = h("section", {}, monitor, bar,
    h("div", { class: "libhead" }, h("h3", { text: "Library" }), filters, h("span", { class: "spacer" }), h("button", { class: "ghost", text: "Refresh", onclick: () => loadLibrary() })),
    h("div", { class: "library", id: "library" }));
  main.append(h("div", { class: "studio" }, h("aside", { class: "controls", id: "studioControls" }), stage));
  const settings = studio.info.settings;
  if (studio.system === null) studio.system = settings.system_audio;
  if (studio.clicks === null) studio.clicks = settings.show_clicks;
  renderStudioControls();
  renderLibrary();
  renderMonitor();
  if (!studio.devices) loadDevices();
  loadLibrary();
  loadRecordStatus();
}

function field(label, control) { return h("label", {}, label, control); }
function check(label, value, onchange) {
  const input = h("input", { type: "checkbox" });
  input.checked = value;
  input.addEventListener("change", () => onchange(input.checked));
  return h("label", { class: "check" }, input, label);
}
function select(options, value, onchange) {
  const node = h("select", {}, options.map(([v, label]) => h("option", { value: v, text: label, selected: v === value })));
  node.addEventListener("change", () => onchange(node.value));
  return node;
}

function renderStudioControls() {
  const box = $("studioControls");
  if (!box) return;
  box.textContent = "";
  const settings = studio.info.settings, devices = studio.devices;
  const screenMode = studio.mode === "screen" || studio.mode === "screen-camera";
  const cameraMode = studio.mode === "camera" || studio.mode === "screen-camera";
  box.append(h("h4", { text: "Record" }), h("div", { class: "levels modes" }, [["screen", "Screen"], ["screen-camera", "Screen + Cam"], ["camera", "Camera"], ["audio", "Audio"]].map(([value, label]) =>
    h("button", { class: value === studio.mode ? "on" : "", text: label, disabled: studio.status.active, onclick: () => { studio.mode = value; studio.format = ""; localStorage.setItem("studio-mode", value); renderStudioControls(); renderMonitor(); } }))));
  if (screenMode) {
    const displays = devices ? devices.displays.map((item) => [String(item.number), item.number + " · " + item.name]) : [["1", "1 · Main display"]];
    box.append(field("Display", select(displays, String(studio.display), (value) => { studio.display = Number(value); renderMonitor(); })));
  }
  if (cameraMode) {
    const cams = [["", "Default (" + settings.camera_device + ")"], ...(devices ? devices.cameras.map((name) => [name, name]) : [])];
    box.append(field("Camera", select(cams, studio.cam, (value) => { studio.cam = value; if (studio.camStream) { stopStream("camStream"); toggleCamera(); } })));
  }
  const mics = [["", "Default (" + settings.audio_device + ")"], ...(devices ? devices.microphones.map((item) => [item.name, item.name + (item.virtual ? " (virtual)" : "")]) : []), ...(studio.mode === "audio" ? [] : [["none", "No microphone"]])];
  box.append(field("Microphone", select(mics, studio.mic, (value) => { studio.mic = value; const chosen = devices?.microphones.find((item) => item.name === value); if (chosen?.virtual) toast(value + " is virtual: it carries app audio, not your voice"); })));
  if (screenMode) {
    box.append(check("System audio (sound of the Mac)", studio.system, (value) => { studio.system = value; }));
    box.append(check("Show clicks", studio.clicks, (value) => { studio.clicks = value; }));
  }
  const formats = studio.mode === "audio" ? [["", "Default (" + settings.audio_format + ")"], ["m4a", "M4A"], ["mp3", "MP3"], ["wav", "WAV"]] : [["", "Default (" + settings.video_format + ")"], ["mov", "MOV"], ["mp4", "MP4"]];
  box.append(field("Format", select(formats, studio.format, (value) => { studio.format = value; })));
  box.append(h("div", { class: "recbox" },
    h("button", { class: "recbtn" + (studio.status.active ? " on" : ""), id: "recButton", title: "Start / stop recording (r)", onclick: toggleRecord }, h("i")),
    h("span", { class: "recclock", id: "recClock", text: "00:00" }),
    h("div", { class: "row" },
      h("button", { id: "recPause", text: studio.status.paused ? "Resume" : "Pause", disabled: !studio.status.active || studio.saving, onclick: pauseRecord, title: "Pause / resume (p)" })),
    h("div", { class: "recstate", id: "recState" })));
  box.append(h("h4", { text: "Screenshot" }), h("div", { class: "row" },
    ["screen", "area", "window"].map((kind) => h("button", { text: kind[0].toUpperCase() + kind.slice(1), title: kind === "screen" ? "The whole display" : "Select on the Mac with the mouse", onclick: () => takeShot(kind) }))));
  box.append(field("Delay", select([["0", "No delay"], ["3", "3 s"], ["5", "5 s"], ["10", "10 s"]], String(studio.delay), (value) => { studio.delay = Number(value); })));
  box.append(check("Copy to the clipboard instead of saving", studio.clipboard, (value) => { studio.clipboard = value; }));
  updateStudioControls();
}

function updateStudioControls() {
  const s = studio.status;
  const button = $("recButton");
  if (!button) return;
  const active = Boolean(s.active || studio.starting);
  button.classList.toggle("on", active);
  $("recPause").disabled = !s.active || studio.saving || s.phase === "saving" || Boolean(studio.starting);
  $("recPause").textContent = s.paused ? "Resume" : "Pause";
  const what = s.active ? (s.camera ? "screen + camera" : s.mode) : "";
  $("recState").textContent = studio.starting ? "Starting…" : studio.saving || s.phase === "saving" ? "Saving… (adding camera and microphone)" : s.phase === "interrupted" ? "Stopped unexpectedly — press stop to save" : s.phase === "unsaved" ? "Not saved — press stop to try again" : s.active ? (s.paused ? "Paused · " : "Recording ") + what : "Ready";
  for (const node of document.querySelectorAll(".modes button")) node.disabled = active;
  drawRecording();
}

async function toggleRecord() {
  if (studio.saving || studio.starting) return;
  if (studio.status.active) {
    studio.saving = true;
    for (const item of studio.levels) item.live = false;
    updateStudioControls();
    const { status, data } = await api("POST", "/api/studio/stop", {});
    if (status !== 200) { studio.saving = false; toast(data.error || "Could not stop"); }
    pollWhileBusy();
    return;
  }
  const body = { mode: studio.mode, display: studio.display };
  if (studio.mic) body.mic = studio.mic;
  if (studio.cam && (studio.mode === "camera" || studio.mode === "screen-camera")) body.cam = studio.cam;
  if (studio.mode === "screen" || studio.mode === "screen-camera") { body.system_audio = studio.system; body.clicks = studio.clicks; }
  if (studio.format) body.format = studio.format;
  // The page's own camera preview would hold the camera; let ffmpeg have it.
  if (studio.mode !== "screen") stopStream("camStream");
  // Show the recording at once: the recorders start in well under a second,
  // and the server's clock replaces this one when it answers.
  studio.starting = Date.now();
  studio.shown = 0;
  studio.levels = [];
  updateStudioControls();
  if (studio.mode === "audio" && !studio.micStream && studio.mic !== "none") toggleMeter();
  renderMonitor();
  const { status, data } = await api("POST", "/api/studio/record", body);
  studio.starting = 0;
  if (status !== 200) { toast(data.error || "Could not start recording"); await loadRecordStatus(); renderMonitor(); return; }
  for (const warning of data.warnings || []) toast(warning);
  studio.status = data;
  studio.statusAt = Date.now();
  updateStudioControls();
  renderMonitor();
  pollWhileBusy();
}

async function pauseRecord() {
  if (!studio.status.active || studio.saving) return;
  const { status, data } = await api("POST", studio.status.paused ? "/api/studio/resume" : "/api/studio/pause", {});
  if (status !== 200) { toast(data.error || "Could not pause"); return; }
  studio.status = data;
  studio.statusAt = Date.now();
  updateStudioControls();
}

let busyTimer = 0;
function pollWhileBusy() {
  clearTimeout(busyTimer);
  busyTimer = setTimeout(async () => {
    busyTimer = 0;
    await loadRecordStatus();
    if ((studio.status.active || studio.saving) && !busyTimer) pollWhileBusy();
    else updateStudioControls();
  }, studio.saving ? 700 : 1500);
}

async function takeShot(kind) {
  const body = { kind, display: studio.display, delay: studio.delay, clipboard: studio.clipboard };
  if (kind !== "screen") toast("Select on the Mac: drag an area or click a window (Esc cancels)");
  else if (studio.delay) toast("Screenshot in " + studio.delay + " s");
  const { status, data } = await api("POST", "/api/studio/shot", body);
  if (status !== 200) { toast(data.error || "Screenshot failed"); return; }
  if (data.clipboard) { toast("Copied to the clipboard"); return; }
  toast("Saved " + data.saved.split("/").pop());
  loadLibrary(false);
}

function renderMonitor() {
  const monitor = $("monitor");
  if (!monitor) return;
  clearTimeout(studio.previewTimer);
  for (const node of [...monitor.children]) if (node.id !== "monBadge") node.remove();
  const screenMode = studio.mode === "screen" || studio.mode === "screen-camera";
  const cameraMode = studio.mode === "camera" || studio.mode === "screen-camera";
  const recording = Boolean(studio.status.active || studio.starting);
  $("togglePreview").textContent = "Screen preview: " + (studio.preview ? "on" : "off");
  $("togglePreview").style.display = screenMode ? "" : "none";
  $("toggleCam").textContent = studio.camStream ? "Hide camera" : "Show camera";
  $("toggleCam").style.display = cameraMode && !recording ? "" : "none";
  $("toggleMic").textContent = studio.micStream ? "Hide sound" : "Show sound";
  $("monHint").textContent = recording && screenMode ? "Preview paused while recording, so the recording stays smooth." : screenMode ? "The preview refreshes every 2 s; the recording itself is smooth." : studio.mode === "audio" ? "The wave shows how loud the microphone is." : "The camera preview uses the browser; it is released when recording starts.";
  if (screenMode && studio.preview) {
    // A full-screen snapshot every 2 s would compete with the recorder, so it stops while recording.
    const image = h("img", { class: "screen", alt: "" });
    image.addEventListener("error", () => { image.remove(); monitor.prepend(h("div", { class: "note", text: "No preview: give the terminal running ul desk Screen Recording permission (System Settings > Privacy & Security)." })); });
    image.addEventListener("load", () => { if (!studio.status.active && !studio.starting) studio.previewTimer = setTimeout(refresh, 2000); });
    const refresh = () => {
      if (!image.isConnected) return;
      if (state.view === "studio" && !document.hidden && !studio.status.active && !studio.starting) image.src = media("/media/preview") + "&display=" + studio.display + "&_=" + Date.now();
      else studio.previewTimer = setTimeout(refresh, 2000);
    };
    if (recording) image.style.opacity = ".35";
    monitor.append(image);
    if (studio.lastPreview && recording) image.src = studio.lastPreview;
    else refresh();
    image.addEventListener("load", () => { if (!recording) studio.lastPreview = image.src; });
  } else if (screenMode) {
    monitor.append(h("div", { class: "note", text: "Display " + studio.display + " · preview off" }));
  }
  if (cameraMode && studio.camStream && !recording) {
    const video = h("video", { class: "cam " + (studio.mode === "camera" ? "full" : studio.info.settings.overlay), autoplay: true, muted: true, playsinline: true });
    video.muted = true;
    video.srcObject = studio.camStream;
    monitor.append(video);
  } else if (studio.mode === "camera") {
    monitor.append(h("div", { class: "note", text: recording ? "Recording the camera" : "Camera · press “Show camera” for a preview" }));
  }
  if (studio.mode === "audio") {
    monitor.append(h("div", { class: "voice" },
      h("div", { class: "voice-clock", id: "waveClock", text: clockText(recordElapsed()) }),
      h("canvas", { id: "wave", class: "wave" }),
      studio.micStream ? null : h("div", { class: "note", text: "Press “Show sound” (or start recording) to see the microphone" })));
  } else if (studio.micStream) {
    monitor.append(h("canvas", { id: "wave", class: "wave strip" }));
  }
  drawWave();
}

async function toggleCamera() {
  if (studio.camStream) { stopStream("camStream"); renderMonitor(); return; }
  if (state.view !== "studio" || studio.status.active || studio.starting) return;
  const request = studio.camRequest = (studio.camRequest || 0) + 1;
  const current = () => request === studio.camRequest && state.view === "studio" && !studio.status.active && !studio.starting;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: true });
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    if (studio.cam) {
      const found = (await navigator.mediaDevices.enumerateDevices()).find((item) => item.kind === "videoinput" && item.label === studio.cam);
      if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
      if (found) { stream.getTracks().forEach((track) => track.stop()); stream = await navigator.mediaDevices.getUserMedia({ video: { deviceId: { exact: found.deviceId } } }); }
    }
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    studio.camStream = stream;
  } catch (error) { if (stream) stream.getTracks().forEach((track) => track.stop()); toast("The browser could not open the camera: " + error.message); }
  renderMonitor();
}

async function toggleMeter() {
  if (studio.micStream) { stopStream("micStream"); renderMonitor(); return; }
  if (state.view !== "studio") return;
  const request = studio.micRequest = (studio.micRequest || 0) + 1;
  const current = () => request === studio.micRequest && state.view === "studio";
  try {
    const constraints = { audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } };
    if (studio.mic && studio.mic !== "none") {
      // Device labels are only visible after the first permission.
      await navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => stream.getTracks().forEach((track) => track.stop()));
      if (!current()) return;
      const found = (await navigator.mediaDevices.enumerateDevices()).find((item) => item.kind === "audioinput" && item.label.includes(studio.mic));
      if (!current()) return;
      if (found) constraints.audio.deviceId = { exact: found.deviceId };
    }
    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    studio.micStream = stream;
  } catch (error) { toast("The browser could not open the microphone: " + error.message); return; }
  studio.audio = new AudioContext();
  studio.analyser = studio.audio.createAnalyser();
  studio.analyser.fftSize = 2048;
  studio.audio.createMediaStreamSource(studio.micStream).connect(studio.analyser);
  const samples = new Float32Array(studio.analyser.fftSize);
  // Like Voice Memos: one bar per 50 ms, louder = taller, red while recording.
  studio.sampler = setInterval(() => {
    if (!studio.analyser) return;
    studio.analyser.getFloatTimeDomainData(samples);
    let sum = 0, peak = 0;
    for (const value of samples) { sum += value * value; peak = Math.max(peak, Math.abs(value)); }
    const rms = Math.sqrt(sum / samples.length);
    const db = 20 * Math.log10(Math.max(rms * 1.4, peak * 0.6, 1e-5));
    const level = Math.min(1, Math.max(0, (db + 55) / 55)) ** 1.3;
    const s = studio.status;
    studio.levels.push({ v: level, live: Boolean(studio.starting || (s.active && s.phase === "recording")) });
    if (studio.levels.length > 2400) studio.levels.splice(0, 600);
  }, 50);
  renderMonitor();
  const stream = studio.micStream;
  const loop = () => { if (studio.micStream !== stream) return; drawWave(); requestAnimationFrame(loop); };
  loop();
}

const ICONS = { audio: "M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zm12-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0z" };
function sizeText(bytes) { return bytes > 1e9 ? (bytes / 1e9).toFixed(1) + " GB" : bytes > 1e6 ? (bytes / 1e6).toFixed(1) + " MB" : Math.max(1, Math.round(bytes / 1e3)) + " KB"; }

function renderLibrary() {
  const box = $("library");
  if (!box) return;
  for (const button of $("libFilters").children) button.classList.toggle("on", button.dataset.filter === studio.filter);
  box.textContent = "";
  const items = studio.library.filter((item) => studio.filter === "all" || item.kind === studio.filter);
  if (!items.length) { box.append(h("div", { class: "empty", text: studio.library.length ? "Nothing of this kind yet." : "No captures yet. Take a screenshot or start a recording." })); return; }
  for (const item of items.slice(0, 120)) {
    const pic = h("div", { class: "pic" });
    if (item.kind === "audio") pic.append(svgIcon(ICONS.audio));
    else pic.append(h("img", { src: media("/media/thumb", item.name), alt: "", loading: "lazy" }));
    if (item.duration) pic.append(h("span", { class: "len", text: format(item.duration) }));
    const when = new Date(item.modified).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    box.append(h("button", { class: "item", title: item.name, onclick: () => openViewer(item) }, pic,
      h("div", { class: "cap" }, h("b", { text: item.name }), h("span", { text: when + " · " + sizeText(item.size) }))));
  }
}

function openViewer(item) {
  studio.item = item;
  studio.trim = { from: null, to: null };
  const sheet = $("viewerSheet");
  sheet.textContent = "";
  const source = media("/media/file", item.name);
  const player = item.kind === "video" ? h("video", { controls: true, src: source, preload: "metadata" }) : item.kind === "audio" ? h("audio", { controls: true, src: source, preload: "metadata" }) : h("img", { src: source, alt: item.name });
  const meta = [item.duration ? format(item.duration) : "", sizeText(item.size), new Date(item.modified).toLocaleString()].filter(Boolean).join(" · ");
  sheet.append(h("div", { class: "top" }, h("b", { text: item.name }), h("span", { class: "where", text: meta }), h("button", { class: "ghost", text: "Close", onclick: closeViewer })));
  sheet.append(h("div", { class: "media" }, player));
  if (item.kind !== "image") {
    const canvas = h("canvas", { class: "filewave", title: "Click to jump there" });
    sheet.append(canvas);
    fileWave(item, player, canvas);
  }
  const act = (action, extra) => async () => {
    const { status, data } = await api("POST", "/api/studio/action", { action, name: item.name, ...(extra || {}) });
    if (status !== 200) { toast(data.error || "Failed"); return null; }
    return data;
  };
  const tools = h("div", { class: "tools" },
    h("button", { text: item.kind === "image" ? "Open in Preview" : "Open in QuickTime", onclick: act("open") }),
    h("button", { text: "Show in Finder", onclick: act("reveal") }),
    item.kind === "image" ? h("button", { text: "Copy", onclick: async () => { if (await act("copy")()) toast("Copied to the clipboard"); } }) : null);
  if (item.kind !== "image") {
    const mark = h("span", { class: "mark", text: "trim: start – end" });
    const show = () => { mark.textContent = "trim: " + (studio.trim.from === null ? "start" : format(studio.trim.from)) + " – " + (studio.trim.to === null ? "end" : format(studio.trim.to)); };
    const convert = select((item.kind === "video" ? [["mp4", "MP4"], ["mov", "MOV"], ["gif", "GIF"], ["m4a", "Audio M4A"], ["mp3", "Audio MP3"]] : [["mp3", "MP3"], ["m4a", "M4A"], ["wav", "WAV"]]).filter(([value]) => !item.name.toLowerCase().endsWith("." + value)), "", () => {});
    tools.append(h("span", { class: "sep" }),
      h("button", { text: "Set start", title: "Trim from the player position", onclick: () => { studio.trim.from = player.currentTime; show(); } }),
      h("button", { text: "Set end", onclick: () => { studio.trim.to = player.currentTime; show(); } }),
      mark,
      h("button", { text: "Save trimmed", onclick: async () => {
        const extra = {};
        if (studio.trim.from !== null) extra.from = studio.trim.from;
        if (studio.trim.to !== null) extra.to = studio.trim.to;
        if (!Object.keys(extra).length) { toast("Set a start or an end first"); return; }
        toast("Trimming…");
        const data = await act("trim", extra)();
        if (data) { toast("Saved " + data.saved.split("/").pop()); loadLibrary(); }
      } }),
      h("span", { class: "sep" }), convert,
      h("button", { text: "Convert", onclick: async () => {
        toast("Converting…");
        const data = await act("convert", { to: convert.value })();
        if (data) { toast("Saved " + data.saved.split("/").pop()); loadLibrary(); }
      } }));
  }
  tools.append(h("span", { class: "spacer", style: "flex:1" }), h("button", { class: "ghost", text: "Move to Trash", onclick: async () => {
    if (!confirm("Move " + item.name + " to the Trash?")) return;
    if (await act("delete")()) { closeViewer(); toast("Moved to the Trash"); loadLibrary(); }
  } }));
  sheet.append(tools);
  $("viewer").classList.add("on");
}

async function fileWave(item, player, canvas) {
  const bars_ = Math.max(60, Math.min(1200, Math.floor((canvas.clientWidth || 900) / 4)));
  const { status, data } = await api("GET", "/api/studio/wave?name=" + encodeURIComponent(item.name) + "&bars=" + bars_);
  if (status !== 200 || studio.item !== item) { if (status !== 200) canvas.remove(); return; }
  const peaks = data.peaks;
  const total = () => (Number.isFinite(player.duration) && player.duration > 0 ? player.duration : data.duration) || 1;
  canvas.addEventListener("click", (event) => {
    const box = canvas.getBoundingClientRect();
    player.currentTime = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)) * total();
  });
  let drawn = "";
  const draw = () => {
    if (!canvas.isConnected) return;
    // Redraw only when something visible changed: an open, paused viewer costs nothing.
    const key = [player.currentTime, studio.trim.from, studio.trim.to, canvas.clientWidth, canvas.clientHeight, window.devicePixelRatio].join();
    if (key === drawn) { requestAnimationFrame(draw); return; }
    drawn = key;
    const [context, width, height] = fitCanvas(canvas);
    const step = width / peaks.length, at = player.currentTime / total();
    const from = studio.trim.from === null ? null : studio.trim.from / total();
    const to = studio.trim.to === null ? null : studio.trim.to / total();
    if (from !== null || to !== null) {
      context.fillStyle = "rgba(107,147,255,.16)";
      context.fillRect((from ?? 0) * width, 0, ((to ?? 1) - (from ?? 0)) * width, height);
    }
    peaks.forEach((value, index) => bars(context, index * step + 0.5, height, value, Math.max(1, step - 1.5), index / peaks.length < at ? "#ff453a" : "#8e8e93"));
    context.fillStyle = "#f2f2f7";
    context.fillRect(at * width - 1, 0, 2, height);
    requestAnimationFrame(draw);
  };
  draw();
}

function closeViewer() {
  const viewer = $("viewer");
  if (!viewer.classList.contains("on")) return;
  viewer.classList.remove("on");
  for (const node of viewer.querySelectorAll("video, audio")) node.pause();
  $("viewerSheet").textContent = "";
  studio.item = null;
}
$("viewer").addEventListener("click", (event) => { if (event.target === $("viewer")) closeViewer(); });
$("recPill").addEventListener("click", () => setView("studio"));

// ---- boards ----
async function loadBoards() {
  const { status, data } = await api("GET", "/api/boards");
  if (status !== 200) return;
  const select = $("boards");
  select.textContent = "";
  for (const path of data.recent.length ? data.recent : [data.current]) {
    select.append(h("option", { value: path, text: path.split("/").pop().replace(/\.md$/i, "") + "  —  " + path.split("/").slice(-2, -1)[0], selected: path === data.current }));
  }
  select.append(h("option", { value: "", text: "Open another board…" }));
}

async function switchBoard(path, create) {
  const { status, data } = await api("POST", "/api/boards", { path, create: Boolean(create) });
  if (status === 200) { state.tag = ""; setBoard(data); loadBoards(); toast("Opened " + data.name); return; }
  if (status === 404 && data.missing && !create && /\.md$/i.test(path) && confirm("No board at\n" + path + "\n\nCreate a new board there?")) return switchBoard(path, true);
  toast(data.error || "Could not open that board");
  loadBoards();
}

$("boards").addEventListener("change", (event) => {
  const value = event.target.value;
  if (value) { switchBoard(value); return; }
  const path = prompt("Path to a Kanban board (.md). A missing file can be created.", "~/");
  if (path && path.trim()) switchBoard(path.trim());
  else loadBoards();
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
  if (state.board && !["stats", "games", "studio"].includes(state.view)) render();
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

// ---- theme, search, keys ----
function applyTheme(theme) {
  const dark = theme ? theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}
applyTheme(localStorage.getItem("desk-theme"));
$("theme").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("desk-theme", next);
  applyTheme(next);
});

$("search").addEventListener("input", (event) => { state.query = event.target.value.trim(); render(); });

document.addEventListener("keydown", (event) => {
  if (gameKey(event)) return;
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
  if (event.key === "Escape") {
    $("help").classList.remove("on");
    closeViewer();
    if (typing) document.activeElement.blur();
    if (state.query || state.tag) { state.query = ""; state.tag = ""; $("search").value = ""; render(); }
    return;
  }
  if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.key === "?") { $("help").classList.toggle("on"); return; }
  if (event.key === "/") { event.preventDefault(); if (state.view === "games" || state.view === "stats") setView("board"); $("search").focus(); }
  else if (event.key === "n") {
    event.preventDefault();
    if (state.view === "today") document.querySelector(".quick input")?.focus();
    else { if (state.view !== "board") setView("board"); document.querySelector(".add input")?.focus(); }
  }
  else if (event.key === " ") { event.preventDefault(); togglePlay(); }
  else if (event.key >= "1" && event.key <= "5") setView(VIEWS[Number(event.key) - 1]);
  else if (state.view === "studio" && event.key === "r") toggleRecord();
  else if (state.view === "studio" && event.key === "p") pauseRecord();
});

// ---- start ----
async function start() {
  if (!TOKEN) { document.body.textContent = "Open the desk with `ul desk`: this page needs its token."; return; }
  await Promise.all([loadBoard(true), loadBoards(), loadTimer(), loadGames(), loadStudioInfo()]);
  render();
  setInterval(() => { if (!document.hidden && !state.dragging && !state.editing && !["games", "studio"].includes(state.view)) loadBoard(false); }, 2000);
  setInterval(() => { if (!document.hidden) loadTimer(); }, 10000);
  setInterval(() => { if (!document.hidden && state.view === "games" && arcade.session) loadGames(); }, 5000);
  setInterval(drawTimer, 500);
  setInterval(drawRecording, 250);
  setInterval(() => { if (!document.hidden && studio.info?.available) return loadRecordStatus(); }, 8000);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { if (state.view === "games") pauseGame(); return; }
    loadBoard(false);
    loadTimer();
  });
}
start();
</script>
</body>
</html>
"""
