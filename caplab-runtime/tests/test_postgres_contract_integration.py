import importlib.util
import os
import subprocess
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

SUBSYSTEM_DIR = Path(__file__).resolve().parents[1]
HOSTCTL = SUBSYSTEM_DIR / "caplab-hostctl.py"
CAPLAB_REPO = Path("/home/halbritt/git/caplab")


def load_hostctl():
    specification = importlib.util.spec_from_file_location("caplab_hostctl_pg", HOSTCTL)
    if specification is None or specification.loader is None:
        raise RuntimeError("could not load caplab-hostctl.py")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


class EphemeralPostgresRunner:
    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        del secret_output
        command = arguments
        if arguments[:4] == ["runuser", "--user", "postgres", "--"]:
            command = arguments[4:]
        completed = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            env=os.environ,
        )
        if completed.returncode not in allowed_returncodes:
            raise RuntimeError(
                f"ephemeral command failed with {completed.returncode}: {completed.stderr}"
            )
        return completed.stdout


@unittest.skipUnless(
    os.environ.get("CAPLAB_RUN_PG_INTEGRATION") == "1",
    "set CAPLAB_RUN_PG_INTEGRATION=1 inside pg_virtualenv",
)
class PostgresContractIntegrationTests(unittest.TestCase):
    def test_migration_matches_the_exact_host_privilege_contract(self) -> None:
        hostctl = load_hostctl()
        runner = EphemeralPostgresRunner()
        role_sql = (
            "CREATE ROLE caplab_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOINHERIT NOREPLICATION NOBYPASSRLS; "
            "CREATE ROLE caplab_writer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD NULL; "
            "CREATE ROLE caplab_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD NULL; "
            "CREATE ROLE caplab_verifier NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD NULL;"
        )
        runner.run(["psql", "-X", "-v", "ON_ERROR_STOP=1", "-c", role_sql])
        runner.run(["createdb", "--owner=caplab_owner", "caplab"])
        boundary_sql = (
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
        runner.run(["psql", "-X", "-v", "ON_ERROR_STOP=1", "-c", boundary_sql])
        source_commit = (SUBSYSTEM_DIR / "SOURCE_COMMIT").read_text(encoding="ascii").strip()
        migration = runner.run(
            [
                "git",
                "-C",
                str(CAPLAB_REPO),
                "show",
                f"{source_commit}:src/caplab/runtime/migrations/0001_runtime_core.sql",
            ]
        )
        runner.run(
            ["psql", "-X", "-v", "ON_ERROR_STOP=1", "--dbname", "caplab"],
            input_text="BEGIN; SET LOCAL ROLE caplab_owner;\n" + migration + "\nCOMMIT;\n",
        )
        controller = hostctl.HostController(
            paths=hostctl.HostPaths(),
            runner=runner,
            identity_resolver=lambda _role: (os.getuid(), os.getgid()),
            clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
        )

        controller._verify_postgres_contract(expected_login=False)


if __name__ == "__main__":
    unittest.main()
