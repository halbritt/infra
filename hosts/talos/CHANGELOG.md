# Host changelog

## 2026-10-22 — Timezone set to Pacific

Owner-requested: `timedatectl set-timezone America/Los_Angeles` (was `Etc/UTC`).
The guarded reboot timer moved from `11:00 UTC` to `04:00 America/Los_Angeles`,
so the window stays at 04:00 local across DST changes.

## 2026-10-22 — Automatic updates

Verified by running `unattended-upgrade -v` under the new policy, rather than
waiting for tomorrow's timer. It applied the 30 pending `-updates` packages
(systemd 259.9, netplan, udev, snapd, cloud-init and others) and removed the
unused 7.0.0-30 kernel packages. Afterwards nothing was upgradable, no reboot was
required, and ssh, docker, tailscaled and resolved were active. Wi-Fi and
Tailscale stayed up, nothing had failed, and the Docker/KiCad holds were intact.


Owner-requested. Unattended-upgrades now also applies the `-updates` pocket and
removes unused kernels and dependencies. needrestart never restarts the container
runtime. A guarded timer reboots at 11:00 UTC only when a reboot is required and
no package manager, container or `halbritt` process is running. Existing apt holds
on Docker and KiCad (set by the agent-ee worker provisioning) are respected; the
KiCad PPA is not an allowed origin. See [updates](config/updates/README.md).

## 2026-10-22 — agent-ee-container profile: nested Bubblewrap

Coordinator task: make agent-ee native tests on talos behave as on the other
worker hosts. `tests.test_add_planes` failed 2 tests on agent-ee main 1da27635
because a nested bwrap in the CI container could not set up its namespace.

- Root cause: the `flags=(unconfined)` profile does not apply its exec rules,
  so `/usr/bin/bwrap` in the container attached to Ubuntu 26.04's host `bwrap`
  profile (`bwrap-userns-restrict`); its children run as
  `bwrap//&unpriv_bwrap`, which denies all capabilities (audit:
  `profile="unpriv_bwrap" comm="bwrap" capname="sys_admin"`), so the second
  bwrap level failed.
- Fix: `/etc/apparmor.d/agent-ee-container` is now an enforce-mode profile with
  `allow all,` and `attach_disconnected,mediate_deleted` (copy in
  [config/apparmor](config/apparmor/README.md)); exec inherits, so every bwrap
  level stays `agent-ee-container`. No host profile, `local/` override or sysctl
  changed. Old file at `~/.cache/agent-ee-container.orig` on talos.
- Verified with `ae-ci-exec`: `tests.test_add_planes` 15 OK (was 2 failures);
  native subset results in README.md.

## 2026-10-22 — agent-ee fleet worker host

Owner 2026-10-22, "delegate an agent to setup talos as a build host" (via the
coordinator). Set up to match peecee-wsl, archon and agent-ee-gate-c4; details
in README.md "Fleet worker host".

- Packages: docker.io 29.1.3 + docker-buildx 0.30.1 (held, enabled at boot,
  `halbritt` in `docker`), git, rsync, jq, zstd, apparmor-utils; KiCad
  10.0.7~ubuntu26.04.1 (held) from the Launchpad snapshot 20261015T000000Z
  with suite `resolute`; stock 26.04 ngspice 45.2, bubblewrap 0.11.1,
  poppler 26.01. The Dockerfile's `noble` snapshot cannot be installed on 26.04;
  tests rely on the CI image.
- Toolchain: node v24.22.0, npm 11.19.1, claude 2.1.307, codex 0.163.0 (full
  standalone tree from peecee-wsl), uv 0.13.4, git-wt/git-land wrappers.
- AppArmor profile `agent-ee-container` installed in `/etc/apparmor.d` and
  loaded. `ae-ci-exec` (`0e8cb9d2…015290`) built `agent-ee:exec-4ff2f011477682a7`
  in 430 s; `tests.test_tree_hygiene` 6 tests OK from a git-wt worktree.
- Repos: `~/git/agent-ee` pushed from proximal (new proximal remote `talos`),
  kicad-route pin 5f1c072, fome-mc 8c42f2ee, kicad-happy 06840467;
  `~/.cache/agent-worktrees/agent-ee/`.
- Credentials: added to `REMOTE_HOSTS` of claude-oauth-refresh and
  codex-auth-mirror; first push mirrored all five profiles (access tokens only).
  claude, claude-harm and codex-3 answered live probes; codex and codex-harm
  authenticated but are at their usage limit until 2026-10-27.
- Launcher: added to `HOSTS` and `REMOTE_ACCOUNTS` (all five accounts); test
  parallelism cap 3. Smoke worker via launch.py passed (exit 0, 13 s, sync_down
  and branch fetch OK) and was cleaned up.
- Added `config/apt/` (the KiCad snapshot sources file), which also supplies
  the `paths.config` directory machine.yaml names.

## 2026-10-22 — Initial record

Fresh Ubuntu Server 26.04.1 LTS install on an Intel NUC10i7FNH, recorded from a
read-only survey. No changes were made on the host.
