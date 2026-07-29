#!/usr/bin/env bash
# Sweep every href on the tailnet index and report its HTTP status.
#
# The index is a hand-maintained list of service URLs, so it goes stale silently
# whenever a service moves port, changes mount prefix, or is retired — exactly
# how the BinKeeper cards broke (2026-07-29). Run this after any service move,
# and before trusting the "last checked" line in the footer.
#
# Codes: 2xx/3xx reachable. 502 = tailscale-serve mapping survives but the
# origin is down (usually a retired service). 000 = curl could not connect.
set -uo pipefail

INDEX="${1:-$(dirname "$0")/../site/index.html}"
fail=0

while read -r url; do
  code=$(curl -sk -o /dev/null --max-time 10 -w '%{http_code}' "$url" 2>/dev/null || echo 000)
  case "$code" in
    2*|3*) status="ok" ;;
    *)     status="DEAD"; fail=1 ;;
  esac
  printf '%-4s %-5s %s\n' "$code" "$status" "$url"
done < <(grep -o 'href="[^"]*"' "$INDEX" | sed 's/href="//;s/"//')

exit "$fail"
