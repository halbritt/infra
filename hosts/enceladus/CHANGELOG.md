# Host changelog

## Wacom Center login autostart disabled (Saturn) — 2026-09-26

Owner request: Saturn doesn't use Wacom Center. Set `WCAutoStart` to `false` in
`C:\Users\Saturn\AppData\Roaming\WTablet\Wacom_Tablet.{dat,bak}` while
only `halbritt` was logged in. Backups are under
`C:\ProgramData\Infra\wacom-prefs-before-20260926\Saturn\`. Not yet checked
at Saturn's next login.

## Wacom Center login autostart disabled (halbritt) — 2026-09-26

Owner request. Set `WCAutoStart` to `false` in the halbritt Wacom driver prefs,
stopping and restarting `WTabletServicePro` around the edit. The tablet driver
itself is unchanged. After restart, the driver's user processes came back but
`WacomCenterUI` did not. See
[config/startup](config/startup/README.md).

## Tailscale unattended mode — 2026-09-26

After a reboot, the owner logged into the child's account first, and Tailscale
never connected. The Windows client ties the connection to the Windows user who
authenticated it unless unattended mode is on. Ran `tailscale set --unattended`
(client 1.98.9). Verified `ForceDaemon: true`, `WantRunning: true`, and service
`Tailscale` Running/Automatic. Pre-login connection is not yet verified by a
reboot. See [config/tailscale](config/tailscale/README.md).

## Initial record — 2026-09-26

Added host partition from a live SSH probe.
