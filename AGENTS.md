# proximal — AGENTS.md

You are maintaining the durable, inspectable, cross-agent **provenance and
desired-state for the host `proximal`** (the workstation + home-lab node). This repo
is operational state, not a codebase: its job is to remember — across runs and across
agents (claude, codex, gemini, opencode-local) — what each service on this box looks
like, what config it should run, and what was already tried and rejected.

It exists because per-agent memory is opaque and single-agent; a git repo is the
opposite — any agent in the fleet can clone, read, diff, and append, and a human can
audit every change.

## How this repo is organized

One repo per host, **one directory per subsystem**. Each subsystem is self-contained
and has its own `AGENTS.md` / `README.md` — read that before working in it. Don't
spread one subsystem's state across the tree, and don't put system-wide concerns
inside a single service's directory.

- **PostgreSQL work** (tuning, GUCs, repack, inventory) → [`postgres/AGENTS.md`](postgres/AGENTS.md).
- **Monitoring / metrics / dashboards** → [`observability/README.md`](observability/README.md).
- New subsystem worth versioning (e.g. `llama/`, `ollama/`, `garage/`, `whisper/`)?
  Create a top-level directory for it with its own README; mirror the conventions below.

Live box facts (hardware, ports, the local LLM service, restart commands) are in
`~/CLAUDE.md` — read it for environment, not for desired-state.

## Conventions (must follow)

- **Values and config, never credentials.** Commit settings, unit files, dashboards,
  rationale. Never commit passwords, `.pgpass`, `pg_hba.conf`, secret-bearing DSNs,
  `*.env`, or keys. Secrets live only in root-only `/etc/…` files (`0600`) on the box.
  The root `.gitignore` catches the obvious cases; you enforce the rest.
- **Canonical-in-repo, installed-on-box.** The repo holds the source of truth; the box
  runs installed copies. When you change config, edit the repo copy, re-install on the
  box, and document the file→install-path mapping in the subsystem README.
- **Every change carries a rationale** tied to a measurement, report, or incident —
  the history is the point.
- **Long-running infra is under systemd.** Check `systemctl` before assuming a service
  is down; capture unit files / drop-ins as the desired-state for that subsystem.
- **Commit and push often.** Never end a turn with a dirty tree or unpushed commits
  (`origin` = `github.com/halbritt/proximal`).
