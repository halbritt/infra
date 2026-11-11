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

The API and scheduling services retain their existing binaries and native behavior.
No source rebuild, migration-version change, token provisioning, or session
re-registration is part of this relocation.

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
