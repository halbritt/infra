# CAPLAB P6 host surface on `proximal`

Desired state for ADR 0014 Stage B / CAPLAB-24. CAPLAB owns the admission
implementation and research records. This subsystem binds the installed
environment, exact historical source stage, local PostgreSQL/Garage/NVR
targets, temporary writer, and independent verifier access window.

P6 completed with independent PASS on 2026-07-17. Manifest
`d2d4f821146c3f39e6726133c383807ec9f6051834e74fbd3a5f33aae8ef148e`
registers 684 restricted evidence records as 325 unique byte identities and
links 20 assignments, first attempts, and mechanical outcomes. Writer,
reader, and verifier PostgreSQL roles are `NOLOGIN`; their P6 Garage keys and
credential files are absent; writer and verifier preservation ACLs were
removed. The installed environment, non-secret config, restricted Git stage,
append-only database registration, Garage bytes, and `/nvr` copies remain.
These are execution and verification observations, not CAPLAB acceptance or
P7 authority.

## Fixed boundary

| Surface | Value |
|---|---|
| CAPLAB source | `137d0724ca22956d04d75f41e02e0b36b146e5f6` |
| authorization expiry | `2026-07-24T23:59:59Z` |
| preservation root | `/var/tmp/striatum-bench/luna-bv-confirmation-preserved-2026-07-14` |
| selected Git stage | `/var/lib/caplab-p6/source-git` |
| PostgreSQL | database `caplab`, schema `caplab_v0`, migration `0003_study_admission.sql` |
| Garage | loopback `127.0.0.1:3900`, bucket `caplab-v0` |
| independent copy | `/nvr/caplab/v0` |
| roles | temporary `caplab_writer`; read-only `caplab_reader`; independent `caplab_verifier` |

The stage contains only the three ADR-selected Git blobs, extracted with `git
show <commit>:<path>` and checked against the ADR hashes. It is `root:caplab`
and group-readable, not a worktree. The dirty historical checkout is neither
read nor changed by a runtime identity.

## Canonical files

| Repository file | Installed path | Owner and mode |
|---|---|---|
| `SOURCE_COMMIT` | `/etc/caplab/P6_SOURCE_COMMIT` | `root:caplab 0640` |
| `admission.toml` | `/etc/caplab/admission.toml` | `root:caplab 0640` |

The exact CAPLAB commit is installed in a dedicated environment beneath
`/opt/caplab/p6/137d0724ca22956d04d75f41e02e0b36b146e5f6`; it does not replace the
P4 environment. Dependencies remain hash-locked by the CAPLAB requirements
lock.

## Ordered execution

1. Verify the CAPLAB and this desired-state worktrees are clean at their pins.
2. Extract and hash-check the three selected Git blobs into the restricted
   stage; verify all 681 preservation-manifest members.
3. Install the exact CAPLAB commit into the dedicated environment and install
   the two canonical files above.
4. Apply only forward migration 0003 as PostgreSQL owner. Confirm the live
   cluster data directory, port, PID/start identity, and P4 registration remain
   unchanged.
5. Issue expiring writer and verifier Garage keys without terminal output;
   grant writer read/write and verifier read on only `caplab-v0`; write each
   role-owned credential file mode 0400; enable only the corresponding
   PostgreSQL peer roles and OS accounts.
6. Run `source-verify` as writer, then `admit` once and as an idempotent replay.
   Reconcile 684 records, 325 unique byte identities, and exactly 20 linked
   assignments, attempts, and outcomes.
7. Disable and delete the writer key and credential, set the writer PostgreSQL
   role `NOLOGIN`, terminate its sessions, and lock/expire its OS account.
8. An executor independent of implementation runs `source-verify` and `verify`
   as verifier, audits PostgreSQL links and both byte stores, and returns PASS
   or FAIL. After PASS, disable verifier access. Reader access remains disabled
   until a separately authorized P7 campaign.

Every command runs with an empty environment except the pinned interpreter
controls. Failure after byte copying but before metadata freeze leaves only
content-addressed restricted copies; it does not authorize deletion. A frozen
registration is append-only and cannot be purged under this surface.

There is no P7 recomputation, provider, model, inference, export, publication,
training, purge, or acceptance command here.
