#!/usr/bin/env bash
# striatum-train — the 04:30 semantic-environment train for striatum-next.
#
# Materialized 2026-08-31 under Principal rulings recorded on the striatum-next
# ledger: RQ-340088 (sitting acceptances), RQ-340254 (timing + D-record
# pre-acceptance + unattended-execution authority, verbatim), RQ-340279
# (branch re-stage to 47e1b98). Executes the accepted governance transaction
# as ONE base movement when the condition is mechanically true. Fail-closed:
# any failure aborts, restores the checkout, preserves all evidence, and
# pages via Alertmanager. It never resolves escalations, never overrides a
# gate verdict, and executes only the personally-accepted payload below.
set -u

REPO=/home/halbritt/git/striatum-next
STATE=/home/halbritt/.local/state/striatum-train
PAYLOAD=/home/halbritt/git/infra/hosts/proximal/config/striatum-train/payload-2026-08-31
GOV_SHA=81f1e69f7b1fbbd6500b8be867468a8743839dbf      # governance-sitting-2026-08-31 (RQ-340088 + RQ-340279; re-staged 2026-08-31 22:50 PDT with the D0016.C8 pin under RQ-345848)
MHCS_SHA=8c3bd40c5a1814a28d1ccc681f676faf34279090     # mhcs-registration (RQ-340088 ruling 2, signed at this commit exactly)
FALLBACK_DATE=2026-09-07                               # RQ-340254: land regardless of frontier state on/after this date
GUARDS=(
  8cbe58cbec88c91e1aab1e16fa9b90d73dfa14e90086788191c090e19383e030
  af069917099ee26d6ae6c18a2f52abfbe4d103fd11a5f40e9fa47c117273e0ef
  c99a906c7280d5e0891ddda86ccc9eae1a4734ca49543a93f8b41821ab427c19
)
AM_URL=http://100.85.100.81:9093/api/v2/alerts
export PATH=/home/halbritt/.local/bin:/usr/local/go/bin:/usr/local/bin:/usr/bin:/bin
export HOME=/home/halbritt
# STRIATUM_TRAIN_FORCE_RULING=RQ-<seq>: a Principal ruling on the ledger that
# supersedes the condition for THIS payload (2026-08-31 22:15 PDT "do it now",
# RQ-345848). STRIATUM_TRAIN_WORKTREE=1: run the transaction from a clean
# detached worktree at origin/main instead of the shared checkout (which may
# carry another session's uncommitted files that must never be touched); the
# shared checkout's main is fast-forwarded afterwards, non-fatally.
FORCE_RULING=${STRIATUM_TRAIN_FORCE_RULING:-}
USE_WORKTREE=${STRIATUM_TRAIN_WORKTREE:-}
WORK=$REPO

mkdir -p "$STATE"
TS=$(date +%Y%m%dT%H%M%S)
LOG="$STATE/train-$TS.log"
exec >>"$LOG" 2>&1
echo "== striatum-train $TS =="

exec 9>"$STATE/lock"
flock -n 9 || { echo "another train run holds the lock; exiting"; exit 0; }

# Done-marker: this payload runs exactly once.
[ -e "$STATE/done-2026-08-31" ] && { echo "payload already landed; nothing to do"; exit 0; }

alert() { # $1 severity $2 summary
  curl -s -m 10 -XPOST "$AM_URL" -H 'Content-Type: application/json' -d "[{
    \"labels\": {\"alertname\": \"StriatumTrain\", \"severity\": \"$1\", \"instance\": \"proximal\"},
    \"annotations\": {\"summary\": \"$2\", \"log\": \"$LOG\"}
  }]" >/dev/null || true
}

ORIG_SHA=""
restore() {
  cd "$WORK" || return
  git branch "train-failed-$TS" HEAD 2>/dev/null || true   # preserve evidence
  git merge --abort 2>/dev/null || true
  [ -n "$ORIG_SHA" ] && git reset --hard "$ORIG_SHA"
  git status --short
}
fail() {
  echo "TRAIN-FAIL: $*"
  restore
  alert page "striatum-train FAILED (fail-closed, checkout restored): $*"
  exit 1
}

req() { # ledger request with lock-busy retries: req <subject> <target> <note-file>
  local i out
  for i in 1 2 3 4 5; do
    out=$(cd "$WORK" && striatum request "$1" -target "$2" -note-file "$3" 2>&1) && { echo "$out"; return 0; }
    echo "$out" | grep -qi 'lock busy' && { sleep 60; continue; }
    echo "$out"; return 1
  done
  return 1
}

# ---- Phase 0: condition -----------------------------------------------------
cd "$REPO" || fail "repo missing"
git fetch -q origin main || fail "fetch failed"
DELIVERED=$(git show origin/main:policy/checks/repository.json | python3 -c "
import json,sys
d=json.load(sys.stdin)
# registry entries key on check_id; a delivered check carries NO delivery_status
# field (only forward-registered red ones do) -- delivered == present and not red.
m={c.get('check_id'):c.get('delivery_status') for c in d['checks']}
ids='${GUARDS[0]} ${GUARDS[1]} ${GUARDS[2]}'.split()
print(sum(1 for i in ids if i in m and m[i]!='red'))
") || fail "condition read failed"
TODAY=$(date +%F)
echo "condition: guards delivered=$DELIVERED/3, today=$TODAY (fallback $FALLBACK_DATE)"
if [ -n "$FORCE_RULING" ]; then
  echo "condition superseded by Principal ruling $FORCE_RULING for this payload; proceeding"
elif [ "$DELIVERED" -lt 3 ] && [[ "$TODAY" < "$FALLBACK_DATE" ]]; then
  echo "condition not met; quiet exit"
  exit 0
fi

# ---- Phase 1: preflight -----------------------------------------------------
if [ -n "$USE_WORKTREE" ]; then
  WORK=/home/halbritt/git/striatum-next-wt/train-$TS
  git worktree add -q --detach "$WORK" origin/main || fail "cannot create train worktree"
  cd "$WORK" || fail "train worktree missing"
  echo "running from detached worktree $WORK"
else
  [ -z "$(git status --porcelain)" ] || fail "working tree not clean"
  git checkout -q main || fail "cannot checkout main"
  git merge --ff-only -q origin/main 2>/dev/null || fail "local main diverged from origin/main"
fi
ORIG_SHA=$(git rev-parse HEAD)
[ "$ORIG_SHA" = "$(git rev-parse origin/main)" ] || fail "HEAD is not origin/main"
git cat-file -e "$GOV_SHA"  || fail "governance sha missing"
git cat-file -e "$MHCS_SHA" || fail "mhcs sha missing"
[ "$(git rev-parse origin/governance-sitting-2026-08-31)" = "$GOV_SHA" ] || fail "governance branch moved off the signed tip"
echo "preflight ok at $ORIG_SHA"

# ---- Phase 2: projection + merge record (BEFORE the write) ------------------
PROJ="$STATE/projection-$TS.txt"
{ timeout 300 striatum status 2>/dev/null | grep -E '^  RQ-' | grep -vE '\[(satisfied|canceled)' || echo "PROJECTION-UNAVAILABLE (status failed — bill uncomputable)"; } > "$PROJ"
grep -q PROJECTION-UNAVAILABLE "$PROJ" && fail "consequence projection unavailable — refusing per the refusal floor (uncomputed consequence lands for no authority kind)"
echo "live requests at projection: $(wc -l < "$PROJ")"
DIFFSTAT=$(git diff --stat "$ORIG_SHA...$GOV_SHA" | tail -1; git diff --stat "$ORIG_SHA...$MHCS_SHA" | tail -1)
NOTE="$STATE/merge-record-$TS.md"
{
  echo "Train merge record (written BEFORE the write), $(date -Is). Executes the personally-accepted governance transaction: rulings RQ-340088 (sitting), RQ-340254 (timing/train/D-record pre-acceptance, verbatim), RQ-340279 (re-stage); instruction RQ-339830; policy record RQ-339831 (cited as context — this is a semantic-environment write priced here, not a code-class landing under that policy)."
  echo
  echo "Payload: merge governance-sitting-2026-08-31@$GOV_SHA + mhcs-registration@$MHCS_SHA into main@$ORIG_SHA; add policy/standing-drain-deadlock-policy.md; regenerate decisions/D0010 and D0016 via tools/decision-gen (outputs pre-accepted for this bracket only, RQ-340254 ruling 2); make deploy."
  echo
  echo "Deploy-surface diff (script output): $DIFFSTAT"
  echo
  echo "Consequence class: semantic-environment (policy/gates.yaml policy_version 2->3 re-pins every gate environment; decision records D0010/D0016 regenerate; catalog gains two target-state registrations with red guards)."
  echo
  echo "Affected-frontier projection (script output, striatum status live-request lines at $(date -Is)); every listed frontier's gate environments re-pin:"
  cat "$PROJ"
  echo
  echo "Condition at execution: withholding-guards delivered=$DELIVERED/3; date=$TODAY; fallback=$FALLBACK_DATE.${FORCE_RULING:+ Condition superseded for this payload by Principal ruling $FORCE_RULING (\"do it now\", verbatim on that record).}"
  echo
  echo "Recovery successor for every affected frontier: ordinary exact regeneration under the cured additive-regeneration path (b731563: an additive Decision Record regeneration keeps pinned environments current; a7eba05: identical regeneration of a stale accepted head is revalidation, not livelock). Stale heads revalidate or rebuild through standard recovery; no manual successor required. Variance handling: if actual consequence exceeds this projection, write a variance record and notify (RQ-339831 variance form applies by analogy)."
} > "$NOTE"
req "striatum-next/passes/governance-train-2026-08-31-merge" captured "$NOTE" || fail "merge record refused"

# ---- Phase 3: merge + artifact ---------------------------------------------
git merge --no-ff --no-verify -q "$GOV_SHA" -m "Merge governance-sitting-2026-08-31 (train; RQ-340088/340254/340279)" || fail "governance merge conflict"
git merge --no-ff --no-verify -q "$MHCS_SHA" -m "Merge mhcs-registration (train; RQ-340088 ruling 2, Phase-2 signatures)" || fail "mhcs merge conflict"
cp "$PAYLOAD/standing-drain-deadlock-policy.md" policy/standing-drain-deadlock-policy.md || fail "policy artifact copy"
git add policy/standing-drain-deadlock-policy.md

# ---- Phase 4: decision-record regeneration (pre-accepted, this bracket only)
go run ./tools/decision-gen -rfc rfcs/0010-work-graph-execution -id D0010 \
  -title "Work-Graph Execution and Verification Runtime" \
  -decided "2026-08-31 (By-Content Continuity and Decoy-Lifecycle Amendment)" \
  > decisions/D0010-work-graph-execution.md || fail "decision-gen D0010"
go run ./tools/decision-gen -rfc rfcs/0016-graduated-acceptance -id D0016 \
  -title "Graduated Acceptance" \
  -decided "2026-08-31 (Pair-Completion and Proxy-Classification Amendment)" \
  > decisions/D0016-graduated-acceptance.md || fail "decision-gen D0016"
git add decisions/D0010-work-graph-execution.md decisions/D0016-graduated-acceptance.md
git commit --no-verify -q -m "train: policy artifact + regenerated D0010/D0016 (outputs pre-accepted, RQ-340254 ruling 2; merge record on ledger)" || fail "artifact commit"

# ---- Phase 5: check + deploy (make deploy runs the full check inline) -------
make deploy || fail "make deploy failed (exit $?)"

# ---- Phase 6: race guard + push + closes ------------------------------------
git fetch -q origin main || true
if [ "$(git rev-parse origin/main)" != "$ORIG_SHA" ]; then
  fail "origin/main moved during the train (variance; not pushing)"
fi
git push origin HEAD:main || fail "push failed after deploy"
touch "$STATE/done-2026-08-31"
if [ -n "$USE_WORKTREE" ]; then
  # Bring the shared checkout's main to the pushed tip without touching its
  # working files (a fast-forward leaves unrelated dirty paths alone).
  ( cd "$REPO" && git fetch -q origin && git merge --ff-only -q origin/main ) \
    && echo "shared checkout main fast-forwarded to $(git rev-parse --short HEAD)" \
    || echo "WARN: shared checkout main NOT fast-forwarded (origin/main is authoritative; ff by hand)"
fi

for pair in \
  "striatum-next/passes/governance-train-2026-08-31-merge:$NOTE" \
  "striatum-next/passes/standing-drain-deadlock-policy-2026-08-31:$PAYLOAD/policy-record-note.md" \
  "striatum-next/passes/principal-instruction-2026-08-31-standing-policy:$PAYLOAD/instruction-note.md" \
  "striatum-next/passes/governance-sitting-2026-08-31:$PAYLOAD/sitting-record-note.md" \
  "striatum-next/passes/governance-train-materialization:$PAYLOAD/train-ruling-note.md"; do
  subj=${pair%%:*}; note=${pair#*:}
  req "$subj" observed "$note" || echo "WARN: observed close refused for $subj (non-fatal; close by hand)"
done

alert warning "striatum-train landed the 2026-08-31 governance transaction: $(git rev-parse --short HEAD) deployed; renewals + C5 pair-completion now in force"
echo "== train complete: $(git rev-parse HEAD) =="
exit 0
