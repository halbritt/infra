# proximal/whisper — whisper.cpp STT server + Praxis shim

Desired-state + provenance for the **speech-to-text path** on host **proximal**: the
`whisper/` subsystem of the [`proximal`](../README.md) whole-system repo. Captured 2026-07-20.

Two system units form Praxis's live STT pipeline (audio stays on-box, Praxis invariant I4 —
both services are **loopback-only**):

1. **`whisper-stt.service`** — whisper.cpp `whisper-server` on `:8910`, GGML `small.en` on the
   **GPU** (~0.95 GiB VRAM). Speaks multipart `/inference`, returns `verbose_json` with
   per-word probabilities.
2. **`praxis-stt-shim.service`** — a stdlib-only Python shim on `:8082` translating Praxis's
   `LiveWhisperSTT` contract (raw `application/octet-stream` in → `{text, confidence}` out) to
   whisper-server's multipart API. Confidence is **real**: mean per-word probability (the A5
   confidence floor routes on it; no faked constant). On internal failure it returns an empty,
   zero-confidence result so Praxis degrades to "ask, don't assert" rather than crashing.

Praxis consumes it via `PRAXIS_STT_URL=http://127.0.0.1:8082/transcribe`.

## At a glance

| | |
|---|---|
| binary | `~/git/whisper.cpp/build/bin/whisper-server` |
| model | `~/git/whisper.cpp/models/ggml-small.en.bin` (~488 MB on disk, ~0.95 GiB VRAM) |
| units | `whisper-stt.service`, `praxis-stt-shim.service` (system, `User=halbritt`, `Restart=on-failure`) |
| ports | `127.0.0.1:8910` (whisper-server) · `127.0.0.1:8082` (shim) — loopback only |
| shim env | `WHISPER_SERVER=http://127.0.0.1:8910` · `PRAXIS_STT_SHIM_PORT=8082` (set in the unit) |

⚠️ **Shares the RTX 3090 with `llama-27b`** (see [`../llama/`](../llama/), ~23 GiB pinned) —
`small.en` leaves ~2.4 GiB free; a larger whisper model risks starving the LLM. To swap models,
change the unit's `-m` flag; other sizes need a
`~/git/whisper.cpp/models/download-ggml-model.sh <name>` first.

## Files → install locations

| repo file | install path |
|---|---|
| `whisper-stt.service` | `/etc/systemd/system/whisper-stt.service` |
| `praxis-stt-shim.service` | `/etc/systemd/system/praxis-stt-shim.service` |
| `praxis-stt-shim.py` | `/home/halbritt/git/whisper.cpp/praxis-stt-shim.py` |

The shim script is **untracked** in the upstream `whisper.cpp` clone (local addition), so the
copy here is its only versioned home — edit here, re-install there.

After editing units: `sudo systemctl daemon-reload && sudo systemctl restart whisper-stt praxis-stt-shim`.

## Manage

```bash
systemctl status whisper-stt praxis-stt-shim
sudo systemctl restart whisper-stt praxis-stt-shim
journalctl -u whisper-stt -f
journalctl -u praxis-stt-shim -f
curl -s -o /dev/null -w '%{http_code}\n' localhost:8910/   # whisper-server up → 200
curl -s -o /dev/null -w '%{http_code}\n' localhost:8082/   # shim up → 200
# end-to-end smoke test (any wav/pcm file):
curl -s -X POST --data-binary @sample.wav -H 'Content-Type: application/octet-stream' \
  localhost:8082/transcribe | jq   # → {"text": "...", "confidence": 0.9x}
```

**Values, never credentials** — no secrets anywhere in this path; loopback-only binding is the
whole security posture (audio never leaves the box).
