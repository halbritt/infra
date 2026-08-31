#!/usr/bin/env python3
"""Generate the plant-moisture Grafana dashboard JSON.

Migration of the appliance's broken "Plant Moisture" Lovelace dashboard onto
proximal Grafana (Recorder keeps 30 days; VictoriaMetrics keeps two years).

SCHEMA — the HA InfluxDB integration's default layout, verified live against
this instance 2026-07-22 (measurement "%" / "%/d", entity_id tags as below).
All of it stays isolated in SOIL_UNIT / RATE_UNIT / the entity_id tables below.
Re-verify after any HA-side rename with:

  influx -host 100.105.145.26 -port 8086 -username grafana_ro -password ... \
         -database homeassistant -execute \
    'SHOW TAG VALUES FROM "%" WITH KEY = "entity_id" WHERE "domain" = '"'"'sensor'"'"''

If the measurement isn't "%" (some setups override_measurement per entity), or
the entity_id tags carry a different form, adjust the two *_UNIT constants and
the PLANTS / RATES tables and re-run. Regenerate:
  python3 build_plant_moisture_dashboard.py > plant-moisture.json
  python3 build_plant_moisture_dashboard.py --backend victoriametrics \
    > plant-moisture-victoriametrics.json
Installs to /var/lib/grafana/dashboards-homeassistant/ (the "Home Assistant"
folder provider), NOT the proximal folder — this is appliance data.
"""
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument("--backend", choices=("influxdb", "victoriametrics"),
                    default="influxdb")
BACKEND = parser.parse_args().backend
VM = BACKEND == "victoriametrics"
DS = ({"type": "prometheus", "uid": "victoriametrics-ha"} if VM else
      {"type": "influxdb", "uid": "influx-ha"})

# HA InfluxDB default schema: measurement = unit_of_measurement, entity_id is a
# tag (short id, no "sensor." prefix), numeric reading in the "value" field.
SOIL_UNIT = "%"      # soil-moisture sensors report percent
RATE_UNIT = "%/d"    # derivative "* Moisture Rate" sensors — VERIFY (may be "/d")

# (display name, entity_id tag value) — soil-moisture gauges + entities panel.
# Black Olive Tree removed 2026-07-23 (ZHA device retired; sensor dead since Jul 3).
PLANTS = [
    ("Ficus Audrey (Top)", "ficus_audrey_top_soil_moisture"),
    ("Dracaena Lisa",      "dracaena_lisa_moisture_soil_moisture"),
    ("Ficus Audrey (Deep)","gw1200b_soil_moisture_1"),
    ("Kangaroo Paw Fern",  "kangaroo_paw_fern_soil_moisture"),
    ("Monstera adansonii", "monstera_adansonii_soil_moisture"),
    ("Palm",               "palm_moisture_soil_moisture"),
    # Dracaena Michiko: ThirdReality 3RSM0347Z paired 2026-07-29; device + soil-moisture
    # entity_id renamed off the ThirdReality default, so this clean tag starts at the
    # rename (the ~90 min of pre-rename data stays under the old third_reality_inc_* tag).
    ("Dracaena Michiko",   "dracaena_michiko_soil_moisture"),
    # Areca Palm: ThirdReality 3RSM0347Z added 2026-08-27; renamed off the default.
    ("Areca Palm",         "areca_palm_soil_moisture"),
]

# (display name, entity_id tag value) — 24h drying-rate derivatives
RATES = [
    ("Dracaena Lisa",     "dracaena_lisa_moisture_rate"),
    ("Ficus Audrey",      "ficus_audrey_top_moisture_rate"),
    ("Kangaroo Paw Fern", "kangaroo_paw_fern_moisture_rate"),
    ("Monstera adansonii","monstera_adansonii_moisture_rate"),
    ("Palm",              "palm_moisture_palm_moisture_rate"),
    ("Dracaena Michiko",  "dracaena_michiko_moisture_rate"),
    ("Areca Palm",        "areca_palm_moisture_rate"),
]

_id = [0]
def nid():
    _id[0] += 1
    return _id[0]

def q(unit, entity_id, fn="mean", fill="none"):
    """One InfluxQL target selecting a single entity's series from a measurement.

    fill=none (not previous): a sensor that stops reporting must leave a real gap,
    not carry its last value forward — otherwise a dead sensor reads as a live one.
    """
    if VM:
        selector = (f'homeassistant_state_value{{db="homeassistant",'
                    f'entity_id="{entity_id}",unit="{unit}"}}')
        rollup = "last_over_time" if fn == "last" else "avg_over_time"
        return {
            "datasource": DS,
            "editorMode": "code",
            "expr": f"{rollup}({selector}[$__interval])",
            "range": True,
            "refId": "A",
        }
    return {
        "datasource": DS,
        "refId": "A",
        "resultFormat": "time_series",
        "query": (
            f'SELECT {fn}("value") FROM "{unit}" '
            f"WHERE (\"entity_id\" = '{entity_id}') AND $timeFilter "
            f"GROUP BY time($__interval) fill({fill})"
        ),
        "rawQuery": True,
    }

def named(target, name):
    target["legendFormat" if VM else "alias"] = name
    return target

def gauge(name, unit, entity_id, x, y, w=4, h=6):
    return {
        "type": "gauge", "title": name, "datasource": DS, "id": nid(),
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        # Gauge reflects only the last 24h so a sensor that has gone silent shows
        # "No data" instead of a stale reading, regardless of the dashboard range.
        # hideTimeOverride keeps the badge out of the header — without it the
        # "Last 24 hours" indicator eats the whole title, truncating it to "P…".
        "timeFrom": "24h",
        "hideTimeOverride": True,
        # alias = plant name: without it the single InfluxQL series is named after
        # the measurement ("%"), so the gauge caption reads "%" instead of the plant.
        "targets": [named(q(unit, entity_id, fn="last"), name)],
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "showThresholdLabels": False, "showThresholdMarkers": True},
        "fieldConfig": {"defaults": {
            "unit": "percent", "min": 0, "max": 100,
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "red", "value": None},
                {"color": "yellow", "value": 30},
                {"color": "green", "value": 50},
            ]},
        }, "overrides": []},
    }

def rate_ts(x, y, w=24, h=9):
    return {
        "type": "timeseries", "title": "Drying rate — % per day (negative = drying)",
        "datasource": DS, "id": nid(),
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [
            {**named(q(RATE_UNIT, eid, fn="mean"), name), "refId": chr(65 + i)}
            for i, (name, eid) in enumerate(RATES)
        ],
        "fieldConfig": {"defaults": {
            "unit": "none",
            "custom": {"drawStyle": "line", "lineInterpolation": "smooth",
                       "fillOpacity": 8, "showPoints": "never", "spanNulls": False},
            "color": {"mode": "palette-classic"},
        }, "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "bottom",
                               "calcs": ["last", "min"]},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
    }

def row(title, y):
    return {"type": "row", "title": title, "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "id": nid(), "panels": []}

def readings_table(x, y, w=24, h=8):
    return {
        "type": "timeseries", "title": "Soil moisture — history",
        "datasource": DS, "id": nid(),
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [
            {**named(q(SOIL_UNIT, eid, fn="mean"), name), "refId": chr(65 + i)}
            for i, (name, eid) in enumerate(PLANTS)
        ],
        "fieldConfig": {"defaults": {
            "unit": "percent", "min": 0, "max": 100,
            "custom": {"drawStyle": "line", "lineInterpolation": "smooth",
                       "fillOpacity": 6, "showPoints": "never", "spanNulls": False},
            "color": {"mode": "palette-classic"},
        }, "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "bottom",
                               "calcs": ["last", "min", "max"]},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
    }

panels = []
y = 0
panels.append(row("Soil Moisture — red <30% · yellow 30–50% · green >50%", y)); y += 1
for i, (name, eid) in enumerate(PLANTS):
    panels.append(gauge(name, SOIL_UNIT, eid, x=(i % 6) * 4, y=y + (i // 6) * 6))
y += 6 * ((len(PLANTS) + 5) // 6)   # wrap 6 gauges per row
panels.append(readings_table(0, y)); y += 8
panels.append(row("Drying Rate", y)); y += 1
panels.append(rate_ts(0, y)); y += 9

# Watering annotations: mark soak dates on the time panels. A watering is a
# sharp moisture rise; difference(max) over 6h buckets, filtered >15 pts, flags
# it — and auto-updates as new waterings land. One layer per surface probe
# (the deep Ficus probe lags the actual soak, so it's excluded).
ANNOT = [
    ("Dracaena Lisa",     "dracaena_lisa_moisture_soil_moisture", "#b48ead"),
    ("Ficus Audrey",      "ficus_audrey_top_soil_moisture",       "#5db8a4"),
    ("Monstera adansonii","monstera_adansonii_soil_moisture",     "#a3be8c"),
    ("Palm",              "palm_moisture_soil_moisture",          "#ebcb8b"),
    ("Kangaroo Paw Fern", "kangaroo_paw_fern_soil_moisture",      "#81a1c1"),
    ("Dracaena Michiko",  "dracaena_michiko_soil_moisture", "#d08770"),
    ("Areca Palm",        "areca_palm_soil_moisture",       "#88c0d0"),
]
def annotation(name, entity_id, color):
    if VM:
        selector = (f'homeassistant_state_value{{db="homeassistant",'
                    f'entity_id="{entity_id}",unit="%"}}')
        return {
            "datasource": DS, "enable": True, "hide": False,
            "iconColor": color, "name": f"{name} watered",
            "expr": (f"(max_over_time({selector}[6h]) - "
                     f"max_over_time({selector}[6h] offset 6h)) > 15"),
            "step": "6h", "tagKeys": "", "textFormat": "",
        }
    return {
        "datasource": DS, "enable": True, "hide": False, "iconColor": color,
        "name": f"{name} watered",
        "query": (
            'SELECT "d" FROM (SELECT difference(max("value")) AS "d" '
            f'FROM "%" WHERE ("entity_id" = \'{entity_id}\') AND $timeFilter '
            'GROUP BY time(6h) fill(none)) WHERE "d" > 15'
        ),
        "textColumn": "", "titleColumn": "", "tagsColumn": "",
    }

dashboard = {
    "uid": "plant-moisture-victoriametrics" if VM else "plant-moisture",
    "title": ("Plant Moisture — homeassistant (via VictoriaMetrics)" if VM else
              "Plant Moisture — homeassistant (via InfluxDB)"),
    "tags": ["plants", "homeassistant", BACKEND],
    "timezone": "browser",
    "schemaVersion": 39,
    "version": 1,
    "refresh": "5m",
    "time": {"from": "now-7d", "to": "now"},
    "templating": {"list": []},
    "annotations": {"list": [annotation(n, e, c) for n, e, c in ANNOT]},
    "editable": True,
    "panels": panels,
}

print(json.dumps(dashboard, indent=2))
