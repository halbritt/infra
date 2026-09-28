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


## Maintenance-v2 — software and OS updates

Owner authority was expanded on 2026-09-27 to updates for Hermes, wigolo,
llama.cpp, installed coding harnesses and the underlying OS. Implementation
`f5e3925` was merged to master, pushed and installed. The model uses a separate
root-owned Hermes snapshot at `/opt/update-bot/hermes-9904fd411587`; imports and
CLI startup were verified against that snapshot.

- 25 repository tests and the infrastructure validator passed. Added checks cover
  target/run/deadline admission, native operation locks, the fixed OS start command,
  the root helper remaining active after its client exits, protected package/origin
  policy, and rejection of model verification claims lacking a native receipt.
- A temporary service copied the installed maintenance unit's filesystem and
  privilege controls. Writing to the infra checkout failed with EROFS (30), writing
  policy failed with EACCES (13), an approved npm-prefix sentinel could be created
  and removed, and `sudo -n true` exited 1. The temporary service was removed.
- Run `563e6f35-0993-4491-8b46-8a71a866119e` admitted OS operation
  `c27398f3-4ce9-4bf3-b44e-e5eebf927b0c` through the envelope and exact polkit grant.
  Native execution and version/audit verification both exited zero. The helper
  upgraded 13 Ubuntu packages, held 28 packages outside policy, and recorded the
  existing reboot requirement. Evidence: `/var/lib/update-bot-os/1790561651538312764`.
- Independent `dpkg --audit` was empty, the temporary `policy-rc.d` was removed,
  and inference remained healthy at `:8081/health` with its original PID 1126876
  and activation timestamp 2026-09-22 22:40:05 PDT. No inference restart or reboot
  was performed. Installed binaries and live activation remain distinct.
- During this commissioning run the model invoked `llama-cpp-update --check`
  directly. This updated remote Git refs outside the required intent envelope;
  it did not build/install or restart llama.cpp. The role now explicitly names
  that misleading flag as mutating and directs discovery to `git ls-remote`.
  The envelope rule is an agent policy within writable prefixes, not an enforced
  per-command filesystem capability boundary. Retain this limitation visibly.

- Cairn intent, outcome and checkpoint records were read back successfully. The
  OS checkpoint is `777de1b7-9e92-45e7-a7a9-ab7448510cbe`; outcome is
  `f86e3b9a-0327-4a26-b466-04179fb957c4`. The publisher ran under a copy of the
  monitor's actual user/filesystem controls, validated the repo, committed and
  pushed `a7ecf7f`, fast-forwarded clean master and removed its detached worktree.
- A follow-up test ensures a native OS receipt with no selected packages does not
  create a Git commit. The full suite now has 26 passing tests. Publication retries
  are independent of host execution and do not replay package changes.

- Follow-up run `bb791a85-0619-4356-b2ee-4a133e7a7366` completed in about seven
  minutes. It used the canonical llama updater and native lock to install build
  11223 (`4da6337767`), preserving inference PID 1126876/build 10210. The first
  two verification attempts incorrectly parsed stdout; native version output is
  on stderr. Failed receipts remain, and operation `9f620ad7-2b2a-44c3-98d2-4f551eb16953`
  subsequently verified installed revision, source HEAD and live health. The
  repeated native updater calls were no-ops; the role now explicitly requires
  read-only verification recovery instead of rerunning a successful installer.
- Independent startup checks for the new llama-server and llama-cli `--help`
  exited zero. llama-quantize printed usage and exited 1, matching its source's
  usage() implementation. New-model inference was not exercised: the existing
  live server remained healthy, and activation of the new binary stays deferred.
- The follow-up correctly distinguished wigolo's installed `c6ad4479` source build
  from current upstream: the later delta is documentation/site/homepage metadata,
  with no source or dependency changes, so no functional update was warranted.
  Agy's online latest remains unknown, rather than claimed current. Hermes remains
  deferred because safe activation of its existing gateway was not established.
  Codex/Claude/OpenCode were current; local Cairn wrappers/patches were retained.
- The second OS helper run selected zero packages and verified cleanly. Both runs
  kept the 28 protected/third-party packages held and retained the reboot flag.
- Final Cairn checkpoint: `e86fd618-b0f3-47ed-b89c-6056696f0a6a`. Automatic publication
  committed/pushed `72beb09` and cleaned its worktree. The independent monitor sent
  Slack message `1790562359.684729` to `D0BMCL7T2FM`; API readback confirmed its run
  ID and Git commit link. Both timers are enabled and active again, with the next
  daily maintenance run on 2026-09-28 shortly after 06:30 America/Los_Angeles.


## 2026-09-28: carry patches rather than blanket deferral

- OpenCode 1.18.33: three patches applied cleanly, typecheck/build passed,
  102 native tests passed (one skipped), 50 Cairn socket/bridge tests passed.
  Actual installed binary is `1.18.33+cairn.9797966`; hash and rollback are in
  `/var/lib/update-bot/opencode-installed.json`. No OpenCode process was found
  at activation; the atomic replacement mechanism preserves existing mappings.
- Hermes upstream `79a6fd3e` plus `9b57ee21`: four local commits ported to the
  current modules, 239 native tests passed (four platform skips). New CLI
  launches select this source and its Python 3.14.6 venv. Existing CLI and gateway
  source/venv and processes were preserved. Gateway activation is not claimed.
- The first Hermes bridge run exposed a four-second cancellation response
  timeout and fixture incompatibilities. Cairn `d08bba3` fixes the bounded wait
  and fixture APIs; 71 combined tests pass against new Hermes, 22 cancellation
  tests against old Hermes, 21 socket-client tests, and `make check` pass.
  Logs retain both failures and repairs under `/var/lib/update-bot/staging/`.
- Broader discovery read 1,754 dpkg package records plus npm/uv/pipx metadata and
  44 venvs (1,933 library records, including archives). This is an installed
  inventory, not an assertion that those libraries are current or unpinned.
  Scope/depth and unvisited directories are recorded in the JSON receipt.
- Updated policy/role require isolated patch carry, behavior verification,
  separate activation and periodic broader discovery. No new model-driven daily
  run was triggered solely to test prompt instructions; future adherence remains
  observable in run receipts. A real-model round trip on new Hermes is untested.


### Gateway activation, later in the same maintenance session

The native reversible drain watcher produced a fresh status for old PID 1378353
with `gateway_state=draining` and aggregate chat/cron/API `active_agents=0`.
Installed canonical `config/hermes/gateway-generation.conf` as the user-unit
50-generation.conf drop-in, reloaded systemd and requested native SIGUSR1 restart.
New PID 785678 reports source `9b57ee21`, running and Slack connected. The drain marker
was removed and separate interactive CLI 2369575 remains alive on its old source.
Exact receipt: `/var/lib/update-bot/hermes-gateway-activation.json`. This supersedes
the earlier pending-gateway status; no active turn was interrupted or force-killed.
Native `code_version` is unknown, while the runtime's full `code_sha` is recorded.

Review method: Pincite packet pkt-f21cd24b2aec64e7 supplied repository-contract
precedence, explicit invariants and default behavior preservation. Typed evidence
satisfied those selected obligations. Forty-eight nonselected generic obligations
remain outside this bounded result, including full CI-only build provenance and
host-wide dependency/CVE qualification; neither is claimed by these checks.


### Recurring gateway activation boundary

Added the fixed `update-bot-hermes-activate.service` so the model can activate a
verified generation without direct user-manager or profile access. The root-owned
controller runs as halbritt with the frozen native drain API. It checks exact source
and launcher identity, refuses existing foreign drains and stale/busy/mismatched
status, reloads once after native zero-work confirmation, and requires a new matching
PID/source plus a freshly written Slack connection state. Failure stays visible;
there is no force-stop, automatic retry or silent rollback. Only its own marker is
removed. Operation receipts retain the native result; verified no-ops are not Git
changes, and the host lock remains held while the separate unit is active.

31 repository tests pass, including gateway boundary failures and both native-unit
drain checks; repository validation and changed-unit verification pass. The latter
also reported an unrelated pre-existing systemd-resolved override warning. A transient
halbritt service with NoNewPrivileges, read-only home/system and inaccessible user
bus successfully started the approved action through polkit (invocation
`d61de06060244810aaa374ec124028e5`). Its receipt verified current revision `9b57ee21`
and `changed=false`; gateway PID 785678 was preserved and no drain marker remained.
This tests the deployed permission/no-op path. The actual changed-generation drain
and restart was observed in the preceding operator procedure, while the controller's
failure and restart decisions are covered with external SDK/systemd fixtures.
Receipt: `/var/lib/update-bot/hermes-activation-latest.json`.
