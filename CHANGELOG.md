# Changelog — proximal (system)

System-level and cross-subsystem changes to host **proximal**, newest first. Each
subsystem's `README.md` is its current-state reference; dense PostgreSQL cluster-config
history lives in [`postgres/CHANGELOG.md`](postgres/CHANGELOG.md). See `git log` for granular
history. **Values and config, never credentials.**

## 2026-06-21

### Authored alerting rules for node / gpu / postgres / infra
Phase 2 of the alerting work (Phase 1 was the routing path, 2026-06-20). The exporters had
dashboards but no alerts; now they do — 18 proximal-authored rules under
`observability/prometheus/rules/{node,gpu,postgres,infra}-alerting.rules.yml`, routing to Slack
`#proximal-alerts` through the same Alertmanager pipe.
- **node** (7): filesystem low (<15%) / critical (<5%) space, low inodes, read-only fs, memory
  <10%, OOM kills, load >2.5×cores. Pseudo-filesystems excluded; read-only mounts excluded from
  the space alerts; load normalized by core count via `group_left`.
- **gpu** (3): high (>84°C) / critical (>90°C) temp, HW thermal throttling — fires per-GPU
  (proximal 3090 + peecee 3090 Ti). **No VRAM alert on purpose**: the local LLM pins ~22.8 GiB, so
  a VRAM-full rule would fire permanently; temperature + the driver thermal-slowdown flag are the
  honest hardware-risk signals.
- **postgres** (7): pg down, connections >80/90% of max_connections, deadlocks, long-running txn
  (>10m), XID wraparound warn/crit. Caught two metric quirks: wraparound is **XID age** not
  seconds (thresholds vs the 2³¹ limit), and the long-txn "oldest" series is a Unix **timestamp**
  so age = `time() - it`, guarded by `count>0` to avoid a stale-timestamp false fire.
- **infra** (1): `TargetDown` for any `up==0` (10m) across all jobs.
- **Verified**, not just installed: all 32 rule groups evaluate `health=ok`, nothing false-fires
  (thresholds sit clear of live readings), and every label-matching expr (`group_left`/`and`/
  `scalar`) was checked to return non-empty so no rule can silently never-fire. Both severity tiers
  already proven live end-to-end — `DoctorRed` (page) and `LivenessMarginCollapse` (warning) are
  routing to `#proximal-alerts` right now via the identical path.

## 2026-06-20

### Stood up Alertmanager → Slack alert routing
Closed the gap where alerting rules evaluated but went nowhere (`alerting.alertmanagers: []`).
Routing decided with the operator: every alert → one Slack channel `#proximal-alerts` via a
**dedicated** Slack app `proximal-alerts` (workspace gearheads), isolated from the praxis app.
- **Alertmanager** installed from apt (`prometheus-alertmanager 0.26.0`), same house pattern as
  the rest: ARGS in `/etc/default/prometheus-alertmanager` bind the tailnet IP
  `100.85.100.81:9093` (HA cluster listener disabled — single node, nothing on `:9094`), a
  `10-tailnet-bind.conf` drop-in orders it `After=tailscaled` + `network-online.target` with
  `Restart=on-failure`. Config `observability/alertmanager/alertmanager.yml` → `/etc/prometheus/`.
- **Routing:** one receiver, channel `#proximal-alerts`. The two striatumd severity tiers share
  the channel but differ in urgency — `page` (NecrosisRate/DoctorRed/SupervisorOriginFlood) waits
  10s and re-alerts hourly; `warning` batches 30s and re-alerts every 4h. An inhibit rule
  suppresses a `warning` when a `page` for the same alertname+instance is already firing.
- **Prometheus** wired: `alerting.alertmanagers` → `100.85.100.81:9093`; verified at
  `:9091/api/v1/alertmanagers` (active). Live `LivenessMarginCollapse` + `WedgeAgeTail` now reach
  AM (`:9093/api/v2/alerts`); AM attempts Slack delivery — proven end-to-end.
- **Secret:** the Slack incoming-webhook URL is the one credential — never in git. AM reads it from
  `/etc/alertmanager/slack_webhook_url` (0640 root:prometheus) via `slack_configs.api_url_file`;
  repo has `slack_webhook_url.template` + the app manifest (`proximal-alerts.slack-manifest.json`).
- **Live + verified.** Created the `proximal-alerts` app (`app_id A0BBJQQPGQ7`, workspace gearheads)
  via `apps.manifest.create` (`--data-urlencode manifest@…`), added an Incoming Webhook to
  `#proximal-alerts`, stored the URL in the file above. End-to-end verified 2026-06-20: a synthetic
  page alert plus the two live striatumd alerts delivered to the channel
  (`alertmanager_notifications_total{slack}` rising, `failed_total` flat), and both a silence
  (active → suppressed → expired → active) and a resolve round-trip succeeded.

### Wired the `striatumd` RFC 0137 exporter into Prometheus + Grafana
The local workflow daemon's lifecycle/liveness exporter (15 families, RFC 0137) is now scraped,
ruled, and dashboarded. Cross-subsystem (`observability/` + `striatum/`).
- **Pinned the scrape target.** `/metrics` rides the daemon's MCP/HTTP listener, which binds a
  **random port per boot** — no stable target. Fixed with
  `Environment=STRIATUM_DAEMON_MCP_HTTP_ADDR=127.0.0.1:9464` in `striatum/striatumd.service` (the
  default for the daemon's `-mcp-http-addr` flag). Loopback-only + tokenless (RFC 0137 §4):
  Prometheus runs on this host and scrapes `127.0.0.1:9464` directly, no TLS/bearer; **not**
  exposed to the tailnet.
- **Scrape job** `striatumd` → `127.0.0.1:9464` in `prometheus/prometheus.yml`; target `up`
  (now 5 targets: gpu×2/node/postgresql/prometheus/striatumd).
- **Rules** vendored verbatim from the striatum repo (`go/pkg/metrics/rules/`) into
  `prometheus/rules/striatum-{recording,alerting}.rules.yml` and installed to
  `/etc/prometheus/rules/`: 5 recording + 9 alerting rules, all `health=ok` via `promtool`. They
  **evaluate but are not routed** — no Alertmanager on this box yet (`alertmanagers: []`); firing
  alerts show at `:9091/alerts`.
- **Dashboard** `grafana/dashboards/striatum-proximal.json` (uid `striatum-proximal`, folder
  "proximal"), generated by `build_striatum_dashboard.py`; 27 panels mapping 1:1 to the §3
  taxonomy (necrosis/apoptosis spine, wedge/liveness forewarning, #417 supervisor flood, leases,
  exporter health). Verified live through Grafana's datasource proxy.
- **Incident (recovered):** the port-pin restart re-exec'd the committee-drifted on-disk
  `striatumd` (`202c1cc5`, `LatestDaemonDBVersion = 40`), which crash-looped against the
  migration-42 DB (`schema version 42 is newer than supported 40`) — the prior "any migration-40
  build runs clean" claim was wrong; that only held for the still-resident 42-capable process.
  Rebuilt from a clean worktree off `origin/main` (ceiling 42) and installed just the daemon
  binary (never `make install`, #509). See `striatum/README.md` (#503 / binary-drift).

### Captured the `praxis/` subsystem
New top-level subsystem for **Praxis** (the local-first executive-function daemon at
`~/git/praxis`). Captures the host integration — two systemd **user** units and the
secret handling — not the codebase.
- **Units:** `praxisd.service` (the daemon; Type=notify, 30s watchdog, `Restart=always`,
  peer-auth `praxis` DB) and the new `praxis-slack.service` (Type=simple Socket Mode
  listener — an outbound WebSocket to Slack, *no public ingress*; `Restart=on-failure`
  because a missing token is a deliberate fail-closed exit 78). Both `enabled`, lingering.
- **Connector went live:** RFC 0020 two-way Slack dialog, verified end-to-end on the box
  — inbound (@mention, DM, **and plain private-channel message**) → `inbox` dock →
  `praxisd` drain → capture (`actor=[]`, `locality=cloud`, **0 attestations** → stays
  behind the said/inferred wall, I1/I3) → egress-gated (I4) ack posted back to
  `#praxis-chat`. Slack app `praxis` (`U0BC0EN59DF`, `A0BBS89SPGB`), team `gearheads`.
- **Slack scopes (via App Manifest API + config token):** added `channels:history` /
  `message.channels` then `groups:history` / `message.groups` — `#praxis-chat` is a
  *private* channel, so `groups:*` is the load-bearing pair (cost two reinstalls; a scope
  change forces an OAuth re-consent, event changes apply live). See `praxis/README.md`.
- **Secrets:** by name only. Values live in `~/.config/praxis/praxisd.env` (`0600`,
  user-owned, outside git), loaded via `EnvironmentFile=-`. Load-bearing cred is the
  `xapp-` app-level token (`connections:write` + Socket Mode toggled on). The Postgres
  DSN is peer-auth (no password) → config, not credential.

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
