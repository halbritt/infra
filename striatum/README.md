# striatum

Desired-state for **`striatumd`**, the Striatum local workflow daemon — the Go
service that drives multi-agent committee/refactoring runs against registered
repositories on this box. Upstream + docs: `github.com/halbritt/striatum`
(checkout at `~/git/striatum`).

This directory tracks **how the daemon is wired into the host** (its systemd unit,
runtime layout, and the shell/peripheral glue), not the application itself. The
binary (`~/.local/bin/striatumd`) and its secrets (`~/.config/striatum/*`) are
installed by `striatum daemon install` / `make install` and are **not** vendored
here.

## What changed: user unit → system unit (2026-06-19)

striatumd ran as a **systemd _user_ unit** (`systemctl --user`, under
`user@1000.service`), with its socket and runtime files in the login-session
runtime dir `/run/user/1000/striatum`. It now runs as a **systemd _system_ unit**
(`/etc/systemd/system/striatumd.service`, `User=halbritt`), with all runtime
state in **`/run/striatum`**.

Why: this matches every other long-running service on the box (`llama-27b`,
`whisper-stt`, `praxis-stt-shim` are all system units with `User=halbritt`),
decouples the daemon from the login session (it no longer depends on
`/run/user/1000`, which `systemd-logind` owns and can tear down), and lets it be
managed with plain `systemctl` like everything else. Linger was already enabled,
so boot-survival was not the motivation — consistency and lifecycle independence
were.

It still runs **as `halbritt`, not root** — that is load-bearing (see the unit
comments): Postgres peer auth, the `sudo -n -u striatum-lane` lane sandbox, and
the home-dir config/checkout all require the owner UID.

## Files → install paths

| repo file | installed to | owner/mode | notes |
|---|---|---|---|
| [`striatumd.service`](striatumd.service) | `/etc/systemd/system/striatumd.service` | root:root 0644 | the system unit; all six former drop-ins folded inline |
| [`profile.d-striatum.sh`](profile.d-striatum.sh) | `/etc/profile.d/striatum.sh` | root:root 0644 | points interactive shells at `/run/striatum` |
| [`warmtier-autoingest.service.d-daemon-socket.conf`](warmtier-autoingest.service.d-daemon-socket.conf) | `~/.config/systemd/user/striatum-warmtier-autoingest.service.d/daemon-socket.conf` | halbritt 0644 | gives the warmtier timer the new socket path |
| — (secrets, never vendored) | `~/.config/striatum/blob.env` | halbritt 0600 | Garage S3 keys; referenced by the unit as `EnvironmentFile=` |
| — (secrets, never vendored) | `~/.config/striatum/daemon.toml` | halbritt 0600 | `postgres_url` (password DSN) read by the daemon |
| [`migration/`](migration/) | — | — | verbatim copy of the pre-migration user unit + drop-ins (provenance + revert source) |

**Edit here, then re-install.** After editing `striatumd.service`:

```bash
sudo install -m 0644 ~/git/proximal/striatum/striatumd.service /etc/systemd/system/striatumd.service
sudo systemctl daemon-reload
sudo systemctl restart striatumd        # KillMode=process: leaves live lane helpers running
systemctl status striatumd
```

## Runtime layout (`/run/striatum`)

systemd creates `/run/striatum` (0700, `halbritt:halbritt`) via
`RuntimeDirectory=striatum`, with `RuntimeDirectoryPreserve=yes` so it survives a
daemon restart (only an explicit stop/disable clears it). The daemon is pinned to
it: `STRIATUM_DAEMON_RUNTIME_DIR=/run/striatum` anchors `admin.RuntimeDir()` (the
`mcp-http-endpoint` discovery file, `web-ui.sock`, `discovery.json`, `instance-id`,
`client-token`, `mcp-boot-epoch`, `striatumd.pid`).

```
/run/striatum/                 0700 halbritt — runtime dir (RuntimeDir + lane-ACL anchor)
├── web-ui.sock                0600        — tailnet UI listener
├── mcp-http-endpoint  discovery.json  instance-id  client-token  mcp-boot-epoch  striatumd.pid
└── rpc/                       0700 halbritt — holds ONLY the lane-facing RPC socket
    └── daemon-go.sock         srw-rw----+  — STRIATUM_DAEMON_SOCKET (+ -socket flag)
```

**Why the RPC socket is nested in `rpc/`.** Supervised lanes run as the
`striatum-lane` OS user and must reach `daemon-go.sock`. striatumd grants that by
`setfacl`-ing a traverse ACL (`u:striatum-lane:--x`) on the socket's directory
**and that directory's parent**, then `rw-` on the socket file
(`go/cmd/striatumd/socket_acl.go`). A non-root daemon can only `setfacl` paths it
owns — so the socket's grandparent must be halbritt-owned. At
`/run/striatum/daemon-go.sock` the grandparent is `/run` (root), and the daemon
**fatally exits**: `grant daemon socket ACL u:striatum-lane:--x on /run: exit
status 1`. Nesting it at `/run/striatum/rpc/daemon-go.sock` makes the parent
(`/run/striatum/rpc`) and grandparent (`/run/striatum`) both halbritt-owned, so
both traverse-ACLs apply and `/run` is never touched. (striatumd also requires the
socket dir be mode `0700`/`0710`, hence the `chmod` in `ExecStartPre`.) Validated:
`sudo -u striatum-lane` can `connect()` the socket through the ACL chain. Filed
upstream — the unconditional grandparent `setfacl` should skip an already
world-traversable ancestor.

### How clients find the daemon

The `striatum` CLI resolves the socket as `STRIATUM_DAEMON_SOCKET` → else
`$XDG_RUNTIME_DIR/striatum/daemon-go.sock`, and the MCP/discovery dir as
`STRIATUM_DAEMON_RUNTIME_DIR` → else `$XDG_RUNTIME_DIR/striatum`. Interactive
shells still have `XDG_RUNTIME_DIR=/run/user/1000`, which now points at the *old,
empty* location — so `/etc/profile.d/striatum.sh` exports both vars for every
halbritt shell. The warmtier user timer gets the same two vars via its drop-in.
Supervised lanes are unaffected: the daemon injects an explicit
`STRIATUM_DAEMON_SOCKET` + `STRIATUM_MCP_URL` into each lane's wiped (`env -i`)
environment.

### Operator note: don't trust `striatum daemon status` here

`striatum daemon status` is built for the **user**-unit install: it hardcodes the
unit path to `~/.config/systemd/user/striatumd.service` and expects the socket at
`RuntimeDir/daemon-go.sock` (no `rpc/`). Against the system unit it therefore
misreports — `unit … (installed=false, … active=inactive)` and `socket … (present=false)`
— **even when the daemon is healthy** (note it still prints `doctor: ok` on the
same call). Use `systemctl status striatumd` for unit state and `striatum doctor`
for health. Filed upstream.

## Cutover (what was done, in order)

A cutover is **disruptive to any in-flight run**: the socket path changes *and*
the in-process MCP HTTP server rebinds to a new port, so active lanes (which hold
the old socket/MCP URL) are orphaned. **Drain to no active run first.**

1. `systemctl --user stop striatumd && systemctl --user disable striatumd`
2. Remove the user unit + drop-ins: `rm -r ~/.config/systemd/user/striatumd.service ~/.config/systemd/user/striatumd.service.d` then `systemctl --user daemon-reload`
3. Install the system unit + profile.d (see commands above) and:
   `sudo systemctl daemon-reload && sudo systemctl enable --now striatumd`
4. Re-point the tailnet web UI at the new socket (it was wired to the old path):
   ```bash
   tailscale serve --bg --https=9443 --set-path=/ unix:/run/striatum/web-ui.sock
   ```
5. Install the warmtier drop-in + `systemctl --user daemon-reload`.
6. Verify: `systemctl status striatumd`, `striatumd -check-config` (exit 0),
   `striatum daemon status` / `striatum doctor` reach the daemon, and
   `https://proximal.tail0ecc2e.ts.net:9443` still serves the read-only UI.

## Revert (system unit → user unit)

The pre-migration user unit + drop-ins are preserved verbatim in
[`migration/user-unit-pre-migration/`](migration/user-unit-pre-migration/).

```bash
sudo systemctl disable --now striatumd
sudo rm /etc/systemd/system/striatumd.service /etc/profile.d/striatum.sh
sudo systemctl daemon-reload
cp -r ~/git/proximal/striatum/migration/user-unit-pre-migration/striatumd.service \
      ~/git/proximal/striatum/migration/user-unit-pre-migration/striatumd.service.d \
      ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now striatumd
# re-point tailscale serve back at /run/user/1000/striatum/web-ui.sock
tailscale serve --bg --https=9443 --set-path=/ unix:/run/user/1000/striatum/web-ui.sock
# drop the warmtier drop-in if you reverted the socket path too
```

## Conventions

**Values and config, never credentials.** `blob.env` and `daemon.toml` carry
secrets and live only on the box (0600). The owner DSN in the unit is peer auth
(no password) and the web-repo/lane/runtime values are non-secret config, so they
are safe to vendor. See the root [`README.md`](../README.md).
