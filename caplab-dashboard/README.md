# CAPLAB study-results dashboard on `proximal`

Desired state for the tailnet-only, read-only Agent Capability Lab (CAPLAB)
study-results dashboard. The application is defined in the `books` repository;
this subsystem records how exact committed application bytes are installed and
published on this host.

This is an inspection surface for a historical aggregate and its selected
measurement contract. It is not evidence admission, CAPLAB recomputation,
capability inference, technical verification, CAPLAB acceptance, or a CAPLAB
runtime. It has no
mutation endpoint and no public Cloudflare or Tailscale Funnel route.

## At a glance

| | |
|---|---|
| tailnet URL | `https://proximal.tail0ecc2e.ts.net:8784/` |
| local origin | `http://127.0.0.1:3021/` (loopback only) |
| tailnet front | Tailscale Serve HTTPS `:8784` to loopback `:3021` |
| unit | `caplab-dashboard.service` (systemd **user** unit) |
| source repository | `/home/halbritt/git/books` |
| source commit | [`SOURCE_COMMIT`](SOURCE_COMMIT) |
| immutable releases | `~/.local/share/caplab-dashboard/releases/<commit>/` |
| active release | `~/.local/share/caplab-dashboard/current` symlink |

## Repository files to installed paths

| canonical file | installed path | purpose |
|---|---|---|
| [`SOURCE_COMMIT`](SOURCE_COMMIT) | `~/.local/share/caplab-dashboard/releases/<commit>/SOURCE_COMMIT` | exact deployed source stamp |
| `books@SOURCE_COMMIT:caplab/` | `~/.local/share/caplab-dashboard/releases/<commit>/app/caplab/` | exact `git archive` application bytes |
| [`caplab-dashboard.service`](caplab-dashboard.service) | `~/.config/systemd/user/caplab-dashboard.service` | loopback origin lifecycle |
| [`install.sh`](install.sh) | not installed | idempotent release install/update |
| [`verify.sh`](verify.sh) | not installed | source, unit, bind, HTTP, and Serve verification |
| [`rollback.sh`](rollback.sh) | not installed | switch to the retained previous release |

The installer stages `git archive SOURCE_COMMIT caplab`, verifies required
runtime files, and moves the complete tree under its immutable commit-named
release directory. It refuses an existing release whose bytes differ. The
`current` symlink is switched atomically, and an update retains the old target
as `previous` for rollback.

## Install or update

Before a live change, confirm that the pinned commit is pushed and available in
the local `books` object store, and recheck that port `3021` is unused by any
other service:

```bash
ss -ltnH 'sport = :3021'
git -C /home/halbritt/git/books cat-file -e "$(<caplab-dashboard/SOURCE_COMMIT)^{commit}"
caplab-dashboard/install.sh /home/halbritt/git/books
caplab-dashboard/verify.sh --local-only
```

`install.sh` installs the canonical unit, reloads the user manager, and enables
and starts the service. The unit binds the application explicitly to
`127.0.0.1:3021`; Tailscale Serve is the only network front door.

The unit's hardening is deliberately limited to directives an unprivileged
user manager can apply. Do not add `ProtectKernelModules`,
`ProtectKernelTunables`, `ProtectControlGroups`, or `ProtectClock`: on this host
those system-unit directives make a user unit fail with
`status=218/CAPABILITIES`.

## Publish on the tailnet

Capture `tailscale serve status --json` immediately before publishing and
confirm HTTPS port `8784` has no TCP or Web entry. Add only this route:

```bash
tailscale serve --bg --https=8784 http://127.0.0.1:3021
```

Afterward, compare the before and after JSON after removing only the new
`:8784` TCP and Web entries. Every pre-existing mapping, especially `:443`,
must remain byte-for-byte equivalent. `AllowFunnel` must remain absent or null.
Then run:

```bash
caplab-dashboard/verify.sh
```

The route is tailnet-only. Do not add a Funnel, Cloudflare hostname, or public
CAPLAB origin.

## Public index card

Only after local and tailnet verification succeeds, add one card to
`/home/halbritt/git/tailscale-index/site/index.html`:

- title: `Agent Capability Lab (CAPLAB)`
- URL: `https://proximal.tail0ecc2e.ts.net:8784/`
- tags: `study results`, `tailnet only`

Capture the complete index SHA-256 immediately before editing and stop if it
changes concurrently. The card must contain no study data. Record the before
hash, after hash, and exact semantic edit in this host record after the live
enactment has been verified.

## Verify

`verify.sh` checks that:

- the active release and installed source stamp equal canonical
  `SOURCE_COMMIT`;
- installed application bytes equal a fresh Git archive of that commit;
- the installed unit equals the canonical unit and is enabled and active;
- TCP `3021` has only a `127.0.0.1` listener;
- health and catalog endpoints respond and mutation is refused;
- unless `--local-only` is used, Serve `:8784` is exactly the expected HTTPS
  loopback proxy and the tailnet health endpoint responds.

For reboot persistence, user lingering must remain enabled:

```bash
loginctl show-user "$USER" -p Linger
systemctl --user is-enabled caplab-dashboard.service
systemctl --user is-active caplab-dashboard.service
caplab-dashboard/verify.sh
```

Another tailnet node should also fetch the HTTPS health endpoint. A same-host
MagicDNS fetch verifies routing and TLS, but it is weaker evidence of remote
tailnet reachability.

## Rollback

Application rollback uses the retained immutable release:

```bash
caplab-dashboard/rollback.sh
```

This swaps `current` and `previous` and restarts the user service. To make the
rollback the new desired state, update `SOURCE_COMMIT` to the restored commit,
install the matching canonical branch, and run `verify.sh --local-only`.

To withdraw only CAPLAB tailnet publication without touching other routes:

```bash
caplab-dashboard/verify.sh
tailscale serve --https=8784 off
```

The verification immediately before withdrawal is a compare-before-mutate
guard: it refuses a Funnel, an additional handler, or a route that no longer
points exactly at the CAPLAB loopback origin. Stop instead of withdrawing a
concurrently changed route. Never use `tailscale serve reset`. Removing the
unit and data is a separate, explicit destructive action and is not part of
routine rollback. Restore the public index from its captured pre-edit bytes
only if the live file still has the recorded post-edit hash; otherwise stop for
concurrent-change review.

## Stop conditions

Stop rather than relax a gate if the source commit is absent, archived bytes
differ, either port is occupied, the new route would alter or shadow an
existing route, the public index changes after its before-hash capture, a
response exposes prohibited content, or rollback cannot restore the captured
state. An observed failure is not authorization to change evidence, add a
public route, or declare the CAPLAB result accepted.
