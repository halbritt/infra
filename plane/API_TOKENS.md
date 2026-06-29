# Plane API token policy

Plane API tokens on `proximal` are credentials. They are never committed to this
repo or to any application repo.

## Current token

The current local/private Proximal MCP wrapper reads:

```text
/home/halbritt/.config/plane/proximal-mcp.env
```

That file is mode `0600` inside a mode `0700` directory and contains the real
`PLANE_API_KEY`, `PLANE_WORKSPACE_SLUG`, and `PLANE_BASE_URL` values. Treat it as the
operator/local-agent token for this host.

The public-intended `plane.harm.org` MCP registration is separate:

```text
/home/halbritt/.config/plane/harm-mcp.env
```

That file is also mode `0600` and contains `PLANE_API_KEY`,
`PLANE_WORKSPACE_SLUG=harm`, `PLANE_BASE_URL=https://plane.harm.org`, and
`PLANE_INTERNAL_BASE_URL=http://127.0.0.1:8190`. Local agents should use the
internal loopback URL for API calls so public edge failures do not break MCP work.

## Per-repo token slots

If separate tokens are desired for individual repos, store them outside git, for
example:

```text
/home/halbritt/.config/plane/repos/<github-repo-slug>.env
```

Each file should be mode `0600` and contain:

```env
PLANE_API_KEY=REDACTED
PLANE_WORKSPACE_SLUG=proximal
PLANE_BASE_URL=https://proximal.tail0ecc2e.ts.net:10000
PLANE_PROJECT_IDENTIFIER=REDACTED
GITHUB_REPOSITORY=halbritt/REDACTED
```

Do not put these tokens in GitHub repository secrets unless a repo genuinely needs
CI access to the local Plane instance. The current local/private pilot is for human
and local-agent coordination on `proximal`, not cloud CI automation.

Current explicit per-repo token:

| purpose | pointer | Plane project |
|---|---|---|
| Praxis Plane connector lab | `/home/halbritt/.config/plane/repos/praxis-pxlab.env` | `Praxis Plane Connector Lab` (`PXLAB`) |
| Praxis personal runtime | `/home/halbritt/.config/plane/repos/praxis-personal.env` | `Praxis` (`PRAXIS`) on `plane.harm.org`, project id `978fcda1-c9c1-4437-b83a-5c3d6de0178e` |

## Automation boundary

As of the 2026-06-28 rollout, the Plane MCP/API-key surface used here can manage
projects, states, labels, and work items with an existing token. The token CRUD
endpoint in Plane CE is session-authenticated at `/api/users/api-tokens/`, not
usable with an existing API key. For this local self-hosted pilot, the PXLAB token
was created directly inside the Plane API container through Django's model layer and
written to the pointer file without printing the token value. Prefer the UI for
ordinary token creation; use the local container path only for explicit local
operator work where the token can be written directly to a `0600` file.
