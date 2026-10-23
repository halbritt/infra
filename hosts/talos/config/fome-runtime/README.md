# fome-mc pinned runtime on talos (`fome-runtime:d96f8e00`)

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
| [observe-router.sh](observe-router.sh) | readiness 1: kicad-route identities inside the base image, under native-admit |
| [fome-qualify.sh](fome-qualify.sh) | readiness 2: fome-mc `bootstrap.sh --no-apt`, `make doctor`, `make smoke` in the runtime, under native-admit |

Isolated managed checkouts on talos live in `~/.cache/fome-qualify/`. The
container sees them as `/work` (HOME `/work/home`):

| Checkout | Commit |
|---|---|
| `fome-mc` | `77ef193d3aed850bf275143f2f7c6ad60799c720` (origin/main) |
| `kicad-libraries` | `ab9c5f8a1517a04b9cada6880d67d190bfd48c05` (proximal's) |
| `home/git/Polygonus-Universal-112` | `ddcf0f77fecf3ea7f093954ce1becb7c4a26e970`, `fome-kicad-libs` submodule uninitialised, as on proximal |

`toolchain/.venv` was built inside the container by fome-mc's own bootstrap,
so it is only valid there. talos's old `~/git/fome-mc` (8c42f2e) is untouched.

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

```sh
ssh talos 'Q=~/.cache/fome-qualify; ~/.local/bin/native-admit run --label "<lane>" --weight 1 -- sh -c "
  docker run --rm --network none --label native-admission.lease=\$NATIVE_ADMISSION_LEASE \
    --cpus \$NATIVE_ADMISSION_CPUS --pids-limit \$NATIVE_ADMISSION_PIDS --user \$(id -u):\$(id -g) \
    -e HOME=/work/home -e FOME_KICAD_LIBS=/work/kicad-libraries -v \$Q:/work -w /work/fome-mc \
    fome-runtime:d96f8e00 make <target> [PROJECT=… REV=…]"'
```

Each lane should use its own fome-mc worktree or checkout under `$Q` at its
own commit, rather than the shared `fome-mc` used for qualification. The venv
must be rebuilt in-container once per checkout (`bash toolchain/bootstrap.sh
--no-apt`, which needs network).
