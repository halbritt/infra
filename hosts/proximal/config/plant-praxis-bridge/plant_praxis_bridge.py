#!/usr/bin/env python3
"""plant-praxis-bridge — file a Praxis reminder when a plant needs attention.

Reads each plant's latest soil moisture from the HA appliance's InfluxDB add-on
and files a work item in the harm Plane `PRAXIS` project — which Praxis imports
as a reminder via its ADR-0014 standing sync — for either of two conditions:

  1. THIRSTY  — moisture has dropped below the plant's per-plant rewater
                threshold (the point where its drying curve flattens).
  2. DARK     — the sensor has stopped reporting (no reading for STALE_HOURS).
                A dark sensor is NOT skipped: it can mean a dead battery/sensor
                OR an unmonitored plant quietly drying out, both of which need a
                human to go look. (This is the whole point — a silent sensor
                must never mean a silent dead plant.)

Each condition alerts once and re-arms only when it clears (watered / sensor
back). State is a small JSON file. No Home Assistant credential or config
change: detection is off InfluxDB, which proximal already reads.

Env (from the unit's EnvironmentFiles):
  INFLUXDB_URL, INFLUXDB_USER, INFLUXDB_PASSWORD   (~/.config/plant-praxis-bridge.env)
  PLANE_API_KEY, PLANE_INTERNAL_BASE_URL, PLANE_WORKSPACE_SLUG  (~/.config/plane/harm-mcp.env)
  PLANT_PRAXIS_STALE_HOURS (optional, default 24), PLANT_PRAXIS_PROJECT_ID (optional)
"""
import json, os, sys, time, urllib.parse, urllib.request, datetime as dt

# (display name, InfluxDB entity_id tag, rewater threshold %)
PLANTS = [
    ("Dracaena Lisa",      "dracaena_lisa_moisture_soil_moisture", 20),
    ("Ficus Audrey",       "ficus_audrey_top_soil_moisture",       40),
    # Deep probe (Ecowitt GW1200B, entity gw1200b_soil_moisture_1), added
    # 2026-08-20. Sits alongside the ThirdReality "top" probe above — the top
    # probe under-reports after watering (reads ~23% while deep reads 37-40%),
    # so the deep probe is the better root-zone signal. Threshold PROVISIONAL:
    # observed dry point ~25% before the 2026-08 watering (30d range 25-52%);
    # refine from its own drying curve after one dry-down.
    ("Ficus Audrey Deep",  "gw1200b_soil_moisture_1",              30),
    ("Monstera adansonii", "monstera_adansonii_soil_moisture",     38),
    ("Palm",               "palm_moisture_soil_moisture",          30),
    ("Kangaroo Paw Fern",  "kangaroo_paw_fern_soil_moisture",      45),
    # Provisional (paired 2026-07-29, no drying curve yet): 20 mirrors Dracaena
    # Lisa, same genus, which dries fully. Refine from its own curve after one
    # dry-down. entity_id renamed off the ThirdReality default 2026-07-29.
    ("Dracaena Michiko",   "dracaena_michiko_soil_moisture", 20),
]
REARM_HYSTERESIS = 8   # re-arm THIRSTY once moisture climbs this far back above threshold
STALE_HOURS = float(os.environ.get("PLANT_PRAXIS_STALE_HOURS", "24"))  # DARK after this silence
LOOKBACK_DAYS = 30     # query window; no point within it => treat as long-dark
PROJECT_ID = os.environ.get("PLANT_PRAXIS_PROJECT_ID",
                            "978fcda1-c9c1-4437-b83a-5c3d6de0178e")  # harm/PRAXIS
STATE_PATH = os.path.expanduser("~/.local/state/plant-praxis-bridge/state.json")


def log(msg):
    print(f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} {msg}", flush=True)


def influx_last(entity):
    """Latest reading as (value, age_seconds), or None if silent for LOOKBACK_DAYS."""
    base = os.environ["INFLUXDB_URL"]
    q = (f'SELECT last("value") FROM "%" WHERE ("entity_id" = \'{entity}\') '
         f'AND time > now()-{LOOKBACK_DAYS}d')
    url = base + "/query?" + urllib.parse.urlencode({
        "u": os.environ["INFLUXDB_USER"], "p": os.environ["INFLUXDB_PASSWORD"],
        "db": "homeassistant", "q": q, "epoch": "s"})
    with urllib.request.urlopen(url, timeout=20) as r:
        d = json.load(r)
    s = d["results"][0].get("series")
    if not s:
        return None
    ts, val = s[0]["values"][0]
    return float(val), max(0.0, time.time() - int(ts))


def create_plane_item(name, description_html):
    base = os.environ.get("PLANE_INTERNAL_BASE_URL", "http://127.0.0.1:8190")
    slug = os.environ.get("PLANE_WORKSPACE_SLUG", "harm")
    url = f"{base}/api/v1/workspaces/{slug}/projects/{PROJECT_ID}/issues/"
    body = json.dumps({"name": name, "description_html": description_html}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "X-API-Key": os.environ["PLANE_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def file_item(st, flag_key, dry_run, name, title, desc):
    """File a Plane item for one alert condition, dedup via st[flag_key]."""
    if st.get(flag_key):
        return
    if dry_run:
        log(f"{name}: WOULD file [{flag_key}] — {title}"); return
    try:
        item = create_plane_item(title, desc)
        log(f"{name}: filed [{flag_key}] {item.get('id','?')} (seq {item.get('sequence_id','?')})")
        st[flag_key] = True
        st[flag_key + "_on"] = dt.date.today().isoformat()
    except Exception as e:
        log(f"{name}: Plane create failed for [{flag_key}]: {e}")


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
        st = state.setdefault(entity, {})
        try:
            res = influx_last(entity)
        except Exception as e:
            log(f"{name}: InfluxDB read failed: {e}"); continue

        # --- DARK: no data within LOOKBACK_DAYS, or last point older than STALE_HOURS
        age_h = res[1] / 3600 if res else LOOKBACK_DAYS * 24
        if res is None or age_h >= STALE_HOURS:
            label = f">{LOOKBACK_DAYS}d" if res is None else f"{age_h:.0f}h"
            st["dark"] = True
            file_item(st, "dark_alerted", dry_run, name,
                      f"\U0001f331 Check {name} — soil sensor dark ({label})",
                      f"<p>{name}'s soil-moisture sensor has not reported for <b>{label}</b>. "
                      f"That can mean a dead battery/sensor <i>or</i> an unmonitored plant "
                      f"drying out — go check the plant and the sensor. "
                      f"(plant-praxis-bridge, {today})</p>")
            log(f"{name}: DARK ({label}), dark_alerted={st.get('dark_alerted')}")
            continue

        # --- sensor is live: clear a prior DARK alert
        val = res[0]
        st["last_value"] = round(val, 1)
        st["last_age_h"] = round(age_h, 1)
        st["dark"] = False
        if st.get("dark_alerted"):
            st["dark_alerted"] = False
            log(f"{name}: sensor recovered ({val:.0f}%) — DARK re-armed")

        # --- THIRSTY: below the rewater threshold
        if val < threshold:
            file_item(st, "alerted", dry_run, name,
                      f"\U0001f331 Water {name}",
                      f"<p>{name} soil moisture is <b>{val:.0f}%</b> — at/below its "
                      f"{threshold}% rewater point (drying has flattened). "
                      f"(plant-praxis-bridge, {today})</p>")
            # Log every run while dry, not just the run that files the item.
            # file_item() returns silently once st['alerted'] is set, so without
            # this a plant that is thirsty and already-alerted vanished from the
            # logs entirely — the driest plant was the least visible one.
            log(f"{name}: {val:.0f}% BELOW {threshold}% — still dry "
                f"(since {st.get('alerted_on', '?')}, re-arms above "
                f"{threshold + REARM_HYSTERESIS}%)")
        elif val >= threshold + REARM_HYSTERESIS and st.get("alerted"):
            st["alerted"] = False
            log(f"{name}: {val:.0f}% back above {threshold}+{REARM_HYSTERESIS}% — THIRSTY re-armed")
        else:
            log(f"{name}: {val:.0f}% (thr {threshold}%, thirsty_alerted={st.get('alerted', False)})")
    if not dry_run:
        save_state(state)


if __name__ == "__main__":
    main()
