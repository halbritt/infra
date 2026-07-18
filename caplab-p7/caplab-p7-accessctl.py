#!/usr/bin/python3
"""Issue, verify, and revoke the one CAPLAB P7 reader identity."""

from __future__ import annotations

import argparse
import json
import os
import pwd
import subprocess
import sys
import tomllib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


CAMPAIGN_ID = "caplab-study-001-p7-recompute-2026-07-18"
CAPLAB_SOURCE_COMMIT = "04ed8213ec7741d76d8bb9f9b6f972ebb4deaf3e"
ADMISSION_MANIFEST_SHA256 = (
    "d2d4f821146c3f39e6726133c383807ec9f6051834e74fbd3a5f33aae8ef148e"
)
AUTHORIZATION_EXPIRES_AT = datetime(2026, 7, 25, 23, 59, 59, tzinfo=UTC)
ACCOUNT_EXPIRE_DATE = "2026-07-26"
ROLE = "caplab_reader"
KEY_ALIAS = "caplab-p7-reader"
GARAGE_BUCKET = "caplab-v0"
TIMER = "caplab-p7-expiry.timer"
DEFAULT_STATE = Path(f"/var/lib/{CAMPAIGN_ID}.state.json")
DEFAULT_CREDENTIAL = Path("/etc/caplab/credentials/caplab_reader/garage.json")
DEFAULT_SOURCE_COMMIT = Path("/etc/caplab/P7_SOURCE_COMMIT")
DEFAULT_CONFIG = Path("/etc/caplab/recomputation.toml")
DEFAULT_RUNTIME_PYTHON = Path(
    f"/opt/caplab/p7/{CAPLAB_SOURCE_COMMIT}/bin/python"
)
SAFE_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "LC_ALL": "C.UTF-8",
}


class HostctlError(RuntimeError):
    """The P7 access boundary is absent, ambiguous, or incomplete."""


class Paths:
    def __init__(
        self,
        *,
        state_file: Path = DEFAULT_STATE,
        credential_file: Path = DEFAULT_CREDENTIAL,
        source_commit_file: Path = DEFAULT_SOURCE_COMMIT,
        config_file: Path = DEFAULT_CONFIG,
        runtime_python: Path = DEFAULT_RUNTIME_PYTHON,
    ) -> None:
        self.state_file = state_file
        self.credential_file = credential_file
        self.source_commit_file = source_commit_file
        self.config_file = config_file
        self.runtime_python = runtime_python


class SubprocessRunner:
    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        completed = subprocess.run(
            arguments,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            env=SAFE_ENV,
        )
        if completed.returncode not in allowed_returncodes:
            detail = "redacted" if secret_output else completed.stderr.strip()
            raise HostctlError(
                f"command failed with status {completed.returncode}: "
                f"{arguments[0]} ({detail})"
            )
        return completed.stdout


def _canonical(document: object) -> bytes:
    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("short write")
        offset += written


def _write_state(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    try:
        _write_all(descriptor, _canonical(document))
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _read_state(path: Path) -> dict[str, object]:
    try:
        metadata = path.lstat()
        if not path.is_file() or path.is_symlink() or metadata.st_mode & 0o077:
            raise HostctlError("campaign state custody is invalid")
        document = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HostctlError("campaign state is unreadable") from error
    if not isinstance(document, dict) or document.get("campaign_id") != CAMPAIGN_ID:
        raise HostctlError("campaign state identity is invalid")
    return document


class HostController:
    def __init__(
        self,
        paths: Paths | None = None,
        *,
        runner: Any | None = None,
        clock: Callable[[], datetime] | None = None,
        identity_resolver: Callable[[str], tuple[int, int]] | None = None,
    ) -> None:
        self.paths = paths or Paths()
        self.runner = runner or SubprocessRunner()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.identity_resolver = identity_resolver or self._system_identity

    @staticmethod
    def _system_identity(role: str) -> tuple[int, int]:
        identity = pwd.getpwnam(role)
        return identity.pw_uid, identity.pw_gid

    def _require_active(self) -> int:
        now = self.clock()
        if now.tzinfo is None:
            raise HostctlError("campaign clock is ambiguous")
        remaining = int(
            (AUTHORIZATION_EXPIRES_AT - now.astimezone(UTC)).total_seconds()
        )
        if remaining <= 0:
            raise HostctlError("campaign authorization has expired")
        return remaining

    def _require_timer(self) -> None:
        enabled = self.runner.run(["systemctl", "is-enabled", TIMER]).strip()
        active = self.runner.run(["systemctl", "is-active", TIMER]).strip()
        if enabled != "enabled" or active != "active":
            raise HostctlError("campaign expiry timer is not active and enabled")

    def _verify_installation(self) -> None:
        for path, label in (
            (self.paths.source_commit_file, "source commit"),
            (self.paths.config_file, "recomputation configuration"),
            (self.paths.runtime_python, "runtime interpreter"),
        ):
            if path.is_symlink() or not path.is_file():
                raise HostctlError(f"installed {label} is absent or ambiguous")
        try:
            retained_commit = self.paths.source_commit_file.read_text(
                encoding="ascii"
            ).strip()
            configuration = tomllib.loads(
                self.paths.config_file.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            raise HostctlError("installed P7 identity files are unreadable") from error
        if retained_commit != CAPLAB_SOURCE_COMMIT:
            raise HostctlError("installed CAPLAB source commit differs")
        authorization = configuration.get("authorization")
        expected = {
            "campaign_id": CAMPAIGN_ID,
            "expires_at": "2026-07-25T23:59:59Z",
            "source_commit": CAPLAB_SOURCE_COMMIT,
            "admission_manifest_sha256": ADMISSION_MANIFEST_SHA256,
        }
        if not isinstance(authorization, dict) or {
            key: authorization.get(key) for key in expected
        } != expected:
            raise HostctlError("installed recomputation authorization differs")

    def _list_keys(self) -> dict[str, str]:
        response = self.runner.run(["garage", "json-api", "ListKeys", "null"])
        try:
            records = json.loads(response)
        except json.JSONDecodeError as error:
            raise HostctlError("Garage returned an invalid key list") from error
        if not isinstance(records, list):
            raise HostctlError("Garage returned an invalid key list")
        aliases: dict[str, str] = {}
        for record in records:
            if not isinstance(record, dict):
                raise HostctlError("Garage returned an invalid key record")
            key_id = record.get("id")
            name = record.get("name")
            if not isinstance(key_id, str) or not key_id.startswith("GK"):
                raise HostctlError("Garage returned an invalid key identity")
            if isinstance(name, str):
                if name in aliases:
                    raise HostctlError("Garage key alias is ambiguous")
                aliases[name] = key_id
        return aliases

    def _key_info(self, *, show_secret: bool) -> dict[str, object]:
        response = self.runner.run(
            ["garage", "json-api", "GetKeyInfo", "-"],
            input_text=json.dumps({"search": KEY_ALIAS, "showSecretKey": show_secret}),
            secret_output=show_secret,
        )
        try:
            document = json.loads(response)
        except json.JSONDecodeError as error:
            raise HostctlError("Garage returned invalid key information") from error
        if not isinstance(document, dict) or document.get("name") != KEY_ALIAS:
            raise HostctlError("Garage returned the wrong key identity")
        return document

    def _validate_key(self, document: dict[str, object], key_id: str) -> None:
        if document.get("accessKeyId") != key_id or "secretAccessKey" in document:
            raise HostctlError("Garage returned the wrong public key identity")
        expiration = document.get("expiration")
        try:
            parsed = datetime.fromisoformat(str(expiration).replace("Z", "+00:00"))
        except ValueError as error:
            raise HostctlError("Garage key expiration is invalid") from error
        if (
            parsed > AUTHORIZATION_EXPIRES_AT
            or document.get("expired") is not False
            or document.get("permissions") != {"createBucket": False}
        ):
            raise HostctlError("Garage key global authority or expiry is wrong")
        expected = {
            "globalAliases": [GARAGE_BUCKET],
            "permissions": {"owner": False, "read": True, "write": False},
        }
        if document.get("buckets") != [expected]:
            raise HostctlError("Garage key bucket authority is wrong")

    def _postgres_state(self) -> tuple[bool, int]:
        output = self.runner.run(
            [
                "runuser",
                "--user",
                "postgres",
                "--",
                "psql",
                "-X",
                "--set",
                "ON_ERROR_STOP=1",
                "--tuples-only",
                "--no-align",
                "--dbname",
                "postgres",
                "--command",
                "SELECT r.rolcanlogin, COUNT(a.pid) FROM pg_roles r LEFT JOIN "
                "pg_stat_activity a ON a.usename=r.rolname WHERE "
                "r.rolname='caplab_reader' GROUP BY r.rolcanlogin;",
            ]
        ).strip()
        parts = output.split("|")
        if len(parts) != 2 or parts[0] not in {"t", "f"}:
            raise HostctlError("PostgreSQL reader state is invalid")
        try:
            sessions = int(parts[1])
        except ValueError as error:
            raise HostctlError("PostgreSQL reader session count is invalid") from error
        return parts[0] == "t", sessions

    def _write_credential(self, key_id: str, secret: str) -> None:
        path = self.paths.credential_file
        if path.parent.is_symlink() or not path.parent.is_dir():
            raise HostctlError("reader credential directory is invalid")
        document = _canonical(
            {"access_key_id": key_id, "secret_access_key": secret}
        )
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o400,
        )
        try:
            _write_all(descriptor, document)
            uid, gid = self.identity_resolver(ROLE)
            os.fchown(descriptor, uid, gid)
            os.fchmod(descriptor, 0o400)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def enable(self) -> None:
        remaining = self._require_active()
        self._verify_installation()
        self._require_timer()
        if self.paths.state_file.exists():
            raise HostctlError("campaign state already exists")
        if self.paths.credential_file.exists() or KEY_ALIAS in self._list_keys():
            raise HostctlError("reader access is not initially disabled")
        login, sessions = self._postgres_state()
        if login or sessions:
            raise HostctlError("PostgreSQL reader is not initially disabled")
        state: dict[str, object] = {
            "schema_version": "caplab-p7-access-state/1",
            "campaign_id": CAMPAIGN_ID,
            "phase": "enabling",
            "garage_key": {"alias": KEY_ALIAS, "access_key_id": None},
        }
        _write_state(self.paths.state_file, state)
        try:
            self.runner.run(
                [
                    "garage",
                    "key",
                    "create",
                    "--expires-in",
                    f"{remaining}s",
                    KEY_ALIAS,
                ],
                secret_output=True,
            )
            secret_record = self._key_info(show_secret=True)
            key_id = secret_record.get("accessKeyId")
            secret = secret_record.get("secretAccessKey")
            if (
                not isinstance(key_id, str)
                or not key_id.startswith("GK")
                or not isinstance(secret, str)
                or len(secret) < 16
            ):
                raise HostctlError("Garage returned an invalid secret-key record")
            expiration = secret_record.get("expiration")
            try:
                parsed = datetime.fromisoformat(str(expiration).replace("Z", "+00:00"))
            except ValueError as error:
                raise HostctlError("Garage key expiration is invalid") from error
            if parsed > AUTHORIZATION_EXPIRES_AT:
                raise HostctlError("Garage key expires after campaign authorization")
            self.runner.run(
                [
                    "garage",
                    "bucket",
                    "allow",
                    "--read",
                    GARAGE_BUCKET,
                    "--key",
                    key_id,
                ]
            )
            self._write_credential(key_id, secret)
            state["garage_key"] = {"alias": KEY_ALIAS, "access_key_id": key_id}
            _write_state(self.paths.state_file, state)
            self.runner.run(
                ["usermod", "--expiredate", ACCOUNT_EXPIRE_DATE, ROLE]
            )
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
                    "ALTER ROLE caplab_reader LOGIN;",
                ]
            )
            state["phase"] = "ready"
            state["enabled_at"] = self.clock().astimezone(UTC).isoformat().replace(
                "+00:00", "Z"
            )
            _write_state(self.paths.state_file, state)
        except (HostctlError, OSError):
            try:
                self.disable()
            except HostctlError as cleanup_error:
                raise HostctlError(
                    "reader enable failed and aggregate disable was incomplete"
                ) from cleanup_error
            raise

    def verify(self, phase: str) -> None:
        if phase not in {"ready", "disabled"}:
            raise HostctlError("verification phase is invalid")
        state = _read_state(self.paths.state_file)
        if state.get("phase") != phase:
            raise HostctlError("campaign state phase differs")
        aliases = self._list_keys()
        login, sessions = self._postgres_state()
        if phase == "ready":
            self._require_active()
            self._verify_installation()
            self._require_timer()
            key = state.get("garage_key")
            if not isinstance(key, dict):
                raise HostctlError("campaign state has no key identity")
            key_id = key.get("access_key_id")
            if (
                not isinstance(key_id, str)
                or aliases.get(KEY_ALIAS) != key_id
                or not login
            ):
                raise HostctlError("reader identity is not ready")
            self._validate_key(self._key_info(show_secret=False), key_id)
            metadata = self.paths.credential_file.lstat()
            uid, gid = self.identity_resolver(ROLE)
            if (
                self.paths.credential_file.is_symlink()
                or not self.paths.credential_file.is_file()
                or metadata.st_mode & 0o777 != 0o400
                or metadata.st_uid != uid
                or metadata.st_gid != gid
            ):
                raise HostctlError("reader credential custody is invalid")
        else:
            if KEY_ALIAS in aliases or login or sessions:
                raise HostctlError("reader identity remains live")
            if self.paths.credential_file.exists():
                raise HostctlError("reader credential remains present")

    def disable(self) -> None:
        failures: list[str] = []
        results: dict[str, str] = {}
        try:
            state = _read_state(self.paths.state_file)
        except HostctlError:
            state = None
            failures.append("state_read")
            results["state_read"] = "failed"

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
                    "ALTER ROLE caplab_reader NOLOGIN; SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity WHERE usename='caplab_reader' AND "
                    "pid <> pg_backend_pid();",
                ]
            ),
        )
        attempt(
            "process",
            lambda: self.runner.run(
                ["pkill", "--signal", "KILL", "--uid", ROLE],
                allowed_returncodes=(0, 1),
            ),
        )
        try:
            aliases = self._list_keys()
        except HostctlError:
            aliases = {}
            failures.append("garage_inventory")
            results["garage_inventory"] = "failed"
        else:
            results["garage_inventory"] = "complete"
        key_ids: set[str] = set()
        if KEY_ALIAS in aliases:
            key_ids.add(aliases[KEY_ALIAS])
        if state is not None:
            record = state.get("garage_key")
            if isinstance(record, dict):
                retained = record.get("access_key_id")
                if isinstance(retained, str) and retained.startswith("GK"):
                    key_ids.add(retained)
        for key_id in sorted(key_ids):
            attempt(
                f"garage_key:{key_id}",
                lambda key_id=key_id: self.runner.run(
                    ["garage", "key", "delete", "--yes", key_id],
                    secret_output=True,
                ),
            )

        def remove_credential() -> None:
            path = self.paths.credential_file
            if path.is_symlink():
                raise HostctlError("refusing a symlinked credential path")
            try:
                path.unlink()
            except FileNotFoundError:
                return

        attempt("credential", remove_credential)
        attempt(
            "os_account",
            lambda: self.runner.run(
                ["usermod", "--lock", "--expiredate", "1", ROLE]
            ),
        )
        if state is not None:
            state["disable_results"] = results
            state["phase"] = "disabled" if not failures else "disable_incomplete"
            state["disabled_at"] = self.clock().astimezone(UTC).isoformat().replace(
                "+00:00", "Z"
            )
            _write_state(self.paths.state_file, state)
        if failures:
            raise HostctlError(
                "campaign access disablement is incomplete: " + ",".join(failures)
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="caplab-p7-accessctl",
        description="Manage the bounded CAPLAB P7 reader lifecycle.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("enable", help="issue the expiring reader identity")
    verify = subparsers.add_parser("verify", help="verify reader lifecycle state")
    verify.add_argument("--phase", choices=("ready", "disabled"), required=True)
    subparsers.add_parser("disable", help="revoke the reader identity")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
        if os.geteuid() != 0:
            raise HostctlError("access lifecycle commands require root")
        controller = HostController()
        if arguments.command == "enable":
            controller.enable()
        elif arguments.command == "verify":
            controller.verify(arguments.phase)
        elif arguments.command == "disable":
            controller.disable()
        else:
            raise AssertionError(f"unhandled command: {arguments.command}")
        print(json.dumps({"campaign_id": CAMPAIGN_ID, "status": arguments.command}))
        return 0
    except (HostctlError, OSError) as error:
        print(f"caplab-p7-accessctl: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
