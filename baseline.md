# Baseline — accepted GUC set

The current accepted, non-default configuration for `proximal:5432`
(`system_identifier 7628053153555146077`, PostgreSQL 16.14, cluster `16/main`).
Default-valued GUCs are not listed.

First captured by the read-only inventory run on **2026-06-16**
(`CLAUDE_OPUS_4_8`, role `halbritt`). Evidence:
`inventory/2026-06-16/` (`pg_settings.tsv`, `non-default-settings.txt`).
All values currently originate from the hand-edited
`/etc/postgresql/16/main/postgresql.conf`; `postgresql.auto.conf` is empty
(no `ALTER SYSTEM` overrides applied). Rationales below are **inventory-derived
observations**, not yet validated by a tuning report — the first run is plan-only.

## Deliberate performance / WAL tuning (diverges from PostgreSQL stock defaults)

| parameter | value | raw | source | rationale (inventory-derived; unverified) |
|---|---|---|---|---|
| `shared_buffers` | 32 GB | 4194304 × 8kB | configuration file | ≈ 26% of 125 GiB RAM and ≈ the whole ~40 GB working set; cache-hit ratios 97–100% across DBs. `postmaster` (restart) context. |
| `effective_cache_size` | 96 GB | 12582912 × 8kB | configuration file | Planner hint ≈ 77% of RAM; consistent with large OS page cache (76 GiB buff/cache observed). |
| `work_mem` | 256 MB | 262144 kB | configuration file | Raised 64× over the 4 MB default. ⚠️ headroom: `max_connections(100) × 256 MB` = 25.6 GB per single sort/hash node; multi-node queries at peak concurrency are unmeasured (no `pg_stat_statements`, quiet-window sample). |
| `maintenance_work_mem` | 2 GB | 2097152 kB | configuration file | Faster autovacuum/index builds; up to `autovacuum_max_workers(3) × 2 GB` = 6 GB concurrent. |
| `wal_buffers` | 64 MB | 8192 × 8kB | configuration file | Explicitly set above the auto (`-1`) default. `postmaster` (restart) context. |

## Explicitly set but equal to PostgreSQL stock defaults (recorded for provenance)

| parameter | value | note |
|---|---|---|
| `max_connections` | 100 | stock default; `postmaster` context. Peak usage observed: 19/100 client backends. |
| `max_wal_size` | 1 GB | stock default — but checkpoints are ~90% WAL-triggered (`checkpoints_req 3402` vs `checkpoints_timed 390`), a candidate bottleneck. |
| `min_wal_size` | 80 MB | stock default. |

## Debian/Ubuntu packaging defaults (not deliberate tuning)

From the distro `postgresql.conf` template, not performance decisions:
`cluster_name=16/main`, `port=5432`, `ssl=on` (snakeoil cert/key),
`dynamic_shared_memory_type=posix`, `DateStyle=ISO, MDY`,
`default_text_search_config=pg_catalog.english`, `log_line_prefix=%m [%p] %q%u@%d`,
`log_timezone=Etc/UTC`, `TimeZone=Etc/UTC`, `lc_messages/monetary/numeric/time=en_US.UTF-8`.
