"""Install canonical watch files and update only the existing outbreak cron job."""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .core import Store

JOB_ID = "1a69fc75271a"


def install(home, source, apply):
    from cron.jobs import get_job, update_job

    state = home / "watchdogs/outbreak-watch"
    job = get_job(JOB_ID)
    if not job or job["name"] != "outbreak-watch":
        raise ValueError("expected existing outbreak-watch job")
    if job.get("fire_claim") or job.get("state") == "running":
        raise RuntimeError("outbreak-watch is running")
    legacy = json.loads((state / "LEDGER.json").read_text())
    files = {
        state / "CRITERIA.md": source / "outbreak_watch/CRITERIA.md",
        home / "scripts/outbreak_watch_job.py": source / "outbreak_watch_job.py",
    }
    for name in ["__init__.py", "core.py", "runtime.py"]:
        files[home / "scripts/outbreak_watch" / name] = source / "outbreak_watch" / name
    changes = {
        "script": "outbreak_watch_job.py",
        "no_agent": True,
        "prompt": "Execute the installed outbreak-watch evidence/review/identity gate. Its stdout is the only alert; failures stay local. Policy: watchdogs/outbreak-watch/CRITERIA.md.",
        "failure_deliver": "local",
        "enabled_toolsets": [],
        "context_from": [],
        "workdir": None,
    }
    plan = {
        "job_id": JOB_ID,
        "files": {str(k): str(v) for k, v in files.items()},
        "job_changes": changes,
        "initialize_state": not (state / "state.sqlite3").exists(),
    }
    if not apply:
        return plan
    os.umask(0o077)
    with (state / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Recheck the current definition before the bounded migration.
        if get_job(JOB_ID) != job:
            raise RuntimeError("job changed during installation")
        manifest = state / "installation.json"
        if manifest.exists():
            for filename, digest in json.loads(manifest.read_text())["files"].items():
                p = Path(filename)
                if (
                    not p.exists()
                    or hashlib.sha256(p.read_bytes()).hexdigest() != digest
                ):
                    raise RuntimeError("installed managed file changed: " + filename)
        backup = (
            state / "backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        )
        backup.mkdir(parents=True)
        (backup / "job.json").write_text(json.dumps(job, indent=2))
        shutil.copy2(state / "LEDGER.json", backup / "LEDGER.json")
        for target in files:
            if target.exists():
                dest = backup / target.relative_to(home)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, dest)
        if not (state / "state.sqlite3").exists():
            temporary = state / "state.sqlite3.installing"
            if temporary.exists():
                raise RuntimeError("unfinished state migration requires inspection")
            Store.initialize(temporary, legacy)
            os.replace(temporary, state / "state.sqlite3")
        for target, origin in files.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".installing")
            temporary.write_bytes(origin.read_bytes())
            os.replace(temporary, target)
        directory_fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        updated = update_job(JOB_ID, changes)
        if not updated or any(updated.get(k) != v for k, v in changes.items()):
            raise RuntimeError("cron update was not confirmed")
        for k in ("schedule", "deliver", "enabled", "next_run_at"):
            if updated[k] != job[k]:
                raise RuntimeError("unrelated scheduling/delivery state changed: " + k)
        receipt = {
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "backup": str(backup),
            "job_id": JOB_ID,
            "files": {
                str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
            },
            "source_commit": subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
            ).strip(),
        }
        manifest.write_text(json.dumps(receipt, indent=2) + "\n")
        return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--hermes-source", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    os.environ["HERMES_HOME"] = str(args.home)
    sys.path.insert(0, str(args.hermes_source))
    print(
        json.dumps(
            install(args.home, Path(__file__).resolve().parent.parent, args.apply),
            indent=2,
        )
    )
