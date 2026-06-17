# Mined insights — Supabase Postgres best-practices, applied to proximal

- **Date:** 2026-06-17
- **Cluster:** `proximal:5432`, PG 16.14, cluster `16/main`
- **Source skill:** `skills/supabase-postgres-best-practices/` (vendored from
  `supabase/agent-skills` @ `1356046`, 2026-06-05, MIT). 28 rule files across 8
  categories. See `skills/README.md` for provenance.
- **Author:** `CLAUDE_OPUS_4_8`, role `halbritt` (read-only mining; no live changes)

This report is the **proximal-specific application** of the vendored reference
library: which rules are already satisfied here, which are actionable, which do
**not** apply to this workload (and why), and the cross-references to the
`INCIDENT_57014` lock-contention finding, `baseline.md`, and `known-bad.md`.
The vendored skill is generic single-node Postgres advice — only 2 of 28 rules
(`security-rls-*`) are Supabase-cloud-specific and are noted as such below.

---

## 1. The lock-contention incident is a textbook case of three rules

`reports/INCIDENT_57014_append_event_row_lock_contention_2026-06-17.md`
(the `striatumd.append_event_row` 60 s 57014 timeouts) is, almost line for line,
the failure the skill's `lock-` and `monitor-` rules exist to prevent. This is
the strongest corroboration in the set — the skill independently prescribes the
exact remediation the incident arrived at empirically.

| skill rule | what it says | incident reality | verdict |
|---|---|---|---|
| `lock-short-transactions` | keep txns short; do external/slow work **outside** the txn; set `statement_timeout` | reconcile sweep wraps hundreds of UPDATEs + tmux subprocess probes + heartbeat appends in **one txn open 24–59 min**, holding the per-repo `repo_event_chain_heads` `FOR UPDATE` lock | **root cause = this exact anti-pattern.** The required app fix (#198/#355) — scope txns per reconcile unit, commit promptly, never append inside the long txn — *is* this rule. |
| `conn-idle-timeout` | set `idle_in_transaction_session_timeout` (rule suggests 30 s) | applied `=15s` at **DB** level 2026-06-17 | **applied, but rule is necessary-not-sufficient here.** The reconcile txn is *actively busy* (statements back-to-back), not idle — so the idle timeout is only a safety net. PG 16 has no `transaction_timeout` (PG 17+); that gap is tracked in the upgrade plan. |
| `monitor-vacuum-analyze` | tune per-table autovacuum on high-churn tables; `scale_factor` 5 % / analyze 2 % | applied `autovacuum_vacuum_scale_factor=0.05`, `autovacuum_analyze_scale_factor=0.02` on the churned tables; one-time ANALYZE of `events`/`audit_log` (had **zero** stats) | **applied — matches the skill's recommended thresholds exactly.** The xmin-pin → can't-reclaim → GB bloat chain is the skill's "stale stats / no autovacuum" warning at scale. |

### Where a `lock-` rule does *not* transfer cleanly

- **`lock-skip-locked` (`FOR UPDATE SKIP LOCKED`)** — the skill's queue-worker
  pattern. It does **not** apply to the `repo_event_chain_heads` `FOR UPDATE`:
  that lock is an *intentional serialization point* (one row per repo, read
  `last_hash` before append to keep the tamper-evident hash chain ordered).
  Skipping the locked head would break the chain. SKIP LOCKED is worth
  considering for striatumd's *run/job dispatch* (if any worker picks the next
  pending run), but **not** for the hash-chain head. Flagging so a future agent
  doesn't misapply the CRITICAL-looking rule to the hot lock.
- **`lock-advisory`** — conceptually the chain-head serialization is app-level
  coordination, but the append must read-and-lock the head row atomically to get
  `previous_hash`; an advisory lock can't carry that read, so it's not a clean
  swap. Low value here.

---

## 2. Corroborations & one rule that does NOT apply to this workload

| skill rule | proximal state | note |
|---|---|---|
| `conn-limits` (CRITICAL) | `baseline.md` already ⚠️ the exact risk | Rule: keep `work_mem × max_connections ≤ 25 % RAM`. Here `256 MB × 100 = 25.6 GB` vs 25 % of 125 GiB ≈ 31 GB — so **one** sort/hash node per connection is already near the ceiling; multi-node plans at concurrency blow past it. The skill gives the clean formula that backs baseline's existing un-quantified warning. **Actionable:** quantify real peak with the now-loaded `pg_stat_statements` before trusting 256 MB. |
| `monitor-pg-stat-statements` (CRITICAL-enabler) | **just loaded this session** (baseline R1) | Now that `pg_stat_statements` is in `shared_preload_libraries`, the skill's query patterns (`order by total_exec_time / calls`, `mean_exec_time > 100 ms`) are usable. **Actionable next run:** this was impossible at the 2026-06-16 inventory (quiet-window sampling only). |
| `conn-pooling` (CRITICAL) | **does NOT apply to current workload** | Skill says "always front with PgBouncer." But the incident shows ~5 long-lived daemon connections, peak 19/100, **no** pooler — and the bottleneck is *lock contention*, not connection churn. Pooling solves a problem proximal doesn't have. A transaction-mode pooler would actually *complicate* the daemon's session GUCs (L0 bootstrap). **Verdict: skip unless connection count climbs.** Knowing when to ignore a CRITICAL rule is the point. |
| `conn-prepared-statements` (HIGH) | N/A | Only bites under transaction-mode pooling, which proximal doesn't run. |
| `monitor-explain-analyze` | always applicable | Standard tool; the DF-2 / striatum#330 `(actor_session_id,run_id,event_type)` index hypothesis on `events` should be validated with `EXPLAIN (ANALYZE, BUFFERS)` before applying — matches `query-missing-indexes`. |

---

## 3. Generic-Postgres security nuggets (mined from the *un-vendored* `supabase` skill)

The broad `supabase` skill was **not** vendored (Supabase-cloud platform stuff).
But it carries a few facts that are pure Postgres and one that is directly
relevant to striatumd's `SECURITY DEFINER` function:

- **`SECURITY DEFINER` functions run with the creator's privileges and bypass
  RLS.** `striatumd.append_event_row` **is** `SECURITY DEFINER` (per the
  incident). That's an intentional privilege-elevation; the security note is that
  any logic relying on RLS is bypassed inside it, and —
- **A `SECURITY DEFINER` function in a schema where `EXECUTE` is granted to
  `PUBLIC` is callable by every role by default.** Worth a one-line audit:
  confirm `append_event_row`'s `EXECUTE` grant is scoped to `striatumd_rw`, not
  `PUBLIC`. (Not a tuning concern; noted for whoever owns the striatumd schema.)
- **Views bypass RLS by default** — PG 15+ wants `CREATE VIEW … WITH
  (security_invoker = true)`; older PG must revoke from untrusted roles.
- **In RLS, `UPDATE` first needs a `SELECT` policy**, and an `UPDATE` policy
  needs **both** `USING` and `WITH CHECK` or a row's owner column can be
  reassigned. (Generic PG RLS, applies only if/when RLS is used here — it
  currently isn't on this single-tenant ops cluster.)
- **Least privilege / `revoke all on schema public from public`** — `security-
  privileges` (vendored) says the same; relevant when provisioning new app roles.

The two genuinely Supabase-only rules (`security-rls-basics`,
`security-rls-performance`) lean on `auth.uid()` and the
`anon`/`authenticated`/`service_role` roles — **not present** on this cluster.
The transferable kernel is "enforce isolation in the DB and index the policy
predicate columns," which only matters if multi-tenant RLS is ever introduced.

---

## 4. Net-new candidates worth a future POSTGRES_TUNING run

Not asserted into `desired.md` — these are *leads* the mining surfaced, each
needs the instrument's falsify-before-apply treatment:

1. **Re-measure `work_mem` headroom with `pg_stat_statements`** now that it's
   loaded (`conn-limits`). The 256 MB value is currently justified only by a
   quiet-window sample; the formula says it's near the single-node 25 %-RAM line.
2. **Partitioning candidates** (`schema-partitioning`): `events` (13.6 M rows,
   17 GB) and `audit_log` (17 M rows, 8.6 GB) are large, append-heavy, and
   time-series-shaped. Below the skill's ~100 M-row rule of thumb today, but
   range-by-date partitioning would make purges instant and bound VACUUM cost as
   they grow. Schema owned by striatumd, not this repo — flag upstream.
3. **FK-index audit** (`schema-foreign-key-indexes`): run the skill's
   `pg_constraint`/`pg_index` gap query against `striatum_daemon` to confirm no
   unindexed FK is doing seq scans on cascades — corroborates/extends DF-2.
4. **`statement_timeout` discipline** (`lock-short-transactions`): the daemon's
   600 s baseline + 60 s per-session is lax vs the skill's 30 s example; the real
   fix is app-side txn scoping (#198/#355), but a tighter writer-path
   `statement_timeout` is worth modelling once the app commits per cycle.

---

## Bottom line

The vendored skill is high-quality, vendor-neutral Postgres advice and it
**independently validates** the empirical remediation in `INCIDENT_57014`
(short transactions, idle timeouts, per-table autovacuum) and the existing
`work_mem × max_connections` warning in `baseline.md`. Its main proximal value
going forward is as a checklist for the tuning instrument; the one trap to avoid
is applying `conn-pooling` / `lock-skip-locked` by reflex where this workload
doesn't want them.
