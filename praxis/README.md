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
- `PRAXIS_LOCAL_MODEL_ENABLED` — Tier-1 cognition switch (see 2026-06-24 lesson: it must
  live HERE to survive restarts, not in a shell).
- **Plane standing sync (ADR 0014, owner-enabled 2026-07-02)** — work items created in
  the personal Plane project (`plane.harm.org`, workspace `harm`, project `PRAXIS`)
  import as Praxis reminders; the poll is read-only toward Plane, watermarked, no
  backfill. Variable names: `PRAXIS_PLANE_STANDING_SYNC=1` (master switch — set `0` +
  restart praxisd as the emergency disable), `PRAXIS_PLANE_STANDING_SYNC_SCOPE=personal`,
  `PRAXIS_PLANE_STANDING_SYNC_ENABLEMENT=ADR-0014`, `PRAXIS_PLANE_PRODUCTION_LIVE=1`,
  `PRAXIS_PLANE_PRODUCTION_ENABLEMENT=ADR-0013`, and `PRAXIS_PLANE_PERSONAL_ENV`
  pointing at `~/.config/plane/repos/praxis-personal.env` (`0600`, holds the Plane API
  token — outside git). Verify: `journalctl --user -u praxisd | grep "plane standing sync"`
  (compact handles only) and the `plane_sync_watermarks` table in db `praxis`.

The Postgres DSN in the units is peer-auth (`postgresql://halbritt@/praxis?host=/var/run/postgresql`)
— **no password**, authenticated by the unit's OS user, so it is config not credential.

## Live Slack app (account-level fact, not a secret)

App `praxis` (`U0BC0EN59DF`, app id `A0BBS89SPGB`) in Slack workspace/team
**`gearheads`** (`TG10DUY2V`). The default channel `#praxis-chat` (`C0BBH54SVST`) is a
**private** channel — so the load-bearing message scope is `groups:*`, not `channels:*`
(a public-channel assumption cost two reinstalls; check `is_private` before scoping).

- **Bot scopes** (granted, via `auth.test` `x-oauth-scopes`): `chat:write`, `im:write`,
  `app_mentions:read`, `im:history`, `channels:history`, `groups:history`. Socket Mode is
  enabled and uses the `xapp-` app token's `connections:write`.
- **Subscribed bot events:** `app_mention`, `message.im`, `message.channels` (public),
  `message.groups` (private — the one that delivers plain `#praxis-chat` messages).
- Capture paths verified live 2026-06-20: **@mention** (`app_mention`), **DM**
  (`message.im`), and **plain private-channel message** (`message.groups`).

**Editing the app config** (scopes/events) is done via the **App Manifest API** with a
**configuration token** (`xoxe.xoxp-…`, minted by the owner at api.slack.com/apps → "Your
App Configuration Tokens", ~12h TTL — the bot/app tokens are `not_allowed_token_type`
here): `apps.manifest.export` → edit `oauth_config.scopes.bot` /
`settings.event_subscriptions.bot_events` → `apps.manifest.update`. Any **scope** change
returns `permissions_updated: true` and needs a one-click **Reinstall** (OAuth re-consent);
**event** changes apply live to the running Socket Mode connection (no restart). Bot tokens
do **not** rotate on reinstall (the same `xoxb-` gains the new scope).

## The wall (why this is safe to expose to a cloud channel)

Slack is a public/cloud channel, so by Praxis invariant **an inbound Slack message is
only ever a *capture* (untrusted ingest), never an attestation** — it cannot cross the
said/inferred wall (I1) and cannot trigger an action (I3). Outbound is always
egress-gated (I4, `verify_no_egress_leak`, fail-closed). "Public/cloud" here means trust,
not Slack channel visibility — a *private* Slack channel is still an untrusted cloud
surface and gets the same treatment. Verified live 2026-06-20: inbound message (@mention
*and* plain private-channel message) → `inbox` row → `praxisd` drain → capture with
`actor=[]`, `locality=cloud`, **0 attestation_events** → egress-gated ack returned to Slack.

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
