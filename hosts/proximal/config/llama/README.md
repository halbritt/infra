# proximal/llama — llama.cpp inference service (`llama-27b.service`)

Desired-state + provenance for the **primary local LLM endpoint** on host **proximal**.
The `llama/` subsystem of the [`proximal`](../README.md) whole-system repo. Captured 2026-07-20;
current serving constraints updated 2026-08-18.

This is the box's main inference service: mainline `llama.cpp` `llama-server`, OpenAI-compatible
at **`:8081`**. The unit name `llama-27b` is historical — since 2026-06 a drop-in override
served **Qwen3.6-35B-A3B (APEX MoE, ~3B active)**; as of **2026-08-14** the override serves
**Qwen3.8-27B (dense, Q5_K_M)** after a clean before/after eval (see "Why Qwen3.8-27B"). The
RTX 3090 (24 GiB) is ~fully pinned by this service. Full-speed serving requires unloading
whisper.cpp and Ollama GPU residents first; see "Strict GPU residency" below.

## At a glance

| | |
|---|---|
| build | mainline llama.cpp `10210 (000547513)` — `~/git/llama.cpp/build/bin/llama-server` |
| unit | `llama-27b.service` (system, `User=halbritt`, `Restart=on-failure`) + drop-in override |
| endpoint | `http://0.0.0.0:8081/v1` (OpenAI-compatible) — reachable on LAN/tailnet, **no API key** |
| model (live) | `~/models/qwen3.8-27b/Qwen3.8-27B-UD-Q4_K_M.gguf` (~15.3 GiB, unsloth UD), alias `qwen3.8-27b` |
| context | 131072 tokens · `-np 1` (one full-context slot) · flash-attn · q8_0 KV cache |
| GPU residency | `-ngl all -ngld all --fit off` · main and MTP draft layers must fit or startup fails |
| sampler | `temp 0.6 / top-p 0.95 / top-k 20 / min-p 0.0` · `--jinja` |
| speculative | `--spec-type draft-mtp` (3.8-27B carries `qwen35.nextn_predict_layers` MTP tensors) |

⚠️ **Reasoning model** — it emits `reasoning_content` (thinking) before `content`. Give it
generous `max_tokens` or short prompts finish (`finish_reason: length`) with empty `content`.
Suppress thinking per-request with `chat_template_kwargs={"enable_thinking": false}` (verified
working on this model 2026-08-14). llama-server **ignores the request `model` field** (single
loaded model), so callers still passing old names (`qwen3.6-27b`, `qwen3.6-35b-a3b`) keep working.

## Stock unit vs. the override (history)

- **`llama-27b.service`** (stock): Qwen3.6-27B dense (`Qwen3.6-27B-IQ4_XS.gguf`, ~15.7 GiB) at
  196608 ctx **with MTP speculative decoding** (`--spec-type draft-mtp`, draft acceptance
  ~0.8–1.0 — the IQ4_XS file carries the MTP `nextn` tensors on blk.64), alias `qwen3.6-27b`.
- **`override.conf`** (the live config): empties `ExecStart=` and replaces it with
  **Qwen3.8-27B dense (UD-Q4_K_M)** at 131072 ctx with MTP draft and strict all-layer GPU
  placement (Q5_K_M at 65536 from 2026-08-14 to 2026-08-20; prior config saved on-box as
  `override.pre-q4km-ctx-20260820`). Originally swapped in 2026-08-14 from the
  prior **Qwen3.6-35B-A3B APEX MoE + Striatum-FT LoRA** config (which ran 262144 ctx, no MTP
  draft). See "Why Qwen3.8-27B" below for the decision.

**Revert to stock 27B** (recorded verbatim from `~/CLAUDE.md`):

```bash
sudo rm -r /etc/systemd/system/llama-27b.service.d && sudo systemctl daemon-reload && sudo systemctl restart llama-27b
```

**Revert to the 35B-A3B MoE** (previous live config): copy the on-box
`/etc/systemd/system/llama-27b.service.d/override.pre-qwen3.8-20260814` back over
`override.conf`, `daemon-reload`, restart. (The Striatum-FT LoRA lives behind a symlink under
`~/models/Qwen3.6-35B-A3B-Striatum-FT/` — do not delete its target while the unit loads it.)

## Why Qwen3.8-27B (2026-08-14)

Replaced the 35B-A3B MoE with the dense Qwen3.8-27B after a clean before/after eval against
**Qwen3.6-27B** (the true same-size predecessor), both at **Q5_K_M** quant, same corpus
(wikitext-2 test), same hardware (RTX 3090, `-ngl 99`):

| metric | Qwen3.6-27B Q5_K_M | Qwen3.8-27B Q5_K_M | Δ |
|---|---|---|---|
| perplexity (wikitext-2 test) | 8.493 ± 0.068 | 6.232 ± 0.039 | **−26.6%** |
| prompt processing (pp512) | 1335 t/s | 1357 t/s | +1.6% |
| token generation (tg128) | 37.2 t/s | 35.9 t/s | −3.4% |

Lower perplexity = better language modeling; the ~27% drop is a large single-point-release gain,
and throughput is a wash. Raw logs: `~/git/qwen-eval/results/{qwen3.6-27b,qwen3.8-27b}-ppl.log`;
corpus at `~/git/qwen-eval/corpus/wikitext-2-test.txt` (built from `Salesforce/wikitext`
`wikitext-2-raw-v1` test split). Note this compares 3.6→3.8 (27B vs 27B), not against the 35B
MoE the box had been serving — the 35B was a MoE-throughput choice for the long-context backfill,
not a quality ceiling, and the 27B dense wins on quality per the eval.

The model transition initially dropped context from 262144 to 196608 because a dense 27B + q8_0
KV cache at 262k would exceed the 24 GiB card. The 2026-08-18 serving incident showed that
196608 with automatic fitting was not a safe operational setting: the observed chair workload
decoded at 8.317 tokens/s (a later long run averaged about 7.6), processed its prompt at 13.870
tokens/s, held about 21.1 GiB on the GPU, mapped another 6.57 GiB on the host, and had about
4.9 GiB swapped.

### Strict GPU residency (2026-08-18)

After unloading whisper.cpp and Ollama GPU residents and reducing context to 65536, the same
service reached 63.957 generation tokens/s and 181.646 prompt tokens/s. A second launch with the
exact durable flags now in `override.conf` — `-c 65536 -ngl all -ngld all --fit off` — reached
64.181 generation tokens/s and 137.200 prompt tokens/s, accepted 35 of 42 MTP draft tokens, and
used 22.676 GiB of GPU memory.

The all-layer flags cover both the main model and its embedded MTP draft. `--fit off` is a
fail-closed resource policy: if another process has consumed the required VRAM, llama-server
must fail to load rather than silently shrink or move work to CPU. Keep whisper.cpp and Ollama
GPU models unloaded while this service is active. If a workload needs more than 131072 tokens,
select a smaller model/KV quant or explicitly re-benchmark a larger context; do not re-enable
automatic fitting as an implicit fallback.

### Q4_K_M at 131072 (2026-08-20)

The Council `qwen-chair` turn on the long `quartermaster` topic measured ~85k tokens of
rendered input and could not fit the 65536 slot (`provider_http_error` on every chair
dispatch). Swapped the weights Q5_K_M (~19.3 GiB) → unsloth **UD-Q4_K_M** (~15.3 GiB) and
doubled context to **131072**, keeping q8_0 KV, `--fit off`, and all-layer residency. Loads
resident at ~21.6 GiB of 24 GiB (≈3 GiB headroom); the UD quant retains the
`qwen35.nextn_predict_layers` MTP tensors and the draft context initializes. Validated the
same day by a successful ~90k-token chair turn on `quartermaster`. Throughput at long
context is not yet benchmarked to the 2026-08-18 standard; generation smoke-tested only.
No Qwen3.8 MoE exists as of 2026-08-20 (the 3.8 generation is dense 27B + closed Max; the
MoE line remains Qwen3.6-35B-A3B, still on disk).

## Files → install locations

| repo file | install path |
|---|---|
| `llama-27b.service` | `/etc/systemd/system/llama-27b.service` (stock 27B+MTP config) |
| `llama-27b.service.d/override.conf` | `/etc/systemd/system/llama-27b.service.d/override.conf` (live 3.8-27B config) |

## Archived models

Other model/quants are **archived on the spinning disk** at `/nvr/models-archive/` (moved
2026-08-04 to relieve root-FS pressure). Archived: Qwen3.6-27B Q5_K_M, Qwen3.6-27B IQ4_XS,
Qwen3.6-27B MTP Q4_K_M, Qwen3.6-35B-A3B (MoE) IQ4_XS, the raw bf16 build source (`hf/`), the
gemma-4 models, and the Qwen3 0.6B/1.7B draft quants. The only models that live in `~/models/`
are the ones actually in service: the live `Qwen3.8-27B-Q5_K_M.gguf`, plus the still-on-box
`Qwen3.6-35B-A3B-APEX-I-Compact.gguf` and its Striatum-FT LoRA symlink (kept for the revert path
above).

⚠️ `Qwen3.6-27B-MTP-IQ4_KS.gguf` (also archived) is an **ik_llama.cpp quant** (ggml types
#144/#152) — mainline llama-server cannot load it; it belongs to the `ik-llama-server` user unit
/ `~/git/ik_llama.cpp` build. Never point this unit at it.

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
  -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"hi"}],"max_tokens":256,"chat_template_kwargs":{"enable_thinking":false}}' \
  | jq -r '.choices[0].message.content'
```

⚠️ **Do not take `:8081` down casually** — it is the standing inference endpoint for local agents
(opencode, Praxis, skill-mining). Restarts are fine; leaving it stopped is not.

**Values, never credentials** — the server runs keyless on purpose (LAN/tailnet trust boundary);
nothing secret lives in the unit or this directory.
