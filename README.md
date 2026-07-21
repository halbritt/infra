# peecee

Whole-system provenance / desired-state for the host **peecee** — a Windows GPU
node in the local-first AI fleet. One repo per host (mirrors `halbritt/proximal`);
one directory per subsystem. Values and desired-state, never credentials.

## This box

- **Host:** `peecee` · Windows 11 Pro · user `halbr` (SSH from proximal:
  `ssh peecee`, key auth, elevated admin session)
- **GPU:** NVIDIA **RTX 3090 Ti, 24 GiB**
- **LAN:** `192.168.1.118` · **Tailscale:** `100.113.63.58` (tailnet `peecee`)
- **Role:** GPU fleet node (see `halbritt/gpu-fleet`). Serves LLM inference via
  Ollama; a second GPU independent of proximal's 3090 (which is pinned by
  `llama-27b`). Candidate host for offloaded batch inference and (future) GPU
  document conversion (marker/surya).

## Ollama — headless server (the primary service)

Ollama runs as a **headless server**, not the desktop tray app. Swapped
2026-06-20 (`ollama/install-ollama-service.ps1`):

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
- **Models:** `C:\Users\halbr\.ollama\models` (qwen3-vl 8b / 32b, qwen3.6 27b /
  35b-a3b / latest, llama3, llama2-uncensored). Set via machine env `OLLAMA_MODELS`
  so the SYSTEM account finds the existing user store.
- **GPU:** confirmed working under SYSTEM (`ollama ps` → `100% GPU`).
- **KV-cache quant (2026-06-22):** `OLLAMA_KV_CACHE_TYPE=q8_0` + `OLLAMA_FLASH_ATTENTION=1`
  (the quant silently no-ops without flash attn). Halves KV memory so a large model
  stays fully resident at long context.
- **Intended resident model (2026-07-21): `qwen3-vl:8b`** — restored by owner
  request (gpu-fleet migration `013_peecee_qwen3_vl_return.sql`) after a
  same-day owner-directed detour to the dense `qwen3.6:27b` (migration 012;
  ran resident `17 GB / 100% GPU / 32768 / Forever` for a few hours). Verified
  post-restore via `ollama ps`: `7.5 GB / 100% GPU / 32768 / Forever`. The
  2026-07-08 entry below remains the governing rationale:
- Fit-rule selection (2026-07-08): `qwen3-vl:8b` — the fleet's first
  vision-language capability, swapped in from the dense `qwen3.6:27b` under the
  gpu-fleet contract `peecee-serves-qwen3-vl@1` (migration `011_peecee_qwen3_vl.sql`).
  The fit rule prefers Qwen3-VL-32B **iff** it stays 100% GPU-resident at the 32768
  context floor, else the 8B. Measured 2026-07-07 on this card (marker idle):
  `qwen3-vl:32b` at 32768 spills to `7%/93% CPU/GPU` (25 GB demand) — **fails** the
  residency gate; `qwen3-vl:8b` at 32768 is `100% GPU`, 8.0 GB (`ollama ps`
  confirmed post-swap: `8.0 GB / 100% GPU / 32768 / Forever`), ~131 tok/s. So **8B
  is the intended resident model** — do NOT advertise the 32B at the 32768 floor
  (won't stay resident on a display-shared 24 GB card), and do not shrink context to
  make it fit. Historical: the dense Q4_K_M `qwen3.6:27b` (~17 GB, verified
  `num_ctx=32768`, KV `1088 MiB`, ~18.9 GB used / ~5.4 GB free, `100% GPU`) was the
  prior resident model here before this swap.
- **Keep-alive:** machine env `OLLAMA_KEEP_ALIVE=-1` (models never unload — pins
  the loaded model's VRAM). ⚠️ For GPU co-tenancy with marker/surya, `marker/convert.ps1`
  issues `ollama stop` to free VRAM per job.

Machine env set by the installer: `OLLAMA_HOST=0.0.0.0:11434`,
`OLLAMA_MODELS=C:\Users\halbr\.ollama\models`, `OLLAMA_KEEP_ALIVE=-1`,
`OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_FLASH_ATTENTION=1`.

### Operate

```powershell
# status / restart (run on peecee, elevated)
Get-ScheduledTask OllamaServer ; ollama ps
Stop-ScheduledTask  OllamaServer ; Start-ScheduledTask OllamaServer

# health (from proximal)
curl -s http://peecee:11434/api/tags
```

- **Apply / re-apply:** `ollama/install-ollama-service.ps1` (idempotent, elevated).
- **Roll back to the desktop app:** `ollama/uninstall-ollama-service.ps1`.

## Marker — batch GPU document conversion

peecee is the fleet's **batch** node for document conversion: marker (surya models)
converts PDF/image/office files to markdown/JSON on the 3090 Ti, keeping proximal's
**interactive** llama-server untouched. Installed 2026-06-20
(`marker/install-marker.ps1`):

- **Install:** uv-managed venv at `C:\Users\halbr\marker\.venv` (Python 3.12),
  `marker-pdf` + CUDA torch (`torch 2.12.1+cu130`, matches driver 610). Surya models
  cache under `%LOCALAPPDATA%\datalab`.
- **Run (on peecee):** `marker/convert.ps1 -Source <file> [-Format markdown|json|html|chunks]`.
  It **frees VRAM first** (`ollama stop` on any resident model) so surya fits on the
  24 GiB card, then converts on the GPU. ollama reloads on its next request.
- **Run (from proximal):** the `marker-convert` skill's
  `scripts/convert-peecee.sh <file>` uploads, runs `convert.ps1` here, and pulls the
  result back — proximal's interactive LLM is never touched.
- **Speed:** ~2.4 s GPU conversion for a 1-page doc (vs ~28 s on proximal CPU);
  first ever run also downloads the surya models.

The GPU is single-tenant: marker and a resident ollama model cannot both hold the
24 GiB at once, so `convert.ps1` unloads ollama for the duration. This is the
proximal-interactive / peecee-batch split: heavy document jobs run here, chat stays
on proximal.

## GPU driver (rolled back 2026-07-20)

- **Installed: GeForce 596.49** (WMI `32.0.15.9649`), silent clean install
  (`nv-596.49.exe -s -clean -noreboot` over SSH) after the 610.62 (R610-branch)
  driver bugchecked (0x1E in `nvlddmkm.sys`; R610 has widespread crash reports).
  Stay off R610 until it matures; installer kept at `C:\Users\halbr\Downloads\`.
- **NVIDIA App uninstalled** (driver-only box; removed via
  `RunDll32 NVI2.DLL,UninstallPackage Display.NvApp -silent`).
- **Power tweaks:** PCIe Link State Power Management = Off (AC+DC, active plan)
  and Fast Startup disabled (`HiberbootEnabled=0`) — both documented nvlddmkm
  triggers.
- **Known-benign-ish residual:** a handful of WHEA ID 17 *corrected* PCIe errors
  at each boot on PCH root port `0:1D.4`, whose child is a **Samsung NVMe SSD**
  (`VEN_144D&DEV_A80A`) — not the GPU. Watched by `health/check-whea.sh`; if
  counts grow between boots, suspect the SSD link (ASPM/seating), not the driver.

## Fleet integration (`halbritt/gpu-fleet`)

peecee is a fleet node addressed by capability via the `gpu_slots` heartbeat table.
Today proximal heartbeats peecee on its behalf. Now that Ollama is a headless
boot-start server, peecee can **self-heartbeat** via its own scheduled task — the
gpu-fleet roadmap's "scheduled task (Windows)" item. (Not yet wired; the
`OllamaServer` task is the template.)

## Subsystems

- `ollama/` — the Ollama headless-server desired-state + install/rollback scripts.
- `marker/` — marker-pdf GPU document conversion: `install-marker.ps1` (uv venv +
  CUDA torch) and `convert.ps1` (VRAM-freeing GPU runner). Proximal-side caller is
  `marker-convert/scripts/convert-peecee.sh` in `halbritt/skills`.
- `health/` — `check-whea.sh`, a proximal-side cron probe (`*/30` in halbritt's
  crontab) counting WHEA-Logger events since boot. Added after the 2026-07-20
  bugcheck (0x1E, `nvlddmkm.sys`, NVIDIA driver 610.62) that followed a storm of
  WHEA ID 17 corrected PCIe errors. Logs to `~/.local/state/peecee-whea/whea.log`
  on proximal; a non-zero count writes an `ALERT` marker file next to it.
