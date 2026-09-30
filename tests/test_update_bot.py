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
PUB_SPEC = importlib.util.spec_from_file_location('maintenance_publish', SOURCE.parent / 'publish.py')
publisher = importlib.util.module_from_spec(PUB_SPEC)
PUB_SPEC.loader.exec_module(publisher)


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

    def test_run_message_renders_structured_sections_not_prose(self):
        report = dict(
            status='partial', summary='prose ' * 250, notification='',
            checked=[dict(target='llama.cpp', evidence='build 11256', outcome='updated'),
                     dict(target='claude', evidence='npm view=2.1.284', outcome='current; no-op')],
            deferred=[dict(target='hermes', reason='patch does not apply ' + 'x' * 400,
                           proposed_action='port the carried commits', verification='tests pass',
                           recovery='additive')],
            unchecked=['Only host proximal was inspected'],
            changes=[dict(target='llama.cpp', operation_id='abc', before='b' * 300,
                          after='a' * 300, status='verified', verification='exit 0',
                          activation='installed')])
        message = bot.report_message({'status': 'partial', 'started': 0, 'finished': 600}, report)
        self.assertTrue(message.startswith('*Proximal maintenance — finished with issues* · 10 min'))
        self.assertIn('1 item waiting for follow-up', message)
        self.assertIn('• *llama.cpp* — verified:', message)
        self.assertIn('    activation: installed', message)
        self.assertIn('next: port the carried commits', message)
        self.assertIn('*Other checks*', message)
        self.assertIn('• *claude* — current; no-op', message)
        self.assertIn('• Only host proximal was inspected', message)
        # One clipped line per field, not the model's paragraph.
        self.assertNotIn('prose prose prose', message)
        self.assertLess(len(message), 4000)

    def test_brief_keeps_failures_and_coverage_visible_without_dumping_receipts(self):
        report = ReportTests().report()
        report.update(notification='Codex is ready for new sessions.\n• I will retry the model build next run.',
                      changes=[dict(target='llama.cpp', status='failed', before='private diagnostic',
                                    after='diagnostic', activation='not installed')])
        message = bot.report_message({'status': 'partial', 'started': 0, 'finished': 60}, report)
        self.assertIn(report['notification'], message)
        self.assertIn('Failed or rolled back: llama.cpp', message)
        self.assertIn('1 area not checked', message)
        self.assertNotIn('private diagnostic', message)
        self.assertNotIn(report['summary'], message)

    def test_successful_change_gets_one_run_report_but_noop_stays_quiet(self):
        report = ReportTests().report()
        report['notification'] = 'Codex updated. No action needed from you.'
        latest = dict(status='completed', recording='recorded', evidence='/fixture', run_id='r4')
        with patch.object(bot, 'read_json', return_value=report):
            messages = self.check(latest, {'finished': 199900}, {'ActiveState': 'inactive'})
            self.assertEqual([key for key, _ in messages], ['run:r4'])
            self.assertIn(report['notification'], messages[0][1])
            report['notification'] = ''
            self.assertEqual(self.check(latest, {'finished': 199900}, {'ActiveState': 'inactive'}), [])

    def test_old_successful_report_does_not_hide_new_service_failure(self):
        latest = dict(status='completed', recording='recorded', evidence='/fixture', run_id='r4')
        messages = self.check(latest, {'finished': 199900},
                              {'ActiveState': 'failed', 'Result': 'signal', 'InvocationID': 'i5'})
        self.assertEqual(messages, [('service:i5', 'Maintenance service failed: signal')])

    def test_slack_envelope_has_details_link_and_bounded_fallback(self):
        latest = dict(run_id='12345678-aaaa', evidence='/var/lib/update-bot/runs/example')
        for publication in ({'status': 'pushed', 'commit': 'abc123'}, {}):
            message = bot.slack_message('Long diagnostic ' * 1000, latest, publication)
            self.assertLessEqual(len(message), 4000)
            self.assertIn('Run 12345678', message)
            self.assertNotIn('Policy:', message)
            if publication:
                self.assertIn('<https://github.com/halbritt/infra/commit/abc123|Full report>', message)
            else:
                self.assertIn(latest['evidence'], message)

    def test_large_legacy_report_leaves_room_for_omission_notice(self):
        report = ReportTests().report()
        report['unchecked'] = ['Long coverage limitation ' * 30] * 80
        message = bot.report_message({'status': 'partial'}, report)
        self.assertLessEqual(len(message), bot.SLACK_BUDGET)
        self.assertIn('more detail lines in the full report', message)

    def test_run_message_falls_back_to_prose_without_a_report(self):
        latest = {'status': 'running', 'run_id': 'r3', 'error': 'launcher killed',
                  'evidence': '/nonexistent/run'}
        self.assertEqual(bot.run_message(latest), 'Maintenance interrupted: launcher killed')
        self.assertIn('inference unavailable',
                      bot.run_message({'status': 'failed', 'error': 'inference unavailable'}))


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
    def test_native_os_noop_does_not_create_a_git_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'runs' / 'r1'
            op = folder / 'operations' / 'o1'
            op.mkdir(parents=True)
            (folder / 'status.json').write_text(json.dumps(dict(
                stage='maintenance-v2', status='completed', run_id='r1')))
            (op / 'intent.json').write_text('{"target":"os"}')
            (op / 'result.json').write_text('{"status":"verified","changed":false}')
            with patch.object(bot, 'STATE', root), patch.object(bot, 'operations_active', return_value=False), \
                 patch.object(publisher, 'git') as git:
                publisher.publish()
                git.assert_not_called()
            self.assertEqual(json.loads((folder / 'publication.json').read_text())['status'], 'noop')

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
            for target, unit in [('os', 'update-bot-os.service'),
                                 ('hermes', 'update-bot-hermes-activate.service'),
                                 ('herdr-archon', 'update-bot-herdr-archon.service')]:
                (folder / 'intent.json').write_text(json.dumps(dict(
                    request, target=target, argv=['systemctl', 'start', unit])))
                with patch.object(bot, 'command', return_value=SimpleNamespace(stdout='activating\n')):
                    self.assertTrue(bot.operations_active(root))
                with patch.object(bot, 'command', return_value=SimpleNamespace(stdout='inactive\n')):
                    self.assertFalse(bot.operations_active(root))

    def test_archon_herdr_only_accepts_fixed_service(self):
        status = dict(run_id='r1', status='running', started=100)
        settings = dict(stage='maintenance-v2', update_targets=['herdr-archon'], agent_timeout_seconds=900)
        request = dict(run_id='r1', target='herdr-archon', argv=['ssh', 'archon', 'reboot'],
                       before='old', recovery='backup', verify_argv=['true'])
        with self.assertRaises(ValueError):
            operation.validate(request, status, settings, 200)
        request['argv'] = ['systemctl', 'start', 'update-bot-herdr-archon.service']
        operation.validate(request, status, settings, 200)

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


class HerdrRemoteTests(unittest.TestCase):
    @staticmethod
    def module(path, name):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def remote_run(self, after='herdr 0.9.3', preserved=True):
        import io
        remote = self.module(SOURCE.parents[3] / 'archon/config/updates/herdr_update.py', 'remote_herdr')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            binary = root / 'herdr'
            binary.write_bytes(b'old binary')
            before = {'123': ['100', 1, 44]}
            live = before if preserved else {'123': ['100', 1, 55]}
            def native_update(argv, **kwargs):
                if after == 'herdr 0.9.3':
                    Path(argv[4]).write_bytes(b'new binary')
                return SimpleNamespace(returncode=0)
            with patch.multiple(remote, STATE=root / 'state', BINARY=str(binary)), \
                 patch.object(remote.sys, 'argv', ['herdr_update.py']), \
                 patch.object(remote.os, 'geteuid', return_value=0), \
                 patch.object(remote.os, 'chown'), \
                 patch.object(remote, 'command', side_effect=['stable', 'stable', 'herdr 0.9.0', after, after]), \
                 patch.object(remote, 'processes', side_effect=[before, live, live]), \
                 patch.object(remote.urllib.request, 'urlopen', return_value=io.StringIO('{"tag_name":"v0.9.3"}')), \
                 patch.object(remote.subprocess, 'run', side_effect=native_update) as native:
                code = remote.run()
            self.assertEqual(binary.read_bytes(), b'new binary' if preserved and after == 'herdr 0.9.3' else b'old binary')
            receipt = json.loads((root / 'state/latest.json').read_text())
            self.assertEqual(Path(receipt['backup']).read_bytes(), b'old binary')
            self.assertEqual(native.call_args.args[0][:4], ['runuser', '-u', 'halbritt', '--'])
            self.assertEqual(native.call_args.args[0][-1], 'update')
            self.assertNotIn('--handoff', native.call_args.args[0])
            self.assertEqual(native.call_args.kwargs['stdin'], subprocess.DEVNULL)
            return code, receipt

    def test_native_zero_exit_without_install_is_not_verified(self):
        code, receipt = self.remote_run(after='herdr 0.9.0')
        self.assertEqual((code, receipt['status']), (1, 'failed'))

    def test_target_version_and_retained_processes_are_required(self):
        code, receipt = self.remote_run()
        self.assertEqual((code, receipt['status']), (0, 'verified'))
        code, receipt = self.remote_run(preserved=False)
        self.assertEqual((code, receipt['status']), (1, 'failed'))

    def test_uncertain_ssh_is_never_repeated_automatically(self):
        helper = self.module(SOURCE.parent / 'herdr_archon.py', 'herdr_archon')
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(bot, 'STATE', Path(folder)), \
             patch.object(helper.sys, 'argv', ['herdr_archon.py']), \
             patch.object(helper.subprocess, 'run', return_value=SimpleNamespace(
                 returncode=255, stdout='', stderr='connection lost')) as ssh:
            self.assertEqual(helper.run(), 1)
            with self.assertRaisesRegex(RuntimeError, 'no automatic retry'):
                helper.run()
            self.assertEqual(ssh.call_count, 1)
            self.assertEqual(json.loads((Path(folder) / 'herdr-archon-latest.json').read_text())['status'], 'uncertain')
