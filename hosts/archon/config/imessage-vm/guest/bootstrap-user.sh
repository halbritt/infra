#!/bin/bash
# User phase of the imessage-vm guest bootstrap, run as imessage. Idempotent.
# stdin line 1: account password (screen lock), line 2: imessage-mcp token.
set -euo pipefail
IFS= read -r PW
IFS= read -r TOKEN
umask 077
mkdir -p ~/.config/imessage-mcp ~/Library/LaunchAgents ~/Library/Logs
printf '%s' "$TOKEN" > ~/.config/imessage-mcp/token
chmod 0600 ~/.config/imessage-mcp/token

# No screen saver or lock in the unattended session.
defaults -currentHost write com.apple.screensaver idleTime -int 0
sysadminctl -screenLock off -password "$PW" 2>&1 | grep -v -i password || true

plist=~/Library/LaunchAgents/org.halbritt.imessage-mcp.plist
install -m 0644 /tmp/imessage-vm-guest/launchd/org.halbritt.imessage-mcp.plist "$plist"
plutil -lint "$plist"
launchctl bootout "gui/$(id -u)/org.halbritt.imessage-mcp" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$plist"
wd=~/Library/LaunchAgents/org.halbritt.imessage-vm-watchdog.plist
install -m 0644 /tmp/imessage-vm-guest/launchd/org.halbritt.imessage-vm-watchdog.plist "$wd"
plutil -lint "$wd"
launchctl bootout "gui/$(id -u)/org.halbritt.imessage-vm-watchdog" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$wd"
echo "user bootstrap complete"
