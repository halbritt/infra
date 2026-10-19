# imessage-vm (archon)

Always-on macOS Sequoia guest on archon for iMessage, BlueBubbles (Windows
access), and read-only imessage-mcp (agent access). **Deployment in progress
(2026-10-19)**; the full runbook replaces this note when verification is done.

- Host side: plain QEMU/KVM under `imessage-vm.service` (user `imsgvm`), state in
  the btrfs subvolume `/var/lib/imessage-vm`. Install with `sudo ./install.sh`.
- Boot disk: OpenCore 1.0.8 built by `bin/imessage-vm-build-boot` from
  `upstream.lock`; config rendered by `opencore/render-config.py`.
- Guest side: `guest/` (bootstrap scripts and LaunchAgent).
