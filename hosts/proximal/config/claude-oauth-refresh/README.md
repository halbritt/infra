# claude-oauth-refresh

Keeps every local Claude Code profile's OAuth access token fresh between
sessions. A systemd user timer runs a stdlib Python script every 15 minutes;
the script renews any profile whose token expires within 45 minutes.

## Why (2026-09-14)

Claude Code refreshes its claude.ai OAuth token lazily: only while a session is
running, and only once the token is within five minutes of expiry (the CLI's
`isOAuthTokenExpired` check, 300000 ms). Tokens live eight hours. Between
sessions the token lapses, and everything else that reads the profile gets 401s
until someone starts the CLI: the agent-usage dashboard flagged `claude-harm`
as "token expired" for ~35 minutes on 2026-09-13/14 while the CLI, once
started, was fine. The CLI re-reads `.credentials.json` whenever its mtime
changes, so an external renewal is picked up by running sessions instead of
fought over.

## What it does

`claude-oauth-refresh.py` (symlinked to `~/.local/bin/claude-oauth-refresh`),
for each profile (`~/.claude`, `~/.claude-harm` by default):

1. Reads `.credentials.json`; skips profiles with no `refreshToken`.
2. Skips if `expiresAt` is more than 45 minutes away (`--lead-minutes`,
   `--force` overrides). Errors out loudly if the refresh token itself has
   expired (that needs `claude auth login`).
3. POSTs `grant_type=refresh_token` to `https://platform.claude.com/v1/oauth/token`
   with Claude Code's public client id and the stored scopes, exactly as the
   CLI does.
4. Re-reads the file and aborts if the refresh token changed underneath it (a
   concurrent CLI refresh wins), otherwise rewrites the `claudeAiOauth` block
   atomically (temp file + rename, mode 0600), preserving every other key such
   as `mcpOAuth`. The provider rotates the refresh token on every renewal, so
   the re-read guard matters.

5. Selects no local harness mirrors: `MIRRORS` is empty after the 2026-10-24
   Striatum migration to Talos. Proximal's retained Striatum store was read-only
   until the owner requested removal of that mount on 2026-10-25.
   Writing those retired consumer homes raised `EROFS` and stopped the run
   before the later source profile and remote mirrors were reached.
   The source profiles remain on Proximal. `--no-mirror` renews only.

6. Pushes the same access-token-only copy of `~/.claude` and `~/.claude-harm`
   to the same paths on every host in `REMOTE_HOSTS` (`peecee-wsl`, `archon`, `agent-ee-gate-c4` since 2026-10-22, `talos` since 2026-10-22)
   over ssh, on every run. See [Remote worker hosts](#remote-worker-hosts-2026-10-21).
   `--no-remote` skips this step.

Nothing is logged but the profile path and minutes-to-expiry. No token material
reaches the journal or this repo.

## Why mirrors get an access token and never a refresh token (2026-09-14)

The striatum harness profiles have no login of their own. On 2026-09-14 an
agent gave `harness-config/claude-code` a byte-identical *copy* of `~/.claude`'s
refresh token; the 08:00 renewal rotated the source and the copy was dead by
08:02. Two holders of one refresh token cannot both survive a rotation — the
same failure the Council credential-rotation note records.

A mirror therefore receives only the fields in `MIRRORED_FIELDS`
(`accessToken`, `expiresAt`, `scopes`, `subscriptionType`, `rateLimitTier`),
and any `refreshToken`/`refreshTokenExpiresAt` already in the mirror is dropped
on write. The mirror holds a read-only lease on the source's session: it can
authenticate, it cannot rotate, so it can never invalidate the source. Tokens
last eight hours and the timer rewrites every fifteen minutes at a 45-minute
lead, so a mirror is never within reach of expiry. Verified 2026-09-14: both
mirrors report `loggedIn: true` on their own account and return PROBE-OK from
a live `claude -p` run with no refresh token present.

Mirroring the `oauthAccount` block matters for the same reason the 2026-09-14
restore went wrong: it asserted the two profiles held different accounts on the
strength of a stale `.claude.json` while the tokens said otherwise. The
authoritative check is the token itself —
`GET https://api.anthropic.com/api/oauth/profile` with
`Authorization: Bearer <accessToken>` and `anthropic-beta: oauth-2025-04-20`
returns `account.uuid` and `organization.name`.

## Remote worker hosts (2026-10-21)

Agent workers also run on `peecee-wsl` and `archon` (same user, `halbritt`) on
the owner's subscription logins. Earlier on 2026-10-21 full credential files,
refresh tokens included, were copied there from proximal. With rotating refresh
tokens that makes three holders of one lineage: whichever host renews first
signs the other two out. Remote hosts are now mirrors in the sense above.
proximal is the only refresh-token holder, and every other host gets an
access token it can use but cannot rotate.

| Account files | What each remote gets | Mechanism |
|---|---|---|
| `~/.claude/.credentials.json`, `~/.claude-harm/.credentials.json` | `claudeAiOauth` reduced to `MIRRORED_FIELDS`; `refreshToken`/`refreshTokenExpiresAt` dropped; other keys kept. The source `oauthAccount` block goes into `~/.claude.json` / `~/.claude-harm/.claude.json` when that file already exists there. | this timer, every run |
| `~/.codex/auth.json`, `~/.codex-harm/auth.json`, `~/.codex-3/auth.json` | proximal's file with `tokens.refresh_token` set to `""` | [`codex-auth-mirror/`](../codex-auth-mirror/README.md), sibling 15-minute timer |
| `~/.gemini/oauth_creds.json` (+ `google_accounts.json`, `settings.json`) | the full copy, left as is | none needed: Google refresh tokens do not rotate (see the codex-auth-mirror README) |

How a run reaches a remote: one `ssh -o BatchMode=yes <host> python3 -I -c
<writer>` per host, with the job list on stdin, so no token material is in any
argv or in the journal. The writer reads the remote file, drops any refresh
fields, overlays the mirrored fields, and writes only when something changed
(temp file in the same directory, `fsync`, mode `0600`, `rename`). The journal
line is per host: `~/.claude mirrored|current[+account]`. A host that is
unreachable, times out (60 s) or fails logs `<host>: remote mirror failed;
retrying next tick` and nothing else. It never fails the unit or blocks the
local refresh.

A remote copy stays valid without a refresh token because this timer renews
45 minutes before expiry and pushes in the same run. The remote CLI's own
refresh window (five minutes before expiry) is therefore never reached while
proximal and the host are both up. If a host is offline for longer than a
token lifetime (eight hours), the token there lapses. Any refresh attempt on
that host fails harmlessly (it has nothing to rotate), and the first tick after
it comes back restores it. A login done on a remote host is overwritten by the
next push: remote hosts do not keep their own Claude logins.

Verified 2026-10-21 11:42 PDT after the first run (both hosts reported
`mirrored`): on both hosts and both profiles the credentials file is mode
`0600`, contains no key matching `refresh` anywhere (checked with `jq paths`,
values never printed), and `CLAUDE_CONFIG_DIR=<dir> claude auth status`
reports `loggedIn: true`, `authMethod: claude.ai`, on the account of the
matching proximal profile. The second run reported `current` for every
profile. A deliberately unreachable host logged one warning line and returned
normally.

To add a host, append it to `REMOTE_HOSTS` here and in `codex-auth-mirror.py`.
It needs key-based `ssh <host>` from proximal without a prompt (BatchMode) and
`python3` on its PATH.

## Units

| File | Installed at |
|---|---|
| `claude-oauth-refresh.service` | `~/.config/systemd/user/` (oneshot, `UMask=0077`) |
| `claude-oauth-refresh.timer` | `~/.config/systemd/user/` — `*:0/15`, `OnBootSec=2min`, `Persistent=true` |
| `claude-oauth-refresh.py` | `~/.local/bin/claude-oauth-refresh` (symlink into this dir) |

```bash
systemctl --user list-timers claude-oauth-refresh.timer
journalctl --user -u claude-oauth-refresh -f
claude-oauth-refresh --dry-run            # report without touching anything
claude-oauth-refresh --force ~/.claude    # renew one profile now
```

Install / reinstall:

```bash
ln -sfn ~/git/infra/hosts/proximal/config/claude-oauth-refresh/claude-oauth-refresh.py ~/.local/bin/claude-oauth-refresh
cp ~/git/infra/hosts/proximal/config/claude-oauth-refresh/claude-oauth-refresh.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now claude-oauth-refresh.timer
```

Verified 2026-09-14 00:39 PDT with `--force ~/.claude`: new 8 h token, rotated
29-day refresh token, `claude auth status` still logged in, and the agent-usage
dashboard (which re-checks immediately on a credential fingerprint change)
went live on the new token within seconds.

## Adding a profile

Pass extra config dirs on the command line, or edit `DEFAULT_PROFILES` in the
script and reinstall. Profiles logged in with an API key or
`CLAUDE_CODE_OAUTH_TOKEN` have no refresh token and are skipped.

## Caveats

- The token endpoint, client id and beta header are Claude Code's private
  contract; a CLI update may change them. The script fails closed (non-zero,
  file untouched) on any non-200 or malformed response.
- If a refresh ever returns `invalid_grant`, the refresh token is dead and the
  profile needs `claude auth login`; the unit will fail every 15 minutes until
  then, which is the intended signal.
