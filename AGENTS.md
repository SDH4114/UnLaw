# Unlaw project notes

- Purpose: small macOS CLI that dispatches commands from `<name>/main.py`.
- Runtime: Python 3.11+, standard library only; current release is 2.1.3.
- Package: `src/unlawful`; console scripts: `unlaw` and `ul`.
- User data: `${XDG_CONFIG_HOME:-~/.config}/unlaw`; a source build and first CLI invocation bootstrap it without overwriting user files.
- Extension rule: only system commands live in the dispatcher; every other command is seeded as standalone source into `${XDG_CONFIG_HOME:-~/.config}/unlaw/commands/<name>/main.py`. Legacy official import wrappers are migrated, but manually edited command files are never overwritten.
- Configuration: `config.toml` is validated and atomically rewritten; aliases are token arrays, not shell strings.
- Test: `python -m unittest discover -s tests -v`.
- Build check: `python -m build` when `build` is available, otherwise install into a temporary venv with `pip install .`.
- Project templates live in `templates/{commands,python,rust,cpp}` and may override generated files.
- macOS Harness is optional; only `ul mac` and its doctor checks may depend on it.
- Personal commands: `todo` edits the configured Obsidian `TODO.md`; `capture` uses macOS `screencapture` and optional ffmpeg; `music`, `work`, and `yt` drive macOS apps/URLs.
- Telegram credentials: bot token is stored in macOS Keychain under service `unlaw.telegram`; only the chat id is in `config.toml`.
- Local AI: `ul lm` accepts localhost LM Studio endpoints only; it must never silently fall back to a cloud model.
- Terminal arcade: `ul game` includes Tetris, Snake, Minesweeper, and Space Invaders using only stdlib curses.
- Storage: captures, Telegram downloads, and runtime files default to the single configurable `storage.root` (`data`, relative to the Unlaw config directory).
- Arcade difficulty: every game supports `easy`, `normal`, and `hard`; the default comes from `games.difficulty`.
