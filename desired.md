# Desired-state config

The canonical GUC set `proximal:5432` should run, as `ALTER SYSTEM` statements.
The live config converges to this; drift from it is a finding. Every line carries
a rationale and points at the report that justified it.

Verified changes land here once a `reports/` record confirms them and a revert
exists. Live config should converge to this set.

```sql
-- P1: ~90% WAL-triggered checkpoints (req 3445 vs timed 393) -> time-driven.
-- VERIFIED 2026-06-16: loaded-window canary = 0 requested / 6 timed checkpoints,
-- 70 MB WAL/window << 16 GB. reports/canary-P1-max_wal_size-2026-06-16.md
-- Revert: reports/rollback-P1-max_wal_size-2026-06-16.sql
ALTER SYSTEM SET max_wal_size = '16GB';

-- R1: enable query-level signal (pg_stat_statements). Restart-class.
-- VERIFIED 2026-06-16: view queryable post-restart. Revert: RESET + restart.
-- reports/PROXIMAL_16_MAIN_POSTGRES_TUNING_PLAN_CLAUDE_OPUS_4_8_2026-06-16.md
-- PENDING (next restart): add pg_qualstats + pg_stat_kcache (pkgs installed, libs on disk):
--   ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements,pg_qualstats,pg_stat_kcache';
ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';

-- Observability / diagnosis (2026-06-16, reload-class, applied; revert = RESET each):
ALTER SYSTEM SET session_preload_libraries = 'auto_explain';
ALTER SYSTEM SET auto_explain.log_min_duration = '500ms';  -- plans for slow stmts only
ALTER SYSTEM SET auto_explain.log_analyze = off;           -- off: log_analyze instruments every stmt
ALTER SYSTEM SET auto_explain.log_nested_statements = on;  -- see plans inside SD functions
ALTER SYSTEM SET log_lock_waits = on;                      -- diagnose striatum lock contention
ALTER SYSTEM SET log_temp_files = 0;                       -- catch work_mem spills (feeds re-eval)

-- Backups / PITR (pgBackRest -> nvr/pg-backups). See backups.md.
ALTER SYSTEM SET archive_command = 'pgbackrest --stanza=proximal archive-push %p';  -- applied (reload)
-- PENDING (next restart, bundled with the shared_preload_libraries change above):
--   ALTER SYSTEM SET archive_mode = on;
```

## Frozen — never weakened without a recorded waiver

`fsync`, `full_page_writes`, `synchronous_commit` (on a primary), `wal_level`.
