"""Acceptance-sensitive report and independent failure classification checks."""
import importlib.util
import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
import sys
import subprocess
import time
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / 'hosts/proximal/config/update-bot/update_bot.py'
SPEC = importlib.util.spec_from_file_location('update_bot', SOURCE)
bot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bot)
sys.modules['update_bot'] = bot
OP_SPEC = importlib.util.spec_from_file_location('maintenance_operation', SOURCE.parent / 'operation.py')
operation = importlib.util.module_from_spec(OP_SPEC)
OP_SPEC.loader.exec_module(operation)
OS_SPEC = importlib.util.spec_from_file_location('maintenance_os', SOURCE.parent / 'os_update.py')
os_update = importlib.util.module_from_spec(OS_SPEC)
OS_SPEC.loader.exec_module(os_update)


class ReportTests(unittest.TestCase):
    def report(self):
        return dict(status='completed', summary='Bounded survey complete',
                    checked=[dict(target='service', evidence='health returned 200', outcome='healthy')],
                    deferred=[], unchecked=['Other services'], notification='')

    def test_successful_bounded_survey_keeps_coverage_limits(self):
        result = bot.validate_report(json.dumps(self.report()), {'completed': True})
        self.assertEqual(result['unchecked'], ['Other services'])

    def test_presentation_preamble_or_fence_does_not_discard_valid_evidence(self):
        raw = json.dumps(self.report())
        for wrapped in ('Survey complete.\n' + raw, '```json\n' + raw + '\n```'):
            self.assertEqual(bot.validate_report(wrapped, {'completed': True})['status'], 'completed')
        with self.assertRaises(ValueError):
            bot.validate_report(raw + '\n' + raw, {'completed': True})

    def test_final_prose_does_not_hide_provider_or_budget_failure(self):
        for usage in ({}, {'completed': False}, {'completed': True, 'failed': True}):
            with self.assertRaises(ValueError):
                bot.validate_report(json.dumps(self.report()), usage)

    def test_secret_shaped_output_is_never_published(self):
        report = self.report()
        report['notification'] = 'sk-or-v1-' + 'a' * 40
        with self.assertRaises(ValueError):
            bot.validate_report(json.dumps(report), {'completed': True})

    def test_empty_survey_is_not_a_successful_noop(self):
        report = self.report()
        report['checked'] = []
        with self.assertRaises(ValueError):
            bot.validate_report(json.dumps(report), {'completed': True})


class MonitorTests(unittest.TestCase):
    settings = {'overdue_seconds': 108000}

    def check(self, latest, completed, service, now=200000):
        return bot.monitor_messages(latest, completed, service, self.settings, now)

    def test_quiet_healthy_noop(self):
        self.assertEqual(self.check({'status': 'completed'}, {'finished': 199900},
                                    {'ActiveState': 'inactive', 'Result': 'success'}), [])

    def test_killed_launcher_is_visible_without_agent_finalization(self):
        result = self.check({'status': 'running', 'run_id': 'r1'}, {'finished': 199900},
                            {'ActiveState': 'failed', 'Result': 'signal'})
        self.assertIn('interrupted', result[0][1])

    def test_missing_launch_is_visible(self):
        self.assertEqual(self.check({}, {}, {'ActiveState': 'inactive'})[0][0], 'overdue')

    def test_partial_does_not_reset_completion_deadline(self):
        result = self.check({'status': 'partial', 'run_id': 'r1'}, {'finished': 1},
                            {'ActiveState': 'failed', 'Result': 'exit-code'})
        self.assertEqual([item[0] for item in result], ['overdue', 'run:r1'])

    def test_provider_failure_is_visible_without_model(self):
        result = self.check({'status': 'failed', 'run_id': 'r2', 'error': 'inference unavailable'},
                            {'finished': 199900}, {'ActiveState': 'failed'})
        self.assertIn('inference unavailable', result[0][1])


class RunnerFailureTests(unittest.TestCase):
    def exercise(self, hermes_exit=0, record_failure=False, retry=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, state = root / 'config', root / 'state'
            config.mkdir()
            (config / 'settings.json').write_text(json.dumps(dict(
                host='test', stage='discovery-v1', model='test', provider='test', agent_timeout_seconds=5)))
            for file in ['policy.md', 'role.md', 'hermes.yaml']:
                (config / file).write_text('fixture')
            report = ReportTests().report()
            hermes = root / 'fake-hermes'
            hermes.write_text('#!/usr/bin/python3\nimport sys,json\nfrom pathlib import Path\n'
                              + 'Path(sys.argv[sys.argv.index("--usage-file")+1]).write_text('
                              + repr('{"completed":true}') + ')\nprint('
                              + repr(json.dumps(report)) + ')\nsys.exit(' + str(hermes_exit) + ')\n')
            hermes.chmod(0o700)
            recording_ids = []
            def record(args, **kwargs):
                if args[0] == 'remember':
                    recording_ids.append(args[args.index('--request-id') + 1])
                if args[0] == 'remember' and record_failure:
                    raise RuntimeError('injected recording outage')
                return {'ok': True, 'data': {}}
            with patch.multiple(bot, CONFIG=config, STATE=state, HERMES=str(hermes)), \
                 patch.dict(bot.os.environ, {'INVOCATION_ID': 'test'}), \
                 patch.object(bot, 'credential', return_value='dummy-test-credential'), \
                 patch.object(bot, 'cairn', side_effect=record):
                rc = bot.run()
                if retry:
                    record_failure = False
                    rc = bot.run()
            status = json.loads((state / 'latest.json').read_text())
            status['_test_recording_ids'] = recording_ids
            return rc, status, (state / 'last-completed.json').exists()

    def test_runner_records_inference_failure_without_success_receipt(self):
        rc, status, completed = self.exercise(hermes_exit=1)
        self.assertEqual((rc, status['status'], completed), (1, 'failed', False))

    def test_recording_outage_retains_request_identity_and_does_not_claim_completion(self):
        rc, status, completed = self.exercise(record_failure=True)
        self.assertEqual((rc, status['recording'], completed), (1, 'pending', False))
        self.assertIn('checkpoint_request_id', status)

    def test_successful_noop_records_completion_without_host_changes(self):
        rc, status, completed = self.exercise()
        self.assertEqual((rc, status['status'], status['recording'], completed),
                         (0, 'completed', 'recorded', True))
        self.assertFalse(status['host_mutations_authorized'])

    def test_recording_retry_reuses_exact_request_before_new_discovery(self):
        rc, status, completed = self.exercise(record_failure=True, retry=True)
        self.assertEqual((rc, completed), (0, True))
        ids = status['_test_recording_ids']
        self.assertEqual(ids[0], ids[1])
        self.assertNotEqual(ids[1], ids[2])
        self.assertIn('reconciled_checkpoint', status)


class MaintenanceBoundaryTests(unittest.TestCase):
    def test_os_start_is_fixed_and_native_service_keeps_drain_active(self):
        status = dict(run_id='r1', status='running', started=100)
        settings = dict(stage='maintenance-v2', update_targets=['os'], agent_timeout_seconds=900)
        request = dict(run_id='r1', target='os', argv=['sudo', 'apt-get', 'upgrade'],
                       before='old', recovery='hold restarts', verify_argv=['true'])
        with self.assertRaises(ValueError):
            operation.validate(request, status, settings, 200)
        request['argv'] = ['systemctl', 'start', 'update-bot-os.service']
        operation.validate(request, status, settings, 200)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'operations' / 'op1'
            folder.mkdir(parents=True)
            (folder / 'intent.json').write_text(json.dumps(request))
            with patch.object(bot, 'command', return_value=SimpleNamespace(stdout='activating\n')):
                self.assertTrue(bot.operations_active(root))
            with patch.object(bot, 'command', return_value=SimpleNamespace(stdout='inactive\n')):
                self.assertFalse(bot.operations_active(root))

    def test_claimed_verification_requires_native_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = ReportTests().report()
            op_id = '0654f626-cd30-4e2a-8c8b-0bea29bdf273'
            report['changes'] = [dict(target='codex', operation_id=op_id, before='old',
                after='new', status='verified', verification='claimed', activation='installed')]
            (root / 'stdout.json').write_text(json.dumps(report))
            (root / 'usage.json').write_text('{"completed":true}')
            folder = root / 'operations' / op_id
            folder.mkdir(parents=True)
            (folder / 'intent.json').write_text('{"target":"codex"}')
            (folder / 'result.json').write_text('{"status":"failed"}')
            with self.assertRaisesRegex(ValueError, 'disagrees'):
                bot.finish_report(root, {})

    def test_only_approved_targets_owned_by_current_run_before_deadline(self):
        status = dict(run_id='r1', status='running', started=100)
        settings = dict(stage='maintenance-v2', update_targets=['opencode'], agent_timeout_seconds=900)
        request = dict(run_id='r1', target='opencode', argv=['true'], before='old',
                       recovery='prior version retained', verify_argv=['true'])
        operation.validate(request, status, settings, 200)
        for bad in (dict(request, target='postgres'), dict(request, run_id='r2')):
            with self.assertRaises(ValueError):
                operation.validate(bad, status, settings, 200)
        with self.assertRaises(ValueError):
            operation.validate(request, status, settings, 1000)

    def test_native_operation_lock_survives_detached_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'operations' / 'op1'
            folder.mkdir(parents=True)
            child = subprocess.Popen([sys.executable, '-c',
                'import fcntl,sys,time; f=open(sys.argv[1],"a"); fcntl.flock(f,fcntl.LOCK_EX); print("ready",flush=True); time.sleep(0.8)',
                str(folder / 'active.lock')], stdout=subprocess.PIPE, text=True, start_new_session=True)
            self.assertEqual(child.stdout.readline().strip(), 'ready')
            self.assertTrue(bot.operations_active(root))
            bot.drain_operations(root)
            child.wait()
            child.stdout.close()
            self.assertFalse(bot.operations_active(root))

    def test_os_scope_keeps_database_cluster_and_gpu_packages_out(self):
        for name in ['postgresql', 'postgresql-18', 'kubelet', 'containerd.io', 'nvidia-container-toolkit']:
            self.assertTrue(os_update.PROTECTED.match(name), name)
        for name in ['curl', 'libaudit1', 'linux-image-generic']:
            self.assertFalse(os_update.PROTECTED.match(name), name)
        def version(origin, archive):
            return SimpleNamespace(origins=[SimpleNamespace(origin=origin, archive=archive)])
        self.assertTrue(os_update.approved_origin(version('Ubuntu', 'noble-security')))
        self.assertFalse(os_update.approved_origin(version('Ubuntu', 'noble-proposed')))
        self.assertFalse(os_update.approved_origin(version('PostgreSQL', 'noble-pgdg')))


if __name__ == '__main__':
    unittest.main()
