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
| `~/council-artifacts` | `/nvr/archive/council-artifacts` |
| `~/.local/share/cairn/backups` | `/nvr/archive/cairn/backups` |
| `~/.local/share/cairn/retired-postgres-20260929` | `/nvr/archive/cairn/retired-postgres-20260929` |
| `~/.local/state/runpod-jobrunner` | `/nvr/archive/runpod-jobrunner-state` |
| `/tmp/claude-1000/-home-halbritt-git-quartermaster/bdaec7d9-…` (dead session, Oct 8–9) | `/nvr/archive/claude-scratch/quartermaster-bdaec7d9-20261009` (no symlink) |
| locally built Docker images (runpod-jobrunner-noop, checkout-refs-runner, kayakgen-*, harbor-prebuilt) | `/nvr/archive/docker-images/local-images-20261017.tar` (`docker load -i`) |

Off-site backup: restic does not follow symlinks, so
`/usr/local/libexec/caplab-p5/restic-backup-locked` (tracked since 2026-10-22 in [config/restic](../restic/README.md);
the previous copy is saved beside it as `.pre-archive-20261017`) now also backs
up `/nvr/archive`, excluding `/nvr/archive/claude-scratch`. That keeps
coverage the same as before the move.
