#!/usr/bin/env bash
# striatum-lane-cred-resync.sh — keep the striatum-lane OS user's Claude OAuth
# credential in lockstep with the operator's rotating token, so supervised lanes
# never wedge on agent_mcp_discovery_stall mid-dogfood.
#
#   halbritt/striatum#583 (the operational backstop; RFC 0165 covers the
#   complementary supervisor-side relaunch resync).
#
# Why a recurring copy and not a one-shot at lane launch: Claude OAuth uses
# ROTATING refresh tokens. Once the operator's CLI refreshes, any point-in-time
# copy holds a *stale* refresh token and can no longer self-refresh either — so a
# copy taken at lane launch is doomed on a long run (the access token AND the
# copy's refresh path both die). Running on a short timer (well under the
# access-token TTL) keeps the lane copy never more than one interval behind the
# operator's live credential.
#
# Idempotent + best-effort: copies only when the operator source differs from the
# lane copy; writes it 0600 owned by the lane user. A missing/unreadable operator
# credential is NOT an error (the operator may simply not be logged in) — exit 0
# and let the next tick try again. Runs as root (system oneshot): it must read
# the operator's 0600 ~/.claude/.credentials.json and write the lane copy with a
# chown, which a single non-root UID cannot do.
set -euo pipefail

OPERATOR_HOME=${STRIATUM_OPERATOR_HOME:-/home/halbritt}
LANE_USER=${STRIATUM_LANE_OS_USER:-striatum-lane}
LANE_HOME=$(getent passwd "$LANE_USER" | cut -d: -f6 || true)

if [[ -z "${LANE_HOME}" ]]; then
  echo "lane user '${LANE_USER}' has no home dir; nothing to resync" >&2
  exit 0
fi

SRC="${OPERATOR_HOME}/.claude/.credentials.json"
DST="${LANE_HOME}/.claude/.credentials.json"

if [[ ! -r "${SRC}" ]]; then
  echo "operator credential ${SRC} not readable; skipping (operator not logged in?)" >&2
  exit 0
fi

# Only copy when content actually differs — avoids needless churn every tick.
if [[ -f "${DST}" ]] && cmp -s "${SRC}" "${DST}"; then
  exit 0
fi

install -d -o "${LANE_USER}" -g "${LANE_USER}" -m 700 "${LANE_HOME}/.claude"
# Atomic replace with correct owner + 0600 mode in one shot.
install -o "${LANE_USER}" -g "${LANE_USER}" -m 600 "${SRC}" "${DST}"
echo "resynced ${SRC} -> ${DST} (owner ${LANE_USER}, 0600)"
