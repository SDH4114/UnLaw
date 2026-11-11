# Ideas

Not planned work yet: things to decide on later. Plans that are already decided live in `PLAN.md`.

## Community commands in the catalog

Today `catalog/` is generated from the seeds in `src/unlawful`, so adding a command to
the catalog means touching the core. Idea: a separate folder for commands written by
other people, so anyone can share a command without knowing the core.

- `community/<name>/` with `main.py` (or another entry point) and a small manifest
  (name, summary, author, dependencies, minimum Unlaw version).
- CI or a test checks every entry: `--help` works without side effects, stdlib only
  (or declared dependencies), no writes outside `UNLAW_*` paths, the manifest is valid.
- `ul commands search` shows official and community commands separately; `get` verifies
  sha256 as it does now and marks community commands as such.
- Open questions: review process for pull requests, how to update a downloaded community
  command without overwriting local edits, name clashes with future official commands.
