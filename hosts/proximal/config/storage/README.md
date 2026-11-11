# Additional SATA SSDs

## Independent filesystems and repository migration — 2026-11-10

The owner subsequently rejected the RAID0 failure domain and selected three
independent Btrfs filesystems for isolation and future flexibility. The empty
RAID0 pool was replaced; the verified NVR archive remains intact. Each SSD uses
single data, DUP metadata on the same drive, zstd:1 compression, async discard
and noatime. DUP metadata is not inter-drive mirroring.

| Mount | Serial | Capacity | UUID |
| --- | --- | --- | --- |
| `/srv/ssd1` | S2L6NWAG900094X | 1.92 TB | 954c1ca5-f288-4927-b2a8-71d45dfcc9f4 |
| `/srv/ssd2` | S2L2NWAG700037N | 960 GB | 1f2e26d5-78a7-4a1c-bfd0-9a48daa151cc |
| `/srv/ssd3` | S2HNNYAG700171 | 1.92 TB | 37d48f58-7d33-46f6-9e3d-5d87c5a392a1 |

`workspaces.fstab` now supplies these three UUID mounts to `/etc/fstab`,
replacing the obsolete `/srv/workspaces` entry. The owner authorized migrating
`/home/halbritt/git` to `/srv/ssd1/git` and binding it at its original path,
including coordinating agent/service restarts to release old directory handles.
`git-bind.fstab` is installed in `/etc/fstab`: `/srv/ssd1/git` is bound at
`/home/halbritt/git`. Its source mount is an explicit systemd dependency and
it is ordered before `local-fs.target`. The underlying mountpoint is root-owned
mode 000, so an absent mount does not silently become an owner-writable tree.
The original paths, including Git worktree references, remain valid.

Cutover passed a full `rsync -aHAXxnc --delete` comparison with zero differences
after final synchronization. The staged tree contains about 125.2 GB logical
data and used about 77.1 GB including Btrfs metadata at verification. Mount
identity/inode equivalence and owner write/read/fsync checks passed. All three
drives have zero Btrfs device errors; NVR remains healthy.

The 24 other agent conversations were checkpointed, exited, and relaunched with
their saved conversation IDs, account profiles and model arguments. All 26
affected services returned active. A later old-directory reference check found
the llama service had been independently restarted during verification; it was
restarted again after cutover and now resolves the new tree. The maintenance
coordinator then restarted into the same conversation, releasing the final old
directory references.

After confirming no process cwd, executable, open-file or mapped-file references
remained, removed only `/home/halbritt/git.before-ssd-20261110`. The removal unit
exited successfully and the old tree is absent. Root available space increased
by 112.98 GiB net during removal (other workloads were active). The source tree
is no longer retained; the SSD copy is authoritative. Evidence, exact launch
profiles and recovery prompts are under
`~/.local/state/ssd-independent-20261110/` (`COPY_VERIFIED`, `CUTOVER`,
`checksum-diff.log`, `resume-manifest.json`, `services-restored.json`,
`cleanup-result.json`).

### Quick performance check

fio 3.41, direct I/O, one drive at a time for each test. Sequential reads:
1 MiB, queue depth 16, 15 seconds over an 8 GiB raw-device region, read-only.
Filesystem sequential writes: 4 GiB incompressible data, 1 MiB, queue depth 16,
final fsync. Random: same 4 GiB file, 4 KiB, 70% reads / 30% writes, queue depth
32, 15 seconds. CoW and checksums remained enabled. All tests returned zero
errors. Files were deleted afterward. Short tests on an active host do not
establish steady-state performance; the repository staging copy began during
the third drive's test, so small differences should not be overinterpreted.

| Drive | Read MB/s (decimal) | Write MB/s | Mixed IOPS |
| --- | ---: | ---: | ---: |
| SSD1 | 566.9 | 371.6 | 47448 |
| SSD2 | 567.4 | 361.5 | 46156 |
| SSD3 | 567.5 | 339.8 | 43751 |

SSD1 was selected for repositories for its capacity and adequate measured
performance. SSD2 now hosts the managed PostgreSQL cluster at `/srv/ssd2/postgresql`, bound
at `/var/lib/postgresql/18/main`; its mount root is root-owned 0755 and the data
subvolume is postgres-owned 0700. SSD3 remains available for independent workload
placement. See the [PostgreSQL migration report](../postgres/reports/SATA_MIGRATION_2026-11-10.md).
The following sections preserve the superseded RAID0 setup and recovery history.

## Initial RAID0 provisioning — 2026-11-10

All three Samsung SSDs were archived, verified, discarded, repartitioned with
GPT, and combined into Btrfs UUID `4e05e477-9107-4eea-af5b-d1760d1d7408`,
label `workspaces`. Live mount: **`/srv/workspaces`**, 4.80 TB / 4.37 TiB,
RAID0 data and single metadata as requested by the owner. The OS/NVMe and NVR
disks were not reformatted. Existing working checkouts were not relocated.

[`workspaces.fstab`](workspaces.fstab) is the canonical entry installed in
`/etc/fstab`; it enables zstd level 1, asynchronous discard, noatime, and the
`@workspaces` subvolume. `nofail` keeps missing workspace disks from blocking
OS startup. The owner has write access to the mount and its `repos`, `build`,
and `cache` subvolumes. Mounting through the generated systemd unit was tested
after unmounting. Owner write/read/fsync, reflink cloning and independent CoW
modification passed; Btrfs device error counters are zero.

The 960 GB SSD's full capacity became visible after unmounting it, removing
only its SCSI device via sysfs, scanning its exact host/target, and refreshing
udev. All serials and byte capacities were revalidated before discard. No
controller-wide reset was used, and NVR remained healthy.

### Preserved data

Archive: `/nvr/archive/ssd-recovery-2026-11-09`.

- `files/` browses the ordinary files on NVR: `ssd-ntfs/`, `ssd-exfat/`, and
  `ssd-sm863/external/`, including `My Pictures2`.
- `timemachine-image` accesses the complete SM863 partclone image. This retains
  the HFS+ structure; restoring it requires partclone and a sufficiently large
  target, not merely extracting Linux's zero-byte directory-link placeholders.
- 761419483107 logical bytes across the ordinary-file snapshot and filesystem
  image occupy 567993729184 stored blob bytes: 193425753923 bytes (25.4%) saved
  through deduplication and compression, excluding small repository overhead.
- All 32209 repository packs passed a complete read; partclone image checksum
  verification passed. A second source read introduced zero data blobs;
  snapshot comparison found zero added, removed or changed files. Three
  representative restored photo/document/RAW files matched source SHA-256.
- `COMPLETE` records archive verification. `PROVISIONED`, `provision-result.json`,
  `provision-preflight.json`, `mkfs-btrfs.log` and `btrfs-usage.txt` record the
  subsequent wipe/provisioning and checks. Original SSD filesystems are gone.

The browser service remains enabled. One-shot completion callback installation
was removed after successful provisioning; its canonical files remain below as
provenance. No automatic snapshots or migration of existing workloads was added.

## 2026-11-09 post-reboot inspection

After the SATA maintenance reboot, all three added SSDs enumerate at 6 Gb/s.
SMART passes on all three, with zero reported reallocated, pending,
uncorrectable or CRC errors and empty ATA error logs. The existing NVR pool
is ONLINE with no known data errors; its datasets are mounted read/write.

The owner requested mounting existing filesystems for inspection. These are
temporary read-only mounts, not fstab entries:

| Serial | Nominal capacity | Filesystem / UUID | Mount |
| --- | --- | --- | --- |
| S2L6NWAG900094X | 1.92 TB | NTFS / `15EFC78F6BC8CB02` | `/mnt/ssd-ntfs` |
| S2L2NWAG700037N | 960 GB | exFAT SSD / `5717-D3E5` | `/mnt/ssd-exfat` |
| S2HNNYAG700171 | 1.92 TB | HFS+ SM863 / `fc8f9ee1-2d51-3d62-a7a8-366c62bd4fa1` | `/mnt/ssd-sm863` |
| S2HNNYAG700171 | 200 MiB partition | FAT EFI / `67E3-17ED` | `/mnt/ssd-sm863-efi` |

NTFS uses ntfs-3g; NTFS, exFAT and FAT mounts select uid/gid 1000. HFS+ uses
the kernel driver with `ro`. Root directory listings were readable as halbritt.
Do not format or repurpose these disks without a separate owner decision.

## Capacity limit removal

At the owner's explicit request, removed the HPA limit from Samsung
MZ7KM960HAHP-0Z005, serial S2L2NWAG700037N, using its stable by-id path and
`hdparm -Np1875385008`. Verified `1875385008/1875385008`, HPA disabled;
SMART IDENTIFY reports 960197124096 bytes. Before this change it exposed
1534405915 sectors (785615828480 bytes).

Saved the partition dump and first 1 MiB before changing the drive setting in
`~/.local/state/infra-restart-20261109/`. Byte comparison of that first MiB
afterward passed. No partition or filesystem resizing occurred.
The existing exFAT partition starts at sector 2 and spans 1534405913 sectors.

Linux still reports the old block-device capacity after sysfs SCSI rescan and
`hdparm -z`; another drive reinitialization/power cycle may be needed to expose
the extra space to the kernel. No controller reset or drive disconnect was
performed because the owner requested inspecting the mounted filesystems.

## Deduplicated NVR archive (owner request, 2026-11-09)

Owner requested moving the identified material to NVR with deduplication, then
explicitly selected removal of originals **after verification**. Destination:
`/nvr/archive/ssd-recovery-2026-11-09`. The transfer also includes the complete
NTFS and exFAT volumes to avoid losing material missed by the initial inventory.
The entire SM863 HFS+ filesystem is captured with partclone, preserving the
Time Machine catalog and directory links which Linux displays as zero-byte files.
Its `external` directory and standalone document are also archived as ordinary
files for convenient browsing.

Restic 0.18.1 provides content-addressed chunk deduplication and compression,
preserving separate filenames and metadata. It is a new **local** repository;
no existing restic repository or ZFS dedup property is changed. Its random
password is stored beside it in `password`, mode 0600, below the owner's private
0700 archive directory. Retain that file with the archive. Never commit it.
Existing off-site backup policy includes `/nvr/archive`; it does not follow
the browser symlink.

`archive-ssds.sh` is canonical here, installed as `<destination>/archive-ssds.sh`
and run as the transient system unit `ssd-recovery-archive.service`. It verifies
source UUIDs and read-only mounts, backs up the files, rereads them with `--force`,
unmounts SM863 for partclone capture and remounts it read-only, performs a full
`restic check --read-data`, and verifies the archived partclone image checksums.
It stops on failures, including incomplete restic backups or producer failure.
It does not delete source files. Source removal is a separate action after the
verification evidence is reviewed. No bypass of HFS+ journal/write protections
is authorized by this procedure.

`status`, `job.log`, and `logs/` record progress and errors. `COMPLETE` means the
archive's verification stages completed; it does not mean sources were removed.
`snapshots.json`, `stored-stats.json`, and `files-logical-stats.json` capture the
final snapshot identities and sizes. A failed run must be inspected before retry.

`ssd-recovery-browse.service` is installed under `/etc/systemd/system/` and enabled.
It mounts the archive read-only at `/mnt/ssd-archive-private/browse`, behind an
owner-only 0700 parent. `<destination>/browse` is a symlink to that mount.
The `/mnt` location is allowed by the installed fusermount AppArmor profile;
mounting directly below `/nvr` was rejected. No AppArmor policy was changed.
The mount retains separate views of every snapshot and updates as snapshots
finish. The local repository remains usable through restic if the browser is down.

The owner subsequently authorized wiping the three Samsung SATA SSDs after
verification and provisioning them for OS use. They explicitly rejected data
mirroring and accepted failure risk: planned Btrfs RAID0 data, single metadata,
capacity/throughput first, at `/srv/workspaces`. Target raw capacity is about
4.8 TB once Linux recognizes the 960 GB SSD's full capacity. Never include the
Seagate NVR drive or NVMe OS drive in this operation.

`ssd-recovery-archive-notify.conf` is installed as a runtime drop-in on the
archive service, with success/failure activation of `ssd-recovery-continue.service`.
The latter queues a follow-up on the same native Codex conversation/profile
using supported `codex queue --resume`; it does not create a replacement agent.
The follow-up must inspect actual verification results before wiping or formatting.
Its journal records whether queueing and resumption succeeded. The original
archive service itself never wipes drives.

### Verification continuation — 2026-11-10

The initial transfer completed all 491860 files (320200807199 logical bytes)
and the 441218675908-byte partclone stream. Snapshots: `7457e3fb` initial files,
`c600a92e` forced reread, `22b969c9` HFS+ image. Source reread added zero data
blobs; `restic diff` reports zero added, removed or changed files. Full read
verification initially refused the live browser's shared lock (exit 11).
The browser was stopped normally; no lock was forcibly removed.

`verify-ssd-archive.sh`, installed beside the archive script, resumes only the
remaining checks with the browser stopped. It validates the captured summaries,
performs the complete repository read and partclone checksum checks, records
stats/COMPLETE, and restarts the browser. It runs as `ssd-recovery-verify.service`
with the same existing-conversation success/failure callback. No source wipe
is permitted until this verification actually succeeds.

## Claude default-profile restart correction — 2026-11-10

The maintenance restart incorrectly normalized an unset `CLAUDE_CONFIG_DIR` to
`/home/halbritt/.claude` for six default-profile Claude conversations. This is
not equivalent: setting it selects `~/.claude/.claude.json`, while leaving it
unset selects `~/.claude.json`. The former lacked the normal user MCP servers.
The storage migration succeeded, but those sessions lost Cairn and other user
MCP tools until their launch environment was corrected.

Preserve **unset** versus explicitly set profile variables in future restart
manifests. Default-profile Claude must launch with `env -u CLAUDE_CONFIG_DIR`;
keep explicit custom profiles such as `~/.claude-harm` unchanged. Preserve the
conversation ID and model/effort flags. Agent-1348 supplied the six exact commands
in `~/.local/state/ssd-independent-20261110/relaunch-default-profile.sh`.
Repair checkpoints and verification live under
`~/.local/state/cairn-profile-fix-20261110/`. The current SSD `resume-manifest.json`
now explicitly unsets the variable for those six panes. Its original was retained
as `resume-manifest.before-profile-fix.json`; older maintenance bundles are
historical evidence, not commands to reuse without this correction.

All six corrected sessions passed a native `mcp__cairn__cairn_search` call after
relaunch (no CLI fallback). Live process environments confirmed the variable
was absent, and all conversation IDs matched their saved originals.
