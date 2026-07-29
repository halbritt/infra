# proximal/tailscale-index — the `tailscale.harm.org` landing page

Desired-state and provenance for the small static index of tailnet service URLs
served from host `proximal` at `https://tailscale.harm.org`.

Folded into this repo on **2026-07-29**. It previously lived as an unversioned
directory at `~/git/tailscale-index` (not a git repo), which is why it drifted —
see [History](#history).

## At A Glance

| | |
|---|---|
| status | live |
| public URL | `https://tailscale.harm.org` |
| local origin | `http://127.0.0.1:3912` (loopback only — no tailnet bind, no `tailscale serve`) |
| public ingress | Cloudflare Tunnel → `http://localhost:3912` (see [`../cloudflared`](../cloudflared/)) |
| unit | `tailscale-index.service` — **user scope** (`systemctl --user`), enabled |
| service user | `halbritt` |
| content root | `site/` **in this repo** (served directly; no separate installed copy) |
| server | `server.py` in this repo — stdlib `http.server`, no dependencies |

The page itself is public; the URLs it lists are tailnet-only unless a service
has its own public route. That is deliberate — the index leaks hostnames and
ports, nothing else, and carries `noindex, nofollow, noarchive` plus
`Referrer-Policy: no-referrer` and `X-Content-Type-Options: nosniff`.

## Single copy, not installed-copy

This subsystem deliberately **breaks the repo's usual canonical-in-repo /
installed-on-box split** for its content: the systemd unit points
`TAILSCALE_INDEX_SITE_DIR` straight at `site/` in this checkout, so the file the
browser gets *is* the file in git. There is no second copy to drift.

That split exists so root-owned `/etc/…` files have a versioned source. It buys
nothing here — the whole service is `halbritt`-owned files under `~/git` — and
an out-of-band copy is precisely the failure this subsystem was created to stop.
The one file that genuinely must be installed is the unit itself.

`server.py` reads the site dir from `TAILSCALE_INDEX_SITE_DIR` and serves with
`Cache-Control: no-cache`, so **editing `site/index.html` takes effect on the
next request — no restart, no reinstall.**

## Files → install paths

| repo file | installed path | owner/mode | notes |
|---|---|---|---|
| [`tailscale-index.service`](tailscale-index.service) | `~/.config/systemd/user/tailscale-index.service` | `halbritt:halbritt 0644` | user-scope unit; the only file that needs installing |
| [`server.py`](server.py) | *served from here* | `halbritt:halbritt 0644` | run in place by the unit's `ExecStart` |
| [`site/index.html`](site/index.html) | *served from here* | `halbritt:halbritt 0644` | run in place via `TAILSCALE_INDEX_SITE_DIR` |
| [`bin/check-links.sh`](bin/check-links.sh) | *run from here* | `halbritt:halbritt 0755` | link sweep, see [Verify](#verify) |

Install after editing the unit:

```bash
install -m 0644 tailscale-index/tailscale-index.service \
  ~/.config/systemd/user/tailscale-index.service
systemctl --user daemon-reload
systemctl --user restart tailscale-index.service
```

Editing `site/index.html` or `server.py` needs no install step; `server.py`
changes do need a restart.

## Routing

| layer | route |
|---|---|
| Cloudflare Tunnel | `tailscale.harm.org` → `http://localhost:3912` |
| systemd (user) | `tailscale-index.service` runs `server.py` on `127.0.0.1:3912` |

Public ingress lives in [`../cloudflared/config.yml`](../cloudflared/config.yml)
(and the parity copy `config.user.yml`) — change it there, not here. There is no
`tailscale serve` mapping for this service; it is reachable only through the
tunnel.

## Cards on the index

Sweep of 2026-07-29 01:57 UTC — 14 cards, all reachable
(`check-links.sh` exit 0). Card names are the `<h2>` text.

| card | target | status |
|---|---|---|
| Plane / Proximal | `:10000/` | 200 |
| Praxis Plane Connector Lab (PXLAB) | `:10000/proximal/projects/…/issues` | 200 |
| Agent Capability Lab (CAPLAB) | `:8784/` | 200 |
| OpenClaw Control | `:443/` | 200 |
| Engram Operator | `:8765/` | 200 |
| BinKeeper: Catalog | `:8766/bins/` | 200 |
| BinKeeper: Photograph and Label | `:8766/` | 200 |
| BinKeeper: Register Labeled Bin | `:8766/register` | 200 |
| BinKeeper: Sort a Stash | `:8766/stash` | 200 |
| Pastebin | `:18080/` | 200 |
| Markdown Browser | `:8444/` | 200 |
| Grafana — proximal dashboards | `:8853/` | 302 (login) |
| Prometheus — proximal | `:9491/` | 302 |
| Alertmanager — proximal | `:9493/` | 200 |

All targets are `https://proximal.tail0ecc2e.ts.net`.

### Removed cards

Removed by owner decision on 2026-07-29. Both had been 502ing in the same shape:
a `tailscale serve` mapping outliving a retired origin, so the port completes TLS
and then fails. Recorded here rather than only in `git log` because each is
restorable — if either subsystem is rolled back per its own README, re-add the
card and re-sweep.

| card | target | why it died |
|---|---|---|
| Striatum Web UI | `:9443/` | `striatumd` **retired 2026-07-21** — [`../striatum/README.md`](../striatum/README.md) |
| Harm Site Mirror | `:8890/` | `harm-enterprises-site.service` **stopped and disabled 2026-07-25** when `harm.org` moved to Cloudflare Pages — [`../harm-enterprises/README.md`](../harm-enterprises/README.md) |

⚠️ The two `tailscale serve` mappings themselves were **left in place** — removing
them is a `tailscale serve` change, not an index change, and neither retirement
record calls for it. So `:9443` and `:8890` still answer TLS and 502; they are
simply no longer advertised here.

⚠️ **`*.ts.net` is HSTS-preloaded.** A card must use `https://`. A service that
binds the tailnet IP and speaks plain HTTP is unreachable from a browser even
though `curl http://…:PORT` works, which reads as a mysteriously broken card.
Front such services with `tailscale serve --bg --https=PORT http://…` and point
the card at the serve URL. This bit the three observability cards on 2026-07-22;
the full write-up is in
[`../observability/README.md`](../observability/README.md) § "Tailnet index".

## Verify

```bash
systemctl --user status tailscale-index --no-pager
systemctl --user is-enabled tailscale-index
ss -ltnp | grep 127.0.0.1:3912
curl -I --max-time 10 http://127.0.0.1:3912/
curl -I --max-time 15 https://tailscale.harm.org/
cloudflared --config ../cloudflared/config.yml tunnel ingress validate

# every link on the page (exit 1 if any is dead)
./bin/check-links.sh
```

Expected: local origin `200`, public `200`, ingress validation `OK`, and
`check-links.sh` exit `0`.

Verified on 2026-07-29 after the fold: unit active and enabled from the new
`WorkingDirectory`, origin on `127.0.0.1:3912`, `https://tailscale.harm.org/`
`200` and byte-identical to `site/index.html`. After the card edits the same
day, `check-links.sh` exits `0` — 14/14 reachable.

## History

**2026-07-29 — folded into this repo, BinKeeper cards repaired.** All three
BinKeeper cards pointed at `https://…:8765/bin-photo/…` and 404'd. BinKeeper had
moved off Engram's port to its own service (`binkeeper.service`, `127.0.0.1:8766`)
during the `BINK-11` / `BINK-13` authority cutover, and its authoring app is now
mounted at **root**, not under `/bin-photo/`:

| card | was (404) | now (200) |
|---|---|---|
| Photograph and Label | `:8765/bin-photo/` | `:8766/` |
| Register Labeled Bin | `:8765/bin-photo/register` | `:8766/register` |
| Catalog | `:8765/bins/` | `:8766/bins/` |

The index had no owner in any repo, no link check, and no changelog, so a port
move three weeks earlier went unnoticed until someone tried to photograph a bin.
Folding it in — plus `bin/check-links.sh` — is the fix for the class, not just
the instance.

This supersedes
[`../observability/tailscale-index-card.patch`](../observability/tailscale-index-card.patch),
the earlier workaround that recorded index edits as an unapplied `.patch` file
because there was nowhere to version the real thing. That file is kept for
history; new index changes are ordinary commits here.

**2026-07-29, same day — card cleanup.** On the owner's call, dropped the two
dead cards (see [Removed cards](#removed-cards)) and added **BinKeeper: Sort a
Stash** (`:8766/stash`), a live surface that had never been listed despite
getting its own operator tab in BinKeeper `6ee3001`. The page is now 14 cards,
all reachable.

## Stop conditions

Stop and ask before:

- adding a card for a service that is **not** already reachable, or that exposes
  something more sensitive than a hostname and port
- rebinding the origin off `127.0.0.1` — the tunnel is the only intended path in
- removing the `noindex` / referrer / nosniff headers in `server.py`
- changing Cloudflare DNS or tunnel ingress (that is [`../cloudflared`](../cloudflared/)'s call)
- deleting a card for a retired service — ask first, then record it under
  [Removed cards](#removed-cards) so it stays restorable
- putting anything on this page that is not a URL: it is world-readable
