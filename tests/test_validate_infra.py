from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


VALIDATOR = Path(__file__).resolve().parents[1] / "scripts" / "validate-infra.py"


class InfrastructureValidationTests(unittest.TestCase):
    def make_repository(self, root: Path) -> Path:
        (root / "scripts").mkdir()
        shutil.copy2(VALIDATOR, root / "scripts" / "validate-infra.py")
        (root / "roles").mkdir()
        (root / "hosts").mkdir()
        (root / "secrets").mkdir()
        (root / "secrets" / "README.md").write_text("# Secrets\n", encoding="utf-8")
        device = root / "devices" / "home-assistant-yellow"
        device.mkdir(parents=True)
        (device / "README.md").write_text("# Home Assistant Yellow\n", encoding="utf-8")
        return device

    def run_validator(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(root / "scripts" / "validate-infra.py")],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

    def write_device_manifest(self, device: Path, *, create_documents: bool) -> None:
        (device / "device.yaml").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "name": "home-assistant-yellow",
                    "resource_type": "device",
                    "paths": {
                        "notes": "notes.md",
                        "changelog": "CHANGELOG.md",
                    },
                }
            ),
            encoding="utf-8",
        )
        if create_documents:
            (device / "notes.md").write_text("# Notes\n", encoding="utf-8")
            (device / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

    def test_device_without_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.make_repository(root)
            completed = self.run_validator(root)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("devices/home-assistant-yellow: device.yaml is missing", completed.stderr)

    def test_device_manifest_name_must_match_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            device = self.make_repository(root)
            (device / "device.yaml").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "homeassistant",
                        "resource_type": "device",
                    }
                ),
                encoding="utf-8",
            )

            completed = self.run_validator(root)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("device.yaml: name must match the directory", completed.stderr)

    def test_valid_device_is_counted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            device = self.make_repository(root)
            self.write_device_manifest(device, create_documents=True)

            completed = self.run_validator(root)

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("1 device(s)", completed.stdout)

    def test_device_manifest_paths_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            device = self.make_repository(root)
            self.write_device_manifest(device, create_documents=False)

            completed = self.run_validator(root)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("paths.notes does not exist: notes.md", completed.stderr)
            self.assertIn("paths.changelog does not exist: CHANGELOG.md", completed.stderr)


if __name__ == "__main__":
    unittest.main()
