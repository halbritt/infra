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
ae-ci-exec --hold IMAGE --router -- CMD...  # run CMD while IMAGE and its copy are held (other tools)
ae-ci-exec --router-copy IMAGE   # path of IMAGE's verified kicad-route copy, for other tools
ae-ci-exec --gc [--dry-run]      # evict unused images and copies now (runs do it when they end)
```

## What it reproduces

### Explicit retained native inputs (AGENTEE-622/624)

Install `native-inputs.py` beside `ae-ci-exec`; the runner invokes it with the
host's Python 3.11 or newer. `AE_CI_INPUT_MANIFEST` selects a local
`agent-ee.native-inputs/1` JSON file; when unset the runner reads
`~/.config/agent-ee/native-inputs.json` if present. With a manifest,
`AE_CI_EVIDENCE_DIR` must name a durable absolute directory outside the checkout.
No other host `AGENT_EE_*` variables are passed through implicitly.

The manifest has `schema` and an `inputs` list. Each entry has a unique `name`,
an explicit input `env`, and an absolute host `path`. Use either `files` (the
complete relative-path-to-SHA-256 inventory) or `git: true` (select the current
clean Git commit). `python3 native-inputs.py inventory PATH` describes a
regular-file input. Review the inventory against its historical provenance
before storing it in the durable local manifest; generating hashes alone does
not qualify a receipt. No captures or local input manifests belong in public Git.

Preparation refuses missing, additional, changed or symlinked file inputs and
dirty Git checkouts. Each invocation retains separate input copies under the
evidence root. Git copies have independent objects and remain at their selected
commit. Inputs mount read-only at `/opt/agent-ee-inputs/NAME`; their named
variables point there. The writable `/artifacts` mount covers only that run's
output directory, so it cannot write through another alias of an input snapshot.
`AGENT_EE_RUN_INPUT_RECEIPT` names `/artifacts/native-inputs.json`, which records
the manifest SHA-256, file inventories or clean Git commit/tree, clean agent-ee
source, image and runner digest. Retained snapshots and outputs survive scratch
cleanup. Test success still requires the actual consumer checks.

An input entry can add a nonempty `modules` list to scope its environment
variable to those `test_*` modules. Disjoint module lists can use the same
variable for different exact-byte inputs; overlapping or global aliases refuse
setup. Optional top-level `outputs` entries have `name`, `env` and `modules`.
The producer creates only `/artifacts/modules/MODULE` parents, leaving each
named output leaf absent. Each run has a fresh output root. It emits and mounts
a read-only `agent-ee.module-env/1` mapping through `AGENT_EE_MODULE_ENV`.
The composed strict-suite consumer validates the complete map before dispatch,
then selects the current module's inputs and outputs. The validator lives in
agent-ee `scripts/strict_inputs.py`; its default policy confines input paths to
`/opt/agent-ee-inputs` and outputs to `/artifacts/modules/MODULE`.

The agent-ee container guide includes the four runtime input entries:
`PCBSCHEMAGEN_ROOT`, `AGENT_EE_K91_FINAL_RECEIPT`,
`AGENT_EE_K91_PROTECTED_EXISTING` and `AGENT_EE_K91_PROTECTED_HUMAN`. The source
checkout must be clean before running with this manifest. The existing `ci.yml`
fome-mc/J1 inputs, sandbox options, admission and image-selection rules still apply.

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
| kicad-route pin `5f1c072` in the image at `/opt/kicad-route`, owned by the image user 10001 | The image's own tree, extracted once per tree identity (every entry's path, type, mode, size and content hash) to a caller-owned copy, verified with the `install.sh verify` of the image that asked for it, mounted `:ro` over `/opt/kicad-route` |
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
  The 2026-11-03 cross-review found why the tag must not move: a version before
  d988c8d reads this tag again after releasing its lock, and it mounts a kicad-route
  copy keyed by input hash, extracted from the image the tag named earlier. Moving the
  tag would have put those callers on a new image with an old router copy. That
  transition is over: d988c8d is installed and no older copy runs. The tag is still
  never moved, because image_for and d988c8d read it. Retention removes it only with
  the other heads of a stale key.
- Lookups: "missing" means that Docker answered `No such image: <tag>` for exactly that
  tag. Any other failure of `docker image inspect` aborts the run with exit 2, before
  the tag write the lookup guards, and names the Docker error. Examples are an
  unreachable daemon, a connection reset or a timeout. So a transient daemon error
  never creates, seeds or moves a tag. The second Sol review (finding 1) showed that
  the previous code read every inspect error as "missing". It could then retag
  `exec-<key>` after a successful build.
- One image per run: a run resolves its image once and prints
  `ae-ci-exec: image sha256:<64 hex> (agent-ee:exec-<key>-<12 hex>, built|window|reused|fallback, resolved in N s)`
  on stderr. Tags only find an image. Every later read, extraction, verification and
  container uses the full image ID (`sha256:…`), so a moving tag cannot change what a
  run reads or runs. The never-moved tag keeps the image tagged for retention. Those
  containers show no `agent-ee:` name, so they carry the label `ae-ci-exec=1`, and
  native-admit (from the same change) counts unleased containers by that label too.
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
  a lock for its tree identity. Retention adds `gc.lock` and use locks (below).
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
  failed, the copy's tree identity differs from the image's, or its `install.sh verify`
  failed.
- No fallback, the failing command's own status (`set -e`, usually 1): other docker
  commands outside the build (tag, create), writes to
  `~/.cache/ae-ci-exec` (on a full disk even the failure record cannot be written),
  git and curl. When `docker run` cannot start the container, the exit is 125.
  native-admit returns 1 for a refused weight and 75 when `AE_CI_MAX_WAIT` runs out.
- kicad-route copies are keyed by the tree identity of `/opt/kicad-route` in the
  image, at `~/.cache/ae-ci-exec/kicad-route/tree-<64 hex>` (about 640 MB each). The
  identity is the SHA-256 of a listing of every entry: its path, type, permission bits,
  size, and content SHA-256 or symlink target. mtimes and owners are excluded. One
  container started from the image ID computes it (inside the caller's lease, about
  15,900 entries for today's images), and it is cached per image ID in `tree-id/`.
  Equal identities mean byte-identical trees, so images with the same tree share one
  copy. A rebuild that changes only later layers, such as a new kicad-happy, keeps the
  router stage's bytes and therefore its copy. The second Sol review (finding 4) showed
  why the earlier key, the hashes of the state manifest and the install record, was not
  enough: a file that neither receipt covers (`site-packages/sitecustomize.py`, say)
  changes what runs without changing the key. A new copy must show the image's identity
  on the host before it is published. Then it is verified offline with the
  `install.sh verify` of the image that asked for it. Its `.ready` record holds the
  identity, the entry count, that image and the verify time.
- `ae-ci-exec --hold IMAGE [--router] -- CMD [ARG...]` is the lifetime protocol for
  other tools: image_for.py and the benchmark, review and run_in_image harnesses are
  to run their docker commands under it. It claims IMAGE as a run does: `gc.lock`
  shared before the first lookup, then the image's key lock (from its
  `ae-ci-exec.inputs` label). It holds the image's use lock for CMD's whole life. With
  `--router` it also holds the use lock of the image's verified copy and exports
  `AE_CI_ROUTER_COPY` with its path. It exports `AE_CI_IMAGE_ID`, marks use when it
  starts and when CMD ends, and returns CMD's exit status. CMD inherits the use locks,
  so they last as long as CMD does. `--hold` takes no native-admit lease: run it inside
  the caller's admitted job, which also pays for a copy it may extract.
- `ae-ci-exec --router-copy IMAGE` claims the same way, ensures the verified copy, marks
  it used and prints its path on stdout. It holds nothing once it exits, so a caller
  that keeps using the copy should use `--hold --router` instead. It takes a
  native-admit lease like a run, or reuses the caller's lease.
- Retention: every run ends with an eviction pass (`AE_CI_AUTO_GC=0` skips it), and
  `ae-ci-exec --gc` runs one now. image_for.py is to call it after its build. The
  integrator is switching image_for.py and the harnesses to `--hold`.
  - Images: only repository `agent-ee`, only tags `exec-*` and `run-*`. An image is
    kept while any container uses it (running or stopped), while it is the target of
    `exec-<key>`, `exec-<key>-current` or `run-<key>` for a key in use, while a run or a
    `--hold` holds it, and for `AE_CI_KEEP_DAYS` (default 3) after it was created or
    last used. Just before a removal the pass rereads the image's tags (a tag that
    became a head keeps it). Before each tag it removes, it lists the containers again
    (a container that started using the image keeps it with its remaining tags) and
    checks that the tag still names the image. Otherwise
    its `exec-*` and `run-*` tags are removed, and Docker deletes the image when no tag
    is left. Other agent-ee tags (`ci-*` and the like) and other repositories are never
    touched. `AE_CI_GC_KEYS` (16-hex keys) limits image and head eviction to those keys.
  - Heads: a key with no sign of use within `AE_CI_KEEP_HEAD_DAYS` (default 7) loses
    its heads (`exec-<key>`, `exec-<key>-current`, `run-<key>`). A container (running
    or stopped) that uses one of its images prevents this. So does a build, run or
    `--hold` that holds the key's image lock or the use lock of one of its images. The
    snapshot only preselects a key. The pass then takes the key's lock and reads its
    tags, signs of use, containers and use locks again. Before it removes a head tag, it
    lists the containers again (a container that started using one of the key's images
    keeps the remaining heads) and checks that the tag still names the image it named
    after the lock. Only a key that lost all its heads frees its images for the image
    rule in the same pass. The signs of use
    are the newest use marker of the key's images, its build record `builds/<key>`, and
    its newest build log, `logs/build-<key>-*` of ae-ci-exec or
    `logs/image-for-<key>-*` of image_for. A build counts as a use, because image_for
    and d988c8d write no use markers yet, and without it their keys would lose their
    heads at once. Once the heads are gone, the key's images fall under the image rule
    in the same pass.
  - Router copies (`tree-*`, and the earlier layouts below): kept while a container
    mounts the copy, while a run or `--hold` holds it, and for `AE_CI_KEEP_DAYS` after
    its last use; otherwise removed. The containers are listed again just before each
    removal. Other names in `kicad-route/` are left alone.
  - Use markers: each run, `--hold` and `--router-copy` touches
    `used/image/<image id>` and `used/route/<copy>`. Copies made by earlier versions
    (`sha256-<image id>` from 2026-11-03, `<16 hex key>` from before) record no use, so
    their age counts from `.ready`. All `sha256-*` copies date from 2026-11-03, and
    once this version is installed, callers of older versions drain within hours,
    long before those copies reach the 3-day age. A container that mounts a copy
    protects it. The second or so between an older caller's `.ready` check and its
    container start is not protected; the age rule covers that gap in practice.
  - Locks: a run or `--hold` holds `locks/gc.lock` shared from before it resolves its
    image until it holds that image's and its copy's use locks (`use-image-<id>`,
    `use-tree-<identity>`). It holds the use locks shared until it exits. An eviction
    pass holds `gc.lock`
    exclusively, and it skips any image or copy whose use or extraction lock it cannot
    take at once. So no pass can remove an image or copy between a run's choice and
    its protection. The pass at the end of a run does not wait for `gc.lock`: it is
    skipped while another run is claiming. `--gc` waits up to `AE_CI_GC_WAIT` seconds
    (default 60).
  - Versions: no pass runs while a process runs an ae-ci-exec script whose SHA-256
    differs from the running one. The pass finds them by bash's open script
    descriptor, or by the script path in a waiting native-admit's command line. It
    logs that it skipped and names up to three such processes. Older versions take no
    use locks and have no `--hold`, so eviction waits until they have drained, for
    example the d988c8d callers after installation. The scan runs again after the pass
    takes `gc.lock` (an older caller may start while `--gc` waits for it) and right
    before every tag or copy removal. If another version has appeared, the pass logs
    what it removed so far and abandons the rest. Only a version that starts between
    that last scan and the removal itself is missed. A scan forks only for processes
    with an open script descriptor (0.1 s for 740 processes on proximal; 2.2 s with a
    `readlink` for each). `AE_CI_GC_IGNORE_OLD_VERSIONS=1` runs a pass anyway (it logs the versions it
    found at the start); it is only for tests on private keys (`AE_CI_GC_KEYS`) and a
    private state directory.
  - `--gc --dry-run` reports on stderr what a pass would remove, and whether a pass
    would be skipped now. It takes no lock and writes nothing: no state directory,
    lock file, log or temporary file.
  - Each removal, and the bytes freed (copies by `du`, image layers from the Engine
    API's `LayersSize`), go to stderr and to `~/.cache/ae-ci-exec/logs/gc.log`. Nothing
    outside `~/.cache/ae-ci-exec` and no image outside repository `agent-ee` is touched.
  - Bounds: this is an age policy, not an image-count or disk-size bound. With the
    defaults an image stays while it is a head of a key used in the last 7 days, while
    a container (running or stopped), a `--hold` or a run uses it, and for 3 days after
    it was created or last used. A copy stays while a container mounts it, a run or
    `--hold` holds it, and for 3 days after its last use.
    - Estimate for one producer: with this version as the only builder of a key, it
      checks upstream at most every 6 hours. That gives at most 4 new images a day and
      about 12 in 3 days, and far fewer when upstream did not change, because an
      unchanged upstream rebuilds the same image ID.
    - Not covered by the estimate: image_for and the installed d988c8d build on every
      invocation and can add more images within 3 days. Containers, holds and repeated
      use keep images and copies longer, and a container keeps a key's heads past 7
      days.
    - What it does bound: a key that nothing uses for 7 days loses its heads, and its
      images go once they are 3 days unused. So images no longer accumulate with the
      number of input versions ever built.
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
