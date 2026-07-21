# striatum

> ## ⚠️ RETIRED — 2026-07-21
>
> Striatum (the Go daemon `striatumd` and its host wiring — what this directory
> documents) is retired. On the Principal's instruction, stopped and disabled on
> 2026-07-21: `striatumd.service` plus its support timers
> (`striatum-lane-cred-resync.timer`, `striatum-worktree-gc.timer`,
> `pg-repack-bloated.timer` — system scope). Port `:39201` closed; zero
> `striatumd_rw` backends.
>
> ⚠️ **NOT part of this retirement — do not touch on the strength of the name:**
> the user-scope `striatum-wake-*.timer` units and
> `striatum-warmtier-autoingest.timer` belong to **striatum-next**
> (`~/git/striatum-next`, a separate live system driving hippo/engram/praxis/
> vitae/gpu-fleet/fleet-knowledge). They were mistakenly disabled during this
> retirement and restored (enabled+active) the same day.
>
> **Warmtier decoupled from the dead daemon (same day):** removed the
> `daemon-socket.conf` drop-in (it pointed `striatum corpus export` at the
> retired daemon's `/run/striatum/rpc/daemon-go.sock`; vendored copy deleted
> from this repo — restore from git history). The `striatum_exhaust` and
> `lane_trajectory` feedstocks can no longer be fed (their producer is the
> retired daemon; both were fully caught up — final run anti-joined 31 /
> 122 592 rows, 0 new) and will self-quarantine after 3 consecutive failures
> (warmtier's designed poison lane). The `operator_log` feedstock — warmtier's
> live leg — continues; verified `ingested`, unit `Result=success` post-change.
> The `corpus-bridge.conf` drop-in + `bridge-bin` shim (pre-archrem `striatum`
> binary) were left in place: harmless, and they produce a clearer error
> (`daemon unreachable`) than the current binary's `unknown verb` if the export
> path is ever poked. If striatum-next grows an exhaust producer, wire it as a
> new bridge rather than resurrecting this socket.
>
> **Deliberately left in place** (reversible retirement, no data destroyed):
> unit files on disk (only `wants/` symlinks removed), the binary + secrets, the
> `striatum_daemon` database (29 GB, in the last pgBackRest backup), and the
> `token-dashboard*` services (still running — they only read the
> `token_dashboard` DB; decide their fate separately).
>
> To reclaim the 29 GB: `sudo -u postgres psql -c 'DROP DATABASE striatum_daemon'`
> — only after confirming the pgBackRest stanza retains a copy, and note that the
> Prometheus `postgres_exporter` connects *to* that DB (repoint it to `postgres`
> first, see `../observability/`). The `ALTER DATABASE`/table-level tuning in
> `../postgres/desired.md` dies with the DB.
>
> The rest of this file is preserved as historical record of how it was wired.

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
| ~~`warmtier-autoingest.service.d-daemon-socket.conf`~~ | ~~`…/striatum-warmtier-autoingest.service.d/daemon-socket.conf`~~ | — | **removed 2026-07-21** (live + vendored) — pointed at the retired daemon's socket; see retirement banner |
| — (secrets, never vendored) | `~/.config/striatum/blob.env` | halbritt 0600 | Garage S3 keys; referenced by the unit as `EnvironmentFile=` |
| — (secrets, never vendored) | `~/.config/striatum/daemon.toml` | halbritt 0600 | `postgres_url` (password DSN) read by the daemon |
| [`striatum-lane-cred-resync.sh`](striatum-lane-cred-resync.sh) | `/usr/local/bin/striatum-lane-cred-resync.sh` | root:root 0755 | copies the operator's Claude OAuth credential → `striatum-lane` (0600), rotating-token-safe — [striatum#583](https://github.com/halbritt/striatum/issues/583) |
| [`striatum-lane-cred-resync.service`](striatum-lane-cred-resync.service) | `/etc/systemd/system/striatum-lane-cred-resync.service` | root:root 0644 | root oneshot wrapping the script |
| [`striatum-lane-cred-resync.timer`](striatum-lane-cred-resync.timer) | `/etc/systemd/system/striatum-lane-cred-resync.timer` | root:root 0644 | fires the resync every 15 min (+2 min after boot) |
| [`striatum-worktree-gc.sh`](striatum-worktree-gc.sh) | `/usr/local/bin/striatum-worktree-gc.sh` | root:root 0755 | periodic worktree GC + ownership normalization; quiescence-gated chown — [striatum#612](https://github.com/halbritt/striatum/issues/612) |
| [`striatum-worktree-gc.service`](striatum-worktree-gc.service) | `/etc/systemd/system/striatum-worktree-gc.service` | root:root 0644 | root oneshot wrapping the script |
| [`striatum-worktree-gc.timer`](striatum-worktree-gc.timer) | `/etc/systemd/system/striatum-worktree-gc.timer` | root:root 0644 | fires the GC every 6h (+10 min after boot) |
| [`migration/`](migration/) | — | — | verbatim copy of the pre-migration user unit + drop-ins (provenance + revert source) |
| [`striatum-wake.service.d-openrouter-env.conf`](striatum-wake.service.d-openrouter-env.conf) | `~/.config/systemd/user/striatum-wake-<repoid>.service.d/openrouter-env.conf` — **one per wake unit** | halbritt 0644 | injects `EnvironmentFile=-%h/.config/striatum/openrouter.env` into every striatum-next liveness wake |
| [`striatum-drive.sh`](striatum-drive.sh) | `~/.local/bin/striatum-drive` | halbritt 0755 | canonical **keyed** operator drive entrypoint — sources `openrouter.env` by reference, then execs `striatum … drive`. Use for any hand/agent-triggered drive so garden lanes get the key |
| — (secrets, never vendored) | `~/.config/striatum/openrouter.env` | halbritt 0600 | `OPENROUTER_API_KEY` = static OpenRouter key for the judgment lanes (backends/{glm,kimi}) |

**Edit here, then re-install.** After editing `striatumd.service`:

```bash
sudo install -m 0644 ~/git/proximal/striatum/striatumd.service /etc/systemd/system/striatumd.service
sudo systemctl daemon-reload
sudo systemctl restart striatumd        # KillMode=process: leaves live lane helpers running
systemctl status striatumd
```

## Lane Claude-credential resync (`striatum-lane-cred-resync.timer`)

Supervised lanes run as the `striatum-lane` OS user and authenticate to Claude via
`~striatum-lane/.claude/.credentials.json`. That file used to be a point-in-time
copy of the operator's (`halbritt`) credential taken at lane launch — and Claude
OAuth uses **rotating refresh tokens**, so once the operator's CLI refreshes, a
frozen copy holds a stale refresh token and can no longer self-refresh. During a
long dogfood the lane copy expired and every claude lane launched afterward wedged
on `agent_mcp_discovery_stall` → `recovery_exhausted` / red doctor
([striatum#583](https://github.com/halbritt/striatum/issues/583)).

A root oneshot (`striatum-lane-cred-resync.sh`), fired every 15 min by the timer,
copies the operator's *current* credential to the lane home (`0600`, owned by the
lane user) whenever the content differs. 15 min is comfortably under the
access-token TTL, so the lane copy is never more than one interval stale. This is
the **operational backstop**; the complementary supervisor-relaunch resync is
RFC 0165 (in design). Caveat: it can only forward a *fresh* operator credential —
if the operator's own `~/.claude/.credentials.json` is itself stale (no interactive
or daemon refresh for hours) the lane inherits that staleness, no worse than today.

```bash
sudo install -m 0755 ~/git/proximal/striatum/striatum-lane-cred-resync.sh /usr/local/bin/striatum-lane-cred-resync.sh
sudo install -m 0644 ~/git/proximal/striatum/striatum-lane-cred-resync.service /etc/systemd/system/
sudo install -m 0644 ~/git/proximal/striatum/striatum-lane-cred-resync.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now striatum-lane-cred-resync.timer
systemctl list-timers striatum-lane-cred-resync.timer    # confirm NEXT is scheduled
```

## OpenRouter judgment-lane credential (`openrouter-env.conf` drop-ins)

striatum-next's judgment-is-plural arc binds the Principal-named frontier models
(`z-ai/glm-5.2`, `moonshotai/kimi-k2.6`) as execution backends
(`striatum-next/backends/{glm,kimi}`, declaration_version 2 — pivoted from the
Vertex Model Garden 2026-07-08 on economics; account rationale lives in
[halbritt/openrouter](https://github.com/halbritt/openrouter), the
inference-provider provenance repo). The declarations name an env var
(`-api-key-env OPENROUTER_API_KEY`) — the env-name credentials pattern: no
secret in a declaration, a ledger record, or git. The value is a **static
OpenRouter key** in `~/.config/striatum/openrouter.env` (0600), so unlike the
decommissioned Vertex predecessor (`striatum-garden-cred-refresh.{service,timer}`
+ rotating ~1h OAuth token, removed 2026-07-08) there is no refresh machinery —
just the drop-in. Every `striatum-wake-*.service` gets it so autonomous,
timer-driven drives see the credential with nobody at the keyboard. New fleet
registrations mint new wake units: **install the drop-in for each new
`striatum-wake-<repoid>.service`** (the drop-in file is identical for all of them).

```bash
for u in $(ls ~/.config/systemd/user/ | grep -oE '^striatum-wake-[0-9a-f]{8}\.service$'); do
  mkdir -p ~/.config/systemd/user/$u.d
  install -m 0644 ~/git/proximal/striatum/striatum-wake.service.d-openrouter-env.conf ~/.config/systemd/user/$u.d/openrouter-env.conf
done
systemctl --user daemon-reload
systemctl --user show striatum-wake-<repoid> -p EnvironmentFiles   # expect openrouter.env
```

⚠️ **The drop-in only keys wake-/timer-driven drives.** The EnvironmentFile is a
property of the `striatum-wake-*.service` units, so a drive started any other way
— a bare `striatum … drive`, `systemd-run --user --scope … drive`, or an agent
shell — does **not** carry `OPENROUTER_API_KEY`. Every garden lane such a drive
dispatches then crashes `OPENROUTER_API_KEY named but unset` (exit 2) and drains
`missing required outputs: [review-ledger]`; the keyless environment propagates
top-drive → lane supervisor → `adapter_wake` child, so one keyless hand-drive can
exhaust the review redispatch budget across several passes and escalate
`bounds_exhausted` (observed 2026-07-08, escalations 15571/15618). **For any
hand- or agent-triggered drive use the keyed entrypoint** `striatum-drive`
(`proximal/striatum/striatum-drive.sh`, installed to `~/.local/bin`), which
sources `openrouter.env` by reference before driving. A bare `striatum drive` is
safe only for repos with no OpenRouter-keyed backend.

## Worktree GC (`striatum-worktree-gc.timer`)

The daemon gives each job its own git worktree under `~/git/striatum/.striatum/worktrees/`.
Supervised lanes run as `striatum-lane` and write **lane-owned** files both inside those
worktrees and into their per-worktree reflog (`.git/worktrees/<id>/logs/HEAD`). The daemon
and `git` both run as `halbritt`, so once a run is terminal those lane-owned files block
cleanup from the operator side:

- `git gc` / `git reflog expire --all` → `failed to create HEAD.lock: Permission denied`
- `striatum worktree gc` → `git worktree remove … Permission denied`

Left alone this compounds: on 2026-06-24 the checkout had **240 registered worktrees** and
the host's `git gc --auto` had been silently failing for weeks ([striatum#612](https://github.com/halbritt/striatum/issues/612)).

A root oneshot (`striatum-worktree-gc.sh`), fired every 6h by the timer, does the cleanup the
operator can't from a plain shell:

1. `striatum worktree gc` — the daemon-blessed sweep (removes only terminal worktrees
   reachable from the run branch; retains divergent pins). It runs **as the operator over
   the unix socket**, with the CLI capability-token cache refreshed each run from the live
   `/run/striatum/client-token`, so it survives a daemon boot-epoch rotation (cf.
   [striatum#512](https://github.com/halbritt/striatum/issues/512)). The MCP-HTTP endpoint is
   per-login-session, so the socket is the only session-independent transport.
2. **Only when the daemon reports zero active runs**, `chown -R halbritt:halbritt` the
   `.striatum/worktrees` + `.git/worktrees` trees (normalizing lane-owned debris so the
   daemon/git can manage it) then a re-sweep. The quiescence gate guarantees it never chowns
   a file an active lane is mid-write.
3. `git worktree prune` + `git gc --auto`.

This is the **operational backstop**; the real fix (setgid + default ACL on the worktree tree,
or daemon-side publish-from-staging so leaves are never lane-owned) lives in
[striatum#612](https://github.com/halbritt/striatum/issues/612) — **retire this timer when it
lands**. The first run took the box from 240 → 74 worktrees (74 = main + 73 divergent pins the
daemon retains) and restored a clean `git gc`.

```bash
sudo install -m 0755 ~/git/proximal/striatum/striatum-worktree-gc.sh /usr/local/bin/striatum-worktree-gc.sh
sudo install -m 0644 ~/git/proximal/striatum/striatum-worktree-gc.service /etc/systemd/system/
sudo install -m 0644 ~/git/proximal/striatum/striatum-worktree-gc.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now striatum-worktree-gc.timer
systemctl list-timers striatum-worktree-gc.timer    # confirm NEXT is scheduled
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
