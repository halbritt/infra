# Cairn candidate detail retention on Proximal

**Window: 14 days.** The owner chose this on 2026-11-01 from measured options, after
the investigation in
[cairn-storage-20261101.md](../observability/cairn-storage-20261101.md). The contract
and commands are in Cairn's `docs/candidate-retention.md`.

| Window | Freed on 2026-11-01 | Settles near | Why not chosen |
| --- | --- | --- | --- |
| **14 days** | about 103 GiB | about 50 GiB | Chosen. Long enough to investigate a retrieval problem noticed a week or two later, and it can be shortened at any time |
| 7 days | about 165 GiB | about 25 GiB | Older detail could not be explained or recompiled without a restore |
| 30 days | none | about 110 GiB | The retained 165 GiB did not fit a rewrite with safe headroom |
| 90 days | none until December | about 320 GiB | The pinned design's number for compacting receipts; it left the disk pressure in place |

"Settles near" assumes the write rate of the week before the decision, about 3.6 GiB
a day. Each search writes one row per note it evaluates, so the rate grows with both
search volume and note count. The bound moves with them.

## What runs

`cairn-candidate-retention.timer` starts `cairn-candidate-retention.service` daily at
about 04:20, after the backup and off-site jobs. It expires receipts older than 14
days, one per transaction, and logs its result as JSON to the journal. It stops at
its time and pressure limits, and the next run resumes.

Install both files under `~/.config/systemd/user/`, plus `managed-database.conf` as
`cairn-candidate-retention.service.d/50-managed-database.conf`, then:

```sh
systemctl --user daemon-reload
systemctl --user enable --now cairn-candidate-retention.timer
journalctl --user -u cairn-candidate-retention.service -n 5 -o cat
```

## If storage grows too fast

`CairnDatabaseGrowingFast` and `CairnDatabaseLarge` remain the signals, and
`CairnCandidateRetentionStalled` fires if rows are inserted for four days with none
deleted. To shorten the window, change `window_days` in the service and run it. That
reuses space but does not return it to the filesystem. `cairn candidate-reclaim`
returns it; see Cairn's `docs/candidate-retention.md`.

## Recovery

- **Rows expired by the 2026-11-01 rewrite:** a verified archive of every candidate row
  at that point is at `/nvr/archive/cairn/retrieval-candidate-archive-20261101/`:
  267,355,652 rows in 14.7 GB, in `COPY` text format, with a SHA-256 sidecar. It stays
  local to this host and is not shipped off-site. It can be deleted once the owner no
  longer wants that history. To restore receipts, extract their rows with
  `zstd -dc FILE | grep -F RECEIPT_UUID > rows.copy`, then follow "Recovery" in Cairn's
  `docs/candidate-retention.md`.
- **Rows expired later:** restorable only through pgBackRest, until the backups holding
  them rotate out, about one to two weeks. See
  [backups.md](../postgres/backups.md). Follow Cairn's `docs/restore-admission.md` for
  a store-level restore.
- **Binary rollback:** do not roll back to a binary older than migration 074 once
  anything has expired. Older binaries report an expired receipt as having no
  candidates.

## The 2026-11-01 rewrite

| Measure | Before | After |
| --- | --- | --- |
| Database `cairn` | 193 GB | 89 GB |
| `retrieval_candidate` | 190 GB, 267M rows | 87 GB (80 heap, 7 index), 125M rows |
| Root filesystem free | 101 GiB just before the drop | 293 GiB (84% used) |

The database figures are logical sizes. The filesystem figures are what `df` reported.
Free space was about 201 GiB when the rewrite started, so the net gain is about
92 GiB. Disk use by other work on this host moved during the same period, and `pg_wal`
still held 16 GB that is recycled over time. Expired rows also stay in pgBackRest until
those backups rotate out, so `/nvr/pg-backups` grew from 122 to 134 GiB for now.

Sequence, all online, on Cairn revision `0f2917a`:

| Step | Time (PST) | Result |
| --- | --- | --- |
| Backup | 18:50 | Differential `20261101-010848F_20261101-185001D` |
| Migration 074 | 18:53 | First attempt, under a 2 s lock timeout; digest matched source |
| Binary and services | 18:53 | All ten services restarted; zero unfinished wakes or leases beforehand |
| Small batch | 18:53 | 5 receipts; refusals, recompile seal and docket checked |
| `plan`, `copy` | 18:54 to 19:32 | 55,472 receipts marked; 125.2M rows copied; 87.6 GB of WAL; archive backlog held at its limit of 256 segments |
| `build` | 19:33 to 19:38 | Primary key, index and foreign keys validated |
| `swap` | 19:38:20 | **73 ms** under the drain, first attempt |
| `verify` | 19:38 to 19:41 | Every receipt's row count, and byte digests of 500 sampled receipts, matched |
| `finish` | 19:42 | Old relation dropped |
| First daily pass | 19:42 | 83 receipts, 308,641 rows, 222 MB of WAL |

Zero rows were retained for expired receipts: the scan found no blocked demand and no
gate refusals in the history.

Impact: the copy slowed some searches. During the 44 minutes of `copy` and `build`, 2 of
9 prompt hooks hit their time budget, against 5 of 266 in the previous 24 hours, and
clients cancelled 15 statements, mostly compiles. No errors were logged after the swap.

Before running this, a full restore of the same backup chain succeeded in 768 seconds on
an isolated `/nvr` target, and the same sequence was rehearsed on that copy. Twelve
sampled receipts in the restore and 8 in the archive matched production byte for byte.
Rehearsing exposed a CLI deadline that unit tests had not, and two independent reviews
found a stale-snapshot race, unbounded holds and a migration deadlock, all fixed first.
Cairn's `docs/verification/cairn-deployment-2026-11-01.md` has the release record.
