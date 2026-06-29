# proximal/plane-public instructions

This subsystem records the public-intended `plane.harm.org` Plane CE instance on
host `proximal`. Read `README.md` before changing anything here.

## Boundaries

- This is a separate Plane instance from the local/private `plane/` pilot. Do not
  reuse its database, Redis, Garage bucket/key, API token, compose project, ports,
  or workspace.
- Keep the Plane proxy bound to loopback until the `plane.harm.org` edge path is
  deliberately enabled.
- The app uses host state services: PostgreSQL 17, Garage S3, and Redis. Do not
  silently fall back to bundled Compose Postgres, Redis/Valkey, or MinIO.
- Docker containers reach loopback-only host services through the documented
  Docker-bridge proxy units. Do not rebind PostgreSQL, Garage, or Redis globally
  without a new rationale and verification.
- Never commit `plane.env`, database passwords, Garage key material, Redis
  credentials, API tokens, dumps, or backup archives.

## Operational rule

The repo holds desired state; installed copies run on the box. If you change a
unit or compose file here, install it to the mapped path, reload systemd, restart
the affected service, verify, and update `README.md` plus the root changelog.
