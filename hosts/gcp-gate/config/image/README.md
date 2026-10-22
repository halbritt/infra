# agent-ee-gate image

Scripts that build the `agent-ee-gate` GCE image and run gates on it. The host
README ([`../../README.md`](../../README.md)) describes the image contents,
validation and cost.

| File | Runs on | Purpose |
|---|---|---|
| `build-image.sh [WARM_SHA]` | proximal | Spot builder VM from the latest `ubuntu-2404-lts-amd64`, uploads inputs, runs provision.sh, images the disk into family `agent-ee-gate`, deletes the builder |
| `provision.sh IN_DIR WARM_SHA` | builder (root) | packages, `halbritt`, gate layout, fome-mc and J1 inputs, AppArmor profile, warm `agent-ee:ci-WARM_SHA` build, cleanup, poweroff |
| `run-gate.sh SHA` | proximal | Spot gate VM, `JOBS=8 ./ci-run.sh SHA`, logs to `~/agent-ee-gate-gcp/`, VM deleted |
| `ci-run.sh` | gate VM | the copy at peecee-wsl and agent-ee-gate-c4 `~/agent-ee-gate/ci-run.sh` (sha256 `edc1fe8a4a43d71357280eb9f8d486ca65b660fcec266f37f2f38ae723e63678` since 2026-10-22, when the strict-suite container gained the admission lease label, CPU/PID bounds and `--init` for pre-tini images; the current image still holds the earlier `2c5c20f8…` without them) |

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
