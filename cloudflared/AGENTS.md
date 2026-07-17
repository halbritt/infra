# proximal/cloudflared instructions

This subsystem records the Cloudflare Tunnel edge for public `harm.org`
hostnames on `proximal`. Read `README.md` before changing anything here.

## Boundaries

- Commit ingress rules, unit files, hostnames, tunnel IDs, and rationale.
- Never commit tunnel credential JSON, origin certificates, API tokens, account
  secrets, or Cloudflare dashboard exports containing secrets.
- Keep `credentials-file` as a pointer to the root-only file in `/etc`; do not
  copy that file into this repo.
- Preserve the final `http_status:404` ingress rule so unknown hostnames do not
  accidentally reach a local service.
- When adding a public hostname, verify both the local origin and the external
  HTTPS route.

## Operational Rule

The repo holds desired state; installed copies run on the box. If you change the
Cloudflared config or units here, install them to the mapped paths, reload or
restart the affected service, verify externally, and update `README.md` plus the
root changelog.


## Branch hygiene

Do not leave unmerged code lying around. If a task uses a branch, merge its authorized work into the intended target branch before reporting completion. If merge authority is absent, report that as a blocker instead of treating the branch as finished. Clean up branches and associated worktrees after merge.
