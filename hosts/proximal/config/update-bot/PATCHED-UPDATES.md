# Updating carried patches

The owner rejected patch-preservation as a standing hold on 2026-09-28. Prepare
and test a successor; keep activation separate from preparation. A conflict or
failed check is evidence to investigate, not permission to discard the patch.

## Installed generations, 2026-09-28

| Target | Installed for new launches | Preserved runtime | Provenance |
| --- | --- | --- | --- |
| Hermes | Upstream `79a6fd3e996b8677658cade73963f9f596a044c9` plus port `9b57ee21af407efc17478deb120dd78cfaceadba`; Python 3.14.6 | Existing CLI continues using `~/.hermes/hermes-agent` at `9904fd411587` and Python 3.11.15 | `/var/lib/update-bot/hermes-installed.json`; [patch](patches/hermes.patch) |
| OpenCode | `1.18.33+cairn.9797966`; upstream tag commit `51ef4be1d3c122f18fefb510dca8d778571f4f18` | Atomic ELF replacement; no restart | `/var/lib/update-bot/opencode-installed.json`; [patches](patches/opencode.patch) |

Hermes's installed generation is `/var/lib/update-bot/staging/hermes-carry`,
selected by `~/.local/bin/hermes`. Despite the directory name, it is now an
installed generation: **do not reuse, mutate or clean it as staging scratch**.
Its source and venv must remain available while consumers use them. The old
checkout is also still in use by the separate interactive CLI. Prepare subsequent generations at distinct paths.
The gateway now selects the versioned launcher through
`~/.config/systemd/user/hermes-gateway.service.d/50-generation.conf` (canonical
`config/hermes/gateway-generation.conf`). Native reversible drain produced a
fresh matching-PID status with zero chat/cron/API work before SIGUSR1. New gateway
PID 785678 reports source `9b57ee21`, running and Slack connected; the marker was
removed. Receipt: `/var/lib/update-bot/hermes-gateway-activation.json`.
The unit's pre-existing ExecStopPost cleanup still uses the old venv; retain it
until that dependency is explicitly migrated.

The maintenance model still cannot write the gateway profile or reach the user
service manager. A fixed root-owned helper, `update-bot-hermes-activate.service`,
runs as the owner and exposes only this native activation procedure. Polkit permits
starting this unit, not arbitrary user-manager commands. It uses the frozen native
drain API, verifies the selected source/launcher against the installed receipt,
requires fresh matching-PID zero-work status, reloads once and verifies the new
source/PID/Slack state. Busy or uncertain state refuses activation. It releases
only its own drain, records failure, and never force-kills or automatically retries.
The generic operation envelope records intent/outcome and retains the host lock
while this separately managed helper drains.

OpenCode's installed ELF is
`~/.npm-global/lib/node_modules/opencode-ai/bin/opencode.exe`; SHA-256
`6ab47df20cf7877d29b722be593b4c26c3ee2c2d9cb3e6a4737710bb99df3fa9`.
The npm wrapper metadata still says 1.18.32. Check the actual binary version and
hash instead of treating that metadata as the installed native build.
Source/build evidence remains at `/var/lib/update-bot/staging/opencode-1.18.33`.

## Procedure and preservation boundaries

1. Verify launcher, executable, source revision, dependency environment and active
   consumers separately. Read the installed receipts and check their hashes.
2. Fetch upstream in an isolated clone through the operation envelope. Establish
   a real ancestor and enumerate local changes; a shallow boundary can make an
   upstream commit appear local. In this case Hermes `13f4cfebf` was already
   upstream; only `b8ae93b03`, `2c6121992`, `131e95b31`, `9904fd411` were local.
3. Carry the local behavior onto current entry points. OpenCode's three patches
   applied cleanly. Hermes's CLI loop, chat, approval context and turn facade had
   moved; the port follows those modules instead of restoring the old monolith.
4. Test before activation. Preserve exact session/request/turn ownership,
   cancellation fencing, serialized queued delivery, typed drafts, upstream
   voice/seeded-input routing, process ownership and approval context. A callback
   or version probe alone is not enough. Keep failures and subsequent repair
   evidence rather than replacing the failed receipt.
5. Install a verified binary atomically, or select a versioned source/venv for
   new processes. Keep the former executable, source and dependency environment
   for existing consumers and rollback. Never change lazy-loaded files beneath
   an active interpreter. Restarting a gateway is a separate operation with a
   fresh activity check and a native drain plan; do not infer idle from uptime
   or an old `gateway_state.json` snapshot.
6. Save exact candidate location, upstream/local pins, tests, result, activation
   state and remaining operation in Cairn. Resume that work next run. A repeated
   generic “preserve patches” entry does not satisfy the maintenance mandate.

Do not run the unmodified old `hermes update` against the patched `main` checkout:
its same-branch divergence path uses `git reset --hard origin/main`, which would
remove these local commits. Native updater behavior must be read again when the
installation model changes.

## Reproducing the checks

OpenCode used Bun 1.3.14, `bun install --frozen-lockfile`, package typecheck, and
these tests from `packages/opencode`:

```sh
bun test test/session/admission.test.ts test/project/instance.test.ts \
  test/server/httpapi-session.test.ts test/session/prompt.test.ts --timeout 30000
OPENCODE_VERSION=1.18.33+cairn.9797966 OPENCODE_CHANNEL=latest \
  bun run script/build.ts --single --skip-install
```

The resulting ELF also passed Cairn's `scripts.test_opencode_queue` using
`OPENCODE_TEST_BINARY` to select that exact artifact.

Hermes dependencies were built in its isolated `.venv` with
`uv sync --frozen --group dev --group test --extra slack`. Native verification used:

```sh
HERMES_PYTHON="$PWD/.venv/bin/python" scripts/run_tests.sh \
  tests/hermes_cli/test_cli_queue_message.py tests/agent/test_turn_context.py \
  tests/tools/test_process_registry.py tests/hermes_cli/test_plugins.py
```

Cairn compatibility commit `d08bba3` changes the abort-response wait from four to
30 seconds, preserving uncertainty and no-replay behavior. New Hermes uses two
process-tree shutdown grace windows that can exceed four seconds. The fixture
also follows current TUI/logging/scratch APIs and the selected checkout's venv.
Both old and new Hermes lanes passed. Only the Python client file was installed;
no Cairn store, API migration, service upgrade or restart was performed.

## Evidence and recovery

Logs and exact receipts are under `/var/lib/update-bot/staging/` and the two
`*-installed.json` files. Backups are under `/var/lib/update-bot/backups/`; their
paths and SHA-256 values are in those receipts. Restore a launcher/client or ELF
by verified atomic replacement. Restoring the launcher affects future launches;
retain each generation while any existing process uses it. Gateway drain, startup identity and Slack connection were verified. A real-model
round trip on the new Hermes runtime was not performed.

The initial broader inventory is `/var/lib/update-bot/inventory-2026-09-28.json`:
1,754 OS package records; global npm, uv Python/tools and pipx metadata; 44 Python
environments and 1,933 library records, including retained/archived environments.
The scan was read-only, bounded to documented roots and depth five, and did not
establish latest versions or approval to rewrite project lockfiles. It excludes
remote hosts, containers and exhaustive system/user site-package discovery.
Recurring agents recall this dated inventory and perform broader rediscovery at
least weekly; the named update priorities do not define discovery's boundary.
