#!/usr/bin/env python3
"""Scaffold local Plane projects and repo AGENTS.md blocks for GitHub repos."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


BEGIN = "<!-- BEGIN PROXIMAL PLANE TRACKING -->"
END = "<!-- END PROXIMAL PLANE TRACKING -->"

STATE_SPECS = [
    ("Backlog", "#60646C", "backlog", "Waiting to be made ready."),
    ("Ready", "#3B82F6", "unstarted", "Ready for an agent to claim."),
    ("Claimed", "#8B5CF6", "unstarted", "Claimed by an agent lease."),
    ("In Progress", "#F59E0B", "started", "Implementation or investigation is active."),
    ("Submitted", "#06B6D4", "started", "Agent submitted artifacts for review."),
    ("Review", "#6366F1", "started", "Human or reviewer-agent review is active."),
    ("Accepted", "#46A758", "completed", "Accepted and no further work is required."),
    ("Rejected", "#EF4444", "cancelled", "Rejected; needs rework or replacement."),
    ("Refused", "#9AA4BC", "cancelled", "Deliberately refused; should not be retried unchanged."),
    ("Blocked", "#DC2626", "started", "Blocked on user input or external state."),
]

LABEL_SPECS = [
    ("agent-coordination", "#5E6AD2", "Work item participates in the agent coordination workflow."),
    ("needs-verification", "#F59E0B", "Verification evidence is required before acceptance."),
    ("authority-required", "#DC2626", "Needs explicit owner authority before action."),
    ("blocked", "#EF4444", "Blocked on input or external state."),
    ("github", "#24292F", "Work item is tied to a GitHub repository."),
]


class ApiError(RuntimeError):
    pass


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value.strip().strip('"').strip("'")
    return env


def json_request(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict | None = None,
    ok: tuple[int, ...] = (200, 201),
) -> tuple[int, dict | list | None]:
    for attempt in range(8):
        body = None
        req_headers = dict(headers)
        if payload is not None:
            body = json.dumps(payload).encode()
            req_headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                data = json.loads(raw.decode() or "null") if raw else None
                if resp.status not in ok:
                    raise ApiError(f"{method} {url} returned {resp.status}: {data}")
                return resp.status, data
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode(errors="replace")
            if exc.code == 429 and attempt < 7:
                retry_after = exc.headers.get("Retry-After")
                delay = int(retry_after) if retry_after and retry_after.isdigit() else min(60, 2**attempt)
                time.sleep(delay)
                continue
            if exc.code not in ok:
                raise ApiError(f"{method} {url} returned {exc.code}: {raw[:500]}")
            return exc.code, json.loads(raw or "null")
    raise ApiError(f"{method} {url} failed after retries")


class PlaneClient:
    def __init__(self, base_url: str, workspace: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.workspace = workspace
        self.headers = {
            "X-Api-Key": token,
            "x-workspace-slug": workspace,
            "Accept": "application/json",
        }

    def url(self, path: str, params: dict[str, str | int] | None = None) -> str:
        full = f"{self.base_url}{path}"
        if params:
            full += "?" + urllib.parse.urlencode(params)
        return full

    def request(self, method: str, path: str, payload: dict | None = None) -> dict | list | None:
        _, data = json_request(method, self.url(path), self.headers, payload)
        return data

    def list_projects(self) -> list[dict]:
        projects: list[dict] = []
        cursor = ""
        while True:
            params: dict[str, str | int] = {"per_page": 100}
            if cursor:
                params["cursor"] = cursor
            data = json_request(
                "GET",
                self.url(f"/api/v1/workspaces/{self.workspace}/projects/", params),
                self.headers,
            )[1]
            if isinstance(data, list):
                projects.extend(data)
                break
            if not isinstance(data, dict):
                break
            projects.extend(data.get("results") or [])
            if not data.get("next_page_results"):
                break
            cursor = data.get("next_cursor") or ""
            if not cursor:
                break
        return projects

    def ensure_project(self, repo: dict, identifier: str, existing: dict | None) -> tuple[dict, str]:
        full_name = repo["nameWithOwner"]
        name = plane_project_name(repo["name"])
        payload = {
            "name": name,
            "identifier": identifier,
            "description": (
                f"GitHub repository {full_name}. Local/private Plane project "
                "scaffolded for agent coordination on proximal."
            ),
            "external_source": "github",
            "external_id": full_name,
            "module_view": True,
            "cycle_view": True,
            "issue_views_view": True,
            "page_view": True,
            "intake_view": True,
            "is_issue_type_enabled": True,
        }
        path = f"/api/v1/workspaces/{self.workspace}/projects/"
        if existing is None:
            return self.request("POST", path, payload), "created"  # type: ignore[return-value]
        update_payload = {
            k: v
            for k, v in payload.items()
            if k not in {"identifier"} and existing.get(k) != v
        }
        if update_payload:
            project_id = existing["id"]
            updated = self.request("PATCH", f"{path}{project_id}/", update_payload)
            return updated if isinstance(updated, dict) else existing, "updated"
        return existing, "unchanged"

    def ensure_states(self, project_id: str) -> dict[str, int]:
        path = f"/api/v1/workspaces/{self.workspace}/projects/{project_id}/states/"
        data = self.request("GET", path)
        states = data if isinstance(data, list) else (data or {}).get("results", [])
        by_name = {state["name"].casefold(): state for state in states}
        created = 0
        for name, color, group, description in STATE_SPECS:
            if name.casefold() in by_name:
                continue
            self.request(
                "POST",
                path,
                {
                    "name": name,
                    "color": color,
                    "group": group,
                    "description": description,
                    "external_source": "proximal-plane-rollout",
                    "external_id": name,
                },
            )
            created += 1
        return {"existing": len(by_name), "created": created}

    def ensure_labels(self, project_id: str) -> dict[str, int]:
        path = f"/api/v1/workspaces/{self.workspace}/projects/{project_id}/labels/"
        data = self.request("GET", path)
        labels = data if isinstance(data, list) else (data or {}).get("results", [])
        by_name = {label["name"].casefold(): label for label in labels}
        created = 0
        for name, color, description in LABEL_SPECS:
            if name.casefold() in by_name:
                continue
            self.request(
                "POST",
                path,
                {
                    "name": name,
                    "color": color,
                    "description": description,
                    "external_source": "proximal-plane-rollout",
                    "external_id": name,
                },
            )
            created += 1
        return {"existing": len(by_name), "created": created}


class GitHubClient:
    def __init__(self):
        token = subprocess.check_output(
            ["env", "-u", "GH_TOKEN", "gh", "auth", "token"], text=True
        ).strip()
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        ok: tuple[int, ...] = (200, 201),
    ) -> tuple[int, dict | list | None]:
        return json_request(method, f"https://api.github.com{path}", self.headers, payload, ok)

    def get_agents(self, full_name: str, branch: str) -> tuple[str | None, str | None]:
        path = (
            f"/repos/{full_name}/contents/AGENTS.md?"
            + urllib.parse.urlencode({"ref": branch})
        )
        try:
            _, data = self.request("GET", path)
        except ApiError as exc:
            if "returned 404" in str(exc):
                return None, None
            raise
        if not isinstance(data, dict):
            return None, None
        content = base64.b64decode(data["content"]).decode()
        return content, data["sha"]

    def put_agents(self, full_name: str, branch: str, content: str, sha: str | None) -> None:
        payload = {
            "message": "docs: add Plane tracking to AGENTS",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        self.request("PUT", f"/repos/{full_name}/contents/AGENTS.md", payload)


def project_identifier(name: str, used: set[str]) -> str:
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", name) if p]
    if len(parts) <= 1:
        base = re.sub(r"[^A-Za-z0-9]", "", name).upper()[:12]
    else:
        base = "".join(part[:3].upper() for part in parts)[:12]
    if not base:
        base = "REPO"
    if not base[0].isalpha():
        base = "R" + base
    candidate = base
    index = 2
    while candidate in used:
        suffix = str(index)
        candidate = f"{base[: 12 - len(suffix)]}{suffix}"
        index += 1
    used.add(candidate)
    return candidate


def plane_project_name(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9]+", " ", name).strip()
    if not clean:
        return "Repository"
    if any(char.isupper() for char in name):
        return clean
    return clean.title()


def agents_block(repo: dict, project: dict) -> str:
    full_name = repo["nameWithOwner"]
    extra_lines = ""
    if full_name == "halbritt/praxis":
        extra_lines = (
            "- Plane connector lab project: `Praxis Plane Connector Lab` (`PXLAB`) for local\n"
            "  connector development and verification only; no personal production data.\n"
            "- Plane connector lab token pointer:\n"
            "  `/home/halbritt/.config/plane/repos/praxis-pxlab.env` (`0600`, outside git).\n"
        )
    return f"""{BEGIN}
## Plane Tracking

This repository is represented in the local/private Plane workspace `Proximal`.

- Plane project: `{project["name"]}` (`{project["identifier"]}`)
{extra_lines}\
- Issue tracker: Plane (`Proximal` workspace), project `{project["name"]}` (`{project["identifier"]}`).
- Plane URL: `https://proximal.tail0ecc2e.ts.net:10000/`
- GitHub repo: `https://github.com/{full_name}`
- GitHub Issues: deprecated; use Plane work items for new issue tracking, claims, reviews, and issue-state changes.
- Use Plane work items for multi-agent planning, claims, submitted artifacts, reviews, and acceptance decisions.
- When updating Plane, include the repo, branch/worktree, `run_id`, `base_sha`, artifact links, verification evidence, and authority scope in the work item description or comments.
- Do not commit Plane API tokens. Local tokens and MCP env files live outside git under `~/.config/plane/`.
{END}"""


def merge_agents(existing: str | None, block: str) -> str:
    if existing is None:
        return f"# AGENTS.md\n\nRepository-level instructions for AI coding agents.\n\n{block}\n"
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
    if pattern.search(existing):
        return pattern.sub(block, existing)
    suffix = "" if existing.endswith("\n") else "\n"
    return f"{existing}{suffix}\n{block}\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repos-json", required=True, type=Path)
    parser.add_argument(
        "--plane-env",
        default=Path.home() / ".config/plane/proximal-mcp.env",
        type=Path,
    )
    parser.add_argument("--skip-agents-repo", action="append", default=[])
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repos = json.loads(args.repos_json.read_text())
    env = load_env(args.plane_env)
    required = ["PLANE_API_KEY", "PLANE_WORKSPACE_SLUG", "PLANE_BASE_URL"]
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise SystemExit(f"Missing required Plane env keys: {', '.join(missing)}")

    plane = PlaneClient(env["PLANE_BASE_URL"], env["PLANE_WORKSPACE_SLUG"], env["PLANE_API_KEY"])
    github = None if args.dry_run else GitHubClient()

    projects = plane.list_projects()
    used_identifiers = {p.get("identifier") for p in projects if p.get("identifier")}
    by_external = {p.get("external_id"): p for p in projects if p.get("external_id")}
    by_identifier = {p.get("identifier"): p for p in projects if p.get("identifier")}
    by_name = {p.get("name", "").casefold(): p for p in projects if p.get("name")}

    report = {
        "repos_total": len(repos),
        "plane": [],
        "agents": [],
        "skipped": [],
    }

    for repo in repos:
        full_name = repo["nameWithOwner"]
        identifier = project_identifier(repo["name"], used_identifiers)
        existing = by_external.get(full_name) or by_identifier.get(identifier) or by_name.get(repo["name"].casefold())
        if existing and existing.get("identifier"):
            identifier = existing["identifier"]
        if args.dry_run:
            project = existing or {"id": "dry-run", "name": repo["name"], "identifier": identifier}
            project_status = "would-create" if existing is None else "would-update"
            state_status = {"existing": 0, "created": 0}
            label_status = {"existing": 0, "created": 0}
        else:
            project, project_status = plane.ensure_project(repo, identifier, existing)
            state_status = plane.ensure_states(project["id"])
            label_status = plane.ensure_labels(project["id"])
            by_external[full_name] = project
            by_identifier[project["identifier"]] = project
            by_name[project["name"].casefold()] = project
        report["plane"].append(
            {
                "repo": full_name,
                "project_id": project["id"],
                "project_name": project["name"],
                "identifier": project["identifier"],
                "status": project_status,
                "states": state_status,
                "labels": label_status,
            }
        )

        branch = repo.get("defaultBranch") or ""
        if repo["name"] in args.skip_agents_repo:
            report["agents"].append({"repo": full_name, "status": "skipped-local-update"})
            continue
        if not branch:
            report["skipped"].append({"repo": full_name, "reason": "no default branch"})
            continue
        block = agents_block(repo, project)
        if args.dry_run:
            report["agents"].append({"repo": full_name, "branch": branch, "status": "would-update"})
            continue
        assert github is not None
        existing_content, sha = github.get_agents(full_name, branch)
        new_content = merge_agents(existing_content, block)
        if existing_content == new_content:
            status = "unchanged"
        else:
            github.put_agents(full_name, branch, new_content, sha)
            status = "created" if existing_content is None else "updated"
            time.sleep(0.25)
        report["agents"].append({"repo": full_name, "branch": branch, "status": status})

    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report_out:
        args.report_out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
