#!/usr/bin/python3
"""Provision and retire the bounded CAPLAB P4 host surface."""

from __future__ import annotations

import argparse
import contextlib
import grp
import hashlib
import json
import os
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol

COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
DEFAULT_SOURCE_COMMIT_FILE = Path("/etc/caplab/SOURCE_COMMIT")
DEFAULT_SOURCE_REPO = Path("/home/halbritt/git/caplab")
DEFAULT_RUNTIME_CONFIG = Path("/etc/caplab/runtime.toml")
DEFAULT_STATE_FILE = Path("/var/lib/caplab-p4-roundtrip-2026-07-15.state.json")
CAMPAIGN_ID = "caplab-p4-roundtrip-2026-07-15"
AUTHORIZATION_EXPIRES_AT = datetime(2026, 7, 22, 23, 59, 59, tzinfo=UTC)
RUNTIME_ROLES = ("caplab_writer", "caplab_reader", "caplab_verifier")
GARAGE_BUCKET = "caplab-v0"
KEY_ALIASES = {role: f"{CAMPAIGN_ID}-{role.removeprefix('caplab_')}" for role in RUNTIME_ROLES}
INVENTORY_LABELS = (
    "before-register",
    "after-first-register",
    "after-replay",
    "after-conflict",
)
POSTGRES_TABLES = (
    "administrations",
    "agent_configurations",
    "artifacts",
    "attempt_artifacts",
    "attempts",
    "audit_events",
    "manifests",
    "model_identities",
    "operation_events",
    "operation_requests",
    "registrations",
    "schema_migrations",
    "trial_assignments",
    "trial_contexts",
)
POSTGRES_VIEWS = (
    "current_operation_state",
    "reconciliation",
    "registration_integrity",
)
POSTGRES_SEQUENCES = (
    "audit_events_audit_id_seq",
    "operation_events_event_id_seq",
    "registrations_registration_id_seq",
)
WRITER_INSERT_TABLES = tuple(table for table in POSTGRES_TABLES if table != "schema_migrations")


def expected_runtime_config(source_commit: str) -> dict[str, object]:
    return {
        "runtime": {
            "campaign_id": CAMPAIGN_ID,
            "authorization_expires_at": "2026-07-22T23:59:59Z",
            "runtime_commit": source_commit,
        },
        "postgres": {"conninfo": "dbname=caplab host=/var/run/postgresql"},
        "garage": {
            "endpoint_url": "http://127.0.0.1:3900",
            "region": "garage",
            "bucket": GARAGE_BUCKET,
            "credentials_root": "/etc/caplab/credentials",
        },
        "local_copy": {"root": "/nvr/caplab/v0"},
    }


class HostctlError(Exception):
    """A fail-closed operator error that is safe to print."""


def resolve_group_id(group: str) -> int:
    try:
        return grp.getgrnam(group).gr_gid
    except KeyError as error:
        raise HostctlError(f"runtime group is absent: {group}") from error


class Runner(Protocol):
    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str: ...


@dataclass(frozen=True)
class SubprocessRunner:
    environment: dict[str, str] | None = None

    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        del secret_output
        environment = (
            self.environment
            if self.environment is not None
            else {
                "HOME": "/root",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "PYTHONNOUSERSITE": "1",
            }
        )
        try:
            completed = subprocess.run(
                arguments,
                input=input_text,
                text=True,
                capture_output=True,
                check=False,
                close_fds=True,
                env=environment,
            )
        except OSError as error:
            raise HostctlError(f"could not execute {Path(arguments[0]).name}") from error
        if completed.returncode not in allowed_returncodes:
            raise HostctlError(
                f"{Path(arguments[0]).name} failed with exit {completed.returncode}; "
                "command output suppressed"
            )
        return completed.stdout


@dataclass(frozen=True)
class HostPaths:
    state_file: Path = DEFAULT_STATE_FILE
    credential_root: Path = Path("/etc/caplab/credentials")
    etc_root: Path = Path("/etc/caplab")
    venv_root: Path = Path("/opt/caplab/venvs")
    nvr_root: Path = Path("/nvr/caplab/v0")
    staging_root: Path = Path("/var/tmp")


@dataclass(frozen=True)
class PinnedFile:
    """One regular file read from the pinned Git tree, not the worktree."""

    path: str
    mode: str
    git_object: str
    payload: bytes


@dataclass
class HostController:
    paths: HostPaths
    runner: Runner
    identity_resolver: Callable[[str], tuple[int, int]]
    clock: Callable[[], datetime]
    group_resolver: Callable[[str], int] = resolve_group_id

    def bootstrap_base(
        self,
        source_commit: str,
        source_pin: Path,
        runtime_config: Path,
        source_repo: Path,
    ) -> None:
        require_active_authorization(self.clock())
        if read_source_commit(source_pin) != source_commit:
            raise HostctlError("bootstrap source pin changed after preflight")
        self._validate_runtime_config(runtime_config, source_commit)
        pinned_files = self._read_pinned_git_package(source_repo, source_commit)
        lock_bytes = self._pinned_payload(
            pinned_files,
            "runtime/requirements.lock",
        )
        self._validate_requirements_lock(lock_bytes)
        lock_hash = hashlib.sha256(lock_bytes).hexdigest()
        stage, source_tree_hash, interpreter_version = self._build_venv_stage(
            pinned_files,
            source_commit,
            lock_bytes,
        )
        state: dict[str, object] = {
            "schema_version": 1,
            "campaign_id": CAMPAIGN_ID,
            "phase": "bootstrapping",
            "effects_armed": False,
            "source_commit": source_commit,
            "source_worktree_clean": True,
            "requirements_lock_sha256": lock_hash,
            "source_tree_manifest_sha256": source_tree_hash,
            "runtime_interpreter": {
                "path": str(self.paths.venv_root / lock_hash / "bin/python"),
                "version": interpreter_version,
                "isolated": True,
                "user_site_disabled": True,
            },
            "garage_keys": [],
            "created_resources": {},
            "resource_steps": {},
            "resource_effects": {},
        }
        try:
            write_state(self.paths.state_file, state)
        except HostctlError as operation_error:
            try:
                self._remove_venv_stage(stage)
            except HostctlError as cleanup_error:
                raise HostctlError(
                    "initial state persistence failed and venv stage cleanup did not complete"
                ) from cleanup_error
            raise operation_error
        try:
            self._run_bootstrap_step(
                state,
                "common_group",
                ("os_group:caplab", "path:etc_root"),
                self._create_common_group_and_etc_root,
            )
            self._run_bootstrap_step(
                state,
                "runtime_identities",
                tuple(
                    effect
                    for role in RUNTIME_ROLES
                    for effect in (f"os_group:{role}", f"os_user:{role}")
                ),
                self._create_runtime_identities,
            )
            self._run_bootstrap_step(
                state,
                "host_paths",
                (
                    "file:source_pin",
                    "file:runtime_config",
                    "acl:postgres_config",
                    "path:credential_root",
                    "path:venv_root",
                    "acl:postgres_venv_traversal",
                    "paths:role_credentials",
                    "path:nvr_parent",
                    "path:nvr_root",
                    "path:venv_environment",
                    "acl:postgres_venv_read",
                ),
                lambda journal: self._install_base_paths(
                    source_pin,
                    runtime_config,
                    stage,
                    lock_hash,
                    journal,
                ),
            )
            state["created_resources"]["venv"] = True
            write_state(self.paths.state_file, state)
            self._run_bootstrap_step(
                state,
                "postgres",
                ("postgres:roles", "postgres:database", "postgres:database_acl"),
                self._create_postgres_namespace,
            )
            self._run_bootstrap_step(
                state,
                "garage_bucket",
                ("garage:bucket", "garage:quota"),
                self._create_garage_bucket,
            )
            state["phase"] = "base"
            write_state(self.paths.state_file, state)
        except HostctlError as operation_error:
            state["phase"] = "bootstrap_failed"
            state["bootstrap_error"] = "host operation failed; command output suppressed"
            cleanup_failures: list[str] = []
            try:
                write_state(self.paths.state_file, state)
            except HostctlError:
                cleanup_failures.append("state_failure_record")
            cleanup_failures.extend(self._rollback_partial_bootstrap(state))
            try:
                self._remove_venv_stage(stage)
            except HostctlError as cleanup_error:
                del cleanup_error
                cleanup_failures.append("venv_stage")
            state["bootstrap_cleanup_failures"] = cleanup_failures
            state["phase"] = (
                "bootstrap_rolled_back" if not cleanup_failures else "bootstrap_cleanup_failed"
            )
            try:
                write_state(self.paths.state_file, state)
            except HostctlError:
                cleanup_failures.append("state_cleanup_record")
            if cleanup_failures:
                raise HostctlError(
                    "bootstrap failed and partial-resource cleanup did not complete: "
                    + ",".join(cleanup_failures)
                ) from operation_error
            raise operation_error

    @staticmethod
    def _validate_requirements_lock(lock_bytes: bytes) -> None:
        if b"--hash=sha256:" not in lock_bytes:
            raise HostctlError("standalone runtime dependencies are not hash-locked")
        return lock_bytes

    @staticmethod
    def _validate_runtime_config(runtime_config: Path, source_commit: str) -> None:
        try:
            with runtime_config.open("rb") as config_stream:
                config = tomllib.load(config_stream)
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise HostctlError("cannot read the canonical runtime config") from error
        if config != expected_runtime_config(source_commit):
            raise HostctlError("canonical runtime config differs from the P4 contract")

    def _build_venv_stage(
        self,
        pinned_files: list[PinnedFile],
        source_commit: str,
        lock_bytes: bytes,
    ) -> tuple[Path, str, str]:
        stage_text = self.runner.run(
            [
                "mktemp",
                "--directory",
                str(self.paths.staging_root / "caplab-venv.XXXXXXXX"),
            ]
        ).strip()
        stage = Path(stage_text)
        if (
            not stage.is_absolute()
            or stage.parent != self.paths.staging_root
            or not stage.name.startswith("caplab-venv.")
            or stage.is_symlink()
            or not stage.is_dir()
        ):
            raise HostctlError("mktemp returned an invalid venv stage path")
        try:
            self.runner.run(["/usr/bin/python3", "-m", "venv", str(stage)])
            python = stage / "bin/python"
            staged_lock = stage / "caplab-requirements.lock"
            self._write_regular_file(staged_lock, lock_bytes, 0o600)
            self.runner.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--require-hashes",
                    "--only-binary=:all:",
                    "--requirement",
                    str(staged_lock),
                ]
            )
            try:
                staged_lock.unlink()
            except OSError as error:
                raise HostctlError("cannot remove the staged runtime lock") from error
            self.runner.run([str(python), "-m", "pip", "check"])
            interpreter_version = self.runner.run([str(python), "--version"]).strip()
            if re.fullmatch(r"Python 3\.12(?:\.[0-9]+)?", interpreter_version) is None:
                raise HostctlError("isolated runtime interpreter is not Python 3.12")
            purelib_text = self.runner.run(
                [
                    "/usr/bin/env",
                    "-i",
                    "PYTHONNOUSERSITE=1",
                    "PYTHONDONTWRITEBYTECODE=1",
                    str(python),
                    "-I",
                    "-c",
                    "import sysconfig; print(sysconfig.get_path('purelib'))",
                ]
            ).strip()
            purelib = Path(purelib_text)
            if (
                not purelib.is_absolute()
                or not purelib.is_relative_to(stage)
                or purelib.is_symlink()
                or not purelib.is_dir()
            ):
                raise HostctlError("venv returned an invalid package directory")
            source_tree_hash = self._install_pinned_package(
                pinned_files,
                source_commit,
                lock_bytes,
                purelib,
            )
            self.runner.run(
                [
                    "/usr/bin/env",
                    "-i",
                    "PYTHONNOUSERSITE=1",
                    "PYTHONDONTWRITEBYTECODE=1",
                    str(python),
                    "-I",
                    "-c",
                    "import caplab.runtime; "
                    "from importlib.resources import files; "
                    "r=files('caplab.runtime'); "
                    "assert r.joinpath('requirements.lock').is_file(); "
                    "assert r.joinpath('migrations/0001_runtime_core.sql').is_file()",
                ]
            )
        except HostctlError as operation_error:
            try:
                self._remove_venv_stage(stage)
            except HostctlError as cleanup_error:
                raise HostctlError(
                    "venv build failed and stage cleanup did not complete"
                ) from cleanup_error
            raise operation_error
        return stage, source_tree_hash, interpreter_version

    def _install_pinned_package(
        self,
        pinned_files: list[PinnedFile],
        source_commit: str,
        lock_bytes: bytes,
        purelib: Path,
    ) -> str:
        source_manifest = self._pinned_source_manifest(pinned_files, source_commit)
        manifest_paths = {entry["path"] for entry in source_manifest["files"]}
        if (
            "runtime/requirements.lock" not in manifest_paths
            or "runtime/migrations/0001_runtime_core.sql" not in manifest_paths
        ):
            raise HostctlError("source package lacks the frozen runtime data")
        destination = purelib / "caplab"
        if destination.exists() or destination.is_symlink():
            raise HostctlError("venv already contains a CAPLAB package")
        try:
            destination.mkdir(mode=0o755)
            for pinned_file in pinned_files:
                target = destination / pinned_file.path
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                mode = 0o755 if pinned_file.mode == "100755" else 0o644
                self._write_regular_file(target, pinned_file.payload, mode)
        except OSError as error:
            raise HostctlError("cannot copy the pinned CAPLAB package") from error
        installed_manifest = self._source_tree_manifest(destination)
        if installed_manifest["files"] != self._installed_projection(source_manifest):
            raise HostctlError("installed CAPLAB package differs from the pinned source")
        try:
            installed_lock = (destination / "runtime/requirements.lock").read_bytes()
        except OSError as error:
            raise HostctlError("cannot verify the installed CAPLAB runtime lock") from error
        if installed_lock != lock_bytes:
            raise HostctlError("installed CAPLAB runtime lock differs from its source")
        manifest_bytes = (
            json.dumps(source_manifest, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_path = purelib / "caplab-source-manifest.json"
        try:
            descriptor = os.open(
                manifest_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            try:
                _write_all(descriptor, manifest_bytes)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError as error:
            raise HostctlError("cannot persist the CAPLAB source manifest") from error
        return manifest_hash

    def _read_pinned_git_package(
        self,
        source_repo: Path,
        source_commit: str,
    ) -> list[PinnedFile]:
        listing = self.runner.run(
            _git_command(
                source_repo,
                "ls-tree",
                "-r",
                "-z",
                "--full-tree",
                source_commit,
                "--",
                "src/caplab",
            )
        )
        files: list[PinnedFile] = []
        seen: set[str] = set()
        for record in listing.split("\0"):
            if not record:
                continue
            try:
                metadata, tree_path = record.split("\t", 1)
                mode, object_type, git_object = metadata.split(" ", 2)
            except ValueError as error:
                raise HostctlError("pinned CAPLAB Git tree is malformed") from error
            prefix = "src/caplab/"
            if object_type != "blob" or mode not in {"100644", "100755"}:
                raise HostctlError("pinned CAPLAB Git tree contains a non-regular file")
            if not tree_path.startswith(prefix):
                raise HostctlError("pinned CAPLAB Git tree escaped its source root")
            relative = tree_path.removeprefix(prefix)
            pure_path = PurePosixPath(relative)
            if (
                not relative
                or pure_path.is_absolute()
                or ".." in pure_path.parts
                or "." in pure_path.parts
                or relative in seen
                or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", git_object) is None
            ):
                raise HostctlError("pinned CAPLAB Git tree has an unsafe path or object")
            payload_text = self.runner.run(
                _git_command(source_repo, "cat-file", "blob", git_object)
            )
            verified_object = self.runner.run(
                _git_command(source_repo, "hash-object", "--stdin"),
                input_text=payload_text,
            ).strip()
            if verified_object != git_object:
                raise HostctlError("pinned CAPLAB Git blob changed during materialization")
            seen.add(relative)
            files.append(
                PinnedFile(
                    path=relative,
                    mode=mode,
                    git_object=git_object,
                    payload=payload_text.encode("utf-8"),
                )
            )
        if not files:
            raise HostctlError("pinned CAPLAB Git tree is empty")
        return sorted(files, key=lambda entry: entry.path)

    @staticmethod
    def _pinned_payload(pinned_files: list[PinnedFile], path: str) -> bytes:
        matches = [entry.payload for entry in pinned_files if entry.path == path]
        if len(matches) != 1:
            raise HostctlError(f"pinned CAPLAB package lacks exactly one {path}")
        return matches[0]

    @staticmethod
    def _pinned_source_manifest(
        pinned_files: list[PinnedFile],
        source_commit: str,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "source_commit": source_commit,
            "files": [
                {
                    "path": entry.path,
                    "mode": entry.mode,
                    "git_object": entry.git_object,
                    "bytes": len(entry.payload),
                    "sha256": hashlib.sha256(entry.payload).hexdigest(),
                }
                for entry in pinned_files
            ],
        }

    @staticmethod
    def _installed_projection(source_manifest: dict[str, object]) -> list[dict[str, object]]:
        files = source_manifest.get("files")
        if not isinstance(files, list):
            raise HostctlError("pinned CAPLAB source manifest is invalid")
        projected: list[dict[str, object]] = []
        for entry in files:
            if (
                not isinstance(entry, dict)
                or set(entry) != {"path", "mode", "git_object", "bytes", "sha256"}
                or not isinstance(entry.get("path"), str)
                or entry.get("mode") not in {"100644", "100755"}
                or not isinstance(entry.get("bytes"), int)
                or re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256"))) is None
                or re.fullmatch(
                    r"[0-9a-f]{40}|[0-9a-f]{64}",
                    str(entry.get("git_object")),
                )
                is None
            ):
                raise HostctlError("pinned CAPLAB source manifest is invalid")
            projected.append(
                {
                    "path": entry["path"],
                    "mode": entry["mode"],
                    "bytes": entry["bytes"],
                    "sha256": entry["sha256"],
                }
            )
        return projected

    @staticmethod
    def _source_tree_manifest(source_package: Path) -> dict[str, object]:
        if (
            not source_package.is_absolute()
            or source_package.is_symlink()
            or not source_package.is_dir()
        ):
            raise HostctlError("pinned CAPLAB source package is not a plain directory")
        files: list[dict[str, object]] = []
        for path in sorted(source_package.rglob("*")):
            relative = path.relative_to(source_package)
            if path.is_symlink():
                raise HostctlError("source package contains a symlink")
            if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            if path.is_dir():
                continue
            if not path.is_file():
                raise HostctlError("source package contains an unsupported entry")
            try:
                payload = path.read_bytes()
            except OSError as error:
                raise HostctlError("cannot read the pinned CAPLAB source package") from error
            files.append(
                {
                    "path": relative.as_posix(),
                    "mode": "100755" if stat.S_IMODE(path.stat().st_mode) & 0o111 else "100644",
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        if not files:
            raise HostctlError("pinned CAPLAB source package is empty")
        return {"schema_version": 1, "files": files}

    @staticmethod
    def _write_regular_file(path: Path, payload: bytes, mode: int) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, mode)
            try:
                _write_all(descriptor, payload)
                os.fchmod(descriptor, mode)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError as error:
            raise HostctlError(f"cannot materialize pinned file: {path.name}") from error

    def _remove_venv_stage(self, stage: Path) -> None:
        if not stage.exists() and not stage.is_symlink():
            return
        if (
            not stage.is_absolute()
            or stage.parent != self.paths.staging_root
            or not stage.name.startswith("caplab-venv.")
            or stage.is_symlink()
            or not stage.is_dir()
        ):
            raise HostctlError("refusing to remove an unexpected venv stage")
        try:
            shutil.rmtree(stage)
        except OSError as error:
            raise HostctlError("could not remove the failed venv stage") from error

    def _run_bootstrap_step(
        self,
        state: dict[str, object],
        name: str,
        effects: tuple[str, ...],
        operation: Callable[[dict[str, object]], None],
    ) -> None:
        resource_steps = state.get("resource_steps")
        created_resources = state.get("created_resources")
        resource_effects = state.get("resource_effects")
        if (
            not isinstance(resource_steps, dict)
            or not isinstance(created_resources, dict)
            or not isinstance(resource_effects, dict)
        ):
            raise HostctlError("bootstrap resource journal is invalid")
        if name in resource_steps or any(effect in resource_effects for effect in effects):
            raise HostctlError(f"bootstrap resource step was already attempted: {name}")
        resource_steps[name] = "started"
        resource_effects.update({effect: "planned" for effect in effects})
        write_state(self.paths.state_file, state)
        operation(state)
        if any(resource_effects.get(effect) != "complete" for effect in effects):
            raise HostctlError(f"bootstrap resource effects are incomplete: {name}")
        resource_steps[name] = "complete"
        created_resources[name] = True
        write_state(self.paths.state_file, state)

    def _complete_bootstrap_effect(self, state: dict[str, object], effect: str) -> None:
        resource_effects = state.get("resource_effects")
        if not isinstance(resource_effects, dict) or resource_effects.get(effect) != "planned":
            raise HostctlError(f"bootstrap effect was not durably planned: {effect}")
        resource_effects[effect] = "complete"
        write_state(self.paths.state_file, state)

    def _create_common_group_and_etc_root(self, state: dict[str, object]) -> None:
        self.runner.run(["groupadd", "--system", "caplab"])
        self._complete_bootstrap_effect(state, "os_group:caplab")
        self.runner.run(
            [
                "install",
                "-d",
                "-o",
                "root",
                "-g",
                "caplab",
                "-m",
                "0750",
                str(self.paths.etc_root),
            ]
        )
        self._complete_bootstrap_effect(state, "path:etc_root")

    def _rollback_partial_bootstrap(self, state: dict[str, object]) -> list[str]:
        """Best-effort removal of only journaled pre-effect namespaces."""

        resource_steps = state.get("resource_steps")
        if not isinstance(resource_steps, dict) or state.get("effects_armed") is not False:
            return ["resource_journal"]
        failures: list[str] = []

        def attempted(name: str) -> bool:
            return resource_steps.get(name) in {"started", "complete"}

        def try_operation(name: str, operation: Callable[[], None]) -> None:
            try:
                operation()
            except (HostctlError, OSError):
                failures.append(name)

        if attempted("garage_bucket"):
            try_operation("garage_bucket", self._remove_partial_garage_bucket)
        if attempted("postgres"):
            try_operation("postgres", self._remove_partial_postgres_namespace)
        if attempted("host_paths"):
            try_operation("host_paths", self._remove_partial_host_paths)
        if attempted("runtime_identities"):
            try_operation("runtime_identities", self._remove_partial_runtime_identities)
        if attempted("common_group"):
            if self.paths.etc_root.exists() or self.paths.etc_root.is_symlink():
                try_operation(
                    "etc_root",
                    lambda: self._remove_bootstrap_tree(self.paths.etc_root),
                )
            try_operation(
                "common_group",
                lambda: self.runner.run(
                    ["groupdel", "caplab"],
                    allowed_returncodes=(0, 6),
                ),
            )
        return failures

    def _remove_partial_garage_bucket(self) -> None:
        buckets = _json_list(
            self.runner.run(["garage", "json-api", "ListBuckets", "null"]),
            "Garage returned an invalid bucket list during rollback",
        )
        exists = any(
            isinstance(bucket, dict) and GARAGE_BUCKET in bucket.get("globalAliases", [])
            for bucket in buckets
        )
        if not exists:
            return
        self._assert_garage_bucket_empty()
        self.runner.run(["garage", "bucket", "delete", "--yes", GARAGE_BUCKET])

    def _remove_partial_postgres_namespace(self) -> None:
        database_state = self.runner.run(
            self._postgres_query_command(
                "postgres",
                "SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_database "
                "WHERE datname = 'caplab') THEN 'present' ELSE 'absent' END;",
            )
        ).strip()
        if database_state not in {"present", "absent"}:
            raise HostctlError("PostgreSQL returned an invalid rollback namespace state")
        if database_state == "present":
            self._assert_postgres_application_empty()
            self.runner.run(["runuser", "--user", "postgres", "--", "dropdb", "caplab"])
        self.runner.run(
            self._postgres_command(
                "postgres",
                "DROP ROLE IF EXISTS caplab_writer; "
                "DROP ROLE IF EXISTS caplab_reader; "
                "DROP ROLE IF EXISTS caplab_verifier; "
                "DROP ROLE IF EXISTS caplab_owner;",
            )
        )

    def _remove_partial_host_paths(self) -> None:
        for path in (self.paths.nvr_root, self.paths.venv_root, self.paths.etc_root):
            if not path.exists() and not path.is_symlink():
                continue
            if path == self.paths.nvr_root:
                self._assert_nvr_empty()
            self._remove_bootstrap_tree(path)
        for parent in (self.paths.nvr_root.parent, self.paths.venv_root.parent):
            if not parent.exists() and not parent.is_symlink():
                continue
            self._remove_empty_bootstrap_directory(parent)

    def _remove_partial_runtime_identities(self) -> None:
        for role in RUNTIME_ROLES:
            self.runner.run(["userdel", role], allowed_returncodes=(0, 6))
        for role in RUNTIME_ROLES:
            self.runner.run(["groupdel", role], allowed_returncodes=(0, 6))

    def _create_runtime_identities(self, state: dict[str, object]) -> None:
        for role in RUNTIME_ROLES:
            self.runner.run(["groupadd", "--system", role])
            self._complete_bootstrap_effect(state, f"os_group:{role}")
            self.runner.run(
                [
                    "useradd",
                    "--system",
                    "--gid",
                    role,
                    "--groups",
                    "caplab",
                    "--home-dir",
                    "/nonexistent",
                    "--no-create-home",
                    "--shell",
                    "/usr/sbin/nologin",
                    role,
                ]
            )
            self._complete_bootstrap_effect(state, f"os_user:{role}")

    def _install_base_paths(
        self,
        source_pin: Path,
        runtime_config: Path,
        stage: Path,
        lock_hash: str,
        state: dict[str, object],
    ) -> None:
        self.runner.run(
            [
                "install",
                "-o",
                "root",
                "-g",
                "caplab",
                "-m",
                "0640",
                str(source_pin),
                str(self.paths.etc_root / "SOURCE_COMMIT"),
            ]
        )
        self._complete_bootstrap_effect(state, "file:source_pin")
        self.runner.run(
            [
                "install",
                "-o",
                "root",
                "-g",
                "caplab",
                "-m",
                "0640",
                str(runtime_config),
                str(self.paths.etc_root / "runtime.toml"),
            ]
        )
        self._complete_bootstrap_effect(state, "file:runtime_config")
        self.runner.run(
            [
                "/usr/bin/setfacl",
                "--modify",
                "user:postgres:--x",
                str(self.paths.etc_root),
            ]
        )
        self.runner.run(
            [
                "/usr/bin/setfacl",
                "--modify",
                "user:postgres:r--",
                str(self.paths.etc_root / "runtime.toml"),
            ]
        )
        self._complete_bootstrap_effect(state, "acl:postgres_config")
        self.runner.run(
            [
                "install",
                "-d",
                "-o",
                "root",
                "-g",
                "caplab",
                "-m",
                "0750",
                str(self.paths.credential_root),
                str(self.paths.venv_root.parent),
                str(self.paths.venv_root),
            ]
        )
        self._complete_bootstrap_effect(state, "path:credential_root")
        self._complete_bootstrap_effect(state, "path:venv_root")
        for directory in (self.paths.venv_root.parent, self.paths.venv_root):
            self.runner.run(
                [
                    "/usr/bin/setfacl",
                    "--modify",
                    "user:postgres:--x",
                    str(directory),
                ]
            )
        self._complete_bootstrap_effect(state, "acl:postgres_venv_traversal")
        for role in RUNTIME_ROLES:
            self.runner.run(
                [
                    "install",
                    "-d",
                    "-o",
                    "root",
                    "-g",
                    role,
                    "-m",
                    "0750",
                    str(self.paths.credential_root / role),
                ]
            )
        self._complete_bootstrap_effect(state, "paths:role_credentials")
        self.runner.run(
            [
                "install",
                "-d",
                "-o",
                "root",
                "-g",
                "caplab",
                "-m",
                "0750",
                str(self.paths.nvr_root.parent),
            ]
        )
        self._complete_bootstrap_effect(state, "path:nvr_parent")
        self.runner.run(
            [
                "install",
                "-d",
                "-o",
                "caplab_writer",
                "-g",
                "caplab",
                "-m",
                "0750",
                str(self.paths.nvr_root),
            ]
        )
        self._complete_bootstrap_effect(state, "path:nvr_root")
        self.runner.run(["chown", "-R", "root:caplab", str(stage)])
        self.runner.run(["chmod", "-R", "u=rwX,g=rX,o=", str(stage)])
        environment = self.paths.venv_root / lock_hash
        self.runner.run(["mv", str(stage), str(environment)])
        self._complete_bootstrap_effect(state, "path:venv_environment")
        self.runner.run(
            [
                "/usr/bin/setfacl",
                "--physical",
                "--recursive",
                "--modify",
                "user:postgres:rX",
                str(environment),
            ]
        )
        self._complete_bootstrap_effect(state, "acl:postgres_venv_read")

    def _create_postgres_namespace(self, state: dict[str, object]) -> None:
        role_sql = (
            "CREATE ROLE caplab_owner NOLOGIN NOSUPERUSER NOCREATEDB "
            "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS; "
            "CREATE ROLE caplab_writer NOLOGIN NOSUPERUSER NOCREATEDB "
            "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD NULL; "
            "CREATE ROLE caplab_reader NOLOGIN NOSUPERUSER NOCREATEDB "
            "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD NULL; "
            "CREATE ROLE caplab_verifier NOLOGIN NOSUPERUSER NOCREATEDB "
            "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD NULL;"
        )
        self.runner.run(self._postgres_command("postgres", role_sql))
        self._complete_bootstrap_effect(state, "postgres:roles")
        self.runner.run(
            [
                "runuser",
                "--user",
                "postgres",
                "--",
                "createdb",
                "--owner=caplab_owner",
                "--encoding=UTF8",
                "--template=template0",
                "caplab",
            ]
        )
        self._complete_bootstrap_effect(state, "postgres:database")
        database_sql = (
            "REVOKE ALL ON DATABASE caplab FROM PUBLIC; "
            "GRANT CONNECT ON DATABASE caplab TO caplab_writer, caplab_reader, "
            "caplab_verifier; "
            "ALTER ROLE caplab_writer IN DATABASE caplab SET search_path "
            "TO caplab_v0, pg_catalog; "
            "ALTER ROLE caplab_reader IN DATABASE caplab SET search_path "
            "TO caplab_v0, pg_catalog; "
            "ALTER ROLE caplab_verifier IN DATABASE caplab SET search_path "
            "TO caplab_v0, pg_catalog;"
        )
        self.runner.run(self._postgres_command("postgres", database_sql))
        self._complete_bootstrap_effect(state, "postgres:database_acl")

    @staticmethod
    def _postgres_command(database: str, sql: str) -> list[str]:
        return [
            "runuser",
            "--user",
            "postgres",
            "--",
            "psql",
            "-X",
            "--set",
            "ON_ERROR_STOP=1",
            "--dbname",
            database,
            "--command",
            sql,
        ]

    @staticmethod
    def _postgres_query_command(database: str, sql: str) -> list[str]:
        command = HostController._postgres_command(database, sql)
        command[8:8] = ["--tuples-only", "--no-align"]
        return command

    def _create_garage_bucket(self, state: dict[str, object]) -> None:
        self.runner.run(["garage", "bucket", "create", GARAGE_BUCKET])
        self._complete_bootstrap_effect(state, "garage:bucket")
        self.runner.run(
            [
                "garage",
                "bucket",
                "set-quotas",
                "--max-size",
                "1GiB",
                "--max-objects",
                "10000",
                GARAGE_BUCKET,
            ]
        )
        self._complete_bootstrap_effect(state, "garage:quota")

    def issue_credentials(self) -> None:
        state = read_state(self.paths.state_file)
        if state.get("phase") != "base" or state.get("effects_armed") is not False:
            raise HostctlError("campaign must be at the base phase before key issue")
        if state.get("garage_keys") != []:
            raise HostctlError("campaign state already records Garage keys")
        if (
            self.runner.run(["systemctl", "is-enabled", "caplab-p4-expiry.timer"]).strip()
            != "enabled"
        ):
            raise HostctlError("campaign expiry timer is not enabled")
        if (
            self.runner.run(["systemctl", "is-active", "caplab-p4-expiry.timer"]).strip()
            != "active"
        ):
            raise HostctlError("campaign expiry timer is not active")

        now = self.clock()
        require_active_authorization(now)
        seconds_to_expiry = int((AUTHORIZATION_EXPIRES_AT - now).total_seconds())
        planned_keys = [
            {
                "role": role,
                "alias": KEY_ALIASES[role],
                "access_key_id": None,
                "expires_at": AUTHORIZATION_EXPIRES_AT.isoformat().replace("+00:00", "Z"),
            }
            for role in RUNTIME_ROLES
        ]
        state["garage_keys"] = planned_keys
        write_state(self.paths.state_file, state)

        try:
            for planned_key in planned_keys:
                role = str(planned_key["role"])
                alias = str(planned_key["alias"])
                self.runner.run(
                    [
                        "garage",
                        "key",
                        "create",
                        "--expires-in",
                        f"{seconds_to_expiry}s",
                        alias,
                    ],
                    secret_output=True,
                )
                key_record = self._read_secret_key(alias)
                access_key_id = key_record["access_key_id"]
                self._grant_bucket(role, access_key_id)
                self._write_credential(
                    role,
                    access_key_id,
                    key_record["secret_access_key"],
                )
                planned_key["access_key_id"] = access_key_id
                write_state(self.paths.state_file, state)

            self.runner.run(
                [
                    "runuser",
                    "--user",
                    "postgres",
                    "--",
                    "psql",
                    "-X",
                    "--set",
                    "ON_ERROR_STOP=1",
                    "--dbname",
                    "postgres",
                    "--command",
                    "ALTER ROLE caplab_writer LOGIN; "
                    "ALTER ROLE caplab_reader LOGIN; "
                    "ALTER ROLE caplab_verifier LOGIN;",
                ]
            )
            state["phase"] = "ready"
            write_state(self.paths.state_file, state)
        except HostctlError:
            try:
                self.disable_access()
            except HostctlError as cleanup_error:
                raise HostctlError(
                    "credential issue failed and access disable did not complete"
                ) from cleanup_error
            raise

    def disable_access(self) -> None:
        failures: list[str] = []
        results: dict[str, str] = {}
        try:
            state: dict[str, object] | None = read_state(self.paths.state_file)
        except HostctlError:
            state = None
            failures.append("state_read")
            results["state_read"] = "failed"

        if state is not None and state.get("phase") == "rollback_complete":
            expected_rollback = {
                "garage_bucket": "complete",
                "postgres": "complete",
                "host_paths": "complete",
                "runtime_identities": "complete",
                "common_group": "complete",
            }
            if (
                state.get("effects_armed") is not False
                or state.get("rollback_steps") != expected_rollback
            ):
                raise HostctlError("completed rollback state is invalid")
            return

        def attempt(name: str, operation: Callable[[], None]) -> None:
            try:
                operation()
            except (HostctlError, OSError):
                failures.append(name)
                results[name] = "failed"
            else:
                results[name] = "complete"

        attempt(
            "postgres",
            lambda: self.runner.run(
                [
                    "runuser",
                    "--user",
                    "postgres",
                    "--",
                    "psql",
                    "-X",
                    "--set",
                    "ON_ERROR_STOP=1",
                    "--dbname",
                    "postgres",
                    "--command",
                    "ALTER ROLE caplab_writer NOLOGIN; "
                    "ALTER ROLE caplab_reader NOLOGIN; "
                    "ALTER ROLE caplab_verifier NOLOGIN; "
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE usename IN ('caplab_writer','caplab_reader','caplab_verifier') "
                    "AND pid <> pg_backend_pid();",
                ]
            ),
        )
        for role in RUNTIME_ROLES:
            attempt(
                f"process:{role}",
                lambda role=role: self.runner.run(
                    ["pkill", "--signal", "KILL", "--uid", role],
                    allowed_returncodes=(0, 1),
                ),
            )
        recorded_key_ids: set[str] = set()
        if state is not None:
            _recorded_keys, recorded_key_ids, records_valid = self._recorded_campaign_keys(state)
            if records_valid:
                results["garage_key_state_inventory"] = "complete"
            else:
                failures.append("garage_key_state_inventory")
                results["garage_key_state_inventory"] = "failed"
        try:
            live_key_ids, alias_key_ids = self._garage_key_inventory()
        except HostctlError:
            key_ids_to_delete = recorded_key_ids
            failures.append("garage_key_inventory")
            results["garage_key_inventory"] = "failed"
        else:
            key_ids_to_delete = (recorded_key_ids & live_key_ids) | alias_key_ids
            results["garage_key_inventory"] = "complete"
        for access_key_id in sorted(key_ids_to_delete):
            attempt(
                f"garage_key:{access_key_id}",
                lambda access_key_id=access_key_id: self.runner.run(
                    ["garage", "key", "delete", "--yes", access_key_id],
                    secret_output=True,
                ),
            )
        for role in RUNTIME_ROLES:
            credential_file = self.paths.credential_root / role / "garage.json"

            def remove_credential(path: Path = credential_file) -> None:
                try:
                    path.unlink()
                except FileNotFoundError:
                    return
                except OSError as error:
                    raise HostctlError("cannot remove a campaign credential file") from error

            attempt(f"credential:{role}", remove_credential)
            attempt(
                f"os_account:{role}",
                lambda role=role: self.runner.run(["usermod", "--lock", "--expiredate", "1", role]),
            )
        if state is not None:
            state["disable_results"] = results
            state["disable_attempted_at"] = self.clock().isoformat().replace("+00:00", "Z")
            state["phase"] = "disabled" if not failures else "disable_incomplete"
            if not failures:
                state["disabled_at"] = state["disable_attempted_at"]
            write_state(self.paths.state_file, state)
        if failures:
            raise HostctlError("campaign access disablement is incomplete: " + ",".join(failures))

    def rollback_empty(self) -> None:
        state = read_state(self.paths.state_file)
        if state.get("effects_armed") is True:
            raise HostctlError("synthetic-effect boundary is armed; disable and quarantine instead")
        require_active_authorization(self.clock())
        if state.get("phase") in {
            "bootstrapping",
            "bootstrap_failed",
            "bootstrap_cleanup_failed",
        }:
            failures = self._rollback_partial_bootstrap(state)
            state["bootstrap_cleanup_failures"] = failures
            state["phase"] = "bootstrap_rolled_back" if not failures else "bootstrap_cleanup_failed"
            write_state(self.paths.state_file, state)
            if failures:
                raise HostctlError(
                    "partial bootstrap rollback is incomplete: " + ",".join(failures)
                )
            return
        if state.get("phase") not in {"disabled", "rollback_started"}:
            raise HostctlError("campaign access must be disabled before empty rollback")
        expected_resources = {
            "common_group": True,
            "runtime_identities": True,
            "host_paths": True,
            "venv": True,
            "postgres": True,
            "garage_bucket": True,
        }
        if state.get("created_resources") != expected_resources:
            raise HostctlError("created-resource identity is incomplete or ambiguous")
        if state.get("phase") == "disabled":
            self._assert_garage_bucket_empty()
            self._assert_postgres_application_empty()
            self._assert_nvr_empty()
            state["phase"] = "rollback_started"
            state["rollback_steps"] = {}
            write_state(self.paths.state_file, state)

        self._run_rollback_step(
            state,
            "garage_bucket",
            self._remove_partial_garage_bucket,
        )
        self._run_rollback_step(
            state,
            "postgres",
            self._remove_partial_postgres_namespace,
        )
        self._run_rollback_step(
            state,
            "host_paths",
            self._remove_partial_host_paths,
        )
        self._run_rollback_step(
            state,
            "runtime_identities",
            self._remove_partial_runtime_identities,
        )
        self._run_rollback_step(
            state,
            "common_group",
            lambda: self.runner.run(
                ["groupdel", "caplab"],
                allowed_returncodes=(0, 6),
            ),
        )
        state["phase"] = "rollback_complete"
        state["rollback_completed_at"] = self.clock().isoformat().replace("+00:00", "Z")
        write_state(self.paths.state_file, state)

    def _run_rollback_step(
        self,
        state: dict[str, object],
        name: str,
        operation: Callable[[], None],
    ) -> None:
        rollback_steps = state.get("rollback_steps")
        if not isinstance(rollback_steps, dict):
            raise HostctlError("empty rollback journal is invalid")
        if rollback_steps.get(name) == "complete":
            return
        rollback_steps[name] = "started"
        write_state(self.paths.state_file, state)
        operation()
        rollback_steps[name] = "complete"
        write_state(self.paths.state_file, state)

    def capture_inventory(self, label: str) -> None:
        if label not in INVENTORY_LABELS:
            raise HostctlError("inventory label is outside the P4 sequence")
        require_active_authorization(self.clock())
        state = read_state(self.paths.state_file)
        if state.get("phase") != "armed" or state.get("effects_armed") is not True:
            raise HostctlError("store inventory requires the armed P4 phase")
        inventories = state.get("inventories")
        if not isinstance(inventories, dict):
            raise HostctlError("campaign state lacks the inventory ledger")
        if label in inventories:
            raise HostctlError(f"inventory label is already recorded: {label}")

        snapshot = {
            "captured_at": self.clock().isoformat().replace("+00:00", "Z"),
            "garage": self._capture_garage_inventory(state),
            "nvr": self._capture_nvr_inventory(),
            "postgres": self._capture_postgres_inventory(),
        }
        inventories[label] = snapshot
        write_state(self.paths.state_file, state)
        self._validate_inventory_sequence(state, label)

    def _capture_garage_inventory(self, state: dict[str, object]) -> dict[str, object]:
        bucket = self._garage_bucket_info()
        counters: dict[str, int] = {}
        for field in (
            "objects",
            "bytes",
            "unfinishedUploads",
            "unfinishedMultipartUploads",
        ):
            value = bucket.get(field)
            if type(value) is not int or value < 0:
                raise HostctlError("Garage returned an invalid bucket counter")
            counters[field] = value

        live_keys = _json_list(
            self.runner.run(["garage", "json-api", "ListKeys", "null"]),
            "Garage returned an invalid key list",
        )
        live_campaign_keys: dict[str, str] = {}
        for key in live_keys:
            if not isinstance(key, dict) or key.get("name") not in set(KEY_ALIASES.values()):
                continue
            alias = key.get("name")
            access_key_id = key.get("id")
            if (
                not isinstance(alias, str)
                or alias in live_campaign_keys
                or not isinstance(access_key_id, str)
                or not access_key_id.startswith("GK")
            ):
                raise HostctlError("Garage returned an invalid campaign key record")
            live_campaign_keys[alias] = access_key_id

        recorded_keys = state.get("garage_keys")
        if not isinstance(recorded_keys, list):
            raise HostctlError("campaign state lacks Garage key identities")
        expected_keys: dict[str, str] = {}
        for key in recorded_keys:
            if not isinstance(key, dict):
                raise HostctlError("campaign state has an invalid Garage key record")
            role = key.get("role")
            alias = key.get("alias")
            access_key_id = key.get("access_key_id")
            if (
                not isinstance(role, str)
                or role not in RUNTIME_ROLES
                or alias != KEY_ALIASES[role]
                or not isinstance(access_key_id, str)
                or not access_key_id.startswith("GK")
                or alias in expected_keys
            ):
                raise HostctlError("campaign state has an invalid Garage key record")
            expected_keys[str(alias)] = access_key_id
        if live_campaign_keys != expected_keys:
            raise HostctlError("Garage campaign-key state is wrong")
        return {**counters, "keys": dict(sorted(live_campaign_keys.items()))}

    def _capture_postgres_inventory(self) -> dict[str, int]:
        branches = [
            f"SELECT '{table}'::text AS table_name, count(*)::bigint AS row_count "
            f"FROM caplab_v0.{table}"
            for table in POSTGRES_TABLES
        ]
        query = (
            "SELECT table_name || ':' || row_count FROM ("
            + " UNION ALL ".join(branches)
            + ") AS inventory ORDER BY table_name;"
        )
        rows = self.runner.run(self._postgres_query_command("caplab", query)).splitlines()
        counts: dict[str, int] = {}
        for row in rows:
            try:
                table, count_text = row.split(":", 1)
                count = int(count_text)
            except (ValueError, TypeError) as error:
                raise HostctlError("PostgreSQL returned an invalid inventory") from error
            if table in counts or table not in POSTGRES_TABLES or count < 0:
                raise HostctlError("PostgreSQL returned an invalid inventory")
            counts[table] = count
        if set(counts) != set(POSTGRES_TABLES):
            raise HostctlError("PostgreSQL returned an incomplete inventory")
        return dict(sorted(counts.items()))

    def _capture_nvr_inventory(self) -> dict[str, object]:
        self._verify_nvr_root()
        common_gid = self.group_resolver("caplab")
        directories: list[str] = []
        files: list[dict[str, object]] = []
        for path in sorted(self.paths.nvr_root.rglob("*")):
            relative = path.relative_to(self.paths.nvr_root).as_posix()
            try:
                metadata = path.lstat()
            except OSError as error:
                raise HostctlError("cannot inspect the NVR inventory") from error
            if stat.S_ISDIR(metadata.st_mode) and not path.is_symlink():
                if stat.S_IMODE(metadata.st_mode) != 0o750 or metadata.st_gid != common_gid:
                    raise HostctlError("NVR directory ownership or mode is wrong")
                directories.append(relative)
                continue
            if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
                raise HostctlError("NVR inventory contains an unsupported entry")
            if stat.S_IMODE(metadata.st_mode) != 0o440 or metadata.st_gid != common_gid:
                raise HostctlError("NVR file ownership or mode is wrong")
            files.append(self._inventory_file(path, relative))
        return {"directories": directories, "files": files}

    @staticmethod
    def _inventory_file(path: Path, relative: str) -> dict[str, object]:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
                byte_count = os.fstat(stream.fileno()).st_size
        except OSError as error:
            raise HostctlError("cannot hash an NVR inventory file") from error
        return {"path": relative, "bytes": byte_count, "sha256": digest}

    def _validate_inventory_sequence(self, state: dict[str, object], label: str) -> None:
        inventories = state["inventories"]
        if not isinstance(inventories, dict):
            raise HostctlError("campaign state lacks the inventory ledger")
        checks = state.setdefault("inventory_checks", {})
        if not isinstance(checks, dict):
            raise HostctlError("campaign state has an invalid inventory-check ledger")
        if label == "before-register":
            return
        if label == "after-first-register":
            before = inventories.get("before-register")
            after_first = inventories[label]
            if not self._single_effect_inventory(before, after_first):
                raise HostctlError("first registration did not add exactly one store effect")
            checks["first_register_single_effect"] = True
            write_state(self.paths.state_file, state)
            return
        after_first = inventories.get("after-first-register")
        if label == "after-replay":
            after_replay = inventories[label]
            if not self._same_store_inventory(after_first, after_replay):
                raise HostctlError("idempotent replay changed the store inventory")
            checks["replay_added_no_effect"] = True
            write_state(self.paths.state_file, state)
            return
        after_replay = inventories.get("after-replay")
        after_conflict = inventories[label]
        if not self._same_store_inventory(after_replay, after_conflict):
            raise HostctlError("conflict changed the store inventory")
        checks["conflict_added_no_effect"] = True
        write_state(self.paths.state_file, state)

    @staticmethod
    def _same_store_inventory(first: object, second: object) -> bool:
        if not isinstance(first, dict) or not isinstance(second, dict):
            return False
        return all(first.get(store) == second.get(store) for store in ("garage", "nvr", "postgres"))

    @staticmethod
    def _single_effect_inventory(before: object, after: object) -> bool:
        if not isinstance(before, dict) or not isinstance(after, dict):
            return False
        before_garage = before.get("garage")
        after_garage = after.get("garage")
        before_nvr = before.get("nvr")
        after_nvr = after.get("nvr")
        before_postgres = before.get("postgres")
        after_postgres = after.get("postgres")
        if not all(
            isinstance(item, dict)
            for item in (
                before_garage,
                after_garage,
                before_nvr,
                after_nvr,
                before_postgres,
                after_postgres,
            )
        ):
            return False
        assert isinstance(before_garage, dict)
        assert isinstance(after_garage, dict)
        assert isinstance(before_nvr, dict)
        assert isinstance(after_nvr, dict)
        assert isinstance(before_postgres, dict)
        assert isinstance(after_postgres, dict)
        empty_database = {table: 0 for table in POSTGRES_TABLES}
        empty_database["schema_migrations"] = 1
        registered_database = dict(empty_database)
        for table in (
            "administrations",
            "agent_configurations",
            "artifacts",
            "attempt_artifacts",
            "attempts",
            "manifests",
            "model_identities",
            "operation_requests",
            "registrations",
            "trial_assignments",
            "trial_contexts",
        ):
            registered_database[table] = 1
        # requested, object-verified, local-copy-verified, registered
        registered_database["operation_events"] = 4
        registered_database["audit_events"] = 1
        if (
            before_garage.get("objects") != 0
            or before_garage.get("bytes") != 0
            or before_garage.get("unfinishedUploads") != 0
            or before_garage.get("unfinishedMultipartUploads") != 0
            or before_nvr != {"directories": [], "files": []}
            or before_postgres != empty_database
            or after_postgres != registered_database
            or before_garage.get("keys") != after_garage.get("keys")
            or after_garage.get("objects") != 1
            or after_garage.get("unfinishedUploads") != 0
            or after_garage.get("unfinishedMultipartUploads") != 0
        ):
            return False
        files = after_nvr.get("files")
        if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict):
            return False
        file_record = files[0]
        path = file_record.get("path")
        digest = file_record.get("sha256")
        byte_count = file_record.get("bytes")
        if (
            not isinstance(path, str)
            or not isinstance(digest, str)
            or not isinstance(byte_count, int)
            or path != f"objects/sha256/{digest[:2]}/{digest}"
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or after_garage.get("bytes") != byte_count
        ):
            return False
        return after_nvr.get("directories") == [
            "objects",
            "objects/sha256",
            f"objects/sha256/{digest[:2]}",
        ]

    def verify(self, expected_phase: str) -> None:
        state = read_state(self.paths.state_file)
        if state.get("phase") != expected_phase:
            raise HostctlError(
                f"recorded campaign phase is {state.get('phase')}, not {expected_phase}"
            )
        installed_commit = read_source_commit(self.paths.etc_root / "SOURCE_COMMIT")
        if state.get("source_commit") != installed_commit:
            raise HostctlError("installed source pin differs from campaign state")
        self._validate_runtime_config(self.paths.etc_root / "runtime.toml", installed_commit)
        self._verify_venv(state)
        self.runner.run(
            [
                "runuser",
                "--user",
                "postgres",
                "--",
                "/usr/bin/test",
                "-r",
                str(self.paths.etc_root / "runtime.toml"),
            ]
        )
        if expected_phase == "armed" and state.get("effects_armed") is not True:
            raise HostctlError("armed phase lacks the irreversible effect marker")
        if expected_phase in {"base", "ready"} and state.get("effects_armed") is not False:
            raise HostctlError("pre-effect phase has an armed effect marker")
        self._verify_nvr_root()
        self._verify_os_identity_state(disabled=expected_phase == "disabled")

        role_rows = self.runner.run(
            self._postgres_query_command(
                "postgres",
                "SELECT rolname || ':' || CASE WHEN rolcanlogin THEN 'true' "
                "ELSE 'false' END FROM pg_roles WHERE rolname IN "
                "('caplab_writer','caplab_reader','caplab_verifier');",
            )
        ).splitlines()
        role_login: dict[str, bool] = {}
        for row in role_rows:
            try:
                role, login_text = row.split(":", 1)
            except ValueError as error:
                raise HostctlError("PostgreSQL returned an invalid role record") from error
            role_login[role] = login_text == "true"
        expected_login = expected_phase in {"ready", "armed"}
        if role_login != {role: expected_login for role in RUNTIME_ROLES}:
            raise HostctlError("PostgreSQL peer-role login state is wrong")
        self._verify_postgres_contract(expected_login=expected_login)

        self._verify_garage_bucket()

        live_keys = _json_list(
            self.runner.run(["garage", "json-api", "ListKeys", "null"]),
            "Garage returned an invalid key list",
        )
        campaign_aliases = set(KEY_ALIASES.values())
        live_campaign_keys: dict[str, str] = {}
        live_key_ids: set[str] = set()
        for key in live_keys:
            if not isinstance(key, dict):
                continue
            access_key_id = key.get("id")
            if isinstance(access_key_id, str):
                live_key_ids.add(access_key_id)
            if key.get("name") not in campaign_aliases:
                continue
            alias = str(key["name"])
            if (
                alias in live_campaign_keys
                or not isinstance(access_key_id, str)
                or not access_key_id.startswith("GK")
            ):
                raise HostctlError("Garage returned an invalid campaign key record")
            live_campaign_keys[alias] = access_key_id

        recorded_campaign_keys, recorded_key_ids, _records_valid = self._recorded_campaign_keys(
            state, strict=True
        )
        if expected_phase in {"ready", "armed"}:
            if set(recorded_campaign_keys) != set(KEY_ALIASES.values()):
                raise HostctlError("campaign state lacks exact Garage key identities")
            expected_live_keys = {
                alias: access_key_id
                for alias, (_role, access_key_id) in recorded_campaign_keys.items()
            }
        else:
            expected_live_keys = {}
            if expected_phase == "base" and recorded_key_ids:
                raise HostctlError("base phase unexpectedly records Garage key identities")
        if live_campaign_keys != expected_live_keys:
            raise HostctlError("Garage campaign-key state is wrong")
        if expected_phase == "disabled" and recorded_key_ids & live_key_ids:
            raise HostctlError("a recorded Garage campaign key is still live")
        if expected_phase in {"ready", "armed"}:
            for alias, (role, access_key_id) in recorded_campaign_keys.items():
                self._verify_garage_key(role, alias, access_key_id)

        credentials_expected = expected_phase in {"ready", "armed"}
        for role in RUNTIME_ROLES:
            credential_file = self.paths.credential_root / role / "garage.json"
            if credential_file.exists() != credentials_expected:
                raise HostctlError(f"credential-file state is wrong for {role}")
            if credentials_expected:
                file_stat = credential_file.stat()
                uid, gid = self.identity_resolver(role)
                if file_stat.st_mode & 0o777 != 0o400:
                    raise HostctlError(f"credential-file mode is wrong for {role}")
                if (file_stat.st_uid, file_stat.st_gid) != (uid, gid):
                    raise HostctlError(f"credential-file owner is wrong for {role}")

    def _verify_os_identity_state(self, *, disabled: bool) -> None:
        for role in RUNTIME_ROLES:
            uid, gid = self.identity_resolver(role)
            passwd_fields = self.runner.run(["getent", "passwd", role]).strip().split(":")
            shadow_fields = self.runner.run(["getent", "shadow", role]).strip().split(":")
            if (
                len(passwd_fields) != 7
                or passwd_fields[0] != role
                or passwd_fields[2] != str(uid)
                or passwd_fields[3] != str(gid)
                or passwd_fields[5] != "/nonexistent"
                or passwd_fields[6] != "/usr/sbin/nologin"
                or len(shadow_fields) != 9
                or shadow_fields[0] != role
                or not shadow_fields[1].startswith("!")
                or (disabled and shadow_fields[7] != "1")
                or (not disabled and shadow_fields[7] == "1")
            ):
                raise HostctlError(f"OS account state is wrong for {role}")

    def _verify_venv(self, state: dict[str, object]) -> None:
        lock_hash = state.get("requirements_lock_sha256")
        source_manifest_hash = state.get("source_tree_manifest_sha256")
        if (
            not isinstance(lock_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", lock_hash) is None
            or not isinstance(source_manifest_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", source_manifest_hash) is None
        ):
            raise HostctlError("campaign state lacks the installed runtime identity")

        environment = self.paths.venv_root / lock_hash
        python = environment / "bin/python"
        if environment.is_symlink() or not environment.is_dir() or not python.is_file():
            raise HostctlError("installed CAPLAB virtual environment is missing")
        self.runner.run(
            [
                "runuser",
                "--user",
                "postgres",
                "--",
                "/usr/bin/test",
                "-x",
                str(python),
            ]
        )
        package_roots = list(environment.glob("lib/python*/site-packages"))
        if (
            len(package_roots) != 1
            or package_roots[0].is_symlink()
            or not package_roots[0].is_dir()
        ):
            raise HostctlError("installed CAPLAB package directory is ambiguous")
        package_root = package_roots[0]
        source_manifest_file = package_root / "caplab-source-manifest.json"
        if source_manifest_file.is_symlink() or not source_manifest_file.is_file():
            raise HostctlError("installed CAPLAB source manifest is missing")
        try:
            manifest_bytes = source_manifest_file.read_bytes()
            recorded_manifest = json.loads(manifest_bytes)
        except (OSError, json.JSONDecodeError) as error:
            raise HostctlError("installed CAPLAB source manifest is invalid") from error
        if hashlib.sha256(manifest_bytes).hexdigest() != source_manifest_hash:
            raise HostctlError("installed CAPLAB source manifest identity is wrong")
        if (
            not isinstance(recorded_manifest, dict)
            or recorded_manifest.get("schema_version") != 1
            or recorded_manifest.get("source_commit") != state.get("source_commit")
        ):
            raise HostctlError("installed CAPLAB source manifest provenance is wrong")

        package = package_root / "caplab"
        installed_manifest = self._source_tree_manifest(package)
        if installed_manifest["files"] != self._installed_projection(recorded_manifest):
            raise HostctlError("installed CAPLAB package differs from its manifest")
        manifest_paths = {entry["path"] for entry in installed_manifest["files"]}
        if (
            "runtime/requirements.lock" not in manifest_paths
            or "runtime/migrations/0001_runtime_core.sql" not in manifest_paths
        ):
            raise HostctlError("installed CAPLAB package lacks the frozen runtime data")
        try:
            installed_lock = (package / "runtime/requirements.lock").read_bytes()
        except OSError as error:
            raise HostctlError("cannot read the installed CAPLAB runtime lock") from error
        if hashlib.sha256(installed_lock).hexdigest() != lock_hash:
            raise HostctlError("installed CAPLAB runtime lock identity is wrong")

        self.runner.run(
            [
                "/usr/bin/env",
                "-i",
                "PYTHONNOUSERSITE=1",
                "PYTHONDONTWRITEBYTECODE=1",
                str(python),
                "-I",
                "-c",
                "import caplab.runtime; "
                "from importlib.resources import files; "
                "r=files('caplab.runtime'); "
                "assert r.joinpath('requirements.lock').is_file(); "
                "assert r.joinpath('migrations/0001_runtime_core.sql').is_file()",
            ]
        )

    def _verify_nvr_root(self) -> None:
        try:
            root_stat = self.paths.nvr_root.lstat()
        except OSError as error:
            raise HostctlError("independent-copy root identity is wrong") from error
        writer_uid, _writer_gid = self.identity_resolver("caplab_writer")
        common_gid = self.group_resolver("caplab")
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or self.paths.nvr_root.is_symlink()
            or stat.S_IMODE(root_stat.st_mode) != 0o750
            or root_stat.st_uid != writer_uid
            or root_stat.st_gid != common_gid
        ):
            raise HostctlError("independent-copy root ownership or mode is wrong")

    def _verify_postgres_contract(self, *, expected_login: bool) -> None:
        role_query = (
            "SELECT rolname || ':' || rolcanlogin || ':' || rolsuper || ':' || "
            "rolcreatedb || ':' || rolcreaterole || ':' || rolinherit || ':' || "
            "rolreplication || ':' || rolbypassrls || ':' || (rolpassword IS NULL) || "
            "':' || (rolvaliduntil IS NULL) || ':' || "
            "COALESCE((SELECT string_agg(COALESCE(d.datname,'*') || '=' || "
            "array_to_string(s.setconfig,'|'),';' ORDER BY COALESCE(d.datname,'*')) "
            "FROM pg_db_role_setting s LEFT JOIN pg_database d ON d.oid=s.setdatabase "
            "WHERE s.setrole=pg_authid.oid),'') FROM pg_authid WHERE rolname "
            "LIKE 'caplab%' "
            "ORDER BY rolname;"
        )
        role_rows = self.runner.run(
            self._postgres_query_command("postgres", role_query)
        ).splitlines()
        login = "true" if expected_login else "false"
        fixed_flags = "false:false:false:false:false:false:true:true"
        expected_roles = [
            f"caplab_owner:false:{fixed_flags}:",
            f"caplab_reader:{login}:{fixed_flags}:caplab=search_path=caplab_v0, pg_catalog",
            f"caplab_verifier:{login}:{fixed_flags}:caplab=search_path=caplab_v0, pg_catalog",
            f"caplab_writer:{login}:{fixed_flags}:caplab=search_path=caplab_v0, pg_catalog",
        ]
        if role_rows != expected_roles:
            raise HostctlError("PostgreSQL role attributes differ from the ADR matrix")

        owner_query = (
            "SELECT 'database:' || datname || ':' || pg_get_userbyid(datdba) FROM "
            "pg_database WHERE datname = 'caplab' UNION ALL SELECT 'schema:' || "
            "nspname || ':' || pg_get_userbyid(nspowner) FROM pg_namespace WHERE "
            "nspname = 'caplab_v0' ORDER BY 1;"
        )
        if self.runner.run(self._postgres_query_command("caplab", owner_query)).splitlines() != [
            "database:caplab:caplab_owner",
            "schema:caplab_v0:caplab_owner",
        ]:
            raise HostctlError("PostgreSQL database or schema ownership is wrong")

        object_query = (
            "SELECT c.relkind::text || ':' || c.relname || ':' || "
            "pg_get_userbyid(c.relowner) "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE "
            "n.nspname = 'caplab_v0' AND c.relkind IN ('r','v','S') ORDER BY 1;"
        )
        expected_objects = sorted(
            [f"r:{name}:caplab_owner" for name in POSTGRES_TABLES]
            + [f"v:{name}:caplab_owner" for name in POSTGRES_VIEWS]
            + [f"S:{name}:caplab_owner" for name in POSTGRES_SEQUENCES]
        )
        if (
            self.runner.run(self._postgres_query_command("caplab", object_query)).splitlines()
            != expected_objects
        ):
            raise HostctlError("PostgreSQL CAPLAB object inventory or ownership is wrong")

        matrix_query = (
            "WITH runtime_roles(rolname) AS (VALUES ('caplab_writer'),"
            "('caplab_reader'),('caplab_verifier')) SELECT r.rolname || ':' || "
            "c.relkind::text || ':' || c.relname || ':' || concat_ws(',', "
            "CASE WHEN has_table_privilege(r.rolname,c.oid,'SELECT') THEN 'SELECT' END, "
            "CASE WHEN has_table_privilege(r.rolname,c.oid,'INSERT') THEN 'INSERT' END, "
            "CASE WHEN has_table_privilege(r.rolname,c.oid,'UPDATE') THEN 'UPDATE' END, "
            "CASE WHEN has_table_privilege(r.rolname,c.oid,'DELETE') THEN 'DELETE' END, "
            "CASE WHEN has_table_privilege(r.rolname,c.oid,'TRUNCATE') THEN 'TRUNCATE' END, "
            "CASE WHEN has_table_privilege(r.rolname,c.oid,'REFERENCES') THEN 'REFERENCES' END, "
            "CASE WHEN has_table_privilege(r.rolname,c.oid,'TRIGGER') THEN 'TRIGGER' END) "
            "FROM runtime_roles r CROSS JOIN pg_class c JOIN pg_namespace n ON "
            "n.oid = c.relnamespace WHERE n.nspname = 'caplab_v0' AND c.relkind "
            "IN ('r','v') ORDER BY 1;"
        )
        expected_matrix: list[str] = []
        for role in RUNTIME_ROLES:
            for table in POSTGRES_TABLES:
                if role == "caplab_writer":
                    privileges = "SELECT,INSERT" if table in WRITER_INSERT_TABLES else "SELECT"
                else:
                    privileges = "SELECT"
                expected_matrix.append(f"{role}:r:{table}:{privileges}")
            for view in POSTGRES_VIEWS:
                privileges = "" if role == "caplab_writer" else "SELECT"
                expected_matrix.append(f"{role}:v:{view}:{privileges}")
        if self.runner.run(
            self._postgres_query_command("caplab", matrix_query)
        ).splitlines() != sorted(expected_matrix):
            raise HostctlError("PostgreSQL table privilege matrix is wrong")

        sequence_query = (
            "WITH runtime_roles(rolname) AS (VALUES ('caplab_writer'),"
            "('caplab_reader'),('caplab_verifier')) SELECT r.rolname || ':' || "
            "c.relname || ':' || concat_ws(',', CASE WHEN "
            "has_sequence_privilege(r.rolname,c.oid,'SELECT') THEN 'SELECT' END, "
            "CASE WHEN has_sequence_privilege(r.rolname,c.oid,'USAGE') THEN 'USAGE' END, "
            "CASE WHEN has_sequence_privilege(r.rolname,c.oid,'UPDATE') THEN 'UPDATE' END) "
            "FROM runtime_roles r CROSS JOIN pg_class c JOIN pg_namespace n ON "
            "n.oid=c.relnamespace WHERE n.nspname='caplab_v0' AND c.relkind='S' "
            "ORDER BY 1;"
        )
        expected_sequences = sorted(
            f"{role}:{sequence}:{'SELECT,USAGE' if role == 'caplab_writer' else ''}"
            for role in RUNTIME_ROLES
            for sequence in POSTGRES_SEQUENCES
        )
        if (
            self.runner.run(self._postgres_query_command("caplab", sequence_query)).splitlines()
            != expected_sequences
        ):
            raise HostctlError("PostgreSQL sequence privilege matrix is wrong")

        boundary_query = (
            "WITH runtime_roles(rolname) AS (VALUES ('caplab_writer'),"
            "('caplab_reader'),('caplab_verifier')) SELECT r.rolname || ':' || "
            "has_database_privilege(r.rolname,'caplab','CONNECT') || ':' || "
            "has_database_privilege(r.rolname,'caplab','CREATE') || ':' || "
            "has_database_privilege(r.rolname,'caplab','TEMP') || ':' || "
            "has_schema_privilege(r.rolname,'caplab_v0','USAGE') || ':' || "
            "has_schema_privilege(r.rolname,'caplab_v0','CREATE') FROM runtime_roles r "
            "ORDER BY 1;"
        )
        expected_boundary = sorted(f"{role}:true:false:false:true:false" for role in RUNTIME_ROLES)
        if (
            self.runner.run(self._postgres_query_command("caplab", boundary_query)).splitlines()
            != expected_boundary
        ):
            raise HostctlError("PostgreSQL database or schema privilege boundary is wrong")

        function_query = (
            "SELECT p.proname || ':' || pg_get_function_identity_arguments(p.oid) || ':' || "
            "pg_get_userbyid(p.proowner) || ':' || "
            "EXISTS (SELECT 1 FROM aclexplode(p.proacl) acl WHERE acl.grantee=0 AND "
            "acl.privilege_type='EXECUTE') || ':' || "
            "has_function_privilege('caplab_writer',p.oid,'EXECUTE') || ':' || "
            "has_function_privilege('caplab_reader',p.oid,'EXECUTE') || ':' || "
            "has_function_privilege('caplab_verifier',p.oid,'EXECUTE') FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='caplab_v0' "
            "ORDER BY 1;"
        )
        if self.runner.run(self._postgres_query_command("caplab", function_query)).splitlines() != [
            "reject_mutation::caplab_owner:false:false:false:false"
        ]:
            raise HostctlError("PostgreSQL function inventory or privilege boundary is wrong")

        public_query = (
            "SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_database d CROSS JOIN LATERAL "
            "aclexplode(d.datacl) acl WHERE d.datname='caplab' AND acl.grantee=0) OR "
            "EXISTS (SELECT 1 FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) "
            "acl WHERE n.nspname='caplab_v0' AND acl.grantee=0) OR EXISTS (SELECT 1 "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN "
            "LATERAL aclexplode(c.relacl) acl WHERE n.nspname='caplab_v0' AND "
            "acl.grantee=0) OR EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON "
            "n.oid=p.pronamespace CROSS JOIN LATERAL aclexplode(p.proacl) acl WHERE "
            "n.nspname='caplab_v0' AND acl.grantee=0) THEN 'public-grant' ELSE "
            "'public-revoked' END;"
        )
        if self.runner.run(self._postgres_query_command("caplab", public_query)).splitlines() != [
            "public-revoked"
        ]:
            raise HostctlError("PostgreSQL PUBLIC privileges are not fully revoked")

        membership_query = (
            "SELECT COUNT(*) FROM pg_auth_members m JOIN pg_roles member ON "
            "member.oid=m.member JOIN pg_roles granted ON granted.oid=m.roleid WHERE "
            "member.rolname LIKE 'caplab%' OR granted.rolname LIKE 'caplab%';"
        )
        if self.runner.run(
            self._postgres_query_command("postgres", membership_query)
        ).splitlines() != ["0"]:
            raise HostctlError("PostgreSQL CAPLAB roles have unexpected memberships")

        if expected_login:
            for role in RUNTIME_ROLES:
                peer_identity = self.runner.run(
                    [
                        "runuser",
                        "--user",
                        role,
                        "--",
                        "/usr/bin/env",
                        "-i",
                        "/usr/bin/psql",
                        "-X",
                        "--tuples-only",
                        "--no-align",
                        "--dbname",
                        "caplab",
                        "--command",
                        "SELECT current_user || ':' || current_database();",
                    ]
                ).splitlines()
                if peer_identity != [f"{role}:caplab"]:
                    raise HostctlError(f"PostgreSQL peer identity is wrong for {role}")

    def _verify_garage_bucket(self) -> None:
        self._garage_bucket_info()

    def _garage_bucket_info(self) -> dict[str, object]:
        response = self.runner.run(
            ["garage", "json-api", "GetBucketInfo", "-"],
            input_text=json.dumps({"globalAlias": GARAGE_BUCKET}),
        )
        try:
            bucket = json.loads(response)
        except json.JSONDecodeError as error:
            raise HostctlError("Garage returned invalid bucket information") from error
        if not isinstance(bucket, dict) or bucket.get("globalAliases") != [GARAGE_BUCKET]:
            raise HostctlError("Garage returned the wrong bucket identity")
        if bucket.get("quotas") != {
            "maxSize": 1_073_741_824,
            "maxObjects": 10_000,
        }:
            raise HostctlError("Garage bucket quota is wrong")
        return bucket

    def _verify_garage_key(
        self,
        role: str,
        alias: str,
        access_key_id: str,
    ) -> None:
        response = self.runner.run(
            ["garage", "json-api", "GetKeyInfo", "-"],
            input_text=json.dumps({"search": alias, "showSecretKey": False}),
            secret_output=True,
        )
        try:
            key = json.loads(response)
        except json.JSONDecodeError as error:
            raise HostctlError("Garage returned invalid key information") from error
        if (
            not isinstance(key, dict)
            or key.get("name") != alias
            or key.get("accessKeyId") != access_key_id
            or "secretAccessKey" in key
        ):
            raise HostctlError("Garage returned the wrong key identity")
        expires_at = key.get("expiration")
        if not isinstance(expires_at, str) or key.get("expired") is not False:
            raise HostctlError("Garage key expiry state is wrong")
        try:
            parsed_expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise HostctlError("Garage key expiration is invalid") from error
        if parsed_expiry > AUTHORIZATION_EXPIRES_AT:
            raise HostctlError("Garage key expires after the authorization boundary")
        if key.get("permissions") != {"createBucket": False}:
            raise HostctlError("Garage key global authority is wrong")
        buckets = key.get("buckets")
        expected_permissions = {
            "owner": False,
            "read": True,
            "write": role == "caplab_writer",
        }
        if (
            not isinstance(buckets, list)
            or len(buckets) != 1
            or not isinstance(buckets[0], dict)
            or buckets[0].get("globalAliases") != [GARAGE_BUCKET]
            or buckets[0].get("permissions") != expected_permissions
        ):
            raise HostctlError("Garage key bucket authority is wrong")

    def _assert_garage_bucket_empty(self) -> None:
        response = self.runner.run(
            ["garage", "json-api", "GetBucketInfo", "-"],
            input_text=json.dumps({"globalAlias": GARAGE_BUCKET}),
        )
        try:
            bucket = json.loads(response)
        except json.JSONDecodeError as error:
            raise HostctlError("Garage returned invalid bucket information") from error
        if not isinstance(bucket, dict) or bucket.get("globalAliases") != [GARAGE_BUCKET]:
            raise HostctlError("Garage returned the wrong bucket identity")
        counters = (
            bucket.get("objects"),
            bucket.get("bytes"),
            bucket.get("unfinishedUploads"),
            bucket.get("unfinishedMultipartUploads"),
        )
        if counters != (0, 0, 0, 0):
            raise HostctlError("Garage bucket is not empty")

    def _assert_postgres_application_empty(self) -> None:
        empty_check = (
            "DO $caplab$ DECLARE table_record record; has_rows boolean; BEGIN "
            "FOR table_record IN SELECT schemaname, tablename FROM pg_tables "
            "WHERE schemaname = 'caplab_v0' AND tablename <> 'schema_migrations' "
            "LOOP EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I.%I)', "
            "table_record.schemaname, table_record.tablename) INTO has_rows; "
            "IF has_rows THEN RAISE EXCEPTION 'CAPLAB application rows exist'; "
            "END IF; END LOOP; END $caplab$;"
        )
        self.runner.run(self._postgres_command("caplab", empty_check))

    def _assert_nvr_empty(self) -> None:
        if not self.paths.nvr_root.is_dir() or self.paths.nvr_root.is_symlink():
            raise HostctlError("independent-copy root identity is wrong")
        if next(self.paths.nvr_root.rglob("*"), None) is not None:
            raise HostctlError("independent-copy root is not empty")

    @staticmethod
    def _remove_bootstrap_tree(path: Path) -> None:
        if not path.is_absolute() or path.is_symlink() or not path.is_dir():
            raise HostctlError(f"refusing to remove unexpected bootstrap path: {path}")
        try:
            shutil.rmtree(path)
        except OSError as error:
            raise HostctlError(f"could not remove bootstrap path: {path}") from error

    @staticmethod
    def _remove_empty_bootstrap_directory(path: Path) -> None:
        if not path.is_absolute() or path.is_symlink() or not path.is_dir():
            raise HostctlError(f"refusing to remove unexpected bootstrap path: {path}")
        try:
            path.rmdir()
        except OSError as error:
            raise HostctlError(f"bootstrap parent is not empty: {path}") from error

    def _garage_key_inventory(self) -> tuple[set[str], set[str]]:
        response = self.runner.run(["garage", "json-api", "ListKeys", "null"])
        try:
            keys = json.loads(response)
        except json.JSONDecodeError as error:
            raise HostctlError("Garage returned an invalid key list") from error
        if not isinstance(keys, list):
            raise HostctlError("Garage returned an invalid key list")
        aliases = set(KEY_ALIASES.values())
        live_ids: set[str] = set()
        matched_ids: set[str] = set()
        for key in keys:
            if not isinstance(key, dict):
                raise HostctlError("Garage returned an invalid key record")
            access_key_id = key.get("id")
            if (
                not isinstance(access_key_id, str)
                or not access_key_id.startswith("GK")
                or access_key_id in live_ids
            ):
                raise HostctlError("Garage returned an invalid campaign key ID")
            live_ids.add(access_key_id)
            if key.get("name") in aliases:
                matched_ids.add(access_key_id)
        return live_ids, matched_ids

    @staticmethod
    def _recorded_campaign_keys(
        state: dict[str, object],
        *,
        strict: bool = False,
    ) -> tuple[dict[str, tuple[str, str]], set[str], bool]:
        records = state.get("garage_keys")
        if not isinstance(records, list):
            if strict:
                raise HostctlError("campaign state lacks Garage key identities")
            return {}, set(), False
        by_alias: dict[str, tuple[str, str]] = {}
        access_key_ids: set[str] = set()
        roles: set[str] = set()
        aliases: set[str] = set()
        valid = True
        for record in records:
            if not isinstance(record, dict):
                valid = False
                continue
            role = record.get("role")
            alias = record.get("alias")
            access_key_id = record.get("access_key_id")
            if (
                not isinstance(role, str)
                or role not in RUNTIME_ROLES
                or alias != KEY_ALIASES[role]
                or (
                    access_key_id is not None
                    and (not isinstance(access_key_id, str) or not access_key_id.startswith("GK"))
                )
            ):
                valid = False
                continue
            if isinstance(access_key_id, str):
                access_key_ids.add(access_key_id)
            if role in roles or alias in aliases:
                valid = False
                continue
            roles.add(role)
            aliases.add(str(alias))
            if isinstance(access_key_id, str):
                by_alias[str(alias)] = (role, access_key_id)
        if strict and not valid:
            raise HostctlError("campaign state has an invalid Garage key record")
        return by_alias, access_key_ids, valid

    def _read_secret_key(self, alias: str) -> dict[str, str]:
        response = self.runner.run(
            ["garage", "json-api", "GetKeyInfo", "-"],
            input_text=json.dumps({"search": alias, "showSecretKey": True}),
            secret_output=True,
        )
        try:
            payload = json.loads(response)
        except json.JSONDecodeError as error:
            raise HostctlError("Garage returned an invalid secret-key record") from error
        if not isinstance(payload, dict) or payload.get("name") != alias:
            raise HostctlError("Garage returned the wrong key identity")
        access_key_id = payload.get("accessKeyId")
        secret_access_key = payload.get("secretAccessKey")
        expires_at = payload.get("expiration")
        if not isinstance(access_key_id, str) or not access_key_id.startswith("GK"):
            raise HostctlError("Garage returned an invalid access-key ID")
        if not isinstance(secret_access_key, str) or len(secret_access_key) < 16:
            raise HostctlError("Garage returned an invalid secret access key")
        if not isinstance(expires_at, str):
            raise HostctlError("Garage key has no expiration")
        try:
            parsed_expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise HostctlError("Garage key expiration is invalid") from error
        if parsed_expiry > AUTHORIZATION_EXPIRES_AT:
            raise HostctlError("Garage key expires after the authorization boundary")
        return {
            "access_key_id": access_key_id,
            "secret_access_key": secret_access_key,
        }

    def _grant_bucket(self, role: str, access_key_id: str) -> None:
        permissions = ["--read", "--write"] if role == "caplab_writer" else ["--read"]
        self.runner.run(
            [
                "garage",
                "bucket",
                "allow",
                *permissions,
                GARAGE_BUCKET,
                "--key",
                access_key_id,
            ]
        )

    def _write_credential(
        self,
        role: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        credential_file = self.paths.credential_root / role / "garage.json"
        document = (
            json.dumps(
                {
                    "access_key_id": access_key_id,
                    "secret_access_key": secret_access_key,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("ascii")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(credential_file, flags, 0o400)
            try:
                _write_all(descriptor, document)
                uid, gid = self.identity_resolver(role)
                os.fchown(descriptor, uid, gid)
                os.fchmod(descriptor, 0o400)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError as error:
            raise HostctlError(f"cannot create credential file for {role}") from error


def read_source_commit(source_commit_file: Path) -> str:
    try:
        source_commit = source_commit_file.read_text(encoding="ascii").strip()
    except OSError as error:
        raise HostctlError(
            f"cannot read standalone CAPLAB source pin: {source_commit_file}"
        ) from error
    if COMMIT_PATTERN.fullmatch(source_commit) is None:
        raise HostctlError("standalone CAPLAB source commit is not pinned")
    return source_commit


def preflight_source(
    source_commit_file: Path,
    source_repo: Path,
    runner: Runner,
) -> str:
    if not source_repo.is_absolute() or source_repo.is_symlink() or not source_repo.is_dir():
        raise HostctlError("standalone CAPLAB source repository is not a plain directory")
    source_commit = read_source_commit(source_commit_file)
    resolved_commit = runner.run(
        _git_command(
            source_repo,
            "rev-parse",
            "--verify",
            f"{source_commit}^{{commit}}",
        )
    ).strip()
    if resolved_commit != source_commit:
        raise HostctlError("standalone CAPLAB source pin does not resolve exactly")
    head_commit = runner.run(_git_command(source_repo, "rev-parse", "HEAD")).strip()
    if head_commit != source_commit:
        raise HostctlError("standalone CAPLAB checkout is not at the pinned commit")
    worktree_status = runner.run(
        _git_command(
            source_repo,
            "status",
            "--porcelain",
            "--untracked-files=normal",
        )
    )
    if worktree_status:
        raise HostctlError("standalone CAPLAB checkout is not clean")
    lock_path = "src/caplab/runtime/requirements.lock"
    try:
        lock_bytes = runner.run(_git_command(source_repo, "show", f"{source_commit}:{lock_path}"))
    except HostctlError as error:
        raise HostctlError(
            "pinned standalone CAPLAB commit lacks the hash-locked runtime"
        ) from error
    if "--hash=sha256:" not in lock_bytes:
        raise HostctlError("pinned standalone CAPLAB commit lacks the hash-locked runtime")
    try:
        runner.run(
            _git_command(
                source_repo,
                "cat-file",
                "-e",
                f"{source_commit}:src/caplab/runtime/__main__.py",
            )
        )
    except HostctlError as error:
        raise HostctlError(
            "pinned standalone CAPLAB commit lacks the runtime entry point"
        ) from error
    return source_commit


def _git_command(source_repo: Path, *arguments: str) -> list[str]:
    return [
        "git",
        "-c",
        f"safe.directory={source_repo}",
        "-C",
        str(source_repo),
        *arguments,
    ]


def preflight_host(paths: HostPaths, runner: Runner) -> None:
    for target in (
        paths.state_file,
        paths.etc_root,
        paths.venv_root.parent,
        paths.venv_root,
        paths.nvr_root.parent,
        paths.nvr_root,
    ):
        if target.exists() or target.is_symlink():
            raise HostctlError(f"target path already exists: {target}")
    if runner.run(
        ["getent", "group", "caplab"],
        allowed_returncodes=(0, 2),
    ):
        raise HostctlError("target group caplab exists")
    for role in RUNTIME_ROLES:
        if runner.run(
            ["getent", "passwd", role],
            allowed_returncodes=(0, 2),
        ):
            raise HostctlError(f"target account {role} exists")
        if runner.run(
            ["getent", "group", role],
            allowed_returncodes=(0, 2),
        ):
            raise HostctlError(f"target group {role} exists")
    for service in ("postgresql.service", "garage.service"):
        if runner.run(["systemctl", "is-active", service]).strip() != "active":
            raise HostctlError(f"required service is not active: {service}")
    postgres_preflight = runner.run(
        [
            "runuser",
            "--user",
            "postgres",
            "--",
            "psql",
            "-X",
            "--tuples-only",
            "--no-align",
            "--dbname",
            "postgres",
            "--command",
            "SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname LIKE "
            "'caplab%') OR EXISTS (SELECT 1 FROM pg_database WHERE datname = "
            "'caplab') THEN 'collision' ELSE 'clear' END; "
            "WITH runtime_roles(role_name) AS (VALUES ('caplab_writer'),"
            "('caplab_reader'),('caplab_verifier')), applicable AS (SELECT "
            "r.role_name,h.line_number,h.auth_method FROM runtime_roles r CROSS JOIN "
            "pg_hba_file_rules h WHERE h.type='local' AND h.error IS NULL AND "
            "EXISTS (SELECT 1 FROM unnest(h.database) item WHERE item IN ('all','caplab') "
            "OR (left(item,1)='/' AND 'caplab' ~ substring(item FROM 2))) AND "
            "EXISTS (SELECT 1 FROM unnest(h.user_name) item WHERE item IN "
            "('all',r.role_name) OR (left(item,1)='/' AND r.role_name ~ "
            "substring(item FROM 2)))), first_rule AS (SELECT DISTINCT ON (role_name) "
            "role_name,auth_method FROM applicable ORDER BY role_name,line_number) "
            "SELECT role_name || ':' || auth_method FROM first_rule ORDER BY role_name;",
        ]
    ).splitlines()
    if postgres_preflight != [
        "clear",
        "caplab_reader:peer",
        "caplab_verifier:peer",
        "caplab_writer:peer",
    ]:
        raise HostctlError("PostgreSQL target names or peer authentication are unfit")
    buckets = _json_list(
        runner.run(["garage", "json-api", "ListBuckets", "null"]),
        "Garage returned an invalid bucket list",
    )
    if any(
        isinstance(bucket, dict) and GARAGE_BUCKET in bucket.get("globalAliases", [])
        for bucket in buckets
    ):
        raise HostctlError(f"target Garage bucket exists: {GARAGE_BUCKET}")
    keys = _json_list(
        runner.run(["garage", "json-api", "ListKeys", "null"]),
        "Garage returned an invalid key list",
    )
    if any(isinstance(key, dict) and key.get("name") in set(KEY_ALIASES.values()) for key in keys):
        raise HostctlError("a campaign-scoped Garage key already exists")
    if (
        runner.run(["findmnt", "--noheadings", "--output", "FSTYPE", "--target", "/nvr"]).strip()
        != "zfs"
    ):
        raise HostctlError("/nvr is not the expected ZFS boundary")


def _json_list(encoded: str, error_message: str) -> list[object]:
    try:
        parsed = json.loads(encoded)
    except json.JSONDecodeError as error:
        raise HostctlError(error_message) from error
    if not isinstance(parsed, list):
        raise HostctlError(error_message)
    return parsed


def read_state(state_file: Path) -> dict[str, object]:
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except OSError as error:
        raise HostctlError(f"cannot read campaign state: {state_file}") from error
    except json.JSONDecodeError as error:
        raise HostctlError(f"campaign state is not valid JSON: {state_file}") from error
    if not isinstance(state, dict):
        raise HostctlError("campaign state must be a JSON object")
    if state.get("schema_version") != 1 or state.get("campaign_id") != CAMPAIGN_ID:
        raise HostctlError("campaign state identity does not match this host surface")
    return state


def write_state(state_file: Path, state: dict[str, object]) -> None:
    encoded = (json.dumps(state, sort_keys=True, indent=2) + "\n").encode("utf-8")
    temporary = state_file.with_name(f".{state_file.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(temporary, flags, 0o600)
        try:
            _write_all(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, state_file)
        directory = os.open(state_file.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as error:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
        raise HostctlError(f"cannot persist campaign state: {state_file}") from error


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise OSError("short write")
        offset += written


def require_active_authorization(now: datetime) -> None:
    if now.tzinfo is None:
        raise HostctlError("authorization comparison requires a timezone-aware clock")
    if now.astimezone(UTC) > AUTHORIZATION_EXPIRES_AT:
        raise HostctlError("campaign authorization has expired")


def arm_effects(state_file: Path, now: datetime) -> None:
    require_active_authorization(now)
    state = read_state(state_file)
    if state.get("effects_armed") is True and state.get("phase") == "armed":
        return
    if state.get("effects_armed") is not False or state.get("phase") != "ready":
        raise HostctlError("campaign must be ready before arming effects")
    state["effects_armed"] = True
    state["phase"] = "armed"
    state["inventories"] = {}
    state["inventory_checks"] = {}
    write_state(state_file, state)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-commit-file",
        type=Path,
        default=DEFAULT_SOURCE_COMMIT_FILE,
    )
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument("--source-repo", type=Path, default=DEFAULT_SOURCE_REPO)
    parser.add_argument(
        "--runtime-config",
        type=Path,
        default=DEFAULT_RUNTIME_CONFIG,
    )
    parser.add_argument(
        "--credential-root",
        type=Path,
        default=Path("/etc/caplab/credentials"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight", help="validate source and host preconditions")
    subparsers.add_parser("bootstrap", help="create the empty P4 host namespaces")
    subparsers.add_parser(
        "issue-credentials",
        help="issue campaign keys and enable peer roles",
    )
    subparsers.add_parser(
        "arm-effects",
        help="irreversibly cross the synthetic-effect rollback boundary",
    )
    inventory_parser = subparsers.add_parser(
        "capture-inventory",
        help="record one fixed P4 store-inventory checkpoint",
    )
    inventory_parser.add_argument("--label", choices=INVENTORY_LABELS, required=True)
    subparsers.add_parser(
        "rollback-empty",
        help="remove bootstrap resources only before the effect boundary",
    )
    verify_parser = subparsers.add_parser(
        "verify",
        help="verify the recorded host phase",
    )
    verify_parser.add_argument(
        "--phase",
        choices=("base", "ready", "armed", "disabled"),
        required=True,
    )
    subparsers.add_parser("disable", help="revoke all campaign access")
    return parser.parse_args(argv)


def execute(arguments: argparse.Namespace) -> int:
    runner = SubprocessRunner()
    paths = HostPaths(
        state_file=arguments.state_file,
        credential_root=arguments.credential_root,
    )
    controller = HostController(
        paths=paths,
        runner=runner,
        identity_resolver=resolve_identity,
        clock=lambda: datetime.now(UTC),
    )
    if arguments.command == "preflight":
        source_commit = preflight_source(
            arguments.source_commit_file,
            arguments.source_repo,
            runner,
        )
        controller._validate_runtime_config(arguments.runtime_config, source_commit)
        preflight_host(paths, runner)
        print(f"CAPLAB P4 preflight passed at {source_commit}")
        return 0
    if arguments.command == "bootstrap":
        source_commit = preflight_source(
            arguments.source_commit_file,
            arguments.source_repo,
            runner,
        )
        preflight_host(paths, runner)
        controller.bootstrap_base(
            source_commit=source_commit,
            source_pin=arguments.source_commit_file,
            runtime_config=arguments.runtime_config,
            source_repo=arguments.source_repo,
        )
        print(f"created empty CAPLAB P4 host base at {source_commit}")
        return 0
    if arguments.command == "issue-credentials":
        preflight_source(
            arguments.source_commit_file,
            arguments.source_repo,
            runner,
        )
        controller.verify("base")
        controller.issue_credentials()
        print(f"issued bounded credentials for {CAMPAIGN_ID}")
        return 0
    if arguments.command == "arm-effects":
        preflight_source(
            arguments.source_commit_file,
            arguments.source_repo,
            runner,
        )
        controller.verify("ready")
        arm_effects(arguments.state_file, controller.clock())
        print(f"armed synthetic-effect boundary for {CAMPAIGN_ID}")
        return 0
    if arguments.command == "capture-inventory":
        preflight_source(
            arguments.source_commit_file,
            arguments.source_repo,
            runner,
        )
        controller.verify("armed")
        controller.capture_inventory(arguments.label)
        print(f"recorded CAPLAB store inventory: {arguments.label}")
        return 0
    if arguments.command == "rollback-empty":
        rollback_state = read_state(arguments.state_file)
        if rollback_state.get("effects_armed") is True:
            raise HostctlError("synthetic-effect boundary is armed; disable and quarantine instead")
        if rollback_state.get("phase") == "disabled":
            preflight_source(
                arguments.source_commit_file,
                arguments.source_repo,
                runner,
            )
        controller.rollback_empty()
        print(f"removed empty bootstrap resources for {CAMPAIGN_ID}")
        return 0
    if arguments.command == "disable":
        controller.disable_access()
        print(f"disabled campaign access for {CAMPAIGN_ID}")
        return 0
    if arguments.command == "verify":
        if arguments.phase != "disabled":
            preflight_source(
                arguments.source_commit_file,
                arguments.source_repo,
                runner,
            )
        controller.verify(arguments.phase)
        print(f"verified CAPLAB host phase: {arguments.phase}")
        return 0
    raise AssertionError(f"unhandled command: {arguments.command}")


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if arguments.command not in {"disable", "rollback-empty"}:
            read_source_commit(arguments.source_commit_file)
        return execute(arguments)
    except HostctlError as error:
        print(f"caplab-hostctl: {error}", file=sys.stderr)
        return 1


def resolve_identity(role: str) -> tuple[int, int]:
    try:
        account = pwd.getpwnam(role)
    except KeyError as error:
        raise HostctlError(f"runtime account is absent: {role}") from error
    return account.pw_uid, account.pw_gid


if __name__ == "__main__":
    raise SystemExit(main())
