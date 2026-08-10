# peecee

Whole-system provenance and desired state for **peecee**, a Windows GPU node in
the local-first AI fleet. This host partition was imported from the standalone
`halbritt/peecee` repository on 2026-08-05 with its history intact. Values and
desired state belong here; credentials do not.

## This box

- **Host:** `peecee` · Windows 11 Pro build `26200` · user `halbr` (SSH from proximal:
  `ssh peecee`, key auth, elevated admin session)
- **GPU:** NVIDIA **RTX 3090 Ti, 24 GiB**
- **LAN:** `192.168.1.118` · **Tailscale:** `100.113.63.58` (tailnet `peecee`)
- **Role:** pull-observed GPU fleet node (see `halbritt/gpu-fleet`). Serves LLM
  inference through Ollama and batch document conversion through Marker; it is
  independent of proximal's interactive GPU.

## Ollama — headless server (the primary service)

Ollama runs as a **headless server**, not the desktop tray app. Swapped
2026-06-20 ([`config/ollama/install-ollama-service.ps1`](config/ollama/install-ollama-service.ps1)):

- **Run mode:** a Scheduled Task `OllamaServer` running `ollama serve` as
  **SYSTEM** (via a `C:\ProgramData\Ollama\run-ollama-serve.cmd` wrapper that
  redirects stdout+stderr to `C:\ProgramData\Ollama\server.log` — the bare SYSTEM
  serve has no console/logfile, so the wrapper is what makes the startup config +
  per-load KV-cache lines auditable). Trigger **At startup**, no time limit,
  auto-restart. Survives logout and reboot with no login session (the desktop
  `Ollama.lnk` startup shortcut is parked `.disabled`). gpu-fleet-sanctioned
  Windows approach ("scheduled task or service").
- **Endpoint:** `http://peecee:11434` (OpenAI-compatible at `/v1`), bound
  `0.0.0.0:11434` → reachable on LAN + tailnet. **Same port as the old desktop app.**
- **Models:** `C:\Users\halbr\.ollama\models`, selected through machine env
  `OLLAMA_MODELS` so the SYSTEM account finds the user store. A read-only
  `ollama list` on 2026-08-05 showed `qwen3-vl:32b`, `qwen3-vl:8b`, and
  `qwen3.6:27b`; inventory can change independently of this repository.
- **GPU:** confirmed working under SYSTEM (`ollama ps` → `100% GPU`).
- **KV-cache quant (2026-06-22):** `OLLAMA_KV_CACHE_TYPE=q8_0` + `OLLAMA_FLASH_ATTENTION=1`
  (the quant silently no-ops without flash attn). Halves KV memory so a large model
  stays fully resident at long context.
- **Historical resident decision (2026-07-21): `qwen3-vl:8b`** — restored by owner
  request (gpu-fleet migration `013_peecee_qwen3_vl_return.sql`) after a
  same-day owner-directed detour to the dense `qwen3.6:27b` (migration 012;
  ran resident `17 GB / 100% GPU / 32768 / Forever` for a few hours). Verified
  post-restore via `ollama ps`: `7.5 GB / 100% GPU / 32768 / Forever`. The
  following the 2026-07-08 fit-rule rationale:
- Fit-rule selection (2026-07-08): `qwen3-vl:8b` — the fleet's first
  vision-language capability, swapped in from the dense `qwen3.6:27b` under the
  gpu-fleet contract `peecee-serves-qwen3-vl@1` (migration `011_peecee_qwen3_vl.sql`).
  The fit rule prefers Qwen3-VL-32B **iff** it stays 100% GPU-resident at the 32768
  context floor, else the 8B. Measured 2026-07-07 on this card (marker idle):
  `qwen3-vl:32b` at 32768 spills to `7%/93% CPU/GPU` (25 GB demand) — **fails** the
  residency gate; `qwen3-vl:8b` at 32768 is `100% GPU`, 8.0 GB (`ollama ps`
  confirmed post-swap: `8.0 GB / 100% GPU / 32768 / Forever`), ~131 tok/s. The 8B
  was therefore selected instead of advertising the spilling 32B at that context
  floor. Historical: the dense Q4_K_M `qwen3.6:27b` (~17 GB, verified
  `num_ctx=32768`, KV `1088 MiB`, ~18.9 GB used / ~5.4 GB free, `100% GPU`) was the
  prior resident model here before this swap.
- **Keep-alive:** machine env `OLLAMA_KEEP_ALIVE=-1` (models never unload — pins
  the loaded model's VRAM). For GPU co-tenancy with Marker, [`convert.ps1`](config/marker/convert.ps1)
  issues `ollama stop` to free VRAM per job.

A read-only probe on 2026-08-05 instead observed `qwen3.6:27b` loaded at
`16 GB / 100% GPU / 4096 / Forever`. Loaded-model state is volatile and governed
by GPU-fleet placement and explicit owner direction; neither historical entry
is standing authority to change it.

Machine env set by the installer: `OLLAMA_HOST=0.0.0.0:11434`,
`OLLAMA_MODELS=C:\Users\halbr\.ollama\models`, `OLLAMA_KEEP_ALIVE=-1`,
`OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_FLASH_ATTENTION=1`.

### Operate

```powershell
# Run on peecee in an elevated shell.
Get-ScheduledTask OllamaServer ; ollama ps
Stop-ScheduledTask  OllamaServer ; Start-ScheduledTask OllamaServer
```

```bash
# Run from proximal.
curl -s http://peecee:11434/api/tags
```

- **Apply / re-apply:** [`config/ollama/install-ollama-service.ps1`](config/ollama/install-ollama-service.ps1)
  from an elevated shell.
- **Roll back to the desktop app:**
  [`config/ollama/uninstall-ollama-service.ps1`](config/ollama/uninstall-ollama-service.ps1).

## Marker — batch GPU document conversion

peecee is the fleet's **batch** node for document conversion: marker (surya models)
converts PDF/image/office files to markdown/JSON on the 3090 Ti, keeping proximal's
**interactive** llama-server untouched. Installed 2026-06-20
([`config/marker/install-marker.ps1`](config/marker/install-marker.ps1)):

- **Install:** uv-managed venv at `C:\Users\halbr\marker\.venv` (Python 3.12),
  `marker-pdf`, and a CUDA-capable Torch selected by `uv --torch-backend=auto`.
  Surya models cache under `%LOCALAPPDATA%\datalab`.
- **Run (on peecee):** `marker/convert.ps1 -Source <file> [-Format markdown|json|html|chunks]`.
  It **frees VRAM first** (`ollama stop` on any resident model) so surya fits on the
  24 GiB card, then converts on the GPU. ollama reloads on its next request.
- **Run (from proximal):** the `marker-convert` skill's
  `scripts/convert-peecee.sh <file>` uploads, runs `convert.ps1` here, and pulls the
  result back — proximal's interactive LLM is never touched.
- **Historical measurement (2026-06-20):** approximately 2.4 seconds for a
  one-page GPU conversion versus approximately 28 seconds on proximal CPU. This
  was a single recorded comparison, not a standing benchmark guarantee.

The GPU is single-tenant: marker and a resident ollama model cannot both hold the
24 GiB at once, so `convert.ps1` unloads ollama for the duration. This is the
proximal-interactive / peecee-batch split: heavy document jobs run here, chat stays
on proximal.

## GPU driver (rolled back 2026-07-20)

- **Installed: GeForce 596.49** (WMI `32.0.15.9649`), silent clean install
  (`nv-596.49.exe -s -clean -noreboot` over SSH) after the 610.62 (R610-branch)
  driver bugchecked (0x1E in `nvlddmkm.sys`). The 596.49 version was confirmed
  again by WMI on 2026-08-05. Installer location is
  `C:\Users\halbr\Downloads\`.
- **NVIDIA App uninstalled** (driver-only box; removed via
  `RunDll32 NVI2.DLL,UninstallPackage Display.NvApp -silent`).
- **Power tweaks:** PCIe Link State Power Management = Off (AC+DC, active plan)
  and Fast Startup disabled (`HiberbootEnabled=0`) — both documented nvlddmkm
  triggers.
- **Known-benign-ish residual:** a handful of WHEA ID 17 *corrected* PCIe errors
  at each boot on PCH root port `0:1D.4`, whose child is a **Samsung NVMe SSD**
  (`VEN_144D&DEV_A80A`) — not the GPU. Watched by [`check-whea.sh`](config/health/check-whea.sh); if
  counts grow between boots, suspect the SSD link (ASPM/seating), not the driver.

## Fleet integration (`halbritt/gpu-fleet`)

Peecee is addressed by capability through the `gpu_slots` registry. It is
pull-observed by design: peer-side code checks the node and records heartbeats.
Do not install fleet database credentials or self-heartbeat code on peecee.
`OllamaServer` is only the Ollama lifecycle task.

## Subsystems

- [`config/ollama/`](config/ollama/) — Ollama headless-server desired state and
  install/rollback scripts.
- [`config/ssh-client/`](config/ssh-client/) — proximal-side OpenSSH route for
  the `peecee` alias, pinned to the host's Tailscale address so stale LAN DNS
  cannot redirect fleet and maintenance traffic.
- [`config/marker/`](config/marker/) — Marker GPU document conversion: `install-marker.ps1` (uv venv +
  CUDA torch) and `convert.ps1` (VRAM-freeing GPU runner). Proximal-side caller is
  `marker-convert/scripts/convert-peecee.sh` in `halbritt/skillpack`.
- [`config/health/`](config/health/) — `check-whea.sh`, a proximal-side cron probe (`*/30` in halbritt's
  crontab) counting WHEA-Logger events since boot. Added after the 2026-07-20
  bugcheck (0x1E, `nvlddmkm.sys`, NVIDIA driver 610.62) that followed a storm of
  WHEA ID 17 corrected PCIe errors. Logs to `~/.local/state/peecee-whea/whea.log`
  on proximal; growth within one boot writes an `ALERT` marker file next to it.
- [`config/nvidia-gpu-exporter/`](config/nvidia-gpu-exporter/) — Windows exporter
  service consumed by proximal's Prometheus stack.
