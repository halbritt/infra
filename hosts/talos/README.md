# talos

Headless Ubuntu Server 26.04.1 LTS on an Intel NUC 10 (`NUC10i7FNH`,
i7-10710U 6C/12T, 61 GiB RAM, Samsung PM961 512 GB NVMe). Installed
2026-10-22 (UTC) with Subiquity and first recorded the same day. Its role has
not been assigned yet.

LAN: `wlp0s20f3` (Wi-Fi), DHCP, observed `192.168.1.196`. Wired `eno1` is
configured in netplan but has no link.
Tailscale: `100.73.54.127` / `talos.tail0ecc2e.ts.net`.
Passwordless administration from proximal: `ssh talos` (entry in
`~/.ssh/config`, `HostKeyAlias talos`). `halbritt` has `NOPASSWD: ALL` sudo.

- [Machine metadata](machine.yaml)
- [Operational notes](notes.md)
- [Changelog](CHANGELOG.md)

## Current state (2026-10-22)

| Area | State |
|---|---|
| Boot | UEFI, Secure Boot disabled. GRUB, kernel `7.0.0-38-generic` |
| Storage | GPT: 1 GiB ESP, 2 GiB `/boot` (ext4), LVM PV. `ubuntu-vg/ubuntu-lv` 100 GiB ext4 on `/`. ~374 GiB of the VG is unallocated. No disk encryption. 8 GiB `/swap.img` |
| Access | OpenSSH on `:22`, keys only (`PasswordAuthentication no`, root `prohibit-password`). `authorized_keys` holds the two `gh:halbritt` ed25519 keys imported by the installer |
| Network | systemd-networkd via netplan (`00-installer-config.yaml`, Wi-Fi credential inside, not recorded). systemd-resolved, Tailscale MagicDNS. No firewall rules (ufw inactive, empty nftables) |
| Tailscale | 1.104.2, auto-update on, Tailscale SSH off, no routes or exit node. Node key expires 2027-04-20 |
| Updates | `unattended-upgrades` enabled (default security origins, no automatic reboot). 30 packages upgradable at first record |
| Time | UTC, chrony, synchronized |
| Services | Base server set only: ssh, tailscaled, chrony, thermald, snapd, avahi, multipathd. No containers, no user services, nothing failed |
| Software | 541 dpkg packages; snaps `core24`, `snapd`, `hwctl`. Python 3.14.4. No Docker, Node, Git checkouts or agent tooling |
