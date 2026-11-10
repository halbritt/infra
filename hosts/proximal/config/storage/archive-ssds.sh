#!/bin/bash
# One-time owner-authorized archive of the November 2026 attached SSDs.
set -euo pipefail
umask 077
base=/nvr/archive/ssd-recovery-2026-11-09
export RESTIC_REPOSITORY="$base/repository"
export RESTIC_PASSWORD_FILE="$base/password"
export RESTIC_CACHE_DIR="$base/cache"
hfs=/dev/disk/by-uuid/fc8f9ee1-2d51-3d62-a7a8-366c62bd4fa1
unmounted=0
browser_stopped=0

stage() {
    printf '%s %s\n' "$(date -Is)" "$1" | tee "$base/status"
}

finish() {
    result=$?
    trap - EXIT
    if [[ $unmounted == 1 ]]; then
        if ! mount -t hfsplus -o ro "$hfs" /mnt/ssd-sm863; then
            printf 'SM863 remount failed\n' >> "$base/errors.log"
            result=1
        fi
    fi
    if [[ $result != 0 ]]; then
        stage "FAILED exit=$result; originals retained; inspect logs"
    fi
    if [[ $browser_stopped == 1 ]]; then
        if ! systemctl start ssd-recovery-browse.service; then result=1; fi
    fi
    exit "$result"
}
trap finish EXIT

[[ $(id -u) == 0 ]]
[[ $(findmnt -n -o SOURCE -T "$base") == nvr/archive ]]
[[ ! -e "$base/COMPLETE" ]]
for spec in \
    /mnt/ssd-ntfs:15EFC78F6BC8CB02 \
    /mnt/ssd-exfat:5717-D3E5 \
    /mnt/ssd-sm863:fc8f9ee1-2d51-3d62-a7a8-366c62bd4fa1 \
    /mnt/ssd-sm863-efi:67E3-17ED; do
    mountpoint=${spec%%:*}
    expected=${spec#*:}
    source=$(findmnt -n -o SOURCE --mountpoint "$mountpoint")
    [[ $(blkid -s UUID -o value "$source") == "$expected" ]]
    options=$(findmnt -n -o OPTIONS --mountpoint "$mountpoint")
    [[ ,$options, == *,ro,* ]]
done

mkdir -p "$base/logs" "$base/metadata" "$RESTIC_CACHE_DIR"
sfdisk --dump /dev/disk/by-id/ata-SAMSUNG_MZ7KM1T9HAJM-00005_S2HNNYAG700171 > "$base/metadata/sm863-partitions.sfdisk"
cp /home/halbritt/.local/state/infra-restart-20261109/samsung960-partitions-before-hpa.txt "$base/metadata/"
files=(/mnt/ssd-ntfs /mnt/ssd-exfat /mnt/ssd-sm863/external
       '/mnt/ssd-sm863/IFP Workshop Series.doc' /mnt/ssd-sm863-efi "$base/metadata")

stage FILE_BACKUP
restic backup --json --tag ssd-files --read-concurrency 2 "${files[@]}" > "$base/logs/files-backup.jsonl"
stage FILE_SOURCE_RECHECK
# Force a second source read; content-addressed storage reuses identical data.
restic backup --json --force --tag ssd-files --read-concurrency 2 "${files[@]}" > "$base/logs/files-recheck.jsonl"

stage HFS_IMAGE
umount /mnt/ssd-sm863
unmounted=1
restic backup --json --tag sm863-filesystem --stdin-filename sm863.hfsp.partclone \
    --stdin-from-command -- /usr/sbin/partclone.hfsp -c -s "$hfs" -o - \
    -L "$base/logs/partclone-image.log" > "$base/logs/image-backup.jsonl"
mount -t hfsplus -o ro "$hfs" /mnt/ssd-sm863
unmounted=0

stage REPOSITORY_FULL_READ_VERIFY
systemctl stop ssd-recovery-browse.service
browser_stopped=1
restic check --read-data > "$base/logs/repository-check.log" 2>&1
stage HFS_IMAGE_CHECKSUM_VERIFY
restic dump --tag sm863-filesystem latest /sm863.hfsp.partclone \
    | partclone.chkimg -s - -L "$base/logs/partclone-verify.log" \
    > "$base/logs/image-check.log" 2>&1
restic snapshots --json > "$base/snapshots.json"
restic stats --mode raw-data --json > "$base/stored-stats.json"
restic stats --mode restore-size --tag ssd-files latest --json > "$base/files-logical-stats.json"
sync -f "$base"
stage 'VERIFIED; originals retained pending owner disposition'
touch "$base/COMPLETE"
systemctl start ssd-recovery-browse.service
browser_stopped=0
