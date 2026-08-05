# proximal/vitae-elicitation — RFC 0007 elicitation interview service

Desired-state and provenance for the **Vitae elicitation interview service** on
host `proximal`: the tailnet-only web interview that mines the Principal's
episodic career memory into the `vitae` knowledge graph (RFC 0007 / decision
D0007, delivered as the `memory-mined@1` Striatum arc, RQ-599).

The service is **defined in the `vitae` repo** (`~/git/vitae/elicitation/`), not
here. This directory records only how it is *enacted on this host*: the unit, the
publication, and the deploy provenance. The artifacts are regenerable — re-run the
installer to refresh the derived config.

## At A Glance

| | |
|---|---|
| tailnet URL | `https://proximal.tail0ecc2e.ts.net/` |
| local origin | `http://127.0.0.1:8909` (loopback only) |
| bind posture | loopback default; LAN / wildcard / public refused in every mode (`elicitation/service/bind.py`) |
| tailnet front | Tailscale Serve, HTTPS `:443` → loopback `:8909` (terminates TLS so the browser mic works) |
| unit | `elicitation.service` (systemd **user** unit, `systemctl --user`) |
| service user | `halbritt` |
| source repo | `~/git/vitae` — `elicitation/`, entrypoint `elicitation/ui/serve.sh` |
| install | `~/git/vitae/elicitation/deploy/install.sh` (idempotent) |
| verify | `~/git/vitae/elicitation/deploy/deploy-smoke.sh` (live bind smoke) |
| deployed | 2026-07-12 (Principal "accept and deploy") |

## Routing

| layer | route |
|---|---|
| Tailscale Serve | `https://proximal.tail0ecc2e.ts.net/` → `http://127.0.0.1:8909` |
| systemd origin | `elicitation.service` runs `elicitation/ui/serve.sh` on `127.0.0.1:8909` |

The service never opens a non-loopback socket; the tailnet front door is Serve.
`deploy-smoke.sh` proves it on the wire: answers on loopback, **silent** on every
LAN address (`192.168.1.92`, the `172.x` docker bridges) and on the tailnet IP
`100.85.100.81`, and the HTTPS Serve front answers. Nothing under `vitae/private/`
(where sessions persist) syncs outward (V7 / D0007.C7).

## Derived config (untracked, install-time discovered)

| path | written by | read by |
|---|---|---|
| `~/.config/systemd/user/elicitation.service` | `install.sh` (rendered from the tracked template) | systemd user manager |
| `~/.config/elicitation/elicitation.env` | `install.sh` | the unit |
| `~/.local/state/elicitation/smoke.env` | `install.sh` | `deploy-smoke.sh` |

No tailnet or LAN address is baked into the tracked `vitae` artifacts; `install.sh`
discovers this node's tailnet IP (`tailscale ip -4`), MagicDNS name, and LAN
negative targets (`ip -4 addr show scope global`) at install time.

## User-mode hardening (host-enactment fix, 2026-07-12)

The unit runs as a **systemd user service**, so its hardening is restricted to
directives a uid-1000 manager can apply: mount-namespace/filesystem protections
(`ProtectSystem=strict`, `ProtectHome=read-only`, `PrivateTmp`,
`ReadWritePaths=…/vitae/private`) and seccomp/prctl filters (`NoNewPrivileges`,
`RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`, `RestrictNamespaces`,
`LockPersonality`, `RestrictSUIDSGID`).

The capability/kernel-object directives a *system* unit would carry —
`ProtectKernelModules`, `ProtectKernelTunables`, `ProtectControlGroups`,
`ProtectClock` — force a `CapabilityBoundingSet` drop that a user service cannot
perform without `CAP_SETPCAP`, aborting the unit with `status=218/CAPABILITIES`.
The original RFC 0007 packet template carried them (it was written for a system
unit); the live smoke at host enactment (work-graph W11.4) caught the crash-loop,
and the `vitae` template (`elicitation/deploy/elicitation.service`) was corrected
to the user-safe set. The loopback-only bind, refused before any non-loopback
socket opens, is the load-bearing network control — not the kernel-object sandbox.

## Operations

    ~/git/vitae/elicitation/deploy/install.sh            # (re)install — idempotent
    ~/git/vitae/elicitation/deploy/deploy-smoke.sh       # verify the live bind posture
    ~/git/vitae/elicitation/deploy/uninstall.sh          # stop, withdraw Serve, remove config
    systemctl --user status elicitation.service
    journalctl --user -u elicitation.service -f
    tailscale serve --https=443 off                      # withdraw the front only
