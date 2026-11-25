# Striatum harness credential delivery

Talos receives access-only Claude profiles from proximal's existing
[`claude-oauth-refresh`](../../../proximal/config/claude-oauth-refresh/README.md)
timer. The Striatum harnesses must read those profile files through symlinks:

| Harness file under `~/.local/share/striatum/harness-config/` | Target |
|---|---|
| `claude-code/.credentials.json` | `~/.claude/.credentials.json` |
| `claude-harm/.credentials.json` | `~/.claude-harm/.credentials.json` |

Proximal's 15-minute Claude mirror runs the link installer on Talos after each
delivery, including when the source files are already current. A failed check
appears in Proximal's `claude-oauth-refresh.service` result. To run the same
check manually from the Talos infra checkout:

```sh
python3 hosts/talos/config/striatum/install-profile-links.py
```

The installer validates both source profiles before replacing credentials with
links. It refuses refresh-token fields, missing or expired access tokens, and
permissions other than 0600. It prints no credential values. Running it again
verifies existing links. It does not log in, refresh credentials, start jobs,
clear exhaustion observations or restart services.

The source-only refresher remains on proximal. Never copy refresh credentials
onto Talos, and keep proximal's retired Striatum data read-only.

## Driving-agent context replacement

The Principal requested a fresh Talos driving agent every 48 hours on
2026-11-25, with a saved handoff before replacement, and clarified the model
as `gpt-6.2-astra` on the `codex-harm` ChatGPT subscription. This replaces the
stopped codex-3 conversation, not the deterministic compiler Driver.

Canonical files here install as follows:

| Source | Installed path under `~` |
|---|---|
| `rceb-supervisor.py` | `.local/libexec/striatum-rceb-supervisor.py` |
| `driving-agent.txt` | `.config/striatum/rceb-supervisor/driving-agent.txt` |
| `striatum-rceb-supervisor.service` | `.config/systemd/user/striatum-rceb-supervisor.service` |
| `striatum-rceb-supervisor.timer` | `.config/systemd/user/striatum-rceb-supervisor.timer` |

The private operational `rotation.json` beside the prompt contains `repo`,
`codex_home`, `model`, `root_inbox`, and `initial_handoff` (Cairn record/version).
It contains no credential. Keep the existing profile token selector and mirrored
access-only auth. Archive the old service, script, prompt, identity and codex-3
drop-in before installation; remove that superseded environment drop-in.

The timer checks every 30 seconds, maintaining presence through the existing
session API without installing a Talos presence watcher. Bounded agent turns
are at least two minutes apart. At age 47.5 hours it requests a handoff and
requires the exact thread/generation, no unresolved effects, and a readable
saved Cairn version. At 48 hours it retires that identity and starts a NEW
conversation, carrying selected handoff context only. Scheduling granularity
and handoff failure can delay replacement; no new work begins while handoff
is pending. A failed/uncertain turn stops the agent controller, preserves its
attempt evidence and refuses automatic replay or provider fallback. The native
Driver and its existing timers remain independent.

Each new conversation first completes a read-only bootstrap and receives its
own registered Cairn identity. It sends root a readiness request. Root verifies
the nonce round trip and exact execution before activating that generation:

```sh
~/.local/libexec/striatum-rceb-supervisor.py status
~/.local/libexec/striatum-rceb-supervisor.py activate --generation UUID
systemctl --user start striatum-rceb-supervisor.service
```

This is the autonomous root supervisor's readiness check, not a new Principal
approval. Root must handle it for every replacement; an unavailable root leaves
the fresh agent ready but inactive. Inspect `rotation/state.json` under
`~/.local/state/striatum/rceb-supervisor/` and the per-attempt events on failures.
Do not clear `in_flight` until the original process and native effects have
been reconciled. Authentication/quota failure requires repair on the existing
subscription route, never a model/account/API fallback. Recurring operation
starts with `systemctl --user enable --now striatum-rceb-supervisor.timer`.
