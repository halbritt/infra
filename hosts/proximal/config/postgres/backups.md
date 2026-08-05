# Backups & PITR — proximal:5432

Physical backups + point-in-time recovery via **pgBackRest**, landing directly on
the **`nvr` ZFS pool** (10 TB spinning disk) — not through Garage/S3. Mirrors the
existing `nvr/engram-backups` pattern; the pool is then replicated off-site.

## Architecture

```
PostgreSQL 16/main ──pgBackRest──▶ /nvr/pg-backups  (ZFS dataset on pool `nvr`)
   archive_command: pgbackrest --stanza=proximal archive-push %p   (WAL stream → PITR)
                                          │
   /nvr/engram-backups ──┐                │
                         └──restic (encrypted)──▶ gs://proximal-backups  (GCS Nearline, off-site)
```

- **Repo:** `/nvr/pg-backups` — ZFS dataset, `recordsize=1M`, `atime=off`,
  `compression=off` (pgBackRest compresses with zstd). Owned `postgres:postgres 0750`.
- **Stanza:** `proximal` → `pg1-path=/var/lib/postgresql/16/main`, socket auth as `postgres`.
- **Config:** `/etc/pgbackrest/pgbackrest.conf` (retention: 2 full / 6 diff; `compress-type=zst`).
- **Encryption:** local on-disk repo on `nvr` is **unencrypted** (matches
  `nvr/engram-backups`). The **off-site** copy IS encrypted — restic encrypts
  client-side before upload. Local at-rest encryption (ZFS-native dataset) remains
  optional if the physical box matters.

## Off-site (restic → GCS Nearline)

restic backs up the local backup repos to Google Cloud Storage, encrypted client-side.

- **Repo:** `gs:proximal-backups:/` → bucket `gs://proximal-backups`, **Nearline**,
  us-west1, project `heath-stuff`. (Nearline over Coldline: at this volume the storage
  saving is pennies and Coldline's 90-day min-duration penalises restic's prune churn;
  Nearline's 30-day min fits better.)
- **Backs up:** `/nvr/pg-backups` + `/nvr/engram-backups`.
- **Auth:** service account `restic-proximal@heath-stuff` (Storage Object Admin scoped
  to this bucket only). Key + repo password + env are **root-only on the box, NOT in
  git**: `/etc/restic/gcs-sa.json`, `/etc/restic/password`, `/etc/restic/proximal.env`.
- **Schedule:** `restic-backup.timer` daily 02:30 (`backup` + `forget` keep 7d/4w/6m);
  `restic-prune.timer` monthly (`prune` + `check`).
- **First snapshot:** `e74b5e2a` (2026-06-17), 6229 files, **5.83 GiB stored**.

> ⚠️ **Disaster recovery needs the restic password.** It lives at `/etc/restic/password`
> AND must be saved off-box (password manager). If the box is gone, you need the password
> + GCS access to read the bucket — losing the password makes the off-site repo
> unrecoverable.

### restic restore quick-reference
```bash
set -a; source /etc/restic/proximal.env          # as root
restic snapshots                                  # list
restic restore latest --target /var/tmp/restore --include /nvr/pg-backups
# then point pgBackRest at the restored repo, or pgbackrest restore for PITR.
```

## Status (2026-06-16)

- ✅ Dataset, pgBackRest 2.50 installed, config written, **stanza created**.
- ✅ **PITR live (2026-06-16 22:08 UTC):** `archive_mode=on` (bundled restart with the
  `pg_qualstats`/`pg_stat_kcache` `shared_preload_libraries` change), `pgbackrest check`
  passed (WAL archived to repo); **first full backup done** (`20260616-220907F`):
  37.9 GB DB → 3.6 GB repo (zstd ~10.5×), status `ok`. WAL now streams to
  `/nvr/pg-backups/archive/` on every segment switch.
- ⚠️ The bundled restart hit an `ALTER SYSTEM` list-quoting bug (~1–2 min downtime);
  see `known-bad.md`. Recovered by hand-fixing `postgresql.auto.conf`.
- ✅ **Off-site live (2026-06-17):** restic → GCS Nearline (encrypted), daily timer
  (see Off-site section). First snapshot `e74b5e2a`, 5.83 GiB.
- ✅ **pgBackRest schedule live (2026-06-17):** daily diff (01:30) + weekly full
  (Sun 01:00) systemd timers. Validated via the unit — diff `…_20260617-004654D`
  (13 GB changed → 1.2 GB) ran as `postgres`, exit 0. Loop closed: pgBackRest produces
  restore points → restic ships them off-site daily.
- ⏭️ Optional only: local at-rest encryption of `/nvr` (off-site is already encrypted).

## Activation runbook (next restart window — bundles all pending restart-class changes)

```bash
# 1. (optional) quiesce writers
# 2. stage the bundled restart-class GUCs (archive_command already set)
sudo -u postgres psql -d postgres -c \
 "ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements,pg_qualstats,pg_stat_kcache';"
sudo -u postgres psql -d postgres -c "ALTER SYSTEM SET archive_mode = on;"
# 3. restart
sudo systemctl restart postgresql@16-main
# 4. verify
sudo -u postgres psql -d postgres -c \
 "select name,setting,pending_restart from pg_settings where name in ('archive_mode','shared_preload_libraries');"
# 5. confirm archiving works (pushes a test WAL), then first full backup
sudo -u postgres pgbackrest --stanza=proximal check
sudo -u postgres pgbackrest --stanza=proximal backup --type=full
# 6. enable the new query extensions
sudo -u postgres psql -d postgres  -c "CREATE EXTENSION pg_qualstats; CREATE EXTENSION pg_stat_kcache;"
sudo -u postgres psql -d template1 -c "CREATE EXTENSION pg_qualstats; CREATE EXTENSION pg_stat_kcache;"
sudo -u postgres pgbackrest --stanza=proximal info     # confirm backup present
```
Stanza is pre-created, so once `archive_mode=on` the `archive_command` succeeds
immediately — no WAL pile-up window.

## Recurring schedule (live)

systemd timers (run `pgbackrest` as `postgres`); ordered so backups precede the restic
off-site ship:

| timer | when | action |
|---|---|---|
| `pgbackrest-diff.timer` | daily 01:30 | `pgbackrest --type=diff backup` |
| `pgbackrest-full.timer` | weekly Sun 01:00 | `pgbackrest --type=full backup` |
| `restic-backup.timer` | daily 02:49 | restic ship `/nvr/pg-backups`+`/nvr/engram-backups` → GCS |
| `restic-prune.timer` | monthly | restic `prune` + `check` |

Retention auto-expires per `pgbackrest.conf` (2 full / 6 diff). `nvr` has ~9 TB free.
Units: `/etc/systemd/system/{pgbackrest-full,pgbackrest-diff,restic-backup,restic-prune}.{service,timer}`.

## Restore quick-reference

```bash
# inspect
sudo -u postgres pgbackrest --stanza=proximal info
# PITR restore (stop PG, restore to a target time, then start to replay WAL):
sudo systemctl stop postgresql@16-main
sudo -u postgres pgbackrest --stanza=proximal --type=time \
  --target="2026-06-16 18:00:00+00" --delta restore
sudo systemctl start postgresql@16-main
```
Revert the whole setup: `ALTER SYSTEM RESET archive_mode; RESET archive_command;`
restart; the repo on `/nvr/pg-backups` can be kept or `zfs destroy nvr/pg-backups`.
