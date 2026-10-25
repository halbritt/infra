# talos

Headless Ubuntu Server 26.04.1 LTS on an Intel NUC 10 (`NUC10i7FNH`,
i7-10710U 6C/12T, 61 GiB RAM, Samsung PM961 512 GB NVMe). Installed
2026-10-22 (UTC) with Subiquity and first recorded the same day. It was an agent-ee
fleet worker host from 2026-10-22 to 2026-10-24. On 2026-10-24 the owner retired it from
agent-ee, and it was cleaned for the striatum-next drive (see
[Retired from agent-ee](#retired-from-agent-ee-2026-10-24)).

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
| Storage | GPT: 1 GiB ESP, 2 GiB `/boot` (ext4), LVM PV. `ubuntu-vg/ubuntu-lv` ext4 on `/`, extended to the whole VG (473.9 GiB) on 2026-10-24. No disk encryption. 8 GiB `/swap.img` |
| Access | OpenSSH on `:22`, keys only (`PasswordAuthentication no`, root `prohibit-password`). `authorized_keys` holds the two `gh:halbritt` ed25519 keys imported by the installer |
| Network | systemd-networkd via netplan (`00-installer-config.yaml`, Wi-Fi credential inside, not recorded). `eno1` DHCP + optional, not required for online ([network](config/network/README.md)). systemd-resolved, Tailscale MagicDNS. No firewall rules (ufw inactive, empty nftables) |
| Tailscale | 1.104.2, auto-update on, Tailscale SSH off, no routes or exit node. Node key expires 2027-04-20 |
| Updates | Automatic: release, security and `-updates` pockets daily. Guarded nightly reboot when required. Docker held (KiCad removed 2026-10-24). See [updates](config/updates/README.md) |
| Time | `America/Los_Angeles` (set 2026-10-22; installed as UTC), chrony, synchronized |
| Services | At first record: base server set only (ssh, tailscaled, chrony, thermald, snapd, avahi, multipathd). Since 2026-10-22 also `docker.service` and `containerd.service` (enabled at boot). No user services or timers |
| Software | At first record: 541 dpkg packages; snaps `core24`, `snapd`, `hwctl`. Python 3.14.4. No Docker, Node, Git checkouts or agent tooling. Worker toolchain added the same day (below) |

## Retired from agent-ee (2026-10-24)

The owner said: "it should not be running anything related to agent-ee at present, and
should be cleaned up. I'm moving the striatum-next drive to it." Nothing was running and
admission was drained.

**Archived first.** Everything was archived to proximal
`~/.local/share/infra/talos-agent-ee-archive-20261024/` (1.2 GB, `SHA256SUMS`):
- git bundles of `agent-ee`, `fome-mc`, `kicad-route`, `kicad-happy` and two
  fome-qualify checkouts. Every branch is included, and each worktree HEAD is under
  `refs/talos-archive/wt-<sha>`.
- the tracked patch and untracked files of the nine dirty agent-ee review worktrees.
- the burndown files that existed only on talos.
- the fome-qualify logs, agent-521's retained harness evidence, the hostmon probe and
  the AGENTEE-438 probe files.

Only the review worktrees `review-review-ee487` and `review-ee485-combined-fable` had
heads missing from proximal's `agent-ee`. kicad-route had none missing.

**Removed:**
- **Repos and caches:** `~/git/{agent-ee,fome-mc,kicad-route,kicad-happy,cairn}`, all
  git-wt worktrees, `~/.cache/{fome-qualify,ae-ci-exec,agent-coordination}` and
  `/tmp/agent-ee-*` (3.9 GB).
- **Docker:** every image (`agent-ee:*`, `fome-runtime:d96f8e00`) and the build cache
  (45 GB in all).
- **Agent-ee tooling:** `native-admit`, `ae-ci-exec`, `~/.config/native-admission`,
  hostmon's probe, rustup/cargo and the user-site pytest/jsonschema pins (the
  `.cargo/env` lines in `~/.bashrc` and `~/.profile` too, with `.bak-20261024` copies)
  and the KiCad user config.
- **Packages:** `kicad`, `kicad-symbols`, `kicad-footprints`, `kicad-templates`,
  `ngspice` and their 180 automatic dependencies (unheld and purged), plus the KiCad
  snapshot apt source and keyring.
- **AppArmor userns relaxation:** `/etc/sysctl.d/60-agent-ee-userns.conf` was removed,
  and `kernel.apparmor_restrict_unprivileged_userns` is back to Ubuntu's 1.

**Unregistered on proximal:**
- talos was removed from the burndown launcher's `HOSTS`, `KICAD_HOSTS` and
  `KICAD_REVIEW_HOSTS` (`launch.py.bak-20261024-talos-retire`).
- the `talos` git remotes were removed from proximal's `agent-ee` and `kicad-route`.
- talos was removed from native admission (`shared/agent-ee/native-admission.json`,
  installer host list).

**Kept, as general tooling the drive may use:**
- docker / buildx (still apt-held) and `halbritt` in group `docker`
- node 24 and npm, the `claude` and `codex` CLIs (`~/.npm-global`, `~/.codex`)
- the CLI login profiles (`~/.claude`, `~/.claude-harm`, `~/.codex*`); talos stays in
  `REMOTE_HOSTS` of proximal's
  [`claude-oauth-refresh`](../proximal/config/claude-oauth-refresh/README.md) and
  [`codex-auth-mirror`](../proximal/config/codex-auth-mirror/README.md)
- uv/uvx, git-wt and git-land
- linger is enabled for `halbritt` (2026-10-24, for the striatum-next drive), so user
  units outlive ssh sessions
- stock bubblewrap, poppler-utils, build-essential and python3-numpy/scipy/pip

To stop credential mirroring as well, remove talos from both `REMOTE_HOSTS` lists and
delete the profile dirs.

The root LV was extended to the whole VG (473.9 GiB) on 2026-10-24, outside this
cleanup.

## Striatum-next runtime — 2026-10-24

The owner moved the Striatum-next engineering runtime from proximal to Talos.
The checkout is `~/git/striatum-next`; the durable instance is
`~/.local/share/striatum`. Run compiler operations, engineering checks and deploys
on Talos. Compiler-generated user units run under `striatum.slice`; the compiler
owns their generation. Linger keeps the user manager alive after SSH logout.

Proximal's retired instance is read-only and its source scheduling units are
masked. Its SSH proxy and the private Cairn/service relays remain for clients;
the source-only credential timers remain there too. Do not resume scheduling
against the retired data or remove its read-only fence.

Both Claude harnesses consume the existing mirrored access-only profiles via
[validated links](config/striatum/README.md). No login or refresh token belongs
on Talos. The root LV already uses the entire volume group, as requested.
