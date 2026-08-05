# striatum-next

Host wiring for **striatum-next** (`~/git/striatum-next`) — the successor to the
retired `striatumd` (see [`../striatum/README.md`](../striatum/README.md), retired
2026-07-21). Unlike the old daemon there is no long-running service: `striatum drive`
runs are fired by per-graph **user-scope wake timers** ("liveness floors"), plus the
warmtier ingest timer. This directory vendors those unit specs verbatim; the
application itself (binary `~/git/striatum-next/bin/striatum`, catalog, policy) is
not vendored here.

Captured 2026-07-21, prompted by this day's incident: the wake timers were
mistakenly disabled during the striatumd retirement because nothing recorded that
`striatum-wake-*`/`striatum-warmtier-*` belong to a *different, live* system.
This directory is that record.

## Layout

`systemd-user/` mirrors `~/.config/systemd/user/` names exactly (units +
`.d/` drop-in dirs). Install = copy back + `systemctl --user daemon-reload` +
`enable --now` the timers.

## The graphs (repoid8 → repo)

| wake unit | repo |
|---|---|
| `019f22ef…` | `~/git/striatum-next` (itself) |
| `019f274c…` | `~/git/praxis` |
| `019f2e17…` | `~/git/engram` |
| `019f3b99…` | `~/git/fleet-knowledge` |
| `019f3d21` | `~/git/vitae` |
| `019f3d37` | `~/git/gpu-fleet` |
| `019f3d58` | `~/git/hippo` |

Timers: `OnActiveSec`/`OnUnitInactiveSec` 900 s floors, `Persistent=true`.

**Shared drop-in dir** `striatum-wake-.service.d/` (systemd truncated-prefix
matching, v247+): `override.conf` (`KillMode=process` — detached lane supervisors
must outlive the oneshot, see `../systemd-user/README.md`) and
`openrouter-env.conf` (`EnvironmentFile=-~/.config/striatum/openrouter.env` —
pointer only, the key lives outside this repo). One dir covers every current and
future `striatum-wake-*` unit, both name shapes. It replaced (2026-07-21) the
per-repoid8 `striatum-wake-<repoid8>.service.d/` dirs, which — despite
`../systemd-user/README.md`'s claim — **never applied to long-named units**
(a drop-in dir must exact-match or dash-boundary-prefix the unit name;
`019f22ef` is a mid-token truncation). Until then, four of seven graphs ran
without the openrouter env and with default `KillMode=control-group`.

**⚠️ ExecStart is self-referential** (`wakeCommand` → `os.Executable()`,
`internal/cli/root.go`): every drive run re-projects the wake units with *the
binary that ran* as ExecStart. Consequence: a drive launched from a throwaway
binary bakes that path into the fleet's liveness floor (this is exactly how the
hippo unit came to exec from a Claude session scratchpad in `/tmp`), and
hand-edits to unit files are overwritten on the next drive. Fix paths, not unit
files: launch drives only from durable binaries.

## warmtier

`striatum-warmtier-autoingest.{service,timer}` — unattended hippo ingest
(`~/git/striatum-warmtier`). Its `corpus-bridge.conf` drop-in prepends
`~/.local/lib/striatum-warmtier/bridge-bin` (a `striatum` symlink to the
pre-archrem binary) so `striatum corpus export` resolves; with striatumd retired
the export fails and the exhaust/lane-trajectory feedstocks self-quarantine —
only the `operator_log` leg is live. The former `daemon-socket.conf` drop-in was
removed 2026-07-21 (see `../striatum/README.md`).

## Fragilities found at capture — fixed 2026-07-21 (same day)

- **`019f3d58` (hippo) exec'd a binary out of a Claude session scratchpad**
  (`/tmp/claude-1000/…/scratchpad/striatum-head`, a Jul 12 build — would die
  203/EXEC on reboot/GC, and every firing re-baked the /tmp path via the
  self-referential ExecStart above). Fixed by firing one drive from
  `~/git/striatum-next/bin/striatum`: it self-projected the current-generation
  long-named unit with the durable path; the stale legacy short pair
  (`striatum-wake-019f3d58.{service,timer}`) was then disabled and removed.
  The scratchpad binary is preserved at
  `~/.local/bin/striatum.bak-hippo-scratchpad-jul12`.
- **Four of seven graphs ran without `KillMode=process` + openrouter env**
  (dead per-repoid8 drop-in dirs, see above). Fixed by the shared
  `striatum-wake-.service.d/`; verified post-change: all 7 wake services show
  `KillMode=process` + the EnvironmentFile.
- Four orphaned `019f22ef…*.timer.d/` dirs from GC'd wake units — removed.
- Still open: `019f22ef`/`019f274c` exec `~/.local/bin/striatum` while the
  rest exec `~/git/striatum-next/bin/striatum` — two build channels for one
  fleet (both durable, so left alone; converge when convenient by running one
  drive per graph from the chosen binary).
