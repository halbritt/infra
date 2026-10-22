# kicad-route worker lanes on remote hosts

Owner request 2026-10-22 (via the coordinator): peecee-wsl, archon, talos and
`agent-ee-gate-c4` run kicad-route worker lanes, as they already run agent-ee
lanes. The burndown launcher on proximal starts them with
`launch.py ... --repo /home/halbritt/git/kicad-route --project KICADROUTE --host H`.
The first attempt failed at `git push -q --force peecee-wsl
<sha>:refs/agent-ee-base/<slug>` (exit 128): proximal's `~/git/kicad-route` had no
remote named after the host, and the hosts had no `~/git/kicad-route`.

Unlike agent-ee, kicad-route tests run natively on the host with the system
`/usr/bin/python3` (KiCad's `pcbnew` bindings exist only there), not in the
agent-ee CI image.

## What a `--repo` launch needs on a host

From `launch.py` `prepare()`, for any repository:

- a remote in proximal's checkout named exactly after the host, to which it pushes
  `<base>:refs/agent-ee-base/<slug>` (and best-effort `main`, `stack-next` and
  `wt/*` refs), and from which it fetches the worker branch afterwards;
- `/home/halbritt/git/<repo>` on the host, where `git-wt create <slug>` makes the
  worktree under `~/.cache/agent-worktrees/<repo>/`;
- the paths that agent-ee lanes already use (`git-wt`, the account homes, and
  `/tmp/agent-ee-burndown-20261017/` from `sync_up`).

## Provisioning (2026-10-22, kicad-route main 409d06ab)

proximal `~/git/kicad-route` remotes, same convention as `~/git/agent-ee`:

| Remote | URL |
|---|---|
| `peecee-wsl` | `ssh://peecee-wsl/home/halbritt/git/kicad-route` |
| `archon` | `ssh://archon/home/halbritt/git/kicad-route` |
| `talos` | `ssh://talos/home/halbritt/git/kicad-route` |
| `agent-ee-gate-c4` | `ssh://agent-ee-gate-c4/home/halbritt/git/kicad-route` |

On every host, `~/git/kicad-route` is a normal clone of
`https://github.com/halbritt/kicad-route.git` (the repository is public, so the
hosts need no GitHub credential), with `receive.denyCurrentBranch updateInstead`
as on the agent-ee checkouts. Its `origin/main` is only what `git-wt create`
starts from; launch.py resets each worktree to the pushed base commit.

### Python for the tests (system `python3`, user site)

The suite imports `pcbnew`, `numpy`, `scipy`, `shapely`, `PIL`, `pytest` and
`jsonschema` (`>=4.18`, for `test_interface_contract.py`). proximal has numpy
1.26.4, scipy 1.11.4 and Pillow 10.2.0 from Ubuntu, and pytest 9.1.0, shapely 2.2.0
and jsonschema 4.26.0 in the user site. The user-site packages are pinned to
proximal's versions on every host:
`pip install --user --break-system-packages` with a constraints file of
`pytest==9.1.0 iniconfig==2.3.0 pluggy==1.6.0 shapely==2.2.0 jsonschema==4.26.0
jsonschema-specifications==2025.9.1 referencing==0.37.0 rpds-py==2026.6.3
attrs==26.1.0 typing_extensions==4.16.0`. numpy 1.26.4 and scipy 1.11.4 have no
Python 3.14 builds, so the 3.14 hosts use their distribution's versions.

| Host | python3 | numpy / scipy / Pillow | Added |
|---|---|---|---|
| peecee-wsl | 3.14.4 | 2.3.5 / 1.16.3 / 12.1.1 (apt) | apt `python3-numpy python3-scipy`; user-site pins |
| archon | 3.14.8 | 2.5.4 / 1.18.1 / 13.0.0 (user site) | pip bootstrapped into the user site from the interpreter's bundled wheel (`python3 /usr/lib/python3.14/ensurepip/_bundled/pip-26.2.1-py3-none-any.whl/pip install --user --break-system-packages pip`; ensurepip itself strips `PIP_*` and refuses the externally-managed marker); then `numpy==2.5.4 scipy==1.18.1 pillow==13.0.0` and the pins into the user site. No pacman change (avoids a partial upgrade on a live host) |
| talos | 3.14.4 | 2.3.5 / 1.16.3 / 12.1.1 (apt) | apt `python3-pip python3-numpy python3-scipy build-essential`; user-site pins |
| agent-ee-gate-c4 | 3.12.3 | 1.26.4 / 1.11.4 / 10.2.0 (apt) | apt `python3-pip python3-numpy python3-scipy build-essential`; user-site pins. Same versions as proximal throughout |

### Router runtime (`kicad-route update` in `~/git/kicad-route`)

Routing tests run the owned router in its own venv, selected through the state
manifest. A worktree has no state of its own, so tests point
`KICAD_ROUTE_STATE` at the main checkout (as proximal does):
`KICAD_ROUTE_STATE=/home/halbritt/git/kicad-route`. Without it the routing
tests fail with "backend produced no candidate" (13 failures on proximal).

Each host built its generation with `cd ~/git/kicad-route &&
UV_CONSTRAINT=<file> bin/kicad-route --out build/kicad-route update`, where the
constraints file pins the router venv to proximal's generation:
`numpy==2.5.4 scipy==1.18.1 pillow==13.0.0 shapely==2.2.0`. Each build needs
`uv`, a Rust toolchain and a C linker.

| Host | Generation | Router | Toolchain added |
|---|---|---|---|
| peecee-wsl | `.router-generations/210bdbb4…` | `owned-3c91fe5c0120`, grid_router 0.23.1 | none (rustc 1.99.1, build-essential already present) |
| archon | `.router-generations/42ddddaf…` | same | `/usr/local/bin/uv` → `~/.local/share/mise/installs/uv/latest/uv-x86_64-unknown-linux-gnu/uv`, because kicad-route runs tools with a contained `HOME` and the mise shim then refuses the untrusted config. `~/.bashrc` sources `~/.cargo/env` before the non-interactive return, so `bash -lc` finds the existing rustc 1.99.1 |
| talos | `.router-generations/9148d30a…` | same | rustup, minimal profile, toolchain 1.99.1 (`~/.cargo`; rustup's `. "$HOME/.cargo/env"` hook in `~/.profile` and `~/.bashrc`) |
| agent-ee-gate-c4 | `.router-generations/04f9b4c1…` | same | rustup, minimal profile, toolchain 1.99.1 (hooks as on talos) |

`update` also put Freerouting v2.5.0 in `vendor/freerouting/`, then exited 1 with
"Freerouting needs Java 25+". No host has Java, so the Freerouting backend
(`test_freerouting_*`, `[freerouting]` parameters, the canary) fails there. These
tests also fail for proximal workers that use a scratch state without Freerouting.
The owned (`builtin`/`krt`) router is complete. To add Java later:
`sudo apt install openjdk-25-jre-headless` on the Ubuntu hosts (candidate
25.0.4.1 on both 24.04 and 26.04), then rerun `update`.

## Verification (2026-10-22, origin/main 409d06ab)

On each host: a `git-wt create` worktree under
`~/.cache/agent-worktrees/kicad-route/`, an empty start-marker commit (otherwise
`git-wt gc` collects a clean worktree whose HEAD is in trunk; this happened once
on proximal during the check), then:

```sh
KICAD_ROUTE_STATE=/home/halbritt/git/kicad-route python3 -m pytest \
  tests/test_owned_router.py tests/test_owned_build.py tests/test_routing_closure.py \
  tests/test_engine_acceptance.py tests/test_routing.py::test_krt_round_trip \
  tests/test_routing.py::test_net_name_selection \
  tests/test_routing.py::test_validation_detects_tampering -q -p no:cacheprovider -rs
```

| Host | Result | Exit |
|---|---|---|
| proximal (reference) | 93 passed in 174 s (loaded) | 0 |
| agent-ee-gate-c4 | 93 passed in 42 s | 0 |
| peecee-wsl | 93 passed in 33 s | **139** |
| archon | 93 passed in 38 s | **139** |
| talos | 93 passed in 58 s | **139** |

The worktrees were then removed.

**Python 3.14 hosts: segfault at teardown.** All tests pass, but on all three
3.14 hosts `pytest` segfaults afterwards. The crash happens in the final garbage
collection, in `_pytest/unraisableexception.py` `gc_collect_harder`
(`pytest_unconfigure`), with `_pcbnew` the only extension module loaded. With
`-p no:unraisableexception` it still segfaults, at interpreter exit. The trigger
is `test_routing.py::test_validation_detects_tampering`, which loads, edits and
saves a board in-process. Every other selected test exits 0 on its own. A
standalone script running the same pcbnew edits exits 0, so the trigger is not
fully isolated. Consequences for workers on these hosts:

- When stdout is a pipe, pytest's summary line is lost (the buffer is not
  flushed before the crash). `-p no:unraisableexception` (or
  `PYTHONUNBUFFERED=1`) keeps the summary.
- An exit status of 139 after a printed all-pass summary is this host artifact,
  not a test failure. agent-ee-gate-c4 (Python 3.12, like proximal) exits 0.

## Launcher dry check

For each host, from proximal's `~/git/kicad-route`:
`git push -q --force H <main sha>:refs/agent-ee-base/test` exited 0, the host
resolved the ref to `409d06ab`, and `git push -q H :refs/agent-ee-base/test`
deleted it. No refs were left under `refs/agent-ee-base/`, and no worker was
launched.

launch.py has one gap in `--repo` mode. Its second push combines
`main:refs/agent-ee-base/main` with
`<agent-ee stack-next tip>:refs/agent-ee-base/stack-next`, but `WT_HOME` is fixed
to the agent-ee worktree root. In kicad-route that tip is an agent-ee commit,
which does not exist in the repository. The push is `check=False`, so the launch
continues, but kicad-route's `refs/agent-ee-base/main` may not be updated on the
host.
