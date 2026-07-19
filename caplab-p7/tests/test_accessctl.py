"""Contracts for the CAPLAB P7 reader-access lifecycle."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "caplab-p7-accessctl.py"
SPEC = importlib.util.spec_from_file_location("caplab_p7_accessctl", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
accessctl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(accessctl)


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.aliases: dict[str, dict[str, object]] = {}
        self.role_login = False
        self.sessions = 0
        self.account_expiry = "1"
        self.passwords_unusable = True
        self.roles_present = True
        self.writer_login = False
        self.verifier_login = False
        self.writer_verifier_sessions = 0
        self.reader_write_authorities = 0
        self.listener_loopback_only = True

    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        self.commands.append(arguments)
        if arguments == ["systemctl", "is-enabled", "caplab-p7-expiry.timer"]:
            return "enabled\n"
        if arguments == ["systemctl", "is-active", "caplab-p7-expiry.timer"]:
            return "active\n"
        if arguments[:3] == ["garage", "json-api", "ListKeys"]:
            return json.dumps(
                [
                    {"id": record["accessKeyId"], "name": name}
                    for name, record in self.aliases.items()
                ]
            )
        if arguments[:3] == ["garage", "key", "create"]:
            alias = arguments[-1]
            self.aliases[alias] = {
                "accessKeyId": "GK-P7-READER",
                "secretAccessKey": "TEST-SECRET-READER-1234",
                "expiration": "2026-07-25T23:59:59Z",
            }
            return "secret output must be discarded"
        if arguments[:3] == ["garage", "json-api", "GetKeyInfo"]:
            request = json.loads(input_text or "")
            record = self.aliases[request["search"]]
            response = {
                "accessKeyId": record["accessKeyId"],
                "name": request["search"],
                "expiration": record["expiration"],
                "expired": False,
                "permissions": {"createBucket": False},
                "buckets": [
                    {
                        "globalAliases": ["caplab-v0"],
                        "id": "85b5ca4bbb912841999ca5f44a77bddc4fc97ab84635d665d00e05b322b866f1",
                        "localAliases": [],
                        "permissions": {"owner": False, "read": True, "write": False},
                    }
                ],
            }
            if request["showSecretKey"]:
                response["secretAccessKey"] = record["secretAccessKey"]
            return json.dumps(response)
        if arguments[:3] == ["garage", "bucket", "allow"]:
            return ""
        if arguments[:3] == ["garage", "key", "delete"]:
            key_id = arguments[-1]
            for alias, record in list(self.aliases.items()):
                if record["accessKeyId"] == key_id:
                    del self.aliases[alias]
            return ""
        if arguments[0] == "usermod":
            self.account_expiry = arguments[arguments.index("--expiredate") + 1]
            return ""
        if arguments[0] == "pkill":
            return ""
        if arguments[:5] == ["runuser", "--user", "postgres", "--", "psql"]:
            sql = arguments[-1]
            if "ALTER ROLE caplab_reader LOGIN" in sql:
                self.role_login = True
            if "ALTER ROLE caplab_reader NOLOGIN" in sql:
                self.role_login = False
                self.sessions = 0
            if "passwords_unusable" in sql:
                return "|".join(
                    (
                        "t" if self.role_login else "f",
                        "t" if self.writer_login else "f",
                        "t" if self.verifier_login else "f",
                        "t" if self.passwords_unusable and self.roles_present else "f",
                        str(self.sessions),
                        str(self.writer_verifier_sessions),
                        str(self.reader_write_authorities),
                        "t" if self.listener_loopback_only else "f",
                    )
                ) + "\n"
            if "rolcanlogin" in sql:
                return f"{'t' if self.role_login else 'f'}|{self.sessions}\n"
            return ""
        raise AssertionError(f"unexpected command: {arguments}")


class AccessLifecycleTests(unittest.TestCase):
    def controller(self, root: Path, runner: FakeRunner):
        credential_dir = root / "credentials" / "caplab_reader"
        credential_dir.mkdir(parents=True)
        source_commit = root / "P7_SOURCE_COMMIT"
        source_commit.write_text(accessctl.CAPLAB_SOURCE_COMMIT + "\n")
        config = root / "recomputation.toml"
        config.write_text(
            "[authorization]\n"
            f'campaign_id = "{accessctl.CAMPAIGN_ID}"\n'
            'expires_at = "2026-07-25T23:59:59Z"\n'
            f'source_commit = "{accessctl.CAPLAB_SOURCE_COMMIT}"\n'
            f'admission_manifest_sha256 = "{accessctl.ADMISSION_MANIFEST_SHA256}"\n'
        )
        runtime_python = root / "runtime-python"
        runtime_python.touch(mode=0o750)
        return accessctl.HostController(
            accessctl.Paths(
                state_file=root / "state.json",
                credential_file=credential_dir / "garage.json",
                source_commit_file=source_commit,
                config_file=config,
                runtime_python=runtime_python,
            ),
            runner=runner,
            clock=lambda: datetime(2026, 7, 18, tzinfo=UTC),
            identity_resolver=lambda _role: (os.getuid(), os.getgid()),
        )

    def test_enable_issues_only_one_expiring_read_only_reader_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = FakeRunner()
            controller = self.controller(root, runner)

            controller.enable()
            controller.verify("ready")

            state = json.loads((root / "state.json").read_text())
            credential = json.loads(
                (root / "credentials/caplab_reader/garage.json").read_text()
            )
            self.assertEqual(state["phase"], "ready")
            self.assertEqual(state["garage_key"]["alias"], "caplab-p7-reader")
            self.assertNotIn("secret", json.dumps(state).lower())
            self.assertEqual(credential["access_key_id"], "GK-P7-READER")
            self.assertTrue(runner.role_login)
            bucket_allow = next(
                command
                for command in runner.commands
                if command[:3] == ["garage", "bucket", "allow"]
            )
            self.assertIn("--read", bucket_allow)
            self.assertNotIn("--write", bucket_allow)
            self.assertFalse(
                any("caplab_writer" in command or "caplab_verifier" in command for command in runner.commands)
            )

    def test_source_pin_drift_stops_before_key_issue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = FakeRunner()
            controller = self.controller(root, runner)
            controller.paths.source_commit_file.write_text("f" * 40 + "\n")

            with self.assertRaisesRegex(accessctl.HostctlError, "source commit"):
                controller.enable()

            self.assertFalse(
                any(command[:3] == ["garage", "key", "create"] for command in runner.commands)
            )

    def test_disable_discovers_the_live_alias_when_state_is_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = FakeRunner()
            controller = self.controller(root, runner)
            controller.enable()
            (root / "state.json").write_text("not-json")

            with self.assertRaisesRegex(accessctl.HostctlError, "state_read"):
                controller.disable()

            self.assertFalse(runner.role_login)
            self.assertEqual(runner.aliases, {})
            self.assertFalse((root / "credentials/caplab_reader/garage.json").exists())
            self.assertEqual(runner.account_expiry, "1")

    def test_ready_verification_rejects_write_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = FakeRunner()
            controller = self.controller(root, runner)
            controller.enable()
            runner.aliases["caplab-p7-reader"]["write"] = True

            original = runner.run

            def widened(arguments, **kwargs):
                response = original(arguments, **kwargs)
                if arguments[:3] == ["garage", "json-api", "GetKeyInfo"]:
                    document = json.loads(response)
                    document["buckets"][0]["permissions"]["write"] = True
                    return json.dumps(document)
                return response

            runner.run = widened
            with self.assertRaisesRegex(accessctl.HostctlError, "bucket authority"):
                controller.verify("ready")

    def test_ready_verification_rejects_a_local_bucket_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = FakeRunner()
            controller = self.controller(root, runner)
            controller.enable()

            original = runner.run

            def widened(arguments, **kwargs):
                response = original(arguments, **kwargs)
                if arguments[:3] == ["garage", "json-api", "GetKeyInfo"]:
                    document = json.loads(response)
                    document["buckets"][0]["localAliases"] = ["unexpected"]
                    return json.dumps(document)
                return response

            runner.run = widened
            with self.assertRaisesRegex(accessctl.HostctlError, "bucket authority"):
                controller.verify("ready")

    def test_ready_verification_accepts_unusable_postgres_password_markers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = FakeRunner()
            controller = self.controller(root, runner)

            controller.enable()
            controller.verify("ready")

    def test_ready_verification_rejects_every_widened_postgres_boundary(self) -> None:
        scenarios = (
            ("passwords_unusable", False),
            ("roles_present", False),
            ("writer_login", True),
            ("verifier_login", True),
            ("writer_verifier_sessions", 1),
            ("reader_write_authorities", 1),
            ("listener_loopback_only", False),
        )
        for attribute, widened_value in scenarios:
            with self.subTest(attribute=attribute), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                runner = FakeRunner()
                controller = self.controller(root, runner)
                controller.enable()
                setattr(runner, attribute, widened_value)

                with self.assertRaisesRegex(
                    accessctl.HostctlError, "access boundary is not ready"
                ):
                    controller.verify("ready")


class CommandSurfaceTests(unittest.TestCase):
    def test_cli_exposes_only_reader_access_lifecycle_commands(self) -> None:
        help_text = accessctl.build_parser().format_help().lower()

        for command in ("enable", "verify", "disable"):
            self.assertIn(command, help_text)
        for forbidden in ("write", "admit", "infer", "export", "train", "accept"):
            self.assertNotIn(forbidden, help_text)

    def test_expiry_backstop_retries_only_aggregate_disable(self) -> None:
        unit = (MODULE_PATH.parent / "caplab-p7-expiry.service").read_text()

        self.assertIn("ExecStart=/usr/local/libexec/caplab-p7-accessctl disable", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertNotIn(" enable", unit)


if __name__ == "__main__":
    unittest.main()
