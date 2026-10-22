#!/bin/sh
set -eu

repository="https://github.com/SDH4114/UnLaw.git"
root="${UNLAW_INSTALL_ROOT:-$HOME/.local}"

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

python=""
for candidate in python3.14 python3.13 python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1; then
        python="$candidate"
        break
    fi
done
if [ -z "$python" ]; then
    echo "Unlaw installer: Python 3.11+ is required (brew install python)." >&2
    exit 1
fi

# Releases before the Rust core were uv tools that own the same ul/unlaw names.
if command -v uv >/dev/null 2>&1 && uv tool list 2>/dev/null | grep -q '^unlaw '; then
    uv tool uninstall unlaw
fi

UNLAW_PYTHON="$python" cargo install --locked --force --git "$repository" --root "$root" unlaw
echo "Installed ul and unlaw into $root/bin. Run: ul doctor --fix"
