# Rulings: desk Studio (plan Tasks 10-13)

Ruling: the worktree started on main (729c0b5); the branch was moved to 21acac0 (feat/studio-recording) before any work — the task names that base — none.
Ruling: Move to Trash / Show in Finder for a project use `/api/studio/action` with `{action, path}` instead of `{action, name}` — a project name could match a capture file; the path is validated as a known project folder and capture itself refuses to trash projects outside captures/projects (400) — a page sending `name` for a project gets 404.
Ruling: `/api/studio/stop` takes `{force: true}` → `ul capture stop --force` — the warnings strip offers it for a stuck recorder (spec 7.5); without it the page could not finish a stuck recording — none.
Ruling: `/api/studio/record` passes `--display` only when the body has `display` — the saved setup chooses the display; the old body keys stay one-off overrides — a page relying on the old implicit display 1 now gets the setup's display.
Ruling: project thumbnails = `ul capture thumb <first media/screen-*.mp4, else camera-*.mp4>`; audio-only projects answer 404 — capture already has a cached thumbnailer that takes a path — none.
Ruling: `/api/studio/setup` and `/api/studio/project` bodies may be 2 MiB (others stay 64 KiB) — layouts for every format and scene do not fit 64 KiB with images, texts and events — none.
Ruling: "unavailable without osascript" for Open project… is tested in-process (DeskFailureTests), not through the server — the server tests keep /usr/bin on PATH, where the real folder dialog would open on the Mac — none.
Ruling: the rewritten library test expects `/api/studio/library` to be empty after a recording — a recording is now a project folder, not a library file; exports land in recordings/ and show up there — none.
