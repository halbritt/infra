# Shared development skills and tools

The owner requested deployment to Talos on 2026-11-17 after the proximal
implementation. These are user-level development commands for `halbritt`.
They do not add a service or restore Talos's retired agent-ee worker role.

| Canonical source on Talos | Installed consumer |
| --- | --- |
| `~/git/skillpack/skills/` | Harness skill directories managed by `~/git/skillpack/install.sh` |
| `~/git/infra/shared/development/development_evidence.py` | `~/.local/bin/development-evidence` |
| `~/git/cairn/scripts/development_checkpoint.py` | `~/.local/bin/cairn-development-checkpoint` |
| `~/git/cairn/scripts/git_trunk_tools.py` | Existing `~/.local/bin/git-land` and `git-wt` wrappers |

The evidence contract and limitations belong to
[`shared/development`](../../../../shared/development/README.md). Checkpoint and
landing contracts are in the Cairn checkout's `docs/development-checkpoints.md`
and `docs/git-integration.md`. Skill instructions remain in skillpack.

After updating clean source checkouts by fast-forward, install and check:

```sh
cd ~/git/skillpack
./install.sh
./install.sh --check
python3 ~/git/infra/shared/development/install.py
python3 ~/git/infra/shared/development/install.py --check
python3 ~/git/cairn/scripts/install-development-checkpoint.py
python3 ~/git/cairn/scripts/install-development-checkpoint.py --check
git-land --help
```

The two Python installers copy canonical bytes to their command paths. The Git
wrappers execute the canonical Cairn source directly. `git-land --evidence PATH`
is advisory: evidence freshness does not replace existing checks or decide
acceptance. Checkpoint status verifies selected references and does not accept
the task or reconcile side effects. Exact Cairn source references need an existing
authorized connection; this deployment does not provision a Cairn profile.
