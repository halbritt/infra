#!/usr/bin/env bash
# run-gate.sh SHA
#
# Runs the agent-ee release gate for SHA on a throwaway Spot VM booted from the
# image family agent-ee-gate, then deletes the VM. Run on proximal.
#
#   1. creates the VM (default c2d-highcpu-16 Spot, termination action DELETE,
#      max run 3 h, no service account);
#   2. stages `git archive SHA` of ~/git/agent-ee into ~/agent-ee-gate/ctx/SHA;
#   3. runs `JOBS=8 ./ci-run.sh SHA > ci-logs/gate-SHA.out` detached on the VM
#      and polls for its "=== exit N" line;
#   4. copies ~/agent-ee-gate/ci-logs back to $OUT (default
#      ~/agent-ee-gate-gcp/SHA-<stamp>/) and deletes the VM.
# A Spot preemption deletes the VM; the run is then repeated on a new VM, up to
# MAX_ATTEMPTS (3) times. Exit status: ci-run.sh's, or 3 when every attempt was
# preempted. KEEP=1 leaves the VM running (delete it yourself).
#
# Environment: AGENT_EE, ZONE (us-west1-b), MACHINE_TYPE (c2d-highcpu-16),
# JOBS (8), REBUILD (passed to ci-run.sh), IMAGE (default: latest in the family).
set -euo pipefail

[ $# = 1 ] && [[ $1 =~ ^[0-9a-f]{7,40}$ ]] || { echo "usage: $0 SHA" >&2; exit 2; }
AGENT_EE=${AGENT_EE:-$HOME/git/agent-ee}
SHA=$(git -C "$AGENT_EE" rev-parse --short=8 "$1^{commit}")
PROJECT=${PROJECT:-heath-stuff}
ZONE=${ZONE:-us-west1-b}
MACHINE_TYPE=${MACHINE_TYPE:-c2d-highcpu-16}
JOBS=${JOBS:-8}
MAX_ATTEMPTS=${MAX_ATTEMPTS:-3}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT=${OUT:-$HOME/agent-ee-gate-gcp/$SHA-$STAMP}
LABELS=purpose=agent-ee-gate,owner=halbritt

gc() { gcloud --project "$PROJECT" "$@"; }
log() { echo "=== run-gate $(date -u +%H:%M:%S): $*"; }
mkdir -p "$OUT"
image_args=(--image-family agent-ee-gate --image-project "$PROJECT")
[ -z "${IMAGE:-}" ] || image_args=(--image "$IMAGE" --image-project "$PROJECT")

preemptions=0
attempt=1
while :; do
  VM=agent-ee-gate-$SHA-$(date -u +%H%M%S)
  log "attempt $attempt: $VM ($MACHINE_TYPE Spot, $ZONE)"
  gc compute instances create "$VM" --zone "$ZONE" --machine-type "$MACHINE_TYPE" \
    --provisioning-model=SPOT --instance-termination-action=DELETE --max-run-duration=3h \
    "${image_args[@]}" --boot-disk-size=100GB --boot-disk-type=pd-balanced \
    --no-service-account --no-scopes --labels "$LABELS" >/dev/null
  [ "${KEEP:-0}" = 1 ] || trap 'gc compute instances delete "$VM" --zone "$ZONE" --quiet >/dev/null 2>&1 || true' EXIT
  vm() { gc compute ssh "$VM" --zone "$ZONE" --ssh-flag=-oServerAliveInterval=30 --command "$1"; }
  gone() { ! gc compute instances describe "$VM" --zone "$ZONE" --format='value(status)' 2>/dev/null | grep -q RUNNING; }

  for i in $(seq 30); do vm true >/dev/null 2>&1 && break; sleep 10; done
  git -C "$AGENT_EE" archive "$SHA" |
    vm "mkdir -p ~/agent-ee-gate/ctx/$SHA && tar -x -C ~/agent-ee-gate/ctx/$SHA"
  t0=$(date +%s)
  vm "cd ~/agent-ee-gate && setsid nohup env JOBS=$JOBS ${REBUILD:+REBUILD=$REBUILD} ./ci-run.sh $SHA \
      > ci-logs/gate-$SHA.out 2>&1 < /dev/null & echo started"
  status=
  while [ -z "$status" ]; do
    sleep 60
    if line=$(vm "grep -a '^=== exit' ~/agent-ee-gate/ci-logs/gate-$SHA.out || true" 2>/dev/null); then
      status=$(printf '%s\n' "$line" | sed -n 's/^=== exit \([0-9]*\).*/\1/p' | tail -n 1)
    elif gone; then
      status=preempted
    fi
  done
  wall=$(( $(date +%s) - t0 ))
  if [ "$status" = preempted ]; then
    preemptions=$((preemptions + 1))
    log "$VM preempted after ${wall}s"
    [ "$attempt" -lt "$MAX_ATTEMPTS" ] || { log "every attempt preempted ($preemptions)"; exit 3; }
    attempt=$((attempt + 1)); continue
  fi
  vm "tail -n 3 ~/agent-ee-gate/ci-logs/gate-$SHA.out; nproc"
  gc compute scp --zone "$ZONE" --recurse "$VM:agent-ee-gate/ci-logs" "$OUT/" >/dev/null
  log "exit $status; ci-run wall ${wall}s (poll granularity 60 s); preemptions $preemptions; logs $OUT/ci-logs"
  break
done
exit "$status"
