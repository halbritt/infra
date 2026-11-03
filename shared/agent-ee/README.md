# agent-ee CI-image test runner (`ae-ci-exec`)

`ae-ci-exec` runs a command inside the agent-ee CI image, built from the given
worktree's own Dockerfile on every run, with the release gate's sandbox options,
inputs and environment. It exists because proximal (Ubuntu 24.04), peecee-wsl (Ubuntu
26.04) and archon (Arch) cannot hold identical distro toolchains. Their native
Python (3.12.3 / 3.14.4 / 3.14.8), poppler (24.02 / 26.01 / 26.08) and ngspice
(42 / 45.2 / 47) differ. On unmodified main that made 7 modules fail on
peecee-wsl and 3 fail on archon. The CI image is the release-gate authority, so
agent-ee tests run inside it on every host.

Installed byte-identical at `~/.local/bin/ae-ci-exec` on proximal, peecee-wsl,
(canonical copy: this directory). talos, archon and agent-ee-gate-c4 were retired from agent-ee on 2026-10-24; the owner replaced the campaign with a single agent. Since
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
| `docker buildx build --load` of the commit's Dockerfile, tag `agent-ee:ci-SHA` | Same Dockerfile, `--builder default`, built on every run. Tags `agent-ee:exec-<16 hex>` (moved to each new build) and `agent-ee:exec-<16 hex>-<12 hex>` (one image, never moved). Never touches `agent-ee:ci-*` |
| `--network none --security-opt seccomp=unconfined --security-opt apparmor=<profile> --security-opt systempaths=unconfined` | `apparmor=unconfined` on every host. No AppArmor profile, ever (owner, 2026-10-23). |
| `AGENT_EE_REQUIRE_TOOLCHAIN=1 PYTHONPATH=src`, `-w /opt/agent-ee` | Same |
| fome-mc: anonymous clone at ci.yml `FOME_MC_COMMIT`, owned by the runtime user, `:ro` at `/opt/fome-mc` | Same clone recipe, in `~/.cache/ae-ci-exec/inputs/fome-mc-<commit>`, owned by the caller (the runtime user here) |
| J1 drawing, ci.yml `J1_DRAWING_SHA256`, `:ro` at `/opt/j1/te-776228-1.pdf` | Same; fetched with the CI curl line if missing, hash-checked on every run |
| kicad-route pin `5f1c072` in the image at `/opt/kicad-route`, owned by the image user 10001 | The image's own tree, extracted once per image ID to a caller-owned copy, verified with the image's `install.sh verify`, mounted `:ro` over `/opt/kicad-route` |
| kicad-happy's newest release when the image is built, at `/opt/kicad-happy`, recorded in `/opt/kicad-happy.install.json` | Same (no mount; root-owned, no `.git`). The build runs on every run, so a new release arrives with the next run |
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

The key is the first 16 hex digits of a SHA-256 over the image build inputs.
These are the Dockerfile plus every file named by its `COPY` instructions, except
`COPY .` and `--from` stages. On agent-ee main ece75c1a that is 52 files (key
`fa17728480fe069a`), among them `docker/kicad-route/*`, which holds the
kicad-route commit pin. For each file the hash
covers the path, the executable bit and the content. The build context is just
those files, written with git-archive modes (775/664), so it matches the gate's
`git archive` contexts and reuses their BuildKit layers. `COPY .` then copies
only that small context, and the worktree mount replaces it at run time.

The key covers local inputs only. The Dockerfile also ADDs two remote files that
follow upstream releases: the KiCad 10.0 PPA `InRelease` and kicad-happy's git ref
listing. BuildKit fetches them again only when a build runs, and a changed file
rebuilds the layers after it. Until 2026-11-03, ae-ci-exec skipped the build when
`agent-ee:exec-<key>` existed. A new KiCad or kicad-happy release therefore never
reached local test runs while the local inputs stayed the same. Now every run
builds, as image_for already did. The owner's direction (2026-11-03) was: "nothing
should be "pinned". Versions should be fixed and recorded ... kept up to date." When
nothing changed, every Dockerfile step comes from the cache, and BuildKit only fetches
the two remote files again. On proximal (2026-11-03) that build took about 1 s: 45
steps were CACHED, and each remote check took 0.2 to 0.7 s.

- Tags: `agent-ee:exec-<key>` is the newest image that ae-ci-exec built for the
  inputs, and each successful build moves it. `agent-ee:exec-<key>-<12 hex>` names
  one image ID and never moves. Before a build moves `agent-ee:exec-<key>`, the image
  it named gets its own tag, so old images never become dangling.
- One image per run: a run resolves its image once and prints
  `ae-ci-exec: image sha256:<64 hex> (agent-ee:exec-<key>-<12 hex>, built|reused|fallback, resolved in N s)`
  on stderr. After that, the kicad-route extraction and `docker run` use only the
  never-moved tag, so a later build cannot change the image of a run in progress.
  This is a tag and not a bare ID because native-admit counts unleased containers by
  their `agent-ee:` image name.
- Records: each build log ends with
  `=== built agent-ee:exec-<key> = sha256:... in N s (attempt n)` or with the
  failure and fallback lines. `~/.cache/ae-ci-exec/builds/<key>` holds the latest
  build's generation, status, input hash, image ID, finish time and log. Concurrent
  runs share it. ae-ci-exec writes no other per-run record; the image ID goes to
  stderr.
- Concurrency: builds, and every read or move of `agent-ee:exec-<key>`, run under
  `flock ~/.cache/ae-ci-exec/locks/image-<key>.lock`. image_for takes the same lock.
  A run reads the build generation before it waits for any lock. If a build for the
  key finished while it waited, the run uses that build's image, or shares its
  failure, and does not build again. Runs that start together therefore share one
  build. A run that starts after a build has finished builds again. Input fetching
  has its own lock, and each kicad-route extraction has a lock for its image ID.
- Build failures: retries follow ci-run.sh. There are 6 attempts (`BUILD_ATTEMPTS`)
  with backoff from 30 s to 600 s, for snapshot.ubuntu.com, Launchpad and GitHub
  errors. The run falls back when every attempt fails and `agent-ee:exec-<key>` names
  an image labelled `ae-ci-exec.inputs=<the same hash>`. It then uses that image,
  after a warning block on stderr that gives the image ID, its creation time, and
  the remote ADDs that were not rechecked. Runs that waited share the outcome. The
  full schedule spends about 16 minutes in backoff before it falls back. These cases
  do not fall back and fail with exit 2, as before: no image exists for the inputs,
  the inputs changed during the copy, a build gives no image ID, docker fails outside
  the build, or the kicad-route verify fails.
- kicad-route copies are keyed by image ID, at
  `~/.cache/ae-ci-exec/kicad-route/sha256-<64 hex>` (about 640 MB each). Copies
  named `<16 hex key>` come from ae-ci-exec versions before 2026-11-03.
- Logs: `~/.cache/ae-ci-exec/logs/build-<key>-<stamp>.log`.
- Signals: INT, TERM and HUP kill the container (`docker kill`) and remove the
  scratch dir. A signal during a build ends the run.
- Image GC is manual; ae-ci-exec never removes an image. Each upstream release adds
  an image for each key in use and a kicad-route copy for each image. List them with
  `docker images agent-ee --filter label=ae-ci-exec.inputs`. Remove an image's
  tags together with `~/.cache/ae-ci-exec/kicad-route/sha256-<id>{,.ready}`.

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
