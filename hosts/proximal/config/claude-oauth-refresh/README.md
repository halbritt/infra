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

Nothing is logged but the profile path and minutes-to-expiry. No token material
reaches the journal or this repo.

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
