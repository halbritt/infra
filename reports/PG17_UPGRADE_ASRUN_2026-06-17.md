# PostgreSQL 16 → 17 upgrade — AS-RUN record (proximal:5432)

- **Date:** 2026-06-17 · **Outcome:** ✅ **PostgreSQL 17.10 live**, `striatum_daemon` and all
  9 databases upgraded; 16/main preserved (down on 5433) as the rollback.
- **Companion docs:** plan `reports/PG17_UPGRADE_PLAN_2026-06-17.md`; CHANGELOG entry
  "MAJOR UPGRADE EXECUTED"; the contention work that motivated it,
  `reports/INCIDENT_57014_append_event_row_lock_contention_2026-06-17.md`.
- **Why:** currency + **PG 17 `transaction_timeout`**, the durable server-side cap on total
  transaction duration that PG 16 lacks — the real backstop for the striatum#198/#355
  runaway-transaction class (DB-side `lock_timeout`/`idle_in_transaction` can't bound an
  *actively-busy* runaway txn).

## Final verified state (22:13 UTC)

| check | result |
|---|---|
| version on 5432 | **PostgreSQL 17.10** (`17.10-1.pgdg24.04+1`) |
| clusters | `17/main` online :5432 · `16/main` **down :5433** (rollback preserved) |
| DB-scoped GUCs (`striatum_daemon`) | `statement_timeout=600s, lock_timeout=3s, idle_in_transaction_session_timeout=15s, transaction_timeout=120s` |
| `transaction_timeout` | landed **and fire-tested** (2 s test → "terminating connection due to transaction timeout") |
| `pg_hba` `striatum-lane` reject rules | present (lines 121–123) — lane isolation intact |
| `shared_preload_libraries` | `pg_stat_statements,pg_qualstats,pg_stat_kcache` loaded |
| roles | **26** (was 37,700) |
| event appends | flowing; **0** `permission denied` since 21:33:19 (last error pre-fix) |
| `repo_event_chain_heads` ACL | `postgres=arwdDxtm`, `striatumd_rw=arw`, **`halbritt=arw`** (the fix) |
| backups | pgBackRest 2.58, stanza `proximal` `status: ok`, archiving to `17-2/` |
| extensions | pgvector **0.8.2** (engram/hippo/engram_test*); contrib updated to 17 |
| apt | PG stack `apt-mark hold`-pinned (no accidental PG 18) |

## Timeline (UTC)

| time | event |
|---|---|
| 20:01:48–20:03:42 | **Phase 0 backup** — pgBackRest full `20260617-200148F` (31 GB), the rollback anchor |
| 20:05:40 | striatumd **stopped** (window 1 begins; `KillMode=process` → lanes survive) |
| ~20:05 | `apt install postgresql-17` + extensions (16/main untouched; 0 removed) |
| 20:06:19 | **Attempt 1**: `pg_upgradecluster -m upgrade 16 main` begins |
| 20:06–21:12 | globals restore **crawls ~1 h** through **37,675 `*_pgtest_*`/`boot2_*` roles** |
| 21:12:45 | **Attempt 1 FAILS** — `pg_largeobject` missing file in transient test DB OID 127575054; pg_upgrade auto-removes the new cluster and **restarts 16/main** (clean rollback, no data touched) |
| ~21:17 | striatumd restarted on 16 → **service restored**; PG16 stack re-held |
| 21:18–21:22 | **Root-cause cleanup (online, no downtime):** dropped all **37,675 junk roles in 63 s** (0 `pg_shdepend` deps); per-DB `pg_largeobject` integrity check — all 9 OK; 0 transient pgtest DBs |
| 21:23:46 | striatumd **stopped** (window 2 begins) |
| 21:24:38 | **Attempt 2 SUCCEEDS in 52 s** — globals instant (25 roles), 31 GB copy fast; 17/main online :5432, 16/main → :5433 |
| 21:26:26 | striatumd restarted on PG 17 |
| 21:26:51 | pgBackRest `pg1-path` repointed `…/16/main`→`…/17/main`; `stanza-upgrade` + `check` OK |
| ~21:27 | config verified carried; `ALTER DATABASE … SET transaction_timeout='120s'` |
| 21:26–21:33 | **event appends failing** `permission denied for repo_event_chain_heads` (post-cutover) |
| ~21:31 | `GRANT SELECT,INSERT,UPDATE ON repo_event_chain_heads TO halbritt` |
| ~21:33:45 | striatumd restarted (refresh cached plans) → **appends resume; last error 21:33:19** |
| 21:35–21:36 | pgvector 0.8.2 update (5 DBs); contrib extensions updated; stack re-pinned |

**Downtime, honestly:** window 1 (failed attempt) kept striatumd down **~71 min** — almost
entirely the 37,675-role globals crawl. Window 2 (successful) was **~2.7 min** daemon-down,
plus **~7 min degraded** (daemon up, reconciling, but appends failing) until the grant+restart.
The supervised lanes/tmux sessions survived the whole time (`KillMode=process`); the run paused
at `needs_branch_confirmation` and was not lost.

## Blockers & resolutions (root causes — all striatum cruft or carry-over gaps)

1. **37,675 abandoned pgtest roles** (`*_pgtest_*`, `boot2_*`) — striatum's pgtest harness
   never drops its per-run roles. pg_upgrade restores globals single-threaded → ~1 h crawl.
   **Fix:** dropped online in 63 s (autocommit per role; a single txn hit
   `max_locks_per_transaction`). 0 dependencies, so plain `DROP ROLE` sufficed.
2. **Broken transient test DB** (OID 127575054, missing `pg_largeobject` file) aborted the
   file copy. Already gone by the retry. Same ephemeral-test-DB class as `engram_test*`.
   **Fix/guard:** verified every DB's `pg_largeobject` readable before retrying.
3. **pgBackRest `pg1-path` hardcoded to `…/16/main`** — pg_upgradecluster doesn't touch
   external tool config. **Fix:** `sed` it to `…/17/main`, then `stanza-upgrade`.
4. **SECURITY DEFINER append broke** — `append_event_row` (owner halbritt) accesses
   `repo_event_chain_heads` (owner postgres). On 16 halbritt reached it by **inheriting**
   `striatumd_rw`'s grant (halbritt is a member); PG16 per-grant `INHERIT` semantics didn't
   carry through pg_upgrade, so the inherited privilege vanished. **Fix:** explicit
   `GRANT … TO halbritt` (mirrors `striatumd_rw=arw`) + daemon restart to drop cached pllpgsql
   plans on the pooled connections.

## Rollback (still available)

16/main is intact on :5433 plus the Phase-0 backup + WAL. To revert: stop striatumd + 17/main,
`pg_dropcluster 17 main`, repoint pgBackRest `pg1-path` to `…/16/main`, start 16/main on :5432,
restart striatumd. (Any writes made on 17 post-cutover would be lost — acceptable given the run
was parked.) Drop 16/main only once 17 is trusted (`pg_dropcluster 16 main` / the generated
`delete_old_cluster.sh`).

## App-side follow-ups (handed to halbritt/striatum)

- **Make the `repo_event_chain_heads` grant explicit in the schema** (`GRANT … TO` the
  SD-function owner) — don't rely on PG16 inherited membership; it breaks on major upgrade.
- **pgtest harness must clean up** its per-run roles and ephemeral databases. 37k roles is a
  real catalog/upgrade hazard (and was the entire first-attempt downtime).
- Optional DB polish: `REINDEX` the two pgvector HNSW indexes (engram 44 MB, hippo 350 MB) for
  0.8; `ALTER DATABASE`-level `transaction_timeout` could later be scoped per-role if 120 s is
  ever too tight for a legitimate long job.
