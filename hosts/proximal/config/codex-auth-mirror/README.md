# codex-auth-mirror

Keeps proximal the only holder of each Codex CLI refresh token while agent
workers on `peecee-wsl` and `archon` use the same ChatGPT logins. A systemd user
timer runs a stdlib Python script every 15 minutes. It has each local Codex
home renew itself well before expiry, through the CLI, and then pushes a copy
of `auth.json` with the refresh token blanked to the remote hosts.

The Claude counterpart is the remote step of
[`claude-oauth-refresh`](../claude-oauth-refresh/README.md#remote-worker-hosts-2026-10-21);
read that for the full rationale. In short, a copied refresh token is a second
holder of a rotating lineage, and whichever host renews first signs the other
out.

## Why (2026-10-21)

Earlier on 2026-10-21 the full `~/.codex/auth.json`, `~/.codex-harm/auth.json`
and `~/.codex-3/auth.json` (refresh tokens included) were copied from proximal
to both remote hosts. Before the first push, all three hosts held byte-identical
refresh tokens for every profile (compared by SHA-256, values never printed).
Nothing had rotated yet. The first push (11:41 PDT) blanked them on both remotes.

## How the Codex CLI refreshes (source: `~/git/codex-upstream` at `rust-v0.163.0`)

The source is the version installed on proximal and archon. File:
`codex-rs/login/src/auth/manager.rs`, unless another file is named.

- **When.** `should_refresh_proactively` renews when the access token's JWT
  `exp` is within `CHATGPT_ACCESS_TOKEN_REFRESH_WINDOW_MINUTES = 5`. Only if
  `exp` cannot be parsed does it fall back to `last_refresh` older than
  `TOKEN_REFRESH_INTERVAL = 8` days. A 401 also triggers recovery
  (`UnauthorizedRecovery`): it reloads `auth.json` from disk first and asks the
  authority only if the reload did not help. The CLI renews only while a
  process is running. Nothing renews a profile that nobody is using.
- **Lifetime.** The access tokens' `exp - iat` is 240 h (ten days) on all three
  profiles. The `id_token` lives one hour but is not used for authentication.
- **Rotation.** `request_chatgpt_token_refresh` POSTs to
  `https://auth.openai.com/oauth/token`, and `persist_tokens` stores any
  returned `refresh_token`. The server reports reuse of an already-rotated
  token as `refresh_token_reused` (`RefreshTokenFailedReason::Exhausted`, "your
  refresh token was already used"), which is a permanent failure. Observed on
  2026-10-21 11:42 PDT: a forced renewal of `~/.codex` returned a new refresh
  token (SHA-256 changed), a new 10-day access token, and a new `last_refresh`.
  So refresh tokens rotate, and the auth server detects reuse.
- **Concurrent processes.** `refresh_token()` does a guarded reload first. If
  `auth.json` on disk differs from the cached copy, it adopts the disk copy and
  does not refresh. Long-running proximal processes (the app-server daemons)
  therefore pick up a renewal done by another process instead of replaying the
  old refresh token.
- **No refresh token.** `TokenData.refresh_token` is a required `String`
  (`codex-rs/login/src/token_data.rs`, no serde default). An `auth.json`
  without the key fails to parse (`missing field refresh_token`). With
  `"refresh_token": ""` the CLI loads normally and authenticates with the
  access token (this is the same shape `from_external_access_token` builds). A
  refresh attempt with an empty token is rejected by the server. The CLI logs
  "Failed to refresh token", keeps using the cached auth, and adopts the next
  pushed file at its next guarded reload or 401 recovery. A remote can
  therefore never rotate, and never invalidate proximal.

## What it does

`codex-auth-mirror.py` (symlinked to `~/.local/bin/codex-auth-mirror`), each run:

1. For each of `~/.codex`, `~/.codex-harm`, `~/.codex-3`: if the access token
   expires within `LEAD_HOURS = 72`, start that profile's own CLI
   (`CODEX_HOME=<profile> ~/.npm-global/bin/codex app-server`) and send
   `initialize` and then `account/read` with `refreshToken: true`. The protocol
   documents this request as "triggers the normal refresh-token flow" (see
   `codex-rs/app-server-protocol/src/protocol/v2/account.rs`). The CLI rotates
   and persists the tokens itself, so this script never writes proximal's
   `auth.json`. Success is judged by re-reading the file: the `exp` claim must
   have moved forward, or the unit fails. That failure is the signal to look.
   72 h is seven days into a ten-day token, ahead of the eight-day
   `last_refresh` interval that older CLIs use. peecee-wsl runs 0.153.4, whose
   source is not on this box.
2. For each host in `REMOTE_HOSTS` (`peecee-wsl`, `archon`, and since 2026-10-22 `agent-ee-gate-c4`): one
   `ssh -o BatchMode=yes <host> python3 -I -c <writer>`, with the jobs on stdin.
   Each job is proximal's `auth.json` with `tokens.refresh_token = ""`. The
   writer replaces the remote file only when it differs (temp file, `fsync`,
   `0600`, `rename`). Each file is therefore pushed again within 15 minutes of
   any change on proximal, and a renewal by step 1 is pushed in the same run. An
   unreachable or failing host logs `<host>: remote mirror failed; retrying next
   tick` and never fails the unit. An expired or unreadable access token is not
   pushed.

Nothing is logged but profile paths, days to expiry and per-host states. No
token material is passed in argv or written to the journal or this repository.
A login done on a remote host is overwritten at the next push.

## Verification (2026-10-21)

- First push (`--no-renew`): both hosts reported `mirrored` for all three
  profiles, and a second run reported `current` for all of them. On both hosts
  each `auth.json` is mode `0600` with `tokens.refresh_token == ""` (checked
  with `jq`, values never printed), and `CODEX_HOME=<dir> codex login status`
  prints `Logged in using ChatGPT` for all three profiles.
- Forced CLI renewal of `~/.codex` on proximal: refresh token rotated, new
  `exp` 10.0 days out, `codex login status` still logged in. The new copy was
  pushed to both hosts in the same run.
- Live use with no refresh token: on archon, `CODEX_HOME=~/.codex-3 codex exec`
  answered `PROBE-OK`. On peecee-wsl, `CODEX_HOME=~/.codex codex exec` reached
  the backend authenticated and was refused only by that account's usage limit
  (a quota answer, not a 401).
- A deliberately unreachable host logged one warning and returned normally.
- The installed unit ran clean (`Result=success`) with all profiles `current`.

## Gemini: no mirror needed

`~/.gemini/oauth_creds.json` (with `google_accounts.json` and `settings.json`)
stays a plain copy on the remote hosts. Google OAuth refresh tokens for this
installed-app flow do not rotate. The refresh response carries a new access
token, not a new refresh token, so any number of hosts can hold the same
refresh token and renew independently. The client confirms this. In
gemini-cli 0.61.0 (archon, `bundle/chunk-5FZXKDXH.js`), google-auth-library's
`OAuth2Client.refreshTokenNoCache` posts `grant_type=refresh_token` to
`https://oauth2.googleapis.com/token`. Both `refreshAccessTokenAsync` and the
request-metadata path then set `tokens.refresh_token =
this.credentials.refresh_token`, so the stored refresh token is always the
original one. gemini-cli's `tokens` listener (`cacheCredentials`) rewrites
`oauth_creds.json` with that object. A Google rotation would therefore have
broken every gemini-cli install, not only copied ones.

Gemini copies do share one failure mode: revoking the grant (removing the app's
access in the Google account, or a password reset that revokes tokens) kills
every copy at once, and each new login counts towards Google's limit of live
refresh tokens per account and client. gemini-cli is installed only on archon.
proximal and peecee-wsl hold the file but have no `gemini` binary.

## Units

| File | Installed at |
|---|---|
| `codex-auth-mirror.service` | `~/.config/systemd/user/` (oneshot, `UMask=0077`, `TimeoutStartSec=10min`) |
| `codex-auth-mirror.timer` | `~/.config/systemd/user/` — `*:0/15`, `OnBootSec=3min`, `Persistent=true` |
| `codex-auth-mirror.py` | `~/.local/bin/codex-auth-mirror` (symlink into this dir) |

```bash
systemctl --user list-timers codex-auth-mirror.timer
journalctl --user -u codex-auth-mirror -f
codex-auth-mirror --dry-run                 # report without renewing or pushing
codex-auth-mirror --no-renew                # push only
codex-auth-mirror --force '~/.codex'        # renew one profile now (quote the ~)
```

Install / reinstall:

```bash
ln -sfn ~/git/infra/hosts/proximal/config/codex-auth-mirror/codex-auth-mirror.py ~/.local/bin/codex-auth-mirror
cp ~/git/infra/hosts/proximal/config/codex-auth-mirror/codex-auth-mirror.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now codex-auth-mirror.timer
```

## Caveats

- `account/read` with `refreshToken: true` is a documented app-server request,
  but the app-server protocol changes between releases. If a CLI update breaks
  it, step 1 fails loudly (`CLI renewal did not produce a newer token`) while
  the access token still has about three days left.
- If proximal is down for more than three days, profiles are not renewed
  until it comes back. Remote tokens then lapse at their ten-day expiry. Do not
  log in on a remote host to work around this: that login is overwritten at
  the next push. Fix proximal instead.
- A profile that loses its refresh token on proximal (`refresh_token_reused`,
  revoked, expired) needs `codex login` there. The next run pushes the result.
