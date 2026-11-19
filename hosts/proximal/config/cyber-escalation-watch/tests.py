#!/usr/bin/env python3
"""Behavioural fixtures for cyber-escalation-watch.

The historical backtest (backtest.py) can only exercise domains that have a
public archive — in practice KEV. Everything else about the alerting logic is
verified here, on synthetic domains, so each rule is proven by a fixture rather
than by waiting weeks for the world to cooperate.

Run: python3 tests.py
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import watch  # noqa: E402

FAILS = []


def domain(name, z, value: float | None = 10.0):
    return {"domain": name, "metric": f"{name}_metric", "value": value,
            "baseline_mean": 5.0, "buckets": 13, "z": z}


def run(results, tripwires=None, errors=None, seed=None, hours_ago=0):
    """Execute main() against a throwaway state dir; return captured stdout."""
    tmp = tempfile.mkdtemp(prefix="cew-test-")
    watch.STATE_DIR = tmp
    watch.DB_PATH = os.path.join(tmp, "history.db")
    watch.CACHE_DIR = os.path.join(tmp, "cache")
    watch.DRY = True
    watch.collect = lambda conn: (results, tripwires or [], errors or [])

    conn = watch.db()
    for key, value in (seed or {}).items():
        watch.kv_set(conn, key, value)
    conn.close()

    buf = io.StringIO()
    with redirect_stdout(buf):
        watch.main()
    return buf.getvalue()


def check(name, condition, detail=""):
    if condition:
        print(f"PASS  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILS.append(name)


# 1. calm world -> total silence (this is the contract cron relies on)
out = run([domain("exploitation", 0.4), domain("extortion", -0.2), domain("posture", None)])
check("green is silent", out.strip() == "", repr(out[:200]))

# 2. one domain screaming is NOT an alert: single-vendor/single-domain events
#    (an AWS outage, one botnet, one zero-day) must never fire the index alone
out = run([domain("exploitation", 5.0), domain("extortion", None), domain("posture", None)])
check("single domain never fires", out.strip() == "", repr(out[:200]))

# 3. two domains at 2 sigma hold ~a day before going YELLOW
out = run([domain("exploitation", 2.6), domain("extortion", 2.3), domain("posture", None)])
check("yellow is held, not instant", "YELLOW" not in out, repr(out[:200]))
seed = {"yellow_since": (datetime.now(timezone.utc) - timedelta(hours=21)).isoformat()}
out = run([domain("exploitation", 2.6), domain("extortion", 2.3), domain("posture", None)], seed=seed)
check("yellow fires after hold", "YELLOW" in out and "exploitation" in out, repr(out[:300]))

# 4. three domains at 3 sigma escalate immediately
out = run([domain("exploitation", 3.4), domain("extortion", 3.1), domain("posture", 3.8)])
check("three domains -> ORANGE", "ORANGE" in out, repr(out[:300]))

# 5. a tripwire alone is enough, no z-score corroboration needed
out = run([domain("exploitation", 0.1), domain("extortion", 0.2)],
          tripwires=["mass exploitation: 4 KEV additions in 7d with EPSS>=0.7 (CVE-2099-0001 0.94)"])
check("tripwire -> ORANGE", "ORANGE" in out and "mass exploitation" in out, repr(out[:300]))

# 6. de-escalation needs the full clean window
seed = {"level": watch.ORANGE, "deesc_since": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}
out = run([domain("exploitation", 0.1), domain("extortion", 0.1)], seed=seed)
check("de-escalation blocked before 5 days", out.strip() == "", repr(out[:200]))

seed = {"level": watch.ORANGE, "deesc_since": (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()}
out = run([domain("exploitation", 0.1), domain("extortion", 0.1)], seed=seed)
check("de-escalation after 5 clean days", "de-escalated" in out.lower(), repr(out[:300]))

# 7. a monitor that stopped collecting must not read as calm
seed = {"level": watch.GREEN, "last_ok_ts": (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()}
out = run([domain("exploitation", None, value=None), domain("extortion", None, value=None)], seed=seed)
check("blind monitor alerts", "blind" in out.lower(), repr(out[:300]))

# 8. cold domains are labelled, not silently treated as healthy
out = run([domain("exploitation", 0.5), domain("routing", None, value=None)])
check("cold domain labelled", "cold" in out.lower() or out.strip() == "", repr(out[:200]))
text = watch.describe([domain("routing", None, value=None)], [], [])
check("describe marks cold", "cold" in text, text)

# 9. missing history must never be read as a calm bucket (zero-fill guard)
dates = [(datetime.now(timezone.utc) - timedelta(days=i)).date().isoformat() for i in range(3)]
buckets = watch.daily_buckets(dates, datetime.now(timezone.utc), days=30)
check("bucket coverage guard", len(buckets) <= 3, f"got {len(buckets)} buckets from 3 days of data")

print()
if FAILS:
    print(f"FAILED: {', '.join(FAILS)}")
    sys.exit(1)
print("all fixtures pass")
