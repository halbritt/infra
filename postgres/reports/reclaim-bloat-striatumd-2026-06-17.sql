-- Bloat reclamation for striatum_daemon hot tables (incident 57014, 2026-06-17).
-- RUN ONLY with the striatumd daemon STOPPED (no runaway txns pinning xmin, no
-- concurrent writes). VACUUM FULL takes ACCESS EXCLUSIVE and rewrites the table +
-- rebuilds indexes; it also applies the new fillfactor set on 2026-06-17.
--
-- Pre-2026-06-17 sizes: pointers 6.36 GB, daemon_supervisors 2.45 GB,
-- process_supervisors 2.23 GB, repo_event_chain_heads 267 MB (all ~50–99% dead).
-- Expected to return ~11 GB. events/audit_log are NOT included (legitimately large
-- append-only; let aggressive insert-autovacuum maintain them).
--
-- Run as halbritt (owns 3 of these) for the first three; run repo_event_chain_heads
-- as postgres (owned by 'postgres').  Total expected downtime ~2–3 min.

\timing on

-- as halbritt:  psql "postgres://halbritt@/striatum_daemon?host=/var/run/postgresql" -f this.sql
VACUUM (FULL, ANALYZE, VERBOSE) striatumd.process_supervisor_pointers;
VACUUM (FULL, ANALYZE, VERBOSE) striatumd.daemon_supervisors;
VACUUM (FULL, ANALYZE, VERBOSE) striatumd.process_supervisors;

-- as postgres:  sudo -u postgres psql -d striatum_daemon -c "VACUUM (FULL, ANALYZE, VERBOSE) striatumd.repo_event_chain_heads;"
VACUUM (FULL, ANALYZE, VERBOSE) striatumd.repo_event_chain_heads;

-- After: confirm sizes collapsed and stats fresh.
SELECT c.relname, pg_size_pretty(pg_total_relation_size(c.oid)) AS total,
       s.n_live_tup, s.n_dead_tup, s.last_vacuum
  FROM pg_class c
  JOIN pg_namespace n ON n.oid=c.relnamespace
  JOIN pg_stat_user_tables s ON s.relid=c.oid
 WHERE n.nspname='striatumd'
   AND c.relname IN ('repo_event_chain_heads','process_supervisor_pointers',
                     'daemon_supervisors','process_supervisors')
 ORDER BY pg_total_relation_size(c.oid) DESC;
