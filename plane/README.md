# proximal/plane - local Plane CE pilot

Desired-state and provenance for the **local/private Plane Community Edition pilot**
on host `proximal`. This is the Striatum/meta-operator issue-tracker experiment, not
the future public personal tracker. Keep the trust boundary local unless the owner
explicitly changes it.

Captured 2026-06-28 from the setup handoffs in `/tmp/plane-proximal-pilot-handoff-2026-06-28.md`,
`/tmp/plane-local-pilot-status-2026-06-28.md`, and
`/tmp/plane-local-setup-handoff-2026-06-28.md`.

## At a glance

| | |
|---|---|
| release | Plane CE `v1.3.1` |
| install root | `/home/halbritt/services/plane-selfhost` |
| app dir | `/home/halbritt/services/plane-selfhost/plane-app` |
| local URL | `http://127.0.0.1:8090` |
| tailnet URL | `https://proximal.tail0ecc2e.ts.net:10000/` |
| workspace | `Proximal` (`proximal`) |
| unit | `plane-selfhost.service` (`oneshot`, boot/lifecycle wrapper) |
| bundled services | Plane Compose Postgres, Valkey/Redis, RabbitMQ, MinIO |

The Plane proxy must publish only loopback ports:

| host | container |
|---|---|
| `127.0.0.1:8090` | `80/tcp` |
| `127.0.0.1:8091` | `443/tcp` |

Tailscale Serve publishes the tailnet entry point:

```bash
tailscale serve --bg --https=10000 http://127.0.0.1:8090
```

Do not replace the existing Tailscale `:443` mapping; it serves another local
service.

## Files -> install paths

| repo file | installed path | owner/mode | notes |
|---|---|---|---|
| [`plane-selfhost.service`](plane-selfhost.service) | `/etc/systemd/system/plane-selfhost.service` | root:root 0644 | starts/stops the Docker Compose pilot as `halbritt` |
| [`plane-mcp-proximal`](plane-mcp-proximal) | `/home/halbritt/.local/bin/plane-mcp-proximal` | halbritt:halbritt 0700 | reads the private MCP env file, then execs `plane-mcp-server stdio` |
| [`plane-public-env.values`](plane-public-env.values) | values inside `/home/halbritt/services/plane-selfhost/plane-app/plane.env` | uncommitted secret-bearing file | only the listed non-secret keys are captured here |
| [`docker-compose-proxy-loopback.patch`](docker-compose-proxy-loopback.patch) | patch against `plane-app/docker-compose.yaml` | uncommitted generated compose file | documents the loopback-only proxy publish change |
| [`scripts/scaffold_github_repos.py`](scripts/scaffold_github_repos.py) | run from this checkout | - | idempotently scaffolds Plane projects/states/labels and remote `AGENTS.md` tracking blocks for `halbritt/*` repos |
| [`API_TOKENS.md`](API_TOKENS.md) | policy only | - | token storage paths and creation boundary; no token values |
| - secrets, never vendored | `/home/halbritt/.config/plane/proximal-mcp.env` | halbritt:halbritt 0600 | contains `PLANE_API_KEY` and non-secret URL/workspace vars |

Install after editing the unit or wrapper:

```bash
sudo install -m 0644 plane/plane-selfhost.service /etc/systemd/system/plane-selfhost.service
install -m 0700 plane/plane-mcp-proximal /home/halbritt/.local/bin/plane-mcp-proximal
sudo systemctl daemon-reload
sudo systemctl enable --now plane-selfhost.service
```

The unit makes the pilot boot-startable and gives it a normal systemd lifecycle. It
does not replace Docker/Plane health checks; after a suspected crash, inspect
`docker compose ps` and the Plane logs directly.

If the Plane URL/env or compose loopback patch changes, edit the generated files under
`/home/halbritt/services/plane-selfhost/plane-app/`, then run:

```bash
cd /home/halbritt/services/plane-selfhost
docker compose -f plane-app/docker-compose.yaml --env-file=plane-app/plane.env config --quiet
sudo systemctl reload plane-selfhost.service
```

## Current non-secret app config

`plane-app/plane.env` contains generated secrets and must not be copied into git.
These public values are the desired local/private posture:

```env
APP_DOMAIN=proximal.tail0ecc2e.ts.net:10000
LISTEN_HTTP_PORT=8090
LISTEN_HTTPS_PORT=8091
WEB_URL=https://proximal.tail0ecc2e.ts.net:10000
CORS_ALLOWED_ORIGINS=https://proximal.tail0ecc2e.ts.net:10000,http://127.0.0.1:8090
API_KEY_RATE_LIMIT=600/minute
```

`API_KEY_RATE_LIMIT` is raised above Plane's default for local bulk automation
against this private pilot. Keep it local; do not treat this as a public-service
posture.

If the UI redirects to `127.0.0.1` when opened through Tailscale, confirm these values
first, then recreate the containers:

```bash
cd /home/halbritt/services/plane-selfhost
docker compose -f plane-app/docker-compose.yaml --env-file=plane-app/plane.env up -d --force-recreate --pull never
```

## MCP

The official Plane MCP server is installed as a uv tool:

```text
/home/halbritt/.local/bin/plane-mcp-server
```

The local wrapper is:

```text
/home/halbritt/.local/bin/plane-mcp-proximal
```

The wrapper reads `/home/halbritt/.config/plane/proximal-mcp.env` by default. That
file must stay outside git, mode `600`, in a mode `700` directory. Expected variable
names:

- `PLANE_API_KEY`
- `PLANE_WORKSPACE_SLUG=proximal`
- `PLANE_BASE_URL=https://proximal.tail0ecc2e.ts.net:10000`
- optional `PLANE_INTERNAL_BASE_URL`

Codex and Claude both register the MCP server as `plane` using the wrapper. `Auth
Unsupported` in `codex mcp list` is normal for a stdio MCP server.

## GitHub repo scaffold

Every `github.com/halbritt/*` repository with a default branch should have:

- a Plane project in workspace `Proximal`, with `external_source=github` and
  `external_id=halbritt/<repo>`
- the standard agent states: `Backlog`, `Ready`, `Claimed`, `In Progress`,
  `Submitted`, `Review`, `Accepted`, `Rejected`, `Refused`, `Blocked`
- the standard coordination labels: `agent-coordination`, `needs-verification`,
  `authority-required`, `blocked`, `github`
- a marked Plane tracking block in repo `AGENTS.md`

Run the idempotent rollout script from this checkout:

```bash
env -u GH_TOKEN gh repo list halbritt --limit 1000 \
  --json name,nameWithOwner,isArchived,isFork,isPrivate,defaultBranchRef,url,pushedAt,updatedAt \
  --jq 'map({name,nameWithOwner,isArchived,isFork,isPrivate,defaultBranch:(.defaultBranchRef.name // ""),url,pushedAt,updatedAt})' \
  > /tmp/halbritt-repos.json

plane/scripts/scaffold_github_repos.py \
  --repos-json /tmp/halbritt-repos.json \
  --skip-agents-repo proximal \
  --report-out /tmp/plane-github-rollout-report-$(date -u +%Y-%m-%dT%H-%M-%SZ).json
```

`proximal` is skipped for remote `AGENTS.md` writes because this checkout is the
canonical local edit path for that repo; update and commit it locally instead.
The script has a built-in Praxis exception for the PXLAB token pointer, so reruns
preserve that repo-specific guidance.

Rollout result on 2026-06-28:

- 66 `github.com/halbritt/*` repos discovered.
- 66 repo projects ensured in Plane, plus the separate `Praxis Plane Connector Lab`
  project (`PXLAB`).
- 62 remote `AGENTS.md` files created or confirmed with the Plane tracking block.
- `proximal` and `praxis` were handled through local checkouts.
- `memory-price-tracker` and `saltitall` had no default branch for `AGENTS.md`
  writes at rollout time. Their Plane projects still exist.

## Verify

Do not print tokens. Source the MCP env file only inside commands that suppress
response bodies:

```bash
systemctl status plane-selfhost --no-pager
cd /home/halbritt/services/plane-selfhost
docker compose -f plane-app/docker-compose.yaml --env-file=plane-app/plane.env ps
docker compose -f plane-app/docker-compose.yaml --env-file=plane-app/plane.env config --quiet
grep -E '^(APP_DOMAIN|LISTEN_HTTP_PORT|LISTEN_HTTPS_PORT|WEB_URL|CORS_ALLOWED_ORIGINS)=' plane-app/plane.env
docker compose -f plane-app/docker-compose.yaml --env-file=plane-app/plane.env config --format json | jq '.services.proxy.ports'
tailscale serve status --json | jq '.Web["proximal.tail0ecc2e.ts.net:10000"]'
curl -o /dev/null -sS -w 'local_root=%{http_code}\n' http://127.0.0.1:8090/
curl -o /dev/null -sS -w 'tailnet_root=%{http_code}\n' https://proximal.tail0ecc2e.ts.net:10000/
curl -o /dev/null -sS -w 'instances=%{http_code}\n' https://proximal.tail0ecc2e.ts.net:10000/api/instances/
curl -o /dev/null -sS -w 'users_me_no_auth=%{http_code}\n' https://proximal.tail0ecc2e.ts.net:10000/api/users/me/
bash -lc 'set -a; . /home/halbritt/.config/plane/proximal-mcp.env; set +a; curl -fsS -o /dev/null -w "api_v1_users_me_auth=%{http_code}\n" -H "X-Api-Key: ${PLANE_API_KEY}" -H "x-workspace-slug: ${PLANE_WORKSPACE_SLUG}" "${PLANE_BASE_URL}/api/v1/users/me/"'
codex mcp list
claude mcp list
```

Expected HTTP checks:

- local root: `200`
- tailnet root: `200`
- `/api/instances/`: `200`
- `/api/users/me/` without auth: `401`
- `/api/v1/users/me/` with API key + workspace slug: `200`

Verified 2026-06-28:

- `plane-selfhost.service` was installed to `/etc/systemd/system/`, enabled, and
  started successfully.
- Docker Compose config was valid.
- Containers were up on Plane CE `v1.3.1`.
- The generated `migrator` container exited `0` after the systemd-managed `up -d`.
- Proxy ports were `127.0.0.1:8090->80/tcp` and `127.0.0.1:8091->443/tcp`.
- Tailscale Serve `:10000` proxied to `http://127.0.0.1:8090`.
- HTTP/API checks returned `200`, `200`, `200`, `401`, and token-auth `200`.
- `codex mcp list` showed `plane` enabled with stdio auth unsupported.
- `claude mcp list` showed `plane` connected.

## Stop conditions

Stop and ask before:

- exposing Plane over public DNS, Tailscale Funnel, or `plane.harm.org`
- printing, rotating, or moving the Plane API token
- replacing bundled Plane Postgres, Valkey/Redis, RabbitMQ, or MinIO with host services
- deleting `/home/halbritt/services/plane-selfhost`
- changing unrelated Tailscale Serve mappings

The future public personal tracker remains separate. The Praxis repo records a TODO
for a full RFC before any public Plane tracker integration.
