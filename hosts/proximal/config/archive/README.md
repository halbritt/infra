# archive — cold data on the ZFS pool

`nvr/archive` (mounted at `/nvr/archive`, `compression=zstd`, `atime=off`, owned
by `halbritt`) holds cold data moved off the root LV. Every moved path left a
symlink in its place, so existing paths still work.

| Original path | Archive path |
|---|---|
| `~/git/surveyor/runs` | `/nvr/archive/surveyor-runs` |
| `~/git/striatum-tuner/out` | `/nvr/archive/striatum-tuner/out` |
| `~/git/striatum-tuner/eval-runs/<untracked entry>` | `/nvr/archive/striatum-tuner/eval-runs/<entry>` (git-tracked entries stayed) |
| `~/.local/share/striatum-tuner` | `/nvr/archive/striatum-tuner/share` |
| `~/.local/share/striatum` | `/nvr/archive/striatum-proximal-retired-20261031` |
| `~/council-artifacts` | `/nvr/archive/council-artifacts` |
| `~/.local/share/cairn/backups` | `/nvr/archive/cairn/backups` |
| `~/.local/share/cairn/retired-postgres-20260929` | `/nvr/archive/cairn/retired-postgres-20260929` |
| `~/.local/state/runpod-jobrunner` | `/nvr/archive/runpod-jobrunner-state` |
| `~/.local/share/agent-ee/campaign-2026-10-26` | `/nvr/archive/agent-ee/campaign-2026-10-26` |
| `~/.local/share/agent-ee/zeroasic-20261028-agent688` | `/nvr/archive/agent-ee/zeroasic-20261028-agent688` |
| `~/.local/share/agent-ee/zeroasic-20261029-agent706` | `/nvr/archive/agent-ee/zeroasic-20261029-agent706` |
| `/tmp/claude-1000/-home-halbritt-git-quartermaster/bdaec7d9-…` (dead session, Oct 8–9) | `/nvr/archive/claude-scratch/quartermaster-bdaec7d9-20261009` (no symlink) |
| locally built Docker images (runpod-jobrunner-noop, checkout-refs-runner, kayakgen-*, harbor-prebuilt) | `/nvr/archive/docker-images/local-images-20261017.tar` (`docker load -i`) |

Off-site backup: restic does not follow symlinks, so
`/usr/local/libexec/caplab-p5/restic-backup-locked` (tracked since 2026-10-22 in [config/restic](../restic/README.md);
the previous copy is saved beside it as `.pre-archive-20261017`) now also backs
up `/nvr/archive`, excluding `/nvr/archive/claude-scratch`. That keeps
coverage the same as before the move.


## Root-disk cleanup — 2026-10-31

Root reached 91% usage with about 168 GiB free. Cleared disposable APT, pip,
npm and unused uv cache entries through their native tools; pruned Docker build
cache unused for at least 24 hours while reserving 10 GB; vacuumed archived
journals to at most 14 days and 1 GiB. Docker reported 18.37 GB reclaimed, uv
5.7 GiB, pip 816 MB, and journal vacuum 1.4 GiB. Dangling-image pruning freed
no additional space. Docker volumes and tagged images were retained.

The directories under `~/.cache` include engineering evidence and worktrees,
so the cache name alone did not justify deletion. The 214 GiB
`agent-ee/zeroasic-20261029-agent707` run tree had a live Docker test writing
its log and was left in place, along with its build cache. The cold archive is
already included in the existing restic backup paths; it remains writable.


Moved the retired Striatum store (89 GiB) and the two inactive Agent EE run
series listed above (about 76 GiB together). Both copies used `rsync -aHAX`
to preserve modes, owners, ACLs, extended attributes, hardlinks and symlinks;
rsync verified each transferred file with its native whole-file checksum.
Post-copy directory comparisons checked for missing, extra or changed paths.
Removed one archive-only temporary file left by an interrupted initial copy.
Striatum had 501 SQLite `.db-shm` files whose timestamps changed during the
copy; resynchronized those files and separately checksum-compared them.
No other differences remained.

Checked `/proc` for open source handles before each move, and mapped source
files before the Striatum move. An audit found no working relative symlinks
escaping the three moved trees. Renamed each original to a staging path,
installed its archive symlink, then removed the verified staging copy. The
original paths remain readable and writable. The active Agent EE run,
application source checkouts, databases, model files, Talos relays and shared
authentication remain in place.


Final root availability was 356 GiB, up from 168 GiB (91% used to 80%).
The net gain is about 188 GiB while other workloads continue writing. All
three original paths passed read/write checks. ZFS is healthy; PostgreSQL,
Docker, Cairn, both Talos relays, authentication timers, both Plane endpoints,
BinKeeper and the local inference health check passed. All 43 repository
tests and infrastructure validation passed. No persistent cleanup/retention
policy was added.

## Root-disk cleanup — 2026-11-01

The owner requested another cleanup at 89% root usage (about 204 GiB free).
Docker's unused build cache reclaimed 20.7 GB across an age-filtered pass and
an unused-cache pass, retaining a 10 GB cache floor. Cleared APT downloads,
4.1 GiB of update-bot npm downloads and 3.5 GiB of inactive Bun downloads.
Unused uv/pip entries and old dangling Docker images yielded no additional
space. Docker volumes, tagged images and installed update candidates remain.

Archived the inactive 30 GiB `agent-ee/campaign-2026-10-26` tree at the path
in the table above. No process held or mapped a source file, and no relative
symlink escaped the source tree. The transfer uses `rsync -aHAX`, including
native whole-file transfer checksums, followed by a comparison for missing,
extra or changed paths before replacing the original with a symlink. The
existing archive backup covers the new location.

The ongoing `zeroasic-20261029-agent707` run had grown from 214 to 340 GiB
since the previous cleanup and remains on root. Engineering evidence under
`~/.cache`, source worktrees, databases, model files and update-bot staging
were retained. No persistent retention policy was changed.

The transfer copied 167,774 regular files (30,770,500,609 bytes). The final
250,417-path comparison reported no missing, extra or changed entries. A
second open-file/mapping check passed before switching the original path to
a symlink and deleting the verified duplicate. User read/write checks through
the symlink passed. Root finished at about 259 GiB free (86% used), a net gain
of 55 GiB. ZFS, PostgreSQL, Docker, Cairn and inference remained healthy; all
43 repository tests and infrastructure validation passed.
