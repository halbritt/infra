# proximal/observability — Prometheus + Grafana + exporters

System-wide monitoring for host **proximal**: a `node_exporter` (whole-host metrics), a
`postgres_exporter` (PostgreSQL 17.10 cluster), an `nvidia_gpu_exporter` (RTX 3090), and the
`striatumd` RFC 0137 exporter (the local workflow daemon's lifecycle/liveness internals) feeding
Prometheus → Grafana. The observability subsystem of the [`proximal`](../README.md) whole-system
repo, stood up 2026-06-18 (GPU exporter added 2026-06-19). A second GPU target — the **peecee**
Windows 11 workstation (RTX 3090 Ti, the same `nvidia_gpu_exporter` as a WinSW service over the
tailnet) — was added 2026-06-20; see [`nvidia-gpu-exporter-peecee/`](nvidia-gpu-exporter-peecee/).
The **striatumd** exporter was wired in 2026-06-20 (scrape job + committed rules + dashboard);
see ["striatumd exporter (RFC 0137)"](#striatumd-exporter-rfc-0137) below.
This dir holds the **canonical** copies; the box runs installed copies at the paths below.
Edit here, then re-install. **No secrets are committed** (see "Secrets" at the bottom).

```
  PostgreSQL 17/main ──(scram, 127.0.0.1:5432)──> postgres_exporter ─┐
  node_exporter (host) ───────────────────────────────────────────────┤ scrape
  nvidia_gpu_exporter (RTX 3090, via nvidia-smi) ─────────────────────┤
                                                                       ▼
                                              Prometheus ──query──> Grafana (dashboards)
```

## Topology & ports

Everything binds the **tailnet IP `100.85.100.81`** (reachable from tailnet peers, e.g.
`homeassistant`; not LAN — there is no host firewall, so binding the specific tailnet IP is
what keeps it off `192.168.1.92`). Default ports collided, so:

| service           | unit                            | bind                  | why this port |
|-------------------|---------------------------------|-----------------------|---------------|
| postgres_exporter   | `prometheus-postgres-exporter`  | `100.85.100.81:9187`  | 9187 free |
| postgres_exporter (gpu-fleet) | `prometheus-postgres-exporter-gpufleet` | `100.85.100.81:9188` | second instance, DSN → db `gpu_fleet` (custom queries can't be scoped per-DB); emits only `pg_gpu_fleet_*` (PROXIMAL-5) |
| node_exporter       | `prometheus-node-exporter`      | `100.85.100.81:9100`  | dep of `prometheus`; rebound off `*` |
| nvidia_gpu_exporter | `nvidia_gpu_exporter`           | `100.85.100.81:9835`  | 9835 free (project default) |
| nvidia_gpu_exporter (peecee) | `nvidia_gpu_exporter` (WinSW, on **peecee**) | `100.113.63.58:9835` | RTX 3090 Ti; Windows host, scraped over tailnet |
| Prometheus          | `prometheus`                    | `100.85.100.81:9091`  | 9090 = `cockpit.socket` |
| Grafana             | `grafana-server`                | `100.85.100.81:3003`  | 3000/3001/3002 taken (open-webui, token-dashboard) |
| Alertmanager        | `prometheus-alertmanager`       | `100.85.100.81:9093`  | 9093 free; HA cluster listener (:9094) disabled (single node) |
| striatumd exporter  | `striatumd` (RFC 0137 `/metrics`) | **`127.0.0.1:9464`** | loopback-only + tokenless (RFC 0137 §4); 9464 = prometheus-community default, free here |
| llama-server /metrics | `llama-27b` (llama.cpp `--metrics`) | **`127.0.0.1:8081`** (scrape) | multiplexed on the API port; server binds 0.0.0.0 but is scraped via loopback — see [`../llama/`](../llama/) |

> The striatumd exporter is the one **loopback-bound** target: `/metrics` is multiplexed onto the
> daemon's MCP/HTTP listener, which is loopback + tokenless by RFC 0137 §4. Prometheus runs on this
> host, so it scrapes `127.0.0.1:9464` directly. Do **not** rebind it to the tailnet — front it with
> `tailscale serve` + a scoped bearer if remote scrape is ever needed (mirrors the RFC 0085 web-ui).
> The llama-server target follows the same precedent: its `/metrics` (enabled 2026-07-20 via
> `--metrics` in the drop-in, PROXIMAL-4) shares the OpenAI-compatible API port `:8081`, and
> Prometheus scrapes it over loopback even though the server itself binds 0.0.0.0.

The six **proximal** units are `systemctl enable`d (the five exporters/servers above plus
`prometheus-alertmanager`). Each has a `*.service.d/` drop-in that orders it
`After=tailscaled.service` + `network-online.target` and sets `Restart=on-failure` /
`RestartSec=5`, so a bind that races tailscale at boot self-heals. (`nvidia_gpu_exporter`'s
drop-in also clears the `.deb`'s all-interfaces `ExecStart` and re-points it at the tailnet IP.)
The peecee exporter is the one off-box piece — a Windows service (WinSW), not systemd; it gets the
same `depend=Tailscale` + restart-on-failure self-heal (see `nvidia-gpu-exporter-peecee/`).

## Tailnet index (tailscale.harm.org)

The three user-facing surfaces are linked from the tailnet landing page
**`tailscale.harm.org`** (served on proximal by `~/git/tailscale-index/server.py` on
`127.0.0.1:3912`, fronted by cloudflared). Unlike most cards there — which point at
`tailscale serve` HTTPS URLs — these bind the tailnet IP directly, so the links are plain
`http://` over the tailnet:

| card | URL |
|---|---|
| Grafana — proximal dashboards | `http://proximal.tail0ecc2e.ts.net:3003/` |
| Prometheus — proximal | `http://proximal.tail0ecc2e.ts.net:9091/` |
| Alertmanager — proximal | `http://proximal.tail0ecc2e.ts.net:9093/` |

The added cards are recorded in [`tailscale-index-card.patch`](tailscale-index-card.patch)
(the index dir is not a git repo, so it's a provenance record of the applied edit, mirroring
[`../caplab-dashboard/tailscale-index-card.patch`](../caplab-dashboard/tailscale-index-card.patch)).
The server serves `site/` statically with `Cache-Control: no-cache`, so edits are live on save.

## Files → install locations

| repo file | install path |
|---|---|
| `exporter/prometheus-postgres-exporter.default.template` | `/etc/default/prometheus-postgres-exporter` (0600 root, **add real DSN**) |
| `exporter/queries.yaml` | `/etc/prometheus-postgres-exporter/queries.yaml` |
| `exporter/10-tailnet-bind.conf` | `/etc/systemd/system/prometheus-postgres-exporter.service.d/` |
| `exporter/prometheus-postgres-exporter-gpufleet.service` | `/etc/systemd/system/` (our own unit — tailnet-bind self-heal inlined) |
| `exporter/prometheus-postgres-exporter-gpufleet.default.template` | `/etc/default/prometheus-postgres-exporter-gpufleet` (0600 root, **add real DSN** — same role/password, db `gpu_fleet`) |
| `exporter/queries-gpu-fleet.yaml` | `/etc/prometheus-postgres-exporter/queries-gpu-fleet.yaml` |
| `node-exporter/prometheus-node-exporter.default` | `/etc/default/prometheus-node-exporter` |
| `node-exporter/10-tailnet-bind.conf` | `/etc/systemd/system/prometheus-node-exporter.service.d/` |
| `nvidia-gpu-exporter/10-tailnet-bind.conf` | `/etc/systemd/system/nvidia_gpu_exporter.service.d/` (binary+unit from the `.deb`) |
| `nvidia-gpu-exporter-peecee/nvidia_gpu_exporter-svc.xml` | `C:\Program Files\nvidia_gpu_exporter\` on **peecee** (WinSW service config) |
| `prometheus/prometheus.yml` | `/etc/prometheus/prometheus.yml` |
| `prometheus/prometheus.default` | `/etc/default/prometheus` |
| `prometheus/10-tailnet-bind.conf` | `/etc/systemd/system/prometheus.service.d/` |
| `prometheus/rules/striatum-recording.rules.yml` | `/etc/prometheus/rules/` (vendored from striatum repo) |
| `prometheus/rules/striatum-alerting.rules.yml` | `/etc/prometheus/rules/` (vendored from striatum repo) |
| `prometheus/rules/node-alerting.rules.yml` | `/etc/prometheus/rules/` (proximal-authored) |
| `prometheus/rules/gpu-alerting.rules.yml` | `/etc/prometheus/rules/` (proximal-authored) |
| `prometheus/rules/postgres-alerting.rules.yml` | `/etc/prometheus/rules/` (proximal-authored) |
| `prometheus/rules/infra-alerting.rules.yml` | `/etc/prometheus/rules/` (proximal-authored) |
| `alertmanager/alertmanager.yml` | `/etc/prometheus/alertmanager.yml` |
| `alertmanager/prometheus-alertmanager.default` | `/etc/default/prometheus-alertmanager` |
| `alertmanager/10-tailnet-bind.conf` | `/etc/systemd/system/prometheus-alertmanager.service.d/` |
| `alertmanager/slack_webhook_url.template` | `/etc/alertmanager/slack_webhook_url` (0640 root:prometheus, **add real webhook URL**) |
| `alertmanager/proximal-alerts.slack-manifest.json` | (not installed — used once to create the Slack app via the manifest API) |
| `grafana/grafana-server.env.overrides` | appended to `/etc/default/grafana-server` |
| `grafana/10-proximal.conf` | `/etc/systemd/system/grafana-server.service.d/` |
| `grafana/provisioning-datasources-proximal.yaml` | `/etc/grafana/provisioning/datasources/proximal.yaml` |
| `grafana/provisioning-dashboards-proximal.yaml` | `/etc/grafana/provisioning/dashboards/proximal.yaml` |
| `grafana/dashboards/pg-proximal-health.json` | `/var/lib/grafana/dashboards/` (provisioned, folder "proximal") |
| `grafana/dashboards/node-exporter-full-proximal.json` | `/var/lib/grafana/dashboards/` (provisioned, folder "proximal") |
| `grafana/dashboards/nvidia-gpu-proximal.json` | `/var/lib/grafana/dashboards/` (provisioned, folder "proximal") |
| `grafana/dashboards/striatum-proximal.json` | `/var/lib/grafana/dashboards/` (provisioned, folder "proximal") |
| `grafana/dashboards/gpu-fleet-proximal.json` | `/var/lib/grafana/dashboards/` (provisioned, folder "proximal") |
| `role.sql` | run once via `sudo -u postgres psql` |
| `tailscale-index-card.patch` | record of the Grafana/Prometheus/Alertmanager cards on `~/git/tailscale-index/site/index.html` (not a git repo; see "Tailnet index" above) |

The port-pin that makes `striatumd` scrapeable lives in the **striatum** subsystem, not here:
`Environment=STRIATUM_DAEMON_MCP_HTTP_ADDR=127.0.0.1:9464` in
[`../striatum/striatumd.service`](../striatum/striatumd.service).

## Install from scratch (the order 2026-06-18 used)

```bash
# 1. packages
sudo apt-get install -y prometheus prometheus-postgres-exporter          # universe
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://apt.grafana.com/gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/grafana.gpg
echo 'deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main' \
  | sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt-get update && sudo apt-get install -y grafana                   # grafana-oss 13.x

# 2. exporter role + secret (see role.sql; password only in the 0600 EnvironmentFile)
PW=$(openssl rand -hex 24); # create role with PW, then write the DSN into
#   /etc/default/prometheus-postgres-exporter (template here), chmod 0600.

# 3. nvidia_gpu_exporter (RTX 3090) — not in apt; install the upstream .deb
#    (utkuozdemir/nvidia_gpu_exporter, nvidia-smi based → works on consumer GeForce).
V=1.4.1
curl -fsSL -o /tmp/nvidia-gpu-exporter.deb \
  "https://github.com/utkuozdemir/nvidia_gpu_exporter/releases/download/v${V}/nvidia-gpu-exporter_${V}_linux_amd64.deb"
sudo dpkg -i /tmp/nvidia-gpu-exporter.deb   # creates the nvidia_gpu_exporter user + unit, binds :9835 on *

# 4. drop the config files into the paths above (incl. the GPU drop-in to rebind to tailnet), then:
sudo systemctl daemon-reload
sudo systemctl enable --now prometheus-postgres-exporter prometheus-node-exporter \
  nvidia_gpu_exporter prometheus grafana-server
```

## Verify

```bash
curl -s http://100.85.100.81:9187/metrics | grep '^pg_up'                     # pg_up 1
curl -s http://100.85.100.81:9187/metrics | grep '^pg_scrape_collector_success' # all 1
curl -s http://100.85.100.81:9835/metrics | grep '^nvidia_smi_gpu_info'        # RTX 3090 line, value 1
curl -s http://100.113.63.58:9835/metrics | grep '^nvidia_smi_gpu_info'        # peecee RTX 3090 Ti, value 1
curl -s http://127.0.0.1:9464/metrics | grep -c '^# HELP striatum_'            # 15 striatumd families
curl -s http://127.0.0.1:8081/metrics | grep -c '^llamacpp:'                   # 11 llama-server series
curl -s http://100.85.100.81:9091/api/v1/targets | jq '.data.activeTargets[].health' # all "up" (gpu×2/node/postgresql/prometheus/striatumd/llama)
curl -s http://100.85.100.81:9091/api/v1/rules | jq '[.data.groups[].rules[]|select(.health!="ok")]|length' # 0 rule errors
curl -s http://100.85.100.81:3003/api/health                                  # database ok
```

## What it monitors (beyond stock collectors)

**PG17 fixes** — postgres_exporter 0.15.0 ships two collectors that break on PG17, so they're
disabled (`--no-collector.stat_bgwriter`, and `stat_statements` is left off) and replaced by
custom queries in `queries.yaml`:
- `stat_bgwriter`: checkpoint columns moved to the new `pg_stat_checkpointer` view in PG17.
- `stat_statements`: `blk_read_time` was split (`shared_blk_read_time`, …) in pg_stat_statements 1.11.

**`queries.yaml` custom metrics**
- `pg_supervisor_tables_*` — size / dead-tuples of `process_supervisor_pointers`,
  `process_supervisors`, `daemon_supervisors`. The bloat watch for `striatum#421` +
  `pg-repack-bloated.timer` (regrows 2.5 MB → ~150 MB in ~90 min under load, plateaus ~150–255 MB).
- `pg_checkpointer_*` — `num_requested` should stay ~0 (validates `max_wal_size=16GB`).
- `pg_bgwriter_*`, `pg_stat_statements_top_*` (top 25 by total exec time).

Plus enabled built-ins: `long_running_transactions` (the 57014 / `transaction_timeout=120s`
family), `stat_activity_autovacuum`, `database_wraparound` (XID age — `…_seconds` is XID age,
not seconds; ÷2^31 ≈ 1.4% baseline), `statio_user_indexes`, `process_idle`.

**Dashboard** — `pg-proximal-health.json` (Grafana folder "proximal"): pg_up, backends vs
`max_connections`, cache-hit ratio, transactions/deadlocks/temp per db, checkpoints (forced vs
timed), bgwriter buffers, supervisor table size + dead tuples, XID wraparound %, top-15
statements by mean time, and a host row (CPU/mem/disk from node_exporter). Regenerate with
`python3 dashboards/build_dashboard.py > dashboards/pg-proximal-health.json`. It's set as the
Grafana **home** dashboard (org pref `homeDashboardUID` + `GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH`).

**Host dashboard** — `node-exporter-full-proximal.json`: the canonical "Node Exporter Full"
(Grafana ID **1860**), fetched + pinned to our datasource (uid `prometheus-proximal`) and dropped
into the same "proximal" folder. Re-fetch/refresh with `python3 dashboards/fetch_node_dashboard.py`
(downloads 1860, rewrites every datasource ref to ours, strips `__inputs`). Unlike the Postgres
case, importing a community dashboard here is fine — node_exporter metric names are stable across
versions, and its panel queries verified live against our `job="node",instance="proximal"` series.

> The Postgres-side community dashboard (Grafana ID 9628) was intentionally **not** imported:
> those target pre-PG17 / older-exporter metric names and would render half-broken here. The
> custom `pg-proximal-health` dashboard uses only metrics verified present against this exporter+PG17.

**GPU dashboard** — `nvidia-gpu-proximal.json`: the exporter author's own dashboard (Grafana ID
**14574**), fetched + pinned to our datasource and `job="gpu"`, dropped into the "proximal" folder.
Re-fetch with `python3 dashboards/fetch_gpu_dashboard.py`. Safe to import — its panels query the
exact `nvidia_smi_*` metric names this exporter emits (23 panels: utilization, VRAM, temp, power,
fan, clocks/throttle reasons). On the 3090, expect VRAM pinned ~23 GiB by the local LLM server.
The exporter logs a few `level=ERROR … unexpected characters` lines for exotic `nvidia-smi` fields
(`power_smoothing.*`) — best-effort parse warnings, harmless; metrics still serve.

## gpu-fleet exporter (second postgres_exporter instance, PROXIMAL-5)

The gpu-fleet registry (`~/git/gpu-fleet`) is live routing truth in Postgres — slots heartbeat
into `gpu_slots`, graduate `unverified → probationary → routable` (migration 009), evaporate
from the `live_slots`/`routable_slots` views past the 45s heartbeat TTL, and are claimed via
exclusive self-renewing leases (migration 007/RFC 0001). Wired into this stack 2026-07-20.

It lives in database **`gpu_fleet`**, not `striatum_daemon`, and postgres_exporter custom
queries **cannot be scoped per-database** — a shared `queries.yaml` would error every scrape in
one DB or the other. So a **second instance** of the same Debian binary runs as our own unit
`prometheus-postgres-exporter-gpufleet.service` (`100.85.100.81:9188`, job `gpu-fleet`): same
`postgres_exporter` role (plus explicit `SELECT` grants on the fleet tables — `role.sql`; the DB
is halbritt-owned, so run those as halbritt, not postgres), DSN pointed at `gpu_fleet`,
`--disable-default-metrics --disable-settings-metrics` **and** all nine default-enabled
new-style collectors switched off — it emits only the `pg_gpu_fleet_*` namespaces from
`exporter/queries-gpu-fleet.yaml`:

- `pg_gpu_fleet_summary_*` — always-one-row fleet totals: `slots_total`, `live_slots`,
  `routable_slots` (the alert-safe real-zero), `active_leases`, `routable_vram_free_mib`
  (derived free VRAM over routable slots).
- `pg_gpu_fleet_status_slots{status=…}` — slots per lifecycle status, zero-filled over the
  full CHECK enum so an empty status emits 0 instead of going absent.
- `pg_gpu_fleet_slot_*{node,endpoint_url,slot_id,…}` — per-slot heartbeat age, alive (decode
  probe, not HTTP 200), VRAM total/free, util, probe ms/streak.
- `pg_gpu_fleet_lease_*{holder,…}` — held exclusive leases: `held` 1 + `ttl_remaining_seconds`.
  The schema stores **no claim timestamp** and leases self-renew, so "lease age" is not
  derivable; a wedged holder shows as remaining TTL sliding to expiry un-topped-up.

**Dashboard** — `gpu-fleet-proximal.json` (folder "proximal", uid `gpu-fleet-proximal`):
overview stats (routable/live/registered/leases/free VRAM), status + heartbeat-age timeseries,
slot registry table, lease TTL + per-slot VRAM. Regenerate with
`python3 dashboards/build_gpu_fleet_dashboard.py > dashboards/gpu-fleet-proximal.json`.

**Alerts** — `gpu_fleet_alerts` group in `infra-alerting.rules.yml`:
`GpuFleetZeroRoutableSlots` (`…summary_routable_slots == 0` for 3m, `page` — every consumer
pick fails) and `GpuFleetHeartbeatStale` (`…slot_heartbeat_age_seconds > 90` for 1m, `warning`
— 2× the live TTL, i.e. a dead/wedged heartbeat writer or a decommissioned row needing DELETE).
Exporter-down blindness is covered by the generic `TargetDown`.

## striatumd exporter (RFC 0137)

The `striatumd` workflow daemon exports its lifecycle/liveness internals as 15 Prometheus
families (RFC 0137, implemented D247). Wired into this stack 2026-06-20. Unlike the other
exporters this one is **loopback-only**: `/metrics` is multiplexed onto the daemon's MCP/HTTP
listener (loopback + tokenless by RFC 0137 §4), so Prometheus — running on this same host —
scrapes `127.0.0.1:9464` directly with no TLS/bearer.

**The scrape target had to be pinned.** The MCP/HTTP listener binds a **random port per boot**
(published to `/run/striatum/mcp-http-endpoint`), giving Prometheus no stable target. Fixed by
setting `Environment=STRIATUM_DAEMON_MCP_HTTP_ADDR=127.0.0.1:9464` in the striatum subsystem's
unit ([`../striatum/striatumd.service`](../striatum/striatumd.service)) — that env var is the
default for the daemon's `-mcp-http-addr` flag, so it pins the addr without touching `ExecStart`.
The daemon still writes the dynamic endpoint file; scraping ignores it and uses the pinned addr.

**Scrape job** — `striatumd` → `127.0.0.1:9464` (in `prometheus/prometheus.yml`). Verify it is
`up` at `100.85.100.81:9091/targets`.

**Rules** — `prometheus/rules/striatum-{recording,alerting}.rules.yml`, **vendored verbatim** from
the striatum repo (`go/pkg/metrics/rules/{recording,alerting}_rules.yml`) with only a provenance
header prepended; install to `/etc/prometheus/rules/` and reference them from `rule_files:`. They
pre-aggregate the counters/histograms (5 recording rules) and map each striatumd failure class to a
signal (9 alerts: `NecrosisRate`, `DoctorRed`, `WedgeAgeTail`, `LivenessMarginCollapse`,
`SupervisorOriginFlood`, plus the staleness/tick/conservation/cardinality closers). A guardrail
test in the striatum repo (`TestPrometheusRulesReferenceRegisteredMetrics`) asserts every series
they reference is one the exporter actually emits, so keep the bodies byte-identical to the source.
**Refresh** when the striatum copies change:
```bash
SRC=~/git/striatum/go/pkg/metrics/rules; DST=~/git/proximal/observability/prometheus/rules
# (re-run the header+cat from the repo, then) sudo cp $DST/*.rules.yml /etc/prometheus/rules/
promtool check rules /etc/prometheus/rules/striatum-*.rules.yml && sudo systemctl reload prometheus
```
The alerts **evaluate** but are **not routed** — there is no Alertmanager on this box yet
(`alerting.alertmanagers: []`). Firing alerts are visible at `:9091/alerts`. (`LivenessMarginCollapse`
may sit `pending`/`firing` whenever lanes carry elapsed liveness deadlines — a real signal, not a
wiring fault.)

**Dashboard** — `grafana/dashboards/striatum-proximal.json` (uid `striatum-proximal`, folder
"proximal"), generated by `build_striatum_dashboard.py`. Panels map 1:1 to the RFC 0137 §3 taxonomy:
the necrosis/apoptosis lifecycle spine, wedge-age p99 + liveness-margin p05 forewarning, the #417
supervisor-flood signal, runs-by-state, lease transitions, non-terminal liveness events (F-A6), and
an exporter-health/data-quality row (snapshot age, tick status, cardinality clips, lifecycle
balance, doctor). It copies two load-bearing PromQL conventions from the rule files: the wedge-age
and liveness-margin **gauge histograms** are read by `histogram_quantile` directly (never through
`rate()`), and `cardinality_clipped_total` is a per-tick snapshot read with `max_over_time` (never
`increase()`). Regenerate with
`python3 dashboards/build_striatum_dashboard.py > dashboards/striatum-proximal.json`.

> **Restart hazard (learned wiring this in).** Pinning the port requires a `striatumd` restart,
> which re-exec's the on-disk binary `~/.local/bin/striatumd`. That binary is **committee-managed
> and drifts**; if it has drifted to one that supports an *older* DB schema than the live DB it
> crash-loops (`daemon PostgreSQL schema version N is newer than supported M`) and takes `/metrics`
> down with it. Recovery is to rebuild from a **clean worktree off `origin/main`** (which tracks the
> current schema) and install just the daemon binary — **never** `make install` (it runs the
> forbidden `striatum daemon install`, #509). Full detail in
> [`../striatum/README.md`](../striatum/README.md) (#503 / binary-drift).

**Verify striatumd end-to-end:**
```bash
curl -s http://127.0.0.1:9464/metrics | grep -c '^# HELP striatum_'                      # 15
curl -s http://100.85.100.81:9091/api/v1/targets | jq -r '.data.activeTargets[]|select(.labels.job=="striatumd")|.health'  # up
curl -s http://100.85.100.81:9091/api/v1/rules | jq '.data.groups|map(.rules|length)|add' # 14 (5+9)
# Grafana: dashboard "Striatum daemon — proximal (RFC 0137)" in folder proximal, panels live.
```

## Alerting rules (what fires)

Two provenances under `prometheus/rules/`, both referenced from `rule_files:` and installed to
`/etc/prometheus/rules/`:

- **Vendored** — `striatum-{recording,alerting}.rules.yml`, byte-identical from the striatum repo
  (see "striatumd exporter" above; a guardrail test there pins them).
- **proximal-authored** — `node/gpu/postgres/infra-alerting.rules.yml`, written here against this
  host's own exporters (2026-06-21). Every series was verified live before authoring, and every
  label-matching expr (`group_left`, `and`, `scalar`) was checked to produce a non-empty result so
  a rule can't silently never-fire. Thresholds sit clear of current readings (nothing false-fires
  on install). All use the house `page`/`warning` severities, so they route through Alertmanager
  to `#proximal-alerts` automatically.

| file | alerts | notable design choices |
|---|---|---|
| `node-alerting` | filesystem low/critical space, low inodes, read-only fs, memory low, OOM kills, high load | pseudo-fs excluded; read-only fs excluded from space alerts (it's its own alert); load normalized by core count via `group_left` |
| `gpu-alerting` | high/critical temp, HW thermal throttling | **no VRAM alert** — the LLM pins ~22.8 GiB by design, so VRAM-full would fire forever; temp + the driver's thermal-slowdown flag are the real hardware-risk signals. Fires per-GPU (proximal 3090 + peecee 3090 Ti) |
| `postgres-alerting` | pg down, connections >80/90%, deadlocks, long-running txn, XID wraparound warn/crit | wraparound metric is **XID age** (not seconds) → thresholds 1.5e9/1.9e9 of the 2³¹ limit; long-txn "oldest" is a Unix **timestamp** → age is `time() - it`, guarded by `count>0` |
| `infra-alerting` | `TargetDown` (any `up==0` for 10m); `LlamaServerDown` (`up{job="llama"}==0` for 1m, `page`); `LlamaSlotSaturated` (`llamacpp:requests_deferred>0` for 5m) | `TargetDown` covers every job uniformly; the off-box peecee GPU target can flap when that host sleeps — silence there, don't loosen the rule. llama gets its own fast down-alert (1m — primary inference endpoint; a normal restart stays pending) and a queue-pressure alert: **no KV-cache-usage series exists** in this llama.cpp build (upstream removed `kv_cache_usage_ratio`), so deferred requests behind the single `-np 1` slot are the pressure signal. Down-alert fire-tested 2026-07-20 (90s deliberate stop, fired at 75s, reached Alertmanager). Also hosts `gpu_fleet_alerts`: `GpuFleetZeroRoutableSlots` (`==0` for 3m, `page`) + `GpuFleetHeartbeatStale` (`>90s` for 1m) — see "gpu-fleet exporter" above |

Refresh/verify after editing: `promtool check rules prometheus/rules/*.yml`, `sudo cp` to
`/etc/prometheus/rules/`, `sudo systemctl reload prometheus`, then
`curl -s :9091/api/v1/rules | jq '[.data.groups[].rules[]|select(.health!="ok")]|length'` → 0.

## Alertmanager — alert routing

Until 2026-06-20 the alerting rules **evaluated but went nowhere** (`alerting.alertmanagers: []`);
firing alerts were only visible at `:9091/alerts`. Now `prometheus-alertmanager` (apt, 0.26.0)
routes them to **Slack `#proximal-alerts`** via a **dedicated** Slack app `proximal-alerts`
(workspace `gearheads`), deliberately isolated from the `praxis` app so alert traffic and Praxis
traffic never mix tokens.

**Topology.** `prometheus-alertmanager.service` binds the tailnet IP `100.85.100.81:9093` (ARGS in
`/etc/default/prometheus-alertmanager`; the HA gossip listener `:9094` is **disabled** —
`--cluster.listen-address=` empty — because this is a single Alertmanager, not a cluster). The
`10-tailnet-bind.conf` drop-in orders it `After=tailscaled` + `network-online.target` /
`Restart=on-failure`, like every other unit. Prometheus points at it via `alerting.alertmanagers`
in `prometheus.yml`.

**Routing (`alertmanager/alertmanager.yml`).** One receiver, one channel. The two striatumd severity
tiers share `#proximal-alerts` but get different urgency:

| severity | alerts | group_wait | repeat_interval |
|---|---|---|---|
| `page` | NecrosisRate, DoctorRed, SupervisorOriginFlood | 10s | 1h |
| `warning` | the other 6 striatumd alerts | 30s | 4h |

An **inhibit rule** suppresses a `warning` when a `page` for the same `alertname`+`instance` is
already firing (no double-notify). Grouping is by `alertname`/`severity`/`instance`.

**The Slack app + the one secret.** Live app: **`proximal-alerts`** (`app_id A0BBJQQPGQ7`) in
workspace **`gearheads`** — an account-level fact, not a secret. Created from
`alertmanager/proximal-alerts.slack-manifest.json` via the manifest API (`apps.manifest.create`
with `--data-urlencode manifest@…` — Slack wants the manifest as a form field, not `-F …=@file`;
needs an `xoxe.xoxp-` config token minted at api.slack.com/apps, ~12h TTL), then an **Incoming
Webhook** is added to `#proximal-alerts` (browser, one click — see below). That
webhook URL is the **only** credential and is **never in git** — Alertmanager reads it from
`/etc/alertmanager/slack_webhook_url` (0640 `root:prometheus`) via `slack_configs.api_url_file`. The
repo carries `slack_webhook_url.template` (provisioning steps) + the manifest only.

**Provision the webhook (final step):**
```bash
# 1. create the app (config token from api.slack.com/apps -> "Your App Configuration Tokens"):
curl -s -F token="$XOXE_CONFIG_TOKEN" \
  -F manifest=@observability/alertmanager/proximal-alerts.slack-manifest.json \
  https://slack.com/api/apps.manifest.create | jq '{ok,app_id,error}'
# 2. install the app to gearheads + add an Incoming Webhook to #proximal-alerts (browser:
#    api.slack.com/apps -> proximal-alerts -> Incoming Webhooks -> Add New Webhook to Workspace).
# 3. drop the URL in (replaces the placeholder) and reload:
printf '%s' 'https://hooks.slack.com/services/T.../B.../XXXX' | sudo tee /etc/alertmanager/slack_webhook_url >/dev/null
sudo chown root:prometheus /etc/alertmanager/slack_webhook_url && sudo chmod 0640 /etc/alertmanager/slack_webhook_url
sudo systemctl reload prometheus-alertmanager
```

**Verify routing end-to-end:**
```bash
amtool check-config /etc/prometheus/alertmanager.yml                                   # SUCCESS
curl -s http://100.85.100.81:9093/-/healthy                                            # OK
curl -s http://100.85.100.81:9091/api/v1/alertmanagers | jq '.data.activeAlertmanagers' # [{url:.../9093/api/v2/alerts}]
curl -s http://100.85.100.81:9093/api/v2/alerts | jq -r '.[].labels.alertname'          # the firing alerts
# fire a synthetic alert through to Slack, then resolve it:
amtool alert add --alertmanager.url=http://100.85.100.81:9093 \
  test_route severity=warning --annotation=summary="routing smoke test"
journalctl -u prometheus-alertmanager -n 20 | grep -i slack                            # no "Notify ... failed"
```

## Secrets (never in git)

- **Slack incoming-webhook URL** — the `proximal-alerts` app's webhook, only in
  `/etc/alertmanager/slack_webhook_url` (0640 `root:prometheus`, read by Alertmanager via
  `api_url_file`). The repo has `alertmanager/slack_webhook_url.template`. See "Alertmanager" above.
- **Exporter DB password** — only in `/etc/default/prometheus-postgres-exporter` (0600 root).
  The repo has a redacted `.template`. `role.sql` documents the role without the password.
- **Grafana admin password** — generated at install, stored only in `/etc/grafana/admin.env`
  (0600 root), loaded via the `10-proximal.conf` drop-in. Retrieve with
  `sudo cat /etc/grafana/admin.env`. User `admin`.
