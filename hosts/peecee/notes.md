# peecee host notes

## Repository import

The standalone repository `github.com/halbritt/peecee` was imported without
squashing on 2026-08-05. Source `main` was clean and synchronized at
`8bc7435470026341bf547de3da5bd0f654db464b`; all 15 source commits are ancestors
of subtree import commit `aef5ed4d85c7249d76ce833108299b2a9ed2071e`.

The import first landed at `hosts/peecee/source-import/` to avoid overwriting the
partial fleet record, then a separate normalization moved its three subsystems
under `config/`. The temporary directory is not part of the final layout. The
standalone checkout was not modified and remains available for historical
comparison. This fleet partition is canonical for future peecee desired-state
changes; archiving or deleting the old repository remains an owner decision.

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
