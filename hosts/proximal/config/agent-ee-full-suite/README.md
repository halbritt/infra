# agent-ee local full suite

AGENTEE-619 prepares a nightly local suite at approximately 04:00 Pacific.
GitHub runs only the recency check. The remediation lead owns installation,
activation and the first operational proof after independent review and landing.
These files are prepared configuration; they are not an installation receipt.
The initial observation on 2026-11-06 found neither unit installed.

The service invokes the reviewed `~/git/agent-ee/scripts/nightly_full_suite.py`
from the main checkout. That runner fetches `origin/main`, selects its exact
commit and runs an isolated worktree through `ae-ci-exec`. An unchanged completed
commit does not run again. Pending Plane or GitHub reporting resumes from its
retained comparison without another native suite. Missing/incomplete suite
verdicts, failed fetches and dirty worktrees return failure.

Normal execution refuses missing state. The lead must explicitly select a
reviewed `run --initialize-baseline` operation; only its complete candidate-bound
verdict records the baseline. Existing/corrupt state cannot be silently replaced.
This records the inventory without
filing inherited problems as new regressions. Its GitHub status still fails if
that baseline contains problems. Later runs compare against that retained
inventory, including changes from missing/skip problems to errors/failures.
No baseline is fabricated from an absent state, and there is no automatic
conversion of an unversioned old state.

The completion monitor accepts an authoritative completed result for the exact
main SHA regardless of age. It preserves the actual finish time and the suite's
failure state. There is no unchanged-main rerun or fake timestamp refresh.
Pending/error, absent, malformed and unmarked evidence does not establish
completion; `--max-hours` is a compatibility argument only.

The prepared unit explicitly selects the owned runtime manifest at
`~/.local/share/agent-ee/native-inputs/runtime/nightly-manifest.json` and landed runner
`~/git/infra/shared/agent-ee/ae-ci-exec`. The controller hashes the runner and its
companions for each attempt. Its private outcome journal sits beside a fresh
`native/` evidence directory, outside writable source/output mounts. Runtime
review approved the store in source; the separate scoped nightly manifest remains runtime-owned and pending.
Its exact reviewed hash must be recorded before activation. The focused
manifest and its 4420b18c hash remain frozen.

Native admission remains in `ae-ci-exec`/`native-admit`: weight 2, two module
workers, at most ten minutes waiting for capacity. The runner bounds its child
at two hours; systemd allows 125 minutes overall. Native scratch is retained
with `AE_CI_KEEP_TMP=1`. The timer follows `America/Los_Angeles`, including DST,
with up to five minutes of delay. `Persistent=true` can trigger an immediate
catch-up when the lead first enables it.

## Install and activate after review

Run from this directory in the landed infra checkout, after the reviewed
agent-ee runner has landed. Commands affect only these two user units.

```sh
install -Dm0644 agent-ee-full-suite.service "$HOME/.config/systemd/user/agent-ee-full-suite.service"
install -Dm0644 agent-ee-full-suite.timer "$HOME/.config/systemd/user/agent-ee-full-suite.timer"
systemctl --user daemon-reload
systemd-analyze --user verify "$HOME/.config/systemd/user/agent-ee-full-suite.service" "$HOME/.config/systemd/user/agent-ee-full-suite.timer"
systemctl --user enable --now agent-ee-full-suite.timer
systemctl --user list-timers agent-ee-full-suite.timer --no-pager
```

Credentials for `git`, `gh` and `plane` remain in their existing local stores.
Do not put credentials in a unit, environment file or Git. The user service
needs their normal noninteractive authentication. `gh`/`plane` errors are
observable as a failed service and unfinished reporting state.

After installation, update `install-record.json` with the real installation
time, both source commits, hashes of the installed units and a durable evidence
path. Record the first service run on a moved `origin/main`, plus a second call
that skips native execution on the unchanged commit. Do not set its status to
installed before those facts are observed. A focused test double is not this
operational proof. The lead coordinates any manual native run with host capacity.
The lead chooses baseline initialization and the authoritative full gate together
so unchanged candidate evidence is not regenerated merely to initialize state.

## Inspect and stop

```sh
systemctl --user show agent-ee-full-suite.service --property=Result,ExecMainStatus
journalctl --user -u agent-ee-full-suite.service
systemctl --user disable --now agent-ee-full-suite.timer
```

Durable state and logs live at `~/.local/share/agent-ee-full-suite/`:
`state.json`, `latest-compare.json`, `latest-failures.json` and `runs/*/`.
Each completed run retains its execution receipt, suite log and comparison.
An interrupted run can have an initial receipt without completion fields;
it is not a completed suite and cannot advance the recorded commit.
An unresolved `active-run.json` stops later native attempts, including `--force`.
Inspect its receipt, native reservation and retained inputs before reconciling
that marker; never remove it simply to make the next schedule run.
Keep this directory, retained native scratch and replay inputs until the lead
has reconciled and retained the evidence. No automatic retention cleanup is
configured here. The prepared service creates a fresh retained worktree per
attempt and refuses ignored files when reusing a configured worktree. It indexes
kept scratch and run outputs, then refuses new native work at 7 retained runs or
20 GiB. One run may cross the byte threshold; the next is held. Unchanged-main
skips and reporting retries still work. The lead selected these admission thresholds on 2026-11-06. Before explicitly releasing a run, retain/export its replay material,
worktree and scratch. The controller deletes no selected evidence.

Only a complete private `not_started` journal bound to the exact attempt,
command, runtime, exit and timestamps clears a failed no-start marker. Its bytes
and supervisor ID are sealed before clearance. Missing, stale, malformed,
interrupted or started/uncertain evidence stays held; an exit code is insufficient.

The agent-ee `qualify` entrypoint can capture the single composed full gate before
landing. After that exact candidate lands, `import-baseline` validates the
lead-selected hashed evidence without native work, preserving original finish
time and publishing no status. See agent-ee `docs/nightly-full-suite.md`. No
baseline is selected or initialized by preparing these files.

The service executes from agent-ee's main checkout. Stop the timer before
changing that installed runner during an unresolved run. No pod attempt,
fabrication order or project upload is part of this schedule.

History accounting validates retention-index.json against every retained run and
its immutable attempt identity/execution receipt. All states count, with duplicate
lineage references grouped by attempt UUID. Byte totals count regular-file sizes
once per device/inode across run outputs, retained worktrees and indexed scratch;
links are not followed. Missing/corrupt index or selected paths hold admission.
retention-check.json records reason/count/bytes (unknown on accounting failure)
and the lead reconciliation path; the service fails without advancing baseline
or last-tested SHA. Existing history needs explicit reconciliation, not an empty
index or automatic migration. No other agent runtime history is counted.
