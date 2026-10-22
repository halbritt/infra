#!/usr/bin/env bash
# Advance the render job's pin to a newer consistent campaign snapshot.
#
#   render-job-pin.sh [--dry-run] <board.kicad_pcb> <project.kicad_pro> [models-dir] <label> <scope-note>
#
# PIN POLICY (agent-521, 2026-10-22): the pin advances to EACH newer consistent campaign
# snapshot, even if it is unrouted or unqualified. Engineering qualification does NOT gate
# progress renders. Each render is labelled with its actual routing state, "not qualified"
# and its actual scope. Run this only on a consistent snapshot: one that nothing is
# writing to, such as a retained candidate or a j6 run output. Never run it on a live
# worktree file that is still being written.
#
# The helper copies the board, the project (renamed to match the board) and every
# project-local model the board references (${KIPRJMOD}/... or a relative path) into
# pinned/<board sha256>/ and makes them read-only. It counts footprints and mounting holes
# against the campaign scope (EXPECTED_NON_HOLE / EXPECTED_HOLES, default: the current
# pin's), then replaces pin.json atomically while holding the job lock. It refuses a board
# identical to the current pin, the 112-footprint pilot (refuse list), a missing
# project-local model or an invalid label.
#   models-dir: the directory that ${KIPRJMOD}-relative model paths resolve against.
#               By default, the board's own directory.
#   label:      the gallery label, "KIND NUMBER" (e.g. "Iteration 9"). The pin name is
#               PIN_NAME, or the label lowercased with dashes (at most 16 characters).
#   stage:      PIN_STAGE (default: diagnostic). Only diagnostic or placement is allowed.
set -euo pipefail
JOB="${RENDER_JOB_DIR:-$HOME/.local/share/agent-ee-render-job}"
DRY=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY=1; shift; fi
case $# in
  4) BOARD=$1 PROJECT=$2 MODELS="" LABEL=$3 NOTE=$4 ;;
  5) BOARD=$1 PROJECT=$2 MODELS=$3 LABEL=$4 NOTE=$5 ;;
  *) sed -n '2,4p' "$0" >&2; exit 2 ;;
esac
exec 9>>"$JOB/job.lock"
if [[ $DRY == 0 ]]; then
  flock -w 1500 9 || { echo "render-job-pin: job lock busy for 25 min; nothing changed" >&2; exit 1; }
fi
exec python3 -I - "$JOB" "$DRY" "$BOARD" "$PROJECT" "$MODELS" "$LABEL" "$NOTE" <<'PY'
import datetime, hashlib, json, os, re, shutil, sys
from pathlib import Path
job, dry, board, project, models, label, note = sys.argv[1:]
job, dry = Path(job), dry == "1"
board, project = Path(board).resolve(), Path(project).resolve()
def die(msg): sys.exit(f"render-job-pin: REFUSED: {msg}")
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
if board.suffix != ".kicad_pcb" or not board.is_file(): die(f"{board} is not a .kicad_pcb file")
if project.suffix != ".kicad_pro" or not project.is_file(): die(f"{project} is not a .kicad_pro file")
if not re.fullmatch(r"(Iteration|Revision|Candidate|Milestone|Diagnostic) (0|[1-9][0-9]{0,5})", label):
    die("label must be gallery KIND NUMBER, e.g. 'Iteration 9'")
name = os.environ.get("PIN_NAME") or re.sub(r"[^a-z0-9-]", "-", label.lower())[:16]
if not re.fullmatch(r"[a-z0-9-]{1,16}", name): die("PIN_NAME must be 1-16 of [a-z0-9-]")
stage = os.environ.get("PIN_STAGE", "diagnostic")
if stage not in ("diagnostic", "placement"): die("PIN_STAGE must be diagnostic or placement")
current = json.loads((job / "pin.json").read_text())
data = board.read_bytes()
board_sha = hashlib.sha256(data).hexdigest()
refuse = current.get("refuse") or {}
if board_sha == current["board"]["sha256"]:
    die(f"board {board_sha} is identical to the current pin '{current['name']}'; nothing to advance "
        "(the scheduled job already labels it unchanged)")
if board_sha in refuse.get("board_sha256", []): die("board is on the refuse list: " + str(refuse.get("reason")))
text = data.decode("utf-8", errors="replace")
refs = re.findall(r'\(property\s+"Reference"\s+"([^"]+)"', text)
fps = re.findall(r'\(footprint\s+"([^"]+)"', text)
if not fps or len(refs) != len(fps): die(f"cannot count scope ({len(fps)} footprints, {len(refs)} references)")
holes = sum(1 for r, f in zip(refs, fps) if re.fullmatch(r"H\d+", r) or "MountingHole" in f)
if len(fps) in refuse.get("footprint_totals", []): die(f"board holds {len(fps)} footprints: {refuse.get('reason')}")
exp = dict(current.get("expected_scope") or {})
if "EXPECTED_NON_HOLE" in os.environ: exp["non_hole_footprints"] = int(os.environ["EXPECTED_NON_HOLE"])
if "EXPECTED_HOLES" in os.environ: exp["mounting_holes"] = int(os.environ["EXPECTED_HOLES"])
copper = sum(len(re.findall(r"\(" + k + r"[\s)]", text)) for k in ("segment", "arc", "via"))
matches = (len(fps) - holes, holes) == (exp.get("non_hole_footprints"), exp.get("mounting_holes"))
base = Path(models).resolve() if models else board.parent
local = {}
for m in re.findall(r'\(model\s+"([^"]+)"', text):
    if m.startswith("${KIPRJMOD}/"): rel = m[len("${KIPRJMOD}/"):]
    elif "$" in m or os.path.isabs(m) or re.match(r"[A-Za-z]:[\\/]", m): continue
    else: rel = m
    if ".." in Path(rel).parts: die(f"model path {m!r} leaves the project directory")
    src = base / rel
    if not src.is_file(): src = base / Path(rel).name
    if not src.is_file(): die(f"project-local model {m!r} not found under {base}")
    local[rel] = src
summary = (f"{board.name} sha256 {board_sha}: {len(fps)} footprints = {len(fps) - holes} non-hole + {holes} holes "
           f"(campaign scope {exp.get('non_hole_footprints')}+{exp.get('mounting_holes')}: "
           f"{'matches' if matches else 'SCOPE MISMATCH, will be labelled'}); "
           f"{'UNROUTED' if copper == 0 else f'{copper} copper items, completeness unverified'}; "
           f"{len(local)} project-local model(s); pin name {name}, label {label!r}, stage {stage}")
if dry:
    print("render-job-pin: DRY RUN, would pin: " + summary); sys.exit(0)
dest = job / "pinned" / board_sha
files = {board.name: board, board.with_suffix(".kicad_pro").name: project,
         **{rel: src for rel, src in local.items()}}
if dest.exists():
    for rel, src in files.items():
        if not (dest / rel).is_file() or sha(dest / rel) != sha(src): die(f"{dest} exists with different contents")
else:
    tmp = dest.with_name(dest.name + ".partial")
    shutil.rmtree(tmp, ignore_errors=True)
    for rel, src in files.items():
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, tmp / rel)
        if sha(tmp / rel) != sha(src): die(f"copy of {src} changed while copying; not a consistent snapshot")
    for path in sorted(tmp.rglob("*"), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)
    tmp.chmod(0o555)
    os.rename(tmp, dest)
rel_board = f"pinned/{board_sha}/{board.name}"
pin = {**current, "name": name, "label": label, "stage": stage, "scope_note": note,
       "board": {"path": rel_board, "sha256": board_sha},
       "project": {"path": f"pinned/{board_sha}/{board.with_suffix('.kicad_pro').name}", "sha256": sha(project)},
       "project_models": {rel: sha(src) for rel, src in local.items()},
       "expected_scope": exp,
       "provenance": {"pinned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      "pinned_by": "render-job-pin.sh", "board_from": str(board), "project_from": str(project),
                      "models_from": str(base), "previous_pin": {"name": current["name"],
                                                                 "board_sha256": current["board"]["sha256"]}}}
tmp = job / "pin.json.next"
tmp.write_text(json.dumps(pin, indent=2) + "\n")
os.replace(tmp, job / "pin.json")
print("render-job-pin: pinned " + summary)
PY
