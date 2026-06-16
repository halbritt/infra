# Canary / verification — P1 `max_wal_size` 1 GB → 16 GB — 2026-06-16

Plan: `PROXIMAL_16_MAIN_POSTGRES_TUNING_PLAN_CLAUDE_OPUS_4_8_2026-06-16.md` ·
Revert: `rollback-P1-max_wal_size-2026-06-16.sql` (staged, drift-guarded).

## Applied
- Staged via `ALTER SYSTEM SET max_wal_size = '16GB'` (postgres superuser), then made
  live with `SELECT pg_reload_conf()` at **2026-06-16 18:43:20 UTC**.
- Clean reload confirmed: log `received SIGHUP, reloading configuration files` →
  `parameter "max_wal_size" changed to "16GB"`; `pg_file_settings` shows
  `postgresql.auto.conf` entry `applied=t`, no `error`; live `pg_settings` =
  `16384 MB`, `pending_restart=false`. Server stayed up (no dropped connections —
  `sighup` reload). Reload-class, no restart.

## "Before" anchor (cumulative `pg_stat_bgwriter`, captured immediately pre-reload)
Window since `stats_reset 2026-06-15 03:01:02 UTC`:

| metric | value at reload |
|---|---|
| `checkpoints_timed` | 393 |
| `checkpoints_req` | 3445 |
| `buffers_checkpoint` | 4,715,626 |
| `buffers_clean` (bgwriter) | 0 |
| `buffers_backend` | 4,117,594 |
| `buffers_alloc` | 5,665,548 |
| `pg_current_wal_lsn()` | `B2/2750C8B8` |

Pre-change ratio: **89.7% of checkpoints WAL-triggered** (3445 req / 3838 total).

## Verification method (delta from the anchor — NOT cumulative)
Counters are monotonic and dominated by 37 h of pre-change history, so measure the
**delta** after the reload over a representative write window:
- `d_timed = checkpoints_timed_now − 393`, `d_req = checkpoints_req_now − 3445`.
- **Pass (confirm):** `d_req / (d_req + d_timed)` falls well below the 89.7% baseline
  (target: checkpoints become predominantly time-driven, i.e. roughly one per
  `checkpoint_timeout`=300 s of active write), and `buffers_backend` growth slows
  relative to `buffers_checkpoint`.
- **Fail (refute):** ratio unchanged → 16 GB still fills inside 300 s → WAL rate
  higher than estimated; re-measure a busy-window WAL rate and re-size, or run the
  revert bundle and log to `known-bad.md`.

## Status: PENDING representative window
At reload the instance was being quiesced (≈10–11 client backends, striatum daemon
partly torn down — note the unrelated pre-existing `daemon authority secret missing`
app errors). A meaningful checkpoint-ratio delta needs the normal write workload to
resume and run for a representative period (hours, ideally spanning a peak). Until
then the change is **applied but unverified**; `baseline.md` / `desired.md` are NOT
updated yet, and the revert bundle remains staged.
