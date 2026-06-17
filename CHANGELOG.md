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
- **`pg_qualstats` 2.1 + `pg_stat_kcache` 2.2.3 — ENABLED** (2026-06-16): added to
  `shared_preload_libraries` (via the bundled restart) and `CREATE EXTENSION`'d in
  postgres + template1. Views live; query-level predicate stats + real OS CPU/I-O
  attribution now available on top of `pg_stat_statements`.
- Revert for all of the above: `ALTER SYSTEM RESET <param>` + reload (default prior).
### Backups / PITR (pgBackRest → ZFS; see `backups.md`)
- Decided **against** routing backups through Garage — Garage has no storage classes /
  tiering (verified v2.3.0: multi-`data_dir` is capacity-weighted only, no hot/cold,
  no S3 storage-class placement), so an S3 indirection adds nothing for backups.
- Set up **pgBackRest 2.50 → `/nvr/pg-backups`** (ZFS dataset on the `nvr` pool;
  `recordsize=1M`, `compression=off`, postgres-owned). Stanza `proximal` **created**;
  `archive_command` **staged** (reload-applied, inert until `archive_mode=on`).
  Discovered `/dev/sda` is a live ZFS pool `nvr` (already holds `nvr/engram-backups`) —
  **not** wiped; added a dataset instead.
- ✅ **Bundled restart done (22:08 UTC):** `archive_mode=on` + `shared_preload_libraries
  = pg_stat_statements,pg_qualstats,pg_stat_kcache`. `pgbackrest check` passed (WAL
  pushed to repo) → **PITR live**. `pg_qualstats`/`pg_stat_kcache` extensions created
  (postgres + template1). **First full backup done** (`20260616-220907F`, ~3 min):
  37.9 GB database → **3.6 GB** repo (zstd ~10.5×), stanza status `ok`, retention
  applied. Encryption not yet enabled (recommended before off-site replication).
- ⚠️ **Incident during the restart** (~1–2 min downtime, no corruption — clean
  shutdown): `ALTER SYSTEM SET shared_preload_libraries='a,b,c'` mangled the comma-list
  into one double-quoted element → `FATAL: could not access file "…"`, server wouldn't
  boot. Recovered by hand-fixing `postgresql.auto.conf` to the plain comma form +
  restart. Logged in `known-bad.md` (don't set multi-value `GUC_LIST_QUOTE` params via
  `ALTER SYSTEM`).
- **Off-site (2026-06-17): restic → GCS Nearline.** restic 0.16.4 backs up
  `/nvr/pg-backups` + `/nvr/engram-backups` to `gs://proximal-backups` (Nearline,
  us-west1, project `heath-stuff`), **encrypted client-side**. SA `restic-proximal`
  (Storage Object Admin scoped to the bucket); creds + repo password root-only at
  `/etc/restic/` (NOT in git). Timers: daily backup (`forget` 7d/4w/6m) + monthly
  `prune`+`check`. First snapshot `e74b5e2a`: 5.83 GiB. Chose Nearline over Coldline —
  storage saving is pennies at this volume and Coldline's 90-day min penalises restic's
  prune churn (Nearline = 30-day). restic encryption also covers the earlier
  "encrypt before off-site" gap. See `backups.md`.
- **pgBackRest schedule live (2026-06-17):** systemd timers — `pgbackrest-diff.timer`
  daily 01:30 + `pgbackrest-full.timer` weekly Sun 01:00 (run as `postgres`), ordered
  before the 02:49 restic ship. Validated through the unit (diff
  `…_20260617-004654D`, 13 GB→1.2 GB, exit 0). **Backup chain now closed and
  self-sustaining:** PG → pgBackRest (full/diff + continuous WAL/PITR) → restic
  (encrypted, daily) → GCS Nearline. `zfs send` remains an alternative off-site path.

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
