# maintenance/observability/ — Prometheus + Grafana + postgres_exporter

From-scratch monitoring for the proximal PostgreSQL 17.10 cluster, stood up 2026-06-18.
This dir holds the **canonical** copies; the box runs installed copies at the paths below.
Edit here, then re-install. **No secrets are committed** (see "Secrets" at the bottom).

```
  PostgreSQL 17/main ──(scram, 127.0.0.1:5432)──> postgres_exporter ─┐
  node_exporter ─────────────────────────────────────────────────────┤ scrape
                                                                       ▼
                                              Prometheus ──query──> Grafana (dashboards)
```

## Topology & ports

Everything binds the **tailnet IP `100.85.100.81`** (reachable from tailnet peers, e.g.
`homeassistant`; not LAN — there is no host firewall, so binding the specific tailnet IP is
what keeps it off `192.168.1.92`). Default ports collided, so:

| service           | unit                            | bind                  | why this port |
|-------------------|---------------------------------|-----------------------|---------------|
| postgres_exporter | `prometheus-postgres-exporter`  | `100.85.100.81:9187`  | 9187 free |
| node_exporter     | `prometheus-node-exporter`      | `100.85.100.81:9100`  | dep of `prometheus`; rebound off `*` |
| Prometheus        | `prometheus`                    | `100.85.100.81:9091`  | 9090 = `cockpit.socket` |
| Grafana           | `grafana-server`                | `100.85.100.81:3003`  | 3000/3001/3002 taken (open-webui, token-dashboard) |

All four are `systemctl enable`d. Each has a `*.service.d/` drop-in that orders it
`After=tailscaled.service` + `network-online.target` and sets `Restart=on-failure` /
`RestartSec=5`, so a bind that races tailscale at boot self-heals.

## Files → install locations

| repo file | install path |
|---|---|
| `exporter/prometheus-postgres-exporter.default.template` | `/etc/default/prometheus-postgres-exporter` (0600 root, **add real DSN**) |
| `exporter/queries.yaml` | `/etc/prometheus-postgres-exporter/queries.yaml` |
| `exporter/10-tailnet-bind.conf` | `/etc/systemd/system/prometheus-postgres-exporter.service.d/` |
| `node-exporter/prometheus-node-exporter.default` | `/etc/default/prometheus-node-exporter` |
| `node-exporter/10-tailnet-bind.conf` | `/etc/systemd/system/prometheus-node-exporter.service.d/` |
| `prometheus/prometheus.yml` | `/etc/prometheus/prometheus.yml` |
| `prometheus/prometheus.default` | `/etc/default/prometheus` |
| `prometheus/10-tailnet-bind.conf` | `/etc/systemd/system/prometheus.service.d/` |
| `grafana/grafana-server.env.overrides` | appended to `/etc/default/grafana-server` |
| `grafana/10-proximal.conf` | `/etc/systemd/system/grafana-server.service.d/` |
| `grafana/provisioning-datasources-proximal.yaml` | `/etc/grafana/provisioning/datasources/proximal.yaml` |
| `grafana/provisioning-dashboards-proximal.yaml` | `/etc/grafana/provisioning/dashboards/proximal.yaml` |
| `grafana/dashboards/pg-proximal-health.json` | `/var/lib/grafana/dashboards/` (provisioned, folder "proximal") |
| `role.sql` | run once via `sudo -u postgres psql` |

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

# 3. drop the config files into the paths above, then:
sudo systemctl daemon-reload
sudo systemctl enable --now prometheus-postgres-exporter prometheus-node-exporter prometheus grafana-server
```

## Verify

```bash
curl -s http://100.85.100.81:9187/metrics | grep '^pg_up'                     # pg_up 1
curl -s http://100.85.100.81:9187/metrics | grep '^pg_scrape_collector_success' # all 1
curl -s http://100.85.100.81:9091/api/v1/targets | jq '.data.activeTargets[].health' # all "up"
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

## Secrets (never in git)

- **Exporter DB password** — only in `/etc/default/prometheus-postgres-exporter` (0600 root).
  The repo has a redacted `.template`. `role.sql` documents the role without the password.
- **Grafana admin password** — generated at install, stored only in `/etc/grafana/admin.env`
  (0600 root), loaded via the `10-proximal.conf` drop-in. Retrieve with
  `sudo cat /etc/grafana/admin.env`. User `admin`.
