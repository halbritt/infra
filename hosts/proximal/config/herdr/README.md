# Herdr restart recovery

Herdr 0.9.5 saves the default session at `~/.config/herdr/session.json`.
It restores layout and eligible native conversations after a client attaches.
Conversation restoration does not restart interrupted commands or background jobs.

## 2026-11-09 maintenance checkpoint

The owner requested saving all agent sessions before a possible reboot to enable
firmware-disabled SATA ports. No reboot is part of this preparation.
The private recovery bundle is `~/.local/state/infra-restart-20261109/`.
It holds the original layout, per-pane acknowledgments and Cairn handoff references,
an exact conversation/profile/launch manifest, and a corrected `session.json.restore`.
Do not commit the bundle or authentication files.

The original layout has 7 workspaces, 12 tabs and 25 agent panes. Twelve Codex
panes lack native session references. Bare Claude resume commands lose account
profiles and Cairn channel flags. One Claude pane has a deleted working directory.
The prepared snapshot uses Herdr's `agent_resume` argv field to retain exact IDs,
profile environment and launch flags, and gives the deleted-worktree pane the
existing primary Cairn checkout. It does not overwrite the running session.

Codex uses the installed Cairn launcher with a fresh private app-server socket.
Do not save or reuse its old `--remote` socket. Do not add `--yolo` to remote
resume: Codex rejects permission overrides for that operation. Saved thread
permissions and profile configuration must be checked before the reboot and
effective permissions checked again after restoration.

`restore-herdr.py` is canonical here; install a copy as executable
`<bundle>/restore-herdr`. It checks snapshot hashes, transcripts, directories and
pause receipts. Run `<bundle>/restore-herdr --check` before reboot. After reboot,
from a terminal **outside Herdr**, before starting the default session, run:

```sh
~/.local/state/infra-restart-20261109/restore-herdr
```

The helper refuses the preparation boot, a running default session, or an already
used bundle. It preserves the existing layout, atomically installs the corrected
snapshot, and attaches Herdr. If attach fails after installation, run `herdr`
again; do not reinstall the old snapshot over newer session state.

After attach, inspect all panes for the expected conversation, account, model,
permissions and Cairn connectivity. Resolve any launch errors before resuming
work. Agents remain under the owner's maintenance pause until explicitly resumed.
Native wakeups and independent system services are separate from conversation
restore; the bundle records exceptions. Keep held branches and checkpoints intact.

Sources checked against the installed version:
[session persistence](https://github.com/herdrdev/herdr/blob/v0.9.5/docs/next/website/src/content/docs/session-state.mdx),
[reported resume commands](https://github.com/herdrdev/herdr/blob/v0.9.5/docs/next/website/src/content/docs/add-herdr-support.mdx),
and `src/persist/{snapshot,restore}.rs` in the same tag.
