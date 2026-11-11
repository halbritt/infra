# agent-board on proximal

Proximal runs the server for the Fernside board. Source and documentation:
`~/git/agent-board` (`halbritt/agent-board`). The display is Iris; see
[its kiosk record](../../../iris/config/kiosk/README.md).

## Installed state (2026-11-11)

| Item | Value |
|---|---|
| Unit | user unit `agent-board.service` (`~/.config/systemd/user/`), enabled |
| Working directory | `~/agent-board`, a copy of the repository's `server/`, `web/`, `kiosk/` and `bin/` |
| Listener | `0.0.0.0:8787` |
| Version | agent-board commit `480fd0f` |

The unit file is `deploy/agent-board.service` in the repository; it did not
change with the touch-board work. Deploy with the `rsync` commands in the
repository README, then `systemctl --user restart agent-board`.

Credentials stay outside Git, all mode 0600:

| File | Use |
|---|---|
| `~/.config/agent-board/ha-mcp-url` | Home Assistant MCP endpoint |
| `~/.config/agent-board/token` | Write token for the item API |
| `~/.config/agent-board/kiosk-token` | Read and answer token, copied to Iris. Created 2026-11-11. |
| `~/.local/share/cairn/event-profiles/board.token` | Cairn principal `agent/board` |

## What changed on 2026-11-11

The server gained a live scene (`/api/scene`, `/api/stream`) for the Iris touch
display, and now publishes Cairn responses as `agent/board` when a request is
answered on the display. Before this it only read the `agent-board` topic.

Polling changed with it: Home Assistant state every 60 seconds (was 300), the
Cairn topic every 5 seconds (was 15), forecasts every 30 minutes, plant history
hourly, calendars every 10 minutes. Each Home Assistant read opens one MCP
session.

Scene reads and touch actions need the kiosk token from other hosts and are
open to loopback clients. `/board.png` and `/api/state` stay open on the LAN
for the E1002 e-paper device.

## Check

```sh
systemctl --user status agent-board
curl -fsS http://127.0.0.1:8787/api/scene | head -c 300
journalctl --user -u agent-board -n 20
```
