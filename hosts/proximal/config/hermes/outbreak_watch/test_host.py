"""Real Hermes script execution/delivery contract, isolated from Slack and live state."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from outbreak_watch.core import Store
from outbreak_watch.test_watch import fact, ground, panel


@unittest.skipUnless(
    os.environ.get("HERMES_SOURCE"), "set HERMES_SOURCE for installed cron integration"
)
class HostTest(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.environ["HERMES_SOURCE"])
        from cron import scheduler

        self.scheduler = scheduler
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"HERMES_HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.state = self.home / "watchdogs/outbreak-watch"
        self.state.mkdir(parents=True)
        Store.initialize(
            self.state / "state.sqlite3",
            {"schema": "outbreak-watch/ledger/1", "entries": []},
        )
        scripts = self.home / "scripts"
        scripts.mkdir()
        shutil.copytree(
            Path(__file__).parent,
            scripts / "outbreak_watch",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        payload = {"facts": [fact()], "grounding": ground(fact()), "panel": panel()}
        (scripts / "fixture.json").write_text(json.dumps(payload))
        (scripts / "fixture.py").write_text("""from pathlib import Path
from datetime import date
import json
from outbreak_watch import runtime
class Fixture:
    members = ['fable', 'sol', 'agy', 'glm']
    today = date(2026, 10, 7)
    def __init__(self, home, state, artifact):
        self.data = json.loads((home/'scripts/fixture.json').read_text())
    def scan(self, registry): return {'facts': self.data['facts']}
    def ground(self, item): return self.data['grounding']
    def review(self, *args): return self.data['panel']
    def record(self, *args): pass
runtime.Live = Fixture
raise SystemExit(runtime.main())
""")
        self.job = {
            "id": "isolated-outbreak-contract",
            "name": "isolated outbreak contract",
            "no_agent": True,
            "script": "fixture.py",
            "deliver": "local",
            "failure_deliver": "local",
        }

    def run_job(self):
        # Executes actual subprocess and returns its response; this method does not deliver.
        return self.scheduler.run_job(self.job)

    def test_actual_cron_returns_alert_then_silence(self):
        ok, _, response, error = self.run_job()
        self.assertTrue(ok, error)
        self.assertIn("TRIGGER", response)
        self.assertIsNone(error)
        ok, _, response, error = self.run_job()
        self.assertTrue(ok, error)
        self.assertEqual(response, "[SILENT]")
        self.assertTrue(self.scheduler._is_cron_silence_response(response))

    def test_failed_state_stays_local_and_is_not_recreated(self):
        (self.state / "state.sqlite3").unlink()
        ok, _, response, error = self.run_job()
        self.assertFalse(ok)
        self.assertIn("Script exited with code 1", error)
        self.assertFalse((self.state / "state.sqlite3").exists())
        # The actual scheduler resolves the failure lane to local, not the success target.
        self.assertEqual(
            self.scheduler._delivery_lane_value(self.job, for_failure=True), "local"
        )

    def test_partial_panel_is_silent_at_scheduler_boundary(self):
        p = self.home / "scripts/fixture.json"
        data = json.loads(p.read_text())
        data["panel"]["status"] = "partial"
        p.write_text(json.dumps(data))
        ok, _, response, error = self.run_job()
        self.assertTrue(ok, error)
        self.assertEqual(response, "[SILENT]")


@unittest.skipUnless(
    os.environ.get("HERMES_SOURCE"), "set HERMES_SOURCE for installer integration"
)
class InstallTest(unittest.TestCase):
    def test_existing_job_migration_and_managed_file_conflict(self):
        sys.path.insert(0, os.environ["HERMES_SOURCE"])
        from cron.jobs import create_job, get_job
        from outbreak_watch import install

        with (
            tempfile.TemporaryDirectory() as d,
            patch.dict(os.environ, {"HERMES_HOME": d}),
        ):
            home = Path(d)
            state = home / "watchdogs/outbreak-watch"
            state.mkdir(parents=True)
            legacy = {
                "schema": "outbreak-watch/ledger/1",
                "entries": [{"key": "old", "fact": "Old fact", "status": "suppressed"}],
            }
            (state / "LEDGER.json").write_text(json.dumps(legacy))
            (state / "CRITERIA.md").write_text("old criteria")
            job = create_job(
                "old prompt", "0 7 * * *", name="outbreak-watch", deliver="local"
            )
            with patch.object(install, "JOB_ID", job["id"]):
                result = install.install(home, Path(__file__).parent.parent, True)
                updated = get_job(job["id"])
                self.assertTrue(updated["no_agent"])
                self.assertEqual(updated["script"], "outbreak_watch_job.py")
                self.assertEqual(updated["schedule"], job["schedule"])
                self.assertEqual(updated["next_run_at"], job["next_run_at"])
                self.assertEqual(
                    json.loads((state / "LEDGER.json").read_text()), legacy
                )
                self.assertTrue((Path(result["backup"]) / "job.json").exists())
                (state / "CRITERIA.md").write_text("concurrent edit")
                with self.assertRaisesRegex(RuntimeError, "managed file changed"):
                    install.install(home, Path(__file__).parent.parent, True)


if __name__ == "__main__":
    unittest.main()
