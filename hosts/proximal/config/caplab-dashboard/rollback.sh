#!/usr/bin/env bash
set -euo pipefail

data_root=${CAPLAB_DASHBOARD_DATA_ROOT:-"$HOME/.local/share/caplab-dashboard"}
source_repo=${CAPLAB_DASHBOARD_SOURCE_REPO:-"$HOME/git/books"}
current_link="$data_root/current"
previous_link="$data_root/previous"

die() {
    printf 'caplab-dashboard rollback: %s\n' "$*" >&2
    exit 1
}

[[ -L "$current_link" ]] || die "current release link is absent"
[[ -L "$previous_link" ]] || die "no previous release is recorded"
current_target=$(readlink -- "$current_link")
previous_target=$(readlink -- "$previous_link")
for target in "$current_target" "$previous_target"; do
    [[ "$target" =~ ^releases/[0-9a-f]{40}$ ]] || die "unexpected release target: $target"
    [[ -d "$data_root/$target/app" ]] || die "release target is absent: $target"
    commit=${target#releases/}
    [[ $(tr -d '\n' < "$data_root/$target/SOURCE_COMMIT") == "$commit" ]] ||
        die "source stamp does not match release directory: $target"
done
[[ "$current_target" != "$previous_target" ]] || die "current and previous releases are identical"

# Reconstruct and compare the complete previous application before it can
# become live. A matching directory name and source stamp are not sufficient.
previous_commit=${previous_target#releases/}
resolved_commit=$(git -C "$source_repo" rev-parse --verify "${previous_commit}^{commit}") ||
    die "previous source commit is unavailable in $source_repo"
[[ "$resolved_commit" == "$previous_commit" ]] || die "previous commit did not resolve exactly"
verify_dir=$(mktemp -d)
trap 'rm -rf -- "$verify_dir"' EXIT
mkdir -p -- "$verify_dir/app"
git -C "$source_repo" archive --format=tar "$previous_commit" caplab |
    tar -xf - -C "$verify_dir/app"
diff -qr -- "$verify_dir/app" "$data_root/$previous_target/app" >/dev/null ||
    die "previous release differs from its exact Git archive"

tmp_current="$data_root/.current-$$"
tmp_previous="$data_root/.previous-$$"
cleanup() {
    rm -f -- "$tmp_current" "$tmp_previous"
    rm -rf -- "$verify_dir"
}
trap cleanup EXIT

restore_links() {
    rm -f -- "$tmp_current" "$tmp_previous"
    ln -s -- "$current_target" "$tmp_current"
    ln -s -- "$previous_target" "$tmp_previous"
    mv -Tf -- "$tmp_current" "$current_link"
    mv -Tf -- "$tmp_previous" "$previous_link"
}

ln -s -- "$previous_target" "$tmp_current"
ln -s -- "$current_target" "$tmp_previous"
mv -Tf -- "$tmp_current" "$current_link"
if ! mv -Tf -- "$tmp_previous" "$previous_link"; then
    restore_links
    die "could not switch the previous-release pointer; original links restored"
fi
if ! systemctl --user restart caplab-dashboard.service; then
    restore_links
    systemctl --user restart caplab-dashboard.service || true
    die "rolled-back service did not start; original links restored"
fi

printf 'rolled back CAPLAB dashboard from %s to %s\n' \
    "${current_target#releases/}" "${previous_target#releases/}"
printf 'run caplab-dashboard/verify.sh --local-only after updating the canonical SOURCE_COMMIT\n'
