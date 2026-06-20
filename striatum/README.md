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
left alone. **Deployed 2026-06-20** — this fix is present in the live binary (the
committee-managed binary drifts, but every `main`-descended build contains
`e9d01815`; verify with `git merge-base --is-ancestor e9d01815 $(striatumd -describe
| grep -oE 'git_sha=[0-9a-f]+' | cut -d= -f2)`). The `rpc/` nesting is no longer
load-bearing (the fixed daemon would also accept the un-nested
`/run/striatum/daemon-go.sock`), but it is kept in place because it works
identically on the fixed binary and removing it costs another restart — see
[Deploy](#deploy-2026-06-20--final-state).

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

### Deploy (2026-06-20) — final state

This deploy *installed* **`01fea155`** (origin/main: the #495/#496 fix +
RFC 0136/0141 code), but the exact daemon binary **drifts** and you should NOT
assume the live binary is `01fea155`. The rfc-0137 committee's `make install` step
swaps `~/.local/bin/striatumd` to whatever it just built — as of last verification
the live binary was **`202c1cc5`** (`striatumd -describe`: `build_dirty=dirty`,
`migration_count=40`), a build that *predates* `01fea155`. Check what is actually
running with `striatumd -describe`; do not trust this commit hash to be current.

What holds regardless of the drift:
- **#495/#496 fix is present** in the live binary — `202c1cc5` descends from
  `e9d01815` (verify any live sha with `git merge-base --is-ancestor e9d01815 <sha>`).
- **#503 crash-loop is resolved at the DB level (migration 42) — but the on-disk
  binary must itself support schema ≥ 42 to boot.** striatumd enforces a hard
  version ceiling at startup (`go/pkg/db/migrations.go`: it errors when the live DB
  schema exceeds the binary's `LatestDaemonDBVersion`), *independent* of whether
  `-migrate` finds work. `202c1cc5` has `LatestDaemonDBVersion = 40`, so against the
  migration-42 DB it never reaches `-migrate` — it dies at the ceiling with `daemon
  PostgreSQL schema version 42 is newer than supported 40`. A drifted-back build
  therefore only *looks* healthy while a 42-capable process from before the clobber
  is still resident; the next restart bricks it. (So the earlier "any migration-40
  build starts cleanly" was wrong — it described the running process, not a restart.)
  The **#495/#496 fix is still present** regardless (`202c1cc5` ⊇ `e9d01815`).

**Empirically confirmed 2026-06-20** while wiring the RFC 0137 exporter: pinning the
MCP port (above) needed a `striatumd` restart, which re-exec'd the 16:15 on-disk
binary (`202c1cc5`, ceiling 40) and crash-looped on that exact error — taking
`/metrics` down. **Recovery:** rebuild from a clean worktree off `origin/main` (it
tracks `LatestDaemonDBVersion = 42` via #507) and install *only* the daemon binary:
```bash
git worktree add --detach /tmp/wt origin/main && make -C /tmp/wt/go build
cp /tmp/wt/go/bin/striatumd ~/.local/bin/
sudo systemctl reset-failed striatumd && sudo systemctl restart striatumd
git -C /tmp/wt worktree remove /tmp/wt
```
Do **NOT** `make install` (it runs the forbidden `striatum daemon install`, #509).
The live-binary invariant: its `LatestDaemonDBVersion` must be ≥ the live DB schema.

Earlier the swap *looked* clean — `daemon status` reads ok (above), `doctor ok`,
lanes spawn, `sudo -u striatum-lane` can `connect()` the socket — but that was the
resident 42-capable process, not the drifted on-disk binary. Backup of the
pre-migration binaries: `~/.local/bin/.striatum-prev-2026-06-20/`.

It took three tries — the story is worth keeping because it's a two-role-split
deployment hazard:

1. **Migration trap (striatum#503).** Migration **0041** (`event_chain_segments`)
   originally added an inbound FK to the **owner-held** `repositories` table.
   `striatumd_rw` (the runtime role that auto-applies migrations, `-migrate`
   defaults true) lacks `REFERENCES` on owner tables, so the first deploy of the
   migration-42 build crash-looped with `permission denied for table repositories
   (SQLSTATE 42501)`. Rolled back to a migration-40 build to restore service.
2. **Clobber.** Within ~80s, an rfc-0137 committee's build/verify step
   `make install`ed its own migration-42 binary over `~/.local/bin/striatumd`,
   re-triggering the crash-loop (35 restarts). Re-pinned to migration 40 again.
3. **Resolution.** striatum#503 was fixed upstream as **`01fea155` (#507)** —
   drop the owner-FK, keep `repository_id` a bare column, integrity in Go (the
   same pattern `0042` already uses). An AFK process then owner-applied the fixed
   `0041`/`0042`, advancing the **DB to migration 42 at 15:03** (verified:
   `event_chain_segments` exists with **no** inbound FK). Deployed `01fea155`.

**Why it's stable now:** the DB is at migration 42, so *every* migration-42 binary
— `01fea155` or any committee build — sees the migrations already applied, skips
`0041`, and starts cleanly. The clobber is permanently harmless; the daemon binary
no longer needs pinning. `git pull && make install` is safe again.

Lesson (striatum#503): a migration applied by the runtime role must never add an
inbound FK to (or otherwise DDL) an owner-held table — enforce that integrity in
Go, or ship it as an owner bundle.

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
