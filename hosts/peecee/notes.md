# peecee host notes

## Repository import

The standalone repository `github.com/halbritt/peecee` was imported without
squashing on 2026-08-05. Source `main` was clean and synchronized at
`8bc7435470026341bf547de3da5bd0f654db464b`; all 15 source commits are ancestors
of subtree import commit `aef5ed4d85c7249d76ce833108299b2a9ed2071e`.

The import first landed at `hosts/peecee/source-import/` to avoid overwriting the
partial host record, then a separate normalization moved its three subsystems
under `config/`. The temporary directory is not part of the final layout. The
standalone checkout remained unchanged during import. After its source tip and
clean state were reverified, `/home/halbritt/git/peecee` was moved to the desktop
trash on 2026-08-05. The checkout is recoverable from trash; the standalone
GitHub repository remains intact. This host partition is canonical for future
peecee desired-state changes.

A path-only heuristic scan of the source's current tree and reachable history
found no credential-like match or sensitive filename. No dedicated secret
scanner was installed, so this is bounded evidence rather than proof that the
history is secret-free.

## Ownership split

The Windows exporter service belongs to `peecee`. Its Prometheus scrape job,
alert rules, and dashboards remain under `hosts/proximal/` because proximal
operates the monitoring stack. The WHEA probe executes on proximal and reads
peecee over SSH. Ollama and Marker run on peecee.

GPU-fleet registry and placement policy remain external authority. Peecee is
pull-observed by design and must not receive fleet database credentials or
self-heartbeat code.

## Read-only live observation — 2026-08-05

A BatchMode SSH probe changed no Windows state and observed:

- Windows 11 Pro, build `26200`, on host `PEECEE`;
- NVIDIA GeForce RTX 3090 Ti, driver `32.0.15.9649`;
- `OllamaServer` Scheduled Task running and listening on port `11434`;
- `nvidia_gpu_exporter` running with automatic startup;
- Marker runner and virtual environment present under the user profile;
- `qwen3.6:27b` resident at that instant, 100% GPU, context `4096`, keep-alive
  `Forever`; and
- four WHEA events recorded since the current boot. The count alone is not an
  alert: `check-whea.sh` alerts only on growth within one boot.

Runtime observations can drift. They do not supersede GPU-fleet placement or
authorize a model change.

## GPU exporter recovery incident — 2026-08-08 to 2026-08-11

Windows Application events and the WinSW wrapper log showed this sequence on
2026-08-08 at 03:25 local time:

- Windows Installer began the Tailscale 1.102.2 MSI transaction;
- SCM cleanly stopped the dependent `nvidia_gpu_exporter` service;
- the exporter child exited with code 0, so failure recovery did not run; and
- Tailscale completed successfully, but the exporter remained stopped.

The service was manually restored on 2026-08-10 at 19:25 local time. Prometheus
then returned `up{job="gpu",instance="peecee"}=1` and cleared `TargetDown`.

On 2026-08-11 the WinSW desired state was changed to delayed automatic startup
without an SCM dependency on Tailscale. The exporter remains bound only to
`100.113.63.58:9835`, keeps its tailnet-scoped firewall, and retains its 5-second
restart-on-failure action. This specifically prevents a future Tailscale update
from cleanly stopping the exporter while preserving startup recovery if its bind
races the tailnet address.

Live verification at 2026-08-11 02:34 UTC showed:

- `sc.exe qc` reports `AUTO_START (DELAYED)` and no dependencies;
- `sc.exe qfailure` reports restart after 5000 ms;
- the installed XML SHA-256 matches the canonical file;
- the listener and firewall remain scoped to the tailnet;
- a controlled child-process termination recovered from PID 3056 to PID 8716;
- the RTX 3090 Ti metrics endpoint responded; and
- Prometheus reported the `gpu/peecee` target `up` with no scrape error.

No reboot or Tailscale restart was performed during this change. Boot persistence
is established by the SCM configuration; a post-reboot observation remains a
separate verification event.

## Proximal SSH route repair — 2026-08-10

The proximal-side `peecee` OpenSSH alias was pinned to Tailscale address
`100.113.63.58` after LAN name resolution returned a stale address. The
canonical client configuration now lives under `config/ssh-client/`; the
private key remains outside Git at `~/.ssh/id_ed25519`.
