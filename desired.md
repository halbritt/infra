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

-- Query-level signal: pg_stat_statements (R1) + pg_qualstats + pg_stat_kcache.
-- Restart-class. APPLIED 2026-06-16 (all three loaded; extensions created).
-- ⚠️ DO NOT set this multi-value via `ALTER SYSTEM SET = 'a,b,c'` — it double-quotes
--    the comma-string as ONE element and the server won't boot (see known-bad.md).
--    It currently lives in postgresql.auto.conf as the plain comma form below.
shared_preload_libraries = 'pg_stat_statements,pg_qualstats,pg_stat_kcache'

-- Observability / diagnosis (2026-06-16, reload-class, applied; revert = RESET each):
ALTER SYSTEM SET session_preload_libraries = 'auto_explain';
ALTER SYSTEM SET auto_explain.log_min_duration = '500ms';  -- plans for slow stmts only
ALTER SYSTEM SET auto_explain.log_analyze = off;           -- off: log_analyze instruments every stmt
ALTER SYSTEM SET auto_explain.log_nested_statements = on;  -- see plans inside SD functions
ALTER SYSTEM SET log_lock_waits = on;                      -- diagnose striatum lock contention
ALTER SYSTEM SET log_temp_files = 0;                       -- catch work_mem spills (feeds re-eval)

-- Backups / PITR (pgBackRest -> nvr/pg-backups). See backups.md.
ALTER SYSTEM SET archive_command = 'pgbackrest --stanza=proximal archive-push %p';  -- applied (reload)
ALTER SYSTEM SET archive_mode = on;  -- APPLIED 2026-06-16 (restart); PITR live, check passed
```

## Frozen — never weakened without a recorded waiver

`fsync`, `full_page_writes`, `synchronous_commit` (on a primary), `wal_level`.
