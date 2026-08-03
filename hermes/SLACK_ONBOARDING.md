# Joining Hermes to Slack — setup runbook

Status: PREPARED, not yet connected. This is the new-Hermes-app path (option 1),
chosen over reusing OpenClaw's tokens because that would disconnect the
currently-running OpenClaw bot from Slack (Socket Mode = one connection per
app token, and the app identity "openclaw" would be shared).

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
