"""The Studio tab of the `ul desk` page: its CSS and JS, injected into desk_ui.PAGE.

Device names, project names and texts are user data, so nodes are built with textContent, never innerHTML.
Recording, projects and export all go through `ul capture ... --json` on the server (desk.py `Studio`);
the page only edits the shared setup (storage.root/studio/setup.json) and shows what capture reports.
"""

from __future__ import annotations

STUDIO_CSS = r""".studio { display: flex; flex-direction: column; gap: 10px; padding: 12px 16px 18px; min-height: 100%; }
.sthead { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sthead .seg { display: flex; gap: 2px; background: var(--column); border: 1px solid var(--line); border-radius: 8px; padding: 2px; }
.sthead .seg button { border: none; background: transparent; padding: 3px 11px; border-radius: 6px; color: var(--muted); font-weight: 550; }
.sthead .seg button.on { background: var(--panel); color: var(--text); box-shadow: var(--shadow), 0 0 0 1px var(--line); }
.sthead .seg button:disabled { opacity: .45; }
.sthead .fmt button.on { color: var(--accent-ink); box-shadow: 0 0 0 1px var(--accent); }
.sthead .lbl { color: var(--muted); font-size: 12px; }
.recgrid { display: grid; grid-template-columns: 230px minmax(0, 1fr) 270px; gap: 12px; align-items: start; }
.pane { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 9px 10px 10px; margin-bottom: 10px; box-shadow: var(--shadow); }
.pane h5 { margin: 0 0 7px; font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 650; display: flex; align-items: center; gap: 6px; }
.pane h5 .add { margin-left: auto; border: none; background: transparent; padding: 0 2px; color: var(--accent-ink); text-transform: none; letter-spacing: 0; font-size: 12px; font-weight: 600; }
:is(.pane, .inspector, .stmenu) .prow { display: flex; align-items: center; gap: 7px; margin: 6px 0; font-size: 12.5px; }
:is(.pane, .inspector, .stmenu) .prow > .lbl { color: var(--muted); width: 74px; flex: none; font-size: 12px; }
:is(.pane, .inspector, .stmenu) .prow select, :is(.pane, .inspector, .stmenu) .prow input[type=text], :is(.pane, .inspector, .stmenu) .prow input[type=number] { flex: 1; min-width: 0; padding: 3px 7px; font-size: 12.5px; }
:is(.pane, .inspector, .stmenu) .prow input[type=range] { flex: 1; min-width: 0; }
:is(.pane, .inspector, .stmenu) .prow input[type=color] { width: 26px; height: 22px; padding: 0; border-radius: 5px; }
:is(.pane, .inspector, .stmenu) .prow .val { color: var(--muted); font: 11.5px var(--mono); min-width: 38px; text-align: right; }
:is(.pane, .inspector, .stmenu, .dock) .note { color: var(--muted); font-size: 11.5px; margin: 4px 0 0; }
.scenes { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.scn { position: relative; border-radius: 6px; border: 1px solid var(--line); background: var(--sunken); overflow: hidden; padding: 0; aspect-ratio: 16 / 10; text-align: left; }
.scn.on { box-shadow: 0 0 0 2px var(--accent); border-color: var(--accent); }
.scn .mini { position: absolute; border-radius: 2px; background: var(--muted); opacity: .45; }
.scn .mini.camera { background: var(--accent); opacity: .8; }
.scn .mini.image, .scn .mini.text { background: var(--energy); opacity: .7; }
.scn kbd { position: absolute; right: 3px; top: 3px; font-size: 10px; }
.scn span { position: absolute; left: 5px; bottom: 3px; right: 4px; font-size: 10.5px; font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.srcs .src { display: flex; align-items: center; gap: 7px; width: 100%; border: none; background: transparent; padding: 5px 6px; border-radius: 6px; text-align: left; font-size: 12.5px; }
.srcs .src:hover { background: var(--column); }
.srcs .src.on { background: var(--sunken); box-shadow: inset 2px 0 0 var(--accent); }
.srcs .src.off { color: var(--muted); }
.srcs .src .ico { width: 16px; text-align: center; color: var(--muted); }
.srcs .src .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.srcs .src .eye { border: none; background: transparent; padding: 0 3px; color: var(--muted); font-size: 12px; }
.srcs .src .eye.hidden { opacity: .4; }
.stmenu { position: absolute; z-index: 20; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--lift); padding: 4px; display: flex; flex-direction: column; gap: 2px; min-width: 150px; }
.stmenu button { border: none; background: transparent; text-align: left; padding: 5px 9px; border-radius: 5px; font-size: 12.5px; }
.stmenu button:hover { background: var(--column); }
.stmenu label { display: flex; align-items: center; gap: 6px; padding: 4px 9px; font-size: 12px; color: var(--muted); }
.centre { min-width: 0; }
.banner { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; background: color-mix(in srgb, var(--danger) 12%, var(--panel)); border: 1px solid color-mix(in srgb, var(--danger) 45%, var(--line)); color: var(--text); border-radius: var(--r); padding: 8px 10px; margin-bottom: 8px; font-size: 12.5px; }
.banner b { color: var(--danger); }
.stage { position: relative; margin: 0 auto; border-radius: 8px; overflow: hidden; background: var(--sunken); box-shadow: var(--shadow); user-select: none; touch-action: none; }
.stage .bg { position: absolute; inset: -8%; width: 116%; height: 116%; object-fit: cover; filter: blur(18px) brightness(.8); }
.stage .ph { position: absolute; overflow: hidden; cursor: grab; box-sizing: border-box; }
.stage .ph > img, .stage .ph > video { width: 100%; height: 100%; display: block; pointer-events: none; }
.stage .ph .camph { width: 100%; height: 100%; display: grid; place-items: center; background: var(--column); color: var(--muted); font-size: 12px; text-align: center; }
.stage .float { position: absolute; z-index: 5; display: flex; gap: 4px; align-items: center; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 3px 5px; box-shadow: var(--lift); }
.shapes { display: flex; gap: 3px; }
.shapes button, .corners button { width: 24px; height: 24px; padding: 0; display: grid; place-items: center; border-radius: 5px; font-size: 12px; }
.shapes button.on, .corners button.on { border-color: var(--accent); color: var(--accent-ink); }
.shapes button i { display: block; background: var(--muted); }
.shapes button.on i { background: var(--accent); }
.corners { display: flex; gap: 3px; }
.stage .badge { position: absolute; right: 8px; top: 8px; z-index: 6; background: var(--panel); color: var(--danger); font: 700 11px var(--mono); padding: 2px 7px; border-radius: 5px; display: none; box-shadow: var(--shadow); }
.stage .badge.on { display: block; }
.stage .badge.paused { color: var(--muted); }
.stage .count { position: absolute; inset: 0; z-index: 7; display: grid; place-items: center; background: color-mix(in srgb, var(--bg) 55%, transparent); font: 700 96px var(--mono); color: var(--accent-ink); }
.stage .empty { position: absolute; inset: 0; display: grid; place-items: center; color: var(--muted); font-size: 12.5px; text-align: center; padding: 20px; }
.sthint { color: var(--muted); font-size: 11.5px; text-align: center; margin: 5px 0 0; }
.recclock { font: 600 21px var(--mono); letter-spacing: .02em; }
.recclock.live { color: var(--danger); }
.recstate { color: var(--muted); font-size: 12px; }
.warns { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }
.warns div { display: flex; align-items: center; gap: 8px; border-radius: var(--r-sm); padding: 5px 9px; font-size: 12.5px; background: color-mix(in srgb, var(--warn) 14%, var(--panel)); border: 1px solid color-mix(in srgb, var(--warn) 40%, var(--line)); }
.warns div button { margin-left: auto; padding: 2px 9px; }
.meter { flex: 1; height: 7px; border-radius: 4px; background: var(--sunken); overflow: hidden; min-width: 40px; }
.meter i { display: block; height: 100%; width: 0; background: linear-gradient(90deg, var(--ok) 0 60%, var(--warn) 60% 85%, var(--danger) 85%); background-size: var(--full, 100px) 100%; transition: width .08s linear; }
.tag { font-size: 10px; color: var(--muted); border: 1px solid var(--line); border-radius: 3px; padding: 0 3px; }
.projbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.projbar .levels { grid-template-columns: repeat(3, auto); }
.projbar .levels button { padding: 3px 12px; }
.library { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.item { background: var(--panel); border-radius: 8px; box-shadow: var(--shadow); overflow: hidden; cursor: pointer; border: 1px solid var(--line); text-align: left; padding: 0; display: flex; flex-direction: column; }
.item:hover { border-color: var(--accent); box-shadow: var(--lift); }
.item .pic { aspect-ratio: 16 / 10; background: var(--sunken); display: grid; place-items: center; color: var(--muted); position: relative; }
.item .pic img { width: 100%; height: 100%; object-fit: cover; }
.item .pic .len { position: absolute; right: 6px; bottom: 6px; background: var(--panel); color: var(--text); font: 11px var(--mono); padding: 1px 6px; border-radius: 5px; }
.item .pic .state { position: absolute; left: 6px; top: 6px; background: var(--panel); color: var(--text); font-size: 10.5px; font-weight: 650; padding: 1px 6px; border-radius: 5px; }
.item .pic .state.incomplete { color: var(--danger); }
.item .pic svg { width: 34px; height: 34px; stroke: var(--muted); fill: none; stroke-width: 1.6; }
.item .cap { padding: 7px 9px 8px; font-size: 12px; }
.item .cap b { display: block; font-weight: 550; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item .cap span { color: var(--muted); }
.projpage { display: grid; grid-template-columns: minmax(0, 1fr) 290px; gap: 12px; align-items: start; }
.projpage .player { display: flex; align-items: center; gap: 8px; margin: 8px 0; }
.projpage .player input[type=range] { flex: 1; }
.projpage .scenelist { display: flex; flex-direction: column; gap: 3px; font-size: 12px; }
.projpage .scenelist div { display: flex; gap: 8px; }
.projpage .scenelist .t { font-family: var(--mono); color: var(--muted); width: 48px; }
.progress { height: 6px; border-radius: 3px; background: var(--sunken); overflow: hidden; margin: 6px 0; }
.progress i { display: block; height: 100%; width: 0; background: var(--accent); transition: width .3s; }
.rec-pill { display: none; border: none; background: color-mix(in srgb, var(--danger) 12%, transparent); color: var(--danger); font: 600 12px var(--mono); border-radius: 999px; padding: 4px 10px; }
.rec-pill.on { display: inline-flex; gap: 6px; align-items: center; }
.rec-pill.on::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--danger); animation: blink 1.2s infinite; }
.rec-pill.paused::before { animation: none; background: var(--muted); }
@keyframes blink { 50% { opacity: .25; } }
#viewer { position: fixed; inset: 0; background: rgba(10,8,4,.6); display: none; place-items: center; z-index: 12; }
#viewer.on { display: grid; }
#viewer .sheet { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; box-shadow: var(--lift); width: min(1100px, 94vw); max-height: 94vh; overflow: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
#viewer .media { background: #0c0c0b; border-radius: 12px; display: grid; place-items: center; min-height: 120px; }
#viewer .media video, #viewer .media img { max-width: 100%; max-height: 66vh; display: block; }
#viewer .media audio { width: 90%; margin: 30px 0; }
#viewer .top { display: flex; align-items: center; gap: 10px; background: none; box-shadow: none; padding: 0; }
#viewer .top b { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#viewer .tools { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
#viewer .tools .sep { width: 1px; height: 22px; background: var(--line); margin: 0 4px; }
#viewer .tools .mark { font: 12px var(--mono); color: var(--muted); }
#viewer canvas.filewave { width: 100%; height: 96px; display: block; cursor: pointer; background: #0c0c0b; border-radius: 12px; }
#viewer .export { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px 12px; }
#viewer .export label { display: grid; gap: 3px; font-size: 12px; color: var(--muted); }
#viewer .export label.check { display: flex; align-items: center; gap: 7px; color: var(--text); }
.studio.rec { height: 100%; padding: 8px 10px 10px; gap: 8px; box-sizing: border-box; }
.obs { flex: 1; min-height: 600px; display: grid; grid-template-columns: minmax(0, 1fr) 300px; grid-template-rows: minmax(300px, 1fr) 238px; gap: 8px; }
.obs .preview { grid-column: 1; grid-row: 1; display: flex; flex-direction: column; min-height: 0; min-width: 0; background: #0f0f0f; border-radius: 10px; border: 1px solid var(--line); overflow: hidden; position: relative; }
.obs .pvtop { position: absolute; left: 10px; right: 10px; top: 10px; z-index: 9; display: flex; flex-direction: column; gap: 6px; pointer-events: none; }
.obs .pvtop > * > * { pointer-events: auto; }
.obs .stagebox { flex: 1; min-height: 0; container-type: size; display: grid; place-items: center; padding: 14px; }
.stagewrap { position: relative; margin: 0 auto; }
.stagewrap > .stage { width: 100%; height: 100%; border-radius: 2px; box-shadow: 0 0 0 1px rgba(255, 255, 255, .14); }
.stageui { position: absolute; inset: 0; pointer-events: none; z-index: 6; }
.stage .ph:hover { outline: 1px solid color-mix(in srgb, var(--accent) 70%, transparent); outline-offset: -1px; }
.stage .ph.locked { cursor: default; }
.selbox { position: absolute; box-sizing: border-box; outline: 2px solid var(--accent); pointer-events: none; }
.selbox.locked { outline-style: dashed; }
.selbox .handle { position: absolute; width: 10px; height: 10px; box-sizing: border-box; background: #fff; border: 2px solid var(--accent); border-radius: 2px; pointer-events: auto; touch-action: none; }
.selbox .handle.hd-top-left { left: -6px; top: -6px; cursor: nwse-resize; }
.selbox .handle.hd-top { left: calc(50% - 5px); top: -6px; cursor: ns-resize; }
.selbox .handle.hd-top-right { right: -6px; top: -6px; cursor: nesw-resize; }
.selbox .handle.hd-right { right: -6px; top: calc(50% - 5px); cursor: ew-resize; }
.selbox .handle.hd-bottom-right { right: -6px; bottom: -6px; cursor: nwse-resize; }
.selbox .handle.hd-bottom { left: calc(50% - 5px); bottom: -6px; cursor: ns-resize; }
.selbox .handle.hd-bottom-left { left: -6px; bottom: -6px; cursor: nesw-resize; }
.selbox .handle.hd-left { left: -6px; top: calc(50% - 5px); cursor: ew-resize; }
.obs .pvbar { display: flex; align-items: center; gap: 10px; padding: 6px 10px; border-top: 1px solid #262626; background: #151515; min-height: 34px; }
.obs .pvbar .sthint { margin: 0; color: #8f8f8f; text-align: left; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pvbar .live { display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 3px 11px; font-size: 12px; background: #232323; color: #d8d8d8; border: 1px solid #343434; flex: none; }
.pvbar .live i { width: 7px; height: 7px; border-radius: 50%; background: #6b6b6b; }
.pvbar .live.on { color: #fff; border-color: #3b8a4a; }
.pvbar .live.on i { background: #3fbf5a; box-shadow: 0 0 6px #3fbf5a; }
.obs .inspector { grid-column: 2; grid-row: 1; overflow: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; min-height: 0; transition: box-shadow .3s; }
.obs .inspector.flash { box-shadow: 0 0 0 2px var(--accent); }
.inspector .ihead { display: flex; align-items: center; gap: 8px; padding: 9px 12px; border-bottom: 1px solid var(--line); position: sticky; top: 0; background: var(--panel); z-index: 1; }
.inspector .ihead b { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.inspector .hint, .dock header .hint { margin-left: auto; color: var(--muted); font-size: 10.5px; text-transform: none; letter-spacing: 0; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.inspector .pad { padding: 8px 12px; display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
.inspector .prow .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.isec { border-bottom: 1px solid var(--line); padding: 0 12px 8px; }
.isec > summary { cursor: pointer; list-style: none; padding: 8px 0 3px; font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 650; user-select: none; }
.isec > summary::-webkit-details-marker { display: none; }
.isec > summary::before { content: ""; display: inline-block; width: 5px; height: 5px; margin: 0 8px 2px 1px; border-right: 1.5px solid currentColor; border-bottom: 1.5px solid currentColor; transform: rotate(45deg); }
.isec:not([open]) > summary::before { transform: rotate(-45deg); margin-bottom: 0; }
.xywh { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 5px; margin: 6px 0; }
.xywh label { display: flex; align-items: center; gap: 3px; font-size: 11px; color: var(--muted); }
.xywh input { width: 100%; min-width: 0; padding: 3px 4px; font: 11.5px var(--mono); }
.btnrow { display: flex; gap: 4px; flex-wrap: wrap; margin: 6px 0; }
.btnrow button { padding: 3px 9px; font-size: 12px; }
.obs .docks { grid-column: 1; grid-row: 2; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr) minmax(0, 1.35fr); gap: 8px; min-height: 0; }
.dock { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; display: flex; flex-direction: column; min-height: 0; min-width: 0; overflow: hidden; }
.dock > header { display: flex; align-items: center; gap: 6px; padding: 6px 10px; font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 650; border-bottom: 1px solid var(--line); background: var(--column); }
.dock .dlist { flex: 1; overflow: auto; padding: 4px; min-height: 0; }
.dock > footer { display: flex; align-items: center; gap: 1px; padding: 3px 6px; border-top: 1px solid var(--line); background: var(--column); }
.dock > footer .spacer { flex: 1; }
.drow { display: flex; align-items: center; gap: 7px; padding: 4px 6px; border-radius: 6px; font-size: 12.5px; cursor: default; user-select: none; outline: none; }
.drow:hover { background: var(--column); }
.drow:focus-visible { box-shadow: inset 0 0 0 1px var(--accent); }
.drow.on { background: color-mix(in srgb, var(--accent) 24%, var(--panel)); }
.drow .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.drow.off .name { color: var(--muted); }
.drow kbd { font-size: 10px; }
.drow input.rename { flex: 1; min-width: 0; font-size: 12.5px; padding: 1px 5px; }
.studio svg.ico, #viewer svg.ico { width: 15px; height: 15px; flex: none; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.studio .drow > svg.ico { color: var(--muted); }
.studio .ib, .stmenu .ib { border: none; background: transparent; padding: 4px; border-radius: 5px; color: var(--text); display: inline-grid; place-items: center; line-height: 0; box-shadow: none; }
.studio .ib:hover:not(:disabled) { background: var(--sunken); }
.studio .ib:disabled { opacity: .3; }
.studio .ib.dim { color: var(--muted); opacity: .5; }
.studio .ib.danger { color: var(--danger); }
.drow .ib { padding: 2px; }
.stmenu svg.ico { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; vertical-align: -2px; margin-right: 6px; }
.stmenu hr { border: none; border-top: 1px solid var(--line); margin: 3px 2px; }
.stmenu button:disabled { opacity: .4; }
.stmenu .settingsbox { padding: 6px 8px; width: 300px; }
.stmenu .settingsbox h5 { margin: 0 0 4px; font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.mixer { flex: 1; overflow: auto; padding: 8px 10px; display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.chan .chead { display: flex; align-items: center; gap: 6px; font-size: 12.5px; }
.chan .chead b { font-weight: 600; flex: none; }
.chan .chead select { flex: 1; min-width: 0; font-size: 12px; padding: 2px 5px; }
.chan .chead .note { margin: 0; flex: 1; }
.chan .db { font: 11px var(--mono); color: var(--muted); min-width: 46px; text-align: right; flex: none; }
.chan .meter { display: block; height: 8px; margin: 6px 0 4px; background: repeating-linear-gradient(90deg, var(--sunken) 0 calc(10% - 1px), color-mix(in srgb, var(--line) 80%, transparent) calc(10% - 1px) 10%); }
.chan .meter i { transition: none; }
.chan .cctl { display: flex; align-items: center; gap: 6px; }
.chan .cctl input[type=range] { flex: 1; min-width: 0; }
.chan .cctl .val { font: 11px var(--mono); color: var(--muted); min-width: 36px; text-align: right; }
.chan.muted .meter, .chan.muted input[type=range] { opacity: .35; }
.chan .tiny { padding: 1px 7px; font-size: 11px; }
.dock.controls { grid-column: 2; grid-row: 2; }
.controls .cbody { flex: 1; padding: 9px 10px; display: flex; flex-direction: column; gap: 7px; overflow: auto; min-height: 0; }
.controls .recbtn { width: 100%; min-height: 38px; border-radius: 8px; border: 1px solid var(--line); background: var(--sunken); display: flex; align-items: center; justify-content: center; gap: 9px; font-weight: 650; font-size: 13px; color: var(--text); }
.controls .recbtn i { width: 13px; height: 13px; border-radius: 50%; background: var(--danger); flex: none; transition: border-radius .15s; }
.controls .recbtn:hover { border-color: var(--danger); }
.controls .recbtn.on { background: var(--danger); border-color: var(--danger); color: #fff; }
.controls .recbtn.on i { background: #fff; border-radius: 2px; }
.controls .crow { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.controls .crow .recclock { font-size: 18px; }
.controls .pill { display: inline-flex; gap: 5px; align-items: center; border-radius: 999px; padding: 3px 10px; font-size: 12px; }
.studio .pill svg.ico, .warns svg.ico, .markname svg.ico { width: 13px; height: 13px; }
.warns div svg.ico { color: var(--warn); flex: none; }
.corners button svg.ico { width: 14px; height: 14px; }
.stage .badge .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: currentColor; margin-right: 5px; vertical-align: 1px; }
.projbar .back { display: inline-flex; align-items: center; gap: 4px; }
.markname { display: inline-flex; align-items: center; gap: 4px; }
#projPlay { display: inline-grid; place-items: center; width: 32px; height: 28px; padding: 0; }
.controls .info { color: var(--muted); font-size: 11px; line-height: 1.45; margin-top: auto; }
@media (max-width: 1100px) {
  .obs { grid-template-columns: 1fr; grid-template-rows: minmax(320px, 58vh) auto auto auto; }
  .obs .preview, .obs .inspector, .obs .docks, .dock.controls { grid-column: 1; grid-row: auto; }
  .obs .docks { grid-template-columns: 1fr 1fr; } .obs .docks > .dock { min-height: 200px; }
  .obs .inspector { max-height: none; }
}
@media (max-width: 860px) { .projpage { grid-template-columns: 1fr; } .obs .docks { grid-template-columns: 1fr; } }
"""

STUDIO_JS = r"""// ---- studio: Record (scenes, sources, live preview) and Projects, all through `ul capture` ----
const studio = { info: null, setup: null, devices: null, modes: {}, doctor: null, status: { active: false }, statusAt: 0, shown: 0, starting: 0, saving: false,
  tab: localStorage.getItem("studio-tab") === "projects" ? "projects" : "record", selected: "camera", library: [], projects: [], filter: localStorage.getItem("studio-filter") || "projects",
  camStream: null, camVideo: null, micStream: null, audio: null, analyser: null, sampler: 0, levels: [], screenUrl: "", screenFailed: false, previewTimer: 0,
  drag: null, saveTimer: 0, counting: 0, countTimer: 0, countdownDone: null, menu: null, delay: 0, clipboard: false,
  item: null, trim: { from: null, to: null }, project: null, projectCanvas: "16:9", projectTimer: 0, player: null, projectsLoaded: false, libraryLoaded: false, exportJob: null, exportTimer: 0 };
const media = (path, name) => path + "?t=" + encodeURIComponent(TOKEN) + (name ? "&name=" + encodeURIComponent(name) : "");

// ---- studio geometry: the same numbers as capture_project.py (apply_shape, pin) and capture_export.py (placement_px) ----
const STUDIO_RATIOS = { "16:9": [16, 9], "9:16": [9, 16], "1:1": [1, 1], "4:5": [4, 5] };
const STUDIO_FORMATS = [["16:9", "16:9"], ["9:16", "9:16"], ["1:1", "1:1"], ["4:5", "4:5"], ["source", "As recorded"]];
const STUDIO_SHAPES = { circle: [1, 1, 0.5], square: [1, 1, 0], rounded: [1, 1, 0.18], wide: [16, 9, 0], tall: [9, 16, 0] };
const STUDIO_ANCHORS = ["top-left", "top-right", "bottom-left", "bottom-right"];
const SNAP = 0.02, MIN_BOX = 0.04;
const studioClone = (value) => JSON.parse(JSON.stringify(value));
// Python's round(): halves go to the even neighbour, so page and export agree on pixels.
function roundHalfEven(value) {
  const rounded = Math.round(value);
  return Math.abs(value % 1) === 0.5 && rounded % 2 !== 0 ? rounded - 1 : rounded;
}
const evenPx = (value) => Math.max(2, roundHalfEven(value / 2) * 2);

function pinPlacement(item, anchor) {
  const out = studioClone(item);
  out.anchor = anchor || null;
  if (!anchor) return out;
  const [, , width, height] = out.box;
  out.box = [anchor.endsWith("left") ? 0 : 1 - width, anchor.startsWith("top") ? 0 : 1 - height, width, height];
  return out;
}

function applyShape(item, shape, canvas) {
  const out = studioClone(item);
  if (!STUDIO_SHAPES[shape] || !STUDIO_RATIOS[canvas]) return out;
  const [shapeWidth, shapeHeight, radius] = STUDIO_SHAPES[shape];
  const [canvasWidth, canvasHeight] = STUDIO_RATIOS[canvas];
  const [x, y] = out.box;
  let width = out.box[2];
  let height = width * (canvasWidth / canvasHeight) * (shapeHeight / shapeWidth);
  if (height > 1) { width = width / height; height = 1; }
  out.box = [x, y, width, height];
  out.radius = radius;
  if (out.anchor) return pinPlacement(out, out.anchor);
  out.box = [Math.min(Math.max(x, 0), 1 - width), Math.min(Math.max(y, 0), 1 - height), width, height];
  return out;
}

// The shape preset a placement matches (box aspect in pixels and radius), or null.
function shapeOf(item, canvas) {
  if (!item || !STUDIO_RATIOS[canvas]) return null;
  const [canvasWidth, canvasHeight] = STUDIO_RATIOS[canvas];
  const aspect = (item.box[2] * canvasWidth) / (item.box[3] * canvasHeight);
  for (const [name, [w, h, radius]] of Object.entries(STUDIO_SHAPES)) {
    if (Math.abs(aspect - w / h) < 0.02 && Math.abs(item.radius - radius) < 0.005) return name;
  }
  return null;
}

function placementPx(item, width, height) {
  const [x, y, w, h] = item.box;
  return { x: roundHalfEven(x * width), y: roundHalfEven(y * height), w: evenPx(w * width), h: evenPx(h * height) };
}

// After a drag: near a corner the box is pinned there (anchor), near an edge it sits flush on it.
function snapPlacement(item, canvas) {
  const out = studioClone(item);
  let [x, y, width, height] = out.box;
  const near = (a, b) => Math.abs(a - b) <= SNAP;
  const left = near(x, 0), right = near(x + width, 1), top = near(y, 0), bottom = near(y + height, 1);
  if ((left || right) && (top || bottom)) return pinPlacement(out, (top ? "top" : "bottom") + "-" + (left ? "left" : "right"));
  if (left) x = 0; else if (right) x = 1 - width;
  if (top) y = 0; else if (bottom) y = 1 - height;
  out.box = [x, y, width, height];
  out.anchor = null;
  return out;
}

// Dragging inside a `cover` box pans what it shows: the picture follows the pointer.
function moveFocus(item, dx, dy) {
  const out = studioClone(item);
  const clamp = (value) => Math.min(1, Math.max(0, value));
  out.focus = [clamp(out.focus[0] - dx), clamp(out.focus[1] - dy)];
  return out;
}

// Resize from one corner; the opposite corner stays, and a pinned box stays pinned.
function resizePlacement(item, corner, dx, dy, keepAspect) {
  const out = studioClone(item);
  const [x, y, width, height] = out.box;
  const right = corner.endsWith("right"), bottom = corner.startsWith("bottom");
  let newWidth = Math.max(MIN_BOX, width + (right ? dx : -dx));
  let newHeight = keepAspect ? newWidth * (height / width) : Math.max(MIN_BOX, height + (bottom ? dy : -dy));
  if (newWidth > 1) { if (keepAspect) newHeight /= newWidth; newWidth = 1; }
  if (newHeight > 1) { if (keepAspect) newWidth /= newHeight; newHeight = 1; }
  out.box = [right ? x : x + width - newWidth, bottom ? y : y + height - newHeight, newWidth, newHeight];
  return out.anchor ? pinPlacement(out, out.anchor) : out;
}

// R record/stop, P pause, M mark, 1-9 scenes (by key position, so every keyboard layout works).
function studioKey(code, current) {
  if (current.typing) return null;
  if (code === "KeyR") return current.active ? "stop" : "record";
  if (code === "KeyP") return "pause";
  if (code === "KeyM") return "mark";
  const digit = /^Digit([1-9])$/.exec(code);
  if (digit) {
    const scene = (current.scenes || [])[Number(digit[1]) - 1];
    return scene ? "scene:" + scene : null;
  }
  return null;
}

// Status polling: never while the page is hidden; every second while a recording runs on the Studio tab,
// every 5 s otherwise (the REC pill also shows recordings started from the terminal).
function studioPollDelay(visible, recording, onStudio) {
  if (!visible) return null;
  return recording && onStudio ? 1000 : 5000;
}

function countdownSteps(n) { return Array.from({ length: Math.max(0, n) }, (_, index) => n - index); }

// ---- studio data ----
function cameraSource() { return studio.setup ? studio.setup.sources.find((item) => item.kind === "camera") || null : null; }
function screenSource() { return studio.setup ? studio.setup.sources.find((item) => item.kind === "screen") || null : null; }
// The layout being edited: the studio setup on the Record tab, or the open project (saved to that project).
function studioDoc() { return studio.project || studio.setup; }
function sourceById(id) { const doc = studioDoc(); return doc ? doc.sources.find((item) => item.id === id) || null : null; }
function currentCanvas() { return studio.project ? studio.projectCanvas : studio.setup ? studio.setup.canvas : "16:9"; }
function currentScene() {
  if (studio.project) return sceneAt(studio.project, studio.player ? studio.player.t : 0);
  return (studio.status.active && studio.status.scene) || (studio.setup ? studio.setup.scene : "screen-camera");
}
function currentLayout() {
  const doc = studioDoc();
  const layouts = doc && doc.layouts[currentCanvas()];
  return layouts ? layouts[currentScene()] || null : null;
}
function placementOf(id) { const layout = currentLayout(); return layout ? layout.placements[id] || null : null; }
function recordingNow() { return Boolean(studio.starting || (studio.status.active && studio.status.phase === "recording")); }
function sourceName(source) {
  if (source.kind === "screen") return "Screen";
  if (source.kind === "camera") return "Camera";
  if (source.kind === "text") return "Text “" + source.text + "”";
  return source.asset;
}
const CAMERA_MB = { max: 90, high: 45, light: 22 };
const MIC_MB = { flac: 3, wav: 6, m4a: 2 };
// screencapture has no bitrate option; ~25-70 MB per minute was measured, so the middle is shown.
function megabytesPerMinute(setup) {
  if (!setup) return 0;
  const camera = setup.sources.find((item) => item.kind === "camera");
  return 45 + (camera && camera.enabled ? CAMERA_MB[camera.quality] || 0 : 0) + (setup.audio.mic.enabled ? MIC_MB[setup.audio.mic.format] || 0 : 0);
}
function gigabytes(bytes) { return bytes === null || bytes === undefined ? "" : (bytes / 1e9).toFixed(bytes > 1e11 ? 0 : 1) + " GB"; }

async function loadStudioInfo() {
  const { status, data } = await api("GET", "/api/studio");
  if (status !== 200) return;
  studio.info = data;
  if (data.available) { loadRecordStatus(); loadSetup(); scheduleStudioPoll(); }
}

async function loadSetup() {
  const { status, data } = await api("GET", "/api/studio/setup");
  if (status !== 200) { toast(data.error || "Could not read the studio setup"); return; }
  for (const warning of data.warnings || []) toast(warning);
  delete data.warnings;
  studio.setup = data;
  startHistory(studio.project || data);
  if (!sourceById(studio.selected)) studio.selected = data.sources[0].id;
}

async function loadDevices() {
  const { status, data } = await api("GET", "/api/studio/devices");
  if (status !== 200) { toast(data.error || "Could not list devices"); return; }
  studio.devices = data;
  if (state.view === "studio") { renderSound(); renderProps(); updateRecordControls(); }
}

async function loadDoctor() {
  const { status, data } = await api("GET", "/api/studio/doctor");
  if (status !== 200) return;
  studio.doctor = data;
  renderBanner();
}

// Edits go to the shared setup file half a second after the last change.
function saveSetupSoon() {
  clearTimeout(studio.saveTimer);
  studio.saveTimer = setTimeout(flushSetup, 500);
}

async function flushSetup() {
  clearTimeout(studio.saveTimer);
  studio.saveTimer = 0;
  if (!studio.setup) return;
  const { status, data } = await api("POST", "/api/studio/setup", studio.setup);
  if (status === 200) return;
  toast(data.error || "Could not save the studio setup");
  await loadSetup();
  if (state.view === "studio") renderStudioBody();
}

function edited(...parts) {
  rememberEdit();
  if (studio.project) saveProjectSoon();
  else saveSetupSoon();
  for (const part of parts) part();
}

// ---- recording state ----
let studioPollTimer = 0;
function scheduleStudioPoll(soon) {
  clearTimeout(studioPollTimer);
  studioPollTimer = 0;
  if (!studio.info || !studio.info.available) return;
  const busy = Boolean(studio.status.active || studio.saving || studio.starting);
  const delay = studioPollDelay(!document.hidden, busy, state.view === "studio");
  if (delay === null) return;
  studioPollTimer = setTimeout(async () => {
    studioPollTimer = 0;
    if (document.hidden) return;
    await loadRecordStatus();
    scheduleStudioPoll();
  }, soon ? 300 : delay);
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
    else recordingSaved(data.saving_done);
  }
  if (!data.active) for (const item of studio.levels) item.live = false;
  drawRecording();
  if (state.view === "studio") {
    updateRecordControls();
    if (Boolean(was.active) !== Boolean(data.active) || was.scene !== data.scene) { renderScenes(); renderSources(); drawStage(); renderProps(); renderSound(); }
  }
}

function recordingSaved(done) {
  if (done.export_error) toast("Saved, but the export failed: " + done.export_error);
  else toast("Saved " + String(done.saved || done.project || "").split("/").pop());
  studio.projectsLoaded = false;
  if (state.view === "studio" && done.project && done.saved === done.project) openProject(done.project, true);
  else if (state.view === "studio" && studio.tab === "projects") loadProjects();
}

function recordElapsed() {
  const s = studio.status;
  if (studio.starting) return 0;  // the clock starts once the microphone and camera deliver
  if (!s.active) return 0;
  const value = s.elapsed + (s.phase === "recording" ? (Date.now() - studio.statusAt) / 1000 : 0);
  // Polls arrive a little late; never let the clock step backwards while recording.
  if (s.phase === "recording") studio.shown = Math.max(studio.shown, value);
  else studio.shown = value;
  return studio.shown;
}

function drawRecording() {
  const s = studio.status, pill = $("recPill");
  const active = s.active || studio.saving || Boolean(studio.starting);
  pill.className = "rec-pill" + (active ? " on" : "") + (s.paused ? " paused" : "");
  pill.textContent = studio.saving || s.phase === "saving" ? "Saving…" : active ? (s.paused ? "Paused " : "REC ") + clockText(recordElapsed()) : "";
  const clock = $("recClock");
  if (clock) {
    clock.textContent = clockText(recordElapsed());
    clock.classList.toggle("live", recordingNow());
  }
  const badge = $("stageBadge");
  if (badge) {
    badge.className = "badge" + (active && !studio.saving ? " on" : "") + (s.paused ? " paused" : "");
    badge.textContent = "";
    badge.append(h("i", { class: "dot" }), studio.starting ? "STARTING…" : (s.paused ? "PAUSED " : "REC ") + clockText(recordElapsed()));
  }
  drawMeter();
}

// Countdown before a recording: the page waits, then calls record (R again cancels).
function runCountdown(seconds) {
  return new Promise((resolve) => {
    studio.counting = seconds;
    studio.countdownDone = resolve;
    drawCountdown();
    const tick = () => {
      if (!studio.counting) return;
      studio.counting -= 1;
      drawCountdown();
      if (studio.counting <= 0) { studio.countdownDone = null; resolve(true); }
      else studio.countTimer = setTimeout(tick, 1000);
    };
    studio.countTimer = setTimeout(tick, 1000);
  });
}

function cancelCountdown() {
  clearTimeout(studio.countTimer);
  studio.counting = 0;
  const done = studio.countdownDone;
  studio.countdownDone = null;
  drawCountdown();
  if (done) done(false);
}

function drawCountdown() {
  const stage = $("stage");
  if (!stage) return;
  let node = $("countdown");
  if (!studio.counting) { if (node) node.remove(); return; }
  if (!node) { node = h("div", { class: "count", id: "countdown" }); stage.append(node); }
  node.textContent = String(studio.counting);
}

async function toggleRecord() {
  if (studio.counting) { cancelCountdown(); return; }
  if (studio.saving || studio.starting) return;
  if (studio.status.active) {
    studio.saving = true;
    for (const item of studio.levels) item.live = false;
    updateRecordControls();
    const { status, data } = await api("POST", "/api/studio/stop", {});
    if (status !== 200) { studio.saving = false; toast(data.error || "Could not stop"); }
    updateRecordControls();
    scheduleStudioPoll(true);
    return;
  }
  const seconds = studio.setup ? studio.setup.countdown : 0;
  if (seconds > 0 && !(await runCountdown(seconds))) return;
  if (studio.status.active || studio.starting || studio.saving) return;
  // The recording copies the saved setup, so a pending edit is saved first.
  if (studio.saveTimer) await flushSetup();
  const body = studio.setup ? { scene: studio.setup.scene, canvas: studio.setup.canvas } : {};
  // Show the recording at once; the server's clock replaces this one when it answers.
  studio.starting = Date.now();
  studio.shown = 0;
  studio.levels = [];
  updateRecordControls();
  const { status, data } = await api("POST", "/api/studio/record", body);
  studio.starting = 0;
  if (status !== 200) {
    toast(data.error || "Could not start recording");
    if (/permission/i.test(data.error || "")) loadDoctor();
    await loadRecordStatus();
    updateRecordControls();
    return;
  }
  for (const warning of data.warnings || []) toast(warning);
  studio.status = data;
  studio.statusAt = Date.now();
  updateRecordControls();
  drawStage();
  scheduleStudioPoll();
}

async function pauseRecord() {
  if (!studio.status.active || studio.saving) return;
  const { status, data } = await api("POST", studio.status.paused ? "/api/studio/resume" : "/api/studio/pause", {});
  if (status !== 200) { toast(data.error || "Could not pause"); return; }
  studio.status = data;
  studio.statusAt = Date.now();
  updateRecordControls();
}

async function addMark() {
  if (!studio.status.active) return;
  const { status, data } = await api("POST", "/api/studio/mark", {});
  if (status !== 200) { toast(data.error || "Could not add a mark"); return; }
  toast("Mark at " + clockText(data.mark ? data.mark.t : recordElapsed()));
}

async function forceStop() {
  if (!confirm("Kill the stuck recorder? Its track is lost; the other tracks are kept.")) return;
  studio.saving = true;
  updateRecordControls();
  const { status, data } = await api("POST", "/api/studio/stop", { force: true });
  if (status !== 200) { studio.saving = false; toast(data.error || "Could not stop"); }
  scheduleStudioPoll(true);
}

async function selectScene(id) {
  if (!studio.setup || !studio.setup.scenes.some((item) => item.id === id)) return;
  studio.setup.scene = id;
  saveSetupSoon();
  if (studio.status.active) {
    const { status, data } = await api("POST", "/api/studio/scene", { scene: id });
    if (status !== 200) toast(data.error || "Could not switch the scene");
    else { studio.status = data; studio.statusAt = Date.now(); }
  }
  renderScenes();
  renderSources();
  drawStage();
  renderProps();
}

function studioKeydown(event) {
  if (state.view !== "studio" || !studio.info || !studio.info.available) return false;
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test((document.activeElement && document.activeElement.tagName) || "");
  if (typing) return false;
  if ((event.metaKey || event.ctrlKey) && event.code === "KeyZ" && (studio.project || (studio.tab === "record" && studio.setup))) {
    event.preventDefault();
    undoEdit(event.shiftKey);
    return true;
  }
  if (studio.tab !== "record" || studio.project) return false;
  if (event.key === "Escape" && studio.menu) { closeStudioMenu(); return true; }
  if (event.metaKey || event.ctrlKey || event.altKey) return false;
  if (studio.setup && studio.selected) {
    const step = event.shiftKey ? 10 : 1;
    const arrows = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (arrows[event.key] && nudgeSelected(...arrows[event.key])) { event.preventDefault(); return true; }
    if (event.key === "Delete" || event.key === "Backspace") { event.preventDefault(); deleteSelected(); return true; }
    if (event.key === "Escape") { selectSource(null); return true; }
  }
  const action = studioKey(event.code, { active: Boolean(studio.status.active), typing, scenes: studio.setup ? studio.setup.scenes.map((item) => item.id) : [] });
  if (!action) return false;
  event.preventDefault();
  if (action === "record" || action === "stop") toggleRecord();
  else if (action === "pause") pauseRecord();
  else if (action === "mark") addMark();
  else selectScene(action.slice(6));
  return true;
}

// ---- browser camera and microphone (preview only; the recording itself is ul capture) ----
function leaveStudio() {
  clearTimeout(studio.previewTimer);
  studio.previewTimer = 0;
  cancelCountdown();
  stopStream("camStream");
  stopStream("micStream");
  stopStream("screenStream");
  closeStudioMenu();
  closeViewer();
  if (studio.projectTimer) flushProject();
  stopProjectPlayer();
  studio.project = null;
}

function stopStream(key) {
  if (key === "screenStream") {
    if (studio.screenStream) { studio.screenStream.getTracks().forEach((track) => track.stop()); studio.screenStream = null; }
    for (const video of [studio.screenVideo, studio.screenBgVideo]) if (video) video.srcObject = null;
    return;
  }
  const request = key === "camStream" ? "camRequest" : "micRequest";
  studio[request] = (studio[request] || 0) + 1;
  if (studio[key]) { studio[key].getTracks().forEach((track) => track.stop()); studio[key] = null; }
  if (key === "camStream" && studio.camVideo) studio.camVideo.srcObject = null;
  if (key === "micStream") {
    clearInterval(studio.sampler);
    studio.analyser = null;
    studio.levels = [];
    if (studio.audio) { studio.audio.close(); studio.audio = null; }
  }
}

async function toggleCamera() {
  if (studio.camStream) { stopStream("camStream"); drawStage(); return; }
  if (state.view !== "studio") return;
  const request = studio.camRequest = (studio.camRequest || 0) + 1;
  const current = () => request === studio.camRequest && state.view === "studio";
  const wanted = (cameraSource() || {}).device || "default";
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: true });
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    if (wanted !== "default") {
      // Labels are only visible after the first permission; the device is matched by its name.
      const found = (await navigator.mediaDevices.enumerateDevices()).find((item) => item.kind === "videoinput" && item.label === wanted);
      if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
      if (found) { stream.getTracks().forEach((track) => track.stop()); stream = await navigator.mediaDevices.getUserMedia({ video: { deviceId: { exact: found.deviceId } } }); }
    }
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    studio.camStream = stream;
  } catch (error) { if (stream) stream.getTracks().forEach((track) => track.stop()); toast("The browser could not open the camera: " + error.message); }
  drawStage();
}

function ensureCamera() {
  const camera = cameraSource();
  if (camera && camera.enabled && !studio.camStream && localStorage.getItem("studio-campreview") !== "off" && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) toggleCamera();
}

async function toggleMeter() {
  if (studio.micStream) { stopStream("micStream"); renderSound(); return; }
  const allowed = () => !studio.setup || studio.setup.audio.mic.enabled;
  if (state.view !== "studio" || !allowed()) return;
  const request = studio.micRequest = (studio.micRequest || 0) + 1;
  const current = () => request === studio.micRequest && state.view === "studio" && allowed();
  const wanted = studio.setup ? studio.setup.audio.mic.device : "default";
  try {
    const constraints = { audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } };
    if (wanted && wanted !== "default") {
      // Device labels are only visible after the first permission.
      await navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => stream.getTracks().forEach((track) => track.stop()));
      if (!current()) return;
      const found = (await navigator.mediaDevices.enumerateDevices()).find((item) => item.kind === "audioinput" && item.label.includes(wanted));
      if (!current()) return;
      if (found) constraints.audio.deviceId = { exact: found.deviceId };
    }
    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    if (!current()) { stream.getTracks().forEach((track) => track.stop()); return; }
    studio.micStream = stream;
  } catch (error) { toast("The browser could not open the microphone: " + error.message); return; }
  studio.audio = new AudioContext();
  studio.analyser = studio.audio.createAnalyser();
  studio.analyser.fftSize = 1024;
  studio.audio.createMediaStreamSource(studio.micStream).connect(studio.analyser);
  const samples = new Float32Array(studio.analyser.fftSize);
  studio.sampler = setInterval(() => {
    if (!studio.analyser) return;
    studio.analyser.getFloatTimeDomainData(samples);
    let peak = 0;
    for (const value of samples) peak = Math.max(peak, Math.abs(value));
    const db = 20 * Math.log10(Math.max(peak, 1e-5));
    studio.levels.push({ v: dbLevel(db), db, live: recordingNow() });
    if (studio.levels.length > 600) studio.levels.splice(0, 300);
  }, 30);
  renderSound();
  const stream = studio.micStream;
  const loop = () => { if (studio.micStream !== stream) return; drawMeter(); requestAnimationFrame(loop); };
  loop();
}

const dbLevel = (db) => Math.min(1, Math.max(0, (db + 60) / 60));
// Fast up, slow down (like a hardware meter), so the bar follows the voice without flicker.
function drawMeter() {
  const meter = $("micMeter");
  if (!meter) return;
  const s = studio.status, on = Boolean(studio.setup && studio.setup.audio.mic.enabled);
  let level = 0, db = null;
  if (on && s.active && typeof s.level_db === "number") { level = dbLevel(s.level_db); db = s.level_db; }
  else if (on && studio.micStream && studio.levels.length) { const last = studio.levels[studio.levels.length - 1]; level = last.v; db = last.db; }
  const now = Date.now(), shown = studio.meterShown || 0;
  const dt = Math.min(0.25, Math.max(0, (now - (studio.meterAt || now)) / 1000));
  studio.meterAt = now;
  studio.meterShown = level >= shown ? level : Math.max(level, shown - dt * 0.6);
  meter.firstChild.style.width = Math.round(studio.meterShown * 100) + "%";
  // The colours (green, yellow, red) sit at fixed dB, so the gradient spans the whole meter, not the bar.
  if (meter.clientWidth) meter.firstChild.style.backgroundSize = meter.clientWidth + "px 100%";
  const text = $("micDb");
  if (text) text.textContent = !on ? "off" : db === null || db === undefined ? "" : db <= -59 ? "-∞ dB" : Math.round(db) + " dB";
}

// ---- screen preview: live through the browser (getDisplayMedia) once asked for, otherwise a snapshot
// every 2 s (every 5 s while recording, so the recording stays smooth) ----
function startPreview() {
  clearTimeout(studio.previewTimer);
  const screen = screenSource();
  if (!screen || state.view !== "studio" || studio.tab !== "record" || studio.screenStream) return;
  const again = (ms) => { studio.previewTimer = setTimeout(startPreview, ms); };
  if (document.hidden) { again(1000); return; }
  const url = media("/media/preview") + "&display=" + screen.display + "&_=" + Date.now();
  const image = new Image();
  image.onload = () => {
    if (studio.screenStream) return;
    const first = !studio.screenUrl;
    studio.screenUrl = url;
    // The first snapshot (or one after a failure) replaces the placeholder, so the stage is redrawn;
    // later ones only swap the image source.
    if (first || studio.screenFailed) { studio.screenFailed = false; drawStage(); }
    else for (const node of document.querySelectorAll("img.screen")) node.src = url;
    again(studio.status.active ? 5000 : 2000);
  };
  image.onerror = () => {
    if (!studio.screenFailed) { studio.screenFailed = true; loadDoctor(); drawStage(); }
    again(5000);
  };
  image.src = url;
}

// ---- rendering ----
function renderStudio(main) {
  if (!studio.info) { main.textContent = ""; main.append(h("div", { class: "page" }, h("div", { class: "empty", text: "Loading…" }))); loadStudioInfo().then(() => state.view === "studio" && render()); return; }
  if (!studio.info.available) {
    main.textContent = "";
    main.append(h("div", { class: "page" }, h("h3", { text: "Studio" }), h("div", { class: "empty", text: "The capture command is not installed in this ul. Turn on the `capture` feature with: ul features" })));
    return;
  }
  if (main.querySelector(".studio")) return;
  main.textContent = "";
  main.append(h("div", { class: "studio", id: "studioRoot" }));
  renderStudioBody();
  if (!studio.setup) loadSetup().then(() => state.view === "studio" && renderStudioBody());
  if (!studio.devices) loadDevices();
  loadDoctor();
  loadRecordStatus();
  scheduleStudioPoll();
}

function setStudioTab(tab) {
  if (tab === studio.tab && !studio.project) return;
  studio.tab = tab;
  localStorage.setItem("studio-tab", tab);
  if (tab !== "record") { clearTimeout(studio.previewTimer); stopStream("camStream"); stopStream("micStream"); stopStream("screenStream"); closeStudioMenu(); }
  if (studio.projectTimer) flushProject();
  stopProjectPlayer();
  studio.project = null;
  renderStudioBody();
}

function renderStudioBody() {
  const root = $("studioRoot");
  if (!root) return;
  root.textContent = "";
  root.className = "studio" + (studio.tab === "record" && studio.setup ? " rec" : "");
  const tabs = h("div", { class: "seg" },
    h("button", { class: studio.tab === "record" ? "on" : "", text: "Record", onclick: () => setStudioTab("record") }),
    h("button", { class: studio.tab === "projects" ? "on" : "", text: "Projects", onclick: () => setStudioTab("projects") }),
    h("button", { text: "Edit", disabled: true, title: "Editing (timeline, cuts, subtitles) is coming soon" }));
  const head = h("div", { class: "sthead" }, tabs, h("span", { class: "spacer" }));
  if (studio.tab === "record" && studio.setup) {
    head.append(iconButton("undo", "Undo (⌘Z; ⇧⌘Z redoes)", () => undoEdit(false)),
      h("span", { class: "lbl", text: "Format" }), h("div", { class: "seg fmt" }, STUDIO_FORMATS.map(([value, label]) =>
        h("button", { class: currentCanvas() === value ? "on" : "", text: label, title: value === "source" ? "The screen as recorded, no composition" : "Layout for " + value, onclick: () => { studio.setup.canvas = value; edited(renderStudioBody); } }))));
  }
  root.append(head);
  if (studio.tab === "projects") { root.append(h("div", { id: "studioProjects" })); renderProjects(); return; }
  if (!studio.setup) { root.append(h("div", { class: "empty", text: "Loading the studio setup…" })); return; }
  root.append(h("div", { class: "obs" },
    h("div", { class: "preview" },
      h("div", { class: "pvtop" }, h("div", { id: "permBanner" }), h("div", { class: "warns", id: "warnStrip" })),
      h("div", { class: "stagebox", id: "stageBox" }, stageFrame()),
      h("div", { class: "pvbar", id: "pvBar" })),
    h("aside", { class: "inspector", id: "propsPane" }),
    h("div", { class: "docks" },
      h("section", { class: "dock", id: "scenesPane" }),
      h("section", { class: "dock", id: "sourcesPane" }),
      h("section", { class: "dock", id: "soundPane" })),
    h("section", { class: "dock controls", id: "recBar" })));
  watchStageSize();
  renderScenes();
  renderSources();
  renderBanner();
  drawStage();
  renderPreviewBar();
  renderRecBar();
  renderSound();
  renderProps();
  updateRecordControls();
  startPreview();
  ensureCamera();
  autoMeter();
}

function permissionBanner(doctor) {
  if (!doctor || doctor.screen !== false) return null;
  const app = doctor.app || "the app that runs ul";
  return h("div", { class: "banner" },
    h("b", { text: "No screen recording permission." }),
    h("span", { text: "Give " + app + " Screen Recording permission in System Settings › Privacy & Security, then quit and reopen " + app + ". Camera and microphone still record." }),
    h("button", { text: "Open System Settings", onclick: () => openSettings("screen") }),
    h("button", { class: "ghost", text: "Check again", onclick: loadDoctor }));
}

function renderBanner() {
  const box = $("permBanner");
  if (!box) return;
  box.textContent = "";
  const banner = permissionBanner(studio.doctor);
  if (banner) box.append(banner);
}

async function openSettings(kind) {
  const { status, data } = await api("POST", "/api/studio/open-settings", { kind });
  if (status !== 200) { toast(data.error || "Could not open System Settings"); return; }
  studio.doctor = data;
  renderBanner();
}

function renderScenes() {
  const box = $("scenesPane");
  if (!box || !studio.setup) return;
  box.textContent = "";
  const setup = studio.setup, current = currentScene(), recording = Boolean(studio.status.active);
  box.append(h("header", {}, h("span", { text: "Scenes" })));
  const list = h("div", { class: "dlist", role: "listbox" });
  studio.sceneRows = {};
  setup.scenes.forEach((scene, index) => {
    const name = h("span", { class: "name", text: scene.name });
    const row = h("div", { class: "drow" + (scene.id === current ? " on" : ""), role: "option", tabindex: "0", title: scene.name + " · key " + (index + 1) + " · double-click to rename · right-click for more",
      onclick: () => selectScene(scene.id), ondblclick: () => renameScene(scene.id), oncontextmenu: (event) => sceneMenu(event, scene.id) },
      studioIcon("scene"), name, h("kbd", { text: String(index + 1) }));
    studio.sceneRows[scene.id] = name;
    list.append(row);
  });
  box.append(list);
  const at = setup.scenes.findIndex((scene) => scene.id === current);
  box.append(h("footer", {},
    iconButton("plus", "Add a scene (a copy of this one)", () => addScene(current)),
    iconButton("minus", "Remove this scene", () => removeScene(current), "", recording || setup.scenes.length < 2),
    iconButton("pencil", "Rename this scene", () => renameScene(current)),
    h("span", { class: "spacer" }),
    iconButton("up", "Move up", () => moveScene(current, -1), "", at <= 0),
    iconButton("down", "Move down", () => moveScene(current, 1), "", at < 0 || at >= setup.scenes.length - 1)));
}

function addScene(from, name) {
  const setup = studio.setup;
  if (setup.scenes.length >= 9) { toast("A studio has at most 9 scenes (keys 1-9)"); return; }
  let number = setup.scenes.length + 1;
  while (setup.scenes.some((item) => item.id === "scene-" + number)) number += 1;
  const id = "scene-" + number;
  const base = from || currentScene();
  setup.scenes.splice(setup.scenes.findIndex((item) => item.id === base) + 1, 0, { id, name: (name || "Scene " + number).slice(0, 40) });
  for (const canvas of Object.keys(setup.layouts)) {
    const source = setup.layouts[canvas][base];
    if (source) setup.layouts[canvas][id] = studioClone(source);
  }
  edited();
  selectScene(id);
  renameScene(id);
}

// Rename in place: the name in the Scenes list becomes a field (Enter saves, Esc cancels).
function renameScene(id) {
  const setup = studio.setup, scene = setup.scenes.find((item) => item.id === id);
  const name = studio.sceneRows && studio.sceneRows[id];
  if (!scene || !name || !name.replaceWith) return;
  const input = h("input", { type: "text", class: "rename", value: scene.name, maxlength: "40" });
  let done = false;
  const finish = (save) => {
    if (done) return;
    done = true;
    const value = input.value.trim().slice(0, 40);
    if (save && value && value !== scene.name) { scene.name = value; edited(renderScenes, renderProps); }
    else renderScenes();
  };
  input.addEventListener("keydown", (event) => { event.stopPropagation(); if (event.key === "Enter") finish(true); else if (event.key === "Escape") finish(false); });
  input.addEventListener("blur", () => finish(true));
  input.addEventListener("click", (event) => event.stopPropagation());
  name.replaceWith(input);
  input.focus();
  input.select();
}

function renderSources() {
  const box = $("sourcesPane");
  if (!box || !studio.setup) return;
  box.textContent = "";
  box.append(h("header", {}, h("span", { text: "Sources" }), h("span", { class: "hint", text: sceneName(currentScene()) })));
  const list = h("div", { class: "dlist", role: "listbox" });
  // Like OBS: the top of the list is in front.
  for (const source of [...studio.setup.sources].reverse()) {
    const item = placementOf(source.id);
    const visible = Boolean(item && item.visible), locked = isLocked(source.id);
    const off = source.kind !== "screen" && !source.enabled;
    list.append(h("div", { class: "drow src" + (source.id === studio.selected ? " on" : "") + (off ? " off" : ""), role: "option", tabindex: "0",
      title: "Click to select · double-click for its settings · right-click for more",
      onclick: () => selectSource(source.id), ondblclick: () => focusInspector(), oncontextmenu: (event) => sourceMenu(event, source.id) },
      studioIcon(SOURCE_ICON[source.kind]), h("span", { class: "name", text: sourceName(source) + (off ? " (off)" : "") }),
      iconButton(visible ? "eye" : "eyeOff", visible ? "Hide in this scene" : "Show in this scene", (event) => { event.stopPropagation(); toggleVisible(source.id); }, visible ? "" : "dim"),
      iconButton(locked ? "lock" : "unlock", locked ? "Locked: it cannot be moved on the preview (click to unlock)" : "Lock its position", (event) => { event.stopPropagation(); toggleLock(source.id); }, locked ? "" : "dim")));
  }
  box.append(list);
  const selected = sourceById(studio.selected);
  const at = selected ? studio.setup.sources.indexOf(selected) : -1;
  box.append(h("footer", {},
    iconButton("plus", "Add a source (image or text)", (event) => openSourceMenu(event.currentTarget)),
    iconButton("minus", "Remove the selected source (Delete)", deleteSelected, "", !selected),
    iconButton("gear", "Settings of the selected source", focusInspector, "", !selected),
    h("span", { class: "spacer" }),
    iconButton("up", "Move forward", () => moveSource(studio.selected, 1), "", at < 0 || at >= studio.setup.sources.length - 1),
    iconButton("down", "Move backward", () => moveSource(studio.selected, -1), "", at <= 0)));
}

function selectSource(id) {
  studio.selected = id;
  renderSources();
  drawStage();
  renderProps();
}

function toggleVisible(id) {
  const layout = currentLayout();
  if (!layout) { toast("“As recorded” has no layout; pick a format to show or hide sources"); return; }
  if (!layout.placements[id]) layout.placements[id] = defaultPlacement(sourceById(id), currentCanvas());
  else layout.placements[id].visible = !layout.placements[id].visible;
  edited(renderSources, drawStage, renderProps);
}

function defaultPlacement(source, canvas, aspect) {
  const item = { visible: true, box: [0, 0, 1, 1], fit: "cover", focus: [0.5, 0.5], radius: 0, border: { width: 0, color: "#ffc933" }, shadow: false, mirror: false, anchor: null };
  if (source.kind === "screen") { item.fit = "contain"; return item; }
  if (source.kind === "camera") { item.mirror = true; return applyShape({ ...item, box: [0, 0, 0.24, 0.24], anchor: "bottom-left" }, "wide", canvas); }
  const [cw, ch] = STUDIO_RATIOS[canvas] || [16, 9];
  const width = 0.2, height = Math.min(1, (width * cw) / ch / (aspect || 1));
  item.fit = "contain";
  return pinPlacement({ ...item, box: [0, 0, width, height] }, "top-right");
}

function openStudioMenu(anchor, items) {
  const box = anchor.getBoundingClientRect();
  showMenu(Math.round(box.left), Math.round(box.bottom + 4), items);
}

function openSourceMenu(anchor) {
  if (studio.setup.sources.length >= 12) { toast("A studio has at most 12 sources"); return; }
  openStudioMenu(anchor, [
    h("button", { onclick: () => { closeStudioMenu(); pickImage(); } }, studioIcon("image"), "Image…"),
    h("button", { onclick: () => { closeStudioMenu(); addTextSource(); } }, studioIcon("text"), "Text"),
  ]);
}

function freeSourceId(prefix) {
  let number = 1;
  while (sourceById(prefix + "-" + number)) number += 1;
  return prefix + "-" + number;
}

async function uploadAsset(name, blob) {
  let response;
  try {
    response = await fetch("/api/studio/asset?name=" + encodeURIComponent(name), { method: "POST", headers: { "X-Desk-Token": TOKEN }, body: blob });
  } catch (error) { toast("Could not reach the desk: " + error.message); return null; }
  let data = {};
  try { data = await response.json(); } catch (error) { data = {}; }
  if (response.status !== 200) { toast(data.error || "Upload failed"); return null; }
  return data.asset;
}

function imageSize(url) {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve([image.naturalWidth || 1, image.naturalHeight || 1]);
    image.onerror = () => resolve([1, 1]);
    image.src = url;
  });
}

// A new source shows in the current scene, in every format, and is selected.
function addSourceWithPlacement(source, aspect) {
  studio.setup.sources.push(source);
  for (const [canvas, scenes] of Object.entries(studio.setup.layouts)) {
    for (const [scene, layout] of Object.entries(scenes)) {
      const item = defaultPlacement(source, canvas, aspect);
      item.visible = scene === currentScene();
      layout.placements[source.id] = item;
    }
  }
  studio.selected = source.id;
  edited(renderSources, drawStage, renderProps);
}

function pickImage() {
  const input = h("input", { type: "file", accept: "image/png,image/jpeg" });
  input.addEventListener("change", async () => {
    const file = input.files && input.files[0];
    if (!file) return;
    if (file.size > 50 * 1024 * 1024) { toast("An image can be at most 50 MB"); return; }
    const asset = await uploadAsset(file.name, file);
    if (!asset) return;
    const local = URL.createObjectURL(file);
    const [width, height] = await imageSize(local);
    URL.revokeObjectURL(local);
    addSourceWithPlacement({ id: freeSourceId("img"), kind: "image", enabled: true, asset }, width / height);
  });
  input.click();
}

const TEXT_FONTS = [["-apple-system, Helvetica, sans-serif", "System"], ["Georgia, serif", "Georgia"], ["Menlo, monospace", "Menlo"], ["'Avenir Next', sans-serif", "Avenir Next"], ["'Helvetica Neue', sans-serif", "Helvetica Neue"]];

// Text sources are pictures: the page draws the text into a PNG and uploads it (ffmpeg here has no drawtext).
async function renderTextAsset(source) {
  const scale = 2, padding = Math.round(source.size * 0.35);
  const measure = document.createElement("canvas").getContext("2d");
  const font = "600 " + source.size * scale + "px " + source.font;
  measure.font = font;
  const lines = source.text.split("\n");
  const width = Math.ceil(Math.max(...lines.map((line) => measure.measureText(line).width)) + padding * 2 * scale);
  const lineHeight = Math.round(source.size * 1.25 * scale);
  const height = lineHeight * lines.length + padding * 2 * scale;
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(2, width);
  canvas.height = Math.max(2, height);
  const context = canvas.getContext("2d");
  if (source.background) {
    context.fillStyle = source.background;
    context.beginPath();
    context.roundRect(0, 0, canvas.width, canvas.height, Math.round(padding * scale * 0.8));
    context.fill();
  }
  context.font = font;
  context.fillStyle = source.color;
  context.textBaseline = "middle";
  lines.forEach((line, index) => context.fillText(line, padding * scale, padding * scale + lineHeight * (index + 0.5)));
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) { toast("Could not draw the text"); return null; }
  const asset = await uploadAsset("text " + source.id + ".png", blob);
  return asset ? { asset, aspect: canvas.width / canvas.height } : null;
}

async function addTextSource() {
  const source = { id: freeSourceId("text"), kind: "text", enabled: true, asset: "", text: "Subscribe", font: TEXT_FONTS[0][0], size: 64, color: "#ffffff", background: "#000000" };
  const drawn = await renderTextAsset(source);
  if (!drawn) return;
  source.asset = drawn.asset;
  addSourceWithPlacement(source, drawn.aspect);
}

function removeSource(id) {
  const source = sourceById(id);
  if (!source || source.kind === "screen" || source.kind === "camera") return;
  studio.setup.sources = studio.setup.sources.filter((item) => item.id !== id);
  for (const scenes of Object.values(studio.setup.layouts)) for (const layout of Object.values(scenes)) delete layout.placements[id];
  studio.selected = null;
  edited(renderSources, drawStage, renderProps);
  toast("Removed " + sourceName(source) + " (⌘Z brings it back)");
}

function stageRatio() {
  const canvas = currentCanvas();
  if (STUDIO_RATIOS[canvas]) return STUDIO_RATIOS[canvas][0] / STUDIO_RATIOS[canvas][1];
  if (studio.project) {
    const info = ((studio.project.segments[0] || {}).info || {}).screen;
    return info && info.width && info.height ? info.width / info.height : 16 / 10;
  }
  const display = displayInfo();
  const pixels = display && /(\d+)\s*x\s*(\d+)/.exec(display.pixels || "");
  return pixels ? Number(pixels[1]) / Number(pixels[2]) : 16 / 10;
}

function displayInfo() {
  const screen = screenSource();
  return studio.devices && screen ? studio.devices.displays.find((item) => item.number === screen.display) || null : null;
}

// The preview draws every visible source with the box, fit, focus, radius, border, shadow and mirror the export uses.
function drawStage() {
  const stage = $("stage");
  if (!stage || !studio.setup) return;
  const frame = $("stageWrap") || stage, overlay = $("stageUi");
  const ratio = stageRatio();
  frame.style.aspectRatio = String(ratio);
  frame.style.width = $("stageBox") ? "min(100cqw, calc(100cqh * " + ratio.toFixed(4) + "))" : "min(100%, calc(58vh * " + ratio.toFixed(4) + "))";
  stage.textContent = "";
  if (overlay) overlay.textContent = "";
  studio.stageNodes = {};
  const canvas = currentCanvas();
  const layout = currentLayout();
  const width = frame.clientWidth || 640, height = width / ratio;
  const scale = Math.min(width, height) / 1080;
  const items = [];
  if (canvas === "source") {
    const screen = studioDoc().sources.find((source) => source.kind === "screen");
    if (screen) items.push([screen, { visible: true, box: [0, 0, 1, 1], fit: "contain", focus: [0.5, 0.5], radius: 0, border: { width: 0, color: "#000000" }, shadow: false, mirror: false, anchor: null }]);
    stage.style.background = "#000000";
  } else if (studio.project) {
    const [background, placed] = projectPlacements(studio.project, currentScene(), canvas);
    stage.style.background = background.kind === "color" ? background.color : "#000000";
    items.push(...placed);
  } else if (layout) {
    const background = layout.background;
    stage.style.background = background.kind === "color" ? background.color : "#000000";
    if (background.kind === "blur") {
      if (studio.screenStream) { const video = streamVideo("screenBgVideo", studio.screenStream); video.className = "bg"; stage.append(video); }
      else if (studio.screenUrl) stage.append(h("img", { class: "bg screen", src: studio.screenUrl, alt: "" }));
    }
    for (const source of studio.setup.sources) {
      const item = layout.placements[source.id];
      if (item && item.visible) items.push([source, item]);
    }
  }
  const editable = canvas !== "source";
  if (!items.length) stage.append(h("div", { class: "empty", text: "Nothing is shown in this scene. Turn a source on with its eye in Sources." }));
  for (const [source, item] of items) {
    const node = stageNode(source, item, width, height, scale, editable);
    studio.stageNodes[source.id] = node;
    stage.append(node);
  }
  stage.append(h("span", { class: "badge", id: "stageBadge" }));
  stage.onpointerdown = (event) => { if (event.target === stage && studio.selected !== null) selectSource(null); };
  const selected = items.find(([source]) => source.id === studio.selected);
  if (selected && editable) (overlay || stage).append(selectionBox(selected[0], selected[1]));
  const hint = $("stageHint");
  if (hint) hint.textContent = canvas === "source" ? "As recorded: the screen exactly as captured, no layout." : "Drag to move (snaps to edges and the centre) · handles resize (⇧ frees the shape) · ⌥-drag pans inside · arrows nudge · Delete removes";
  if (studio.project) { resumePlayer(); return; }
  drawCountdown();
  drawRecording();
}

function stageNode(source, item, width, height, scale, editable) {
  const px = placementPx(item, width, height);
  const node = h("div", { class: "ph" + (editable && source.id === studio.selected ? " sel" : "") + (editable && isLocked(source.id) ? " locked" : "") });
  placeNode(node, item);
  node.style.borderRadius = Math.round(item.radius * Math.min(px.w, px.h)) + "px";
  if (item.border.width) node.style.border = Math.max(1, Math.round(item.border.width * scale)) + "px solid " + item.border.color;
  if (item.shadow) node.style.boxShadow = "0 " + Math.round(8 * scale) + "px " + Math.round(28 * scale) + "px rgba(0,0,0,.55)";
  const fitStyle = (child) => {
    child.style.objectFit = item.fit;
    child.style.objectPosition = item.focus[0] * 100 + "% " + item.focus[1] * 100 + "%";
    // Videos are reused across redraws, so the transform is always set (or cleared).
    child.style.transform = item.mirror ? "scaleX(-1)" : "";
    return child;
  };
  const player = studio.project && studio.player;
  if (player && (source.kind === "screen" || source.kind === "camera")) {
    node.append(fitStyle(player[source.kind]));
  } else if (player) {
    node.append(fitStyle(h("img", { src: projectMedia(studio.project.path, "assets/" + source.asset), alt: "" })));
  } else if (source.kind === "screen") {
    if (studio.screenStream) { const video = streamVideo("screenVideo", studio.screenStream); video.className = "screen live"; node.append(fitStyle(video)); }
    else if (studio.screenUrl && !studio.screenFailed) node.append(fitStyle(h("img", { class: "screen", src: studio.screenUrl, alt: "" })));
    else node.append(h("div", { class: "camph", text: studio.screenFailed ? "No screen preview (see above)" : "Screen " + source.display }));
  } else if (source.kind === "camera") {
    if (studio.camStream) node.append(fitStyle(streamVideo("camVideo", studio.camStream)));
    else node.append(h("div", { class: "camph", text: source.enabled ? "Camera" : "Camera (off)" }));
  } else {
    node.append(fitStyle(h("img", { src: media("/media/asset", source.asset), alt: "" })));
  }
  if (!editable) return node;
  node.addEventListener("pointerdown", (event) => startStageDrag(event, source.id, event.altKey ? "focus" : "move"));
  node.addEventListener("dblclick", focusInspector);
  node.addEventListener("contextmenu", (event) => { if (studio.selected !== source.id) selectSource(source.id); sourceMenu(event, source.id); });
  return node;
}

function startStageDrag(event, id, mode) {
  if (event.button !== 0) return;
  event.preventDefault();
  closeStudioMenu();
  if (studio.selected !== id) selectSource(id);
  if (isLocked(id)) return;
  const stage = $("stage"), layout = currentLayout();
  if (!stage || !layout || !layout.placements[id]) return;
  const start = studioClone(layout.placements[id]);
  const rect = stage.getBoundingClientRect();
  const source = sourceById(id);
  let moved = false;
  const move = (e) => {
    if (!moved && Math.abs(e.clientX - event.clientX) + Math.abs(e.clientY - event.clientY) < 3) return;
    moved = true;
    const dx = (e.clientX - event.clientX) / rect.width, dy = (e.clientY - event.clientY) / rect.height;
    let next;
    if (mode === "move") next = clampBox({ ...studioClone(start), box: [start.box[0] + dx, start.box[1] + dy, start.box[2], start.box[3]], anchor: null });
    else if (mode === "focus") next = moveFocus(start, dx / start.box[2], dy / start.box[3]);
    else {
      const where = mode.slice(7);
      next = clampBox(where.includes("-") ? resizePlacement(start, where, dx, dy, (source.kind !== "screen") !== e.shiftKey) : resizeEdge(start, where, dx, dy));
    }
    layout.placements[id] = next;
    placeNode(studio.stageNodes[id], next);
    placeNode($("selBox"), next);
    const node = studio.stageNodes[id], child = node && node.querySelector && node.querySelector("img, video");
    if (child && mode === "focus") child.style.objectPosition = next.focus[0] * 100 + "% " + next.focus[1] * 100 + "%";
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    if (!moved) return;
    if (mode === "move") layout.placements[id] = snapPlacement(layout.placements[id], currentCanvas());
    if (JSON.stringify(start) !== JSON.stringify(layout.placements[id])) edited(drawStage, renderProps);
    else drawStage();
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
}

function shapeButtons(item, onpick) {
  const current = shapeOf(item, currentCanvas());
  const sizes = { circle: [12, 12, "50%"], square: [12, 12, "0"], rounded: [12, 12, "4px"], wide: [16, 9, "0"], tall: [9, 16, "0"] };
  return h("div", { class: "shapes" }, Object.keys(STUDIO_SHAPES).map((shape) => {
    const mark = h("i");
    Object.assign(mark.style, { width: sizes[shape][0] + "px", height: sizes[shape][1] + "px", borderRadius: sizes[shape][2] });
    return h("button", { class: current === shape ? "on" : "", title: shape[0].toUpperCase() + shape.slice(1), onclick: () => onpick(shape) }, mark);
  }));
}

function cornerButtons(item, onpick) {
  return h("div", { class: "corners" }, STUDIO_ANCHORS.map((anchor) =>
    h("button", { class: item.anchor === anchor ? "on" : "", title: "Pin to the " + anchor.replace("-", " ") + " corner", "aria-label": "Pin to the " + anchor.replace("-", " ") + " corner", onclick: () => onpick(anchor) }, studioIcon(anchor))));
}

function changePlacement(id, change) {
  const layout = currentLayout();
  if (!layout || !layout.placements[id]) return;
  layout.placements[id] = change(layout.placements[id]);
  edited(drawStage, renderScenes, renderProps);
}

function renderRecBar() {
  const box = $("recBar");
  if (!box) return;
  box.textContent = "";
  box.append(h("header", {}, h("span", { text: "Controls" })),
    h("div", { class: "cbody" },
      h("button", { class: "recbtn", id: "recButton", title: "Start / stop recording (R)", onclick: toggleRecord }, h("i"), h("span", { id: "recLabel", text: "Start recording" })),
      h("div", { class: "crow" }, h("span", { class: "recclock", id: "recClock", text: "00:00" }), h("span", { class: "recstate", id: "recState" })),
      h("div", { class: "crow" },
        h("button", { class: "pill", id: "recPause", title: "Pause / resume (P)", onclick: pauseRecord }, studioIcon("pause"), "Pause"),
        h("button", { class: "pill", id: "recMark", title: "Add a mark at this moment (M)", onclick: addMark }, studioIcon("flag"), "Mark")),
      h("div", { class: "crow" },
        h("button", { class: "pill", title: "Take a screenshot", onclick: (event) => openShotMenu(event.currentTarget) }, studioIcon("shot"), "Screenshot", studioIcon("chevron")),
        h("button", { class: "pill", title: "Recording files, countdown, menu-bar clock", onclick: (event) => openRecordSettings(event.currentTarget) }, studioIcon("gear"), "Settings")),
      h("div", { class: "info", id: "recInfo" })));
}

function openShotMenu(anchor) {
  const delay = h("select", {}, [["0", "No delay"], ["3", "3 s delay"], ["5", "5 s delay"], ["10", "10 s delay"]].map(([value, label]) => h("option", { value, text: label, selected: String(studio.delay) === value })));
  delay.addEventListener("change", () => { studio.delay = Number(delay.value); });
  const clip = h("input", { type: "checkbox" });
  clip.checked = studio.clipboard;
  clip.addEventListener("change", () => { studio.clipboard = clip.checked; });
  openStudioMenu(anchor, [
    ...["screen", "area", "window"].map((kind) => h("button", { text: kind[0].toUpperCase() + kind.slice(1), onclick: () => { closeStudioMenu(); takeShot(kind); } })),
    h("label", {}, delay), h("label", {}, clip, "Copy to the clipboard"),
  ]);
}

function updateRecordControls() {
  const s = studio.status;
  const button = $("recButton");
  if (!button) return;
  const active = Boolean(s.active || studio.starting);
  button.className = "recbtn" + (active ? " on" : "");
  const busy = studio.saving || s.phase === "saving";
  $("recLabel").textContent = studio.counting ? "Cancel (" + studio.counting + ")" : studio.starting ? "Starting…" : busy ? "Saving…" : s.active ? "Stop recording" : "Start recording";
  const pause = $("recPause");
  pause.disabled = !s.active || busy || Boolean(studio.starting);
  pause.textContent = "";
  pause.append(studioIcon(s.paused ? "play" : "pause"), s.paused ? "Resume" : "Pause");
  $("recMark").disabled = !s.active || Boolean(studio.starting);
  $("recState").textContent = studio.counting ? "Starting in " + studio.counting + "…" : studio.starting ? "Waking the microphone and camera…" : busy ? "Saving…" : s.phase === "interrupted" ? "A recorder stopped; press stop to save the rest" : s.phase === "unsaved" ? "Not saved; press stop to try again" : s.phase === "stuck" ? "A recorder hangs" : s.active ? (s.paused ? "Paused" : "Recording") : "Ready";
  const display = displayInfo();
  const free = s.free_bytes;
  $("recInfo").textContent = "";
  $("recInfo").append(
    h("div", { text: (display ? display.pixels.replace(/\s*x\s*/, "×") + " · " : "") + "60 fps" }),
    h("div", { text: (free ? "free " + gigabytes(free) + " · " : "") + "≈ " + megabytesPerMinute(studio.setup) + " MB/min" }));
  renderWarnings();
  drawRecording();
}

function renderWarnings() {
  const box = $("warnStrip");
  if (!box) return;
  box.textContent = "";
  const s = studio.status;
  for (const warning of s.warnings || []) box.append(h("div", {}, studioIcon("alert"), h("span", { text: warning })));
  if ((s.stuck && s.stuck.length) || s.phase === "stuck") {
    box.append(h("div", {}, studioIcon("alert"), ((s.stuck || []).join(", ") || "A recorder") + " does not stop. Stop again to retry, or kill it (its track is lost).",
      h("button", { text: "Force stop", onclick: forceStop })));
  }
}

function prow(label, ...controls) { return h("div", { class: "prow" }, h("span", { class: "lbl", text: label }), ...controls); }
function studioSelect(options, value, onchange) {
  const node = h("select", {}, options.map(([v, label]) => h("option", { value: v, text: label, selected: v === value })));
  node.addEventListener("change", () => onchange(node.value));
  return node;
}
function studioCheck(value, onchange, label) {
  const input = h("input", { type: "checkbox" });
  input.checked = Boolean(value);
  input.addEventListener("change", () => onchange(input.checked));
  return label ? h("label", { class: "check" }, input, " " + label) : input;
}
function studioRange(min, max, step, value, oninput, shown) {
  const input = h("input", { type: "range", min, max, step, value });
  const val = h("span", { class: "val", text: shown(value) });
  input.addEventListener("input", () => { val.textContent = shown(Number(input.value)); oninput(Number(input.value), false); });
  input.addEventListener("change", () => oninput(Number(input.value), true));
  return [input, val];
}

// The audio mixer: one channel per input, OBS style. The button turns the input on or off for the next
// recording (off = not recorded at all, and the page closes the microphone).
function renderSound() {
  const box = $("soundPane");
  if (!box || !studio.setup) return;
  box.textContent = "";
  const audio = studio.setup.audio, devices = studio.devices, recording = Boolean(studio.status.active || studio.starting);
  box.append(h("header", {}, h("span", { text: "Audio mixer" })));
  const body = h("div", { class: "mixer" });
  const mics = [["default", "Default microphone"], ...(devices ? devices.microphones.map((item) => [item.name, item.name + (item.virtual ? " (virtual)" : "")]) : [])];
  if (!mics.some(([value]) => value === audio.mic.device)) mics.splice(1, 0, [audio.mic.device, audio.mic.device]);
  const device = studioSelect(mics, audio.mic.device, (value) => {
    audio.mic.device = value;
    const chosen = devices && devices.microphones.find((item) => item.name === value);
    if (chosen && chosen.virtual) toast(value + " is virtual: it carries app audio, not your voice");
    if (studio.micStream) { stopStream("micStream"); toggleMeter(); }
    edited(renderSound);
  });
  device.disabled = recording;
  const micOn = audio.mic.enabled;
  const level = micOn && !studio.micStream && !recording ? h("button", { class: "ghost tiny", text: "Show level", title: "Open the microphone in this page to show its level (the recording itself uses ul capture)", onclick: toggleMeter }) : null;
  body.append(h("div", { class: "chan" + (micOn ? "" : " muted") },
    h("div", { class: "chead" }, h("b", { text: "Mic" }), device, h("span", { class: "db", id: "micDb" })),
    h("div", { class: "meter", id: "micMeter", title: "-60 dB … 0 dB" }, h("i")),
    h("div", { class: "cctl" },
      iconButton(micOn ? "mic" : "micOff", micOn ? "The microphone is on: click to turn it off" : "The microphone is off (not recorded): click to turn it on", () => toggleInput("mic"), micOn ? "" : "danger", recording),
      ...studioRange(0, 200, 5, Math.round(audio.mic.volume * 100), (value, done) => { audio.mic.volume = value / 100; if (done) edited(); }, (v) => v + "%"), level)));
  const macOn = audio.system.enabled;
  body.append(h("div", { class: "chan" + (macOn ? "" : " muted") },
    h("div", { class: "chead" }, h("b", { text: "Mac sound" }), h("span", { class: "note", text: macOn ? "what the Mac plays" : "off: not recorded" })),
    h("div", { class: "cctl" },
      iconButton(macOn ? "speaker" : "speakerOff", macOn ? "The Mac's sound is recorded: click to turn it off" : "The Mac's sound is off: click to turn it on", () => toggleInput("system"), macOn ? "" : "danger", recording),
      ...studioRange(0, 200, 5, Math.round(audio.system.volume * 100), (value, done) => { audio.system.volume = value / 100; if (done) edited(); }, (v) => v + "%"))));
  if (recording) body.append(h("p", { class: "note", text: "On/off and devices apply to the next recording; volumes apply at export." }));
  box.append(body);
  drawMeter();
}

// The inspector's sections for one placement (DaVinci style): transform, shape, border and effects.
function placementControls(source, item) {
  const id = source.id, canvas = currentCanvas();
  const visible = prow("Visible", studioCheck(item.visible, (value) => changePlacement(id, (p) => ({ ...p, visible: value })), "in this scene"));
  const transform = [visible, transformFields(id, item),
    prow("Size", ...studioRange(4, 200, 1, Math.round(item.box[2] * 100), (value, done) => {
      if (!done) return;
      changePlacement(id, (p) => {
        let width = value / 100, height = p.box[3] * (width / p.box[2]);
        if (height > 2) { width = (width * 2) / height; height = 2; }
        const next = { ...studioClone(p), box: [p.box[0], p.box[1], Math.min(width, 2), height] };
        return next.anchor ? pinPlacement(next, next.anchor) : clampBox(next);
      });
    }, (v) => v + "%")),
    h("div", { class: "btnrow" },
      h("button", { text: "Fit", title: "The whole picture inside the frame", onclick: () => changePlacement(id, (p) => ({ ...p, box: [0, 0, 1, 1], fit: "contain", anchor: null })) }),
      h("button", { text: "Fill", title: "Fill the frame (the edges are cropped)", onclick: () => changePlacement(id, (p) => ({ ...p, box: [0, 0, 1, 1], fit: "cover", anchor: null })) }),
      h("button", { text: "Centre", title: "Centre in the frame", onclick: () => changePlacement(id, (p) => ({ ...p, box: [(1 - p.box[2]) / 2, (1 - p.box[3]) / 2, p.box[2], p.box[3]], anchor: null })) }),
      h("button", { text: "Reset", title: "Back to the default place and look", onclick: () => changePlacement(id, (p) => ({ ...defaultPlacement(source, canvas), visible: p.visible })) })),
    prow("Corner", cornerButtons(item, (anchor) => changePlacement(id, (p) => pinPlacement(p, anchor))),
      item.anchor ? h("button", { class: "ghost", text: "free", title: "Unpin", onclick: () => changePlacement(id, (p) => pinPlacement(p, null)) }) : null)];
  const shape = [];
  if (source.kind !== "screen") shape.push(prow("Shape", shapeButtons(item, (value) => changePlacement(id, (p) => applyShape(p, value, canvas)))));
  shape.push(prow("Fit", studioSelect([["cover", "Fill (crop)"], ["contain", "Whole picture"]], item.fit, (value) => changePlacement(id, (p) => ({ ...p, fit: value })))));
  shape.push(prow("Radius", ...studioRange(0, 50, 1, Math.round(item.radius * 100), (value, done) => { if (done) changePlacement(id, (p) => ({ ...p, radius: value / 100 })); }, (v) => v + "%")));
  if (item.fit === "cover") shape.push(h("p", { class: "note", text: "⌥-drag on the preview moves the picture inside the frame." }));
  const color = h("input", { type: "color", value: item.border.color });
  color.addEventListener("change", () => changePlacement(id, (p) => ({ ...p, border: { ...p.border, color: color.value } })));
  const effects = [
    prow("Border", color, ...studioRange(0, 40, 1, item.border.width, (value, done) => { if (done) changePlacement(id, (p) => ({ ...p, border: { ...p.border, width: value } })); }, (v) => v + " px")),
    prow("Effects", studioCheck(item.shadow, (value) => changePlacement(id, (p) => ({ ...p, shadow: value })), "shadow"),
      studioCheck(item.mirror, (value) => changePlacement(id, (p) => ({ ...p, mirror: value })), "mirror"))];
  return [inspectorSection("Transform", transform), inspectorSection("Shape & crop", shape), inspectorSection("Border & effects", effects)];
}

function renderProps() {
  if (studio.project) { renderProjectProps(); return; }
  const box = $("propsPane");
  if (!box || !studio.setup) return;
  box.textContent = "";
  const source = sourceById(studio.selected);
  if (!source) { renderSceneInspector(box); return; }
  const devices = studio.devices;
  const recording = Boolean(studio.status.active);
  box.append(h("header", { class: "ihead" }, studioIcon(SOURCE_ICON[source.kind]), h("b", { text: sourceName(source) }), h("span", { class: "hint", text: "Inspector" })));
  const item = placementOf(source.id);
  if (currentCanvas() === "source") box.append(h("p", { class: "note pad", text: "“As recorded” has no layout; pick a format to place sources." }));
  else if (item && item.visible) box.append(...placementControls(source, item));
  else box.append(h("div", { class: "pad" }, h("p", { class: "note", text: "Hidden in this scene." }), h("button", { text: "Show in this scene", onclick: () => toggleVisible(source.id) })));
  const settings = [];
  if (source.kind === "camera") {
    settings.push(prow("Record", studioCheck(source.enabled, (value) => { source.enabled = value; if (value) ensureCamera(); else stopStream("camStream"); edited(renderSources, drawStage, renderProps, updateRecordControls); }, "the camera")));
    const cams = [["default", "Default camera"], ...(devices ? devices.cameras.map((name) => [name, name]) : [])];
    if (!cams.some(([value]) => value === source.device)) cams.push([source.device, source.device]);
    const device = studioSelect(cams, source.device, (value) => { source.device = value; source.mode = "auto"; if (studio.camStream) { stopStream("camStream"); toggleCamera(); } edited(renderProps); });
    device.disabled = recording;
    settings.push(prow("Device", device));
    const name = source.device === "default" ? (devices && devices.cameras[0]) || "" : source.device;
    const modes = [["auto", "Best (auto)"], ...(studio.modes[name] || []).map((mode) => [mode.width + "x" + mode.height + "@" + mode.max_fps, mode.width + "×" + mode.height + " · " + Math.round(Number(mode.max_fps)) + " fps"])];
    if (!modes.some(([value]) => value === source.mode)) modes.push([source.mode, source.mode]);
    const mode = studioSelect(modes, source.mode, (value) => { source.mode = value; edited(); });
    mode.disabled = recording;
    settings.push(prow("Mode", mode, iconButton("refresh", "Read the camera's modes (the camera light turns on for a moment)", () => loadCameraModes(name), "", recording || !name)));
    const quality = studioSelect([["max", "Max · 1080p · ~90 MB/min"], ["high", "High · 1080p · ~45 MB/min"], ["light", "Light · 720p · ~22 MB/min"]], source.quality, (value) => { source.quality = value; edited(updateRecordControls); });
    quality.disabled = recording;
    settings.push(prow("File", quality));
    settings.push(prow("Preview", studioCheck(localStorage.getItem("studio-campreview") !== "off", (value) => { localStorage.setItem("studio-campreview", value ? "on" : "off"); if (value) ensureCamera(); else { stopStream("camStream"); drawStage(); } }, "live camera in this page")));
  } else if (source.kind === "screen") {
    const displays = devices ? devices.displays.map((entry) => [String(entry.number), entry.number + " · " + entry.name + " " + entry.pixels.replace(/\s*x\s*/, "×")]) : [[String(source.display), String(source.display)]];
    const display = studioSelect(displays, String(source.display), (value) => { source.display = Number(value); studio.screenUrl = ""; edited(drawStage, updateRecordControls, startPreview); });
    display.disabled = recording;
    settings.push(prow("Display", display));
    const area = h("input", { type: "text", value: source.area || "", placeholder: "Whole display, or X,Y,W,H in points" });
    area.disabled = recording;
    area.addEventListener("change", () => {
      const value = area.value.replace(/\s+/g, "");
      if (value && !/^\d{1,5},\d{1,5},[1-9]\d{0,4},[1-9]\d{0,4}$/.test(value)) { toast("Area is X,Y,WIDTH,HEIGHT in points, e.g. 0,0,1280,720"); area.value = source.area || ""; return; }
      source.area = value || null;
      edited();
    });
    settings.push(prow("Area", area));
    settings.push(prow("Show", studioCheck(source.clicks, (value) => { source.clicks = value; edited(); }, "clicks")));
    settings.push(prow("Preview", h("button", { text: studio.screenStream ? "Stop live screen" : "Live screen", onclick: toggleLiveScreen })));
  } else if (source.kind === "text") {
    const text = h("input", { type: "text", value: source.text, maxlength: "500" });
    const font = studioSelect(TEXT_FONTS.some(([value]) => value === source.font) ? TEXT_FONTS : [...TEXT_FONTS, [source.font, source.font]], source.font, () => {});
    const size = h("input", { type: "number", min: "8", max: "400", value: String(source.size) });
    const color = h("input", { type: "color", value: source.color });
    const back = h("input", { type: "color", value: source.background || "#000000" });
    const backOn = studioCheck(Boolean(source.background), () => {});
    settings.push(prow("Text", text), prow("Font", font), prow("Size", size), prow("Colours", color, backOn, back));
    settings.push(prow("", h("button", { class: "primary", text: "Apply", onclick: async () => {
      const value = text.value.trim(), points = Number(size.value);
      if (!value) { toast("The text is empty"); return; }
      if (!Number.isInteger(points) || points < 8 || points > 400) { toast("Size is 8-400"); return; }
      const next = { ...source, text: value.slice(0, 500), font: font.value, size: points, color: color.value, background: backOn.checked ? back.value : null };
      const drawn = await renderTextAsset(next);
      if (!drawn) return;
      Object.assign(source, next, { asset: drawn.asset });
      edited(renderSources, drawStage, renderProps);
    } })));
  } else {
    settings.push(prow("File", h("span", { class: "name", text: source.asset })));
  }
  if (source.kind === "image" || source.kind === "text") {
    settings.push(prow("Use", studioCheck(source.enabled, (value) => { source.enabled = value; edited(renderSources, drawStage); }, "in recordings"), h("button", { class: "ghost", text: "Remove", onclick: () => removeSource(source.id) })));
  }
  box.append(inspectorSection(source.kind === "camera" ? "Camera" : source.kind === "screen" ? "Screen" : source.kind === "text" ? "Text" : "Image", settings));
}

// ---- Record tab, OBS style: icons, menus, docks, inspector, live screen, undo ----
// Icons are SVG strokes (24x24) drawn with currentColor, never emoji (they render in colour and differ per Mac).
const STUDIO_ICON = {
  eye: "M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  eyeOff: "M3 3l18 18M10.6 5.1A10.8 10.8 0 0 1 12 5c7 0 11 7 11 7a18 18 0 0 1-3.2 4M6.6 6.6C3.4 8.7 1 12 1 12s4 7 11 7a10.6 10.6 0 0 0 5.4-1.5M9.9 9.9a3 3 0 0 0 4.2 4.2",
  lock: "M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4",
  unlock: "M5 11h14v10H5zM8 11V7a4 4 0 0 1 7.8-1.2",
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  up: "M12 19V5M5 12l7-7 7 7",
  down: "M12 5v14M19 12l-7 7-7-7",
  gear: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  pencil: "M17 3l4 4L8 20H4v-4z",
  screen: "M3 4h18v12H3zM8 20h8M12 16v4",
  camera: "M3 7h12v10H3zM15 10l6-3v10l-6-3",
  image: "M3 4h18v16H3zM8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM21 15l-5-5L5 20",
  text: "M4 7V4h16v3M9 20h6M12 4v16",
  mic: "M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3zM19 10v2a7 7 0 0 1-14 0v-2M12 19v3",
  micOff: "M3 3l18 18M9 9v3a3 3 0 0 0 5.1 2.1M15 9.3V5a3 3 0 0 0-5.9-.6M17 16.9A7 7 0 0 1 5 12v-2M19 10v2c0 .8-.1 1.5-.4 2.2M12 19v3",
  speaker: "M11 5L6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14",
  speakerOff: "M11 5L6 9H2v6h4l5 4zM23 9l-6 6M17 9l6 6",
  scene: "M12 2l10 5-10 5L2 7zM2 17l10 5 10-5M2 12l10 5 10-5",
  undo: "M9 14L4 9l5-5M4 9h11a5 5 0 0 1 0 10h-3",
  play: "M7 4l13 8-13 8z",
  pause: "M8 5v14M16 5v14",
  flag: "M5 21V4h12l-2 4 2 4H5",
  alert: "M12 3l10 18H2zM12 10v5M12 18h.01",
  refresh: "M21 12a9 9 0 1 1-2.6-6.4M21 4v5h-5",
  chevron: "M6 9l6 6 6-6",
  back: "M15 18l-6-6 6-6",
  shot: "M4 8h3l2-3h6l2 3h3v11H4zM12 16a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  "top-left": "M4 4h16v16H4zM8 8h4M8 8v4",
  "top-right": "M4 4h16v16H4zM16 8h-4M16 8v4",
  "bottom-left": "M4 4h16v16H4zM8 16h4M8 16v-4",
  "bottom-right": "M4 4h16v16H4zM16 16h-4M16 16v-4",
};
const SOURCE_ICON = { screen: "screen", camera: "camera", image: "image", text: "text" };
const CANVAS_PIXELS = { "16:9": [1920, 1080], "9:16": [1080, 1920], "1:1": [1080, 1080], "4:5": [1080, 1350] };
const STAGE_HANDLES = ["top-left", "top", "top-right", "right", "bottom-right", "bottom", "bottom-left", "left"];

function studioIcon(name) {
  const svg = svgIcon(STUDIO_ICON[name] || "");
  svg.setAttribute("class", "ico");
  svg.setAttribute("aria-hidden", "true");
  return svg;
}

function iconButton(name, title, onclick, extra, disabled) {
  return h("button", { class: "ib" + (extra ? " " + extra : ""), title, "aria-label": title, disabled: disabled || null, onclick }, studioIcon(name));
}

// ---- menus: one at a time, closed by Esc, a click outside or a choice ----
function closeStudioMenu() {
  if (studio.menu) { studio.menu.remove(); studio.menu = null; }
}

function showMenu(left, top, items) {
  closeStudioMenu();
  const menu = h("div", { class: "stmenu" }, items);
  Object.assign(menu.style, { position: "fixed", left: left + "px", top: top + "px" });
  document.body.append(menu);
  studio.menu = menu;
  if (menu.getBoundingClientRect && typeof window.innerWidth === "number") {
    const box = menu.getBoundingClientRect();
    if (box.right > window.innerWidth - 6) menu.style.left = Math.max(6, window.innerWidth - box.width - 6) + "px";
    if (box.bottom > window.innerHeight - 6) menu.style.top = Math.max(6, window.innerHeight - box.height - 6) + "px";
  }
  setTimeout(() => {
    const away = (event) => {
      if (studio.menu !== menu) { document.removeEventListener("pointerdown", away); return; }
      if (!menu.contains(event.target)) { closeStudioMenu(); document.removeEventListener("pointerdown", away); }
    };
    document.addEventListener("pointerdown", away);
  }, 0);
  return menu;
}

// items: [label, action, disabled] or "-" for a separator.
function contextMenu(event, items) {
  event.preventDefault();
  event.stopPropagation();
  showMenu(event.clientX, event.clientY, items.filter(Boolean).map((item) => item === "-" ? h("hr") :
    h("button", { text: item[0], disabled: item[2] || null, onclick: () => { closeStudioMenu(); item[1](); } })));
}

// ---- scenes ----
function moveScene(id, step) {
  const scenes = studio.setup.scenes, at = scenes.findIndex((item) => item.id === id), to = at + step;
  if (at < 0 || to < 0 || to >= scenes.length) return;
  scenes.splice(to, 0, scenes.splice(at, 1)[0]);
  edited(renderScenes);
}

function removeScene(id) {
  const setup = studio.setup, scene = setup.scenes.find((item) => item.id === id);
  if (!scene) return;
  if (studio.status.active) { toast("Scenes cannot be removed while recording"); return; }
  if (setup.scenes.length < 2) { toast("The last scene stays"); return; }
  setup.scenes = setup.scenes.filter((item) => item.id !== id);
  for (const layouts of Object.values(setup.layouts)) delete layouts[id];
  if (setup.scene === id) setup.scene = setup.scenes[0].id;
  edited(renderScenes, renderSources, drawStage, renderProps);
  toast("Removed the scene “" + scene.name + "” (⌘Z brings it back)");
}

function sceneMenu(event, id) {
  const setup = studio.setup, at = setup.scenes.findIndex((item) => item.id === id), scene = setup.scenes[at];
  if (!scene) return;
  contextMenu(event, [
    ["Switch to this scene", () => selectScene(id), id === currentScene()],
    ["Rename", () => { if (id !== currentScene()) selectScene(id); setTimeout(() => renameScene(id), 0); }],
    ["Duplicate", () => addScene(id, scene.name + " copy"), setup.scenes.length >= 9],
    "-",
    ["Move up", () => moveScene(id, -1), at === 0],
    ["Move down", () => moveScene(id, 1), at === setup.scenes.length - 1],
    "-",
    ["Remove", () => removeScene(id), setup.scenes.length < 2 || Boolean(studio.status.active)],
  ]);
}

// ---- sources ----
function lockedIds() {
  try { return new Set(JSON.parse(localStorage.getItem("studio-locked") || "[]")); } catch (error) { return new Set(); }
}
function isLocked(id) { return lockedIds().has(id); }
function toggleLock(id) {
  const ids = lockedIds();
  if (ids.has(id)) ids.delete(id); else ids.add(id);
  localStorage.setItem("studio-locked", JSON.stringify([...ids]));
  renderSources();
  drawStage();
}

// The sources list is the z order (later = in front), in every scene, like the export.
function moveSource(id, step, to) {
  const sources = studio.setup.sources, at = sources.findIndex((item) => item.id === id);
  const target = to === undefined ? at + step : to;
  if (at < 0 || target < 0 || target >= sources.length || target === at) return;
  sources.splice(target, 0, sources.splice(at, 1)[0]);
  edited(renderSources, drawStage);
}

function deleteSelected() {
  const source = sourceById(studio.selected);
  if (!source) return;
  if (source.kind === "image" || source.kind === "text") { removeSource(source.id); return; }
  const item = placementOf(source.id);
  if (item && item.visible) { toggleVisible(source.id); toast(sourceName(source) + " is hidden in this scene (the screen and the camera stay in the list)"); }
}

function sourceMenu(event, id) {
  const source = sourceById(id);
  if (!source) return;
  const item = placementOf(id), last = studio.setup.sources.length - 1, at = studio.setup.sources.indexOf(source);
  const place = (change) => () => changePlacement(id, change);
  const removable = source.kind === "image" || source.kind === "text";
  contextMenu(event, [
    [item && item.visible ? "Hide in this scene" : "Show in this scene", () => toggleVisible(id), currentCanvas() === "source"],
    [isLocked(id) ? "Unlock" : "Lock position", () => toggleLock(id)],
    "-",
    ["Bring to front", () => moveSource(id, 0, last), at === last],
    ["Move forward", () => moveSource(id, 1), at === last],
    ["Move backward", () => moveSource(id, -1), at === 0],
    ["Send to back", () => moveSource(id, 0, 0), at === 0],
    "-",
    ["Fit to the frame", place((p) => ({ ...p, box: [0, 0, 1, 1], fit: "contain", anchor: null })), !item],
    ["Fill the frame", place((p) => ({ ...p, box: [0, 0, 1, 1], fit: "cover", anchor: null })), !item],
    ["Centre", place((p) => ({ ...p, box: [(1 - p.box[2]) / 2, (1 - p.box[3]) / 2, p.box[2], p.box[3]], anchor: null })), !item],
    ["Reset transform", place((p) => ({ ...defaultPlacement(source, currentCanvas()), visible: p.visible })), !item],
    "-",
    source.kind === "camera" ? [source.enabled ? "Turn the camera off" : "Turn the camera on", () => { source.enabled = !source.enabled; if (source.enabled) ensureCamera(); else stopStream("camStream"); edited(renderSources, drawStage, renderProps, updateRecordControls); }, Boolean(studio.status.active)] : null,
    removable ? ["Remove", () => removeSource(id)] : null,
  ]);
}

function focusInspector() {
  const box = $("propsPane");
  if (!box) return;
  if (box.scrollTo) box.scrollTo({ top: 0, behavior: "smooth" });
  box.className = "inspector flash";
  setTimeout(() => { if (box.className === "inspector flash") box.className = "inspector"; }, 600);
}

// ---- stage geometry ----
function stageFrame() {
  return h("div", { class: "stagewrap", id: "stageWrap" }, h("div", { class: "stage", id: "stage" }), h("div", { class: "stageui", id: "stageUi" }));
}

// The preview keeps its pixel numbers (border widths) right when the window changes size.
function watchStageSize() {
  const box = $("stageBox");
  if (!box || typeof ResizeObserver === "undefined") return;
  if (studio.stageObserver) studio.stageObserver.disconnect();
  let last = 0, timer = 0;
  studio.stageObserver = new ResizeObserver(() => {
    const width = box.clientWidth;
    if (Math.abs(width - last) < 2) return;
    last = width;
    clearTimeout(timer);
    timer = setTimeout(() => { if ($("stageBox") === box) drawStage(); }, 80);
  });
  studio.stageObserver.observe(box);
}

function placeNode(node, item) {
  if (!node) return;
  Object.assign(node.style, { left: item.box[0] * 100 + "%", top: item.box[1] * 100 + "%", width: item.box[2] * 100 + "%", height: item.box[3] * 100 + "%" });
}

function selectionBox(source, item) {
  const locked = isLocked(source.id);
  const box = h("div", { class: "selbox" + (locked ? " locked" : ""), id: "selBox", title: locked ? "Locked (unlock it in Sources)" : "" });
  placeNode(box, item);
  if (!locked) {
    for (const where of STAGE_HANDLES) {
      const handle = h("i", { class: "handle hd-" + where });
      handle.addEventListener("pointerdown", (event) => { event.stopPropagation(); startStageDrag(event, source.id, "resize:" + where); });
      box.append(handle);
    }
  }
  return box;
}

// Keep a box inside what the setup file allows ([-1, 1] corners, sizes up to 2) and partly on the canvas.
function clampBox(item) {
  const out = studioClone(item);
  let [x, y, width, height] = out.box;
  width = Math.min(2, Math.max(MIN_BOX, width));
  height = Math.min(2, Math.max(MIN_BOX, height));
  x = Math.min(Math.min(1, 1 - 0.02), Math.max(Math.max(-1, 0.02 - width), x));
  y = Math.min(Math.min(1, 1 - 0.02), Math.max(Math.max(-1, 0.02 - height), y));
  out.box = [x, y, width, height];
  return out;
}

// Resize from an edge handle: only that side moves; a pinned corner is let go.
function resizeEdge(item, edge, dx, dy) {
  const out = studioClone(item);
  let [x, y, width, height] = out.box;
  if (edge === "right") width = Math.max(MIN_BOX, width + dx);
  else if (edge === "left") { const next = Math.max(MIN_BOX, width - dx); x += width - next; width = next; }
  else if (edge === "bottom") height = Math.max(MIN_BOX, height + dy);
  else if (edge === "top") { const next = Math.max(MIN_BOX, height - dy); y += height - next; height = next; }
  out.box = [x, y, width, height];
  out.anchor = null;
  return out;
}

function nudgeSelected(dx, dy) {
  const layout = currentLayout(), id = studio.selected;
  if (!layout || !layout.placements[id] || !layout.placements[id].visible || isLocked(id) || currentCanvas() === "source") return false;
  const [width, height] = CANVAS_PIXELS[currentCanvas()];
  const item = layout.placements[id];
  layout.placements[id] = clampBox({ ...studioClone(item), box: [item.box[0] + dx / width, item.box[1] + dy / height, item.box[2], item.box[3]], anchor: null });
  edited(drawStage, renderProps);
  return true;
}

// ---- inspector ----
function inspectorSection(title, nodes) {
  const open = localStorage.getItem("studio-closed-" + title) !== "1";
  const section = h("details", { class: "isec", open: open || null }, h("summary", { text: title }), ...nodes.filter(Boolean));
  section.addEventListener("toggle", () => localStorage.setItem("studio-closed-" + title, section.open ? "0" : "1"));
  return section;
}

// X, Y, W, H in pixels of a 1080p canvas, typed like in DaVinci's inspector.
function transformFields(id, item) {
  const [width, height] = CANVAS_PIXELS[currentCanvas()] || [1920, 1080];
  const field = (label, value, apply) => {
    const input = h("input", { type: "number", step: "1", value: String(Math.round(value)), title: label + " in pixels of a " + width + "×" + height + " frame" });
    input.addEventListener("change", () => {
      const number = Number(input.value);
      if (!Number.isFinite(number)) return;
      changePlacement(id, (p) => clampBox(apply(studioClone(p), number)));
    });
    input.addEventListener("keydown", (event) => { if (event.key === "Enter" && input.blur) input.blur(); });
    return h("label", {}, h("span", { text: label }), input);
  };
  const sized = (p, box) => { const next = { ...p, box }; return next.anchor ? pinPlacement(next, next.anchor) : next; };
  return h("div", { class: "xywh" },
    field("X", item.box[0] * width, (p, v) => ({ ...p, box: [v / width, p.box[1], p.box[2], p.box[3]], anchor: null })),
    field("Y", item.box[1] * height, (p, v) => ({ ...p, box: [p.box[0], v / height, p.box[2], p.box[3]], anchor: null })),
    field("W", item.box[2] * width, (p, v) => sized(p, [p.box[0], p.box[1], Math.max(MIN_BOX, v / width), p.box[3]])),
    field("H", item.box[3] * height, (p, v) => sized(p, [p.box[0], p.box[1], p.box[2], Math.max(MIN_BOX, v / height)])));
}

// Nothing selected: the scene itself (name, background) and how to start.
function renderSceneInspector(box) {
  const scene = studio.setup.scenes.find((item) => item.id === currentScene());
  box.append(h("header", { class: "ihead" }, studioIcon("scene"), h("b", { text: scene ? scene.name : "Scene" }), h("span", { class: "hint", text: "Inspector" })));
  const layout = currentLayout();
  const nodes = [];
  if (scene) {
    const name = h("input", { type: "text", value: scene.name, maxlength: "40" });
    name.addEventListener("change", () => { const value = name.value.trim().slice(0, 40); if (value) { scene.name = value; edited(renderScenes, renderProps); } else name.value = scene.name; });
    nodes.push(prow("Name", name));
  }
  if (layout) {
    const background = layout.background;
    const kind = studioSelect([["color", "Colour"], ["blur", "Blurred screen"]], background.kind, (value) => {
      layout.background = value === "blur" ? { kind: "blur" } : { kind: "color", color: background.color || "#000000" };
      edited(drawStage, renderProps);
    });
    const color = background.kind === "color" ? h("input", { type: "color", value: background.color }) : null;
    if (color) color.addEventListener("change", () => { layout.background = { kind: "color", color: color.value }; edited(drawStage); });
    nodes.push(prow("Background", kind, color));
    nodes.push(h("p", { class: "note", text: "The background fills what the sources leave free in " + currentCanvas() + "." }));
  } else nodes.push(h("p", { class: "note", text: "“As recorded” is the screen as captured: nothing to lay out." }));
  box.append(inspectorSection("Scene", nodes));
  box.append(inspectorSection("Tips", [h("p", { class: "note", text: "Click a source on the preview or in Sources to edit it. Right-click for its menu. 1-9 switch scenes, R records, P pauses, M marks, ⌘Z undoes." })]));
}

function openRecordSettings(anchor) {
  const box = h("div", { class: "settingsbox", id: "outputPane" });
  openStudioMenu(anchor, [box]);
  renderOutput(box);
}

// ---- audio inputs ----
function toggleInput(kind) {
  if (studio.status.active || studio.starting) { toast("This applies to the next recording; the running one keeps its inputs"); return; }
  const input = studio.setup.audio[kind];
  input.enabled = !input.enabled;
  if (kind === "mic" && !input.enabled) stopStream("micStream");
  edited(renderSound, updateRecordControls);
  if (kind === "mic" && input.enabled) autoMeter();
}

// The level meter starts by itself once the browser may use the microphone; before that it waits for a click.
async function autoMeter() {
  if (studio.micStream || !studio.setup || !studio.setup.audio.mic.enabled || !navigator.permissions || !navigator.mediaDevices) return;
  try {
    const answer = await navigator.permissions.query({ name: "microphone" });
    if (answer.state === "granted" && state.view === "studio" && studio.tab === "record" && !studio.micStream && studio.setup.audio.mic.enabled) toggleMeter();
  } catch (error) { /* this browser cannot say; the "Show level" button stays */ }
}

// ---- live screen ----
function streamVideo(key, stream) {
  if (!studio[key]) { studio[key] = h("video", { autoplay: true, playsinline: true }); studio[key].muted = true; }
  const video = studio[key];
  if (video.srcObject !== stream) video.srcObject = stream;
  const playing = video.play && video.play();
  if (playing && playing.catch) playing.catch(() => {});
  return video;
}

function renderPreviewBar() {
  const box = $("pvBar");
  if (!box) return;
  box.textContent = "";
  const live = Boolean(studio.screenStream);
  box.append(h("button", { class: "live" + (live ? " on" : ""), id: "liveBtn", onclick: toggleLiveScreen,
    title: live ? "Back to snapshots every 2 s" : "Show the screen live, 30 fps (the browser asks which screen; only this preview uses it, the recording does not)" },
    h("i"), live ? "Live" : "Live screen"), h("span", { class: "sthint", id: "stageHint" }));
}

async function toggleLiveScreen() {
  if (studio.screenStream) { stopStream("screenStream"); renderPreviewBar(); drawStage(); startPreview(); renderProps(); return; }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) { toast("This browser cannot show the screen live; snapshots are used"); return; }
  let stream;
  try {
    stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: { ideal: 30, max: 60 }, displaySurface: "monitor" }, audio: false });
  } catch (error) {
    if (error && error.name !== "NotAllowedError" && error.name !== "AbortError") toast("The browser could not share the screen: " + error.message);
    return;
  }
  if (state.view !== "studio" || studio.tab !== "record") { stream.getTracks().forEach((track) => track.stop()); return; }
  stopStream("screenStream");
  studio.screenStream = stream;
  clearTimeout(studio.previewTimer);
  const track = stream.getVideoTracks()[0];
  if (track) track.onended = () => { if (studio.screenStream !== stream) return; studio.screenStream = null; renderPreviewBar(); drawStage(); startPreview(); };
  renderPreviewBar();
  drawStage();
  renderProps();
}

// ---- undo: snapshots of the setup (or the open project) before each edit ----
function rememberEdit() {
  const doc = studioDoc();
  if (!doc) return;
  const now = JSON.stringify(doc);
  if (studio.historyDoc !== doc) { studio.historyDoc = doc; studio.undo = []; studio.redo = []; studio.historyLast = now; return; }
  if (studio.historyLast && studio.historyLast !== now) {
    studio.undo.push(studio.historyLast);
    if (studio.undo.length > 100) studio.undo.shift();
    studio.redo = [];
  }
  studio.historyLast = now;
}

// Called whenever a setup or project is loaded, so the first edit can be undone.
function startHistory(doc) {
  studio.historyDoc = doc;
  studio.undo = [];
  studio.redo = [];
  studio.historyLast = doc ? JSON.stringify(doc) : "";
}

function undoEdit(redo) {
  const doc = studioDoc();
  if (!doc || studio.historyDoc !== doc) { toast(redo ? "Nothing to redo" : "Nothing to undo"); return; }
  const from = redo ? studio.redo : studio.undo, to = redo ? studio.undo : studio.redo;
  if (!from.length) { toast(redo ? "Nothing to redo" : "Nothing to undo"); return; }
  to.push(JSON.stringify(doc));
  const previous = JSON.parse(from.pop());
  for (const key of Object.keys(doc)) delete doc[key];
  Object.assign(doc, previous);
  studio.historyLast = JSON.stringify(doc);
  if (studio.selected && !sourceById(studio.selected)) studio.selected = null;
  if (studio.project) { saveProjectSoon(); drawStage(); renderProps(); return; }
  saveSetupSoon();
  renderStudioBody();
}

async function loadCameraModes(name) {
  toast("Reading the modes of " + name + "…");
  const { status, data } = await api("GET", "/api/studio/camera-modes?device=" + encodeURIComponent(name));
  if (status !== 200) { toast(data.error || "Could not read the camera modes"); return; }
  Object.assign(studio.modes, data.modes || {});
  renderProps();
}

function renderOutput(target) {
  const box = target || $("outputPane");
  if (!box || !studio.setup) return;
  box.textContent = "";
  const camera = cameraSource(), mic = studio.setup.audio.mic;
  box.append(h("h5", { text: "Recording" }));
  if (camera) box.append(prow("Camera", studioSelect([["max", "Max · 1080p · ~90 MB/min"], ["high", "High · 1080p · ~45 MB/min"], ["light", "Light · 720p · ~22 MB/min"]], camera.quality, (value) => { camera.quality = value; edited(renderOutput, updateRecordControls); })));
  box.append(prow("Microphone", studioSelect([["flac", "FLAC lossless · ~3 MB/min"], ["wav", "WAV lossless · ~6 MB/min"], ["m4a", "M4A (AAC) · ~2 MB/min"]], mic.format, (value) => { mic.format = value; edited(renderOutput, updateRecordControls); })));
  box.append(prow("Countdown", studioSelect([["0", "None"], ["3", "3 seconds"], ["5", "5 seconds"], ["10", "10 seconds"]], String(studio.setup.countdown), (value) => { studio.setup.countdown = Number(value); edited(); })));
  box.append(prow("Menu bar", studioCheck(studio.setup.menubar, (value) => { studio.setup.menubar = value; edited(); }, "clock while recording")));
  box.append(h("p", { class: "note", text: "This setup ≈ " + megabytesPerMinute(studio.setup) + " MB per minute (the screen alone is ~25-70 MB/min, depending on what moves). Export chooses the format, size and fps." }));
}

const ICONS = { audio: "M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zm12-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0z" };
function sizeText(bytes) { return bytes > 1e9 ? (bytes / 1e9).toFixed(1) + " GB" : bytes > 1e6 ? (bytes / 1e6).toFixed(1) + " MB" : Math.max(1, Math.round(bytes / 1e3)) + " KB"; }

async function takeShot(kind) {
  const screen = screenSource();
  const body = { kind, display: screen ? screen.display : 1, delay: studio.delay, clipboard: studio.clipboard };
  if (kind !== "screen") toast("Select on the Mac: drag an area or click a window (Esc cancels)");
  else if (studio.delay) toast("Screenshot in " + studio.delay + " s");
  const { status, data } = await api("POST", "/api/studio/shot", body);
  if (status !== 200) { toast(data.error || "Screenshot failed"); return; }
  if (data.clipboard) { toast("Copied to the clipboard"); return; }
  toast("Saved " + data.saved.split("/").pop());
  studio.libraryLoaded = false;
}

// ---- projects tab ----
const projectMedia = (path, file) => "/media/project?t=" + encodeURIComponent(TOKEN) + "&path=" + encodeURIComponent(path) + "&file=" + encodeURIComponent(file);
const PROJECT_TRACKS = ["screen", "camera", "mic"];

// Global project time -> the segment file that plays it and the time inside that segment.
function projectClock(project, t) {
  const segments = project.segments || [];
  if (!segments.length) return { segment: -1, local: 0 };
  const at = Math.max(0, t);
  let start = 0;
  for (let index = 0; index < segments.length; index++) {
    const length = segments[index].duration;
    if (at < start + length || index === segments.length - 1) return { segment: index, local: Math.min(length, Math.max(0, at - start)) };
    start += length;
  }
  return { segment: -1, local: 0 };
}

function segmentStart(project, index) {
  let start = 0;
  for (let i = 0; i < index; i++) start += project.segments[i].duration;
  return start;
}

// The scene shown at a moment: the last scene event at or before it (marks change nothing).
function sceneAt(project, t) {
  let scene = project.scenes && project.scenes.length ? project.scenes[0].id : "screen";
  let first = true;
  for (const event of project.events || []) {
    if (!event.scene) continue;
    if (first || event.t <= t + 1e-9) scene = event.scene;
    first = false;
    if (event.t > t + 1e-9) break;
  }
  return scene;
}

function sceneName(id) {
  const doc = studioDoc();
  const scene = doc && doc.scenes.find((item) => item.id === id);
  return scene ? scene.name : id;
}

// What a project shows in a scene, like capture_project.effective_placements: sources that were not recorded
// are skipped, and a scene left with only the screen uses the `screen` scene's layout.
function projectPlacements(project, scene, canvas) {
  const tracks = new Set();
  for (const segment of project.segments) for (const track of Object.keys(segment.files || {})) tracks.add(track);
  const available = new Set(project.sources.filter((source) => source.enabled && (source.kind === "image" || source.kind === "text" || tracks.has(source.kind))).map((source) => source.id));
  const layouts = project.layouts[canvas] || {};
  const pick = (name) => {
    const layout = layouts[name];
    if (!layout) return [{ kind: "color", color: "#000000" }, [], false];
    const chosen = [];
    let dropped = false;
    for (const source of project.sources) {
      const item = layout.placements[source.id];
      if (!item || !item.visible) continue;
      if (available.has(source.id)) chosen.push([source, item]);
      else dropped = true;
    }
    return [layout.background, chosen, dropped];
  };
  let [background, chosen, dropped] = pick(scene);
  const onlyScreen = chosen.length === 1 && chosen[0][0].id === "screen";
  if (scene !== "screen" && (!chosen.length || (onlyScreen && dropped)) && layouts.screen) [background, chosen] = pick("screen");
  return [background, chosen];
}

// ---- project player: the screen video is the clock; camera and microphone follow their `starts` ----
function makePlayer() {
  const screen = h("video", { playsinline: true, preload: "auto" });
  const camera = h("video", { playsinline: true, preload: "auto" });
  camera.muted = true;
  const mic = h("audio", { preload: "auto" });
  return { screen, camera, mic, segment: -1, t: 0, playing: false, timer: 0 };
}

function stopProjectPlayer() {
  const player = studio.player;
  if (!player) return;
  clearInterval(player.timer);
  for (const track of PROJECT_TRACKS) {
    const node = player[track];
    if (node.pause) node.pause();
    if (node.removeAttribute) node.removeAttribute("src");
  }
  studio.player = null;
}

function clockTrack(segment) { return PROJECT_TRACKS.find((track) => segment.files && segment.files[track]) || null; }
function playMedia(node) { const playing = node.play && node.play(); if (playing && playing.catch) playing.catch(() => {}); }
function setMediaTime(node, value) {
  if (node.readyState >= 1) node.currentTime = value;
  else node.addEventListener("loadedmetadata", () => { node.currentTime = value; }, { once: true });
}

function seekProject(t) {
  const project = studio.project, player = studio.player;
  if (!project || !player) return;
  const { segment, local } = projectClock(project, t);
  if (segment < 0) return;
  const before = currentScene();
  const part = project.segments[segment], starts = part.starts || {};
  if (segment !== player.segment) {
    player.segment = segment;
    for (const track of PROJECT_TRACKS) {
      const file = part.files && part.files[track];
      if (file) player[track].src = projectMedia(project.path, file);
      else { if (player[track].pause) player[track].pause(); if (player[track].removeAttribute) player[track].removeAttribute("src"); }
    }
  }
  player.t = segmentStart(project, segment) + local;
  for (const track of PROJECT_TRACKS) if (part.files && part.files[track]) setMediaTime(player[track], Math.max(0, local - (starts[track] || 0)));
  resumePlayer();
  drawPlayerClock();
  if (currentScene() !== before) { drawStage(); renderProjectProps(); }
}

function resumePlayer() {
  const player = studio.player;
  if (!player || !player.playing || !studio.project) return;
  const part = studio.project.segments[player.segment];
  if (part) for (const track of PROJECT_TRACKS) if (part.files && part.files[track]) playMedia(player[track]);
}

function toggleProjectPlay() {
  const player = studio.player;
  if (!player) return;
  player.playing = !player.playing;
  if (player.playing) {
    if (player.t >= studio.project.duration - 0.05) seekProject(0);
    resumePlayer();
  } else for (const track of PROJECT_TRACKS) if (player[track].pause) player[track].pause();
  drawPlayerClock();
}

function syncPlayer() {
  const project = studio.project, player = studio.player;
  if (!project || !player || player.segment < 0) return;
  const part = project.segments[player.segment], clock = clockTrack(part);
  if (!clock) return;
  const starts = part.starts || {};
  const local = (player[clock].currentTime || 0) + (starts[clock] || 0);
  const before = currentScene();
  player.t = segmentStart(project, player.segment) + Math.min(local, part.duration);
  if (player.playing) {
    for (const track of PROJECT_TRACKS) {
      if (track === clock || !part.files[track]) continue;
      const node = player[track], wanted = local - (starts[track] || 0);
      if (wanted < 0) { if (!node.paused) node.pause(); continue; }
      if (Math.abs(node.currentTime - wanted) > 0.25) node.currentTime = wanted;
      if (node.paused && !node.ended) playMedia(node);
    }
    if (player[clock].ended || local >= part.duration - 0.03) {
      if (player.segment + 1 < project.segments.length) seekProject(segmentStart(project, player.segment + 1));
      else { player.playing = false; for (const track of PROJECT_TRACKS) if (player[track].pause) player[track].pause(); }
    }
  }
  drawPlayerClock();
  if (currentScene() !== before) { drawStage(); renderProjectProps(); }
}

function drawPlayerClock() {
  const player = studio.player, project = studio.project;
  if (!player || !project) return;
  const time = $("projTime"), seek = $("projSeek"), play = $("projPlay");
  if (time) time.textContent = clockText(player.t) + " / " + clockText(project.duration);
  if (seek && document.activeElement !== seek) seek.value = String(player.t);
  if (play) { play.textContent = ""; play.append(studioIcon(player.playing ? "pause" : "play")); }
}

// ---- projects list ----
async function loadLibrary() {
  studio.libraryLoaded = true;
  const { status, data } = await api("GET", "/api/studio/library");
  if (status !== 200) return;
  studio.library = Array.isArray(data) ? data : [];
  if (state.view === "studio" && studio.tab === "projects" && !studio.project) renderProjects();
}

async function loadProjects() {
  studio.projectsLoaded = true;
  const { status, data } = await api("GET", "/api/studio/projects");
  if (status !== 200) { toast(data.error || "Could not list the projects"); return; }
  studio.projects = Array.isArray(data) ? data : [];
  if (state.view === "studio" && studio.tab === "projects" && !studio.project) renderProjects();
}

function exportLabel(path) {
  const found = /\s(16x9|9x16|1x1|4x5|source)(?:\s\d+)?\.(\w+)$/.exec(path);
  return found ? found[1].replace("x", ":") + " " + found[2].toUpperCase() : String(path).split(".").pop().toUpperCase();
}

function renderProjects() {
  const box = $("studioProjects");
  if (!box) return;
  if (studio.project) { renderProjectPage(box); return; }
  box.textContent = "";
  const filters = h("div", { class: "levels", id: "libFilters" }, [["projects", "Projects"], ["exports", "Exports"], ["screenshots", "Screenshots"]].map(([value, label]) =>
    h("button", { class: studio.filter === value ? "on" : "", text: label, onclick: () => { studio.filter = value; localStorage.setItem("studio-filter", value); renderProjects(); } })));
  box.append(h("div", { class: "projbar" }, filters, h("span", { class: "spacer" }),
    h("button", { text: "Open project…", title: "Open a project folder from anywhere (a moved or copied project)", onclick: openProjectDialog }),
    h("button", { class: "ghost", text: "Refresh", onclick: () => { loadProjects(); loadLibrary(); } })));
  const grid = h("div", { class: "library", id: "library" });
  box.append(grid);
  if (studio.filter === "projects") {
    if (!studio.projectsLoaded) loadProjects();
    if (!studio.projects.length) { grid.append(h("div", { class: "empty", text: "No projects yet. Every recording becomes one." })); return; }
    for (const item of studio.projects.slice(0, 200)) grid.append(projectCard(item));
    return;
  }
  if (!studio.libraryLoaded) loadLibrary();
  renderLibrary(grid);
}

function projectCard(item) {
  const pic = h("div", { class: "pic" });
  if (item.tracks.includes("screen") || item.tracks.includes("camera")) pic.append(h("img", { src: media("/media/thumb") + "&path=" + encodeURIComponent(item.path), alt: "", loading: "lazy" }));
  else pic.append(svgIcon(ICONS.audio));
  pic.append(h("span", { class: "len", text: clockText(item.duration) }));
  if (item.state !== "ready") pic.append(h("span", { class: "state " + item.state, text: item.state, title: (item.problems || []).join("\n") }));
  const formats = item.exports.map(exportLabel);
  const when = new Date(item.created).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  return h("button", { class: "item", title: item.path, onclick: () => openProject(item.path) }, pic,
    h("div", { class: "cap" }, h("b", { text: item.name }), h("span", { text: when + " · " + sizeText(item.size) + " · " + (formats.length ? formats.join(", ") : "not exported") })));
}

async function openProjectDialog() {
  const { status, data } = await api("POST", "/api/studio/open-project", {});
  if (status !== 200) { toast(data.error || "Could not open the project"); return; }
  if (data.unavailable) { toast("The folder dialog needs macOS (osascript)"); return; }
  if (!data.path) return;
  studio.projectsLoaded = false;
  await openProject(data.path);
}

// ---- one project: synced preview, timeline, layout edits saved to the project, export ----
async function openProject(path, withExport) {
  const { status, data } = await api("GET", "/api/studio/project?path=" + encodeURIComponent(path));
  if (status !== 200) { toast(data.error || "Could not open the project"); return; }
  if (studio.projectTimer) await flushProject();
  stopProjectPlayer();
  studio.tab = "projects";
  localStorage.setItem("studio-tab", "projects");
  clearTimeout(studio.previewTimer);
  stopStream("camStream");
  stopStream("micStream");
  stopStream("screenStream");
  delete data.warnings;
  studio.project = data;
  startHistory(data);
  studio.projectCanvas = STUDIO_RATIOS[data.export.canvas] ? data.export.canvas : "16:9";
  const shown = projectPlacements(data, sceneAt(data, 0), studio.projectCanvas)[1];
  studio.selected = shown.length ? shown[shown.length - 1][0].id : data.sources[0].id;
  studio.player = makePlayer();
  studio.player.timer = setInterval(syncPlayer, 200);
  if (state.view === "studio") renderStudioBody();
  seekProject(0);
  if (withExport) renderExportDialog(data);
}

async function closeProject() {
  if (studio.projectTimer) await flushProject();
  stopProjectPlayer();
  studio.project = null;
  studio.projectsLoaded = false;
  renderStudioBody();
}

function saveProjectSoon() {
  clearTimeout(studio.projectTimer);
  studio.projectTimer = setTimeout(flushProject, 500);
}

async function flushProject() {
  clearTimeout(studio.projectTimer);
  studio.projectTimer = 0;
  const project = studio.project;
  if (!project) return;
  // Only project.json keys go back; capture keeps what was recorded (segments, exports, ...) from disk.
  const body = {};
  for (const [key, value] of Object.entries(project)) if (!["path", "size", "warnings"].includes(key)) body[key] = value;
  const { status, data } = await api("POST", "/api/studio/project", { path: project.path, project: body });
  if (status !== 200) toast(data.error || "Could not save the project");
}

async function projectAction(action) {
  const project = studio.project;
  if (!project) return;
  if (action === "delete" && !confirm("Move the project “" + project.name + "” to the Trash? Exported videos stay.")) return;
  const { status, data } = await api("POST", "/api/studio/action", { action, path: project.path });
  if (status !== 200) { toast(data.error || "Failed"); return; }
  if (action !== "delete") return;
  toast("Moved to the Trash");
  clearTimeout(studio.projectTimer);
  studio.projectTimer = 0;
  stopProjectPlayer();
  studio.project = null;
  studio.projects = studio.projects.filter((item) => item.path !== project.path);
  if (state.view === "studio") renderStudioBody();
}

function renderProjectPage(box) {
  const project = studio.project;
  box.textContent = "";
  const meta = [clockText(project.duration), project.state, sizeText(project.size || 0)].join(" · ");
  box.append(h("div", { class: "projbar" },
    h("button", { class: "ghost back", onclick: closeProject }, studioIcon("back"), "Projects"),
    h("b", { text: project.name }), h("span", { class: "where", text: meta }), h("span", { class: "spacer" }),
    h("div", { class: "seg fmt" }, STUDIO_FORMATS.map(([value, label]) =>
      h("button", { class: studio.projectCanvas === value ? "on" : "", text: label, onclick: () => { studio.projectCanvas = value; renderProjectPage(box); } }))),
    h("button", { class: "primary", text: "Export…", onclick: () => renderExportDialog(project) }),
    h("button", { text: "Show in Finder", onclick: () => projectAction("reveal") }),
    h("button", { class: "ghost", text: "Move to Trash", onclick: () => projectAction("delete") })));
  if (project.problems.length) box.append(h("div", { class: "warns" }, project.problems.map((problem) => h("div", {}, studioIcon("alert"), h("span", { text: problem })))));
  const seek = h("input", { type: "range", id: "projSeek", min: "0", max: String(project.duration), step: "0.01", value: "0" });
  seek.addEventListener("input", () => seekProject(Number(seek.value)));
  const timeline = h("div", { class: "scenelist" });
  for (const event of project.events) {
    if (!event.scene && !("mark" in event)) continue;
    timeline.append(h("div", { role: "button", tabindex: "0", style: "cursor:pointer", onclick: () => seekProject(event.t) },
      h("span", { class: "t", text: clockText(event.t) }), event.scene ? h("span", { text: sceneName(event.scene) }) : h("span", { class: "markname" }, studioIcon("flag"), event.mark || "mark")));
  }
  const exports = h("div", { class: "scenelist" }, project.exports.length ? project.exports.map((item) => {
    const name = String(item.path).split("/").pop();
    return h("div", { role: "button", tabindex: "0", style: "cursor:pointer", title: "Show in Finder", onclick: () => revealExport(name) }, h("span", { text: name }));
  }) : h("div", { class: "where", text: "Not exported yet." }));
  box.append(h("div", { class: "projpage" },
    h("div", { class: "centre" },
      stageFrame(),
      h("div", { class: "player" }, h("button", { id: "projPlay", title: "Play / pause", "aria-label": "Play / pause", onclick: toggleProjectPlay }, studioIcon("play")), seek, h("span", { class: "where", id: "projTime" })),
      h("div", { class: "sthint", id: "stageHint" })),
    h("div", { class: "right" },
      h("div", { class: "pane" }, h("h5", { text: "Timeline" }), timeline),
      h("div", { class: "pane", id: "propsPane" }),
      h("div", { class: "pane" }, h("h5", { text: "Exports" }), exports))));
  drawStage();
  drawPlayerClock();
  renderProjectProps();
}

function renderProjectProps() {
  const box = $("propsPane");
  if (!box || !studio.project) return;
  box.textContent = "";
  box.append(h("h5", { text: "Layout · " + sceneName(currentScene()) + " · " + currentCanvas() }));
  if (currentCanvas() === "source") { box.append(h("p", { class: "note", text: "“As recorded” is the screen as captured; pick a format to change the layout." })); return; }
  const shown = projectPlacements(studio.project, currentScene(), currentCanvas())[1].map(([source]) => source);
  if (!shown.length) { box.append(h("p", { class: "note", text: "Nothing of this project is visible in this scene." })); return; }
  if (!shown.some((source) => source.id === studio.selected)) studio.selected = shown[shown.length - 1].id;
  box.append(prow("Source", studioSelect(shown.map((source) => [source.id, sourceName(source)]), studio.selected, (value) => { studio.selected = value; drawStage(); renderProjectProps(); })));
  const source = sourceById(studio.selected), item = placementOf(studio.selected);
  if (source && item) box.append(...placementControls(source, item));
  else box.append(h("p", { class: "note", text: "Shown through the Screen scene's layout; edit it while that scene plays." }));
  box.append(h("p", { class: "note", text: "Saved to this project only; the studio setup stays as it is." }));
}

async function revealExport(name) {
  const { status, data } = await api("POST", "/api/studio/action", { action: "reveal", name });
  if (status !== 200) toast(data.error || "Not in the recordings folder");
}

// ---- export dialog ----
const EXPORT_DEFAULTS = { canvas: "16:9", height: 1440, fps: 60, codec: "h264", quality: "high", container: "mov", normalize: true, delete_sources: false };

// Pre-fill: this project's last export, else the last settings used anywhere (setup.export), like capture's export_settings.
function exportDefaults(project, setup) {
  const values = { ...EXPORT_DEFAULTS };
  for (const layer of [(setup && setup.export) || {}, (project && project.export) || {}]) {
    for (const key of Object.keys(EXPORT_DEFAULTS)) if (key in layer) values[key] = layer[key];
  }
  if (project && project.mode === "camera" && !(project.export && "height" in project.export)) values.height = 1080;
  values.delete_sources = false;
  return values;
}

function exportHeightFor(canvas, mode) { return canvas === "16:9" && mode !== "camera" ? 1440 : 1080; }

function renderExportDialog(project) {
  const sheet = $("viewerSheet");
  if (!sheet) return;
  studio.item = null;
  sheet.textContent = "";
  const values = exportDefaults(project, studio.setup);
  const audioOnly = project.mode === "audio";
  const field = (label, control) => h("label", {}, label, control);
  const tick = (label, key) => {
    const input = h("input", { type: "checkbox" });
    input.checked = values[key];
    input.addEventListener("change", () => { values[key] = input.checked; });
    return h("label", { class: "check" }, input, label);
  };
  sheet.append(h("div", { class: "top" }, h("b", { text: "Export " + project.name }), h("button", { class: "ghost", text: "Close", onclick: closeViewer })));
  const form = h("div", { class: "export" });
  if (!audioOnly) {
    const height = studioSelect([["1080", "1080p"], ["1440", "1440p"], ["2160", "2160p (4K)"]], String(values.height), (value) => { values.height = Number(value); });
    height.disabled = values.canvas === "source";
    form.append(
      field("Format", studioSelect(STUDIO_FORMATS, values.canvas, (value) => {
        values.canvas = value;
        values.height = exportHeightFor(value, project.mode);
        height.value = String(values.height);
        height.disabled = value === "source";
      })),
      field("Size (short side)", height),
      field("Frame rate", studioSelect([["60", "60 fps"], ["30", "30 fps"]], String(values.fps), (value) => { values.fps = Number(value); })),
      field("Codec", studioSelect([["h264", "H.264 (plays everywhere)"], ["hevc", "HEVC (smaller files)"]], values.codec, (value) => { values.codec = value; })),
      field("Quality", studioSelect([["high", "High"], ["max", "Max (1.5× bitrate)"]], values.quality, (value) => { values.quality = value; })),
      field("File", studioSelect([["mov", "MOV"], ["mp4", "MP4"]], values.container, (value) => { values.container = value; })));
  }
  form.append(tick("Loudness to −14 LUFS", "normalize"), tick("Delete the recorded tracks after a successful export", "delete_sources"));
  sheet.append(form);
  sheet.append(h("p", { class: "where", text: audioOnly ? "Saved to captures/recordings in the audio format of capture.audio_format." : "Saved to captures/recordings as “" + project.name + " 16x9.mov” (the format in the name), never over another file. 10 minutes of 1440p60 take about 5 minutes; “As recorded” takes seconds." }));
  sheet.append(h("div", { class: "progress" }, h("i", { id: "exportBar" })), h("div", { class: "where", id: "exportState" }));
  sheet.append(h("div", { class: "tools" }, h("button", { class: "primary", text: "Export", onclick: () => startExport(project, values) })));
  $("viewer").classList.add("on");
  if (studio.exportJob && ["queued", "running"].includes(studio.exportJob.phase)) pollExport();
}

async function startExport(project, values) {
  if (values.delete_sources && !confirm("Delete the recorded tracks of “" + project.name + "” after the export? Only the exported file stays.")) return;
  const body = project.mode === "audio"
    ? { path: project.path, normalize: values.normalize, delete_sources: values.delete_sources }
    : { path: project.path, canvas: values.canvas, height: values.height, fps: values.fps, codec: values.codec, quality: values.quality, format: values.container, normalize: values.normalize, delete_sources: values.delete_sources };
  drawExportState({ phase: "queued", percent: 0 });
  const { status, data } = await api("POST", "/api/studio/export", body);
  if (status !== 200) { drawExportState({ phase: "failed", error: data.error || "the export did not start" }); return; }
  await pollExport();
}

// One export runs at a time (capture keeps the queue); the page follows it every second until it ends.
async function pollExport() {
  clearTimeout(studio.exportTimer);
  studio.exportTimer = 0;
  const { status, data } = await api("GET", "/api/studio/export/status");
  if (status !== 200) { drawExportState({ phase: "failed", error: data.error || "no export status" }); return; }
  drawExportState(data);
  if (data.phase === "queued" || data.phase === "running") studio.exportTimer = setTimeout(pollExport, 1000);
  else if (data.phase === "done") { studio.projectsLoaded = false; studio.libraryLoaded = false; }
}

function drawExportState(job) {
  studio.exportJob = job;
  const bar = $("exportBar"), node = $("exportState");
  if (bar) bar.style.width = (job.phase === "done" ? 100 : Math.max(0, Math.min(100, Number(job.percent) || 0))) + "%";
  if (!node) return;
  node.textContent = "";
  const name = String(job.output || "").split("/").pop();
  const left = Number(job.eta) > 90 ? Math.round(job.eta / 60) + " min" : Math.round(Number(job.eta) || 0) + " s";
  if (job.phase === "queued") node.append("Waiting for the export to start…");
  else if (job.phase === "running") node.append("Exporting… " + Math.round(Number(job.percent) || 0) + "%" + (job.eta ? " · about " + left + " left" : ""));
  else if (job.phase === "done") node.append("Saved " + name + " ", h("button", { class: "ghost", text: "Show in Finder", onclick: () => revealExport(name) }));
  else if (job.phase === "failed") node.append("Export failed: " + (job.error || "unknown error"));
}

function renderLibrary(box) {
  box = box || $("library");
  if (!box) return;
  box.textContent = "";
  const kinds = { exports: ["video", "audio"], screenshots: ["image"] }[studio.filter] || ["video", "audio"];
  const items = studio.library.filter((item) => kinds.includes(item.kind));
  if (!items.length) { box.append(h("div", { class: "empty", text: "Nothing here yet." })); return; }
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
    const convert = studioSelect((item.kind === "video" ? [["mp4", "MP4"], ["mov", "MOV"], ["gif", "GIF"], ["m4a", "Audio M4A"], ["mp3", "Audio MP3"]] : [["mp3", "MP3"], ["m4a", "M4A"], ["wav", "WAV"]]).filter(([value]) => !item.name.toLowerCase().endsWith("." + value)), "", () => {});
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
  const count = Math.max(60, Math.min(1200, Math.floor((canvas.clientWidth || 900) / 4)));
  const { status, data } = await api("GET", "/api/studio/wave?name=" + encodeURIComponent(item.name) + "&bars=" + count);
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
$("recPill").addEventListener("click", () => { if (state.view !== "studio") setView("studio"); });
window.addEventListener("resize", () => { if (state.view === "studio" && studio.tab === "record") drawStage(); });

"""
