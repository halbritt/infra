# Kev on peecee — local System One classifier

Kev ([jaredpalmer/kev](https://github.com/jaredpalmer/kev)) is a Qwen3.5-4B-Base backbone
with a LoRA adapter and a pointer head that answers typed questions (Choice / Score / Noul)
with calibrated probabilities over a System One–compatible HTTP API (`POST /v1/systemone`).
It is the local stand-in for the hosted jev classifier in the snap design
(`~/git/showerthoughts/jev/`), placed on peecee by owner direction on 2026-09-23 because
proximal's 3090 is fully committed to the 27B at 131k context.

Benchmark that selected it (balanced 64-command permission-gate set, agreement with jev,
majority baseline 0.30): risk 0.83, irreversible 0.89, reaches_network 0.92 at 133 ms per
three-question request on proximal's 3090; see
`showerthoughts/jev/research/tiny-model-benchmark-2026-09-22.md`.

## Files

- [`install-kev.ps1`](install-kev.ps1) — user-scope uv venv at `C:\Users\halbr\kev\.venv`
  with torch 2.8.0+cu128, triton-windows 3.4, flash-linear-attention 0.5.2 and kev pinned
  to commit `557598f` (installed from the GitHub source tarball; peecee has no git).
  Idempotent. Checks exit codes rather than using `$ErrorActionPreference = 'Stop'`
  (see gotchas).
- [`run-kev-install.cmd`](run-kev-install.cmd) — runs the installer under a one-shot
  scheduled task `KevInstall` with a combined log at `kev\logs\install.log`.
- [`kev-serve.py`](kev-serve.py) — `python -m kev.serve` with the bind address changed
  from the hard-coded 127.0.0.1 to `KEV_HOST` (0.0.0.0), so proximal reaches it on the
  tailnet. Run, port and cache dir come from `KEV_RUN`, `KEV_PORT`, `HF_HOME`.
- [`run-kev-serve.cmd`](run-kev-serve.cmd) — the `KevServer` task action: sets
  `HF_HOME=%USERPROFILE%\kev\hf`, `KEV_MERGE=0`, port 8008, and appends to
  `kev\logs\server.log`.
- [`install-kev-task.ps1`](install-kev-task.ps1) — registers `KevServer` (user `halbr`,
  S4U logon, AtStartup, no time limit, three restarts) and starts it.

## Serving contract

- Endpoint: `http://100.113.63.58:8008/v1/systemone` (tailnet) and `http://peecee:8008`
  on the LAN; `GET /v1/models` for the card. No API key (`KEV_API_KEY` unset), same
  exposure as ollama's `:11434`.
- Model: `jaredpalmer/kev-4b`, CUDA, bf16, **adapter unmerged** (`KEV_MERGE=0`). Kev's
  default merge path loads the base in fp32 and moves it to the GPU before merging, a
  16 GB peak that does not fit beside ollama and the desktop; the unmerged path loads
  bf16 directly. Kev documents the two as giving the same argmax on its checks.
- VRAM: ~8.5 GB resident. Co-tenant with ollama's `qwen3-vl:8b` (8 GB at 32768). The
  desktop itself holds a further 6–7 GB when the owner's usual apps are open, so the
  card is full: a third GPU tenant (marker, a larger ollama model) will not fit while
  Kev is up. `convert.ps1`'s `ollama stop` does not stop Kev; stop the `KevServer` task
  first for a marker job.
- gpu-fleet: Kev is not a fleet slot. Slot 0 (`ollama-ondemand`, `qwen3-vl:8b`) stays
  WARM-alive while the 8B is resident; if the 8B is ever unloaded, the COLD/LOADABLE
  check needs 21,000 MiB free, which Kev's residency prevents until the 8B reloads.

## Install or refresh

```bash
scp hosts/peecee/config/kev/{install-kev.ps1,run-kev-install.cmd,kev-serve.py,run-kev-serve.cmd,install-kev-task.ps1} peecee:kev/
ssh peecee 'Start-ScheduledTask KevInstall'          # first time: register it as in the CHANGELOG entry
ssh peecee 'Get-Content kev\logs\install.log -Tail 3'
ssh peecee 'powershell -NoProfile -ExecutionPolicy Bypass -File kev\install-kev-task.ps1'
```

Weights (~9 GB: base + adapter) download on the first serve into `kev\hf`.

## Operate

```bash
ssh peecee 'Get-ScheduledTask KevServer | Select State; Get-Content kev\logs\server.log -Tail 5'
ssh peecee 'Stop-ScheduledTask KevServer'   # frees ~8.5 GB VRAM
ssh peecee 'Start-ScheduledTask KevServer'
curl -s http://100.113.63.58:8008/v1/models | jq '.models[0].name'
```

## Windows gotchas met on 2026-09-23

- **Windows OpenSSH kills the process tree when the session closes**, `Start-Process`
  or not. Anything that must outlive the shell (installs, servers) runs under the Task
  Scheduler.
- **PowerShell 5.1 + `$ErrorActionPreference = 'Stop'` + redirected stderr**: a native
  tool's first stderr line (uv prints progress there) becomes a terminating error and the
  script dies silently after it.
- **`cmd /c "quoted exe" args > "log"`** strips the outer quotes and exits 1; put the
  command in a `.cmd` file and point the task at that.
- `New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME"` fails with "No
  mapping between account names and security IDs" on this box; the bare user name works.
- `uv venv` refuses to overwrite an existing venv (exit 2); the installer skips it.
