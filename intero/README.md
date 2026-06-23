# proximal/intero — sense-organ surfacing timers

Two `--user` systemd timers that run the **intero blind-spot ledger** — Layer 0
("interoception") of the `showerthoughts` coordination spine. The code, contract, and
rollout record live in [`~/git/showerthoughts/coordination/intero/`](../../showerthoughts/coordination/intero/)
(`SPEC.md`, `ledger.py`, `intero.py`, `ROLLOUT.md`); this dir is **only** the box's
desired-state for the two scheduled surfaces. Stateless, zero-GPU, no daemon — these
timers run a Python script that reads per-repo `.intero.json` files and prints; they
never gate anything.

This dir holds the **canonical** copies; the box runs installed copies under
`~/.config/systemd/user/`. Edit here, re-install, `daemon-reload`.

## The two surfaces

| Unit | Cadence | What it runs | Digest |
|---|---|---|---|
| `intero-ledger.{service,timer}` | daily, `*-*-* 09:00` | `ledger.py` — the blind-spot ranking ("which repos have gone past their own promised heartbeat") | `~/.local/state/intero/ledger-latest.txt` |
| `intero-drift.{service,timer}` | weekly, `Mon *-*-* 09:15` | `ledger.py --drift` — per repo, declared cadence beside the raw last-N actual inter-write intervals (displays, never interprets) | `~/.local/state/intero/drift-latest.txt` |

Both are `Type=oneshot`, `Persistent=true` (a run missed while the box was off is
caught up), and write to the journal as well as the digest file. The weekly read is
offset 15m after the daily so they never collide.

## File → install-path

```
intero/intero-ledger.service  ->  ~/.config/systemd/user/intero-ledger.service
intero/intero-ledger.timer    ->  ~/.config/systemd/user/intero-ledger.timer
intero/intero-drift.service   ->  ~/.config/systemd/user/intero-drift.service
intero/intero-drift.timer     ->  ~/.config/systemd/user/intero-drift.timer
```

Re-install after editing:

```bash
cp intero/intero-*.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now intero-ledger.timer intero-drift.timer
```

## Inspect / operate

```bash
systemctl --user list-timers 'intero-*'          # both armed + next-fire
journalctl --user -u intero-ledger -n 50         # daily ledger output
journalctl --user -u intero-drift  -n 50         # weekly drift output
cat ~/.local/state/intero/ledger-latest.txt      # latest daily digest
cat ~/.local/state/intero/drift-latest.txt       # latest weekly digest
systemctl --user disable --now intero-drift.timer # stop the weekly read
```

`Linger=yes` for the `halbritt` user lets both fire off-session (set once at the
account level, not in these units).

## Why versioned here

The units are the box's desired-state for a recurring surface; capturing them keeps the
sense organ's own liveness auditable across agents and survivable across a reimage —
the same provenance discipline the organ itself enforces on every other repo.
