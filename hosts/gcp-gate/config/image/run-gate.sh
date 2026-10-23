#!/usr/bin/env bash
# run-gate.sh SHA
#
# Runs the agent-ee release gate for SHA on a throwaway Spot VM booted from the
# image family agent-ee-gate, then deletes the VM. Run on proximal.
#
#   1. creates the VM (default c2d-highcpu-32 Spot, the measured wall-time knee (README "Right-sizing"), termination action DELETE,
#      max run 3 h, no service account);
#   2. stages `git archive SHA` of ~/git/agent-ee into ~/agent-ee-gate/ctx/SHA;
#   3. runs `JOBS=32 CI_RUN_EPHEMERAL_VM=1 ./ci-run.sh SHA > ci-logs/gate-SHA.out` detached on
#      the VM (one VM per gate, so ci-run.sh may run without native-admit there)
#      and polls for its "=== exit N" line;
#   4. copies ~/agent-ee-gate/ci-logs back to $OUT (default
#      ~/agent-ee-gate-gcp/SHA-<stamp>/) and deletes the VM.
# A Spot preemption deletes the VM; the run is then repeated on a new VM, up to
# MAX_ATTEMPTS (3) times, but only after a CONFIRMED preemption (a successful describe or an
# exact-name listing) and a proven teardown of the previous VM, whose reservation is then released.
# Unknown VM state (failed observations) never retries: exit 5. A teardown that cannot be proven keeps
# the reservation and exits 6. Exit status: ci-run.sh's, or 3 when every attempt was
# preempted. KEEP=1 leaves the VM running (delete it yourself).
#
# Environment: AGENT_EE, ZONE (us-west1-b), MACHINE_TYPE (c2d-highcpu-32),
# JOBS (32; keep JOBS = vCPUs), REBUILD (passed to ci-run.sh), IMAGE (default: latest in the family).
set -euo pipefail

[ $# = 1 ] && [[ $1 =~ ^[0-9a-f]{7,40}$ ]] || { echo "usage: $0 SHA" >&2; exit 2; }
AGENT_EE=${AGENT_EE:-$HOME/git/agent-ee}
SHA=$(git -C "$AGENT_EE" rev-parse --short=8 "$1^{commit}")
PROJECT=${PROJECT:-heath-stuff}
ZONE=${ZONE:-us-west1-b}
MACHINE_TYPE=${MACHINE_TYPE:-c2d-highcpu-32}
JOBS=${JOBS:-32}
MAX_ATTEMPTS=${MAX_ATTEMPTS:-3}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT=${OUT:-$HOME/agent-ee-gate-gcp/$SHA-$STAMP}
LABELS=purpose=agent-ee-gate,owner=halbritt

gc() { gcloud --project "$PROJECT" "$@"; }
. "$(dirname "$0")/teardown.sh"
SPEND=${GCP_SPEND:-$(cd "$(dirname "$0")/../budget" && pwd)/gcp-spend}
log() { echo "=== run-gate $(date -u +%H:%M:%S): $*"; }
mkdir -p "$OUT"
image_args=(--image-family agent-ee-gate --image-project "$PROJECT")
[ -z "${IMAGE:-}" ] || image_args=(--image "$IMAGE" --image-project "$PROJECT")

preemptions=0
attempt=1
VM= RES= unknown_limit=${UNKNOWN_LIMIT:-10}
on_exit() { # keep the reservation unless teardown is proven; an unproven teardown makes the exit 6
  local code=$?
  [ -n "$VM" ] && [ "${KEEP:-0}" != 1 ] || exit $code
  teardown_vm "$VM" "$ZONE" "$RES" || code=6
  exit $code
}
trap on_exit EXIT
while :; do
  VM=agent-ee-gate-$SHA-$(date -u +%H%M%S)
  log "attempt $attempt: $VM ($MACHINE_TYPE Spot, $ZONE)"
  # Campaign cap (owner: under $100 cumulative): no ledger reservation, no VM (3 h max-run-duration).
  RES=$("$SPEND" reserve --label "gate $SHA" --vm "$VM" --machine-type "$MACHINE_TYPE" --max-hours 3) ||
    { log "BUDGET REFUSED; no VM created"; exit 2; }
  gc compute instances create "$VM" --zone "$ZONE" --machine-type "$MACHINE_TYPE" \
    --provisioning-model=SPOT --instance-termination-action=DELETE --max-run-duration=3h \
    "${image_args[@]}" --boot-disk-size=100GB --boot-disk-type=pd-balanced \
    --no-service-account --no-scopes --labels "$LABELS" >/dev/null
  vm() { gc compute ssh "$VM" --zone "$ZONE" --ssh-flag=-oServerAliveInterval=30 --command "$1"; }

  for i in $(seq 30); do vm true >/dev/null 2>&1 && break; sleep 10; done
  git -C "$AGENT_EE" archive "$SHA" |
    vm "mkdir -p ~/agent-ee-gate/ctx/$SHA && tar -x -C ~/agent-ee-gate/ctx/$SHA"
  t0=$(date +%s)
  vm "cd ~/agent-ee-gate && setsid nohup env JOBS=$JOBS CI_RUN_EPHEMERAL_VM=1 ${REBUILD:+REBUILD=$REBUILD} ./ci-run.sh $SHA \
      > ci-logs/gate-$SHA.out 2>&1 < /dev/null & echo started"
  status= unknown=0
  while [ -z "$status" ]; do
    sleep "${POLL:-60}"
    if line=$(vm "grep -a '^=== exit' ~/agent-ee-gate/ci-logs/gate-$SHA.out || true" 2>/dev/null); then
      unknown=0; status=$(printf '%s\n' "$line" | sed -n 's/^=== exit \([0-9]*\).*/\1/p' | tail -n 1)
      continue
    fi
    case $(vm_state "$VM" "$ZONE") in
      running) unknown=0 ;;
      gone:*) status=preempted ;;   # confirmed by a successful describe or an exact-name listing
      *) unknown=$((unknown + 1)); log "$VM state UNKNOWN (observation $unknown failed)"
         [ "$unknown" -lt "$unknown_limit" ] || { log "$VM state still UNKNOWN; giving up without retrying"; exit 5; } ;;
    esac
  done
  wall=$(( $(date +%s) - t0 ))
  if [ "$status" = preempted ]; then
    preemptions=$((preemptions + 1))
    log "$VM preempted after ${wall}s"
    teardown_vm "$VM" "$ZONE" "$RES" || { log "previous VM's teardown not proven; not retrying"; VM=; exit 6; }
    VM= RES=
    [ "$attempt" -lt "$MAX_ATTEMPTS" ] || { log "every attempt preempted ($preemptions)"; exit 3; }
    attempt=$((attempt + 1)); continue
  fi
  vm "tail -n 3 ~/agent-ee-gate/ci-logs/gate-$SHA.out; nproc"
  gc compute scp --zone "$ZONE" --recurse "$VM:agent-ee-gate/ci-logs" "$OUT/" >/dev/null
  log "exit $status; ci-run wall ${wall}s (poll granularity 60 s); preemptions $preemptions; logs $OUT/ci-logs"
  break
done
exit "$status"
