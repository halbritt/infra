#!/usr/bin/env python3
"""Backtest gate for cyber-escalation-watch.

Point-in-time replay: every evaluation uses only data that existed on that date
(KEV dateAdded <= D, ransomwatch discovered < D), so the z-scores are what the
monitor would actually have printed that morning — not a fit to hindsight.

Gate windows (all three must pass before the monitor is trusted):
  A  2026-11-12 .. 2026-11-17   mundane outage cluster (MSFT/FAA/Workday/AWS/Chase/United)
                               must read GREEN. This is the week that motivated the build.
  B  2026-02-16 .. 2026-02-22   Cloudflare BYOIP withdrawal (vendor config error)
                               must read GREEN.
  C  2026-10-09 .. 2026-10-14   IRGC sabotage of French refrigeration controllers
                               should read elevated (YELLOW+) if the index can see it.

Usage: backtest.py [--from YYYY-MM-DD --to YYYY-MM-DD] [--verbose]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from watch import (  # noqa: E402
    MIN_BUCKETS, Z_ORANGE, Z_YELLOW, cached, fetch_kev, fetch_ransomware_posts, weekly_buckets, zscore,
)

GATES = [
    ("A", "2026-11-12", "2026-11-17", "mundane outage cluster", "GREEN"),
    ("B", "2026-02-16", "2026-02-22", "Cloudflare BYOIP withdrawal", "GREEN"),
    ("C", "2026-10-09", "2026-10-14", "IRGC sabotage of FR refrigeration", "elevated"),
]


def z_at(dates: list[str], day: datetime, floor_sd: float) -> tuple[float, float, float | None]:
    """z for the 7d window ending at `day`, using only data strictly before `day`."""
    end = day.date().isoformat()
    hist = [d for d in dates if d < end]
    prior = weekly_buckets(hist, day)[1:]
    cur = sum(1 for d in hist if d >= (day - timedelta(days=7)).date().isoformat())
    z = zscore(cur, prior, floor_sd=floor_sd)
    mean = statistics.fmean(prior) if prior else 0.0
    return cur, mean, z


def window_rows(kev_dates, ransom_dates, start: str, end: str):
    rows = []
    day = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    stop = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    while day <= stop:
        k_cur, k_mean, k_z = z_at(kev_dates, day, 1.0)
        r_cur, r_mean, r_z = z_at(ransom_dates, day, 5.0)
        rows.append({"day": day.date().isoformat(), "kev": k_cur, "kev_mean": k_mean, "kev_z": k_z,
                     "ran": r_cur, "ran_mean": r_mean, "ran_z": r_z})
        day += timedelta(days=1)
    return rows


def verdict(rows) -> tuple[str, int]:
    hits = 0
    worst = "GREEN"
    for r in rows:
        zs = [z for z in (r["kev_z"], r["ran_z"]) if z is not None]
        if len(zs) < 2:
            worst = max(worst, "COLD", key=["GREEN", "COLD", "YELLOW", "ORANGE"].index)
            continue
        if sum(1 for z in zs if z >= Z_ORANGE) >= 2:
            hits += 1
            worst = "ORANGE"
        elif sum(1 for z in zs if z >= Z_YELLOW) >= 2:
            hits += 1
            worst = max(worst, "YELLOW", key=["GREEN", "COLD", "YELLOW", "ORANGE"].index)
    return worst, hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    kev = cached("kev.json", 20, fetch_kev)
    kev_dates = sorted(v["added"] for v in kev.values())
    ransom_dates = cached("ransomwatch.json", 6, fetch_ransomware_posts)

    print(f"history: {len(kev_dates)} KEV additions ({kev_dates[0]}..{kev_dates[-1]}), "
          f"{len(ransom_dates)} ransomware posts ({min(ransom_dates)}..{max(ransom_dates)})")

    if args.start and args.end:
        rows = window_rows(kev_dates, ransom_dates, args.start, args.end)
        for r in rows:
            fz = lambda z: "cold" if z is None else f"{z:+.1f}"  # noqa: E731
            print(f"{r['day']}  kev {r['kev']:>3} (base {r['kev_mean']:5.1f}, z {fz(r['kev_z'])})   "
                  f"ransom {r['ran']:>4} (base {r['ran_mean']:6.1f}, z {fz(r['ran_z'])})")
        print("verdict:", verdict(rows))
        return 0

    failures = []
    for tag, start, end, label, expect in GATES:
        rows = window_rows(kev_dates, ransom_dates, start, end)
        worst, hits = verdict(rows)
        ok = (worst == "GREEN") if expect == "GREEN" else (worst != "GREEN")
        if not ok:
            failures.append(tag)
        print(f"\n[{tag}] {start}..{end}  {label}")
        print(f"    verdict={worst}  days_breached={hits}/{len(rows)}  expect={expect}  {'PASS' if ok else 'FAIL'}")
        if args.verbose or not ok:
            for r in rows:
                fz = lambda z: "cold" if z is None else f"{z:+.1f}"  # noqa: E731
                print(f"    {r['day']}  kev {r['kev']:>3} z{fz(r['kev_z'])}   ransom {r['ran']:>4} z{fz(r['ran_z'])}")

    print("\nGATE:", "PASS" if not failures else f"FAIL ({','.join(failures)})")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
