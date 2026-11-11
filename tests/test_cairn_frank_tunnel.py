import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch


SOURCE = Path(__file__).resolve().parents[1] / "hosts/proximal/config/cairn/frank-tunnel.py"
SPEC = importlib.util.spec_from_file_location("frank_tunnel", SOURCE)
tunnel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tunnel)


class FrankTunnelTests(unittest.TestCase):
    def setUp(self):
        self.session = {
            "agent_id": "22318d92-da34-456c-be93-bc74716063cb",
            "execution_id": "8e785813-3fbd-40ce-ab4b-7c4ddf83cc03",
            "display_name": "test-session",
        }
        self.child = Mock(pid=12345)
        self.child.poll.return_value = None
        self.stopping = Mock()
        self.stopping.is_set.return_value = False
        self.stopping.wait.return_value = True
        for name, replacement in (
            ("register", Mock(return_value=self.session)),
            ("save_session", Mock()),
            ("session_call", Mock()),
        ):
            patcher = patch.object(tunnel, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(tunnel.subprocess, "Popen", return_value=self.child)
        self.spawn = patcher.start()
        self.addCleanup(patcher.stop)

    def test_clean_stop_leaves_only_registered_execution(self):
        self.assertEqual(tunnel.supervise(self.stopping), 0)
        self.child.terminate.assert_called_once()
        self.child.wait.assert_called_once_with(timeout=10)
        tunnel.session_call.assert_called_once_with(
            "leave", "--agent-id", self.session["agent_id"],
            "--execution-id", self.session["execution_id"],
        )

    def test_launch_failure_still_leaves(self):
        self.spawn.side_effect = FileNotFoundError("missing tunnel client")
        with self.assertRaises(FileNotFoundError):
            tunnel.supervise(self.stopping)
        self.assertEqual(tunnel.session_call.call_args.args[0], "leave")
        self.child.terminate.assert_not_called()

    def test_heartbeat_failure_stops_tunnel_and_leaves(self):
        self.stopping.wait.return_value = False
        tunnel.session_call.side_effect = [RuntimeError("STALE_SESSION"), {}]
        with patch.object(tunnel.time, "monotonic", side_effect=[0, 26]):
            with self.assertRaisesRegex(RuntimeError, "STALE_SESSION"):
                tunnel.supervise(self.stopping)
        self.assertEqual([c.args[0] for c in tunnel.session_call.call_args_list],
                         ["heartbeat", "leave"])
        self.child.terminate.assert_called_once()

    def test_unexpected_clean_exit_is_a_service_failure(self):
        self.stopping.wait.return_value = False
        self.child.poll.return_value = 0
        with self.assertRaisesRegex(RuntimeError, "exited unexpectedly: 0"):
            tunnel.supervise(self.stopping)
        self.child.terminate.assert_not_called()
        self.assertEqual(tunnel.session_call.call_args.args[0], "leave")

    def test_shutdown_during_registration_does_not_start_tunnel(self):
        self.stopping.is_set.return_value = True
        self.assertEqual(tunnel.supervise(self.stopping), 0)
        self.spawn.assert_not_called()
        self.assertEqual(tunnel.session_call.call_args.args[0], "leave")

    def test_invalid_pid_is_never_signalled(self):
        for pid in (-1, 0, 1):
            child = Mock(pid=pid)
            child.poll.return_value = None
            with self.assertRaisesRegex(RuntimeError, "invalid child PID"):
                tunnel.stop_child(child)
            child.terminate.assert_not_called()
            child.kill.assert_not_called()

    def test_unresponsive_owned_child_is_reaped(self):
        self.child.wait.side_effect = [subprocess.TimeoutExpired("test", 10), -9]
        tunnel.stop_child(self.child)
        self.child.kill.assert_called_once()
        self.assertEqual(self.child.wait.call_count, 2)


class SessionCallTests(unittest.TestCase):
    def test_failed_api_envelope_is_not_success(self):
        with patch.object(tunnel.subprocess, "run", return_value=Mock(
                returncode=0, stdout='{"ok":false,"status":"STALE_SESSION"}')):
            with self.assertRaisesRegex(RuntimeError, "STALE_SESSION"):
                tunnel.session_call("heartbeat")

    def test_registration_failure_cannot_start_a_tunnel(self):
        with patch.object(tunnel, "register", side_effect=RuntimeError("unavailable")), \
                patch.object(tunnel.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                tunnel.supervise(Mock())
            spawn.assert_not_called()

    def test_session_file_is_atomic_and_private(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "session.json"
            with patch.object(tunnel, "SESSION_FILE", target):
                tunnel.save_session({"agent_id": "test"})
            self.assertEqual(json.loads(target.read_text()), {"agent_id": "test"})
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertFalse(target.with_suffix(".pending").exists())
