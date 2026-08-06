# proximal/ollama — Ollama inference service

Desired-state + provenance for the **Ollama** service on host **proximal**. The `ollama/`
subsystem of the [`proximal`](../README.md) whole-system repo. Captured 2026-06-19.

Ollama is the **secondary** local inference endpoint on this box. The primary is mainline
`llama.cpp` (`llama-27b.service`, OpenAI-compatible at `:8081`, serving Qwen3.6-35B-A3B — see
`~/CLAUDE.md`). Both share the single **RTX 3090 (24 GiB)**, so Ollama is used for the few
models below, not as a general always-loaded server.

## At a glance

| | |
|---|---|
| version | `0.9.5` |
| endpoint | `http://127.0.0.1:11434` — **loopback only** (not on LAN/tailnet) |
| unit | `ollama.service` (`User=ollama`, `Restart=always`); `WantedBy=default.target` |
| binary | `/usr/local/bin/ollama` |
| models dir | `/usr/share/ollama/.ollama/models` (~8.9 GiB) |

## Configuration

Stock unit + a tuning **drop-in** (`/etc/systemd/system/ollama.service.d/override.conf`):

| env | value | why |
|---|---|---|
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | quantized KV cache — less VRAM, room to coexist with llama.cpp |
| `OLLAMA_CONTEXT_LENGTH` | `32768` | default context window |
| `OLLAMA_FLASH_ATTENTION` | `1` | flash attention on |
| `OLLAMA_KEEP_ALIVE` | `-1` | keep a loaded model resident (no unload timeout) once requested |

> Note `KEEP_ALIVE=-1` + a 24 GiB card shared with the llama.cpp server (~23 GiB pinned): a
> loaded Ollama model stays resident until the service restarts or another model is pulled in.

Production callers must therefore request only models whose indefinite
residency is intentional. `memory-price-tracker-ingest.service` uses peecee
Ollama as its primary sentiment endpoint and the already-resident proximal
llama.cpp server as fallback. It does not use proximal `qwen3:14b`; its
canonical drop-in lives in the memory-price-tracker repository under
`systemd/memory-price-tracker-ingest.service.d/`.

## Models on disk

| name | size |
|---|---|
| `qwen3:14b` | 9.3 GB |
| `nomic-embed-text:latest` | 274 MB |

`qwen3:14b` remains available on disk but is not intended to stay resident.
`nomic-embed-text:latest` is the intended resident Ollama workload.

## Files → install locations

| repo file | install path |
|---|---|
| `ollama.service` | `/etc/systemd/system/ollama.service` (stock upstream unit) |
| `override.conf` | `/etc/systemd/system/ollama.service.d/override.conf` (the tuning) |

## Manage

```bash
systemctl status ollama
sudo systemctl restart ollama
journalctl -u ollama -f
ollama list                              # models on disk
curl -s localhost:11434/api/tags | jq    # models via API
```

**Values, never credentials** — Ollama needs no secrets here; this captures the unit + tuning
only. If exposure is ever widened beyond loopback, set `OLLAMA_HOST` in the drop-in (bind the
tailnet IP `100.85.100.81`, never `0.0.0.0` — no host firewall) and record it here.
