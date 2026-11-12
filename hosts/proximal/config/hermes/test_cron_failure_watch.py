import unittest

from cron_failure_watch import check


def job(streak, status="error", jid="j1", name="outbreak-watch", enabled=True):
    return {
        "id": jid,
        "name": name,
        "enabled": enabled,
        "failure_streak": streak,
        "last_status": status,
        "last_run_at": "2026-11-11T07:00:03-08:00",
        "last_error": "Script exited with code 1\nstdout:\n[SILENT]",
    }


class CheckTest(unittest.TestCase):
    def test_below_threshold_is_silent(self):
        self.assertEqual(check([job(2)], {}), ([], {}))

    def test_notifies_once_per_streak(self):
        lines, state = check([job(3)], {})
        self.assertIn("outbreak-watch (j1): 3 failed runs in a row", lines[1])
        self.assertIn("Script exited with code 1", lines[1])
        self.assertEqual(state, {"j1": 3})
        self.assertEqual(check([job(9)], state), ([], {"j1": 3}))

    def test_recovery_reported_then_rearmed(self):
        lines, state = check([job(0, "ok")], {"j1": 3})
        self.assertEqual(
            lines, ["Recovered:", "• outbreak-watch (j1) succeeded again."]
        )
        self.assertEqual(state, {})
        self.assertTrue(check([job(3)], state)[0])

    def test_reset_between_checks_counts_as_recovery_and_new_streak(self):
        lines, state = check([job(4)], {"j1": 5})
        self.assertTrue(any("succeeded again" in x for x in lines))
        self.assertTrue(any("4 failed runs" in x for x in lines))
        self.assertEqual(state, {"j1": 4})

    def test_skips_itself_and_disabled_jobs(self):
        jobs = [job(5, name="cron-failure-watch"), job(5, jid="j2", enabled=False)]
        self.assertEqual(check(jobs, {}), ([], {}))


if __name__ == "__main__":
    unittest.main()
