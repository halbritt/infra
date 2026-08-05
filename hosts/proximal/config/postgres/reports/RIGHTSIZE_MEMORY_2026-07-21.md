# Right-size memory GUCs for the contested-RAM era — 2026-07-21

**Change:** `shared_buffers 32GB → 16GB`, `effective_cache_size 96GB → 32GB`,
`maintenance_work_mem 2GB → 1GB`. Applied via `ALTER SYSTEM` + restart @ ~2026-07-21
22:0x UTC. Restart clean; all three preload libs loaded; `striatumd_rw` reconnected.

## Why

The 32 GB pool was sized on 2026-06-16 when the box was otherwise idle ("use all the
memory you want"). The host is no longer idle: llama-server (8 GiB host RSS + 21 GiB
VRAM), whisper, two Plane stacks, ~23 containers, 6 node processes, multiple agent
sessions. Observed before the change: **107/125 GiB used, swap 15.9/15.9 GiB full,
18 GiB available** — zero spillover headroom, with Postgres shmem the single largest
consumer (31.8 GiB of `Shmem`).

## Evidence (pg_buffercache, stats window = since 2026-06-17 upgrade, ~5 weeks)

Occupancy of the 32 GB pool at capture (`inventory/2026-07-21/`):

| segment | resident | hot (usagecount ≥ 3) |
|---|---|---|
| **empty / never used** | **11 GB** | — |
| engram (12 GB DB) | 10 GB | 10 GB — fully hot (pgvector) |
| striatum_daemon (29 GB DB) | 10 GB | **216 MB** — scan churn, tiny hot set |
| hippo | 1 GB | 1 GB |
| everything else | ~0.3 GB | ~0.2 GB |

True hot working set ≈ **11–12 GB**. A third of the pool sat empty; another third held
cold striatum scan pages that the OS page cache can serve equally well (striatum hit
rate 90.4% is scan-driven, not fit-driven — its hot set is a quarter-gigabyte).
16 GB covers the whole hot set with ~4 GB of slack for growth and striatum churn.

- `effective_cache_size 96GB` assumed a 76 GiB OS page cache that no longer exists
  (~15 GiB actual file cache). 32 GB ≈ new shared_buffers + realistic OS cache.
- `maintenance_work_mem 1GB`: PG17 TidStore vacuum rarely needs >1 GB; worst-case
  concurrent ceiling drops 6 GB → 3 GB.
- `work_mem 256MB` **left alone**: 2026-06-17 verification called it a non-lever, and
  current temp spills (engram 15 GB temp_bytes, avg spill ≫ 256 MB) would spill at any
  plausible setting. Not worth the regression risk on engram batch sorts.

## Result

`free` before → after: available **18 → 51 GiB**, swap used **15.9 → 13.2 GiB**,
shmem 31.8 → 0.8 GiB. Cluster healthy, clients reconnected, llama-server unaffected.

## Follow-up

- Warm-up: engram's 10 GB hot set must re-fault into the new pool; expect elevated
  `blks_read` for the first hours. Check `pg_stat_database` hit ratios in a few days —
  if engram's hit% degrades durably below ~99% or latency regresses, the next step is
  20 GB, not a full revert.
- Revert: `ALTER SYSTEM SET shared_buffers='32GB'; ALTER SYSTEM SET
  effective_cache_size='96GB'; ALTER SYSTEM SET maintenance_work_mem='2GB';` + restart
  (or `ALTER SYSTEM RESET …` to fall back to postgresql.conf values, which are the
  same 32GB/96GB/2GB — the old values still live there; auto.conf now overrides).
