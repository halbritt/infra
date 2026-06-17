# Incident — `append_event_row` 60 s statement timeouts (SQLSTATE 57014)

- **Date:** 2026-06-17
- **Cluster:** `proximal:5432`, PG 16.14, DB `striatum_daemon`
- **Reporter symptom:** `striatum run prepare` →
  `append_event_row (sd): ERROR: canceling statement due to statement timeout (SQLSTATE 57014)`,
  blocking ~60,028 ms (== the daemon's per-session `statement_timeout` of 60 s) then cancelled.
  100 % reproducible under 6–18 concurrent supervised runs. `striatum doctor` = ok the whole time.
- **Prior:** matches striatum#198 ("supervisor-reconcile transactions stay open for minutes …
  starving all event appends — global 57014"), regressed at 2.33.0. Recurrence issue #355.

## Root cause (proven, DB side)

A single event INSERT consuming the entire 60 s window is a **lock wait, not slow disk.**
`striatumd.append_event_row` (SECURITY DEFINER) begins every append with:

```sql
SELECT last_hash INTO v_previous_hash
  FROM striatumd.repo_event_chain_heads
 WHERE repository_id = p_repository_id
   FOR UPDATE;            -- row-level exclusive lock on the per-repo hash-chain head
```

There is **exactly one `repo_event_chain_heads` row per repository** (19 repos), and every
append must `FOR UPDATE`-lock it to read `previous_hash` before inserting (tamper-evident
hash chain). The **supervisor-reconcile path also appends events** (heartbeats) under the
same long-lived transaction, so a reconcile transaction that stays open for minutes holds
that row lock. Every other append for that repo — including `prepare` — blocks on the
tuple lock until the holder commits, which is far longer than 60 s ⇒ statement_timeout ⇒ 57014.

### Evidence captured during load (2026-06-17 ~17:00–17:15 UTC)

- **Two runaway daemon transactions** (`striatumd_rw`, app `striatumd-go/2.33.0`), open
  **59 min** (pid 347033) and **24 min** (pid 368936), cycling back-to-back through
  `UPDATE process_supervisor_pointers/daemon_supervisors/process_supervisors`,
  reconcile `SELECT … FOR UPDATE OF ps`, and `SELECT append_event_row(...)` — one
  transaction doing the entire multi-run reconcile sweep without committing.
- **`pgrowlocks('striatumd.repo_event_chain_heads')`** — direct proof of the contention:

  | locked chain-head row | locker xid | held by pid | txn age | mode |
  |---|---|---|---|---|
  | `(357,7)`  | 28514246 | 347033 | 59 min | `Update` (= `FOR UPDATE`) |
  | `(3802,7)` | 28515090 | 368936 | 24 min | `Update` (= `FOR UPDATE`) |

- **Lock type is row-level**, not advisory and not a relation lock: both transactions hold
  only `RowExclusiveLock`/`RowShareLock`/`AccessShareLock` at relation level (those don't
  conflict between writers); the serialization is the `FOR UPDATE` tuple lock above.
- **Reconcile statements are individually fast and PK-driven** (`WHERE repository_id=… AND
  supervisor_id=…`, joins on the PKs) — **no missing index causes the 60 s.** The hot path
  indexes are adequate. (Separate query-perf finding DF-2 / striatum#330 about a
  `(actor_session_id,run_id,event_type)` index on `events` is unrelated to this timeout.)
- **Not connection exhaustion / pooling:** no pgbouncer; ~5 daemon connections of
  `max_connections=100`.

### Co-morbidity — xmin-pinned bloat (same root cause)

The never-committing transactions pin the global xmin horizon (`backend_xmin` age ~1.4 k
xids — the daemon commits rarely), so autovacuum runs but **cannot reclaim**:

| table | live rows | dead % | total size | n_tup_upd (cum) |
|---|---|---|---|---|
| `repo_event_chain_heads` | 19–37 | **98.7 %** | **267 MB** | 1.21 M (1.19 M HOT) |
| `process_supervisor_pointers` | ~2.5 k | 48.6 % | **6.36 GB** | 1.38 M |
| `daemon_supervisors` | ~2.3 k | 51.4 % | **2.45 GB** | 1.38 M |
| `process_supervisors` | ~2.3 k | 50.6 % | **2.23 GB** | 1.38 M |

Vicious cycle: long txns block appends **and** pin xmin → bloat to GBs → each reconcile
UPDATE/FOR-UPDATE on a bloated page is slower → txns last longer → hold the chain-head
lock longer. `events` (13.6 M rows, 17 GB) and `audit_log` (17 M rows, 8.6 GB) had
**never been (auto)vacuumed or analyzed** — the planner had zero stats.

## Remediation

### Applied 2026-06-17 (online, non-disruptive — no daemon impact)

Timeouts on the writer path (takes effect on the daemon's **next** connections):

```sql
ALTER DATABASE striatum_daemon SET lock_timeout = '3s';                       -- fail fast, retry
ALTER DATABASE striatum_daemon SET idle_in_transaction_session_timeout = '15s'; -- bound idle stalls
```

⚠️ **Applied at DATABASE level, not role level.** First tried `ALTER ROLE striatumd_rw
SET …`; the daemon's startup **L0 credential bootstrap re-asserts `striatumd_rw`'s role
GUCs** (resets them to its baseline `statement_timeout=600s`), which **wiped the role-level
timeouts on the next restart.** Database-level settings are not touched by the role
bootstrap and were **verified to survive a restart**. (Trade-off: DB-level also applies to
the owner/`halbritt` sessions on this DB — acceptable; neither holds long lock waits or
idle transactions.)

- `lock_timeout=3s` — a blocked append now aborts in ~3 s with **55P03**
  (`lock_not_available`) and the daemon's bounded retry kicks in, instead of burning the
  full 60 s as **57014**. Symptom relief that works whether the blocker is idle or active.
  ⚠️ **App note:** the SQLSTATE the daemon sees changes 57014 → 55P03 — both must be
  treated as retryable.
- `idle_in_transaction_session_timeout=15s` — caps any transaction left **idle** between
  statements and lets the xmin horizon advance so autovacuum can reclaim. **Partial:** live
  sampling shows the reconcile transactions are *mostly active* (statements back-to-back),
  so this is a safety net for stalled/hung-probe cases, **not** a full bound on an
  actively-busy transaction. PG 16 has **no `transaction_timeout`** (PG 17+ only) — there
  is no server-side cap on an actively-working transaction's total duration. The complete
  fix is app-side (below).

Table-scoped autovacuum + HOT headroom (reclaim aggressively once long txns stop;
`fillfactor` applies on next rewrite / VACUUM FULL):

```sql
-- repo_event_chain_heads owned by 'postgres' -> applied as postgres
ALTER TABLE striatumd.repo_event_chain_heads      SET (fillfactor=70, autovacuum_vacuum_scale_factor=0.0,  autovacuum_vacuum_threshold=25, autovacuum_analyze_scale_factor=0.05, autovacuum_vacuum_cost_delay=0);
ALTER TABLE striatumd.process_supervisor_pointers SET (fillfactor=80, autovacuum_vacuum_scale_factor=0.05, autovacuum_vacuum_threshold=50, autovacuum_analyze_scale_factor=0.05, autovacuum_vacuum_cost_delay=0);
ALTER TABLE striatumd.daemon_supervisors          SET (fillfactor=80, autovacuum_vacuum_scale_factor=0.05, autovacuum_vacuum_threshold=50, autovacuum_analyze_scale_factor=0.05, autovacuum_vacuum_cost_delay=0);
ALTER TABLE striatumd.process_supervisors         SET (fillfactor=80, autovacuum_vacuum_scale_factor=0.05, autovacuum_vacuum_threshold=50, autovacuum_analyze_scale_factor=0.05, autovacuum_vacuum_cost_delay=0);
ALTER TABLE striatumd.events    SET (autovacuum_vacuum_insert_scale_factor=0.05, autovacuum_vacuum_insert_threshold=10000, autovacuum_analyze_scale_factor=0.02, autovacuum_analyze_threshold=5000);
ALTER TABLE striatumd.audit_log SET (autovacuum_vacuum_insert_scale_factor=0.05, autovacuum_vacuum_insert_threshold=10000, autovacuum_analyze_scale_factor=0.02, autovacuum_analyze_threshold=5000);
```

Plus a one-time `ANALYZE` of `events`, `audit_log`, and the three supervisor tables
(they had no stats). Installed `pgrowlocks` (diagnostic).

### Executed 2026-06-17 ~17:34 UTC (operator-authorized)

Stopped the daemon (`systemctl --user stop striatumd.service` — `KillMode=process`, so the
474 attached supervised lanes/tmux sessions kept running), which dropped both runaway
transactions → released the chain-head locks → unpinned xmin (verified: 0 `striatumd_rw`
connections, 0 open txns). Then `VACUUM FULL (… ANALYZE)` the four bloated tables and
restarted the daemon.

**Bloat reclaimed (~11.3 GB) in ~12 s, daemon-down:**

| table | before | after | reclaimed |
|---|---|---|---|
| `process_supervisor_pointers` | 6364 MB | 2432 kB | −6.36 GB |
| `daemon_supervisors` | 2445 MB | 1400 kB | −2.44 GB |
| `process_supervisors` | 2227 MB | 1400 kB | −2.23 GB |
| `repo_event_chain_heads` | 267 MB | 32 kB | −267 MB |

(The "before" dead-tuple count had ballooned to ~226 k/table once the runaway snapshots
released — direct measure of how much the long txns were holding un-reclaimable.)

**After state (daemon back up, healthy):** 3 fresh pooled connections, all plain `idle`
(committed — `commit` seen, **not** idle-in-transaction); **oldest writer xact = 0 s** (was
59 min); **0** chain-head rows locked (`pgrowlocks`); **0** blocked appends. The tmux
liveness storm still fires (unchanged app behavior) but is **no longer wrapped in a
lock-holding long transaction** — the daemon commits per cycle. Likely helped further by
the reclaim: reconcile statements now hit 2.4 MB tables instead of 6.3 GB, so the sweep
commits fast. Settings verified to **survive the restart/bootstrap** (DB-level).

**Remaining (operator):** resume the workflow (`doctor` → `prepare` → `start` → drive) to
confirm an `append_event_row` completes « 60 s under 15+ concurrent runs. Watch:
```sql
SELECT pid, now()-xact_start AS xact_age, state FROM pg_stat_activity
 WHERE usename='striatumd_rw' AND xact_start < now()-interval '30s';   -- expect: no rows
SELECT * FROM pgrowlocks('striatumd.repo_event_chain_heads');         -- expect: brief/none
```

## MUST be fixed in striatumd application code (handled separately — #198 / #355)

The DB can only mitigate. The defect is **transaction scope**: striatumd 2.33.0 wraps the
entire multi-run supervisor-reconcile sweep — hundreds of `UPDATE`s, the tmux-probe-driven
reconcile reads, **and** `append_event_row` heartbeat appends — in **one transaction held
open for tens of minutes**, holding the per-repo `repo_event_chain_heads` `FOR UPDATE` lock
and pinning xmin throughout. Required app fixes:
- Scope DB transactions per supervisor/per reconcile unit; **commit promptly** (ideally
  autocommit each reconcile UPDATE). Never hold a transaction open across tmux subprocess
  probes.
- Do **not** call `append_event_row` inside the long reconcile transaction — append
  heartbeats in their own short transactions so they don't hold the chain-head lock.
- Durable server-side backstop available only after a **PG 17 upgrade**: `transaction_timeout`
  (caps total transaction duration regardless of activity). Not available on 16.14.
- **L0 bootstrap clobbers role GUCs:** the daemon re-asserts `striatumd_rw`'s role config
  on every startup (only `statement_timeout=600s`), wiping any operator `ALTER ROLE … SET`.
  The timeouts therefore live at DB level. If striatum wants to own them, add
  `lock_timeout` + `idle_in_transaction_session_timeout` to that bootstrap baseline so the
  app's intent is explicit and not silently reset.
