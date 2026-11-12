#!/usr/bin/env python3
"""Tell the owner when a Hermes cron job keeps failing.

Hermes jobs with failure_deliver=local (outbreak-watch) or deliver=local report
failures nowhere. outbreak-watch failed 35 days in a row (2026-10-08..11-11) while its
Slack thread stayed quiet. This no_agent job reads the cron job store and prints a
notice when an enabled job reaches THRESHOLD consecutive failures, and a recovery
note when it next succeeds. Stdout is delivered; empty stdout is silent.

One notice per failure streak (state in watchdogs/cron-failure-watch/). An error here exits nonzero, so this
job's own failures follow its delivery target instead of staying local.
"""

import json
import os
from pathlib import Path

THRESHOLD = int(os.environ.get("CRON_FAILURE_THRESHOLD", "3"))
SELF_NAME = "cron-failure-watch"


def hermes_home():
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))


def first_line(text, limit=200):
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    line = lines[0] if lines else "no error text"
    return line if len(line) <= limit else line[: limit - 1] + "…"


def check(jobs, state, threshold=THRESHOLD):
    """Return (message lines, new state). state maps job id -> streak when notified."""
    failing, recovered, new_state = [], [], {}
    for job in jobs:
        if job.get("name") == SELF_NAME or not job.get("enabled", True):
            continue
        jid, streak = job["id"], int(job.get("failure_streak") or 0)
        label = f"{job.get('name') or jid} ({jid})"
        notified = state.get(jid)
        if notified is not None and streak < notified:
            # The streak reset, so the job succeeded at least once since the notice.
            recovered.append(f"• {label} succeeded again.")
            notified = None
        if streak >= threshold:
            if notified is None:
                error = job.get("last_error") or (job.get("last_failure") or {}).get(
                    "detail"
                )
                failing.append(
                    f"• {label}: {streak} failed runs in a row, last at "
                    f"{job.get('last_run_at')}. {first_line(error)}"
                )
                notified = streak
            new_state[jid] = notified
    lines = []
    if failing:
        lines.append("Hermes cron jobs keep failing:")
        lines += failing
        lines.append("Inspect with `hermes cron runs <id>`.")
    if recovered:
        lines.append("Recovered:")
        lines += recovered
    return lines, new_state


def main():
    from cron.jobs import list_jobs

    state_path = hermes_home() / "watchdogs/cron-failure-watch/state.json"
    try:
        state = json.loads(state_path.read_text())
    except FileNotFoundError:
        state = {}
    lines, new_state = check(list_jobs(include_disabled=False), state)
    if new_state != state:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(new_state, indent=1, sort_keys=True))
        os.replace(tmp, state_path)
    if lines:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
