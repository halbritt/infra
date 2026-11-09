# Local agent-ee nightly suite on proximal

AGENTEE-619 requires a working installed schedule, truthful failure reporting,
and native execution on moved main. The recovery committee (actual Astra,
Fable and Argon subscription sessions) agreed to these existing systemd units
and the existing `native-admit` / `ae-ci-exec` runner. There is no supervisor,
receiver, process transfer, private outcome journal or additional scheduler.

The two units were originally prepared in the earlier AGENTEE-619 worktree.
This version selects the complete runtime inputs and fresh stock configuration,
uses the installed runner, and omits the old retained-run/byte hard stops.
The earlier worktree and its unrelated work remain untouched.

## Installed paths and configuration

| Canonical source | Installed path |
|---|---|
| `agent-ee-full-suite.service` | `~/.config/systemd/user/agent-ee-full-suite.service` |
| `agent-ee-full-suite.timer` | `~/.config/systemd/user/agent-ee-full-suite.timer` |
| `shared/agent-ee/ae-ci-exec` | `~/.local/bin/ae-ci-exec` |
| `shared/agent-ee/native-inputs.py` | `~/.local/bin/native-inputs.py` |
| `shared/agent-ee/native-input-policy.json` | `~/.local/bin/native-input-policy.json` |

Paths under `shared/` are relative to the infra repository root. The runtime
manifest and stock configuration are private local files under
`~/.local/share/agent-ee/native-inputs/runtime/`; they and the captures are not
committed. The selected manifest has 36 bindings. Its stock context contains
14 actual part observations in two disjoint populations, including both authored
R6 variants. Each selected run recaptures them with the existing producer:
10 seconds per request, 190 seconds per population, five seconds between
requests (including the population boundary), two MiB per response, no retry.
Historical captures and design identities remain unchanged.

The service selects both files through explicit controller arguments. It uses
weight 2 and two module workers, a fresh retained worktree for every attempt,
and retained scratch with automatic GC disabled. It does not select or hold
an installed tool version. Actual source, verifier, runner, image and input
identities are recorded for each run.

Stock preparation has a 440-second outer bound. The controller's 7200-second
suite deadline includes admission waiting (at most 600 seconds); its termination
grace is 60 seconds. The 150-minute service start limit leaves room for capture,
checkout, reporting and cleanup. `KillMode=control-group` and a 90-second stop
limit cover service termination. No automatic retry or evidence deletion is
configured. The timer follows 04:00 America/Los_Angeles, including DST, with
up to five minutes of delay; persistent catch-up can fire when it is enabled.

## Installation and operational proof

`install-record.json` distinguishes prepared configuration from observed live
installation. Install from landed infra, preserve the previous runtime files,
record both repository revisions and actual installed hashes, and verify the
units with `systemd-analyze --user verify`. Do not enable the timer while its
inputs or initialization are unresolved.

The initial recovery uses one ordinary temporary service drop-in selecting
`--initialize-baseline`, because no prior nightly state exists. An owned manifest
with one intentionally wrong source hash first verifies actual service failure
before capture/native work: the failed attempt remains indexed and no baseline
or active-native marker is created. Original inputs are never modified.

After correcting the selected manifest, a temporary override of this same timer
triggers the first full run immediately. Record its trigger and service invocation
from systemd and the journal. This is the one composed full gate on newly moved
main, following scoped verification and source-bound landing checks. It does not
claim a previously completed persisted baseline. Remove initialization whenever
state has been written, even if later reporting fails. Remove the timer override
and verify the effective normal calendar and next trigger.

An unchanged-main service invocation must create no new attempt, capture or
native run. Incomplete execution reports a service failure and GitHub error;
completed tests publish their actual problem count. Reporting failure resumes
from retained state without rerunning tests. Plane issues use a stable commit
identity and the selected owner assignee. Existing local Git/GitHub/Plane
credentials remain in their normal stores; no credentials belong in these units.

## Evidence and inspection

Runtime state is `~/.local/share/agent-ee-full-suite/`. Each `runs/<id>/` retains
attempt/execution records, stock captures, the selected manifest, native receipts,
the full suite log, comparisons and an output manifest. Failed attempts stay in
the retention index. Never remove an unresolved active marker merely to retry.
The recovery ledger and original 152 problem identities are at
`~/.local/share/agent-ee/recovery-agent1321/PROGRESS.md` and
`problem-dispositions.json`; the initial real Plane create/deduplication proof
is reused with its verified unchanged reporting behavior and CLI.

```sh
systemctl --user show agent-ee-full-suite.service -p Result -p ExecMainStatus -p InvocationID
systemctl --user list-timers agent-ee-full-suite.timer --no-pager
journalctl --user -u agent-ee-full-suite.service
systemctl --user disable --now agent-ee-full-suite.timer
```

The live installation, timer-triggered full result, deliberate failure,
unchanged-main skip and GitHub recency evidence are recorded only after they
actually occur. The telemetry-pod hold remains in force; no project upload,
fabrication order or change to unrelated agent services is part of this schedule.
