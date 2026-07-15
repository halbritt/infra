# CAPLAB P4 host surface on `proximal`

Desired state for the standalone Agent Capability Lab's bounded P4 synthetic
round trip. CAPLAB owns its runtime and research records in
`/home/halbritt/git/caplab`; this Proximal subsystem owns only the host
integration selected by CAPLAB ADR 0007 and moved to the standalone repository
by ADR 0008.

This branch has not been installed. No CAPLAB account, group, path, PostgreSQL
namespace, Garage bucket, key, credential, timer, or synthetic attempt was
created while authoring it.

## Current source pin

[`SOURCE_COMMIT`](SOURCE_COMMIT) and `runtime.runtime_commit` in
[`runtime.toml`](runtime.toml) both name reviewed standalone CAPLAB runtime
commit `405efb136b221d1270578417c64b3f7878383f32`. Preflight requires the exact
checkout to be clean at that commit. It also requires
`src/caplab/runtime/__main__.py` and the SHA-256-hash-locked
`src/caplab/runtime/requirements.lock`; a resolvable Git identity alone is not
runtime fitness. Change both pin surfaces together under a later CAPLAB
decision and authorization.

## Fixed boundary

| Surface | Selected value |
|---|---|
| campaign | `caplab-p4-roundtrip-2026-07-15` |
| authorization expiry | `2026-07-22T23:59:59Z` |
| PostgreSQL | database `caplab`, schema `caplab_v0` |
| Garage | bucket `caplab-v0`, 1 GiB, 10,000 objects |
| object keys | `objects/sha256/<first-two>/<sha256>` |
| independent copy | `/nvr/caplab/v0/objects/sha256` |
| runtime identities | `caplab_writer`, `caplab_reader`, `caplab_verifier` |
| expiry backstop | `caplab-p4-expiry.timer`, 2026-07-22 23:50 UTC |

The writer's Garage grant is read/write, which includes deletion capability in
Garage 2.3. The runtime omits deletion operations and reconciles content, but
this is application containment rather than WORM storage.

## Canonical files and installed paths

| Repository file | Installed path | Owner and mode |
|---|---|---|
| [`caplab-hostctl.py`](caplab-hostctl.py) | `/usr/local/libexec/caplab-hostctl` | `root:root 0755` |
| [`runtime.toml`](runtime.toml) | `/etc/caplab/runtime.toml` | `root:caplab 0640` |
| [`SOURCE_COMMIT`](SOURCE_COMMIT) | `/etc/caplab/SOURCE_COMMIT` | `root:caplab 0640` |
| [`caplab-p4-expiry.service`](caplab-p4-expiry.service) | `/etc/systemd/system/caplab-p4-expiry.service` | `root:root 0644` |
| [`caplab-p4-expiry.timer`](caplab-p4-expiry.timer) | `/etc/systemd/system/caplab-p4-expiry.timer` | `root:root 0644` |

Generated state is not committed:

- `/var/lib/caplab-p4-roundtrip-2026-07-15.state.json` is a
  root-only, atomically written, secret-free lifecycle record containing the
  installed lock, pinned-Git source manifest, interpreter identity, durable
  resource journals, revocation outcomes, and store inventories;
- `/etc/caplab/credentials/<role>/garage.json` is `<role>:<role> 0400`;
- `/opt/caplab/venvs/<requirements-lock-sha256>` is `root:caplab`, group
  read/execute, and group non-writable. The OS `postgres` identity receives
  only the ACL traversal and read/execute access needed for migration; and
- `/nvr/caplab/v0` is `caplab_writer:caplab 0750`.

The host tool reads regular-file blobs directly from the exact pinned Git tree;
it never copies runtime bytes from the mutable worktree. Symlinks and other
non-regular tree entries are refused. The installed manifest binds every path,
mode, Git object, byte count, and SHA-256 to the source commit, and the tool
verifies the installed dependency lock and migration SQL byte identities. It
imports the installed runtime with an empty environment,
`PYTHONNOUSERSITE=1`, `PYTHONDONTWRITEBYTECODE=1`, and isolated Python mode.
Runtime commands do not import from the source checkout.

## Command contract

`caplab-hostctl` exposes only:

- `preflight` — require a clean, exact, runtime-fit standalone commit; active
  PostgreSQL and Garage; peer authentication; absent target names; and `/nvr`
  on ZFS;
- `bootstrap` — build the hash-locked virtual environment before creating the
  empty identities, paths, database, and bucket; install and manifest exact Git
  blobs; durably journal each resource class before mutation and automatically
  roll back a failed partial bootstrap; all peer roles remain `NOLOGIN` and no
  Garage key is issued;
- `issue-credentials` — require the expiry timer active, create three expiring
  keys, capture their values without terminal output, apply least-available
  bucket grants, write role-owned files, and then enable PostgreSQL peer login;
- `verify --phase {base,ready,armed,disabled}` — compare the lifecycle record,
  installed pin and config, installed source manifest and lock, PostgreSQL
  config/venv access, exact role attributes, ownership and privilege matrices,
  live peer identity, Garage bucket quota and exact key grants, credential
  files, OS-account lock/expiry state, and independent-copy owner/mode;
- `arm-effects` — verify `ready`, then atomically and irreversibly record the
  point after which deletion is forbidden;
- `capture-inventory --label
  {before-register,after-first-register,after-replay,after-conflict}` — record
  verifier-owned store inventories. The first effect must be exactly one
  content-addressed object and independent copy; replay and conflict must leave
  the first-effect inventory unchanged;
- `disable` — independently of source-checkout and lifecycle-record health,
  attempt every revocation layer: set peer roles `NOLOGIN`, terminate CAPLAB
  database sessions and dedicated-UID processes, delete exact campaign keys,
  remove credential files, and expire the three OS accounts. It records an
  aggregate result when possible and fails if any layer remains incomplete so
  systemd retries; and
- `rollback-empty` — only while unarmed, resume a journaled partial-bootstrap
  cleanup or, for a complete disabled base, prove zero Garage objects/uploads,
  zero CAPLAB application rows, and an empty `/nvr` root before removing the
  recorded bootstrap resources.

There is no purge, S3 object-delete, application-row-delete, restore, fault,
daemon, dashboard, model-call, or public-network command.

## Model-free repository checks

These checks make no live changes:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s caplab-runtime/tests -v
python3 caplab-runtime/caplab-hostctl.py --help
systemd-analyze calendar '2026-07-22 23:50:00 UTC'
systemd-analyze verify \
  caplab-runtime/caplab-p4-expiry.service \
  caplab-runtime/caplab-p4-expiry.timer
git diff --check
```

Before the hostctl executable is installed, `systemd-analyze verify` reports
that `/usr/local/libexec/caplab-hostctl` is absent. That expected staging warning
must disappear after installation; other unit errors are stop conditions.

## Authorized live sequence after the final runtime pin

The following is a runbook, not evidence that it has been executed. Stop if the
active CAPLAB authorization or exact source pin differs.

1. From a clean, committed Proximal desired-state worktree, prove that the
   install targets are absent and run preflight directly from the reviewed
   source before the first host mutation:

   ```bash
   test ! -e /usr/local/libexec/caplab-hostctl
   test ! -e /etc/systemd/system/caplab-p4-expiry.service
   test ! -e /etc/systemd/system/caplab-p4-expiry.timer
   test ! -e /var/lib/caplab-p4-roundtrip-2026-07-15.state.json
   sudo /usr/bin/python3 "$PWD/caplab-runtime/caplab-hostctl.py" \
     --source-commit-file "$PWD/caplab-runtime/SOURCE_COMMIT" \
     --runtime-config "$PWD/caplab-runtime/runtime.toml" \
     --source-repo /home/halbritt/git/caplab \
     preflight
   ```

2. Install only the reviewed host tool and expiry units, then bootstrap. The
   bootstrap command repeats source and host preflight before creating the
   empty namespaces.

   ```bash
   sudo install -d -o root -g root -m 0755 /usr/local/libexec
   sudo install -o root -g root -m 0755 \
     caplab-runtime/caplab-hostctl.py /usr/local/libexec/caplab-hostctl
   sudo install -o root -g root -m 0644 \
     caplab-runtime/caplab-p4-expiry.service \
     caplab-runtime/caplab-p4-expiry.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo /usr/local/libexec/caplab-hostctl \
     --source-commit-file "$PWD/caplab-runtime/SOURCE_COMMIT" \
     --runtime-config "$PWD/caplab-runtime/runtime.toml" \
     --source-repo /home/halbritt/git/caplab \
     bootstrap
   ```

3. Continue steps 3 through 5 in one Bash session. Name the installed runtime
   exactly, stage only the three pinned synthetic
   inputs inside that environment, verify their source hashes, and apply the
   migration as PostgreSQL `postgres` from an empty environment. The role
   processes never read through `/home/halbritt`.

   ```bash
   set -euo pipefail
   umask 077
   LOCK_SHA=b5c05b76c4e383b9bdedb783ed658fe33c368d660a1efe45f80c98e0f8adb3a0
   PYTHON=/opt/caplab/venvs/$LOCK_SHA/bin/python
   FIXTURE_ROOT=/opt/caplab/venvs/$LOCK_SHA/share/caplab-p4
   RECORD_ROOT=$(mktemp -d /var/tmp/caplab-p4-execution.XXXXXXXX)
   SOURCE_FIXTURES=/home/halbritt/git/caplab/tests/fixtures/runtime
   EFFECTS_ARMED=0

   run_runtime() {
     local role=$1
     shift
     sudo -n -u "$role" -- /usr/bin/env -i PYTHONNOUSERSITE=1 \
       PYTHONDONTWRITEBYTECODE=1 \
       "$PYTHON" -m caplab.runtime "$@"
   }

   emergency_quarantine() {
     local original_status=$?
     local plan_status=not-attempted
     local copy_status=not-attempted
     local disable_status=not-attempted
     trap - EXIT
     set +e
     if [[ "${EFFECTS_ARMED:-0}" == 1 && -n "${OPERATION_ID:-}" && \
           -n "${VERIFIER_OUTPUT:-}" && -d "${VERIFIER_OUTPUT:-}" ]]; then
       if [[ ! -f "$VERIFIER_OUTPUT/cleanup-plan.json" ]]; then
         run_runtime caplab_verifier cleanup-plan \
           --config /etc/caplab/runtime.toml \
           --operation-id "$OPERATION_ID" \
           --output "$VERIFIER_OUTPUT/cleanup-plan.json"
         plan_status=$?
       else
         plan_status=already-present
       fi
       if [[ -f "$VERIFIER_OUTPUT/cleanup-plan.json" ]]; then
         sudo install -o "$(id -un)" -g "$(id -gn)" -m 0600 \
           "$VERIFIER_OUTPUT/cleanup-plan.json" \
           "$RECORD_ROOT/cleanup-plan.json"
         copy_status=$?
       fi
     fi
     # Revocation must not depend on the evidence filesystem being writable.
     sudo /usr/local/libexec/caplab-hostctl disable
     disable_status=$?
     printf 'original_status=%s\nplan_status=%s\ncopy_status=%s\ndisable_status=%s\n' \
       "$original_status" "$plan_status" "$copy_status" "$disable_status" \
       >"$RECORD_ROOT/emergency-quarantine-status.txt" 2>/dev/null || true
     if [[ "$disable_status" -ne 0 ]]; then
       exit 1
     fi
     exit "$original_status"
   }

   sudo install -d -o root -g caplab -m 0750 "$FIXTURE_ROOT"
   sudo install -o root -g caplab -m 0440 \
     "$SOURCE_FIXTURES/synthetic-attempt.json" \
     "$SOURCE_FIXTURES/synthetic-payload.json" \
     "$SOURCE_FIXTURES/synthetic-payload-conflict.json" \
     "$FIXTURE_ROOT/"
   test "$(sudo sha256sum "$FIXTURE_ROOT/synthetic-attempt.json" | cut -d' ' -f1)" = \
     97304a771459f40d978d4becc9ebe317527e7ba1874b9a0cacc40af5f9e6ac0c
   test "$(sudo sha256sum "$FIXTURE_ROOT/synthetic-payload.json" | cut -d' ' -f1)" = \
     87fcfd5dbd6607da7899181ddd707b697cd4fa503c5e8cff8e169b5472172d92
   test "$(sudo sha256sum "$FIXTURE_ROOT/synthetic-payload-conflict.json" | cut -d' ' -f1)" = \
     3d86a1f2030284501a41bdfb82f17108cf49070e73e5c0e9a4954abc399eb82a

   sudo -n -u postgres -- /usr/bin/env -i PYTHONNOUSERSITE=1 \
     PYTHONDONTWRITEBYTECODE=1 \
     "$PYTHON" -m caplab.runtime migrate \
     --config /etc/caplab/runtime.toml | tee "$RECORD_ROOT/migrate.json"
   ```

4. Install and activate the expiry backstop before credentials exist:

   ```bash
   sudo systemctl enable --now caplab-p4-expiry.timer
   sudo /usr/local/libexec/caplab-hostctl verify --phase base
   trap emergency_quarantine EXIT
   sudo /usr/local/libexec/caplab-hostctl issue-credentials
   sudo /usr/local/libexec/caplab-hostctl verify --phase ready
   ```

5. Arm the irreversible boundary and execute the frozen operation one command
   at a time under the already-installed quarantine trap. Capture all three stores
   before registration and after first registration, replay, and conflict.
   Wrong-role calls must return runtime refusal status `2`. The changed request
   must also return `2` before any additional store effect.

   ```bash
   OPERATION_ID=op-caplab-p4-roundtrip-0001
   FIXTURE=$FIXTURE_ROOT/synthetic-attempt.json
   PAYLOAD=$FIXTURE_ROOT/synthetic-payload.json
   CONFLICT=$FIXTURE_ROOT/synthetic-payload-conflict.json
   READER_OUTPUT=$(sudo -n -u caplab_reader -- /usr/bin/env -i \
     /usr/bin/mktemp -d /var/tmp/caplab-p4-reader.XXXXXXXX)
   VERIFIER_OUTPUT=$(sudo -n -u caplab_verifier -- /usr/bin/env -i \
     /usr/bin/mktemp -d /var/tmp/caplab-p4-verifier.XXXXXXXX)
   printf 'reader=%s\nverifier=%s\n' "$READER_OUTPUT" "$VERIFIER_OUTPUT" \
     >"$RECORD_ROOT/role-output-paths.txt"

   sudo /usr/local/libexec/caplab-hostctl arm-effects
   EFFECTS_ARMED=1
   sudo /usr/local/libexec/caplab-hostctl capture-inventory \
     --label before-register

   set +e
   run_runtime caplab_reader register --config /etc/caplab/runtime.toml \
     --operation-id "$OPERATION_ID" --fixture "$FIXTURE" --payload "$PAYLOAD" \
     >"$RECORD_ROOT/reader-register.stdout" \
     2>"$RECORD_ROOT/reader-register.stderr"
   READER_REFUSAL=$?
   run_runtime caplab_verifier register --config /etc/caplab/runtime.toml \
     --operation-id "$OPERATION_ID" --fixture "$FIXTURE" --payload "$PAYLOAD" \
     >"$RECORD_ROOT/verifier-register.stdout" \
     2>"$RECORD_ROOT/verifier-register.stderr"
   VERIFIER_REFUSAL=$?
   set -e
   test "$READER_REFUSAL" -eq 2
   test "$VERIFIER_REFUSAL" -eq 2

   run_runtime caplab_writer register --config /etc/caplab/runtime.toml \
     --operation-id "$OPERATION_ID" --fixture "$FIXTURE" --payload "$PAYLOAD" \
     | tee "$RECORD_ROOT/register-first.json"
   sudo /usr/local/libexec/caplab-hostctl capture-inventory \
     --label after-first-register

   run_runtime caplab_writer register --config /etc/caplab/runtime.toml \
     --operation-id "$OPERATION_ID" --fixture "$FIXTURE" --payload "$PAYLOAD" \
     | tee "$RECORD_ROOT/register-replay.json"
   sudo /usr/local/libexec/caplab-hostctl capture-inventory \
     --label after-replay

   set +e
   run_runtime caplab_writer register --config /etc/caplab/runtime.toml \
     --operation-id "$OPERATION_ID" --fixture "$FIXTURE" --payload "$CONFLICT" \
     >"$RECORD_ROOT/register-conflict.stdout" \
     2>"$RECORD_ROOT/register-conflict.stderr"
   CONFLICT_REFUSAL=$?
   set -e
   test "$CONFLICT_REFUSAL" -eq 2
   sudo /usr/local/libexec/caplab-hostctl capture-inventory \
     --label after-conflict

   run_runtime caplab_reader retrieve --config /etc/caplab/runtime.toml \
     --operation-id "$OPERATION_ID" \
     --output "$READER_OUTPUT/retrieved-synthetic-payload.json" \
     | tee "$RECORD_ROOT/retrieve.json"
   sudo sha256sum "$READER_OUTPUT/retrieved-synthetic-payload.json" \
     >"$RECORD_ROOT/retrieved.sha256"
   test "$(cut -d' ' -f1 "$RECORD_ROOT/retrieved.sha256")" = \
     87fcfd5dbd6607da7899181ddd707b697cd4fa503c5e8cff8e169b5472172d92
   run_runtime caplab_verifier verify --config /etc/caplab/runtime.toml \
     --operation-id "$OPERATION_ID" | tee "$RECORD_ROOT/verify.json"
   run_runtime caplab_verifier reconcile --config /etc/caplab/runtime.toml \
     --operation-id "$OPERATION_ID" --fixture "$FIXTURE" \
     | tee "$RECORD_ROOT/reconcile.json"
   run_runtime caplab_verifier cleanup-plan --config /etc/caplab/runtime.toml \
     --operation-id "$OPERATION_ID" \
     --output "$VERIFIER_OUTPUT/cleanup-plan.json" \
     | tee "$RECORD_ROOT/cleanup-plan-receipt.json"
   sudo install -o "$(id -un)" -g "$(id -gn)" -m 0600 \
     "$VERIFIER_OUTPUT/cleanup-plan.json" "$RECORD_ROOT/cleanup-plan.json"
   sudo /usr/local/libexec/caplab-hostctl verify --phase armed

   sudo /usr/local/libexec/caplab-hostctl disable
   sudo /usr/local/libexec/caplab-hostctl verify --phase disabled
   trap - EXIT
   sudo install -o "$(id -un)" -g "$(id -gn)" -m 0600 \
     /var/lib/caplab-p4-roundtrip-2026-07-15.state.json \
     "$RECORD_ROOT/final-state.json"
   sha256sum "$RECORD_ROOT"/* >"$RECORD_ROOT/SHA256SUMS"
   printf '%s\n' "$RECORD_ROOT"
   ```

After `arm-effects`, do not run `rollback-empty`, even if later inspection
appears empty. Preserve the runtime's content-identified cleanup plan and leave
all synthetic state quarantined. A failed partial bootstrap is automatically
rolled back from its durable journal; `rollback-empty` can resume the same
verified cleanup if an interruption prevents that automatic path. A complete
but unarmed base must first be disabled and independently shown empty.

## Stop conditions

Stop rather than weaken a check if the pinned source is not clean and exact,
the runtime lock is missing or unhashed, any target already exists, PostgreSQL
peer auth is absent, either state service is unhealthy, `/nvr` is not ZFS, the
timer is inactive, a key expires after authorization, a credential could reach
output or an environment variable, a role or grant is broader than recorded,
store reconciliation fails, or any operation would cross into P5, historical
evidence, model use, publication, training, purge, or acceptance.
