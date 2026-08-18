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

⚠️ **Time-shares the RTX 3090 with `llama-27b`** (see [`../llama/`](../llama/)). The
LLM's current strict-GPU configuration uses 22.676 GiB in its measured chair workload and must
run without a resident whisper model for its verified full-speed profile. Stop `whisper-stt`
before starting that workload; the separate CPU-only Praxis shim can remain active. The fleet
lease protects fleet-routed requests, but a caller using `:8081` directly bypasses that routing
guard. To swap whisper models, change the unit's `-m` flag; other sizes need a
`~/git/whisper.cpp/models/download-ggml-model.sh <name>` first.

## Files → install locations

| repo file | install path |
|---|---|
| `whisper-stt.service` | `/etc/systemd/system/whisper-stt.service` |
| `praxis-stt-shim.service` | `/etc/systemd/system/praxis-stt-shim.service` |
| `praxis-stt-shim.py` | `/home/halbritt/git/whisper.cpp/praxis-stt-shim.py` |
| `whisper-stt.service.d/gpu-fleet-lease.conf` | `/etc/systemd/system/whisper-stt.service.d/gpu-fleet-lease.conf` |
| `whisper-stt-lease-renew.service` | `/etc/systemd/system/whisper-stt-lease-renew.service` |

## gpu-fleet lease onboarding (2026-07-20, gpu-fleet RFC 0006 / Plane GPUFLE-1)

whisper-stt is a **standing exclusive lease-holder** in the gpu-fleet registry: while STT
is hot it holds the RFC 0001 lease on proximal's llama slot row
(`gpu_slots` · `proximal / http://localhost:8081/v1 / 0`), so fleet `pick`/claim derive
the shared 3090 below routable and skip it — the whisper-vs-llama OOM collision is now a
scheduling skip in both directions (a whisper start under a live fleet lease defers with
exit 75 until it drains; `StartLimitIntervalSec=0` keeps systemd retrying).

Wiring (both files versioned here AND in `~/git/gpu-fleet/systemd/`, logic in
`~/git/gpu-fleet/whisper_lease.py`):

- **`whisper-stt.service.d/gpu-fleet-lease.conf`** — drop-in: `ExecStartPre` acquires,
  `ExecStopPost` releases (fenced, never blocks the stop path).
- **`whisper-stt-lease-renew.service`** — companion renew loop (`BindsTo=whisper-stt`,
  enabled into `whisper-stt.service.wants/`), renews every 15 s (45 s TTL) and restores
  coverage after any gap. It never kills whisper-stt.
- Registry dark / slot not offerable → whisper starts **without** a lease (degrade open,
  loud journal line): Praxis voice intake is never hostage to Postgres, and fleet
  consumers can only be scheduled through that same registry anyway.
- Lease state handoff file: `~/.local/state/gpu-fleet/whisper-stt-lease.json`.

After editing: `sudo systemctl daemon-reload && sudo systemctl enable whisper-stt-lease-renew && sudo systemctl restart whisper-stt`.
Check: `psql -d gpu_fleet -c "SELECT lease_holder, lease_expires FROM gpu_slots WHERE node='proximal'"`
(expect `whisper-stt/proximal` with a future expiry while STT runs) and
`journalctl -u whisper-stt-lease-renew -f` for `coverage:` transitions.

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
