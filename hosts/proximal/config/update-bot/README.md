# Daily software and OS maintenance — proximal

The owner clarified on 2026-09-27 that this job must **perform updates**, including
Hermes, wigolo, llama.cpp, coding harnesses and the underlying OS. The installed
`maintenance-v2` policy supersedes the initial discovery-only deployment. Routine
updates in that scope are standing-authorized; specific unsafe transitions are
held without stopping unrelated updates.

## Scope and ownership

| Target | Approved behavior |
| --- | --- |
| Hermes | Preserve carried commits and native integrations; use supported updates, preserving active sessions. Maintenance runs from an independent frozen runtime. |
| wigolo | Follow its existing upstream-main build/pack/npm installation; preserve configuration and data. Never downgrade to stale npm latest. |
| llama.cpp | Invoke the existing canonical updater under its native lock when warranted; its existing timer stays authoritative. Install binaries without restarting inference. |
| Codex, Claude Code, OpenCode, Agy | Update existing installations on their current stable channels, with native methods. Preserve wrappers, configuration and live session resources. Gemini CLI is covered only if installed. |
| Ubuntu | Refresh metadata and install routine noble/security/updates packages through the fixed root helper. Preserve config files; no removals, release upgrade or reboot. |

The OS helper also checks simulated dependencies. Database, Kubernetes,
container-runtime, NVIDIA/CUDA and third-party package transitions remain held for
separate review. It temporarily installs a policy-rc.d restart hold (only when no
policy already exists), uses needrestart list mode, checks dpkg and observed
package versions afterward, and reports deferred packages and reboot requirements.
Existing apt timers/native locks remain in force. It never changes apt sources.

A busy process is not automatically a blocker for a supported versioned/atomic
install. If an update would replace lazy-loaded runtime files or interrupt work,
defer that target. Dirty/diverged source is preserved; no stash/reset of owner work.
The bot cannot expand this scope, change its schedule, or approve its own proposals.

## Runtime and execution boundary

Daily at **06:30 America/Los_Angeles**, with up to ten minutes jitter and persistent
catch-up. Hermes/OpenRouter `deepseek/deepseek-v4.1-flash`, no model fallback.
The launcher and non-model Slack sender use a root-owned snapshot of Hermes source
and its venv under `/opt/update-bot/`, with editable import paths relocated and
verified. Updating the user installation does not update the active maintenance
runtime. Refresh that snapshot only through an authorized installation, with the
maintenance unit idle. `/etc/update-bot/runtime.json` records the frozen revision.

The host is read-only except the approved user installation/source/cache paths and
private run state. No sudo, arbitrary root shell, user-manager socket or Docker
socket. One polkit rule permits only **starting update-bot-os.service**, whose root
entrypoint accepts no caller commands. Configuration, permissions and the frozen
runtime are root-owned and read-only to the agent. This remains the trusted-host
model: the policy controls semantic scope within writable prefixes and network
APIs; it is not hostile-agent isolation.

All mutations use `operation.py` with native argv, before-state, recovery limits
and verification argv. It durably records intent in Cairn before execution, runs
native commands in an independent process group, and records completion and checks.
The agent still chooses the work and native tools; there is no package-adapter
framework. Actual receipts must support every reported verified change.

The **15-minute deadline closes admission** to new operations. The model ends at
that deadline, but admitted native transactions drain while the launcher retains
the host lock. Systemd does not impose a destructive package-manager timeout.
A 30-minute overrun is independently reported; investigate a hung transaction
rather than kill it blindly. The controller also observes the root OS unit, so
losing its client does not release the maintenance lock prematurely. Memory is
bounded at 12 GiB and CPU at two cores. Thirty turns are guidance because this
Hermes one-shot version does not enforce its max_turns setting. Costs are estimates.

## Continuity, Git and Slack

Run state/evidence: `/var/lib/update-bot/` (0700, halbritt). OS receipts:
`/var/lib/update-bot-os/` (root-owned). Cairn remains the only inventory/history
memory; local JSON is execution evidence, not a competing inventory database.
Interrupted intents must be inspected and reconciled before new mutations. Failed
recording retries the same request identity; notification retries never rerun updates.

The independent monitor runs every 15 minutes and on failure. It publishes
meaningful operation outcomes into this subsystem's `CHANGELOG.md` using a detached
worktree, repository checks, a normal commit and a non-force push to master. Dirty
owner checkouts are preserved. Pending publication is separately reported and
retried; a pushed run marker prevents duplicate commits after uncertain receipt
writes. No-op runs do not create empty commits.

The existing Hermes Slack bot delivers changes/failures/decisions to the operator
DM, independently of the interactive gateway. Delivery is deduplicated; ambiguous
sends stay explicitly uncertain until reconciled. Host/systemd/Slack outages still
need external host monitoring. Policy and cadence are already approved: no repeated
permission requests for routine work.

## Installation and operations

Run `bash install.sh` here. It installs canonical scripts below
`/usr/local/lib/update-bot/`, policy/role/settings/profile below `/etc/update-bot/`,
all `*.service`/`*.timer` under `/etc/systemd/system/`, and `91-update-bot.rules`
under `/etc/polkit-1/rules.d/`. It freezes Hermes and copies the existing provider
and Slack tokens from `~/.hermes/.env` to root-only `/etc/update-bot/*.key`.
Systemd LoadCredential supplies each only to its consumer. Credentials are never
committed; rerun installation after credential rotation.

```sh
sudo systemctl start update-bot.service
systemctl status update-bot.service update-bot.timer update-bot-monitor.timer
cat /var/lib/update-bot/latest.json
journalctl -u update-bot -u update-bot-os -u update-bot-monitor --since today
sudo systemctl disable --now update-bot.timer update-bot-monitor.timer
```

Read-only report repair: `python3 /usr/local/lib/update-bot/update_bot.py reconcile RUN_UUID`.
It validates a saved completed model response and preserves its prior failure
receipt without rerunning host actions. Publication/delivery receipts are separate.
Do not erase an ambiguous delivery marker without checking the Slack DM.

Rollback the automation by disabling its timers and allowing admitted transactions
to drain; remove the installed units/polkit rule and scripts only after idle. Keep
runtime/OS/Cairn evidence. Reverting the automation does **not** downgrade updated
software. Original design and first-stage evidence remain in `ARCHITECTURE.md`,
`INITIAL-SCOPE.md`, and `VERIFICATION.md` as historical provenance.
