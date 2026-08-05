#!/usr/bin/env bash
# Install the pinned headless WezTerm mux build and canonical server config.
# This is intentionally user-local: the GUI runs on clients, not on proximal.
set -euo pipefail

WEZTERM_VERSION=20260715-174104-3658b656
WEZTERM_SHA256=8bd7746682f3290b1fb9b3673f40fdc7203c557ac10e32b2107caef37ccbf77b
ASSET_URL=https://github.com/wezterm/wezterm/releases/download/nightly/wezterm-nightly.Ubuntu24.04.tar.xz

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)
SERVER_CONFIG="$REPO_ROOT/shared/editor/wezterm/server.lua"
BASE="$HOME/.local/opt"
TARGET="$BASE/wezterm-$WEZTERM_VERSION"
CURRENT="$BASE/wezterm-current"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/wezterm"

if [[ $(uname -m) != x86_64 ]]; then
  printf 'unsupported architecture: %s (expected x86_64)\n' "$(uname -m)" >&2
  exit 1
fi

source /etc/os-release
if [[ ${ID:-} != ubuntu || ${VERSION_ID:-} != 24.04 ]]; then
  printf 'unsupported OS: %s %s (expected Ubuntu 24.04)\n' "${ID:-unknown}" "${VERSION_ID:-unknown}" >&2
  exit 1
fi

install -d -m 0755 "$BASE" "$BIN_DIR" "$CONFIG_DIR"

installed_version=
if [[ -x "$TARGET/usr/bin/wezterm" ]]; then
  installed_version=$($TARGET/usr/bin/wezterm -V 2>/dev/null || true)
fi

if [[ $installed_version != "wezterm $WEZTERM_VERSION" ]]; then
  if [[ -e $TARGET ]]; then
    printf 'refusing to replace unexpected target: %s\n' "$TARGET" >&2
    exit 1
  fi

  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  archive="$tmp/wezterm.tar.xz"
  curl --fail --location --silent --show-error "$ASSET_URL" --output "$archive"

  actual_sha=$(sha256sum "$archive" | awk '{print $1}')
  if [[ $actual_sha != "$WEZTERM_SHA256" ]]; then
    printf 'nightly asset changed: expected %s, got %s\n' "$WEZTERM_SHA256" "$actual_sha" >&2
    printf 'update WEZTERM_VERSION and WEZTERM_SHA256 together; refusing drift\n' >&2
    exit 1
  fi

  staging="$TARGET.new"
  rm -rf "$staging"
  install -d -m 0755 "$staging"
  tar -xJf "$archive" -C "$staging" --strip-components=1

  extracted_version=$($staging/usr/bin/wezterm -V)
  if [[ $extracted_version != "wezterm $WEZTERM_VERSION" ]]; then
    printf 'asset version mismatch: expected %s, got %s\n' "$WEZTERM_VERSION" "$extracted_version" >&2
    exit 1
  fi

  mv "$staging" "$TARGET"
fi

ln -sfn "$TARGET" "$CURRENT"
ln -sfn "$CURRENT/usr/bin/wezterm" "$BIN_DIR/wezterm"
ln -sfn "$CURRENT/usr/bin/wezterm-mux-server" "$BIN_DIR/wezterm-mux-server"
if [[ ! -f $SERVER_CONFIG ]]; then
  printf 'shared server config is missing: %s\n' "$SERVER_CONFIG" >&2
  exit 1
fi

install -m 0644 "$SERVER_CONFIG" "$CONFIG_DIR/wezterm.lua"

"$BIN_DIR/wezterm" -V
"$BIN_DIR/wezterm-mux-server" --version
printf 'installed server config: %s\n' "$CONFIG_DIR/wezterm.lua"
printf 'running mux processes were not restarted\n'
