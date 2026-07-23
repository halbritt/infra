#!/usr/bin/env python3
"""plant-praxis-bridge — file a Praxis reminder when a plant needs water.

Reads each plant's latest soil moisture from the HA appliance's InfluxDB add-on,
compares against a per-plant rewater threshold (the point where its drying curve
flattens; see the observability plant-moisture dashboard analysis, 2026-07-23),
and creates a work item in the harm Plane `PRAXIS` project when a plant first
crosses below. Praxis's standing Plane sync (ADR 0014) imports that item as a
reminder. One alert per dry-down: re-arms only after the plant is watered
(moisture rises back above threshold + hysteresis).

No Home Assistant credential or config change: detection is off InfluxDB, which
proximal already reads. Runs as a systemd user timer (hourly).

Env (from the unit's EnvironmentFiles):
  INFLUXDB_URL, INFLUXDB_USER, INFLUXDB_PASSWORD   (~/.config/plant-praxis-bridge.env)
  PLANE_API_KEY, PLANE_INTERNAL_BASE_URL, PLANE_WORKSPACE_SLUG  (~/.config/plane/harm-mcp.env)
"""
import json, os, sys, time, urllib.parse, urllib.request, datetime as dt

# (display name, InfluxDB entity_id tag, rewater threshold %)
PLANTS = [
    ("Dracaena Lisa",      "dracaena_lisa_moisture_soil_moisture", 20),
    ("Ficus Audrey",       "ficus_audrey_top_soil_moisture",       40),
    ("Monstera adansonii", "monstera_adansonii_soil_moisture",     38),
    ("Palm",               "palm_moisture_soil_moisture",          30),
    ("Kangaroo Paw Fern",  "kangaroo_paw_fern_soil_moisture",      45),
]
REARM_HYSTERESIS = 8          # re-arm once moisture climbs this far back above threshold
PROJECT_ID = os.environ.get("PLANT_PRAXIS_PROJECT_ID",
                            "978fcda1-c9c1-4437-b83a-5c3d6de0178e")  # harm/PRAXIS
STATE_PATH = os.path.expanduser("~/.local/state/plant-praxis-bridge/state.json")


def log(msg):
    print(f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} {msg}", flush=True)


def influx_last(entity):
    """Latest soil-moisture reading in the last 24h, or None if the sensor is silent."""
    base = os.environ["INFLUXDB_URL"]
    q = (f'SELECT last("value") FROM "%" WHERE ("entity_id" = \'{entity}\') '
         f'AND time > now()-24h')
    url = base + "/query?" + urllib.parse.urlencode({
        "u": os.environ["INFLUXDB_USER"], "p": os.environ["INFLUXDB_PASSWORD"],
        "db": "homeassistant", "q": q})
    with urllib.request.urlopen(url, timeout=20) as r:
        d = json.load(r)
    s = d["results"][0].get("series")
    return float(s[0]["values"][0][1]) if s else None


def create_plane_item(name, description_html):
    base = os.environ.get("PLANE_INTERNAL_BASE_URL", "http://127.0.0.1:8190")
    slug = os.environ.get("PLANE_WORKSPACE_SLUG", "harm")
    url = f"{base}/api/v1/workspaces/{slug}/projects/{PROJECT_ID}/issues/"
    body = json.dumps({"name": name, "description_html": description_html}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "X-API-Key": os.environ["PLANE_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)


def main():
    dry_run = "--dry-run" in sys.argv
    state = load_state()
    today = dt.date.today().isoformat()
    for name, entity, threshold in PLANTS:
        try:
            val = influx_last(entity)
        except Exception as e:
            log(f"{name}: InfluxDB read failed: {e}"); continue
        if val is None:
            log(f"{name}: no reading in last 24h — skipping"); continue
        st = state.setdefault(entity, {"alerted": False})
        st["last_value"] = round(val, 1)
        if val < threshold and not st["alerted"]:
            title = f"\U0001f331 Water {name}"
            desc = (f"<p>{name} soil moisture is <b>{val:.0f}%</b> — at/below its "
                    f"{threshold}% rewater point (drying has flattened). Detected "
                    f"{today} by plant-praxis-bridge from InfluxDB.</p>")
            if dry_run:
                log(f"{name}: {val:.0f}% < {threshold}% — WOULD file Plane item")
            else:
                try:
                    item = create_plane_item(title, desc)
                    log(f"{name}: {val:.0f}% < {threshold}% — filed {item.get('id','?')} "
                        f"({item.get('sequence_id','?')})")
                    st["alerted"] = True
                    st["last_alert"] = today
                except Exception as e:
                    log(f"{name}: Plane create failed: {e}")
        elif val >= threshold + REARM_HYSTERESIS and st["alerted"]:
            st["alerted"] = False
            log(f"{name}: {val:.0f}% back above {threshold}+{REARM_HYSTERESIS}% — re-armed")
        else:
            log(f"{name}: {val:.0f}% (threshold {threshold}%, alerted={st['alerted']})")
    if not dry_run:
        save_state(state)


if __name__ == "__main__":
    main()
