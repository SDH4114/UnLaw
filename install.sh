#!/bin/sh
set -eu

repository="git+https://github.com/SDH4114/UnLaw.git"

if command -v uv >/dev/null 2>&1; then
    uv tool install --force "$repository"
    exit 0
fi

echo "Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh

if command -v uv >/dev/null 2>&1; then
    uv tool install --force "$repository"
elif [ -x "$HOME/.local/bin/uv" ]; then
    "$HOME/.local/bin/uv" tool install --force "$repository"
else
    echo "Unlaw installer: uv installation did not produce an executable." >&2
    exit 1
fi
