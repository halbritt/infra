# Host changelog

## Herdr board publisher disabled — 2026-09-27

The agent board showed "herdr@archon not reporting since 04:25". Herdr
publishing had been retired on 2026-09-25, but the user unit
`herdr-publish.service`, which runs
`~/git/agent-board/publisher/herdr_publish.py --url http://proximal.attlocal.net:8787`,
was still enabled. Its reports began failing at 04:25 because
`proximal.attlocal.net` stopped resolving (`Name or service not known`). The
unit is now disabled and stopped; the file is kept. Rollback:
`systemctl --user enable --now herdr-publish.service`. The `herdr` server
itself is untouched.

## Terminal font size 9 → 11 — 2026-09-26

The owner requested a font 2 points larger. Changed `font=` in
`~/.config/foot/foot.ini` from `size=9` to `size=11`. Backup:
`foot.ini.bak-20260926`. `foot --check-config` passed. See
[config/terminal](config/terminal/README.md).

## System update — 2026-09-26

The owner requested an update. Omarchy went from `4.0.3-1` to `4.0.4-1`. The
update covered all 5 repo packages (including aether, mise-bin, and voxtype-bin)
and three mise tools (claude, codex, gh). A migration installed the
`linux-omarchy` kernel `7.2.5-3` and rebuilt the UKIs. The update left `checkupdates` and `yay -Qua`
empty. **Reboot pending** (`~/.local/state/omarchy/reboot-required`); still
running `7.2.3-arch1-3`. See [config/updates](config/updates/README.md).

## Initial record — 2026-09-26

Added host partition from a live SSH probe.
