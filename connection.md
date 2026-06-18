# Connection

How to reach the PostgreSQL instance on **proximal**. **No passwords here** — use
`~/.pgpass` or `PG*` environment variables for credentials.

| field | value |
|---|---|
| host | `localhost` (proximal; also LAN `192.168.1.92`, tailnet `100.85.100.81`) |
| port | `5432` (listening `127.0.0.1:5432` + unix socket `/var/run/postgresql/.s.PGSQL.5432`) |
| version | PostgreSQL 17.10, cluster `17/main`, `system_identifier 7652478211804703267` |
| topology | standalone primary (`pg_is_in_recovery()=false`, no slots/standbys) |

> Upgraded PG 16.14 → 17.10 on 2026-06-16/17 (pg_upgrade — note the **new
> `system_identifier`**; the old PG16 cluster was `7628053153555146077`). See
> `reports/PG17_UPGRADE_ASRUN_2026-06-17.md`.

## Databases (confirmed 2026-06-17, post-upgrade)

`striatum_daemon` (busiest, 27 GB — down from 34 GB after the 57014 bloat reclaim),
`hippo` (3455 MB, pgvector 0.8.2), `engram` (941 MB, pgvector 0.8.2), newer `praxis`
and `token_dashboard` (~8–10 MB each), `ob1`, `engram_test` + `engram_test_worker_*`
(test), transient `striatum_pgtest_*`, `postgres`. The maintenance/inventory DB is
`postgres`.

## Roles (confirmed 2026-06-16)

| role | use | notes |
|---|---|---|
| `halbritt` | inventory + admin | non-superuser; `createrole`+`createdb`; **peer auth** on the socket (no password). Used for inventory/read-only runs. **Now inherits `pg_monitor`** (via `proximal_monitor`, 2026-06-17) → reads full `pg_stat_*`, `pg_read_all_settings`, `pg_read_all_stats`. Still not a superuser (apply phase needs `postgres`). |
| `proximal_monitor` | read-only observability | `NOLOGIN` capability role, member of `pg_monitor`; granted into `halbritt`. No password. Created 2026-06-17 so inventory runs read full stats/settings without superuser. Revert: `REVOKE proximal_monitor FROM halbritt; DROP ROLE proximal_monitor;`. |
| `postgres_exporter` | metrics exporter | **LOGIN** role for the Prometheus `postgres_exporter` (created 2026-06-18). Inherits `proximal_monitor` → `pg_monitor` (read-only, no DDL/write). scram password; connects TCP `127.0.0.1:5432` → `striatum_daemon`. Secret lives only in `/etc/default/prometheus-postgres-exporter` (0600 root) — **not in this repo**; role SQL in `maintenance/observability/role.sql`. Revert: `DROP ROLE postgres_exporter;`. |
| `striatumd_rw` | striatum daemon app role | read/write against `striatum_daemon` (7 active backends observed). |
| `postgres` | superuser | OS-account peer auth: `sudo -u postgres psql`. The apply-phase / DDL role. |

For the inventory/evidence-gate phase, `halbritt` over the local socket is the
least-privileged path that can read `pg_settings`/`pg_stat_*`. The dedicated read-only
monitoring role `proximal_monitor` (member of `pg_monitor`) **was created 2026-06-17**
and granted into `halbritt`, so inventory runs now read `data_directory`, `sourcefile`,
and full `pg_stat_*` (incl. other roles' query text in `pg_stat_statements`) without
superuser. The apply phase needs a role that can run
`ALTER SYSTEM` + `pg_reload_conf()` (i.e. superuser or `pg_signal_backend` +
`ALTER SYSTEM` privilege); `halbritt` is **not** that role today.
