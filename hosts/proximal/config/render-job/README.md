# render-job: scheduled telemetry-pod renders for the private agent-ee gallery

**Owner:** agent-449 (dispatcher), per agent-521's campaign process.
**Instruction implemented:** the owner asked for an initial render refresh now, then about
every four hours, through a persistent, serialized, bounded job on the latest consistent
snapshot. The job renders top, bottom and isometric views, attaches status and identity,
and labels unchanged boards. The owner instruction was relayed through agent-521's campaign
process (`docs/campaign-process.md`, "Production runtime and renders", 2026-10-22). Installed
2026-10-22. It was corrected the same day after agent-521's HOLD (Cairn 14664d84); see
"Correction" below.

## Source: an explicit, immutable pin

The job renders only the candidate named by `~/.local/share/agent-ee-render-job/pin.json`
(copy: [`pin.json`](pin.json)). The pinned files live in `pinned/<board sha256>/`: the board,
its sibling `.kicad_pro` and the project-local models under `inputs/models/`. They are read-only.
On every run, and again after rendering, the job hashes each file. If any hash differs from the
pin, the run refuses. It also refuses a board on the pin's refuse list (the 112-footprint v9
pilot, by sha256 and by footprint count). The job never selects a board from a repository HEAD
or a live worktree.

Current pin, `iter8t`:
- Board: `pinned/56313982…/candidate.kicad_pcb`, sha256
  `56313982e6871d8054359d61ae5f74202a19b707d051efb56bc20233d5c6dd72`.
- Project: sha256 `a91ee4d1…`.
- Project models: J1 `c-1-776163-1-t-3d.stp` (`43ba1f80…`) and U3
  `NEO-M9N-00B_visualization-only_datasheet-derived…step` (`8a7f1984…`).
- Gallery label `Iteration 8`, stage `diagnostic`.
- Scope: 309 footprints, which are 305 non-hole footprints and 4 mounting holes. This matches
  the expected 305 + 4.
- Routing: UNROUTED (no tracks, arcs or vias). Qualification: not qualified.

**Updating the pin (agent-449):** do this only when a newer qualified snapshot exists, for
example the integrated j6 candidate.
1. Copy the board, its `.kicad_pro` and its project models into a new
   `pinned/<sha256>/` directory and make it read-only.
2. Write the new path, the hashes, the label and the scope note to `pin.json`. Set
   `expected_scope` to the expected non-hole footprint and hole counts.

The next run publishes the new board. A gallery label must be `KIND NUMBER`, so the pin name
is carried in the receipt name.

## What each run does

1. Takes `job.lock` with `flock` without waiting. If the lock is held, the run logs `skipped`
   to `history.jsonl` and exits 0.
2. Verifies the pin (see above).
3. Checks the scope. It counts the footprints and the mounting holes (reference `H<n>` or a
   `MountingHole` footprint) and compares them with `expected_scope`. A mismatch is not hidden:
   the receipt name says `SCOPE-MISMATCH-<n>fp+<m>holes`, and the job never claims the expected
   count. A refused footprint total (112) refuses the run.
4. Counts copper. No tracks, arcs or vias gives `unrouted`, which the gallery checks against
   the board. Otherwise the board has copper and its completeness is not verified. The job
   claims no routing acceptance.
5. Computes an identity: the board, project and project-model hashes, the resolved stock-model
   digest (`KICAD10_3DMODEL_DIR=/usr/share/kicad/3dmodels`, `KIPRJMOD` = the pinned directory),
   the KiCad version, the render settings, the gallery app file hashes and the label and stage.
   It compares this identity with the job's last publication in `state.json`.
6. **Changed:** renders with `agent_ee.render3d.render_board` (2400x1600, high quality, 3 views,
   900 s timeout per view). It then publishes with
   `python3 -m agent_ee.render_gallery --root … publish --label <pin label> --stage <pin stage>`,
   using the deployed gallery app (`~/.local/share/agent-ee-render-gallery/app`). The new
   bundle becomes Latest.
   **Unchanged:** it does not render or publish a new bundle. It attaches a new status record
   to the existing bundle, with a `board-unchanged` receipt.
7. Attaches a hash-bound status record (`render_gallery status`). Routing is `unrouted` (from
   the board) or `routed` ("has tracks or vias, completeness not verified"). Qualification is
   `unqualified`. The evidence is the board, a receipt and a job-generated association. The
   association is mechanical; no reviewer produced it. The receipt name carries the facts that
   the gallery's fixed vocabulary cannot:
   `rj_<pin>_<305fp+4holes|SCOPE-MISMATCH-…>_<unrouted|copper-present>_not-qualified_<change>_<UTC>.json`.
   The change part is `new-board`, `board-unchanged`, `board-unchanged-inputs-changed` or
   `same-board-as-gallery-<bundle id>`. The receipt holds the full pin, the scope counts, the
   hashes and the previous publication.
8. Deletes run directories older than 7 days. It keeps every run in that window, including
   failures.

The job runs no tests, no regression suite and no DRC. It does not restart or reconfigure the
gallery server (`agent-ee-render-gallery.service`, `100.85.100.81:18510`).

## Correction (2026-10-22)

The first version took `telemetry-pod/telemetry-pod.kicad_pcb` from fome-mc `origin/main`
(through `git archive`). Its first run (`20261022T191106Z`) therefore rendered the **old
112-footprint v9 pilot** (sha256 `2938ee1e…`) as bundle `2938ee1ee2ca-2d84c7eebd46`
("Revision 1"). agent-521 issued a HOLD (Cairn 14664d84) and stopped the timer. The fixes:

- The job now renders only the immutable pin, with scope checks and the pilot on the refuse
  list.
- The wrong bundle is kept, not deleted. Status record `2d84c7eebd46-044a6cc4d22a` marks it
  with the receipt
  `HISTORICAL_INCORRECT-SELECTION_old-112-footprint-pilot-rendered-by-mistake_retained-as-evidence.json`
  (not adopted, not qualified). The evidence is in
  [`corrections/2938ee1ee2ca-2d84c7eebd46/`](corrections/2938ee1ee2ca-2d84c7eebd46/) and in
  `~/.local/share/agent-ee-render-job/corrections/`, which is not pruned.
- A fresh Iter8t render was published as bundle `56313982e687-1f6b371a7792` (`Iteration 8`,
  diagnostic, unrouted, not qualified, 305fp+4holes). It is the same board as the earlier
  gallery bundle `56313982e687-0e28e3b235a2` and is now Latest.
- The pre-correction `state.json` was moved aside, so the pilot is never used as the
  "previous" board.

## Files

| here | installed at |
|---|---|
| `render-job.py` | `~/.local/share/agent-ee-render-job/render-job.py` |
| `pin.json` | `~/.local/share/agent-ee-render-job/pin.json` (pinned bytes in `pinned/<sha>/`, not in git) |
| `agent-ee-render-job.service` | `~/.config/systemd/user/agent-ee-render-job.service` |
| `agent-ee-render-job.timer` | `~/.config/systemd/user/agent-ee-render-job.timer` |

Runtime state is in `~/.local/share/agent-ee-render-job/`:
- `runs/<UTC>/`: `job.log`, `renders/`, `evidence/` and `result.json`. A failed run also has a
  `FAILED` file.
- `latest-status.json`: the last run. Failure is `"ok": false` with a `reason`.
- `history.jsonl`: one line for each run or skip.
- `state.json`: the last publication by this job.

## Schedule and bounds

- Timer: `OnCalendar=*-*-* 00/4:17:00` (local time), `Persistent=true`, 2 min randomized delay.
  When the timer is re-enabled after a missed slot, it runs once at once.
- Service: `Type=oneshot`, `Nice=10`, `IOSchedulingClass=idle`. The job runs under
  `timeout --kill-after=60s 20m`, with `TimeoutStartSec=23min`. On SIGTERM it stops the KiCad
  children and records the failure. `ExecStopPost=… post-check` marks a run that was killed
  before it wrote its result as failed.
- Notification: agent-449 reads `latest-status.json` or `history.jsonl`. A failure is `ok:false`
  with a reason, a `FAILED` marker and a `FAILED:` log line. A refused pin shows as
  `Refused: PIN MISMATCH …`.

## Operate, stop or hand off

```sh
systemctl --user list-timers agent-ee-render-job.timer
systemctl --user start agent-ee-render-job.service        # manual run (blocks until done)
cat ~/.local/share/agent-ee-render-job/latest-status.json
journalctl --user -u agent-ee-render-job.service
systemctl --user disable --now agent-ee-render-job.timer  # stop the schedule when the programme ends
```

Stop the schedule when the programme ends, or hand it off: give the new owner this README
and update the owner line above. Published bundles are immutable and remain in the gallery.
After you edit the files here, copy them to the installed paths and run
`systemctl --user daemon-reload`.
