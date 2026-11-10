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
