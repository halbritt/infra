#!/usr/bin/env python3
"""Scheduled telemetry-pod render job for the private agent-ee render gallery.

Owner instruction (relayed via agent-521's campaign process, 2026-10-22; job
owned by agent-449): render top/bottom/isometric views of the telemetry-pod PCB
from the latest consistent snapshot about every four hours, publish them to the
existing private gallery, bind board/model hashes, timestamp, routing and
qualification state and whether the board changed; serialize, bound runtime,
retain failures.

Source of truth: the COMMITTED fome-mc origin/main board, extracted with
`git archive` (never a working tree another process may be mutating).

Subcommands:
  run         one serialized run (skips and logs if another run holds the lock)
  post-check  systemd ExecStopPost backstop: marks a run that did not finish as failed

Outputs (under ~/.local/share/agent-ee-render-job):
  runs/<UTC>/            job.log, snapshot/, renders/, evidence/, result.json, FAILED (on failure)
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
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import traceback
from pathlib import Path

HOME = Path.home()
JOB = HOME / ".local/share/agent-ee-render-job"
RUNS = JOB / "runs"
LOCK = JOB / "job.lock"
LATEST = JOB / "latest-status.json"
HISTORY = JOB / "history.jsonl"
STATE = JOB / "state.json"
GALLERY_ROOT = HOME / ".local/share/agent-ee-render-gallery/artifacts"
GALLERY_APP = HOME / ".local/share/agent-ee-render-gallery/app"
FOME = HOME / "git/fome-mc"
REF = "origin/main"
BOARD = "telemetry-pod/telemetry-pod.kicad_pcb"
ARCHIVE_PATHS = ["telemetry-pod/telemetry-pod.kicad_pcb", "telemetry-pod/telemetry-pod.kicad_pro",
                 "telemetry-pod/telemetry-pod.kicad_dru", "telemetry-pod/fp-lib-table",
                 "telemetry-pod/sym-lib-table", "telemetry-pod/kicad-libraries",
                 "telemetry-pod/captured-footprints", "telemetry-pod/README.md"]
MODEL_DIR = "/usr/share/kicad/3dmodels"
SETTINGS = {"width": 2400, "height": 1600, "quality": "high", "jobs": 3, "timeout": 900}
STAGE = "diagnostic"
RETAIN_DAYS = 7
SCHEMA = "proximal.agent-ee-render-job.receipt/1"


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


def git(*args, timeout=180):
    return subprocess.run(["git", "-C", str(FOME), *args], capture_output=True, check=True,
                          timeout=timeout)


def fetch(log):
    last = None
    for attempt in range(1, 4):
        try:
            git("fetch", "--quiet", "origin", "main", timeout=300)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            last = getattr(exc, "stderr", b"") or str(exc).encode()
            log(f"fetch attempt {attempt} failed: {last.decode(errors='replace').strip()}")
            time.sleep(10 * attempt)
    raise RuntimeError("git fetch origin main failed after 3 attempts: "
                       + last.decode(errors="replace").strip())


def extract(commit, dest):
    """Extract the committed pod board and project files: a consistent snapshot by construction."""
    dest.mkdir()
    archive = dest.parent / "snapshot.tar"
    with archive.open("wb") as out:
        subprocess.run(["git", "-C", str(FOME), "archive", "--format=tar", commit, "--", *ARCHIVE_PATHS],
                       stdout=out, check=True, timeout=300)
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if member.issym() or member.islnk() or member.name.startswith("/") or ".." in Path(member.name).parts:
                raise RuntimeError(f"refusing unsafe archive member {member.name!r}")
        tar.extractall(dest, filter="data")
    archive.unlink()
    return dest / BOARD


def copper(text):
    counts = {kind: len(re.findall(r"\(" + kind + r"[\s)]", text)) for kind in ("segment", "arc", "via", "zone")}
    counts["footprints"] = len(re.findall(r"\(footprint\s", text))
    return counts


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


def attach_status(subject, board, receipt, evidence_dir, readme, routing_value, log):
    """Attach a hash-bound status record: routing from the board, not qualified from the receipt."""
    board_sha = sha256_file(board)
    evidence = [("receipt", receipt)] + ([("index", readme)] if readme else [])
    association = {"schema": "agent-ee.gallery-association/1", "board_sha256": board_sha,
                   "evidence": [{"role": role, "sha256": sha256_file(path)} for role, path in evidence],
                   "models": []}
    association_path = evidence_dir / f"render-job-association_{board_sha[:12]}_{receipt.stem.rsplit('_', 1)[-1]}.json"
    write_json(association_path, association)
    disposition = ["receipt"] + (["index"] if readme else [])
    record = {"routing": {"value": routing_value,
                          "evidence": ["board"] if routing_value == "unrouted" else ["board", "receipt"]},
              "qualification": {"value": "unqualified", "evidence": disposition}}
    record_path = evidence_dir / "status-record.json"
    write_json(record_path, record)
    args = ["status", "--subject", f"bundles/{subject}", "--record", str(record_path),
            "--evidence", f"board={board}", "--evidence", f"association={association_path}"]
    for role, path in evidence:
        args += ["--evidence", f"{role}={path}"]
    return gallery(*args, log=log)


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
        holder = read_json(LATEST, {}).get("run_id")
        message = f"skipped: another render run holds {LOCK} (running: {holder})"
        print(message, flush=True)
        append_history({"run_id": run_id, "ok": None, "skipped": True, "reason": message,
                        "at": started.isoformat()})
        return 0
    run_dir = RUNS / run_id
    run_dir.mkdir()
    log = Log(run_dir / "job.log")
    status = {"schema": "proximal.agent-ee-render-job.status/1", "run_id": run_id, "run_dir": str(run_dir),
              "started_at": started.isoformat(), "state": "running", "ok": None,
              "pid": os.getpid(), "unit": os.environ.get("INVOCATION_ID") and "agent-ee-render-job.service"}
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
        fetch(log)
        commit = git("rev-parse", f"{REF}^{{commit}}").stdout.decode().strip()
        meta = git("show", "-s", "--format=%cI%x00%s", commit).stdout.decode().strip().split("\x00")
        log(f"fome-mc {REF} = {commit} ({meta[0]}) {meta[1]}")
        board = extract(commit, run_dir / "snapshot")
        board_text = board.read_text()
        board_sha = sha256_file(board)
        project = board.with_suffix(".kicad_pro")
        project_sha = sha256_file(project) if project.is_file() else None
        items = copper(board_text)
        log(f"board {BOARD} sha256 {board_sha}; project sha256 {project_sha}; items {items}")
        models_summary, models_digest = model_identity(board, log)
        identity = {"board_sha256": board_sha, "project_sha256": project_sha, "models_digest": models_digest,
                    "kicad": kicad_version(), "settings": SETTINGS, "app": app_identity()}
        identity_digest = sha256_bytes(json.dumps(identity, sort_keys=True).encode())
        state = read_json(STATE, {}) or {}
        previous = state.get("last_publication")
        previous_exists = bool(previous) and (GALLERY_ROOT / "bundles" / previous["bundle"] / "manifest.json").is_file()
        board_changed = not previous_exists or previous.get("board_sha256") != board_sha
        inputs_changed = not previous_exists or previous.get("identity_digest") != identity_digest
        index = read_json(GALLERY_ROOT / "index.json", []) or []
        same_board_elsewhere = [e.get("id") for e in index if e.get("board_sha256") == board_sha
                                and (not previous or e.get("id") != previous.get("bundle"))]
        readme_path = board.parent / "README.md"
        readme_text = readme_path.read_text(errors="replace") if readme_path.is_file() else ""
        readme_binds_board = board_sha in readme_text
        routing_value = "unrouted" if items["segment"] + items["arc"] + items["via"] == 0 else "routed"
        if routing_value == "unrouted":
            routing_note = "UNROUTED: the committed board has no tracks, arcs or vias"
        else:
            routing_note = (f"copper present ({items['segment']} segments, {items['arc']} arcs, {items['via']} vias, "
                            f"{items['zone']} zones); routing completeness NOT verified by this job; "
                            "no routing acceptance is claimed")
        change = ("board-changed" if board_changed else
                  "board-unchanged-inputs-changed" if inputs_changed else "board-unchanged")
        log(f"change: {change} (previous publication: {previous and previous.get('bundle')}; "
            f"same board elsewhere in gallery: {same_board_elsewhere})")

        evidence_dir = run_dir / "evidence"
        evidence_dir.mkdir()
        readme_copy = None
        if readme_binds_board:
            readme_copy = evidence_dir / f"fome-mc-main-{commit[:12]}_telemetry-pod-README.md"
            shutil.copyfile(readme_path, readme_copy)
        receipt = {
            "schema": SCHEMA, "run_id": run_id, "checked_at": now().isoformat(),
            "owner_instruction": "telemetry-pod render job, ~every 4 h, relayed via agent-521 campaign "
                                 "process 2026-10-22; job owner agent-449",
            "source": {"repository": str(FOME), "ref": REF, "commit": commit, "commit_date": meta[0],
                       "commit_subject": meta[1], "board_path": BOARD,
                       "kind": "committed fome-mc main board extracted with git archive; this is the "
                               "committed fome-mc main board, which may be older than the newest agent-ee "
                               "placement iteration published by other agents"},
            "board": {"sha256": board_sha, "project_sha256": project_sha, **items},
            "models": {"KICAD10_3DMODEL_DIR": MODEL_DIR, "summary": models_summary, "digest": models_digest},
            "routing": {"gallery_value": routing_value, "statement": routing_note},
            "qualification": {"state": "not qualified",
                              "statement": "NOT QUALIFIED. This scheduled render job performs no qualification; "
                                           "the board is treated as unqualified unless evidence says otherwise, "
                                           "and no acceptance is claimed.",
                              "fome_mc_readme_names_this_board_sha256": readme_binds_board},
            "change": {"label": change, "board_changed_since_last_job_publication": board_changed,
                       "render_inputs_changed": inputs_changed, "previous_publication": previous,
                       "same_board_in_gallery_from_other_publishers": same_board_elsewhere},
            "identity": identity, "identity_digest": identity_digest,
        }
        result.update(fome_mc_commit=commit, board_sha256=board_sha, change=change, routing=routing_note,
                      qualification="not qualified")
        if not inputs_changed:
            receipt["publication"] = {"bundle": previous["bundle"], "new_bundle": False,
                                      "note": "unchanged: no new render published; status re-attached"}
            receipt_path = evidence_dir / f"render-job_fome-mc-main-{commit[:12]}_{change}_not-qualified_{run_id}.json"
            write_json(receipt_path, receipt)
            status_id = attach_status(previous["bundle"], board, receipt_path, evidence_dir, readme_copy,
                                      routing_value, log)
            log(f"board unchanged since bundle {previous['bundle']}; attached status {status_id}; no re-render")
            shutil.rmtree(run_dir / "snapshot")
            result.update(ok=True, bundle=previous["bundle"], new_bundle=False, status_id=status_id,
                          label=previous.get("label"), stage=STAGE)
        else:
            from agent_ee.render3d import render_board
            env_backup = os.environ.get("KICAD10_3DMODEL_DIR")
            os.environ["KICAD10_3DMODEL_DIR"] = MODEL_DIR
            try:
                manifest_path = render_board(board, run_dir / "renders", width=SETTINGS["width"],
                                             height=SETTINGS["height"], quality=SETTINGS["quality"],
                                             jobs=SETTINGS["jobs"], timeout=SETTINGS["timeout"], progress=log)
            finally:
                if env_backup is None:
                    os.environ.pop("KICAD10_3DMODEL_DIR", None)
                else:
                    os.environ["KICAD10_3DMODEL_DIR"] = env_backup
            manifest = read_json(manifest_path)
            log(f"render completed in {manifest.get('duration_seconds')} s; manifest {manifest_path}")
            revision = int(state.get("revision", 0)) + 1
            label = f"Revision {revision}"
            bundle = gallery("publish", "--renders", str(run_dir / "renders"), "--label", label,
                             "--stage", STAGE, log=log)
            if not re.fullmatch(r"[a-f0-9]{12}-[a-f0-9]{12}", bundle):
                raise RuntimeError(f"unexpected publish output: {bundle!r}")
            published = read_json(GALLERY_ROOT / "bundles" / bundle / "manifest.json", {})
            if published.get("board_sha256") != board_sha:
                raise RuntimeError("published manifest does not carry this board's sha256")
            receipt["publication"] = {"bundle": bundle, "new_bundle": True, "label": label, "stage": STAGE,
                                      "render_manifest_sha256": sha256_file(manifest_path),
                                      "images": manifest.get("images"),
                                      "render_duration_seconds": manifest.get("duration_seconds")}
            receipt_path = evidence_dir / f"render-job_fome-mc-main-{commit[:12]}_{change}_not-qualified_{run_id}.json"
            write_json(receipt_path, receipt)
            status_id = attach_status(bundle, board, receipt_path, evidence_dir, readme_copy, routing_value, log)
            log(f"published bundle {bundle} ({label}, stage {STAGE}); attached status {status_id}")
            state = {"revision": revision, "last_publication": {
                "bundle": bundle, "label": label, "board_sha256": board_sha, "identity_digest": identity_digest,
                "fome_mc_commit": commit, "published_at": published.get("published_at"), "run_id": run_id}}
            write_json(STATE, state)
            result.update(ok=True, bundle=bundle, new_bundle=True, status_id=status_id, label=label, stage=STAGE,
                          images={v: str(GALLERY_ROOT / "bundles" / bundle / f"{v}.png")
                                  for v in ("top", "bottom", "isometric")})
        result["receipt"] = str(receipt_path)
        code = 0
    except BaseException as exc:  # includes Terminated and KeyboardInterrupt from render_board
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
    append_history({k: result.get(k) for k in ("run_id", "ok", "reason", "bundle", "new_bundle", "change",
                                               "board_sha256", "fome_mc_commit", "wall_seconds", "finished_at")})
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
