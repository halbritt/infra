# gcp-gate

The agent-ee release gate on Google Compute Engine: a private image family,
`agent-ee-gate` in project `heath-stuff`, and throwaway Spot VMs booted from it.
Each VM runs the same `~/agent-ee-gate/ci-run.sh` as peecee-wsl, so a gate result
here means the same thing as one there. Requested by the owner on 2026-10-21 to
move the CPU-bound gate off shared hosts. Build and run scripts:
[`config/image/`](config/image/README.md).

## Current image

| | |
|---|---|
| Image | `agent-ee-gate-20261022-0352`, family `agent-ee-gate`, storage `us-west1`, labels `purpose=agent-ee-gate,owner=halbritt` |
| Self link | `https://www.googleapis.com/compute/v1/projects/heath-stuff/global/images/agent-ee-gate-20261022-0352` |
| Created | 2026-10-21T21:02:42-07:00; 100 GB disk, 7.50 GB archive (7500887616 bytes) |
| Base | `ubuntu-2404-noble-amd64-v20261021` (family `ubuntu-2404-lts-amd64`) |
| Docker | Ubuntu `docker.io` 29.1.3 (`29.1.3-0ubuntu3~24.04.2`) and `docker-buildx` 0.30.1 (`0.30.1-0ubuntu1~24.04.1`), both held. Same upstream versions and the same Ubuntu packaging as peecee-wsl (`29.1.3-0ubuntu4.1` / `0.30.1-0ubuntu1` on 26.04). containerd image store (overlayfs snapshotter), as on peecee-wsl. |
| Other packages | git, rsync, jq, python3, apparmor, apparmor-utils, zstd, curl |
| User | `halbritt` (uid 1001: the GCE image already has `ubuntu` at 1000), groups `docker`; `/etc/sudoers.d/agent-ee-gate` allows `sudo -n` for `chown` only, the one command ci-run.sh runs. The guest agent also adds SSH users to `google-sudoers`. |
| AppArmor | enabled for the distro profiles only. No agent-ee profile (owner, 2026-10-23): containers run `apparmor=unconfined`, and provision.sh sets `kernel.apparmor_restrict_unprivileged_userns=0` so bwrap works in them. The existing c4 disk still holds `/etc/apparmor.d/agent-ee-container` from before; it is removed if c4 is ever started again, or goes with the disk at retirement. |

### Contents of `/home/halbritt`

| Path | What |
|---|---|
| `agent-ee-gate/ci-run.sh` | image copy: sha256 `2c5c20f80838a26e49a21fecce0af5c64a14609ef7cc4d69215c7b4ec3eea3e5`. On agent-ee-gate-c4 and peecee-wsl since 2026-10-22: `99b77facef615f6edec9b3bd9d3ffbd51e70552e68481f867fc8c86358fca786` (under `native-admit run`: lease label, `--cpus`/`--pids-limit` from the lease, `--init` for images without tini) |
| `agent-ee-gate/ci-logs/`, `ctx/`, `tmp/` | empty (ci-run.sh needs `tmp/` for its summary dir) |
| `agent-ee-gate/inputs/te-776228-1.pdf` | J1 drawing, sha256 `14bd5c3b…6e4fe8` (ci.yml `J1_DRAWING_SHA256`) |
| `agent-ee-gate/ci-inputs/fome-mc-1289f3149d2bcaa83a3b490a0bfbd11ed8a17589` | anonymous clone of public github.com/halbritt/fome-mc at the ci.yml `FOME_MC_COMMIT`, owned 10001:10001, no credential config (the ci-run.sh recipe) |
| `.local/bin/ae-ci-exec` | sha256 `0e8cb9d2cd030755859932a52bcbbe3d1207039f195385aa5e20cf2d61015290` ([`shared/agent-ee`](../../shared/agent-ee/README.md)) |

Docker holds `agent-ee:ci-14ef7275` and its BuildKit cache (about 6 GB), so a
new `agent-ee:ci-SHA` build reuses the toolchain layers (KiCad 10.0.7 with
kicad-packages3d, ngspice 42, Bubblewrap, the Rust build stage, kicad-route
5f1c072, kicad-happy 2.3.1 at 06840467). The build context was deleted.

kicad-route and kicad-happy are not host checkouts: the Dockerfile pins and
fetches both into the image (`docker/kicad-route/install.sh`, `KICAD_HAPPY_COMMIT`).
ci-run.sh reads only the two host inputs above. There is no agent-ee bare mirror
(the repository is private), so contexts are staged with `git archive`.

Not in the image: credentials of any kind, SSH host keys, `authorized_keys`,
shell history, apt lists, machine-id, and `.git` directories other than the
public fome-mc store. VMs run with no service account.

## Run a gate

Default recipe: a Spot `c2d-highcpu-32` with termination action DELETE and
`JOBS=32`. This is the measured knee (see "Right-sizing" below). It was
`c2d-highcpu-16` with `JOBS=8` until 2026-10-23. From proximal:

```sh
~/git/infra/hosts/gcp-gate/config/image/run-gate.sh SHA
```

It creates the VM, stages `git archive SHA`, runs `JOBS=32 ./ci-run.sh SHA >
ci-logs/gate-SHA.out` detached, polls for `=== exit N`, copies `ci-logs/` to
`~/agent-ee-gate-gcp/SHA-<stamp>/` and deletes the VM. A preemption deletes the
VM; the script retries on a new one (3 attempts) and reports the count. By hand:

```sh
gcloud compute instances create agent-ee-gate-SHA --zone us-west1-b \
  --machine-type c2d-highcpu-32 --provisioning-model=SPOT --instance-termination-action=DELETE \
  --max-run-duration=3h --image-family agent-ee-gate --image-project heath-stuff \
  --boot-disk-size=100GB --boot-disk-type=pd-balanced --no-service-account --no-scopes \
  --labels purpose=agent-ee-gate,owner=halbritt
git -C ~/git/agent-ee archive SHA | gcloud compute ssh agent-ee-gate-SHA --zone us-west1-b \
  --command 'mkdir -p ~/agent-ee-gate/ctx/SHA && tar -x -C ~/agent-ee-gate/ctx/SHA'
gcloud compute ssh agent-ee-gate-SHA --zone us-west1-b \
  --command 'cd ~/agent-ee-gate && JOBS=32 ./ci-run.sh SHA > ci-logs/gate-SHA.out 2>&1; tail -n 3 ci-logs/gate-SHA.out'
gcloud compute instances delete agent-ee-gate-SHA --zone us-west1-b --quiet
```

SSH uses the project-metadata key (`~/.ssh/google_compute_engine`) over the
default network's existing SSH rule; no firewall change.

## Validation (2026-10-22, agent-ee main 14ef7275)

`REBUILD=1 run-gate.sh 14ef7275` on Spot `c2d-highcpu-16` (us-west1-b), `JOBS=8`,
0 preemptions. REBUILD forces the image build so the warm cache is exercised.

```
strict suite passed: 258 modules, 4789 tests, no skips.

=== exit 0; log /home/halbritt/agent-ee-gate/ci-logs/14ef7275-20261022T040740Z.log
```

| | GCE c2d-highcpu-16, JOBS=8 | peecee-wsl, JOBS=8 (fc9c9cae) |
|---|---|---|
| image build | 3 s (all layers cached) | cached |
| ci-run.sh wall | about 18 min (1099 s, 60 s polling) | about 21 min (02:20:38Z to 02:41:25Z) |

Module times sum to 8108 s; the longest module (`test_placement_campaign`)
takes 448 s, which bounds the wall time however many JOBS are used. The doctor
JSON is identical across the two GCE runs.

## Cost

Campaign spend is capped at **$100 cumulative** (owner, 2026-10-22). Every launch
needs a `gcp-spend reserve`, and a guard stops c4 before the cap. See
[budget](config/budget/README.md).

Measured with Cloud Billing catalog prices for us-west1 on 2026-10-22 (Spot
prices change):

| Item | Price |
|---|---|
| Spot c2d-highcpu-16 (16 × $0.01428 + 32 GiB × $0.001915) | $0.29/h |
| 100 GB pd-balanced | $0.10/GB-month, about $0.014/h |
| One gate run (about 25 min with boot and staging) | about $0.13 |
| Image storage (7.5 GB archive × $0.05/GB-month) | about $0.38/month |
| Spot c4-highcpu-96 (96 × $0.02074 + 192 GiB × $0.002357) | $2.44/h, plus about $0.08/h for 200 GB Hyperdisk Balanced at 10000 IOPS / 440 MiB/s |

The image build and validation (two builds, two gate runs, about 70 Spot
VM-minutes) cost about $0.40.

## Right-sizing (owner, 2026-10-22)

The owner said: "the aim of which is to throw as much CPU at it as it can use
and no more", and "Other tests as well, again on smaller instances run for the
duration and shut down."

Every cloud test job, gate or not, gets its own ephemeral Spot VM. It is sized
at the knee, the smallest shape at which wall time stops improving materially.
The VM is deleted when the job ends. Ledger reservation, maximum lifetime and
verified cleanup still apply. The rest of this section covers sizing; the
reasons c4 does not fit are under "c4: retirement plan".

[`config/image/gate-size`](config/image/gate-size) does the sizing:
`gate-size LOG [--modules M...] [--vcpus 4,8,16,32]`.

- It replays a measured ci-run log through strict_suite.py's own scheduling:
  modules are submitted in sorted order, and each of `--jobs` workers takes the
  next one when it frees.
- It prints predicted suite time and estimated cost per shape, then names the
  smallest shape within 10% of the best.
- `--modules` sizes an affected-test subset run through
  `strict_suite.py --jobs N MODULE...`.
- Module times carry the reference run's load, so check a new shape with one
  real run.

### Measured (2026-10-23, agent-ee main d04b5121: 282 modules, 5547 tests)

Both gates ran at the same time on separate VMs, from the same image and the
same warm cache (image build 71 s). Neither was preempted, and both passed. Teardown was
verified by empty instance and disk listings. Evidence is in
`proximal:~/.local/share/infra/gcp-sizing-20261023/`.

| Shape | JOBS | ci-run wall | Strict suite (replayed) | Slowest module | VM time | Metered cost |
|---|---|---|---|---|---|---|
| c2d-highcpu-16 | 16 | 1150 s | 1047 s | 667 s | 0.34 h | $0.103 |
| **c2d-highcpu-32** | 32 | **703 s** | 600 s | 549 s | 0.22 h | **$0.131** |
| c2d-highcpu-56 (predicted from the 32 run) | 56 | — | 555 s | 549 s | — | about $0.25 |
| c4-highcpu-48 (persistent, 2026-10-22, 9d57124d, 259 modules) | 32 | 378 s | — | 285 s | — | (see c4 below) |

Findings:

- **Full gate: `c2d-highcpu-32`, `JOBS=32`, now run-gate.sh's default.** It is
  39% faster than 16 vCPU for 27% more money. 56 vCPU would gain under 8% for
  1.75× the rate, because the suite is already within 1.09× of its slowest module.
- The floor is the slowest module: test_envelope_mechanics, 549 s on c2d. More
  vCPU cannot beat it. Only faster cores can (c4: 285–323 s), or splitting that
  module.
- The model fits. Replaying each run's own log reproduces its wall time to
  within about 3 s, after adding the 71 s build and about 30 s for doctor and
  probes. Cross-shape predictions carry the reference run's per-module load:
  the 16-vCPU log predicts 711 s at 32, against 600 s measured. Use a reference
  log from the target shape.
- Ordering is free speed, in agent-ee and not owned here. strict_suite submits
  modules alphabetically. Longest-first submission replays to 549 s at 32
  (the floor, against 600 s) and 978 s at 16 (against 1061 s).

### Job classes

| Class | Shape | Basis |
|---|---|---|
| Full strict gate (`run-gate.sh`) | c2d-highcpu-32, JOBS=32 | measured above |
| Affected-test subset through `strict_suite.py --jobs N` | `gate-size --modules …` against the latest c2d-32 log | replay, then one real run |
| Single-process `python3 -m unittest …` job (`run-overflow.sh`) | c2d-highcpu-4 (default) | one interpreter plus tool subprocesses; record the first real run's wall time and CPU before changing it |

### c4: retirement plan

**Done 2026-10-24 (owner):** the instance and its 200 GB Hyperdisk were deleted. The image `agent-ee-gate-20261022-0352` and the ephemeral `run-gate.sh` path remain.

A persistent, mostly idle c4-highcpu-48 does not fit this model. Its 12.4
running hours are most of the estimate, and its 200 GB Hyperdisk costs about
$63/month even when stopped.

Plan: once the ephemeral right-sized path has passed a real gate for agent-449,
preserve c4's logs and evidence and keep the image. Then report, through
agent-519, before deleting the instance or its disk. Until then, the idle stop
and the spend guard stay in place.

## Test overflow: `run-overflow.sh` (owner, 2026-10-22)

The owner said: "with the hosts being fully loaded, if tests are waiting too long, small gcp
spot instances could be used". [`config/image/run-overflow.sh`](config/image/run-overflow.sh)
moves ONE queued, never-started test job to a throwaway small Spot VM. agent-449 (or
agent-507 for router tests) picks the job; agent-475 runs the script.

Protocol, in order:

1. **Prepare without running.** The script creates the VM (default
   `c2d-highcpu-4`, `--max` lifetime with default 90m, DELETE on termination,
   boot-disk auto-delete, no service account). It stages the job's tree (tracked
   files plus `--include` paths, which must exist) and the current
   `native-admit`/`ae-ci-exec`, and builds the image with `ae-ci-exec . -- true`.
   The job does not run yet.
2. **Hand off exclusively.** `--handoff MATCH` runs `native-admit cancel-queued
   --match MATCH` on the job's host. Under the admission mutex it stops the one
   matching queued request and proves it never held a lease (`handoff.json`).
   If that request had already started, it keeps running locally and the VM
   copy is never executed (exit 7). A selector that matches both running and queued
   work is refused without touching either (rc 6, so the VM copy is not run:
   exit 8). `--operator-stopped` records a handoff the
   lane owner made themselves.
3. **Run and observe.** The script runs the job's exact `ae-ci-exec . -- CMD`.
   The VM counts as gone only from an explicit GCE status in a successful
   `describe` (TERMINATED, STOPPING, STOPPED, SUSPENDING, SUSPENDED), or from a
   successful exact-name `instances list` that comes back empty (exit 3).
   Empty or unrecognised output and arbitrary stderr are UNKNOWN. Failed observations are UNKNOWN, retried
   within a bound, and never restart the job (exit 5).
4. **Collect evidence.** Required: `job.log` with its exit marker and every
   `--collect` path. Anything missing gives exit 4, and partial evidence is kept.
5. **Clean up.** Absence is claimed only from successful instance AND disk
   listings (otherwise exit 6). `summary.json` records handoff, job exit,
   collection and cleanup separately.

```sh
~/git/infra/hosts/gcp-gate/config/image/run-overflow.sh --host HOST --tree WORKTREE --label LABEL \
  --handoff 'ae-ci-exec <worktree>: <command prefix>' [--include build/x] [--collect build/x] \
  [--machine-type c2d-highcpu-8] [--max 90m] -- CMD [ARG...]
```

Readiness smoke, 2026-10-22 23:44Z (first version of the script, doctor only):

| Step | Time |
|---|---|
| SSH ready | 37 s |
| Staging | 5 s |
| Image from cache | 74 s |
| Total VM time | 177 s |

That cost about $0.004, and teardown was verified. Practical startup before a
test starts is about 2–2.5 min. The failure paths were then checked locally with a fake `gcloud`
(`evidence-20261022/overflow-failure-paths/`), all seven passing:

| Case | Exit | Result |
|---|---|---|
| Normal | 0 | handoff cancelled, never leased; ran once on the VM; collection complete; cleanup verified |
| Raced to running | 7 | VM copy not executed |
| Missing collect path | 4 | partial log kept |
| Failed observations | 5 | UNKNOWN, no restart |
| TERMINATED | 3 | preempted or expired |
| Instance listing failed | 6 | cleanup not proven |
| Missing `--include` | 2 | refused before staging |

## Long-running work host: `agent-ee-gate-c4` (c4-highcpu-48 stand-in)

**Deleted 2026-10-24 (owner)**, with its disk. The rest of this section is history. The ssh client config is parked at `~/.ssh/config.d/.agent-ee-gate-c4.deleted-20261024`. The offline tailnet device `agent-ee-gate-c4` (100.122.93.61) still has to be removed in the Tailscale admin console.

Owner request 2026-10-21: one Spot C4 host that stays RUNNING for gates and
tests. The requested `c4-highcpu-96` is blocked by quota, so a `c4-highcpu-48`
(the largest that fits) stands in until the owner raises it. No quota request
was filed.

Quota (2026-10-22): `CPUS-PER-VM-FAMILY-per-project-region`, `vm_family=C4`, is
0 in us-west1 and us-west2 (create refused: "Quota 'CPUS_PER_VM_FAMILY' exceeded.
Limit: 0.0"), 48 in us-central1, and 24 in us-east1, us-east4, us-east5, us-south1,
us-west3 and us-west4. `PREEMPTIBLE_CPUS` is 0 everywhere, so Spot VMs use the
standard quotas.

| | |
|---|---|
| Instance | `agent-ee-gate-c4`, zone `us-central1-a`, `c4-highcpu-48` (48 vCPU, 96 GiB), Spot, termination action STOP |
| Disk | 200 GB `hyperdisk-balanced`, 10000 IOPS, 440 MiB/s (the default throughput for 200 GiB; Hyperdisk needs both set). The root filesystem grew to 193 GB at boot. |
| Image | family `agent-ee-gate` (`agent-ee-gate-20261022-0352`) |
| Access | `ssh agent-ee-gate-c4` from proximal (`~/.ssh/config.d/agent-ee-gate-c4`, below) |
| Tailnet | `agent-ee-gate-c4` / `agent-ee-gate-c4.tail0ecc2e.ts.net`, `100.122.93.61` and `fd7a:115c:a1e0::552c:5d3e` (joined 2026-10-22; see [Tailnet](#tailnet-2026-10-22)) |
| Root fs | ext4 without online `discard` since 2026-10-22: the image's fstab default stalled the Hyperdisk (I/O PSI about 90 while idle). Weekly `fstrim.timer`. See CHANGELOG |
| Idle stop | Powers off (stops) after 30 idle minutes; usage logged every minute. `config/idle-stop/c4-usage` reports run hours and cost. See [idle stop](config/idle-stop/README.md) (since 2026-10-22) |
| Spot price | $1.22/h compute (48 × $0.02074 + 96 GiB × $0.002357) + $0.086/h disk ($16 capacity + $35 IOPS above 3000 + $12 throughput above 140 MiB/s, per month) = **about $1.31/h, about $955/month if left running**. It no longer stays up when idle; see [idle stop](config/idle-stop/README.md). Stopped, it costs the disk only (about $63/month). |

```sh
gcloud compute instances create agent-ee-gate-c4 --zone us-central1-a --machine-type c4-highcpu-48 \
  --provisioning-model=SPOT --instance-termination-action=STOP \
  --image-family agent-ee-gate --image-project heath-stuff \
  --boot-disk-size=200GB --boot-disk-type=hyperdisk-balanced \
  --boot-disk-provisioned-iops=10000 --boot-disk-provisioned-throughput=440 \
  --no-service-account --no-scopes --labels purpose=agent-ee-gate,owner=halbritt
```

For the 96-vCPU host after a quota increase, change `--machine-type` to
`c4-highcpu-96` (and the zone, if another region gets the quota).

A STOP preemption keeps the disk but changes the ephemeral external IP. Restart
with `gcloud compute instances start agent-ee-gate-c4 --zone us-central1-a`. The
SSH alias looks up the address on each connection:

```
Host agent-ee-gate-c4
	User halbritt
	IdentityFile ~/.ssh/google_compute_engine
	IdentitiesOnly yes
	HostKeyAlias agent-ee-gate-c4
	UserKnownHostsFile ~/.ssh/google_compute_known_hosts
	StrictHostKeyChecking accept-new
	ServerAliveInterval 30
	ProxyCommand sh -c 'exec nc "$(gcloud compute instances describe agent-ee-gate-c4 --project heath-stuff --zone us-central1-a --format="value(networkInterfaces[0].accessConfigs[0].natIP)")" %p'
```

Run a gate on it:

```sh
git -C ~/git/agent-ee archive SHA | ssh agent-ee-gate-c4 'mkdir -p ~/agent-ee-gate/ctx/SHA && tar -x -C ~/agent-ee-gate/ctx/SHA'
ssh agent-ee-gate-c4 'cd ~/agent-ee-gate && JOBS=32 ./ci-run.sh SHA > ci-logs/gate-SHA.out 2>&1; tail -n 3 ci-logs/gate-SHA.out'
```

### Timings (2026-10-22, agent-ee main 9d57124d: 259 modules, 4831 tests)

| Run | Result | Wall |
|---|---|---|
| JOBS=16, one gate (image build from warm cache: 13 s) | passed | 458 s (about 445 s without the build) |
| JOBS=32, one gate (image reused) | passed | **378 s** |
| two gates at once, JOBS=16 each (9d57124d and 14ef7275) | 9d57124d passed; 14ef7275 FAILED one test | 591 s / 590 s |
| two gates at once, JOBS=12 each (same SHAs) | both passed | 625 s / 624 s; peak 1-min load 168 |

- Best single-gate setting: **JOBS=32**. On C4 the slowest module
  (`test_placement_campaign`) takes 285 s and module times sum to about 6200 s, so
  a gate cannot go much below about 300 s whatever JOBS is.
- Two concurrent gates each take about 1.35 to 1.4 times a single JOBS=16 gate.
  Two in parallel (about 10.4 min for both) finish only slightly before two
  back-to-back JOBS=32 gates (2 × 378 s = 12.6 min).
- Load sensitivity: in the 2 × 16 run, `test_concurrent_reviews ...
  test_coordinator_reports_failure_incomplete_and_does_not_adjudicate` failed with
  "budget exceeded under load 77.33 (initial roles ('circuit', 'physical') did not
  overlap in time)". The test asserts that two review roles overlap in wall time,
  so it can fail on an oversubscribed host. The tool subprocesses push the load
  well above the 48 vCPUs. The 2 × 12 run passed, but its load still peaked at 168,
  so it is no guarantee. For release decisions, run one gate at a time (JOBS=32),
  or treat a lone failure of this test under concurrency as a rerun, not a verdict.

### Fleet worker host (2026-10-22)

Owner 2026-10-22 ("load the machine now"): `agent-ee-gate-c4` is also an
agent-ee fleet worker host, set up to match peecee-wsl and archon. The
burndown launcher (`launch.py` / `review.py`) runs Claude and Codex workers
here over ssh with the same paths as proximal. Release gates in
`~/agent-ee-gate` are unchanged and share the CPUs.

| Tool | Version | Source on this host |
|---|---|---|
| node / npm | v24.22.0 / 11.19.1 | nodejs.org `node-v24.22.0-linux-x64.tar.xz` (SHASUMS256 checked) extracted into `/usr/local`; `npm i -g npm@11.19.1` |
| claude | 2.1.307 | `npm i -g --allow-scripts=@anthropic-ai/claude-code @anthropic-ai/claude-code@2.1.307` under prefix `~/.npm-global` (npm 11 blocks the postinstall that selects `claude.exe` unless allowed) |
| codex | 0.163.0 | the full standalone tree `~/.codex/packages/standalone/releases/0.163.0-x86_64-unknown-linux-musl/` (`bin/`, `codex-path/rg`, `codex-resources/`) copied from peecee-wsl; `~/.local/bin/codex` symlinks to its `bin/codex`. `@openai/codex@0.163.0` is also in `~/.npm-global`, as on peecee-wsl |
| uv / uvx | 0.13.4 | binaries and `~/.local/bin/env` copied from peecee-wsl |
| git-wt / git-land | cairn `git_trunk_tools.py` | `~/.local/bin` wrappers identical to peecee-wsl; the script alone at `~/git/cairn/scripts/git_trunk_tools.py` |
| ae-ci-exec | `0e8cb9d2…015290` | from the image; verified as uid 1001 (`tests.test_tree_hygiene`, 6 tests OK) |
| KiCad / ngspice / bwrap / poppler (native) | 10.0.7 / 42 / 0.9.0 / 24.02.0 | apt from the Dockerfile's snapshot PPA (`kicad-10.0-snapshot.sources`, `20261015T000000Z`, key `docker/kicad-10.0-releases.asc`); kicad held. Same versions as the CI image (no packages3d natively) |
| python3 / git / rsync / jq | 3.12.3 / 2.43.0 / 3.2.7 / 1.7 | Ubuntu 24.04 (peecee-wsl on 26.04 has 3.14.4 / 2.53.0 / 3.4.1 / 1.8.1; gating tests run in the CI image, so this is native drift only) |

`~/.profile` sources `~/.local/bin/env` and `~/.profile.d-toolchains.sh` (copied
from peecee-wsl), so `bash -lc` puts `~/.local/bin` and `~/.npm-global/bin` on
PATH. Global git config: `user.name halbritt`, `user.email`, `init.defaultBranch
main`, `safe.directory *` (no credential helper).

Layout, as on peecee-wsl:

| Path | What |
|---|---|
| `~/git/agent-ee` | `git init` + `receive.denyCurrentBranch updateInstead`, populated by `git push agent-ee-gate-c4 main:main` from proximal (no origin: GitHub agent-ee is private and the host holds no GitHub credential). proximal's `~/git/agent-ee` has remote `agent-ee-gate-c4` = `ssh://agent-ee-gate-c4/home/halbritt/git/agent-ee`, which launch.py pushes base refs to and fetches worker branches from |
| `~/git/agent-ee/build/kicad-route-pin-5f1c072` | copied from proximal (HEAD 5f1c072b, clean) |
| `~/git/fome-mc` | public clone at peecee-wsl's 8c42f2ee |
| `~/git/kicad-happy` | public clone at 06840467 (2.3.1) |
| `~/git/kicad-route` | public clone of github.com/halbritt/kicad-route + `receive.denyCurrentBranch updateInstead`; proximal's `~/git/kicad-route` has remote `agent-ee-gate-c4` = `ssh://agent-ee-gate-c4/home/halbritt/git/kicad-route` for `launch.py --repo`. Router generation `.router-generations/04f9b4c1…` built by `kicad-route update` (rustup 1.99.1 and `build-essential` added). See [shared/kicad-route](../../shared/kicad-route/README.md) |
| `~/.cache/agent-worktrees/kicad-route/` | git-wt worktrees for kicad-route lanes |
| `~/.cache/agent-worktrees/agent-ee/` | git-wt worktrees created by launch.py |
| `/tmp/agent-ee-burndown-20261017/` | created by launch.py `sync_up` (rsync -R) per worker |

Credentials come only from proximal's mirror timers; nobody logs in on this host.
`agent-ee-gate-c4` is in `REMOTE_HOSTS` of
[`claude-oauth-refresh`](../proximal/config/claude-oauth-refresh/README.md) and
[`codex-auth-mirror`](../proximal/config/codex-auth-mirror/README.md). Before the
first push `~/.claude-harm/.claude.json` was created as `{}` so the account block
is mirrored (as on peecee-wsl). First run 2026-10-22 05:2x UTC: `~/.claude
mirrored`, `~/.claude-harm mirrored+account`, `~/.codex`, `~/.codex-harm`,
`~/.codex-3 mirrored`. Checked without printing values: every file mode 0600, no
`refresh` key in either Claude file, `tokens.refresh_token == ""` in all three
Codex files. Live probes, launch.py's own argv shape: `claude --print` (haiku)
answered OK for `~/.claude` and `~/.claude-harm`; `codex exec` answered OK for
`~/.codex-3`; `~/.codex` and `~/.codex-harm` authenticated and were refused by
the accounts' usage limits (until 2026-10-27), not by auth. Gemini: not mirrored
here (peecee-wsl holds a plain copy, but no remote host runs agy; launch.py
keeps argon/agyopus on proximal).

Launcher registration (`/tmp/agent-ee-burndown-20261017`, backups
`*.bak-20261022c4`): `HOSTS` and `REMOTE_ACCOUNTS` include `agent-ee-gate-c4`
with all five accounts; `pick_host` scores it by 1-minute load / 48 threads like
the others. Worker and reviewer notes cap test parallelism here at 8 processes.

Smoke test 2026-10-22: `launch.py haiku claude-harm 397 c4-smoke-20261022 --host
agent-ee-gate-c4` with a no-op note. The worker ran on the host (hostname, nproc
48, all CLIs on PATH), made one empty commit, exited 0 in 18 s; `sync_down`
brought `result.md` back and the runner fetched `wt/c4-smoke-20261022` (2e2d69fd)
into proximal. Worktrees, branches and the base ref were then removed on both
sides; the worker dir is kept at `/tmp/agent-ee-burndown-20261017/smoke/`.

To retire it as a worker host: remove it from `REMOTE_HOSTS` in both mirror
scripts and from `HOSTS`/`REMOTE_ACCOUNTS`, then delete the profile dirs on the
VM (or the VM).

### Tailnet (2026-10-22)

Owner request 2026-10-22: `agent-ee-gate-c4` is on the tailnet, mainly so it can
reach proximal's Garage S3 endpoint `http://100.85.100.81:3900` (see
[`../proximal/config/garage/README.md`](../proximal/config/garage/README.md#tailnet-s3-endpoint)).

| | |
|---|---|
| Package | `tailscale` 1.104.2 from `https://pkgs.tailscale.com/stable/ubuntu noble main` (`/etc/apt/sources.list.d/tailscale.list`, keyring `/usr/share/keyrings/tailscale-archive-keyring.gpg`); `tailscaled` enabled |
| Join | `sudo tailscale up --hostname=agent-ee-gate-c4 --ssh=false`, authorized by the owner in the browser (no auth key stored anywhere) |
| Node | `agent-ee-gate-c4`, MagicDNS `agent-ee-gate-c4.tail0ecc2e.ts.net`, `100.122.93.61`, `fd7a:115c:a1e0::552c:5d3e`; node key expires 2027-04-20 06:57 UTC |
| Prefs | Tailscale SSH off, no exit node, no advertised routes, does not accept routes (`RouteAll=false`), MagicDNS on through systemd-resolved (GCE metadata and public names still resolve) |

Verified 2026-10-22: `tailscale ping` works in both directions (proximal reached
c4 through DERP `ord` first, then directly at `34.173.184.33:41641`). From
proximal, `ssh -i ~/.ssh/google_compute_engine -o HostKeyAlias=agent-ee-gate-c4
-o UserKnownHostsFile=~/.ssh/google_compute_known_hosts halbritt@100.122.93.61`
reaches the same host key. The `ssh agent-ee-gate-c4` alias (public IP through
gcloud) still works and is unchanged. No GCP firewall rule and no tailnet ACL
was changed. From c4, `curl http://100.85.100.81:3900/` returns Garage's 403
`AccessDenied` (reachable, unsigned).

The node's tailnet identity is in `/var/lib/tailscale` on this VM's disk. It is
not part of the `agent-ee-gate` image. Never image this disk without removing
that directory first. To leave the tailnet: `sudo tailscale logout` on the VM,
then remove the machine in the Tailscale admin console. Deleting the VM leaves a
stale machine entry, which also has to be removed there.
