# proximal/plane-public - plane.harm.org Plane CE instance

Desired-state and provenance for the public-intended `plane.harm.org` Plane
Community Edition instance on host `proximal`.

This is **not** the local/private Plane pilot in [`../plane`](../plane). It uses
its own compose project, database, Redis DB, Garage bucket/key, ports, and
generated env file. Public ingress is handled by
[`../cloudflared`](../cloudflared/); this instance still binds only loopback
ports on `proximal`.

## At a glance

| | |
|---|---|
| release | Plane CE `v1.3.1` |
| install root | `/home/halbritt/services/plane-harm-org` |
| app dir | `/home/halbritt/services/plane-harm-org/plane-app` |
| compose project | `plane-harm-org` |
| planned public URL | `https://plane.harm.org` |
| local URL | `http://127.0.0.1:8190` |
| public edge | Cloudflare Tunnel `token-dashboard`, `plane.harm.org` -> `http://localhost:8190` |
| unit | `plane-harm-org.service` |
| app state | system PostgreSQL 17, host Redis, Garage S3, bundled RabbitMQ |

## State services

The host services remain loopback-only. Plane containers reach them through
Docker-bridge proxy units bound only on `172.17.0.1`:

| state service | host service | bridge unit | container endpoint |
|---|---|---|---|
| PostgreSQL | `127.0.0.1:5432` | `plane-harm-org-postgres-bridge.service` | `172.17.0.1:15432` |
| Redis | `127.0.0.1:6379` | `plane-harm-org-redis-bridge.service` | `172.17.0.1:16379` |
| Garage S3 | `127.0.0.1:3900` | `plane-harm-org-garage-bridge.service` | `172.17.0.1:13900` |

Persistent resources:

| resource | name |
|---|---|
| PostgreSQL database | `plane_harm_org` |
| PostgreSQL role | `plane_harm_org` |
| Redis DB | `1` |
| Garage bucket | `plane-harm-org` |
| Garage key local alias | `plane-harm-org` |

The app uses `USE_MINIO=0` and `USE_STORAGE_PROXY=1`, so browsers should not need
direct access to the private Garage endpoint.

## Files -> install paths

| repo file | installed path | owner/mode | notes |
|---|---|---|---|
| [`docker-compose.yaml`](docker-compose.yaml) | `/home/halbritt/services/plane-harm-org/plane-app/docker-compose.yaml` | `halbritt:halbritt 0644` | external-state Plane compose; no secrets |
| [`plane-harm-org.service`](plane-harm-org.service) | `/etc/systemd/system/plane-harm-org.service` | `root:root 0644` | starts/stops the public-intended Plane stack |
| [`plane-harm-org-postgres-bridge.service`](plane-harm-org-postgres-bridge.service) | `/etc/systemd/system/plane-harm-org-postgres-bridge.service` | `root:root 0644` | Docker-bridge proxy to loopback Postgres |
| [`plane-harm-org-redis-bridge.service`](plane-harm-org-redis-bridge.service) | `/etc/systemd/system/plane-harm-org-redis-bridge.service` | `root:root 0644` | Docker-bridge proxy to loopback Redis |
| [`plane-harm-org-garage-bridge.service`](plane-harm-org-garage-bridge.service) | `/etc/systemd/system/plane-harm-org-garage-bridge.service` | `root:root 0644` | Docker-bridge proxy to loopback Garage S3 |
| [`plane-public-env.values`](plane-public-env.values) | selected values inside `plane.env` | non-secret reference | do not add secret values |
| - secrets, never vendored | `/home/halbritt/services/plane-harm-org/plane-app/plane.env` | `halbritt:halbritt 0600` | generated app secrets, database password, Garage key |

Install after edits:

```bash
install -m 0644 plane-public/docker-compose.yaml /home/halbritt/services/plane-harm-org/plane-app/docker-compose.yaml
sudo install -m 0644 plane-public/plane-harm-org*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now plane-harm-org-postgres-bridge.service plane-harm-org-redis-bridge.service plane-harm-org-garage-bridge.service
sudo systemctl enable --now plane-harm-org.service
```

## Verify

Do not print `plane.env`.

```bash
systemctl status redis-server plane-harm-org-postgres-bridge plane-harm-org-redis-bridge plane-harm-org-garage-bridge plane-harm-org --no-pager
sudo ss -ltnp | grep -E '172[.]17[.]0[.]1:(15432|16379|13900)'
cd /home/halbritt/services/plane-harm-org
docker compose -p plane-harm-org -f plane-app/docker-compose.yaml --env-file=plane-app/plane.env config --quiet
docker compose -p plane-harm-org -f plane-app/docker-compose.yaml --env-file=plane-app/plane.env ps
docker compose -p plane-harm-org -f plane-app/docker-compose.yaml --env-file=plane-app/plane.env config --format json | jq '.services.proxy.ports'
sudo -u postgres psql -XAtqc "select datname from pg_database where datname = 'plane_harm_org';"
sudo garage bucket info plane-harm-org
redis-cli -n 1 ping
curl -o /dev/null -sS -w 'plane_harm_local_root=%{http_code}\n' http://127.0.0.1:8190/
curl -o /dev/null -sS -w 'plane_harm_instances=%{http_code}\n' http://127.0.0.1:8190/api/instances/
curl -o /dev/null -sS -w 'plane_harm_users_me_no_auth=%{http_code}\n' http://127.0.0.1:8190/api/users/me/
curl -o /dev/null -sS -w 'plane_harm_public_instances=%{http_code}\n' https://plane.harm.org/api/instances/
curl -o /dev/null -sS -w 'plane_harm_public_users_me_no_auth=%{http_code}\n' https://plane.harm.org/api/users/me/
```

Expected HTTP checks:

- local root: `200`
- `/api/instances/`: `200`
- `/api/users/me/` without auth: `401`
- public `/api/instances/`: `200`
- public `/api/users/me/` without auth: `401`

Verified on 2026-06-29:

- `redis-server.service`, `garage.service`, `postgresql@17-main.service`, all
  three bridge units, and `plane-harm-org.service` were active.
- Docker published only `127.0.0.1:8190` and `127.0.0.1:8191` for this
  instance; the PostgreSQL, Redis, and Garage bridge listeners were only on
  `172.17.0.1`.
- Plane migrations existed in system PostgreSQL (`django_migrations=162`).
- The API startup check found Garage bucket `plane-harm-org`.
- Local HTTP checks returned `plane_harm_local_root=200`,
  `plane_harm_instances=200`, and `plane_harm_users_me_no_auth=401`.
- Public Cloudflare Tunnel checks returned `plane_harm_public_instances=200`
  and `plane_harm_public_users_me_no_auth=401`.
- The existing local/private Plane pilot at `http://127.0.0.1:8090/` still
  returned `200`.

## Stop conditions

Stop and ask before:

- changing the public DNS/Cloudflare Tunnel edge after it is enabled
- reusing or importing data from the local/private `plane/` pilot
- printing or moving the generated `plane.env`, database password, Garage secret
  key, or future Plane API tokens
- rebinding PostgreSQL, Redis, or Garage off loopback
- deleting the PostgreSQL database, Garage bucket, or install root
