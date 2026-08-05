# infra repository — AGENTS.md

This repository is the durable, cross-agent provenance and desired state for a
set of managed infrastructure resources. It is operational state, not an
application codebase. Preserve the evidence that explains what each resource
runs, why it runs it, how it is installed, and what was tried and rejected.

## Scope and routing

- Work on one machine under `hosts/<machine>/`.
- Read that host's `AGENTS.md`, `machine.yaml`, and `notes.md` before changing it.
- Read a subsystem's `README.md` or `AGENTS.md` before changing files below it.
- Put reusable configuration under `shared/` only when its bytes and meaning are
  genuinely reusable across hosts.
- Put reusable machine-type or responsibility contracts under `roles/`. Roles
  declare shared inputs; host-specific overrides stay with the host.
- Do not create or keep one Git branch per machine. Use short-lived task branches
  only when the work itself needs a branch.
- Put managed appliances such as printers and network gear under `devices/`.
- Put service-level desired state that is not owned by one host under `services/`.
- Put external-provider policy and resource declarations under `providers/`.
- Read [`CONTEXT.md`](CONTEXT.md) before introducing a new resource category.

The current host record is [`hosts/proximal/`](hosts/proximal/). Live facts for
that box are also in `~/CLAUDE.md`; live state must be rechecked before an
operational action.

## Conventions

- **Values and config, never plaintext credentials.** Never commit passwords,
  tokens, private keys, secret-bearing DSNs, `.pgpass`, `pg_hba.conf`, decrypted
  SOPS files, or generated credential bundles. Read `secrets/README.md`.
- **Canonical-in-repo, installed-on-box.** Edit the canonical file, install it at
  the path documented by the host subsystem, reload or restart as required, and
  verify the live result.
- **Preserve provenance.** Every operational change carries a rationale tied to
  a measurement, report, incident, or explicit decision. Do not rewrite old
  evidence to make the present state look cleaner.
- **Preserve imports.** Bring another resource repository in with its useful Git
  history. Scan for secrets before merging and normalize paths in a separate,
  reviewable commit.
- **System services stay managed.** Check the target host's service manager before
  assuming a long-running service is down.
- **Commit and push often.** Never end a turn with a dirty tree or unpushed commits
  (`origin` = `github.com/halbritt/infra`).

## Structural rules

- Every `hosts/<name>/machine.yaml` declares a unique host name and existing
  roles.
- Every host has `config/`, `notes.md`, and a host changelog.
- Each immediate directory under a host's `config/` is a self-contained
  subsystem with a `README.md` or `AGENTS.md`.
- A role may reference only files below `shared/`.
- Host overrides remain under the host. Do not modify a shared file to encode a
  single machine's hardware, identity, address, port collision, or exception.
- Do not add compatibility symlinks at the repository root for old subsystem
  paths. Update canonical scripts, units, and documentation to infrastructure paths.

Run `scripts/validate-infra.py` before committing.

<!-- BEGIN PROXIMAL PLANE TRACKING -->
## Plane Tracking

This repository is represented in the local/private Plane workspace `Proximal`.

- Plane project: `Infra` (legacy identifier `PROXIMAL`)
- Issue tracker: Plane (`Proximal` workspace), project `Infra` (`PROXIMAL`).
- Plane URL: `https://proximal.tail0ecc2e.ts.net:10000/`
- GitHub repo: `https://github.com/halbritt/infra`
- GitHub Issues: deprecated; use Plane work items for new issue tracking, claims,
  reviews, and issue-state changes.
- When updating Plane, include the repo, branch/worktree, `run_id`, `base_sha`,
  artifact links, verification evidence, and authority scope.
- Do not commit Plane API tokens. Local tokens and MCP environment files live
  outside Git under `~/.config/plane/`.
<!-- END PROXIMAL PLANE TRACKING -->

## Branch and worktree hygiene

Do not leave unmerged work lying around. If a task uses a branch, merge its
authorized work into the intended target before reporting completion. If merge
authority is absent, report that blocker. Remove merged task branches and their
worktrees.

Concurrent agents use one sibling worktree per branch under
`../infra-wt/<branch>`. Worktrees isolate files, not ports, databases, service
managers, or remote machines; coordinate those separately. Regenerate generated
artifacts once on the merged tree rather than merging competing generated copies.
