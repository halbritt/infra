# Baseline — accepted GUC set

The current accepted, non-default configuration for `proximal:5432`
(`system_identifier 7628053153555146077`, PostgreSQL 16.14, cluster `16/main`).
Default-valued GUCs are not listed.

First captured by the read-only inventory run on **2026-06-16**
(`CLAUDE_OPUS_4_8`, role `halbritt`). Evidence:
`inventory/2026-06-16/` (`pg_settings.tsv`, `non-default-settings.txt`).
The pre-session values below originate from the hand-edited
`/etc/postgresql/16/main/postgresql.conf`; their rationales are **inventory-derived
observations**. Changes applied this session via `ALTER SYSTEM`
(`postgresql.auto.conf`) are tracked in **Applied changes** below.

## Applied changes (this session — 2026-06-16)

| parameter | value | change | status | evidence / revert |
|---|---|---|---|---|
| `max_wal_size` | **16 GB** (was 1 GB) | P1, reload-class, `ALTER SYSTEM` + `pg_reload_conf()` @ 18:43 UTC | **APPLIED — VERIFIED** (loaded canary: 0 req / 6 timed checkpoints; was 89.7% WAL-triggered) | `reports/canary-P1-max_wal_size-2026-06-16.md`; revert `reports/rollback-P1-max_wal_size-2026-06-16.sql` |
| `shared_preload_libraries` | **`pg_stat_statements`** (was empty) | R1, restart-class, `ALTER SYSTEM` + restart @ 19:14 UTC | **APPLIED — verified loaded** (view queryable; defaults `max=5000`, `track=top`) | revert: `ALTER SYSTEM RESET shared_preload_libraries` + restart |

## Deliberate performance / WAL tuning (diverges from PostgreSQL stock defaults)

| parameter | value | raw | source | rationale (inventory-derived; unverified) |
|---|---|---|---|---|
| `shared_buffers` | ~~32 GB~~ → 16 GB | 2097152 × 8kB | `ALTER SYSTEM` (auto.conf overrides the 32GB in postgresql.conf) | Right-sized 2026-07-21: pg_buffercache showed true hot set ≈ 11–12 GB (11 GB of the 32 GB pool empty, 10 GB cold striatum scan pages); host RAM now contested (llama-server etc., swap was 100% full). `reports/RIGHTSIZE_MEMORY_2026-07-21.md`. |
| `effective_cache_size` | ~~96 GB~~ → 32 GB | 4194304 × 8kB | `ALTER SYSTEM` (overrides postgresql.conf) | Right-sized 2026-07-21: the 76 GiB OS page cache it assumed no longer exists (~15 GiB actual). ≈ shared_buffers + realistic OS cache. Same report. |
| `work_mem` | 256 MB | 262144 kB | configuration file | Raised 64× over the 4 MB default. ⚠️ headroom: `max_connections(100) × 256 MB` = 25.6 GB per single sort/hash node; multi-node queries at peak concurrency are unmeasured (no `pg_stat_statements`, quiet-window sample). |
| `maintenance_work_mem` | ~~2 GB~~ → 1 GB | 1048576 kB | `ALTER SYSTEM` (overrides postgresql.conf) | Halved 2026-07-21: PG17 TidStore vacuum rarely needs >1 GB; worst-case `autovacuum_max_workers(3) × 1 GB` = 3 GB. `reports/RIGHTSIZE_MEMORY_2026-07-21.md`. |
| `wal_buffers` | 64 MB | 8192 × 8kB | configuration file | Explicitly set above the auto (`-1`) default. `postmaster` (restart) context. |

## Explicitly set but equal to PostgreSQL stock defaults (recorded for provenance)

| parameter | value | note |
|---|---|---|
| `max_connections` | 100 | stock default; `postmaster` context. Peak usage observed: 19/100 client backends. |
| `max_wal_size` | ~~1 GB~~ → 16 GB | was stock default; **changed this session** (see Applied changes) to address ~90% WAL-triggered checkpoints. |
| `min_wal_size` | 80 MB | stock default. |

## Debian/Ubuntu packaging defaults (not deliberate tuning)

From the distro `postgresql.conf` template, not performance decisions:
`cluster_name=16/main`, `port=5432`, `ssl=on` (snakeoil cert/key),
`dynamic_shared_memory_type=posix`, `DateStyle=ISO, MDY`,
`default_text_search_config=pg_catalog.english`, `log_line_prefix=%m [%p] %q%u@%d`,
`log_timezone=Etc/UTC`, `TimeZone=Etc/UTC`, `lc_messages/monetary/numeric/time=en_US.UTF-8`.
