# proximal/llama — llama.cpp inference service (`llama-27b.service`)

Desired-state + provenance for the **primary local LLM endpoint** on host **proximal**.
The `llama/` subsystem of the [`proximal`](../README.md) whole-system repo. Captured 2026-07-20.

This is the box's main inference service: mainline `llama.cpp` `llama-server`, OpenAI-compatible
at **`:8081`**. The unit name `llama-27b` is historical — since the 2026-06 skill-mining backfill
a drop-in override serves **Qwen3.6-35B-A3B (APEX MoE, ~3B active)** instead of the stock 27B
dense model. The RTX 3090 (24 GiB) is ~fully pinned by this service (shares the card only with
the small whisper.cpp model, see [`../whisper/`](../whisper/)).

## At a glance

| | |
|---|---|
| build | mainline llama.cpp `9586 (76da2450a)` — `~/git/llama.cpp/build/bin/llama-server` |
| unit | `llama-27b.service` (system, `User=halbritt`, `Restart=on-failure`) + drop-in override |
| endpoint | `http://0.0.0.0:8081/v1` (OpenAI-compatible) — reachable on LAN/tailnet, **no API key** |
| model (live) | `~/models/Qwen3.6-35B-A3B-APEX-I-Compact.gguf` (~16 GiB), alias `qwen3.6-35b-a3b` |
| context | 262144 tokens · `-np 1` (one full-context slot) · flash-attn · q8_0 KV cache |
| sampler | `temp 0.6 / top-p 0.95 / top-k 20 / min-p 0.0` · `--jinja` |

⚠️ **Reasoning model** — it emits `reasoning_content` (thinking) before `content`. Give it
generous `max_tokens` or short prompts finish (`finish_reason: length`) with empty `content`.
llama-server **ignores the request `model` field** (single loaded model), so callers still
passing the old `qwen3.6-27b` name keep working.

## Stock unit vs. the 35B override

- **`llama-27b.service`** (stock): Qwen3.6-27B dense (`Qwen3.6-27B-IQ4_XS.gguf`, ~15.7 GiB) at
  196608 ctx **with MTP speculative decoding** (`--spec-type draft-mtp`, draft acceptance
  ~0.8–1.0 — the IQ4_XS file carries the MTP `nextn` tensors on blk.64), alias `qwen3.6-27b`.
- **`override.conf`** (the live config): empties `ExecStart=` and replaces it with the
  **Qwen3.6-35B-A3B APEX MoE** at 262144 ctx. Chosen for MoE throughput on the skill-mining
  stage2 backfill (≫ 27B dense at long context) plus a full single-slot context for big stage2
  buckets — full rationale in `~/git/agent-artifact-miner/SPEC.md` → "Inference server & model
  choice". The 35B config runs **no MTP draft** and does not honor `enable_thinking:false`
  (both were stock-27B-only behaviors). Since 2026-07-20 (PROXIMAL-4) it also passes
  `--metrics`: Prometheus-compatible `/metrics` (`llamacpp:*` series) on the API port,
  scraped by the local Prometheus over loopback with down/queue-pressure alerts — see
  [`../observability/`](../observability/).

**Revert to stock 27B** (recorded verbatim from `~/CLAUDE.md`):

```bash
sudo rm -r /etc/systemd/system/llama-27b.service.d && sudo systemctl daemon-reload && sudo systemctl restart llama-27b
```

Other model/quants are **archived on the spinning disk** at `/nvr/models-archive/` (moved 2026-08-04 to relieve root-FS pressure — root was 89%, now ~60%). The only model files that live in `~/models/` are the ones actually in service:

- `~/models/Qwen3.6-35B-A3B-APEX-I-Compact.gguf` — **the live model** (served by the override).
- `~/models/Qwen3.6-35B-A3B-Striatum-FT/` — **symlink only** to the live LoRA adapter
  (`adapter-f32.gguf`), whose real file lives under the runpod-jobrunner artifacts.
  Do not delete the symlink or its target while the unit loads it.

Archived on `/nvr/models-archive/` (re-locatable / re-downloadable; swap back into `~/models/`
and point the unit's `-m` flag at them to use): Qwen3.6-27B Q5_K_M, Qwen3.6-27B IQ4_XS,
Qwen3.6-27B MTP Q4_K_M, Qwen3.6-35B-A3B (MoE) IQ4_XS, the raw bf16 build source (`hf/`), the
gemma-4 models, and the Qwen3 0.6B/1.7B draft quants — all mainline-loadable once restored.
⚠️ `Qwen3.6-27B-MTP-IQ4_KS.gguf` (also archived) is an **ik_llama.cpp quant** (ggml types
#144/#152) — mainline llama-server cannot load it; it belongs to the `ik-llama-server` user unit
/ `~/git/ik_llama.cpp` build. Never point this unit at it.

## Files → install locations

| repo file | install path |
|---|---|
| `llama-27b.service` | `/etc/systemd/system/llama-27b.service` (stock 27B+MTP config) |
| `llama-27b.service.d/override.conf` | `/etc/systemd/system/llama-27b.service.d/override.conf` (live 35B APEX config) |

After editing: `sudo systemctl daemon-reload && sudo systemctl restart llama-27b`.

## Manage

```bash
systemctl status llama-27b
sudo systemctl restart llama-27b
journalctl -u llama-27b -f
curl -s localhost:8081/health                          # {"status":"ok"}
curl -s localhost:8081/metrics | grep -c '^llamacpp:'  # 11 Prometheus series (--metrics)
curl -s localhost:8081/v1/models | jq '.data[].id'     # loaded model alias
curl -s localhost:8081/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.6-35b-a3b","messages":[{"role":"user","content":"hi"}],"max_tokens":256}' \
  | jq -r '.choices[0].message.content'
```

⚠️ **Do not take `:8081` down casually** — it is the standing inference endpoint for local agents
(opencode, Praxis, skill-mining). Restarts are fine; leaving it stopped is not.

**Values, never credentials** — the server runs keyless on purpose (LAN/tailnet trust boundary);
nothing secret lives in the unit or this directory.
