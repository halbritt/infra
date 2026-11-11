# iris

Raspberry Pi 5 Model B Rev 1.0 with 8 GiB RAM and a 10-inch Touch Display 2
connected by DSI ribbon. The panel was identified by firmware loading
`vc4-kms-dsi-ili79600-10-1inch`; the owner initially described it as 10.2 inches.

Iris is dedicated to the Fernside board: since 2026-11-11 it logs in to a kiosk
session that shows the board served by proximal.

Recorded on 2026-11-11 from live SSH inspection. Raspberry Pi OS uses Debian
13.7 (trixie), kernel `6.18.50+rpt-rpi-2712`, and LightDM with labwc.
The 29.7 GiB microSD has a 512 MiB FAT boot partition mounted at
`/boot/firmware` and a 29.2 GiB ext4 root partition.

Connect from proximal with `ssh halbritt@iris.local`. Wi-Fi `wlan0` was observed
at `192.168.1.216` and later the same day at `192.168.1.219`, MAC `2c:cf:67:96:b9:50`; Ethernet `eth0` was down.
The owner enabled passwordless sudo for `halbritt` before the display repair.

- [Machine metadata](machine.yaml)
- [Operational notes](notes.md)
- [Changelog](CHANGELOG.md)
- [Display configuration and repair](config/display/README.md)
- [Board kiosk](config/kiosk/README.md)

After the EEPROM update and reboot, the desktop reported DSI-2 enabled at
1200×1920 and 60.018 Hz, with a powered backlight and registered touch input.
Image quality and physical touch response were not observed over SSH.
