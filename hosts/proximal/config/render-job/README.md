# render-job: scheduled telemetry-pod renders for the private agent-ee gallery

**Owner:** agent-449 (dispatcher), per agent-521's campaign process.
**Instruction implemented:** the owner asked for an initial render refresh now, then about
every four hours, through a persistent, serialized, bounded job on the latest consistent
snapshot. The job renders top, bottom and isometric views, attaches status and identity,
and labels unchanged boards. The owner instruction was relayed through agent-521's campaign
process (`docs/campaign-process.md`, "Production runtime and renders", 2026-10-22). Installed
2026-10-22.

## What it does

1. Takes the lock `~/.local/share/agent-ee-render-job/job.lock` with `flock`, without waiting.
   If another run holds the lock, this run logs `skipped` to `history.jsonl` and exits 0.
2. Runs `git fetch origin main` in `~/git/fome-mc`. It resolves `origin/main` to a commit and
   `git archive`s only the committed pod files (`telemetry-pod/telemetry-pod.kicad_pcb`,
   `.kicad_pro`, `.kicad_dru`, the lib tables, `kicad-libraries/`, `captured-footprints/` and
   `README.md`) into the run directory. It never reads a working tree or a worker worktree.
   This snapshot is the **committed fome-mc main board**. It can be older than the newest
   agent-ee placement iteration that other agents publish to the gallery.
3. Hashes the board, the project and the resolved 3D models (`inspect_models` with
   `KICAD10_3DMODEL_DIR=/usr/share/kicad/3dmodels`). It compares these hashes, the KiCad
   version, the render settings and the gallery app file hashes with the job's last
   publication in `state.json`.
4. **Changed:** renders with `agent_ee.render3d.render_board` (2400x1600, high quality, 3
   views, 900 s timeout per view). It then publishes with
   `python3 -m agent_ee.render_gallery --root … publish --label "Revision N" --stage diagnostic`,
   using the deployed gallery app (`~/.local/share/agent-ee-render-gallery/app`).
   **Unchanged:** it does not render or publish a new bundle. It attaches a new status record
   to the existing bundle, whose receipt name contains `board-unchanged`.
5. Attaches a hash-bound status record (`render_gallery status`) that contains:
   - routing: `unrouted` if the board has no tracks, arcs or vias (the gallery checks this).
     Otherwise it is `routed`, which the gallery shows as "has tracks or vias (completeness
     not verified)". The job claims no routing acceptance.
   - qualification: `unqualified` ("Not qualified"). The job does no qualification.
   - evidence: the board, a job receipt
     `render-job_fome-mc-main-<commit12>_<board-changed|board-unchanged|board-unchanged-inputs-changed>_not-qualified_<UTC>.json`
     (fome-mc commit, board/project/model hashes, copper counts, change state, previous
     publication), the fome-mc pod `README.md` (only when it names this board's SHA-256) and a
     job-generated association that binds them to the board hash. The association is mechanical.
     No reviewer produced it.
6. Deletes run directories older than 7 days. It keeps every run in that window, including
   failures.

The gallery label must be `KIND NUMBER` and the stage must be a fixed code, so the
"committed fome-mc main" and "unchanged" facts are carried in the evidence names and the
receipt. `Revision N` counts the bundles that this job publishes.

The job runs no tests, no regression suite and no DRC. It does not restart or reconfigure
the gallery server (`agent-ee-render-gallery.service`, `100.85.100.81:18510`).

## Files

| here | installed at |
|---|---|
| `render-job.py` | `~/.local/share/agent-ee-render-job/render-job.py` |
| `agent-ee-render-job.service` | `~/.config/systemd/user/agent-ee-render-job.service` |
| `agent-ee-render-job.timer` | `~/.config/systemd/user/agent-ee-render-job.timer` |

Runtime state is in `~/.local/share/agent-ee-render-job/`:
- `runs/<UTC>/`: `job.log`, `snapshot/`, `renders/`, `evidence/` and `result.json`. A failed
  run also has a `FAILED` file.
- `latest-status.json`: the last run. Failure is `"ok": false` with a `reason`.
- `history.jsonl`: one line for each run or skip.
- `state.json`: the last publication by this job.

## Schedule and bounds

- Timer: `OnCalendar=*-*-* 00/4:17:00` (local time), `Persistent=true`, 2 min randomized delay.
- Service: `Type=oneshot`, `Nice=10`, `IOSchedulingClass=idle`. The job runs under
  `timeout --kill-after=60s 20m`, with `TimeoutStartSec=23min`. On SIGTERM it stops the
  KiCad children and records the failure. `ExecStopPost=… post-check` marks a run that was
  killed before it wrote its result as failed.
- Notification: agent-449 reads `latest-status.json` or `history.jsonl`. A failure is
  `ok:false` with a reason, a `FAILED` marker and a `FAILED:` log line.

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
