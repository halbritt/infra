# CalculiX on proximal

The owner requested command-line feasibility verification and installation on
2026-11-04. CalculiX supports unattended preparation, solving, and postprocessing:
`ccx` consumes an Abaqus-style text input deck; `cgx` executes command files for
geometry, meshing, result selection, and image export. CGX still initializes
OpenGL/X even with `-bg`, so use the existing Xvfb for unattended runs.

## Active installation

On 2026-11-22 the owner requested the current upstream release. The default commands
`/usr/local/bin/{ccx,cgx}` resolve through `/opt/calculix/current` to
`/opt/calculix/2.23/bin/`. Both run on the CPU. Ubuntu still supplies 2.21
in `/usr/bin`; APT updates those packages independently. Check command resolution
with `type -a ccx cgx`. For the upstream version, see the [authors' release page](https://www.dhondt.de/).

CGX is the official x86-64 Linux binary. The upstream CCX executable requires
`libgfortran.so.4`. Proximal has `libgfortran.so.5`, so CCX was built from the
2.23 release source using Ubuntu GCC and GFortran 13.4.0 and linked to the host's
SPOOLES 2.2-16, ARPACK 3.9.1-6build1, LAPACK and BLAS 3.12.1-7ubuntu1.
The build extracted matching Ubuntu SPOOLES development headers into its workspace.

### Rebuild the 2.23 tools

Run these commands in Bash as an ordinary user. Use the CLI checks below with the
new `bin` directory first on PATH before selecting the executables on the host.

```bash
set -e
builddir=$(mktemp -d "$HOME/.cache/calculix-build.XXXXXX")
cd "$builddir"
curl -fsSLO https://www.dhondt.de/ccx_2.23.src.tar.bz2
curl -fsSLO https://www.dhondt.de/cgx_2.23.bz2
apt-get download libspooles-dev=2.2-16
sha256sum -c <<'HASHES'
9c88385c10fb04f5dc6c4e98027a51bebdd8aee3920e05190d6c1dd08357d6e7  ccx_2.23.src.tar.bz2
847e625a95eb2db01ebcbef043b6b2d5a1e4a99c2fa8e5d49575ba28e6716404  cgx_2.23.bz2
d6224a523fc4c0731ae6b0bbd2624e66d82fbcef2c8766cf36375a119b7c253b  libspooles-dev_2.2-16_amd64.deb
HASHES
tar xjf ccx_2.23.src.tar.bz2
dpkg-deb -x libspooles-dev_2.2-16_amd64.deb deps
mkdir bin
bzip2 -dc cgx_2.23.bz2 > bin/cgx
chmod 755 bin/cgx
src="$builddir/CalculiX/ccx_2.23/src"
lib=/usr/lib/x86_64-linux-gnu
make -C "$src" -j8 CC=gcc-13 FC=gfortran-13 \
  "CFLAGS=-O2 -I$builddir/deps/usr/include/spooles -DARCH=\"Linux\" -DSPOOLES -DARPACK -DMATRIXSTORAGE -DNETWORKOUT" \
  'FFLAGS=-O2 -cpp -std=legacy' \
  "LIBS=$lib/libspooles.so.2.2 $lib/libarpack.so.2 $lib/liblapack.so.3 $lib/libblas.so.3 -lpthread -lm -lc"
install -m 755 "$src/ccx_2.23" bin/ccx
export PATH="$builddir/bin:$PATH"
```

The verified binaries were installed root-owned under `/opt/calculix/2.23/bin`.
The relative `current -> 2.23` link selects the release for both command links.
For a rollback to Ubuntu, use `/usr/bin/ccx` and `/usr/bin/cgx` directly, or
remove the two local command links to restore that selection on PATH.

Verification on 2026-11-22 used the default command paths in a fresh directory.
CGX generated 27 nodes and eight C3D8 elements. CCX finished the tension solve.
All eight nodal displacement vectors and all eight integration-point stress tensors
matched the analytical values within output precision. CGX read the FRD and
exported a 784 × 672 stress PNG. Build log, installed executable hashes, solve
outputs and PNG are in `~/.local/state/calculix-2.23-20261122.BeMcxx/`.

## Original Ubuntu installation (2026-11-04)

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
