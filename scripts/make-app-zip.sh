#!/bin/sh
# Build the downloadable Unlaw.app: the menu bar app with the whole command line
# inside (Contents/Resources/bin). Started without `ul` on the Mac, the app
# installs those programs into ~/.local/bin (app/src/setup.rs). The result is
# dist/Unlaw-<version>-arm64.zip, signed ad hoc: without an Apple Developer ID a
# downloaded copy needs one "Open Anyway" in System Settings > Privacy & Security.
# Usage: scripts/make-app-zip.sh   (from anywhere; needs cargo, Python 3.11+, ditto)
set -eu
cd "$(dirname "$0")/.."
version=$(sed -n 's/^version = "\(.*\)"/\1/p' Cargo.toml | head -n 1)
arch=$(uname -m)
cargo build --release --workspace
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
# `ul gui install` builds the bundle (Info.plist, icon, marker, signature) without
# loading a login job; its own config goes to the temporary folder.
UNLAW_GUI_APPS="$work" XDG_CONFIG_HOME="$work/config" target/release/ul gui install --no-start >/dev/null
bundle="$work/Unlaw.app"
mkdir -p "$bundle/Contents/Resources/bin"
for program in ul unlaw ule ul-rec ula unlawagent ul-app; do
    if [ -f "target/release/$program" ]; then
        cp "target/release/$program" "$bundle/Contents/Resources/bin/"
    fi
done
codesign --force --deep --sign - "$bundle"
mkdir -p dist
out="dist/Unlaw-$version-$arch.zip"
rm -f "$out"
ditto -c -k --keepParent "$bundle" "$out"
echo "Built $out"
