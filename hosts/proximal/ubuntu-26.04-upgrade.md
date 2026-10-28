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
There are 21,597 roles and no replication slots. The initial decision was to
preserve all roles and allow time for the native globals restore. That was a
preflight error: the June upgrade report explicitly required checking and
cleaning abandoned test roles before another migration (see correction below).
Data checksums are off, so the target cluster
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

## Test-role cleanup correction

The owner challenged the roughly 64,000 restored role grants. Investigation
found 21,557 roles with the exact Striatum test naming patterns, with embedded
creation timestamps from June 17 through July 2. The
[June as-run report](config/postgres/reports/PG17_UPGRADE_ASRUN_2026-06-17.md)
already documented the same failure and the companion plan explicitly required
pre-upgrade cleanup. This instruction was missed during this run's preflight.

The local historical Striatum harness (`go/pkg/pgtest/pgtest.go`) registers
`DROP ROLE` cleanup after database cleanup registration, so Go's reverse cleanup
order attempts to drop a role while its database CONNECT grant still exists.
The error is ignored; the subsequent database deletion leaves the role behind.
Its stale-database sweep also does not remove roles. The old Striatum daemon was
retired in July; this is accumulated historical debris, not evidence of an
active leak in the current Talos deployment.

The native migration was already restoring globals when this was identified.
Let it finish before mutating catalogs. Audit the complete target cluster for
exact test-role names, absent corresponding databases, absence of sessions,
and absence of shared dependencies. Remove only verified orphan roles using
plain `DROP ROLE` in separate transactions; do not use `DROP OWNED`, cascade,
or delete application databases. Preserve the private globals backup and old
cluster. Record actual counts and remaining application-role checks below once
the cleanup has completed.

## PG18 migration and validation results

The native copy-mode migration ran from approximately 08:56 to 09:24 PDT and
completed successfully. Most elapsed time was the avoidable globals restore.
All 22 databases were preserved. PG18 is online on 5432; PG17 is stopped on
5434 with manual startup, and the earlier PG16 copy is stopped on 5433.
No old cluster or application database was deleted.

The complete target catalogs confirmed 21,557 exact test-role matches with no
matching databases, active sessions, or shared dependencies. Plain `DROP ROLE`
in individual transactions removed them, reducing the PG18 catalog from 21,598
roles / 64,124 memberships to **41 roles / 33 memberships**. Comparisons found
zero changes to retained role attributes and unrelated memberships. The
historical `halbritt` grant on `striatumd.repo_event_chain_heads` remains effective.

The generated extension-update script encountered the known dependency of
`pg_stat_kcache` on the `pg_stat_statements` view being replaced. All affected
extensions were owned by postgres in public with standard grants. The initial
schema-dump restore attempt included unrelated application types and failed;
its transaction rolled back. The successful repair transaction used plain
`DROP EXTENSION pg_stat_kcache`, updated `pg_stat_statements`, and recreated
`pg_stat_kcache` with the same effective privileges. No CASCADE was used. The
native extension script then completed, and all installed extension SQL
versions match their available defaults, including pgvector 0.8.7.

Reindexed all 20 connectable databases with changed default glibc collations,
then refreshed their version metadata from 2.39 to 2.43. Cairn uses C and has
no objects depending on changed explicit collations, so its indexes did not
need a locale rebuild. All 21 connectable databases have zero invalid indexes,
zero extension-version mismatches and zero collation-version mismatches. Native
missing-statistics and full ANALYZE passes completed successfully. Durability
and shared-preload settings remain unchanged.

Installed the canonical PG18 pgBackRest configuration and completed offline
`stanza-upgrade`. Native checks confirmed WAL archive delivery to `18-3/`,
including another successful check after applications returned. The original
HBA policy was restored byte-for-byte on PG18 and the retained PG17 cluster;
the temporary cluster-creation override was removed. The first full PG18 backup,
**`20261028-093231F`**, completed successfully at 09:44 PDT: 220.6 GiB of database
files, 29.8 GiB compressed. Normal retention cleanup completed at 09:45, and
`ubuntu2604-pg18-fullbackup.service` exited successfully. Native pgBackRest info
reports `status: ok`; the preceding PG17 full and pre-upgrade incremental backup
remain available. Private log: `pg18-fullbackup.log`.

## Services and boot activation

The remaining vendor packages were upgraded to Ubuntu 26.04 builds, and the
OpenFOAM development/default packages removed by the release upgrader were
restored. `apt-get -s dist-upgrade` reports zero pending upgrades, dpkg audit is
clean, and no APT holds remain. The routine update helper now permits resolute
release/security/updates packages; its original protected-package scope remains.

All baseline user services returned to active state. Restarted Python HTTP and
Praxis services passed startup with the new system interpreter; retained Python
3.12 environments also start successfully. Cairn authenticated reads/writes,
both Plane instance APIs, BinKeeper's root page and the token-dashboard API
respond successfully. The token-dashboard privacy canary passed. Transient
database-outage failures in Cairn delivery alerts recovered on their normal
timer. The previously failed email canary remains a baseline issue.

ZFS reports healthy. NVIDIA persistence/CDI failures reflect the still-loaded
old driver versus newly installed userspace; activation requires reboot.
The installed target kernel is 7.0.0-42-generic, while 6.8.0-147 is still running.
New initramfs contains GPU-unlock and excludes early NVIDIA driver loading.
The [one-time boot check](config/apt/README.md#one-time-upgrade-boot-check)
is enabled for the next boot; its private log and success marker distinguish
installation from verified activation. Shell syntax and native systemd-unit
validation passed; the same-boot guard correctly refuses premature verification.
Native unit validation also reported pre-existing warnings: an ignored
`[Resolve]` section in a service drop-in and a deprecated XFS accounting option.
Live DNS works; those unrelated settings were not changed.

The four maintenance timers stopped for the upgrade are active again. All 43
repository tests and infrastructure validation pass. The remaining step is the
reboot and its automatic verification; do not treat installed kernel/driver
packages as evidence of successful boot activation. Read
`/var/backups/ubuntu-26.04-20261028/postboot-check.log` and require the matching
`postboot-check.passed` marker from the new boot before recording completion.
