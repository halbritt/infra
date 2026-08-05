# proximal/postgres — AGENTS.md

You are an expert PostgreSQL administrator. This directory is the durable,
inspectable, cross-agent provenance and desired-state for the PostgreSQL instance
on the host **proximal** (the workstation; loopback `:5432`) — the Postgres
subsystem of the [`proximal`](../README.md) whole-system repo. It is operational
state, not a codebase: its job is to remember — across runs and across agents
(claude, codex, gemini, opencode-local) — what this cluster looks like, what config
it should run, and what was already tried and rejected.

It exists because Claude's per-project memory is opaque and single-agent; a git
repo is the opposite — any agent in the fleet can clone, read, diff, and append to
it, and a human can audit every change.

## The instrument

Tuning and config-review work is driven by the reusable prompt
`~/git/prompts/POSTGRES_TUNING.md`. That prompt is stateless; this repo is where
its durable artifacts live. Read it before tuning. In short: it reviews the
instance for performance and reliability, proposes config (GUC) changes, verifies
each as a falsifiable hypothesis before applying, and applies reversibly.
**Durability is frozen** (`fsync`, `full_page_writes`, `synchronous_commit` on a
primary, `wal_level`) and **reliability blockers outrank performance wins**.

## Layout

- `baseline.md` — the current accepted GUC set and a one-line rationale for each
  non-default value (decision records). Populated by the first inventory run.
- `desired.md` — desired-state: the canonical GUC set this cluster should run, as
  `ALTER SYSTEM` statements. The live config should converge to this.
- `known-bad.md` — the known-bad-settings ledger: values tried here and reverted,
  with evidence. Do not re-propose a reverted value without new evidence that
  overcomes the prior failure. Append a row whenever you revert something.
- `inventory/` — dated, read-only snapshots (`pg_settings` dump, environment,
  config-file checksums) captured at the start of a run. Evidence; never edited
  after the fact.
- `reports/` — dated `POSTGRES_TUNING` reports, one per run.
- `connection.md` — how to reach the instance: host, port, database, role names.
  **No passwords.**
- `skills/` — vendored, version-pinned reference skills (Postgres best-practices
  library) for the instrument and the fleet to read. Reference material, not
  desired-state; see `skills/README.md`. The proximal-specific application of
  these rules is the mined-insights report under `reports/`.

## Conventions

- **Values, never credentials.** Commit GUC values, settings, and rationale. Never
  commit passwords, `.pgpass`, `pg_hba.conf`, connection strings with secrets, or
  `.env`. The `.gitignore` catches the obvious cases; you enforce the rest.
- Every change to `desired.md` or `baseline.md` carries a one-line rationale tied
  to a measurement or a report under `reports/`.
- Snapshots in `inventory/` are read-only captures — they are evidence, not
  working files.
- One fleet repo, one directory per host, one directory per subsystem; this is
  the `postgres/` subsystem of `proximal`. If a host ever runs more than one cluster,
  nest the per-instance files under `instances/<port-or-name>/`. System-wide
  concerns (Prometheus/Grafana/exporters, etc.) live in sibling top-level
  directories, not here — see [`../README.md`](../README.md).
- **Commit and push often.** This repo's value is its history — commit after every
  change and push to `origin` so the rest of the fleet sees it. Never end a turn with
  a dirty tree or unpushed commits.


## Branch hygiene

Do not leave unmerged code lying around. If a task uses a branch, merge its authorized work into the intended target branch before reporting completion. If merge authority is absent, report that as a blocker instead of treating the branch as finished. Clean up branches and associated worktrees after merge.
