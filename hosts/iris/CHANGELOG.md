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

## 2026-11-13

- Iris dropped off the Wi-Fi network overnight; the board server on proximal
  stayed up. The owner power-cycled it at about 00:57 PST. The cause is not
  known: the stock image keeps the journal in memory (`Storage=volatile`), so
  the earlier logs were lost. `vcgencmd get_throttled` read `0x0` after the
  reboot. It came back at 192.168.1.247 (was 192.168.1.219; still no DHCP
  reservation).
- Re-ran `kiosk/deploy.sh` from `halbritt/agent-board`, which now also installs:
  - `/etc/NetworkManager/conf.d/agent-board-wifi-powersave.conf`
    (`wifi.powersave = 2`). The kernel log shows `power save disabled`.
  - `agent-board-net-watchdog.timer` and `.service` with
    `/usr/local/sbin/agent-board-net-watchdog`: checks the router every minute;
    reconnects Wi-Fi after 3 minutes, restarts NetworkManager after 10, reboots
    after 30.
  - `/etc/systemd/journald.conf.d/zz-agent-board.conf` (`Storage=persistent`,
    `SystemMaxUse=200M`), so the next failure leaves logs.
- Wi-Fi power saving as the cause is a guess. The recovery steps of the
  watchdog were not exercised; only a healthy check was run.
