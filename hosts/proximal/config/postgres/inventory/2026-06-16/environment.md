# Environment inventory — 2026-06-16

Read-only Preflight snapshot (POSTGRES_TUNING.md Preflight, steps 1–7). Captured by
`CLAUDE_OPUS_4_8` as role `halbritt` (non-superuser) over the local unix socket.
Evidence only — do not edit after the fact.

## Cluster identity
| field | value |
|---|---|
| `system_identifier` | `7628053153555146077` |
| version | PostgreSQL 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1), x86_64 |
| cluster | `16/main` (Debian/Ubuntu packaging) |
| data directory | `/var/lib/postgresql/16/main` (mode 0700 postgres; not readable as `halbritt`) |
| config file | `/etc/postgresql/16/main/postgresql.conf` |
| `postgresql.auto.conf` | present but **empty** (header only) — no `ALTER SYSTEM` overrides ever applied |
| `conf.d/` drop-ins | none (directory empty) |
| `pg_is_in_recovery()` | `false` → **standalone primary** |
| topology | 0 replication slots, 0 WAL senders → no standbys, no slots pinning WAL |

## Host (confirmed live, not from docs)
| field | value |
|---|---|
| RAM | 125 GiB total (`MemTotal` 131,817,780 kB); ~92 GiB available, 76 GiB buff/cache at capture |
| swap | 15 GiB, 0 used |
| CPU | Intel i5-11400F — 6 cores / 12 threads |
| OS | Ubuntu 24.04.4 LTS, kernel 6.8.0-124-generic |
| storage class | **NVMe** — data dir on `/` (ext4) → LV `ubuntu-vg/ubuntu-lv` → `/dev/nvme0n1p3` (Samsung SSD 990 PRO 2TB, `rotational=0`) |
| free disk (data+WAL FS) | **~1019 GiB free / 1.8 TiB, 42% used** — `pg_wal` is on the same NVMe filesystem |
| other disk | `/dev/sda` ST10000VE001 10TB spinning (`rotational=1`) — **not** backing PostgreSQL |

## Extensions installed (all databases scanned at instance level)
| extension | version | note |
|---|---|---|
| `plpgsql` | 1.0 | default |
| `vector` (pgvector) | 0.6.0 | used by `engram`/`hippo` embeddings (227k `segment_embeddings` rows) |

`pg_stat_statements` is **NOT** loaded (absent from `shared_preload_libraries`).
Query-level reasoning is therefore unavailable this run — all workload claims below
are instance- or table-level only.

## Databases (size desc)
| database | size | note |
|---|---|---|
| `striatum_daemon` | 34 GB | busiest by transaction volume; role `striatumd_rw` |
| `hippo` | 2980 MB | engram phase-2 segments/embeddings (pgvector) |
| `engram` | 941 MB | personal knowledge graph |
| `engram_test` | 92 MB | test DB |
| `engram_test_worker_e` | 32 MB | test worker DB |
| `engram_test_worker_e2e_runner_2` | 27 MB | test worker DB |
| `striatum_pgtest_*` | ~10 MB | transient striatum test DBs (name carries a nonce) |
| `ob1` | 7625 kB | |
| `postgres` | 7615 kB | maintenance DB |

## Role used for inventory
`halbritt` — `rolsuper=f`, `rolcreaterole=t`, `rolcreatedb=t`, `rolreplication=f`,
`rolbypassrls=f`, login via **peer auth** on the unix socket. Non-superuser, so
`pg_settings.sourcefile`/`sourceline` and `data_directory` were not readable (require
`pg_read_all_settings`); config-file paths above were resolved from systemd + packaging
layout, and config checksums via read-only `sudo` (see `config-checksums.txt`).

## Evidence files in this snapshot
- `pg_settings.tsv` — full 343-row `pg_settings` dump (the provenance baseline)
- `non-default-settings.txt` — the 24 settings with `source != default`
- `config-checksums.txt` — sha256 of `postgresql.conf`, `postgresql.auto.conf`, `pg_hba.conf`
- `workload-signal.txt` — connections, cache-hit, temp files, checkpoints, deadlocks, db sizes
- `reliability-and-autovacuum.txt` — reliability-frontier walk + per-table autovacuum/freeze age
