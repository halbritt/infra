# Cairn consolidated into managed PostgreSQL — 2026-09-29

The owner explicitly requested moving Cairn into the managed cluster. It now uses
its own database `cairn` in Proximal's `17/main` PostgreSQL 17.11 server, with
pgvector 0.8.6. Existing role `halbritt` uses peer authentication and is not a
PostgreSQL superuser. No application binary, token, model, schema migration, or
agent registration was changed.

## Transfer and verification

A staged dump restored successfully into a validation database on the managed
cluster. Cairn's native audit checkpoint verified with no missing or altered
members, and all indexes were valid. No ordinary consumers used the staged copy.

Stopped the API, presence watcher, scheduler, and seven wake-worker daemons.
Their worker cgroups contained no hosted coding-agent children. With no remaining
source clients, created the final native checkpoint, made the source database
read-only, and captured a dump plus every table/sequence fingerprint. Stopped
the old server before creating the final managed database.

Restored with `pg_restore --exit-on-error --single-transaction`, preserving object
owners, into a database created from `template0`, UTF8, C locale. Revoked public
CONNECT; existing owner and cluster administrator retain access. Application
tables remain owned by `halbritt`; extensions are managed by the administrator.

Before admitting consumers, **all 77 table hashes matched, covering 7,565,786 rows,
and all seven sequence states matched**. Rows were streamed in primary-key order,
or full-row order for tables without a primary key. No raw table contents entered
logs or this repository. Native checkpoint `6cf5c2da-40c8-412d-b55f-8d36aec1dd28`
verified. No invalid indexes were found; ANALYZE completed before activation.

This transferred the complete current state; it did not rewind history. Authority,
request, agent, and execution identities were retained. `restore-status` reports
unpaused, generation 0. Agent-224 returned online with the same provisioned
agent/execution UUIDs. No re-registration was performed.

All ten Cairn daemon services are active. Native MCP search and CLI API/version
queries work. Archon's existing relay reaches the API successfully. The unchanged
application binary revision is `0f0e4a323824e01554fb301d5105a9f4ef51a5e2`.

## Service configuration and corrected failure

Per-service `CAIRN_DATABASE_URL` selects the managed socket. The old CLI socket
path is now an alias to the same managed server. No production DSN is exported
globally into unrelated test processes. The private store unit is masked; a
retirement marker file at its former data path prevents bootstrap initialization.

The first admission attempt failed because empty `Requires=` and `After=` drop-in
assignments did not remove the dependency on the masked private store. Installed
canonical complete API/scheduler unit files without that dependency, retaining
other settings and the existing semantic/HTTP drop-in. Verified the actual
resulting dependency graph and ran `systemd-analyze --user verify`, then started
services successfully. The failure and manual completion are retained in receipts.

Services were unavailable approximately 08:50:53–08:54:29 PDT. Coding-agent
processes were not stopped. Presence briefly expired and recovered under existing
identities. These checks establish observed operation, not every agent workflow.

## Backup and recovery

After activation, managed pgBackRest differential backup
`20260927-010427F_20260929-085520D` completed with error false. Native backup/archive
checks passed before and after removing the temporary validation database. The
managed backup/WAL schedule now covers Cairn. External run artifacts retain their
independent retention requirements.

Retired physical source: `~/.local/share/cairn/retired-postgres-20260929/data`, with
its former socket directory alongside. This is a retained recovery copy, not a
fallback writer. Switching back after new managed writes would lose those writes;
recovery must preserve the latest state or use Cairn's historical restore/admission
workflow. Do not run `scripts/local-store.sh start/backup` in this production setup.

Private receipts, exact scripts, old units, hashes and checkpoint metadata:
`/var/lib/update-bot/cairn-consolidation-20260929/`.
Final dump SHA-256:
`fb9ffc857e33236679d5b321fd4a43b4e0844216679f794ab9d92bcaa0c649ea`.
The staged backup remains in the existing private backup directory. No retained
production data was deleted. `result.json` records successful completion after
the unit dependency correction; the original script's failed admission is retained.

33 infrastructure tests and the repository validator passed. References:
[PostgreSQL dump/restore](https://www.postgresql.org/docs/17/backup-dump.html),
Cairn `docs/audit-checkpoints.md`, and `docs/restore-admission.md`.

## Bounded design review

Selected concepts: repository-contract-precedence, explicit-invariants, and
minimize-simultaneous-uncertainty. Authority came from the owner's instruction;
doctrine granted none. Preserved data, identities and sole-writer routing were
mandatory gates. Retaining a separate server was rejected by the owner. Native
DSN selection made an application code change unnecessary.

Validated release `d3e0c0d4ccd1920b2e045c156f1cf0db4fc5f04f`, corpus
`corpus-2026-07-12-a11702cc9217`, doctrine `doctrine-f6bbb5196a3f8bf9`.
Packet `pkt-a25f9c2e1687f2cf`, canonical content SHA-256
`a25f9c2e1687f2cf5a7909b9e649021fba0580e6e72f131b32a7e820f8353f54`.
The selected concepts' material obligations were satisfied by owner instruction,
source/service inspection, staged restoration and fail-closed final gates. The
remaining generic obligations below are nonmaterial to this narrow deployment:

- refactoring-change-type-classification: request and authority inventory — Nonmaterial: Authorized deployment migration, not a source refactor.

- refactoring-stop-backtrack-escalate: current diff | failure output — Nonmaterial: The startup failure and correction are recorded above; no unresolved failure remains.

- repository-assessment-metrics-not-performance: No evidence threshold makes individual performance scoring admissible from these signals. | none — Nonmaterial: No individual productivity judgment is made.

- task:legacy-change: evidence-incidents — Nonmaterial: Explicit owner direction supplied the requirement; an incident is not necessary.

- universal-information-hiding: actual caller needs | caller needs and decision owner | decision owner and volatility | leaked knowledge or coordinated change | material cost/failure semantics callers require — Nonmaterial: No new application abstraction or interface.

- universal-local-reasoning: knowledge and navigation required by callers/maintainers | representative change or use scenario | representative change scenario | state, invariant, and dependency ownership — Nonmaterial: No source-module restructuring; host ownership is documented.

- universal-measure-claimed-improvement: representative comparison or replayed motivating scenario | semantic preservation and confound analysis — Nonmaterial: No performance improvement claimed; topology and transfer preservation were verified.

- universal-no-change-option: actual current cost/risk or absence within a stated interval | expected future change from accepted plans | intervention cost and uncertainty | latent security, safety, data, durability, and compatibility check | proc-decide-leave-code-alone — Nonmaterial: Owner selected consolidation after the separate-instance option was identified.

- universal-preserve-behavior-by-default: proc-establish-preservation-boundaries — Nonmaterial: Generic procedure not selected; explicit full-data/session/identity gates supplied the operational contract.

- universal-separate-semantic-structural-change: checkpoint verification | per-edit change classification — Nonmaterial: No application semantic or source-structural change; separate stage, transfer and activation evidence retained.
