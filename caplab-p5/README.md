# CAPLAB P5 recovery host surface on `proximal`

Desired state for the bounded CAPLAB-23/P5 failure and recovery campaign
selected by standalone CAPLAB ADR 0009 and its corrective continuations in ADR
0010, ADR 0011, and ADR 0012. CAPLAB owns product decisions and the recovery
implementation at `/home/halbritt/git/caplab`; this subsystem owns only
temporary Proximal identities, installed source and configuration, backup
serialization, isolated restore, root staging, expiry, and disablement.

This is an authorized execution surface, not evidence that P5 has run or
passed. The P4 subsystem under `caplab-runtime/` is unchanged and its preserved
registration is read-only control state.

## Frozen boundary

| Surface | Value |
|---|---|
| corrected executor source | [`SOURCE_COMMIT`](SOURCE_COMMIT) |
| registered request source | `c82b5512661c537db06f725af70198eccc818358` |
| data campaign | `caplab-p5-recovery-2026-07-16` |
| corrective campaign | `caplab-p5-corrective-2026-07-16` |
| isolated-restore correction | `caplab-p5-isolated-restore-corrective-2026-07-16` |
| isolated-restore authorization | ADR 0011 SHA-256 `d110fd0e74285f22ecffb31e36eae256190a4eeaf50cd082cd14fc9c03cc15fb` |
| recovery-compatibility correction | `caplab-p5-recovery-compatibility-corrective-2026-07-17` |
| recovery-compatibility authorization | ADR 0012 SHA-256 `7dabe6891bc1679ccbad4a893ba864ba42a59a301cbce472de15a2b03fbd64f0` |
| authorization expiry | `2026-07-23T23:59:59Z` |
| operation | `op-p5-recovery-0001` |
| PostgreSQL | `caplab`, `caplab_v0` |
| Garage | `caplab-v0`, exact content-addressed P5 key |
| local copy | `/nvr/caplab/v0`, exact content-addressed P5 key |
| operator | `caplab_p5_operator` |
| independent verifier | `caplab_p5_verifier` |

[`recovery.toml`](recovery.toml) freezes both authorization hashes, both source
identities, the request, content, object, manifest, and identity-layer hashes.
It contains no credentials.

## Canonical files and install paths

| Repository file | Installed path |
|---|---|
| `caplab-p5-hostctl.py` | `/usr/local/libexec/caplab-p5-hostctl` |
| `recovery.toml` | `/etc/caplab-p5/recovery.toml` |
| `SOURCE_COMMIT` | `/etc/caplab-p5/SOURCE_COMMIT` |
| `bin/*` | `/usr/local/libexec/caplab-p5/*` |
| restic drop-ins | `/etc/systemd/system/restic-{backup,prune}.service.d/20-caplab-p5-lock.conf` |
| expiry unit and timer | `/etc/systemd/system/caplab-p5-expiry.{service,timer}` |

Generated state and credentials are not committed:

- `/var/lib/caplab-p5-recovery.state.json` is a root-only, secret-free
  lifecycle record;
- `/opt/caplab-p5/venvs/<source-commit>` is the exact installed CAPLAB source;
- `/etc/caplab-p5/credentials/<role>/garage.json` is role-owned `0400`;
- `/var/tmp/caplab-p5-execution.*` is the root-only execution record;
- `/var/tmp/caplab-p5-recovery.*` stages only the exact P5 bytes; and
- `/var/tmp/caplab-p5-pgrestore` is the isolated PostgreSQL restore target.
- `/var/lib/caplab-p5-isolated-restore.state` is the root-only guard record
  for the exact isolated target and live-cluster identity.

`run-receipt` requires `CAPLAB_P5_EXECUTION_ROOT` to name a root-only
`/var/tmp/caplab-p5-execution.*` directory and writes one immutable command
description, stdout, stderr, and direct numeric `.rc` per label. Commands must
not carry credentials in arguments.

`pgbackrest-restore-isolated BACKUP_LABEL` restores only into
`/var/tmp/caplab-p5-pgrestore` and starts PostgreSQL 17 on loopback port
`55435`. It writes target-owned PostgreSQL, HBA, ident, and recovery-only
configuration, rejects TCP clients, and permits only local peer access by the
`postgres` verifier path. Its explicit `max_wal_senders=10` matches the
selected backup's recovery control value; it grants process capacity only,
while explicit HBA rules reject local and TCP physical replication. After
promotion, the helper proves the effective value, zero active replication
senders, and HBA rejection of a loopback TCP database connection. The
root-only target marker and external guard record freeze the selected backup,
target, authorization, configuration hashes, and live postmaster identity.

Both helpers observe the live cluster read-only before acting and verify its
data directory, postmaster PID, port, start time, and active state on exit. The
stop path refuses marker or hash drift, requires a separately queryable
isolated endpoint and PID, rejects the live PID, and invokes `pg_ctl` only with
the exact isolated target. It does not remove the target; removal remains gated
on the ADR 0011 interim independent report.

## Backup lock

The backup and prune services are both replaced by wrappers that hold one
exclusive `flock` on `/run/lock/caplab-backup.lock` across their complete
command sequences. `restic-check-locked` takes the same lock and runs only
non-destructive `restic check`. Installing the prune wrapper does not execute
`restic prune`; ADR 0009 does not authorize a manual prune.

## Repository checks

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s caplab-p5/tests -v
python3 caplab-p5/caplab-p5-hostctl.py --help
shellcheck caplab-p5/bin/* caplab-p5/install-desired-state.sh
systemd-analyze verify \
  caplab-p5/systemd/caplab-p5-expiry.service \
  caplab-p5/systemd/caplab-p5-expiry.timer
git diff --check
```

## Live sequence

1. From a clean committed Proximal worktree, run repository checks and
   `sudo caplab-p5/install-desired-state.sh`.
2. Run `sudo /usr/local/libexec/caplab-p5-hostctl preflight`, assign the fresh
   verifier, then run `bootstrap`.
3. Create one root-only execution directory. Run every CAPLAB command through
   a receipt wrapper that writes stdout, stderr, and a direct numeric `.rc`.
4. Preserve and remove only the already-stopped ADR 0011 target, then, under
   ADR 0012, retry only backup `20260712-010203F_20260716-195901D` with the
   committed isolated helper. Query the restored database and obtain the fresh
   verifier's interim report while it remains available.
5. Stop only the verified isolated instance, re-prove the live identity,
   preserve the evidence, remove only the isolated target, and obtain the
   verifier's final report. ADR 0012 does not authorize dependency creation,
   byte deletion, database purge, P6, or CAPLAB acceptance.
