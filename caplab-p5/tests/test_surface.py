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
        self.assertEqual(config["campaign"]["runtime_commit"], source_commit)
        self.assertEqual(
            config["campaign"]["campaign_id"],
            "caplab-p5-recovery-2026-07-16",
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
        restore = (ROOT / "bin/pgbackrest-restore-isolated").read_text(encoding="utf-8")
        self.assertIn("/var/tmp/caplab-p5-pgrestore", restore)
        self.assertIn("55435", restore)
        self.assertIn('--pg1-path="$target"', restore)
        self.assertNotIn("systemctl stop postgresql", restore)
        self.assertNotIn("/var/lib/postgresql/17/main", restore)

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


if __name__ == "__main__":
    unittest.main()
