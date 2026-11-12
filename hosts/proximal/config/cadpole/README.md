# Cadpole CAD viewer

Cadpole runs at https://cadpole.harm.org through the existing Cloudflare Tunnel.
The owner requested this public hostname on 2026-11-11 after installing the
upstream application and starting its bracket example.

| Resource | Location |
| --- | --- |
| Upstream | https://github.com/mikelikespie/cadpole |
| Checkout | `/home/halbritt/git/cadpole` |
| Installed revision | `25d5af0c55b0a5a333518e14c0c6fb939e95e1a6` (CLI 0.1.0) |
| CLI | `~/.local/bin/cadpole` links to the checkout's `bin/cadpole` |
| Build | Bazelisk at `~/.local/bin/bazel`, repository-pinned Bazel 9.2.0 |
| Origin | `http://127.0.0.1:7332` |
| Service | User `cadpole.service`, enabled under the lingering user manager |
| Unit mapping | `cadpole.service` → `~/.config/systemd/user/cadpole.service` |
| Runtime | `/run/user/1000/cadpole`, private run records, sockets and tokens |
| Documents | `~/Documents/cadpole` |

Port 7331 already serves another application. Cloudflare ingress is specific to
`cadpole.harm.org`; existing wildcard DNS already reaches the tunnel. TLS ends at
Cloudflare and the origin listens only on loopback. See [cloudflared](../cloudflared/README.md).

## Authentication and scope

This is one editable session, not a multi-user hosting service. Upstream describes
`serve` as a single-user/private-network tool. Public routing retains its browser
token requirement, origin checks and operation limits. HTML and static assets are
public; API calls require the browser token. Agent session/listener tokens remain
on the Unix socket and are not admitted over HTTP. No coding-agent listener is
started by this service.

Each restart generates a new browser token and invalidates old login links. The
private `<instance>.url` file holds the current login URL; substitute
`https://cadpole.harm.org/` for its loopback origin when giving the link to the
owner. Keep the fragment token out of Git, notes and service logs. The UI consumes
it into session storage. Do not disable authentication to make the bare URL work.

## Install and operate

Build the existing checkout with `./bin/install` before starting the unit. The
service sets `CADPOLE_NO_BUILD=1` so boot does not compile source or fetch toolchains.
The first build took about 24 minutes and includes the bundled web UI.

```sh
install -Dm644 cadpole.service ~/.config/systemd/user/cadpole.service
systemctl --user daemon-reload
systemctl --user enable --now cadpole.service
systemctl --user status cadpole.service
journalctl --user -u cadpole.service -n 20
```

Install both Cloudflare configs following their README, validate parity, and
restart `cloudflared.service`. For upgrades, update the clean upstream checkout,
build explicitly, restart the user service, verify the new login link and record
the revision here. Startup loads `examples/bracket.star`; save desired session
changes through Cadpole before a restart.

To remove public access, remove only the Cadpole hostname rule from both tunnel
configs and redeploy them. Stop/disable the user unit to stop the application.
Do not delete documents or build caches as part of withdrawing the route.

## Verification record

On 2026-11-11, native evaluation and an 800×600 bracket render passed. Public
HTTPS HTML and bundled JavaScript returned 200; authenticated session JSON
returned 200 with the public Origin header. Anonymous API reads returned 401 and
cross-origin requests returned 403. Both tunnel configurations validated and all
four canonical/installed ingress blocks matched. The user service is enabled;
Plane, Artifact and 3D viewer checks returned 200 after the tunnel restart.
