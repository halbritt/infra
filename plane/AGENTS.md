# proximal/plane instructions

This subsystem records the local/private Plane CE pilot on host `proximal`.
Read `README.md` before changing anything here.

## Boundaries

- Keep this deployment local/private: loopback Docker publish ports, fronted only by
  Tailscale Serve on `proximal.tail0ecc2e.ts.net:10000`.
- Do not expose it through public DNS, Tailscale Funnel, or `plane.harm.org` without
  explicit user approval.
- Do not migrate Plane to system PostgreSQL, Garage, or host Redis without an
  explicit migration plan and backup/restore proof.
- Never commit Plane API tokens, generated passwords, `plane.env`, `.env` files,
  MinIO keys, database dumps, or MCP credential files.

## Operational rule

The repo holds the desired state; installed copies run on the box. If you change a
file here, install the matching copy and verify the service. If the live setup
changes, update `README.md` and the root changelog in the same commit.


## Branch hygiene

Do not leave unmerged code lying around. If a task uses a branch, merge its authorized work into the intended target branch before reporting completion. If merge authority is absent, report that as a blocker instead of treating the branch as finished. Clean up branches and associated worktrees after merge.
