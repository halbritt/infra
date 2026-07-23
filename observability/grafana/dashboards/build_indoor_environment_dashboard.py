#!/usr/bin/env python3
"""Generate the indoor-environment Grafana dashboard JSON, reading the HA
appliance's InfluxDB add-on via the influx-ha datasource.

Ambient conditions across the house: temperature, humidity, barometric
pressure, light, dewpoint. Sensor set discovered 2026-07-23 (no CO2/PM/VOC
sensors exist on this install, so it's the temp/humidity/pressure/light family).
Labels come from each sensor's HA friendly name / user rename (there are no HA
areas assigned). Outdoor is included as a reference line, not indoor.

Installs to /var/lib/grafana/dashboards-homeassistant/ (the "Home Assistant"
folder provider), same as plant-moisture. Regenerate:
  python3 build_indoor_environment_dashboard.py > indoor-environment.json
"""
import json

DS = {"type": "influxdb", "uid": "influx-ha"}

# (label, measurement, entity_id)
TEMPS = [
    ("Indoor (Ecowitt)", "°F", "gw1200b_indoor_temperature"),
    ("Greenhouse",       "°F", "sonoff_snzb_02d_temperature"),
    ("Room (THS)",       "°F", "temperature_and_humidity_sensor_temperature"),
    ("AC (Midea)",       "°F", "midea_ac_temperature"),
    ("Dewpoint (indoor)","°F", "gw1200b_indoor_dewpoint"),
    ("Outdoor",          "°F", "sonoff_snzb_02wd_temperature"),
]
HUMS = [
    ("Indoor (Ecowitt)",   "%", "gw1200b_indoor_humidity"),
    ("Greenhouse",         "%", "sonoff_snzb_02d_humidity"),
    ("Room (THS)",         "%", "temperature_and_humidity_sensor_humidity"),
    ("Humidifier (Levoit)","%", "classic_300s_humidity"),
    ("Outdoor",            "%", "sonoff_snzb_02wd_humidity"),
]
LIGHTS = [
    ("Light sensor (LUMI)", "lx", "lumi_light_sensor"),
    ("Hall night light",    "lx", "hall_night_light_illuminance"),
]
PRESSURE = ("Barometric (relative)", "inHg", "gw1200b_relative_pressure")

_id = [0]
def nid():
    _id[0] += 1
    return _id[0]

def q(measurement, entity_id, alias, fn="mean", refid="A"):
    return {
        "datasource": DS, "refId": refid, "resultFormat": "time_series",
        "alias": alias, "rawQuery": True,
        "query": (f'SELECT {fn}("value") FROM "{measurement}" '
                  f"WHERE (\"entity_id\" = '{entity_id}') AND $timeFilter "
                  f"GROUP BY time($__interval) fill(none)"),
    }

def row(title, y):
    return {"type": "row", "title": title, "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "id": nid(), "panels": []}

def stat(label, measurement, entity_id, x, y, unit, w=4, h=4, steps=None):
    return {
        "type": "stat", "title": label, "datasource": DS, "id": nid(),
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        # Last 24h only + no header badge: a silent sensor reads "No data",
        # not a stale value (learned on the plant-moisture gauges).
        "timeFrom": "24h", "hideTimeOverride": True,
        "targets": [q(measurement, entity_id, label, fn="last")],
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "colorMode": "value", "graphMode": "area", "textMode": "auto"},
        "fieldConfig": {"defaults": {
            "unit": unit,
            "thresholds": {"mode": "absolute",
                           "steps": steps or [{"color": "blue", "value": None}]},
        }, "overrides": []},
    }

def ts(title, specs, x, y, w=24, h=8, unit="none", log=False):
    p = {
        "type": "timeseries", "title": title, "datasource": DS, "id": nid(),
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [q(m, e, lbl, refid=chr(65 + i)) for i, (lbl, m, e) in enumerate(specs)],
        "fieldConfig": {"defaults": {
            "unit": unit,
            "custom": {"drawStyle": "line", "lineInterpolation": "smooth",
                       "fillOpacity": 6, "showPoints": "never", "spanNulls": False},
            "color": {"mode": "palette-classic"},
        }, "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "bottom",
                               "calcs": ["last", "min", "max"]},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
    }
    if log:
        p["fieldConfig"]["defaults"]["custom"]["scaleDistribution"] = {"type": "log", "log": 10}
    return p

TEMP_STEPS = [{"color": "blue", "value": None}, {"color": "green", "value": 64},
              {"color": "orange", "value": 80}]
HUM_STEPS = [{"color": "orange", "value": None}, {"color": "green", "value": 30},
             {"color": "blue", "value": 65}]

panels = []
y = 0
panels.append(row("Now", y)); y += 1
panels.append(stat("Indoor Temp", "°F", "gw1200b_indoor_temperature", 0, y, "fahrenheit", steps=TEMP_STEPS))
panels.append(stat("Indoor Humidity", "%", "gw1200b_indoor_humidity", 4, y, "percent", steps=HUM_STEPS))
panels.append(stat("Barometric", *PRESSURE[1:], x=8, y=y, unit="pressureinhg"))
panels.append(stat("Light (LUMI)", "lx", "lumi_light_sensor", 12, y, "lux"))
panels.append(stat("Dewpoint", "°F", "gw1200b_indoor_dewpoint", 16, y, "fahrenheit"))
panels.append(stat("Outdoor Temp", "°F", "sonoff_snzb_02wd_temperature", 20, y, "fahrenheit"))
y += 4

panels.append(row("Temperature", y)); y += 1
panels.append(ts("Temperature (°F) — indoor rooms + outdoor reference", TEMPS, 0, y, unit="fahrenheit")); y += 8

panels.append(row("Humidity", y)); y += 1
panels.append(ts("Relative humidity (%)", HUMS, 0, y, unit="percent")); y += 8

panels.append(row("Pressure & Light", y)); y += 1
panels.append(ts("Barometric pressure (inHg)", [PRESSURE], 0, y, w=12, unit="pressureinhg"))
panels.append(ts("Illuminance (lux, log)", LIGHTS, 12, y, w=12, unit="lux", log=True)); y += 8

dashboard = {
    "uid": "indoor-environment",
    "title": "Indoor Environment — homeassistant (via InfluxDB)",
    "tags": ["environment", "homeassistant", "influxdb"],
    "timezone": "browser",
    "schemaVersion": 39,
    "version": 1,
    "refresh": "5m",
    "time": {"from": "now-2d", "to": "now"},
    "templating": {"list": []},
    "annotations": {"list": []},
    "editable": True,
    "panels": panels,
}

print(json.dumps(dashboard, indent=2))
