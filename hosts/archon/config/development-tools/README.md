# Shared development skills and tools

The owner requested deployment to Archon on 2026-11-17. These are user-level
development commands for `halbritt`; installation does not require a desktop or
service restart.

| Canonical source | Installed consumer |
| --- | --- |
| `~/git/skillpack/skills/` | Harness skill directories managed by `~/git/skillpack/install.sh` |
| `~/git/infra/shared/development/development_evidence.py` | `~/.local/bin/development-evidence` |
| `~/git/cairn/scripts/development_checkpoint.py` | `~/.local/bin/cairn-development-checkpoint` |
| `~/git/cairn/scripts/git_trunk_tools.py` | `~/.local/lib/git-trunk-tools/git_trunk_tools.py`, used by the existing `git-land` and `git-wt` wrappers |

The evidence contract and limitations belong to
[`shared/development`](../../../../shared/development/README.md). Checkpoint and
landing contracts are in Cairn's `docs/development-checkpoints.md` and
`docs/git-integration.md`. Skill instructions remain in skillpack.

After updating clean source checkouts by fast-forward, install and check:

```sh
cd ~/git/skillpack
./install.sh
./install.sh --check
python3 ~/git/infra/shared/development/install.py
python3 ~/git/infra/shared/development/install.py --check
python3 ~/git/cairn/scripts/install-development-checkpoint.py
python3 ~/git/cairn/scripts/install-development-checkpoint.py --check
install -m 755 ~/git/cairn/scripts/git_trunk_tools.py \
  ~/.local/lib/git-trunk-tools/git_trunk_tools.py
cmp ~/git/cairn/scripts/git_trunk_tools.py \
  ~/.local/lib/git-trunk-tools/git_trunk_tools.py
git-land --help
```

`git-land --evidence PATH` remains advisory. Checkpoint status verifies selected
references, not task acceptance or side effects. Exact Cairn source references
require an existing authorized connection; this deployment does not create a
Cairn profile or change the owner's graphical session.
