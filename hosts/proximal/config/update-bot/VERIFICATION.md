# Deployment verification — 2026-09-27

The discovery-v1 evidence below is historical. The owner subsequently authorized
automatic updates to Hermes, wigolo, llama.cpp, coding harnesses and the underlying
OS. Maintenance-v2 implements that expanded authority; activation evidence is
recorded separately below and does not rewrite the earlier scope.

Host: proximal. Initial repository base: `2bded13`. Implementation branch/worktree:
`update-bot`, `/home/halbritt/git/infra-wt/update-bot`. Deployment session:
`85aa4960-cd05-4035-afc3-2b748e8183b3`. Authority: implement the reviewed architecture's
discovery-only first stage; host upgrades/restarts remain outside scope.

## Live execution boundary

A temporary service copied the actual discovery unit's controls and ran a small
acceptance probe. `/var/lib/update-bot/probe-result.json` retains the result:

- Opening an owner-modified sentinel for writing failed with `EROFS` (30); its
  contents remained unchanged.
- Opening the installed policy for writing failed with `EACCES` (13).
- `sudo -n true` exited 1 under `NoNewPrivileges`.
- Access to the user's systemd bus exited 1.
- Taking the host lock while the real discovery run held it was refused.
- A detached `setsid sleep` child was absent from `/proc` after the probe service
  stopped, demonstrating cgroup cleanup beyond the parent's process group.

The temporary probe service/script and sentinel were removed. No existing service
was restarted. These controls establish the documented filesystem/privilege
boundary, not arbitrary network API isolation.

## Real model and continuity trials

- `d4489afc-2654-42b0-9723-83efe99012bc`: interrupted after discovering that Hermes
  filters custom environment variables from MCP subprocesses. Fixed explicit
  `mcp_servers.cairn.env.UPDATE_BOT_RUN_ID` interpolation. The next run recognized
  the interrupted receipt; no host action was replayed.
- `d6ade181-e588-4684-9337-e50648663088`: provider conversation completed in 13 API
  calls, estimated $0.020234. The report was initially rejected for a summary 42
  characters over its target. Validation now retains bounded extra prose rather
  than discarding useful evidence for that cosmetic excess. Its failed receipt
  remains preserved.
- `b1b25a99-8047-4eb3-af22-a04e12a740d2`: completed survey with native Cairn search
  and pull, 9 API calls, estimated $0.016796. Hermes prefixed its JSON with a short
  sentence; parsing now tolerates a short preamble or code fence while requiring
  exactly one valid report and a completed provider conversation. Saved evidence
  was finalized without another model or host action; the prior failure receipt
  is retained as `before-reconciliation.json` and `prior_error`.
- Checkpoint persisted as Cairn record `b63a6b49-3bfe-4c8e-96c2-c6f0354fa7bb`.
  Hermes Slack delivery returned `success: true`, channel `D0BMCL7T2FM`, message
  `1790559439.576089`. Earlier commissioning failures also produced real messages;
  commissioning artifacts are now explicitly classified in the run prompt.
- Follow-up `2799fd5d-402a-4b79-b5d6-a2fef6fa89c3` completed normally with no
  record repair, recalling the prior checkpoint and saving Cairn record
  `0f05b66d-f152-47a9-a9d6-3a091e95610e`. It reported the actual transition from
  commissioning to enabled timers (10 API calls, estimated $0.018891). The role
  was then clarified to avoid re-requesting already settled deployment choices
  and to keep notifications limited to new findings.
- The first findings message was independently read back through Slack's history
  API with its exact message timestamp; the expected maintenance prefix matched.
- Quiet follow-up `4333c68b-d856-4d8e-b3ba-169cf7115051` completed with an empty
  notification, seven API calls and estimated $0.012956; checkpoint
  `e1986734-ac7d-4eee-9e45-b44c8c4aad57`. Running the actual monitor afterward
  left `delivery.json` byte-identical (SHA-256
  `e18ac0327904c79d84187f663bb52ca8e5258e5c484229e6fe1ab386ef440d88`),
  demonstrating a quiet no-op without suppressing its Cairn completion record.
  Both services reported `Result=success`, `ExecMainStatus=0`.

Both timers are enabled. Daily schedule readback showed the next run on September
28 at approximately 06:30 PDT plus jitter; monitor cadence is 15 minutes.

These figures are provider-model estimates, not actual billing. The upstream
Hermes one-shot path's iteration-limit omission is documented in the README;
15-minute agent and 18-minute service deadlines are enforced externally.

## Automated checks

20 repository tests passed at initial installation, including report completion,
secret-shaped-output rejection, quiet no-op classification, absent scheduler runs,
killed launcher classification, inference failure injection, checkpoint recording
outage, and exact-request replay before a later successful run. Failure injection
uses a test executable; it is not a claim of an induced OpenRouter outage.

`scripts/validate-infra.py` passed. `systemd-analyze verify` accepted the four
units; it also reported an existing unrelated `systemd-resolved` drop-in warning.
No verified software-update acceptance is claimed: this deployment has no such
authority and performs discovery only.
