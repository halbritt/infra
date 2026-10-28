# Ubuntu 26.04 upgrade — 2026-10-28

Owner request: upgrade this box to Ubuntu 26.04. Operator: agent-684.
This record tracks execution; it is not a claim that the upgrade is complete.

## Before the upgrade

- Ubuntu 24.04.5 LTS, kernel `6.8.0-147-generic`, amd64.
- The supported `do-release-upgrade -c` check offers **26.04.1 LTS**.
  Follow Canonical's [server release upgrade procedure](https://ubuntu.com/server/docs/how-to/software/upgrade-your-release/).
- Root has 385 GiB available; `/boot` has 1.5 GiB available. The root LV has
  no free VG extents for an LVM snapshot.
- ZFS pool `nvr` is ONLINE without known data errors. Preserve its 16 GiB ARC
  cap and do not upgrade pool feature flags as part of the OS upgrade.
- Managed PostgreSQL `17/main` is online on 5432; retained `16/main` is down
  on 5433. Existing package holds protect the database major version and
  extensions. An OS upgrade does not require migrating the database to PG18.
- Most databases use glibc `en_US.UTF-8` collation version 2.39. After the
  libc upgrade, inspect actual collation versions and rebuild affected indexes
  before refreshing version metadata. Cairn itself uses `C` collation.
- Several running services and virtual environments use `/usr/bin/python3.12`.
  Preserve that interpreter during transition and check service imports/startup
  after the system Python changes to 3.14.
- Pre-existing failures: system `binkeeper-label-drift.service` and
  `openipmi.service`; user `email-injection-canary.service`.

## Recovery evidence

Private, root-only directory: `/var/backups/ubuntu-26.04-20261028/`.
It contains `etc-boot-apt.tgz` (configuration, boot and dpkg state), package and
hold inventories, system/user service baselines, and `python312.tgz`.
These archives contain private configuration and must never enter Git.
They are recovery inputs, not a complete bootable disk image.

The scheduled restic backup completed successfully at 03:33 PDT on October 28.
The PostgreSQL differential backup completed at 01:37 PDT. A native pgBackRest
check under the postgres account verified WAL archival at 08:19 PDT. A fresh
incremental backup runs as `ubuntu2604-pgbackup.service`; inspect its result
and `pgbackup.log` before proceeding.

## Execution

The idle `update-bot`, `update-bot-monitor`, `apt-daily`, and
`apt-daily-upgrade` timers were stopped for this maintenance window. Restore
them afterwards; no persistent enablement change was made.

Prerequisite package updates run independently of the interactive session as
`ubuntu2604-prerequisites.service`, with output in `prerequisites.log` in the
private recovery directory. The reviewed transaction upgrades 32 packages,
removes none, preserves configuration files and leaves PostgreSQL holds intact.

Before accepting the release upgrade, review its calculated removals. Afterwards
check dpkg consistency, Python services, PostgreSQL and collation versions,
Docker containers, ZFS, NVIDIA, SSH/Tailscale and the new boot image. Reboot is
required to activate the new kernel; verify the host again after boot.
