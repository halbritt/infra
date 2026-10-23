# fome-mc pinned runtime (`fome-runtime:d96f8e00`) on talos and proximal

agent-521 asked (2026-10-23) for talos to be qualified for FUTURE fome-mc and
qualified-runtime work. agent-449 dispatches; this directory only provides the
environment.

talos runs Ubuntu 26.04 with Python 3.14.4, no uv and no Python 3.12. fome-mc
pins Ubuntu 24.04: KiCad `10.0.7~ubuntu24.04.1`, Python 3.12, and pcbnew/wx
4.2.1 at a matching ABI. So the environment is a container. The host Python
and packages are untouched.

| Piece | What |
|---|---|
| Base | the qualified agent-ee image `agent-ee:ee466-gate-b29cead1`, config digest `sha256:d96f8e00a50a1bb6fab119ac8973a083af9373e2c9c235f3df20f655cfc3b5b7` (proximal's image ID). talos's containerd image store reports it as `sha256:9724a2d0…` (its manifest digest). `docker save` on talos shows Config `d96f8e00…` and the same 15 layers. Copied from proximal with `docker save \| ssh talos docker load` (147 s). |
| [Dockerfile](Dockerfile) | `FROM` the base, plus the exact apt pins the base lacks (`mupdf-tools=1.23.10+ds1-1build3`, `librsvg2-bin=2.58.0+dfsg-1ubuntu0.1`, `ghostscript=10.02.1~dfsg1-0ubuntu7.9`, held), plus `make`, plus `uv` 0.13.4 (proximal's binary). Same Ubuntu snapshot, `20261015T000000Z`. |
| [build.sh](build.sh) | builds `fome-runtime:d96f8e00` on talos. Refuses unless the base is the qualified image (either store's ID and the exact layer-list digest) and uv's sha256 matches. Built 2026-10-23: image `sha256:6c724d65…`, config `sha256:ab569ec0…`. |
| [observe-router.sh](observe-router.sh), [router-identity-check.sh](router-identity-check.sh) | readiness 1: kicad-route identities inside the base image under native-admit (class test w1). Compares each identity with its qualified value and exits non-zero on any mismatch or verify failure |
| [fome-qualify.sh](fome-qualify.sh) | readiness 2: one native-admit lease per step: bootstrap test w1, doctor test w1, smoke suite w2. Stops at the first failure and exits with its status; logs and `.rc` kept |

Isolated managed checkouts on talos live in `~/.cache/fome-qualify/`. The
container sees them as `/work` (HOME `/work/home`):

| Checkout | Commit |
|---|---|
| `fome-mc` | `77ef193d3aed850bf275143f2f7c6ad60799c720` (origin/main) |
| `kicad-libraries` | `ab9c5f8a1517a04b9cada6880d67d190bfd48c05` (proximal's) |
| `home/git/Polygonus-Universal-112` | `ddcf0f77fecf3ea7f093954ce1becb7c4a26e970`, `fome-kicad-libs` submodule uninitialised, as on proximal |

`toolchain/.venv` was built inside the container by fome-mc's own bootstrap,
so it is only valid there. talos's old `~/git/fome-mc` (8c42f2e) is untouched.

## Status: accepted (agent-521, 2026-10-23, infra d066270)

agent-521 accepted the environment and wrapper readiness. The installed
script hashes on talos match the repo. agent-449 may schedule FUTURE fome-mc
and exact-`d96f8e00` qualified-runtime lanes on talos, provided each lane uses:

- the explicit class and weight from the table below;
- its own checkout with an in-container bootstrap;
- an immutable identity for that lane.

Attempts already running stay where they are, with no replay. This acceptance
covers the environment only. It does not cover the missing K91 producer at
b577, qualify a different router extension, imply board acceptance, or widen
GCP use.

## Readiness results (2026-10-23)

1. **Qualified image and router identity (talos, inside `d96f8e00`).**
   - PID 1 is tini.
   - kicad-route `b5774496d8466b67ffa0362b6665fee2108155a3`, clean.
   - Extension `grid_router.so` sha256 `ec5fb733d321343456917b2925ec275af233e3a44d34b2f332800d51352b2cd9`,
     computed live and equal to the manifest.
   - Source `9cfc5d5e9369…` (`owned-9cfc5d5e9369`, the manifest value), backed
     by the image's `install.sh verify` PASS.
   - Interpreter `/usr/bin/python3.12` 3.12.3 via `.venv-krt`.
   - `grid_router` 0.23.1 imports.
2. **fome-mc pinned environment (talos, in `fome-runtime:d96f8e00`).**
   - Bootstrap installed the venv matching `uv.lock` (KiBot 1.9.1, KiAuto
     2.3.10), kicad-happy `06840467`, and skills.
   - `make doctor`: **PASS, 54 checks, 0 required failures**. That covers
     every apt pin, pcbnew 10.0.7 = kicad-cli, wx 4.2.1 and the FOME library
     pin.
   - `make smoke`: **18 passed** in 103 s, `--network none`.
   - The first run failed only because the Universal-112 donor repo was not
     staged (2 doctor failures, and 1 smoke test that checks doctor); logs
     are kept in `run1/`.

Not run, and not claimed: the full production suite, pod regeneration, real
routing and renders.

## Invocation (for agent-449)

Pass an explicit admission class and weight for the target: `native-admit`
only recognizes `strict_suite` and `ci-run.sh` by itself, so a bare
`--weight 1` would run aggregate work as class `test`, past `max_suites` 1.

| Target kind | Examples | `--class` / `--weight` |
|---|---|---|
| Aggregate (multi-step suites, pytest) | `smoke`, `check`, `export`, `analyze`, `baseline`, `verify-io`, `fab-package`, `verify-fab-package` | `suite` / `2` |
| Single native step | `doctor`, `erc`, `drc`, `netlist`, `simulate` | `test` / `1` |

KiCad steps are multi-threaded, so a suite weighs 2 and gets 6 CPUs at
talos's 3 per unit. Raise the weight (at most 4) only for real parallel work.

```sh
ssh talos 'Q=~/.cache/fome-qualify; ~/.local/bin/native-admit run --label "<lane>" --class <suite|test> --weight <2|1> -- sh -c "
  exec docker run --rm --network none --label native-admission.lease=\$NATIVE_ADMISSION_LEASE \
    --cpus \$NATIVE_ADMISSION_CPUS --pids-limit \$NATIVE_ADMISSION_PIDS --user \$(id -u):\$(id -g) \
    -e HOME=/work/home -e FOME_KICAD_LIBS=/work/kicad-libraries -v \$Q:/work -w /work/<checkout> \
    fome-runtime:d96f8e00 make <target> [PROJECT=… REV=…]"'
```

The exit status is make's, through `exec` and `native-admit`. `fome-qualify.sh`
(one lease per step, stops at the first failure and exits with its status)
and `observe-router.sh` (exits non-zero if any identity check in
[router-identity-check.sh](router-identity-check.sh) fails) are the
reference wrappers.

Each lane should use its own fome-mc worktree or checkout under `$Q` at its
own commit, rather than the shared `fome-mc` used for qualification. The venv
must be rebuilt in-container once per checkout (`bash toolchain/bootstrap.sh
--no-apt`, which needs network).

## Wrapper corrections (agent-521 review, 2026-10-23)

- `fome-qualify.sh` and `observe-router.sh` used to exit 0 after a failed
  step or identity check, and smoke ran as class `test`. Both are fixed.
- Evidence in `evidence-20261022/talos-fome-wrapper-fixes/`:
  - fake docker: all pass gives exit 0; doctor failing gives exit 3 with smoke
    not run; smoke failing gives exit 3; leases run as test/test/suite with
    weights 1/1/2;
  - fake kicad-route tree: every mismatched identity is a FAIL, exit 1;
  - real image on talos: PASS exits 0; with `install.sh verify` forced to
    fail, exit 1.
- The accepted readiness logs are unchanged (`logs/`, `logs/run1/`).

## proximal lane (2026-10-23, agent-449 request)

Since 2026-10-22, infra's update-bot has kept proximal's host
ghostscript/poppler on current Ubuntu security releases (7.10 / 9.11), so
fome-mc's pinned `make doctor` fails on the host. The disposition (agent-449,
cc agent-521) is a container lane identical to talos's. No host package change,
no apt hold, no update-bot exclusion, no GCP.

- **Image.** `./build.sh proximal` builds `fome-runtime:d96f8e00` from the
  same Dockerfile, on proximal's local base `agent-ee:ee466-gate-b29cead1`.
  That base has ID/config `d96f8e00…` and layer-list `940e0e6f…`. The built
  image is ID and config `sha256:3d57118c47f35c24fe42af03d100e0167ba2ec0cf57d3827f14783905db4559c`
  (proximal's store is classic). Its packages are identical to talos's:
  ghostscript `10.02.1~dfsg1-0ubuntu7.9`, poppler-utils `24.02.0-1ubuntu9.10`,
  mupdf-tools `1.23.10+ds1-1build3`, librsvg2-bin `2.58.0+dfsg-1ubuntu0.1`,
  kicad `10.0.7~ubuntu24.04.1`, ngspice `42+ds-3build1`, wx `4.2.1`, uv
  0.13.4. Builds are not byte-reproducible, so talos's ID differs.
- **Checkouts.** `~/.cache/fome-qualify/` on proximal, at the same commits as
  talos: fome-mc `77ef193d…`, kicad-libraries `ab9c5f8a…`,
  Polygonus-Universal-112 `ddcf0f77…`.
- **Readiness.** One run of `fome-qualify.sh` (per-step leases: bootstrap test
  w1, doctor test w1, smoke suite w2):
  - bootstrap rc 0;
  - `make doctor` PASS, 54 checks, 0 required failures;
  - `make smoke` 18 passed in 54.6 s;
  - "all steps passed".

  Evidence: `proximal:~/.local/share/infra/native-admission/evidence-20261022/proximal-fome-qualification/`.
- **Invocation on proximal.** The same as talos without the `ssh`. The class
  and weight table above applies:

```sh
Q=~/.cache/fome-qualify; ~/.local/bin/native-admit run --label "<lane>" --class <suite|test> --weight <2|1> -- sh -c "
  exec docker run --rm --network none --label native-admission.lease=\$NATIVE_ADMISSION_LEASE \
    --cpus \$NATIVE_ADMISSION_CPUS --pids-limit \$NATIVE_ADMISSION_PIDS --user \$(id -u):\$(id -g) \
    -e HOME=/work/home -e FOME_KICAD_LIBS=/work/kicad-libraries -v \$Q:/work -w /work/<checkout> \
    fome-runtime:d96f8e00 make <target> [PROJECT=… REV=…]"
```

Once agent-521 accepts it, agent-449 moves `integration/fome-gate.sh` and the
fome templates to this lane, and host fome runs on proximal stop counting as
qualified.

`fome-qualify.sh` changed once more on 2026-10-23: its lease label is now
`fome-qual <host> <step> d96f8e00` instead of `talos-qual …`. It is
`aa6fd9a2a2761a88…`, installed identically on talos and proximal. Only the
label differs from the accepted `3281dea8…`.
