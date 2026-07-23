# plant-praxis-bridge/ — watering alerts → Praxis reminders

Desired-state for the **plant-praxis-bridge** on `proximal`: a small systemd
user timer that turns "a plant needs water" into a Praxis reminder, without
touching Home Assistant.

## What it does

Hourly, it reads each plant's latest soil moisture from the HA appliance's
InfluxDB add-on (`100.105.145.26:8086`, the same data the observability
`plant-moisture` Grafana dashboard uses), compares against a per-plant rewater
threshold, and — when a plant first crosses below — creates a work item in the
**harm** Plane `PRAXIS` project (`plane.harm.org`, id `978fcda1-…`). Praxis's
standing Plane sync (ADR 0014) imports that item as a reminder and surfaces it
(Slack `#praxis-chat`).

One alert per dry-down: a plant that stays dry is not re-filed every hour. It
re-arms only after the plant is watered — moisture back above `threshold +
8%`. State is a small JSON file at `~/.local/state/plant-praxis-bridge/`.

**Why here and not in HA:** detection is off InfluxDB, which proximal already
reads, so no HA config change and no Plane token on the (public-repo'd)
appliance — both tokens already live on proximal. Chosen over an HA
`rest_command` because that would have needed the `ha_mcp_tools` helper
component installed + an HA restart, and a workspace-broad Plane token on the
appliance. Trade-off accepted: ~hourly latency instead of event-driven.

## Thresholds (the rewater points)

From the 2026-07-23 drying-curve analysis (see the plant-moisture dashboard).
Buffered plants (plateau high) nudge just below plateau; Dracaena dries fully
so it nudges with lead time. **Edit `PLANTS` in the script** to retune.

| plant | entity_id | below % |
|---|---|---|
| Dracaena Lisa | `dracaena_lisa_moisture_soil_moisture` | 20 |
| Ficus Audrey | `ficus_audrey_top_soil_moisture` | 40 |
| Monstera adansonii | `monstera_adansonii_soil_moisture` | 38 |
| Palm | `palm_moisture_soil_moisture` | 30 |
| Kangaroo Paw Fern | `kangaroo_paw_fern_soil_moisture` | 45 |

These mirror the `Plant needs water — per-plant rewater point` HA automation
(the in-HA layer). Two copies today; keep them in sync when retuning, or drop
the HA automation's notify if Praxis should be the sole channel.

## Repo file → install path

| repo (canonical) | installed copy (box) |
|---|---|
| `plant_praxis_bridge.py` | run in place from `~/git/proximal/plant-praxis-bridge/` |
| `plant-praxis-bridge.service` | `~/.config/systemd/user/plant-praxis-bridge.service` |
| `plant-praxis-bridge.timer` | `~/.config/systemd/user/plant-praxis-bridge.timer` |
| `plant-praxis-bridge.env.template` | `~/.config/plant-praxis-bridge.env` (`0600`, **add real InfluxDB creds**) |

Install: `cp *.service *.timer ~/.config/systemd/user/ && systemctl --user
daemon-reload && systemctl --user enable --now plant-praxis-bridge.timer`.

## Secrets — by name only, never value

No credentials in this repo. Two env files, both `0600`, outside git:

- `~/.config/plant-praxis-bridge.env` — `INFLUXDB_URL/USER/PASSWORD`
  (read-only `grafana_ro`, the same user the Grafana HA-InfluxDB datasource
  uses; see `observability/`).
- `~/.config/plane/harm-mcp.env` — `PLANE_API_KEY` for the harm Plane, plus
  `PLANE_INTERNAL_BASE_URL` / `PLANE_WORKSPACE_SLUG` (reused, not duplicated).

## Operate

```bash
systemctl --user list-timers plant-praxis-bridge.timer   # next run
systemctl --user start plant-praxis-bridge.service       # run now
journalctl --user -u plant-praxis-bridge.service -f       # logs
python3 plant_praxis_bridge.py --dry-run                  # read + decide, no Plane writes
```
