# Power configuration for truck-pc

The owner requested disabling sleep on AC power on 2026-09-16.

## Rationale

`truck-pc` (Dell Latitude 7280) operates as an unattended endpoint reachable via
Tailscale and OpenSSH. The default Windows Balanced power scheme puts the system
to sleep after 30 minutes of idle inactivity on AC power (`STANDBYIDLE` = 1800s),
severing network connectivity and rendering the machine unreachable for remote
administration.

The power policy:
- **AC power (plugged in):** Sleep disabled (`standby-timeout-ac` = 0). System remains
  awake and reachable. Display timeout remains managed normally.
- **DC power (battery):** Sleep timeout retained at 15 minutes (`standby-timeout-dc` = 15)
  to prevent battery exhaustion when unplugged.

## Apply

Ensure `truck-pc` is awake and reachable over SSH, then run [set-power.ps1](set-power.ps1)
from an elevated PowerShell session:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\ProgramData\Infra\set-power.ps1
```

Or from proximal:

```bash
scp hosts/truck-pc/config/power/set-power.ps1 truck-pc:'C:/ProgramData/Infra/set-power.ps1'
ssh truck-pc 'powershell.exe -ExecutionPolicy Bypass -File C:\ProgramData\Infra\set-power.ps1'
```

The script backs up prior power settings to `C:\ProgramData\Infra\power-before-20260916.json`,
disables AC standby and hibernate timeouts, and verifies the resulting configuration.

## Verify

```bash
ssh truck-pc 'powercfg /q SCHEME_CURRENT SUB_SLEEP STANDBYIDLE'
```

The `Current AC Power Setting Index` must be `0x00000000` (disabled), and `Current DC Power Setting Index`
must be `0x00000384` (900 seconds / 15 minutes).

## Rollback

To restore the original 30-minute AC sleep timeout:

```bash
ssh truck-pc 'powercfg /change standby-timeout-ac 30'
```
