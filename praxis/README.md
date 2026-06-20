# praxis/ — Praxis executive-function daemon + connectors

Desired-state for **Praxis** on `proximal`: a local-first executive-function daemon
(`praxisd`) plus its inbound/outbound message connectors. The codebase lives at
`~/git/praxis` (repo `github.com/halbritt/praxis`); this directory captures only the
**host integration** — the systemd user units, where secrets live (by name, never
value), and how to verify/operate it on the box.

Like `striatum/`, Praxis is a local-first daemon: a systemd **user** unit, peer-auth
Postgres, tailnet-only trust surface.

## Services on this box

| unit (user) | what it is | bind / trust |
|---|---|---|
| `praxisd.service` | the daemon: SAFE→ARMED boot, ticks the loop, drains the `inbox` dock into captures, runs the wall/redaction gates | local; Postgres peer-auth `:5432` db `praxis`; tailnet-only UI/API (I5) |
| `praxis-slack.service` | inbound Slack **transport** — Socket Mode (outbound WebSocket, *no public ingress*); captures into the shared `inbox`, posts an egress-gated ack back | outbound WSS to Slack; writes the same `praxis` DB |

Run **exactly one** `praxis-slack` instance — Slack load-balances events across
connections, so a second listener would split the event stream.

## Repo file → install path

| repo (canonical) | installed copy (box) |
|---|---|
| `praxisd.service` | `~/.config/systemd/user/praxisd.service` |
| `praxis-slack.service` | `~/.config/systemd/user/praxis-slack.service` |

Canonical-in-repo, installed-on-box: edit here, then
`cp praxis/<unit> ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user restart <unit>`.
The *application* code (units' `ExecStart` runs `python3 -m praxis[.slack_socket]`
from the `~/git/praxis` checkout, `PYTHONPATH=src`) is versioned in the praxis repo,
not here.

## Secrets — by name only, never value

**No credentials in this repo** (the one rule). Praxis secrets live in
`~/.config/praxis/praxisd.env` (`0600`, user-owned, **outside both git repos**), loaded
by `praxis-slack.service` via `EnvironmentFile=-` (the leading `-` makes a missing file
non-fatal — the handler then exits 78 and nothing can egress). The variable *names*:

- `PRAXIS_SLACK_APP_TOKEN` — `xapp-…` app-level token; **the load-bearing credential**
  for Socket Mode (needs scope `connections:write` **and** Settings→Socket Mode toggled
  ON in the Slack app). Distinct from the bot token / signing secret.
- `PRAXIS_SLACK_BOT_TOKEN` — `xoxb-…` bot token (`chat:write`, used for the ack + auth.test).
- `PRAXIS_SLACK_SIGNING_SECRET` — v0 request-signing secret (Events-API path; unused by
  Socket Mode but kept for the webhook fallback).
- `PRAXIS_SLACK_BOT_USER` — the bot's own user id (`U…`), for the echo guard (prevents
  reply loops). Live value: `U0BC0EN59DF`.
- `PRAXIS_SLACK_CHANNEL` — default post channel (`#praxis-chat`).
- `PRAXIS_TWILIO_*` / `PRAXIS_SMS_OWNER` — SMS connector (RFC 0019), placeholders for now.

The Postgres DSN in the units is peer-auth (`postgresql://halbritt@/praxis?host=/var/run/postgresql`)
— **no password**, authenticated by the unit's OS user, so it is config not credential.

## Live Slack app (account-level fact, not a secret)

App `praxis` (`U0BC0EN59DF`) in Slack workspace/team **`gearheads`**, channel
`#praxis-chat`. Current scopes reliably receive events via **@mention or DM**; plain
channel messages additionally need `channels:history` + the `message.channels` bot event.

## The wall (why this is safe to expose to a cloud channel)

Slack is a public/cloud channel, so by Praxis invariant **an inbound Slack message is
only ever a *capture* (untrusted ingest), never an attestation** — it cannot cross the
said/inferred wall (I1) and cannot trigger an action (I3). Outbound is always
egress-gated (I4, `verify_no_egress_leak`, fail-closed). Verified live 2026-06-20:
inbound @mention → `inbox` row → `praxisd` drain → capture with `actor=[]`,
`locality=cloud`, **0 attestation_events** → egress-gated ack returned to Slack.

## Operate

```bash
systemctl --user status praxisd praxis-slack
journalctl --user -u praxis-slack -f          # tail the Slack listener
systemctl --user restart praxis-slack         # after editing the env file or unit
# capture/processing state:
psql "postgresql://halbritt@/praxis?host=/var/run/postgresql" \
  -c "select connector_id,count(*),max(received_at) from inbox group by 1;"
```

Both units are `enabled` (`WantedBy=default.target`) with lingering on, so they start
at boot. `praxisd` is `Restart=always` (Type=notify + 30s watchdog); `praxis-slack` is
`Restart=on-failure` (a missing token is a deliberate fail-closed exit 78, not a crash
to restart-spin).
