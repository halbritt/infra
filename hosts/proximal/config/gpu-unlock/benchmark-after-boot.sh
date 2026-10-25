#!/bin/bash
set -euo pipefail

source_dir=/home/halbritt/git/infra/hosts/proximal/config/gpu-unlock
result_dir=/home/halbritt/.local/state/gpu-unlock
mkdir -p "$result_dir"

# Capture activation evidence even if the benchmark refuses a changed build.
journalctl -k -b --no-pager > "$result_dir/kernel-after.log"
grep -F '0000:01:00.0: gpu_unlock: unlocked' "$result_dir/kernel-after.log"

# The fleet needs heartbeat samples after a reboot before offering the slot.
for attempt in {1..20}; do
    set +e
    /home/halbritt/git/gpu-fleet/bin/gpu-fleet-run \
        --model qwen3.8-27b --max-context 17000 \
        --job gpu-unlock-after-20261025 --timeout 1200 -- \
        python3 "$source_dir/benchmark.py" "$result_dir/after.json" \
        --compare "$source_dir/results/before.json"
    result=$?
    set -e
    if (( result == 0 )); then
        exit 0
    fi
    # Retry only a pre-execution lease failure. Never replay a partial run.
    if (( result != 75 )) || [[ -e "$result_dir/after.json" ]]; then
        exit "$result"
    fi
    sleep 15
done
exit 75
