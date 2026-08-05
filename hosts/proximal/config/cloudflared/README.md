# proximal/cloudflared - Cloudflare Tunnel edge

Desired-state and provenance for the Cloudflare Tunnel that exposes selected
`harm.org` hostnames from host `proximal`.

## At A Glance

| | |
|---|---|
| tunnel name | `token-dashboard` |
| tunnel ID | `e6e104cb-75a2-4ccc-a46f-aca2c725328c` |
| unit | `cloudflared.service` |
| installed config | `/etc/cloudflared/config.yml` |
| user-scope fallback config | `/home/halbritt/.cloudflared/config.yml` (not used by the unit; see below) |
| credentials | `/etc/cloudflared/e6e104cb-75a2-4ccc-a46f-aca2c725328c.json` (root-only, never committed) |

## Two configs, one tunnel

The same tunnel has a second config under `~/.cloudflared/`, left over from the
original `cloudflared tunnel login` bootstrap. The unit is immune to it — its
`ExecStart` passes `--config /etc/cloudflared/config.yml` explicitly — but an
ad-hoc `cloudflared tunnel run` as `halbritt` picks the home-dir file up instead.

The two files must therefore carry **identical `tunnel` and `ingress` blocks**.
Only `credentials-file` differs, and it has to: the `/etc` credential is
`root:root 0400`, so a user-scope run needs the `halbritt:halbritt 0400` copy in
`~/.cloudflared/`. Edit both whenever ingress changes.

## Ingress

The final catch-all rule must remain `http_status:404`.

**`harm.org` and `www.harm.org` were removed 2026-07-25** — the site moved to
Cloudflare Pages ([`halbritt/harm-org`](https://github.com/halbritt/harm-org));
see [`../harm-enterprises`](../harm-enterprises/). They now resolve to
`harm-org.pages.dev`, not this tunnel.

⚠️ `*.harm.org` CNAMEs **to the tunnel**, not to the apex. It followed the apex
until cutover; leaving it there would have dragged `plane.harm.org` — which has
no explicit DNS record of its own — onto Pages. Do not point it back at `harm.org`.

| public hostname | local service |
|---|---|
| `tailscale.harm.org` | `http://localhost:3912` ([`../tailscale-index`](../tailscale-index/)) |
| `tokens.harm.org` | `http://localhost:3001` |
| `dram.harm.org` | `http://localhost:3011` |
| `plane.harm.org` | `http://localhost:8190` |

## Files -> install paths

| repo file | installed path | owner/mode | notes |
|---|---|---|---|
| [`config.yml`](config.yml) | `/etc/cloudflared/config.yml` | `root:root 0644` | public hostname ingress; no secrets |
| [`config.user.yml`](config.user.yml) | `/home/halbritt/.cloudflared/config.yml` | `halbritt:halbritt 0644` | user-scope fallback; ingress must match `config.yml` |
| [`cloudflared.service`](cloudflared.service) | `/etc/systemd/system/cloudflared.service` | `root:root 0644` | runs the named tunnel |
| [`cloudflared-update.service`](cloudflared-update.service) | `/etc/systemd/system/cloudflared-update.service` | `root:root 0644` | updates Cloudflared |
| [`cloudflared-update.timer`](cloudflared-update.timer) | `/etc/systemd/system/cloudflared-update.timer` | `root:root 0644` | daily updater |
| - credentials, never vendored | `/etc/cloudflared/e6e104cb-75a2-4ccc-a46f-aca2c725328c.json` | `root:root 0400` | tunnel secret |
| - credentials, never vendored | `/home/halbritt/.cloudflared/e6e104cb-75a2-4ccc-a46f-aca2c725328c.json` | `halbritt:halbritt 0400` | same tunnel secret, user-readable copy |

Install after edits:

```bash
sudo install -m 0644 cloudflared/config.yml /etc/cloudflared/config.yml
install -m 0644 cloudflared/config.user.yml /home/halbritt/.cloudflared/config.yml
sudo install -m 0644 cloudflared/cloudflared*.service cloudflared/cloudflared-update.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart cloudflared.service
sudo systemctl enable --now cloudflared-update.timer
```

Installing `config.user.yml` alone needs no restart — the running unit does not
read it.

## Verify

Do not print the tunnel credentials JSON.

```bash
cloudflared --config cloudflared/config.yml tunnel ingress validate
cloudflared --config /home/halbritt/.cloudflared/config.yml tunnel ingress validate
# ingress parity between the system and user-scope configs (expect no output)
diff <(grep -Ev '^#|^credentials-file|^$' /home/halbritt/.cloudflared/config.yml) \
     <(grep -Ev '^#|^credentials-file|^$' /etc/cloudflared/config.yml)
systemctl status cloudflared cloudflared-update.timer --no-pager
curl -o /dev/null -sS -w 'plane_origin=%{http_code}\n' http://127.0.0.1:8190/api/instances/
curl -I --max-time 15 https://harm.org/        # now Cloudflare Pages, not this tunnel
curl -I --max-time 15 https://plane.harm.org/  # still this tunnel, via *.harm.org
curl -o /dev/null -sS -w 'plane_public=%{http_code}\n' https://plane.harm.org/api/instances/
curl -o /dev/null -sS -w 'plane_public_unauth=%{http_code}\n' https://plane.harm.org/api/users/me/
```

Expected checks:

- local origin `/api/instances/`: `200`
- public `/api/instances/`: `200`
- public `/api/users/me/` without auth: `401`
- root `harm.org` / `www.harm.org`: `200` (served by Pages)
- both `ingress validate` runs: `OK`
- parity `diff`: no output

Verified on 2026-07-25, after the harm.org cutover:

- Both configs validated `OK`; parity `diff` empty; both matched this repo.
- `harm.org` and `www.harm.org` route to Pages, not the tunnel:
  `harm_org=200`, `www_harm_org=200`, and `cloudflared tunnel ingress rule
  https://harm.org/` now falls through to the `http_status:404` catch-all.
- Everything still on the tunnel survived the ingress removal and restart:
  `plane_origin=200`, `plane_public=200`, `plane_unauth=401`, and
  `tokens` / `dram` / `tailscale` each returned `200`.
- The retired origin is gone: zero listeners on `127.0.0.1:18888`,
  `harm-enterprises-site.service` inactive and disabled.
- Tunnel `e6e104cb-…328c` held four edge connections (`2xlax`, `2xsjc`).

Verified on 2026-07-25, earlier the same day (pre-cutover, config parity work):

- Both configs validated `OK`, and the parity `diff` between
  `~/.cloudflared/config.yml` and `/etc/cloudflared/config.yml` was empty.
- `cloudflared`, `cloudflared-update.timer`, and `harm-enterprises-site` were
  active; the running unit was not restarted (that change did not touch it).
- `plane_origin=200`, `local_site=200`, `harm_org=200`, `www_harm_org=200`,
  `plane_public=200`, `plane_public_unauth=401`.

Verified on 2026-06-29:

- `cloudflared --config cloudflared/config.yml tunnel ingress validate` returned
  `OK`.
- The installed `/etc/cloudflared/config.yml` and systemd unit/timer files
  matched this repo.
- `cloudflared.service`, `cloudflared-update.timer`, and `plane-harm-org.service`
  were active.
- `cloudflared --config /etc/cloudflared/config.yml tunnel ingress rule
  https://plane.harm.org/api/instances/` matched the `plane.harm.org` rule to
  `http://localhost:8190`.
- Local and public checks returned `plane_origin_instances=200`,
  `plane_public_instances=200`, and `plane_public_users_me_no_auth=401`.

## Stop Conditions

Stop and ask before:

- deleting or rotating the tunnel credential JSON
- changing Cloudflare DNS records or tunnel routes for unrelated hostnames
- routing wildcard hostnames to local services
- exposing new local services without a hostname-specific ingress rule and
  external verification
- letting the two configs diverge: an ingress change to one is a change to both
