# CalculiX on proximal

The owner requested command-line feasibility verification and installation on
2026-11-04. CalculiX supports unattended preparation, solving, and postprocessing:
`ccx` consumes an Abaqus-style text input deck; `cgx` executes command files for
geometry, meshing, result selection, and image export. CGX still initializes
OpenGL/X even with `-bg`, so use the existing Xvfb for unattended runs.

## Installed state

Native Ubuntu 26.04 packages, managed by APT, with no version hold:

- `calculix-ccx` 2.21-1build1 → `/usr/bin/ccx` (CPU/SPOOLES solver).
- `calculix-cgx` 2.21+dfsg-2 → `/usr/bin/cgx`.
- `calculix-cgx-examples` 2.21+dfsg-2 →
  `/usr/share/doc/calculix-cgx-examples/examples/`.
- `imagemagick` / `imagemagick-7.q16` 8:7.1.2.18+dfsg1-1: CGX hardcopy
  invokes `mogrify` and `composite`; without these it fails to finish image export.
- `xvfb` and `xauth` were already installed.

Upstream was 2.23 at installation. Ubuntu's 2.21 packages were selected for native
package maintenance and passed the required workflow. This is not a CUDA or
PaStiX build. There is no daemon, container, network listener, or service unit.

Reinstall using the approved Ubuntu repositories:

```sh
sudo apt-get install --no-remove --no-install-recommends \
  calculix-ccx calculix-cgx calculix-cgx-examples imagemagick xvfb xauth
```

The initial install used the update bot's `/var/lib/update-bot-os/lock` and
`NEEDRESTART_MODE=l`. Nine packages were added across two transactions; no
existing package was upgraded or removed.

## Reproduce the CLI checks

The three fixtures here are canonical examples, not installed executables.
Copy them to a fresh job directory so generated output stays outside Git:

```sh
jobdir=$(mktemp -d "$HOME/.cache/calculix-check.XXXXXX")
cp /home/halbritt/git/infra/hosts/proximal/config/calculix/{mesh.fbl,tension.inp,post.fbl} "$jobdir/"
cd "$jobdir"
timeout 30 env -u DISPLAY xvfb-run -a cgx -bg mesh.fbl > mesh.log 2>&1
env -u DISPLAY OMP_NUM_THREADS=2 ccx -i tension > solve.log 2>&1
timeout 30 env -u DISPLAY xvfb-run -a cgx -b post.fbl > post.log 2>&1
cat tension.dat
```

- `mesh.fbl` independently constructs a 10 mm cube and exports `all.msh`, with
  27 nodes and eight hexahedral elements. This demonstrates scripted geometry
  and meshing; the analytical solver fixture uses its own explicit one-element mesh.
- `tension.inp` stretches a 10 mm cube with 1000 N, E=210000 MPa, nu=0.3.
  Three symmetry planes prevent rigid motion while allowing Poisson contraction.
  Expected loaded-face X displacement is FL/(EA) = 0.000476190476 mm;
  uniform axial stress is F/A = 10 MPa. `tension.dat` contains text displacement
  and integration-point stress tables; `tension.frd` contains visualization data.
- `post.fbl` reads that FRD, selects axial stress, and exports `stress.png`.
  Use `-b` for rendering; `-bg` suppresses graphics work. End command files with
  `quit`; use `.fbl` rather than `.fbd` to avoid accidental geometry-save overwrite.

Verification on 2026-11-04: all three commands exited 0; all eight nodal
vectors and all eight integration-point stresses matched the analytical solution
within output precision. `stress.png` was rendered and visually inspected.
CGX's nodal stress display reads 9.9996 MPa due to extrapolation precision;
CCX's integration-point result is 10 MPa. Local logs, raw results, and image:
`~/.local/state/calculix-install-20261104/`.

The fixtures verify installation and automation, not a real structure's fitness.
Arbitrary CAD geometry still needs an appropriate mesh, material model, loads,
and boundary conditions. This install does not add an external tetrahedral mesher.

## Primary references

- [CalculiX downloads and release information](https://www.dhondt.de/).
- [Official CGX manual](https://www.dhondt.de/cgx_2.23.pdf), section B.14
  (batch mode), program parameters, and `send`, `ds`, `hcpy`, `quit` commands.
