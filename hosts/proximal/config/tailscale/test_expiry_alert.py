import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location('expiry_alert', Path(__file__).with_name('expiry_alert.py'))
alert = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alert)
NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)


def status(days):
    return {'BackendState': 'Running', 'Self': {'KeyExpiry': (NOW + timedelta(days=days)).isoformat()}}


class ExpiryAlertTest(unittest.TestCase):
    def test_thresholds_and_renewal(self):
        self.assertIsNone(alert.notice(status(14.001), NOW))
        for days, bucket in [(14, '14-days'), (7.001, '14-days'), (7, '7-days'),
                             (3.001, '7-days'), (3, '2026-10-13'), (0, '2026-10-13'),
                             (-1, '2026-10-13')]:
            with self.subTest(days=days):
                self.assertTrue(alert.notice(status(days), NOW)[0].endswith(bucket))
        self.assertIsNone(alert.notice(status(180), NOW))

    def test_null_expiry_and_malformed_observations(self):
        self.assertIsNone(alert.notice({'BackendState': 'Running', 'Self': {'KeyExpiry': None}}, NOW))
        for malformed in [{}, {'BackendState': 'Running'},
                          {'BackendState': 'Running', 'Self': {}},
                          {'BackendState': 'Running', 'Self': {'KeyExpiry': 'bad'}},
                          {'BackendState': 'Running', 'Self': {'KeyExpiry': '2027-01-01'}}]:
            with self.subTest(malformed=malformed), self.assertRaises((KeyError, ValueError)):
                alert.notice(malformed, NOW)

    def test_offline_warns_without_self(self):
        key, message = alert.notice({'BackendState': 'NeedsLogin'}, NOW)
        self.assertEqual(key, 'offline:2026-10-13')
        self.assertIn('offline', message)

    def test_duplicate_and_escalation_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def send(message, now):
                calls.append(message)
                return 'gateway-id'
            path = Path(directory)
            snapshot = status(14)
            self.assertEqual(alert.check(snapshot, NOW, path, send), 'accepted-by-gateway')
            self.assertEqual(alert.check(snapshot, NOW + timedelta(hours=1), path, send), 'already-alerted')
            self.assertEqual(alert.check(snapshot, NOW + timedelta(days=7), path, send), 'accepted-by-gateway')
            for day in (11, 12, 13, 14):
                self.assertEqual(alert.check(snapshot, NOW + timedelta(days=day), path, send), 'accepted-by-gateway')
            self.assertEqual(len(calls), 6)
            self.assertEqual(alert.check(status(180), NOW, path, send), 'outside-warning-window')

    def test_uncertain_send_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def fail(message, now):
                calls.append(message)
                raise TimeoutError('uncertain')
            for _ in range(2):
                with self.assertRaises((TimeoutError, RuntimeError)):
                    alert.check(status(7), NOW, Path(directory), fail)
            self.assertEqual(len(calls), 1)
            receipts = json.loads((Path(directory) / 'receipts.json').read_text())
            self.assertEqual(next(iter(receipts.values()))['status'], 'pending')

    def test_known_rejection_can_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            def reject(message, now):
                raise alert.NotSent('modem unavailable')
            with self.assertRaises(alert.NotSent):
                alert.check(status(7), NOW, Path(directory), reject)
            self.assertEqual(alert.check(status(7), NOW, Path(directory), lambda *_: 'id'), 'accepted-by-gateway')

    def test_corrupt_receipts_do_not_send(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'receipts.json').write_text('broken')
            def unexpected(*_):
                self.fail('sent after state corruption')
            with self.assertRaises(ValueError):
                alert.check(status(7), NOW, path, unexpected)


if __name__ == '__main__':
    unittest.main()
