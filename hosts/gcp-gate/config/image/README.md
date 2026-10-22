# agent-ee-gate image

Scripts that build the `agent-ee-gate` GCE image and run gates on it. The host
README ([`../../README.md`](../../README.md)) describes the image contents,
validation and cost.

| File | Runs on | Purpose |
|---|---|---|
| `build-image.sh [WARM_SHA]` | proximal | Spot builder VM from the latest `ubuntu-2404-lts-amd64`, uploads inputs, runs provision.sh, images the disk into family `agent-ee-gate`, deletes the builder |
| `provision.sh IN_DIR WARM_SHA` | builder (root) | packages, `halbritt`, gate layout, fome-mc and J1 inputs, AppArmor profile, warm `agent-ee:ci-WARM_SHA` build, cleanup, poweroff |
| `run-gate.sh SHA` | proximal | Spot gate VM, `JOBS=8 ./ci-run.sh SHA`, logs to `~/agent-ee-gate-gcp/`, VM deleted |
| `ci-run.sh` | gate VM | byte-identical copy of peecee-wsl `~/agent-ee-gate/ci-run.sh` (sha256 `2c5c20f80838a26e49a21fecce0af5c64a14609ef7cc4d69215c7b4ec3eea3e5`) |

Rebuild when ci-run.sh, ae-ci-exec or the toolchain pins in agent-ee's
Dockerfile change: update the sha256 pins at the top of `build-image.sh`, run
`build-image.sh <current main>`, validate with `REBUILD=1 run-gate.sh <same SHA>`
(expect a build of a few seconds), then delete the superseded image.

```sh
~/git/infra/hosts/gcp-gate/config/image/build-image.sh 14ef7275   # about 15 min
REBUILD=1 ~/git/infra/hosts/gcp-gate/config/image/run-gate.sh 14ef7275
```

The warm context must be extracted with git-archive modes (umask 0002), as an
SSH-staged gate context is; BuildKit's COPY cache key includes file modes.
