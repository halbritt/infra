# Read-only verification of the 7 mined best-practice recommendations — 2026-06-17

**Author:** `CLAUDE_OPUS_4_8` · **Type:** verification pass · **Authority:** read-only
(`SELECT`/`EXPLAIN` only); **no change applied, no `ALTER` issued.**
**Cluster:** PostgreSQL **17.10**, `17/main`, `system_identifier 7652478211804703267`,
standalone primary (`pg_is_in_recovery()=false`, 0 slots, 0 standbys).
**Role:** `halbritt` over the local socket (peer auth; **not** superuser, **not** in
`pg_monitor`/`pg_read_all_stats`).
**Source of recommendations:** `reports/SUPABASE_PG_BEST_PRACTICES_MINED_2026-06-17.md`.

Verdict up front: **two recommendations were falsified as non-levers for this workload**
(#2 work_mem, and #3's premise), **one passed clean** (#5 timeouts), **one was already
done** (#6 HNSW reindex), and **#3's own audit query is buggy** — it over-reports. The
real structural gaps (#3/#4) are dormant today and are striatumd-owned schema → upstream.

| # | recommendation | verdict | one-line result |
|---|---|---|---|
| 1 | first pg_stat_statements baseline | **COMPLETE** | created `proximal_monitor` role → de-masked the daemon hot path (heartbeats + `append_event_row`) |
| 2 | re-measure work_mem headroom | **FALSIFIED → no change** | 0 temp spills, peak concurrency far below ceiling |
| 3 | unindexed-FK audit | **FALSIFIED (dormant) + query bug** | 41 truly-uncovered (not 62/90); all NO ACTION, **0 parent deletes** → no active cost |
| 4 | partitioning candidates | **CONFIRMED as future lead** | events 13.8M/18GB, audit_log 17.1M/8.6GB; append-only; upstream |
| 5 | timeout backstops at DB scope | **PASS** | all four present & DB-scoped on `striatum_daemon` |
| 6 | REINDEX HNSW indexes | **DONE** (commit `c0269b7`) | both HNSW indexes present on pgvector 0.8.2 |
| 7 | append_event_row owner grant | n/a here | app-side (`halbritt/striatum`); not a DB-config item |

---

## #1 — pg_stat_statements baseline — COMPLETE

`pg_stat_statements` 1.11 is live in `striatum_daemon` (also 1.10 in `postgres`).
`stats_reset = 2026-06-17 21:23:52 UTC`; **4,915** distinct statements, **686,402** calls.

**Resolved the masking limitation:** created `proximal_monitor` (`NOLOGIN`, member of
`pg_monitor`) and granted it into `halbritt`, so the daemon's (`striatumd_rw`) query text is
now visible without superuser. Created via `sudo -u postgres`; recorded in `connection.md`.
De-masked top of the hot path (by total time):

| query | calls | mean ms | total ms |
|---|---|---|---|
| `UPDATE process_supervisor_pointers SET updated_at …` | 517,450 | 1.31 | 678,025 |
| `SELECT ps.supervisor_id, ps.run_id, … (supervisor read)` | 520,395 | 1.10 | 571,747 |
| `SELECT striatumd.append_event_row(…)` | 518,177 | 0.95 | 493,790 |
| `UPDATE process_supervisors SET heartbeat_at …` | 517,456 | 0.63 | 325,827 |
| `UPDATE daemon_supervisors SET heartbeat_at …` | 517,448 | 0.59 | 307,294 |
| `SELECT pg_advisory_xact_lock(hashtext($1))` | 720 | 17.49 | 12,596 |

A call-volume-dominated OLTP firehose: supervisor heartbeats (pointers + supervisors +
daemon_supervisors ≈ 1.5M calls/window) and `append_event_row`, all sub-2 ms / ~100% cached —
identical in shape to the `PROXIMAL_16_MAIN_..._REPORT` characterization. The
`pg_advisory_xact_lock` calls (17 ms mean) are the slowest in the hot set — the per-repo
chain serialization points (intentional; see the mined report's lock-skip-locked note).
**Observation:** `process_supervisor_pointers` is the #1 total-time consumer (517k churned
`updated_at` UPDATEs) and is bloated (252 MB / 1,451 live rows) — the `fillfactor=80` +
aggressive-autovacuum tuning in `desired.md` (applied 2026-06-17) targets exactly this; worth
a follow-up check that autovacuum is keeping pace.
**Reset:** not performed — `pg_stat_statements_reset()` discards the accumulated window the
2026-06-17 tuning analysis relied on. Reset is an explicit operator choice, not done here.

## #2 — work_mem headroom — FALSIFIED → no change

- **0 queries with `temp_blks_written > 0`** in `striatum_daemon`. Nothing spills.
- Live concurrency: **8** daemon backends / 11 client total; historical peak 19/100.
- The `256 MB × 100 = 25.6 GB` ceiling worry is **unrealized** — peak work_mem use ≈ 0.

Re-confirms `desired.md`'s standing verdict: oversized but harmless; optional future lower
to ~64 MB for defense-in-depth at zero perf cost. **No change warranted; do not re-propose
without new evidence (a spill).**

## #3 — unindexed FK audit — FALSIFIED (dormant) + the audit query is buggy

**The recommendation's query is wrong.** Its `k.attnum = i.indkey[0]` test only checks the
*leading* index column, so it (a) over-flags trailing columns of composite FKs that are
already covered by a composite index, and (b) the obvious "fix" — slicing `indkey::smallint[]`
— is *also* wrong because `int2vector` casts to a **0-based** array (`(indkey::smallint[])[1:2]`
drops element 0). Correct left-prefix test uses `string_to_array(indkey::text,' ')`:

| method | "uncovered" FKs reported |
|---|---|
| recommendation's `indkey[0]`-only | 62 (over-reports — flags composite-covered FKs) |
| naive `::smallint[]` slice | 90 (broken — 0-based off-by-one) |
| **corrected `string_to_array` left-prefix** | **41** (12 on tables >1 MB) |

Ground-truthed on `events`: of its 7 FKs, `(repository_id,job_id)`→`idx_events_job` and
`(repository_id,run_id)`→`idx_events_run_time` and `repository_id` (PK leading col) **are**
covered; only `actor_session_id`, `artifact_id`, `lease_id`, `message_id` are genuinely
uncovered. The only material uncovered FKs (heap > 1 MB that would actually seq-scan):

- **`events`** (9.4 GB): `actor_session_id`, `artifact_id`, `lease_id`, `message_id`
- **`audit_log`** (6.2 GB): `segment_id`
- (smaller: `repo_event_chain_heads.last_event_id`, `sessions.parent_session_id`, a few <2 MB)

**But the premise is falsified — these are dormant.** Every uncovered FK is
`confdeltype='a'` (**NO ACTION**, *not* CASCADE), so the child-table seq scan only fires when
a **parent** row is deleted or its **referenced key** is updated. Measured on the parents
(`pg_stat_user_tables`, post-upgrade window):

| parent | live | **deletes** | updates | hot_upd |
|---|---|---|---|---|
| sessions | 2121 | **0** | 1416 | 1363 |
| leases | 1821 | **0** | 233 | 212 |
| jobs / queue_messages / runs | — | **0** | 27 / 22 / 2 | — |
| artifacts / audit_segments / repositories | — | **0** | 0 | 0 |

**Zero parent deletes**, and the updates are HOT updates to non-key status columns (the RI
trigger doesn't fire on those). So there is **no active seq-scan cost today** — like
`work_mem`, this is a structural shape, not a live fire. `repository_id` cardinality is only
**19**, so the moment retention/GC starts deleting parents, the repository_id-prefix fallback
scans ~700k events/parent-delete — *then* the indexes matter.

**Action:** raise upstream (`halbritt/striatum`, corroborating DF-2 / #330) so the indexes
land **before** any parent-deletion/retention job ships — but do not treat as a present
performance issue, and do not create indexes here (striatumd-owned schema). Note
`events(actor_session_id,…)` overlaps the #1 index already handed off in the 2026-06-17
tuning report — same column, two motivations (read path + FK enforcement).

## #4 — partitioning candidates — CONFIRMED as a future lead (upstream)

`events` 13.8M rows / 18 GB total (9.4 GB heap); `audit_log` 17.1M rows / 8.6 GB (6.2 GB
heap). Both append-only (0 deletes), insert-driven autovacuum already tuned in `desired.md`.
Below the ~100M-row rule of thumb today. Range-by-`created_at` partitioning would make
retention purges instant **and** sidestep the #3 FK-delete cliff entirely (drop a partition
instead of `DELETE`-ing rows that trigger child seq scans). Schema is striatumd-owned →
flag upstream; do not `ALTER` here.

## #5 — timeout backstops at DB scope — PASS

`pg_db_role_setting` for `striatum_daemon` carries all four, **DB-scoped** (survives the
daemon L0 bootstrap that wipes role GUCs):

```
lock_timeout=3s · idle_in_transaction_session_timeout=15s
transaction_timeout=120s (PG17, survived the upgrade) · statement_timeout=600s
```

`transaction_timeout=120s` is present and DB-scoped (not role-scoped) — the strongest
backstop against an `INCIDENT_57014` repeat. **No re-assert needed.**

## #6 — HNSW reindex — DONE

Confirmed complete (commit `c0269b7`; operator confirmed). Both HNSW indexes
(`segment_embeddings_nomic_768_hnsw_idx` in `hippo` and `engram`) present; `vector`
extension is **0.8.2** in both DBs. (`postgres` DB still carries a stale `vector 0.6.0` with
no real vector data — harmless.)

## #7 — append_event_row owner grant — app-side, not a DB-config item

`SECURITY DEFINER` owner-grant hardening belongs in the `striatum` schema
(`halbritt/striatum`), already tracked in CHANGELOG app-side follow-ups. Nothing to verify
or apply at the cluster-config layer.

---

## Bottom line

Nothing to apply to `postgresql.conf`/`desired.md` from this pass. #5 passes, #6 is done,
#2 and #3 are falsified as non-levers for the current workload, and #3's audit query should
be corrected wherever it's reused (it over-reports by ~50%). The two genuine structural
shapes (uncovered FKs + partitioning) are dormant, striatumd-owned, and belong upstream —
ideally landed before retention/GC introduces parent-row deletes. The one cluster change made
this session was additive and read-only by nature: the `proximal_monitor` role (so #1 could
be completed without superuser); recorded in `connection.md`.
