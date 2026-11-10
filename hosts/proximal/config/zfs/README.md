# ZFS ARC limit (proximal)

[`zfs.conf`](zfs.conf) is installed at `/etc/modprobe.d/zfs.conf`. It caps the ARC
for the `nvr` pool at 16 GiB (`zfs_arc_max=17179869184`). The `zfs` module is not in
the initramfs, so the option applies at module load without `update-initramfs`.

**Why (owner, 2026-10-24).** ZFS 2.2.2's default ceiling is half of RAM (62.9 GiB here),
and the ARC sat at that ceiling: 61 GiB, outside `free`'s "used" and `MemAvailable`.
`nvr` holds pg-backups, engram-backups, `/nvr/archive` and NVR recordings. The nightly
restic run reads about 1 TB of them, so demand-data hits were about 51%. Meanwhile swap was
completely full (16 GiB): about 5.8 GiB of postgres `shared_buffers` and about 0.9 GiB
per Docker container were swapped out. Memory PSI was near zero, so the cost was a
missing safety margin and swapped database cache, not stalls.

**Applied live.**
- `echo 17179869184 > /sys/module/zfs/parameters/zfs_arc_max`: the ARC fell from 61 to
  16 GiB in 25 s.
- `swapoff -a && swapon -a` took 2 min and brought 16 GiB back into RAM.
- Afterwards: swap 0 B used, about 61 GiB available, PSI 0.

**Not the cause of the October OOMs.** Both kernel OOMs in the journal (10-14 21:45 and
10-20 10:57) were global, with about 115–118 GiB of anonymous memory, and both killed a
`striatum` drive process (46 and 24 GiB anon). The ARC had already shrunk. The
oversized ARC only meant swap was full beforehand.

**Check:**
`awk '/^(size|c_max) /{print $1, $3/2^30 " GiB"}' /proc/spl/kstat/zfs/arcstats; swapon --show`

**Revert:** delete `/etc/modprobe.d/zfs.conf`, then
`echo 0 | sudo tee /sys/module/zfs/parameters/zfs_arc_max` (0 restores the automatic
half-of-RAM ceiling). OpenZFS 2.3 and later default to nearly all of RAM on Linux, so
keep an explicit cap across a ZFS upgrade.

## SATA disconnect recovery — 2026-11-09

Owner requested recovery after briefly disconnecting the NVR disk while adding
three SATA SSDs. The pool suspended after the Seagate
`ST10000VE001-3BX101`, serial `WWY0EY82`, disappeared from `ata1`.
An AHCI host scan initially found a Samsung SSD on that same port; ports
`ata2`–`ata6` reported no link. Temporarily changing the five empty ports from
`med_power_with_dipm` to `max_performance` and rescanning found no additional
drives; all five policies were restored. The cause of the other ports' missing
links remains unconfirmed. No reboot or controller reset was performed.

After the owner adjusted connections, another scan detected the original
Seagate at `/dev/sdb` via its unchanged by-id identity. `zpool clear nvr`
resumed the existing pool. An initial error listed `nvr/pg-backups:<0x24>`;
read-only `zdb` identified object 36 as SA attribute-layout metadata. The
automatic resilver completed at 21:43:29 PST, processing 168 KiB in one second
with zero errors. Subsequent status was ONLINE with zero device error counters
and **no known data errors**. All five datasets remained mounted, and temporary
create/read/fsync/delete checks passed at their mountpoints. No full scrub was
run; the previous full scrub completed November 8 with zero errors.

The Samsung seen before the final cable adjustment was
`MZ7KM960HAHP-0Z005`, serial `S2L2NWAG700037N`: an existing exFAT partition
labeled `SSD`, UUID `5717-D3E5`, and an HPA exposing 1,534,405,915 of
1,875,385,008 native 512-byte sectors. SMART passed with 462 power-on hours
and no logged errors. Its filesystem and capacity limit were left untouched.
After Seagate recovery, none of the three added SSDs was visible; further
SATA-port diagnosis remains outstanding.
