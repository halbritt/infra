#!/usr/bin/env bash
# ci-run.sh SHA "<modules>"
#
# Reproduces the agent-ee hosted CI job (.github/workflows/ci.yml, job "image")
# on this host: build the image from the Dockerfile at SHA (tag agent-ee:ci-SHA,
# reused when present), run the doctor and sandbox probe, then run the given
# unittest modules through scripts/strict_suite.py with the CI docker run flags.
# Modules may be given as tests.test_x or test_x; an empty list runs every module.
#
# Build context: ~/agent-ee-gate/ctx/SHA. When it is missing it is created with
# `git archive SHA` from $AGENT_EE_REPO (default ~/agent-ee-gate/agent-ee.git, a
# bare mirror of https://github.com/halbritt/agent-ee, fetched when SHA is absent).
# From proximal instead:  git -C ~/git/agent-ee archive SHA | ssh peecee-wsl \
#   'mkdir -p ~/agent-ee-gate/ctx/SHA && tar -x -C ~/agent-ee-gate/ctx/SHA'
#
# Environment: JOBS (strict_suite --jobs, default 4 as in CI),
# BUILD_ATTEMPTS (default 6), REBUILD=1 forces a fresh image build.
set -euo pipefail

usage() { echo "usage: $0 SHA \"<modules>\"" >&2; exit 2; }
[ $# -ge 1 ] && [ $# -le 2 ] || usage
SHA=$1
MODULES=${2:-}
[[ $SHA =~ ^[0-9a-f]{7,40}$ ]] || usage

GATE=$HOME/agent-ee-gate
CTX=$GATE/ctx/$SHA
IMAGE=agent-ee:ci-$SHA
REPO=${AGENT_EE_REPO:-$GATE/agent-ee.git}
JOBS=${JOBS:-4}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOGDIR=$GATE/ci-logs
LOG=$LOGDIR/$SHA-$STAMP.log
mkdir -p "$LOGDIR"
exec > >(tee "$LOG") 2>&1
echo "ci-run $SHA at $STAMP; log $LOG"

# --- build context ----------------------------------------------------------
if [ ! -f "$CTX/Dockerfile" ]; then
  if [ ! -d "$REPO" ]; then
    git clone --bare --quiet https://github.com/halbritt/agent-ee.git "$REPO"
  fi
  git -C "$REPO" cat-file -e "$SHA^{commit}" 2>/dev/null ||
    git -C "$REPO" fetch --quiet origin '+refs/heads/*:refs/heads/*'
  git -C "$REPO" cat-file -e "$SHA^{commit}" ||
    { echo "commit $SHA not in $REPO; create $CTX with git archive from proximal" >&2; exit 2; }
  rm -rf "$CTX.partial"; mkdir -p "$CTX.partial"
  git -C "$REPO" archive "$SHA" | tar -x -C "$CTX.partial"
  mv "$CTX.partial" "$CTX"
fi

# CI pins, read from this commit's workflow.
ci_env() { sed -n "s/^ *$1: *\([^ #]*\).*/\1/p" "$CTX/.github/workflows/ci.yml" | head -n 1; }
FOME_MC_COMMIT=$(ci_env FOME_MC_COMMIT)
J1_DRAWING_SHA256=$(ci_env J1_DRAWING_SHA256)
[ -n "$FOME_MC_COMMIT" ] && [ -n "$J1_DRAWING_SHA256" ] || { echo "cannot read CI pins" >&2; exit 2; }

# --- image ------------------------------------------------------------------
if [ "${REBUILD:-0}" = 1 ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  attempts=${BUILD_ATTEMPTS:-6} delay=30 n=1
  while :; do
    echo "=== docker build $IMAGE (attempt $n/$attempts)"
    start=$(date +%s)
    if docker buildx build --progress=plain --load -t "$IMAGE" "$CTX"; then
      echo "=== built $IMAGE in $(( $(date +%s) - start ))s"
      break
    fi
    # Mirror 503s (snapshot.ubuntu.com, Launchpad) fail a layer; BuildKit keeps the
    # finished layers, so a retry resumes after the last good one.
    [ "$n" -lt "$attempts" ] || { echo "image build failed after $n attempts" >&2; exit 1; }
    echo "=== build failed; retrying in ${delay}s"
    sleep "$delay"; delay=$(( delay * 2 > 600 ? 600 : delay * 2 )); n=$(( n + 1 ))
  done
else
  echo "=== reusing $IMAGE"
fi
docker image inspect "$IMAGE" --format 'image {{.Id}} size {{.Size}}'

# --- sandbox options (CI step "Permit container user namespaces") ------------
profile=$(bash "$CTX/scripts/container_apparmor.sh")
SANDBOX_OPTS="--network none --security-opt seccomp=unconfined --security-opt apparmor=$profile --security-opt systempaths=unconfined"
echo "SANDBOX_OPTS=$SANDBOX_OPTS"

echo "=== doctor"
docker run --rm $SANDBOX_OPTS "$IMAGE" agent-ee doctor --checks-only > "$LOGDIR/$SHA-$STAMP.doctor.json"
echo "doctor written to $LOGDIR/$SHA-$STAMP.doctor.json"
echo "=== sandbox probe"
docker run --rm $SANDBOX_OPTS "$IMAGE" python3 /opt/agent-ee/scripts/check_container_sandbox.py

# --- required external inputs -------------------------------------------------
# fome-mc: anonymous public clone at the pinned commit, owned by the image user.
STORE=$GATE/ci-inputs/fome-mc-$FOME_MC_COMMIT
g() { GIT_TERMINAL_PROMPT=0 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 git -c safe.directory='*' "$@"; }
if [ ! -d "$STORE/.git" ]; then
  mkdir -p "$GATE/ci-inputs"
  rm -rf "$STORE.partial"
  g -c credential.helper= -c http.extraheader= clone --quiet --no-checkout https://github.com/halbritt/fome-mc "$STORE.partial"
  g -C "$STORE.partial" checkout --quiet --detach "$FOME_MC_COMMIT"
  mv "$STORE.partial" "$STORE"
fi
head=$(g -C "$STORE" rev-parse --verify 'HEAD^{commit}')
[ "$head" = "$FOME_MC_COMMIT" ] || { echo "fome-mc HEAD $head is not $FOME_MC_COMMIT" >&2; exit 1; }
if g -C "$STORE" config --local --get-regexp '^(http\..*\.extraheader|credential\.)'; then
  echo "credentials persisted in the fome-mc store" >&2; exit 1
fi
owner=$(docker run --rm --network none "$IMAGE" sh -c 'echo "$(id -u):$(id -g)"')
if [ "$(stat -c %u:%g "$STORE")" != "$owner" ]; then sudo -n chown -R "$owner" "$STORE"; fi
echo "fome-mc store $STORE at $head owned by $owner"

# J1 drawing: local copy, checked against the CI hash (never committed).
J1_DRAWING=$GATE/inputs/te-776228-1.pdf
printf '%s  %s\n' "$J1_DRAWING_SHA256" "$J1_DRAWING" | sha256sum --check --strict

# --- strict suite (CI step "Full test suite, strict toolchain mode, no skips") --
mods=()
for m in $MODULES; do mods+=("${m#tests.}"); done
summary=$(mktemp -d "$GATE/tmp/ci-summary-XXXXXX")
chmod 0777 "$summary"
status=0
set -x
# Under native-admit (infra shared/agent-ee): label the suite container with the
# caller's lease (so admission does not count it twice) and apply the lease's CPU
# and PID bounds; images without a tini ENTRYPOINT (before agent-ee 7e5bdc46) get
# docker's init so orphaned bwrap children are reaped.
ADMIT_OPTS=
if [ -n "${NATIVE_ADMISSION_LEASE:-}" ]; then
  ADMIT_OPTS="--label native-admission.lease=$NATIVE_ADMISSION_LEASE"
  [ -z "${NATIVE_ADMISSION_CPUS:-}" ] || ADMIT_OPTS="$ADMIT_OPTS --cpus $NATIVE_ADMISSION_CPUS"
  [ -z "${NATIVE_ADMISSION_PIDS:-}" ] || ADMIT_OPTS="$ADMIT_OPTS --pids-limit $NATIVE_ADMISSION_PIDS"
fi
case $(docker image inspect -f '{{json .Config.Entrypoint}}' "$IMAGE") in *tini*) ;; *) ADMIT_OPTS="$ADMIT_OPTS --init" ;; esac
docker run --rm $SANDBOX_OPTS $ADMIT_OPTS \
  -e AGENT_EE_REQUIRE_TOOLCHAIN=1 -e PYTHONPATH=src -v "$summary:/summary" \
  -v "$STORE:/opt/fome-mc:ro" -e AGENT_EE_FOME_MC_CHECKOUT=/opt/fome-mc \
  -v "$J1_DRAWING:/opt/j1/te-776228-1.pdf:ro" -e AGENT_EE_J1_DRAWING=/opt/j1/te-776228-1.pdf \
  -w /opt/agent-ee "$IMAGE" python3 scripts/strict_suite.py --jobs "$JOBS" \
  --summary /summary/strict-suite.md "${mods[@]}" || status=$?
{ set +x; } 2>/dev/null
if [ -f "$summary/strict-suite.md" ]; then
  cp "$summary/strict-suite.md" "$LOGDIR/$SHA-$STAMP.summary.md"
  cat "$summary/strict-suite.md"
else
  echo "strict suite wrote no summary"; status=1
fi
rm -rf "$summary"
echo "=== exit $status; log $LOG"
exit "$status"
