# Host changelog

## Requested identity change — 2026-09-15

Owner selected computer name `truck-pc` and login `halbritt`, with display name
Heath Albritton. Renamed the repository host directory and prepared the live
recipe. Both LAN and Tailscale access were unavailable; live changes are pending.

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
Nine application installers returned success. Windows App Runtime 1.7 stalled in
the deployment queue; paused its clients and preserved two pending runtime
upgrades for after restart. Reapplied the optional-helper startup policy after
the upgrades. Added resume support and corrected rollback to restore Cowork from
its own saved state. Restart, remaining runtimes, ESU assessment, and post-boot
performance/access verification remain pending.

The owner approved restart after saving work. Completed two restarts: the first
exposed September 2026 OS/.NET/recovery updates, and the second booted build
19045.7725. All three update installers reported success. Both remaining runtime
installers then returned exit 0 with current x86/x64 framework registrations;
all 11 selected application upgrades are complete. SSH/Tailscale returned before
login, seven optional services stayed stopped/manual, and Defender/firewall
remained enabled. Logged-out CPU averaged 2.12% over 30 samples.

Found a separate recovery issue: KB5127070 reports success and is re-offered,
while WinRE is disabled and its image remains build 19041.6094. The 535 MB recovery
partition has only 22 MB free, and its recorded offset is stale. Recorded the
partition layout and one retry result for a separate recovery repair; made no
partition or boot-configuration changes. Removed temporary maintenance tasks.
