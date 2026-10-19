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
