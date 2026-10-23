#!/usr/bin/env bash
# provision.sh IN_DIR WARM_SHA
#
# Runs as root on the GCE builder VM (Ubuntu 24.04, family ubuntu-2404-lts-amd64),
# started by build-image.sh. IN_DIR holds the uploaded inputs:
#   ci-run.sh             byte-identical copy of peecee-wsl ~/agent-ee-gate/ci-run.sh
#   ae-ci-exec            byte-identical copy of infra shared/agent-ee/ae-ci-exec
#   agent-ee-WARM_SHA.tar `git archive WARM_SHA` of agent-ee (deleted after the warm build)
#   te-776228-1.pdf       optional; the J1 drawing, else fetched with the CI curl line
# Expected hashes come from the environment (CI_RUN_SHA256, AE_CI_EXEC_SHA256).
# The last step removes build-time keys, history and caches, then powers off.
# Run it under systemd-run with stdout in /run/provision.log: the tail of that log
# and a marker line "AGENT-EE-GATE-PROVISION rc=N" go to the serial console,
# which build-image.sh reads, because SSH logins stop once authorized_keys is gone.
# On failure the VM stays up for diagnosis.
set -euo pipefail

report() {
  local rc=$?
  { tail -n 60 /run/provision.log 2>/dev/null; echo "AGENT-EE-GATE-PROVISION rc=$rc"; } > /dev/ttyS0 2>/dev/null || true
  if [ "$rc" = 0 ]; then systemctl --no-block poweroff; fi
}
trap report EXIT

IN=$1
WARM_SHA=$2
: "${CI_RUN_SHA256:?}" "${AE_CI_EXEC_SHA256:?}"

# Versions on peecee-wsl (Ubuntu docker.io packaging): Docker 29.1.3, buildx 0.30.1.
DOCKER_IO_VERSION=29.1.3-0ubuntu3~24.04.2
DOCKER_BUILDX_VERSION=0.30.1-0ubuntu1~24.04.1
J1_URL=https://www.farnell.com/cad/2916153.pdf
GATE_USER=halbritt
GATE=/home/$GATE_USER/agent-ee-gate

log() { echo "=== provision: $*"; }
check_sha() { printf '%s  %s\n' "$1" "$2" | sha256sum --check --strict; }

check_sha "$CI_RUN_SHA256" "$IN/ci-run.sh"
check_sha "$AE_CI_EXEC_SHA256" "$IN/ae-ci-exec"
test -f "$IN/agent-ee-$WARM_SHA.tar"

log "packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q --no-install-recommends \
  "docker.io=$DOCKER_IO_VERSION" "docker-buildx=$DOCKER_BUILDX_VERSION" \
  git rsync jq python3 apparmor apparmor-utils zstd curl ca-certificates
apt-mark hold docker.io docker-buildx
systemctl enable --now docker.service containerd.service
docker version --format 'docker {{.Server.Version}}'
docker buildx version

log "user $GATE_USER"
if ! id "$GATE_USER" >/dev/null 2>&1; then
  if getent passwd 1000 >/dev/null; then useradd -m -s /bin/bash "$GATE_USER"
  else useradd -m -u 1000 -s /bin/bash "$GATE_USER"; fi
fi
usermod -aG docker "$GATE_USER"
# ci-run.sh calls `sudo -n chown` when a new fome-mc pin is cloned. Nothing else.
printf '%s\n' "$GATE_USER ALL=(root) NOPASSWD: /usr/bin/chown" \
  > /etc/sudoers.d/agent-ee-gate
chmod 0440 /etc/sudoers.d/agent-ee-gate
visudo -cf /etc/sudoers.d/agent-ee-gate

asuser() { runuser -u "$GATE_USER" -- "$@"; }

log "gate layout"
asuser mkdir -p "$GATE"/{ci-logs,ctx,tmp,inputs,ci-inputs} "/home/$GATE_USER/.local/bin"
install -o "$GATE_USER" -g "$GATE_USER" -m 0775 "$IN/ci-run.sh" "$GATE/ci-run.sh"
install -o "$GATE_USER" -g "$GATE_USER" -m 0755 "$IN/ae-ci-exec" "/home/$GATE_USER/.local/bin/ae-ci-exec"
check_sha "$CI_RUN_SHA256" "$GATE/ci-run.sh"
check_sha "$AE_CI_EXEC_SHA256" "/home/$GATE_USER/.local/bin/ae-ci-exec"

log "warm build context $WARM_SHA"
CTX=$GATE/ctx/$WARM_SHA
# Extract with umask 0002, as an SSH login of halbritt does (pam_umask usergroups),
# so files keep git-archive modes 664/775. BuildKit's COPY cache key includes the
# mode: a 0022 extraction (644) missed every layer after FROM on the first image.
asuser sh -c 'umask 0002 && mkdir -p "$1" && tar -x -C "$1" -f "$2"' sh "$CTX" "$IN/agent-ee-$WARM_SHA.tar"
stat -c '%a %n' "$CTX/Dockerfile" "$CTX/docker" | tee /dev/stderr | grep -q '^664 '
ci_env() { sed -n "s/^ *$1: *\([^ #]*\).*/\1/p" "$CTX/.github/workflows/ci.yml" | head -n 1; }
FOME_MC_COMMIT=$(ci_env FOME_MC_COMMIT)
J1_SHA256=$(ci_env J1_DRAWING_SHA256)
[ -n "$FOME_MC_COMMIT" ] && [ -n "$J1_SHA256" ]

log "J1 drawing"
J1=$GATE/inputs/te-776228-1.pdf
if [ -f "$IN/te-776228-1.pdf" ]; then
  install -o "$GATE_USER" -g "$GATE_USER" -m 0444 "$IN/te-776228-1.pdf" "$J1"
else
  # The CI acquisition line (.github/workflows/ci.yml).
  curl --fail --silent --show-error --location --proto '=https' --retry 2 \
    --max-time 90 --max-filesize 10000000 --user-agent 'Mozilla/5.0 (X11; Linux x86_64)' \
    "$J1_URL" --output "$J1"
  chown "$GATE_USER:$GATE_USER" "$J1"; chmod 0444 "$J1"
fi
check_sha "$J1_SHA256" "$J1"

log "fome-mc store $FOME_MC_COMMIT"
# Same anonymous clone recipe as ci-run.sh, then owned by the image user (10001).
STORE=$GATE/ci-inputs/fome-mc-$FOME_MC_COMMIT
g() { GIT_TERMINAL_PROMPT=0 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 git -c safe.directory='*' "$@"; }
asuser env GIT_TERMINAL_PROMPT=0 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
  git -c credential.helper= -c http.extraheader= clone --quiet --no-checkout \
  https://github.com/halbritt/fome-mc "$STORE.partial"
asuser env GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 git -C "$STORE.partial" checkout --quiet --detach "$FOME_MC_COMMIT"
mv "$STORE.partial" "$STORE"
[ "$(g -C "$STORE" rev-parse --verify 'HEAD^{commit}')" = "$FOME_MC_COMMIT" ]
if g -C "$STORE" config --local --get-regexp '^(http\..*\.extraheader|credential\.)'; then
  echo "credentials persisted in the fome-mc store" >&2; exit 1
fi
chown -R 10001:10001 "$STORE"

log "userns sysctl (no AppArmor profile, owner 2026-10-23)"
# Containers run apparmor=unconfined; bwrap inside them needs user namespaces without
# Ubuntu's AppArmor restriction.
printf '%s\n' "kernel.apparmor_restrict_unprivileged_userns = 0" > /etc/sysctl.d/60-agent-ee-userns.conf
sysctl -q -p /etc/sysctl.d/60-agent-ee-userns.conf
rm -f /etc/apparmor.d/agent-ee-container

log "warm docker build agent-ee:ci-$WARM_SHA"
# The exact ci-run.sh build line, so later agent-ee:ci-SHA builds hit these layers.
start=$(date +%s)
n=1
until asuser docker buildx build --progress=plain --load -t "agent-ee:ci-$WARM_SHA" "$CTX"; do
  [ "$n" -lt 6 ] || { echo "warm build failed after $n attempts" >&2; exit 1; }
  n=$((n + 1)); sleep 30
done
echo "warm build took $(( $(date +%s) - start ))s"
asuser docker run --rm --network none "agent-ee:ci-$WARM_SHA" agent-ee doctor --checks-only >/dev/null
docker image ls agent-ee
docker system df

log "remove the build context"
# The image and the BuildKit cache stay; only the source tree goes.
rm -rf "$CTX" "$IN"

log "clean up for imaging"
apt-get clean
rm -rf /var/lib/apt/lists/* /var/cache/apt/*.bin
rm -rf /tmp/* /var/tmp/*
for h in /root "/home/$GATE_USER" /home/*; do
  [ -d "$h" ] || continue
  rm -f "$h/.bash_history" "$h/.python_history" "$h/.lesshst" "$h/.viminfo" "$h/.wget-hsts" "$h/.sudo_as_admin_successful"
  rm -f "$h/.ssh/authorized_keys" "$h/.ssh/known_hosts"
  rm -rf "$h/.docker" "$h/.cache" "$h/.config/gcloud"
done
# Users the guest agent created for build-time SSH logins (none expected but halbritt).
for u in $(getent group google-sudoers | cut -d: -f4 | tr , ' '); do
  [ "$u" = "$GATE_USER" ] || userdel -r "$u" 2>/dev/null || true
done
rm -f /etc/ssh/ssh_host_*
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id
cloud-init clean --logs
journalctl --rotate >/dev/null 2>&1 || true
journalctl --vacuum-time=1s >/dev/null 2>&1 || true
find /var/log -type f \( -name '*.gz' -o -name '*.[0-9]' \) -delete
find /var/log -type f -exec truncate -s 0 {} +
unset HISTFILE
sync
log "done"
