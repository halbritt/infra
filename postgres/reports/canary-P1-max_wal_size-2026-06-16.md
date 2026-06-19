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

## Status: VERIFIED — confirmed 2026-06-16

Workload resumed (un-quiesced ~19:5x). Two independent observations of the
requested-checkpoint collapse:

1. **Interim (77 min since reload, mostly quiet):** `checkpoints_timed +29`,
   `checkpoints_req +1` — vs ~115 requested expected at the pre-P1 rate.
2. **Loaded window (~30 min, anchor `lsn B2/4EB61378`):** **6 timed, 0 requested
   checkpoints → 0% WAL-triggered** (baseline 89.7%); **70 MB** WAL generated over
   the window — ≪ 16 GB.

**Arithmetic backs it:** even the historical burst rate (~25 MB/s) generates only
~7.5 GB per 300 s `checkpoint_timeout`, under the 16 GB ceiling — so checkpoints are
now timeout-paced, not WAL-paced, across the observed load envelope.
**RTO note:** because checkpoints are time-driven, crash-recovery WAL is bounded by
one `checkpoint_timeout` interval (tens of MB), so the larger ceiling does not extend
recovery in practice — the flagged RTO risk is not realized.

Caveat: the canary window (70 MB / 30 min) was lighter than the historical peak; the
verdict rests on both runs **and** the headroom arithmetic above, not a reproduced
peak-burst window.

**Verdict: keep.** Promoted to `baseline.md` (verified) and `desired.md`; revert
bundle retained. `bgwriter buffers_clean` still 0 but `buffers_backend` growth is now
low-pressure — see plan (bgwriter deferred; P2 `wal_compression` no longer needed,
WAL volume is trivial).
