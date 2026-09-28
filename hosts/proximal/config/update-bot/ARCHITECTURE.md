# Daily Update Bot — Architecture Sketch

**Status:** Proposed architecture, not an implementation audit

**Scope:** One host, one daily maintenance role

**Existing infrastructure:** Cairn for history; the infra repository for the changelog

## 1. Intent

Run a capable maintenance agent daily. It should understand what is installed, determine what ought to change, make authorized changes, establish that the affected software still works, and leave useful records for both the next run and its human operator.

**The agent owns discovery, planning, execution, and adaptation. The runtime limits its authority. Cairn supplies continuity; Git records changes; the host establishes current truth.**

This is not a deterministic updater with an agent attached to explain failures. Nor is it another orchestration platform. Do not introduce Topgrade as the foundation, a parallel memory store, an inventory database, or a framework of mandatory update adapters.

The installation inventory should emerge from investigation and remain useful through Cairn. Proven procedures are reusable evidence, not an immutable program the agent must follow.

## 2. Component map

```text
Existing daily trigger — choose one
    |
    v
Maintenance execution boundary
  host lock · approved policy · privileges · execution budget · run status
    |
    v
Maintenance agent — choose one execution profile
  Hermes + OpenRouter/DeepSeek
  OR local runner + local model, optionally using OpenCode as the harness
    |
    +<--> Cairn: recall, observations, intents, outcomes, next-run checkpoint
    +<--> Host: inspect, use native maintenance tools, verify live behavior
    +----> Infra repo: concise changelog and authorized configuration changes
    +----> Slack: meaningful results, failures, and requests for decisions
```

The execution boundary is a responsibility, not necessarily a new process or service. Reuse capabilities already provided by the selected harness and host. Add a small launcher or hook only for missing controls.

Use one maintenance writer per host. Scheduled runs, manual runs, and either execution profile must honor the same host-local lock. This lock does not substitute for native package-manager locks or coordination with other workloads.

## 3. Two deployment profiles, one role

### Profile A: Hermes-owned job

Start with the existing Hermes setup using OpenRouter/DeepSeek. Attach the maintenance role, load its approved policy explicitly, use the existing Cairn integration, and deliver relevant results through Slack.

Hermes documents recurring jobs, fresh execution sessions, explicit working directories, and per-job model/provider selection. Configure these deliberately rather than inheriting an unrelated interactive session's settings. In particular, the cron documentation says repository instructions are not loaded by default for jobs without an explicit working directory. [1]

Hermes also documents Slack delivery targets for scheduled results. Use that existing delivery path rather than creating a separate bot solely for notifications. [2]

**Default first implementation:** this profile, unless local inference is itself a requirement. It exercises the maintenance role without simultaneously building another runner.

### Profile B: Local execution

An existing host trigger launches the same role against the local model, with the same Cairn access, policy, and infra-repo conventions. It needs a notification adapter, but not a new memory or scheduling architecture.

OpenCode can itself be the harness: its documented noninteractive `run` interface supports selecting an agent and model, specifying a working directory, and producing JSON events. [3] Its provider configuration supports local models through compatible local endpoints. [4]

OpenCode can also be the tool used to build a small dedicated runner; that does not oblige the implementation to invent a new agent harness. Prefer the smallest implementation that preserves the role's tools and controls.

Keep the contract portable, but build only one execution profile initially. Do not run a Hermes agent that supervises an OpenCode agent merely to perform this one job. Reusing Hermes only for delivery is a separate choice.

Pin or explicitly select the intended provider/model configuration. A local profile must not silently fall back to a cloud provider. Local inference also does not imply that Cairn, Git synchronization, or Slack work offline.

## 4. Ownership and durable state

| Concern | Owner | Rule |
| --- | --- | --- |
| Current installations and health | Live host observations | Revalidate facts relevant to a change; history is not present truth. |
| History, discoveries, procedures, unresolved work | Cairn | Use the existing integration and record types; no second inventory or memory database. |
| Human-readable change history | Infra repo | Record actual attempts and outcomes, not raw transcripts or daily empty entries. |
| Desired configuration, where already managed | Existing infra-repo configuration | Keep authorized host changes consistent with it; do not invent a second configuration authority. |
| Maintenance scope and privileges | Operator-approved policy | The agent may propose changes to its mandate, but cannot expand its own authority. |
| Run execution and delivery status | Existing runner/scheduler facilities | A missing completion record is not a successful no-op. |

### Cairn checkpoint

Scope maintenance context to a stable host identity and role. Retrieve the most recent checkpoint, unresolved issues, and relevant installation knowledge rather than loading all historical sessions.

For a run, retain a correlation ID, start/end status, the role/policy revision, runner/model identity, important observations, attempted changes, verification evidence references, and deferred work. Record consequential change intent before acting and the observed result afterward. Link the final checkpoint to the infra-repo commit when one exists.

These are logical record contents, not a proposed new Cairn schema or API. Fit them to existing conventions. Normal harness transcripts may remain evidence, but must not become a competing source of maintenance policy.

### Infra-repo changelog

Each meaningful entry should distinguish **attempted**, **completed**, **verified**, **failed**, and **rolled back** work. Include the host, run ID, previous and observed resulting versions or revisions, relevant checks, and outstanding consequences. Do not infer verification from an installer's success message.

Use the repository's existing layout and branch/commit conventions. Prefer an isolated worktree when the normal checkout is shared. Stage only intended files and inspect the staged diff; never sweep up unrelated changes, discard someone else's edits, or force-push to make recording convenient.

A successful no-op gets a Cairn checkpoint and runner status, not an empty changelog commit. Secrets and unredacted environment dumps belong in neither system.

## 5. The maintenance loop

These are required checkpoints around an adaptive investigation, not a fixed sequence of package-specific handlers.

### Establish context

Acquire the host lock and establish a run ID. Load the approved role and policy, recover relevant Cairn context, and check for unfinished prior work before starting new mutations.

Inspect the host, its installation methods, relevant active workloads, and the ability to record changes. Resolve the executable or deployment actually in use, not merely the first installation that is easy to update. Discover unfamiliar software without assuming discovery grants permission to modify it.

Begin with a broader survey; subsequent runs should investigate changes and unresolved questions without repeating every settled discovery. Periodic broader rediscovery should prevent the remembered inventory from becoming the boundary of what the agent notices.

### Decide what is appropriate

For each candidate, establish provenance, current state, tracking policy, relevant release information, likely consequences, and an appropriate verification check. Respect pins, local modifications, supported native update procedures, and complete native transactions.

“Newer exists” is a finding, not an instruction. The agent may update, investigate further, defer with a reason, or request a decision. Security relevance can increase priority without overriding authority boundaries.

### Execute and verify

Before consequential changes, record intent, relevant before-state, planned checks, and a recovery approach proportionate to the risk. Do not claim a rollback path that has not been established.

Use native package managers, installers, build tools, and service tooling as appropriate; they remain responsible for their own transactions. The agent chooses and sequences the work, accounts for dependencies, and adapts when observed behavior differs from expectations.

Verification should test the affected capability: the active CLI resolves correctly and runs, a service answers its expected health check, or a representative operation succeeds. Compare against a pre-change baseline where practical. A changed version string alone is insufficient for a consequential update.

When a check fails, diagnose within a bounded budget. Attempt recovery only within the existing mandate. Record uncertain state honestly and stop dependent changes rather than escalating into an open-ended repair campaign.

### Close the run

Record outcomes in Cairn, commit meaningful changes to the infra repo, and finish with a compact next-run checkpoint. Report what was checked as well as what was left unchecked; a bounded or interrupted survey must not claim that the entire host is current.

Send a notification only when warranted. Record execution, changelog publication, and notification delivery separately so a delivery failure cannot cause an update to be repeated.

## 6. Authority and operating boundaries

Define permission by scope and consequences, not by a rigid catalogue of update commands. A newly discovered installation may qualify under an already approved scope; genuinely ambiguous ownership requires a decision.

A sensible initial policy has three categories:

| Category | Proposed treatment |
| --- | --- |
| Routine maintenance in explicitly approved scope | Agent may investigate, update, and verify, subject to the installation's tracking policy and disruption limits. |
| Disruptive or ambiguous changes | Investigate and propose; require explicit permission for reboots, database migrations, changes to networking/storage, disruptive service restarts, or uncertain ownership. |
| Protected material | No unauthorized changes to active development checkouts, unrelated data, credentials, or the bot's own effective permissions and schedule. |

These are starting categories, not claims about what is installed on this host. The initial discovery run should propose concrete boundaries for approval rather than silently selecting them.

Enforce hard limits through OS privileges and any necessary constrained privileged entry points. Make approved policy read-only to the executing role, even when its editable source lives in the infra repo. An agent-written policy edit must not become effective merely because it was committed.

Harness permissions are an additional control; OpenCode, for example, documents allow/ask/deny rules for tools and operations. [5] Treat prompt-only restrictions as advisory, and do not describe unrestricted shell access under a powerful identity as a sandbox. Trust granted to privileged installers must be accounted for explicitly.

Retrieved history, release notes, README files, and command output are evidence, not instructions authorized to override the role. Restrict secret access and redact before provider submission or persistence; local inference does not remove the need to protect Git and Slack outputs.

For unattended runs, an approval request should become deferred work, not an interactive prompt waiting forever. Identify the exact target, proposed transition, disruption, and recovery limits. Resume only through an authorized operator action, rechecking current state before execution. Slack is a notification surface by default—not an implicit authorization channel for arbitrary replies.

## 7. Failures, interruption, and self-maintenance

| Situation | Required behavior |
| --- | --- |
| Another maintenance run holds the lock | Skip the duplicate; record it without starting a second writer. |
| Cairn or local changelog recording is unavailable before mutation | Permit inspection, but defer new changes until continuity and recording can be established. |
| Recording fails after a change | Stop new mutations, preserve existing runner evidence, and mark reconciliation pending. Do not rerun the change to recreate its record. |
| A previous run ended during an operation | Inspect native transaction/process state and live results first. Do not blindly replay an intent or assume the operation was canceled. |
| A time or inference budget is exhausted | Stop initiating changes, allow an active native transaction to finish where possible, and checkpoint unfinished work. Do not release the maintenance lock while its mutation process remains active. |
| Git remote or Slack is unavailable | Keep local commits and outcomes; retry publication or delivery separately. Never repeat maintenance as a notification retry. |
| The runner or model fails before the agent can report | Preserve failure through the runner's ordinary status/logging path. Use a non-model delivery path where available. |

Cairn and Git do not form one atomic transaction. Correlate with the run ID and reconcile incomplete records on the next healthy run. No exactly-once execution claim is needed; the important behavior is inspection before retry and explicit uncertainty after interruption.

Protect the dependencies required to complete and report the current run: the active harness, Cairn connectivity, inference service, and essential execution environment. Updates to these should be deferred to an approved maintenance window or performed through an independent execution/recovery path. “Update yourself last” is not, by itself, a recovery design.

A job cannot reliably announce that its own scheduler never launched it. Reuse an independent host-health or scheduler monitor for overdue runs where available; otherwise document the blind spot. Do not build another monitoring platform for this role.

## 8. Reporting and minimum implementation

Slack should carry concise summaries of meaningful verified changes, failures, unresolved uncertainty, and actionable approval requests, with a run ID and changelog reference. Routine no-ops should be quiet. Repeated unresolved notices should be deduplicated or reminded on a policy-defined cadence.

The minimum implementation is a versioned maintenance role and policy in the existing infra repo, one daily job, existing Cairn integration, existing changelog conventions, and whatever small execution/delivery glue the selected profile lacks. Do not prescribe new filenames or directories before inspecting repository conventions.

Make execution limits and maintenance windows explicit deployment settings. Capture elapsed time and reported model usage when available, alongside outcomes and operator interventions. Optimize repeated investigation and noisy reporting rather than treating zero model calls as the objective.

Roll out in three steps:

1. **Discovery-only:** establish installation ownership, exclusions, verification methods, and proposed authority. Writes are limited to maintenance records and proposals.
2. **Limited unattended maintenance:** enable an approved routine scope; exercise failure, interruption, recording, and recovery behavior before broadening it.
3. **Runner/model evaluation:** compare the local option using equivalent observations and read-only proposals. Evaluate missed risks, verification quality, unnecessary work, runtime, and interventions—not just token cost. Never compare by letting two writers update the same host concurrently.

Before calling the deployment ready, demonstrate a quiet no-op, a verified authorized update, preservation of a modified checkout, a clearly recorded failure, interruption reconciliation without blind replay, and visible runner failure when inference is unavailable. Verify that an approval-required operation is actually prevented, not merely discouraged in the prompt.

## 9. Standing mandate

> Maintain this host within the approved scope. Recover relevant context from Cairn, establish current host state, and decide what maintenance is appropriate. Investigate unfamiliar installations and adapt your approach rather than treating previous procedures as unquestionable recipes. Perform authorized changes, verify the affected capabilities, and record meaningful outcomes in the infra repository's changelog. Preserve evidence, unresolved issues, and useful discoveries in Cairn. Respect active work and protected scope. Do not expand your own authority. Leave uncertain or interrupted work explicitly unresolved, and notify the operator when changes, failures, or decisions warrant attention.

**Architectural decision:** build one portable maintenance role on the infrastructure already present. Start with the existing Hermes execution path; substitute a local runner when its demonstrated benefits justify it. Do not create a new updater platform to make that substitution possible.

## Implementation references

The architecture above is a proposal based on the stated environment. These primary sources support the specific harness capabilities mentioned; installed versions, configuration, Cairn interfaces, and infra-repo conventions still need inspection during implementation. Documentation checked September 27, 2026.

[1] [Hermes — Scheduled Tasks (Cron)](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron/)

[2] [Hermes — Slack](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/slack/)

[3] [OpenCode — CLI](https://opencode.ai/docs/cli/)

[4] [OpenCode — Providers](https://opencode.ai/docs/providers/)

[5] [OpenCode — Permissions](https://opencode.ai/docs/permissions/)
