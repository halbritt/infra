#!/usr/bin/env bash
# CPU document inference alongside Proximal's resident GPU services.
set -euo pipefail

case "${1:-}" in
  marker|marker_single|surya_ocr|surya_layout|surya_table) tool="$1"; shift ;;
  *) echo 'usage: marker-local {marker|marker_single|surya_ocr|surya_layout|surya_table} [arguments...]' >&2; exit 2 ;;
esac

export CUDA_VISIBLE_DEVICES=''
export TORCH_DEVICE=cpu
export SURYA_INFERENCE_BACKEND=llamacpp
export LLAMA_CPP_BINARY="${LLAMA_CPP_BINARY:-$HOME/git/llama.cpp/build/bin/llama-server}"
export LLAMA_CPP_NGL=0
export LLAMA_CPP_NO_MMPROJ_OFFLOAD=true
export SURYA_INFERENCE_PARALLEL="${SURYA_INFERENCE_PARALLEL:-1}"
export SURYA_INFERENCE_CTX_PER_SLOT="${SURYA_INFERENCE_CTX_PER_SLOT:-24576}"

exec "${MARKER_VENV:-$HOME/git/marker/.venv}/bin/$tool" "$@"
