#!/bin/sh
# Build fome-runtime:d96f8e00 on talos from this directory. Run from proximal:
#   ~/git/infra/hosts/talos/config/fome-runtime/build.sh
# Refuses unless talos holds the exact qualified base image ID. Copies proximal's uv (sha256 checked).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
# The qualified image's config digest (classic store ID, e.g. proximal) and talos's containerd-store ID
# for the same image (its manifest digest; talos `docker save` shows Config = BASE_ID, 15 layers).
BASE_ID=sha256:d96f8e00a50a1bb6fab119ac8973a083af9373e2c9c235f3df20f655cfc3b5b7
BASE_MANIFEST=sha256:9724a2d0269250e2a44725a0d2b24b43a6a05f1598d0bd6ff2496b2fba7042e3
BASE_LAYERS=940e0e6f633f9ad94b1d383dc10e8fba80fa81936bd8f50a62ef2732e53bb707   # sha256 of `docker image inspect -f '{{json .RootFS.Layers}}'`
UV_SHA256=$(sha256sum "$HOME/.local/bin/uv" | cut -d' ' -f1)
"$HOME/.local/bin/uv" --version | grep -qx 'uv 0.13.4.*' || { echo "proximal uv is not 0.13.4" >&2; exit 2; }
ctx=$(mktemp -d); trap 'rm -rf "$ctx"' EXIT
cp "$HERE/Dockerfile" "$ctx/"; install -m 0755 "$HOME/.local/bin/uv" "$ctx/uv"
tar -C "$ctx" -c . | ssh talos "set -e
  id=\$(docker image inspect -f '{{.Id}}' agent-ee:ee466-gate-b29cead1)
  layers=\$(docker image inspect -f '{{json .RootFS.Layers}}' agent-ee:ee466-gate-b29cead1 | sha256sum | cut -d' ' -f1)
  case \$id in $BASE_ID|$BASE_MANIFEST) ;; *) echo \"base image \$id is not the qualified image\" >&2; exit 2 ;; esac
  [ \"\$layers\" = $BASE_LAYERS ] || { echo 'base image layer list differs' >&2; exit 2; }
  d=\$(mktemp -d); tar -x -C \$d; [ \"\$(sha256sum \$d/uv | cut -d' ' -f1)\" = $UV_SHA256 ] || exit 2
  docker build -t fome-runtime:d96f8e00 \$d; rm -r \$d
  docker image inspect -f 'built {{.Id}}' fome-runtime:d96f8e00"
