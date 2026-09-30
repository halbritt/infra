# Host changelog

## Herdr 0.9.3 and daily maintenance coverage — 2026-09-30

Added owner-authorized Herdr-only maintenance from proximal through a fixed
root-owned helper. Native stable update replaced the existing 0.9.0 binary with
0.9.3; its SHA-256 matches proximal's verified binary. Existing server and client
process start times and executable inodes were preserved. The live server remains
0.9.0 with compatible endpoint/private protocol; no handoff or desktop restart.

Pacman still records the original 0.8.2-1 installation; this mismatch existed
before the update and is now documented. Daily checks use binary and server
versions, not that stale package version. Root-only before/after receipts,
updater log, lock and old binary are under `/var/lib/update-bot-herdr/`.
See [update procedure](config/updates/README.md) for deployment and rollback.

## Agent accounts and shared skills — 2026-09-29

Replicated the owner's default and harm Codex/Claude accounts, added named harm
launchers, configured OpenCode with the existing Z.ai/OpenRouter accounts, and
set Hermes to DeepSeek 4.1 Flash via OpenRouter. Updated skillpack and verified
all 52 curated skills across the requested harnesses, including Hermes through
its external directory support. All six live inference probes passed. Jevgrep
also has verified direct TypeSafe access. Credentials and rollback snapshots
remain outside Git. See [agent configuration](config/agents/README.md).

## Herdr board publisher disabled — 2026-09-27

The agent board showed "herdr@archon not reporting since 04:25". Herdr
publishing had been retired on 2026-09-25, but the user unit
`herdr-publish.service`, which runs
`~/git/agent-board/publisher/herdr_publish.py --url http://proximal.attlocal.net:8787`,
was still enabled. Its reports began failing at 04:25 because
`proximal.attlocal.net` stopped resolving (`Name or service not known`). The
unit was disabled and stopped. At the owner's request, the leftovers were
then removed: the unit file and archon's copy of the board write token
(`~/.config/agent-board/token`, whose SHA-256 matched proximal's copy, so
nothing was lost). The publisher script was already absent from archon's
agent-board checkout at `8483060`. Afterwards, nothing on archon referenced
`proximal.attlocal.net`, and no publisher process ran. The `herdr` app itself
is untouched.

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
