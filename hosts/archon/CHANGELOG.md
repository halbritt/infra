# Host changelog

## 2026-10-25 — install ugrep

Owner-requested CLI installation: `sudo pacman -S --needed ugrep` installed
Arch's `7.8.5-1` package from extra. Verified `/usr/bin/ugrep`, its version, and
an exact-line stdin search with line numbers.

## 2026-10-24 — agent-ee material removed (owner: "you clean up archon")

The owner replaced the agent-ee campaign with a single agent; archon is no longer an
agent-ee host. Only the owner's own `claude` session was running, and it was left alone.
Nothing was restarted; Hyprland and the session were untouched.
- **Archive first:** everything went to proximal
  `~/.local/share/infra/archon-agent-ee-archive-20261024/` (2.2 GB; 297 files verified by
  checksum on both ends, plus `burndown-archon-only.tgz`). It holds git bundles of
  `agent-ee`, `fome-mc`, `kicad-route` and `kicad-happy`, with every branch and worktree
  HEAD. That includes 98 agent-ee, 30 kicad-route, 2 fome-mc and 4 kicad-happy commits
  that existed only locally. It also holds the patches and untracked files of 73 dirty
  worktrees, 61,839 burndown files not on proximal, and the small `/tmp/agent-ee-*` dirs.
- **Removed:**
  - `~/git/agent-ee` and all agent worktrees (about 44 GB)
  - the agent branches in `fome-mc`, `kicad-route` and `kicad-happy`, whose main
    checkouts are kept, clean (kicad-happy stays detached at v2.3.1)
  - `/tmp/agent-ee-*` (19 GB) and `~/.cache/ae-ci-exec`
  - `native-admit`, `ae-ci-exec` and `~/.config/native-admission`
  - every `agent-ee*` Docker image and the build cache (about 45 GB)
- **Kept:** `agent-board`, `skillpack`, and `ubuntu:24.04`.

## 2026-10-22 — kicad-route worker lanes

Owner request (via the coordinator): run kicad-route lanes here as well as agent-ee lanes. Details: [shared/kicad-route](../../shared/kicad-route/README.md).

- `~/git/kicad-route`: public clone of halbritt/kicad-route with `receive.denyCurrentBranch updateInstead`. proximal's checkout has the remote `archon`.
- pip 26.2.1 was bootstrapped into the user site from the interpreter's bundled wheel. The user site also has numpy 2.5.4, scipy 1.18.1, pillow 13.0.0 and proximal's pins: pytest 9.1.0, shapely 2.2.0 and jsonschema 4.26.0. pacman was not changed.
- `/usr/local/bin/uv` is a symlink to mise's `uv/latest` binary. The mise shim fails under kicad-route's contained `HOME`. `~/.bashrc` now sources `~/.cargo/env` for non-interactive shells too.
- `kicad-route update` built router generation `42ddddaf…` (`owned-3c91fe5c0120`). There is no Java, so the Freerouting backend is unavailable.
- Check at kicad-route 409d06ab: 93 focused pcbnew/router tests passed. pytest then segfaulted at teardown (exit 139), a known Python 3.14 + pcbnew issue.

## 2026-10-21 — agent-ee tests run in the CI image (`ae-ci-exec`); uv 0.13.4, claude 2.1.307

Owner-requested. Natively (Python 3.14.8, poppler 26.08, ngspice 47), main fails
test_fab_package DeclaredFabCampaignTests, test_fab_stage and the Python 3.14
recursion subcases of test_electrical_locality. All three pass in the image
(Python 3.12.3, poppler 24.02, ngspice 42).

- Installed `~/.local/bin/ae-ci-exec` (sha256
  `a824b664ec9907fbb5abef7ee17e3d4a93b6cac6d96488b6a2c9c5c300a877b5`, identical on
  proximal, peecee-wsl and archon). Canonical source and documentation:
  [`shared/agent-ee/`](../../shared/agent-ee/README.md). It runs agent-ee
  commands in the pinned CI image built from the worktree's own Dockerfile, with
  the release gate's sandbox options, fome-mc and J1 inputs, and kicad-route pin.
  agent-ee tests on every host should go through it rather than through the
  distro toolchain.
- Image `agent-ee:exec-2657c88d90d4f0a9` (agent-ee main de12cca).
  State lives in `~/.cache/ae-ci-exec/`: the fome-mc clone at 1289f314, the J1
  drawing, a caller-owned kicad-route copy, build logs and parity results.
- Parity on a clean `git archive de12cca`, run with `strict_suite.py --jobs 3`:
  all 10 modules pass with 295 tests and 0 skips, the same result as on the
  other two hosts. The modules are the 7 peecee-wsl drift modules, test_fab_package,
  test_fab_stage and test_electrical_locality. Doctor output is byte-identical
  across hosts.
- Image build: 262 s cold (pulled the pinned ubuntu:24.04 and rust:1.99.1 bases).
  Batch A 133 s, batch B 103 s. AppArmor is disabled, so the profile is `unconfined`.
  halbritt was already in `docker`, so no sudo was used.
- Host tools: `mise upgrade uv claude`: uv 0.12.19 → 0.13.4, claude 2.1.306 → 2.1.307.
  codex is 0.163.0 (mise). git-wt/git-land launch `~/.local/lib/git-trunk-tools/git_trunk_tools.py`
  (no cairn checkout here). That file has the same sha256 (7d6accc6…) as cairn's
  `scripts/git_trunk_tools.py` on proximal and peecee-wsl. Only the launcher path
  differs, so the copy must be refreshed by hand when cairn changes it.

## 2026-10-21 — KiCad 10.0.7 with the stock 3D model library

KiCad was installed at 01:00 PDT with `pacman -S --needed kicad kicad-library
kicad-library-3d ngspice` (pacman.log). This entry records it after the fact.
Packages: `kicad 10.0.7-2`, `kicad-library 10.0.7-1`, `kicad-library-3d 10.0.7-1`
(Arch extra, explicitly installed). The 3D library is the same upstream release
(10.0.7) as proximal's and peecee-wsl's `kicad-packages3d`.

- Path `/usr/share/kicad/3dmodels`: 7252 `.step`, 3.14 GiB. `pacman -Qkk`
  reports 0 altered files.
- Verified 2026-10-21 for agent-ee's placement renders. With an empty
  `KICAD_CONFIG_HOME`, `kicad-cli pcb render` of the pod candidate shows
  component bodies (J3 microSD on the bottom). All 27 unique stock files that the
  pod board's 281 `${KICAD10_3DMODEL_DIR}` references cite are present. No
  install was needed. See the [proximal entry](../proximal/CHANGELOG.md).

## 2026-10-21 — Claude and Codex logins are mirrors of proximal

`~/.claude*/.credentials.json` and `~/.codex*/auth.json` here are now written by
proximal's `claude-oauth-refresh` and `codex-auth-mirror` timers every 15
minutes. They hold access tokens only (Claude refresh fields removed, Codex
`refresh_token` blanked), so this host can never rotate, or invalidate, the
owner's logins. Do not run `claude auth login` or `codex login` here: the next
push overwrites it. `~/.gemini/oauth_creds.json` remains a plain copy, which is
safe because Google refresh tokens do not rotate. See
[proximal codex-auth-mirror](../proximal/config/codex-auth-mirror/README.md).

## imessage-vm and TPM root unlock — 2026-10-19

Owner-requested always-on iMessage host. Installed QEMU 11.1.1 (exact
archived versions, no system upgrade), a dedicated `imsgvm` user and btrfs
subvolume `/var/lib/imessage-vm`, and the enabled units `imessage-vm.service`
and `imessage-vm-mcp-tunnel.service`. Guest: macOS 15.8.1 with OpenCore 1.0.8,
VMHide, BlueBubbles 1.9.9 and imessage-mcp 3.2.0. Tailscale Serve (tailnet
only): `:8443` → BlueBubbles, `:8765` → MCP. The runtime kvm `ignore_msrs=1`
is set by the unit. Added peecee's forwarding-only key to `authorized_keys`
(backup `.bak-20261019`). The owner signed in to the Apple Account; native
iMessage, the BlueBubbles Windows client and the read-only MCP were verified,
including after controlled VM restarts. See
[imessage-vm](config/imessage-vm/README.md).

Incident: VNC key tracing while debugging console input logged the owner's
typed Apple credentials to the system journal. The journal file covering
Oct 17 19:30 to Oct 19 14:55 was deleted, and the owner was advised to change
the Apple Account password. Never enable input tracing.

TPM2 unlock prepared and enrolled (PCR 7, passphrase kept); first reboot
pending with the owner present. See [tpm-unlock](config/tpm-unlock/README.md).

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
