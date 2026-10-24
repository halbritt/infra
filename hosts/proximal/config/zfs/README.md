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
