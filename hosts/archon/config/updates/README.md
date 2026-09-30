# Updates

Omarchy's supported path is `omarchy-update` (snapshot, keyring, pacman, Omarchy
migrations, post-update hook, AUR, mise, orphan cleanup, restart prompt).

## Running it over SSH

`omarchy-update -y` fails non-interactively. It wraps itself in `script`, which
gives it a pty, so `omarchy-update-stay-awake` calls `sudo -v`. Sudo's default
`verifypw=all` makes `sudo -v` ask for a password because `(ALL) ALL` still
requires one. The `NOPASSWD: ALL` rule does not satisfy it. The run aborts after
the prune and snapshot steps.

Workaround used on 2026-09-26. The steps need a login shell because
`OMARCHY_PATH` is set by `/usr/share/omarchy/default/bash/env-bootstrap`. Run
them in the same order and omit stay-awake and the restart prompt:

```bash
ssh archon 'bash -lc '\''export OMARCHY_UPDATE_UNATTENDED=1; set -e
omarchy-snapshot create || true
for s in omarchy-update-dev omarchy-update-keyring omarchy-update-system-pkgs \
  omarchy-migrate "omarchy-hook post-update" omarchy-update-aur-pkgs \
  omarchy-update-mise omarchy-update-orphan-pkgs omarchy-update-analyze-logs \
  omarchy-update-status; do echo "### $s"; $s </dev/null; done'\'''
```

Afterwards, check `~/.local/state/omarchy/reboot-required` and
`restart-*-required`. Reboot only with owner approval, because the host is an
interactive desktop.

## 2026-09-26 result

`omarchy` 4.0.3-1 → 4.0.4-1; `omarchy-settings`, `aether` 4.30.0, `mise-bin`
2026.9.12, and `voxtype-bin` 1.1.0 were also updated. Migration `1789444024`
installed `linux-omarchy` 7.2.5-3 and headers, and the limine UKIs were
rebuilt. mise updated claude 2.1.283, codex 0.157.1, and gh 2.101.0. Nothing
remains pending in the repos or AUR. The reboot into the new kernel is pending.
Snapper snapshot taken before the upgrade.


## Herdr — daily coverage from proximal

Owner-authorized on 2026-09-30. Canonical `herdr_update.py` installs as
`/usr/local/lib/update-bot/herdr_update.py`, root:root 0755. The proximal bot can
start a fixed system unit that reaches this helper through the existing SSH alias.
It accepts no arguments. It stages a binary and runs native noninteractive `herdr update` as `halbritt`,
so session/protocol checks see the actual desktop sessions. Only after native
checks and version/process verification pass does root atomically replace
`/usr/bin/herdr`. The existing stable channel is checked for both user and helper. It never requests server stop or live handoff.

The helper checks the actual resulting version against the stable release and
verifies pre-existing Herdr process start times and executable inodes. A zero
updater exit is not sufficient: upstream can decline an installation while
returning success. Receipts, a private update log, lock and hash-named backup
binaries live in root-only `/var/lib/update-bot-herdr/`. Do not retry a receipt
left running/uncertain without checking its processes and resulting installation.
A client disconnect can leave the outcome uncertain at proximal even if Archon
finished; read both receipts before clearing the hold.

Rollback is an explicit atomic replacement of `/usr/bin/herdr` from the receipt's
backup, retaining the failed binary for investigation. Do not restart Herdr,
Hyprland or the host as part of rollback. Existing sessions keep their old inode.

Before this change, pacman recorded `herdr 0.8.2-1` installed on September 10
(local time), while `/usr/bin/herdr --version` and the running server both reported
0.9.0. The binary differed from the package checksum and had a later modification
time. This demonstrates replacement after package installation, but does not
identify who performed it. The package repository still offered 0.8.2-1; preserve
the newer upstream binary and leave package metadata honest about the mismatch.
