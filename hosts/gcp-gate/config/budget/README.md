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

## Enforcement

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
    rsyncs `~/agent-ee-gate/ci-logs/` to
    `proximal:~/agent-ee-gate-c4-preserved/<stamp>/`.
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
