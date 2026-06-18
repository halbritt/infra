# Off-peak pg_repack of bloated heartbeat/chain tables — 2026-06-18

**Author:** `CLAUDE_OPUS_4_8` · **Type:** maintenance (online table rebuild) ·
**Authority:** mutating — `pg_repack` (online, brief locks only). Verified healthy after.
**Cluster:** PostgreSQL 17.10, `striatum_daemon`. **Window:** ~13:22–13:26 UTC (~06:22 PDT),
verified low-activity (7 idle backends, 0 active queries, no xact > 2 s, ~9–14 stmts/s).

## Motivation

`RECS_VERIFICATION_2026-06-17.md` (#1) flagged stable high-water-mark bloat on the daemon's
hot heartbeat/chain tables: the aggressive per-table autovacuum from `desired.md` holds dead
tuples at ~0 (90+ autovacuum runs/day) but plain VACUUM only returns space to the free-space
map — it does not truncate the file, so the physical bloat persisted. Operator approved an
off-peak `pg_repack` to reclaim it.

## Tooling installed (new cluster dependency)

- `postgresql-17-repack` (PGDG) → **`pg_repack` client 1.5.3**.
- `CREATE EXTENSION pg_repack` (v1.5.3) in `striatum_daemon` (schema `repack`: 2 views —
  `repack.tables`, `repack.primary_keys`).
- Run as `postgres` (superuser; one table is `postgres`-owned, three are `halbritt`-owned),
  with **`--no-kill-backend`** (pg_repack's default *kills* lock-blocking backends after its
  wait-timeout — unacceptable on the daemon's hottest tables) and `--wait-timeout=30`.

## Result — ~454 MB reclaimed

| table | live rows | before | after | owner |
|---|---|---|---|---|
| `process_supervisor_pointers` | 1,454 | 255 MB | **2.5 MB** | halbritt |
| `daemon_supervisors` | 1,454 | 93 MB | **1.46 MB** | halbritt |
| `process_supervisors` | 1,459 | 87 MB | **1.46 MB** | halbritt |
| `repo_event_chain_heads` | 19 | 24 MB | **32 KB** | postgres |

Each copy was near-instant — the *live* row counts are tiny; the size was almost all dead
space. All four `pg_repack` runs exited 0 with no killed backends and no errors in the PG log.

## Post-repack verification (all PASS)

- **10/10 indexes `indisvalid` + `indisready`** on the four tables, including the
  `uq_active_*` unique constraints — pg_repack rebuilt them correctly.
- **No orphan repack triggers** left behind; `repack` schema holds only the 2 extension views.
- Write path intact (no-op `UPDATE … WHERE false` planned + executed, rolled back).
- Cluster throughput alive (~9/s), backends idle/ClientRead (not lock-blocked), appends/
  heartbeats resume with daemon activity.

## Forward note — regrowth re-measured under load (2026-06-18, CORRECTS the above)

The "recurs slowly / flat day-over-day" read in the first draft was a sampling artifact —
both checks landed in quiet windows. Re-measured during a real workload burst (~510 stmts/s,
~35× the morning lull), `process_supervisor_pointers` regrew **2.5 MB → 149 MB in ~90 min**,
then plateaus (~150–255 MB). It does **not** run away.

Mechanism (diagnosed, not assumed):
- **Not** xmin-horizon pinning — the long (~106 s) daemon transactions are READ COMMITTED, so
  their snapshot advances (`age(backend_xmin)=7`).
- **Not** autovacuum failure — `n_dead_tup` returns to **0** (100+ autovac runs); dead tuples
  are reclaimed.
- **It is** plain heap extension: at burst rates the heartbeat `UPDATE`s outrun VACUUM's
  tail-truncation, and 8–20 % are non-HOT (`n_tup_newpage_upd`). Worst on
  `process_supervisor_pointers`: **80 % HOT / 20 % new-page**, because its `state` column is
  indexed (partial-unique on `state`, plus `idx_..._run` includes `state`), so any `state`
  change defeats HOT. `fillfactor=80` is correctly applied.

Impact is **low**: bounded plateau (~150–255 MB), `n_dead_tup`≈0, fully cached (<1 % of the
32 GB `shared_buffers`), index-accessed — not a stability/durability risk. So the **monthly
off-peak `pg_repack` is the right cadence**: it resets the plateau during a verified-quiet
window without adding ACCESS EXCLUSIVE lock pressure during bursts. Aggressive daily repacking
*during* active load would fight the daemon on its hottest tables for little gain. The true
root-cause fix is app-side, **filed as `striatum#421`**: cut the reconcile-loop write
amplification (~8.1M heartbeat writes/window) / avoid churning the indexed `state` column.
`desired.md` autovacuum tuning stays — it correctly bounds *dead tuples*, just not physical
file size.
