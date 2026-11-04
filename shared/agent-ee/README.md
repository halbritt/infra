# agent-ee CI-image test runner (`ae-ci-exec`)

`ae-ci-exec` runs a command inside the agent-ee CI image, built from the given
worktree's own Dockerfile and rechecked against upstream at most every 6 hours
(`AE_CI_REFRESH_HOURS`), with the release gate's sandbox options, inputs and
environment. It exists because proximal (Ubuntu 24.04), peecee-wsl (Ubuntu
26.04) and archon (Arch) cannot hold identical distro toolchains. Their native
Python (3.12.3 / 3.14.4 / 3.14.8), poppler (24.02 / 26.01 / 26.08) and ngspice
(42 / 45.2 / 47) differ. On unmodified main that made 7 modules fail on
peecee-wsl and 3 fail on archon. The CI image is the release-gate authority, so
agent-ee tests run inside it on every host.

Installed at `~/.local/bin/ae-ci-exec` (canonical copy: this directory). proximal runs
the 2026-11-03 version (a build on every run), sha256 `2e1a6567…`, installed
2026-11-03T23:54:08Z by atomic rename. The retention version described below (refresh
window, router copies keyed by content, eviction) is not installed yet. peecee-wsl was
not updated and its copy was not checked; it is not used by the current single-agent
campaign. talos, archon and agent-ee-gate-c4 were retired from agent-ee on 2026-10-24; the owner replaced the campaign with a single agent. Since
2026-10-22 every run is admitted by `native-admit` (host-wide budget, leases,
queue, CPU/PID bounds, init for old images); see
[native-admission.md](native-admission.md).

```sh
ae-ci-exec WORKTREE -- COMMAND [ARG...]
ae-ci-exec . -- python3 -m unittest tests.test_x
ae-ci-exec . -- python3 scripts/strict_suite.py --jobs 3 test_x test_y
AGENT_EE_SKIP_VISUALS=1 ae-ci-exec . -- python3 -m unittest tests.test_x
AE_CI_REFRESH_HOURS=0 ae-ci-exec . -- python3 -m unittest tests.test_x  # recheck upstream now
ae-ci-exec --router-copy IMAGE   # path of IMAGE's verified kicad-route copy, for other tools
ae-ci-exec --gc [--dry-run]      # evict unused images and copies now (runs do it when they end)
```

## What it reproduces

Source of truth: `~/agent-ee-gate/ci-run.sh` on peecee-wsl and agent-ee's
`.github/workflows/ci.yml` (job `image`, step "Full test suite, strict toolchain
mode, no skips").

| Gate | ae-ci-exec |
|---|---|
| `docker buildx build --load` of the commit's Dockerfile, tag `agent-ee:ci-SHA` | Same Dockerfile, `--builder default`, rebuilt at most every `AE_CI_REFRESH_HOURS` (default 6). Tags `agent-ee:exec-<16 hex>-current` (moved to each new build), `agent-ee:exec-<16 hex>-<12 hex>` (one image, never moved) and the older `agent-ee:exec-<16 hex>` (created once, never moved). Never touches `agent-ee:ci-*` |
| `--network none --security-opt seccomp=unconfined --security-opt apparmor=<profile> --security-opt systempaths=unconfined` | `apparmor=unconfined` on every host. No AppArmor profile, ever (owner, 2026-10-23). |
| `AGENT_EE_REQUIRE_TOOLCHAIN=1 PYTHONPATH=src`, `-w /opt/agent-ee` | Same |
| fome-mc: anonymous clone at ci.yml `FOME_MC_COMMIT`, owned by the runtime user, `:ro` at `/opt/fome-mc` | Same clone recipe, in `~/.cache/ae-ci-exec/inputs/fome-mc-<commit>`, owned by the caller (the runtime user here) |
| J1 drawing, ci.yml `J1_DRAWING_SHA256`, `:ro` at `/opt/j1/te-776228-1.pdf` | Same; fetched with the CI curl line if missing, hash-checked on every run |
| kicad-route pin `5f1c072` in the image at `/opt/kicad-route`, owned by the image user 10001 | The image's own tree, extracted once per router state (the image's state manifest and install record) to a caller-owned copy, verified with the `install.sh verify` of the image that asked for it, mounted `:ro` over `/opt/kicad-route` |
| kicad-happy's newest release when the image is built, at `/opt/kicad-happy`, recorded in `/opt/kicad-happy.install.json` | Same (no mount; root-owned, no `.git`). A new release arrives with the first run after the refresh window (6 h by default; `AE_CI_REFRESH_HOURS=0` checks now) |
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
reached local test runs while the local inputs stayed the same. The owner's direction
(2026-11-03) was: "nothing should be "pinned". Versions should be fixed and recorded
... kept up to date." So a run builds, which rechecks upstream, when the last
successful check for its inputs is older than `AE_CI_REFRESH_HOURS` (default 6; `0`
checks on every run). It also builds when `-current` is missing or the local inputs
changed (a new key). Otherwise it reuses `-current` without building and prints when
upstream was last checked and when it will be checked next. A run also shares the
build of a run it waited for. The window came after the owner called the unbounded
growth of images and copies "stupid" (2026-11-03): a build on every run made a new
image whenever any branch of kicad-happy moved. When
nothing changed, every Dockerfile step comes from the cache, and BuildKit only fetches
the two remote files again. On proximal (2026-11-03) that build took about 1 s: 45
steps were CACHED, and each remote check took 0.2 to 0.7 s.

- Tags: `agent-ee:exec-<key>-current` is the newest image this version built for the
  inputs, and each successful build moves it. `agent-ee:exec-<key>-<12 hex>` names
  one image ID and never moves. Before a build moves `-current`, the image it named
  gets its own tag, so old images never become dangling.
- `agent-ee:exec-<key>` is the tag that earlier ae-ci-exec versions and image_for use.
  A build creates it when it is missing, as image_for does, and never moves it. When
  `-current` is missing, a run seeds it once from `exec-<key>`, under the lock. It does
  this only if that image is labelled with the same full input hash, so the first run
  of this version has an image to fall back to. Runs never use `exec-<key>` directly.
  The 2026-11-03 cross-review found why the tag must not move: an earlier version
  reads this tag again after releasing its lock, and it mounts a kicad-route copy
  keyed by input hash, extracted from the image the tag named earlier. Moving the tag
  would put those callers on a new image with an old router copy. So older callers (an
  installed copy that has not been replaced, or a run admitted before the replacement)
  keep a consistent image and copy.
- Lookups: "missing" means that Docker answered `No such image: <tag>` for exactly that
  tag. Any other failure of `docker image inspect` aborts the run with exit 2, before
  the tag write the lookup guards, and names the Docker error. Examples are an
  unreachable daemon, a connection reset or a timeout. So a transient daemon error
  never creates, seeds or moves a tag. The second Sol review (finding 1) showed that
  the previous code read every inspect error as "missing". It could then retag
  `exec-<key>` after a successful build.
- One image per run: a run resolves its image once and prints
  `ae-ci-exec: image sha256:<64 hex> (agent-ee:exec-<key>-<12 hex>, built|window|reused|fallback, resolved in N s)`
  on stderr. After that, the kicad-route extraction and `docker run` use only the
  never-moved tag, so a later build cannot change the image of a run in progress.
  This is a tag and not a bare ID because native-admit counts unleased containers by
  their `agent-ee:` image name.
- Records: each build log ends with
  `=== built agent-ee:exec-<key>-current = sha256:... in N s (attempt n of N)` or with
  the failure and fallback lines. Line 1 of `~/.cache/ae-ci-exec/builds/<key>` holds
  the latest build's generation, status, input hash, image ID, finish time and log;
  concurrent runs share it. Line 2, `checked <input hash> <image ID> <epoch>`, holds the
  last successful upstream check, which the refresh window uses. A failed build keeps
  line 2. Older versions read line 1 only and drop line 2 when they write, so the next
  run of this version checks again. ae-ci-exec writes no other per-run record; the
  image ID goes to stderr.
- Concurrency: builds, every read or move of `-current`, and every tag write run under
  `flock ~/.cache/ae-ci-exec/locks/image-<key>.lock`. image_for takes the same lock.
  A run reads the build generation before it waits for any lock. If a build for the
  key finished while it waited, the run uses that build's image, or shares its
  failure, and does not build again. Runs that start together therefore share one
  build. A run that starts after a build has finished builds again, unless the refresh
  window applies. Input fetching has its own lock, and each kicad-route extraction has
  a lock for its router state. Retention adds `gc.lock` and use locks (below).
- Build failures: each nonzero `docker buildx build` result is retried; there is no
  error classifier. The default is 2 attempts, with one 30 s backoff, when `-current`
  names an image labelled `ae-ci-exec.inputs=<the same hash>`. `-current` may have
  just been seeded from `exec-<key>`. In that case the run has an image to fall back
  to. Otherwise the default is 6 attempts, with backoffs of 30, 60, 120, 240 and
  480 s (15.5 minutes), as in ci-run.sh. `BUILD_ATTEMPTS` overrides both. No limit
  applies to the build itself.
- Fallback: when every attempt fails and that image exists, the run uses it. First it
  prints a warning block on stderr. The block says the run's image was not refreshed
  because the build failed. It gives the build log, the image ID and creation time,
  and the remote ADDs the image may lag. A run that waited for the failed build first
  prints that build's last log lines, then the same warning with the same log.
- No fallback, exit 2 (die): no image for the inputs; the inputs changed during the
  copy; the build gave no image ID, or `-current` does not name it; an image lookup
  failed other than with `No such image`; copying `/opt/kicad-route` out of the image
  failed, or its `install.sh verify` failed.
- No fallback, the failing command's own status (`set -e`, usually 1): other docker
  commands outside the build (tag, create), writes to
  `~/.cache/ae-ci-exec` (on a full disk even the failure record cannot be written),
  git and curl. When `docker run` cannot start the container, the exit is 125.
  native-admit returns 1 for a refused weight and 75 when `AE_CI_MAX_WAIT` runs out.
- kicad-route copies are keyed by the image's router state, at
  `~/.cache/ae-ci-exec/kicad-route/state-<64 hex>` (about 640 MB each). The key is the
  SHA-256 over the hashes of `/opt/kicad-route/manifest.json` (the state manifest that
  `install.sh verify` checks the tree against) and `/opt/kicad-route.install.json`. The
  two small files are read from the image through a created container, without
  extracting the tree, and the key is cached per image ID in `route-key/`. Images with
  the same router state share one copy. A rebuild that changes only later layers, such
  as a new kicad-happy, keeps the router stage's bytes and therefore its copy. Each new
  copy is verified offline with the `install.sh verify` of the image that asked for it.
- `ae-ci-exec --router-copy IMAGE` gives other tools (image_for, the benchmark harness)
  the same copy instead of their own. It ensures the verified copy for IMAGE under the
  same locks, marks the image and the copy used, and prints the copy's path on stdout.
  It takes a native-admit lease like a run, or reuses the caller's lease. The copy is
  then kept for `AE_CI_KEEP_DAYS` after that use and while a container mounts it.
- Retention: every run ends with an eviction pass (`AE_CI_AUTO_GC=0` skips it), and
  `ae-ci-exec --gc` runs one now. image_for.py is to call it after its build, and the
  integrator is switching it and the benchmark harness over. `--gc --dry-run` only
  reports.
  - Images: only repository `agent-ee`, only tags `exec-*` and `run-*`. An image is
    kept while any container uses it (running or stopped), while it is the target of
    `exec-<key>`, `exec-<key>-current` or `run-<key>` for any key, while a run holds it,
    and for `AE_CI_KEEP_DAYS` (default 3) after it was created or last used. Otherwise
    its `exec-*` and `run-*` tags are removed, and Docker deletes the image when no tag
    is left. Other agent-ee tags (`ci-*` and the like) and other repositories are never
    touched. `AE_CI_GC_KEYS` (16-hex keys) limits image eviction to those keys.
  - Router copies, of every layout: kept while a container mounts the copy, while a
    run holds it, and for `AE_CI_KEEP_DAYS` after its last use; otherwise removed.
  - Use markers: each run, and each `--router-copy`, touches
    `used/image/<image id>` and `used/route/<copy>`. Copies made by earlier versions
    (`sha256-<image id>` from 2026-11-03, `<16 hex key>` from before) record no use, so
    their age counts from `.ready`. All `sha256-*` copies date from 2026-11-03, and
    once this version is installed, callers of older versions drain within hours,
    long before those copies reach the 3-day age. A container that mounts a copy
    protects it. The second or so between an older caller's `.ready` check and its
    container start is not protected; the age rule covers that gap in practice.
  - Locks: a run holds `locks/gc.lock` shared from before it resolves its image until
    it holds that image's and its copy's use locks (`use-image-<id>`, `use-route-<key>`).
    It holds the use locks shared until it exits. An eviction pass holds `gc.lock`
    exclusively, and it skips any image or copy whose use or extraction lock it cannot
    take at once. So no pass can remove an image or copy between a run's choice and
    its protection. The pass at the end of a run does not wait for `gc.lock`: it is
    skipped while another run is claiming. `--gc` waits up to `AE_CI_GC_WAIT` seconds
    (default 60). Older versions take no use locks; their containers, the head tags and
    the age rule protect what they use.
  - Each removal, and the bytes freed (copies by `du`, image layers from the Engine
    API's `LayersSize`), go to stderr and to `~/.cache/ae-ci-exec/logs/gc.log`. Nothing
    outside `~/.cache/ae-ci-exec` and no image outside repository `agent-ee` is touched.
  - Bounds with the defaults: per key, the heads plus the images built or used in the
    last 3 days. A key is rechecked at most every 6 hours, so it gains at most 4 images
    a day, about 12 in 3 days. In practice it gains far fewer, because an unchanged
    upstream rebuilds the same image ID. Router copies: one for each router state used
    in the last 3 days, plus those mounted by containers. Heads are not evicted: the
    `exec-<key>` (and `run-<key>`) image of every key ever built stays until someone
    removes those tags.
- Logs: `~/.cache/ae-ci-exec/logs/build-<key>-<stamp>.log` and `logs/gc.log`.
- Signals: INT, TERM and HUP kill the container (`docker kill`) and remove the
  scratch dir. A signal during a build ends the run.

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
