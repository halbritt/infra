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
| credentials | `/etc/cloudflared/e6e104cb-75a2-4ccc-a46f-aca2c725328c.json` (root-only, never committed) |

## Ingress

The final catch-all rule must remain `http_status:404`.

| public hostname | local service |
|---|---|
| `tailscale.harm.org` | `http://localhost:3912` |
| `tokens.harm.org` | `http://localhost:3001` |
| `harm.org` | `http://localhost:18888` |
| `www.harm.org` | `http://localhost:18888` |
| `dram.harm.org` | `http://localhost:3011` |
| `plane.harm.org` | `http://localhost:8190` |

## Files -> install paths

| repo file | installed path | owner/mode | notes |
|---|---|---|---|
| [`config.yml`](config.yml) | `/etc/cloudflared/config.yml` | `root:root 0644` | public hostname ingress; no secrets |
| [`cloudflared.service`](cloudflared.service) | `/etc/systemd/system/cloudflared.service` | `root:root 0644` | runs the named tunnel |
| [`cloudflared-update.service`](cloudflared-update.service) | `/etc/systemd/system/cloudflared-update.service` | `root:root 0644` | updates Cloudflared |
| [`cloudflared-update.timer`](cloudflared-update.timer) | `/etc/systemd/system/cloudflared-update.timer` | `root:root 0644` | daily updater |
| - credentials, never vendored | `/etc/cloudflared/e6e104cb-75a2-4ccc-a46f-aca2c725328c.json` | `root:root 0400` | tunnel secret |

Install after edits:

```bash
sudo install -m 0644 cloudflared/config.yml /etc/cloudflared/config.yml
sudo install -m 0644 cloudflared/cloudflared*.service cloudflared/cloudflared-update.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart cloudflared.service
sudo systemctl enable --now cloudflared-update.timer
```

## Verify

Do not print the tunnel credentials JSON.

```bash
cloudflared --config cloudflared/config.yml tunnel ingress validate
systemctl status cloudflared cloudflared-update.timer --no-pager
curl -o /dev/null -sS -w 'plane_origin=%{http_code}\n' http://127.0.0.1:8190/api/instances/
curl -o /dev/null -sS -w 'plane_public=%{http_code}\n' https://plane.harm.org/api/instances/
curl -o /dev/null -sS -w 'plane_public_unauth=%{http_code}\n' https://plane.harm.org/api/users/me/
```

Expected Plane checks:

- local origin `/api/instances/`: `200`
- public `/api/instances/`: `200`
- public `/api/users/me/` without auth: `401`

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
