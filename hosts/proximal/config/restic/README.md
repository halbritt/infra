# restic off-site backup (proximal → `gs://proximal-backups`)

This directory holds copies of what is installed on proximal. The secrets stay
on the host and are not copied here.

| Item | Installed at |
|---|---|
| [restic-backup-locked](restic-backup-locked) | `/usr/local/libexec/caplab-p5/restic-backup-locked` |
| [restic-prune-locked](restic-prune-locked) | `/usr/local/libexec/caplab-p5/restic-prune-locked` |
| [home-excludes.txt](home-excludes.txt) | `/etc/restic/home-excludes.txt` |
| [systemd/](systemd/) units | `/etc/systemd/system/restic-{backup,prune}.{service,timer}` |
| [systemd/](systemd/) drop-ins | `/etc/systemd/system/restic-*.service.d/{20-caplab-p5-lock,30-cache}.conf` |
| Environment | `/etc/restic/proximal.env`, holding `RESTIC_REPOSITORY`, `RESTIC_PASSWORD_FILE`, `GOOGLE_PROJECT_ID` and `GOOGLE_APPLICATION_CREDENTIALS` (all root-only) |
| Secrets (not in git) | `/etc/restic/password` and the bucket's service-account key `/etc/restic/gcs-sa.json` |
| Cache | `/var/cache/restic`, created by systemd `CacheDirectory=restic` |

**Repository.** `gs:proximal-backups:/` in project heath-stuff: Nearline,
us-west1, about 1.39 TB on 2026-10-22, 7-day soft delete. Storage is roughly
$15 a month at list price. Reads (restores, `check`, `prune`) add Nearline
retrieval and egress charges. Deleting objects younger than 30 days costs as if
they had been kept 30 days.

**Schedule.**
- **Backup:** daily at 02:30 (`Persistent=true`, up to 20 minutes of random delay).
- **Prune and check:** monthly, on the 1st at 03:30.

**What is backed up.**
- **Paths:** `/nvr/pg-backups`, `/nvr/engram-backups`, `/nvr/archive` (excluding
  `/nvr/archive/claude-scratch`) and `/home/halbritt`, minus `home-excludes.txt`.
- **Symlinks:** restic does not follow them. Anything archived out of home
  behind a symlink must be added to the backup script, as `/nvr/archive` was
  on 2026-10-17.
- **Locking:** both scripts take `/run/lock/caplab-backup.lock`, so backup and
  prune never overlap.
- **Retention:** `forget` keeps 7 daily, 4 weekly and 6 monthly snapshots. It
  runs after any backup that saved a snapshot, including exit 3.
- **Exit 3:** the snapshot was saved, but some files could not be read
  (usually live sqlite `-wal`/`-shm` files that vanished mid-run). The unit
  still reports the 3, and the unreadable paths are in the journal.

**Check it.**

```sh
systemctl status restic-backup.service; systemctl list-timers 'restic-*'
sudo journalctl -u restic-backup -n 30 --no-pager      # "snapshot … saved", "processed N files … in H:MM:SS"
```

## History

- **2026-10-22: no cache.** systemd sets no `HOME` for this root service, so
  every run logged `unable to open cache: … neither $XDG_CACHE_HOME nor $HOME
  are defined`. restic then fetched every tree blob of the parent snapshot from
  the Nearline bucket, one request at a time. Runs took 117 h (finished
  10-15) and 76 h (finished 10-18). The run started on 10-19 was still going
  after 3.7 days, nearly idle.
  - Fix: drop-in `30-cache.conf` (`CacheDirectory=restic`,
    `RESTIC_CACHE_DIR=/var/cache/restic`) for both units, seeded from the old
    July manual cache in `/root/.cache/restic`.
  - The stalled run was stopped with SIGTERM and restarted.
- **2026-10-22: retention never ran.** Every backup since `/nvr/archive` was
  added ended with exit 3, and `set -e` stopped the script before
  `restic forget`.
  - Fix: `forget` now runs on exit 0 or 3, and the script still exits with
    the backup's status.
  - The previous script is kept on the host as
    `restic-backup-locked.pre-cache-20261022`.
