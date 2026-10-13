# Unlaw project notes

- Purpose: small macOS CLI that dispatches commands from `<name>/main.py`.
- Runtime: Python 3.11+, standard library only; current release is 2.1.3.
- Package: `src/unlawful`; console scripts: `unlaw` and `ul`.
- User data: `${XDG_CONFIG_HOME:-~/.config}/unlaw`; a source build and first CLI invocation bootstrap it without overwriting user files.
- Extension rule: only system commands live in the dispatcher; every other command is seeded as standalone source into `${XDG_CONFIG_HOME:-~/.config}/unlaw/commands/<name>/main.py`. Legacy official import wrappers are migrated, but manually edited command files are never overwritten.
- Seeded sources contain only that command's logic and minimal config helpers/defaults; unrelated command code must never be concatenated into them.
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

- Every new or changed command must support `--help` and `-h` before any side effects, returning 0 and showing its purpose, all actions/options, defaults, dependencies and examples. Keep help accurate when behavior changes; include it in standalone seeded sources and command templates.
- YouTube downloads: `ul yt download <URL> [--format mov|mp4|raw] [--audio] [--quality <height>] [--output <directory>]` invokes optional external yt-dlp and ffmpeg/ffprobe, defaults to MOV in `storage.root/youtube` (`raw` keeps source codecs/container; `--audio` saves MP3), and never downloads an entire playlist or overwrites existing files.

- YouTube subtitles: `--sub` or `--sub-lang [code]` saves only Markdown (original language if omitted); invalid codes list available tracks. Markdown starts with the video link and labels authored/automatic captions. `--full` saves video, separate MP3 and Markdown using one media download; unavailable/failed captions report an incomplete result while retaining saved media. Subtitle-only mode needs no ffmpeg.
- Archives: `ul zip` creates zip (default `zip.format`), 7z, rar (needs `rar`), tar.zst/xz/gz and auto-extracts by content; levels use one 0-9 scale (7-Zip names, default `max` = 7) mapped to each format's native settings, and media-heavy input without an explicit level drops to 1; 7-Zip is preferred with zip/bsdtar fallbacks. It never overwrites (adds " 2"), strips macOS junk unless `--keep-junk`, extracts multi-item archives into a folder, and feeds passwords via stdin, never argv.
