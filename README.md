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

- **Run mode:** a Scheduled Task `OllamaServer` running `ollama.exe serve` as
  **SYSTEM**, trigger **At startup**, no time limit, auto-restart. Survives logout
  and reboot with no login session (the desktop `Ollama.lnk` startup shortcut is
  parked as `.disabled`). This is the gpu-fleet-sanctioned Windows approach
  ("scheduled task or service").
- **Endpoint:** `http://peecee:11434` (OpenAI-compatible at `/v1`), bound
  `0.0.0.0:11434` → reachable on LAN + tailnet. **Same port as the old desktop app.**
- **Models:** `C:\Users\halbr\.ollama\models` (qwen3.6 27b / 35b-a3b / latest,
  llama3, llama2-uncensored). Set via machine env `OLLAMA_MODELS` so the SYSTEM
  account finds the existing user store.
- **GPU:** confirmed working under SYSTEM (`ollama ps` → `100% GPU`).
- **Keep-alive:** machine env `OLLAMA_KEEP_ALIVE=-1` (models never unload — pins
  ~22 GiB). ⚠️ For GPU co-tenancy with marker/surya on this box later, set this to
  e.g. `5m` so VRAM frees when idle.

Machine env set by the installer: `OLLAMA_HOST=0.0.0.0:11434`,
`OLLAMA_MODELS=C:\Users\halbr\.ollama\models`, `OLLAMA_KEEP_ALIVE=-1`.

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

## Fleet integration (`halbritt/gpu-fleet`)

peecee is a fleet node addressed by capability via the `gpu_slots` heartbeat table.
Today proximal heartbeats peecee on its behalf. Now that Ollama is a headless
boot-start server, peecee can **self-heartbeat** via its own scheduled task — the
gpu-fleet roadmap's "scheduled task (Windows)" item. (Not yet wired; the
`OllamaServer` task is the template.)

## Subsystems

- `ollama/` — the Ollama headless-server desired-state + install/rollback scripts.
