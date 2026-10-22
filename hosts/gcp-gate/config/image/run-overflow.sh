#!/usr/bin/env bash
# run-overflow.sh --host HOST --tree PATH --label LABEL [options] -- COMMAND [ARG...]
#
# Test overflow (owner, 2026-10-22: "if tests are waiting too long, small gcp spot
# instances could be used"). Runs ONE queued, not-yet-running agent-ee test job on a
# throwaway small Spot VM booted from the image family agent-ee-gate, then deletes the
# VM and verifies that the instance and its boot disk are gone. Run on proximal.
#
#   1. creates the VM: MACHINE_TYPE (default c2d-highcpu-4) Spot, termination action
#      DELETE, --max-run-duration MAX (default 90m), boot disk auto-delete, no service
#      account, labels purpose=agent-ee-overflow,owner=halbritt;
#   2. stages the job's worktree from HOST:PATH: tracked files with their working-tree
#      content (`git ls-files`), plus every --include PATH (e.g. untracked build inputs).
#      There is no .git on the VM, the same as the release gate's `git archive` trees;
#   3. installs the current native-admit and ae-ci-exec (infra shared/agent-ee) with a
#      config of budget = max_weight = nproc, so the job runs admitted, with the same
#      --cpus/--pids-limit/init bounds as on shared hosts (the image's own ae-ci-exec
#      predates admission);
#   4. runs `ae-ci-exec . -- COMMAND` detached, with AGENT_EE_SKIP_VISUALS passed through
#      if set, and polls for an exit marker;
#   5. copies the log, the exit marker and every --collect PATH back to OUT (default
#      ~/agent-ee-overflow/<label>-<stamp>/), deletes the VM, and verifies that no
#      instance or disk with its name remains.
# A Spot preemption is reported (exit 3) with whatever was collected. It is not retried
# here: retries are the lane owner's call, under the original job identity.
#
# Options: --machine-type T, --max DURATION, --include PATH (repeatable),
#          --collect PATH (repeatable), --zone Z, --keep (leave the VM; delete it yourself).
# Exit status: COMMAND's exit status, 3 on preemption, 2 on usage/setup errors.
set -euo pipefail

usage() { sed -n '2,3p' "$0" >&2; exit 2; }
HOST= TREE= LABEL= MACHINE_TYPE=c2d-highcpu-4 MAX=90m ZONE=us-west1-b KEEP=0 includes=() collects=()
while [ $# -gt 0 ]; do
  case $1 in
    --host) HOST=$2; shift 2 ;; --tree) TREE=$2; shift 2 ;; --label) LABEL=$2; shift 2 ;;
    --machine-type) MACHINE_TYPE=$2; shift 2 ;; --max) MAX=$2; shift 2 ;; --zone) ZONE=$2; shift 2 ;;
    --include) includes+=("$2"); shift 2 ;; --collect) collects+=("$2"); shift 2 ;;
    --keep) KEEP=1; shift ;; --) shift; break ;; *) usage ;;
  esac
done
[ -n "$HOST" ] && [ -n "$TREE" ] && [[ $LABEL =~ ^[a-z0-9][a-z0-9-]{0,40}$ ]] && [ $# -ge 1 ] || usage
PROJECT=${PROJECT:-heath-stuff}
HERE=$(cd "$(dirname "$0")" && pwd); SHARED=$HERE/../../../../shared/agent-ee
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT=${OUT:-$HOME/agent-ee-overflow/$LABEL-$STAMP}
VM=agent-ee-ovf-$LABEL-$(date -u +%H%M%S); VM=${VM:0:62}
gc() { gcloud --project "$PROJECT" "$@"; }
log() { echo "=== run-overflow $(date -u +%H:%M:%S): $*" | tee -a "$OUT/run.txt"; }
src() { if [ "$HOST" = proximal ]; then bash -c "$1"; else ssh -o BatchMode=yes "$HOST" "$1"; fi; }
mkdir -p "$OUT"
printf '%q ' "$0" --host "$HOST" --tree "$TREE" --label "$LABEL" -- "$@" > "$OUT/invocation.txt"; echo >> "$OUT/invocation.txt"
src "git -C $(printf %q "$TREE") rev-parse HEAD 2>/dev/null; git -C $(printf %q "$TREE") status --porcelain | wc -l" > "$OUT/source.txt" ||
  { echo "cannot read $HOST:$TREE" >&2; exit 2; }

t_create=$(date +%s)
log "creating $VM ($MACHINE_TYPE Spot, $ZONE, max $MAX, delete on termination)"
gc compute instances create "$VM" --zone "$ZONE" --machine-type "$MACHINE_TYPE" \
  --provisioning-model=SPOT --instance-termination-action=DELETE --max-run-duration="$MAX" \
  --image-family agent-ee-gate --image-project "$PROJECT" \
  --boot-disk-size=100GB --boot-disk-type=pd-balanced --boot-disk-auto-delete \
  --no-service-account --no-scopes --labels purpose=agent-ee-overflow,owner=halbritt >/dev/null
cleanup() {
  [ "$KEEP" = 1 ] && { log "KEEP=1: $VM left running"; return; }
  gc compute instances delete "$VM" --zone "$ZONE" --quiet >/dev/null 2>&1 || true
  local left; left=$( { gc compute instances list --filter="name=$VM" --format='value(name)'; gc compute disks list --filter="name=$VM" --format='value(name)'; } 2>/dev/null)
  if [ -z "$left" ]; then log "teardown verified: no instance or disk named $VM"; else log "TEARDOWN INCOMPLETE: $left"; fi
}
trap cleanup EXIT
vm() { gc compute ssh "$VM" --zone "$ZONE" --ssh-flag=-oServerAliveInterval=30 --command "$1"; }
for i in $(seq 30); do vm true >/dev/null 2>&1 && break; sleep 10; done
t_ready=$(date +%s); log "ssh ready after $((t_ready - t_create))s"

# Stage: the current admission tools (budget = nproc on this single-job VM) and the tree.
tar -C "$SHARED" -c native-admit ae-ci-exec | vm 'set -e; mkdir -p ~/.local/bin ~/.config/native-admission ~/overflow/tree ~/.cache/ae-ci-exec/inputs
  d=$(mktemp -d); tar -x -C $d; install -m 0755 $d/native-admit $d/ae-ci-exec ~/.local/bin/; rm -r $d
  n=$(nproc); printf "{\"budget\": %s, \"max_weight\": %s, \"max_suites\": 1, \"cpu_psi_max\": 1000, \"io_psi_max\": 1000, \"pids_limit\": 16384}\n" $n $n > ~/.config/native-admission/config.json
  cp ~/agent-ee-gate/inputs/te-776228-1.pdf ~/.cache/ae-ci-exec/inputs/ 2>/dev/null || true'
inc=$(printf '%q ' "${includes[@]+"${includes[@]}"}")
src "cd $(printf %q "$TREE") && { git ls-files -z; for p in $inc; do find \"\$p\" -print0 2>/dev/null; done; } | tar --null --no-recursion -T - -c" |
  vm 'tar -x -C ~/overflow/tree'
t_staged=$(date +%s); log "staged $HOST:$TREE after $((t_staged - t_ready))s"

envs=""; [ -z "${AGENT_EE_SKIP_VISUALS+x}" ] || envs="AGENT_EE_SKIP_VISUALS=$AGENT_EE_SKIP_VISUALS"
cmd=$(printf '%q ' "$@")
vm "cd ~/overflow/tree && setsid nohup bash -lc 'env $envs AE_CI_MAX_WAIT=600 ~/.local/bin/ae-ci-exec . -- $cmd; echo \"=== exit \$?\"' > ~/overflow/job.log 2>&1 < /dev/null & echo started" >/dev/null
status=
while [ -z "$status" ]; do
  sleep 30
  if line=$(vm "grep -a '^=== exit' ~/overflow/job.log || true" 2>/dev/null); then
    status=$(printf '%s\n' "$line" | sed -n 's/^=== exit \([0-9]*\).*/\1/p' | tail -n 1)
  elif ! gc compute instances describe "$VM" --zone "$ZONE" --format='value(status)' 2>/dev/null | grep -q RUNNING; then
    status=preempted
  fi
done
t_done=$(date +%s)
if [ "$status" = preempted ]; then log "PREEMPTED after $((t_done - t_staged))s; nothing collected from the VM"; exit 3; fi
vm "cd ~/overflow && { nproc; ~/.local/bin/native-admit sample --print; } > vm-facts.txt 2>&1; tar -c job.log vm-facts.txt \$(cd tree && for p in $(printf '%q ' "${collects[@]+"${collects[@]}"}"); do [ -e \"\$p\" ] && echo tree/\$p; done) ~/.local/state/native-admission/events.jsonl 2>/dev/null" |
  tar -x -C "$OUT" 2>/dev/null || true
hours=$(echo "($t_done - $t_create) / 3600" | bc -l)
log "exit $status; job wall $((t_done - t_staged))s; total VM time $((t_done - t_create))s"
log "estimate: $(printf '%.3f' "$(echo "$hours * 0.086" | bc -l)") USD at about \$0.086/h (c2d-highcpu-4 Spot 4 vCPU + 8 GiB, plus 100 GB pd-balanced)"
exit "$status"
