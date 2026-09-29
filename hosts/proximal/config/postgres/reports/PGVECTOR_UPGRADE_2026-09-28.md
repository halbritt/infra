# pgvector 0.8.6 — 2026-09-28

The owner approved updating the databases on pgvector 0.8.2, while leaving
`ob1` (unknown application) and the 0.6.0 databases outside this SQL upgrade.
This was an operator-run change under the update-bot host lock, not an expansion
of the daily bot's database authority.

## Result

Installed only `postgresql-17-pgvector` 0.8.2-1.pgdg24.04+1 →
0.8.6-1.pgdg24.04+2 through the existing PGDG apt repository. The simulation
and actual transaction introduced no dependencies or removals. The package hold
was retained. PostgreSQL remains 17.10; its postmaster start time did not change.

Ran `ALTER EXTENSION vector UPDATE TO '0.8.6'` in individual transactions,
with a 3-second lock timeout and 30-second statement timeout, in:

- `engram`
- `hippo`
- `engram_test`
- `engram_test_worker_e`
- `engram_test_worker_e2e_runner_2`

All five now report 0.8.6. All eleven previously observed 0.6.0 extension
versions remain unchanged. The binary library is shared across PostgreSQL 17:
new connections to those databases also load the new binary, even though their
SQL extension versions stay at 0.6.0. Existing backends may retain the previous
mapped library until they disconnect; no sessions were terminated. A post-upgrade
process-map check found zero PostgreSQL processes retaining the deleted old
`vector.so`.

## Evidence and recovery

- Native pgBackRest check passed; a fresh differential backup completed before
  installation: `20260927-010427F_20260928-170759D`, stanza `proximal`.
- Archived the old library and extension SQL/control files. No package maintainer
  scripts were present. The four upgrade SQL steps from 0.8.2 through 0.8.6
  contain no schema-changing statements beyond advancing extension metadata.
- Used the [upstream upgrade procedure](https://github.com/pgvector/pgvector#upgrading)
  and reviewed the [0.8.6 changelog](https://github.com/pgvector/pgvector/blob/v0.8.6/CHANGELOG.md).
- Fresh connections verified vector distance operators in all sixteen databases
  with the extension, including the eleven left on 0.6.0.
- No invalid or unready HNSW/IVFFlat indexes in the five upgraded databases.
- Nearest-neighbor queries against existing `segment_embeddings` data succeeded:
  five rows each in `engram` and `hippo`; the three test databases returned zero.
- PostgreSQL service remained active. No PostgreSQL package upgrade, restart,
  data deletion, index rebuild, or application reconnect was performed.
- Post-commit recovery requires a planned restore/PITR or another validated repair;
  an SQL extension downgrade was not attempted or claimed to be supported.

Local receipts, exact operator script, backup metadata, archived files, package,
transaction logs, and verification results:
`/var/lib/update-bot/pgvector-20260928/` (private operator artifact directory).

## ob1 observation

`ob1` is owned by `postgres`, about 7.7 MiB. Its only user table is
`public.thoughts`, with an `embedding` vector column and exactly zero rows at
inspection. No other client was connected during that observation. Its originating
application remains unknown. No SQL upgrade or deletion was performed there.
