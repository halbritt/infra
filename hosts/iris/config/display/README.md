# Iris DSI touch display

## Configuration

[`config.txt`](config.txt) records the installed `/boot/firmware/config.txt`
captured after repair on 2026-11-11. It was not edited during the repair.
Review this host-specific copy before any future installation; it includes
boot settings beyond the display.

The effective settings retain `display_auto_detect=1`, `dtoverlay=vc4-kms-v3d`,
and `disable_fw_kms_setup=1`. Firmware automatically loads
`vc4-kms-dsi-ili79600-10-1inch` for the attached panel. No explicit panel overlay
is needed in `config.txt` for the verified setup.

The desktop uses LightDM and labwc. The display appeared as DSI-2 with normal
transform and scale 1.0 after repair. DRM card numbers can change across boots.

## Missing display: 2026-11-11

Before repair, labwc exposed only a headless NOOP-1 output. Both HDMI connectors
were disconnected; there was no DSI connector or backlight device, and both
DSI device-tree nodes were disabled. The required panel overlay was already
installed, and display auto-detection was enabled.

The running EEPROM was older than the installed default release:

| State | Release | Version |
|---|---|---|
| Before repair | 2025-05-08 | `69471177ba7e4cb7597cb2496f2a0b23f19c1113` |
| After repair | 2026-09-25 | `1accd6659983613cd104973ce2432da14f1a7682` |

With the owner's authorization, ran on Iris:

```sh
sudo rpi-eeprom-update -a
sudo reboot
```

The installed image came from
`/usr/lib/firmware/raspberrypi/bootloader-2712/default/pieeprom-2026-09-25.bin`.
SSH returned after approximately two minutes. No package upgrade, manual
overlay, or physical cable change was part of this repair.

Post-reboot observations:

| Check | Result |
|---|---|
| `vcgencmd bootloader_version` | 2026-09-25, version above |
| `sudo rpi-eeprom-update` | Bootloader up to date against installed default release |
| `sudo vclog --msg` | Loaded overlay `vc4-kms-dsi-ili79600-10-1inch` |
| DRM | `card0-DSI-2` connected and enabled |
| `wlr-randr` | DSI-2 enabled, 1200×1920, 60.018002 Hz, preferred/current |
| Backlight | `panel_backlight@1`, brightness 15/31, `bl_power=0` |
| `/proc/bus/input/devices` | `11-0041 ili_v3`, handlers `mouse0 event5` |
| `systemctl --failed --no-legend` | No failed services |
| `vcgencmd get_throttled` | `0x0` |

The firmware update restored detection and desktop output. These are software
checks; visible image quality and physical touch response were not independently
tested.

## Recheck

Run as `halbritt` on Iris while its desktop session is active:

```sh
vcgencmd bootloader_version
sudo rpi-eeprom-update
XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 wlr-randr
cat /sys/class/drm/card*-DSI-*/status
cat /sys/class/drm/card*-DSI-*/enabled
cat /proc/bus/input/devices
sudo vclog --msg
```

If DSI disappears again, compare the running EEPROM with the installed release
and inspect firmware logs before forcing an overlay. For physical installation
and power checks, use the [Raspberry Pi Touch Display 2 documentation](https://www.raspberrypi.com/documentation/accessories/touch-display-2.html).
Disconnect power before adjusting ribbon or GPIO connections.
