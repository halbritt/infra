# Changelog

Notable changes to the **proximal** PostgreSQL cluster's configuration and to this
provenance repo. Newest first. Config changes record the live cluster (`proximal:5432`,
`system_identifier 7628053153555146077`, PG 16.14); see `reports/` and `inventory/` for
the evidence behind each entry, and `git log` for granular history.

## 2026-06-16

### Config (live cluster)
- **`shared_preload_libraries` empty → `pg_stat_statements`** (R1). Staged via
  `ALTER SYSTEM`, applied by **restart** of `postgresql@16-main` at **19:14:59 UTC**
  (restart-class; instance was quiesced). Boot pre-validated (lib present). Extension
  `pg_stat_statements` 1.10 created in `postgres` + `template1`; view queryable
  (signal flowing — top statement by total time is `append_event_row`). Defaults
  `max=5000`, `track=top`. **Status: APPLIED, verified loaded.** Unblocks the three
  refused knobs (`work_mem` headroom, `random_page_cost`, `effective_io_concurrency`)
  once a representative query window accrues. Revert: `ALTER SYSTEM RESET
  shared_preload_libraries` + restart. `max_wal_size=16GB` confirmed to survive the
  restart.
- **`max_wal_size` 1 GB → 16 GB** (P1). Staged via `ALTER SYSTEM`, made live with
  `pg_reload_conf()` at **18:43:20 UTC** (reload-class, no restart, no dropped
  connections). Addresses ~90% WAL-triggered checkpoints (`checkpoints_req 3445` vs
  `timed 393`). **Status: APPLIED, VERIFIED** — loaded-window canary (2026-06-16):
  6 timed / 0 requested checkpoints, 70 MB WAL ≪ 16 GB; was 89.7% WAL-triggered.
  Promoted to `baseline.md` + `desired.md`. **P2 (`wal_compression`) closed — not
  needed** (WAL volume trivial; P1 resolved the bottleneck). bgwriter deferred (low
  pressure once checkpoints are time-driven). Revert:
  `reports/rollback-P1-max_wal_size-2026-06-16.sql` (drift-guarded, retained).
  Plan/canary:
  `reports/PROXIMAL_16_MAIN_POSTGRES_TUNING_PLAN_CLAUDE_OPUS_4_8_2026-06-16.md`,
  `reports/canary-P1-max_wal_size-2026-06-16.md`.

### Diagnostic tooling (ancillary; reload-class, no restart)
- **`auto_explain` enabled** via `session_preload_libraries` (built-in contrib, no
  install): logs plans for statements > 500 ms (`log_analyze=off` to avoid per-stmt
  overhead; `log_nested_statements=on`). New connections pick it up.
- **Diagnosis logging on:** `log_lock_waits=on` (striatum lock contention),
  `log_temp_files=0` (catch `work_mem` spills — feeds the deferred work_mem re-eval).
  `log_checkpoints` was already on.
- **Extensions created** (no preload needed): `hypopg` 1.4 (hypothetical-index testing
  for the deferred index/planner work) + `pgstattuple` in `postgres`/`striatum_daemon`/
  `hippo`/`engram`; `pg_buffercache` in `postgres`.
- **Installed, pending next restart** (need `shared_preload_libraries`):
  `pg_qualstats` 2.1, `pg_stat_kcache` 2.2.3 (libs on disk). Enable by adding both to
  `shared_preload_libraries` at the next restart window, then `CREATE EXTENSION` each.
- Revert for all of the above: `ALTER SYSTEM RESET <param>` + reload (default prior).
- **Deferred (not easy / needs infra):** backups — pgBackRest/WAL-G → Garage. Requires
  reconfiguring Garage onto the 10 TB spinning disk (`/dev/sda`); then replicate Garage
  off-site. `archive_mode` still `off` — no PITR yet. Planned, not done.

### Provenance / repo
- First read-only Preflight inventory captured (`CLAUDE_OPUS_4_8`, role `halbritt`,
  non-superuser, peer auth): `inventory/2026-06-16/` — full `pg_settings` dump (343 rows,
  24 non-default), config checksums, environment, workload signal, reliability frontier.
- `baseline.md` and `connection.md` populated from the inventory.
- Tuning plan written (P1 reload win, P2 `wal_compression`, R1 `pg_stat_statements`
  enablement, and `cannot-measure → refuse` for `work_mem` / `random_page_cost` /
  `effective_io_concurrency`).
- Remote created: `github.com/halbritt/proximal-pg` (private).

### Reliability frontier (inventory)
- Clear, no blockers: standalone primary (no slots/standbys), archiver clean, ~1 TiB
  free vs WAL, freeze age ~27.9 M ≪ 200 M, autovacuum current. Durability invariants
  intact (`fsync`/`full_page_writes`/`synchronous_commit` on, `wal_level=replica`).

### Deferred findings (handed off — not config)
- **`striatum_daemon` authority gate hard-fails `append_event_row`** (≥517k
  `daemon authority secret missing` errors, ongoing) → `halbritt/striatum#329`.
  Details: `inventory/2026-06-16/deferred-findings.md`.

### Known limitations carried forward
- ~~`pg_stat_statements` not loaded~~ → **resolved same day by R1** (above); query
  signal now flowing. The three refused knobs still need a representative query window
  before they can be re-evaluated.
- Inventory ran as non-superuser; a `pg_monitor` read-only role is recommended before
  the next run (see `connection.md`).
