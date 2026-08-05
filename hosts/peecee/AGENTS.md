# peecee host — AGENTS.md

This partition is the canonical desired-state and operational record for the
Windows GPU node `peecee`. Read [`README.md`](README.md), [`notes.md`](notes.md),
and the target subsystem README before changing it. The repository-level
[`AGENTS.md`](../../AGENTS.md) governs Git, secrets, installation, and worktree
practice.

## Plane tracking

- Workspace: local/private `Proximal`
- Project: `Peecee` (`PEECEE`)
- Plane URL: `https://proximal.tail0ecc2e.ts.net:10000/`
- Historical source repository: `https://github.com/halbritt/peecee`
- New work belongs in Plane, not GitHub Issues.
- Include repository, branch/worktree, `run_id`, base SHA, artifacts,
  verification evidence, and authority scope in tracker updates.
- Plane tokens and MCP environment files remain outside Git under
  `~/.config/plane/`.

## Host boundaries

- Do not infer unrecorded hardware, services, paths, or credentials.
- Preserve Windows Scheduled Task and service recovery behavior, Tailscale
  dependencies, firewall scope, and installed paths unless current host
  evidence justifies a change.
- `peecee` is a pull-observed GPU-fleet node: do not install fleet database
  credentials or self-heartbeat code. Peer-side polling owns its heartbeat.
- Model placement and residency are governed by the GPU fleet and explicit
  owner direction. Historical model observations in this partition are not
  standing authority to change a loaded model.
- Do not treat a successful scrape or SSH probe from `proximal` as authority to
  mutate the Windows host.
- Windows Scheduled Tasks and services are the platform-specific exception to
  the infrastructure repository's systemd convention.
- Keep tokens, private keys, remote-access credentials, generated service
  credentials, and model-store contents outside Git.
- Record live verification dates separately from historical deployment facts.
