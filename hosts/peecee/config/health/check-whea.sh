#!/usr/bin/env bash
# Periodic WHEA-error probe for peecee, run from proximal via cron.
#
# Context: on 2026-07-20 peecee bugchecked (0x1E, nvlddmkm.sys) after a ~40 min
# storm of WHEA ID 17 corrected PCIe errors (root ports 0:1D.4 and 0:06.0).
# This probe counts WHEA-Logger events since the current boot so a recurrence
# is caught while it is still "corrected", before the next BSOD.
#
# Log: ~/.local/state/peecee-whea/whea.log — one line per run:
#   <proximal-ts> boot=<peecee-boot-time> whea_since_boot=<n>
#   <proximal-ts> UNREACHABLE
# A non-zero count also writes an ALERT line and leaves a marker file so a
# human (or agent) checking the log can see it at a glance.

set -u
STATE_DIR="$HOME/.local/state/peecee-whea"
LOG="$STATE_DIR/whea.log"
mkdir -p "$STATE_DIR"

PS='
$b=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime
$n=(Get-WinEvent -FilterHashtable @{LogName="System"; ProviderName="Microsoft-Windows-WHEA-Logger"; StartTime=$b} -ErrorAction SilentlyContinue | Measure-Object).Count
"boot=$($b.ToString("s")) whea_since_boot=$n"
'
ENC=$(printf '%s' "$PS" | iconv -f UTF-8 -t UTF-16LE | base64 -w0)

TS=$(date -Is)
OUT=$(timeout 60 ssh -o BatchMode=yes -o ConnectTimeout=10 peecee \
        "powershell -NoProfile -EncodedCommand $ENC" 2>/dev/null \
      | tr -d '\r' | grep '^boot=')

if [[ -z "$OUT" ]]; then
    echo "$TS UNREACHABLE" >> "$LOG"
    exit 0
fi

echo "$TS $OUT" >> "$LOG"

# A few corrected errors fire at every boot on root port 0:1D.4 (NVMe link) —
# benign so far. Alert only when the count GROWS within the same boot, i.e.
# errors are occurring at runtime like in the pre-BSOD storm of 2026-07-20.
COUNT=${OUT##*whea_since_boot=}
BOOT=${OUT#boot=}; BOOT=${BOOT%% *}
LAST_FILE="$STATE_DIR/last"
if [[ "$COUNT" =~ ^[0-9]+$ ]]; then
    { read -r LAST_BOOT LAST_COUNT < "$LAST_FILE"; } 2>/dev/null || LAST_BOOT=""
    if [[ "$BOOT" == "$LAST_BOOT" ]] && (( COUNT > LAST_COUNT )); then
        echo "$TS ALERT whea count grew within boot ($LAST_COUNT -> $COUNT): $OUT" >> "$LOG"
        echo "$TS $OUT" > "$STATE_DIR/ALERT"
    fi
    echo "$BOOT $COUNT" > "$LAST_FILE"
fi
