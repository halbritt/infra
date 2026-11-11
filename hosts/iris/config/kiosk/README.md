# Iris board kiosk

Iris is the display for the Fernside board. The source, installer and design
are in `~/git/agent-board` (`halbritt/agent-board`): read its `README.md` and
`kiosk/` before changing anything here. This record describes what is installed
on Iris and how to check it.

## Role

Iris holds one kiosk token and no logic. Proximal renders the board's scene;
Iris shows it and sends touches back. See
[proximal's record](../../../proximal/config/agent-board/README.md).

## Installed state (2026-11-11)

Installed from proximal with `~/git/agent-board/kiosk/deploy.sh`, at
agent-board commit `480fd0f`. The script is idempotent.

| Path on Iris | Purpose |
|---|---|
| `~/agent-board/kiosk/` | Copy of the repository's `kiosk/` directory |
| `~/.config/systemd/user/agent-board-kiosk.service` | User unit for `iris_agent.py`, enabled |
| `~/.config/agent-board/kiosk-token` | Kiosk token, mode 0600. Not in Git. |
| `~/.config/agent-board/kiosk.env` | `AGENT_BOARD_UPSTREAM=http://proximal.local:8787` |
| `~/.config/agent-board/labwc/` | Compositor configuration for the board session |
| `~/.local/share/icons/board-blank/` | Transparent cursor theme |
| `~/.local/state/agent-board/` | Last scene, cached page, display settings, browser profile |
| `/usr/local/bin/agent-board-session` | Starts labwc with the board configuration only |
| `/usr/share/wayland-sessions/agent-board.desktop` | The `agent-board` session |
| `/etc/lightdm/lightdm.conf` | `user-session` and `autologin-session` set to `agent-board` |

`iris_agent.py` listens on `127.0.0.1:8788`. It proxies the page and API to
proximal, keeps the last scene on disk, writes
`/sys/class/backlight/panel_backlight@1/brightness` from the scene, applies the
saved rotation with `wlr-randr`, and restarts Chromium when the page stops
reporting, at most three times an hour. `halbritt` is in group `video`, which
owns the backlight file; no udev rule or root service was needed.

The board session runs `labwc -C ~/.config/agent-board/labwc`. It does not merge
the desktop configuration, so the panel (`wf-panel-pi`) and the desktop
(`pcmanfm`) do not start. Touch is mapped to DSI-2 with mouse emulation off.
Chromium 154 runs in kiosk mode under `lwrespawn`.

## Changes to the stock image

- LightDM autologin session changed from `rpd-labwc` to `agent-board`.
- No packages were installed or removed. Chromium, labwc, wlr-randr, grim and
  Python 3.13 came with the image.
- The stock desktop session files were not edited.

To return to the desktop:

```sh
sudo sed -i -E 's/^(autologin-session|user-session)=.*/\1=rpd-labwc/' /etc/lightdm/lightdm.conf
systemctl --user disable --now agent-board-kiosk.service
sudo systemctl restart lightdm
```

## Check

From proximal:

```sh
ssh halbritt@iris.local 'systemctl --user is-active agent-board-kiosk
  curl -s localhost:8788/local/status
  pgrep -fc "chromium.*--kiosk"
  XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 grim /tmp/board.png'
scp halbritt@iris.local:/tmp/board.png .
```

`link.ok` in the status is false when Iris cannot reach proximal. The page then
shows a red banner with the time it last heard from proximal.

## Verified 2026-11-11

- After `sudo reboot`, Iris returned in about one minute showing the board, with
  the agent active, one kiosk browser, no panel or desktop process and no cursor.
- Backlight followed the scene: 25 of 31 by day, with a pulse to 31 for an urgent
  request.
- With proximal's `agent-board.service` stopped for 50 seconds, the page showed
  "Not receiving updates since 10:40". The link recovered within 30 seconds of
  the service returning.
- Interactions were driven over HTTP during the install, not by touch.
- Orientation: later on 2026-11-11 the owner turned the output a quarter turn
  with **Rotate** on the board and set manual brightness, both by touch.
  `~/.local/state/agent-board/display.json` then held `"rotation": "90"` and
  `"auto": false, "level": 0.67`, and a capture was 1920×1200. Iris is used in
  landscape. This also shows touch input reaches the page; the individual
  controls were still not checked one by one.

## Not done

- Iris is not on the tailnet. It reaches proximal by mDNS on the LAN.
- No DHCP reservation. The address changed from 192.168.1.216 to 192.168.1.219
  during 2026-11-11; use `iris.local`.
- Screen blanking is off (`raspi-config nonint get_blanking` returns 1). The
  board dims the backlight at night instead of turning the panel off.
