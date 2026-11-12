# Shared host testing

Owner authorized deployment on 2026-11-11 after rejecting a container-first
plan: test agents need the normal host tools, skills, authentication and local
services. The deployed workflow uses upstream mise for task discovery, execution
and reports, plus existing native-admit and systemd user scopes for bounded
host execution. It adds no persistent daemon.

Canonical source and operating instructions:
[`shared/testing`](../../../../shared/testing/README.md).

| Canonical file | Installed location |
|---|---|
| `shared/testing/install.py` release pin | `~/.local/bin/mise` |
| `shared/testing/tasks/host/exec` | `~/.config/mise/tasks/host/exec` |
| `shared/testing/tasks/host/doctor` | `~/.config/mise/tasks/host/doctor` |
| skillpack `skills/test-workflow` | Each harness's existing skillpack deployment |
| `shared/testing/agent-instructions.md` | Managed section in existing Codex/Claude/Agy global instructions |

Project-specific task files remain in their repositories. Normal host runs
preserve the real home, tool PATH, subscriptions and service access. Fixtures
remain responsible for selecting disposable application state and databases.
The cgroup scope bounds owned child processes; it is not filesystem isolation.

Install and byte verification are performed using the canonical installer.
Rollback restores the prior mise binary from `~/.cache/host-testing` and runs
the prior infra revision's installer for the global task files.

## Deployment checks, 2026-11-12

Mise 2026.11.7 was installed from the upstream Linux x86_64 release; archive
SHA-256 `3198a5ed5716ca8c17ecfc54521e2769d6cacbf2d13f24f0c2f9706620ec0024`.
The installed binary and both task files are checked by `install.py --check`.
The lifecycle suite exercises real user scopes, literal argument forwarding,
normal home/PATH/cwd, inherited admission, TCP and Unix sockets, command failure,
timeouts, detached children, cancellation, killed clients and concurrent runs.

The stale `~/.local/bin/pytest` launcher imported `_pytest.config._console_main`,
which is absent from the installed pytest 9.0.2. It now points to `/usr/bin/pytest`;
the original bytes are retained at
`~/.cache/host-testing/pytest-before-71454206e0ae15b2181bdabcb7cf96aa67acaa892081be0cd62f4eb06cbb70cc`.
`pytest --version` and `python3 -m pytest --version` agree. No pytest package or
Python interpreter was replaced.
