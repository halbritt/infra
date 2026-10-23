# Campaign GCP budget (`gcp-spend`)

Owner, 2026-10-22: "keep the gcp spend under control, I don't want to exceed $100".

That is the **cumulative ceiling for the agent-ee/kicad-route telemetry-pod
campaign** in project `heath-stuff`. It covers:

- gate and builder VMs;
- `agent-ee-gate-c4`;
- overflow and experiment VMs;
- their disks and image storage;
- related charges.

It is not daily, per VM or per billing period. Splitting jobs does not reset
it. There is no spend authorization beyond it.

| Piece | Where | Role |
|---|---|---|
| [gcp-spend](gcp-spend) | run from this checkout on proximal | `status` itemized estimate, `reserve`/`release` launch ledger, `guard` |
| [gcp-spend-guard.service](gcp-spend-guard.service), [.timer](gcp-spend-guard.timer) | `~/.config/systemd/user/` on proximal | `gcp-spend guard` every 15 min |
| Ledger | `~/.local/share/infra/gcp-budget/ledger.jsonl` on proximal | reservations (worst case), closes, guard events |

## How spend is established

The billing data is not readable here: there is no billing export, the Budget API
is disabled, and enabling either is a separate change. So spend is an
**estimate**:

- **Compute:** GCE admin audit log lifetimes since 2026-10-21. Successful
  create, start or resume opens running time; stop, preempt, guest poweroff,
  suspend or delete closes it.
- **Disks:** each boot disk counts from create to delete. c4's 200 GB Hyperdisk
  is billed while c4 is stopped too.
- **Pricing:** catalog Spot prices measured 2026-10-22 (c2d $0.01428/vCPU-h +
  $0.001915/GiB-h in us-west1; c4 $0.02074 + $0.002357 in us-central1),
  pd-balanced $0.10/GB-month, the c4 Hyperdisk at about $63/month, and image
  storage at $0.05/GB-month.
- **Safety factor:** ×1.25.
- **Allowance:** $3 for egress, logging and other unmetered charges.
- **Hold point:** launches stop at **$90**, which leaves $10 of headroom.
- **Exclusions:** `tailscale-exit-node` is not campaign work and is excluded.

## Enforcement (controls in place; under agent-521/522 review, so the cap is not yet declared enforced)

- **Atomic decisions.** One process lock (`ledger.lock`) covers fresh estimate,
  decision and ledger write for `reserve`, `release` and guard events, so
  concurrent reservations cannot both spend the same remainder. Durations must be
  finite and positive, and disk sizes non-negative.
- **Reconciliation with live inventory.** Every estimate lists live instances
  AND disks:
  - a live instance missing from the (possibly delayed) audit history is charged
    from its creation time;
  - a live disk is charged until it is gone, even if its instance was deleted
    or it never had one;
  - an unpriced instance shape or disk type, or a lifecycle query that returns
    a full page of 5000 events (possibly truncated), makes the estimate unknown,
    so `reserve` refuses.

  The shapes of live instances are cached (`shapes.json`) so they stay
  priceable after deletion.
- **Disk accounting.** Every live disk is priced from its OWN listed type, size
  and provisioning: pd-balanced, pd-standard and pd-ssd per GB, and
  hyperdisk-balanced from capacity plus provisioned IOPS above 3000 plus
  throughput above 140 MiB/s. A disk sharing a VM's name is no exception. An
  unknown type or missing Hyperdisk provisioning refuses. Every live disk is
  both accrued since creation and counted in hourly commitments, whether or not
  its VM still exists. History prices only disks that are gone.
- **Contradictory history.** A VM that is live RUNNING while its history ends
  in a stop (a delayed or missing restart) is charged from its last recorded
  event.
- **Notification.** Every guard stop or failed stop sends a bounded
  (60 s) Cairn notice to agent-519 (owner notifications) through the existing
  hosted profile (`cairn agent remember` + `cairn publish --to agent/…`). The
  delivery result ("notified … event X" or "NOTIFY FAILED") is recorded in the
  ledger event. journald alone is not counted as notification.
- **No expiry release.** Open reservations stay charged past their nominal end
  until `release` after verified teardown.

- **Launches.** `run-overflow.sh`, `run-gate.sh` and `build-image.sh` call
  `gcp-spend reserve` before `instances create`. The reservation is the
  machine's worst case (rate × max-run-duration × 1.25), plus the current hourly
  commitments over the same window. It must fit the remaining allowance, or no
  VM is created. If spend cannot be established (a gcloud failure, an unknown
  instance shape, an unpriced machine type), the launch is refused. Every
  launched VM carries `--max-run-duration` and DELETE on termination. The
  reservation is released only after verified teardown.
- **c4.** `agent-ee-gate-c4` costs about $1.31/h running, plus its disk.
  - Its idle stop (30 min) still applies.
  - The guard stops c4 when the remaining allowance would not cover the next
    hour, or when spend has been unknown for 3 consecutive checks. It first
    tries a bounded best-effort rsync of `~/agent-ee-gate/ci-logs/` to
    `proximal:~/agent-ee-gate-c4-preserved/<stamp>/`. It always attempts the
    stop, and records the preservation result truthfully ("preserved", "FAILED"
    or "TIMED OUT"). A failed stop is recorded and exits non-zero.
  - Restarting c4 (`gcloud compute instances start`) is a launch: run
    `gcp-spend reserve --label 'c4 restart' --machine-type c4-highcpu-48
    --max-hours H` first.
- **Alerts are not enforcement.** The guard and the reservations are.

```sh
~/git/infra/hosts/gcp-gate/config/budget/gcp-spend status        # itemized estimate and remaining allowance
journalctl --user -u gcp-spend-guard -n 5 -o cat                 # guard verdicts
```

## First reconciliation (2026-10-23 00:09Z)

| Item | Shape | VM h | Disk h | Estimate |
|---|---|---:|---:|---:|
| agent-ee-gate-c4 (running) | c4-highcpu-48 + 200 GB hyperdisk | 11.82 | 19.62 | $16.14 |
| 2 gate VMs (14ef7275) | c2d-highcpu-16 | 0.77 | 0.77 | $0.23 |
| 2 image builders | c2d-highcpu-16 | 0.30 | 0.40 | $0.10 |
| agent-524 Rust, PyPy VMs | c2d-highcpu-4 | 0.86 | 0.86 | $0.07 |
| overflow smoke | c2d-highcpu-4 | 0.06 | 0.06 | $0.01 |
| image agent-ee-gate-20261022-0352 (7.5 GB) | | | | $0.01 |
| **metered** | | | | **$16.55** |

Accrued estimate: $16.55 × 1.25 + $3 allowance = **$23.69**. Committed: $1.64/h
with safety, almost all c4 running. Remaining before the $90 hold: **$66.31**,
about 40 h of c4 at the current rate. Measured: lifecycle times and machine
shapes. Estimated: prices (catalog, not billing), egress and logging.
