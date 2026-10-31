"""The optional parts of Unlaw, chosen at install time (`ul features`).

The single source of the list: rust/gen_assets.py embeds it into the Rust
core (`rust/src/features.rs`), and install.sh carries a copy that
tests/test_features.py keeps identical. The core (ul, ule, system commands,
zip, app, browser) is always installed and is not listed here.
"""

from __future__ import annotations

CORE = "ul, ule, system commands, zip, app, browser"

# (name, group, summary); the order is the order of every listing.
FEATURES: tuple[tuple[str, str, str], ...] = (
    ("lm", "AI", "Local AI models on MLX: chat, vision, speech, images, video, API server"),
    ("agent", "AI", "Local AI agent in the console or Telegram (ula); needs lm"),
    ("tg", "AI", "Telegram: send messages and files, download through your bot"),
    ("gpt", "AI", "Open the ChatGPT app"),
    ("yt", "Media", "YouTube: search, download video, MP3, podcasts, subtitles"),
    ("music", "Media", "Spotify: open it or play a track"),
    ("lofi", "Media", "Open the lofi website"),
    ("netflix", "Media", "Open Netflix"),
    ("capture", "Media", "Screenshots and screen, camera and microphone recording"),
    ("todo", "Productivity", "Obsidian TODO board"),
    ("desk", "Productivity", "Kanban board, TODO and pomodoro in the browser"),
    ("obsidian", "Productivity", "Open Obsidian"),
    ("work", "Productivity", "lofi plus the current folder in your editor"),
    ("git", "Development", "Stage, commit and push in one command"),
    ("py", "Development", "New Python project from a template"),
    ("rust", "Development", "New Rust project from a template"),
    ("cpp", "Development", "New C++ project from a template"),
    ("zed", "Development", "Open the current folder in your editor"),
    ("mac", "System", "Control macOS apps through macos-harness"),
    ("steam", "System", "Open Steam"),
    ("minecraft", "System", "Open Prism Launcher"),
    ("game", "Fun", "Terminal arcade: Tetris, Snake, Minesweeper, Invaders, Chomp"),
)
# Cargo features of the Rust core; `agent` only gates the ula/unlawagent shortcuts.
CARGO = ("lm", "agent", "game")
REQUIRES: dict[str, tuple[str, ...]] = {"agent": ("lm",)}
NAMES = tuple(name for name, _, _ in FEATURES)


def resolve(names: list[str] | tuple[str, ...]) -> list[str]:
    """Expand "all" (and "none"), add requirements; FEATURES order."""
    chosen = set(NAMES if "all" in names else names)
    for name in list(chosen):
        chosen.update(REQUIRES.get(name, ()))
    return [name for name in NAMES if name in chosen]
