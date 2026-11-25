import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / 'hosts/talos/config/striatum/rceb-supervisor.py'
spec = importlib.util.spec_from_file_location('rceb_supervisor', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RotationTests(unittest.TestCase):
    def test_handoff_precedes_rotation_and_blocks_work(self):
        state = {'phase': 'active', 'rotate_at': 10000}
        self.assertEqual(module.next_action(state, 8199), 'work')
        self.assertEqual(module.next_action(state, 8200), 'handoff')
        self.assertEqual(module.next_action(state, 20000), 'handoff')
        state['phase'] = 'handoff_saved'
        self.assertEqual(module.next_action(state, 9999), 'wait')
        self.assertEqual(module.next_action(state, 10000), 'rotate')

    def test_uncertain_turn_never_replays_even_when_overdue(self):
        for phase in ('new', 'ready', 'active', 'handoff_saved'):
            with self.subTest(phase=phase), self.assertRaisesRegex(RuntimeError, 'Unreconciled'):
                module.next_action({'phase': phase, 'rotate_at': 0, 'in_flight': {'attempt': 'old'}}, 100)

    def test_polling_does_not_spend_an_agent_turn(self):
        state = {'phase': 'active', 'rotate_at': 10000, 'next_turn_at': 500}
        self.assertEqual(module.next_action(state, 499), 'wait')
        self.assertEqual(module.next_action(state, 500), 'work')

    def test_handoff_rejects_another_thread_or_unresolved_effect(self):
        valid = {'thread_id': 't', 'generation': 'g', 'quiescent': True,
                 'unresolved_effects': [], 'handoff_record_id': '9ebe790f-caf0-493b-b1e9-a47899224037',
                 'handoff_version': 3}
        self.assertEqual(module.checked_receipt(valid, 't', 'g')['version'], 3)
        for change in ({'thread_id': 'other'}, {'generation': 'old'}, {'quiescent': False},
                       {'unresolved_effects': ['possibly committed']}, {'handoff_version': True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                module.checked_receipt(valid | change, 't', 'g')

    def supervisor(self, directory):
        supervisor = object.__new__(module.Supervisor)
        supervisor.directory = Path(directory)
        supervisor.path = Path(directory) / 'state.json'
        supervisor.config = {'initial_handoff': {'record_id': 'initial', 'version': 1},
                             'model': 'gpt-6.2-astra', 'codex_home': '/example/.codex-harm'}
        supervisor.state = {'phase': 'handoff_saved', 'rotate_at': 0, 'generation': 'old',
                            'handoff': {'record_id': 'next', 'version': 2},
                            'thread_id': 'old-thread', 'identity': {'agent_id': 'old-agent'}}
        (Path(directory) / 'old').mkdir()
        return supervisor

    def test_retirement_failure_cannot_launch_successor(self):
        with tempfile.TemporaryDirectory() as directory:
            supervisor = self.supervisor(directory)
            with patch.object(supervisor, 'heartbeat'), patch.object(supervisor, 'cairn',
                       side_effect=RuntimeError('stale execution')), patch.object(supervisor, 'run_turn') as run:
                with self.assertRaisesRegex(RuntimeError, 'stale execution'):
                    supervisor.tick()
                run.assert_not_called()
                self.assertEqual(supervisor.state['thread_id'], 'old-thread')

    def test_successor_has_no_inherited_thread_or_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            supervisor = self.supervisor(directory)
            fresh = supervisor.fresh(supervisor.state['handoff'])
            self.assertNotEqual(fresh['generation'], 'old')
            self.assertNotIn('thread_id', fresh)
            self.assertNotIn('identity', fresh)
            self.assertEqual(fresh['handoff'], {'record_id': 'next', 'version': 2})

    def test_completed_turn_is_not_reexecuted_after_transition_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            supervisor = self.supervisor(directory)
            (Path(directory) / 'answer.txt').write_text('saved result')
            supervisor.state['pending_result'] = {'mode': 'handoff', 'attempt': directory}
            with patch.object(module.subprocess, 'Popen') as popen:
                self.assertEqual(supervisor.run_turn('handoff'), 'saved result')
                popen.assert_not_called()

    def test_two_replacements_each_require_a_new_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            supervisor = self.supervisor(directory)
            identities = []

            def bootstrap(mode):
                self.assertEqual(mode, 'bootstrap')
                self.assertNotIn('thread_id', supervisor.state)
                supervisor.state['thread_id'] = 'thread-' + supervisor.state['generation']
                (supervisor.directory / supervisor.state['generation']).mkdir()
                return 'READY'

            def register():
                supervisor.state['identity'] = {'agent_id': supervisor.state['generation'],
                                                'display_name': 'fixture-agent',
                                                'inbox': 'agent/' + supervisor.state['generation']}
                supervisor.state['phase'] = 'ready'
                identities.append(supervisor.state['thread_id'])

            with patch.object(supervisor, 'heartbeat'), patch.object(supervisor, 'cairn'), \
                    patch.object(supervisor, 'notify_root'), patch.object(supervisor, 'run_turn', side_effect=bootstrap), \
                    patch.object(supervisor, 'register', side_effect=register):
                for version in (2, 3):
                    supervisor.state['phase'] = 'handoff_saved'
                    supervisor.state['rotate_at'] = 0
                    supervisor.state['handoff'] = {'record_id': 'next', 'version': version}
                    supervisor.tick()
                    self.assertEqual(supervisor.state['phase'], 'ready')
                    self.assertEqual(supervisor.state['handoff']['version'], version)
                self.assertEqual(len(set(identities)), 2)


if __name__ == '__main__':
    unittest.main()
