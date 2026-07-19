# CAPLAB P7 host surface on `proximal`

This directory is the desired state for CAPLAB-25/P7. CAPLAB commit
`bf6de2b24ac61e82107208cdc609c7e534c6eaaa` implements one deterministic,
read-only Study 001 recomputation command. This host surface installs that
commit without replacing P4 or P6, gives `caplab_reader` one expiring read-only
Garage key and PostgreSQL login, captures the result, and revokes all access.

Nothing here authorizes live execution. ADR 0016 Stage A stops before reader
enablement. A separate CAPLAB continuation must name the final clean Proximal
commit, the hashes below, the evidence root, the executor, the expiry, the
cleanup sequence, and the independent checks before this runbook may run.

## Fixed boundary

| Surface | Value |
|---|---|
| campaign | `caplab-study-001-p7-recompute-2026-07-18` |
| CAPLAB source | `bf6de2b24ac61e82107208cdc609c7e534c6eaaa` |
| requirements lock | `b5c05b76c4e383b9bdedb783ed658fe33c368d660a1efe45f80c98e0f8adb3a0` |
| P6 admission | `d2d4f821146c3f39e6726133c383807ec9f6051834e74fbd3a5f33aae8ef148e` |
| authorization expiry | `2026-07-25T23:59:59Z` |
| runtime | `/opt/caplab/p7/bf6de2b24ac61e82107208cdc609c7e534c6eaaa` |
| PostgreSQL | database `caplab`, schema `caplab_v0`, peer role `caplab_reader` |
| Garage | loopback `127.0.0.1:3900`, bucket `caplab-v0`, read only |
| independent copy | `/nvr/caplab/v0` |
| access state | `/var/lib/caplab-study-001-p7-recompute-2026-07-18.state.json` |
| execution evidence | `/var/tmp/caplab-p7-execution-2026-07-18` |
| expiry backstop | `caplab-p7-expiry.timer`, 2026-07-25 23:50 UTC |

The live PostgreSQL start identity, P4 control, P6 registration, all 326 Garage
objects, all 326 independent copies, and writer/verifier disablement are
preservation controls. Recomputation has no write method. Its result is an
observation, not a capability inference or acceptance record.

## Canonical files

| Repository file | Installed path | Owner and mode |
|---|---|---|
| `SOURCE_COMMIT` | `/etc/caplab/P7_SOURCE_COMMIT` | `root:caplab 0640` |
| `recomputation.toml` | `/etc/caplab/recomputation.toml` | `root:caplab 0640` |
| `caplab-p7-accessctl.py` | `/usr/local/libexec/caplab-p7-accessctl` | `root:root 0755` |
| `caplab-p7-expiry.service` | `/etc/systemd/system/caplab-p7-expiry.service` | `root:root 0644` |
| `caplab-p7-expiry.timer` | `/etc/systemd/system/caplab-p7-expiry.timer` | `root:root 0644` |

The access controller has only `enable`, `verify`, and `disable`. `enable`
refuses source/config drift, an inactive timer, an existing state file, a live
reader key, a credential, or PostgreSQL login. It creates one expiring
`caplab-p7-reader` key, grants read on `caplab-v0`, writes the secret directly
to the role-owned mode-0400 file, and enables only `caplab_reader`. A partial
failure runs aggregate disablement. `disable` independently revokes PostgreSQL
login and sessions, reader processes, every state- or alias-discovered P7 key,
the credential, and the OS-account window.

`verify --phase ready` also owns the complete PostgreSQL readiness boundary. It
requires exactly the reader, writer, and verifier roles; accepts only an absent
password or PostgreSQL's unusable `*` marker without emitting the stored value;
requires writer and verifier `NOLOGIN`; requires zero reader, writer, and
verifier sessions; rejects reader write authority in `caplab_v0`; and requires
loopback-only PostgreSQL listening.

## Model-free checks

These commands make no live changes:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  caplab-p7/tests/test_accessctl.py -v
python3 caplab-p7/caplab-p7-accessctl.py --help
systemd-analyze calendar '2026-07-25 23:50:00 UTC'
systemd-analyze verify \
  caplab-p7/caplab-p7-expiry.service \
  caplab-p7/caplab-p7-expiry.timer
git diff --check
```

The uninstalled unit check reports the absent
`/usr/local/libexec/caplab-p7-accessctl` executable. That staging warning must
disappear after installation.

## Ordered live sequence

This sequence is a preparation artifact, not an execution record.

1. Require clean CAPLAB and Proximal worktrees at the continuation's exact
   commits. Re-run the CAPLAB `make check`, the model-free checks above, and
   read-only P6/P4/cluster controls. Stop on any drift.
2. Create a temporary detached CAPLAB worktree at the source commit. Build the
   runtime at a temporary sibling of the fixed `/opt` path using
   `/usr/bin/python3 -m venv --copies`; the installed `bin/python` must be a
   regular, non-symlinked file under `lstat`. Install dependencies with
   `pip --require-hashes` from `src/caplab/runtime/requirements.lock`, install
   CAPLAB with `--no-deps`, emit hashes for every installed CAPLAB source file,
   then atomically rename the complete environment into place. Remove the
   temporary worktree. Make the runtime `root:caplab`, group readable/executable,
   and group non-writable. Stop before `enable` on any interpreter custody drift.
3. Install the five canonical files at the paths and modes above. Run
   `systemctl daemon-reload`, enable and start the expiry timer, and prove the
   installed controller and unit hashes match the committed Proximal files.
4. Require `/var/tmp/caplab-p7-execution-2026-07-18` to be absent, then create
   it as `root:root 0700`. Record the source/config/install hashes, clean
   commits, test output, UTC clock, PostgreSQL start identity and
   cardinalities, P4 control identity, 326/326 store counts, disabled
   writer/verifier/reader state, and empty P7 key/credential inventory.
5. Install an `EXIT` trap that runs
   `/usr/local/libexec/caplab-p7-accessctl disable` and records its status.
   Run `enable`, then `verify --phase ready`. Treat that versioned verification
   as the readiness authority; do not add a second assertion about PostgreSQL's
   password storage representation. Stop if it reports any missing role, usable
   password, writer or verifier login, reader write authority, public listener,
   or unexpected session.
6. Run exactly this product command as `caplab_reader` with an empty
   environment and capture stdout and stderr separately:

   ```bash
   sudo -n -u caplab_reader -- /usr/bin/env -i \
     PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
     /opt/caplab/p7/bf6de2b24ac61e82107208cdc609c7e534c6eaaa/bin/python \
     -m caplab.recomputation --config /etc/caplab/recomputation.toml \
     recompute
   ```

   Require exit 0, canonical JSON, `assertion_type=observation`, the exact P6
   admission identity, implementation commit, 20 outcome identities,
   `historical_comparison.status=byte-identical`, and a self-consistent result
   manifest SHA-256. Re-run once and require byte-identical stdout. Any other
   result is a quarantine stop, not permission to repair historical state.
7. Run `disable`, `verify --phase disabled`, and clear the trap only after both
   pass. Re-record all pre-effect controls and require no changed database
   cardinality or timestamp, Garage object/version inventory, independent-copy
   inventory, P4 control, or P6 registration. Hash every retained evidence file
   into `SHA256SUMS` without retaining a Garage secret.

The executor may record the technical result and cleanup observations. It may
not make the CAPLAB-27 capability inference, CAPLAB-29 eligibility decision,
CAPLAB-30 export decision, CAPLAB-33 independent verdict, or CAPLAB-34
acceptance disposition.
