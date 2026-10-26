# Hangar evaluation — retired

Removed on 2026-10-26 at the owner's request after production migration.
The test service, containers, volumes, networks, runtime files, test snapshot,
browser artifacts, and port-10001 Tailscale mapping were removed. This includes
the sandbox-only Test Epic and baking tasks. Production remains on port 10000;
production migration backups and rollback volumes are retained.

The deployment files are available in Git history (introduced in `3d5a576`).
Do not reinstall the test instance without a new owner request.

## Historical evaluation record

The following records the completed evaluation before retirement; its URLs,
paths and startup commands describe the former deployment, not current state.


Owner-authorized test instance for simple epic hierarchy and work-item
relationships, created 2026-10-26. Production is now [Hangar on port 10000](../hangar-prod/README.md); this sandbox
remains an independent snapshot.

- URL: https://proximal.tail0ecc2e.ts.net:10001/
- Local listener: `127.0.0.1:8290`, tailnet only via Tailscale Serve.
- Release: `v0.1.0-rc.64`, upstream source commit
  `e925794ce253b67fea7125dfe693bb102f790487`.
- Source checkout: `/home/halbritt/git/hangar` (unmodified).
- Runtime: `/home/halbritt/services/hangar-test`.
- Lifecycle: `hangar-test.service`, enabled at boot; Compose project `hangar-test`.
- Login: existing internal Plane account, ordinary email/password. Signup,
  magic-link login and external identity providers are disabled. The owner wants
  one local account with a password, not Hangar's extended identity-management
  features (explicit preference confirmed 2026-10-26).

## Canonical files

Install `docker-compose.yaml` and `config.js` into the runtime directory, and
`hangar-test.service` into `/etc/systemd/system/`. The generated `hangar.env`
contains independent database, queue, storage, application and Live secrets;
keep it outside Git with mode 0600 in the mode-0700 runtime directory.

The Compose definition derives from Hangar's
`deployments/cli/community/docker-compose.yml` at the revision above. Changes:

- Dedicated project, volumes, network, secrets, and loopback listener.
- Internal network isolates backend/data services from outbound connections.
  Only the reverse proxy also joins an ingress network to publish its listener.
- Runtime `config.js` mounts supply the instance origin to browser applications;
  the upstream Compose recipe omits this file although the frontends load it.
  Its format comes from upstream's `frontend-configmap.yaml`.
- Distinct `hangar-test-session-id` user cookie avoids overwriting Plane's login.
- Import/mail workers are optional profiles; the corresponding features are off.
- MinIO uses the exact locally available Plane image digest because the upstream
  Quay image reference returned unauthorized. Its test volume is independent.
- Credentials have no upstream sample-password fallbacks.

`CERT_ACME_CA` must be nonempty even when Caddy serves HTTP behind Tailscale TLS;
otherwise its unconditional `acme_ca` directive fails parsing. Runtime value is
`https://acme-v02.api.letsencrypt.org/directory`; `SITE_ADDRESS=:80` means Caddy
is not obtaining certificates for this test service.

Apply configuration:

```sh
sudo systemctl reload hangar-test
```

Compose recreates containers to apply changed environment variables. Stop with
`sudo systemctl stop hangar-test`. To remove only this tailnet mapping:
`sudo tailscale serve --https=10001 off`. Do not change Plane's port 10000 mapping.

## Copied data and isolation

A fresh logical dump of internal Plane CE v1.4.2 contained 50 projects and 1,511
work items. It was restored into the dedicated database before Hangar migrations.
All 33 uploaded objects (1,639,772 bytes) were copied through S3 into independent
storage. Snapshot files are under
`~/.local/share/infra/backups/hangar-test-20261026/`, protected locally and excluded
from Git. The database snapshot and object copy are sequential, suitable for this
sandbox rather than an atomic disaster-recovery backup.

Before starting Hangar, the copied database's browser sessions, API tokens,
workspace integrations, and instance configurations were removed. Webhooks were
disabled, the instance named as a test, and telemetry disabled. Password hashes
were retained so the owner's existing password works; production was not changed.
Fresh instance configuration initializes without production mail/SSO credentials.
The internal Docker network also prevents backend outbound delivery. Copied data
is a snapshot: test edits never synchronize to production.

The standard user login is the evaluation entry point. Hangar's separate God Mode
console retains upstream's security-key requirement; no SSO or user-management
expansion is required to test project features.

## Verified evaluation workflow

The `Hangar Test` project contains:

- `HTEST-1`: Epic, **Try epics and relationships**.
- `HTEST-2`, `HTEST-3`, `HTEST-4`: three Task children.
- HTEST-2 blocks HTEST-3, which blocks HTEST-4.
- HTEST-2 and HTEST-4 also have a symmetric “relates to” relationship.

Open the [sample project](https://proximal.tail0ecc2e.ts.net:10001/proximal/projects/7e892463-9f3a-4364-afa6-94bf0f89271d/issues/).
Create an Epic through **Add work item → Work item type → Epic**. Open a work
item to use **Add sub-work item** or **Add relation**.

Validation on 2026-10-26: all migrations completed; `migrate --check` passed;
project/type/item/relationship HTTP requests passed with persisted parent links
and both forward/reverse relationship reads. Chromium loaded the populated
project without page JavaScript errors and opened HTEST-3 with the parent Epic
and blocking/blocked-by activity visible. The unauthenticated login page offers
email/password, and the instance API confirms signup, magic links, Google,
GitHub, GitLab, Gitea, OIDC and SAML are disabled. This was a focused deployment
smoke check, not a comprehensive upstream test-suite or accessibility review.
Local browser evidence: `~/.cache/hangar-test-browser/`.

Upstream registration resets the database `is_test` flag; the visible instance
name and isolated deployment are the test markers. The test was not promoted to
production: a separate Hangar deployment was migrated from a fresh production
snapshot. This sandbox is not the default agent issue tracker.
