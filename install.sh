#!/bin/sh
set -eu

repository="https://github.com/SDH4114/UnLaw.git"
root="${UNLAW_INSTALL_ROOT:-$HOME/.local}"

python=""
# Newest first; a range so a new Python (3.15, ...) is found without a new installer.
for minor in 20 19 18 17 16 15 14 13 12 11; do
    if command -v "python3.$minor" >/dev/null 2>&1; then
        python="python3.$minor"
        break
    fi
done
if [ -z "$python" ] && command -v python3 >/dev/null 2>&1 \
    && python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    python="python3"
fi
if [ -z "$python" ]; then
    echo "Unlaw installer: Python 3.11+ is required (brew install python)." >&2
    exit 1
fi

# Optional features. UNLAW_FEATURES="yt game" (or "all"/"none") decides without
# questions; an existing installation keeps its core.features (re-running the
# installer is an update and never asks); otherwise a checklist on the terminal,
# or everything when there is no terminal. The list is a copy of
# src/unlawful/features.py; tests/test_features.py keeps them identical.
chooser=$(cat <<'PY'
import os, sys

CORE = "ul, ule, system commands, zip, app, browser"
FEATURES = [
    ("lm", "AI", "Local AI models on MLX: chat, vision, speech, images, video, API server"),
    ("agent", "AI", "Local AI agent in the console or Telegram (ula); needs lm"),
    ("tg", "AI", "Telegram: send messages and files, download through your bot"),
    ("gpt", "AI", "Open the ChatGPT app"),
    ("claude", "AI", "Open the Claude app"),
    ("yt", "Media", "YouTube: search, download video, MP3, podcasts, subtitles"),
    ("spotify", "Media", "Spotify: open it or play a track"),
    ("lofi", "Media", "Open the lofi website"),
    ("netflix", "Media", "Open Netflix"),
    ("capture", "Media", "Screenshots and screen, camera and microphone recording"),
    ("desk", "Productivity", "Kanban boards, Reminders, pomodoro and canvas; terminal access for agents"),
    ("obsidian", "Productivity", "Open Obsidian"),
    ("work", "Productivity", "lofi plus the current folder in your editor"),
    ("timer", "Productivity", "Countdown timers and alarms with macOS notifications"),
    ("clip", "Productivity", "Clipboard history in the background: list, search, copy again"),
    ("weather", "Productivity", "Weather now and the forecast (Open-Meteo, no key)"),
    ("doc", "Productivity", "Documents for Edit and ule: text, images, PDF, Office, CSV, SQLite"),
    ("git", "Development", "Stage, commit and push in one command"),
    ("py", "Development", "New Python project from a template"),
    ("rust", "Development", "New Rust project from a template"),
    ("cpp", "Development", "New C++ project from a template"),
    ("zed", "Development", "Open the current folder in your editor"),
    ("awake", "System", "Keep the Mac awake for a time, until a time or while a command runs; lid closed too"),
    ("sys", "System", "Computer stats: CPU, GPU, RAM, disk, battery and charge cycles"),
    ("menubar", "System", "Unlaw.app: menu bar items, hotkeys and a command palette for every command"),
    ("mac", "System", "Control macOS apps through macos-harness"),
    ("steam", "System", "Open Steam"),
    ("minecraft", "System", "Open Prism Launcher"),
    ("game", "Fun", "Terminal arcade: Tetris, Snake, Minesweeper, Invaders, Chomp, Dash"),
]
REQUIRES = {"agent": ("lm",)}
CARGO = ("lm", "agent", "game", "capture")
NAMES = [name for name, _, _ in FEATURES]


def resolve(names):
    chosen = set(NAMES if "all" in names else names)
    for name in list(chosen):
        chosen.update(REQUIRES.get(name, ()))
    return [name for name in NAMES if name in chosen]


def report(chosen):
    """Line 1: the selection for `ul features set`; line 2: cargo features."""
    print("all" if len(chosen) == len(NAMES) else " ".join(chosen) or "none")
    print(",".join(name for name in NAMES if name in chosen and name in CARGO))


def toggle(chosen, name):
    if name in chosen:
        chosen.discard(name)
        chosen.difference_update(other for other, needs in REQUIRES.items() if name in needs)
    else:
        chosen.add(name)
        chosen.update(REQUIRES.get(name, ()))


def draw(tty, chosen, at):
    lines = [
        ("Unlaw: choose what to install", False),
        ("Up/Down move, Space toggle, a all/none, Enter install, q cancel", False),
        ("Core (always): " + CORE, False),
    ]
    group, cursor = "", 0
    for index, (name, section, summary) in enumerate(FEATURES):
        if section != group:
            group = section
            lines += [("", False), (group, False)]
        if index == at:
            cursor = len(lines)
        mark = "x" if name in chosen else " "
        lines.append(("%s [%s] %-10s %s" % (">" if index == at else " ", mark, name, summary), index == at))
    try:
        width, height = os.get_terminal_size(tty)
    except OSError:
        width, height = 0, 0
    # Some terminals (and pseudo-terminals) report 0x0.
    width, height = width or 100, max(height or 40, 5)
    top = min(max(cursor - height + 2, 0), max(len(lines) - height, 0))
    out = ["\x1b[H\x1b[2J"]
    for row, (text, current) in enumerate(lines[top:top + height]):
        text = text[:width]
        out.append("\x1b[%d;1H" % (row + 1) + ("\x1b[7m%s\x1b[0m" % text if current else text))
    os.write(tty, "".join(out).encode())


def choose():
    import termios, tty as ttymode
    tty = os.open("/dev/tty", os.O_RDWR)
    saved = termios.tcgetattr(tty)
    chosen, at = set(NAMES), 0
    try:
        ttymode.setcbreak(tty)
        os.write(tty, b"\x1b[?1049h\x1b[?25l")
        while True:
            draw(tty, chosen, at)
            key = os.read(tty, 8)
            if key in (b"\x1b[A", b"k"):
                at = (at - 1) % len(NAMES)
            elif key in (b"\x1b[B", b"j"):
                at = (at + 1) % len(NAMES)
            elif key == b" ":
                toggle(chosen, NAMES[at])
            elif key == b"a":
                chosen = set() if len(chosen) == len(NAMES) else set(NAMES)
            elif key in (b"\r", b"\n"):
                return resolve(chosen)
            elif key in (b"q", b"\x1b", b"\x03"):
                return None
    finally:
        os.write(tty, b"\x1b[?25h\x1b[?1049l")
        termios.tcsetattr(tty, termios.TCSADRAIN, saved)
        os.close(tty)


def configured(path):
    """core.features of an existing config.toml; unreadable or invalid means all."""
    import tomllib
    try:
        with open(path, "rb") as handle:
            names = tomllib.load(handle).get("core", {}).get("features", ["all"])
    except (OSError, tomllib.TOMLDecodeError, AttributeError):
        return ["all"]
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        return ["all"]
    return [name for name in names if name == "all" or name in NAMES]


mode, value = (sys.argv[1:] + ["", ""])[:2]
if mode == "--preset":
    names = value.replace(",", " ").split()
    unknown = [name for name in names if name not in ("all", "none") and name not in NAMES]
    if unknown or not names:
        sys.stderr.write("Unlaw installer: unknown feature(s) in UNLAW_FEATURES: %s\n" % (", ".join(unknown) or "(empty)"))
        sys.exit(2)
    report(resolve(names))
elif mode == "--config":
    report(resolve(configured(value)))
elif mode == "--all":
    report(list(NAMES))
else:
    chosen = choose()
    if chosen is None:
        sys.exit(1)
    report(chosen)
PY
)

config="${XDG_CONFIG_HOME:-$HOME/.config}/unlaw/config.toml"
if [ -n "${UNLAW_FEATURES:-}" ]; then
    set -- --preset "$UNLAW_FEATURES"
elif [ -f "$config" ]; then
    echo "Existing Unlaw configuration found: keeping its features (change them with: ul features)."
    set -- --config "$config"
elif (: </dev/tty) 2>/dev/null; then
    set -- --choose
else
    set -- --all
fi
if ! choice=$("$python" -I -c "$chooser" "$@"); then
    echo "Unlaw installer: cancelled; nothing was installed." >&2
    exit 1
fi
selection=$(printf '%s\n' "$choice" | sed -n 1p)
cargo_features=$(printf '%s\n' "$choice" | sed -n 2p)
echo "Installing the core and: $selection"

# cargo links with the system compiler; without the Command Line Tools /usr/bin/cc
# is only a stub and the build fails late with "linker `cc` not found".
if ! xcode-select -p >/dev/null 2>&1; then
    echo "Unlaw installer: the Xcode Command Line Tools are required to build Unlaw." >&2
    echo "Install them with: xcode-select --install, then run the installer again." >&2
    exit 1
fi

if ! command -v cargo >/dev/null 2>&1 && [ -x "$HOME/.cargo/bin/cargo" ]; then
    PATH="$HOME/.cargo/bin:$PATH"
fi
if ! command -v cargo >/dev/null 2>&1; then
    echo "Installing Rust (rustup)..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
    PATH="$HOME/.cargo/bin:$PATH"
fi
if ! command -v cargo >/dev/null 2>&1; then
    echo "Unlaw installer: Rust installation did not produce cargo." >&2
    exit 1
fi

# Releases before the Rust core were uv tools that own the same ul/unlaw names.
if command -v uv >/dev/null 2>&1 && uv tool list 2>/dev/null | grep -q '^unlaw '; then
    uv tool uninstall unlaw
fi

# Both packages share one build folder, like `ul update`.
CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$HOME/Library/Caches/unlaw/cargo-target}"
export CARGO_TARGET_DIR
UNLAW_PYTHON="$python" cargo install --locked --force --git "$repository" --root "$root" \
    --no-default-features ${cargo_features:+--features "$cargo_features"} unlaw
UNLAW_PYTHON="$python" cargo install --locked --force --git "$repository" --root "$root" ule
# Unlaw.app (feature menubar): its own package, so ul never links the window libraries.
case " $selection " in
    *" all "* | *" menubar "*) with_gui=yes ;;
    *) with_gui=no ;;
esac
# Optional and heavy (a web view): a failed build must not stop the shell setup
# below, without which `ul` looks hung (macOS has its own /usr/bin/ul).
if [ "$with_gui" = yes ]; then
    if ! UNLAW_PYTHON="$python" cargo install --locked --force --git "$repository" --root "$root" unlaw-app; then
        echo "Unlaw installer: Unlaw.app could not be built; the command line is installed. Retry later with: ul update --force" >&2
        with_gui=no
    fi
fi
# shellcheck disable=SC2086 # the selection is a list of words
"$root/bin/ul" features set --no-build $selection

case " $selection " in
    *" all "* | *" yt "* | *" capture "*)
        if ! command -v ffmpeg >/dev/null 2>&1; then
            echo "yt and capture use ffmpeg (and yt uses yt-dlp): brew install ffmpeg yt-dlp"
        fi
        ;;
esac
# macOS ships its own /usr/bin/ul (an underline filter that waits on stdin), so
# $root/bin must come before /usr/bin, or `ul` seems to hang and `ul doctor`
# says "No such file or directory". doctor --fix adds the PATH line and the shell
# integration to ~/.zshrc (only what is missing) and creates the data folders.
echo "Setting up the shell (~/.zshrc)..."
if ! "$root/bin/ul" doctor --fix; then
    echo "Unlaw installer: some checks above need attention (ul doctor shows them again)." >&2
fi
# Teach every AI agent on this Mac (Claude Code, Codex, OpenCode, Gemini, Kimi...)
# how to use ul and write commands; `ul update` refreshes it.
if ! "$root/bin/ul" skills install; then
    echo "Unlaw installer: the agent skill was not installed (run: ul skills install)." >&2
fi
if [ "$with_gui" = yes ] && ! "$root/bin/ul" gui install; then
    echo "Unlaw installer: Unlaw.app was not installed (run: ul gui install)." >&2
fi
echo "Installed Unlaw into $root/bin. Change features later: ul features."
ready=no
saved_ifs=$IFS
IFS=:
set -f
for entry in $PATH; do
    if [ "$entry" = "$root/bin" ]; then
        ready=yes
        break
    fi
    [ "$entry" != /usr/bin ] || break
done
set +f
IFS=$saved_ifs
if [ "$ready" = no ]; then
    echo "Open a new terminal window (or run: exec zsh) before using ul: in this one"
    echo "\`ul\` is still macOS' own /usr/bin/ul, not Unlaw."
fi
