# Iris changelog

## 2026-11-11

- Discovered `iris.local` through mDNS and recorded the Raspberry Pi 5 hardware,
  Wi-Fi identity, OS, and local touch display in infra.
- Owner enabled passwordless sudo for `halbritt` to permit the requested repair.
- Updated EEPROM from 2025-05-08 to the installed default release 2026-09-25
  using `sudo rpi-eeprom-update -a`, then rebooted.
- Verified automatic loading of the 10-inch panel overlay, DSI-2 enabled at
  1200×1920 / 60.018 Hz, backlight power, and registration of the touch input.
  No manual overlay or desktop configuration change was required.
- Installed the Fernside board kiosk from `halbritt/agent-board` commit `480fd0f`
  with `kiosk/deploy.sh`: user unit `agent-board-kiosk.service`, a Wayland
  session named `agent-board`, and LightDM autologin into that session. The
  stock desktop session was not edited. See `config/kiosk/README.md`.
- Rebooted to verify: Iris returned showing the board with no desktop panel.
- Observed the Wi-Fi address change from 192.168.1.216 to 192.168.1.219 during
  the day. There is still no DHCP reservation; `iris.local` resolved throughout.
