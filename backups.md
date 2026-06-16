# Backups & PITR — proximal:5432

Physical backups + point-in-time recovery via **pgBackRest**, landing directly on
the **`nvr` ZFS pool** (10 TB spinning disk) — not through Garage/S3. Mirrors the
existing `nvr/engram-backups` pattern; the pool is then replicated off-site.

## Architecture

```
PostgreSQL 16/main ──pgBackRest──▶ /nvr/pg-backups  (ZFS dataset on pool `nvr`)
   archive_command: pgbackrest --stanza=proximal archive-push %p   (WAL stream → PITR)
                                          │
                                          └── off-site: zfs send nvr/* ▶ remote  (operator)
```

- **Repo:** `/nvr/pg-backups` — ZFS dataset, `recordsize=1M`, `atime=off`,
  `compression=off` (pgBackRest compresses with zstd). Owned `postgres:postgres 0750`.
- **Stanza:** `proximal` → `pg1-path=/var/lib/postgresql/16/main`, socket auth as `postgres`.
- **Config:** `/etc/pgbackrest/pgbackrest.conf` (retention: 2 full / 6 diff; `compress-type=zst`).
- **Encryption:** **none** (matches `nvr/engram-backups`). For the off-site copy, add
  either ZFS-native encryption on the dataset (raw `zfs send` stays encrypted) or
  pgBackRest `repo-cipher-type=aes-256-cbc` + `repo-cipher-pass`. Recommended before
  replicating off-site; not yet enabled.

## Status (2026-06-16)

- ✅ Dataset, pgBackRest 2.50 installed, config written, **stanza created**.
- ✅ **PITR live (2026-06-16 22:08 UTC):** `archive_mode=on` (bundled restart with the
  `pg_qualstats`/`pg_stat_kcache` `shared_preload_libraries` change), `pgbackrest check`
  passed (WAL archived to repo); **first full backup done** (`20260616-220907F`):
  37.9 GB DB → 3.6 GB repo (zstd ~10.5×), status `ok`. WAL now streams to
  `/nvr/pg-backups/archive/` on every segment switch.
- ⚠️ The bundled restart hit an `ALTER SYSTEM` list-quoting bug (~1–2 min downtime);
  see `known-bad.md`. Recovered by hand-fixing `postgresql.auto.conf`.
- ⏭️ Still to do: enable a recurring schedule (below); add encryption before off-site.

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

## Recurring schedule (wire after the first successful backup)

Suggested (systemd timers or cron, run as `postgres`): weekly `--type=full`, daily
`--type=diff`. Retention (2 full / 6 diff) prunes automatically. `nvr` has ~9 TB free.

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
