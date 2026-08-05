# proximal host — AGENTS.md

You are maintaining the durable, inspectable, cross-agent **provenance and
desired-state for the host `proximal`** (the workstation + home-lab node). This host
partition is operational state, not a codebase: its job is to remember — across runs and across
agents (claude, codex, gemini, opencode-local) — what each service on this box looks
like, what config it should run, and what was already tried and rejected.

It exists because per-agent memory is opaque and single-agent; a git repo is the
opposite — any agent in the fleet can clone, read, diff, and append, and a human can
audit every change.

## How this repo is organized

The fleet repo uses one directory per host and this host uses **one directory per
subsystem** below `config/`. Each subsystem is self-contained
and has its own `AGENTS.md` / `README.md` — read that before working in it. Don't
spread one subsystem's state across the tree, and don't put system-wide concerns
inside a single service's directory.

- **PostgreSQL work** (tuning, GUCs, repack, inventory) → [`config/postgres/AGENTS.md`](config/postgres/AGENTS.md).
- **Monitoring / metrics / dashboards** → [`config/observability/README.md`](config/observability/README.md).
- New subsystem worth versioning (e.g. `llama/`, `ollama/`, `garage/`, `whisper/`)?
  Create `config/<subsystem>/` with its own README; mirror the conventions below.

Machine metadata and declared roles live in [`machine.yaml`](machine.yaml).
Machine-wide notes and exceptions live in [`notes.md`](notes.md). Fleet-wide
structure and import rules live at the repository root.

Live box facts (hardware, ports, the local LLM service, restart commands) are in
`~/CLAUDE.md` — read it for environment, not for desired-state.

## Conventions (must follow)

- **Values and config, never credentials.** Commit settings, unit files, dashboards,
  rationale. Never commit passwords, `.pgpass`, `pg_hba.conf`, secret-bearing DSNs,
  `*.env`, or keys. Secrets live only in root-only `/etc/…` files (`0600`) on the box.
  The root [`.gitignore`](../../.gitignore) catches the obvious cases; you enforce the rest.
- **Canonical-in-repo, installed-on-box.** The repo holds the source of truth; the box
  runs installed copies. When you change config, edit the repo copy, re-install on the
  box, and document the file→install-path mapping in the subsystem README.
- **Every change carries a rationale** tied to a measurement, report, or incident —
  the history is the point.
- **Long-running infra is under systemd.** Check `systemctl` before assuming a service
  is down; capture unit files / drop-ins as the desired-state for that subsystem.
- **Commit and push often.** Never end a turn with a dirty tree or unpushed commits
  (`origin` = `github.com/halbritt/infra`).

<!-- BEGIN PROXIMAL PLANE TRACKING -->
## Plane Tracking

This repository is represented in the local/private Plane workspace `Proximal`.

- Plane project: `Proximal` (`PROXIMAL`)
- Issue tracker: Plane (`Proximal` workspace), project `Proximal` (`PROXIMAL`).
- Plane URL: `https://proximal.tail0ecc2e.ts.net:10000/`
- GitHub repo: `https://github.com/halbritt/infra`
- GitHub Issues: deprecated; use Plane work items for new issue tracking, claims, reviews, and issue-state changes.
- Use Plane work items for multi-agent planning, claims, submitted artifacts, reviews, and acceptance decisions.
- When updating Plane, include the repo, branch/worktree, `run_id`, `base_sha`, artifact links, verification evidence, and authority scope in the work item description or comments.
- Do not commit Plane API tokens. Local tokens and MCP env files live outside git under `~/.config/plane/`.
<!-- END PROXIMAL PLANE TRACKING -->


## Branch hygiene

Do not leave unmerged code lying around. If a task uses a branch, merge its authorized work into the intended target branch before reporting completion. If merge authority is absent, report that as a blocker instead of treating the branch as finished. Clean up branches and associated worktrees after merge.

## Parallel work: one worktree per branch

When more than one agent works this repo at once, do not share a working
directory — give each unit of work its own git worktree. A branch can be
checked out in only one worktree at a time, so concurrent edits to shared
files (Makefile, configs, generated/golden files) become impossible.

- One worktree per branch, one agent per worktree; name the dir after the branch.
- Siblings, not nested: create worktrees OUTSIDE this checkout
  (`../infra-wt/<branch>`), never inside it — recursive globs, file-count/hash
  gates, and IDE indexers must not scan across worktrees.
- Lifecycle: `git worktree add ../infra-wt/<branch> -b <branch>` /
  `git worktree list` / `git worktree remove <path>` after merge /
  `git worktree prune`. Agents with worktree isolation get this for free.
- Shared object store and build caches are fine; worktrees do NOT isolate
  ports, databases, or local services — coordinate those separately.
- Regenerate, don't merge, generated artifacts (golden files, compiled
  indexes): merge the source change, then regenerate once on the merged tree.
