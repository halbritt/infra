# CAPLAB P5 recovery host surface on `proximal`

Desired state for the bounded CAPLAB-23/P5 failure and recovery campaign
selected by standalone CAPLAB ADR 0009. CAPLAB owns product decisions and the
recovery implementation at `/home/halbritt/git/caplab`; this subsystem owns
only temporary Proximal identities, installed source and configuration,
backup serialization, isolated restore, root staging, expiry, and disablement.

This is an authorized execution surface, not evidence that P5 has run or
passed. The P4 subsystem under `caplab-runtime/` is unchanged and its preserved
registration is read-only control state.

## Frozen boundary

| Surface | Value |
|---|---|
| CAPLAB source | [`SOURCE_COMMIT`](SOURCE_COMMIT) |
| campaign | `caplab-p5-recovery-2026-07-16` |
| authorization expiry | `2026-07-23T23:59:59Z` |
| operation | `op-p5-recovery-0001` |
| PostgreSQL | `caplab`, `caplab_v0` |
| Garage | `caplab-v0`, exact content-addressed P5 key |
| local copy | `/nvr/caplab/v0`, exact content-addressed P5 key |
| operator | `caplab_p5_operator` |
| independent verifier | `caplab_p5_verifier` |

[`recovery.toml`](recovery.toml) freezes the authorization, request, content,
object, manifest, and identity-layer hashes. It contains no credentials.

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

`run-receipt` requires `CAPLAB_P5_EXECUTION_ROOT` to name a root-only
`/var/tmp/caplab-p5-execution.*` directory and writes one immutable command
description, stdout, stderr, and direct numeric `.rc` per label. Commands must
not carry credentials in arguments.

`pgbackrest-restore-isolated BACKUP_LABEL` restores only into
`/var/tmp/caplab-p5-pgrestore` and starts PostgreSQL 17 on loopback port
`55435`. It never stops or replaces the live cluster. The paired stop command
does not remove the target; removal remains gated on independent verification.

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
4. Follow ADR 0009 steps in order: P4 control, P5 registration and refusals,
   controlled interruption, object and copy recovery, locked restic check,
   pgBackRest backup and isolated restore, dependency refusal, staged byte
   removal, guarded database purge, and disablement.
5. Do not remove the isolated restore or root staging until the independent
   verifier preserves its report. Verification can pass or fail P5; it cannot
   accept CAPLAB or authorize P6.
