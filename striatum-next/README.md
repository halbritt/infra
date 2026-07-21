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

Timers: `OnActiveSec`/`OnUnitInactiveSec` 900 s floors (some with
`OnCalendar=*:0/5` via `50-calendar-floor.conf` drop-ins), `Persistent=true`.
Service drop-ins: `override.conf` (`KillMode=process` — detached lane supervisors
must outlive the oneshot, see `../systemd-user/README.md`) and
`openrouter-env.conf` (`EnvironmentFile=-~/.config/striatum/openrouter.env` —
pointer only, the key lives outside this repo).

## warmtier

`striatum-warmtier-autoingest.{service,timer}` — unattended hippo ingest
(`~/git/striatum-warmtier`). Its `corpus-bridge.conf` drop-in prepends
`~/.local/lib/striatum-warmtier/bridge-bin` (a `striatum` symlink to the
pre-archrem binary) so `striatum corpus export` resolves; with striatumd retired
the export fails and the exhaust/lane-trajectory feedstocks self-quarantine —
only the `operator_log` leg is live. The former `daemon-socket.conf` drop-in was
removed 2026-07-21 (see `../striatum/README.md`).

## ⚠️ Known fragilities (found at capture, left as-is)

- **`019f3d58` (hippo) execs a binary out of a Claude session scratchpad**:
  `ExecStart=/tmp/claude-1000/-home-halbritt-git-hippo/c0e99ee4…/scratchpad/striatum-head` —
  gone on reboot or scratchpad GC, at which point the hippo floor dies with
  203/EXEC. Repoint to a durable path (`~/git/striatum-next/bin/striatum` or a
  pinned copy under `~/.local/bin`).
- `019f22ef` mixes ExecStart binaries with the others (`~/.local/bin/striatum` vs
  `~/git/striatum-next/bin/striatum`) — two build channels for the same fleet.
- `019f3b99` and `019f3d58` lack the `KillMode=process` override the other five
  have; their dispatched lanes die with the oneshot.
- Four orphaned `striatum-wake-019f22ef…-<hash>.timer.d/` dirs remain from
  GC'd wake units (their `.timer` files no longer exist); vendored as found.
