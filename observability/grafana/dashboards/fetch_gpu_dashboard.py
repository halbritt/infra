#!/usr/bin/env python3
"""Fetch Grafana 'NVIDIA GPU Metrics' (ID 14574, the utkuozdemir/nvidia_gpu_exporter
dashboard), pin it to our datasource + job, provision-ready."""
import json, urllib.request

DS_UID = "prometheus-proximal"
URL = "https://grafana.com/api/dashboards/14574/revisions/latest/download"

req = urllib.request.Request(URL, headers={"User-Agent": "curl/8"})
data = json.load(urllib.request.urlopen(req, timeout=45))

def fix(o):
    if isinstance(o, dict):
        if "datasource" in o:
            ds = o["datasource"]
            if isinstance(ds, str):
                if ds.startswith("$") or ds in ("", "default"):
                    o["datasource"] = {"type": "prometheus", "uid": DS_UID}
            elif isinstance(ds, dict):
                uid = ds.get("uid", "")
                if isinstance(uid, str) and uid.startswith("$"):
                    o["datasource"] = {"type": "prometheus", "uid": DS_UID}
            elif ds is None:
                o["datasource"] = {"type": "prometheus", "uid": DS_UID}
        for v in o.values():
            fix(v)
    elif isinstance(o, list):
        for v in o:
            fix(v)

fix(data)
data.pop("__inputs", None)
data.pop("__requires", None)
data["uid"] = "nvidia-gpu-proximal"
data["title"] = "NVIDIA GPU — proximal"
data["editable"] = True
data["refresh"] = "30s"

# Pin the datasource template var to ours; default job=gpu (our scrape job name).
for var in data.get("templating", {}).get("list", []):
    if var.get("type") == "datasource":
        var["current"] = {"text": "Prometheus", "value": DS_UID, "selected": True}
        var["query"] = "prometheus"
    if var.get("name") == "job":
        var["current"] = {"text": "gpu", "value": "gpu", "selected": True}

# Cross-GPU comparison panel: overlays every instance in job=gpu (proximal +
# peecee) so the two GPUs can be read side by side. The stock panels filter by
# the single-select $node/$gpu vars and only ever show one GPU; this one ignores
# them. Appended below the grid so a re-fetch from upstream keeps it.
def add_compare_panel(d):
    panels = d.setdefault("panels", [])
    next_y = max((p["gridPos"]["y"] + p["gridPos"]["h"] for p in panels if "gridPos" in p), default=0)
    next_id = max((p.get("id", 0) for p in panels), default=0) + 1
    panels.append({
        "id": next_id,
        "type": "timeseries",
        "title": "GPU Utilization — all GPUs (proximal vs peecee)",
        "description": "Every GPU in job=gpu overlaid for direct comparison; "
                       "ignores the $node/$gpu selectors above.",
        "datasource": {"type": "prometheus", "uid": DS_UID},
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": next_y},
        "fieldConfig": {
            "defaults": {
                "unit": "percentunit", "min": 0, "max": 1,
                "color": {"mode": "palette-classic"},
                "custom": {
                    "drawStyle": "line", "lineInterpolation": "smooth",
                    "lineWidth": 2, "fillOpacity": 10, "showPoints": "never",
                    "axisPlacement": "auto", "spanNulls": True,
                },
            },
            "overrides": [],
        },
        "options": {
            "legend": {"displayMode": "table", "placement": "bottom",
                       "showLegend": True, "calcs": ["mean", "max", "lastNotNull"]},
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
        "targets": [{
            "datasource": {"type": "prometheus", "uid": DS_UID},
            "expr": "nvidia_smi_utilization_gpu_ratio{job=\"$job\"}",
            "legendFormat": "{{instance}}",
            "refId": "A",
        }],
    })

add_compare_panel(data)

json.dump(data, open("/home/halbritt/git/proximal/observability/grafana/dashboards/nvidia-gpu-proximal.json", "w"))
print(f"OK title={data['title']!r} panels~={len(data.get('panels', []))} "
      f"templating_vars={[v.get('name') for v in data.get('templating', {}).get('list', [])]}")
