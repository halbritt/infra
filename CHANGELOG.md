# Changelog — proximal (system)

System-level and cross-subsystem changes to host **proximal**, newest first. Each
subsystem's `README.md` is its current-state reference; dense PostgreSQL cluster-config
history lives in [`postgres/CHANGELOG.md`](postgres/CHANGELOG.md). See `git log` for granular
history. **Values and config, never credentials.**

## 2026-06-19

### Added NVIDIA GPU exporter to the observability stack
GPU monitoring for the **RTX 3090** (shared by the `llama.cpp` server `:8081` and `whisper-stt`).
- **Exporter:** `utkuozdemir/nvidia_gpu_exporter` **v1.4.1**, installed from the upstream `.deb`
  (not in apt). Chosen over NVIDIA's official **DCGM exporter** because it shells out to
  `nvidia-smi` and works on consumer GeForce cards — DCGM targets datacenter GPUs (many fields
  unsupported on GeForce) and runs a heavier `nv-hostengine` daemon. Driver `610.43.02`.
- **Bind:** the `.deb` unit listens on all interfaces `:9835`; a `10-tailnet-bind.conf` drop-in
  clears its `ExecStart` and re-points it at `100.85.100.81:9835` (tailnet only, no host firewall),
  ordered `After=tailscaled` + `network-online.target`, `Restart=on-failure` — matching the other
  exporters. Runs as the unprivileged `nvidia_gpu_exporter` user (querying `nvidia-smi` needs no root).
- **Prometheus:** new `gpu` scrape job → `100.85.100.81:9835`, target `up`, 93 `nvidia_smi_*`
  series (VRAM, util, temp, power, fan, clocks). VRAM read ~22.8/25.8 GiB (the LLM, as expected).
- **Grafana:** vendored dashboard **ID 14574** (the exporter author's own), pinned to datasource
  `prometheus-proximal` + `job=gpu`, provisioned as "NVIDIA GPU — proximal" (folder proximal).
  Regenerate with `observability/grafana/dashboards/fetch_gpu_dashboard.py`.
- Exporter logs a few `level=ERROR … unexpected characters` lines for exotic `power_smoothing.*`
  `nvidia-smi` fields — best-effort parse warnings, harmless; metrics still serve.

### Captured the `ollama/` subsystem
New top-level subsystem documenting the **secondary** local inference service (primary is the
`llama.cpp` server). Ollama `0.9.5`, loopback `:11434`, models `qwen3:14b` + `nomic-embed-text`
(~8.9 GiB on disk). Captured the stock `ollama.service` + the tuning drop-in (q8_0 KV cache,
context 32768, flash-attention, `KEEP_ALIVE=-1`); exposure left loopback-only, unchanged.

### Reorganized into one-system-one-repo: `proximal-pg` → `proximal`
The repo became the per-host provenance for the **whole** system: PostgreSQL demoted to a
`postgres/` subsystem, observability promoted from `maintenance/observability/` to a top-level
`observability/` sibling, new whole-system `README.md` + `AGENTS.md`. GitHub repo renamed
(old name redirects). Full detail in [`postgres/CHANGELOG.md`](postgres/CHANGELOG.md).
