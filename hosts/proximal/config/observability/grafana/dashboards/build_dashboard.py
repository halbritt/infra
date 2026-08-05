#!/usr/bin/env python3
"""Generate the proximal PostgreSQL Grafana dashboard JSON (verified metric names)."""
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
        "refId": chr(65 + 0), "instant": instant, "format": fmt, "range": not instant,
    }

def targets(specs):
    out = []
    for i, (expr, legend) in enumerate(specs):
        t = {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": chr(65 + i)}
        out.append(t)
    return out

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

def table(title, expr, x, y, w=24, h=10, unit="ms"):
    return {
        "type": "table", "title": title, "datasource": DS, "id": nid(),
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [target(expr, "", instant=True, fmt="table")],
        "transformations": [
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "__name__": True, "job": True,
                                  "instance": True, "server": True, "Value #A": False},
                "renameByName": {"Value": "mean ms", "short_query": "query",
                                 "datname": "db", "usename": "role", "queryid": "queryid"},
            }},
        ],
        "fieldConfig": {"defaults": {"custom": {"align": "left"}}, "overrides": [
            {"matcher": {"id": "byName", "options": "mean ms"},
             "properties": [{"id": "unit", "value": unit},
                            {"id": "custom.cellOptions", "value": {"type": "color-background"}},
                            {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                                {"color": "green", "value": None}, {"color": "yellow", "value": 50},
                                {"color": "red", "value": 500}]}}]},
        ]},
        "options": {"showHeader": True, "sortBy": [{"displayName": "mean ms", "desc": True}]},
    }

y = 0
# --- Overview ---
panels.append(row("Overview", y)); y += 1
panels.append(stat("PG up", "pg_up", 0, y, w=4,
                   thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 1}]))
panels.append(stat("Backends (current)", "sum(pg_stat_database_numbackends)", 4, y, w=4,
                   thresholds=[{"color": "green", "value": None}, {"color": "yellow", "value": 70},
                               {"color": "red", "value": 90}]))
panels.append(stat("max_connections", "pg_settings_max_connections", 8, y, w=4))
panels.append(stat("Cache hit ratio",
                   "100 * sum(pg_stat_database_blks_hit) / clamp_min(sum(pg_stat_database_blks_hit) + sum(pg_stat_database_blks_read), 1)",
                   12, y, w=6, unit="percent",
                   thresholds=[{"color": "red", "value": None}, {"color": "yellow", "value": 95},
                               {"color": "green", "value": 99}]))
panels.append(stat("Long-running txns", "sum(pg_long_running_transactions)", 18, y, w=6,
                   thresholds=[{"color": "green", "value": None}, {"color": "yellow", "value": 1},
                               {"color": "red", "value": 5}]))
y += 4

# --- Activity & Connections ---
panels.append(row("Activity & Connections", y)); y += 1
panels.append(ts("Connections by database", [
    ("pg_stat_database_numbackends{datname!=\"\"}", "{{datname}}"),
    ("pg_settings_max_connections", "max_connections"),
], 0, y, unit="none", stack=False, fill=0,
    extra_overrides=[{"matcher": {"id": "byName", "options": "max_connections"},
                      "properties": [{"id": "custom.lineStyle", "value": {"dash": [10, 10], "fill": "dash"}},
                                     {"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]}]))
panels.append(ts("Transactions / s", [
    ("sum by (datname)(rate(pg_stat_database_xact_commit{datname!=\"\"}[$__rate_interval]))", "commit {{datname}}"),
    ("sum by (datname)(rate(pg_stat_database_xact_rollback{datname!=\"\"}[$__rate_interval]))", "rollback {{datname}}"),
], 12, y, unit="ops"))
y += 8
panels.append(ts("Deadlocks / s (rate)", [
    ("rate(pg_stat_database_deadlocks{datname!=\"\"}[$__rate_interval])", "{{datname}}"),
], 0, y, unit="ops", fill=0))
panels.append(ts("Temp file bytes / s", [
    ("rate(pg_stat_database_temp_bytes{datname!=\"\"}[$__rate_interval])", "{{datname}}"),
], 12, y, unit="Bps"))
y += 8

# --- Checkpoints & Buffers ---
panels.append(row("Checkpoints & Buffers", y)); y += 1
panels.append(ts("Checkpoints / s (requested should stay ~0)", [
    ("rate(pg_checkpointer_num_requested[$__rate_interval])", "requested (forced)"),
    ("rate(pg_checkpointer_num_timed[$__rate_interval])", "timed (scheduled)"),
], 0, y, unit="ops", fill=0))
panels.append(ts("Buffers / s", [
    ("rate(pg_bgwriter_buffers_alloc[$__rate_interval])", "alloc"),
    ("rate(pg_bgwriter_buffers_clean[$__rate_interval])", "bgwriter clean"),
    ("rate(pg_checkpointer_buffers_written[$__rate_interval])", "checkpoint written"),
], 12, y, unit="ops"))
y += 8

# --- Bloat & Longevity ---
panels.append(row("Bloat & Longevity (striatum#421 / pg-repack-bloated.timer)", y)); y += 1
panels.append(ts("Supervisor table size (total)", [
    ("pg_supervisor_tables_total_bytes", "{{table_name}}"),
], 0, y, unit="bytes"))
panels.append(ts("Supervisor dead tuples", [
    ("pg_supervisor_tables_dead_tuples", "{{table_name}}"),
], 12, y, unit="short"))
y += 8
panels.append(ts("XID wraparound age (% of 2^31)", [
    ("topk(10, max by (datname)(pg_database_wraparound_age_datfrozenxid_seconds)) / 2147483648 * 100", "{{datname}}"),
], 0, y, unit="percent", fill=0))
panels.append(ts("Supervisor heap vs index bytes", [
    ("pg_supervisor_tables_heap_bytes", "heap {{table_name}}"),
    ("pg_supervisor_tables_index_bytes", "index {{table_name}}"),
], 12, y, unit="bytes"))
y += 8

# --- Top queries ---
panels.append(row("Top Queries (pg_stat_statements)", y)); y += 1
panels.append(table("Top 15 statements by mean execution time",
                    "topk(15, pg_stat_statements_top_mean_exec_time_ms)", 0, y, w=24, h=10, unit="ms"))
y += 10

# --- Host ---
panels.append(row("Host (node_exporter)", y)); y += 1
panels.append(ts("CPU busy %", [
    ("100 * (1 - avg(rate(node_cpu_seconds_total{mode=\"idle\"}[$__rate_interval])))", "cpu busy"),
], 0, y, w=8, h=7, unit="percent"))
panels.append(ts("Memory used %", [
    ("100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)", "mem used"),
], 8, y, w=8, h=7, unit="percent"))
panels.append(ts("Filesystem free bytes (/)", [
    ("node_filesystem_avail_bytes{mountpoint=\"/\",fstype!=\"tmpfs\"}", "{{mountpoint}}"),
], 16, y, w=8, h=7, unit="bytes"))

dashboard = {
    "uid": "pg-proximal-health",
    "title": "PostgreSQL — proximal (17/main)",
    "tags": ["postgresql", "proximal", "striatum"],
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
