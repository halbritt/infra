#!/usr/bin/env python3
"""Migrate open halbritt/striatum GitHub issues into the local Plane project."""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from scaffold_github_repos import ApiError, PlaneClient, json_request, load_env


DEFAULT_REPO = "halbritt/striatum"
DEFAULT_PROJECT_EXTERNAL_ID = "halbritt/striatum"
DEFAULT_PLANE_ENV = Path.home() / ".config/plane/proximal-mcp.env"
EXTERNAL_SOURCE = "github"


def now_slug() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")


def run_gh_issue_export(repo: str, limit: int) -> list[dict]:
    fields = (
        "number,title,body,comments,labels,assignees,milestone,createdAt,updatedAt,url,author"
    )
    env = dict(os.environ)
    env.pop("GH_TOKEN", None)
    raw = subprocess.check_output(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--limit",
            str(limit),
            "--json",
            fields,
        ],
        text=True,
        env=env,
    )
    issues = json.loads(raw)
    if not isinstance(issues, list):
        raise RuntimeError("gh issue export did not return a list")
    return issues


def normalize_color(value: str | None) -> str:
    if not value:
        return "#5E6AD2"
    value = value.strip()
    if value.startswith("#"):
        return value
    return f"#{value}"


def item_external_id(repo: str, number: int) -> str:
    return f"{repo}#{number}"


def truncate_name(value: str, limit: int = 240) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def label_names(issue: dict) -> list[str]:
    return [label["name"] for label in issue.get("labels") or [] if label.get("name")]


def comment_author(comment: dict) -> str:
    return (comment.get("author") or {}).get("login") or "(unknown)"


def plain_comments(issue: dict) -> list[str]:
    lines: list[str] = []
    comments = issue.get("comments") or []
    if not comments:
        return lines
    lines.extend(["", "GitHub comments at migration time:", ""])
    for index, comment in enumerate(comments, start=1):
        body = (comment.get("body") or "").strip() or "(No comment body.)"
        lines.extend(
            [
                f"Comment {index}: {comment_author(comment)} at {comment.get('createdAt') or ''}",
                f"URL: {comment.get('url') or ''}",
                "",
                body,
                "",
            ]
        )
    return lines


def html_comments(issue: dict) -> list[str]:
    comments = issue.get("comments") or []
    if not comments:
        return []
    parts = ["<h2>GitHub Comments At Migration Time</h2>"]
    for index, comment in enumerate(comments, start=1):
        author = comment_author(comment)
        created = comment.get("createdAt") or ""
        url = comment.get("url") or ""
        body = (comment.get("body") or "").strip() or "(No comment body.)"
        parts.extend(
            [
                f"<h3>Comment {index}</h3>",
                "<ul>",
                f"<li><strong>Author:</strong> {html.escape(author)}</li>",
                f"<li><strong>Created:</strong> {html.escape(created)}</li>",
                f'<li><strong>URL:</strong> <a href="{html.escape(url, quote=True)}">{html.escape(url)}</a></li>',
                "</ul>",
                f"<pre>{html.escape(body)}</pre>",
            ]
        )
    return parts


def choose_state(issue_labels: set[str], states_by_name: dict[str, dict]) -> tuple[str, str]:
    if "ready-for-agent" in issue_labels and "ready" in states_by_name:
        return states_by_name["ready"]["id"], "Ready"
    if "ready-for-human" in issue_labels and "blocked" in states_by_name:
        return states_by_name["blocked"]["id"], "Blocked"
    return states_by_name["backlog"]["id"], "Backlog"


def plain_description(repo: str, issue: dict) -> str:
    labels = ", ".join(label_names(issue)) or "(none)"
    assignees = ", ".join(a.get("login", "") for a in issue.get("assignees") or []) or "(none)"
    milestone = (issue.get("milestone") or {}).get("title") or "(none)"
    author = (issue.get("author") or {}).get("login") or "(unknown)"
    body = (issue.get("body") or "").strip() or "(No GitHub issue body.)"
    lines = [
        f"GitHub issue: {issue['url']}",
        f"Repository: {repo}",
        f"GitHub number: #{issue['number']}",
        f"Author: {author}",
        f"Created: {issue.get('createdAt') or ''}",
        f"Updated: {issue.get('updatedAt') or ''}",
        f"Labels: {labels}",
        f"Assignees: {assignees}",
        f"Milestone: {milestone}",
        "",
        "Original GitHub body:",
        "",
        body,
    ]
    lines.extend(plain_comments(issue))
    return "\n".join(lines)


def html_description(repo: str, issue: dict) -> str:
    labels = ", ".join(label_names(issue)) or "(none)"
    assignees = ", ".join(a.get("login", "") for a in issue.get("assignees") or []) or "(none)"
    milestone = (issue.get("milestone") or {}).get("title") or "(none)"
    author = (issue.get("author") or {}).get("login") or "(unknown)"
    body = (issue.get("body") or "").strip() or "(No GitHub issue body.)"
    url = issue["url"]
    rows = [
        ("Repository", repo),
        ("GitHub number", f"#{issue['number']}"),
        ("Author", author),
        ("Created", issue.get("createdAt") or ""),
        ("Updated", issue.get("updatedAt") or ""),
        ("Labels", labels),
        ("Assignees", assignees),
        ("Milestone", milestone),
    ]
    items = "\n".join(
        f"<li><strong>{html.escape(key)}:</strong> {html.escape(value)}</li>"
        for key, value in rows
    )
    parts = [
        "<h2>GitHub Issue</h2>",
        "<ul>",
        f'<li><strong>URL:</strong> <a href="{html.escape(url, quote=True)}">{html.escape(url)}</a></li>',
        items,
        "</ul>",
        "<h2>Original GitHub Body</h2>",
        f"<pre>{html.escape(body)}</pre>",
    ]
    parts.extend(html_comments(issue))
    return "\n".join(parts)


class PlaneWorkItemClient:
    def __init__(self, base_url: str, workspace: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.workspace = workspace
        self.headers = {
            "X-Api-Key": token,
            "x-workspace-slug": workspace,
            "Accept": "application/json",
        }

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        ok: tuple[int, ...] = (200, 201),
    ) -> dict | list | None:
        return json_request(method, self.url(path), self.headers, payload, ok=ok)[1]

    def list_paginated(self, path: str) -> list[dict]:
        items: list[dict] = []
        cursor = ""
        separator = "&" if "?" in path else "?"
        while True:
            page_path = f"{path}{separator}per_page=100"
            if cursor:
                page_path += f"&cursor={cursor}"
            data = self.request("GET", page_path)
            if isinstance(data, list):
                return data
            if not isinstance(data, dict):
                return items
            items.extend(data.get("results") or [])
            cursor = data.get("next_cursor") or ""
            if not data.get("next_page_results") or not cursor:
                return items

    def project_path(self, project_id: str, suffix: str) -> str:
        return f"/api/v1/workspaces/{self.workspace}/projects/{project_id}/{suffix.strip('/')}/"

    def ensure_label(
        self, project_id: str, repo: str, label: dict, existing: dict | None
    ) -> tuple[dict, str]:
        path = self.project_path(project_id, "labels")
        payload = {
            "name": label["name"],
            "color": normalize_color(label.get("color")),
            "description": label.get("description") or f"Mirrored GitHub label {label['name']}.",
            "external_source": EXTERNAL_SOURCE,
            "external_id": f"{repo}:label:{label['name']}",
        }
        if existing is None:
            created = self.request("POST", path, payload)
            if not isinstance(created, dict):
                raise RuntimeError(f"Plane returned non-object for label {label['name']}")
            return created, "created"
        patch = {
            key: value
            for key, value in payload.items()
            if value and existing.get(key) != value and existing.get("external_source") == EXTERNAL_SOURCE
        }
        if patch:
            updated = self.request("PATCH", f"{path}{existing['id']}/", patch)
            return updated if isinstance(updated, dict) else existing, "updated"
        return existing, "unchanged"

    def ensure_work_item(
        self,
        project_id: str,
        issue: dict,
        state_id: str,
        label_ids: list[str],
        existing: dict | None,
        repo: str,
        refresh_descriptions: bool = False,
    ) -> tuple[dict, str]:
        path = self.project_path(project_id, "work-items")
        payload = {
            "name": truncate_name(f"GH #{issue['number']}: {issue['title']}"),
            "description_html": html_description(repo, issue),
            "description_stripped": plain_description(repo, issue),
            "priority": "none",
            "state": state_id,
            "labels": label_ids,
            "external_source": EXTERNAL_SOURCE,
            "external_id": item_external_id(repo, issue["number"]),
        }
        if existing is None:
            created = self.request("POST", path, payload)
            if not isinstance(created, dict):
                raise RuntimeError(f"Plane returned non-object for issue #{issue['number']}")
            return created, "created"
        existing_label_ids = sorted(label_id for label_id in item_label_ids(existing) if label_id)
        wanted_label_ids = sorted(label_ids)
        existing_state = item_state_id(existing)
        patch = {
            key: value
            for key, value in payload.items()
            if key
            not in {"description_html", "description_stripped", "labels", "state"}
            and existing.get(key) != value
        }
        if refresh_descriptions:
            patch["description_html"] = payload["description_html"]
        if existing_label_ids != wanted_label_ids:
            patch["labels"] = label_ids
        if existing_state != state_id:
            patch["state"] = state_id
        if patch:
            updated = self.request("PATCH", f"{path}{existing['id']}/", patch)
            return updated if isinstance(updated, dict) else existing, "updated"
        return existing, "unchanged"


def item_label_ids(item: dict) -> list[str]:
    labels = item.get("labels") or []
    ids: list[str] = []
    for label in labels:
        if isinstance(label, dict) and label.get("id"):
            ids.append(label["id"])
        elif isinstance(label, str):
            ids.append(label)
    return ids


def item_state_id(item: dict) -> str | None:
    state = item.get("state")
    if isinstance(state, dict):
        return state.get("id")
    if isinstance(state, str):
        return state
    return None


def unique_github_labels(issues: list[dict]) -> list[dict]:
    by_name: dict[str, dict] = {}
    for issue in issues:
        for label in issue.get("labels") or []:
            name = label.get("name")
            if name and name not in by_name:
                by_name[name] = label
    return [by_name[name] for name in sorted(by_name)]


def load_plane(args: argparse.Namespace) -> tuple[PlaneClient, PlaneWorkItemClient, dict[str, str]]:
    env = load_env(args.plane_env)
    required = ["PLANE_API_KEY", "PLANE_WORKSPACE_SLUG", "PLANE_BASE_URL"]
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise SystemExit(f"Missing required Plane env keys: {', '.join(missing)}")
    return (
        PlaneClient(env["PLANE_BASE_URL"], env["PLANE_WORKSPACE_SLUG"], env["PLANE_API_KEY"]),
        PlaneWorkItemClient(env["PLANE_BASE_URL"], env["PLANE_WORKSPACE_SLUG"], env["PLANE_API_KEY"]),
        env,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--project-external-id", default=DEFAULT_PROJECT_EXTERNAL_ID)
    parser.add_argument("--plane-env", default=DEFAULT_PLANE_ENV, type=Path)
    parser.add_argument("--limit", default=500, type=int)
    parser.add_argument("--report-out", type=Path)
    parser.add_argument(
        "--refresh-descriptions",
        action="store_true",
        help="Rewrite existing Plane descriptions from current GitHub issue bodies/comments.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    issues = run_gh_issue_export(args.repo, args.limit)
    plane_projects, work_items, env = load_plane(args)
    projects = plane_projects.list_projects()
    project = next((p for p in projects if p.get("external_id") == args.project_external_id), None)
    if project is None:
        raise SystemExit(f"No Plane project found with external_id={args.project_external_id!r}")
    project_id = project["id"]

    states = work_items.list_paginated(work_items.project_path(project_id, "states"))
    states_by_name = {state["name"].casefold(): state for state in states if state.get("name")}
    if "backlog" not in states_by_name:
        raise SystemExit("Striatum Plane project has no Backlog state")

    labels = work_items.list_paginated(work_items.project_path(project_id, "labels"))
    labels_by_name = {label["name"].casefold(): label for label in labels if label.get("name")}

    standard_label_names = ["github", "agent-coordination"]
    label_results: list[dict] = []
    if not args.dry_run:
        for label in unique_github_labels(issues):
            existing = labels_by_name.get(label["name"].casefold())
            ensured, status = work_items.ensure_label(project_id, args.repo, label, existing)
            labels_by_name[ensured["name"].casefold()] = ensured
            label_results.append({"name": ensured["name"], "status": status})
    else:
        for label in unique_github_labels(issues):
            status = "would-create" if label["name"].casefold() not in labels_by_name else "would-use"
            label_results.append({"name": label["name"], "status": status})

    labels = work_items.list_paginated(work_items.project_path(project_id, "labels"))
    labels_by_name = {label["name"].casefold(): label for label in labels if label.get("name")}

    existing_items = work_items.list_paginated(
        work_items.project_path(project_id, "work-items")
        + (
            "?fields=id,name,description_html,description_stripped,priority,"
            "external_id,external_source,state,labels,sequence_id&expand=labels,state"
        )
    )
    items_by_external = {
        item.get("external_id"): item
        for item in existing_items
        if item.get("external_source") == EXTERNAL_SOURCE and item.get("external_id")
    }

    migrated: list[dict] = []
    for issue in sorted(issues, key=lambda item: item["number"]):
        names = set(label_names(issue))
        state_id, state_name = choose_state(names, states_by_name)
        wanted_labels = list(label_names(issue)) + standard_label_names
        if "ready-for-human" in names:
            wanted_labels.append("authority-required")
        label_ids = [
            labels_by_name[name.casefold()]["id"]
            for name in sorted(set(wanted_labels), key=str.casefold)
            if name.casefold() in labels_by_name
        ]
        external_id = item_external_id(args.repo, issue["number"])
        existing = items_by_external.get(external_id)
        if args.dry_run:
            status = "would-update" if existing else "would-create"
            item = existing or {}
        else:
            item, status = work_items.ensure_work_item(
                project_id,
                issue,
                state_id,
                label_ids,
                existing,
                args.repo,
                refresh_descriptions=args.refresh_descriptions,
            )
        migrated.append(
            {
                "github_issue": issue["number"],
                "github_url": issue["url"],
                "plane_id": item.get("id"),
                "plane_identifier": (
                    f"{project['identifier']}-{item.get('sequence_id')}"
                    if item.get("sequence_id")
                    else None
                ),
                "state": state_name,
                "status": status,
                "labels": sorted(set(wanted_labels), key=str.casefold),
            }
        )

    report = {
        "repo": args.repo,
        "project": {
            "id": project_id,
            "identifier": project.get("identifier"),
            "name": project.get("name"),
            "external_id": project.get("external_id"),
        },
        "dry_run": args.dry_run,
        "github_open_issues": len(issues),
        "plane_existing_work_items_before": len(existing_items),
        "labels": label_results,
        "work_items": migrated,
        "summary": {
            "created": sum(1 for item in migrated if item["status"] == "created"),
            "updated": sum(1 for item in migrated if item["status"] == "updated"),
            "unchanged": sum(1 for item in migrated if item["status"] == "unchanged"),
            "would_create": sum(1 for item in migrated if item["status"] == "would-create"),
            "would_update": sum(1 for item in migrated if item["status"] == "would-update"),
        },
    }
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    report_out = args.report_out or Path(f"/tmp/plane-striatum-gh-issue-migration-{now_slug()}.json")
    report_out.write_text(output)
    print(output)
    print(f"report={report_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ApiError as exc:
        raise SystemExit(str(exc)) from exc
