# Updates

Owner-requested automatic updates, 2026-10-22. talos is being provisioned as an
agent-ee/KiCad worker (agent-ee worktrees, Docker, KiCad 10.0.7 from the KiCad
snapshot PPA). The policy keeps the OS patched without upgrading pinned
toolchains or interrupting worker runs.

| Piece | Installed at | What it does |
|---|---|---|
| [52infra-unattended-upgrades](52infra-unattended-upgrades) | `/etc/apt/apt.conf.d/` | Adds the `-updates` pocket to Ubuntu's default release/security origins. Removes unused kernels and dependencies. Disables unattended-upgrades' own reboot |
| [50-infra-container-runtime.conf](50-infra-container-runtime.conf) | `/etc/needrestart/conf.d/` | needrestart never restarts `docker.service`, `docker.socket` or `containerd.service` after library upgrades |
| [infra-reboot-if-idle](infra-reboot-if-idle) | `/usr/local/sbin/` | Reboots only if `/run/reboot-required` exists and the host is idle |
| [infra-reboot-if-idle.service](infra-reboot-if-idle.service), [.timer](infra-reboot-if-idle.timer) | `/etc/systemd/system/` | Runs the guard daily at 04:00 Pacific (`America/Los_Angeles`, DST-aware), up to 10 minutes late |
| [install.sh](install.sh) | — | Installs all of the above and enables the timer (run on talos as root) |

Ubuntu's stock `apt-daily.timer` and `apt-daily-upgrade.timer` drive the
upgrades. `20auto-upgrades` was already enabled by the installer. Unattended
upgrades run at most once a day: the first-boot run on 2026-10-22 at 05:02 UTC
consumed that day's stamp.

Each timer run first waits on `systemd-networkd-wait-online`. It times out after
about 30 s and logs `apt-helper ... returned an error code (1)`, because the
installer's netplan configures the unplugged `eno1` without `optional: true`. The
step is `ExecStartPre=-`, so the error is ignored and updates still run. To clear
it, mark `eno1` `optional: true` in `/etc/netplan/00-installer-config.yaml`.
Use `netplan try`, since Wi-Fi is the only link.

## What is not upgraded automatically

- Packages held with `apt-mark hold` by the worker provisioning: `docker.io`,
  `docker-buildx`, `kicad`, `kicad-symbols`, `kicad-footprints`,
  `kicad-templates`. Upgrade them deliberately and re-hold them.
- The KiCad snapshot PPA and the Tailscale repository are not allowed origins.
  Tailscale updates itself (`tailscale set --auto-update`, already on).
- Release upgrades (`do-release-upgrade`).
- Snaps follow snapd's own refresh schedule (default, 4 times a day).

## Guarded reboot

The guard skips the night when any of these hold, and logs the reason to the
journal (`journalctl -u infra-reboot-if-idle`):

- `apt`, `apt-get`, `dpkg` or `/usr/bin/unattended-upgrade` is running. The
  idle `unattended-upgrade-shutdown` helper shares the truncated process name
  `unattended-upgr`, so the guard matches the upgrade script by path.
- Any Docker container is running.
- Any `halbritt` process other than the idle `systemd --user` manager is running.
  Agent workers arrive as non-interactive SSH commands, which do not appear in
  utmp, so unattended-upgrades' `Automatic-Reboot-WithUsers` cannot detect them.

A worker active every night at 04:00 Pacific would defer kernel and libc restarts
indefinitely. Check `/run/reboot-required` if that happens. Wi-Fi is the only
network link; the first boot after install brought it up unattended.

## Verify

```sh
ssh talos 'apt-config dump | grep Unattended-Upgrade::; systemctl list-timers infra-reboot-if-idle.timer apt-daily-upgrade.timer; sudo unattended-upgrade --dry-run -v | grep -E "Allowed origins|will be upgraded"; sudo /usr/local/sbin/infra-reboot-if-idle'
```

The last command performs a real reboot if one is pending and the host is idle.

## Rollback

```sh
sudo systemctl disable --now infra-reboot-if-idle.timer
sudo rm /etc/systemd/system/infra-reboot-if-idle.{service,timer} /usr/local/sbin/infra-reboot-if-idle \
  /etc/apt/apt.conf.d/52infra-unattended-upgrades /etc/needrestart/conf.d/50-infra-container-runtime.conf
sudo systemctl daemon-reload
```

This returns talos to Ubuntu's default security-only unattended upgrades with no
automatic reboot.
