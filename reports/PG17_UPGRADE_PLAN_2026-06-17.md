# PostgreSQL 16 → 17 upgrade plan (proximal:5432) + pgvector / ancillary tooling

- **Date:** 2026-06-17
- **Cluster:** `proximal:5432`, PG **16.14** (Ubuntu distro build `16.14-0ubuntu0.24.04.1`),
  PGDATA `/var/lib/postgresql/16/main`, Ubuntu 24.04 (kernel 6.8)
- **Goal:** move to **PG 17.x** + **pgvector latest (0.8.x)** + refreshed ancillary
  extensions, with minimal, well-bounded downtime and a real rollback path.
- **Primary motivation (beyond currency):** PG 17 adds **`transaction_timeout`** — the
  durable, server-side cap on *total* transaction duration that PG 16 lacks. This is the
  exact backstop for the long-running-transaction class behind
  `reports/INCIDENT_57014_append_event_row_lock_contention_2026-06-17.md` / striatum#355
  (the DB-side mitigations there — `lock_timeout`, `idle_in_transaction_session_timeout` —
  cannot bound an *actively-busy* runaway txn; `transaction_timeout` can). Landing PG 17
  closes that gap from the server side.

> **Status: PLAN ONLY.** Nothing here has been executed. No services touched.

## Current-state inventory (measured 2026-06-17)

| item | value |
|---|---|
| Server | PG 16.14, Ubuntu universe package (**not PGDG**) |
| PGDATA / size | `/var/lib/postgresql/16/main`, **31 GB** on disk; **1.0 TB free** on `/` (same fs) |
| Databases (9) | `striatum_daemon` 26 GB, `hippo` 2.98 GB, `engram` 941 MB, `engram_test*` (3, ephemeral), `praxis` 10 MB, `postgres`, `ob1` 8 MB |
| Encoding/locale | UTF8 / `en_US.UTF-8` (all) |
| Replication | **no slots, no standbys** → single-node, simple upgrade |
| `shared_preload_libraries` | `pg_stat_statements,pg_qualstats,pg_stat_kcache` |
| WAL / archiving | `wal_level=replica`, `archive_mode=on`, pgBackRest `archive-push` |
| Backups | pgBackRest **2.58** (upgraded 2026-06-17 from 2.50), stanza `proximal` (status ok), full 20260616 (3.6 GB repo) + diffs; restic → GCS Nearline off-site |
| Upgrade tooling | `/usr/bin/pg_upgradecluster` (Debian wrapper) + `/usr/lib/postgresql/16/bin/pg_upgrade` present |

### Extensions in use (carry-forward matrix)

| extension | current | source | PG17 package | notes |
|---|---|---|---|---|
| **vector (pgvector)** | **0.6.0** | `postgresql-16-pgvector` (Ubuntu) | `postgresql-17-pgvector` (PGDG, **0.8.x**) | HNSW indexes in `engram` + `hippo` (`segment_embeddings_nomic_768_hnsw_idx`, 768-dim); also `embedding_cache`/`segment_embeddings` vector cols. In 8 DBs. |
| pg_stat_statements | 1.10 | contrib | `postgresql-contrib`/`-17` | in `shared_preload_libraries` |
| pg_qualstats | 2.1.0 | `postgresql-16-pg-qualstats` | `postgresql-17-pg-qualstats` (PGDG) | preload |
| pg_stat_kcache | 2.2.3 | `postgresql-16-pg-stat-kcache` | `postgresql-17-pg-stat-kcache` (PGDG) | preload |
| hypopg | 1.4.0 | `postgresql-16-hypopg` | `postgresql-17-hypopg` (PGDG) | |
| pgcrypto / pgrowlocks / pgstattuple | 1.3 / 1.2 / 1.5 | contrib | `-17` contrib | |

### Two blocking prerequisites discovered

1. ✅ **DONE 2026-06-17 — PGDG apt repo wired up.** Key `/usr/share/keyrings/postgresql.gpg`,
   source `/etc/apt/sources.list.d/pgdg.list` (`noble-pgdg main`), `apt update` clean.
   Now available (nothing installed): `postgresql-17` **17.10**, `postgresql-17-pgvector`
   **0.8.2**, `postgresql-17-pg-qualstats` 2.1.3, `postgresql-17-pg-stat-kcache` 2.3.1,
   `postgresql-17-hypopg` 1.4.2, `pgbackrest` **2.58.0**. ⚠️ Enabling PGDG armed an
   `apt upgrade` foot-gun (would pull PGDG `postgresql-16-pgvector 0.6→0.8` over the *live*
   cluster + try to bring PG 18); mitigated by `apt-mark hold` on the running PG16 stack
   (`postgresql postgresql-16 postgresql-client-16 postgresql-common postgresql-client-common
   libpq5 pgbackrest postgresql-16-{pgvector,pg-qualstats,pg-stat-kcache,hypopg}`).
   **`apt-mark unhold` these at the start of the upgrade window.**
2. ✅ **DONE 2026-06-17 — pgBackRest upgraded 2.50 → 2.58.0** (PG 17-capable; landed in
   2.53). Done ahead of the window since 2.58 is backward-compatible with PG 16. Validated
   live: stanza `proximal` `status: ok`, existing backups intact, and `pgbackrest check`
   forced a WAL switch that archived successfully with the new binary. Re-pinned via
   `apt-mark hold pgbackrest`. **No pgBackRest action remains for the upgrade window** —
   only the post-upgrade `stanza-upgrade` (Phase 3) to register the new PG 17 cluster.

## Recommended method

**`pg_upgrade` in copy mode via the Debian wrapper** (`pg_upgradecluster --method=upgrade`),
**not `--link`**, **not dump/restore**.

- **Why copy (`--method=upgrade`) over `--link`:** at 31 GB with 1 TB free, the file copy
  costs only minutes but **leaves the old 16/main cluster fully intact and bootable** —
  rollback is "start the old cluster" rather than "restore from backup". `--link` hard-links
  the data files and renders the old cluster unusable the moment 17 starts; its only rollback
  is the backup. The copy is cheap insurance here. (`--link`/`--clone` remain the
  minimal-downtime fallback if the copy window is ever too long — it is not, at this size.)
- **Why not dump/restore:** would rebuild every index (incl. HNSW) and take far longer with
  no benefit at this scale; `pg_upgrade` preserves data files, catalogs, and
  `pg_db_role_setting` (so the `ALTER DATABASE striatum_daemon SET …` timeouts carry over).
- **Downtime estimate:** ~**10–20 min** striatumd-down (dominated by copying the 26 GB
  `striatum_daemon` heap) + online `ANALYZE` afterward. `--link` would cut this to ~3–5 min.

## Runbook (phased)

### Phase 0 — Pre-flight (no downtime)
- [ ] Fresh **pgBackRest full backup** + verify: `pgbackrest --stanza=proximal --type=full backup` then `info`. This is the real rollback safety net.
- [ ] Confirm restic off-site is current.
- [ ] (Optional) LVM/filesystem snapshot of `/var/lib/postgresql` if the volume supports it.
- [ ] Drop ephemeral test DBs to shrink the copy + avoid extension surprises: `engram_test`, `engram_test_worker_e`, `engram_test_worker_e2e_runner_2` (confirm with operator they're regenerable).
- [ ] Capture current state for diff: `pg_dumpall --globals-only > /tmp/globals_pre.sql`; record `\dx` per DB, `pg_db_role_setting`, and the custom `pg_hba.conf` lines (esp. the **`striatum-lane` reject rule** — RFC 0096/0110 lane sandbox; it must be re-applied to the new cluster's `pg_hba.conf`).

### Phase 1 — Add PGDG repo + install PG17 stack (no downtime; new cluster auto-created on a temp port)
- [ ] Add PGDG: `sudo install -d /usr/share/postgresql-common/pgdg && sudo curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc` and add `deb https://apt.postgresql.org/pub/repos/apt noble-pgdg main` → `apt update`.
- [x] ✅ pgBackRest already at **2.58.0** (upgraded + validated 2026-06-17, prereq #2) — no action here.
- [ ] Install PG17 + **all** matching extensions (parity is required for `pg_upgrade --check`):
      `apt install postgresql-17 postgresql-17-pgvector postgresql-17-pg-qualstats postgresql-17-pg-stat-kcache postgresql-17-hypopg`
      (`postgresql-17` pulls contrib for pg_stat_statements/pgcrypto/pgrowlocks/pgstattuple).
- [ ] Installing `postgresql-17` auto-creates an empty `17/main` on port 5433. **Stop + disable autostart** of it before the upgrade (`pg_dropcluster 17 main` if `pg_upgradecluster` will recreate it, per wrapper requirement).
- [ ] **`pg_upgrade --check` dry run** (or `pg_upgradecluster --check` where supported) to catch any missing library/extension mismatch with zero downtime.

### Phase 2 — Upgrade (downtime starts)
- [ ] **Stop striatumd:** `systemctl --user stop striatumd.service`. `KillMode=process` → the supervised lane helpers / tmux sessions stay alive (RFC 0103 W3); they re-bridge over files. Confirm 0 `striatumd_rw` connections.
- [ ] Stop any other writers (token-dashboard ingest, engram/praxis services) to quiesce all DBs.
- [ ] Re-assert `shared_preload_libraries` as the **plain comma form** in the new cluster's config — **do not** set it via `ALTER SYSTEM` (the `GUC_LIST_QUOTE` trap in `known-bad.md` makes the server unbootable). Carry forward the tuned GUCs (`max_wal_size=16GB`, `auto_explain`, `log_lock_waits`, archive settings) from `desired.md`.
- [ ] Run: `sudo pg_upgradecluster --method=upgrade 16 main` (copy mode; new cluster takes port 5432, old 16 cluster is left stopped and intact).
- [ ] Re-apply the custom `pg_hba.conf` entries (lane-sandbox **`striatum-lane` reject** rule + any loopback rules) to `17/main/pg_hba.conf`; `systemctl reload postgresql@17-main`.

### Phase 3 — Post-upgrade (finish downtime, then online)
- [ ] **Stats:** `sudo -u postgres vacuumdb --all --analyze-in-stages` (planner has no stats on the new cluster — mirrors the 57014 finding that `events`/`audit_log` must be analyzed).
- [ ] **Extensions:** per DB, `ALTER EXTENSION vector UPDATE;` (→ 0.8.x) and `ALTER EXTENSION <name> UPDATE;` for qualstats/kcache/hypopg/statements to pick up new SQL.
- [ ] **pgvector HNSW:** `REINDEX INDEX CONCURRENTLY engram.public.segment_embeddings_nomic_768_hnsw_idx;` and the `hippo` equivalent. pg_upgrade carries the index files, but a reindex is cheap insurance across the 0.6→0.8 jump (and lets you adopt 0.8 build options). Both DBs are small (≤3 GB) so this is minutes.
- [ ] **pgBackRest:** `sudo -u postgres pgbackrest --stanza=proximal stanza-upgrade` then a new **full backup**; verify `archive-push` works on the new timeline (`info` shows db `(17)`).
- [ ] **Verify carried-over settings:** `SELECT datname, setconfig FROM pg_db_role_setting` shows `striatum_daemon → {statement_timeout=600s, lock_timeout=3s, idle_in_transaction_session_timeout=15s}`. Re-add if missing.
- [ ] **Restart writers:** `systemctl --user start striatumd.service`; confirm it reconnects and `doctor` is green; restart token-dashboard / engram / praxis.

### Phase 4 — Land the `transaction_timeout` backstop (the point of the upgrade)
- [ ] `ALTER DATABASE striatum_daemon SET transaction_timeout = '120s';` — DB-scoped (same level the 57014 timeouts live, so it survives the daemon's role-GUC re-assertion). 120 s comfortably exceeds any legitimate reconcile/append txn but kills the multi-minute runaway class that caused 57014. Tune after observing real txn durations (`pg_stat_activity`).
- [ ] **Validate:** open a psql txn, `BEGIN; SELECT pg_sleep(130);` → expect the session terminated at ~120 s with `terminating connection due to transaction timeout`. Record in CHANGELOG.
- [ ] Update `desired.md` (add `transaction_timeout` to the DB-scoped block) and `CHANGELOG.md`.

## Validation / smoke tests
- `SELECT version();` → 17.x; `\dx` per DB matches the carry-forward matrix at new versions.
- pgvector: a known ANN query on `engram.segment_embeddings` returns expected neighbors; `EXPLAIN` shows the HNSW index in use.
- striatumd: `doctor` ok; drive a `prepare` append → completes « 60 s (57014 follow-up).
- pgBackRest: `info` healthy on db `(17)`; a `--type=diff backup` succeeds; WAL archiving advancing.
- `transaction_timeout` validation above passes.

## Rollback
- **Primary (copy mode):** the old `16/main` cluster is untouched and bootable. To revert:
  stop `17/main`, `pg_dropcluster 17 main`, start `16/main` on 5432, downgrade pgBackRest
  config back to the 16 stanza, restart striatumd. Any writes made on 17 after cutover are
  lost — acceptable for a short, supervised window; quiesce writers first.
- **Ultimate:** the Phase-0 pgBackRest full backup + WAL (PITR) and restic off-site.

## Risks & open questions for the operator
- **Repo migration (Ubuntu → PGDG):** `postgresql-common`/`-client-common` may be replaced
  by PGDG versions; usually clean, but verify no held/broken packages after `apt update`.
  Decide whether to also move the *running* 16 packages to PGDG (recommended for consistency)
  or leave 16 on Ubuntu until decommissioned.
- ~~**pgBackRest 2.50 → latest** is mandatory and changes the binary under a working PITR
  setup~~ — **done 2026-06-17**: upgraded to 2.58.0 and re-verified (`info` ok + live
  `check` archived a forced WAL segment). No longer a window risk.
- **pgvector 0.6 → 0.8** is a two-major jump; HNSW on-disk format has been stable, but the
  REINDEX step removes all doubt. Confirm engram/hippo apps tolerate a brief index rebuild
  (use `CONCURRENTLY`).
- **`striatum-lane` pg_hba reject rule** must be re-applied to the new cluster or the lane
  sandbox (`doctor lane_pg_isolated`) regresses — easy to miss because `pg_upgradecluster`
  generates fresh config.
- **`shared_preload_libraries` quoting trap** (`known-bad.md`): set the plain comma form in a
  conf file, never via `ALTER SYSTEM`.
- **Timing:** schedule during a low-run window; the ~10–20 min striatumd stop is the main
  user-visible cost (lanes survive, but no new daemon RPCs during the window).

## Cross-references
- `reports/INCIDENT_57014_append_event_row_lock_contention_2026-06-17.md` — the
  `transaction_timeout` motivation and the DB-scoped settings that must survive.
- `desired.md` (GUC convergence + the DB-scoped timeout block), `known-bad.md`
  (`shared_preload_libraries` trap), `backups.md` (pgBackRest stanza + restic).
