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
`sudo -u striatum-lane` can `connect()` the socket through the ACL chain.

**Fixed upstream** in `e9d01815` (striatum#495): `daemonSocketACLGrantTargets` now
skips the traverse-ACL on any ancestor already world-traversable, so `/run` is
left alone. **Deployed 2026-06-20** — the live daemon runs `e9d01815`. The `rpc/`
nesting is no longer load-bearing (the fixed daemon would also accept the
un-nested `/run/striatum/daemon-go.sock`), but it is kept in place because it
works identically on the fixed binary and removing it costs another restart — see
[Deploy](#deploy-2026-06-20).

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

### Operator note: `striatum daemon status` (fixed in the deployed binary)

`striatum daemon status` used to be built for the **user**-unit install — it
hardcoded the unit path to `~/.config/systemd/user/striatumd.service` and the
socket to `RuntimeDir/daemon-go.sock` (no `rpc/`), so against the system unit it
falsely reported `unit … (installed=false, active=inactive)` / `socket …
(present=false)` even while healthy.

**Fixed upstream** in `e9d01815` (striatum#496) and **deployed 2026-06-20**:
`inspectDaemonUnit` is now scope-aware and the socket field honours
`STRIATUM_DAEMON_SOCKET`. The live CLI now reads correctly:

```
  unit:    /etc/systemd/system/striatumd.service (scope=system, installed=true, enabled=enabled, active=active)
  socket:  /run/striatum/rpc/daemon-go.sock (present=true)
  doctor:  ok
```

### Deploy (2026-06-20)

The `e9d01815` binaries (#495/#496 fix) are installed at `~/.local/bin` and the
daemon was restarted onto them. Verified: `daemon status` reads clean (above),
`doctor ok`, lanes spawn, `sudo -u striatum-lane` can `connect()` the socket.

**Watch out — the migration trap (striatum#503).** `e9d01815` sits at PG
**migration 40**, deliberately. `origin/main` HEAD (`bff9e682`) is at migration
42, and migration **0041** (`event_chain_segments`) adds an inbound FK to the
**owner-held** `repositories` table — which `striatumd_rw` lacks `REFERENCES` on,
so a daemon that auto-applies it (`-migrate` defaults true) **crash-loops** with
`permission denied for table repositories (SQLSTATE 42501)`. A first deploy of
`bff9e682` hit exactly this and was rolled back; `e9d01815` (migration 40) is the
pinned-safe build. **Do not `git pull && make install` past migration 40 until
striatum#503 is fixed** — it will take the daemon down. The previous binaries are
backed up at `~/.local/bin/.striatum-prev-2026-06-20/` (rollback: `install` them
back + `sudo systemctl restart striatumd`).

**⚠️ Active conflict (2026-06-20): a committee self-installs migration-42 binaries.**
Within ~80s of this deploy, an rfc-0137 committee build/verify step ran
`make install` from a migration-42 checkout (`a88c9dd8`), overwrote
`~/.local/bin/striatumd`, and the daemon crash-looped (35 restarts) on the #503
trap until re-pinned to `e9d01815`. As long as a committee that self-installs the
daemon is running, `~/.local/bin/striatumd` can be clobbered back to a
crash-looping migration-42 build at any time. Until #503 is resolved, the daemon
binary is **not stably pinned** here — this needs either (a) striatum#503 fixed in
code (drop the 0041 owner-FK) so migration-42 builds run, (b) migrations 0041/0042
applied as the **owner** to advance the DB to 42 (then both builds run), or (c)
the committee's self-install pointed at a protected daemon path. Decision pending.

The `rpc/` socket nesting is **kept** (it works identically on the fixed binary).
Un-nesting back to `/run/striatum/daemon-go.sock` is now possible (the fixed
daemon skips the `/run` ACL) but is optional cleanup that costs another restart —
not done. If ever wanted: drop the two `rpc/` `ExecStartPre` lines + the `rpc/`
from `STRIATUM_DAEMON_SOCKET`/`-socket` here, in `profile.d-striatum.sh`, and the
warmtier drop-in, then restart.

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
