# Changelog — peecee

Machine-level changes for `peecee`, newest first. The exporter README and its Git
history contain the original 2026-06-20 deployment record.

## 2026-09-23 — Kev classifier service; ollama resident model back to qwen3-vl:8b

Owner-directed (option "2" of the VRAM tradeoff in
`showerthoughts/jev/research/tiny-model-benchmark-2026-09-22.md`).

- Unloaded the drifted resident `qwen3.6:27b` (16 GB, ctx 4096) and loaded
  `qwen3-vl:8b` at `num_ctx` 32768 with keep-alive forever, converging the box on
  gpu-fleet migration 013's advertised slot-0 state. No fleet migration needed.
- Installed Kev (`jaredpalmer/kev` @ `557598f`, torch 2.8.0+cu128, triton-windows,
  flash-linear-attention 0.5.2) under `C:\Users\halbr\kev` via the one-shot task
  `KevInstall`, and registered `KevServer` (user, S4U, AtStartup, restart x3) serving
  `kev-4b` bf16 with the adapter unmerged on `0.0.0.0:8008`. New subsystem
  `config/kev/` holds the installer, both task wrappers, the bind shim and a README
  with the serving contract and five Windows gotchas (SSH kills the process tree;
  PS 5.1 Stop preference vs. redirected stderr; cmd quote stripping; DOMAIN\user
  SID mapping; uv venv refuses overwrite).
- Verified from proximal: `/v1/models` reports cuda/bfloat16; the 64-row benchmark
  matches the proximal run (risk 0.83, irreversible 0.88, network 0.92) at 439 ms p50.
- Not changed: ollama task, marker, exporter, firewall. Card is now full (~0.7 GB free
  with the desktop open); marker jobs must stop `KevServer` first.

## 2026-08-11

### GPU exporter made independent of Tailscale service restarts

A Tailscale 1.102.2 MSI update on 2026-08-08 cleanly stopped the
`nvidia_gpu_exporter` service because it declared `depend=Tailscale`. Clean SCM
stops do not activate WinSW failure recovery, and the updater did not restart
the dependent service, leaving Prometheus blind until the exporter was restored
on 2026-08-10 local time.

Removed the hard service dependency and made delayed automatic startup explicit.
The existing 5-second restart-on-failure action, tailnet-only listener, and
tailnet-scoped firewall remain unchanged. This preserves boot-race recovery while
allowing Tailscale upgrades and restarts without stopping the exporter.

Reinstalled the live WinSW service definition and verified delayed automatic
startup, no Tailscale dependency, and the 5-second recovery action. A controlled
exporter child-process termination restarted it with a new PID; its metrics and
the Prometheus `gpu/peecee` target returned healthy.

## 2026-08-05

### Standalone peecee repository imported with history

Imported all 15 commits from `github.com/halbritt/peecee` `main` at
`8bc7435470026341bf547de3da5bd0f654db464b` using an unsquashed subtree merge.
Normalized its Ollama, Marker, and WHEA content under `config/` without changing
the Windows machine. Reconciled its root instructions and operating notes with
the existing fleet host record.

Read-only SSH verification confirmed the Windows host, GPU, Ollama task,
exporter service, and Marker installation were reachable. It also showed that
the currently loaded model differs from the 2026-07-21 repository observation;
the current state is recorded in `notes.md` without treating it as new desired
state.

Updated proximal's WHEA cron entry and the Marker skill's maintenance reference
to the fleet paths after the normalization.

### Existing Windows GPU exporter assigned to its owning host

Moved the already-versioned `nvidia_gpu_exporter` WinSW configuration from the
`proximal` observability subtree to `hosts/peecee/config/nvidia-gpu-exporter/`.
Updated `proximal`'s consumer references. No Windows service, firewall rule,
address, executable, or credential changed, and no live Windows action was
performed.
