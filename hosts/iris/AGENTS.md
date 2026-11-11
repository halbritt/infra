# iris

Read `machine.yaml`, `README.md`, `notes.md`, and the target subsystem README
before changes. Iris is a Raspberry Pi 5 with a local DSI touch display.

The observed management connection uses Wi-Fi. Recheck its address before
operating; the recorded LAN address is an observation, not a reservation.
Wi-Fi credentials and SSH private keys stay outside Git.

For a missing display, check EEPROM firmware as well as OS packages. The
2026-11-11 repair used the installed default EEPROM release and preserved
display auto-detection. Read `config/display/README.md` before changing overlays.
Disconnect power before reseating the display ribbon or GPIO power cable.

Iris runs the Fernside board kiosk. Its code lives in `~/git/agent-board`; change
it there and install with `kiosk/deploy.sh`, not by editing files on Iris. Read
`config/kiosk/README.md` first. The owner dedicated this host to the board on
2026-11-11.
