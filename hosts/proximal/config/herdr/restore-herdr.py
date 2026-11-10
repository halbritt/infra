#!/usr/bin/env python3
"""Install a verified maintenance snapshot after reboot, then attach Herdr."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    ready = json.loads((bundle / "ready.json").read_text())
    for name, digest in ready["sha256"].items():
        require(Path(name).name == name, "Invalid bundle filename")
        require(hashlib.sha256((bundle / name).read_bytes()).hexdigest() == digest,
                f"Bundle checksum mismatch: {name}")
    manifest = json.loads((bundle / "resume-manifest.json").read_text())
    require(len(manifest) == ready["pane_count"], "Incomplete resume manifest")
    config_path = Path(ready["session_dir"]) / "config.toml"
    with config_path.open("rb") as config_file:
        config = tomllib.load(config_file)
    require(config.get("session", {}).get("resume_agents_on_restore", True),
            "Herdr native conversation restore is disabled")
    for pane in manifest:
        require(Path(pane["cwd"]).is_dir(), f"Missing cwd: {pane['cwd']}")
        require(Path(pane["transcript"]).is_file(), f"Missing transcript: {pane['pane_id']}")
        ack = json.loads((bundle / "acks" / (pane["pane_id"].replace(":", "-") + ".json")).read_text())
        require(ack["paused"] is True and ack["work_saved"] is True,
                f"Unconfirmed pause: {pane['pane_id']}")
        require(ack["native_session_id"] == pane["native_session_id"], "Session ID mismatch")
    print(f"Verified {len(manifest)} saved conversations and pause receipts.", flush=True)
    if args.check:
        return
    require(os.environ.get("HERDR_ENV") != "1", "Run from a terminal outside Herdr")
    require(Path("/proc/sys/kernel/random/boot_id").read_text().strip() != ready["boot_id"],
            "This recovery bundle is for the next boot; no session changed")
    marker = bundle / "installed.json"
    require(not marker.exists(), "Snapshot already installed; run herdr to attach")
    sessions = json.loads(subprocess.check_output(["herdr", "session", "list", "--json"]))
    defaults = [s for s in sessions["sessions"] if s["default"]]
    require(len(defaults) == 1, "Cannot identify default Herdr session")
    session = defaults[0]
    require(not session["running"], "Default Herdr is running; refusing to overwrite its layout")
    destination = Path(session["session_dir"]) / "session.json"
    require(destination.parent == Path(ready["session_dir"]), "Herdr session directory changed")
    backup = bundle / "session.json.before-install"
    require(not backup.exists(), "Prior restore attempt exists; inspect before retrying")
    if destination.exists():
        shutil.copy2(destination, backup)
    fd, temporary = tempfile.mkstemp(prefix=".restart-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write((bundle / "session.json.restore").read_bytes())
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    marker.write_text(json.dumps({"boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}))
    os.execvp("herdr", ["herdr"])


if __name__ == "__main__":
    main()
