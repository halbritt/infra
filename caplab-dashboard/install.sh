#!/usr/bin/env bash
set -euo pipefail

umask 077

subsystem_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_commit_file="$subsystem_dir/SOURCE_COMMIT"
unit_source="$subsystem_dir/caplab-dashboard.service"
source_repo=${1:-"$HOME/git/books"}
data_root=${CAPLAB_DASHBOARD_DATA_ROOT:-"$HOME/.local/share/caplab-dashboard"}
unit_dir=${CAPLAB_DASHBOARD_UNIT_DIR:-"$HOME/.config/systemd/user"}

die() {
    printf 'caplab-dashboard install: %s\n' "$*" >&2
    exit 1
}

[[ -r "$source_commit_file" ]] || die "cannot read $source_commit_file"
source_commit=$(tr -d '\n' < "$source_commit_file")
[[ "$source_commit" =~ ^[0-9a-f]{40}$ ]] || die "SOURCE_COMMIT is not a full lowercase Git commit"
[[ -d "$source_repo/.git" || -f "$source_repo/.git" ]] || die "not a Git worktree: $source_repo"

resolved_commit=$(git -C "$source_repo" rev-parse --verify "${source_commit}^{commit}") ||
    die "source commit is unavailable in $source_repo"
[[ "$resolved_commit" == "$source_commit" ]] || die "source commit did not resolve exactly"

releases_dir="$data_root/releases"
release_dir="$releases_dir/$source_commit"
stage_dir="$releases_dir/.stage-${source_commit}-$$"
unit_target="$unit_dir/caplab-dashboard.service"
current_link="$data_root/current"
previous_link="$data_root/previous"
tmp_current="$data_root/.current-$$"
tmp_previous="$data_root/.previous-$$"

cleanup() {
    rm -rf -- "$stage_dir"
    rm -f -- "$tmp_current" "$tmp_previous"
}
trap cleanup EXIT

mkdir -p -- "$releases_dir" "$unit_dir"
mkdir -p -- "$stage_dir/app"
git -C "$source_repo" archive --format=tar "$source_commit" caplab |
    tar -xf - -C "$stage_dir/app"
install -m 0444 -- "$source_commit_file" "$stage_dir/SOURCE_COMMIT"

for required in \
    caplab/__init__.py \
    caplab/dashboard/__init__.py \
    caplab/dashboard/server.py \
    caplab/dashboard/index.html \
    caplab/dashboard/app.css \
    caplab/dashboard/app.js \
    caplab/dashboard/studies/caplab-study-001.json
do
    [[ -f "$stage_dir/app/$required" ]] || die "source archive lacks $required"
done

if [[ -e "$release_dir" ]]; then
    [[ -d "$release_dir" && ! -L "$release_dir" ]] || die "release path is not a directory: $release_dir"
    cmp -s -- "$stage_dir/SOURCE_COMMIT" "$release_dir/SOURCE_COMMIT" ||
        die "existing release has a different source stamp"
    diff -qr -- "$stage_dir/app" "$release_dir/app" >/dev/null ||
        die "existing release differs from the exact Git archive"
    rm -rf -- "$stage_dir"
else
    mv -- "$stage_dir" "$release_dir"
fi

old_target=
if [[ -L "$current_link" ]]; then
    old_target=$(readlink -- "$current_link")
    [[ "$old_target" =~ ^releases/[0-9a-f]{40}$ ]] ||
        die "current link has an unexpected target: $old_target"
    [[ -d "$data_root/$old_target" ]] || die "current release target is absent"
elif [[ -e "$current_link" ]]; then
    die "current path exists but is not a symbolic link"
fi

new_target="releases/$source_commit"
if [[ -n "$old_target" && "$old_target" != "$new_target" ]]; then
    ln -s -- "$old_target" "$tmp_previous"
    mv -Tf -- "$tmp_previous" "$previous_link"
fi
ln -s -- "$new_target" "$tmp_current"
mv -Tf -- "$tmp_current" "$current_link"

install -m 0644 -- "$unit_source" "$unit_target"
systemctl --user daemon-reload
systemctl --user enable caplab-dashboard.service
# The server snapshots application and study bytes at process start. Restart
# even when the unit is already active so an update cannot keep serving the
# release that was current before the atomic link switch.
systemctl --user restart caplab-dashboard.service

printf 'installed CAPLAB dashboard source %s\n' "$source_commit"
printf 'release: %s\n' "$release_dir"
printf 'origin: http://127.0.0.1:3021/\n'
