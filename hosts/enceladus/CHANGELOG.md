# Host changelog

## Wacom Center login autostart disabled (halbritt) — 2026-09-26

Owner request. Set `WCAutoStart` to `false` in the halbritt Wacom driver prefs,
stopping and restarting `WTabletServicePro` around the edit. The tablet driver
itself is unchanged. After restart, the driver's user processes came back but
`WacomCenterUI` did not. The `Saturn` profile still has `true`. See
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
