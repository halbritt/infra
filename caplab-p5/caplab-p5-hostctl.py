#!/usr/bin/python3
"""Provision and retire the bounded CAPLAB P5 host identities."""

from __future__ import annotations

import argparse
import grp
import json
import os
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CAMPAIGN_ID = "caplab-p5-recovery-2026-07-16"
EXPIRY = datetime(2026, 7, 23, 23, 59, 59, tzinfo=UTC)
SOURCE_REPO = Path("/home/halbritt/git/caplab")
SOURCE_COMMIT_FILE = Path("/etc/caplab-p5/SOURCE_COMMIT")
CONFIG_FILE = Path("/etc/caplab-p5/recovery.toml")
STATE_FILE = Path("/var/lib/caplab-p5-recovery.state.json")
VENV_ROOT = Path("/opt/caplab-p5/venvs")
CREDENTIAL_ROOT = Path("/etc/caplab-p5/credentials")
LOCAL_COPY_ROOT = Path("/nvr/caplab/v0")
LOCAL_COPY_PREFIX = LOCAL_COPY_ROOT / "objects/sha256/a1"
GROUP = "caplab-p5"
OPERATOR = "caplab_p5_operator"
VERIFIER = "caplab_p5_verifier"
ROLES = (OPERATOR, VERIFIER)
KEY_ALIASES = {
    OPERATOR: f"{CAMPAIGN_ID}-operator",
    VERIFIER: f"{CAMPAIGN_ID}-verifier",
}
SAFE_ENV = {
    "HOME": "/root",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "PYTHONNOUSERSITE": "1",
}


class HostctlError(RuntimeError):
    """A fail-closed error whose text contains no credential material."""


def run(
    arguments: list[str],
    *,
    input_text: str | None = None,
    allowed: tuple[int, ...] = (0,),
) -> str:
    try:
        completed = subprocess.run(
            arguments,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            close_fds=True,
            env=SAFE_ENV,
        )
    except OSError as error:
        raise HostctlError(f"could not execute {Path(arguments[0]).name}") from error
    if completed.returncode not in allowed:
        raise HostctlError(
            f"{Path(arguments[0]).name} failed with exit {completed.returncode}; "
            "command output suppressed"
        )
    return completed.stdout


def now() -> datetime:
    return datetime.now(UTC)


def require_root() -> None:
    if os.geteuid() != 0:
        raise HostctlError("CAPLAB P5 host control requires root")


def require_active() -> None:
    if now() > EXPIRY:
        raise HostctlError("CAPLAB P5 authorization has expired")


def read_exact(path: Path, *, mode: int, uid: int, gid: int) -> bytes:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise HostctlError(f"cannot open trusted file: {path}") from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != mode
            or metadata.st_uid != uid
            or metadata.st_gid != gid
        ):
            raise HostctlError(f"trusted file ownership or mode is wrong: {path}")
        return os.read(descriptor, 1_048_577)
    finally:
        os.close(descriptor)


def source_commit() -> str:
    try:
        value = SOURCE_COMMIT_FILE.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as error:
        raise HostctlError("installed CAPLAB source commit is unreadable") from error
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise HostctlError("installed CAPLAB source commit is invalid")
    return value


def config() -> dict[str, Any]:
    try:
        group_id = grp.getgrnam(GROUP).gr_gid
    except KeyError as error:
        raise HostctlError("CAPLAB P5 group is absent") from error
    data = read_exact(CONFIG_FILE, mode=0o640, uid=0, gid=group_id)
    if len(data) > 1_048_576:
        raise HostctlError("CAPLAB P5 configuration is too large")
    try:
        value = tomllib.loads(data.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise HostctlError("CAPLAB P5 configuration is invalid") from error
    if value.get("campaign", {}).get("campaign_id") != CAMPAIGN_ID:
        raise HostctlError("CAPLAB P5 configuration campaign is wrong")
    if value.get("campaign", {}).get("runtime_commit") != source_commit():
        raise HostctlError("CAPLAB P5 configuration source identity is wrong")
    if value.get("campaign", {}).get("authorization_expires_at") != "2026-07-23T23:59:59Z":
        raise HostctlError("CAPLAB P5 configuration expiry is wrong")
    return value


def read_state(*, required: bool = True) -> dict[str, Any]:
    if not STATE_FILE.exists() and not required:
        return {}
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HostctlError("CAPLAB P5 lifecycle state is unreadable") from error
    if not isinstance(value, dict) or value.get("campaign_id") != CAMPAIGN_ID:
        raise HostctlError("CAPLAB P5 lifecycle state identity is wrong")
    return value


def write_state(value: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    temporary = STATE_FILE.with_name(f".{STATE_FILE.name}.{os.getpid()}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, STATE_FILE)


def role_exists(role: str) -> bool:
    output = run(
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
            f"SELECT count(*) FROM pg_roles WHERE rolname = '{role}';",
        ]
    )
    return output.strip() == "1"


def garage_keys() -> list[dict[str, Any]]:
    try:
        value = json.loads(run(["garage", "json-api", "ListKeys", "null"]))
    except json.JSONDecodeError as error:
        raise HostctlError("Garage returned an invalid key inventory") from error
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise HostctlError("Garage returned an invalid key inventory")
    return value


def key_by_alias(alias: str) -> dict[str, Any] | None:
    matches = [key for key in garage_keys() if key.get("name") == alias]
    if len(matches) > 1:
        raise HostctlError("Garage returned duplicate P5 key aliases")
    return matches[0] if matches else None


def p4_control() -> str:
    return run(
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
            "caplab",
            "--command",
            "SELECT operation_id || '|' || campaign_id || '|' || content_sha256 || "
            "'|' || manifest_sha256 FROM caplab_v0.registrations "
            "WHERE campaign_id = 'caplab-p4-roundtrip-2026-07-15' ORDER BY operation_id;",
        ]
    ).strip()


def git_command(*arguments: str) -> list[str]:
    return [
        "git",
        "-c",
        f"safe.directory={SOURCE_REPO}",
        "-C",
        str(SOURCE_REPO),
        *arguments,
    ]


def preflight() -> None:
    require_root()
    require_active()
    cfg = config()
    commit = source_commit()
    state = read_state(required=False)
    retry = bool(state) and state.get("phase") == "disabled"
    if run(git_command("rev-parse", "HEAD")).strip() != commit:
        raise HostctlError("CAPLAB source checkout differs from the frozen commit")
    if run(git_command("status", "--porcelain")).strip():
        raise HostctlError("CAPLAB source checkout is dirty")
    for service in ("postgresql.service", "garage.service"):
        if run(["systemctl", "is-active", service]).strip() != "active":
            raise HostctlError(f"required service is not active: {service}")
    if not retry:
        run(["/usr/local/libexec/caplab-hostctl", "verify", "--phase", "disabled"])
    if run(["systemctl", "is-active", "restic-backup.service"], allowed=(0, 3)).strip() == "active":
        raise HostctlError("restic backup is active")
    if run(["systemctl", "is-active", "restic-prune.service"], allowed=(0, 3)).strip() == "active":
        raise HostctlError("restic prune is active")
    if not p4_control().startswith("op-caplab-p4-roundtrip-0001|"):
        raise HostctlError("P4 control registration is absent")
    if retry and state.get("source_commit") != commit:
        raise HostctlError("disabled P5 retry state has the wrong source identity")
    for role in ROLES:
        if _user_exists(role) != retry:
            condition = "absent" if retry else "exists"
            raise HostctlError(f"target operating-system identity is not {condition}: {role}")
        if role_exists(role) != retry:
            condition = "absent" if retry else "exists"
            raise HostctlError(f"target PostgreSQL identity is not {condition}: {role}")
        if key_by_alias(KEY_ALIASES[role]) is not None:
            raise HostctlError(f"target Garage key alias exists: {KEY_ALIASES[role]}")
    if retry:
        p4_login = run(
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
                "SELECT rolname || ':' || rolcanlogin FROM pg_roles "
                "WHERE rolname IN ('caplab_writer','caplab_reader','caplab_verifier') "
                "ORDER BY rolname;",
            ]
        ).splitlines()
        if p4_login != [
            "caplab_reader:false",
            "caplab_verifier:false",
            "caplab_writer:false",
        ]:
            raise HostctlError("P4 runtime roles are not disabled during P5 retry")
        if not role_exists("caplab_custodian"):
            raise HostctlError("disabled P5 retry state lacks its custodian role")
        if CREDENTIAL_ROOT.exists():
            raise HostctlError("disabled P5 retry state retains credentials")
        retained = run(
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
                "caplab",
                "--command",
                "SELECT "
                "(SELECT count(*) FROM caplab_v0.operation_requests "
                " WHERE operation_id = 'op-p5-recovery-0001') || '|' || "
                "(SELECT count(*) FROM caplab_v0.custody_requests "
                " WHERE operation_id = 'op-p5-recovery-0001') || '|' || "
                "(SELECT count(*) FROM caplab_v0.purge_tombstones "
                " WHERE operation_id = 'op-p5-recovery-0001');",
            ]
        ).strip()
        if retained != "0|0|0":
            raise HostctlError("disabled P5 retry state retains campaign data")
    if cfg["identity"]["operation_id"] != "op-p5-recovery-0001":
        raise HostctlError("P5 operation identity is wrong")


def _user_exists(role: str) -> bool:
    try:
        pwd.getpwnam(role)
    except KeyError:
        return False
    return True


def ensure_group(name: str) -> None:
    try:
        grp.getgrnam(name)
    except KeyError:
        run(["groupadd", "--system", name])


def ensure_user(name: str) -> None:
    if not _user_exists(name):
        run(
            [
                "useradd",
                "--system",
                "--no-create-home",
                "--home-dir",
                "/nonexistent",
                "--shell",
                "/usr/sbin/nologin",
                "--gid",
                GROUP,
                "--groups",
                "caplab",
                name,
            ]
        )
    else:
        run(["usermod", "--expiredate", "-1", name])


def install_source(commit: str) -> Path:
    target = VENV_ROOT / commit
    VENV_ROOT.mkdir(mode=0o755, parents=True, exist_ok=True)
    os.chown(VENV_ROOT.parent, 0, grp.getgrnam(GROUP).gr_gid)
    os.chmod(VENV_ROOT.parent, 0o750)
    os.chown(VENV_ROOT, 0, grp.getgrnam(GROUP).gr_gid)
    os.chmod(VENV_ROOT, 0o750)
    if target.exists():
        secure_source_tree(target)
        return target
    with tempfile.TemporaryDirectory(prefix="caplab-p5-source-") as scratch_name:
        scratch = Path(scratch_name)
        archive = scratch / "source.tar"
        source = scratch / "source"
        source.mkdir()
        run(git_command("archive", "--format=tar", "-o", str(archive), commit))
        run(["tar", "-xf", str(archive), "-C", str(source)])
        run(["python3", "-m", "venv", str(scratch / "venv")])
        run(
            [
                str(scratch / "venv/bin/python"),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--require-hashes",
                "--requirement",
                str(source / "src/caplab/runtime/requirements.lock"),
            ]
        )
        purelib = Path(
            run(
                [
                    str(scratch / "venv/bin/python"),
                    "-c",
                    "import sysconfig; print(sysconfig.get_path('purelib'))",
                ]
            ).strip()
        )
        shutil.copytree(source / "src/caplab", purelib / "caplab")
        (scratch / "venv/share/caplab-p5").mkdir(parents=True)
        shutil.copy2(
            source / "tests/fixtures/recovery/synthetic-attempt.json",
            scratch / "venv/share/caplab-p5/synthetic-attempt.json",
        )
        shutil.copy2(
            source / "tests/fixtures/recovery/synthetic-payload.json",
            scratch / "venv/share/caplab-p5/synthetic-payload.json",
        )
        os.replace(scratch / "venv", target)
    secure_source_tree(target)
    return target


def secure_source_tree(target: Path) -> None:
    run(["chown", "--recursive", f"root:{GROUP}", str(target)])
    run(["chmod", "--recursive", "u=rwX,g=rX,o=", str(target)])


def create_database_roles() -> None:
    sql = """
DO $p5$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caplab_custodian') THEN
    CREATE ROLE caplab_custodian NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caplab_p5_operator') THEN
    CREATE ROLE caplab_p5_operator LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caplab_p5_verifier') THEN
    CREATE ROLE caplab_p5_verifier LOGIN;
  END IF;
END
$p5$;
GRANT caplab_writer, caplab_reader, caplab_verifier, caplab_custodian
  TO caplab_p5_operator;
GRANT caplab_reader, caplab_verifier TO caplab_p5_verifier;
ALTER ROLE caplab_p5_operator LOGIN;
ALTER ROLE caplab_p5_verifier LOGIN;
"""
    run(
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
            sql,
        ]
    )


def apply_migration(venv: Path) -> None:
    run(
        [
            "runuser",
            "--user",
            "postgres",
            "--",
            str(venv / "bin/python"),
            "-m",
            "caplab.recovery",
            "migrate",
        ]
    )


def secret_key(alias: str) -> dict[str, str]:
    try:
        value = json.loads(
            run(
                ["garage", "json-api", "GetKeyInfo", "-"],
                input_text=json.dumps({"search": alias, "showSecretKey": True}),
            )
        )
    except json.JSONDecodeError as error:
        raise HostctlError("Garage returned an invalid secret-key record") from error
    access = value.get("accessKeyId") if isinstance(value, dict) else None
    secret = value.get("secretAccessKey") if isinstance(value, dict) else None
    if value.get("name") != alias or not isinstance(access, str) or not access.startswith("GK"):
        raise HostctlError("Garage returned the wrong P5 key identity")
    if not isinstance(secret, str) or len(secret) < 16:
        raise HostctlError("Garage returned an invalid P5 secret")
    return {"access_key_id": access, "secret_access_key": secret}


def write_credentials(role: str, credentials: dict[str, str]) -> None:
    identity = pwd.getpwnam(role)
    directory = CREDENTIAL_ROOT / role
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chown(directory, identity.pw_uid, identity.pw_gid)
    os.chmod(directory, 0o700)
    target = directory / "garage.json"
    descriptor = os.open(
        target,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o400,
    )
    try:
        os.write(descriptor, (json.dumps(credentials, sort_keys=True) + "\n").encode())
        os.fchown(descriptor, identity.pw_uid, identity.pw_gid)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def issue_keys(state: dict[str, Any]) -> None:
    seconds = int((EXPIRY - now()).total_seconds())
    for role in ROLES:
        alias = KEY_ALIASES[role]
        state["garage_keys"].append(
            {
                "role": role,
                "alias": alias,
                "access_key_id": None,
            }
        )
        write_state(state)
        run(["garage", "key", "create", "--expires-in", f"{seconds}s", alias])
        credentials = secret_key(alias)
        permissions = ["--read", "--write"] if role == OPERATOR else ["--read"]
        run(
            [
                "garage",
                "bucket",
                "allow",
                *permissions,
                "caplab-v0",
                "--key",
                credentials["access_key_id"],
            ]
        )
        write_credentials(role, credentials)
        state["garage_keys"][-1]["access_key_id"] = credentials["access_key_id"]
        write_state(state)


def prepare_local_copy_prefix() -> None:
    if LOCAL_COPY_PREFIX.is_symlink():
        raise HostctlError("P5 local-copy prefix is a symlink")
    LOCAL_COPY_PREFIX.mkdir(mode=0o750, parents=False, exist_ok=True)
    if next(LOCAL_COPY_PREFIX.iterdir(), None) is not None:
        raise HostctlError("P5 local-copy prefix is not empty before bootstrap")
    operator = pwd.getpwnam(OPERATOR)
    group_id = LOCAL_COPY_ROOT.stat().st_gid
    os.chown(LOCAL_COPY_PREFIX, operator.pw_uid, group_id)
    os.chmod(LOCAL_COPY_PREFIX, 0o750)


def bootstrap() -> None:
    preflight()
    commit = source_commit()
    state: dict[str, Any] = {
        "schema_version": 1,
        "campaign_id": CAMPAIGN_ID,
        "source_commit": commit,
        "phase": "bootstrapping",
        "garage_keys": [],
        "p4_control_before": p4_control(),
        "bootstrapped_at": now().isoformat().replace("+00:00", "Z"),
    }
    write_state(state)
    try:
        ensure_group(GROUP)
        run(["usermod", "--append", "--groups", GROUP, "postgres"])
        for role in ROLES:
            ensure_user(role)
        venv = install_source(commit)
        create_database_roles()
        apply_migration(venv)
        prepare_local_copy_prefix()
        CREDENTIAL_ROOT.mkdir(mode=0o750, parents=True, exist_ok=True)
        os.chown(CREDENTIAL_ROOT, 0, grp.getgrnam(GROUP).gr_gid)
        os.chmod(CREDENTIAL_ROOT, 0o750)
        issue_keys(state)
        run(["systemctl", "enable", "--now", "caplab-p5-expiry.timer"])
        state["phase"] = "ready"
        state["ready_at"] = now().isoformat().replace("+00:00", "Z")
        write_state(state)
        verify("ready")
    except Exception:
        try:
            disable()
        except Exception as disable_error:
            raise HostctlError(
                "P5 bootstrap failed and automatic disablement also failed"
            ) from disable_error
        raise


def verify(expected_phase: str) -> None:
    require_root()
    cfg = config()
    state = read_state()
    if state.get("phase") != expected_phase:
        raise HostctlError(
            f"CAPLAB P5 phase is {state.get('phase')!r}, expected {expected_phase!r}"
        )
    if state.get("source_commit") != source_commit():
        raise HostctlError("CAPLAB P5 state source identity is wrong")
    if p4_control() != state.get("p4_control_before"):
        raise HostctlError("P4 control changed during P5")
    if cfg["identity"]["object_key"] != (
        "objects/sha256/a1/a1ac9f819a8a9e330290910b1049e70fe1a2a73a7ee98068a5fd9fe0c0d8b43d"
    ):
        raise HostctlError("P5 object identity drifted")
    prefix = LOCAL_COPY_PREFIX
    if expected_phase == "ready":
        operator = pwd.getpwnam(OPERATOR)
        metadata = prefix.stat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o750
            or metadata.st_uid != operator.pw_uid
            or metadata.st_gid != LOCAL_COPY_ROOT.stat().st_gid
        ):
            raise HostctlError("P5 local-copy prefix custody is wrong")
    live_ids = {str(key.get("id")) for key in garage_keys()}
    for record in state.get("garage_keys", []):
        role = str(record["role"])
        access = str(record["access_key_id"])
        credential = CREDENTIAL_ROOT / role / "garage.json"
        if expected_phase == "ready":
            if access not in live_ids or not credential.is_file():
                raise HostctlError("P5 Garage access is incomplete")
            metadata = credential.stat()
            identity = pwd.getpwnam(role)
            if (
                stat.S_IMODE(metadata.st_mode) != 0o400
                or metadata.st_uid != identity.pw_uid
                or metadata.st_gid != identity.pw_gid
            ):
                raise HostctlError("P5 Garage credential custody is wrong")
        elif expected_phase == "disabled":
            if access in live_ids or credential.exists():
                raise HostctlError("P5 Garage access remains after disablement")
    role_rows = run(
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
            "SELECT rolname || ':' || rolcanlogin FROM pg_roles "
            "WHERE rolname IN ('caplab_p5_operator','caplab_p5_verifier') "
            "ORDER BY rolname;",
        ]
    ).splitlines()
    expected_login = "true" if expected_phase == "ready" else "false"
    if role_rows != [
        f"{OPERATOR}:{expected_login}",
        f"{VERIFIER}:{expected_login}",
    ]:
        raise HostctlError("P5 PostgreSQL login state is wrong")
    if expected_phase == "ready":
        for role in ROLES:
            observed_role = run(
                [
                    "runuser",
                    "--user",
                    role,
                    "--",
                    "psql",
                    "-X",
                    "--tuples-only",
                    "--no-align",
                    "--dbname",
                    "caplab",
                    "--command",
                    "SELECT current_user;",
                ]
            ).strip()
            if observed_role != role:
                raise HostctlError(f"P5 PostgreSQL peer identity is wrong: {role}")
    timer_active = run(
        ["systemctl", "is-active", "caplab-p5-expiry.timer"],
        allowed=(0, 3),
    ).strip()
    if expected_phase == "ready" and timer_active != "active":
        raise HostctlError("P5 expiry timer is not active")


def disable() -> None:
    require_root()
    state = read_state(required=False)
    failures: list[str] = []
    try:
        keys = garage_keys()
    except HostctlError:
        keys = []
        failures.append("Garage key inventory failed during disablement")
    for role, alias in KEY_ALIASES.items():
        matches = [key for key in keys if key.get("name") == alias]
        if len(matches) > 1:
            failures.append(f"duplicate Garage aliases prevent exact revocation for {role}")
            continue
        if matches:
            access = matches[0].get("id")
            if not isinstance(access, str) or not access.startswith("GK"):
                failures.append(f"Garage key identity is invalid for {role}")
                continue
            try:
                run(["garage", "key", "delete", "--yes", access])
            except HostctlError:
                failures.append(f"Garage key revocation failed for {role}")
    if CREDENTIAL_ROOT.exists():
        try:
            shutil.rmtree(CREDENTIAL_ROOT)
        except OSError:
            failures.append("credential removal failed")
    if LOCAL_COPY_PREFIX.exists():
        try:
            os.chown(LOCAL_COPY_PREFIX, 0, LOCAL_COPY_ROOT.stat().st_gid)
            os.chmod(LOCAL_COPY_PREFIX, 0o750)
            if next(LOCAL_COPY_PREFIX.iterdir(), None) is None:
                LOCAL_COPY_PREFIX.rmdir()
        except OSError:
            failures.append("local-copy prefix revocation failed")
    sql = """
DO $p5$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caplab_p5_operator') THEN
    ALTER ROLE caplab_p5_operator NOLOGIN;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'caplab_p5_verifier') THEN
    ALTER ROLE caplab_p5_verifier NOLOGIN;
  END IF;
END
$p5$;
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE usename IN ('caplab_p5_operator','caplab_p5_verifier')
AND pid <> pg_backend_pid();
"""
    try:
        run(
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
                sql,
            ]
        )
    except HostctlError:
        failures.append("PostgreSQL role disablement failed")
    for role in ROLES:
        if _user_exists(role):
            try:
                run(["usermod", "--lock", "--expiredate", "1", role])
            except HostctlError:
                failures.append(f"operating-system identity disablement failed for {role}")
    try:
        run(["systemctl", "disable", "--now", "caplab-p5-expiry.timer"])
    except HostctlError:
        failures.append("expiry timer disablement failed")
    state.update(
        {
            "schema_version": 1,
            "campaign_id": CAMPAIGN_ID,
            "source_commit": state.get("source_commit", source_commit()),
            "phase": "disable-failed" if failures else "disabled",
            "garage_keys": state.get("garage_keys", []),
            "p4_control_before": state.get("p4_control_before", p4_control()),
            "disabled_at": now().isoformat().replace("+00:00", "Z"),
        }
    )
    if failures:
        state["disable_failures"] = failures
    else:
        state.pop("disable_failures", None)
    write_state(state)
    if failures:
        raise HostctlError("; ".join(failures))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight", help="validate the frozen source and live host")
    subparsers.add_parser("bootstrap", help="create temporary P5 identities and access")
    verify_parser = subparsers.add_parser("verify", help="verify a lifecycle phase")
    verify_parser.add_argument("--phase", choices=("ready", "disabled"), required=True)
    subparsers.add_parser("disable", help="revoke temporary P5 identities and access")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv or sys.argv[1:])
    try:
        if arguments.command == "preflight":
            preflight()
            print(f"CAPLAB P5 preflight passed at {source_commit()}")
        elif arguments.command == "bootstrap":
            bootstrap()
            print(f"CAPLAB P5 host surface ready at {source_commit()}")
        elif arguments.command == "verify":
            verify(arguments.phase)
            print(f"verified CAPLAB P5 host phase: {arguments.phase}")
        elif arguments.command == "disable":
            disable()
            print("disabled CAPLAB P5 host access")
        return 0
    except HostctlError as error:
        print(f"caplab-p5-hostctl: {error}", file=sys.stderr)
        return 2
    except Exception:
        print(
            "caplab-p5-hostctl: unexpected failure; no lifecycle phase was declared successful",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
