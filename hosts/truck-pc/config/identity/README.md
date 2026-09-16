# Host and account identity

The owner requested these names on 2026-09-15:

| Identity | Requested value |
|---|---|
| Windows computer and Tailscale node | `truck-pc` |
| Local account login | `halbritt` |
| Account display name | Heath Albritton |

Deployment is pending: the laptop was offline on both its LAN and Tailscale
addresses when the request arrived. The repository resource is now `truck-pc`;
`machine.yaml` retains the last observed Windows hostname and DNS name until
live verification. The previous resource path was `hosts/userpas-gbb8opo/`.
The recipe has been reviewed but has not been parsed or executed on Windows yet;
local PowerShell is unavailable. Perform the Windows parser check before running.

## Apply

Read the live computer name, local accounts, service logon accounts, scheduled
task principals, and logged-in sessions before applying. Confirm the existing
`User` account's SID against the recipe and check that `halbritt` is not already
another account. Check the tailnet for a conflicting `truck-pc` node.

Copy [rename.ps1](rename.ps1) to `C:\ProgramData\Infra\rename.ps1`, then run it
from elevated 64-bit PowerShell with process-local `-ExecutionPolicy Bypass`.
The recipe preserves a non-secret identity snapshot, retains the account SID,
and updates Windows and Tailscale names. The Windows hostname requires restart.

Verify a fresh SSH connection as `halbritt@100.121.157.17` before restarting.
Coordinate with any logged-in users before closing sessions. After restart,
verify `hostname`, `whoami`, the account's full name and SID, administrator
membership, SSH and Tailscale services, and DNS access at
`truck-pc.tail0ecc2e.ts.net`. Update current host records after verification.

The profile directory remains `C:\Users\User`; renaming a login does not require
moving its profile. Keep existing application paths and SID-based permissions.
Do not rename the profile folder or alter `ProfileImagePath` as part of this work.

To undo, use the saved identity snapshot and the same rename commands with the
original names; the Windows hostname rollback also requires a restart. Preserve
the existing administrator public key throughout.

References: Microsoft's [Rename-LocalUser](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.localaccounts/rename-localuser?view=powershell-5.1)
and [Rename-Computer](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/rename-computer?view=powershell-5.1).
