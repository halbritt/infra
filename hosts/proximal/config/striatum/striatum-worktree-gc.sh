#!/usr/bin/env bash
# striatum-worktree-gc.sh — periodic worktree GC + ownership normalization for the
# striatum checkout.
#
# Why this exists: lanes run as the striatum-lane OS user and write lane-owned files
# both inside their job worktree (.striatum/worktrees/wt_*) and into the worktree
# reflog (.git/worktrees/<id>/logs/HEAD). The daemon and git both run as the operator
# (halbritt), so once a run is terminal those lane-owned files block:
#   * `git gc` / `git reflog expire --all` — "failed to create HEAD.lock: Permission denied"
#   * `striatum worktree gc`              — "git worktree remove ... Permission denied"
# Without cleanup, terminal-run worktrees accumulate unbounded (240+ observed) and the
# host's git gc silently fails. See halbritt/striatum#612.
#
# Runs as root (from striatum-worktree-gc.service) and drops to the operator for every
# daemon/git op. The destructive step (chown) only runs when the daemon reports zero
# active runs, so it can never chown a file an active striatum-lane lane is still writing.
set -uo pipefail

REPO=/home/halbritt/git/striatum
OP=halbritt
HOMEDIR=/home/halbritt
STRIATUM=/home/halbritt/.local/bin/striatum
GIT=/usr/bin/git
RUNTIME_DIR=/run/striatum

log() { echo "[striatum-worktree-gc] $*"; }
[ -d "$REPO/.git" ] || { log "no repo at $REPO; nothing to do"; exit 0; }

# The `striatum` CLI resolves the active (registered) repository from the working
# directory; systemd runs services with cwd=/, so anchor to the repo. CWD propagates
# through runuser/env -i to every operator subprocess below.
cd "$REPO" || { log "cannot cd to $REPO"; exit 0; }

# Resolve the daemon socket and refresh the operator's CLI capability-token cache from the
# daemon's live runtime token. Refreshing every run means we never serve a stale token
# across a daemon boot-epoch rotation (cf. #512); the CLI then authenticates over the unix
# socket (the session-independent transport — the MCP-HTTP endpoint is per-login-session).
SOCK=$(jq -r '.socket_path // empty' "$RUNTIME_DIR/discovery.json" 2>/dev/null)
[ -n "$SOCK" ] || SOCK=/run/striatum/rpc/daemon-go.sock
if [ -r "$RUNTIME_DIR/client-token" ]; then
  install -D -o "$OP" -g "$OP" -m 0600 "$RUNTIME_DIR/client-token" \
    "$HOMEDIR/.cache/striatum/runtime/client-token" 2>/dev/null || true
fi

# Run a command as the operator with a clean, explicit environment (matches the service's
# own minimal env; does not depend on an interactive login profile).
asop() { runuser -u "$OP" -- /usr/bin/env -i HOME="$HOMEDIR" PATH=/usr/bin:/bin \
           STRIATUM_DAEMON_SOCKET="$SOCK" /bin/bash -c "$1"; }

before=$(asop "$GIT -C $REPO worktree list 2>/dev/null | wc -l")

# 1. Daemon-blessed sweep of reachable terminal worktrees (always safe: skips active and
#    divergent-pin worktrees, only removes terminal ones reachable from the run branch).
asop "$STRIATUM worktree gc >/dev/null 2>&1 || true"

# 2. Deep ownership normalization + re-sweep ONLY when quiescent (zero active runs), so we
#    never chown a file an active striatum-lane lane is still writing. A non-quiescent or
#    unreadable state skips the chown; the next quiet tick catches up.
states=$(asop "$STRIATUM list runs 2>/dev/null | jq -r '.items[].state' 2>/dev/null")
if [ -z "$states" ]; then
  active=unknown
else
  active=$(printf '%s\n' "$states" | grep -vcE '^(completed|canceled|failed)$')
fi
log "active runs: $active"
if [ "$active" = "0" ]; then
  chown -R "$OP:$OP" "$REPO/.striatum/worktrees" "$REPO/.git/worktrees" 2>/dev/null || true
  asop "$STRIATUM worktree gc >/dev/null 2>&1 || true"
fi

# 3. Git-level prune + auto-gc (--auto is a cheap no-op unless git's own thresholds are hit;
#    the point is that ownership is now normalized so it can actually run to completion).
asop "$GIT -C $REPO worktree prune 2>/dev/null || true"
asop "$GIT -C $REPO gc --auto --quiet 2>/dev/null || true"

after=$(asop "$GIT -C $REPO worktree list 2>/dev/null | wc -l")
log "worktrees $before -> $after (deep_sweep=$([ "$active" = "0" ] && echo yes || echo skipped:non-quiescent))"
