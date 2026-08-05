# peecee host — AGENTS.md

This host partition records only configuration and evidence known to belong to
the Windows workstation `peecee`. Read [`notes.md`](notes.md) and the target
subsystem README before changing it.

- Do not infer unrecorded hardware, services, paths, or credentials.
- Preserve Windows service recovery, Tailscale dependency, firewall scope, and
  install paths unless current host evidence justifies a change.
- Do not treat a successful scrape from `proximal` as authority to mutate the
  Windows host.
- Keep tokens, private keys, remote-access credentials, and generated service
  credentials outside Git.
- Record live verification dates separately from historical deployment facts.

The root fleet instructions and commit/push requirements also apply.
