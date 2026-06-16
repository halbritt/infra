# Changelog

Notable changes to the **proximal** PostgreSQL cluster's configuration and to this
provenance repo. Newest first. Config changes record the live cluster (`proximal:5432`,
`system_identifier 7628053153555146077`, PG 16.14); see `reports/` and `inventory/` for
the evidence behind each entry, and `git log` for granular history.

## 2026-06-16

### Config (live cluster)
- **`max_wal_size` 1 GB → 16 GB** (P1). Staged via `ALTER SYSTEM`, made live with
  `pg_reload_conf()` at **18:43:20 UTC** (reload-class, no restart, no dropped
  connections). Addresses ~90% WAL-triggered checkpoints (`checkpoints_req 3445` vs
  `timed 393`). **Status: APPLIED, canary pending** — checkpoint-ratio delta needs a
  representative write window; `baseline.md`/`desired.md` not updated until verified.
  Revert: `reports/rollback-P1-max_wal_size-2026-06-16.sql` (drift-guarded).
  Plan/canary: `reports/PROXIMAL_16_MAIN_POSTGRES_TUNING_PLAN_CLAUDE_OPUS_4_8_2026-06-16.md`,
  `reports/canary-P1-max_wal_size-2026-06-16.md`.

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
- `pg_stat_statements` not loaded → no query-level signal (blocks the three refused
  knobs). Enabling it is R1 (restart-class).
- Inventory ran as non-superuser; a `pg_monitor` read-only role is recommended before
  the next run (see `connection.md`).
