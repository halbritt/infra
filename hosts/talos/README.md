# talos

Headless Ubuntu Server 26.04.1 LTS on an Intel NUC 10 (`NUC10i7FNH`,
i7-10710U 6C/12T, 61 GiB RAM, Samsung PM961 512 GB NVMe). Installed
2026-10-22 (UTC) with Subiquity and first recorded the same day. Role since
2026-10-22: agent-ee fleet worker host (see [Fleet worker host](#fleet-worker-host-2026-10-22)).

LAN: `wlp0s20f3` (Wi-Fi), DHCP, observed `192.168.1.196`. Wired `eno1` has no
cable; it is DHCP and optional, so a cable works without config changes
([network](config/network/README.md)).
Tailscale: `100.73.54.127` / `talos.tail0ecc2e.ts.net`.
Passwordless administration from proximal: `ssh talos` (entry in
`~/.ssh/config`, `HostKeyAlias talos`). `halbritt` has `NOPASSWD: ALL` sudo.

- [Machine metadata](machine.yaml)
- [Operational notes](notes.md)
- [Changelog](CHANGELOG.md)
- [Updates](config/updates/README.md)
- [Network](config/network/README.md)

## Current state (2026-10-22)

| Area | State |
|---|---|
| Boot | UEFI, Secure Boot disabled. GRUB, kernel `7.0.0-38-generic` |
| Storage | GPT: 1 GiB ESP, 2 GiB `/boot` (ext4), LVM PV. `ubuntu-vg/ubuntu-lv` 100 GiB ext4 on `/`. ~374 GiB of the VG is unallocated. No disk encryption. 8 GiB `/swap.img` |
| Access | OpenSSH on `:22`, keys only (`PasswordAuthentication no`, root `prohibit-password`). `authorized_keys` holds the two `gh:halbritt` ed25519 keys imported by the installer |
| Network | systemd-networkd via netplan (`00-installer-config.yaml`, Wi-Fi credential inside, not recorded). `eno1` DHCP + optional, not required for online ([network](config/network/README.md)). systemd-resolved, Tailscale MagicDNS. No firewall rules (ufw inactive, empty nftables) |
| Tailscale | 1.104.2, auto-update on, Tailscale SSH off, no routes or exit node. Node key expires 2027-04-20 |
| Updates | Automatic: release, security and `-updates` pockets daily. Guarded nightly reboot when required. Docker and KiCad held. See [updates](config/updates/README.md) |
| Time | `America/Los_Angeles` (set 2026-10-22; installed as UTC), chrony, synchronized |
| Services | At first record: base server set only (ssh, tailscaled, chrony, thermald, snapd, avahi, multipathd). Since 2026-10-22 also `docker.service` and `containerd.service` (enabled at boot). No user services or timers |
| Software | At first record: 541 dpkg packages; snaps `core24`, `snapd`, `hwctl`. Python 3.14.4. No Docker, Node, Git checkouts or agent tooling. Worker toolchain added the same day (below) |

## Fleet worker host (2026-10-22)

Owner 2026-10-22 ("delegate an agent to setup talos as a build host"): talos is
an agent-ee fleet worker host, set up to match peecee-wsl, archon and
`agent-ee-gate-c4` (see [gcp-gate](../gcp-gate/README.md#fleet-worker-host-2026-10-22)).
The burndown launcher (`launch.py` / `review.py`) on proximal runs Claude and
Codex workers here over ssh with the same paths as proximal.

| Tool | Version | Source on this host |
|---|---|---|
| docker / buildx | 29.1.3 / 0.30.1 | Ubuntu `docker.io 29.1.3-0ubuntu4.1`, `docker-buildx 0.30.1-0ubuntu1` (the peecee-wsl packages), held; `docker` and `containerd` enabled at boot; `halbritt` in group `docker` |
| node / npm | v24.22.0 / 11.19.1 | nodejs.org `node-v24.22.0-linux-x64.tar.xz` (SHASUMS256 checked) extracted into `/usr/local`; `npm i -g npm@11.19.1` |
| claude | 2.1.307 | `npm i -g --allow-scripts=@anthropic-ai/claude-code @anthropic-ai/claude-code@2.1.307` under prefix `~/.npm-global` (`~/.npmrc`) |
| codex | 0.163.0 | the full standalone tree `~/.codex/packages/standalone/releases/0.163.0-x86_64-unknown-linux-musl/` (`bin/`, `codex-path/rg`, `codex-resources/`) copied from peecee-wsl; `~/.local/bin/codex` symlinks to its `bin/codex`. `@openai/codex@0.163.0` is also in `~/.npm-global` |
| uv / uvx | 0.13.4 | binaries and `~/.local/bin/env{,.fish}` copied from peecee-wsl |
| git-wt / git-land | cairn `git_trunk_tools.py` (sha256 `7d6accc6…f751e35`) | `~/.local/bin` wrappers identical to peecee-wsl; the script alone at `~/git/cairn/scripts/git_trunk_tools.py` |
| ae-ci-exec | `0e8cb9d2…015290` | byte-identical copy of [shared/agent-ee/ae-ci-exec](../../shared/agent-ee/README.md) at `~/.local/bin/ae-ci-exec` |
| KiCad (native) | 10.0.7~ubuntu26.04.1 | Launchpad snapshot `20261015T000000Z`, suite `resolute` ([config/apt](config/apt/README.md)); kicad, -symbols, -footprints, -templates held; no packages3d |
| ngspice / bwrap / poppler (native) | 45.2 / 0.11.1 / 26.01.0 | stock Ubuntu 26.04, the same as peecee-wsl. The Dockerfile's snapshot is `noble` and does not install on 26.04, so native tools are diagnostic only and tests rely on the CI image (ngspice 42 / bwrap 0.9.0 / poppler 24.02 / Python 3.12) |
| python3 / git / rsync / jq / zstd | 3.14.4 / 2.53.0 / 3.4.1 / 1.8.1 / 1.5.7 | Ubuntu 26.04; also `apparmor-utils` 5.0.2, `curl`, `xz-utils` |

`~/.profile` sources `~/.local/bin/env` and `~/.profile.d-toolchains.sh` (copied
from peecee-wsl), so `bash -lc` puts `~/.local/bin` and `~/.npm-global/bin` on
PATH. Global git config: `user.name halbritt`, `user.email`, `init.defaultBranch
main`, `safe.directory *` (no credential helper).

AppArmor is enabled, so `ae-ci-exec` runs containers under the
`agent-ee-container` profile, installed at `/etc/apparmor.d/agent-ee-container`
(loaded at boot). Since 2026-10-22 it is a talos-specific enforce-mode
`allow all,` profile, not agent-ee's `flags=(unconfined) { userns, }`
`docker/agent-ee.apparmor`: under Ubuntu 26.04's `bwrap-userns-restrict`
the unconfined-mode profile let nested Bubblewrap attach to
`bwrap//&unpriv_bwrap` and fail. See [config/apparmor](config/apparmor/README.md).
`halbritt` has full passwordless sudo, so agent-ee
`scripts/container_apparmor.sh` (`sudo -n apparmor_parser`) also works, but
until agent-ee adopts the new profile running it reloads the old one.

Native test check 2026-10-22 (agent-ee main 1da27635, git-wt worktree,
`ae-ci-exec ... env AGENT_EE_SKIP_VISUALS=1 PYTHONPATH=src:tests python3 -m
unittest`): `tests.test_add_planes` 15 tests OK, no skips (2 failures before the
profile change); `tests.test_placer_native tests.test_placement_native
tests.test_kicad_route_native tests.test_tree_hygiene tests.test_capabilities`
65 tests OK, no skips, 201 s. No AppArmor denials in the kernel log.

CI image check 2026-10-22: from a git-wt worktree of agent-ee main 1da27635,
`ae-ci-exec <worktree> -- env AGENT_EE_SKIP_VISUALS=1 PYTHONPATH=src:tests
python3 -m unittest tests.test_tree_hygiene` built `agent-ee:exec-4ff2f011477682a7`
(the tag peecee-wsl holds for the same inputs) cold in 430 s, cloned fome-mc
1289f314 and fetched the J1 drawing into `~/.cache/ae-ci-exec/inputs`, and ran
6 tests OK. The image is 6.4 GB.

Layout, as on peecee-wsl:

| Path | What |
|---|---|
| `~/git/agent-ee` | `git init` + `receive.denyCurrentBranch updateInstead`, populated by `git push talos main:main` from proximal (no origin; the host holds no GitHub credential). proximal's `~/git/agent-ee` has remote `talos` = `ssh://talos/home/halbritt/git/agent-ee`, which launch.py pushes base refs to and fetches worker branches from |
| `~/git/agent-ee/build/kicad-route-pin-5f1c072` | copied from proximal (HEAD 5f1c072b, clean) |
| `~/git/fome-mc` | public clone at peecee-wsl's 8c42f2ee |
| `~/git/kicad-happy` | public clone at 06840467 (2.3.1) |
| `~/git/kicad-route` | public clone of github.com/halbritt/kicad-route + `receive.denyCurrentBranch updateInstead`; proximal's `~/git/kicad-route` has remote `talos` = `ssh://talos/home/halbritt/git/kicad-route` for `launch.py --repo`. Router generation `.router-generations/9148d30a…` built by `kicad-route update` (rustup 1.99.1 and `build-essential` added). See [shared/kicad-route](../../shared/kicad-route/README.md) |
| `~/.cache/agent-worktrees/kicad-route/` | git-wt worktrees for kicad-route lanes |
| `~/.cache/agent-worktrees/agent-ee/` | git-wt worktrees created by launch.py |
| `/tmp/agent-ee-burndown-20261017/` | created by launch.py `sync_up` (rsync -R) per worker |

Credentials come only from proximal's mirror timers; nobody logs in on this host.
`talos` is in `REMOTE_HOSTS` of
[`claude-oauth-refresh`](../proximal/config/claude-oauth-refresh/README.md) and
[`codex-auth-mirror`](../proximal/config/codex-auth-mirror/README.md). Before the
first push `~/.claude-harm/.claude.json` was created as `{}` so the account block
is mirrored. First run 2026-10-22 05:5x UTC: `~/.claude mirrored`,
`~/.claude-harm mirrored+account`, `~/.codex`, `~/.codex-harm`, `~/.codex-3
mirrored`. Checked without printing values: every file mode 0600, no `refresh`
key in either Claude file, `tokens.refresh_token == ""` in all three Codex
files. Live probes, launch.py's own argv shape: `claude --print 'reply OK'`
(haiku) answered OK for `~/.claude` and `~/.claude-harm`; `codex exec` answered
OK for `~/.codex-3`; `~/.codex` and `~/.codex-harm` authenticated and were
refused by the accounts' usage limits (until 2026-10-27), not by auth. Gemini:
not mirrored (launch.py keeps argon/agyopus on proximal).

Launcher registration (`/tmp/agent-ee-burndown-20261017`, backups
`*.bak-20261022talos`): `HOSTS` and `REMOTE_ACCOUNTS` include `talos` with all
five accounts; `pick_host` scores it by 1-minute load / 12 threads like the
others. Worker and reviewer notes (`common.txt`, `review-common.txt`) cap test
parallelism here at 3 processes and list talos among the `ae-ci-exec` hosts.

Smoke test 2026-10-22: `launch.py haiku claude-harm 397 talos-smoke-20261022
--host talos` with a no-op note. The worker ran on the host (hostname `talos`,
nproc 12, all CLIs on PATH), made one empty commit, exited 0 in 13 s;
`sync_down` brought `result.md` back and the runner fetched
`wt/talos-smoke-20261022` (97315502) into proximal. Worktrees, branches and the
base ref were then removed on both sides; the worker dir is kept at
`/tmp/agent-ee-burndown-20261017/smoke/` on both machines.

To retire it as a worker host: remove it from `REMOTE_HOSTS` in both mirror
scripts and from `HOSTS`/`REMOTE_ACCOUNTS`, then delete the profile dirs
(`~/.claude`, `~/.claude-harm`, `~/.codex*`) on talos.
