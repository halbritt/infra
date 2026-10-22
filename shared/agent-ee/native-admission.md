# Native admission (`native-admit`)

Host-wide admission control for native agent-ee work (KiCad, Bubblewrap,
strict-suite modules). Requested 2026-10-22 by agent-521 on the owner's
instruction to fix the agent-522 efficiency findings
(`~/.local/share/agent-ee/reviews/2026-10-22-efficiency-agent522/findings.md`):
per-agent worker limits did not bound a host. Talos ran five strict suites (13
module workers plus native children) on 12 threads, with load 45 to 75, CPU
PSI 53 to 77, and tens of thousands of zombies.

| File | Installed at (every agent-ee host) | Role |
|---|---|---|
| [native-admit](native-admit) | `~/.local/bin/native-admit` | Lease manager: `run`, `status`, `sample`, `reserve`, `unreserve` |
| [native-admission.json](native-admission.json) | `~/.config/native-admission/config.json` (that host's entry) | Per-host budget and limits |
| [ae-ci-exec](ae-ci-exec) | `~/.local/bin/ae-ci-exec` | Re-executes itself under `native-admit run`, so every agent-ee container run is admitted |
| [install-native-admission.sh](install-native-admission.sh) | — | Installs all three on proximal, peecee-wsl, archon, talos and agent-ee-gate-c4 |

## How admission works

- **Lease.** An admitted command holds an exclusive `flock` on
  `~/.local/state/native-admission/leases/<id>.json`. The descriptor is
  inherited by the command and its children. The lease ends when they have all
  exited, whether normally, by crash, by `kill -9` or by cancellation. Every
  decision runs under `mutex.lock` and first removes entries whose lock is free.
- **Weight.** Units are strict-suite module workers. `strict_suite --jobs N`
  weighs `min(N, max_weight)`. A suite without `--jobs` weighs `max_weight`,
  because its default is the CPU count. Anything else weighs 1.
  `ae-ci-exec` honours `AE_CI_WEIGHT`.
- **Usage** is the sum of live leases plus agent-ee containers that hold no
  live lease, weighted the same way. Those are jobs started before admission, or
  containers whose client was killed. So a pre-existing backlog counts.
- **Admission** follows strict FIFO order. The queue head starts when all of
  these hold:
  - `used + weight <= budget`, or nothing is running;
  - suites stay below `max_suites`;
  - CPU and I/O PSI (some avg10) are under their limits whenever work is
    running;
  - no reservation is active, or the caller holds it
    (`NATIVE_ADMISSION_RESERVATION`).
- **Waiting.** A waiting caller prints `native-admit: waiting: <reason>` every
  5 minutes. `--max-wait S` (`AE_CI_MAX_WAIT` in `ae-ci-exec`) exits 75 instead.
- **Container bounds** (`ae-ci-exec`) on every admitted container:
  - `--cpus = weight × cpus_per_unit`;
  - `--pids-limit = pids_limit`;
  - label `native-admission.lease=<id>`;
  - `--init` when the image has no tini `ENTRYPOINT`. Images from agent-ee
    7e5bdc46 on (AGENTEE-459) do have one.
- **Not covered:**
  - native work that bypasses `ae-ci-exec`, such as kicad-route lanes run
    directly or fome-mc gates on proximal (wrap with `native-admit run --label X
    -- CMD`);
  - the release-gate `ci-run.sh`. Its `agent-ee:ci-*` containers are still
    counted as unleased usage.

  Model sessions are not leases. State is per user (`halbritt`), which runs all
  of this work.

## Per-host limits (2026-10-22, interim policy from agent-521)

Interim policy: at most one suite per host and at most 4 module workers per
suite.

| Host | Threads | budget | cpus_per_unit | max_suites | PSI cpu / io max |
|---|---:|---:|---:|---:|---|
| proximal | 12 | 4 | 3 | 1 | 50 / 30 |
| talos | 12 | 4 | 3 | 1 | 50 / 30 |
| archon | 16 | 4 | 4 | 1 | 50 / 30 |
| peecee-wsl | 24 | 8 | 3 | 1 | 50 / 30 |
| agent-ee-gate-c4 | 48 | 8 | 6 | 1 | 50 / 20 |

Change a host by editing `native-admission.json` and rerunning
`./install-native-admission.sh --tool-only HOST`. The config is read on every
decision.

## Operate

```sh
native-admit status                       # used/budget, leases, unleased containers, queue, reservation
native-admit status --json
tail ~/.local/state/native-admission/events.jsonl   # admitted / released / gave-up / reserved
native-admit sample --print               # one snapshot; appends to samples.jsonl
eval "$(native-admit reserve --label 'benchmark X' --minutes 60)"   # exports NATIVE_ADMISSION_RESERVATION
native-admit unreserve
```

Emergency off for one host: set `"enforce": false` in its config. Commands then
run unadmitted, and the event `unenforced` is logged.
