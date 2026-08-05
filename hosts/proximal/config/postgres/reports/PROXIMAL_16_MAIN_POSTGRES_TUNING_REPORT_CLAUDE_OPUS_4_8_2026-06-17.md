# PostgreSQL query-level analysis — PROXIMAL_16_MAIN — 2026-06-17

**Author:** `CLAUDE_OPUS_4_8` · **Type:** analysis (lifts the three `cannot-measure → refuse`
knobs from the 2026-06-16 plan) · **Authority:** read-only analysis; **no change applied.**

Now that `pg_stat_statements` + `pg_qualstats` + `pg_stat_kcache` have collected on live
traffic (~hours since the 2026-06-16 22:08 restart), the knobs deferred as
`cannot-measure` are measurable. Verdict up front: **no GUC change is warranted — the
bottleneck is missing indexes (a schema surface, handed off), not server config.**

## Workload characterization (cluster, via pgss + kcache)

- **CPU-bound on cached data.** `striatum_daemon`: **737 s user CPU / 10 s sys vs only
  132 physical-read blocks** (pg_stat_kcache). ~100% `shared_blks_hit` on the hot path —
  the 32 GB `shared_buffers` holds the working set; almost no disk reads.
- **OLTP firehose.** Top by calls: supervisor SELECT (213k), three heartbeat UPDATEs
  (213k each, 0.1–0.26 ms), `append_event_row` (152k, 0.91 ms). Tiny, fast, frequent.
- **Top by total time:** the event-read `SELECT event_id, run_id, actor_session_id …`
  — **31,931 calls × 37.3 ms = 1,190 s**, the single largest cost, 100% cached.
- **Zero `work_mem` spills** cluster-wide (`temp_blks_written = 0` for every statement).

## The three refused knobs — now measured

| knob | current | measurement | verdict |
|---|---|---|---|
| `work_mem` | 256 MB | 0 temp spills anywhere; OLTP workload does no large sort/hash; kcache shows no memory pressure | **No change needed.** Oversized for the workload but harmless (unused). The 2026-06-16 headroom worry (`100 × 256 MB`) is *unrealized* — peak work_mem use is ~0. Optional: lower to ~64 MB for defense-in-depth (zero perf cost). |
| `random_page_cost` | 4.0 | **EXPLAIN-proven no-op:** the hot query's plan is byte-identical at rpc 4 vs 1.1 (no index to switch to); +132 physical reads total ⇒ near-zero random I/O to mis-cost | **No change.** Would only matter *after* the indexes below exist, and even then marginal given full-cache. Not a standalone win. |
| `effective_io_concurrency` | 1 | 132 physical-read blocks total on the busy DB ⇒ nothing to prefetch | **No change.** No measurable benefit for an all-cached workload. |

**Net: no `postgresql.conf`/GUC change recommended.** Durability and the verified
2026-06-16 changes (`max_wal_size=16GB`, `pg_stat_statements`) stand.

## The actual bottleneck (out of scope for GUC tuning → handed off)

Missing indexes. CPU is burned on **sequential scans of cached tables** the planner has
no index for. Evidence (hypopg, no DDL built):

- **`striatumd.events (actor_session_id, run_id, event_type)`** — the #1 query
  (1,190 s total). Current plan: **Parallel Seq Scan of 1,012,715 rows, cost ≈
  1,218,979, every call.** With the hypothetical index: **Index Scan, cost 8.08**
  (~150,000× planner-cost reduction; 37 ms → sub-ms). **Highest-value fix on the box.**
- **`striatumd.audit_log (ts)`** — `SELECT max(ts)` does a **791,000-block full scan**
  (no index on `ts`); a btree makes it O(1).
- **`pg_qualstats_index_advisor` also suggests:** `client_capabilities (client_id)`,
  `(repository_id)`, `(capability)`; `leases (resource_id)`;
  `process_supervisors (session_id)`; `job_recovery_state (repository_id, job_id)`,
  `(run_id)`.

These are **application schema changes** — they belong in the `striatum` repo, not in
this cluster's server config (`POSTGRES_TUNING` scope rule: name index/query problems
and hand them off). Recommend filing them against `halbritt/striatum`. Until they land,
no GUC tuning will move the needle — the win is the indexes.

## Residual / notes

- The big `events`/`audit_log` full scans (`max()`/`count()`) appeared as 1-call queries
  — if they run periodically (housekeeping), the index wins compound.
- `hippo` analytical `DISTINCT` queries (96k/87k blocks, cached) are the only non-OLTP
  pattern; still 0 spills, so `work_mem` is not constraining them.
