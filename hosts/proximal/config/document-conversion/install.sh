#!/usr/bin/env bash
set -euo pipefail

source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
marker_venv="${MARKER_VENV:-$HOME/git/marker/.venv}"
test -x "${LLAMA_CPP_BINARY:-$HOME/git/llama.cpp/build/bin/llama-server}"

uv venv --allow-existing --python 3.12 "$marker_venv"
uv pip install --upgrade --python "$marker_venv/bin/python" --torch-backend cpu 'marker-pdf[full]==2.1.0'
uv tool install --upgrade --python 3.12 --torch-backend cpu 'docling==2.145.0'
uv tool install --upgrade --python 3.12 'mineru==4.1.3'
uv pip check --python "$marker_venv/bin/python"
install -Dm755 "$source_dir/run-marker.sh" "$HOME/.local/bin/marker-local"
install -Dm644 "$source_dir/mineru-config.yaml" "$HOME/.mineru/config.yaml"
MINERU_TELEMETRY_DISABLED=1 mineru-kit models download --tier standard --source huggingface
MINERU_TELEMETRY_DISABLED=1 mineru-kit models verify --tier standard
# The managed API currently resolves its empty upload path against its cwd.
cd "$HOME/.mineru"
mineru_was_running="$(mineru server status --json | python3 -c 'import json,sys; print("yes" if json.load(sys.stdin)["running"] else "no")')"
if [ "$mineru_was_running" = no ]; then
  MINERU_TELEMETRY_DISABLED=1 mineru server start
  trap 'mineru server stop' EXIT
fi
MINERU_TELEMETRY_DISABLED=1 mineru telemetry disable
mineru config set parse_server.local.mode managed
