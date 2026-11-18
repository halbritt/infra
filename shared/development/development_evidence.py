#!/usr/bin/env python3
"""Record, inspect and compare development evidence receipts.

record   capture repository identity, declared material files, review rules,
         caller-supplied observations and artifact digests into one receipt
inspect  validate a receipt and verify its artifacts (read-only)
compare  compare a receipt's source/input identity with a repository's current
         state (read-only); reports freshness separately from recorded outcome

The tool never runs a command named in a receipt or an observation, reads only
the files the caller declares, and decides no acceptance. See README.md.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

SCHEMA = "development-evidence/1"
INSPECTION_SCHEMA = "development-evidence-inspection/1"
COMPARISON_SCHEMA = "development-evidence-comparison/1"
OUTCOMES = ("clear-within-scope", "findings-open", "failed-check", "incomplete")
STATUSES = ("passed", "failed", "skipped", "not-run", "unknown")
KINDS = ("runtime", "source-reasoning", "model-judgment")
FILE_STATES = ("present", "missing", "unreadable", "unsupported")
EXIT = {"current": 0, "stale": 1, "unknown": 2, "missing": 3}
EXIT_USAGE = 64
OBJECT_ID = re.compile(r"\A(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
SHA256 = re.compile(r"\A[0-9a-f]{64}\Z")
TIMESTAMP = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
GIT_REDIRECTS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                 "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_COMMON_DIR")


class EvidenceError(Exception):
    """A diagnosable failure: bad input, unreadable repository or malformed record."""


# ---- primitives -------------------------------------------------------------

def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def fingerprint(path):
    """Describe one declared file without following a final symlink."""
    entry = {"state": "missing", "kind": None, "sha256": None, "size": None}
    try:
        info = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return entry
    except OSError:
        return dict(entry, state="unreadable")
    try:
        if os.path.islink(path):
            target = os.fsencode(os.readlink(path))
            return {"state": "present", "kind": "symlink", "sha256": sha256_bytes(target), "size": len(target)}
        if not os.path.isfile(path):
            return dict(entry, state="unsupported")
        with open(path, "rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        return {"state": "present", "kind": "file", "sha256": digest, "size": info.st_size}
    except OSError:
        return dict(entry, state="unreadable")


def relative_path_error(value):
    """Return why VALUE is not a safe relative POSIX path, or None."""
    if not isinstance(value, str) or not value or "\0" in value or "\\" in value:
        return "must be a non-empty relative POSIX path"
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("..", ".") for part in value.split("/")) or str(path) != value:
        return "must be a normalized relative path without '..'"
    return None


# ---- git --------------------------------------------------------------------

def git(repo, *args, text=True, ok=(0,)):
    env = {k: v for k, v in os.environ.items() if k not in GIT_REDIRECTS}
    env["GIT_OPTIONAL_LOCKS"] = "0"  # never refresh or lock the index: read-only
    command = ["git", "-c", "core.fsmonitor=false", "-C", str(repo), *args]
    try:
        done = subprocess.run(command, env=env, capture_output=True, check=False)
    except OSError as error:
        raise EvidenceError(f"cannot run git: {error}") from error
    if done.returncode not in ok:
        detail = done.stderr.decode(errors="replace").strip().splitlines()
        raise EvidenceError(f"git {args[0]} failed in {repo}: {detail[-1] if detail else done.returncode}")
    out = done.stdout
    return (out.decode(errors="surrogateescape").strip() if text else out), done.returncode


def resolve_commit(repo, revision):
    out, _ = git(repo, "rev-parse", "--verify", "--quiet", "--end-of-options", revision + "^{commit}")
    return out


def nonmaterial(path, declared):
    """True when PATH is an exact declared nonmaterial path or below a declared 'dir/'."""
    return any(path == item or (item.endswith("/") and path.startswith(item)) for item in declared)


def snapshot_digest(head, changes, staged):
    return sha256_bytes(canonical({"head": head, "changes": changes, "staged": staged}))


def repository_state(repo, exclude=(), ignore=()):
    """Current identity of REPO's tracked working state.

    EXCLUDE: top-relative paths accounted for elsewhere (material, receipt, artifacts).
    IGNORE: paths the caller classified as nonmaterial. Untracked files are listed with
    ls-files, which does not depend on status.showUntrackedFiles.
    """
    top, _ = git(repo, "rev-parse", "--show-toplevel")
    head = resolve_commit(top, "HEAD")
    tree, _ = git(top, "rev-parse", "--verify", "HEAD^{tree}")
    roots, _ = git(top, "rev-list", "--max-parents=0", "HEAD")
    raw, _ = git(top, "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--ignore-submodules=none",
                 "--name-status", "-z", "HEAD", "--", text=False)
    fields = [os.fsdecode(part) for part in raw.split(b"\0") if part]
    changes = []
    for status, path in zip(fields[0::2], fields[1::2]):
        found = fingerprint(os.path.join(top, path))
        changes.append({"path": path, "status": status, "state": found["state"],
                        "kind": found["kind"], "sha256": found["sha256"]})
    changes.sort(key=lambda item: item["path"])
    # Index against HEAD: a staged change can hide behind a working file restored to HEAD.
    raw, _ = git(top, "diff", "--cached", "--no-ext-diff", "--no-textconv", "--no-renames",
                 "--ignore-submodules=none", "--raw", "--no-abbrev", "-z", "HEAD", "--", text=False)
    fields = [os.fsdecode(part) for part in raw.split(b"\0") if part]
    staged = sorted(({"path": path, "status": meta.split()[4], "object": meta.split()[3]}
                     for meta, path in zip(fields[0::2], fields[1::2])), key=lambda item: item["path"])
    raw, _ = git(top, "ls-files", "--others", "--exclude-standard", "-z", text=False)
    skip = set(exclude)
    untracked = sorted(p for p in (os.fsdecode(part) for part in raw.split(b"\0") if part)
                       if p not in skip and not nonmaterial(p, ignore))
    return {
        "root": top, "head": head, "head_tree": tree,
        "roots_sha256": sha256_bytes(canonical(sorted(roots.split()))),
        "dirty": bool(changes or staged), "changes": changes, "staged": staged,
        "snapshot": snapshot_digest(head, changes, staged) if changes or staged else None,
        "untracked": untracked,
    }


def rules_at(top, revision, paths):
    files = []
    for path in paths:
        blob, code = git(top, "cat-file", "blob", f"{revision}:{path}", text=False, ok=(0, 128))
        files.append({"path": path, "state": "present" if code == 0 else "missing",
                      "sha256": sha256_bytes(blob) if code == 0 else None})
    return files


def inside(top, target):
    """TARGET (absolute) as a top-relative POSIX path, or None when outside."""
    parent = os.path.realpath(os.path.dirname(target))
    try:
        relative = os.path.relpath(os.path.join(parent, os.path.basename(target)), top)
    except ValueError:
        return None
    if relative == os.pardir or relative.startswith(os.pardir + os.sep) or relative == ".":
        return None
    return PurePosixPath(*Path(relative).parts).as_posix()


# ---- schema -----------------------------------------------------------------

def validate(record):
    """Return every reason RECORD is not a development-evidence/1 receipt."""
    errors = []

    def need(obj, where, key, check, describe):
        if not isinstance(obj, dict) or key not in obj:
            errors.append(f"{where}.{key}: required field is missing")
            return None
        if not check(obj[key]):
            errors.append(f"{where}.{key}: {describe}")
            return None
        return obj[key]

    def exact(obj, where, keys):
        if isinstance(obj, dict):
            for key in sorted(set(obj) - set(keys)):
                errors.append(f"{where}.{key}: unknown field")

    text = lambda v: isinstance(v, str) and v != "" and "\0" not in v  # noqa: E731
    opt_text = lambda v: v is None or text(v)  # noqa: E731
    oid = lambda v: isinstance(v, str) and bool(OBJECT_ID.match(v))  # noqa: E731
    opt_oid = lambda v: v is None or oid(v)  # noqa: E731
    digest = lambda v: isinstance(v, str) and bool(SHA256.match(v))  # noqa: E731
    opt_digest = lambda v: v is None or digest(v)  # noqa: E731
    stamp = lambda v: isinstance(v, str) and bool(TIMESTAMP.match(v))  # noqa: E731
    opt_stamp = lambda v: v is None or stamp(v)  # noqa: E731
    flag = lambda v: isinstance(v, bool)  # noqa: E731
    count = lambda v: isinstance(v, int) and not isinstance(v, bool) and v >= 0  # noqa: E731
    path = lambda v: relative_path_error(v) is None  # noqa: E731
    listing = lambda v: isinstance(v, list)  # noqa: E731

    if not isinstance(record, dict):
        return ["record: must be a JSON object"]
    if record.get("schema") != SCHEMA:
        return [f"record.schema: must be {SCHEMA!r}, found {record.get('schema')!r}; other versions are not read"]
    exact(record, "record", ("schema", "hash", "recorded_at", "project", "intent_source", "repository",
                             "subject", "rules", "material", "nonmaterial", "unaccounted_inputs",
                             "observations", "outcome", "unknowns", "annotations"))
    need(record, "record", "hash", lambda v: v == "sha256", "must be 'sha256'")
    need(record, "record", "recorded_at", stamp, "must be UTC 'YYYY-MM-DDTHH:MM:SSZ'")
    need(record, "record", "project", text, "must be a non-empty string")
    need(record, "record", "intent_source", opt_text, "must be a string or null")
    need(record, "record", "outcome", lambda v: v in OUTCOMES, f"must be one of {', '.join(OUTCOMES)}")
    unknowns = need(record, "record", "unknowns", listing, "must be a list of strings")
    if unknowns is not None and not all(text(item) for item in unknowns):
        errors.append("record.unknowns: must be a list of non-empty strings")
    for key, rule in (("unaccounted_inputs", text),
                      ("nonmaterial", lambda v: isinstance(v, str) and relative_path_error(v.removesuffix("/")) is None)):
        values = need(record, "record", key, listing, "must be a list")
        if values is not None and not all(rule(item) for item in values):
            errors.append(f"record.{key}: every entry must be a " +
                          ("non-empty string" if key == "unaccounted_inputs" else "relative path or 'directory/'"))
    notes = record.get("annotations", {})
    if not isinstance(notes, dict) or not all(isinstance(v, str) for v in notes.values()):
        errors.append("record.annotations: must be an object of strings")

    repo = need(record, "record", "repository", lambda v: isinstance(v, dict), "must be an object")
    if repo is not None:
        exact(repo, "repository", ("root", "roots_sha256"))
        need(repo, "repository", "root", text, "must be a non-empty string")
        need(repo, "repository", "roots_sha256", digest, "must be a SHA-256 hex digest")

    subject = need(record, "record", "subject", lambda v: isinstance(v, dict), "must be an object")
    if subject is not None:
        exact(subject, "subject", ("base", "head", "head_tree", "dirty", "candidate", "tree", "snapshot",
                                   "changes", "staged", "untracked_count"))
        need(subject, "subject", "base", opt_oid, "must be a full commit ID or null")
        need(subject, "subject", "head", oid, "must be a full commit ID")
        need(subject, "subject", "head_tree", oid, "must be a full tree ID")
        dirty = need(subject, "subject", "dirty", flag, "must be true or false")
        need(subject, "subject", "candidate", opt_oid, "must be a full commit ID or null")
        need(subject, "subject", "tree", opt_oid, "must be a full tree ID or null")
        need(subject, "subject", "snapshot", opt_digest, "must be a SHA-256 hex digest or null")
        need(subject, "subject", "untracked_count", count, "must be a non-negative integer")
        changes = need(subject, "subject", "changes", listing, "must be a list")
        for index, change in enumerate(changes or []):
            where = f"subject.changes[{index}]"
            exact(change, where, ("path", "status", "state", "kind", "sha256"))
            need(change, where, "path", path, "must be a normalized relative path")
            need(change, where, "status", text, "must be a string")
            need(change, where, "state", lambda v: v in FILE_STATES, f"must be one of {', '.join(FILE_STATES)}")
            need(change, where, "kind", opt_text, "must be a string or null")
            need(change, where, "sha256", opt_digest, "must be a SHA-256 hex digest or null")
        staged = need(subject, "subject", "staged", listing, "must be a list")
        for index, item in enumerate(staged or []):
            where = f"subject.staged[{index}]"
            exact(item, where, ("path", "status", "object"))
            need(item, where, "path", path, "must be a normalized relative path")
            need(item, where, "status", text, "must be a string")
            need(item, where, "object", oid, "must be a full object ID")
        if dirty is True and (subject.get("candidate") is not None or subject.get("tree") is not None
                              or subject.get("snapshot") is None or not (changes or staged)):
            errors.append("subject: a dirty snapshot needs snapshot and changes or staged entries, "
                          "and null candidate and tree")
        elif dirty is True and not errors and subject["snapshot"] != snapshot_digest(
                subject["head"], changes, staged):
            errors.append("subject.snapshot: does not match the digest of head, changes and staged")
        if changes and [c.get("path") for c in changes if isinstance(c, dict)] != sorted(
                {c.get("path") for c in changes if isinstance(c, dict)}, key=str):
            errors.append("subject.changes: paths must be unique and sorted")
        if dirty is False and (subject.get("candidate") != subject.get("head") or subject.get("snapshot") is not None
                               or subject.get("tree") != subject.get("head_tree") or changes or staged):
            errors.append("subject: a clean subject needs candidate = head, tree = head_tree and no snapshot")

    rules = need(record, "record", "rules", lambda v: v is None or isinstance(v, dict), "must be an object or null")
    if rules is not None:
        exact(rules, "rules", ("revision", "files"))
        revision = need(rules, "rules", "revision", oid, "must be a full commit ID")
        if subject is not None and revision is not None and revision != subject.get("base"):
            errors.append("rules.revision: must equal subject.base")
        for index, item in enumerate(need(rules, "rules", "files", listing, "must be a list") or []):
            where = f"rules.files[{index}]"
            exact(item, where, ("path", "state", "sha256"))
            need(item, where, "path", path, "must be a normalized relative path")
            state = need(item, where, "state", lambda v: v in ("present", "missing"), "must be present or missing")
            value = need(item, where, "sha256", opt_digest, "must be a SHA-256 hex digest or null")
            if (state == "present") != (value is not None) and state is not None:
                errors.append(f"{where}: sha256 is required exactly when state is present")

    def files(items, where_name):
        for index, item in enumerate(items or []):
            where = f"{where_name}[{index}]"
            exact(item, where, ("path", "state", "kind", "sha256", "size"))
            need(item, where, "path", path, "must be a normalized relative path")
            state = need(item, where, "state", lambda v: v in FILE_STATES, f"must be one of {', '.join(FILE_STATES)}")
            need(item, where, "kind", lambda v: v in (None, "file", "symlink"), "must be file, symlink or null")
            value = need(item, where, "sha256", opt_digest, "must be a SHA-256 hex digest or null")
            need(item, where, "size", lambda v: v is None or count(v), "must be a non-negative integer or null")
            if state is not None and (state == "present") != (value is not None):
                errors.append(f"{where}: sha256 is required exactly when state is present")

    material = need(record, "record", "material", listing, "must be a list")
    files(material, "material")
    names = [m.get("path") for m in material or [] if isinstance(m, dict)]
    if len(names) != len(set(names)):
        errors.append("material: paths must be unique")
    for index, item in enumerate(need(record, "record", "observations", listing, "must be a list") or []):
        where = f"observations[{index}]"
        exact(item, where, ("claim", "kind", "command", "cwd", "status", "exit_code", "started_at",
                            "ended_at", "reason", "artifacts"))
        need(item, where, "claim", text, "must be a non-empty string")
        need(item, where, "kind", lambda v: v in KINDS, f"must be one of {', '.join(KINDS)}")
        need(item, where, "command", lambda v: v is None or (isinstance(v, list) and v and all(
            isinstance(part, str) for part in v)), "must be a list of strings or null; it is never executed")
        need(item, where, "cwd", opt_text, "must be a string or null")
        status = need(item, where, "status", lambda v: v in STATUSES, f"must be one of {', '.join(STATUSES)}")
        need(item, where, "exit_code", lambda v: v is None or (isinstance(v, int) and not isinstance(v, bool)),
             "must be an integer or null")
        need(item, where, "started_at", opt_stamp, "must be UTC 'YYYY-MM-DDTHH:MM:SSZ' or null")
        need(item, where, "ended_at", opt_stamp, "must be UTC 'YYYY-MM-DDTHH:MM:SSZ' or null")
        reason = need(item, where, "reason", opt_text, "must be a string or null")
        if status in ("skipped", "not-run", "unknown") and reason is None and "reason" in item:
            errors.append(f"{where}.reason: required when status is {status}")
        files(need(item, where, "artifacts", listing, "must be a list"), f"{where}.artifacts")
    return errors


def load(receipt):
    """Return (record, raw bytes). Raises FileNotFoundError or EvidenceError."""
    raw = Path(receipt).read_bytes()
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise EvidenceError(f"{receipt}: not valid UTF-8 JSON: {error}") from error
    errors = validate(record)
    if errors:
        raise EvidenceError(f"{receipt}: malformed {SCHEMA} record: " + "; ".join(errors))
    return record, raw


def artifact_checks(record, receipt):
    """Recompute every recorded artifact relative to the receipt's directory."""
    base = Path(receipt).resolve().parent
    checks = []
    for index, observation in enumerate(record["observations"]):
        for artifact in observation["artifacts"]:
            found = fingerprint(base / artifact["path"])
            if found["kind"] == "symlink":
                found = {"state": "unsupported", "kind": None, "sha256": None, "size": None}
            if artifact["state"] != "present":
                verdict = "unavailable"   # never recorded with a digest
            elif found["state"] != "present":
                verdict = found["state"]
            else:
                verdict = "verified" if found["sha256"] == artifact["sha256"] else "changed"
            checks.append({"observation": index, "path": artifact["path"], "result": verdict,
                           "recorded_sha256": artifact["sha256"], "current_sha256": found["sha256"]})
    return checks


# ---- operations -------------------------------------------------------------

def read_observations(sources):
    observations = []
    for source in sources:
        try:
            raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
            value = json.loads(raw)
        except (OSError, ValueError) as error:
            raise EvidenceError(f"observation input {source}: {error}") from error
        items = value if isinstance(value, list) else [value]
        for item in items:
            if not isinstance(item, dict):
                raise EvidenceError(f"observation input {source}: each observation must be a JSON object")
            observations.append(item)
    return observations


def record(repo, output, project, outcome, base=None, intent=None, material=(), rules=(),
           observations=(), unknowns=(), annotations=None, cwd=None, nonmaterial_paths=(),
           unaccounted_inputs=()):
    """Build and write one receipt. Returns (record, sha256 of the written file)."""
    cwd = Path(cwd or os.getcwd())
    output = Path(output)
    output = output if output.is_absolute() else cwd / output
    if output.exists() or output.is_symlink():
        raise EvidenceError(f"{output}: already exists; a receipt is written once and never overwritten")
    if not output.parent.is_dir():
        raise EvidenceError(f"{output.parent}: receipt directory does not exist")
    if outcome not in OUTCOMES:
        raise EvidenceError(f"outcome must be one of {', '.join(OUTCOMES)}")
    top, _ = git(repo, "rev-parse", "--show-toplevel")
    if rules and not base:
        raise EvidenceError("--rules needs --base: review rules are read from the established base revision")
    base_commit = resolve_commit(top, base) if base else None

    declared = []
    for item in material:
        target = Path(item) if os.path.isabs(item) else cwd / item
        relative = inside(top, str(target))
        if relative is None:
            raise EvidenceError(f"material file {item}: is outside the repository {top}")
        declared.append(relative)
    declared = sorted(set(declared))
    ignore = []
    for item in nonmaterial_paths:
        problem = relative_path_error(item.removesuffix("/"))
        if problem:
            raise EvidenceError(f"nonmaterial path {item!r}: {problem} (relative to the repository root)")
        ignore.append(item)
    ignore = sorted(set(ignore))
    rule_paths = []
    for item in rules:
        problem = relative_path_error(item)
        if problem:
            raise EvidenceError(f"rules path {item!r}: {problem} (relative to the repository root)")
        rule_paths.append(item)

    receipt_dir = output.parent.resolve()
    shaped = []
    for index, source in enumerate(observations):
        item = dict(source)
        artifacts = []
        for name in item.get("artifacts") or []:
            problem = relative_path_error(name)
            if problem:
                raise EvidenceError(f"observation {index} artifact {name!r}: {problem} (relative to the receipt)")
            found = fingerprint(receipt_dir / name)
            if found["kind"] == "symlink":
                found = {"state": "unsupported", "kind": None, "sha256": None, "size": None}
            artifacts.append({"path": name, **found})
        shaped.append({"claim": item.get("claim"), "kind": item.get("kind"), "command": item.get("command"),
                       "cwd": item.get("cwd"), "status": item.get("status"), "exit_code": item.get("exit_code"),
                       "started_at": item.get("started_at"), "ended_at": item.get("ended_at"),
                       "reason": item.get("reason"), "artifacts": artifacts})
        extra = sorted(set(item) - set(shaped[-1]))
        if extra:
            raise EvidenceError(f"observation {index}: unknown field(s) {', '.join(extra)}")

    evidence_files = {p for p in (inside(top, str(receipt_dir / a["path"])) for o in shaped for a in o["artifacts"])
                      if p}
    own = inside(top, str(output))
    state = repository_state(top, exclude=set(declared) | evidence_files | ({own} if own else set()),
                             ignore=ignore)
    result = {
        "schema": SCHEMA, "hash": "sha256", "recorded_at": now(), "project": project,
        "intent_source": intent,
        "repository": {"root": state["root"], "roots_sha256": state["roots_sha256"]},
        "subject": {
            "base": base_commit, "head": state["head"], "head_tree": state["head_tree"],
            "dirty": state["dirty"],
            # A dirty working state is never identified by the commit under it.
            "candidate": None if state["dirty"] else state["head"],
            "tree": None if state["dirty"] else state["head_tree"],
            "snapshot": state["snapshot"], "changes": state["changes"], "staged": state["staged"],
            "untracked_count": len(state["untracked"]),
        },
        "rules": {"revision": base_commit, "files": rules_at(top, base_commit, rule_paths)} if rule_paths else None,
        "material": [{"path": path, **fingerprint(os.path.join(top, path))} for path in declared],
        "nonmaterial": ignore, "unaccounted_inputs": list(unaccounted_inputs),
        "observations": shaped, "outcome": outcome, "unknowns": list(unknowns),
        "annotations": dict(annotations or {}),
    }
    errors = validate(result)
    if errors:
        raise EvidenceError("refusing to write a malformed record: " + "; ".join(errors))
    data = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False).encode() + b"\n"
    try:
        with open(output, "xb") as handle:
            handle.write(data)
    except FileExistsError as error:
        raise EvidenceError(f"{output}: already exists; a receipt is written once") from error
    return result, sha256_bytes(data)


def unavailable(record_):
    """Recorded inputs and artifacts that never had a digest."""
    subject = record_["subject"]
    items = [f"material {m['path']} ({m['state']})" for m in record_["material"] if m["state"] != "present"]
    items += [f"tracked change {c['path']} ({c['state']})" for c in subject["changes"]
              if c["state"] not in ("present", "missing")]
    if subject["untracked_count"]:
        items.append(f"{subject['untracked_count']} untracked file(s) neither declared material nor nonmaterial")
    items += [f"unaccounted input: {item}" for item in record_["unaccounted_inputs"]]
    items += [f"artifact {a['path']} ({a['state']})" for o in record_["observations"] for a in o["artifacts"]
              if a["state"] != "present"]
    return items


def inspect(receipt):
    """Validate RECEIPT and verify its artifacts. Returns (report, exit code)."""
    report = {"schema": INSPECTION_SCHEMA, "receipt": str(receipt), "receipt_sha256": None, "valid": False,
              "diagnostics": [], "artifacts": [], "record": None}
    try:
        loaded, raw = load(receipt)
    except FileNotFoundError:
        report["diagnostics"].append(f"{receipt}: receipt does not exist")
        return report, EXIT["missing"]
    except (OSError, EvidenceError) as error:
        report["diagnostics"].append(str(error))
        return report, EXIT["unknown"]
    report.update(valid=True, receipt_sha256=sha256_bytes(raw), record=loaded,
                  artifacts=artifact_checks(loaded, receipt))
    report["diagnostics"] += [f"recorded without a digest: {item}" for item in unavailable(loaded)]
    bad = [a for a in report["artifacts"] if a["result"] != "verified"]
    report["diagnostics"] += [f"artifact {a['path']}: {a['result']}" for a in bad]
    statuses = {o["status"] for o in loaded["observations"]}
    if loaded["outcome"] == "clear-within-scope" and statuses & {"failed", "unknown"}:
        report["diagnostics"].append("outcome is clear-within-scope but an observation is failed or unknown; "
                                     "the responsible workflow decides, this tool does not")
    return report, 1 if bad else 0


def compare(receipt, repo, base=None):
    """Compare RECEIPT's identity with REPO now. Returns (report, exit code)."""
    report = {"schema": COMPARISON_SCHEMA, "receipt": str(receipt), "receipt_sha256": None,
              "freshness": "unknown", "outcome": None, "current_subject": None, "reasons": [], "limits": []}

    def reason(kind, code, detail, path=None):
        report["reasons"].append({"class": kind, "code": code, "path": path, "detail": detail})

    def finish():
        kinds = {item["class"] for item in report["reasons"]}
        for name in ("missing", "stale", "unknown"):
            if name in kinds:
                report["freshness"] = name
                break
        else:
            report["freshness"] = "current"
        return report, EXIT[report["freshness"]]

    def observe_only():
        try:
            state = repository_state(repo)
        except EvidenceError:
            return
        report["current_subject"] = {"head": state["head"], "dirty": state["dirty"], "snapshot": state["snapshot"],
                                     "candidate": None if state["dirty"] else state["head"]}

    try:
        loaded, raw = load(receipt)
    except FileNotFoundError:
        reason("missing", "receipt-missing", "receipt does not exist; no evidence is assumed")
        observe_only()
        return finish()
    except (OSError, EvidenceError) as error:
        reason("unknown", "receipt-malformed", str(error))
        observe_only()
        return finish()
    report.update(receipt_sha256=sha256_bytes(raw), outcome=loaded["outcome"])
    subject = loaded["subject"]
    try:
        top, _ = git(repo, "rev-parse", "--show-toplevel")
        receipt_dir = Path(receipt).resolve().parent
        skip = {m["path"] for m in loaded["material"]}
        skip |= {p for p in (inside(top, str(receipt_dir / a["path"]))
                             for o in loaded["observations"] for a in o["artifacts"]) if p}
        own = inside(top, str(Path(receipt).resolve()))
        state = repository_state(top, exclude=skip | ({own} if own else set()), ignore=loaded["nonmaterial"])
        report["current_subject"] = {"head": state["head"], "dirty": state["dirty"], "snapshot": state["snapshot"],
                                     "candidate": None if state["dirty"] else state["head"]}
        current_base = resolve_commit(top, base) if base else None
    except EvidenceError as error:
        reason("unknown", "repository-unreadable", str(error))
        return finish()

    if state["roots_sha256"] != loaded["repository"]["roots_sha256"]:
        reason("stale", "repository-changed", "root commits differ from the recorded repository")
    if subject["base"] and current_base is None:
        reason("unknown", "base-not-supplied", "the receipt records a base; pass --base to compare it")
    elif current_base and not subject["base"]:
        reason("unknown", "base-not-recorded", "the receipt records no base to compare with --base")
    elif current_base and current_base != subject["base"]:
        reason("stale", "base-changed", f"recorded {subject['base']}, current {current_base}")

    if subject["dirty"]:
        if not state["dirty"]:
            reason("stale", "snapshot-changed", f"recorded a dirty snapshot; the tree is now clean at {state['head']}")
        elif state["snapshot"] != subject["snapshot"]:
            reason("stale", "snapshot-changed", "tracked working or staged changes differ from the recorded snapshot")
    elif state["dirty"]:
        paths = ", ".join(sorted({c["path"] for c in state["changes"] + state["staged"]})[:5])
        reason("stale", "working-tree-dirty",
               f"working or staged files differ from HEAD ({paths}); HEAD does not identify this state")
    elif state["head"] != subject["candidate"]:
        reason("stale", "candidate-changed", f"recorded {subject['candidate']}, current {state['head']}")
    if state["head"] == subject["head"] and state["head_tree"] != subject["head_tree"]:
        reason("unknown", "receipt-inconsistent",
               f"recorded tree {subject['head_tree']} is not the tree of commit {state['head']}")
    for change in subject["changes"]:
        if change["state"] not in ("present", "missing"):
            reason("unknown", "change-unfingerprinted",
                   f"recorded tracked change was {change['state']} and has no content digest", change["path"])
    for change in state["changes"]:
        if change["state"] not in ("present", "missing"):
            reason("unknown", "change-unfingerprinted",
                   f"tracked change is {change['state']} (for example a submodule) and has no content digest",
                   change["path"])

    if loaded["rules"] and current_base:
        now_rules = {r["path"]: r for r in rules_at(top, current_base, [r["path"] for r in loaded["rules"]["files"]])}
        for rule in loaded["rules"]["files"]:
            found = now_rules[rule["path"]]
            if (found["state"], found["sha256"]) != (rule["state"], rule["sha256"]):
                reason("stale", "rules-changed", f"recorded {rule['state']}, at the current base {found['state']}",
                       rule["path"])

    for item in loaded["material"]:
        found = fingerprint(os.path.join(top, item["path"]))
        if item["state"] != "present":
            reason("unknown", "material-unavailable",
                   f"recorded as {item['state']}; it was never fingerprinted", item["path"])
        elif found["state"] == "missing":
            reason("stale", "material-missing", "recorded present, now absent", item["path"])
        elif found["state"] != "present":
            reason("unknown", "material-unreadable", f"now {found['state']}", item["path"])
        elif (found["kind"], found["sha256"]) != (item["kind"], item["sha256"]):
            reason("stale", "material-changed", "content differs from the recorded digest", item["path"])

    if subject["untracked_count"]:
        reason("unknown", "untracked-unaccounted-at-record",
               f"recorded with {subject['untracked_count']} untracked file(s) neither material nor nonmaterial")
    if state["untracked"]:
        reason("unknown", "untracked-unaccounted",
               f"{len(state['untracked'])} untracked file(s) are neither declared material nor nonmaterial "
               f"and are not fingerprinted: {', '.join(state['untracked'][:5])}")
    for item in loaded["unaccounted_inputs"]:
        reason("unknown", "input-unaccounted", item)
    if loaded["nonmaterial"]:
        report["limits"].append("declared nonmaterial, not fingerprinted: " + ", ".join(loaded["nonmaterial"]))

    for check in artifact_checks(loaded, receipt):
        if check["result"] != "verified":
            reason("unknown", "artifact-" + check["result"], "recorded evidence cannot be confirmed", check["path"])
    report["limits"] += [f"coverage unknown: {item}" for item in loaded["unknowns"]]
    report["limits"].append("outcome is the recorded one; it is not re-evaluated here")
    return finish()


# ---- command line -----------------------------------------------------------

class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: {message}\n")


def emit(report, as_json, lines):
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print("\n".join(lines))


def main(argv=None):
    parser = Parser(prog="development-evidence", description=__doc__,
                    formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=SCHEMA)
    commands = parser.add_subparsers(dest="operation", required=True, parser_class=Parser)

    rec = commands.add_parser("record", help="write one receipt for the repository's current state")
    rec.add_argument("--repo", default=".", help="repository or a directory inside it (default: .)")
    rec.add_argument("--output", required=True, help="new receipt file; never overwritten")
    rec.add_argument("--project", required=True)
    rec.add_argument("--outcome", required=True, choices=OUTCOMES)
    rec.add_argument("--base", help="established base revision (resolved to a full commit ID)")
    rec.add_argument("--intent", help="where the intent came from, such as a task reference")
    rec.add_argument("--material", action="append", default=[], metavar="FILE",
                     help="material file inside the repository, including ignored or generated (repeatable)")
    rec.add_argument("--rules", action="append", default=[], metavar="PATH",
                     help="review rule path, read from --base and relative to the repository root (repeatable)")
    rec.add_argument("--observations", action="append", default=[], metavar="JSON",
                     help="file holding one observation object or a list; '-' reads stdin (repeatable)")
    rec.add_argument("--nonmaterial", action="append", default=[], metavar="PATH",
                     help="untracked path, or 'directory/', the caller classifies as not material; relative to "
                          "the repository root, never read (repeatable)")
    rec.add_argument("--unaccounted-input", action="append", default=[], metavar="TEXT",
                     help="a material input that could not be fingerprinted; the receipt can never be current "
                          "(repeatable)")
    rec.add_argument("--unknown", action="append", default=[], metavar="TEXT",
                     help="a limit on what the assessment covered; not for unfingerprinted inputs (repeatable)")
    rec.add_argument("--annotation", action="append", default=[], metavar="KEY=VALUE",
                     help="free-form string, never interpreted (repeatable)")
    rec.add_argument("--json", action="store_true", help="print the receipt path and digest as JSON")

    ins = commands.add_parser("inspect", help="validate a receipt and verify its artifacts (read-only)")
    ins.add_argument("receipt")
    ins.add_argument("--json", action="store_true")

    com = commands.add_parser("compare", help="compare a receipt with a repository's current state (read-only)")
    com.add_argument("receipt")
    com.add_argument("--repo", default=".", help="repository to compare (default: .)")
    com.add_argument("--base", help="current established base revision, such as origin/master")
    com.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.operation == "record":
            notes = {}
            for item in args.annotation:
                key, separator, value = item.partition("=")
                if not separator or not key:
                    parser.error(f"--annotation needs KEY=VALUE, found {item!r}")
                notes[key] = value
            result, digest = record(args.repo, args.output, args.project, args.outcome, base=args.base,
                                    intent=args.intent, material=args.material, rules=args.rules,
                                    observations=read_observations(args.observations), unknowns=args.unknown,
                                    annotations=notes, nonmaterial_paths=args.nonmaterial,
                                    unaccounted_inputs=args.unaccounted_input)
            subject = result["subject"]
            missing = unavailable(result)
            for item in missing:
                print(f"development-evidence: recorded without a digest: {item}", file=sys.stderr)
            summary = {"receipt": str(Path(args.output).resolve()), "receipt_sha256": digest, "schema": SCHEMA,
                       "dirty": subject["dirty"], "candidate": subject["candidate"],
                       "snapshot": subject["snapshot"], "unavailable": missing,
                       "can_be_current": not missing}
            emit(summary, args.json, [
                f"receipt {summary['receipt']}", f"sha256 {digest}",
                f"identity {'dirty snapshot ' + subject['snapshot'] if subject['dirty'] else 'commit ' + subject['head']}",
                f"outcome {result['outcome']}"])
            return 0
        if args.operation == "inspect":
            report, code = inspect(args.receipt)
            lines = [f"receipt {report['receipt']}", f"valid {str(report['valid']).lower()}"]
            if report["record"]:
                loaded = report["record"]
                subject = loaded["subject"]
                lines += [
                    f"sha256 {report['receipt_sha256']}", f"project {loaded['project']}",
                    f"recorded_at {loaded['recorded_at']}", f"base {subject['base'] or 'not recorded'}",
                    f"identity {'dirty snapshot ' + subject['snapshot'] if subject['dirty'] else 'commit ' + subject['head']}",
                    f"outcome {loaded['outcome']}",
                    f"material {len(loaded['material'])}  observations {len(loaded['observations'])}  "
                    f"artifacts {len(report['artifacts'])}  unknowns {len(loaded['unknowns'])}"]
                lines += [f"observation {o['status']} [{o['kind']}] {o['claim']}" for o in loaded["observations"]]
            lines += [f"diagnostic {item}" for item in report["diagnostics"]]
            emit(report, args.json, lines)
            return code
        report, code = compare(args.receipt, args.repo, base=args.base)
        lines = [f"freshness {report['freshness']}", f"outcome {report['outcome'] or 'unavailable'}"]
        lines += [f"{r['class']} {r['code']}{' ' + r['path'] if r['path'] else ''}: {r['detail']}"
                  for r in report["reasons"]]
        lines += [f"limit {item}" for item in report["limits"]]
        emit(report, args.json, lines)
        return code
    except EvidenceError as error:
        print(f"development-evidence: {error}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
