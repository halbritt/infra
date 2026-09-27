# Startup

## Inventory — 2026-09-26

- All-users Startup folder: `Tailscale.lnk` (tray UI; the connection itself is
  the service).
- No Wacom entries in the Run keys, StartupApproved, the Startup folders,
  scheduled tasks, or AppX packages.

## Wacom Center

The Wacom driver launches Wacom Center itself, so no Windows startup entry
exists for it. Launch chain: service `WTabletServicePro` (Automatic, session 0)
→ `Wacom_TabletUser.exe` (the user's session) → `WacomCenterUI.exe`. The switch
is the per-user driver preference `WCAutoStart` in
`%APPDATA%\WTablet\Wacom_Tablet.dat` (plain UTF-8 XML, no BOM; `.bak` is its
twin). Wacom Center's own settings UI writes the same value.

The driver writes its in-memory prefs back to disk, which would overwrite a
file edit made while it runs. Edit the file only with the driver stopped:

```powershell
Stop-Service WTabletServicePro -Force
Get-Process Wacom_*,WacomHost,WacomCenterUI -ErrorAction SilentlyContinue | Stop-Process -Force
# in Wacom_Tablet.dat and Wacom_Tablet.bak:
#   <WCAutoStart type="bool">true</WCAutoStart> -> false
Start-Service WTabletServicePro
```

State on 2026-09-26: `false` for both `halbritt` and `Saturn` (owner request;
Saturn doesn't use Wacom Center). Saturn was edited while logged out, when no
driver session holds the prefs, so no service restart was needed; the files keep
their inherited ACL (Saturn FullControl). Pre-change copies are in
`C:\ProgramData\Infra\wacom-prefs-before-20260926\` (the `Saturn\` subfolder
holds that profile's files). Rollback: copy them back
using the same stop/start procedure, or turn the option back on in Wacom Center.
Do not disable `WTabletServicePro`, because pen input needs it.
