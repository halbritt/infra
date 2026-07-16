# Proximal CAPLAB P5 host integration

Read [`README.md`](README.md) before changing or enacting this subsystem.

CAPLAB product authority lives in `/home/halbritt/git/caplab`. This directory
owns only the Proximal host integration authorized by CAPLAB ADRs 0009, 0010,
and 0011: temporary identities, exact installed source and configuration, backup
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
cluster, alter another Garage object, or remove the isolated restore before
the independent verifier preserves its interim report. ADR 0011 does not
authorize dependency creation, P5 byte removal, database purge, or P6.
