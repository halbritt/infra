#!/usr/bin/env bash
# run-overflow.sh --host HOST --tree PATH --label LABEL (--handoff MATCH | --operator-stopped) [options] -- COMMAND [ARG...]
#
# Test overflow (owner, 2026-10-22: "if tests are waiting too long, small gcp spot
# instances could be used"). Moves ONE queued, never-started agent-ee test job to a
# throwaway small Spot VM booted from the image family agent-ee-gate, then deletes the
# VM and proves the instance and its boot disk are gone. Run on proximal.
#
#   1. creates the VM: MACHINE_TYPE (default c2d-highcpu-4) Spot, termination action
#      DELETE, --max-run-duration MAX (default 90m), boot-disk auto-delete, no service
#      account, labels purpose=agent-ee-overflow,owner=halbritt;
#   2. stages the job's worktree from HOST:PATH (tracked files with their working-tree
#      content, plus every --include PATH; no .git, as in the gate's `git archive`
#      trees) and the current native-admit/ae-ci-exec with budget = max_weight = nproc,
#      so the job is admitted and bounded (--cpus/--pids-limit/init) as on shared
#      hosts. It then prepares the image (`ae-ci-exec . -- true`) WITHOUT running the job;
#   3. hands the job off. With --handoff MATCH, `native-admit cancel-queued --match MATCH`
#      on HOST stops the one queued, never-admitted local request under the admission
#      mutex and proves it never held a lease. If that request had already started
#      (it raced to RUNNING), the original is kept and the VM copy is NEVER executed
#      (exit 7). --operator-stopped records that the lane owner stopped the local job
#      themselves;
#   4. runs `ae-ci-exec . -- COMMAND` detached on the VM (AGENT_EE_SKIP_VISUALS passed
#      through if set) and polls for its exit marker. The VM counts as gone only when
#      `instances describe` succeeds and reports a non-RUNNING state or not-found.
#      Failed observations are UNKNOWN and are retried within a bound; they never
#      restart the job;
#   5. collects job.log, the exit marker, the VM's admission events and every
#      --collect PATH into OUT (default ~/agent-ee-overflow/<label>-<stamp>/). Missing
#      required evidence is reported, and whatever arrived is kept;
#   6. deletes the VM and proves absence only from SUCCESSFUL instance AND disk
#      listings. OUT/summary.json records job, collection and cleanup outcomes
#      separately.
#
# Options: --machine-type T, --max DURATION, --include PATH, --collect PATH (repeatable),
#          --zone Z, --keep. Environment: GCLOUD (default gcloud), OVERFLOW_TOOLS (dir
#          holding native-admit and ae-ci-exec; default infra shared/agent-ee).
# Exit status: the job's exit status when evidence and cleanup are complete; otherwise
# 2 usage/setup, 3 preempted or expired, 4 evidence incomplete, 5 VM state unknown,
# 6 cleanup not proven, 7 local job already running (VM copy not run), 8 handoff failed.
set -uo pipefail

usage() { sed -n '2p' "$0" >&2; exit 2; }
HOST= TREE= LABEL= HANDOFF= OPSTOP=0 MACHINE_TYPE=c2d-highcpu-4 MAX=90m ZONE=us-west1-b KEEP=0 includes=() collects=()
while [ $# -gt 0 ]; do
  case $1 in
    --host) HOST=$2; shift 2 ;; --tree) TREE=$2; shift 2 ;; --label) LABEL=$2; shift 2 ;;
    --handoff) HANDOFF=$2; shift 2 ;; --operator-stopped) OPSTOP=1; shift ;;
    --machine-type) MACHINE_TYPE=$2; shift 2 ;; --max) MAX=$2; shift 2 ;; --zone) ZONE=$2; shift 2 ;;
    --include) includes+=("$2"); shift 2 ;; --collect) collects+=("$2"); shift 2 ;;
    --keep) KEEP=1; shift ;; --) shift; break ;; *) usage ;;
  esac
done
[ -n "$HOST" ] && [ -n "$TREE" ] && [[ $LABEL =~ ^[a-z0-9][a-z0-9-]{0,40}$ ]] && [ $# -ge 1 ] || usage
{ [ -n "$HANDOFF" ] || [ "$OPSTOP" = 1 ]; } || { echo "need --handoff MATCH or --operator-stopped" >&2; exit 2; }
PROJECT=${PROJECT:-heath-stuff}; GCLOUD=${GCLOUD:-gcloud}
HERE=$(cd "$(dirname "$0")" && pwd); TOOLS=${OVERFLOW_TOOLS:-$HERE/../../../../shared/agent-ee}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT=${OUT:-$HOME/agent-ee-overflow/$LABEL-$STAMP}
VM=agent-ee-ovf-$LABEL-$(date -u +%H%M%S); VM=${VM:0:62}
mkdir -p "$OUT"
gc() { "$GCLOUD" --project "$PROJECT" "$@"; }
log() { echo "=== run-overflow $(date -u +%H:%M:%S): $*" | tee -a "$OUT/run.txt"; }
src() { if [ "$HOST" = proximal ]; then bash -c "$1"; else ssh -o BatchMode=yes "$HOST" "$1"; fi; }
vm() { gc compute ssh "$VM" --zone "$ZONE" --ssh-flag=-oServerAliveInterval=30 --command "$1"; }
job_status=none collection=none cleanup=none handoff=none created=0
summary() {
  printf '{"vm": "%s", "machine_type": "%s", "zone": "%s", "handoff": "%s", "job_exit": "%s", "collection": "%s", "cleanup": "%s"}\n' \
    "$VM" "$MACHINE_TYPE" "$ZONE" "$handoff" "$job_status" "$collection" "$cleanup" > "$OUT/summary.json"
}
# vm_state: running | gone:<state> | unknown. Only explicit GCE status values from a successful
# describe count; absence needs a successful exact-name listing that comes back empty. Anything
# else (failed calls, empty or unrecognised output, arbitrary stderr) is UNKNOWN.
vm_state() {
  local out rc
  out=$(gc compute instances describe "$VM" --zone "$ZONE" --format='value(status)' 2>/dev/null); rc=$?
  if [ $rc = 0 ]; then
    case $out in
      RUNNING|PROVISIONING|STAGING|REPAIRING) echo running ;;
      TERMINATED|STOPPING|STOPPED|SUSPENDING|SUSPENDED) echo "gone:$out" ;;
      *) echo unknown ;;
    esac
    return
  fi
  out=$(gc compute instances list --filter="name=$VM" --format='value(name)' 2>/dev/null); rc=$?
  if [ $rc = 0 ] && [ -z "$out" ]; then echo gone:not-found; else echo unknown; fi
}
cleanup() {
  [ "$created" = 1 ] || { summary; return; }
  if [ "$KEEP" = 1 ]; then cleanup=kept; log "--keep: $VM left running"; summary; return; fi
  local err i out_i out_d rc_i rc_d
  err=$(gc compute instances delete "$VM" --zone "$ZONE" --quiet 2>&1) || log "delete reported: $(tail -n1 <<<"$err")"
  for i in 1 2 3; do
    out_i=$(gc compute instances list --filter="name=$VM" --format='value(name)' 2>"$OUT/cleanup-instances.err"); rc_i=$?
    out_d=$(gc compute disks list --filter="name=$VM" --format='value(name)' 2>"$OUT/cleanup-disks.err"); rc_d=$?
    [ $rc_i = 0 ] && [ $rc_d = 0 ] && [ -z "$out_i$out_d" ] && break
    sleep 10
  done
  if [ $rc_i = 0 ] && [ $rc_d = 0 ] && [ -z "$out_i$out_d" ]; then
    cleanup=verified; log "teardown verified: instance and disk listings both succeeded and are empty for $VM"
  else
    cleanup="NOT-PROVEN instances(rc=$rc_i:${out_i:-none}) disks(rc=$rc_d:${out_d:-none})"
    log "CLEANUP NOT PROVEN for $VM: $cleanup; check by hand"
  fi
  summary
}
finish() { # finish CODE: exit after cleanup, preferring the most serious unproven outcome
  local code=$1; cleanup
  [[ $cleanup == verified || $cleanup == kept ]] || code=6
  exit "$code"
}
trap 'finish 2' INT TERM
printf '%q ' "$0" --host "$HOST" --tree "$TREE" --label "$LABEL" ${HANDOFF:+--handoff "$HANDOFF"} -- "$@" > "$OUT/invocation.txt"; echo >> "$OUT/invocation.txt"
src "git -C $(printf %q "$TREE") rev-parse HEAD 2>/dev/null; git -C $(printf %q "$TREE") status --porcelain | wc -l" > "$OUT/source.txt" ||
  { echo "cannot read $HOST:$TREE" >&2; exit 2; }

t_create=$(date +%s)
log "creating $VM ($MACHINE_TYPE Spot, $ZONE, max $MAX, delete on termination, boot-disk auto-delete)"
gc compute instances create "$VM" --zone "$ZONE" --machine-type "$MACHINE_TYPE" \
  --provisioning-model=SPOT --instance-termination-action=DELETE --max-run-duration="$MAX" \
  --image-family agent-ee-gate --image-project "$PROJECT" \
  --boot-disk-size=100GB --boot-disk-type=pd-balanced --boot-disk-auto-delete \
  --no-service-account --no-scopes --labels purpose=agent-ee-overflow,owner=halbritt >/dev/null || { log "create failed"; exit 2; }
created=1
for i in $(seq 30); do vm true >/dev/null 2>&1 && break; sleep 10; done
vm true >/dev/null 2>&1 || { log "VM never became reachable"; finish 5; }
t_ready=$(date +%s); log "ssh ready after $((t_ready - t_create))s"

tar -C "$TOOLS" -c native-admit ae-ci-exec | vm 'set -e; mkdir -p ~/.local/bin ~/.config/native-admission ~/overflow/tree ~/.cache/ae-ci-exec/inputs
  d=$(mktemp -d); tar -x -C $d; install -m 0755 $d/native-admit $d/ae-ci-exec ~/.local/bin/; rm -r $d
  n=$(nproc); printf "{\"budget\": %s, \"max_weight\": %s, \"max_suites\": 1, \"cpu_psi_max\": 1000, \"io_psi_max\": 1000, \"pids_limit\": 16384}\n" $n $n > ~/.config/native-admission/config.json
  cp ~/agent-ee-gate/inputs/te-776228-1.pdf ~/.cache/ae-ci-exec/inputs/ 2>/dev/null || true' || { log "tool staging failed"; finish 2; }
inc=$(printf '%q ' "${includes[@]+"${includes[@]}"}")
missing=$(src "cd $(printf %q "$TREE") && for p in $inc; do [ -e \"\$p\" ] || echo \"\$p\"; done")
[ -z "$missing" ] || { log "declared --include paths missing on $HOST: $missing"; finish 2; }
src "cd $(printf %q "$TREE") && { git ls-files -z; for p in $inc; do find \"\$p\" -print0; done; } | tar --null --no-recursion -T - -c" |
  vm 'tar -x -C ~/overflow/tree' || { log "tree staging failed"; finish 2; }
vm "cd ~/overflow/tree && bash -lc '~/.local/bin/ae-ci-exec . -- true' > ~/overflow/prepare.log 2>&1" || { log "image preparation failed (job not run)"; finish 2; }
t_staged=$(date +%s); log "staged and image prepared after $((t_staged - t_ready))s; job not yet run"

# Handoff: the local request must be stopped, with proof it never ran, before the VM copy starts.
if [ -n "$HANDOFF" ]; then
  res=$(src "~/.local/bin/native-admit cancel-queued --match $(printf %q "$HANDOFF")"); rc=$?
  echo "$res" > "$OUT/handoff.json"
  case $rc in
    0) handoff=cancelled; log "handoff: local queued request stopped, never leased: $res" ;;
    3) handoff=already-running; log "handoff: local request already RUNNING; keeping it, VM copy NOT executed: $res"; finish 7 ;;
    *) handoff="failed(rc=$rc)"; log "handoff failed (rc $rc): $res; VM copy NOT executed"; finish 8 ;;
  esac
else
  handoff=operator-stopped; log "handoff: --operator-stopped (lane owner stopped the local job)"
fi

envs=""; [ -z "${AGENT_EE_SKIP_VISUALS+x}" ] || envs="AGENT_EE_SKIP_VISUALS=$AGENT_EE_SKIP_VISUALS"
cmd=$(printf '%q ' "$@")
vm "cd ~/overflow/tree && setsid nohup bash -lc 'env $envs AE_CI_MAX_WAIT=600 ~/.local/bin/ae-ci-exec . -- $cmd; echo \"=== exit \$?\"' > ~/overflow/job.log 2>&1 < /dev/null & echo started" >/dev/null ||
  { log "could not start the job on the VM"; finish 5; }
unknown=0
while :; do
  sleep "${POLL:-30}"
  if line=$(vm "grep -a '^=== exit' ~/overflow/job.log || true" 2>/dev/null); then
    unknown=0; job_status=$(printf '%s\n' "$line" | sed -n 's/^=== exit \([0-9]*\).*/\1/p' | tail -n 1)
    [ -n "$job_status" ] && break; continue
  fi
  state=$(vm_state)
  case $state in
    running) unknown=0 ;;
    gone:*) job_status="vm-${state#gone:}"; log "VM terminated before the job finished (state ${state#gone:}): preempted or expired"; finish 3 ;;
    *) unknown=$((unknown + 1)); log "VM state UNKNOWN (observation $unknown failed)"
       [ "$unknown" -lt "${UNKNOWN_LIMIT:-10}" ] || { job_status=unknown; log "VM state still UNKNOWN; giving up observation (job not restarted)"; finish 5; } ;;
  esac
done
t_done=$(date +%s)

# Collect: required evidence is job.log with an exit marker plus every declared --collect path.
col=$(printf '%q ' "${collects[@]+"${collects[@]}"}")
vm "cd ~/overflow && { nproc; ~/.local/bin/native-admit sample --print; } > vm-facts.txt 2>&1; missing=; for p in $col; do [ -e tree/\$p ] || missing=\"\$missing \$p\"; done; echo \"\$missing\" > collect-missing.txt
    tar -c job.log vm-facts.txt prepare.log collect-missing.txt \$(for p in $col; do [ -e tree/\$p ] && echo tree/\$p; done) \$(cd ~ && [ -e .local/state/native-admission/events.jsonl ] && echo -C ~ .local/state/native-admission/events.jsonl)" > "$OUT/collected.tar"
crc=$?; tar -x -C "$OUT" -f "$OUT/collected.tar" 2>/dev/null; xrc=$?
problems=
[ $crc = 0 ] || problems="$problems transfer(rc=$crc)"
[ $xrc = 0 ] || problems="$problems unpack(rc=$xrc)"
grep -qa '^=== exit [0-9]' "$OUT/job.log" 2>/dev/null || problems="$problems job.log/exit-marker"
[ -s "$OUT/collect-missing.txt" ] && [ -n "$(tr -d ' \n' < "$OUT/collect-missing.txt")" ] && problems="$problems missing:$(tr '\n' ' ' < "$OUT/collect-missing.txt")"
if [ -z "$problems" ]; then collection=complete; else collection="INCOMPLETE:$problems"; fi
hours=$(echo "($t_done - $t_create) / 3600" | bc -l)
log "job exit $job_status; collection $collection; job wall $((t_done - t_staged))s; total VM time $((t_done - t_create))s"
log "estimate: $(printf '%.3f' "$(echo "$hours * 0.086" | bc -l)") USD at about \$0.086/h (c2d-highcpu-4 Spot 4 vCPU + 8 GiB, plus 100 GB pd-balanced)"
[ "$collection" = complete ] && finish "$job_status" || finish 4
