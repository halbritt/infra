# proximal/harm-enterprises - harm.org static site (RETIRED)

> ## ⚠️ Retired 2026-07-25 — this host no longer serves harm.org
>
> `harm.org` and `www.harm.org` migrated to **Cloudflare Pages**, built from
> [`halbritt/harm-org`](https://github.com/halbritt/harm-org) (Astro + Sveltia
> CMS). The tunnel ingress rules were removed and
> `harm-enterprises-site.service` was stopped and **disabled**.
>
> Nothing was deleted. The content root, the unit file, and `serve.py` are all
> still on disk, so this subsystem can be brought back — see
> [Rollback](#rollback). The rest of this document describes the retired
> arrangement and is kept for provenance.

Desired-state and provenance for the static Harm Enterprises website formerly
served from host `proximal` at `https://harm.org` and `https://www.harm.org`.

## At A Glance

| | |
|---|---|
| status | **retired 2026-07-25** — now on Cloudflare Pages |
| replacement | [`halbritt/harm-org`](https://github.com/halbritt/harm-org) → `harm-org.pages.dev` |
| former public URLs | `https://harm.org`, `https://www.harm.org` |
| former Cloudflare origin | `http://localhost:18888` |
| tailnet URL | `https://proximal.tail0ecc2e.ts.net:8890/` (Serve mapping may persist) |
| local origin | `http://127.0.0.1:18888` (stopped) |
| content root | `/home/halbritt/sites/harm-enterprises/public` (preserved) |
| server script | `/home/halbritt/sites/harm-enterprises/bin/serve.py` (preserved) |
| unit | `harm-enterprises-site.service` (installed, disabled) |
| service user | `halbritt` |

## Rollback

```bash
# 1. restore the two ingress rules in BOTH cloudflared configs (see ../cloudflared)
# 2. bring the origin back
sudo systemctl enable --now harm-enterprises-site.service
# 3. repoint DNS from harm-org.pages.dev back to the tunnel
#    harm.org / www.harm.org CNAME -> e6e104cb-75a2-4ccc-a46f-aca2c725328c.cfargotunnel.com
```

⚠️ Leave `*.harm.org` pointing at the tunnel. It used to CNAME to the apex; that
was changed during cutover because `plane.harm.org` has no explicit DNS record
and would otherwise have followed `harm.org` onto Pages and broken.

## Routing

| layer | route |
|---|---|
| Cloudflare Tunnel | `harm.org` / `www.harm.org` -> `http://localhost:18888` |
| Tailscale Serve | `https://proximal.tail0ecc2e.ts.net:8890/` -> `http://127.0.0.1:18888` |
| systemd origin | `harm-enterprises-site.service` runs `bin/serve.py` on `127.0.0.1:18888` |

The server adds conservative headers:

- `X-Robots-Tag: noindex, nofollow, noarchive, noimageindex, nosnippet`
- `Referrer-Policy: no-referrer`
- `Content-Security-Policy: default-src 'self'; img-src 'self'; style-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'`

## Files -> install paths

| repo file | installed path | owner/mode | notes |
|---|---|---|---|
| [`harm-enterprises-site.service`](harm-enterprises-site.service) | `/etc/systemd/system/harm-enterprises-site.service` | `root:root 0644` | system lifecycle for the local origin |
| [`bin/serve.py`](bin/serve.py) | `/home/halbritt/sites/harm-enterprises/bin/serve.py` | `halbritt:halbritt 0755` | loopback-only static file server |
| - site content, not mirrored here | `/home/halbritt/sites/harm-enterprises/public` | `halbritt:halbritt` | static HTML/CSS/assets |

Install after edits:

```bash
install -m 0755 harm-enterprises/bin/serve.py /home/halbritt/sites/harm-enterprises/bin/serve.py
sudo install -m 0644 harm-enterprises/harm-enterprises-site.service /etc/systemd/system/harm-enterprises-site.service
sudo systemctl daemon-reload
sudo systemctl enable --now harm-enterprises-site.service
```

The Cloudflare routing lives in [`../cloudflared/config.yml`](../cloudflared/config.yml).
The current Tailscale Serve mapping is runtime state; verify it before relying on
the tailnet URL:

```bash
tailscale serve status
```

Expected mapping:

```text
https://proximal.tail0ecc2e.ts.net:8890 (tailnet only)
|-- / proxy http://127.0.0.1:18888
```

## Verify

```bash
systemctl status harm-enterprises-site cloudflared tailscaled --no-pager
systemctl is-enabled harm-enterprises-site cloudflared tailscaled
ss -ltnp | grep -E '127[.]0[.]0[.]1:18888|100[.]85[.]100[.]81:8890'
tailscale serve status
cloudflared --config cloudflared/config.yml tunnel ingress validate
curl -I --max-time 10 http://127.0.0.1:18888/
curl -I --max-time 10 https://proximal.tail0ecc2e.ts.net:8890/
curl -I --max-time 15 https://harm.org/
curl -I --max-time 15 https://www.harm.org/
```

Expected checks:

- local origin: `200`
- tailnet route: `200`
- public `harm.org`: `200`
- public `www.harm.org`: `200`
- `cloudflared` ingress validation: `OK`

Verified on 2026-06-30:

- `harm-enterprises-site.service`, `cloudflared.service`, and
  `tailscaled.service` were enabled and active.
- `harm-enterprises-site.service` ran
  `/usr/bin/python3 /home/halbritt/sites/harm-enterprises/bin/serve.py` as
  `halbritt`.
- The origin listened on `127.0.0.1:18888`.
- `tailscale serve status` showed
  `https://proximal.tail0ecc2e.ts.net:8890/` proxying to
  `http://127.0.0.1:18888`.
- Local origin, tailnet route, `https://harm.org/`, and
  `https://www.harm.org/` returned `200`.

## Stop Conditions

Stop and ask before:

- changing Cloudflare DNS, tunnel routes, or wildcard ingress rules
- removing the noindex / CSP / referrer headers
- rebinding the origin off loopback
- deleting or replacing `/home/halbritt/sites/harm-enterprises/public`
- committing Cloudflare credentials, analytics credentials, private business
  data, or generated TLS material
