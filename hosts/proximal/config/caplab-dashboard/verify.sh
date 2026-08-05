#!/usr/bin/env bash
set -euo pipefail

subsystem_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_repo=${CAPLAB_DASHBOARD_SOURCE_REPO:-"$HOME/git/books"}
data_root=${CAPLAB_DASHBOARD_DATA_ROOT:-"$HOME/.local/share/caplab-dashboard"}
unit_dir=${CAPLAB_DASHBOARD_UNIT_DIR:-"$HOME/.config/systemd/user"}
local_only=false

if [[ ${1:-} == "--local-only" ]]; then
    local_only=true
    shift
fi
[[ $# -eq 0 ]] || {
    printf 'usage: %s [--local-only]\n' "$0" >&2
    exit 2
}

die() {
    printf 'caplab-dashboard verify: %s\n' "$*" >&2
    exit 1
}

expected_commit=$(tr -d '\n' < "$subsystem_dir/SOURCE_COMMIT")
[[ "$expected_commit" =~ ^[0-9a-f]{40}$ ]] || die "invalid canonical SOURCE_COMMIT"
[[ -L "$data_root/current" ]] || die "current release link is absent"
current_target=$(readlink -- "$data_root/current")
[[ "$current_target" == "releases/$expected_commit" ]] ||
    die "current release is $current_target, expected releases/$expected_commit"
release_dir="$data_root/$current_target"
[[ -d "$release_dir/app" ]] || die "current application directory is absent"
cmp -s -- "$subsystem_dir/SOURCE_COMMIT" "$release_dir/SOURCE_COMMIT" ||
    die "installed source stamp differs from canonical SOURCE_COMMIT"
cmp -s -- "$subsystem_dir/caplab-dashboard.service" "$unit_dir/caplab-dashboard.service" ||
    die "installed user unit differs from canonical unit"

tmp_dir=$(mktemp -d)
trap 'rm -rf -- "$tmp_dir"' EXIT
mkdir -p -- "$tmp_dir/app"
resolved_commit=$(git -C "$source_repo" rev-parse --verify "${expected_commit}^{commit}") ||
    die "source commit is unavailable in $source_repo"
[[ "$resolved_commit" == "$expected_commit" ]] || die "source commit did not resolve exactly"
git -C "$source_repo" archive --format=tar "$expected_commit" caplab |
    tar -xf - -C "$tmp_dir/app"
diff -qr -- "$tmp_dir/app" "$release_dir/app" >/dev/null ||
    die "installed application differs from the exact Git archive"

[[ $(systemctl --user is-enabled caplab-dashboard.service) == enabled ]] ||
    die "user service is not enabled"
[[ $(systemctl --user is-active caplab-dashboard.service) == active ]] ||
    die "user service is not active"
main_pid=$(systemctl --user show caplab-dashboard.service --property=MainPID --value)
[[ "$main_pid" =~ ^[1-9][0-9]*$ ]] || die "user service has no live main process"
process_cwd=$(readlink -- "/proc/$main_pid/cwd") || die "cannot read service process cwd"
expected_cwd=$(realpath -- "$release_dir/app")
[[ "$process_cwd" == "$expected_cwd" ]] ||
    die "service process is running from $process_cwd, expected $expected_cwd"

listeners=$(ss -ltnH "sport = :3021")
[[ -n "$listeners" ]] || die "nothing is listening on TCP port 3021"
while IFS= read -r listener; do
    local_address=$(awk '{print $4}' <<<"$listener")
    [[ "$local_address" == "127.0.0.1:3021" ]] ||
        die "non-loopback or unexpected listener on port 3021: $local_address"
done <<<"$listeners"

health=$(curl --fail --silent --show-error --max-time 10 http://127.0.0.1:3021/healthz)
python3 -c '
import json, sys
payload = json.load(sys.stdin)
if payload.get("status") != "ok":
    raise SystemExit("health response is not ok")
' <<<"$health"
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:3021/api/studies >/dev/null
status=$(curl --silent --output /dev/null --write-out '%{http_code}' --request POST --max-time 10 http://127.0.0.1:3021/)
[[ "$status" == 405 ]] || die "POST / returned $status instead of 405"

if ! $local_only; then
    serve_status=$(tailscale serve status --json)
    python3 -c '
import json, sys
payload = json.load(sys.stdin)
tcp = payload.get("TCP", {}).get("8784")
web = payload.get("Web", {}).get("proximal.tail0ecc2e.ts.net:8784")
expected_web = {"Handlers": {"/": {"Proxy": "http://127.0.0.1:3021"}}}
if tcp != {"HTTPS": True} or web != expected_web:
    raise SystemExit("expected tailnet-only HTTPS :8784 proxy is absent or changed")
if payload.get("AllowFunnel") is not None:
    raise SystemExit("Tailscale Funnel is enabled")
' <<<"$serve_status"
    curl --fail --silent --show-error --max-time 15 \
        https://proximal.tail0ecc2e.ts.net:8784/healthz >/dev/null
fi

printf 'verified CAPLAB dashboard source %s\n' "$expected_commit"
printf 'origin: http://127.0.0.1:3021/\n'
if ! $local_only; then
    printf 'tailnet: https://proximal.tail0ecc2e.ts.net:8784/\n'
fi
