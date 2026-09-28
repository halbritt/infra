# Daily maintenance discovery — proximal

The owner authorized deployment on 2026-09-27 after reviewing the maintenance
architecture. This is its **discovery-only first stage**. No software updates,
restarts, migrations, repository edits, or changes to other schedulers are
authorized. The first report proposes a concrete scope for a later decision.

One systemd daily job runs the installed Hermes CLI, explicitly selecting
OpenRouter `deepseek/deepseek-v4.1-flash`. It uses a separate Hermes home, existing
Cairn credentials/collection, and the existing Hermes Slack bot and operator DM.
There is no nested agent, alternate inventory database, or model fallback.

## Canonical files and installation

| Source | Installed path |
| --- | --- |
| `update_bot.py` | `/usr/local/lib/update-bot/update_bot.py` |
| `cairn-mcp` | `/usr/local/lib/update-bot/cairn-mcp` |
| `policy.md`, `role.md`, `hermes.yaml`, `settings.json` | `/etc/update-bot/`, root-owned |
| `update-bot.service`, `update-bot.timer` | `/etc/systemd/system/` |
| `update-bot-monitor.service`, `update-bot-monitor.timer` | `/etc/systemd/system/` |

Run `bash install.sh` from this directory to install the files and refresh the
existing credential copies, then enable the two timers after acceptance checks.
The reviewed source proposal is preserved in `ARCHITECTURE.md`; this README and
installed policy describe the narrower, actually deployed first stage.

Run state and private evidence live in `/var/lib/update-bot/` (0700, halbritt).
`latest.json` is an execution receipt, not installation inventory. Per-run
directories retain the final report, usage estimate, Cairn receipts, and stderr.
Cairn stores the next-run checkpoint. No-op/discovery runs do not produce daily
Git commits. This subsystem and meaningful deployment changes are versioned here;
enabling actual maintenance requires an explicit policy revision and publication
implementation appropriate to the approved scope.

The existing OpenRouter key and Slack bot token are copied at install time from
`~/.hermes/.env` into root-only `/etc/update-bot/{openrouter,slack}.key`; systemd
passes each only to the service needing it via `LoadCredential`. These are copies
of existing credentials, not new identities. Refresh those two files after key
rotation; never commit them. The Cairn hosted profile remains unchanged.

## Boundaries

The service runs as halbritt with a read-only host filesystem, writable private
runtime state and private temporary files, no privilege escalation, no device
access, and no access to the user service-manager bus or Docker socket. The
installed policy/configuration is read-only. Filesystem writes and `sudo` are
mechanically blocked; a live acceptance probe verifies both. Systemd owns the
whole process cgroup and terminates descendants on stop. A host-local flock
prevents overlapping launcher runs; manual execution uses `systemctl start`.

This is the existing **trusted-host model**, not hostile-agent isolation. The
agent has shell inspection and network access; read-only API use, secret avoidance,
signal avoidance, and consequence assessment still depend on the approved role.
Do not claim that a mount namespace makes network APIs read-only. Sensitive known
credential paths are hidden, but this is not an exhaustive secret detector.

Existing updater timers retain ownership. The bot observes them and proposes
changes; it does not rerun, disable, or take them over. Installed versions and
active process versions are separate findings. User-systemd inspection through
the bus is intentionally unavailable inside this profile; unit files and journal
evidence remain readable, and that coverage limitation must be reported.

## Schedule, status, and delivery

Daily at **06:30 America/Los_Angeles**, with up to ten minutes of jitter and
persistent catch-up. Hard budget: 15 minutes for inference/investigation,
18 minutes for the complete service, 4 GiB RAM, 100% of one CPU. These are execution
bounds; usage USD is an estimate, not an enforced dollar cap or actual billing.
The role requests at most 30 turns. Installed Hermes 0.20.5 one-shot construction
does not pass `agent.max_turns` into `AIAgent`, so that setting is advisory here;
the outer timeout and systemd limit are the enforced budget. No upstream runtime
patch is installed for this deployment.
Read-only discovery permits terminating an over-budget process tree. A future
mutation stage must establish transaction-aware draining before it is enabled.

An independent, non-model monitor runs every 15 minutes and after job failure.
It reports failed/partial/interrupted runs, absence of a completed run for 30 hours,
and meaningful findings through `hermes send`; the interactive gateway need not
be running. The monitor records delivery separately, deduplicates findings for
seven days, and records uncertain sends without blindly repeating them. Its
journal retains delivery failures. A host outage or failed systemd/Slack itself
still requires external host monitoring.

## Operations

```sh
sudo systemctl start update-bot.service
systemctl status update-bot.service update-bot.timer update-bot-monitor.timer
sudo cat /var/lib/update-bot/latest.json
journalctl -u update-bot -u update-bot-monitor --since today
sudo systemctl disable --now update-bot.timer update-bot-monitor.timer
```

`latest.json` distinguishes execution status and Cairn checkpoint recording.
Interrupted `running` receipts are reconciled on the next run, with no replay of
an update. The monitor also checks systemd's result, so a killed launcher cannot
silently leave a successful receipt. A report that covers only a bounded subset
must use `partial` and identify what remains unchecked.

If recording fails after the report exists, the next run retries the exact Cairn
request ID before investigating again. To finalize the latest completed model
response after fixing a report-parser issue, use
`python3 /usr/local/lib/update-bot/update_bot.py reconcile RUN_UUID` as halbritt.
This takes the host lock, validates the saved response/usage, preserves the prior
failure receipt, and records the checkpoint without another model or host action.
For a Slack send marked `sending-uncertain`, inspect the operator DM and receipt
before manually resolving `/var/lib/update-bot/delivery.json`; do not blindly retry.

Rollback: disable both timers, stop this discovery service, and remove only the
four installed units and `/usr/local/lib/update-bot` and `/etc/update-bot` files.
Keep state and Cairn records as provenance. No existing gateway or updater changes
are required. See `VERIFICATION.md` for deployed acceptance evidence.
