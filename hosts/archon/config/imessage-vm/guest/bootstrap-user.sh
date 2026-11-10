#!/bin/bash
# User phase of the imessage-vm guest bootstrap, run as imessage. Idempotent.
# stdin line 1: account password (screen lock).
set -euo pipefail
IFS= read -r PW
umask 077
mkdir -p ~/Library/LaunchAgents ~/Library/Logs

# No screen saver or lock in the unattended session.
defaults -currentHost write com.apple.screensaver idleTime -int 0
sysadminctl -screenLock off -password "$PW" 2>&1 | grep -v -i password || true

# imessage-mcp was retired 2026-11-09; remove it from older guests.
launchctl bootout "gui/$(id -u)/org.halbritt.imessage-mcp" 2>/dev/null || true
rm -f ~/Library/LaunchAgents/org.halbritt.imessage-mcp.plist ~/Library/Logs/imessage-mcp.log
rm -rf ~/.config/imessage-mcp
wd=~/Library/LaunchAgents/org.halbritt.imessage-vm-watchdog.plist
install -m 0644 /tmp/imessage-vm-guest/launchd/org.halbritt.imessage-vm-watchdog.plist "$wd"
plutil -lint "$wd"
launchctl bootout "gui/$(id -u)/org.halbritt.imessage-vm-watchdog" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$wd"
echo "user bootstrap complete"
