"""Nightly can retry a proven no-start, while a launched/uncertain command stays distinct."""

import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import unittest

HELPER = Path(__file__).resolve().parents[1] / 'shared/agent-ee/ae-ci-outcome.py'


class ExecOutcomeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='ae-outcome-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.record = self.root / 'execution.json'

    def run_case(self, code):
        return subprocess.run([sys.executable, str(HELPER), 'run', '--record', str(self.record),
                               '--runner', str(HELPER), '--', sys.executable, '-c', code],
                              capture_output=True, text=True, timeout=10)

    def test_admission_no_start_is_completed_and_preserves_original_exit(self):
        result = self.run_case('raise SystemExit(75)')
        self.assertEqual(result.returncode, 75, result.stderr)
        record = json.loads(self.record.read_text())
        self.assertEqual(record['state'], 'not_started')
        self.assertTrue(record['complete'])
        self.assertEqual(record['exit_code'], 75)

    def test_marked_command_failure_cannot_masquerade_as_a_no_start(self):
        code = ('import os,subprocess,sys; '
                f'subprocess.run([sys.executable,{str(HELPER)!r},"mark-started",'
                'os.environ["AE_CI_OUTCOME_FILE"]],check=True); raise SystemExit(2)')
        result = self.run_case(code)
        self.assertEqual(result.returncode, 2, result.stderr)
        record = json.loads(self.record.read_text())
        self.assertEqual(record['state'], 'started_or_uncertain')
        self.assertTrue(record['complete'])

    def test_existing_attempt_is_not_overwritten_or_replayed(self):
        self.record.write_text('{"old":"attempt"}')
        side_effect = self.root / 'executed'
        result = self.run_case(f'from pathlib import Path; Path({str(side_effect)!r}).touch()')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(side_effect.exists())
        self.assertEqual(json.loads(self.record.read_text()), {'old': 'attempt'})

    def test_invalid_child_transition_cannot_leave_a_false_completed_no_start(self):
        code = ('import os,json,pathlib; p=pathlib.Path(os.environ["AE_CI_OUTCOME_FILE"]); '
                'r=json.loads(p.read_text()); r.update(state="not_started",complete=True); '
                'p.write_text(json.dumps(r))')
        result = self.run_case(code)
        self.assertNotEqual(result.returncode, 0)
        record = json.loads(self.record.read_text())
        self.assertFalse(record['complete'])
        self.assertEqual(record['state'], 'uncertain')

    def test_interrupted_attempt_remains_uncertain_and_forwards_termination(self):
        code = ('import os,signal,subprocess,sys; signal.alarm(4); '
                f'subprocess.run([sys.executable,{str(HELPER)!r},"mark-started",'
                'os.environ["AE_CI_OUTCOME_FILE"]],check=True); '
                'print("ready",flush=True); signal.pause()')
        proc = subprocess.Popen([sys.executable, str(HELPER), 'run', '--record', str(self.record),
                                 '--runner', str(HELPER), '--', sys.executable, '-c', code],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                self.assertTrue(selector.select(timeout=3), 'fixture did not reach command boundary')
                self.assertEqual(proc.stdout.readline().strip(), 'ready')
            proc.send_signal(signal.SIGTERM)
            proc.communicate(timeout=5)
            record = json.loads(self.record.read_text())
            self.assertFalse(record['complete'])
            self.assertEqual(record['state'], 'interrupted')
            self.assertEqual(proc.returncode, 128 + signal.SIGTERM)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()
