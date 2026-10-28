# Ubuntu 26.04 upgrade — 2026-10-28

Owner request: upgrade this box to Ubuntu 26.04. Operator: agent-684.
This record tracks execution; it is not a claim that the upgrade is complete.

The owner subsequently authorized migrating the managed PostgreSQL cluster to
18 as well. Install the OS first, then migrate the database with extension
parity and a retained PG17 copy for rollback.
The owner also directed that versions must not be pinned arbitrarily, and asked
to preserve the reason for using NVIDIA's own driver packaging. No APT holds
remain after preparation of the PG18 migration.

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
  extensions. These remain in place for the OS transaction; the separately
  authorized PG18 migration follows it.
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
incremental backup `20261025-010451F_20261028-081942I` completed successfully at
08:20 PDT (23.2 GB changed). Its log is `pgbackup.log`.
`pg17-globals.sql` privately preserves role definitions and privileges.

## Execution

The idle `update-bot`, `update-bot-monitor`, `apt-daily`, and
`apt-daily-upgrade` timers were stopped for this maintenance window. Restore
them afterwards; no persistent enablement change was made.

Prerequisite package updates run independently of the interactive session as
`ubuntu2604-prerequisites.service`, with output in `prerequisites.log` in the
private recovery directory. The reviewed transaction upgrades 32 packages,
removes none, preserves configuration files and leaves PostgreSQL holds intact.
This prerequisite transaction completed successfully. Native dpkg audit was clean.

The release upgrader runs in the dedicated tmux server `ubuntu2604`, session
`upgrade`; attach with `tmux -L ubuntu2604 attach -t upgrade`. Native logs are
under `/var/log/dist-upgrade/`. Its reviewed initial plan removes 24 packages,
installs 289 and upgrades 1,525, downloading 2.8 GB. Removals include superseded
libraries and `openfoam2512-default`/`openfoam2512-dev`; inspect OpenFOAM after
the upgrade. Database packages and Python 3.12 are retained. Temporary exact
version pins in `/etc/apt/preferences.d/99-proximal-db-release-upgrade` preserve
the existing database holds through the OS transaction; remove them when
preparing the authorized PG18 package installation.

The managed PG17 cluster was stopped before accepting the OS installation to
avoid writes across the glibc collation transition. Its on-disk size is 227 GiB;
root has enough space for a copy-mode migration with the old cluster retained.
There are 21,597 roles and no replication slots. Preserve the roles; allow time
for the native globals restore. Data checksums are off, so the target cluster
must match during `pg_upgrade`. Required extensions include pgvector,
pg_qualstats, pg_stat_kcache, hypopg and pg_repack, plus PostgreSQL contrib.
The Ubuntu pgvector package (0.8.1) is older than the installed 0.8.6; use a
compatible PGDG build for PG18 rather than downgrading the extension.

## OS installation and NVIDIA repair

The release upgrader installed Ubuntu 26.04.1, but reported errors because NVIDIA
615.71.10's CXL header detection failed against kernel 7.0.0-42. The GPU-unlock
and nct6687d modules built successfully. The [NVIDIA compatibility patch](config/nvidia/README.md)
corrects five CXL capability guards through DKMS, retaining NVIDIA's packages.
All five NVIDIA modules subsequently built and installed successfully, and
`dpkg --configure -a` completed successfully. The package database is clean.
This is a source compatibility repair, not a driver or kernel version hold.

The [vendor APT sources](config/apt/README.md) were restored for 26.04. Native
APT signature verification passed, including NVIDIA's new Ubuntu 26.04 key.
SSH configuration was preserved, native `sshd -t` passed and SSH was started.
The existing GRUB menu and GPU-unlock command line were preserved.

Four existing virtual environments (`/opt/binkeeper/venv`, `~/agent-board/.venv`,
`~/git/engram/.venv`, `~/git/ai-newsroom/.venv`) had unversioned interpreter links
that would silently switch their Python ABI. Their links now explicitly use
their original Python 3.12 interpreter. System Python is 3.14. This preserves
the environments' existing dependencies; it is not an APT version hold.

## Database maintenance state

The original PG17 `pg_hba.conf` is privately saved as `pg17-hba.original` in the
recovery directory. Temporary rules allow only local peer-authenticated
`postgres` and reject all other connections during migration. Restore the
original access policy on the validated PG18 cluster before restarting clients.

The temporary exact-version preference file and all 17 original APT holds were
removed. `create_main_cluster = false` temporarily prevents package installation
from creating an unrelated empty PG18 cluster; its original configuration is
saved as `createcluster.conf.original`. Package installation runs as
`ubuntu2604-pg18-packages.service`, with private output in `pg18-packages.log`.

Before accepting the release upgrade, review its calculated removals. Afterwards
check dpkg consistency, Python services, PostgreSQL and collation versions,
Docker containers, ZFS, NVIDIA, SSH/Tailscale and the new boot image. Reboot is
required to activate the new kernel; verify the host again after boot.
