# proximal/postgres — PostgreSQL subsystem

Durable provenance and desired-state for the PostgreSQL instance on **proximal**
(`localhost:5432`). The Postgres subsystem of the
[`proximal`](../README.md) whole-system repo — one repo per host, one directory
per subsystem.

This is operational state for the reusable tuning instrument at
`~/git/prompts/POSTGRES_TUNING.md` — it remembers, across runs and across agents,
what this cluster looks like, what config it should run, and what was tried and
reverted. Start with [`AGENTS.md`](AGENTS.md).

- [`baseline.md`](baseline.md) — current accepted GUC set + rationale
- [`desired.md`](desired.md) — desired-state config (ALTER SYSTEM)
- [`known-bad.md`](known-bad.md) — reverted-values ledger
- `inventory/` — dated read-only snapshots
- `reports/` — dated tuning reports
- [`connection.md`](connection.md) — how to reach the instance (no secrets)
- [`skills/`](skills/) — vendored Postgres best-practices reference skill (see [`skills/README.md`](skills/README.md))

**Values, never credentials.** No passwords, `pg_hba.conf`, or secret-bearing
connection strings in this repo — ever.
