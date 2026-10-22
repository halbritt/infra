# Host changelog

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
