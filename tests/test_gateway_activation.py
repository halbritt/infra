"""Native SDK and systemd are external boundaries; status/markers are real files."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'hosts/proximal/config/update-bot'
for name in ('update_bot', 'gateway_activate'):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
gateway = sys.modules['gateway_activate']


class GatewayActivationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.launcher = self.root / 'hermes'
        self.launcher.write_text('fixture versioned launcher')
        self.revision = 'a' * 40
        self.pid = 101
        self.clock = 0
        self.mode = 'idle'
        self.actions = []
        self.status = self.home / 'gateway_state.json'
        self.marker = self.home / '.drain_request.json'
        self.write_status()
        (self.root / 'hermes-installed.json').write_text(json.dumps({
            'source': str(self.root / 'generation'), 'source_revision': self.revision,
            'artifacts': [{'installed': str(self.launcher),
                           'sha256': hashlib.sha256(self.launcher.read_bytes()).hexdigest()}]}))
        sdk = SimpleNamespace(write_drain_request=self.begin, clear_drain_request=self.clear)
        patches = [patch.object(gateway.bot, 'STATE', self.root),
                   patch.object(gateway, 'HOME', self.home), patch.object(gateway, 'LAUNCHER', self.launcher),
                   patch.dict(sys.modules, {'gateway': SimpleNamespace(drain_control=sdk), 'gateway.drain_control': sdk}),
                   patch.object(gateway.subprocess, 'check_output', side_effect=self.command),
                   patch.object(gateway.time, 'monotonic', side_effect=lambda: self.clock),
                   patch.object(gateway.time, 'sleep', side_effect=self.tick)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tick(self, seconds):
        self.clock += seconds

    def write_status(self, state='running', active=0, revision=None, pid=None):
        self.status.write_text(json.dumps({'pid': self.pid if pid is None else pid,
            'gateway_state': state, 'active_agents': active, 'code_sha': revision or 'b' * 40,
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'platforms': {'slack': {'state': 'connected', 'updated_at': datetime.now(timezone.utc).isoformat()}}}))

    def begin(self, *, principal, **kwargs):
        self.marker.write_text(json.dumps({'principal': principal}))
        self.write_status('draining', active=1 if self.mode == 'busy' else 0,
                          pid=999 if self.mode == 'foreign-pid' else self.pid)
        if self.mode == 'stale':
            stale = json.loads(self.status.read_text())
            stale['updated_at'] = '1970-01-01T00:00:01+00:00'
            self.status.write_text(json.dumps(stale))
        if self.mode == 'switched':
            self.pid = 202
        if self.mode == 'replaced-marker':
            self.marker.write_text('{"principal":"another-operator"}')

    def clear(self, **kwargs):
        self.marker.unlink()
        self.write_status(revision=self.revision if self.pid == 202 else None)
        return True

    def command(self, argv, **kwargs):
        if argv[0] == 'git':
            return self.revision + '\n'
        if 'MainPID' in argv:
            return str(self.pid)
        if 'ExecStart' in argv:
            return '{ path=' + str(self.launcher) + ' ; argv[]=' + str(self.launcher) + ' gateway run ; }'
        self.actions.append(argv[2])
        if argv[2] == 'reload':
            self.pid = 202
            self.write_status('draining', revision=('c' * 40 if self.mode == 'wrong-generation' else self.revision))
        return ''

    def test_idle_gateway_switches_once_and_releases_owned_drain(self):
        result = gateway.activate()
        self.assertEqual((result['status'], result['changed'], result['pid']), ('verified', True, 202))
        self.assertEqual(self.actions, ['reload'])
        self.assertFalse(self.marker.exists())
        self.assertEqual(json.loads(self.status.read_text())['gateway_state'], 'running')

    def test_busy_stale_or_foreign_state_never_restarts(self):
        for mode in ('busy', 'stale', 'foreign-pid', 'switched'):
            with self.subTest(mode=mode):
                self.mode, self.pid, self.clock = mode, 101, 0
                with self.assertRaises(RuntimeError):
                    gateway.activate()
                self.assertFalse(self.actions)
                self.assertFalse(self.marker.exists())

    def test_existing_or_replaced_drain_is_never_removed(self):
        self.marker.write_text('{"principal":"another-operator"}')
        with self.assertRaises(RuntimeError):
            gateway.activate()
        self.assertEqual(json.loads(self.marker.read_text())['principal'], 'another-operator')
        self.marker.unlink()
        self.mode = 'replaced-marker'
        with self.assertRaises(RuntimeError):
            gateway.activate()
        self.assertFalse(self.actions)
        self.assertEqual(json.loads(self.marker.read_text())['principal'], 'another-operator')

    def test_wrong_generation_fails_without_repeated_restart(self):
        self.mode = 'wrong-generation'
        with self.assertRaisesRegex(RuntimeError, 'unverified'):
            gateway.activate()
        self.assertEqual(self.actions, ['reload'])
        self.assertFalse(self.marker.exists())

    def test_current_healthy_gateway_is_noop_and_changed_launcher_is_refused(self):
        self.write_status(revision=self.revision)
        result = gateway.activate()
        self.assertEqual((result['status'], result['changed']), ('verified', False))
        self.launcher.write_text('unverified replacement')
        with self.assertRaises(ValueError):
            gateway.activate()
        self.assertFalse(self.actions)
        self.assertFalse(self.marker.exists())
