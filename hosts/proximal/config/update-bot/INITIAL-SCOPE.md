# Initial findings and held maintenance scope — 2026-09-27

The owner authorized installation of the discovery stage. No host-update scope
has been approved. This document records proposals, not commands to execute.
The first completed survey is Cairn record
`b63a6b49-3bfe-4c8e-96c2-c6f0354fa7bb`, run
`b1b25a99-8047-4eb3-af22-a04e12a740d2`. Its full evidence and coverage limits remain
in Cairn and `/var/lib/update-bot/runs/`, rather than a second inventory here.

## Findings worth carrying forward

- **llama.cpp installed versus active:** on-disk build 11222 (`a97cce86a`),
  live process build 10210 (`000547513`), directly checked through
  `/proc/1126876/exe --version`. The health endpoint was healthy on the old build.
  The existing autonomous updater remains the update owner; activation requires
  a separately authorized restart window. A previous-binary rollback is not yet
  established. Reverting a systemd override does not restore the old executable.
- **OS maintenance:** the survey reported 39 upgradable packages and a pending
  reboot. Its blanket `apt upgrade` suggestion is **not an approved execution
  plan**. PostgreSQL, Kubernetes and container-runtime dependencies need explicit
  package-transition review, service-impact checks, and recovery evidence first.
  Existing unattended-upgrade timers retain their authority.
- **Development work:** `ik_llama.cpp` had local modifications and untracked
  files. It is protected; no maintenance pull, stash, cleanup or reset is allowed.
- **Self-dependencies:** Hermes, Cairn, the inference endpoint and reporting
  dependencies remain protected from this job's mutation authority. The separate
  maintenance Hermes profile must not be confused with the gateway profile:
  seven enabled gateway cron jobs were observed through metadata inspection.

## Proposed next scope, still held

The smallest consequential trial would be one scheduled activation of the already
installed llama.cpp binary, after confirming current workloads, GPU capacity,
expected outage and an operator-owned recovery path. Success must include a new
process, its actual executable version and a representative inference operation.
This is a proposal for later approval; the deployed discovery policy forbids it.

OS upgrade/reboot work and automatic user-tool updates should remain separate
decisions. No general approval can be inferred from these proposals or a Slack
reply. The current job continues read-only discovery and records useful changes.
