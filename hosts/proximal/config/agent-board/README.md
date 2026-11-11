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
| Version | agent-board commit `5dc7616` |

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

## Light control (2026-11-11, later the same day)

The owner asked for light controls on the board. The server now calls
`light.turn_on` and `light.turn_off` through the Home Assistant MCP endpoint
when a light is tapped on the Iris display. This is the first write the board
makes to Home Assistant; before this it only read.

- Only entities that Home Assistant lists in the `light` domain can be switched.
  Locks, switches and everything else are refused in `server/lights.py`.
- "All off" and "Room off" skip lights whose name contains "grow".
- The calls need the kiosk token from other hosts, like the other touch actions.
- Light states are read every 60 seconds, and every 5 seconds while the lights
  view is open on the display.
- Verified through Iris: the hall night light was set to 15 %, read back, and
  turned off; a lock entity was refused.

## Check

```sh
systemctl --user status agent-board
curl -fsS http://127.0.0.1:8787/api/scene | head -c 300
journalctl --user -u agent-board -n 20
```

## Front door lock (2026-11-11)

The owner asked for the door tile to lock the door. The server now calls
`lock.lock` on `lock.aqara_smart_lock_u200` when **Lock the door** is tapped on
the Iris display (`POST /api/door/lock`, kiosk token required from the LAN).

- Lock only. No code path calls `lock.unlock`, and a test fails if one is added.
- The server waits up to 12 seconds for the lock to report `locked` and returns
  an error to the display if it does not.
- Not exercised against the real lock by the agent: the door was unlocked at
  deploy time and the first real use was left to the owner.
