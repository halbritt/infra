# Proximal CAPLAB P5 host integration

Read [`README.md`](README.md) before changing or enacting this subsystem.

CAPLAB product authority lives in `/home/halbritt/git/caplab`. The immutable
P5 executor source is verified through the dedicated linked worktree selected
by ADR 0015. This directory owns only the Proximal host integration authorized
by CAPLAB ADRs 0009 through 0015: temporary identities, exact installed source and configuration, backup
serialization, isolated PostgreSQL restore, root-custodied staging, expiry,
disablement, and host verification.

Do not modify the existing `caplab-runtime/**` P4 subsystem except for an
optional documentation link. The P4 registration and artifacts are read-only
control state throughout P5.

Never commit, print, or retain in command arguments a Garage secret key,
restic password, service-account key, PostgreSQL password, or secret-bearing
environment. Generated credentials are role-owned `0400` files under
`/etc/caplab-p5/credentials/` and are removed during disablement.

`SOURCE_COMMIT`, `recovery.toml`, fixtures, scripts, unit files, and their
hashes are one frozen host surface. The corrective config keeps the installed
executor source separate from the runtime commit retained in the immutable P5
request. Repository checks do not authorize live effects. Stop on source
drift, expired authority, a running restic operation, P4 control change,
identity mismatch, missing verifier, or any target outside the exact P5
closure.

Never run destructive `restic prune`, stop or replace the live PostgreSQL
cluster, or alter another Garage object. ADR 0014 authorizes only its exact
dependency rehearsal, P5 byte removal, guarded database purge, and tombstone
after independent preflight; P6 remains gated on the fresh independent P5
PASS.
