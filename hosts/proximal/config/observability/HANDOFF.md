# Handoff — stand up Prometheus + Grafana + postgres_exporter on `proximal`

> **STATUS: COMPLETED (2026-06-18).** This stack is built, running under systemd, and committed.
> Historical record of the original task — see [`README.md`](README.md) for current state.
> Paths below predate the repo reorg: this repo is now `proximal` (origin
> `github.com/halbritt/proximal`) and these files live in `observability/`, not
> `maintenance/observability/`.

**One task:** build a from-scratch observability stack on host **proximal** to monitor the
local **PostgreSQL 17.10** cluster. Nothing else — the DB-tuning/repack/issue-filing work from
this session is already done, committed, and pushed (see "Already done" below); do not redo it.

**Goal state:** `prometheus-postgres-exporter` → **Prometheus** (scraping it) → **Grafana**
(dashboards), all under systemd (this box's convention), loopback/tailnet only, secrets out of git.

---

## Environment (discovered — don't re-investigate)

- Host `proximal`, Ubuntu 24.04, kernel 6.8. Superuser shell via `sudo -u postgres psql`;
  `sudo -n` works non-interactively here. General box facts: `~/CLAUDE.md`.
- **PostgreSQL 17.10**, cluster `17/main`, loopback `127.0.0.1:5432` + socket
  `/var/run/postgresql`. Standalone primary, `system_identifier 7652478211804703267`. Busiest
  DB `striatum_daemon` (27 GB); others `hippo`, `engram`, `praxis`, `token_dashboard`, `ob1`.
- **No monitoring stack exists yet.** Earlier-assumed "Prometheus on :9090" was wrong:
  - `:9090` = **`cockpit.socket`** (Cockpit, enabled, active) → **Prometheus default port is taken.**
  - `:3000` = a `python3` web UI, `:3001` = another Python app → **Grafana default :3000 is taken.**
  - No prometheus/grafana/exporter binaries, services, or containers (only docker
    `engram-postgres` pgvector on `127.0.0.1:54329` and `open-webui-openclaw`).
- **Packages:** `apt` has `prometheus 2.45.3+ds` and `prometheus-postgres-exporter 0.15.0`
  (both universe). **Grafana has NO apt candidate** → use Grafana's official APT repo
  (`apt.grafana.com`) for a maintained systemd unit, or Docker.
- **pg_hba** (`/etc/postgresql/17/main/pg_hba.conf`): `local … peer`; `host …127.0.0.1/32
  scram-sha-256`. So the exporter over TCP-localhost needs a **scram password role**; over the
  socket needs **peer** (matching OS user).
- **Monitoring DB role already exists:** `proximal_monitor` — `NOLOGIN`, member of `pg_monitor`.
  Create a *login* role for the exporter and `GRANT proximal_monitor TO <role>` (it inherits
  full `pg_stat_*`/settings read). `pgstattuple` is available-but-not-installed; `pg_repack`
  1.5.3 is installed.

## Port plan (defaults collide — use these)

| service | default | use on this box | why |
|---|---|---|---|
| postgres_exporter | 9187 | **9187** (free) | ok |
| Prometheus | 9090 | **9091** (`--web.listen-address`) | 9090 = cockpit |
| Grafana | 3000 | **3002** (`http_port`, verify free) | 3000/3001 taken |

## Recommended approach

1. **Exporter PG role + secret.** Create login role (e.g. `postgres_exporter`), `GRANT
   proximal_monitor TO postgres_exporter;` set a generated scram password. Put the DSN in a
   **root-only `0600`** systemd `EnvironmentFile` (e.g.
   `/etc/default/prometheus-postgres-exporter` →
   `DATA_SOURCE_NAME=postgresql://postgres_exporter:<pw>@127.0.0.1:5432/postgres?sslmode=disable`).
   **The password NEVER goes in the proximal-pg repo** (repo rule: no credentials). Document the
   role SQL *without* the password.
2. **postgres_exporter:** `apt install prometheus-postgres-exporter`; point its env at the DSN;
   confirm `curl -s localhost:9187/metrics | grep pg_up` → `pg_up 1`. Enable extra collectors
   for `pg_stat_statements` and add custom queries (below) via the exporter's query config.
3. **Prometheus:** `apt install prometheus`; set listen `:9091`; add scrape job
   `postgresql` → `localhost:9187`; `systemctl enable --now`; verify target UP at
   `localhost:9091/targets`.
4. **Grafana:** install from `apt.grafana.com`; `http_port=3002`; enable; add Prometheus
   datasource `http://localhost:9091`; import a postgres_exporter dashboard (e.g. Grafana ID
   **9628**, verify vs exporter 0.15/PG17) + the node/instance basics. **Change the default
   admin password.**
5. **Exposure:** keep loopback, or publish via tailnet `100.85.100.81` like the box's other
   services — confirm with the user; don't bind `0.0.0.0` by default.

## What to actually graph/alert (domain knowledge from this session)

Beyond the stock dashboard, these are the live concerns on this cluster — add custom exporter
queries (`pg_total_relation_size`, `pg_stat_database`, etc.):
- **Supervisor-table bloat regrowth** — `process_supervisor_pointers` / `process_supervisors` /
  `daemon_supervisors` size over time (regrows 2.5 MB→150 MB in ~90 min under load, plateaus
  ~150–255 MB). Ties to `striatum#421` + the `pg-repack-bloated.timer`. A graph here validates
  the monthly repack and would catch a runaway.
- **Deadlocks** on `striatum_daemon` (`pg_stat_database.deadlocks`, ~10/2 days baseline) and
  **long transactions** near `transaction_timeout=120s` (the 57014 family).
- Cache hit ratio (~99.9 % baseline), temp files (0 = healthy), connections vs `max=100`
  (peak ~19), checkpoints (`pg_stat_checkpointer.num_requested` should stay ~0 — validates
  `max_wal_size=16GB`), XID wraparound age (~1.4 %).
- Top queries: needs the exporter's `pg_stat_statements` collector (loaded in `striatum_daemon`
  1.11). `pg_stat_kcache` (per-query CPU) is currently only in the `postgres` DB — optional
  `CREATE EXTENSION pg_stat_kcache` in `striatum_daemon` to expose it there.

## Provenance / conventions (must follow)

- Repo: `~/git/proximal-pg` (origin `github.com/halbritt/proximal-pg`). It already has a
  `maintenance/` dir (the `pg-repack-bloated.{sh,service,timer}` + README) — add the
  observability units/config/role-SQL there (e.g. `maintenance/observability/`). Mirror the
  canonical copies in the repo, install copies on the box, document in `CHANGELOG.md`
  (newest-first). **Commit and push often; never commit secrets** (`AGENTS.md`).
- `connection.md` already flags the monitoring-role need — now satisfied by `proximal_monitor`;
  update it with the exporter role once created.

## Already done this session (reference, do NOT redo) — all committed & pushed to `master`

- PG 17.10 verification of 7 mined recs; `proximal_monitor` role created; `pg_stat_statements`
  reset (window from 2026-06-17 23:51 UTC). Report: `reports/RECS_VERIFICATION_2026-06-17.md`.
- `pg_repack` 1.5.3 installed; 4 bloated tables reclaimed (~454 MB);
  `pg-repack-bloated.timer` (monthly) installed + enabled.
  Report: `reports/REPACK_supervisor_tables_2026-06-18.md`.
- Upstream issues filed: `striatum#386` (unindexed FKs), `#387` (partitioning), `#421`
  (reconcile-loop write amplification / bloat root cause).

## Verification (definition of done)

`pg_up 1` at `:9187` → Prometheus `postgresql` target UP at `:9091/targets` → Grafana
dashboard renders live PG data at `:3002`, admin password changed, all under systemd
(`systemctl is-enabled`), bind/exposure confirmed with user, repo updated (no secrets) + pushed.

## Suggested skills for the next agent

- **`verify`** — confirm the stack end-to-end (exporter scraped, target UP, dashboard renders
  live data) by actually hitting the endpoints, not just installing.
- **`diagnose`** — if the exporter can't auth (pg_hba/scram), Prometheus won't scrape, or a
  panel is empty: reproduce → instrument → fix.
- **`update-config`** — only if any of this should be wired into Claude Code settings/hooks
  (e.g. an alert relay); otherwise the work is direct apt/systemd/psql.
- Skipping `to-issues`/`triage`/striatum skills — not relevant to this infra task.
