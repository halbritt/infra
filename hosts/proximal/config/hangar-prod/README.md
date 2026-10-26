# Hangar internal production tracker

Owner-authorized migration from Plane CE v1.4.2 on 2026-10-26, to provide epics
and ordinary work-item relationships. This replaces the internal Plane service;
public `plane.harm.org` and the test sandbox on port 10001 remain separate.

- URL: https://proximal.tail0ecc2e.ts.net:10000/
- Workspace: `Proximal`, slug `proximal`.
- Release: Hangar `v0.1.0-rc.64`, source commit
  `e925794ce253b67fea7125dfe693bb102f790487`.
- Runtime: `/home/halbritt/services/hangar-prod`.
- Lifecycle: `hangar-prod.service`; Compose project `hangar-prod`.
- Local listener after cutover: `127.0.0.1:8090` (the existing Plane address).
- Authentication: existing accounts/passwords/API tokens preserved. Owner wants
  one local password account; signup, magic links and external identity providers
  are disabled. The inherited internal bot identity remains for agent API access.
- New and existing projects have canonical Task and Epic work-item types.

## Canonical files and operation

Install `docker-compose.yaml`, `config.js`, `start.sh`, and
`maintenance.Caddyfile` into the runtime directory. Install
`hangar-prod.service` under `/etc/systemd/system/`. Runtime `hangar.env` contains
secrets and remains mode 0600 outside Git in a mode-0700 directory. The existing
application and Live secrets were retained, preserving configuration encryption
and user/session compatibility; database, queue and S3 credentials are independent.

`start.sh` starts the data services, runs exactly one migration process to
completion, then starts applications. The migrator has an explicit Compose
profile, so ordinary `up` cannot launch a second runner. Application updates
must be reviewed against the migration history before changing APP_RELEASE.

Use `sudo systemctl start|stop|reload hangar-prod`. Compose `up` applies changed
configuration by recreating affected containers. Do not restart retired
`plane-selfhost.service` while Hangar owns port 8090.

The source checkout at `/home/halbritt/git/hangar` is unmodified upstream.
Compose is derived from the evaluated test configuration, with production
networking and the ordinary `session-id` cookie. Runtime `config.js` supplies
browser origins that upstream Compose omits. MinIO uses the existing local image
digest (with new independent storage); the upstream Quay reference returned
unauthorized. TLS terminates at the existing Tailscale Serve mapping.

## Migration evidence and preservation boundary

The source queue had zero ready/unacknowledged messages. Ingress, API, Live,
Beat and worker were stopped; the source database was made read-only before the
final logical dump and object copy. A fresh database was restored and migrated,
not the earlier test database. Sandbox edits remain on port 10001.

Source backup: `~/.local/share/infra/backups/plane-to-hangar-20261026/`.
Contains a custom-format PostgreSQL dump, old Compose/environment, the object
archive, and object manifest. These files can contain private data and credentials;
keep them outside Git. Runtime verification receipts are in the production
runtime directory; command logs are `~/.cache/hangar-prod-*.log`.

Verified before and after schema migration: identical IDs/counts for 1 workspace,
50 projects, 2 users, 2 API tokens, 1,511 issues, 3,253 comments, 7,749 activities,
55 issue links, 209 relations, 30 file-asset rows, 547 states, 211 labels,
30 modules, 50 project memberships and 2 workspace memberships. Password hashes,
API token values, and existing issue content/parent/state/sequence values were
also compared directly without printing credentials. All 33 stored objects
(1,639,772 bytes) were copied and byte-verified. Migration history has no duplicate
(app, name) entries.

## Rollback

Before reopening writes, the original Plane database and uploads are a complete
rollback point. Restore the old Compose service, reset the source database's
`default_transaction_read_only` setting to `off`, and return port 8090 to Plane.
Start only the retained Plane database first, reset that setting with `psql`,
then start the full Plane stack; starting its API while the database remains
read-only will fail writes.
The original deployment and data volumes are retained; the service is disabled
and old containers removed without deleting volumes to prevent boot conflicts.

After reopening writes, that old database is stale. **Do not simply switch back.**
Freeze writes again and reconcile/export post-cutover changes or repair Hangar
forward before deciding whether restoring the old snapshot is acceptable.

The temporary maintenance container uses `maintenance.Caddyfile` to return 503
with Retry-After while holding port 8090. It is removed at cutover. No public DNS
or unrelated Tailscale mappings change.

## Cutover and compatibility results

Write freeze began at 17:21:18 UTC; the original endpoint reopened on Hangar at
17:32:55 UTC (11 minutes 37 seconds). Post-cutover attachment/CLI verification
completed at 17:33:52 UTC. Maintenance and resume notices were each published to
18 registered agent inboxes using the Cairn coordination skill; publication does
not prove every agent has consumed its notice.

Both preexisting API tokens returned HTTP 200. The installed `plane` CLI verified
project listing, epic creation, task creation, comment creation, updates, parent
and state persistence, deletion, and an exact-byte attachment round trip through
the original HTTPS URL. Temporary verification items PROXIMAL-9 through -11 were
removed; normal activity/audit history and sequence allocation remain.
Chromium rendered the migrated Infra project without page JavaScript errors.
The migration history has 233 entries and zero duplicate (app, name) pairs.

Hangar's public API treats `state` and `parent` as read-only response fields;
write `state_id` and `parent_id`. This initially caused old CLI flags to be silently
ignored. `halbritt/plane-cli` commit `fc7f557` sends both spellings with identical
values for compatibility with Hangar and the still-running public Plane server.
Regression tests cover create/update and flag precedence over `--data`; full Go
tests and vet passed. The binary installed at `~/.local/bin/plane` includes the fix.
Raw or remote API clients must use canonical writable fields, or update their CLI.

Production identities and existing work-item IDs did not change. Port 10001 still
contains the owner's test Epic and baking tasks; those sandbox-only additions
were not imported into production.
