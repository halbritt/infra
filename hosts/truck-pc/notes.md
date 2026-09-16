# Host notes

## Initial observation — 2026-09-15

The owner requested Tailscale setup over the newly enabled Windows OpenSSH server.
SSH to `User@192.168.1.116` reported hostname `USERPAS-GBB8OPO`, Windows 10 Pro
build 19045, 64-bit, and an elevated administrator session. `sshd` was running
with automatic startup. No Tailscale service or default-path executable existed.

The resource name follows the observed hostname; no Windows rename was requested.
The supplied SSH password remains outside Git on the operator host.

## Identity change and power diagnosis — 2026-09-16

The owner requested `truck-pc` for the computer, `halbritt` for the existing `User`
login, and Heath Albritton for its display name.

### Power and sleep diagnosis
On 2026-09-16 when the laptop reconnected, inspection of Windows power/shutdown
event logs confirmed the earlier unreachable state was standard idle sleep, not a
hardware fault or crash:
- Active power plan is Balanced with 30-minute idle sleep on AC (`STANDBYIDLE` 1800s).
- Event logs show clean sleep entry (Kernel-Power Event 42) at 2026-09-15 18:31:16,
  exactly 30 minutes after post-update boot (18:00:42).
- Zero unexpected shutdowns (Event 6008) and zero Kernel-Power crash events (Event 41)
  in the 7-day log history.
- The system resumed normally from low power (Event 107 / Power-Troubleshooter Event 1)
  at 2026-09-16 11:18:59 on console activity.

### Live application and verification
- Copied canonical recipe `config/identity/rename.ps1` to `C:\ProgramData\Infra\rename.ps1`
  after Windows AST parser check passed with 0 errors.
- Executed `rename.ps1`: saved non-secret identity snapshot to
  `C:\ProgramData\Infra\identity-before-20260915.json`, staged computer rename `truck-pc`,
  updated Tailscale node name to `truck-pc`, and renamed local user `User` to `halbritt`
  (display name Heath Albritton).
- Account SID `S-1-5-21-1644079127-1291031853-2162120719-1002`, profile `C:\Users\User`,
  files, permissions, and administrator membership were preserved.
- Verified key-authenticated SSH as `halbritt@100.121.157.17` prior to restart.
- Initiated reboot and verified:
  - Hostname is `truck-pc`.
  - SSH login is `halbritt` with full name `Heath Albritton`.
  - Both `sshd` and `Tailscale` returned running automatically before login.
  - Tailscale DNS `truck-pc.tail0ecc2e.ts.net` is active and reachable over SSH.

### SSH key pair installation
Installed owner's ED25519 SSH key pair from proximal `~/.ssh/` to `C:\Users\User\.ssh/`
with strict ACLs restricted to `halbritt`, `SYSTEM`, and `Administrators`:
- Private key `id_ed25519` and public key `id_ed25519.pub` placed in `C:\Users\User\.ssh/`.
- `authorized_keys` and `C:\ProgramData\ssh\administrators_authorized_keys` updated.
- Proximal `~/.ssh/authorized_keys` updated and outgoing SSH from `truck-pc` to
  `proximal` verified with key authentication.
- Client alias configured in `~/.ssh/config.d/truck-pc` on proximal.

### Power policy: disable sleep on AC
The owner requested disabling sleep on AC power on 2026-09-16 to keep `truck-pc`
consistently reachable for remote SSH and Tailscale administration. Prepared the
`config/power/` subsystem with recipe `set-power.ps1` (`standby-timeout-ac 0` and
`hibernate-timeout-ac 0`, retaining 15-minute DC battery sleep). When the request
arrived, the laptop had returned to idle sleep ~30 minutes after prior maintenance;
deployment will be applied and verified as soon as the machine is woken.
