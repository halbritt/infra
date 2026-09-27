# Tailscale

The Windows client (1.98.9 on 2026-09-26) runs as the `Tailscale` service
(Automatic). A `Tailscale.lnk` in the all-users Startup folder starts the tray UI.

## Unattended mode (required)

By default, the Windows client connects only while the Windows user who
authenticated it is logged in. It stays offline at the lock screen and while
another user, such as `Saturn`, is logged in. That makes the host unreachable
from proximal. Unattended mode (`ForceDaemon`) keeps it connected from boot for
every user.

```powershell
tailscale set --unattended          # enabled 2026-09-26
tailscale debug prefs | Select-String ForceDaemon   # expect "ForceDaemon": true
```

The same setting is in the tray menu: Preferences → Run unattended.
Rollback: `tailscale set --unattended=false`.

Still to verify: after the next owner-approved reboot, check that
`tailscale status` on proximal shows enceladus online before anyone logs in.
