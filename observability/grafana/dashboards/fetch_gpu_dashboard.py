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

json.dump(data, open("/home/halbritt/git/proximal/observability/grafana/dashboards/nvidia-gpu-proximal.json", "w"))
print(f"OK title={data['title']!r} panels~={len(data.get('panels', []))} "
      f"templating_vars={[v.get('name') for v in data.get('templating', {}).get('list', [])]}")
