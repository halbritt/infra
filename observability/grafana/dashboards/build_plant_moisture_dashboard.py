#!/usr/bin/env python3
"""Generate the plant-moisture Grafana dashboard JSON, reading the HA appliance's
InfluxDB add-on via the influx-ha datasource.

Migration of the appliance's broken "Plant Moisture" Lovelace dashboard onto
proximal Grafana (the recorder only keeps ~10 days; InfluxDB keeps full history).

SCHEMA ASSUMPTION — the HA InfluxDB integration's default layout, NOT yet
verified against this instance (needs the read credential first). All of it is
isolated in SOIL_UNIT / RATE_UNIT / the entity_id tag values below. Verify with:

  influx -host 100.105.145.26 -port 8086 -username grafana_ro -password ... \
         -database homeassistant -execute \
    'SHOW TAG VALUES FROM "%" WITH KEY = "entity_id" WHERE "domain" = '"'"'sensor'"'"''

If the measurement isn't "%" (some setups override_measurement per entity), or
the entity_id tags carry a different form, adjust the two *_UNIT constants and
the PLANTS / RATES tables and re-run. Regenerate:
  python3 build_plant_moisture_dashboard.py > plant-moisture-proximal.json
"""
import json

DS = {"type": "influxdb", "uid": "influx-ha"}

# HA InfluxDB default schema: measurement = unit_of_measurement, entity_id is a
# tag (short id, no "sensor." prefix), numeric reading in the "value" field.
SOIL_UNIT = "%"      # soil-moisture sensors report percent
RATE_UNIT = "%/d"    # derivative "* Moisture Rate" sensors — VERIFY (may be "/d")

# (display name, entity_id tag value) — soil-moisture gauges + entities panel
PLANTS = [
    ("Black Olive Tree",   "black_olive_tree_soil_moisture"),
    ("Ficus Audrey (Top)", "ficus_audrey_top_soil_moisture"),
    ("Dracaena Lisa",      "dracaena_lisa_moisture_soil_moisture"),
    ("Ficus Audrey (Deep)","gw1200b_soil_moisture_1"),
    ("Kangaroo Paw Fern",  "kangaroo_paw_fern_soil_moisture"),
    ("Monstera adansonii", "monstera_adansonii_soil_moisture"),
    ("Palm",               "palm_moisture_soil_moisture"),
]

# (display name, entity_id tag value) — 24h drying-rate derivatives
RATES = [
    ("Dracaena Lisa",     "dracaena_lisa_moisture_rate"),
    ("Ficus Audrey",      "ficus_audrey_top_moisture_rate"),
    ("Kangaroo Paw Fern", "kangaroo_paw_fern_moisture_rate"),
    ("Monstera adansonii","monstera_adansonii_moisture_rate"),
    ("Palm",              "palm_moisture_palm_moisture_rate"),
]

_id = [0]
def nid():
    _id[0] += 1
    return _id[0]

def q(unit, entity_id, fn="mean", fill="previous"):
    """One InfluxQL target selecting a single entity's series from a measurement."""
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

def gauge(name, unit, entity_id, x, y, w=4, h=6):
    return {
        "type": "gauge", "title": name, "datasource": DS, "id": nid(),
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [q(unit, entity_id, fn="last")],
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
            {**q(RATE_UNIT, eid, fn="mean"), "refId": chr(65 + i), "alias": name}
            for i, (name, eid) in enumerate(RATES)
        ],
        "fieldConfig": {"defaults": {
            "unit": "none",
            "custom": {"drawStyle": "line", "lineInterpolation": "smooth",
                       "fillOpacity": 8, "showPoints": "never", "spanNulls": True},
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
            {**q(SOIL_UNIT, eid, fn="mean"), "refId": chr(65 + i), "alias": name}
            for i, (name, eid) in enumerate(PLANTS)
        ],
        "fieldConfig": {"defaults": {
            "unit": "percent", "min": 0, "max": 100,
            "custom": {"drawStyle": "line", "lineInterpolation": "smooth",
                       "fillOpacity": 6, "showPoints": "never", "spanNulls": True},
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
    panels.append(gauge(name, SOIL_UNIT, eid, x=(i % 6) * 4, y=y))
y += 6
panels.append(readings_table(0, y)); y += 8
panels.append(row("Drying Rate", y)); y += 1
panels.append(rate_ts(0, y)); y += 9

dashboard = {
    "uid": "plant-moisture-proximal",
    "title": "Plant Moisture — homeassistant (via InfluxDB)",
    "tags": ["plants", "homeassistant", "influxdb"],
    "timezone": "browser",
    "schemaVersion": 39,
    "version": 1,
    "refresh": "5m",
    "time": {"from": "now-7d", "to": "now"},
    "templating": {"list": []},
    "annotations": {"list": []},
    "editable": True,
    "panels": panels,
}

print(json.dumps(dashboard, indent=2))
