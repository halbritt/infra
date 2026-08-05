# plant-praxis-bridge/ — watering alerts → Praxis reminders

Desired-state for the **plant-praxis-bridge** on `proximal`: a small systemd
user timer that turns "a plant needs water" into a Praxis reminder, without
touching Home Assistant.

## What it does

Hourly, it reads each plant's latest soil moisture from the HA appliance's
InfluxDB add-on (`100.105.145.26:8086`, the same data the observability
`plant-moisture` Grafana dashboard uses) and files a work item in the **harm**
Plane `PRAXIS` project (`plane.harm.org`, id `978fcda1-…`) — which Praxis's
standing Plane sync (ADR 0014) imports as a reminder (Slack `#praxis-chat`) —
for either of two conditions:

- **THIRSTY** — moisture dropped below the plant's per-plant rewater threshold.
- **DARK** — the sensor stopped reporting for `STALE_HOURS` (default 24). A dark
  sensor is **not skipped**: it can mean a dead battery/sensor *or* an
  unmonitored plant quietly drying out — both need a human to go look. A silent
  sensor must never become a silent dead plant.

Each condition alerts once and re-arms only when it clears: THIRSTY re-arms when
moisture climbs back above `threshold + 8%` (watered); DARK re-arms when the
sensor reports again. State is a small JSON file at
`~/.local/state/plant-praxis-bridge/` (`last_value`, `last_age_h`, and the two
`*_alerted` flags per plant).

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
| Dracaena Michiko | `dracaena_michiko_soil_moisture` | 20 (provisional — paired 2026-07-29, mirrors Dracaena Lisa; retune after one dry-down) |

The `Plant needs water — per-plant rewater point` HA automation that held the
same thresholds was **disabled 2026-07-23** (`initial_state: false` + turned
off) so Praxis is the sole watering-alert channel — this bridge is now the live
authority. The disabled automation is kept in HA only as the in-HA record of
the thresholds; if you retune here, mirror it there only if you ever re-enable
it.

## Repo file → install path

| repo (canonical) | installed copy (box) |
|---|---|
| `plant_praxis_bridge.py` | run in place from `~/git/infra/hosts/proximal/config/plant-praxis-bridge/` |
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
PLANT_PRAXIS_STALE_HOURS=0 python3 plant_praxis_bridge.py --dry-run   # exercise the DARK branch
```
