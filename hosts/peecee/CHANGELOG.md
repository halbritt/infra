# Changelog — peecee

Machine-level changes for `peecee`, newest first. The exporter README and its Git
history contain the original 2026-06-20 deployment record.

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
