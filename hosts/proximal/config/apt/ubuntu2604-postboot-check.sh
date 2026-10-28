#!/usr/bin/env bash
set -euo pipefail

state=/var/backups/ubuntu-26.04-20261028
previous_boot=$(cat "$state/preboot-id")
expected_kernel=$(cat "$state/expected-kernel")
current_boot=$(cat /proc/sys/kernel/random/boot_id)
if [[ "$current_boot" == "$previous_boot" ]]; then
    echo 'No reboot has occurred; postboot verification refused.'
    exit 1
fi
rm -f "$state/postboot-check.passed"

failures=0
check() {
    local label=$1
    shift
    printf '\nChecking %s\n' "$label"
    if "$@"; then
        printf 'PASS: %s\n' "$label"
    else
        local result=$?
        printf 'FAIL: %s (exit %s)\n' "$label" "$result"
        failures=$((failures + 1))
    fi
}

date --iso-8601=seconds
uname -a
check kernel test "$(uname -r)" = "$expected_kernel"
check ubuntu bash -ec '. /etc/os-release; test "$VERSION_ID" = 26.04'
check dpkg bash -ec 'audit=$(dpkg --audit); printf "%s\n" "$audit"; test -z "$audit"'
check nvidia nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
check nvidia-container nvidia-container-cli info
check zfs bash -ec 'zpool status -x; test "$(zpool list -H -o health nvr)" = ONLINE'
check postgres runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -d postgres <<'SQL'
DO $$ BEGIN
  IF current_setting('server_version_num')::int / 10000 <> 18
     OR EXISTS (SELECT FROM pg_database WHERE datcollversion <> pg_database_collation_actual_version(oid))
     OR EXISTS (SELECT FROM pg_roles WHERE rolname ~ '^(striatumd_rw|striatumd_sut|norol|boot[0-9]+|rot)_striatum_pgtest_[0-9]+_[0-9]+$')
  THEN RAISE EXCEPTION 'Post-upgrade PostgreSQL checks failed'; END IF;
END $$;
SQL
check archiving runuser -u postgres -- pgbackrest --stanza=proximal check

# ssh.socket starts sshd on demand; an idle service is not a boot failure.
check ssh bash -o pipefail -ec 'ssh-keyscan -T 5 127.0.0.1 2>/dev/null | grep -q "^127.0.0.1 "'
for unit in tailscaled docker postgresql@18-main nvidia-persistenced binkeeper llama-27b plane-harm-org; do
    check "$unit.service" systemctl is-active --quiet "$unit.service"
done
for unit in cairn-api cairn-scheduler praxisd praxis-slack praxis-sms gpu-fleet-heartbeat token-dashboard-api; do
    check "user/$unit.service" runuser -u halbritt -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user is-active --quiet "$unit.service"
done
for port in 8090 8190; do
    check "Plane/$port" curl --fail --silent --show-error --max-time 15 --output /dev/null "http://127.0.0.1:$port/api/instances/"
done
check BinKeeper curl --fail --silent --show-error --max-time 15 --output /dev/null http://127.0.0.1:8766/
check llama curl --fail --silent --show-error --max-time 15 --output /dev/null http://127.0.0.1:8081/health
check token-dashboard curl --fail --silent --show-error --max-time 15 --output /dev/null http://127.0.0.1:3002/api/daily-burn

if (( failures != 0 )); then
    printf '\nPostboot checks failed: %s\n' "$failures"
    exit 1
fi
systemctl disable ubuntu2604-postboot-check.timer
printf '%s PASS\n' "$(date --iso-8601=seconds)" > "$state/postboot-check.passed"
echo 'All postboot checks passed.'
