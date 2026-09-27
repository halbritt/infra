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
