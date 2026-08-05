#!/usr/bin/env bash
# pg-repack-bloated.sh — monthly off-peak bloat reclaim for striatum_daemon's
# heartbeat/chain tables. Online pg_repack only, with --no-kill-backend so it
# SKIPS (and retries next run) rather than ever disrupting the daemon on its
# hottest tables. Idempotent: a table is repacked only if it exceeds THRESHOLD_MB.
#
# Canonical copy: proximal/postgres/maintenance/. Installed at /usr/local/bin/.
# Runs as the postgres superuser (peer auth on the local socket) via a systemd
# timer (pg-repack-bloated.timer). Rationale + first run:
# reports/REPACK_supervisor_tables_2026-06-18.md.
set -uo pipefail

DB=striatum_daemon
PG_REPACK=/usr/bin/pg_repack
PSQL=/usr/bin/psql
THRESHOLD_MB=16                       # healthy is ~2 MB; bloated run was 24-255 MB
THRESHOLD_BYTES=$(( THRESHOLD_MB * 1024 * 1024 ))
WAIT_TIMEOUT=30                       # seconds pg_repack waits for its brief locks

# Known heartbeat/chain churn tables. This job NEVER auto-discovers — add tables
# here deliberately, after vetting them the way the 2026-06-18 run did.
TABLES=(
  striatumd.process_supervisor_pointers
  striatumd.daemon_supervisors
  striatumd.process_supervisors
  striatumd.repo_event_chain_heads
)

log() { printf '%s pg-repack-bloated: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

log "start (db=$DB threshold=${THRESHOLD_MB}MB)"
active=$("$PSQL" -d "$DB" -At -c \
  "SELECT count(*) FROM pg_stat_activity WHERE datname='$DB' AND state='active' AND pid<>pg_backend_pid();" \
  2>/dev/null || echo '?')
log "active backends now: $active (informational; --no-kill-backend keeps this safe regardless)"

repacked=0; skipped=0; failed=0
for t in "${TABLES[@]}"; do
  bytes=$("$PSQL" -d "$DB" -At -c "SELECT pg_total_relation_size('$t');" 2>/dev/null || echo '')
  if [[ -z "$bytes" ]]; then
    log "WARN $t: could not read size (renamed/dropped?) — skip"; failed=$((failed+1)); continue
  fi
  mb=$(( bytes / 1024 / 1024 ))
  if (( bytes > THRESHOLD_BYTES )); then
    log "$t: ${mb}MB > ${THRESHOLD_MB}MB — repacking"
    if "$PG_REPACK" -d "$DB" -t "$t" --no-kill-backend --wait-timeout="$WAIT_TIMEOUT" 2>&1; then
      after=$("$PSQL" -d "$DB" -At -c "SELECT pg_total_relation_size('$t');" 2>/dev/null || echo 0)
      log "$t: repacked ${mb}MB -> $(( after / 1024 / 1024 ))MB"; repacked=$((repacked+1))
    else
      log "WARN $t: pg_repack failed/skipped (likely lock wait-timeout under load) — retry next run"
      failed=$((failed+1))
    fi
  else
    log "$t: ${mb}MB <= ${THRESHOLD_MB}MB — ok, skip"; skipped=$((skipped+1))
  fi
done

log "done (repacked=$repacked skipped=$skipped failed=$failed)"
exit 0
