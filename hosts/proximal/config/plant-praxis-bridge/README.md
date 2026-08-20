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
| Ficus Audrey (top) | `ficus_audrey_top_soil_moisture` | 40 |
| Ficus Audrey (deep) | `gw1200b_soil_moisture_1` | 30 (provisional — added 2026-08-20, no drying curve yet; deep Ecowitt probe alongside the ThirdReality top probe) |
| Monstera adansonii | `monstera_adansonii_soil_moisture` | 38 |
| Palm | `palm_moisture_soil_moisture` | 30 |
| Kangaroo Paw Fern | `kangaroo_paw_fern_soil_moisture` | 45 |
| Dracaena Michiko | `dracaena_michiko_soil_moisture` | 20 (provisional — paired 2026-07-29, mirrors Dracaena Lisa; retune after one dry-down) |

### Two live channels (2026-08-12) — keep the thresholds in sync

The `Plant needs water — per-plant rewater point` HA automation
(`automation.plant_drying_rate_has_slowed`) was disabled 2026-07-23 to make
Praxis the sole watering channel. It was **re-enabled 2026-08-12** as a
redundant second channel after this bridge went silent for 5 days across the
2026-08-07 reboot without anything surfacing the outage — Praxis is not yet
proven robust enough to be the only path. **Duplicate alerts are expected and
deliberate.**

So the thresholds above now live in two places and must be changed together:

| channel | where | covers |
|---|---|---|
| Praxis (this bridge) | `PLANTS` in `plant_praxis_bridge.py` | THIRSTY + DARK |
| HA push (phones) | the automation's `numeric_state` triggers | THIRSTY only |

Two asymmetries to keep in mind:

- **Only this bridge detects DARK.** A dead sensor never crosses a numeric
  threshold, so the HA automation cannot see a plant going unmonitored — that
  is exactly how Ficus Audrey went unnoticed from 2026-08-07 to 2026-08-12.
- **Ficus Audrey's deep probe (`gw1200b_soil_moisture_1`) is bridge-only.**
  Added 2026-08-20; the HA automation's `numeric_state` triggers still watch
  only the top probe, so the deep probe is not duplicated on the HA side.
- **The HA side has no re-arm hysteresis.** It re-fires on each fresh threshold
  crossing after `for: 06:00:00`, where this bridge alerts once and re-arms only
  above `threshold + 8%`.

Retire the HA channel again only once this bridge has demonstrably survived a
reboot; if you do, set `initial_state: false` **and** turn it off, since
`initial_state` alone only takes effect at HA restart.

## Repo file → install path

| repo (canonical) | installed copy (box) |
|---|---|
| `plant_praxis_bridge.py` | run in place from `~/git/infra/hosts/proximal/config/plant-praxis-bridge/` |
| `plant-praxis-bridge.service` | `~/.config/systemd/user/plant-praxis-bridge.service` |
| `plant-praxis-bridge.timer` | `~/.config/systemd/user/plant-praxis-bridge.timer` |
| `plant-praxis-bridge.env.template` | `~/.config/plant-praxis-bridge.env` (`0600`, **add real InfluxDB creds**) |

Install: `cp *.service *.timer ~/.config/systemd/user/ && systemctl --user
daemon-reload && systemctl --user enable --now plant-praxis-bridge.timer`.

### The timer must stay wall-clock — do not go back to monotonic

The schedule is `OnCalendar=hourly` + `Persistent=true`. It was originally
`OnBootSec=10min` + `OnUnitActiveSec=1h`, and that pair **silently killed the
alerts for 5 days** across the 2026-08-07 reboot: both trigger points evaluated
as already-past, the unit parked in `SubState=elapsed` with
`NextElapseUSecMonotonic=infinity`, and it kept reporting `enabled`/`active` the
whole time. `Persistent=` does not rescue that — it only applies to
`OnCalendar=`. See the 2026-08-12 entry in the host
[CHANGELOG](../../CHANGELOG.md).

A green `is-enabled`/`is-active` says nothing here. The real check is that
`NEXT` is a populated future timestamp:

```bash
systemctl --user list-timers plant-praxis-bridge.timer   # NEXT must not be '-'
```

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
