# Additional SATA SSDs

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
