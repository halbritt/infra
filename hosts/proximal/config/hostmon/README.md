# hostmon — read-only host monitors (agent-ee fleet)

Owner instruction (relayed by agent-521): "I asked for agents to be deployed on each host to report the host status".
Owner/lifecycle: agent-449. This directory is the versioned source. The deployed copy is `~/.local/share/hostmon/`
on each host, and the working copy is under `/tmp/agent-ee-burndown-20261017/hostmon/` (fleet tooling, not a repo).

## Files
- `probe.py` — deterministic sampler (load, PSI, memory/swap, disk, admission leases, strict suites, containers,
  zombies). Run locally or `ssh HOST python3 - < probe.py`. Never reads secrets or environments; a missing probe reads UNKNOWN.
- `hostmon.py run HOST KIND ACCOUNT [--via-ssh H]` — per-host monitor: sample every 60 s into
  `~/.local/state/hostmon/HOST/{samples,alerts}.jsonl`; model turns only on new alert transitions, otherwise at most
  every 5 min when the job/queue digest changes; session rotates every 40 turns. KIND is `sonnet` (Claude, tools
  disallowed) or `luna` (gpt-6-luna via `codex exec`, `-c sandbox_mode="read-only"`).
- `hostmon.py forward HOSTMAP` — proximal forwarder: publishes new outbox lines as Cairn notices to 449 (475 when
  addressed, 521 when critical) with persisted idempotent request IDs, and aggregates `~/.local/state/hostmon/capacity.json`.
- `brief.txt` — the model's standing brief (read-only; never kills, restarts, renices, bypasses admission or runs tests).

## Deterministic alerts (independent of the model)
- `monitor-model-failed` / `monitor-model-recovered` — first failed model turn raises one warning to 449; the first
  successful turn afterwards sends the clearance. Quota/auth failures stop the monitor with `route-unavailable`.
- `monitor-stale-HOST` — a host's newest sample is older than 300 s (cleared with `-cleared`).
- `idle-host-queued-work` — some hosts have queued admission work while others report free units (cleared with `-cleared`).

## History
- 2026-10-22: launched by agent-449 on proximal, peecee-wsl, archon, talos, and agent-ee-gate-c4 (sampled from proximal).
- 2026-10-23: `codex exec resume` rejects `--sandbox`; every resumed luna turn failed and the failure was only written
  to summaries. Fixed with the `sandbox_mode` config key; failed turns now alert (agent-521 request 9e692914).
  Added the capacity aggregator and stale/idle-host alerts. Verified resumed luna turns on talos, peecee-wsl and c4
  (sessions created 2026-10-22T22:19Z, resumed OK 2026-10-23T02:37Z) and an injected failure/recovery drill
  delivered through the forwarder to Cairn.
