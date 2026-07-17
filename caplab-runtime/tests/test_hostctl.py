import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from datetime import UTC, datetime
from pathlib import Path

SUBSYSTEM_DIR = Path(__file__).resolve().parents[1]
HOSTCTL = SUBSYSTEM_DIR / "caplab-hostctl.py"


def load_hostctl():
    specification = importlib.util.spec_from_file_location("caplab_hostctl", HOSTCTL)
    if specification is None or specification.loader is None:
        raise RuntimeError("could not load caplab-hostctl.py")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def write_runtime_config(root: Path, source_commit: str) -> None:
    provisional_commit = (SUBSYSTEM_DIR / "SOURCE_COMMIT").read_text(encoding="ascii").strip()
    (root / "runtime.toml").write_text(
        (SUBSYSTEM_DIR / "runtime.toml")
        .read_text(encoding="utf-8")
        .replace(provisional_commit, source_commit),
        encoding="utf-8",
    )


def make_source_package(root: Path) -> tuple[Path, Path]:
    source_package = root / "source/src/caplab"
    runtime = source_package / "runtime"
    migrations = runtime / "migrations"
    migrations.mkdir(parents=True)
    (source_package / "__init__.py").write_text("", encoding="ascii")
    (runtime / "__init__.py").write_text("", encoding="ascii")
    requirements_lock = runtime / "requirements.lock"
    requirements_lock.write_text(
        "boto3==1.34.46 --hash=sha256:" + "a" * 64 + "\n",
        encoding="ascii",
    )
    (migrations / "0001_runtime_core.sql").write_text("SELECT 1;\n", encoding="ascii")
    return source_package, requirements_lock


def make_source_repo(root: Path) -> tuple[Path, Path, Path, str]:
    source_repo = root / "source"
    source_package, requirements_lock = make_source_package(root)
    subprocess.run(["git", "init", "-q", str(source_repo)], check=True)
    subprocess.run(
        ["git", "-C", str(source_repo), "config", "user.name", "Test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(source_repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(source_repo), "add", "src/caplab"], check=True)
    subprocess.run(
        ["git", "-C", str(source_repo), "commit", "-qm", "runtime"],
        check=True,
    )
    commit = subprocess.run(
        ["git", "-C", str(source_repo), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    return source_repo, source_package, requirements_lock, commit


def make_installed_venv(
    hostctl,
    root: Path,
    source_commit: str,
) -> tuple[Path, str, str]:
    source_package, requirements_lock = make_source_package(root)
    lock_hash = hashlib.sha256(requirements_lock.read_bytes()).hexdigest()
    venv_root = root / "venvs"
    environment = venv_root / lock_hash
    python = environment / "bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="ascii")
    python.chmod(0o750)
    purelib = environment / "lib/python3.12/site-packages"
    purelib.mkdir(parents=True)
    shutil.copytree(source_package, purelib / "caplab")
    installed = hostctl.HostController._source_tree_manifest(source_package)
    manifest = {
        "schema_version": 1,
        "source_commit": source_commit,
        "files": [],
    }
    for entry in installed["files"]:
        payload = (source_package / entry["path"]).read_bytes()
        git_object = hashlib.sha1(
            f"blob {len(payload)}\0".encode("ascii") + payload,
            usedforsecurity=False,
        ).hexdigest()
        manifest["files"].append({**entry, "git_object": git_object})
    manifest_bytes = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    (purelib / "caplab-source-manifest.json").write_bytes(manifest_bytes)
    return venv_root, lock_hash, hashlib.sha256(manifest_bytes).hexdigest()


class HostctlCommandTests(unittest.TestCase):
    def test_checked_in_source_pin_names_the_reviewed_runtime_commit(self) -> None:
        self.assertEqual(
            "405efb136b221d1270578417c64b3f7878383f32",
            (SUBSYSTEM_DIR / "SOURCE_COMMIT").read_text(encoding="ascii").strip(),
        )

    def test_cli_exposes_only_the_authorized_host_lifecycle(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(HOSTCTL), "--help"],
            text=True,
            capture_output=True,
            check=True,
        )

        for command in (
            "preflight",
            "bootstrap",
            "issue-credentials",
            "arm-effects",
            "capture-inventory",
            "verify",
            "disable",
            "rollback-empty",
        ):
            self.assertIn(command, completed.stdout)
        self.assertNotIn("purge", completed.stdout)
        self.assertNotIn("delete-object", completed.stdout)

    def test_runtime_config_freezes_only_non_secret_p4_namespaces(self) -> None:
        config_file = SUBSYSTEM_DIR / "runtime.toml"
        config_bytes = config_file.read_bytes()
        config = tomllib.loads(config_bytes.decode("utf-8"))

        source_commit = (SUBSYSTEM_DIR / "SOURCE_COMMIT").read_text(encoding="ascii").strip()
        self.assertEqual("caplab-p4-roundtrip-2026-07-15", config["runtime"]["campaign_id"])
        self.assertEqual(
            "2026-07-22T23:59:59Z",
            config["runtime"]["authorization_expires_at"],
        )
        self.assertEqual(source_commit, config["runtime"]["runtime_commit"])
        self.assertEqual(
            "dbname=caplab host=/var/run/postgresql",
            config["postgres"]["conninfo"],
        )
        self.assertEqual("caplab-v0", config["garage"]["bucket"])
        self.assertEqual("/etc/caplab/credentials", config["garage"]["credentials_root"])
        self.assertEqual("/nvr/caplab/v0", config["local_copy"]["root"])
        lowered = config_bytes.lower()
        self.assertNotIn(b"secret", lowered)
        self.assertNotIn(b"password", lowered)

    def test_runtime_config_drift_is_rejected_before_host_commands(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            runtime_config = Path(directory) / "runtime.toml"
            runtime_config.write_text(
                (SUBSYSTEM_DIR / "runtime.toml")
                .read_text(encoding="utf-8")
                .replace('bucket = "caplab-v0"', 'bucket = "caplab-drift"'),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(hostctl.HostctlError, "canonical runtime config differs"):
                hostctl.HostController._validate_runtime_config(
                    runtime_config,
                    "2d5d9d76b643827aa9ed77824a630dc76c1bbfe3",
                )

    def test_expiry_timer_invokes_only_the_disable_command_before_expiry(self) -> None:
        service = (SUBSYSTEM_DIR / "caplab-p4-expiry.service").read_text(encoding="utf-8")
        timer = (SUBSYSTEM_DIR / "caplab-p4-expiry.timer").read_text(encoding="utf-8")

        self.assertIn("ExecStart=/usr/local/libexec/caplab-hostctl disable", service)
        self.assertIn("Restart=on-failure", service)
        self.assertNotIn("ConditionPathExists", service)
        self.assertNotIn("issue-credentials", service)
        self.assertNotIn("bootstrap", service)
        self.assertIn("OnCalendar=2026-07-22 23:50:00 UTC", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("AccuracySec=1s", timer)

    def test_preflight_refuses_a_pinned_commit_without_the_runtime_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_repo = Path(directory) / "caplab"
            source_repo.mkdir()
            subprocess.run(["git", "init", "-q", str(source_repo)], check=True)
            subprocess.run(
                ["git", "-C", str(source_repo), "config", "user.name", "Test"],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source_repo),
                    "config",
                    "user.email",
                    "test@example.invalid",
                ],
                check=True,
            )
            (source_repo / "pyproject.toml").write_text(
                "[project]\nname = 'agent-capability-lab'\n",
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "-C", str(source_repo), "add", "pyproject.toml"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(source_repo), "commit", "-qm", "structure"],
                check=True,
            )
            commit = subprocess.run(
                ["git", "-C", str(source_repo), "rev-parse", "HEAD"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            source_commit_file = Path(directory) / "SOURCE_COMMIT"
            source_commit_file.write_text(commit + "\n", encoding="ascii")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(HOSTCTL),
                    "--source-commit-file",
                    str(source_commit_file),
                    "--source-repo",
                    str(source_repo),
                    "preflight",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(1, completed.returncode)
            self.assertIn("lacks the hash-locked runtime", completed.stderr)
            self.assertNotIn("Traceback", completed.stderr)
            self.assertEqual("", completed.stdout)

    def test_arming_effects_permanently_refuses_empty_resource_rollback(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            source_commit_file = scratch / "SOURCE_COMMIT"
            source_commit_file.write_text("1" * 40 + "\n", encoding="ascii")
            state_file = scratch / "state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": "caplab-p4-roundtrip-2026-07-15",
                        "phase": "ready",
                        "effects_armed": False,
                    }
                ),
                encoding="utf-8",
            )

            hostctl.arm_effects(state_file, datetime(2026, 7, 15, tzinfo=UTC))
            persisted = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertTrue(persisted["effects_armed"])
            self.assertEqual("armed", persisted["phase"])
            self.assertEqual(0o600, os.stat(state_file).st_mode & 0o777)

            rollback = subprocess.run(
                [
                    sys.executable,
                    str(HOSTCTL),
                    "--source-commit-file",
                    str(source_commit_file),
                    "--state-file",
                    str(state_file),
                    "rollback-empty",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(1, rollback.returncode)
            self.assertIn("synthetic-effect boundary is armed", rollback.stderr)

    def test_expired_authorization_cannot_arm_synthetic_effects(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": hostctl.CAMPAIGN_ID,
                        "phase": "ready",
                        "effects_armed": False,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(hostctl.HostctlError, "authorization has expired"):
                hostctl.arm_effects(state_file, datetime(2026, 7, 23, tzinfo=UTC))

            persisted = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual("ready", persisted["phase"])
            self.assertFalse(persisted["effects_armed"])

    def test_credential_issue_keeps_secrets_out_of_output_and_state(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            credential_root = scratch / "credentials"
            for role in hostctl.RUNTIME_ROLES:
                (credential_root / role).mkdir(parents=True)
            state_file = scratch / "state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": hostctl.CAMPAIGN_ID,
                        "phase": "base",
                        "effects_armed": False,
                        "garage_keys": [],
                    }
                ),
                encoding="utf-8",
            )
            runner = FakeGarageRunner()
            paths = hostctl.HostPaths(
                state_file=state_file,
                credential_root=credential_root,
            )
            controller = hostctl.HostController(
                paths=paths,
                runner=runner,
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                controller.issue_credentials()

            credential_text = ""
            for role in hostctl.RUNTIME_ROLES:
                credential_file = credential_root / role / "garage.json"
                self.assertEqual(0o400, os.stat(credential_file).st_mode & 0o777)
                credential_document = json.loads(credential_file.read_text(encoding="ascii"))
                self.assertEqual(
                    {"access_key_id", "secret_access_key"},
                    set(credential_document),
                )
                credential_text += json.dumps(credential_document)
            persisted_state = state_file.read_text(encoding="utf-8")
            self.assertIn("TEST-SECRET-caplab_writer", credential_text)
            self.assertNotIn("TEST-SECRET", persisted_state)
            self.assertNotIn("TEST-SECRET", stdout.getvalue())
            self.assertNotIn("TEST-SECRET", stderr.getvalue())
            self.assertEqual("ready", json.loads(persisted_state)["phase"])
            command_text = "\n".join(" ".join(command) for command in runner.commands)
            self.assertIn("systemctl is-enabled caplab-p4-expiry.timer", command_text)
            self.assertIn("systemctl is-active caplab-p4-expiry.timer", command_text)

    def test_partial_key_issue_disables_access_and_removes_credentials(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            credential_root = scratch / "credentials"
            for role in hostctl.RUNTIME_ROLES:
                (credential_root / role).mkdir(parents=True)
            state_file = scratch / "state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": hostctl.CAMPAIGN_ID,
                        "phase": "base",
                        "effects_armed": False,
                        "garage_keys": [],
                    }
                ),
                encoding="utf-8",
            )
            runner = FailingGarageRunner(hostctl)
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(
                    state_file=state_file,
                    credential_root=credential_root,
                ),
                runner=runner,
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            with self.assertRaisesRegex(hostctl.HostctlError, "simulated key failure"):
                controller.issue_credentials()

            persisted = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual("disabled", persisted["phase"])
            self.assertFalse(any(credential_root.rglob("garage.json")))
            self.assertIn("GK-TEST-writer", runner.deleted_keys)

    def test_secret_subprocess_failure_suppresses_command_output(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            command = Path(directory) / "secret-failure"
            command.write_text(
                "#!/bin/sh\nprintf 'TEST-SECRET-STDOUT\\n'\n"
                "printf 'TEST-SECRET-STDERR\\n' >&2\nexit 7\n",
                encoding="ascii",
            )
            command.chmod(0o700)
            runner = hostctl.SubprocessRunner()

            with self.assertRaises(hostctl.HostctlError) as raised:
                runner.run([str(command)], secret_output=True)

            message = str(raised.exception)
            self.assertNotIn("TEST-SECRET", message)
            self.assertIn("exit 7", message)

    def test_host_preflight_refuses_an_existing_target_before_mutation(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            paths = hostctl.HostPaths(
                state_file=scratch / "etc/campaigns/state.json",
                credential_root=scratch / "etc/credentials",
                etc_root=scratch / "etc",
                venv_root=scratch / "opt/caplab/venvs",
                nvr_root=scratch / "nvr/caplab/v0",
            )
            runner = ExistingGroupRunner()

            with self.assertRaisesRegex(hostctl.HostctlError, "group caplab exists"):
                hostctl.preflight_host(paths, runner)

            self.assertFalse(runner.mutation_attempted)

    def test_host_preflight_checks_live_stores_and_nvr_before_bootstrap(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            runner = HealthyEmptyHostRunner()

            hostctl.preflight_host(
                hostctl.HostPaths(
                    state_file=scratch / "state.json",
                    credential_root=scratch / "etc/credentials",
                    etc_root=scratch / "etc",
                    venv_root=scratch / "opt/caplab/venvs",
                    nvr_root=scratch / "nvr/caplab/v0",
                ),
                runner,
            )

            command_text = "\n".join(" ".join(command) for command in runner.commands)
            self.assertIn("systemctl is-active postgresql.service", command_text)
            self.assertIn("systemctl is-active garage.service", command_text)
            self.assertIn("garage json-api ListBuckets null", command_text)
            self.assertIn("garage json-api ListKeys null", command_text)
            self.assertIn("findmnt --noheadings --output FSTYPE --target /nvr", command_text)
            self.assertIn("pg_hba_file_rules", command_text)

    def test_base_bootstrap_records_identity_without_issuing_keys(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            state_file = scratch / "state" / "state.json"
            state_file.parent.mkdir()
            paths = hostctl.HostPaths(
                state_file=state_file,
                credential_root=scratch / "etc/caplab/credentials",
                etc_root=scratch / "etc/caplab",
                venv_root=scratch / "opt/caplab/venvs",
                nvr_root=scratch / "nvr/caplab/v0",
                staging_root=scratch,
            )
            source_repo, _source_package, requirements_lock, source_commit = make_source_repo(
                scratch
            )
            source_pin = scratch / "SOURCE_COMMIT"
            source_pin.write_text(source_commit + "\n", encoding="ascii")
            runtime_config = scratch / "runtime.toml"
            write_runtime_config(scratch, source_commit)
            runner = BootstrapRunner(scratch)
            controller = hostctl.HostController(
                paths=paths,
                runner=runner,
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            controller.bootstrap_base(
                source_commit=source_commit,
                source_pin=source_pin,
                runtime_config=runtime_config,
                source_repo=source_repo,
            )

            persisted = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual("base", persisted["phase"])
            self.assertEqual(source_commit, persisted["source_commit"])
            self.assertEqual(
                __import__("hashlib").sha256(requirements_lock.read_bytes()).hexdigest(),
                persisted["requirements_lock_sha256"],
            )
            self.assertRegex(persisted["source_tree_manifest_sha256"], r"\A[0-9a-f]{64}\Z")
            self.assertTrue(persisted["source_worktree_clean"])
            self.assertEqual("Python 3.12.0", persisted["runtime_interpreter"]["version"])
            packaged_runtime = runner.purelib / "caplab/runtime"
            self.assertEqual(
                requirements_lock.read_bytes(),
                (packaged_runtime / "requirements.lock").read_bytes(),
            )
            self.assertTrue((packaged_runtime / "migrations/0001_runtime_core.sql").is_file())
            flattened = [argument for command in runner.commands for argument in command]
            self.assertNotIn("create-key", flattened)
            self.assertNotIn("LOGIN", flattened)
            command_text = "\n".join(" ".join(command) for command in runner.commands)
            self.assertIn("/usr/bin/setfacl --modify user:postgres:--x", command_text)
            self.assertIn("/usr/bin/setfacl --modify user:postgres:r--", command_text)
            self.assertIn(
                f"/usr/bin/setfacl --modify user:postgres:--x {paths.venv_root.parent}",
                command_text,
            )
            self.assertIn(
                "/usr/bin/setfacl --physical --recursive --modify user:postgres:rX "
                f"{paths.venv_root / persisted['requirements_lock_sha256']}",
                command_text,
            )
            useradd_commands = [command for command in runner.commands if command[0] == "useradd"]
            self.assertEqual(3, len(useradd_commands))
            for role, command in zip(hostctl.RUNTIME_ROLES, useradd_commands, strict=True):
                self.assertEqual(1, command.count("/nonexistent"))
                self.assertEqual(role, command[-1])

    def test_failed_venv_build_removes_its_private_stage(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            source_repo, _source_package, requirements_lock, source_commit = make_source_repo(
                scratch
            )
            runner = FailingVenvRunner(scratch, hostctl)
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(staging_root=scratch),
                runner=runner,
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            pinned_files = controller._read_pinned_git_package(source_repo, source_commit)
            with self.assertRaisesRegex(hostctl.HostctlError, "simulated pip failure"):
                controller._build_venv_stage(
                    pinned_files,
                    source_commit,
                    requirements_lock.read_bytes(),
                )

            self.assertFalse(runner.stage.exists())

    def test_initial_state_write_failure_removes_the_completed_venv_stage(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            source_repo, _source_package, _requirements_lock, source_commit = make_source_repo(
                scratch
            )
            source_pin = scratch / "SOURCE_COMMIT"
            source_pin.write_text(source_commit + "\n", encoding="ascii")
            write_runtime_config(scratch, source_commit)
            runner = BootstrapRunner(scratch)
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(
                    state_file=scratch / "state.json",
                    staging_root=scratch,
                ),
                runner=runner,
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            original_write_state = hostctl.write_state

            def fail_initial_state_write(_path, _state):
                raise hostctl.HostctlError("simulated initial state failure")

            hostctl.write_state = fail_initial_state_write
            try:
                with self.assertRaisesRegex(
                    hostctl.HostctlError,
                    "simulated initial state failure",
                ):
                    controller.bootstrap_base(
                        source_commit=source_commit,
                        source_pin=source_pin,
                        runtime_config=scratch / "runtime.toml",
                        source_repo=source_repo,
                    )
            finally:
                hostctl.write_state = original_write_state

            stages = list(scratch.glob("caplab-venv.*"))
            self.assertEqual([], stages)
            command_text = "\n".join(" ".join(command) for command in runner.commands)
            self.assertNotIn("groupadd", command_text)

    def test_source_package_manifest_rejects_symlinks(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            source_repo, source_package, _requirements_lock, source_commit = make_source_repo(
                scratch
            )
            (source_package / "escape").symlink_to("/etc/passwd")
            subprocess.run(["git", "-C", str(source_repo), "add", "src/caplab/escape"], check=True)
            subprocess.run(
                ["git", "-C", str(source_repo), "commit", "-qm", "symlink"],
                check=True,
            )
            source_commit = subprocess.run(
                ["git", "-C", str(source_repo), "rev-parse", "HEAD"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(staging_root=scratch),
                runner=BootstrapRunner(scratch),
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            with self.assertRaisesRegex(hostctl.HostctlError, "non-regular file"):
                controller._read_pinned_git_package(source_repo, source_commit)

    def test_source_install_excludes_generated_python_state(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            source_repo, source_package, requirements_lock, source_commit = make_source_repo(
                scratch
            )
            generated = source_package / "runtime/__pycache__/generated.cpython-312.pyc"
            generated.parent.mkdir()
            generated.write_bytes(b"generated")
            purelib = scratch / "purelib"
            purelib.mkdir()
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(staging_root=scratch),
                runner=BootstrapRunner(scratch),
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            pinned_files = controller._read_pinned_git_package(source_repo, source_commit)
            controller._install_pinned_package(
                pinned_files,
                source_commit,
                requirements_lock.read_bytes(),
                purelib,
            )

            installed = purelib / "caplab/runtime/__pycache__/generated.cpython-312.pyc"
            self.assertFalse(installed.exists())

    def test_source_manifest_uses_git_path_order_for_sibling_module_and_package(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            source_package = Path(directory) / "caplab"
            package = source_package / "runtime/migrations"
            package.mkdir(parents=True)
            (source_package / "runtime/migrations.py").write_text("# module\n", encoding="ascii")
            (package / "0001.sql").write_text("SELECT 1;\n", encoding="ascii")

            manifest = hostctl.HostController._source_tree_manifest(source_package)

            self.assertEqual(
                ["runtime/migrations.py", "runtime/migrations/0001.sql"],
                [entry["path"] for entry in manifest["files"]],
            )

    def test_empty_rollback_removes_only_verified_bootstrap_resources(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            state_file = scratch / "state/state.json"
            state_file.parent.mkdir()
            etc_root = scratch / "etc/caplab"
            venv_root = scratch / "opt/caplab/venvs"
            nvr_root = scratch / "nvr/caplab/v0"
            for path in (etc_root, venv_root, nvr_root):
                path.mkdir(parents=True)
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": hostctl.CAMPAIGN_ID,
                        "phase": "disabled",
                        "effects_armed": False,
                        "garage_keys": [],
                        "created_resources": {
                            "common_group": True,
                            "runtime_identities": True,
                            "host_paths": True,
                            "venv": True,
                            "postgres": True,
                            "garage_bucket": True,
                        },
                    }
                ),
                encoding="utf-8",
            )
            runner = RollbackRunner()
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(
                    state_file=state_file,
                    credential_root=etc_root / "credentials",
                    etc_root=etc_root,
                    venv_root=venv_root,
                    nvr_root=nvr_root,
                ),
                runner=runner,
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            controller.rollback_empty()

            self.assertFalse(etc_root.exists())
            self.assertFalse(venv_root.exists())
            self.assertFalse(nvr_root.exists())
            self.assertFalse(venv_root.parent.exists())
            self.assertFalse(nvr_root.parent.exists())
            command_text = "\n".join(" ".join(command) for command in runner.commands)
            self.assertIn("garage bucket delete --yes caplab-v0", command_text)
            self.assertIn("dropdb caplab", command_text)
            self.assertNotIn("DELETE FROM", command_text)
            self.assertNotIn("object delete", command_text)

    def test_disabled_verification_requires_revoked_roles_keys_and_files(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            etc_root = scratch / "etc/caplab"
            credential_root = etc_root / "credentials"
            for role in hostctl.RUNTIME_ROLES:
                (credential_root / role).mkdir(parents=True)
            source_commit = "3" * 40
            (etc_root / "SOURCE_COMMIT").write_text(source_commit + "\n", encoding="ascii")
            write_runtime_config(etc_root, source_commit)
            nvr_root = scratch / "nvr/caplab/v0"
            nvr_root.mkdir(parents=True)
            nvr_root.chmod(0o750)
            venv_root, lock_hash, source_tree_hash = make_installed_venv(
                hostctl, scratch, source_commit
            )
            state_file = scratch / "state.json"
            garage_keys = [
                {
                    "role": role,
                    "alias": hostctl.KEY_ALIASES[role],
                    "access_key_id": f"GK-TEST-{role}",
                    "expires_at": "2026-07-22T23:59:59Z",
                }
                for role in hostctl.RUNTIME_ROLES
            ]
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": hostctl.CAMPAIGN_ID,
                        "phase": "disabled",
                        "effects_armed": True,
                        "source_commit": source_commit,
                        "requirements_lock_sha256": lock_hash,
                        "source_tree_manifest_sha256": source_tree_hash,
                        "garage_keys": garage_keys,
                    }
                ),
                encoding="utf-8",
            )
            runner = VerifyRunner(hostctl)
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(
                    state_file=state_file,
                    credential_root=credential_root,
                    etc_root=etc_root,
                    venv_root=venv_root,
                    nvr_root=nvr_root,
                ),
                runner=runner,
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                group_resolver=lambda _group: os.getgid(),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            controller.verify("disabled")

            command_text = "\n".join(" ".join(command) for command in runner.commands)
            self.assertIn("rolcanlogin", command_text)
            self.assertIn("has_table_privilege", command_text)
            self.assertIn("c.relkind IN ('r','v','S')", command_text)
            self.assertIn("pg_get_function_identity_arguments", command_text)
            self.assertIn("garage json-api ListKeys null", command_text)
            self.assertIn("garage json-api GetBucketInfo -", command_text)
            self.assertIn("runuser --user postgres -- /usr/bin/test -r", command_text)
            self.assertIn("getent shadow caplab_writer", command_text)

            runner.renamed_disabled_key = True
            with self.assertRaisesRegex(
                hostctl.HostctlError,
                "recorded Garage campaign key is still live",
            ):
                controller.verify("disabled")

    def test_disabled_verification_refuses_an_unexpired_os_account(self) -> None:
        hostctl = load_hostctl()
        controller = hostctl.HostController(
            paths=hostctl.HostPaths(),
            runner=VerifyRunner(hostctl, phase="ready"),
            identity_resolver=lambda _role: (os.getuid(), os.getgid()),
            group_resolver=lambda _group: os.getgid(),
            clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
        )

        with self.assertRaisesRegex(hostctl.HostctlError, "OS account state is wrong"):
            controller._verify_os_identity_state(disabled=True)

    def test_verification_refuses_an_unsafe_nvr_root_mode(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            nvr_root = Path(directory) / "nvr/caplab/v0"
            nvr_root.mkdir(parents=True)
            nvr_root.chmod(0o755)
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(nvr_root=nvr_root),
                runner=VerifyRunner(hostctl),
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                group_resolver=lambda _group: os.getgid(),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            with self.assertRaisesRegex(
                hostctl.HostctlError, "independent-copy root ownership or mode is wrong"
            ):
                controller._verify_nvr_root()

    def test_inventory_sequence_proves_conflict_added_no_store_effect(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            nvr_root = scratch / "nvr/caplab/v0"
            nvr_root.mkdir(parents=True)
            nvr_root.chmod(0o750)
            state_file = scratch / "state.json"
            garage_keys = [
                {
                    "role": role,
                    "alias": hostctl.KEY_ALIASES[role],
                    "access_key_id": f"GK-TEST-{role}",
                    "expires_at": "2026-07-22T23:59:59Z",
                }
                for role in hostctl.RUNTIME_ROLES
            ]
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": hostctl.CAMPAIGN_ID,
                        "phase": "armed",
                        "effects_armed": True,
                        "garage_keys": garage_keys,
                        "inventories": {},
                    }
                ),
                encoding="utf-8",
            )
            runner = InventoryRunner(hostctl)
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(state_file=state_file, nvr_root=nvr_root),
                runner=runner,
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                group_resolver=lambda _group: os.getgid(),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            controller.capture_inventory("before-register")
            payload = b"synthetic CAPLAB P4 payload\n"
            content_sha256 = __import__("hashlib").sha256(payload).hexdigest()
            copy = nvr_root / "objects" / "sha256" / content_sha256[:2] / content_sha256
            copy.parent.mkdir(parents=True)
            for parent in (copy.parent.parent.parent, copy.parent.parent, copy.parent):
                parent.chmod(0o750)
            copy.write_bytes(payload)
            copy.chmod(0o440)
            runner.objects = 1
            runner.bytes = len(payload)
            runner.registered = True

            controller.capture_inventory("after-first-register")
            controller.capture_inventory("after-replay")
            controller.capture_inventory("after-conflict")

            state = json.loads(state_file.read_text(encoding="utf-8"))
            checks = state["inventory_checks"]
            self.assertTrue(checks["first_register_single_effect"])
            self.assertTrue(checks["replay_added_no_effect"])
            self.assertTrue(checks["conflict_added_no_effect"])
            self.assertEqual(
                state["inventories"]["after-first-register"]["garage"],
                state["inventories"]["after-conflict"]["garage"],
            )
            self.assertEqual(
                state["inventories"]["after-first-register"]["nvr"],
                state["inventories"]["after-conflict"]["nvr"],
            )
            self.assertEqual(
                state["inventories"]["after-first-register"]["postgres"],
                state["inventories"]["after-conflict"]["postgres"],
            )

    def test_inventory_records_then_refuses_a_conflict_side_effect(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            nvr_root = scratch / "nvr/caplab/v0"
            nvr_root.mkdir(parents=True)
            nvr_root.chmod(0o750)
            state_file = scratch / "state.json"
            garage_keys = [
                {
                    "role": role,
                    "alias": hostctl.KEY_ALIASES[role],
                    "access_key_id": f"GK-TEST-{role}",
                    "expires_at": "2026-07-22T23:59:59Z",
                }
                for role in hostctl.RUNTIME_ROLES
            ]
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": hostctl.CAMPAIGN_ID,
                        "phase": "armed",
                        "effects_armed": True,
                        "garage_keys": garage_keys,
                        "inventories": {},
                    }
                ),
                encoding="utf-8",
            )
            runner = InventoryRunner(hostctl)
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(state_file=state_file, nvr_root=nvr_root),
                runner=runner,
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                group_resolver=lambda _group: os.getgid(),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            controller.capture_inventory("before-register")
            payload = b"first\n"
            content_sha256 = __import__("hashlib").sha256(payload).hexdigest()
            copy = nvr_root / "objects" / "sha256" / content_sha256[:2] / content_sha256
            copy.parent.mkdir(parents=True)
            for parent in (copy.parent.parent.parent, copy.parent.parent, copy.parent):
                parent.chmod(0o750)
            copy.write_bytes(payload)
            copy.chmod(0o440)
            runner.objects = 1
            runner.bytes = len(payload)
            runner.registered = True
            controller.capture_inventory("after-first-register")
            controller.capture_inventory("after-replay")

            second = copy.parent / ("f" * 64)
            second.write_bytes(b"unexpected\n")
            second.chmod(0o440)
            runner.objects = 2
            runner.bytes += len(b"unexpected\n")
            with self.assertRaisesRegex(
                hostctl.HostctlError, "conflict changed the store inventory"
            ):
                controller.capture_inventory("after-conflict")

            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertIn("after-conflict", state["inventories"])

    def test_ready_verification_checks_key_expiry_and_bucket_permissions(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            etc_root = scratch / "etc/caplab"
            credential_root = etc_root / "credentials"
            for role in hostctl.RUNTIME_ROLES:
                role_root = credential_root / role
                role_root.mkdir(parents=True)
                credential_file = role_root / "garage.json"
                credential_file.write_text("opaque\n", encoding="ascii")
                credential_file.chmod(0o400)
            source_commit = "4" * 40
            (etc_root / "SOURCE_COMMIT").write_text(source_commit + "\n", encoding="ascii")
            write_runtime_config(etc_root, source_commit)
            nvr_root = scratch / "nvr/caplab/v0"
            nvr_root.mkdir(parents=True)
            nvr_root.chmod(0o750)
            venv_root, lock_hash, source_tree_hash = make_installed_venv(
                hostctl, scratch, source_commit
            )
            garage_keys = [
                {
                    "role": role,
                    "alias": hostctl.KEY_ALIASES[role],
                    "access_key_id": f"GK-TEST-{role}",
                    "expires_at": "2026-07-22T23:59:59Z",
                }
                for role in hostctl.RUNTIME_ROLES
            ]
            state_file = scratch / "state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": hostctl.CAMPAIGN_ID,
                        "phase": "ready",
                        "effects_armed": False,
                        "source_commit": source_commit,
                        "requirements_lock_sha256": lock_hash,
                        "source_tree_manifest_sha256": source_tree_hash,
                        "garage_keys": garage_keys,
                    }
                ),
                encoding="utf-8",
            )
            runner = VerifyRunner(hostctl, phase="ready")
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(
                    state_file=state_file,
                    credential_root=credential_root,
                    etc_root=etc_root,
                    venv_root=venv_root,
                    nvr_root=nvr_root,
                ),
                runner=runner,
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                group_resolver=lambda _group: os.getgid(),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            controller.verify("ready")

            key_checks = [
                command
                for command in runner.commands
                if command[:3] == ["garage", "json-api", "GetKeyInfo"]
            ]
            self.assertEqual(3, len(key_checks))

    def test_ready_verification_refuses_an_altered_installed_source_tree(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            etc_root = scratch / "etc/caplab"
            credential_root = etc_root / "credentials"
            for role in hostctl.RUNTIME_ROLES:
                role_root = credential_root / role
                role_root.mkdir(parents=True)
                credential_file = role_root / "garage.json"
                credential_file.write_text("opaque\n", encoding="ascii")
                credential_file.chmod(0o400)
            source_commit = "6" * 40
            (etc_root / "SOURCE_COMMIT").write_text(source_commit + "\n", encoding="ascii")
            write_runtime_config(etc_root, source_commit)
            nvr_root = scratch / "nvr/caplab/v0"
            nvr_root.mkdir(parents=True)
            nvr_root.chmod(0o750)
            venv_root, lock_hash, source_tree_hash = make_installed_venv(
                hostctl, scratch, source_commit
            )
            installed_package = next(venv_root.rglob("site-packages/caplab"))
            (installed_package / "runtime/__init__.py").write_text(
                "# altered after bootstrap\n", encoding="ascii"
            )
            state_file = scratch / "state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": hostctl.CAMPAIGN_ID,
                        "phase": "ready",
                        "effects_armed": False,
                        "source_commit": source_commit,
                        "requirements_lock_sha256": lock_hash,
                        "source_tree_manifest_sha256": source_tree_hash,
                        "garage_keys": [
                            {
                                "role": role,
                                "alias": hostctl.KEY_ALIASES[role],
                                "access_key_id": f"GK-TEST-{role}",
                                "expires_at": "2026-07-22T23:59:59Z",
                            }
                            for role in hostctl.RUNTIME_ROLES
                        ],
                    }
                ),
                encoding="utf-8",
            )
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(
                    state_file=state_file,
                    credential_root=credential_root,
                    etc_root=etc_root,
                    venv_root=venv_root,
                    nvr_root=nvr_root,
                ),
                runner=VerifyRunner(hostctl, phase="ready"),
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                group_resolver=lambda _group: os.getgid(),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            with self.assertRaisesRegex(
                hostctl.HostctlError, "installed CAPLAB package differs from its manifest"
            ):
                controller.verify("ready")

    def test_ready_verification_refuses_a_reader_write_grant(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            etc_root = scratch / "etc/caplab"
            credential_root = etc_root / "credentials"
            for role in hostctl.RUNTIME_ROLES:
                role_root = credential_root / role
                role_root.mkdir(parents=True)
                credential_file = role_root / "garage.json"
                credential_file.write_text("opaque\n", encoding="ascii")
                credential_file.chmod(0o400)
            source_commit = "5" * 40
            (etc_root / "SOURCE_COMMIT").write_text(source_commit + "\n", encoding="ascii")
            write_runtime_config(etc_root, source_commit)
            nvr_root = scratch / "nvr/caplab/v0"
            nvr_root.mkdir(parents=True)
            nvr_root.chmod(0o750)
            venv_root, lock_hash, source_tree_hash = make_installed_venv(
                hostctl, scratch, source_commit
            )
            state_file = scratch / "state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": hostctl.CAMPAIGN_ID,
                        "phase": "ready",
                        "effects_armed": False,
                        "source_commit": source_commit,
                        "requirements_lock_sha256": lock_hash,
                        "source_tree_manifest_sha256": source_tree_hash,
                        "garage_keys": [
                            {
                                "role": role,
                                "alias": hostctl.KEY_ALIASES[role],
                                "access_key_id": f"GK-TEST-{role}",
                                "expires_at": "2026-07-22T23:59:59Z",
                            }
                            for role in hostctl.RUNTIME_ROLES
                        ],
                    }
                ),
                encoding="utf-8",
            )
            runner = VerifyRunner(hostctl, phase="ready", reader_write=True)
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(
                    state_file=state_file,
                    credential_root=credential_root,
                    etc_root=etc_root,
                    venv_root=venv_root,
                    nvr_root=nvr_root,
                ),
                runner=runner,
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                group_resolver=lambda _group: os.getgid(),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            with self.assertRaisesRegex(
                hostctl.HostctlError, "Garage key bucket authority is wrong"
            ):
                controller.verify("ready")

    def test_pinned_install_ignores_a_worktree_change_after_preflight(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            source_repo, source_package, requirements_lock, source_commit = make_source_repo(
                scratch
            )
            committed = (source_package / "runtime/__init__.py").read_bytes()
            (source_package / "runtime/__init__.py").write_text(
                "# mutable worktree drift\n",
                encoding="ascii",
            )
            runner = BootstrapRunner(scratch)
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(staging_root=scratch),
                runner=runner,
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )
            pinned_files = controller._read_pinned_git_package(source_repo, source_commit)
            purelib = scratch / "purelib"
            purelib.mkdir()

            controller._install_pinned_package(
                pinned_files,
                source_commit,
                requirements_lock.read_bytes(),
                purelib,
            )

            self.assertEqual(
                committed,
                (purelib / "caplab/runtime/__init__.py").read_bytes(),
            )
            manifest = json.loads(
                (purelib / "caplab-source-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(source_commit, manifest["source_commit"])

    def test_bootstrap_failure_journal_cleans_every_started_resource_class(self) -> None:
        hostctl = load_hostctl()
        failure_points = (
            "runtime_identities",
            "host_paths",
            "postgres",
            "garage_bucket",
        )
        for failure_point in failure_points:
            with (
                self.subTest(failure_point=failure_point),
                tempfile.TemporaryDirectory() as directory,
            ):
                scratch = Path(directory)
                source_repo, _source_package, _lock, source_commit = make_source_repo(scratch)
                source_pin = scratch / "SOURCE_COMMIT"
                source_pin.write_text(source_commit + "\n", encoding="ascii")
                write_runtime_config(scratch, source_commit)
                state_file = scratch / "state.json"
                runner = PartialBootstrapRunner(scratch, hostctl, failure_point)
                controller = hostctl.HostController(
                    paths=hostctl.HostPaths(
                        state_file=state_file,
                        credential_root=scratch / "etc/caplab/credentials",
                        etc_root=scratch / "etc/caplab",
                        venv_root=scratch / "opt/caplab/venvs",
                        nvr_root=scratch / "nvr/caplab/v0",
                        staging_root=scratch,
                    ),
                    runner=runner,
                    identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                    clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
                )

                with self.assertRaisesRegex(hostctl.HostctlError, "simulated bootstrap"):
                    controller.bootstrap_base(
                        source_commit=source_commit,
                        source_pin=source_pin,
                        runtime_config=scratch / "runtime.toml",
                        source_repo=source_repo,
                    )

                state = json.loads(state_file.read_text(encoding="utf-8"))
                self.assertEqual("bootstrap_rolled_back", state["phase"])
                self.assertEqual("started", state["resource_steps"][failure_point])
                command_text = "\n".join(" ".join(command) for command in runner.commands)
                self.assertIn("groupdel caplab", command_text)
                if failure_point != "runtime_identities":
                    self.assertIn("userdel caplab_writer", command_text)

    def test_disable_attempts_every_layer_and_records_aggregate_failure(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            credential_root = scratch / "credentials"
            for role in hostctl.RUNTIME_ROLES:
                role_root = credential_root / role
                role_root.mkdir(parents=True)
                (role_root / "garage.json").write_text("opaque\n", encoding="ascii")
            state_file = scratch / "state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": hostctl.CAMPAIGN_ID,
                        "phase": "armed",
                        "effects_armed": True,
                    }
                ),
                encoding="utf-8",
            )
            runner = DegradedDisableRunner(hostctl)
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(
                    state_file=state_file,
                    credential_root=credential_root,
                ),
                runner=runner,
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            with self.assertRaisesRegex(hostctl.HostctlError, "disablement is incomplete"):
                controller.disable_access()

            command_text = "\n".join(" ".join(command) for command in runner.commands)
            for role in hostctl.RUNTIME_ROLES:
                self.assertIn(f"pkill --signal KILL --uid {role}", command_text)
                self.assertIn(f"usermod --lock --expiredate 1 {role}", command_text)
            self.assertIn("GK-TEST-caplab_verifier", command_text)
            self.assertFalse(any(credential_root.rglob("garage.json")))
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual("disable_incomplete", state["phase"])
            self.assertEqual("complete", state["disable_results"]["os_account:caplab_verifier"])

    def test_disable_revokes_state_recorded_keys_after_their_aliases_are_renamed(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            state_file = scratch / "state.json"
            garage_keys = [
                {
                    "role": role,
                    "alias": hostctl.KEY_ALIASES[role],
                    "access_key_id": f"GK-TEST-{role}",
                    "expires_at": "2026-07-22T23:59:59Z",
                }
                for role in hostctl.RUNTIME_ROLES
            ]
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": hostctl.CAMPAIGN_ID,
                        "phase": "armed",
                        "effects_armed": True,
                        "garage_keys": garage_keys,
                    }
                ),
                encoding="utf-8",
            )
            runner = RenamedKeyDisableRunner(hostctl)
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(
                    state_file=state_file,
                    credential_root=scratch / "credentials",
                ),
                runner=runner,
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            controller.disable_access()
            controller.disable_access()

            deleted_ids = [
                command[-1]
                for command in runner.commands
                if command[:3] == ["garage", "key", "delete"]
            ]
            self.assertCountEqual(
                [f"GK-TEST-{role}" for role in hostctl.RUNTIME_ROLES], deleted_ids
            )
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual("disabled", state["phase"])

    def test_expiry_disable_accepts_a_fully_journaled_empty_rollback(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": hostctl.CAMPAIGN_ID,
                        "phase": "rollback_complete",
                        "effects_armed": False,
                        "rollback_steps": {
                            "garage_bucket": "complete",
                            "postgres": "complete",
                            "host_paths": "complete",
                            "runtime_identities": "complete",
                            "common_group": "complete",
                        },
                    }
                ),
                encoding="utf-8",
            )
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(state_file=state_file),
                runner=NoHostCommandRunner(),
                identity_resolver=lambda _role: (_ for _ in ()).throw(
                    AssertionError("rollback-complete disable resolved a deleted identity")
                ),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            controller.disable_access()

    def test_empty_rollback_resumes_after_first_delete_interruption(self) -> None:
        hostctl = load_hostctl()
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            state_file = scratch / "state.json"
            etc_root = scratch / "etc/caplab"
            venv_root = scratch / "opt/caplab/venvs"
            nvr_root = scratch / "nvr/caplab/v0"
            for path in (etc_root, venv_root, nvr_root):
                path.mkdir(parents=True)
            state_file.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "campaign_id": hostctl.CAMPAIGN_ID,
                        "phase": "disabled",
                        "effects_armed": False,
                        "created_resources": {
                            "common_group": True,
                            "runtime_identities": True,
                            "host_paths": True,
                            "venv": True,
                            "postgres": True,
                            "garage_bucket": True,
                        },
                    }
                ),
                encoding="utf-8",
            )
            runner = InterruptedRollbackRunner(hostctl)
            controller = hostctl.HostController(
                paths=hostctl.HostPaths(
                    state_file=state_file,
                    credential_root=etc_root / "credentials",
                    etc_root=etc_root,
                    venv_root=venv_root,
                    nvr_root=nvr_root,
                ),
                runner=runner,
                identity_resolver=lambda _role: (os.getuid(), os.getgid()),
                clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
            )

            with self.assertRaisesRegex(hostctl.HostctlError, "simulated delete interruption"):
                controller.rollback_empty()
            interrupted = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual("rollback_started", interrupted["phase"])
            self.assertEqual("started", interrupted["rollback_steps"]["garage_bucket"])

            controller.rollback_empty()

            completed = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual("rollback_complete", completed["phase"])
            self.assertTrue(
                all(value == "complete" for value in completed["rollback_steps"].values())
            )

    def test_postgres_contract_refuses_an_extra_writer_update_grant(self) -> None:
        hostctl = load_hostctl()
        controller = hostctl.HostController(
            paths=hostctl.HostPaths(),
            runner=VerifyRunner(
                hostctl,
                phase="ready",
                postgres_writer_update=True,
            ),
            identity_resolver=lambda _role: (os.getuid(), os.getgid()),
            clock=lambda: datetime(2026, 7, 15, tzinfo=UTC),
        )

        with self.assertRaisesRegex(hostctl.HostctlError, "table privilege matrix"):
            controller._verify_postgres_contract(expected_login=True)


class FakeGarageRunner:
    def __init__(self) -> None:
        self.created_aliases: list[str] = []
        self.commands: list[list[str]] = []

    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        self.commands.append(arguments)
        if arguments == ["systemctl", "is-enabled", "caplab-p4-expiry.timer"]:
            return "enabled\n"
        if arguments == ["systemctl", "is-active", "caplab-p4-expiry.timer"]:
            return "active\n"
        if arguments[:3] == ["garage", "key", "create"]:
            self.created_aliases.append(arguments[-1])
            return "discarded-create-output"
        if arguments[:2] == ["garage", "json-api"]:
            request = json.loads(input_text or "")
            alias = request["search"]
            role = alias.rsplit("-", 1)[-1]
            return json.dumps(
                {
                    "accessKeyId": f"GK-TEST-{role}",
                    "name": alias,
                    "expiration": "2026-07-22T23:59:59Z",
                    "secretAccessKey": f"TEST-SECRET-caplab_{role}",
                }
            )
        if arguments[:3] == ["garage", "bucket", "allow"]:
            return ""
        if arguments[:5] == ["runuser", "--user", "postgres", "--", "psql"]:
            return ""
        raise AssertionError(f"unexpected command: {arguments}")


class FailingGarageRunner(FakeGarageRunner):
    def __init__(self, hostctl) -> None:
        super().__init__()
        self.hostctl = hostctl
        self.deleted_keys: list[str] = []

    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        if (
            arguments[:3] == ["garage", "key", "create"]
            and arguments[-1] == self.hostctl.KEY_ALIASES["caplab_reader"]
        ):
            raise self.hostctl.HostctlError("simulated key failure")
        if arguments[:3] == ["garage", "key", "delete"]:
            self.deleted_keys.append(arguments[-1])
            return ""
        if arguments[:3] == ["garage", "json-api", "ListKeys"]:
            return json.dumps(
                [
                    {
                        "id": "GK-TEST-writer",
                        "name": self.hostctl.KEY_ALIASES["caplab_writer"],
                    }
                ]
            )
        if arguments[0] in {"pkill", "usermod"}:
            return ""
        return super().run(
            arguments,
            input_text=input_text,
            secret_output=secret_output,
            allowed_returncodes=allowed_returncodes,
        )


class DegradedDisableRunner:
    def __init__(self, hostctl) -> None:
        self.hostctl = hostctl
        self.commands: list[list[str]] = []

    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        del input_text, secret_output, allowed_returncodes
        self.commands.append(arguments)
        if arguments[:5] == ["runuser", "--user", "postgres", "--", "psql"]:
            raise self.hostctl.HostctlError("simulated PostgreSQL outage")
        if arguments[:3] == ["garage", "json-api", "ListKeys"]:
            return json.dumps(
                [
                    {
                        "id": f"GK-TEST-{role}",
                        "name": self.hostctl.KEY_ALIASES[role],
                    }
                    for role in self.hostctl.RUNTIME_ROLES
                ]
            )
        if arguments[:3] == ["garage", "key", "delete"]:
            if arguments[-1] == "GK-TEST-caplab_writer":
                raise self.hostctl.HostctlError("simulated Garage delete outage")
            return ""
        if arguments[0] in {"pkill", "usermod"}:
            return ""
        raise AssertionError(f"unexpected command: {arguments}")


class RenamedKeyDisableRunner:
    def __init__(self, hostctl) -> None:
        self.hostctl = hostctl
        self.commands: list[list[str]] = []
        self.live_ids = {f"GK-TEST-{role}" for role in self.hostctl.RUNTIME_ROLES}

    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        del input_text, secret_output, allowed_returncodes
        self.commands.append(arguments)
        if arguments[:3] == ["garage", "json-api", "ListKeys"]:
            return json.dumps(
                [
                    {
                        "id": access_key_id,
                        "name": f"renamed-{access_key_id}",
                    }
                    for access_key_id in sorted(self.live_ids)
                ]
            )
        if arguments[:5] == ["runuser", "--user", "postgres", "--", "psql"]:
            return ""
        if arguments[:3] == ["garage", "key", "delete"]:
            self.live_ids.remove(arguments[-1])
            return ""
        if arguments[0] in {"pkill", "usermod"}:
            return ""
        raise AssertionError(f"unexpected command: {arguments}")


class NoHostCommandRunner:
    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        del input_text, secret_output, allowed_returncodes
        raise AssertionError(f"rollback-complete disable ran a host command: {arguments}")


class ExistingGroupRunner:
    def __init__(self) -> None:
        self.mutation_attempted = False

    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        del input_text, secret_output, allowed_returncodes
        if arguments == ["getent", "group", "caplab"]:
            return "caplab:x:995:\n"
        if arguments[0] in {"groupadd", "useradd", "install"}:
            self.mutation_attempted = True
        raise AssertionError(f"unexpected command: {arguments}")


class HealthyEmptyHostRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        del input_text, secret_output, allowed_returncodes
        self.commands.append(arguments)
        if arguments[0] == "getent":
            return ""
        if arguments[:2] == ["systemctl", "is-active"]:
            return "active\n"
        if arguments[:3] == ["garage", "json-api", "ListBuckets"]:
            return "[]\n"
        if arguments[:3] == ["garage", "json-api", "ListKeys"]:
            return "[]\n"
        if arguments[0] == "findmnt":
            return "zfs\n"
        if arguments[:5] == ["runuser", "--user", "postgres", "--", "psql"]:
            return "clear\ncaplab_reader:peer\ncaplab_verifier:peer\ncaplab_writer:peer\n"
        raise AssertionError(f"unexpected command: {arguments}")


class BootstrapRunner:
    def __init__(self, scratch: Path) -> None:
        self.scratch = scratch
        self.stage = scratch / "caplab-venv.test"
        self.purelib = self.stage / "lib/python3.12/site-packages"
        self.commands: list[list[str]] = []

    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        del secret_output, allowed_returncodes
        self.commands.append(arguments)
        if arguments[0] == "git":
            return subprocess.run(
                arguments,
                input=input_text,
                text=True,
                capture_output=True,
                check=True,
            ).stdout
        if arguments[:2] == ["mktemp", "--directory"]:
            self.stage.mkdir()
            return str(self.stage) + "\n"
        if arguments == [str(self.stage / "bin/python"), "--version"]:
            return "Python 3.12.0\n"
        if arguments[:3] == ["/usr/bin/env", "-i", "PYTHONNOUSERSITE=1"]:
            if "sysconfig.get_path" in arguments[-1]:
                self.purelib.mkdir(parents=True)
                return str(self.purelib) + "\n"
            return ""
        return ""


class FailingVenvRunner(BootstrapRunner):
    def __init__(self, scratch: Path, hostctl) -> None:
        super().__init__(scratch)
        self.hostctl = hostctl

    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        if arguments[1:4] == ["-m", "pip", "install"]:
            raise self.hostctl.HostctlError("simulated pip failure")
        return super().run(
            arguments,
            input_text=input_text,
            secret_output=secret_output,
            allowed_returncodes=allowed_returncodes,
        )


class PartialBootstrapRunner(BootstrapRunner):
    def __init__(self, scratch: Path, hostctl, failure_point: str) -> None:
        super().__init__(scratch)
        self.hostctl = hostctl
        self.failure_point = failure_point
        self.failed = False
        self.bucket_exists = False

    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        if arguments[:3] == ["garage", "json-api", "ListBuckets"]:
            self.commands.append(arguments)
            return (
                json.dumps([{"globalAliases": [self.hostctl.GARAGE_BUCKET]}])
                if self.bucket_exists
                else "[]"
            )
        if arguments[:3] == ["garage", "json-api", "GetBucketInfo"]:
            self.commands.append(arguments)
            return json.dumps(
                {
                    "globalAliases": [self.hostctl.GARAGE_BUCKET],
                    "objects": 0,
                    "bytes": 0,
                    "unfinishedUploads": 0,
                    "unfinishedMultipartUploads": 0,
                }
            )
        if arguments[:3] == ["garage", "bucket", "create"]:
            self.bucket_exists = True
        if arguments[:4] == ["garage", "bucket", "delete", "--yes"]:
            self.bucket_exists = False
            self.commands.append(arguments)
            return ""
        if (
            arguments[:5] == ["runuser", "--user", "postgres", "--", "psql"]
            and "pg_database" in arguments[-1]
        ):
            self.commands.append(arguments)
            return "absent\n"
        should_fail = (
            (
                self.failure_point == "runtime_identities"
                and arguments[:1] == ["useradd"]
                and arguments[-1] == "caplab_reader"
            )
            or (
                self.failure_point == "host_paths"
                and arguments[:2] == ["/usr/bin/setfacl", "--modify"]
            )
            or (
                self.failure_point == "postgres"
                and arguments[:5] == ["runuser", "--user", "postgres", "--", "psql"]
                and "CREATE ROLE caplab_owner" in arguments[-1]
            )
            or (
                self.failure_point == "garage_bucket"
                and arguments[:3] == ["garage", "bucket", "set-quotas"]
            )
        )
        if should_fail and not self.failed:
            self.failed = True
            self.commands.append(arguments)
            raise self.hostctl.HostctlError(f"simulated bootstrap failure at {self.failure_point}")
        return super().run(
            arguments,
            input_text=input_text,
            secret_output=secret_output,
            allowed_returncodes=allowed_returncodes,
        )


class RollbackRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.bucket_exists = True
        self.database_exists = True

    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        del secret_output, allowed_returncodes
        self.commands.append(arguments)
        if arguments[:3] == ["garage", "json-api", "ListBuckets"]:
            if not self.bucket_exists:
                return "[]\n"
            return json.dumps([{"globalAliases": ["caplab-v0"]}])
        if arguments[:3] == ["garage", "json-api", "GetBucketInfo"]:
            self.assert_get_bucket_request(input_text)
            return json.dumps(
                {
                    "globalAliases": ["caplab-v0"],
                    "objects": 0,
                    "bytes": 0,
                    "unfinishedUploads": 0,
                    "unfinishedMultipartUploads": 0,
                }
            )
        if arguments[:4] == ["garage", "bucket", "delete", "--yes"]:
            self.bucket_exists = False
            return ""
        if arguments[:5] == ["runuser", "--user", "postgres", "--", "psql"]:
            if "pg_database" in arguments[-1]:
                return "present\n" if self.database_exists else "absent\n"
            return ""
        if arguments[:5] == ["runuser", "--user", "postgres", "--", "dropdb"]:
            self.database_exists = False
            return ""
        return ""

    @staticmethod
    def assert_get_bucket_request(input_text: str | None) -> None:
        if json.loads(input_text or "") != {"globalAlias": "caplab-v0"}:
            raise AssertionError(f"unexpected bucket request: {input_text}")


class InterruptedRollbackRunner(RollbackRunner):
    def __init__(self, hostctl) -> None:
        super().__init__()
        self.hostctl = hostctl
        self.interrupted = False

    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        if arguments[:4] == ["garage", "bucket", "delete", "--yes"] and not self.interrupted:
            self.commands.append(arguments)
            self.bucket_exists = False
            self.interrupted = True
            raise self.hostctl.HostctlError("simulated delete interruption")
        return super().run(
            arguments,
            input_text=input_text,
            secret_output=secret_output,
            allowed_returncodes=allowed_returncodes,
        )


class VerifyRunner:
    def __init__(
        self,
        hostctl,
        *,
        phase: str = "disabled",
        reader_write: bool = False,
        postgres_writer_update: bool = False,
        renamed_disabled_key: bool = False,
    ) -> None:
        self.hostctl = hostctl
        self.phase = phase
        self.reader_write = reader_write
        self.postgres_writer_update = postgres_writer_update
        self.renamed_disabled_key = renamed_disabled_key
        self.commands: list[list[str]] = []

    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        del secret_output, allowed_returncodes
        self.commands.append(arguments)
        if arguments[:3] == ["/usr/bin/env", "-i", "PYTHONNOUSERSITE=1"]:
            return ""
        if arguments[:5] == [
            "runuser",
            "--user",
            "postgres",
            "--",
            "/usr/bin/test",
        ] and arguments[5] in {"-r", "-x"}:
            return ""
        if arguments[:5] == ["runuser", "--user", "postgres", "--", "psql"]:
            sql = arguments[-1]
            if "FROM pg_authid" in sql:
                login = "true" if self.phase in {"ready", "armed"} else "false"
                flags = "false:false:false:false:false:false:true:true"
                return (
                    "\n".join(
                        [
                            f"caplab_owner:false:{flags}:",
                            f"caplab_reader:{login}:{flags}:caplab="
                            "search_path=caplab_v0, pg_catalog",
                            f"caplab_verifier:{login}:{flags}:caplab="
                            "search_path=caplab_v0, pg_catalog",
                            f"caplab_writer:{login}:{flags}:caplab="
                            "search_path=caplab_v0, pg_catalog",
                        ]
                    )
                    + "\n"
                )
            if "database:' || datname" in sql:
                return "database:caplab:caplab_owner\nschema:caplab_v0:caplab_owner\n"
            if "pg_get_userbyid(c.relowner)" in sql:
                rows = sorted(
                    [f"r:{name}:caplab_owner" for name in self.hostctl.POSTGRES_TABLES]
                    + [f"v:{name}:caplab_owner" for name in self.hostctl.POSTGRES_VIEWS]
                    + [f"S:{name}:caplab_owner" for name in self.hostctl.POSTGRES_SEQUENCES]
                )
                return "\n".join(rows) + "\n"
            if "has_sequence_privilege" in sql:
                rows = sorted(
                    f"{role}:{sequence}:{'SELECT,USAGE' if role == 'caplab_writer' else ''}"
                    for role in self.hostctl.RUNTIME_ROLES
                    for sequence in self.hostctl.POSTGRES_SEQUENCES
                )
                return "\n".join(rows) + "\n"
            if "concat_ws" in sql:
                rows = []
                for role in self.hostctl.RUNTIME_ROLES:
                    for table in self.hostctl.POSTGRES_TABLES:
                        if role == "caplab_writer":
                            privileges = (
                                "SELECT,INSERT"
                                if table in self.hostctl.WRITER_INSERT_TABLES
                                else "SELECT"
                            )
                            if self.postgres_writer_update and table == "attempts":
                                privileges += ",UPDATE"
                        else:
                            privileges = "SELECT"
                        rows.append(f"{role}:r:{table}:{privileges}")
                    for view in self.hostctl.POSTGRES_VIEWS:
                        privileges = "" if role == "caplab_writer" else "SELECT"
                        rows.append(f"{role}:v:{view}:{privileges}")
                return "\n".join(sorted(rows)) + "\n"
            if "has_database_privilege" in sql:
                rows = sorted(
                    f"{role}:true:false:false:true:false" for role in self.hostctl.RUNTIME_ROLES
                )
                return "\n".join(rows) + "\n"
            if "pg_get_function_identity_arguments" in sql:
                return "reject_mutation::caplab_owner:false:false:false:false\n"
            if "public-grant" in sql:
                return "public-revoked\n"
            if "pg_auth_members" in sql:
                return "0\n"
            login = "true" if self.phase in {"ready", "armed"} else "false"
            return "\n".join(f"{role}:{login}" for role in self.hostctl.RUNTIME_ROLES) + "\n"
        if (
            arguments[:2] == ["runuser", "--user"]
            and arguments[2] in self.hostctl.RUNTIME_ROLES
            and "/usr/bin/psql" in arguments
        ):
            role = arguments[2]
            return f"{role}:caplab\n"
        if arguments[:2] == ["getent", "passwd"]:
            role = arguments[2]
            return f"{role}:x:{os.getuid()}:{os.getgid()}::/nonexistent:/usr/sbin/nologin\n"
        if arguments[:2] == ["getent", "shadow"]:
            role = arguments[2]
            expiry = "1" if self.phase == "disabled" else ""
            return f"{role}:!:1:0:99999:7::{expiry}:\n"
        if arguments[:3] == ["garage", "json-api", "ListKeys"]:
            if self.phase == "disabled" and self.renamed_disabled_key:
                return json.dumps(
                    [
                        {
                            "id": "GK-TEST-caplab_writer",
                            "name": "renamed-outside-campaign",
                        }
                    ]
                )
            if self.phase not in {"ready", "armed"}:
                return "[]\n"
            return json.dumps(
                [
                    {
                        "id": f"GK-TEST-{role}",
                        "name": self.hostctl.KEY_ALIASES[role],
                    }
                    for role in self.hostctl.RUNTIME_ROLES
                ]
            )
        if arguments[:3] == ["garage", "json-api", "GetBucketInfo"]:
            return json.dumps(
                {
                    "globalAliases": [self.hostctl.GARAGE_BUCKET],
                    "objects": 0,
                    "bytes": 0,
                    "unfinishedUploads": 0,
                    "unfinishedMultipartUploads": 0,
                    "quotas": {
                        "maxSize": 1_073_741_824,
                        "maxObjects": 10_000,
                    },
                }
            )
        if arguments[:3] == ["garage", "json-api", "GetKeyInfo"]:
            if self.phase == "disabled":
                raise AssertionError("disabled verification must not fetch a deleted key")
            request = json.loads(input_text or "")
            alias = request["search"]
            role = next(
                role
                for role, expected_alias in self.hostctl.KEY_ALIASES.items()
                if expected_alias == alias
            )
            write = role == "caplab_writer" or (role == "caplab_reader" and self.reader_write)
            return json.dumps(
                {
                    "accessKeyId": f"GK-TEST-{role}",
                    "name": alias,
                    "expiration": "2026-07-22T23:59:59Z",
                    "expired": False,
                    "permissions": {"createBucket": False},
                    "buckets": [
                        {
                            "globalAliases": [self.hostctl.GARAGE_BUCKET],
                            "localAliases": [],
                            "permissions": {
                                "owner": False,
                                "read": True,
                                "write": write,
                            },
                        }
                    ],
                }
            )
        raise AssertionError(f"unexpected command: {arguments}")


class InventoryRunner:
    def __init__(self, hostctl) -> None:
        self.hostctl = hostctl
        self.objects = 0
        self.bytes = 0
        self.registered = False
        self.commands: list[list[str]] = []

    def run(
        self,
        arguments: list[str],
        *,
        input_text: str | None = None,
        secret_output: bool = False,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        del input_text, secret_output, allowed_returncodes
        self.commands.append(arguments)
        if arguments[:5] == ["runuser", "--user", "postgres", "--", "psql"]:
            counts = {table: 0 for table in self.hostctl.POSTGRES_TABLES}
            counts["schema_migrations"] = 1
            if self.registered:
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
                    counts[table] = 1
                counts["operation_events"] = 4
                counts["audit_events"] = 1
            return "\n".join(f"{table}:{counts[table]}" for table in sorted(counts)) + "\n"
        if arguments[:3] == ["garage", "json-api", "GetBucketInfo"]:
            return json.dumps(
                {
                    "globalAliases": [self.hostctl.GARAGE_BUCKET],
                    "objects": self.objects,
                    "bytes": self.bytes,
                    "unfinishedUploads": 0,
                    "unfinishedMultipartUploads": 0,
                    "quotas": {
                        "maxSize": 1_073_741_824,
                        "maxObjects": 10_000,
                    },
                }
            )
        if arguments[:3] == ["garage", "json-api", "ListKeys"]:
            return json.dumps(
                [
                    {
                        "id": f"GK-TEST-{role}",
                        "name": self.hostctl.KEY_ALIASES[role],
                    }
                    for role in self.hostctl.RUNTIME_ROLES
                ]
            )
        raise AssertionError(f"unexpected command: {arguments}")


if __name__ == "__main__":
    unittest.main()
