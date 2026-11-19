#!/usr/bin/env python3
"""cyber-escalation-watch — breadth index + tripwire watch for state-level cyber escalation.

Two instruments, deliberately separate:

  1. tripwire   discrete, citable strategic events (mass exploitation of a perimeter
                product, a state attribution of destructive/sabotage operations).
                Any hit raises ORANGE immediately.
  2. index      per-domain z-scores against the domain's own trailing baseline.
                A domain only counts as breached at >=2 sigma; escalation needs
                corroboration across *independent* domains, so a single cloud
                provider outage (one domain, one vendor) can never fire alone.

Output contract (see skill automation/cron-watchdogs): silent stdout = no change.
Non-empty stdout = an alert, delivered verbatim by cron. Exit 0 always.

Env overrides: CEW_STATE_DIR, CEW_CHANNEL, CEW_DRY.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

STATE_DIR = os.environ.get("CEW_STATE_DIR", os.path.expanduser("~/.local/share/cyber-escalation-watch"))
DB_PATH = os.path.join(STATE_DIR, "history.db")
CACHE_DIR = os.path.join(STATE_DIR, "cache")
CHANNEL = os.environ.get("CEW_CHANNEL", "slack:#ai-blather")
DRY = os.environ.get("CEW_DRY") == "1"
UA = "hermes-proximal/1.0 (cyber-escalation-watch)"

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
EPSS_URL = "https://api.first.org/data/v1/epss"
CISA_NEWS = "https://www.cisa.gov/news.xml"
CERTFR_AVIS = "https://www.cert.ssi.gouv.fr/avis/feed/"
RANSOMLOOK = "https://www.ransomlook.io/api/recent"
RIPESTAT_VIS = "https://stat.ripe.net/data/visibility/data.json?resource="

# Anycast name-resolution / CDN canaries: if these stop being visible to RIS
# peers, something structural is wrong with the internet's plumbing.
PREFIXES = ["1.1.1.0/24", "8.8.8.0/24", "9.9.9.0/24", "208.67.222.0/24", "104.16.0.0/12"]

# Posture keywords: conflict / destructive / attribution language only. Generic
# "critical infrastructure" talk is allowed to sit in the baseline via z-scoring.
STRONG_KW = [
    "sabotage", "wiper", "destructive", "destructif", "attribution", "attribu",
    "state-sponsored", "state sponsored", "étatique", "apt", "ics", "scada",
    "operational technology", "critical infrastructure", "infrastructure critique",
    "mass exploitation", "actively exploited", "emergency directive",
]

GREEN, YELLOW, ORANGE, RED = 0, 1, 2, 3
LEVEL_NAME = {GREEN: "GREEN", YELLOW: "YELLOW", ORANGE: "ORANGE", RED: "RED"}
LEVEL_ICON = {GREEN: "🟢", YELLOW: "🟡", ORANGE: "🟠", RED: "🔴"}

Z_YELLOW = 2.0
Z_ORANGE = 3.0
MIN_BUCKETS = 8          # weekly buckets needed before a domain is scored at all
BUCKETS = 13             # trailing weekly buckets used for the baseline
DEESCALATE_DAYS = 5      # clean days before stepping down
YELLOW_HOLD_HOURS = 20   # breach must persist ~a day before YELLOW
BLIND_HOURS = 6          # no successful collection for this long = monitor is blind


# ---------------------------------------------------------------- http helpers

def http_get(url: str, timeout: int = 30, retries: int = 2) -> bytes:
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001 - per-feed failure must not be fatal
            last = exc
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


def cached(name: str, max_age_h: float, fetch):
    """Return parsed cache if fresh, else fetch + store. Cache is per-file JSON."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, name)
    if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < max_age_h * 3600:
        try:
            with open(path) as fh:
                return json.load(fh)
        except Exception:  # noqa: BLE001
            pass
    value = fetch()
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(value, fh)
    os.replace(tmp, path)
    return value


# --------------------------------------------------------------------- feeds

def fetch_kev() -> dict:
    """{cve_id: {"added": "YYYY-MM-DD", "vendor": str, "product": str}}"""
    raw = json.loads(http_get(KEV_URL, timeout=60))
    out = {}
    for v in raw.get("vulnerabilities", []):
        cve = v.get("cveID")
        added = v.get("dateAdded")
        if cve and added:
            out[cve] = {
                "added": added,
                "vendor": v.get("vendorProject", ""),
                "product": v.get("product", ""),
                "name": v.get("vulnerabilityName", ""),
            }
    return out


def fetch_epss(cves: list[str]) -> dict:
    """{cve: epss_float} — batched, FIRST API caps at 100 per call."""
    out = {}
    for i in range(0, len(cves), 90):
        chunk = cves[i:i + 90]
        url = f"{EPSS_URL}?cve={','.join(chunk)}&envelope=false"
        try:
            payload = json.loads(http_get(url, timeout=25))
        except Exception as exc:  # noqa: BLE001
            print(f"epss: {exc}", file=sys.stderr)
            continue
        # FIRST returns a bare list when envelope=false, {"data": [...]} otherwise
        rows = payload.get("data", []) if isinstance(payload, dict) else payload
        for row in rows if isinstance(rows, list) else []:
            try:
                out[row["cve"]] = float(row["epss"])
            except (KeyError, TypeError, ValueError):
                continue
    return out


def parse_feed(xml_bytes: bytes) -> list[dict]:
    """Tolerant RSS 2.0 / Atom item extraction."""
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        print(f"feed parse: {exc}", file=sys.stderr)
        return items
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        rec = {"title": "", "link": "", "ts": None}
        for child in node:
            ctag = child.tag.split("}")[-1]
            text = (child.text or "").strip()
            if ctag == "title":
                rec["title"] = text
            elif ctag == "link":
                rec["link"] = text or child.get("href", "")
            elif ctag in ("pubDate", "published", "updated"):
                try:
                    rec["ts"] = parsedate_to_datetime(text).astimezone(timezone.utc).isoformat()
                except Exception:  # noqa: BLE001 - some feeds use ISO-8601
                    try:
                        rec["ts"] = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
                    except Exception:  # noqa: BLE001
                        pass
        if rec["title"]:
            items.append(rec)
    return items


def fetch_advisories() -> list[dict]:
    out = []
    for url in (CISA_NEWS, CERTFR_AVIS):
        try:
            out.extend(parse_feed(http_get(url, timeout=30)))
        except Exception as exc:  # noqa: BLE001
            print(f"advisories {url}: {exc}", file=sys.stderr)
    return out


def fetch_ransomware_posts() -> list[str]:
    """[discovered ISO dates] from ransomlook (live, ~100 most recent posts).

    NOTE: ransomwatch's posts.json — the obvious historical source — went stale at
    2025-06-16, so it silently reported "0 posts/week" forever and would have been
    counted as a healthy domain. Extortion history therefore starts at install
    time; this domain is cold until it accumulates MIN_BUCKETS daily buckets.
    """
    raw = json.loads(http_get(RANSOMLOOK, timeout=45))
    dates = []
    for row in raw if isinstance(raw, list) else []:
        d = (row.get("discovered") or "")[:10]
        if len(d) == 10:
            dates.append(d)
    return dates


def fetch_visibility(prefix: str) -> float | None:
    """Best origin visibility for the prefix, 0..1."""
    try:
        payload = json.loads(http_get(RIPESTAT_VIS + prefix, timeout=25))
        best = None
        for entry in payload.get("data", {}).get("visibilities", []):
            for fam in ("v4", "v6"):
                for o in entry.get(fam, []) or []:
                    vis = o.get("visibility")
                    if vis is None:
                        continue
                    if best is None or vis > best:
                        best = float(vis)
        return best
    except Exception as exc:  # noqa: BLE001
        print(f"ripestat {prefix}: {exc}", file=sys.stderr)
        return None


# ------------------------------------------------------------------ storage

def db() -> sqlite3.Connection:
    os.makedirs(STATE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS samples(
        ts TEXT, domain TEXT, metric TEXT, value REAL, z REAL, hot INTEGER)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS advisories(
        link TEXT PRIMARY KEY, title TEXT, ts TEXT, feed TEXT, hit INTEGER)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS routing(
        ts TEXT, prefix TEXT, visibility REAL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS levels(
        ts TEXT PRIMARY KEY, computed INTEGER, level INTEGER, reasons TEXT)""")
    conn.execute("CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    return conn


def kv_get(conn, key, default=None):
    row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except Exception:  # noqa: BLE001
        return default


def kv_set(conn, key, value):
    conn.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, json.dumps(value)))
    conn.commit()


# ------------------------------------------------------------------ scoring

def weekly_buckets(dates: list[str], end: datetime, weeks: int = BUCKETS) -> list[int]:
    """Counts per 7-day bucket, newest first, ending at `end` (exclusive).

    Buckets reaching before the oldest observation are dropped — a zero-filled
    bucket from missing history must never be read as a calm week.
    """
    if not dates:
        return []
    oldest = min(dates)
    counts = []
    for i in range(weeks):
        hi = (end - timedelta(days=7 * i)).date()
        lo = hi - timedelta(days=7)
        if lo.isoformat() < oldest:
            break
        counts.append(sum(1 for d in dates if lo.isoformat() <= d < hi.isoformat()))
    return counts


def daily_buckets(dates: list[str], end: datetime, days: int = 30) -> list[int]:
    """Counts per 1-day bucket, newest first. Same coverage guard as weekly_buckets."""
    if not dates:
        return []
    oldest = min(dates)
    counts = []
    for i in range(days):
        hi = (end - timedelta(days=i)).date()
        lo = hi - timedelta(days=1)
        if lo.isoformat() < oldest:
            break
        counts.append(sum(1 for d in dates if lo.isoformat() <= d < hi.isoformat()))
    return counts


def zscore(current: float, prior: Sequence[float], floor_sd: float = 0.5) -> float | None:
    """z of `current` against prior buckets. None when there is not enough history."""
    if len(prior) < MIN_BUCKETS:
        return None
    mean = statistics.fmean(prior)
    sd = statistics.pstdev(prior) if len(prior) > 1 else 0.0
    sd = max(sd, floor_sd)
    return (current - mean) / sd


def score_domain(conn, domain, metric, value, prior, floor_sd=0.5):
    z = zscore(value, prior, floor_sd)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT INTO samples(ts,domain,metric,value,z,hot) VALUES(?,?,?,?,?,?)",
                 (now, domain, metric, value, z, 0 if z is None else 1))
    return {"domain": domain, "metric": metric, "value": value,
            "baseline_mean": statistics.fmean(prior) if prior else None,
            "buckets": len(prior), "z": z}


# --------------------------------------------------------------------- main

def collect(conn) -> tuple[list[dict], list[str], list[str]]:
    """Returns (domain results, tripwires, errors)."""
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    results, tripwires, errors = [], [], []

    # --- D1 exploitation tempo: KEV additions per week, EPSS-weighted tripwire
    kev = {}
    try:
        kev = cached("kev.json", 20, fetch_kev)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"kev: {exc}")
    if kev:
        added_dates = sorted(v["added"] for v in kev.values())
        recent = {c: v for c, v in kev.items() if v["added"] >= (now - timedelta(days=7)).date().isoformat()}
        prior = weekly_buckets(added_dates, now)[1:]  # skip the current (partial) week
        res = score_domain(conn, "exploitation", "kev_adds_7d", len(recent), prior, floor_sd=1.0)
        results.append(res)
        if recent:
            epss = fetch_epss(sorted(recent))
            hot = [(c, epss.get(c, 0.0)) for c in recent if epss.get(c, 0.0) >= 0.7]
            if len(hot) >= 3:
                tripwires.append(
                    "mass exploitation: %d KEV additions in 7d with EPSS>=0.7 (%s)" % (
                        len(hot), ", ".join(f"{c} {s:.2f}" for c, s in hot[:6])))
            top = sorted(((epss.get(c, 0.0), c) for c in recent), reverse=True)[:3]
            res["top_epss"] = top

    # --- D2 extortion tempo: ransomware leak-site posts per day
    try:
        posts = cached("ransomlook.json", 3, fetch_ransomware_posts)
        prior = daily_buckets(posts, now)[1:]
        cur = sum(1 for d in posts if d >= (now - timedelta(days=1)).date().isoformat())
        results.append(score_domain(conn, "extortion", "posts_24h", cur, prior, floor_sd=8.0))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ransomlook: {exc}")

    # --- D3 government posture: conflict/attribution language in advisories
    try:
        for item in fetch_advisories():
            text = item["title"].lower()
            hit = int(any(k in text for k in STRONG_KW))
            conn.execute("INSERT OR IGNORE INTO advisories(link,title,ts,feed,hit) VALUES(?,?,?,?,?)",
                         (item["link"] or item["title"], item["title"], item["ts"], "feed", hit))
            if hit and item["ts"] and item["ts"] >= (now - timedelta(hours=36)).isoformat():
                if any(k in text for k in ("sabotage", "wiper", "destructive", "destructif", "attribution", "attribu")):
                    tripwires.append(f"advisory: {item['title'][:110]} ({item['ts'][:10]})")
        conn.commit()
        rows = conn.execute("SELECT substr(ts,1,10) FROM advisories WHERE hit=1 AND ts IS NOT NULL").fetchall()
        prior = weekly_buckets([r[0] for r in rows], now)[1:]
        cur = sum(1 for r in rows if r[0] >= (now - timedelta(days=7)).date().isoformat())
        results.append(score_domain(conn, "posture", "conflict_advisories_7d", cur, prior, floor_sd=1.0))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"advisories: {exc}")

    # --- D4 routing visibility: worst anycast canary drop vs its own baseline
    drops = []
    for prefix in PREFIXES:
        vis = fetch_visibility(prefix)
        if vis is None:
            continue
        conn.execute("INSERT INTO routing(ts,prefix,visibility) VALUES(?,?,?)", (now.isoformat(), prefix, vis))
        hist = [r[0] for r in conn.execute(
            "SELECT visibility FROM routing WHERE prefix=? AND ts >= ?",
            (prefix, (now - timedelta(days=14)).isoformat())).fetchall()]
        z = zscore(1.0 - vis, [1.0 - h for h in hist[:-1]], floor_sd=0.02) if len(hist) >= MIN_BUCKETS else None
        if z is not None:
            drops.append((z, prefix, vis))
    conn.commit()
    if drops:
        z, prefix, vis = max(drops)
        results.append({"domain": "routing", "metric": "worst_visibility_drop", "value": vis,
                        "baseline_mean": None, "buckets": len(drops), "z": z, "prefix": prefix})
        conn.execute("INSERT INTO samples(ts,domain,metric,value,z,hot) VALUES(?,?,?,?,?,1)",
                     (now.isoformat(), "routing", f"visibility:{prefix}", vis, z))
    else:
        results.append({"domain": "routing", "metric": "worst_visibility_drop", "value": None,
                        "baseline_mean": None, "buckets": 0, "z": None})

    return results, tripwires, errors


def evaluate(conn, results: list[dict], tripwires: list[str], now: datetime):
    hot = [r for r in results if r["z"] is not None]
    breached_y = [r for r in hot if r["z"] >= Z_YELLOW]
    breached_o = [r for r in hot if r["z"] >= Z_ORANGE]
    reasons = []

    computed = GREEN
    if tripwires:
        computed = ORANGE
        reasons.extend(tripwires)
    elif len(hot) >= 2 and len(breached_o) >= min(3, len(hot)):
        computed = ORANGE
    elif len(breached_y) >= 2:
        # must persist ~a day before it counts: one noisy day is not a trend
        first = kv_get(conn, "yellow_since")
        if not first:
            kv_set(conn, "yellow_since", now.isoformat())
            reasons.append("yellow condition met (holding %dh)" % YELLOW_HOLD_HOURS)
        elif (now - datetime.fromisoformat(first)) >= timedelta(hours=YELLOW_HOLD_HOURS):
            computed = YELLOW
        else:
            reasons.append("yellow condition met (holding since %s)" % first[:16])
    else:
        kv_set(conn, "yellow_since", None)

    return computed, reasons, hot, breached_y


def describe(results: list[dict], tripwires: list[str], errors: list[str]) -> str:
    lines = []
    for r in results:
        if r["z"] is None:
            lines.append(f"• {r['domain']}: cold ({r['buckets']}/{MIN_BUCKETS} buckets, {r['value']})")
        else:
            base = "" if r["baseline_mean"] is None else f", baseline {r['baseline_mean']:.1f}"
            lines.append(f"• {r['domain']}: {r['value']} ({r['metric']}, z={r['z']:+.1f}{base})")
    if tripwires:
        lines.append("tripwires: " + "; ".join(tripwires))
    if errors:
        lines.append("feed errors: " + "; ".join(errors[:3]))
    return "\n".join(lines)


def send(text: str) -> bool:
    if DRY:
        print(text)
        return True
    exe = shutil.which("hermes") or os.path.expanduser("~/.local/bin/hermes")
    try:
        p = subprocess.run([exe, "send", "--to", CHANNEL, text],
                           capture_output=True, text=True, timeout=90)
        if p.returncode != 0:
            print(f"send failed rc={p.returncode}: {p.stderr[:300]}", file=sys.stderr)
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"send failed: {exc}", file=sys.stderr)
        return False


def main() -> int:
    now = datetime.now(timezone.utc)
    conn = db()

    if "--status" in sys.argv:
        results, tripwires, errors = collect(conn)
        level = kv_get(conn, "level", GREEN)
        print(f"level={LEVEL_NAME[level]}  last_ok={kv_get(conn, 'last_ok_ts')}")
        print(describe(results, tripwires, errors))
        return 0

    level = kv_get(conn, "level", GREEN)
    results, tripwires, errors = collect(conn)

    ok = sum(1 for r in results if r["value"] is not None)
    if ok >= 2:
        kv_set(conn, "last_ok_ts", now.isoformat())

    computed, reasons, hot, breached = evaluate(conn, results, tripwires, now)
    body = describe(results, tripwires, errors)
    alert = None

    if computed > level:
        alert = (f"{LEVEL_ICON[computed]} *{LEVEL_NAME[computed]}* — cyber-escalation index "
                 f"{LEVEL_NAME[level]} → {LEVEL_NAME[computed]}\n"
                 f"{len(breached)}/{len(hot)} hot domains ≥{Z_YELLOW}σ\n{body}")
        kv_set(conn, "level", computed)
        kv_set(conn, "deesc_since", None)
        level = computed
    elif computed < level:
        since = kv_get(conn, "deesc_since")
        if not since:
            kv_set(conn, "deesc_since", now.isoformat())
        elif (now - datetime.fromisoformat(since)) >= timedelta(days=DEESCALATE_DAYS):
            alert = (f"{LEVEL_ICON[computed]} *{LEVEL_NAME[computed]}* — de-escalated from "
                     f"{LEVEL_NAME[level]} after {DEESCALATE_DAYS} clean days\n{body}")
            kv_set(conn, "level", computed)
            kv_set(conn, "deesc_since", None)
            level = computed
    else:
        kv_set(conn, "deesc_since", None)

    # a silent monitor that has stopped collecting reads exactly like calm
    last_ok = kv_get(conn, "last_ok_ts")
    if not alert and last_ok and (now - datetime.fromisoformat(last_ok)) > timedelta(hours=BLIND_HOURS):
        if not kv_get(conn, "blind_alerted"):
            alert = (f"⚠️ *cyber-escalation watch is blind* — no successful collection since "
                     f"{last_ok[:16]}Z\n{body}")
            kv_set(conn, "blind_alerted", True)
    elif last_ok and (now - datetime.fromisoformat(last_ok)) <= timedelta(hours=BLIND_HOURS):
        kv_set(conn, "blind_alerted", False)

    conn.execute("INSERT OR REPLACE INTO levels(ts,computed,level,reasons) VALUES(?,?,?,?)",
                 (now.isoformat(), computed, level, json.dumps(reasons + tripwires)))
    conn.commit()

    if alert:
        send(alert)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - never let a crash masquerade as calm
        print(f"cyber-escalation-watch crashed: {exc}", file=sys.stderr)
        sys.exit(0)
