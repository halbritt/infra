#!/bin/bash
# Resume verification of completed SSD snapshots without copying them again.
set -euo pipefail
umask 077
base=/nvr/archive/ssd-recovery-2026-11-09
export RESTIC_REPOSITORY="$base/repository"
export RESTIC_PASSWORD_FILE="$base/password"
export RESTIC_CACHE_DIR="$base/cache"
stage() { printf '%s %s\n' "$(date -Is)" "$1" | tee "$base/status"; }
finish() {
    result=$?
    trap - EXIT
    if [[ $result != 0 ]]; then stage "FAILED verification exit=$result; originals retained"; fi
    if ! systemctl start ssd-recovery-browse.service; then
        printf 'Archive browser restart failed\n' >> "$base/errors.log"
        result=1
    fi
    exit "$result"
}
trap finish EXIT
[[ $(id -u) == 0 ]]
[[ $(findmnt -n -o SOURCE -T "$base") == nvr/archive ]]
python3 - "$base" <<'PY'
import json, pathlib, sys
base = pathlib.Path(sys.argv[1])
summaries = []
for name in ('files-backup', 'files-recheck', 'image-backup'):
    records = [json.loads(line) for line in (base/'logs'/f'{name}.jsonl').read_text().splitlines()]
    summary = [r for r in records if r.get('message_type') == 'summary']
    assert len(summary) == 1, name
    summaries.append(summary[0])
first, second, image = summaries
assert first['total_files_processed'] == second['total_files_processed'] == 491860
assert first['total_bytes_processed'] == second['total_bytes_processed'] == 320200807199
assert second['data_blobs'] == 0
assert image['total_files_processed'] == 1 and image['total_bytes_processed'] == 441218675908
PY
# A FUSE browser holds a shared lock; check requires an exclusive lock.
systemctl stop ssd-recovery-browse.service
stage REPOSITORY_FULL_READ_VERIFY
restic check --read-data > "$base/logs/repository-check-resumed.log" 2>&1
stage HFS_IMAGE_CHECKSUM_VERIFY
restic dump --tag sm863-filesystem latest /sm863.hfsp.partclone \
    | partclone.chkimg -s - -L "$base/logs/partclone-verify.log" \
    > "$base/logs/image-check.log" 2>&1
restic snapshots --json > "$base/snapshots.json"
restic stats --mode raw-data --json > "$base/stored-stats.json"
restic stats --mode restore-size --tag ssd-files latest --json > "$base/files-logical-stats.json"
sync -f "$base"
stage 'VERIFIED; ready for owner-authorized SSD wipe and provisioning'
touch "$base/COMPLETE"
