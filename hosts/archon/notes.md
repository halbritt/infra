# archon notes

## Initial record and live observation — 2026-09-26

Recorded at the owner's request. The observed system was Omarchy `4.0.3-1` on
Arch kernel `7.2.3-arch1-3`, uptime about 1 day. The user `halbritt` had a
graphical session on seat0/tty1. `sshd` and `tailscaled` were active. The
Omarchy default terminal is `foot` (the only terminal binary installed). Config
directories for ghostty, alacritty, and kitty also exist, but those terminals
are not installed.

The proximal `archon-lan` SSH alias pointed at `192.168.1.167`; the host
reported `192.168.1.179` on `wlo1`. The alias was updated to match.

## TPM root unlock prepared — 2026-10-19

Owner chose TPM2 auto-unlock (passphrase kept as fallback) so archon and the
imessage-vm survive unattended reboots. The initramfs moved to systemd hooks
via a drop-in; cmdline carries both `cryptdevice=` and `rd.luks.*`. Snapper
snapshot 3 is the boot fallback. TPM enrollment and the first reboot need the
owner at the keyboard. See [tpm-unlock](config/tpm-unlock/README.md).

## Hyprland crash left a lock with no lock screen — 2026-10-19/20

At 20:14 Hyprland (running since Sep 25, before the Sep 26 update) segfaulted
in libaquamarine. start-hyprland restarted it as `Hyprland --safe-mode
--locked`. Quickshell (Omarchy's bar, idle monitor and lock screen) died with
it, so the session was locked with no unlock UI.

Recovery without a reboot, from SSH with
`HYPRLAND_INSTANCE_SIGNATURE=$(ls -t /run/user/1000/hypr | head -1)`:
- `hyprctl eval 'hl.config({ misc = { allow_session_lock_restore = true } })'`
  (safe mode skips Omarchy's config, which normally sets it);
- `hyprctl eval 'hl.exec_cmd("omarchy-launch-shell")'`.

The shell logs `lock-stranded: recovering` and shows the password prompt.
Hyprland 0.56 has a Lua config: `hyprctl keyword` and string `dispatch` are
rejected. The owner then rebooted (see tpm-unlock README).
