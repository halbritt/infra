#!/bin/bash
# Root phase of the imessage-vm guest bootstrap (macOS 15). Idempotent.
# Run from archon:  imessage-vm-guest bootstrap   (see README). stdin line 2 is
# the imessage account password (line 1 is consumed by sudo -S).
set -euo pipefail
U=imessage
BB_VER=1.9.9
BB_SHA256=9681e65f60214a6a95f3bd12b57bd4cc8ad6d8f58cd9c1d8811b2a4606ad7c04  # size 306050865, matches the GitHub asset; computed 2026-10-19
IFS= read -r PW

# SSH: keys only, this user only.
cat > /etc/ssh/sshd_config.d/100-imessage-vm.conf <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AllowUsers imessage
CONF
/usr/sbin/sshd -t

# The archon stop hook may shut the guest down without a password.
echo "$U ALL=(root) NOPASSWD: /sbin/shutdown -h now" > /etc/sudoers.d/imessage-vm-shutdown
chmod 0440 /etc/sudoers.d/imessage-vm-shutdown
visudo -cf /etc/sudoers.d/imessage-vm-shutdown

# Never sleep; restart after power loss.
pmset -a sleep 0 displaysleep 0 disksleep 0 standby 0 powernap 0 autopoweroff 0 hibernatemode 0 womp 0 autorestart 1 ttyskeepawake 1

# Security/config data updates stay automatic; macOS and App Store updates are manual (see README).
SU=/Library/Preferences/com.apple.SoftwareUpdate
defaults write $SU AutomaticCheckEnabled -bool true
defaults write $SU AutomaticDownload -bool false
defaults write $SU AutomaticallyInstallMacOSUpdates -bool false
defaults write $SU ConfigDataInstall -bool true
defaults write $SU CriticalUpdateInstall -bool true
defaults write /Library/Preferences/com.apple.commerce AutoUpdate -bool false

# Automatic login is set in System Settings > Users & Groups (sysadminctl
# -autologin fails with error 22 on 15.8.1). It needs FileVault off; archon's
# LUKS volume protects the disk image at rest.
if [[ "$(fdesetup status)" != "FileVault is Off." ]]; then
  echo "FileVault is on; automatic login is impossible" >&2
  exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# imessage-mcp and its Node.js were retired 2026-11-09 (missive replaced them).
# Remove them from older guests; also remove node's Full Disk Access entry in
# System Settings (TCC.db is SIP-protected, so this step cannot do it).
rm -rf /opt/imessage-mcp

# BlueBubbles server (Intel build), checksum-pinned and notarization-checked.
if [[ "$(defaults read /Applications/BlueBubbles.app/Contents/Info CFBundleShortVersionString 2>/dev/null)" != "$BB_VER" ]]; then
  dmg="$work/BlueBubbles-$BB_VER.dmg"
  curl -fsSL -o "$dmg" "https://github.com/BlueBubblesApp/bluebubbles-server/releases/download/v$BB_VER/BlueBubbles-$BB_VER.dmg"
  echo "$BB_SHA256  $dmg" | shasum -a 256 -c -
  mnt="$work/mnt"
  mkdir "$mnt"
  hdiutil attach -nobrowse -readonly -mountpoint "$mnt" "$dmg" >/dev/null
  rm -rf /Applications/BlueBubbles.app
  ditto "$mnt/BlueBubbles.app" /Applications/BlueBubbles.app
  hdiutil detach "$mnt" >/dev/null
  # Upstream 1.9.9 is Developer ID signed but not notarized, so spctl rejects it;
  # verify the signature and team ID of the fresh copy. Checked only here: the
  # running app writes files into its own bundle (cloudflared pidfile), which
  # breaks the seal afterwards.
  codesign --verify --deep --strict /Applications/BlueBubbles.app
  codesign -dv /Applications/BlueBubbles.app 2>&1 | grep -qx 'TeamIdentifier=WPV275H8W7'
  xattr -dr com.apple.quarantine /Applications/BlueBubbles.app 2>/dev/null || true
fi
# Session watchdog (BlueBubbles/Messages start and crash recovery).
install -d -o root -g wheel -m 0755 /opt/imessage-vm/bin
install -o root -g wheel -m 0755 /tmp/imessage-vm-guest/session-watchdog /opt/imessage-vm/bin/session-watchdog
echo "root bootstrap complete"
