#!/usr/bin/env bash
# build-image.sh [WARM_SHA]
#
# Builds the GCE image `agent-ee-gate-<stamp>` (family agent-ee-gate) from the
# latest ubuntu-2404-lts-amd64 public image. Run on proximal with gcloud
# configured (project heath-stuff); no sudo on proximal.
#
#   1. checks ci-run.sh and ae-ci-exec against their pinned sha256;
#   2. `git archive WARM_SHA` of ~/git/agent-ee (default 14ef7275) for the warm build;
#   3. creates a Spot builder VM (no service account), uploads the inputs and
#      runs provision.sh as a transient systemd unit;
#   4. stops the builder, creates the image, deletes the builder.
#
# Environment: AGENT_EE (default ~/git/agent-ee), ZONE (us-west1-b),
# BUILDER_TYPE (c2d-highcpu-16), J1_DRAWING (local copy of the J1 PDF; when
# absent the builder downloads it with the CI curl line).
set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
INFRA=$(cd -- "$HERE/../../../.." && pwd)
WARM_SHA=${1:-14ef7275}
AGENT_EE=${AGENT_EE:-$HOME/git/agent-ee}
PROJECT=${PROJECT:-heath-stuff}
ZONE=${ZONE:-us-west1-b}
REGION=${ZONE%-*}
BUILDER_TYPE=${BUILDER_TYPE:-c2d-highcpu-16}
J1_DRAWING=${J1_DRAWING:-$HOME/.cache/ae-ci-exec/inputs/te-776228-1.pdf}
STAMP=$(date -u +%Y%m%d-%H%M)
BUILDER=agent-ee-gate-builder-$STAMP
IMAGE=agent-ee-gate-$STAMP
LABELS=purpose=agent-ee-gate,owner=halbritt

# Pins: ci-run.sh is byte-identical to peecee-wsl ~/agent-ee-gate/ci-run.sh;
# ae-ci-exec is the installed wrapper (infra shared/agent-ee).
export CI_RUN_SHA256=99b77facef615f6edec9b3bd9d3ffbd51e70552e68481f867fc8c86358fca786
export AE_CI_EXEC_SHA256=0e8cb9d2cd030755859932a52bcbbe3d1207039f195385aa5e20cf2d61015290
J1_SHA256=14bd5c3bb2ca16bfcf01918b678eab1aa19df10001c17735dd1f11356a6e4fe8

gc() { gcloud --project "$PROJECT" "$@"; }
ssh_b() { gc compute ssh "$BUILDER" --zone "$ZONE" --ssh-flag=-oServerAliveInterval=30 --command "$1"; }
log() { echo "=== build-image: $*"; }

stage=$(mktemp -d "${TMPDIR:-/tmp}/agent-ee-gate-build.XXXXXX")
trap 'rm -rf "$stage"' EXIT
install -m 0775 "$HERE/ci-run.sh" "$stage/ci-run.sh"
install -m 0755 "$INFRA/shared/agent-ee/ae-ci-exec" "$stage/ae-ci-exec"
install -m 0755 "$HERE/provision.sh" "$stage/provision.sh"
printf '%s  %s\n' "$CI_RUN_SHA256" "$stage/ci-run.sh" | sha256sum --check --strict
printf '%s  %s\n' "$AE_CI_EXEC_SHA256" "$stage/ae-ci-exec" | sha256sum --check --strict
WARM_SHA=$(git -C "$AGENT_EE" rev-parse --short=8 "$WARM_SHA^{commit}")
git -C "$AGENT_EE" archive -o "$stage/agent-ee-$WARM_SHA.tar" "$WARM_SHA"
if [ -f "$J1_DRAWING" ] && printf '%s  %s\n' "$J1_SHA256" "$J1_DRAWING" | sha256sum --check --strict --quiet; then
  cp "$J1_DRAWING" "$stage/te-776228-1.pdf"
fi

base=$(gc compute images describe-from-family ubuntu-2404-lts-amd64 --project ubuntu-os-cloud --format='value(name)')
log "builder $BUILDER ($BUILDER_TYPE Spot, $ZONE) from $base, warm $WARM_SHA"
SPEND=${GCP_SPEND:-$(cd "$(dirname "$0")/../budget" && pwd)/gcp-spend}
# Campaign cap (owner: under $100 cumulative): no ledger reservation, no builder (3 h max-run-duration).
RES=$("$SPEND" reserve --label "image builder" --vm "$BUILDER" --machine-type "$BUILDER_TYPE" --max-hours 3) ||
  { log "BUDGET REFUSED; no builder created"; exit 2; }
gc compute instances create "$BUILDER" --zone "$ZONE" --machine-type "$BUILDER_TYPE" \
  --provisioning-model=SPOT --instance-termination-action=DELETE --max-run-duration=3h \
  --image "$base" --image-project ubuntu-os-cloud \
  --boot-disk-size=100GB --boot-disk-type=pd-balanced \
  --no-service-account --no-scopes --labels "$LABELS"
. "$(dirname "$0")/teardown.sh"
# The reservation is released only when the builder and its disk are proven gone.
cleanup_builder() { teardown_vm "$BUILDER" "$ZONE" "$RES" || echo "builder teardown not proven; reservation $RES kept" >&2; }
trap 'rm -rf "$stage"; cleanup_builder' EXIT

for i in $(seq 30); do ssh_b true 2>/dev/null && break; sleep 10; done
ssh_b 'mkdir -p /var/tmp/gate-build'
gc compute scp --zone "$ZONE" "$stage"/* "$BUILDER:/var/tmp/gate-build/"
ssh_b "sudo systemd-run --unit=agent-ee-gate-provision --collect \
  -p StandardOutput=file:/run/provision.log -p StandardError=inherit \
  -E CI_RUN_SHA256=$CI_RUN_SHA256 -E AE_CI_EXEC_SHA256=$AE_CI_EXEC_SHA256 \
  bash /var/tmp/gate-build/provision.sh /var/tmp/gate-build $WARM_SHA"

# provision.sh reports on the serial console and powers the builder off; after
# its cleanup step SSH logins no longer work (no authorized_keys).
log "provisioning (warm docker build included; ~15 min)"
marker=
while [ -z "$marker" ]; do
  sleep 30
  if ! out=$(gc compute instances get-serial-port-output "$BUILDER" --zone "$ZONE" 2>/dev/null); then
    gc compute instances describe "$BUILDER" --zone "$ZONE" --format='value(status)' >/dev/null 2>&1 ||
      { echo "builder $BUILDER is gone (Spot preemption?); rerun build-image.sh" >&2; exit 1; }
    continue
  fi
  marker=$(printf '%s\n' "$out" | grep -o 'AGENT-EE-GATE-PROVISION rc=[0-9]*' | tail -n 1 || true)
done
# Serial lines may carry a console prefix, so match anywhere in the line.
printf '%s\n' "$out" | grep -E '(=== provision|warm build took|agent-ee +ci-|AGENT-EE-GATE-PROVISION)' || true
if [ "$marker" != 'AGENT-EE-GATE-PROVISION rc=0' ]; then
  printf '%s\n' "$out" | tail -n 60 >&2
  echo "provision.sh failed ($marker); builder $BUILDER kept for diagnosis (delete it when done)" >&2
  trap 'rm -rf "$stage"' EXIT
  exit 1
fi
for i in $(seq 60); do
  [ "$(gc compute instances describe "$BUILDER" --zone "$ZONE" --format='value(status)')" = TERMINATED ] && break
  sleep 10
done

log "create image $IMAGE"
gc compute instances stop "$BUILDER" --zone "$ZONE" --quiet
gc compute images create "$IMAGE" --source-disk "$BUILDER" --source-disk-zone "$ZONE" \
  --family agent-ee-gate --labels "$LABELS" --storage-location "$REGION" \
  --description "agent-ee release-gate host: Ubuntu 24.04 ($base), docker.io 29.1.3, buildx 0.30.1, ci-run.sh $CI_RUN_SHA256, warm agent-ee:ci-$WARM_SHA"
gc compute images describe "$IMAGE" --format='value(name,selfLink,diskSizeGb,archiveSizeBytes,creationTimestamp)'
log "done: $IMAGE"
