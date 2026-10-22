# Host changelog

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
