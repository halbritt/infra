# Changelog

Notable changes to the **proximal** PostgreSQL cluster's configuration and to this
provenance repo. Newest first. Config changes record the live cluster (`proximal:5432`,
`system_identifier 7652478211804703267`, PG 17.10 — was `7628053153555146077`/16.14 before
the 2026-06-16/17 pg_upgrade); see `reports/` and `inventory/` for the evidence behind each
entry, and `git log` for granular history.

## 2026-06-18

### Off-peak `pg_repack` of bloated heartbeat/chain tables — ~454 MB reclaimed
Acted on the bloat observation from `RECS_VERIFICATION_2026-06-17.md` (#1). Installed
`postgresql-17-repack` (PGDG, `pg_repack` 1.5.3) + `CREATE EXTENSION pg_repack` in
`striatum_daemon`, then online-repacked four tables during a verified low-activity window
(~13:22 UTC), run as `postgres` with `--no-kill-backend` (never risk killing daemon backends
on its hottest tables). Record: `reports/REPACK_supervisor_tables_2026-06-18.md`.
- `process_supervisor_pointers` 255 MB → **2.5 MB**; `daemon_supervisors` 93 → **1.46 MB**;
  `process_supervisors` 87 → **1.46 MB**; `repo_event_chain_heads` 24 MB → **32 KB**.
- Verified healthy: 10/10 indexes valid+ready, no orphan repack triggers, write path intact,
  throughput alive. One-time cleanup (bloat recurs slowly under heartbeat churn) — re-run
  periodically or reduce write amplification app-side; `desired.md` autovacuum tuning stands.

### Automated the recurring reclaim — `pg-repack-bloated` systemd timer (monthly, off-peak)
Since the bloat regrows, added a fail-safe systemd timer rather than leaving it manual.
Canonical artifacts in `maintenance/` (`pg-repack-bloated.{sh,service,timer}` + README);
installed to `/usr/local/bin` + `/etc/systemd/system`, runs as `postgres`. **Why systemd, not
`/schedule`:** the cloud-agent scheduler can't reach proximal's loopback PG or `sudo`; local DB
maintenance must run on the box. Behaviour: monthly (1st @ 13:00 UTC ≈ 06:00 PDT, the verified
quiet window, `Persistent=true`); repacks a listed table only if it exceeds **16 MB** (healthy
~2 MB); `pg_repack --no-kill-backend` so it **skips + retries next month** rather than ever
disrupting the daemon. Validated: dry run no-op'd cleanly (4 tables ≤16 MB); next run
2026-07-01. Operate: `journalctl -u pg-repack-bloated.service`; run now with
`sudo systemctl start pg-repack-bloated.service`.

## 2026-06-17

### Verified the 7 mined best-practice recommendations (read-only) — no change applied
Worked the candidate list from `SUPABASE_PG_BEST_PRACTICES_MINED_2026-06-17.md`,
`SELECT`/`EXPLAIN` only. Record: `reports/RECS_VERIFICATION_2026-06-17.md`. Outcomes:
- **#5 timeouts — PASS:** `lock_timeout=3s`, `idle_in_transaction_session_timeout=15s`,
  `transaction_timeout=120s` (PG17, survived), `statement_timeout=600s` all DB-scoped on
  `striatum_daemon`. No re-assert needed.
- **#6 HNSW reindex — DONE** (commit `c0269b7`): both HNSW indexes present on pgvector 0.8.2.
- **#2 work_mem — FALSIFIED:** 0 temp spills, peak concurrency far below ceiling → non-lever
  (re-confirms `desired.md`). **#3 unindexed-FK premise — FALSIFIED (dormant):** 41 truly-
  uncovered FKs (the skill's `indkey[0]` query over-reports at 62; corrected with
  `string_to_array`), all `NO ACTION` with **0 parent deletes** → no active cost; raise
  upstream before retention/GC ships. Annotated the bug in the mined report.
- **#1 baseline — COMPLETE:** created role **`proximal_monitor`** (`NOLOGIN`, member of
  `pg_monitor`, granted into `halbritt`) so inventory runs read full stats without superuser;
  de-masked the daemon hot path — supervisor heartbeats (`process_supervisor_pointers`/
  `process_supervisors`/`daemon_supervisors` UPDATEs, ~1.5M calls/window) + `append_event_row`,
  all sub-2 ms / 100% cached. **#4 partitioning** confirmed as a future upstream lead;
  **#7** is app-side.
- Refreshed `connection.md` + this preamble for the post-upgrade reality (PG17.10, new sysid,
  current DB list, new `proximal_monitor`/`postgres` rows). Set AGENTS.md convention to
  **commit and push often**.
- **Reset `pg_stat_statements`** at operator request (via `sudo -u postgres`) — fresh baseline
  window from **2026-06-17 23:51:42 UTC** (pre-reset peak ~4,875 stmts / 4.19M calls).
- **Filed the two upstream schema leads** in `halbritt/striatum`: **#386** (unindexed FKs on
  `events`/`audit_log` — latent seq-scan cliff before retention; distinct from closed #330) and
  **#387** (range-partition both tables by `created_at`), cross-linked as companions.

### MAJOR UPGRADE EXECUTED: PostgreSQL 16.14 → 17.10 (+ pgvector 0.8.2)
Live cluster upgraded via `pg_upgradecluster -m upgrade 16 main` (copy mode). **16/main is
preserved** (down on 5433) as the rollback. **Downtime, honestly:** the failed first attempt
held striatumd down **~71 min** (almost entirely the 37,675-role globals crawl); the
successful retry was **~3 min** daemon-down + **~7 min degraded** (appends failing until the
grant fix). The supervised lanes survived throughout (`KillMode=process`) and the run paused at
`needs_branch_confirmation` — not lost. Two failures + recovery, both caused by **striatum
pgtest-harness cruft** — worth flagging to the app team:
- **Attempt 1 failed twice over:** the globals restore crawled for ~1 h on **~37,675
  abandoned `*_pgtest_*` / `boot2_*` roles**, then pg_upgrade aborted on a **broken transient
  test DB** (OID 127575054, missing `pg_largeobject` file). Auto-rolled-back cleanly (16
  restarted, new cluster removed) — no data touched.
- **Cleanup (online, no downtime):** dropped all 37,675 junk roles in 63 s (0 dependencies);
  verified all 9 DBs file-consistent; 0 transient pgtest DBs remained.
- **Attempt 2: clean success in 52 s** (globals instant with 25 roles, 31 GB copy fast).
- **Post-upgrade fixes:** (1) pgBackRest config still hardcoded `pg1-path=…/16/main` → updated
  to `…/17/main`, then `stanza-upgrade` + `check` (archives to `17-2/` now). (2) **Event
  appends broke with `permission denied for repo_event_chain_heads`**: the SECURITY DEFINER
  `append_event_row` (owner halbritt) lost its *inherited* `arw` (halbritt is a member of
  `striatumd_rw`) because PG16 per-grant `INHERIT` semantics didn't carry — fixed with a direct
  `GRANT SELECT,INSERT,UPDATE … TO halbritt` + a daemon restart to refresh cached plans.
- **Verified:** PG 17.10 on 5432; `pg_hba` `striatum-lane` reject rules intact; DB-scoped
  `lock_timeout/idle` carried; **`transaction_timeout=120s` landed + fire-tested** (the durable
  #198/#355 backstop PG16 lacked); `shared_preload_libraries` loaded; stats present; pgvector
  0.8.2 + contrib extensions updated; daemon appending cleanly. Stack `apt-mark hold`-pinned.
- **App-side follow-ups (halbritt/striatum):** the `repo_event_chain_heads` grant to the
  SD-function owner should be explicit in the schema (don't rely on PG16 inherited membership);
  the pgtest harness must drop its per-run roles + ephemeral DBs (37k roles is a real upgrade/
  catalog hazard). pgvector HNSW indexes **reindexed for 0.8** (engram 44 MB/4.1 s, hippo
  350 MB/11.9 s, `REINDEX … CONCURRENTLY`, 0 invalid left).
- Evidence: full as-run timeline + commands in `reports/PG17_UPGRADE_ASRUN_2026-06-17.md`;
  plan + lessons in `reports/PG17_UPGRADE_PLAN_2026-06-17.md`.

### Vendored Supabase Postgres best-practices skill + mined insights (docs only)
- Added `skills/supabase-postgres-best-practices/` — vendored (pinned commit
  `1356046`, 2026-06-05, MIT) from `supabase/agent-skills`: 28 vendor-neutral
  Postgres rule files across 8 categories, a reference library for the tuning
  instrument and the fleet. Authoring scaffolds dropped; provenance + refresh
  steps in `skills/README.md`. The companion `supabase` (cloud-platform) skill
  was deliberately **not** vendored.
- `reports/SUPABASE_PG_BEST_PRACTICES_MINED_2026-06-17.md` — proximal-specific
  application: the rules independently validate the `INCIDENT_57014` remediation
  (short txns / idle timeout / per-table autovacuum) and baseline's
  `work_mem × max_connections` warning; flags that `conn-pooling` and
  `lock-skip-locked` do **not** fit this workload; mines the generic-Postgres
  security facts (notably `SECURITY DEFINER` runs as owner — exactly what broke
  `append_event_row` during this day's PG17 upgrade) from the un-vendored skill.
  Updated post-upgrade for PG 17.10 / live `transaction_timeout=120s`. No live
  cluster changes.

### pgBackRest 2.50 → 2.58.0 (upgrade prerequisite #2; done ahead of the window)
- Upgraded the pgBackRest binary only (PGDG; 22 held packages untouched). 2.58 is
  PG 17-capable (support landed in 2.53) and backward-compatible with PG 16, so it was done
  now to de-risk the upgrade window. Validated live: stanza `proximal` `status: ok`,
  existing backups intact, and `pgbackrest --stanza=proximal check` forced WAL segment
  `…B800000098` which archived successfully (120 ms) with the new binary. Re-pinned via
  `apt-mark hold`. Remaining pgBackRest work for the window is just the post-upgrade
  `stanza-upgrade`. See `reports/PG17_UPGRADE_PLAN_2026-06-17.md`.

### PGDG apt repo wired up (upgrade prerequisite #1; no packages installed)
- Added `apt.postgresql.org` (`noble-pgdg main`) — key `/usr/share/keyrings/postgresql.gpg`,
  source `/etc/apt/sources.list.d/pgdg.list`. `apt update` clean. Makes available (installed
  nothing): `postgresql-17` 17.10, `postgresql-17-pgvector` 0.8.2, `pgbackrest` 2.58.0,
  `postgresql-17-pg-qualstats`/`-pg-stat-kcache`/`-hypopg`. Running PG 16.14 / pgBackRest
  2.50 / pgvector 0.6 untouched.
- **Protective `apt-mark hold`** on the running PG16 stack (`postgresql postgresql-16
  postgresql-client-16 postgresql-common postgresql-client-common libpq5 pgbackrest
  postgresql-16-{pgvector,pg-qualstats,pg-stat-kcache,hypopg}`) — enabling PGDG otherwise lets
  a blanket `apt upgrade` swap the live pgvector `.so` and pull PG 18. `apt-mark unhold` at the
  start of the planned upgrade window. See `reports/PG17_UPGRADE_PLAN_2026-06-17.md`.

### Incident: `append_event_row` 60 s timeouts / SQLSTATE 57014 (striatum#198 regress, #355)
- **Root cause (proven):** `striatum run prepare` appends time out at the 60 s
  `statement_timeout` because `append_event_row` opens with `SELECT … FROM
  repo_event_chain_heads … FOR UPDATE` (one row per repo, tamper-evident hash chain), and
  the **supervisor-reconcile path holds that row lock inside a single transaction left open
  for tens of minutes** (observed 59 min & 24 min). `pgrowlocks` proved the two chain-head
  rows locked `Update` by the two runaway `striatumd_rw` txns. Row-lock contention, **not**
  disk/index/pooling. Same long txns pin xmin → autovacuum can't reclaim → 267 MB / 6.4 GB /
  2.4 GB / 2.2 GB bloat (50–99 % dead) on the hot churned tables.
- **Applied (config + vacuum, non-disruptive):**
  `ALTER DATABASE striatum_daemon SET lock_timeout='3s'` (blocked appends fail fast as
  55P03 + retry instead of 60 s 57014 — ⚠️ app must treat 55P03 as retryable) and
  `idle_in_transaction_session_timeout='15s'` (bounds idle stalls, unpins xmin; partial —
  reconcile txns are mostly *active*, and PG 16 has no `transaction_timeout`). **DB level,
  not role level:** the daemon's L0 credential bootstrap re-asserts `striatumd_rw`'s role
  GUCs on startup and wiped the role-level form; DB-level verified to survive a restart.
  Aggressive autovacuum + `fillfactor` storage params on the 4 hot tables; insert-vacuum +
  analyze params on `events`/`audit_log`; one-time `ANALYZE` (both had **zero** planner
  stats — `events` is 13.6 M rows / `audit_log` 17 M, not the stale 1.0 M estimate).
  Installed `pgrowlocks`.
- **Executed restart + reclaim (operator-authorized, ~17:34 UTC):** `systemctl --user
  stop/start striatumd.service` (*user* unit, `KillMode=process` → kept the 474 supervised
  lanes alive) dropped both runaway txns; `VACUUM FULL` returned **~11.3 GB** (pointers
  6364 MB→2432 kB, daemon_supervisors 2445 MB→1400 kB, process_supervisors 2227 MB→1400 kB,
  chain_heads 267 MB→32 kB). After: oldest writer xact **0 s** (was 59 min), 0 chain-head
  locks, 0 blocked appends, daemon committing per cycle. Operator to drive `prepare` under
  load for the final append-latency confirmation.
- **Handed to halbritt/striatum (app, #198/#355):** transaction scope — stop wrapping the
  whole multi-run reconcile sweep + heartbeat `append_event_row` calls in one long
  transaction; commit per unit; keep heartbeat appends out of the reconcile txn.
- Evidence: `reports/INCIDENT_57014_append_event_row_lock_contention_2026-06-17.md`.

### Query-level analysis (no config change)
- Used the now-collecting `pg_stat_statements`/`pg_qualstats`/`pg_stat_kcache` to lift the
  three `cannot-measure → refuse` knobs from the 2026-06-16 plan. All three measured out
  as **non-levers** → **no GUC change**: workload is CPU-bound on fully-cached data
  (737 s CPU vs 132 physical-read blocks on `striatum_daemon`), **0 `work_mem` spills**,
  and `random_page_cost` is EXPLAIN-proven a no-op (identical plans at 1.1 vs 4).
- **Real bottleneck = missing indexes** (handed off, not config): the #1 query (1,190 s
  total) seq-scans all 1.01M `events` rows every call; a hypopg `(actor_session_id,
  run_id, event_type)` index drops planner cost ~1,218,979 → 8.08. Plus `audit_log (ts)`
  and the advisor's set. Recorded as DF-2 (`inventory/2026-06-16/deferred-findings.md`)
  and `reports/PROXIMAL_16_MAIN_POSTGRES_TUNING_REPORT_CLAUDE_OPUS_4_8_2026-06-17.md`;
  belongs in `halbritt/striatum`. `desired.md` notes the knobs as evaluated/left-default.
- Backups: restic `/home/halbritt` initial upload running (excl. `.cache`/`models`/
  `node_modules`, ~138 G); off-site repo confirmed.

## 2026-06-16

### Config (live cluster)
- **`shared_preload_libraries` empty → `pg_stat_statements`** (R1). Staged via
  `ALTER SYSTEM`, applied by **restart** of `postgresql@16-main` at **19:14:59 UTC**
  (restart-class; instance was quiesced). Boot pre-validated (lib present). Extension
  `pg_stat_statements` 1.10 created in `postgres` + `template1`; view queryable
  (signal flowing — top statement by total time is `append_event_row`). Defaults
  `max=5000`, `track=top`. **Status: APPLIED, verified loaded.** Unblocks the three
  refused knobs (`work_mem` headroom, `random_page_cost`, `effective_io_concurrency`)
  once a representative query window accrues. Revert: `ALTER SYSTEM RESET
  shared_preload_libraries` + restart. `max_wal_size=16GB` confirmed to survive the
  restart.
- **`max_wal_size` 1 GB → 16 GB** (P1). Staged via `ALTER SYSTEM`, made live with
  `pg_reload_conf()` at **18:43:20 UTC** (reload-class, no restart, no dropped
  connections). Addresses ~90% WAL-triggered checkpoints (`checkpoints_req 3445` vs
  `timed 393`). **Status: APPLIED, VERIFIED** — loaded-window canary (2026-06-16):
  6 timed / 0 requested checkpoints, 70 MB WAL ≪ 16 GB; was 89.7% WAL-triggered.
  Promoted to `baseline.md` + `desired.md`. **P2 (`wal_compression`) closed — not
  needed** (WAL volume trivial; P1 resolved the bottleneck). bgwriter deferred (low
  pressure once checkpoints are time-driven). Revert:
  `reports/rollback-P1-max_wal_size-2026-06-16.sql` (drift-guarded, retained).
  Plan/canary:
  `reports/PROXIMAL_16_MAIN_POSTGRES_TUNING_PLAN_CLAUDE_OPUS_4_8_2026-06-16.md`,
  `reports/canary-P1-max_wal_size-2026-06-16.md`.

### Diagnostic tooling (ancillary; reload-class, no restart)
- **`auto_explain` enabled** via `session_preload_libraries` (built-in contrib, no
  install): logs plans for statements > 500 ms (`log_analyze=off` to avoid per-stmt
  overhead; `log_nested_statements=on`). New connections pick it up.
- **Diagnosis logging on:** `log_lock_waits=on` (striatum lock contention),
  `log_temp_files=0` (catch `work_mem` spills — feeds the deferred work_mem re-eval).
  `log_checkpoints` was already on.
- **Extensions created** (no preload needed): `hypopg` 1.4 (hypothetical-index testing
  for the deferred index/planner work) + `pgstattuple` in `postgres`/`striatum_daemon`/
  `hippo`/`engram`; `pg_buffercache` in `postgres`.
- **`pg_qualstats` 2.1 + `pg_stat_kcache` 2.2.3 — ENABLED** (2026-06-16): added to
  `shared_preload_libraries` (via the bundled restart) and `CREATE EXTENSION`'d in
  postgres + template1. Views live; query-level predicate stats + real OS CPU/I-O
  attribution now available on top of `pg_stat_statements`.
- Revert for all of the above: `ALTER SYSTEM RESET <param>` + reload (default prior).
### Backups / PITR (pgBackRest → ZFS; see `backups.md`)
- Decided **against** routing backups through Garage — Garage has no storage classes /
  tiering (verified v2.3.0: multi-`data_dir` is capacity-weighted only, no hot/cold,
  no S3 storage-class placement), so an S3 indirection adds nothing for backups.
- Set up **pgBackRest 2.50 → `/nvr/pg-backups`** (ZFS dataset on the `nvr` pool;
  `recordsize=1M`, `compression=off`, postgres-owned). Stanza `proximal` **created**;
  `archive_command` **staged** (reload-applied, inert until `archive_mode=on`).
  Discovered `/dev/sda` is a live ZFS pool `nvr` (already holds `nvr/engram-backups`) —
  **not** wiped; added a dataset instead.
- ✅ **Bundled restart done (22:08 UTC):** `archive_mode=on` + `shared_preload_libraries
  = pg_stat_statements,pg_qualstats,pg_stat_kcache`. `pgbackrest check` passed (WAL
  pushed to repo) → **PITR live**. `pg_qualstats`/`pg_stat_kcache` extensions created
  (postgres + template1). **First full backup done** (`20260616-220907F`, ~3 min):
  37.9 GB database → **3.6 GB** repo (zstd ~10.5×), stanza status `ok`, retention
  applied. Encryption not yet enabled (recommended before off-site replication).
- ⚠️ **Incident during the restart** (~1–2 min downtime, no corruption — clean
  shutdown): `ALTER SYSTEM SET shared_preload_libraries='a,b,c'` mangled the comma-list
  into one double-quoted element → `FATAL: could not access file "…"`, server wouldn't
  boot. Recovered by hand-fixing `postgresql.auto.conf` to the plain comma form +
  restart. Logged in `known-bad.md` (don't set multi-value `GUC_LIST_QUOTE` params via
  `ALTER SYSTEM`).
- **Off-site (2026-06-17): restic → GCS Nearline.** restic 0.16.4 backs up
  `/nvr/pg-backups` + `/nvr/engram-backups` to `gs://proximal-backups` (Nearline,
  us-west1, project `heath-stuff`), **encrypted client-side**. SA `restic-proximal`
  (Storage Object Admin scoped to the bucket); creds + repo password root-only at
  `/etc/restic/` (NOT in git). Timers: daily backup (`forget` 7d/4w/6m) + monthly
  `prune`+`check`. First snapshot `e74b5e2a`: 5.83 GiB. Chose Nearline over Coldline —
  storage saving is pennies at this volume and Coldline's 90-day min penalises restic's
  prune churn (Nearline = 30-day). restic encryption also covers the earlier
  "encrypt before off-site" gap. See `backups.md`.
- **pgBackRest schedule live (2026-06-17):** systemd timers — `pgbackrest-diff.timer`
  daily 01:30 + `pgbackrest-full.timer` weekly Sun 01:00 (run as `postgres`), ordered
  before the 02:49 restic ship. Validated through the unit (diff
  `…_20260617-004654D`, 13 GB→1.2 GB, exit 0). **Backup chain now closed and
  self-sustaining:** PG → pgBackRest (full/diff + continuous WAL/PITR) → restic
  (encrypted, daily) → GCS Nearline. `zfs send` remains an alternative off-site path.

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
- ~~`pg_stat_statements` not loaded~~ → **resolved same day by R1** (above); query
  signal now flowing. The three refused knobs still need a representative query window
  before they can be re-evaluated.
- Inventory ran as non-superuser; a `pg_monitor` read-only role is recommended before
  the next run (see `connection.md`).
