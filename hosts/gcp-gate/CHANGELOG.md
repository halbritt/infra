# Host changelog

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
