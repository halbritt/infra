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
