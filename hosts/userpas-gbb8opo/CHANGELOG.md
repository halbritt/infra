# Host changelog

## 2026-09-15

Recorded the Windows host after the owner supplied its LAN SSH endpoint and
requested Tailscale setup. Initial state: administrator SSH works, Tailscale absent.

Installed Tailscale 1.102.4 with verified vendor signature, unattended mode, and
automatic service startup. Enrolled at `100.121.157.17`; direct ping and SSH work.
Added proximal's existing ED25519 public key to the Windows administrator key
file, preserving prior entries. Verified passwordless LAN and tailnet SSH.

The owner expanded scope to startup cleanup and software updates, explicitly
retired the Wacom tablet, and chose manual startup for optional helpers.
Uninstalled Wacom (vendor success/reboot-required code 2); made seven optional
services manual, disabled two vendor scheduled launches, and removed five login
launches. Saved rollback state on Windows and documented retained components.
Samsung migration cannot stop until reboot; no forced termination was attempted.

Checked FORScan explicitly: installed 2.3.71 matches the official current release.
Started a SYSTEM Windows Update task for six offered software updates. Application
upgrade inventory succeeds in an interactive scheduled task; the same WinGet
source operation failed in the OpenSSH logon context.

All six Windows updates subsequently reported success, with a restart required.
The cumulative-update servicing log briefly reported a missing `prjflt.sys`
component but completed successfully; no separate repair was necessary. Removed
the completed Windows Update task and started the selected application upgrades.
Application updates and post-reboot verification remain in progress.
