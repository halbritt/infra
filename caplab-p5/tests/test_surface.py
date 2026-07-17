from __future__ import annotations

import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class P5HostSurfaceTests(unittest.TestCase):
    def test_source_config_and_identity_are_frozen(self) -> None:
        source_commit = (ROOT / "SOURCE_COMMIT").read_text(encoding="ascii").strip()
        config = tomllib.loads((ROOT / "recovery.toml").read_text(encoding="utf-8"))

        self.assertRegex(source_commit, r"\A[0-9a-f]{40}\Z")
        self.assertEqual(config["campaign"]["executor_source_commit"], source_commit)
        self.assertEqual(
            config["campaign"]["registration_runtime_commit"],
            "c82b5512661c537db06f725af70198eccc818358",
        )
        self.assertEqual(
            config["campaign"]["campaign_id"],
            "caplab-p5-recovery-2026-07-16",
        )
        self.assertEqual(
            config["campaign"]["corrective_campaign_id"],
            "caplab-p5-corrective-2026-07-16",
        )
        self.assertEqual(
            config["campaign"]["authorization_sha256"],
            "0b0682acaa749f7715687e10f3c0565f0776da951375d9f3fb5ed329c94e2b9a",
        )
        self.assertEqual(
            config["campaign"]["superseded_authorization_sha256"],
            "e8cd172af19cb631ba6814a3fd57c7b91f381cd799de862d9bd277b6ef68d34f",
        )
        self.assertEqual(
            config["campaign"]["authorization_expires_at"],
            "2026-07-23T23:59:59Z",
        )
        self.assertEqual(config["identity"]["operation_id"], "op-p5-recovery-0001")
        self.assertEqual(config["garage"]["bucket"], "caplab-v0")
        self.assertEqual(config["local_copy"]["root"], "/nvr/caplab/v0")
        self.assertEqual(
            config["garage"]["credentials_root"],
            "/etc/caplab-p5/credentials",
        )

    def test_backup_and_prune_use_one_blocking_lock(self) -> None:
        backup = (ROOT / "bin/restic-backup-locked").read_text(encoding="utf-8")
        prune = (ROOT / "bin/restic-prune-locked").read_text(encoding="utf-8")
        check = (ROOT / "bin/restic-check-locked").read_text(encoding="utf-8")

        for script in (backup, prune, check):
            self.assertIn("exec 9>/run/lock/caplab-backup.lock", script)
            self.assertIn("/usr/bin/flock --exclusive 9", script)
        self.assertIn("/usr/bin/restic prune", prune)
        self.assertNotIn("/usr/bin/restic prune", check)

    def test_dropins_hold_the_lock_across_each_complete_service(self) -> None:
        backup = (ROOT / "systemd/restic-backup.service.d/20-caplab-p5-lock.conf").read_text(
            encoding="utf-8"
        )
        prune = (ROOT / "systemd/restic-prune.service.d/20-caplab-p5-lock.conf").read_text(
            encoding="utf-8"
        )

        for dropin in (backup, prune):
            self.assertIn("ExecStart=", dropin)
            self.assertIn("ExecStartPost=", dropin)
            self.assertIn("/usr/local/libexec/caplab-p5/", dropin)

    def test_hostctl_exposes_only_bounded_lifecycle_commands(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "caplab-p5-hostctl.py"), "--help"],
            text=True,
            capture_output=True,
            check=True,
        )
        for command in ("preflight", "bootstrap", "verify", "disable"):
            self.assertIn(command, completed.stdout)
        self.assertNotIn("purge-object", completed.stdout)
        self.assertNotIn("restic-prune", completed.stdout)

    def test_root_git_reads_trust_only_the_exact_caplab_checkout(self) -> None:
        hostctl = (ROOT / "caplab-p5-hostctl.py").read_text(encoding="utf-8")
        self.assertIn("safe.directory={SOURCE_REPO}", hostctl)
        self.assertNotIn("safe.directory=*", hostctl)

    def test_receipt_wrapper_records_a_direct_numeric_status(self) -> None:
        receipt = (ROOT / "bin/run-receipt").read_text(encoding="utf-8")
        self.assertIn('printf \'%d\\n\' "$rc" >"$rc_file"', receipt)
        self.assertIn("env -i", receipt)
        self.assertNotIn("eval ", receipt)

    def test_isolated_restore_never_stops_or_replaces_live_postgres(self) -> None:
        common = (ROOT / "bin/isolated-postgres-common").read_text(encoding="utf-8")
        restore = (ROOT / "bin/pgbackrest-restore-isolated").read_text(encoding="utf-8")
        stop = (ROOT / "bin/pgbackrest-stop-isolated").read_text(encoding="utf-8")

        self.assertIn("/var/tmp/caplab-p5-pgrestore", common)
        self.assertIn("55435", common)
        self.assertIn(
            "campaign=caplab-p5-recovery-compatibility-corrective-2026-07-17",
            common,
        )
        self.assertIn(
            "authorization_sha256="
            "7dabe6891bc1679ccbad4a893ba864ba42a59a301cbce472de15a2b03fbd64f0",
            common,
        )
        self.assertIn('--pg1-path="$target"', restore)
        self.assertIn('source /usr/local/libexec/caplab-p5/isolated-postgres-common', restore)
        self.assertIn('source /usr/local/libexec/caplab-p5/isolated-postgres-common', stop)
        self.assertIn('isolated_postmaster_pid" == "$live_postmaster_pid', common)
        self.assertIn("stop_verified_isolated", common)
        self.assertIn("run_as_postgres", common)
        self.assertIn('marker="$target/CAPLAB_P5_ISOLATED_STATE"', common)
        for script in (restore, stop):
            self.assertIn("live_data_directory", script)
            self.assertIn("live_postmaster_pid", script)
            self.assertIn("verify_live_unchanged", script)
            self.assertNotIn("systemctl stop postgresql", script)
            self.assertNotIn("kill ", script)
            self.assertNotIn("/var/lib/postgresql/17/main", script)

    def test_isolated_restore_uses_target_owned_config_and_rejects_tcp_clients(
        self,
    ) -> None:
        common = (ROOT / "bin/isolated-postgres-common").read_text(encoding="utf-8")
        restore = (ROOT / "bin/pgbackrest-restore-isolated").read_text(encoding="utf-8")
        stop = (ROOT / "bin/pgbackrest-stop-isolated").read_text(encoding="utf-8")

        self.assertIn('config="$target/postgresql.conf"', common)
        self.assertIn('hba="$target/pg_hba.conf"', common)
        self.assertIn("data_directory = '$target'", restore)
        self.assertIn("port = $port", restore)
        self.assertIn("unix_socket_directories = '$socket'", restore)
        self.assertIn("host all all 127.0.0.1/32 reject", restore)
        self.assertIn("local replication all reject", restore)
        self.assertIn("host replication all 127.0.0.1/32 reject", restore)
        self.assertIn("host replication all ::1/128 reject", restore)
        self.assertIn("local all postgres peer", restore)
        self.assertLess(
            restore.index("local replication all reject"),
            restore.index("local all postgres peer"),
        )
        self.assertLess(
            restore.index("host replication all 127.0.0.1/32 reject"),
            restore.index("host all all 127.0.0.1/32 reject"),
        )
        self.assertIn("archive_mode = off", restore)
        self.assertIn("ssl = off", restore)
        self.assertIn("max_wal_senders = 10", restore)
        self.assertNotIn("max_wal_senders = 0", restore)
        self.assertIn("SHOW data_directory", restore)
        self.assertIn("SHOW port", restore)
        self.assertIn("SHOW max_wal_senders", restore)
        self.assertIn("SELECT count(*) FROM pg_stat_replication", restore)
        self.assertIn("TCP access to isolated PostgreSQL unexpectedly succeeded", restore)
        self.assertIn("pg_hba.conf rejects connection", restore)
        self.assertIn("recovery_target = 'immediate'", restore)
        self.assertNotIn("archive_command =", restore)
        self.assertIn('chown root:root "$marker"', restore)
        self.assertIn('stat -c \'%U:%G:%a\' -- "$marker"', stop)

    def test_installer_copies_canonical_files_before_reload(self) -> None:
        installer = (ROOT / "install-desired-state.sh").read_text(encoding="utf-8")
        self.assertIn("/usr/local/libexec/caplab-p5-hostctl", installer)
        self.assertIn("/etc/caplab-p5/recovery.toml", installer)
        self.assertIn("-g caplab-p5 /etc/caplab-p5", installer)
        self.assertIn("systemctl daemon-reload", installer)
        self.assertNotIn("restic prune", installer)

    def test_pinned_source_tree_is_group_traversable_despite_executor_umask(
        self,
    ) -> None:
        hostctl = (ROOT / "caplab-p5-hostctl.py").read_text(encoding="utf-8")
        self.assertIn("os.chmod(VENV_ROOT, 0o750)", hostctl)
        self.assertIn('"u=rwX,g=rX,o="', hostctl)
        self.assertIn("os.chmod(CREDENTIAL_ROOT, 0o750)", hostctl)

    def test_role_login_verification_uses_postgres_boolean_text(self) -> None:
        hostctl = (ROOT / "caplab-p5-hostctl.py").read_text(encoding="utf-8")
        self.assertIn('"true" if expected_phase == "ready" else "false"', hostctl)

    def test_local_write_custody_uses_only_the_exact_content_prefix(self) -> None:
        hostctl = (ROOT / "caplab-p5-hostctl.py").read_text(encoding="utf-8")
        self.assertIn('LOCAL_COPY_PREFIX = LOCAL_COPY_ROOT / "objects/sha256/a1"', hostctl)
        self.assertIn("prepare_local_copy_prefix(corrective_retry=corrective_retry)", hostctl)
        self.assertNotIn("setfacl", hostctl)

    def test_disabled_quarantine_can_resume_without_rewriting_request(self) -> None:
        hostctl = (ROOT / "caplab-p5-hostctl.py").read_text(encoding="utf-8")
        self.assertIn('state.get("phase") == "disabled"', hostctl)
        self.assertIn('retained != "1|1|0|0"', hostctl)
        self.assertIn('"registration_runtime_commit"', hostctl)
        self.assertIn("P5 quarantine local copy is absent", hostctl)
        self.assertIn("ALTER ROLE caplab_p5_operator LOGIN", hostctl)
        self.assertIn("P4 runtime roles are not disabled during P5 retry", hostctl)
        self.assertIn("if not corrective_retry:", hostctl)


if __name__ == "__main__":
    unittest.main()
