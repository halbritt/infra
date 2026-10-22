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
- **Unknown state.** A failed `docker ps` or unreadable `/proc/pressure` queues
  the request ("capacity unknown" or "pressure unknown"). It is never treated
  as idle.
- **Re-entry.** Nested `ae-ci-exec` and `native-admit run` skip admission only
  when `native-admit verify` finds an inherited descriptor on the live lease
  file. The environment alone is not trusted: `AE_CI_EXEC_ADMITTED=1` without
  that descriptor dies with exit 2.
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
| agent-ee-gate-c4 | 48 | 12 (`max_weight` 4; 12 with the reservation) | 4 | 1 | 50 / 20 |

c4 exception, approved by agent-521 on 2026-10-22: only the holder of the c4
reservation may exceed `max_weight` 4, up to `reserved_max_weight` 12. That is
for the sole authoritative integration gate (`JOBS=12`). Without the reservation,
weight 12 is refused like any other oversized request.

Change a host by editing `native-admission.json` and rerunning
`./install-native-admission.sh --tool-only HOST`. The config is read on every
decision.

## Operate

```sh
native-admit status                       # used/budget, leases, unleased containers, queue, reservation
native-admit status --json
tail ~/.local/state/native-admission/events.jsonl   # admitted / released / gave-up / reserved
native-admit sample --print               # one snapshot (load, PSI, memory, root free space, zombies + top parents,
                                          # leases, unleased jobs, queue, drain/reservation, and per agent-ee
                                          # container: PID 1, init, cpus, pids limit, lease); appends to samples.jsonl
eval "$(native-admit reserve --label 'benchmark X' --minutes 60)"   # exports NATIVE_ADMISSION_RESERVATION
native-admit unreserve
```

Emergency off for one host: set `"enforce": false` in its config. Commands then
run unadmitted, and the event `unenforced` is logged.

## Rollout and verification (2026-10-22)

Deployed to all five hosts at about 21:55Z. Current hashes, identical on every
host: `native-admit` `8838c8a5bd5c68fc…` and `ae-ci-exec` `2d653097fa422f19…`. Raw evidence:
`proximal:~/.local/share/infra/native-admission/evidence-20261022/` (README
inside).

- **Competing launches.** Local harness, budget 3: peak weight 3, at most one
  suite, admission in arrival order. peecee-wsl, 10 real `ae-ci-exec` launches:
  peak 7 of 8, suites serialized.
- **Cancellation.** TERM to `ae-ci-exec` kills the container and frees the
  lease; the queued work started in the same second.
- **Crash.** `kill -9` of the whole `ae-ci-exec` process group released the
  lease. The orphaned container still counted as unleased w4 suite usage, and the
  queued suite started only after it exited (22:12:01Z exit, 22:12:06Z admit).
- **Refusals and unknown capacity.** `--jobs 8`, and a suite without `--jobs`,
  are refused on a max_weight 4 host. A `docker ps` failure queues as
  "capacity unknown". `drain --suites-only` blocks suites and still admits tests.
- **Container bounds.** Old image under AppArmor: PID 1 `docker-init`,
  `cpu.max 300000 100000`, `pids.max 16384`, orphans reaped, bwrap and
  kicad-cli 10.0.7 work. In production, every container started after the deploy
  has an init (tini, or docker-init for old images), a lease label, `--cpus`
  and `--pids-limit`.
- **talos.**
  - Zombies: 35,587 at 21:44Z, 69 at 21:54Z, 4 at 22:15Z.
  - Load: 75 → 1.1.
  - CPU PSI: 77 → 0.
  - Drained for new suites (`--suites-only`) since about 22:09Z, per
    agent-521's interim policy. `native-admit undrain` on talos lifts it.
- **Root review fixes (22:2xZ).**
  - Unreadable PSI queues.
  - Oversized weight is allowed only to the reservation holder.
  - A forged `AE_CI_EXEC_ADMITTED=1` is refused with exit 2.
  - A sibling process that knows a live lease ID but did not inherit its
    descriptor fails `verify`.
  - In a real run on peecee-wsl, the Docker client (child of `ae-ci-exec`) holds
    the lease file as fd 5 (`fd-inheritance-peecee.txt`).
- **c4 storage.** The stall was ext4 online discard. c4 now runs without it:
  I/O PSI went from about 90 idle to under about 13 under load (see the gcp-gate
  CHANGELOG). `AE_CI_TMPFS` exists as an opt-in for nondurable `/tmp` scratch,
  but it is not adopted. The measured runs were CPU-quota-bound, so no storage
  benefit was shown.

## Monitors (owner instruction, 2026-10-22)

The per-host monitor agents that agent-449 launches use `native-admit sample
--print` as their cheap probe. A field they can't read is UNKNOWN:
`capacity_known: false`, `containers: null`, or a PSI of `null`.

**c4:** run its monitor from proximal (`ssh agent-ee-gate-c4
'~/.local/bin/native-admit sample --print'`), not as a resident agent on c4. A
probe lasts under 60 s, so the idle stop ignores it. A long-running `claude` or
`codex` process on c4 counts as busy and would keep the paid host up
indefinitely.
