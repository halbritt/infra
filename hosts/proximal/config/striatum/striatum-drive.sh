#!/usr/bin/env bash
# striatum-drive — canonical KEYED operator entrypoint for driving the
# striatum-next fleet by hand (or from any ad-hoc/agent shell).
#
# Why this exists: the OpenRouter judgment lanes (backends/glm, backends/kimi)
# resolve their bearer from $OPENROUTER_API_KEY. That variable is injected into
# the striatum-wake-*.service units via the openrouter-env.conf EnvironmentFile
# drop-in, so TIMER- and wake-driven drives carry it. A drive started any other
# way — a bare `striatum ... drive`, or `systemd-run --user --scope ... drive` —
# does NOT, so every garden lane it dispatches (and every adapter_wake drive that
# lane's supervisor spawns, which inherits this environment) crashes
# `OPENROUTER_API_KEY named but unset` (exit 2) and drains "missing required
# outputs: [review-ledger]", exhausting the review redispatch budget.
#
# This wrapper closes that gap the same way the wake units do — by REFERENCE,
# not by copying the secret: it sources the one mode-600 key file at spawn and
# execs the real driver. The key value never lands in a second file, in the
# systemd environment, in git, or in a ledger record.
#
# Use this (not a bare `striatum drive`) for any hand-triggered fleet drive.
set -euo pipefail

KEY_ENV="$HOME/.config/striatum/openrouter.env"
REPO="$HOME/git/striatum-next"

if [[ -r "$KEY_ENV" ]]; then
  set -a; . "$KEY_ENV"; set +a
else
  echo "striatum-drive: warning: $KEY_ENV not readable; garden lanes will fail unset" >&2
fi

exec "$REPO/bin/striatum" \
  -repo    "$REPO" \
  -data-home "$HOME/.local/share" \
  -catalog "$REPO/catalog" \
  -backends "$REPO/backends" \
  -policy  "$REPO/policy/driver.yaml" \
  -backlog "$REPO/policy/backlog.yaml" \
  -checks  "$REPO/policy/checks/repository.json" \
  drive -trigger operator "$@"
