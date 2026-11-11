# PostgreSQL storage migration to SSD2 — 2026-11-10

The owner authorized comparing synchronous-write performance on the existing
NVMe/ext4 storage and idle 960 GB Samsung SATA SSD, then moving PostgreSQL if
the SATA drive passed. This is a storage-placement change. Cluster version,
connection paths, authentication, schema and durability settings are preserved.

## Benchmark and decision

Before observing results, the gate required two runs with zero I/O errors,
SATA fdatasync p99 <= 5 ms, p99.9 <= 20 ms, and mean <= twice the paired NVMe
mean. fio 3.41 used one process, 8 KiB buffered sequential writes with fdatasync
after each write, a 64 MiB file, incompressible buffers and 30 seconds per run.
Tests ran sequentially on the actual source ext4 and destination Btrfs volumes.
PostgreSQL 18's pg_test_fsync ran on each volume twice, one second per subtest.
No benchmark files were placed inside the live cluster directory.

| Path / run | Write+flush cycles/s | Mean flush ms | p99 ms | p99.9 ms |
| --- | ---: | ---: | ---: | ---: |
| nvme / 1 | 187 | 5.314 | 10.289 | 14.746 |
| sata / 1 | 1592 | 0.614 | 1.270 | 3.490 |
| nvme / 2 | 482 | 2.053 | 6.783 | 10.682 |
| sata / 2 | 1524 | 0.640 | 1.221 | 3.523 |

Both pairs passed. pg_test_fsync's one-8-KiB-write fdatasync averages corroborated
the result: SATA 740/608 microseconds versus NVMe 1359/1366 microseconds.
Measurements include current filesystem behavior and host contention. These
short tests do not certify peak production query throughput or long-term CoW
fragmentation behavior. The move is justified by the declared durable-write
gate, dedicated capacity and release of NVMe space.

## Identity and preservation

- PostgreSQL 18/main, system identifier `7701748156229123175`.
- Logical data directory `/var/lib/postgresql/18/main` remains unchanged.
- Target `/srv/ssd2/postgresql`, a postgres-owned mode-0700 Btrfs subvolume.
- SSD Samsung MZ7KM960HAHP-0Z005, serial `S2L2NWAG700037N`, full 960 GB;
  filesystem UUID `1f2e26d5-78a7-4a1c-bfd0-9a48daa151cc`.
- `fsync`, `full_page_writes`, `synchronous_commit` stay on; `wal_level=replica`,
  `wal_sync_method=fdatasync`. PostgreSQL data checksums were already off and are
  unchanged. Btrfs CoW, checksums and zstd:1 remain enabled, data single and
  metadata DUP on this one drive.
- No external tablespaces or replication slots. Managed cluster includes Cairn.
- pgBackRest stanza `proximal`: latest differential backup healthy; WAL archive
  check passed before migration. NVR repository `/nvr/pg-backups` is unchanged.

## Execution and verification

Initial live rsync completed successfully: 128759919578 logical bytes, 13885
regular files, 141 seconds. PostgreSQL is then stopped cleanly and temporarily
runtime-masked to prevent accidental starts during the final sync. Offline
`rsync -aHAXc --delete` compares every file's contents and verifies transferred
contents; a metadata dry-run must report no changes and pg_control must match.
The original directory is retained until the new cluster is verified.

`../storage.fstab` is installed additively in `/etc/fstab`; it bind-mounts the
subvolume at the original data path, requires `/srv/ssd2`, and runs before
local-fs.target. `../storage.conf` is installed as
`/etc/systemd/system/postgresql@18-main.service.d/storage.conf`, requiring the
source and destination mounts and asserting that PGDATA is a mountpoint.
The hidden empty mountpoint is root-owned mode 000; `/srv/ssd2` is root-owned
0755 to protect the database directory from renaming by unprivileged clients.

Completed successfully. The offline checksum sync returned zero, the metadata
comparison was empty, and source/destination pg_control matched. The service
was unavailable for 161 seconds (16:23:08–16:25:49 PST). The same cluster started
as primary on SSD2. All 21 connectable databases passed catalog reads; system
identifier, database names and durability settings matched the captured values.
A new WAL restore point was written, and pgBackRest confirmed its WAL segment
archived to NVR. Cairn native MCP returned READY; Engram returned HTTP 200 and
its MCP health check reported db_reachable=true. Previously running system/user
services remained active; client connections re-established.

Confirmed the PostgreSQL unit requires both the SSD and bind mounts, with all
three units active. fstab validation passed (only the existing swapfile warning).
No process held the original cluster directory after cutover. Removed exactly
`/var/lib/postgresql/18/main.before-ssd-20261110` after verification and removed
the benchmark files. Reclaimed 119.9 GiB net; OS disk now about 524 GiB free.
SSD2 reports about 34 GiB used and 858 GiB available; compression includes WAL
and database files. All Btrfs device error counters remain zero; NVR healthy.
No reboot was needed. Actual boot was not tested; live mount dependency and
configuration checks establish the installed startup arrangement.

After admitting writes on SSD2, the new copy is authoritative. Any future move
back must copy the current cluster with the same stopped-writer consistency
procedure; an old snapshot would lose subsequent writes.

Local evidence: `~/.local/state/postgres-ssd-20261110/`, including raw fio and
pg_test_fsync results, benchmark-results.json, COPY_VERIFIED, metadata-diff.log,
CUTOVER, DATABASE_VERIFIED, database-checks.json, settings-before/after.txt and
migration-result.json. pgBackRest archive-check output was also observed live.

References: [PostgreSQL file-system copy consistency](https://www.postgresql.org/docs/18/backup-file.html)
and [pg_test_fsync scope](https://www.postgresql.org/docs/18/pgtestfsync.html).

