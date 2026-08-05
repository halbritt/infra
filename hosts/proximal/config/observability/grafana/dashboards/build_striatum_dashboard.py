#!/usr/bin/env python3
"""Generate the Striatum daemon (RFC 0137) Grafana dashboard JSON.

Panels map 1:1 to the RFC 0137 §3 metric taxonomy and the committed Prometheus
rules (striatum-{recording,alerting}.rules.yml). Datasource is the proximal
Prometheus (uid prometheus-proximal); every expr targets a family the striatumd
exporter actually emits (verified live at 127.0.0.1:9464/metrics).

Two PromQL conventions are load-bearing and copied from the rule files:
  * run_wedge_age and liveness_deadline_margin are PER-TICK GAUGE histograms
    (rebuilt each fold), so histogram_quantile reads their _bucket series
    DIRECTLY — never through rate(), which would mis-read the snapshot's natural
    rise-and-fall as counter resets.
  * cardinality_clipped is a per-tick SNAPSHOT despite the _total suffix, so it is
    read with max_over_time, never increase().

Regenerate: python3 dashboards/build_striatum_dashboard.py > dashboards/striatum-proximal.json
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
    out = []
    for i, (expr, legend) in enumerate(specs):
        out.append({"datasource": DS, "expr": expr, "legendFormat": legend,
                    "refId": chr(65 + i)})
    return out


def row(title, y):
    return {"type": "row", "title": title, "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "id": nid(), "panels": []}


def stat(title, expr, x, y, w=4, h=4, unit="none", thresholds=None, legend="", desc=""):
    steps = thresholds or [{"color": "green", "value": None}]
    return {
        "type": "stat", "title": title, "datasource": DS, "id": nid(),
        "description": desc,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [target(expr, legend, instant=True)],
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "colorMode": "value", "graphMode": "area", "textMode": "auto", "orientation": "auto"},
        "fieldConfig": {"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps}},
                        "overrides": []},
    }


def ts(title, specs, x, y, w=12, h=8, unit="none", extra_overrides=None, stack=False,
       fill=10, desc="", thresholds=None):
    defaults = {
        "unit": unit,
        "custom": {"drawStyle": "line", "lineInterpolation": "smooth",
                   "fillOpacity": fill, "showPoints": "never", "spanNulls": True,
                   "stacking": {"mode": "normal" if stack else "none", "group": "A"}},
        "color": {"mode": "palette-classic"},
    }
    if thresholds:
        defaults["thresholds"] = {"mode": "absolute", "steps": thresholds}
        defaults["custom"]["thresholdsStyle"] = {"mode": "line"}
    return {
        "type": "timeseries", "title": title, "datasource": DS, "id": nid(),
        "description": desc,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": targets(specs),
        "fieldConfig": {"defaults": defaults, "overrides": extra_overrides or []},
        "options": {"legend": {"displayMode": "table", "placement": "bottom",
                               "calcs": ["last", "max"]},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
    }


GREEN = {"color": "green", "value": None}
y = 0

# --- SLIs (the page-worthy signals at a glance) ---
panels.append(row("SLIs — striatumd health", y)); y += 1
panels.append(stat("Necrosis (1h)", "sum(increase(striatum_necrosis_total[1h]))", 0, y, w=4,
                   desc="Confirmed-dead uncontrolled terminations in the last hour. Any nonzero value is uncontrolled death (alert: NecrosisRate).",
                   thresholds=[GREEN, {"color": "red", "value": 0.5}]))
panels.append(stat("Doctor problems", "sum(striatum_doctor_problems) or vector(0)", 4, y, w=4,
                   desc="Open doctor integrity problems by static check class. >0 is a stop-and-fix (alert: DoctorRed).",
                   thresholds=[GREEN, {"color": "red", "value": 0.5}]))
panels.append(stat("Stranded supervisors", "striatum_stranded_supervisors", 8, y, w=4,
                   desc="Supervisors attached to terminal runs — the #417 phantom-supervisor storm signal (alert: SupervisorOriginFlood at >50).",
                   thresholds=[GREEN, {"color": "yellow", "value": 1}, {"color": "red", "value": 50}]))
panels.append(stat("Lifecycle balance", "striatum_lifecycle_balance", 12, y, w=4,
                   desc="Terminal transitions unaccounted for in apoptosis or necrosis — a runner blind spot / conservation-law violation (alert: LifecycleBalanceNonzero).",
                   thresholds=[GREEN, {"color": "red", "value": 0.5}]))
panels.append(stat("Snapshot age", "striatum_metrics_snapshot_age_seconds", 16, y, w=4, unit="s",
                   desc="Seconds since the metrics snapshot was folded at the recovery sweep tick. Stale means the reconcile loop may be wedged (alert: MetricsSnapshotStale at >300s).",
                   thresholds=[GREEN, {"color": "yellow", "value": 300}, {"color": "red", "value": 600}]))
panels.append(stat("Tick errored", "striatum_metrics_tick_status{status=\"error\"}", 20, y, w=4,
                   desc="1 when the sweep tick that folded the current snapshot errored; numbers are then carried-forward last-good (alert: MetricsTickErrored).",
                   thresholds=[GREEN, {"color": "red", "value": 0.5}]))
y += 4

# --- The apoptosis/necrosis spine ---
panels.append(row("Lifecycle spine — apoptosis vs necrosis", y)); y += 1
panels.append(ts("Necrosis rate by origin/reason", [
    ("sum by (origin, reason) (rate(striatum_necrosis_total[$__rate_interval]))", "{{origin}} / {{reason}}"),
], 0, y, unit="cps", fill=0,
    desc="Confirmed-dead uncontrolled terminations. The confirmed-dead classes only (agent_pid_dead, agent_exited_unsealed, recovery_exhausted); liveness_deadline_missed is excluded by design (F-A6)."))
panels.append(ts("Apoptosis rate by origin/reason", [
    ("sum by (origin, reason) (rate(striatum_apoptosis_total[$__rate_interval]))", "{{origin}} / {{reason}}"),
], 12, y, unit="cps", stack=True,
    desc="Healthy programmed self-terminations — never confused with damage (the terminator declares intent at the lifecycle-ending code site)."))
y += 8

# --- Pre-necrosis forewarning: wedge + liveness ---
panels.append(row("Forewarning — wedge age & liveness margin", y)); y += 1
panels.append(ts("Run wedge-age p99 by origin", [
    ("histogram_quantile(0.99, sum by (le, origin) (striatum_run_wedge_age_seconds_bucket))", "p99 {{origin}}"),
], 0, y, unit="s",
    desc="Time since a non-terminal run last advanced a job state. PER-TICK gauge histogram — buckets read directly, NOT through rate(). Alert WedgeAgeTail fires at p99 > 1h.",
    thresholds=[GREEN, {"color": "red", "value": 3600}]))
panels.append(ts("Liveness-deadline margin p05 by origin", [
    ("histogram_quantile(0.05, sum by (le, origin) (striatum_liveness_deadline_margin_seconds_bucket))", "p05 {{origin}}"),
], 12, y, unit="s",
    desc="Seconds of margin to the nearest liveness deadline; negative once elapsed. The low tail sliding toward zero forewarns misses before they become necrosis. PER-TICK gauge histogram. Alert LivenessMarginCollapse fires at p05 < 60s.",
    thresholds=[{"color": "red", "value": None}, {"color": "yellow", "value": 60}, {"color": "green", "value": 300}]))
y += 8

# --- Supervisor flood (#417) + run inventory ---
panels.append(row("Supervisor flood (#417) & run inventory", y)); y += 1
panels.append(ts("Supervisor-origin churn & stranded count", [
    ("sum (rate(striatum_apoptosis_total{origin=\"supervisor\"}[$__rate_interval]))", "supervisor apoptosis rate"),
    ("striatum_stranded_supervisors", "stranded supervisors"),
], 0, y, unit="none", fill=0,
    desc="The #417 reconcile-storm signal: a stranded-supervisor pileup and/or a flood of supervisor-origin lifecycle churn. Alert SupervisorOriginFlood: stranded>50 or supervisor apoptosis rate>5."))
panels.append(ts("Runs by lifecycle state", [
    ("striatum_runs", "{{state}}"),
], 12, y, unit="short", stack=True,
    desc="Run count grouped by lifecycle state; unknown states bucket to 'other'."))
y += 8

# --- Leases & non-terminal liveness events (F-A6) ---
panels.append(row("Leases & liveness events", y)); y += 1
panels.append(ts("Lease transitions rate by to/reason", [
    ("sum by (to, reason) (rate(striatum_lease_transitions_total[$__rate_interval]))", "{{to}} / {{reason}}"),
], 0, y, unit="cps",
    desc="Lease state churn. to=\"stale_lease\" rate is the primary stale-lease storm signal; requeue/transfer reasons surface dead-agent-recovery thrash."))
panels.append(ts("Liveness-deadline events rate by reason (F-A6)", [
    ("sum by (reason) (rate(striatum_liveness_deadline_events_total[$__rate_interval]))", "{{reason}}"),
], 12, y, unit="cps", fill=0,
    desc="Reversible liveness-deadline observations (deadline_missed / recovered) — the non-terminal home for liveness stalls. Outside the apoptosis/necrosis conservation law by design (F-A6); a reversible stall moves these, never necrosis_total."))
y += 8

# --- Exporter meta / data-quality ---
panels.append(row("Exporter health & data quality", y)); y += 1
panels.append(ts("Metrics snapshot age", [
    ("striatum_metrics_snapshot_age_seconds", "snapshot age"),
], 0, y, w=8, h=7, unit="s", fill=0,
    desc="Staleness SLI. >300s means the sweep tick has not refolded; scrapers serve last-good numbers (alert: MetricsSnapshotStale).",
    thresholds=[GREEN, {"color": "red", "value": 300}]))
panels.append(ts("Fold tick status", [
    ("striatum_metrics_tick_status", "{{status}}"),
], 8, y, w=8, h=7, unit="short", fill=0,
    desc="Status of the sweep tick that folded the current snapshot: one of ok / partial / error (value 1 for the current status)."))
panels.append(ts("Cardinality clipped (per family)", [
    ("sum (max_over_time(striatum_metrics_cardinality_clipped_total[$__interval]))", "clipped tuples"),
], 16, y, w=8, h=7, unit="short", fill=0,
    desc="Distinct label tuples collapsed to the 'other' bucket by the per-family series budget. Per-tick SNAPSHOT — read with max_over_time, NOT increase(). >0 means a family's dimensions were silently lost (alert: MetricsCardinalityClipped)."))
y += 7

# --- Doctor detail ---
panels.append(row("Doctor & provenance (consent-gated)", y)); y += 1
panels.append(ts("Open doctor problems by class", [
    ("striatum_doctor_problems", "{{class}}"),
], 0, y, w=8, h=7, unit="short", fill=0,
    desc="Open doctor integrity problems by STATIC check class (never dynamic run/gate/supervisor ids). Empty = green."))
panels.append(ts("Repo metrics consent by bucket", [
    ("striatum_metrics_repo_consent", "{{bucket}}"),
], 8, y, w=8, h=7, unit="short", fill=0,
    desc="Per-repo provenance-metrics consent state by salted bucket; 1 when consented, 0 otherwise. Gates the repo_runs family below (RFC 0137 §4)."))
panels.append(ts("Per-repo runs by state (consent-gated)", [
    ("sum by (state) (striatum_repo_runs)", "{{state}}"),
], 16, y, w=8, h=7, unit="short", stack=True,
    desc="Per-repo run count by salted bucket and lifecycle state — only present for consented repos (consent-gated provenance family)."))
y += 7

dashboard = {
    "uid": "striatum-proximal",
    "title": "Striatum daemon — proximal (RFC 0137)",
    "tags": ["striatum", "proximal", "rfc-0137", "exporter"],
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
