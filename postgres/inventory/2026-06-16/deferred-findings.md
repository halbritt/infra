# Deferred findings — 2026-06-16

Non-config findings surfaced by the read-only inventory that are **out of scope for
GUC tuning** (POSTGRES_TUNING.md: name it and hand it to the right surface). Recorded
here for provenance; the fix lives in another repo.

## DF-1 — `striatum_daemon`: authority gate hard-fails every `append_event_row`

- **Surface:** application (Go daemon write path) — **not** a PostgreSQL config issue.
- **Filed:** [`halbritt/striatum#329`](https://github.com/halbritt/striatum/issues/329).
- **What:** `striatumd.assert_daemon_authority()` raises `daemon authority secret
  missing` (SQLSTATE `28000`) on every `append_event_row` call — the per-transaction
  GUC `striatum.daemon_auth` is empty on that code path.
- **Scale (this host's PG logs):** ≥ 517,389 occurrences, exclusively
  `striatumd_rw@striatum_daemon`, since at least 2026-06-04, ongoing at ~0.6/s. It is
  the single dominant line in the server log.
- **Diagnosis:** `missing`, never `mismatch` (the secret is never presented, not
  mis-rotated); registry `striatumd.daemon_auth_registry` is healthy (7 instances,
  newest rotated 2026-06-16 16:33); only `append_event_row` is affected.
- **Why it matters here:** correlates with this DB's reliability noise also seen in the
  inventory — 74 `deadlock detected`, 184 lock-timeout cancels, ~6% rollback rate
  (110k/1.75M). Aborted event-append txns are a plausible contributor. Pure-config
  tuning cannot fix it; tracked upstream.

Evidence: `workload-signal.txt` (deadlocks/rollbacks), `reliability-and-autovacuum.txt`,
and the PG server log on proximal (`/var/log/postgresql/`).

## DF-2 — `striatum_daemon`: missing indexes (CPU burned on seq scans of cached tables)

- **Surface:** application schema (index DDL) — **not** a server-config issue. Found
  2026-06-17 via `pg_stat_statements`/`pg_qualstats`/`pg_stat_kcache`. **Filed:**
  [`halbritt/striatum#330`](https://github.com/halbritt/striatum/issues/330). Full analysis:
  `reports/PROXIMAL_16_MAIN_POSTGRES_TUNING_REPORT_CLAUDE_OPUS_4_8_2026-06-17.md`.
- **What:** the busiest DB is CPU-bound on cached data (737 s CPU vs 132 physical-read
  blocks). The #1 query by total time (1,190 s) **seq-scans all 1.01M `events` rows
  every call**; a `(actor_session_id, run_id, event_type)` index drops the planner cost
  from ~1,218,979 to **8.08** (hypopg-proven, ~150,000×). `audit_log` has no index on
  `ts` → `max(ts)` is a 791k-block full scan.
- **Recommended indexes** (advisor + analysis, to apply in `striatum_daemon`):
  `events (actor_session_id, run_id, event_type)` ⟵ biggest win; `audit_log (ts)`;
  `client_capabilities (client_id)`/`(repository_id)`/`(capability)`;
  `leases (resource_id)`; `process_supervisors (session_id)`;
  `job_recovery_state (repository_id, job_id)`/`(run_id)`.
- **Why it matters here:** no GUC change moves this — the three `cannot-measure` knobs
  (`work_mem`/`random_page_cost`/`effective_io_concurrency`) all measured out as
  non-levers for an all-cached OLTP workload. The indexes are the win. Hand off to
  `halbritt/striatum` (managed by its owner-bundle migrations, like the auth schema).
