# agent-ee CI-image test runner (`ae-ci-exec`)

`ae-ci-exec` runs a command inside the pinned agent-ee CI image, built from the
given worktree's own Dockerfile, with the release gate's sandbox options, inputs
and environment. It exists because proximal (Ubuntu 24.04), peecee-wsl (Ubuntu
26.04) and archon (Arch) cannot hold identical distro toolchains. Their native
Python (3.12.3 / 3.14.4 / 3.14.8), poppler (24.02 / 26.01 / 26.08) and ngspice
(42 / 45.2 / 47) differ. On unmodified main that made 7 modules fail on
peecee-wsl and 3 fail on archon. The CI image is the release-gate authority, so
agent-ee tests run inside it on every host.

Installed byte-identical at `~/.local/bin/ae-ci-exec` on proximal, peecee-wsl,
archon and agent-ee-gate-c4 (canonical copy: this directory; talos was retired from agent-ee on 2026-10-24). Since
2026-10-22 every run is admitted by `native-admit` (host-wide budget, leases,
queue, CPU/PID bounds, init for old images); see
[native-admission.md](native-admission.md).

```sh
ae-ci-exec WORKTREE -- COMMAND [ARG...]
ae-ci-exec . -- python3 -m unittest tests.test_x
ae-ci-exec . -- python3 scripts/strict_suite.py --jobs 3 test_x test_y
AGENT_EE_SKIP_VISUALS=1 ae-ci-exec . -- python3 -m unittest tests.test_x
```

## What it reproduces

Source of truth: `~/agent-ee-gate/ci-run.sh` on peecee-wsl and agent-ee's
`.github/workflows/ci.yml` (job `image`, step "Full test suite, strict toolchain
mode, no skips").

| Gate | ae-ci-exec |
|---|---|
| `docker buildx build --load` of the commit's Dockerfile, tag `agent-ee:ci-SHA` | Same Dockerfile, `--builder default`, tag `agent-ee:exec-<16 hex>`; never touches `agent-ee:ci-*` |
| `--network none --security-opt seccomp=unconfined --security-opt apparmor=<profile> --security-opt systempaths=unconfined` | `apparmor=unconfined` on every host. No AppArmor profile, ever (owner, 2026-10-23). |
| `AGENT_EE_REQUIRE_TOOLCHAIN=1 PYTHONPATH=src`, `-w /opt/agent-ee` | Same |
| fome-mc: anonymous clone at ci.yml `FOME_MC_COMMIT`, owned by the runtime user, `:ro` at `/opt/fome-mc` | Same clone recipe, in `~/.cache/ae-ci-exec/inputs/fome-mc-<commit>`, owned by the caller (the runtime user here) |
| J1 drawing, ci.yml `J1_DRAWING_SHA256`, `:ro` at `/opt/j1/te-776228-1.pdf` | Same; fetched with the CI curl line if missing, hash-checked on every run |
| kicad-route pin `5f1c072` in the image at `/opt/kicad-route`, owned by the image user 10001 | The image's own tree, extracted once per image to a caller-owned copy, verified with the image's `install.sh verify`, mounted `:ro` over `/opt/kicad-route` |
| kicad-happy 2.3.1 in the image at `/opt/kicad-happy` | Same (no mount; root-owned, no `.git`) |
| Runs as image user 10001 on the image's source copy | Runs as `--user $(id -u):$(id -g)` (uid 1000 = image user `ubuntu`) on the **live worktree**, mounted read-write at `/opt/agent-ee` |
| strict_suite gives each module a private TMPDIR | Per-run scratch dir mounted at `/tmp`, `TMPDIR=/tmp`, `HOME=/tmp` (as in the CI fixture step); removed after the run (`AE_CI_KEEP_TMP=1` keeps it) |
| `/opt/agent-ee` has no `.git` (`.dockerignore`), so agent-ee falls back to a file walk | git works on the live tree. For a linked worktree (`.git` is a file), the common gitdir is mounted read-only and the worktree's own gitdir (index, HEAD) read-write, both at their host paths. A generated gitfile names that gitdir absolutely at `/opt/agent-ee/.git`. Object alternates are mounted read-only. A plain checkout's `.git` is inside the mount already. |

Why git is exposed instead of hidden: agent-ee (`tests/test_tree_hygiene.py`,
`scripts/check_origins.py`) uses `git ls-files` whenever `.git` exists, and walks
files only when it is absent. A mount cannot make `.git` absent. The first
version (infra ea97a44) put a tmpfs or `/dev/null` over it. That left a broken
`.git`, so `git ls-files` failed in agent worktrees (found by the AGENTEE-417
review). On a live tree, `git ls-files` is also the right answer, because a file
walk would include untracked scratch.

Why the kicad-route copy is needed: as uid 1000, `git` refuses the image's
10001-owned `/opt/kicad-route` ("dubious ownership"). The gate's runtime user
owns that tree, so a caller-owned copy restores the gate's behaviour. It is
read-only because concurrent runs share it.

## Image tag and build

The tag is the first 16 hex digits of a SHA-256 over the image build inputs.
These are the Dockerfile plus every file named by its `COPY` instructions, except
`COPY .` and `--from` stages. Today that is `docker/apt-retry.sh`,
`docker/kicad-10.0-releases.asc`, `docker/kicad-route/*` (which holds the
kicad-route commit pin) and `docker/image-context.json`. For each file the hash
covers the path, the executable bit and the content. The build context is just
those files, written with git-archive modes (775/664), so it matches the gate's
`git archive` contexts and reuses their BuildKit layers. `COPY .` then copies
only that small context, and the worktree mount replaces it at run time.

- Builds run under `flock ~/.cache/ae-ci-exec/locks/image-<hash>.lock`, after a
  recheck that the image is still missing. Concurrent workers therefore build
  once and share the image. Input fetching has its own lock.
- Build retries follow ci-run.sh: 6 attempts, with backoff from 30 s to 600 s
  for snapshot.ubuntu.com and Launchpad 503s.
- Logs: `~/.cache/ae-ci-exec/logs/build-<hash>-<stamp>.log`.
- Signals: INT, TERM and HUP kill the container (`docker kill`) and remove the
  scratch dir.
- Image GC is manual. List with `docker images agent-ee --filter
  label=ae-ci-exec.inputs`. Remove `~/.cache/ae-ci-exec/kicad-route/<hash>{,.ready}`
  with the image.

No sudo, and no AppArmor profile (owner, 2026-10-23). On an AppArmor host, bwrap
inside the unconfined container needs `kernel.apparmor_restrict_unprivileged_userns=0`:
install [60-agent-ee-userns.conf](60-agent-ee-userns.conf) in `/etc/sysctl.d/` and run
`sudo sysctl -p` on it. ae-ci-exec refuses to start while the restriction is on. Set on
proximal (talos had it until it left agent-ee on 2026-10-24); archon and peecee-wsl run without AppArmor. Do not run agent-ee's
`scripts/container_apparmor.sh`: it loads the profile again.

## Git verification (2026-10-21, proximal, agent-ee main cc6b124)

| Checkout | `check_origins.py` | `test_tree_hygiene` | in-container git |
|---|---|---|---|
| linked worktree `~/.cache/agent-worktrees/agent-ee/ae-ci-gitfix` | `errors: []` | 6 tests OK | `status` clean, `rev-parse HEAD` ok, common gitdir read-only |
| plain clone with alternates (`git clone --shared`) | `errors: []` | OK | `status` clean, `cat-file` ok |
| `git archive` tree (no `.git`) | not run | OK (file walk) | none |

## Parity (2026-10-21, agent-ee main de12cca)

Image `agent-ee:exec-2657c88d90d4f0a9` (inputs
`2657c88d90d4f0a93887a98d2328448b4ce6d34b5c2b52d96979de24bdf9956a`). The
clean tree is `git archive de12cca`. The runs used `strict_suite.py --jobs 3`
(at most 3 test processes) and started only when the 1-minute load was at or
below the thread count. Batch A ran with `AGENT_EE_SKIP_VISUALS=1`. Batch B ran
the imaging and coordinator modules without it. Before the tests, the sandbox
probe and `agent-ee doctor --checks-only` passed on every host. The doctor JSON
is byte-identical across the three hosts.

| Module | proximal | peecee-wsl | archon | native failure it replaces |
|---|---|---|---|---|
| test_schematic_render (B) | pass | pass | pass | peecee-wsl drift |
| test_dc_path | pass | pass | pass | peecee-wsl drift |
| test_netlist_parity | pass | pass | pass | peecee-wsl drift |
| test_empirical_facts (B) | pass | pass | pass | peecee-wsl drift |
| test_datasheet_capabilities | pass | pass | pass | peecee-wsl drift |
| test_passive_corners | pass | pass | pass | peecee-wsl drift |
| test_stage_receipts (B) | pass | pass | pass | peecee-wsl drift |
| test_fab_package | pass | pass | pass | archon (DeclaredFabCampaignTests) |
| test_fab_stage | pass | pass | pass | archon |
| test_electrical_locality | pass | pass | pass | archon (Python 3.14 recursion subcases) |
| **total** | 295 tests, 0 skips | 295 tests, 0 skips | 295 tests, 0 skips | |

| Host | image build | batch A (7 modules, 180 tests) | batch B (3 modules, 115 tests) |
|---|---|---|---|
| proximal | 267 s (cold; base images pulled) | 141 s | 156 s |
| peecee-wsl | 2 s (every toolchain layer cached from the gate's `agent-ee:ci-*` builds) | 102 s | 92 s |
| archon | 262 s (cold; base images pulled) | 133 s | 103 s |

Image IDs differ per host (proximal `e634b4e20463`, peecee-wsl `aa11c35328c2`,
archon `f6a1a6ac56e9`). Docker builds are not bit-reproducible (layer
timestamps). The pinned contents agree, as the identical doctor output
(binary hashes and versions) shows.
