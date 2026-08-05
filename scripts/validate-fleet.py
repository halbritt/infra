#!/usr/bin/env python3
"""Validate the lightweight fleet repository contracts without third-party packages."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
IGNORED_PARTS = {".git", ".ruff_cache", "__pycache__"}


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.host_count = 0
        self.role_count = 0
        self.shared_reference_count = 0

    def error(self, message: str) -> None:
        self.errors.append(message)

    def load_manifest(self, path: Path) -> dict[str, object] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self.error(f"{path.relative_to(ROOT)}: invalid JSON-compatible YAML: {exc}")
            return None
        if not isinstance(value, dict):
            self.error(f"{path.relative_to(ROOT)}: manifest root must be a mapping")
            return None
        return value

    def safe_relative(self, owner: Path, raw: object, field: str) -> Path | None:
        if not isinstance(raw, str) or not raw:
            self.error(f"{owner.relative_to(ROOT)}: {field} must be a non-empty string")
            return None
        candidate = PurePosixPath(raw)
        if candidate.is_absolute() or ".." in candidate.parts:
            self.error(f"{owner.relative_to(ROOT)}: {field} must stay within its owner")
            return None
        return Path(*candidate.parts)

    def validate_roles(self) -> set[str]:
        roles_root = ROOT / "roles"
        known: set[str] = set()
        if not roles_root.is_dir():
            self.error("roles/: directory is missing")
            return known

        for directory in sorted(path for path in roles_root.iterdir() if path.is_dir()):
            name = directory.name
            manifest_path = directory / "role.yaml"
            if not NAME.fullmatch(name):
                self.error(f"roles/{name}: role directory is not DNS-safe kebab-case")
            if not manifest_path.is_file():
                self.error(f"roles/{name}: role.yaml is missing")
                continue
            manifest = self.load_manifest(manifest_path)
            if manifest is None:
                continue
            if manifest.get("schema_version") != 1:
                self.error(f"roles/{name}/role.yaml: schema_version must be 1")
            if manifest.get("name") != name:
                self.error(f"roles/{name}/role.yaml: name must match the directory")
            shared = manifest.get("shared")
            if not isinstance(shared, list) or not all(isinstance(item, str) for item in shared):
                self.error(f"roles/{name}/role.yaml: shared must be a string list")
                continue
            if len(shared) != len(set(shared)):
                self.error(f"roles/{name}/role.yaml: shared references must be unique")
            for reference in shared:
                relative = PurePosixPath(reference)
                if relative.is_absolute() or not relative.parts or relative.parts[0] != "shared":
                    self.error(f"roles/{name}/role.yaml: shared reference must start with shared/: {reference}")
                    continue
                if ".." in relative.parts or not (ROOT / Path(*relative.parts)).is_file():
                    self.error(f"roles/{name}/role.yaml: missing shared file: {reference}")
                    continue
                self.shared_reference_count += 1
            known.add(name)
            self.role_count += 1
        return known

    def validate_hosts(self, known_roles: set[str]) -> set[str]:
        hosts_root = ROOT / "hosts"
        known_hosts: set[str] = set()
        if not hosts_root.is_dir():
            self.error("hosts/: directory is missing")
            return known_hosts

        for directory in sorted(path for path in hosts_root.iterdir() if path.is_dir()):
            name = directory.name
            known_hosts.add(name)
            self.host_count += 1
            if not NAME.fullmatch(name):
                self.error(f"hosts/{name}: host directory is not DNS-safe kebab-case")
            manifest_path = directory / "machine.yaml"
            if not manifest_path.is_file():
                self.error(f"hosts/{name}: machine.yaml is missing")
                continue
            manifest = self.load_manifest(manifest_path)
            if manifest is None:
                continue
            if manifest.get("schema_version") != 1:
                self.error(f"hosts/{name}/machine.yaml: schema_version must be 1")
            if manifest.get("name") != name:
                self.error(f"hosts/{name}/machine.yaml: name must match the directory")
            hostname = manifest.get("hostname")
            if not isinstance(hostname, str) or not hostname:
                self.error(f"hosts/{name}/machine.yaml: hostname must be a non-empty string")

            roles = manifest.get("roles")
            if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
                self.error(f"hosts/{name}/machine.yaml: roles must be a string list")
            else:
                if len(roles) != len(set(roles)):
                    self.error(f"hosts/{name}/machine.yaml: roles must be unique")
                for role in roles:
                    if role not in known_roles:
                        self.error(f"hosts/{name}/machine.yaml: unknown role: {role}")

            paths = manifest.get("paths")
            if not isinstance(paths, dict):
                self.error(f"hosts/{name}/machine.yaml: paths must be a mapping")
                continue
            resolved: dict[str, Path] = {}
            for field in ("config", "notes", "changelog"):
                relative = self.safe_relative(manifest_path, paths.get(field), f"paths.{field}")
                if relative is None:
                    continue
                target = directory / relative
                resolved[field] = target
                if not target.exists():
                    self.error(f"hosts/{name}/machine.yaml: paths.{field} does not exist: {relative}")

            if not (directory / "AGENTS.md").is_file():
                self.error(f"hosts/{name}: AGENTS.md is missing")
            if (directory / "source-import").exists():
                self.error(f"hosts/{name}/source-import: temporary import directory must be normalized")
            config = resolved.get("config")
            if config is not None and config.is_dir():
                for subsystem in sorted(path for path in config.iterdir() if path.is_dir()):
                    if not (subsystem / "README.md").is_file() and not (subsystem / "AGENTS.md").is_file():
                        self.error(
                            f"{subsystem.relative_to(ROOT)}: immediate subsystem needs README.md or AGENTS.md"
                        )
        return known_hosts

    def validate_secret_paths(self) -> None:
        secrets = ROOT / "secrets"
        if not (secrets / "README.md").is_file():
            self.error("secrets/README.md is missing")
            return
        allowed_names = {"README.md", ".gitkeep", ".sops.yaml"}
        allowed_suffixes = (".sops.yaml", ".sops.json", ".sops.env")
        for path in secrets.rglob("*"):
            if not path.is_file():
                continue
            if path.name in allowed_names or path.name.endswith(allowed_suffixes):
                continue
            self.error(f"{path.relative_to(ROOT)}: plaintext or unrecognized secret file")

    def validate_symlinks(self) -> None:
        for directory, names, files in os.walk(ROOT):
            names[:] = [name for name in names if name not in IGNORED_PARTS]
            for name in [*names, *files]:
                path = Path(directory) / name
                if path.is_symlink() and not path.exists():
                    self.error(f"{path.relative_to(ROOT)}: broken symlink")

    def validate_markdown_links(self) -> None:
        vendor = ROOT / "hosts/proximal/config/postgres/skills"
        for path in ROOT.rglob("*.md"):
            if any(part in IGNORED_PARTS for part in path.parts) or path.is_relative_to(vendor):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                self.error(f"{path.relative_to(ROOT)}: cannot read Markdown: {exc}")
                continue
            for match in MARKDOWN_LINK.finditer(text):
                target = match.group(1).strip()
                if target.startswith("<") and target.endswith(">"):
                    target = target[1:-1]
                elif " " in target:
                    target = target.split(" ", 1)[0]
                if (
                    not target
                    or target.startswith(("#", "/", "~"))
                    or "://" in target
                    or target.startswith(("mailto:", "file:"))
                    or "<" in target
                    or ">" in target
                ):
                    continue
                target = target.split("#", 1)[0]
                if not target:
                    continue
                resolved = (path.parent / target).resolve()
                try:
                    resolved.relative_to(ROOT)
                except ValueError:
                    continue
                if not resolved.exists():
                    self.error(f"{path.relative_to(ROOT)}: broken Markdown link: {target}")

    def validate_legacy_paths(self) -> None:
        config = ROOT / "hosts/proximal/config"
        if not config.is_dir():
            return
        subsystem_names = sorted(path.name for path in config.iterdir() if path.is_dir())
        old_prefixes = (
            "/home/halbritt/git/" + "proximal/",
            "%h/git/" + "proximal/",
            "~/git/" + "proximal/",
            "github.com/halbritt/" + "proximal/tree/master/",
        )
        for path in ROOT.rglob("*"):
            if not path.is_file() or any(part in IGNORED_PARTS for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            for prefix in old_prefixes:
                for subsystem in subsystem_names:
                    legacy = prefix + subsystem
                    if legacy in text:
                        self.error(f"{path.relative_to(ROOT)}: stale single-host path: {legacy}")

    def finish(self) -> int:
        if self.errors:
            for error in sorted(set(self.errors)):
                print(f"ERROR: {error}", file=sys.stderr)
            print(f"fleet validation failed: {len(set(self.errors))} error(s)", file=sys.stderr)
            return 1
        print(
            "fleet validation passed: "
            f"{self.host_count} host(s), {self.role_count} role(s), "
            f"{self.shared_reference_count} shared reference(s)"
        )
        return 0


def main() -> int:
    validation = Validation()
    known_roles = validation.validate_roles()
    validation.validate_hosts(known_roles)
    validation.validate_secret_paths()
    validation.validate_symlinks()
    validation.validate_markdown_links()
    validation.validate_legacy_paths()
    return validation.finish()


if __name__ == "__main__":
    raise SystemExit(main())
