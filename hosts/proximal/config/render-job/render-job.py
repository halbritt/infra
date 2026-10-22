#!/usr/bin/env python3
"""Scheduled telemetry-pod render job for the private agent-ee render gallery.

Owner instruction (relayed via agent-521's campaign process, 2026-10-22; job
owned by agent-449): render top/bottom/isometric views of the telemetry-pod PCB
about every four hours, publish them to the existing private gallery, bind
board/model hashes, timestamp, routing and qualification state and whether the
board changed; serialize, bound runtime, retain failures.

Source: an explicit, IMMUTABLE pinned candidate named by pin.json (board,
project and project-local models copied into pinned/<board sha256>/). Every
file is re-hashed on every run and the run refuses on any mismatch. The job
never selects a board from a repository HEAD or a live worktree; agent-449
updates the pin when a newer qualified snapshot exists. (Correction 2026-10-22,
agent-521 HOLD Cairn 14664d84: the first version rendered the old 112-footprint
fome-mc main pilot by mistake.)

Subcommands:
  run         one serialized run (skips and logs if another run holds the lock)
  post-check  systemd ExecStopPost backstop: marks a run that did not finish as failed

Outputs (under ~/.local/share/agent-ee-render-job):
  runs/<UTC>/            job.log, renders/, evidence/, result.json, FAILED (on failure)
  latest-status.json     last finished run: ok true/false, reason, bundle, hashes
  history.jsonl          one line per run (including skips)
  state.json             last publication by this job (for unchanged detection)
"""
import datetime
import fcntl
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import shutil
import time
import traceback
from pathlib import Path

HOME = Path.home()
JOB = HOME / ".local/share/agent-ee-render-job"
RUNS = JOB / "runs"
PINNED = JOB / "pinned"
PIN = JOB / "pin.json"
LOCK = JOB / "job.lock"
LATEST = JOB / "latest-status.json"
HISTORY = JOB / "history.jsonl"
STATE = JOB / "state.json"
GALLERY_ROOT = HOME / ".local/share/agent-ee-render-gallery/artifacts"
GALLERY_APP = HOME / ".local/share/agent-ee-render-gallery/app"
MODEL_DIR = "/usr/share/kicad/3dmodels"
SETTINGS = {"width": 2400, "height": 1600, "quality": "high", "jobs": 3, "timeout": 900}
STAGES = ("diagnostic", "placement")  # never routed/review: no acceptance claims
RETAIN_DAYS = 7
SCHEMA = "proximal.agent-ee-render-job.receipt/2"
HEX64 = re.compile(r"[a-f0-9]{64}")


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, data):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def append_history(entry):
    with HISTORY.open("a") as stream:
        stream.write(json.dumps(entry, sort_keys=True) + "\n")


class Log:
    def __init__(self, path):
        self.stream = open(path, "a", buffering=1)

    def __call__(self, message):
        line = f"{now().isoformat(timespec='seconds')} {message}"
        self.stream.write(line + "\n")
        print(line, flush=True)


class Refused(Exception):
    pass


def pinned_file(relative):
    path = (JOB / relative).resolve()
    if not path.is_relative_to(PINNED.resolve()) or not path.is_file():
        raise Refused(f"pinned file {relative!r} is missing or outside {PINNED}")
    return path


def load_pin(log):
    """Read pin.json and re-verify every pinned file; refuse on any mismatch."""
    pin = read_json(PIN)
    if not isinstance(pin, dict) or pin.get("schema") != "proximal.agent-ee-render-job.pin/1":
        raise Refused(f"{PIN} is missing or not a proximal.agent-ee-render-job.pin/1 file")
    if not re.fullmatch(r"[a-z0-9-]{1,16}", str(pin.get("name"))):
        raise Refused("pin name must be 1-16 of [a-z0-9-]")
    if not re.fullmatch(r"(Iteration|Revision|Candidate|Milestone|Diagnostic) (0|[1-9][0-9]{0,5})", str(pin.get("label"))):
        raise Refused("pin label must be gallery KIND NUMBER")
    if pin.get("stage") not in STAGES:
        raise Refused(f"pin stage must be one of {STAGES}")
    board = pinned_file(pin["board"]["path"])
    project = pinned_file(pin["project"]["path"])
    if board.suffix != ".kicad_pcb" or project != board.with_suffix(".kicad_pro"):
        raise Refused("pinned project must be the board's sibling .kicad_pro")
    checks = [(board, pin["board"]["sha256"]), (project, pin["project"]["sha256"])]
    for relative, expected in (pin.get("project_models") or {}).items():
        path = (board.parent / relative).resolve()
        if not path.is_relative_to(board.parent) or not path.is_file():
            raise Refused(f"pinned project model {relative!r} is missing")
        checks.append((path, expected))
    for path, expected in checks:
        if not HEX64.fullmatch(str(expected)):
            raise Refused(f"pin has no valid sha256 for {path}")
        actual = sha256_file(path)
        if actual != expected:
            raise Refused(f"PIN MISMATCH: {path} sha256 {actual} != pinned {expected}")
    if pin["board"]["sha256"] in (pin.get("refuse") or {}).get("board_sha256", []):
        raise Refused("pinned board is on the refuse list: " + str(pin["refuse"].get("reason")))
    log(f"pin {pin['name']} verified: board {board} sha256 {pin['board']['sha256']}; "
        f"project and {len(checks) - 2} project model(s) match")
    return pin, board, project


def scope(text, pin):
    refs = re.findall(r'\(property\s+"Reference"\s+"([^"]+)"', text)
    names = re.findall(r'\(footprint\s+"([^"]+)"', text)
    if len(refs) != len(names):
        raise Refused(f"cannot count scope: {len(names)} footprints but {len(refs)} references")
    holes = sum(1 for ref, name in zip(refs, names) if re.fullmatch(r"H\d+", ref) or "MountingHole" in name)
    counts = {"footprints": len(names), "mounting_holes": holes, "non_hole_footprints": len(names) - holes}
    expected = pin.get("expected_scope") or {}
    if len(names) in (pin.get("refuse") or {}).get("footprint_totals", []):
        raise Refused(f"board holds {len(names)} footprints, the count of a refused board: "
                      + str(pin["refuse"].get("reason")))
    matches = (counts["non_hole_footprints"] == expected.get("non_hole_footprints")
               and holes == expected.get("mounting_holes"))
    counts.update(expected_non_hole=expected.get("non_hole_footprints"),
                  expected_holes=expected.get("mounting_holes"), matches_expected=matches)
    counts["tag"] = (f"{counts['non_hole_footprints']}fp+{holes}holes" if matches else
                     f"SCOPE-MISMATCH-{counts['non_hole_footprints']}fp+{holes}holes")
    return counts


def copper(text):
    return {kind: len(re.findall(r"\(" + kind + r"[\s)]", text)) for kind in ("segment", "arc", "via", "zone")}


def model_identity(board, log):
    from agent_ee.models3d import inspect_models
    env = dict(os.environ, KIPRJMOD=str(board.parent), KICAD10_3DMODEL_DIR=MODEL_DIR)
    coverage = inspect_models(board, env)
    rows = []
    for footprint in coverage.get("footprints", []):
        for model in footprint.get("models", []) or [{}]:
            rows.append([footprint.get("reference"), footprint.get("status"), model.get("path"),
                         model.get("status"), model.get("sha256")])
    rows.sort(key=lambda r: [str(x) for x in r])
    digest = sha256_bytes(json.dumps(rows, separators=(",", ":")).encode())
    log(f"model coverage {coverage.get('summary')} digest {digest}")
    return coverage.get("summary", {}), digest


def app_identity():
    release = GALLERY_APP.resolve()
    files = {name: sha256_file(release / "agent_ee" / name)
             for name in ("render3d.py", "render_gallery.py", "models3d.py", "viewer.py")}
    return {"release": str(release), "files": files}


def kicad_version():
    return subprocess.run(["kicad-cli", "version"], capture_output=True, text=True, timeout=30,
                          check=True).stdout.strip()


def gallery(*args, log):
    env = dict(os.environ, PYTHONPATH=str(GALLERY_APP))
    command = [sys.executable, "-m", "agent_ee.render_gallery", "--root", str(GALLERY_ROOT), *args]
    log("gallery: " + " ".join(command))
    result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=300)
    if result.stderr.strip():
        log("gallery stderr: " + result.stderr.strip())
    if result.returncode:
        raise RuntimeError(f"render_gallery {args[0]} exited {result.returncode}: "
                           + (result.stderr.strip().splitlines() or ["(no stderr)"])[-1])
    return result.stdout.strip()


def attach_status(subject, board, receipt, evidence_dir, routing_value, log, run_id):
    """Attach a hash-bound status record: routing checked against the board, not qualified per the receipt."""
    board_sha = sha256_file(board)
    association = {"schema": "agent-ee.gallery-association/1", "board_sha256": board_sha,
                   "evidence": [{"role": "receipt", "sha256": sha256_file(receipt)}], "models": []}
    association_path = evidence_dir / f"render-job-association_{board_sha[:12]}_{run_id}.json"
    write_json(association_path, association)
    record = {"routing": {"value": routing_value,
                          "evidence": ["board"] if routing_value == "unrouted" else ["board", "receipt"]},
              "qualification": {"value": "unqualified", "evidence": ["receipt"]}}
    record_path = evidence_dir / "status-record.json"
    write_json(record_path, record)
    return gallery("status", "--subject", f"bundles/{subject}", "--record", str(record_path),
                   "--evidence", f"board={board}", "--evidence", f"association={association_path}",
                   "--evidence", f"receipt={receipt}", log=log)


def receipt_name(pin, counts, routing_value, change, run_id):
    routing = "unrouted" if routing_value == "unrouted" else "copper-present"
    name = f"rj_{pin['name']}_{counts['tag']}_{routing}_not-qualified_{change}_{run_id}.json"
    if len(name) > 128:
        name = f"rj_{pin['name']}_{counts['tag']}_{routing}_not-qualified_{run_id}.json"
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+-]{0,127}", name):
        raise Refused(f"receipt name {name!r} is not a plain gallery file name")
    return name


def prune(log):
    cutoff = time.time() - RETAIN_DAYS * 86400
    for run in sorted(RUNS.iterdir()):
        try:
            if run.is_dir() and run.stat().st_mtime < cutoff:
                shutil.rmtree(run)
                log(f"pruned run older than {RETAIN_DAYS} days: {run.name}")
        except OSError as exc:
            log(f"prune failed for {run}: {exc}")


class Terminated(Exception):
    pass


def run():
    JOB.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(exist_ok=True)
    lock = open(LOCK, "a")
    started = now()
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        holder = (read_json(LATEST, {}) or {}).get("run_id")
        message = f"skipped: another render run holds {LOCK} (running: {holder})"
        print(message, flush=True)
        append_history({"run_id": run_id, "ok": None, "skipped": True, "reason": message,
                        "at": started.isoformat()})
        return 0
    run_dir = RUNS / run_id
    run_dir.mkdir()
    log = Log(run_dir / "job.log")
    status = {"schema": "proximal.agent-ee-render-job.status/1", "run_id": run_id, "run_dir": str(run_dir),
              "started_at": started.isoformat(), "state": "running", "ok": None, "pid": os.getpid()}
    write_json(LATEST, status)

    def on_term(signum, frame):
        raise Terminated(f"terminated by signal {signum} (timeout or stop)")
    signal.signal(signal.SIGTERM, on_term)
    t0 = time.monotonic()
    result = {"run_id": run_id}
    try:
        log(f"render job start; run dir {run_dir}; nice={os.nice(0)}")
        prune(log)
        sys.path.insert(0, str(GALLERY_APP))
        pin, board, project = load_pin(log)
        text = board.read_text()
        board_sha = pin["board"]["sha256"]
        counts = scope(text, pin)
        log(f"scope: {counts}")
        items = copper(text)
        routing_value = "unrouted" if items["segment"] + items["arc"] + items["via"] == 0 else "routed"
        routing_note = ("UNROUTED: the pinned board has no tracks, arcs or vias" if routing_value == "unrouted" else
                        f"copper present ({items}); routing completeness NOT verified; no routing acceptance claimed")
        models_summary, models_digest = model_identity(board, log)
        identity = {"board_sha256": board_sha, "project_sha256": pin["project"]["sha256"],
                    "project_models": pin.get("project_models"), "models_digest": models_digest,
                    "kicad": kicad_version(), "settings": SETTINGS, "app": app_identity(),
                    "label": pin["label"], "stage": pin["stage"]}
        identity_digest = sha256_bytes(json.dumps(identity, sort_keys=True).encode())
        state = read_json(STATE, {}) or {}
        previous = state.get("last_publication")
        previous_exists = bool(previous) and (GALLERY_ROOT / "bundles" / previous["bundle"] / "manifest.json").is_file()
        board_changed = not previous_exists or previous.get("board_sha256") != board_sha
        inputs_changed = not previous_exists or previous.get("identity_digest") != identity_digest
        index = read_json(GALLERY_ROOT / "index.json", []) or []
        same_board = [e.get("id") for e in index if e.get("board_sha256") == board_sha
                      and (not previous or e.get("id") != previous.get("bundle"))]
        if not inputs_changed:
            change = "board-unchanged"
        elif not board_changed:
            change = "board-unchanged-inputs-changed"
        elif same_board:
            change = f"same-board-as-gallery-{same_board[0]}"
        else:
            change = "new-board"
        log(f"change: {change} (previous job publication: {previous and previous.get('bundle')}; "
            f"same board in other gallery bundles: {same_board})")
        evidence_dir = run_dir / "evidence"
        evidence_dir.mkdir()
        receipt = {
            "schema": SCHEMA, "run_id": run_id, "checked_at": now().isoformat(),
            "owner_instruction": "telemetry-pod render job, ~every 4 h, relayed via agent-521 campaign "
                                 "process 2026-10-22; job owner agent-449",
            "source": {"pin": pin, "pin_sha256": sha256_file(PIN), "board_path": str(board),
                       "kind": "explicit immutable pinned candidate; never a repository HEAD or live worktree"},
            "board": {"sha256": board_sha, "project_sha256": pin["project"]["sha256"], **items},
            "scope": counts,
            "models": {"KICAD10_3DMODEL_DIR": MODEL_DIR, "KIPRJMOD": str(board.parent),
                       "summary": models_summary, "digest": models_digest},
            "routing": {"gallery_value": routing_value, "statement": routing_note},
            "qualification": {"state": "not qualified",
                              "statement": "NOT QUALIFIED. This scheduled render job performs no qualification "
                                           "and claims no acceptance; the board is treated as unqualified."},
            "change": {"label": change, "board_changed_since_last_job_publication": board_changed,
                       "render_inputs_changed": inputs_changed, "previous_job_publication": previous,
                       "same_board_in_other_gallery_bundles": same_board},
            "identity": identity, "identity_digest": identity_digest,
        }
        result.update(pin=pin["name"], board_sha256=board_sha, scope=counts, change=change,
                      routing=routing_note, qualification="not qualified")
        receipt_path = evidence_dir / receipt_name(pin, counts, routing_value, change, run_id)
        if not inputs_changed:
            receipt["publication"] = {"bundle": previous["bundle"], "new_bundle": False,
                                      "note": "unchanged: no new render published; status re-attached"}
            write_json(receipt_path, receipt)
            status_id = attach_status(previous["bundle"], board, receipt_path, evidence_dir, routing_value, log, run_id)
            log(f"board unchanged since bundle {previous['bundle']}; attached status {status_id}; no re-render")
            result.update(ok=True, bundle=previous["bundle"], new_bundle=False, status_id=status_id,
                          label=pin["label"], stage=pin["stage"])
        else:
            from agent_ee.render3d import render_board
            os.environ["KICAD10_3DMODEL_DIR"] = MODEL_DIR
            manifest_path = render_board(board, run_dir / "renders", width=SETTINGS["width"],
                                         height=SETTINGS["height"], quality=SETTINGS["quality"],
                                         jobs=SETTINGS["jobs"], timeout=SETTINGS["timeout"], progress=log)
            manifest = read_json(manifest_path)
            log(f"render completed in {manifest.get('duration_seconds')} s; manifest {manifest_path}")
            load_pin(log)  # the pinned bytes must still match after rendering
            bundle = gallery("publish", "--renders", str(run_dir / "renders"), "--label", pin["label"],
                             "--stage", pin["stage"], log=log)
            if not re.fullmatch(r"[a-f0-9]{12}-[a-f0-9]{12}", bundle):
                raise RuntimeError(f"unexpected publish output: {bundle!r}")
            published = read_json(GALLERY_ROOT / "bundles" / bundle / "manifest.json", {})
            if published.get("board_sha256") != board_sha:
                raise RuntimeError("published manifest does not carry the pinned board sha256")
            receipt["publication"] = {"bundle": bundle, "new_bundle": True, "label": pin["label"],
                                      "stage": pin["stage"], "render_manifest_sha256": sha256_file(manifest_path),
                                      "images": manifest.get("images"),
                                      "render_duration_seconds": manifest.get("duration_seconds")}
            write_json(receipt_path, receipt)
            status_id = attach_status(bundle, board, receipt_path, evidence_dir, routing_value, log, run_id)
            log(f"published bundle {bundle} ({pin['label']}, stage {pin['stage']}); attached status {status_id}")
            write_json(STATE, {"last_publication": {
                "bundle": bundle, "label": pin["label"], "pin": pin["name"], "board_sha256": board_sha,
                "identity_digest": identity_digest, "published_at": published.get("published_at"),
                "run_id": run_id}})
            result.update(ok=True, bundle=bundle, new_bundle=True, status_id=status_id, label=pin["label"],
                          stage=pin["stage"], images={v: str(GALLERY_ROOT / "bundles" / bundle / f"{v}.png")
                                                      for v in ("top", "bottom", "isometric")})
        result["receipt"] = str(receipt_path)
        code = 0
    except BaseException as exc:  # includes Refused, Terminated and KeyboardInterrupt from render_board
        reason = f"{type(exc).__name__}: {exc}"
        log("FAILED: " + reason)
        log(traceback.format_exc())
        (run_dir / "FAILED").write_text(reason + "\n")
        result.update(ok=False, reason=reason)
        code = 1
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
    result.update(finished_at=now().isoformat(), wall_seconds=round(time.monotonic() - t0, 1))
    write_json(run_dir / "result.json", result)
    write_json(LATEST, {**status, **result, "state": "finished"})
    append_history({k: result.get(k) for k in ("run_id", "ok", "reason", "pin", "bundle", "new_bundle", "change",
                                               "board_sha256", "wall_seconds", "finished_at")})
    log(f"render job {'OK' if result['ok'] else 'FAILED'} in {result['wall_seconds']} s")
    return code


def post_check():
    """ExecStopPost backstop: a run killed before writing its result is recorded as failed."""
    latest = read_json(LATEST, {}) or {}
    if latest.get("state") != "running":
        return 0
    if latest.get("pid"):
        try:
            os.kill(latest["pid"], 0)
            return 0  # still alive: not ours to judge (e.g. a manual run)
        except ProcessLookupError:
            pass
    reason = (f"run did not finish: SERVICE_RESULT={os.environ.get('SERVICE_RESULT')} "
              f"EXIT_CODE={os.environ.get('EXIT_CODE')} EXIT_STATUS={os.environ.get('EXIT_STATUS')}")
    run_dir = Path(latest.get("run_dir", ""))
    if run_dir.is_dir():
        (run_dir / "FAILED").write_text(reason + "\n")
        with (run_dir / "job.log").open("a") as stream:
            stream.write(f"{now().isoformat(timespec='seconds')} FAILED (post-check): {reason}\n")
    latest.update(state="finished", ok=False, reason=reason, finished_at=now().isoformat())
    write_json(LATEST, latest)
    append_history({"run_id": latest.get("run_id"), "ok": False, "reason": reason,
                    "finished_at": latest["finished_at"]})
    return 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    if command == "run":
        sys.exit(run())
    if command == "post-check":
        sys.exit(post_check())
    sys.exit(f"usage: {sys.argv[0]} run|post-check")
