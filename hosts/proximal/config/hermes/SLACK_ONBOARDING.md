# Joining Hermes to Slack — setup runbook

Status: **LIVE + round-trip-verified 2026-08-04** (Agent-mode "hermes" Slack app,
Socket Mode; the Agent replies to DMs). This doc records how it was wired, the
two real root causes hit during bring-up, and how to operate it.

## How the OpenClaw Slack connection works (the reference)

- There is ONE Slack app in the `gearheads` workspace (truckchat.slack.com,
  team `TG10DUY2V`): the `openclaw` app (bot user `U0AS8ABDJ3V`).
- It runs in Socket Mode with two credentials:
    - appToken `xapp-1-A...` (Socket Mode connection)
    - botToken `xoxb-545...` (API calls)
- BOTH the ai-newsroom `SLACK_BOT_TOKEN` and openclaw's `botToken` resolve to
  this same app — the newsroom has been POSTING AS the openclaw bot.
- The openclaw gateway is LIVE on this app right now
  (`openclaw-gateway.service`, v2026.5.7).
- Hermes's Slack adapter (`plugins/platforms/slack/adapter.py`) needs the same
  two-token shape: `SLACK_BOT_TOKEN` (xoxb) + `SLACK_APP_TOKEN` (xapp).

## Decision

Create a NEW Slack app for Hermes so it appears in Slack as "Hermes", not
reusing the openclaw app. Requires one manual admin step on api.slack.com
(Slack requires the workspace admin to approve the OAuth install), then
Hermes wires the resulting tokens and runs its gateway.

## Steps (for the user)

### 1. Create the app
- Open https://api.slack.com/apps -> Create New App -> From an app manifest.
- Pick the `gearheads` (truckchat.slack.com) workspace.

### 2. Paste the manifest
- File already generated: /home/halbritt/.hermes/slack-manifest.json
  (bot name "Hermes", all slash commands, Socket Mode, the required OAuth
  scopes: app_mentions:read, assistant:write, channels:history/read,
  chat:write, commands, files:read/write, groups:history/read, im:*,
  mpim:*, reactions:read, users:read).
- Features -> App Manifest -> Edit -> paste -> Save. Slack prompts to
  reinstall if scopes/slash commands changed.

### 3. Confirm Socket Mode + gather tokens
- App Home / Socket Mode should be ON for the app (manifest sets it).
- Done: two tokens available under the app's OAuth & Permissions / App-Level
  Tokens:
    - Bot token  xoxb-...  (SLACK_BOT_TOKEN)
    - App token  xapp-...  (SLACK_APP_TOKEN)
- Copy both, give them to the agent (they will be written to
  ~/.hermes/.env — secrets only, never committed).

### 4. Wire + start (agent does this)
- Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN in ~/.hermes/.env
  (the Slack platform_toolsets `hermes-slack` is already enabled in config).
- `hermes gateway install`  (install as user systemd service)
- `hermes gateway start`
- `hermes gateway status`    -> expect running + connected

### 5. Verify
- In Slack, DM @Hermes or use /hermes; a reply proves the Socket Mode
  connection and gateway are live.
- Optional: `hermes logs` / `journalctl --user -u hermes-gateway` for errors.

## Notes / guardrails

- Do NOT reuse the openclaw app's tokens for Hermes (conflict described above).
  If the newsroom ever needs to keep posting, it can keep its own bot token;
  if the openclaw app is retired, that's a separate decision.
- The manifest was generated with `hermes slack manifest --name "Hermes"`.
- No live state has been changed during preparation: Hermes gateway is NOT yet
  installed/running, no tokens written, openclaw unaffected.

## Live wiring (done 2026-08-03)

- A dedicated "hermes" Slack app was created for the `gearheads` workspace
  (user `hermes`, member id `U0BMCL982NP`, bot id `B0BND7XHWFJ`) — distinct
  from the existing `openclaw` app, so no Socket Mode conflict (one connection
  per app token, and the identities are separate bots).
- Tokens stored in `~/.hermes/.env` (mode 0600): `SLACK_BOT_TOKEN` (xoxb), 
  `SLACK_APP_TOKEN` (xapp). Secrets live only there, never committed.
- Gateway installed as a user systemd service (linger enabled):
  - `hermes gateway install` → `~/.config/systemd/user/hermes-gateway.service`
  - `hermes gateway start` / `restart` / `status`
- Reachability posture mirrors OpenClaw (open in a small personal workspace):
  - `GATEWAY_ALLOW_ALL_USERS=true` in `~/.hermes/.env`
  - `platforms.slack.dm_policy: open`, `platforms.slack.group_policy: open`
    in `~/.hermes/config.yaml`
  - Tighten later to `SLACK_ALLOWED_USERS=<your-member-id>` if wanted.
- Verify: `hermes gateway status` → active; established outbound TLS to a
  Slack endpoint from the gateway PID; no allowlist-denial warning in
  `journalctl --user -u hermes-gateway`. In Slack, DM @Hermes or `/hermes`.

## Bring-up: the two real root causes (diagnosed 2026-08-04 with DEBUG logs)

The Slack app was installed with only `chat:write` + `channels:history` — the
DMs never reached the box (silent). Chasing it with `-vv` DEBUG proved it and
surfaced a SECOND, hidden failure. Both fixed. Keep these in mind:

1. **The installed app must carry the FULL manifest scopes + event
   subscriptions, and run in Agent (assistant) mode.** A minimal app (or one
   created from a stale/reduced manifest) looks connected (Socket Mode works
   via the xapp token) but silently drops DMs — Hermes only gets them when the
   app subscribes to `message.im` / `assistant_thread_*` and holds the read
   scopes. Symptom in the gateway: `channel_directory: Slack team <T> lacks
   channels:read` and zero `[Slack] event received` DEBUG lines. Fix:
   regenerate with `hermes slack manifest --name "Hermes"` (Agent mode by
   default), paste it at Features → App Manifest, Save, **Reinstall**. This
   grants all scopes (`channels:read`, `im:*`, `groups:*`, `mpim:*`,
   `assistant:write`, …) and subscribes the events in one step.

2. **The gateway needs `OPENROUTER_API_KEY` in `~/.hermes/.env` — NOT just in
   `~/.profile`.** The box exports the key from `~/.profile` (that's how the
   interactive CLI gets it), but the systemd user service never sources a shell
   profile. So a message that *did* arrive failed the LLM call with
   `OpenRouter credential pool has no usable entries (credentials may be
   exhausted)` → the bot replied "Sorry, I encountered an unexpected error."
   Fix: add `OPENROUTER_API_KEY=` to `~/.hermes/.env` (the gateway loads it via
   `load_hermes_dotenv()`), then `systemctl --user restart hermes-gateway`.

   ⚠️ `/proc/<pid>/environ` will NOT show a `.env`-loaded key after start —
   dotenv writes to `os.environ` post-exec; that check is misleading. Test with
   a real DM instead.

Verified round-trip (2026-08-04): DM → `assistant_thread` event → Slack-origin
session (`platform=slack`) → `run_agent` via openrouter/deepseek-v4-flash-0731
→ `[Slack] Sending response` → reply landed in Slack thread. Working at default
logging (DEBUG `-vv` reverted).
