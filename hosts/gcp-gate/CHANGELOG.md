# Host changelog

## 2026-10-23 — owner: "stop everything" (campaign paused)

Relayed by agent-521 at about 04:47Z. Actions:
- At 04:49Z agent-524's Spot VM `agent-ee-rust524-greenfield-20261023-0310`
  was **stopped**, not deleted. Its 100 GB boot disk is kept. Its ledger
  reservation `84825dbe28` stays open until agent-524 retrieves evidence and
  tears the VM down.
- `agent-ee-gate-c4` was already TERMINATED; its disk is kept.
- No other campaign instances exist.
- The passive gcp-spend guard and the c4 idle-stop timers keep running.
- Native admission was drained ("all work") on proximal, talos, peecee-wsl and
  archon with that reason. No leases were active.
- To resume, `native-admit undrain` on each host, but only on a new owner
  instruction.

## 2026-10-23 — billed spend from the Budget API (owner via agent-519)

- Enabled `billingbudgets.googleapis.com` and created budget `3c5ecec4…`:
  $100 from 2026-10-21; heath-stuff, Compute Engine and Networking only;
  credits excluded; thresholds at 25, 50, 75, 90 and 100%.
- Created Pub/Sub topic `campaign-budget` and subscription
  `campaign-budget-pull`. A budget's API record holds no spend figure, so the
  notifications are the only way to read billed cost.
- `gcp-spend` now enforces the larger of billed and estimate, in status,
  reserve and guard. First comparison: billed $8.51 against an estimate of
  $25.22.
- The cap, ledger and guard are unchanged. There is no BigQuery export.

## 2026-10-23 — right-sized ephemeral gates (owner direction via agent-519)

- Measured d04b5121 on Spot c2d-highcpu-16 / JOBS=16 (1150 s, $0.103) and
  c2d-highcpu-32 / JOBS=32 (703 s, $0.131). Both passed, and teardown was
  verified for both. The knee is c2d-highcpu-32.
- `run-gate.sh` now defaults to c2d-highcpu-32 with JOBS=32.
- `gate-size` added (384b05d): it predicts suite time and cost for a shape or
  module subset from a measured log.
- gcp-spend now prices every c2d and c4 highcpu shape (adba58b). Before that,
  c2d-highcpu-32 was refused for lack of a price. New gates are charged at
  the shape recorded in their ledger reservation. Unledgered 2026-10-22 gates
  keep their actual c2d-highcpu-16 shape.
- The c4 retirement plan is recorded in the README. The c4 instance and disk
  are unchanged.

## 2026-10-23 — K91 stores: owner-write briefly restored, then reverted

The canonical gate of 76f221ac on peecee-wsl failed in
`test_routing_experiment_boundary`. On agent-449's request, the stores'
owner-write bit was restored at 02:08:55Z.

agent-521 then ruled (fd37d2b0) that the mounted originals stay read-only, and
that the fix belongs in the test's fixture copies. The request was withdrawn,
and modes were set back to `a+rX,a-w` at 02:09:58Z.

All three tree digests were verified at each step and are unchanged. The
staging script and docs were reverted (cc9a35b). No gate mounted the stores in
that window.

## 2026-10-23 — `ci-run.sh` stages K91 native receipt inputs

Request from agent-449. agent-ee's `tests/test_routing_experiment_boundary.py`
(from AGENTEE-442) needs agent-507's external kicad-route a0ed434 receipts,
which hold route_demo geometry and are not committed. They gave 22 "SKIP
refused in strict mode" in the 484ce18e gate on peecee-wsl.

- `k91-inputs.json` pins three directories, `final`, `protected-existing` and
  `protected-human`. For each it records the test's per-file sha256 (agent-ee
  484ce18e `K91_FINAL_PINNED` / `K91_PROTECTED`) and a content tree digest.
- `stage-k91-inputs.sh HOST` verifies both on proximal, then copies to
  `~/agent-ee-gate/ci-inputs/k91/<name>-<tree>`, re-verifies, and makes it
  read-only.
- `ci-run.sh`, for commits whose tests reference `AGENT_EE_K91_*`, verifies
  all three stores before building, refusing (exit 2) when one is missing or
  altered. It then mounts each read-only at `/opt/k91/<name>` with
  `AGENT_EE_K91_FINAL_RECEIPT` / `_PROTECTED_EXISTING` / `_PROTECTED_HUMAN`.
  There is no test change and no skip allowance.

Done on peecee-wsl, with `ci-run.sh` `99b77facef615f6e…` (backup
`ci-run.sh.bak-20261023-k91`). c4 is stopped: stage it and deploy the script
there when it next runs, or its K91 gates refuse. The image pin was updated.

Tests (`evidence-20261022/k91-gate-inputs/`):

- the committed block in isolation: present gives verified mounts; missing and
  altered give exit 2; a commit without K91 tests skips the block;
- on peecee-wsl, in `agent-ee:ci-484ce18e…` as uid 10001: all three stores
  readable and read-only, with each `attempt.json` hash equal to the test pin.

## 2026-10-23 — `agent-ee-fourway524-20261023-0020` torn down (verified)

agent-524's VM for the owner-directed four-way scorer benchmark (c2d-highcpu-4
Spot, 2 h max) was created at about 00:13Z without a ledger reservation and
charged from inventory. agent-475's poll found it gone. Exact-name instance
and disk listings both succeeded and were empty.

## 2026-10-23 — c4 stopped after its final gate; estimator undercount fixed

- agent-521 reported c4's gate d04b5121 terminal (exit 0, 5547 tests, 0
  skips). c4 had then been idle for 12 min with no processes, containers or
  admissions. The ee449d worker had completed.
- The gate logs (`~/agent-ee-gate/ci-logs/`) and ee449d results
  (`build/ee449d`) were preserved to
  `proximal:~/agent-ee-gate-c4-preserved/20261023T004340Z-final/` (163 files,
  211 MB, sha256 verified). Then `gcloud compute instances stop` ran: c4 is
  TERMINATED, and its 200 GB disk remains (about $63/month).
- Found by that stop: `gcp-spend` dropped an open run when the VM was no
  longer RUNNING but its stop event had not reached the audit log yet. The
  estimate fell from $24 to $13.84, an undercount. Now an open run is charged
  to now until a closing event appears (regression R4). Estimate after the
  fix: $24.72 accrued, $65.28 remaining.

## 2026-10-23 — `run-gate.sh` and `build-image.sh`: release only after proven teardown

agent-521 found that both scripts released their `gcp-spend` reservation even
after a failed delete. Both now use the shared `config/image/teardown.sh`, with
the semantics reviewed for `run-overflow.sh`:

- `teardown_vm` deletes the VM, then releases the reservation only when the
  exact-name instance AND disk listings both succeed and are empty. Otherwise
  the reservation is kept and the result is reported.
- `vm_state` trusts only explicit GCE statuses or a successful empty exact
  listing.
- `run-gate.sh` retries only after a confirmed preemption and a proven teardown
  of the previous VM, whose reservation is then released. Unknown state exits 5
  without a retry; an unproven teardown exits 6.

Tests: `evidence-20261022/gate-builder-teardown/`, with no cloud: 5
`teardown_vm` cases, 6 `vm_state` cases, and the `run-gate.sh` loop for unknown
state (exit 6, no retry, reservation kept) and for preemption (2 attempts, 2
releases, exit 3).

## 2026-10-23 — `gcp-spend` inventory accounting follow-up and guard notification

Second agent-521 review: H1–H3 accepted; H4 corrected.

- Every live disk is priced from its own type, size and provisioning, and
  counted in commitments.
- A live RUNNING VM with contradictory history is charged from its last
  recorded event.
- Guard stops, and failed stops, notify agent-519 through Cairn, and the
  delivery is recorded.

Tests: `evidence-20261022/gcp-budget-boundaries-2/`.

- R1: an unpriced type on a disk sharing a VM's name is refused.
- R1b: a Hyperdisk without provisioning is refused.
- R1c: c4's Hyperdisk is priced at $0.0864/h.
- R2: a retained disk is a $0.017/h commitment.
- R3: a missing restart charges the unaccounted ~1 h.
- N1 and N2: a budget stop and a failed stop are both recorded and notified
  (the failed stop exits 1).
- A real delivery test to agent-475's own inbox gave event 172f615d.

Spend is still an ESTIMATE.

## 2026-10-23 — `gcp-spend` boundary corrections (agent-521 review)

Spend is still an estimate (billing data is unreadable), and the cap is not
yet declared enforced.

- **H1:** `reserve`, `release` and guard writes run under a process lock, and
  durations are validated.
- **H2:** guard log preservation is bounded best effort, the stop is always
  attempted, and both results are recorded truthfully.
- **H3:** open reservations stay charged until released after teardown.
- **H4:** live instances and disks are reconciled against the audit history.
  Missing live instances and residual disks are charged; an unpriced shape or a
  possibly truncated history refuses.

Live pricing now comes from the inventory's machine type. That surfaced agent-524's
`agent-ee-fourway524-20261023-0020` (c2d-highcpu-4 Spot, 2 h max), which had
been launched without a reservation; it is now charged. Tests:
`evidence-20261022/gcp-budget-boundaries/` (11 cases, fake gcloud, isolated
ledger).

## 2026-10-22 — $100 cumulative campaign cap: `gcp-spend` ledger and guard

Owner: "keep the gcp spend under control, I don't want to exceed $100".

- New `config/budget/gcp-spend`: an itemized estimate from audit-log lifetimes
  and catalog prices, with ×1.25 safety, a $3 allowance and $10 headroom.
  Billing data is not readable.
- `run-overflow.sh`, `run-gate.sh` and `build-image.sh` reserve the worst case
  before any create and refuse when spend is unknown or insufficient.
- A 15-minute user timer on proximal (`gcp-spend-guard`) stops c4, after
  preserving its gate logs, before the cap.
- First reconciliation: accrued about $23.69, $1.64/h committed, $66.31 left
  before the hold. Tests: reserve, refuse (oversized and unpriced) and release
  work against an isolated ledger, and the guard's first run made no stop.
  Details: [budget](config/budget/README.md).

## 2026-10-22 — Overflow boundaries: VM state and mixed handoff matches

Second agent-521 review of `run-overflow.sh`:

- `vm_state` now trusts only explicit GCE status values from a successful
  `describe`, and absence only from a successful exact-name listing that comes
  back empty. Arbitrary stderr ("helper command not found") and empty or
  unrecognised output are UNKNOWN.
- `native-admit cancel-queued` refuses (rc 6, touching nothing) when its
  selector matches both running and queued work.

Regressions in `evidence-20261022/overflow-boundaries/`: 7 `vm_state` cases,
and mixed, unique-queued and running-only `cancel-queued` probes with real
processes. All pass.

## 2026-10-22 — `run-overflow.sh` failure-path corrections (agent-521 review)

These fixes landed before any real overflow migration. Details are in README
"Test overflow".

- **Exclusive handoff:** the script now prepares the VM without running the
  job, then calls the new `native-admit cancel-queued`. That stops the one queued
  request under the admission mutex, with proof it never held a lease. A job
  that had already started is kept, and the VM copy is not run.
- **Collection:** collection is reported separately from the job result.
  Required evidence (log, exit marker, declared paths) must be complete, or the
  run exits 4.
- **VM state:** state comes only from a successful `describe`. Failed
  observations count as UNKNOWN, with no restart.
- **Cleanup:** cleanup is proven only from successful instance and disk
  listings.

All seven failure paths passed locally with a fake `gcloud`. `native-admit`
`37828fc2…` (adds `cancel-queued`) is on all five hosts.

## 2026-10-22 — Test overflow path `run-overflow.sh`

Owner authorization relayed by agent-521: use small GCP Spot instances when
tests wait too long. Added `config/image/run-overflow.sh`, which runs one
queued job per small Spot VM with an explicit lifetime, boot-disk auto-delete,
current admission tools, collection, and verified teardown.

The readiness smoke (doctor only, no tests) passed. Total VM time 177 s:
SSH ready in 37 s, image built from cache in 74 s. Cost about $0.004, and
teardown was verified.

At 23:4xZ the only long waiter was ee449d on c4 (20 min, behind the one-suite
cap), while archon had a free suite slot. agent-449 was told that local
re-dispatch was cheaper, and no overflow VM was used for a real job.

## 2026-10-22 — `agent-ee-pypy524-20261022-2330`: short-lived VM for the PyPy comparison

Owner request relayed by agent-524: a PyPy comparison after the Rust one, with
the same frozen iter8n and j6b2 inputs. Instance id 3532614198875333350,
us-west1-b, `c2d-highcpu-4` Spot, `DELETE` on termination,
`max-run-duration=7200s` (self-deletes by about 18:28 PDT at the latest). No
service account. Labels `purpose=agent-ee-pypy-scorer,owner=halbritt`. Image
`agent-ee-gate-20261022-0352`. Created 16:28:10 PDT; agent-475 verified it with
`gcloud compute instances describe`. agent-524 will delete it and its boot disk;
teardown is noted below once confirmed. Cost: about $0.07/h, at most about $0.15.
Torn down: agent-475 independently confirmed that no `pypy524` instance or disk remains in heath-stuff, checked by a poll that ended when the instance was gone.
agent-524 reported that the instance and disk lists were empty at 23:51:36Z. Result: two matched iter8n pairs, PyPy mean 69.889 s vs CPython 95.528 s (about 27% faster), with exact board parity. j6b2 kept its fixed_conflict refusal. The VM ran about 23 minutes, about $0.03.

## 2026-10-22 — `ci-run.sh` fails closed without `native-admit`

A missing or non-executable `~/.local/bin/native-admit` used to skip admission
silently. Now `ci-run.sh` exits 2 before any context, network, build or
container work. The exception is explicit: `run-gate.sh` passes
`CI_RUN_EPHEMERAL_VM=1` to its one-VM gates. The flag only excuses the missing
helper; where `native-admit` exists the gate is always admitted. The image
build pin (`build-image.sh` `CI_RUN_SHA256`) now matches the new script
(`2c4d75fd49b2b215…`). The current image (`agent-ee-gate-20261022-0352`) still holds
the older, admission-free `2c5c20f8…`, which these one-VM gates run until the
image is rebuilt. Installed on agent-ee-gate-c4 and peecee-wsl. Evidence:
`evidence-20261022/ci-run-admission/output-v2.txt`.

## 2026-10-22 — `ci-run.sh` admits itself

Correction requested in agent-522's audit. `ci-run.sh` used to read only optional
admission environment variables, so calling it directly ran unadmitted. It now
starts with `native-admit run --class suite --weight $JOBS`, which runs before
the build context, the image build or any container. Inside an already admitted
job it re-enters only after `native-admit verify` proves an inherited
lock-owning lease descriptor, so it is not charged twice. `CI_RUN_MAX_WAIT`
bounds the wait (exit 75). The doctor, sandbox-probe and owner-probe containers
now get the same label, `--cpus`, `--pids-limit` and `--init` (pre-tini images)
as the suite container. Throwaway `run-gate.sh` VMs have no `native-admit` and
run unadmitted, by design. Installed on agent-ee-gate-c4 and peecee-wsl
(`edc1fe8a4a43d713…`). Evidence: `evidence-20261022/ci-run-admission/` (draining
host waits then exits 75; idle host admitted w4; nested not double-charged;
forged marker exits 2; `JOBS=8` unreserved refused).

## 2026-10-22 — `agent-ee-rust524-20261022-2238`: short-lived VM for the Rust scorer timing

The owner authorized agent-524 to start a small isolated VM ("spin up a small
isolated one with the image already built"). Recorded here because the owner
wants GCP use tracked.

- Instance id 19682330611757326, us-west1-b, `c2d-highcpu-4` Spot,
  `instance-termination-action=DELETE`, `max-run-duration=7200s` (it deletes
  itself by about 17:36 PDT at the latest). No service account. Labels
  `purpose=agent-ee-rust-scorer,owner=halbritt`. Image
  `agent-ee-gate-20261022-0352`. Created 15:36:17 PDT. agent-475 verified it
  with `gcloud compute instances describe` at about 16:00 PDT.
- agent-524 applied nodiscard and ran its timing pairs under native-admit.
  agent-524 will delete it and verify that the instance and its boot disk are
  gone. Teardown is noted below once confirmed.
- Cost at Spot c2d about $0.018/vCPU-h: about $0.07/h, at most about $0.15.
- Torn down: agent-524 deleted the instance and reported the instance and disk lists empty at 23:07:20Z. agent-475 independently confirmed that no `rust524` instance or disk remains in heath-stuff. It ran about 31 minutes, about $0.04. agent-524's result: full iter8n placement, Python mean 94.293 s vs Rust 94.057 s (no meaningful speedup), all four boards identical.

## 2026-10-22 — `ci-run.sh` containers get the lease's CPU/PID bounds and an init

Following up the lease label: under `native-admit run`, the strict-suite
container now also gets `--cpus $NATIVE_ADMISSION_CPUS` and `--pids-limit
$NATIVE_ADMISSION_PIDS`. Images without a tini ENTRYPOINT (from before agent-ee
7e5bdc46) get `--init`. This matches what `ae-ci-exec` applies. Installed on
agent-ee-gate-c4 and peecee-wsl (`807be9b04958a1dc…`). The flag logic was checked on c4
against a tini image, a pre-tini image and an unadmitted call. The running gate
b29cead1 keeps the script it started with.

## 2026-10-22 — `ci-run.sh` labels its suite container with the admission lease

When agent-449 runs the c4 integration gate under `native-admit run`, the gate's
strict-suite container was also counted as an unleased suite. One gate showed as
used 8 with 2 suites against a limit of 1, and other suites waited needlessly.
`ci-run.sh` now adds `--label native-admission.lease=$NATIVE_ADMISSION_LEASE`
when it is set; test behaviour is unchanged. It is installed on
agent-ee-gate-c4 and peecee-wsl (`d8725585de04853b…`, backups `ci-run.sh.bak-20261022-lease`).
The gate that was already running keeps the old script until it exits.

## 2026-10-22 — `agent-ee-gate-c4`: root filesystem without online discard

The I/O stall agent-522 found (`jbd2_log_wait_commit`) is ext4 online
`discard`, which comes from the GCE Ubuntu image's fstab. Deleting trees such as
worktrees and per-run scratch queues discards on the Hyperdisk.

- Measured: with the filesystem idle, I/O PSI was 89–97 for about an hour, and
  the device sat at 90–99% utilization on about 100 discards/s at about 10 ms
  each. It also blocked admission of new work, since c4's `io_psi_max` is 20.
- Live `mount -o remount,nodiscard /` at 22:28:48Z cut PSI from 28–34 to 6–13
  within a minute, while a 4-worker suite started. The discard backlog already
  queued kept draining at about 100/s.
- Made persistent: `discard` removed from the root line in `/etc/fstab`
  (backup `/etc/fstab.bak-20261022-discard`). `fstrim.timer` (weekly) is
  enabled. `findmnt --verify` is clean.
- tmpfs scratch (`AE_CI_TMPFS`) was measured but is not adopted. Runs were
  CPU-quota-bound, and the matched pair was not completed. Evidence:
  `proximal:~/.local/share/infra/native-admission/evidence-20261022/`.
- The `agent-ee-gate` image still has `discard` in its fstab. A VM created from
  it needs the same fstab edit until the image is rebuilt.

## 2026-10-22 — `agent-ee-gate-c4`: idle stop and usage tracking

Owner request: "track its use, we should shut it down if it goes idle."

- `infra-idle-stop.timer` on c4 samples every minute into
  `/var/log/infra-usage/usage.jsonl`. After 30 idle minutes it powers off, which
  stops the instance. Idle means no running container, no `halbritt` work process
  older than 60 s, and 1-minute load under 2.0. Details:
  [idle stop](config/idle-stop/README.md).
- `c4-usage`, run from proximal, gives run hours and estimated cost from the GCE
  audit log, plus the busy share from the VM log. It skips failed operations.
  First report: 7.3 h, about $9, since creation.
- Verified on install: dry runs showed busy (5 containers, load about 150) and
  an idle path, the timer is active, the first journal verdict is busy, and the
  logrotate config is accepted. The decision logic was checked with a scratch
  test. The idle poweroff itself has not run yet.
- Observed: about 21,400 zombie `bwrap` processes on c4. Each in-container
  `strict_suite.py` run leaves thousands, because nothing in the container reaps
  orphans. Reported to agent-521 with the 3D-render finding.
  Fixed by AGENTEE-459 (agent-ee main 7e5bdc46: tini as PID 1 in the CI image).
  The c4 gate ran the new image: 5360 tests, exit 0.

## 2026-10-22 — `agent-ee-gate-c4`: kicad-route worker lanes

Owner request (via the coordinator): run kicad-route lanes here as well as agent-ee lanes. Details: [shared/kicad-route](../../shared/kicad-route/README.md).

- `~/git/kicad-route`: public clone of halbritt/kicad-route with `receive.denyCurrentBranch updateInstead`. proximal's checkout has the remote `agent-ee-gate-c4`.
- apt `python3-pip python3-numpy python3-scipy build-essential` (numpy 1.26.4, scipy 1.11.4, the same as proximal). The user site has proximal's pins: pytest 9.1.0, shapely 2.2.0 and jsonschema 4.26.0.
- rustup with toolchain 1.99.1 (minimal profile). `kicad-route update` built router generation `04f9b4c1…` (`owned-3c91fe5c0120`). There is no Java, so the Freerouting backend is unavailable.
- Check at kicad-route 409d06ab: 93 focused pcbnew/router tests passed in 42 s, exit 0, the same result as proximal.

## 2026-10-22 — `agent-ee-gate-c4` joins the tailnet

Owner request 2026-10-22 (via the coordinator).

- Installed tailscale 1.104.2 (pkgs.tailscale.com stable noble), then ran
  `tailscale up --hostname=agent-ee-gate-c4 --ssh=false`. The owner authorized it
  in the browser. Node `agent-ee-gate-c4`, `100.122.93.61` /
  `fd7a:115c:a1e0::552c:5d3e`, key expiry 2027-04-20.
- Verified: `tailscale ping` both ways (direct after DERP ord), ssh from proximal
  to `100.122.93.61` (same host key), and proximal Garage S3 at
  `100.85.100.81:3900` from c4 (403 AccessDenied when unsigned). The public-IP
  `ssh agent-ee-gate-c4` path is unchanged. No firewall or ACL change.

## 2026-10-22 — `agent-ee-gate-c4` becomes an agent-ee fleet worker host

Owner 2026-10-22, "load the machine now" (via the coordinator). Set up to match
peecee-wsl and archon; details in README.md "Fleet worker host".

- Toolchain: node v24.22.0, npm 11.19.1, claude 2.1.307, codex 0.163.0 (full
  standalone tree from peecee-wsl), uv 0.13.4, git-wt/git-land wrappers, native
  KiCad 10.0.7 / ngspice 42 / bwrap 0.9.0 / poppler 24.02 from the Dockerfile's
  apt snapshot.
- Repos: `~/git/agent-ee` pushed from proximal (new proximal remote
  `agent-ee-gate-c4`), kicad-route pin 5f1c072, fome-mc 8c42f2ee, kicad-happy
  06840467; `~/.cache/agent-worktrees/agent-ee/`.
- Credentials: added to `REMOTE_HOSTS` of claude-oauth-refresh and
  codex-auth-mirror; first push mirrored all five profiles (access tokens only).
  claude, claude-harm and codex-3 answered live probes; codex and codex-harm
  authenticated but are at their usage limit until 2026-10-27.
- Launcher: added to `HOSTS` and `REMOTE_ACCOUNTS` (all five accounts); test
  parallelism cap 8. Smoke worker via launch.py passed (exit 0, 18 s, sync_down
  and branch fetch OK) and was cleaned up.

## 2026-10-22 — `agent-ee-gate-c4` (c4-highcpu-48 Spot) launched as the 96-vCPU stand-in

Owner request (via coordinator agent-449). The C4 quota is at most 48 vCPUs in
us-*, so a c4-highcpu-48 stands in for the c4-highcpu-96. No quota request filed.

- `agent-ee-gate-c4` in us-central1-a: Spot, STOP on preemption, 200 GB
  hyperdisk-balanced at 10000 IOPS / 440 MiB/s, image family agent-ee-gate, no
  service account. It stays RUNNING. Spot about $1.31/h including the disk.
- `ssh agent-ee-gate-c4` from proximal via `~/.ssh/config.d/agent-ee-gate-c4`
  (address looked up through gcloud per connection).
- agent-ee 9d57124d: JOBS=16 458 s, JOBS=32 378 s (best). Two concurrent gates:
  2 × 16 took 591 s, with one load-sensitive failure in test_concurrent_reviews
  for 14ef7275; 2 × 12 took 625 s and both passed. Details in README.md.

## 2026-10-22 — agent-ee-gate image built and validated; C4 work host blocked by quota

Owner request (via coordinator agent-449): a GCE image for the agent-ee release
gate, then Spot validation VMs, then a long-running c4-highcpu-96 host.

- Added `config/image/` (build-image.sh, provision.sh, run-gate.sh, and ci-run.sh
  copied byte-identical from peecee-wsl, sha256 `2c5c20f8…eea3e5`).
- Image `agent-ee-gate-20261022-0352` (family `agent-ee-gate`): Ubuntu 24.04
  `ubuntu-2404-noble-amd64-v20261021`, docker.io 29.1.3, docker-buildx 0.30.1, the
  gate layout, fome-mc store at 1289f314, J1 drawing, ae-ci-exec `0e8cb9d2…015290`,
  and a warm `agent-ee:ci-14ef7275` build cache.
- Validation: Spot c2d-highcpu-16, `REBUILD=1 JOBS=8 ci-run.sh 14ef7275`: build 3 s,
  "strict suite passed: 258 modules, 4789 tests, no skips", `=== exit 0`, about
  18 min wall (peecee-wsl about 21 min). 0 preemptions.
- The first image (`agent-ee-gate-20261022-0315`) was deleted: its warm cache did
  not match SSH-staged contexts (umask; see notes.md).
- c4-highcpu-96 Spot host not launched: `CPUS-PER-VM-FAMILY-per-project-region`
  for C4 is 0 in us-west1/us-west2 and at most 48 elsewhere in us-*. No quota
  request filed. Recipe in README.md.
- Spend: about $0.40. No VMs left running.
