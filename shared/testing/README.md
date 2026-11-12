# Host test workflow

Use **mise** to discover and run a repository's existing tests. Tests and the
agents they launch use the normal host tools, skills, sign-ins and services.
Project test runners and assertions retain their meaning. There is no default
container or replacement agent home.

```sh
mise tasks ls                         # what this project actually provides
mise tasks info test:unit              # command, arguments and source file
mise run test:unit -- <focused-args>    # arguments belong to the existing runner
mise run --output summary test:unit -- <focused-args>
mise run --report-file /absolute/run.json test:unit -- <focused-args>
mise tasks history                    # recent results and timings
mise tasks log test:unit               # retained task output
mise run host:doctor                   # host tools, skill locations, task list
```

Task names and selectors are described by each project's configuration. `test`
is its documented default; `test:unit`, `test:integration`, and `test:agent` name
different kinds of checks where they exist. A successful focused run is not a
full-suite result. Run real-agent tests explicitly, within the task's existing
subscription route and budget. Missing prerequisites and skipped checks are
reported; they are never substitutes for a passing selected check.

## Shared execution, project-owned fixtures

The globally installed `host:exec` task connects mise to the existing
`native-admit` and systemd user scopes. It preserves the caller's environment,
working directory, stdin and output. It creates no accounts or containers.
The default deadline is ten minutes, including a maximum one-minute admission
wait. Explicit deadlines and admission weights are available when a test needs
them:

```sh
mise run host:exec -- --timeout 3m --weight 1 -- python3 -m unittest tests.test_example
HOST_TEST_TIMEOUT=20m mise run test:integration
```

Without `--weight`, native-admit keeps its existing weight and suite-class
inference. The shared task does not reclassify a native suite as a small test.

Each command gets a unique scope. Systemd enforces the deadline and stops the
scope's descendants, including children that start their own process session.
GNU timeout prints a signal diagnostic when the budget expires and returns 124
after TERM, or 137 if it must escalate to KILL three seconds later. A command
can itself return either status: use the signal diagnostic, not the status
alone, to identify a timeout. Admission waiting counts against this budget;
`native-admit: waiting` followed by a timeout can mean the test never started.
Do not treat unavailable host capacity as a code failure. The scope has a
second deadline five seconds later, so abrupt client loss cannot leave its
detached children running indefinitely. Systemd allows ten seconds for its own
graceful stop before the final kill. Cancellation is nonzero (SIGTERM: 143),
and admission refusal is 75 with its reason.
The shared task stops that same scope on success, failure or ordinary interrupt.
If the task client is killed abruptly, the scope's deadline remains enforced.
It never selects other sessions' processes by name or signals a guessed PID.
Processes deliberately launched in another service, Herdr pane or container
belong to that service's lifecycle and are outside this scope.
Mise's own timeout is useful for ordinary tasks but can wait on a detached child
holding an output pipe open; use `host:exec` for process-spawning test harnesses.

Only test resources should be disposable: use pytest's `tmp_path` and
`monkeypatch`, unittest's `TemporaryDirectory` and `mock.patch.dict`, existing
per-run database fixtures, and ports allocated by binding to port zero. Keep
the agent's real `HOME` and authentication. Application state can point to a
fixture directory using that application's own configuration. This workflow
does not intercept writes to live stores; tests must select their test stores.

## Add a project once

Add a small `mise.toml` around the command the project already documents:

```toml
[tasks."test:unit"]
description = "Run the existing focused unittest checks; accepts module names"
run = "mise run host:exec -- python3 -m unittest"
```

Define an appropriate default or require selectors when the existing runner
would otherwise run no tests. Preserve project prerequisites, `load_tests`
hooks, native harnesses, and existing Make targets. Verify a representative
run through both commands before changing the documented entry point.
Use mise's existing `[tools]`, `[env]`, task templates, locks and includes when
a project needs them; do not write another version manager or task scheduler.
Tasks that only invoke existing tools need no shell activation or global tool
configuration. Review/trust a specific project config when it introduces
environment or tool setup; do not trust every future repository globally.

New projects reuse `host:exec` automatically through global task discovery.
A lifecycle fix goes here once, then the installer updates all callers. A
test-specific fixture stays in its repository until another real consumer
needs it. The `test-workflow` skill supplies the same guidance to agents.

## Install and verify

```sh
python3 shared/testing/install.py
python3 shared/testing/install.py --check
mise run test:host
```

The installer uses mise **2026.11.7** for Linux x86_64, verified against the
upstream release checksum. It installs the binary at `~/.local/bin/mise` and
the two global tasks at `~/.config/mise/tasks/host/{exec,doctor}`. Other global
tasks, shell setup and tool versions remain owned by their existing config.
It adds one managed testing-workflow section to existing Codex, Claude and Agy
global instruction files, retaining their other instructions and backing up
each original under `~/.cache/host-testing/instruction-backups`.
The optional `--archive` argument uses an already-downloaded, checksum-verified
release. Previous mise binaries are retained under `~/.cache/host-testing`.
The real lifecycle checks acquire capacity before their deliberately short
deadlines. They preserve the admission file descriptor in child probes, as
required by native-admit's existing lease contract.
To roll back tasks, reinstall this directory from the previous infra revision.

Upstream: [mise tasks](https://mise.jdx.dev/tasks/),
[global discovery](https://mise.jdx.dev/tasks/task-discovery.html),
[2026.11.7 release](https://github.com/jdx/mise/releases/tag/v2026.11.7).
