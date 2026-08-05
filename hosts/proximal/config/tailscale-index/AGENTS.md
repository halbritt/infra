# proximal/tailscale-index instructions

This subsystem owns the public landing page at `https://tailscale.harm.org` — a
static index of tailnet service URLs. Read `README.md` before changing anything
here.

## Boundaries

- Commit the user unit, the stdlib server, the page itself, and the link-check
  script. All four are non-secret by construction.
- **The page is world-readable.** It lists hostnames and ports and nothing else.
  Never add tokens, project IDs that imply access, internal notes, or a URL whose
  path is itself a credential (the `ha-mcp` pattern in `~/CLAUDE.md`).
- Public ingress belongs to [`../cloudflared`](../cloudflared/); this subsystem
  owns the loopback origin and the page content.
- Keep the origin on `127.0.0.1:3912`. The tunnel is the only intended way in.

## Operational rule

Unlike most subsystems here, the box serves `site/` and `server.py` **directly
from this checkout** — there is no installed second copy, on purpose (README §
"Single copy, not installed-copy"). So:

- Editing `site/index.html` is live on the next request. No install, no restart.
- Editing `server.py` needs `systemctl --user restart tailscale-index`.
- Editing `tailscale-index.service` needs an install to
  `~/.config/systemd/user/`, a `--user daemon-reload`, and a restart.

It follows that **an uncommitted edit here is already serving in public.** Commit
before ending the turn — the tree being dirty is not a staging area, it is a
live-but-unrecorded production page.

## Every card must be verified

A card is a claim that a URL works. Do not add or edit one from a config file, a
port you remember, or a service's documentation — fetch it:

```bash
curl -skI --max-time 10 https://proximal.tail0ecc2e.ts.net:PORT/PATH
```

`*.ts.net` is HSTS-preloaded, so cards must be `https://`; a plain-HTTP tailnet
bind is browser-unreachable while `curl http://…` still succeeds, which is a
trap. Front those with `tailscale serve` and link the serve URL.

Run `./bin/check-links.sh` after any edit, and after any service on this box
moves port or mount prefix. Update the sweep table and the "Verified on" line in
the README when you do, and refresh the page footer's "Last checked" date.

Do not silently delete a card whose service died — record it under the README's
known-dead table with a pointer to that subsystem's retirement record. Removal is
an owner decision.

## Branch hygiene

Do not leave unmerged code lying around. If a task uses a branch, merge its
authorized work into the intended target branch before reporting completion. If
merge authority is absent, report that as a blocker instead of treating the
branch as finished. Clean up branches and associated worktrees after merge.
