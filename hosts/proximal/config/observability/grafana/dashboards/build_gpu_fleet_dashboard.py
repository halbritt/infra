#!/usr/bin/env python3
"""Generate the gpu-fleet registry/lease Grafana dashboard JSON (PROXIMAL-5).

Every expr targets a pg_gpu_fleet_* series emitted by the dedicated second
postgres_exporter instance (:9188, database gpu_fleet — see
observability/exporter/queries-gpu-fleet.yaml) and verified live in Prometheus.
Alert thresholds mirror rules/infra-alerting.rules.yml (gpu_fleet_alerts):
routable == 0 pages; heartbeat age > 90s (2x the 45s live TTL) warns.

Regenerate: python3 dashboards/build_gpu_fleet_dashboard.py > dashboards/gpu-fleet-proximal.json
"""
import json

DS = {"type": "prometheus", "uid": "prometheus-proximal"}
panels = []
_id = [0]

def nid():
    _id[0] += 1
    return _id[0]

def target(expr, legend="", instant=False, fmt="time_series"):
    return {
        "datasource": DS, "expr": expr, "legendFormat": legend,
        "refId": "A", "instant": instant, "format": fmt, "range": not instant,
    }

def targets(specs):
    return [{"datasource": DS, "expr": expr, "legendFormat": legend, "refId": chr(65 + i)}
            for i, (expr, legend) in enumerate(specs)]

def row(title, y):
    return {"type": "row", "title": title, "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "id": nid(), "panels": []}

def stat(title, expr, x, y, w=4, h=4, unit="none", thresholds=None, legend=""):
    steps = thresholds or [{"color": "green", "value": None}]
    return {
        "type": "stat", "title": title, "datasource": DS, "id": nid(),
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [target(expr, legend, instant=True)],
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "colorMode": "value", "graphMode": "area", "textMode": "auto", "orientation": "auto"},
        "fieldConfig": {"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps}},
                        "overrides": []},
    }

def ts(title, specs, x, y, w=12, h=8, unit="none", extra_overrides=None, stack=False, fill=10):
    return {
        "type": "timeseries", "title": title, "datasource": DS, "id": nid(),
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": targets(specs),
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {"drawStyle": "line", "lineInterpolation": "smooth",
                           "fillOpacity": fill, "showPoints": "never", "spanNulls": True,
                           "stacking": {"mode": "normal" if stack else "none", "group": "A"}},
                "color": {"mode": "palette-classic"},
            },
            "overrides": extra_overrides or [],
        },
        "options": {"legend": {"displayMode": "table", "placement": "bottom",
                               "calcs": ["last", "max"]},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
    }

def table(title, expr, x, y, w=24, h=8):
    return {
        "type": "table", "title": title, "datasource": DS, "id": nid(),
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [target(expr, "", instant=True, fmt="table")],
        "transformations": [
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "job": True,
                                  "instance": True, "cluster": True, "server": True},
                "renameByName": {"Value": "heartbeat age (s)"},
            }},
        ],
        "fieldConfig": {"defaults": {"custom": {"align": "left"}}, "overrides": [
            {"matcher": {"id": "byName", "options": "heartbeat age (s)"},
             "properties": [{"id": "unit", "value": "s"},
                            {"id": "custom.cellOptions", "value": {"type": "color-background"}},
                            {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                                {"color": "green", "value": None}, {"color": "yellow", "value": 45},
                                {"color": "red", "value": 90}]}}]},
        ]},
        "options": {"showHeader": True, "sortBy": [{"displayName": "heartbeat age (s)", "desc": True}]},
    }

y = 0
# --- Overview: the four numbers that summarize routability ---
panels.append(row("Fleet overview", y)); y += 1
panels.append(stat("Routable slots", "pg_gpu_fleet_summary_routable_slots", 0, y, w=4,
                   thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 1}]))
panels.append(stat("Live slots (45s TTL)", "pg_gpu_fleet_summary_live_slots", 4, y, w=4,
                   thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 1}]))
panels.append(stat("Registered slots", "pg_gpu_fleet_summary_slots_total", 8, y, w=4))
panels.append(stat("Active exclusive leases", "pg_gpu_fleet_summary_active_leases", 12, y, w=4,
                   thresholds=[{"color": "green", "value": None}]))
panels.append(stat("Routable free VRAM", "pg_gpu_fleet_summary_routable_vram_free_mib", 16, y, w=8, unit="mbytes",
                   thresholds=[{"color": "red", "value": None}, {"color": "yellow", "value": 2000},
                               {"color": "green", "value": 8000}]))
y += 4

# --- Lifecycle & heartbeats ---
panels.append(row("Lifecycle & heartbeats", y)); y += 1
panels.append(ts("Slots by status (zero-filled enum)", [
    ("pg_gpu_fleet_status_slots", "{{status}}"),
], 0, y, unit="short", fill=0))
panels.append(ts("Heartbeat age per slot (45s = live TTL, 90s = alert)", [
    ("pg_gpu_fleet_slot_heartbeat_age_seconds", "{{node}} {{endpoint_url}}/{{slot_id}}"),
], 12, y, unit="s", fill=0))
y += 8
panels.append(table("Slot registry (live read of gpu_slots)",
                    "pg_gpu_fleet_slot_heartbeat_age_seconds", 0, y, w=24, h=8))
y += 8

# --- Leases & capacity ---
panels.append(row("Exclusive leases & VRAM", y)); y += 1
panels.append(ts("Lease TTL remaining (self-renewing holders keep topping up)", [
    ("pg_gpu_fleet_lease_ttl_remaining_seconds", "{{holder}} @ {{node}}/{{slot_id}}"),
], 0, y, unit="s", fill=0))
panels.append(ts("Free VRAM per slot", [
    ("pg_gpu_fleet_slot_vram_free_mib", "{{node}} {{endpoint_url}}/{{slot_id}}"),
    ("pg_gpu_fleet_slot_vram_total_mib", "total {{node}} {{endpoint_url}}/{{slot_id}}"),
], 12, y, unit="mbytes", fill=0))
y += 8

dashboard = {
    "uid": "gpu-fleet-proximal",
    "title": "gpu-fleet — registry & leases",
    "tags": ["gpu-fleet", "proximal", "postgresql"],
    "timezone": "browser",
    "schemaVersion": 39,
    "version": 1,
    "refresh": "30s",
    "time": {"from": "now-6h", "to": "now"},
    "templating": {"list": []},
    "annotations": {"list": []},
    "editable": True,
    "panels": panels,
}

print(json.dumps(dashboard, indent=2))
