# Cairn on managed PostgreSQL

Desired state: Cairn uses database `cairn`, owned by existing role `halbritt`,
on Proximal's managed PostgreSQL `17/main` cluster at `/var/run/postgresql:5432`.
Peer authentication is used; no new password or database superuser role is needed.
All application identities, tokens, API sockets, relay settings, and agent session
identities remain under the existing Cairn home.

## Installed configuration

- `managed-database.conf` is installed as `50-managed-database.conf` beneath the
  user unit drop-in directories for `cairn-api`, `cairn-scheduler`,
  `cairn-presence`, and each of the seven `cairn-wake-worker-NN` services.
- `cairn-api.service` and `cairn-scheduler.service` are installed as the user
  unit base files, without a dependency on the retired private store. Existing
  unrelated drop-ins are retained. Dependency removal requires replacing the base
  unit: empty dependency assignments in drop-ins did not remove those edges.
  User services cannot order against a system-manager unit;
  their existing retry policy handles the system cluster being unavailable.
- The database URL is scoped to these services, not exported globally into
  unrelated processes or disposable tests. Operator CLI commands can explicitly set
  `CAIRN_DATABASE_URL='host=/var/run/postgresql port=5432 dbname=cairn user=halbritt sslmode=disable'`.
- The legacy `~/.local/share/cairn/socket` directory is replaced by a symlink to
  `/var/run/postgresql`. This preserves existing CLI processes' default connection
  path; it leads to the same managed database, not a second server.
- `cairn-store.service` is masked. Its original unit is retained with migration
  evidence. The old `data` directory is archived and a regular-file marker at
  that path prevents the old local bootstrap script from initializing another
  private cluster accidentally. Do not run `scripts/local-store.sh start/backup`.

The relocation itself left the API and scheduling services on their existing
binaries and native behavior.
No source rebuild, migration-version change, token provisioning, or session
re-registration is part of this relocation.

## Runtime, semantic worker, and lifecycle hooks

Since 2026-11-23 (source `ae498426`; see `hosts/proximal/CHANGELOG.md`, 2026-11-23 entries):
- `~/.local/bin/cairn` (API, CLI, scheduler, wake supervisors), `~/.local/bin/cairn-lifecycle` and `~/.local/bin/cairn-stage-lifecycle` are VCS-stamped Go binaries built from `ae498426` (`be9e35d6…`, `881ab664…`, `8577155c…`). The database is unchanged by this deploy.
- `cairn-api.service` uses drop-in `zz-c301-api-rust.conf` to run `~/.local/bin/cairn serve --semantic-rust-config ~/.local/share/cairn/semantic-rust/configs/d6b1b845e456d4e9…/semantic-rust-embed.json ...` with Rust `cairn-semantic-embed` query/document workers from `semantic-rust/payloads/834eda5e…`. The config is a byte-identical, content-addressed copy (since 2026-11-24, w24) of the former `go-rollout-d809e8f3/semantic-rust-embed.json`, so the API no longer depends on any rollout directory.
- `cairn-presence.service` uses drop-in `zz-c301-go-presence.conf` to run `~/.local/bin/cairn-lifecycle coordination watch --config-dir ~/.local/share/cairn/go-rollout-ae498426/watcher-bindings-v3` (since 2026-11-23 22:23; claude-one, claude-two, codex-one and codex-two point at the compact `/3` generations, the others are the v2 files). The `codex-three` and `hermes-one` bindings there are the unchanged `f7bec707` files.
- Claude (`~/.claude`, `~/.claude-harm`), Codex (`~/.codex`, `~/.codex-harm`), Agy (`~/.gemini/config`) and OpenCode (`~/.config/opencode/cairn-lifecycle.json`, `cairn-coordination.json`) hook rows delegate to staged Go launchers of the Go-only generations under `~/.local/share/cairn/go-rollout-ae498426/cohorts/`: `/3` (with `compact_inbox_version: 1`) for claude-one `6f2a5cfd`, claude-two `f131b449` and codex-shared `da06c663` (codex-one, codex-two); `/2` for agy-one and opencode-one, which cannot take compact inbox. The `/2` and `ae498426` /1 generations stay as rollbacks. Codex 3 (`~/.codex-3`, deprecated) and Hermes stay on the `f7bec707` cohorts. Sessions started before a rollout keep their older launchers, so the `f7bec707`, `d809e8f3` and `3f574e89` rollout directories must stay.
- The Python semantic worker (`~/.local/share/cairn/semantic`, `semantic-python-retained`), its `semantic.conf` drop-in, the old `cairn267-distinct-api-4884f6a` unit and the Python presence stages (`deployments/cairn-423-*`, `cairn-424-*`, drop-in `90-cairn423-runtime.conf`) were removed on 2026-11-24 (w25). There is no Python rollback for the API or presence any more; `go-rollout-d809e8f3/revert.sh` no longer touches cairn-api.
- Reverse of the compact `/3` step: `~/.local/share/cairn/go-rollout-ae498426/revert-v3.sh`.
- Reverse of the `/2` step: `~/.local/share/cairn/go-rollout-ae498426/revert-v2.sh`. Reverse of the whole `ae498426` rollout: `~/.local/share/cairn/go-rollout-ae498426/revert.sh` (add `--api` to also return the API binary; get the coordinator's go first).

## Candidate detail retention

Search diagnostics expire after 14 days, by a daily timer. See
[candidate-retention.md](candidate-retention.md) for the decision, operation and
recovery.

## Native coordination hooks

`coordination-entrypoint.py` is installed as the regular executable file
`~/.local/share/cairn/coordination/coordination.py`. It selects the complete
verified bundle at
`~/.local/share/cairn/deployments/codex-interrupt-agent1333-20261108/lifecycle/`.
The native hook commands keep their existing paths and account configurations.
Runtime implementation remains canonical in the Cairn repository; this launcher
records the host's selected deployment.

The selected bundle preserves the previously installed implementation with only
the Codex interruption repair from Cairn commit `86a78e6f`. Interruption updates
presence and returns `{}`, preserving pending inbox work. All three Codex profiles
use this entrypoint. The presence service and pinned inbox memory/bridge bundles
keep their separate deployment paths.

The adjacent old helper files and manifest are retained installation material;
the launcher loads the selected deployment's own manifest and helpers. Do not
replace individual members of a live pinned bundle. See the
[deployment record](codex-interrupt-20261108.md) for verification and rollback.

## Frank / ChatGPT messaging

Frank reaches Cairn through a dedicated private OpenAI tunnel and a supervised
connector inbox. See [configuration, identity and operations](frank-tunnel.md).

## Backup and recovery

The managed cluster's pgBackRest backup/WAL schedule now covers the Cairn database.
Cairn audit checkpoints complement physical backups; they are not substitutes for
full data backups. Run artifacts outside PostgreSQL retain their existing locations
and are not covered by PostgreSQL backups.

The retired data is a retained cutover recovery source, not a live fallback.
After new writes are accepted by the managed database, pointing clients back at
the old copy would lose those writes. Recovery must preserve the latest managed
state or use Cairn's explicit restore/admission workflow for a historical restore.
See `MIGRATION-2026-09-29.md` for execution evidence and retained artifact paths.
