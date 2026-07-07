# Plane Agent Guide

Purpose: load this file before an agent reads or writes Plane data from this
host. It summarizes the Plane product model, the local instance split on
`proximal`, and the safe automation path through MCP or REST.

This guide is deliberately about usage and operating boundaries. Deployment
details remain in `plane/README.md` and `plane-public/README.md`.

## Instance Map

| MCP name | Plane instance | Workspace | Use for | Local API route | Secret file |
|---|---|---|---|---|---|
| `plane` | local/private pilot | `proximal` / `Proximal` | repo and multi-agent engineering tracker work | `http://127.0.0.1:8090` or tailnet URL | `/home/halbritt/.config/plane/proximal-mcp.env` |
| `plane-harm` | public-intended personal tracker | `harm` | personal/public tasks such as motorcycles and Praxis projection | `http://127.0.0.1:8190` via `PLANE_INTERNAL_BASE_URL` | `/home/halbritt/.config/plane/harm-mcp.env` |

Rules:

- Do not mix the two instances. They have separate workspaces, databases, Redis
  state, object storage, ports, API tokens, and trust boundaries.
- Do not commit tokens, `plane.env`, `.env`, dumps, generated passwords, Garage
  keys, Redis credentials, or MCP env files.
- Use `plane-harm` only when the user means `plane.harm.org` or the `harm`
  workspace. Use `plane` for the local/private `Proximal` workspace.
- Prefer loopback API routes for local automation. Keep public URLs as owner
  facing identities, not as the critical local-agent dependency.
- If an action would delete a project, delete a workspace, move data between
  instances, expose a token, or rebind state services off loopback, stop first.

## Product Model

Plane's hierarchy is:

```text
Workspace -> Project -> Work item
```

Use this vocabulary in new docs and comments:

- Workspace: top-level container for projects, members, pages, and work.
- Project: container for related work. A project has a short identifier such as
  `WR250R`, `CRF450RL`, `PRAXIS`, or `PROXIMAL`; work item identifiers use this
  prefix plus a sequence number.
- Work item: the tracked unit of work. Current Plane docs use "work item";
  some API paths, source files, and older UI strings still say "issue".
- State: workflow status. Default groups are `backlog`, `unstarted`, `started`,
  `completed`, and `cancelled`; API surfaces may also expose `triage`.
- Label: project-scoped tag for classification and filtering.
- Cycle: time-boxed planning period, similar to a sprint.
- Module: a focused grouping of work items, such as a feature, milestone,
  campaign, or subsystem. A work item can belong to multiple modules.
- View: saved filters, layout, sorting, and display settings. Views do not move
  or duplicate work items.
- Page: durable notes/specs/decisions attached to a project or workspace.
- Intake: request queue before accepted work enters the project workflow.
- Comment: discussion on a work item. Activity/history is separate system data.
- Epic: in current Plane docs, an Epic is a work item type, not a separate object
  family in every deployment.

## Agent Workflow

For a normal create/update task:

1. Pick the correct MCP connector: `plane` or `plane-harm`.
2. List projects and match by `identifier` or exact name. Keep the project UUID.
3. List states and choose the intended state UUID, usually `Todo` for new work.
4. List or create labels before using them. Labels are UUIDs in work item writes.
5. Create or update work items with stable `external_source` and `external_id`
   when the source data may be replayed. This makes imports idempotent.
6. Use the parent work item UUID for sub-items. Do not pass a human identifier
   such as `WR250R-1` where the API expects a UUID.
7. Verify with `list_work_items` or the equivalent REST list endpoint. Check the
   total count and spot-check labels/state/parent links.
8. Leave a local repo clean if you changed docs or desired state.

Recommended import pattern for a Markdown checklist:

- Create one project label per heading.
- Create one `Todo` work item per unchecked checkbox.
- Preserve nested checkboxes with `parent=<parent work item UUID>`.
- Preserve section grouping with labels instead of inventing fake parent tasks,
  unless the source list explicitly has a parent task.
- Use `external_source` such as `codex-plane-import` and deterministic
  `external_id` strings derived from the source item.

## MCP Notes

Codex can expose the Plane tools as namespaces like `mcp__plane` and
`mcp__plane_harm`. Tool exposure can vary by session, so discover tools first if
you need an operation that is not already loaded.

Useful operations usually include:

- `list_projects`, `create_project`, `retrieve_project`
- `list_states`, `create_state`, `update_state`
- `list_labels`, `create_label`
- `list_work_items`, `search_work_items`, `retrieve_work_item`
- `retrieve_work_item_by_identifier`
- `create_work_item`, `update_work_item`, `create_work_item_comment`
- `list_pages`, `create_page`
- cycle, module, milestone, estimate, type, and property tools when loaded

Tool gotchas:

- UUID fields require UUIDs. Resolve names first with list calls.
- `fields` and `expand` shape the returned payload. A missing field in a sparse
  response can mean you did not request it, not that the value is absent.
- Work item descriptions may use `description_html` or `description_stripped`.
  Prefer the connector's documented argument names over ad hoc JSON.
- Some Plane deployments expose Epics as a work item type. Resolve/import the
  type before creating typed Epic work items.
- `Auth Unsupported` in `codex mcp list` is normal for local stdio MCP servers.

Official MCP modes:

- Local stdio uses env vars such as `PLANE_API_KEY`, `PLANE_WORKSPACE_SLUG`, and
  `PLANE_BASE_URL`.
- HTTP with PAT token uses request headers. Official remote MCP docs name
  `Authorization: Bearer <PAT_TOKEN>` and `X-Workspace-slug: <SLUG>`.
- `PLANE_INTERNAL_BASE_URL` is for server-to-server calls when local/internal
  routing differs from public routing.

## REST API Notes

Prefer MCP inside Codex when the tool is available. Use REST only for diagnosis
or when no MCP tool exists.

Official REST shape:

```text
GET  /api/v1/workspaces/{workspace_slug}/projects/
POST /api/v1/workspaces/{workspace_slug}/projects/

GET  /api/v1/workspaces/{workspace_slug}/projects/{project_id}/work-items/
POST /api/v1/workspaces/{workspace_slug}/projects/{project_id}/work-items/
GET  /api/v1/workspaces/{workspace_slug}/projects/{project_id}/work-items/{resource_id}/
PATCH /api/v1/workspaces/{workspace_slug}/projects/{project_id}/work-items/{resource_id}/
DELETE /api/v1/workspaces/{workspace_slug}/projects/{project_id}/work-items/{resource_id}/

GET  /api/v1/workspaces/{workspace_slug}/work-items/search/
GET  /api/v1/workspaces/{workspace_slug}/projects/{project_id}/pages/
```

Authentication:

```text
X-API-Key: <token>
Authorization: Bearer <oauth-token>
```

Local probes in this repo often use:

```bash
curl -fsS \
  -H "X-Api-Key: ${PLANE_API_KEY}" \
  -H "x-workspace-slug: ${PLANE_WORKSPACE_SLUG}" \
  "${PLANE_INTERNAL_BASE_URL}/api/v1/users/me/"
```

Notes:

- Header names are case-insensitive over HTTP. Keep the exact local probe shape
  when copying existing repo checks.
- API key creation is not an ordinary API-key-authenticated automation path in
  this Plane CE setup. Prefer UI token creation unless doing explicit local
  operator work.
- Official docs state a default API-key limit of 60 requests per minute. The
  local/private pilot has a higher local limit for repo scaffolding; do not copy
  that posture to public-facing automation without a new rationale.
- Use `fields`, `expand`, `cursor`, and `per_page` to control response size.
  Official pagination uses cursors and caps page size at 100 in the documented
  API.

## UI Notes

When working through the UI:

- Select the workspace first.
- Open the project from the sidebar or workspace search.
- Use workspace search or `Cmd/Ctrl+K` when the target project, work item, page,
  or comment is known by name or identifier.
- Create a work item, set state/priority/labels/assignee/cycle/module, and put
  durable context in the description or a linked page.
- Use filters and PQL for temporary narrowing. Save a View only when the filter
  should be reused.
- Use Pages for decisions, specs, or context that should outlive a single work
  item comment.

## Destructive Operations

Project deletion is permanent in Plane. Official docs warn that deleting a
project removes work items, cycles, modules, views, pages, and related project
data with no recovery path. Prefer archive for ordinary cleanup.

Before any delete/archive/bulk state operation:

- list the target and verify the workspace and project
- confirm whether the action is reversible
- include the source of authority in a comment or artifact
- stop if the request could affect the wrong Plane instance

## Local Verification

For `plane` local/private pilot, see `plane/README.md`.

For `plane-harm` / `plane.harm.org`, see `plane-public/README.md`.

Fast MCP sanity checks:

```bash
codex mcp list
```

Fast REST auth sanity checks are documented in the subsystem READMEs and should
source the relevant env file locally. Do not print token values.

## Source Pointers

Official docs reviewed on 2026-07-07:

- https://docs.plane.so/introduction/core-concepts
- https://docs.plane.so/core-concepts/projects/overview
- https://docs.plane.so/core-concepts/issues/overview
- https://docs.plane.so/core-concepts/issues/states
- https://docs.plane.so/core-concepts/cycles
- https://docs.plane.so/core-concepts/modules
- https://docs.plane.so/core-concepts/views
- https://developers.plane.so/api-reference/introduction
- https://developers.plane.so/api-reference/issue/add-issue
- https://developers.plane.so/api-reference/issue/list-issues
- https://developers.plane.so/api-reference/project/add-project
- https://developers.plane.so/api-reference/page/list-project-pages
- https://developers.plane.so/dev-tools/mcp-server
- https://github.com/makeplane/plane-mcp-server

Local desired-state docs:

- `AGENTS.md`
- `plane/README.md`
- `plane/API_TOKENS.md`
- `plane-public/AGENTS.md`
- `plane-public/README.md`
