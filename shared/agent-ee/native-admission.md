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
| [ae-ci-exec](ae-ci-exec) | `~/.local/bin/ae-ci-exec` | Re-executes itself under `native-admit run`, so every `ae-ci-exec` container run is admitted and bounded |
| [ci-run.sh](../../hosts/gcp-gate/config/image/ci-run.sh) | `~/agent-ee-gate/ci-run.sh` on agent-ee-gate-c4 and peecee-wsl | Release gate. Since 2026-10-22 it enters admission itself (class suite, weight `$JOBS`) and bounds all of its containers |
| [install-native-admission.sh](install-native-admission.sh) | — | Installs all three on proximal, peecee-wsl, archon, talos and agent-ee-gate-c4 |

## How admission works

- **Lease.** An admitted command holds an exclusive `flock` on
  `~/.local/state/native-admission/leases/<id>.json`. The descriptor is
  inherited by the command and its children. The lease ends when they have all
  exited, whether normally, by crash, by `kill -9` or by cancellation. Every
  decision runs under `mutex.lock` and first removes entries whose lock is free.
- **Weight.** Units are strict-suite module workers. `strict_suite --jobs N`
  weighs N. A suite without `--jobs` weighs the CPU count, which is its
  default. `ci-run.sh` weighs `$JOBS`. Anything else weighs 1. A weight above
  `max_weight` is refused (exit 1), and nothing is clamped. Going above
  `max_weight` requires holding a live **gate** reservation made with
  `reserve --allow-weight W`, and is capped by the host's `reserved_max_weight`.
  An ordinary reservation confers no extra weight.
- **Grant-time revalidation.** Every grant attempt runs under the mutex. It
  re-reads the host config and the current reservation and checks the request's
  weight against both. A queued request whose allowance has lapsed (reservation
  expired, revoked or replaced, or `max_weight` lowered) is refused at that
  point (exit 1, event `refused`) and never admitted.
  `ae-ci-exec` honours `AE_CI_WEIGHT`.
- **Usage** is the sum of live leases plus agent-ee containers that hold no
  live lease, weighted by their actual `--jobs`. Those are jobs started before admission, or
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
- **Re-entry.** Nested `ae-ci-exec`, `ci-run.sh` and `native-admit run` skip
  admission only when `native-admit verify` finds a descriptor on the live lease
  file that owns the flock. `/proc/self/fdinfo/<fd>` shows a `lock:` line only on
  the open file description holding the lock, so a separately reopened
  descriptor or a forged `NATIVE_ADMISSION_LEASE` does not pass. Re-entry markers
  without that descriptor die with exit 2 (`AE_CI_EXEC_ADMITTED=1`,
  `CI_RUN_ADMITTED=1`). This establishes execution ownership. It is not a
  security boundary against the same uid.
- **Waiting.** A waiting caller prints `native-admit: waiting: <reason>` every
  5 minutes. `--max-wait S` (`AE_CI_MAX_WAIT` in `ae-ci-exec`) exits 75 instead.
- **Container bounds** on every container that `ae-ci-exec` or `ci-run.sh`
  starts (`ci-run.sh` covers doctor, sandbox probe, owner probe and the strict
  suite):
  - `--cpus = weight × cpus_per_unit`;
  - `--pids-limit = pids_limit`;
  - label `native-admission.lease=<id>`;
  - `--init` when the image has no tini `ENTRYPOINT`. Images from agent-ee
    7e5bdc46 on (AGENTEE-459) do have one.
- **Entry-point coverage (2026-10-22).**

  | Entry point | Admission | Container bounds | Owner of remaining wiring |
  |---|---|---|---|
  | `ae-ci-exec` (all 5 hosts) | yes | yes | — |
  | `ci-run.sh` (agent-ee-gate-c4, peecee-wsl) | yes, self-admitting; a missing `native-admit` fails closed (exit 2) unless `CI_RUN_EPHEMERAL_VM=1` | yes | — |
  | `native-admit run -- CMD` (direct) | yes | only if CMD uses `ae-ci-exec` or passes the lease label/`$NATIVE_ADMISSION_CPUS`/`$NATIVE_ADMISSION_PIDS`/`--init` itself | caller |
  | raw `docker run` of an agent-ee image | no; counted as unleased usage | no | agent-449 (review lanes, e.g. `sleepy_galileo`) |
  | kicad-route lanes run natively (`kicad-route run`, pytest on the host) | no | n/a (no container) | agent-449 / agent-507 |
  | fome-mc gates on proximal (native KiCad, `make analyze`) | no | n/a | agent-449 / fome-mc lane |
  | `run-gate.sh` throwaway Spot VMs | no: `run-gate.sh` passes `CI_RUN_EPHEMERAL_VM=1` explicitly (one VM per gate, nothing else on it) | n/a | by design. Anywhere else, `ci-run.sh` without `native-admit` refuses (exit 2) before any work |
  | owner-directed Rust scorer (agent-524) | its own choice; not commandeered | — | owner |

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

c4 exception, approved by agent-521 on 2026-10-22: the sole authoritative
integration gate may run `JOBS=12`. Mechanically, only the holder of a c4 gate
reservation (`native-admit reserve --label ... --minutes N --allow-weight 12`,
token exported as `NATIVE_ADMISSION_RESERVATION`) may exceed `max_weight` 4, up
to `reserved_max_weight` 12. Ordinary reservations and unreserved callers are
refused above 4.

Change a host by editing `native-admission.json` and rerunning
`./install-native-admission.sh --tool-only HOST`. The config is re-read on every
grant attempt.

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

Deployed to all five hosts at about 21:55Z. Current hashes (23:1xZ): `native-admit`
`2228099e0649b094…` and `ae-ci-exec` `2d653097fa422f19…`, identical on all five
hosts; `ci-run.sh` `2c4d75fd49b2b215…` on agent-ee-gate-c4 and peecee-wsl. Raw evidence:
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
  kicad-cli 10.0.7 work. In production, every `ae-ci-exec` container started
  after the deploy had an init (tini, or docker-init for old images), a lease
  label, `--cpus` and `--pids-limit` (pid1-inventory). Raw `docker run`
  containers (for example `sleepy_galileo`, 22:30Z) and the c4 gate started
  before the `ci-run.sh` change did not; see the coverage table.
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
- **Second correction round (agent-522 audit 8a741306, 23:1xZ).** Retained
  evidence:
  - `ownership-fdinfo/`: an inherited child verifies; nested reuse makes no
    second lease; a reopened descriptor of the live lease file and a forged env
    are both refused.
  - `config-and-allowance/`: an ordinary reservation is refused at weight 12;
    a `--allow-weight 12` gate reservation is admitted at 12; weight 13 is
    refused; a queued w3 is refused at grant after `max_weight` is lowered to 2.
  - `regression-reservation-expiry/output-v2.txt`: an expiry while queued is
    still refused under a gate reservation; the valid control is admitted.
  - `ci-run-admission/`:
    - draining host: waits, then exit 75;
    - idle host: admitted as suite w4 before any work;
    - nested: no second charge;
    - forged `CI_RUN_ADMITTED`: exit 2;
    - `JOBS=8` unreserved: refused.
  - The real container bindings of the first post-change c4 gate are captured
    by `~/.local/state/native-admission/handoff/first-ci-run-watch.sh` on c4.
- **Third correction round (agent-522 response 3b9b7f03, 23:3xZ).**
  - `ownership-fdinfo/` v2: the negative now provably passes a reopened
    descriptor. The child holds fd 3 on the same live lease file (same inode),
    with no `lock:` line in its fdinfo, and `verify` refuses it. Meanwhile the
    admitted parent's fd 5 still owns the FLOCK. v1 is kept
    (`run-v1.sh`, `output-v1.txt`); its case 3 never passed the descriptor.
  - `ci-run-admission/output-v2.txt`, with `ci-run.sh` `2c4d75fd49b2b215…`:
    - helper missing on a shared host: exit 2 before any log, context or
      container;
    - helper missing with `CI_RUN_EPHEMERAL_VM=1`: runs unadmitted, as
      announced;
    - helper present: admitted (suite w4);
    - helper present with the flag set: still admitted.

    `output-v2-regression.txt` repeats the earlier drain, idle, nested, forged
    and `JOBS=8` cases on the new script.
