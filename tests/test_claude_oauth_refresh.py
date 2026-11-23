import errno
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "hosts/proximal/config/claude-oauth-refresh/claude-oauth-refresh.py"


class RetiredLocalMirrorTests(unittest.TestCase):
    def test_scheduled_run_reaches_remotes_without_retired_local_writes(self):
        spec = importlib.util.spec_from_file_location("claude_refresh_retirement_test", SCRIPT)
        refresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(refresh)
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"HOME": home}):
            for name, consumer in ((".claude", "claude-code"), (".claude-harm", "claude-harm")):
                source = Path(home) / name
                source.mkdir()
                (source / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {
                    "accessToken": "test-access-only", "expiresAt": int(time.time() * 1000) + 3600000,
                }}))
                (Path(home) / ".local/share/striatum/harness-config" / consumer).mkdir(parents=True)
            with mock.patch.object(refresh, "refresh_profile", return_value=True) as renew, \
                    mock.patch.object(refresh, "write_mirror", side_effect=OSError(errno.EROFS, "retired local runtime is fenced")) as local_write, \
                    mock.patch.object(refresh, "mirror_remotes", return_value=True) as remotes, \
                    mock.patch("sys.argv", [str(SCRIPT)]):
                self.assertEqual(refresh.main(), 0)
            self.assertEqual([str(call.args[0]) for call in renew.call_args_list], [str(Path(home) / ".claude"), str(Path(home) / ".claude-harm")])
            local_write.assert_not_called()
            remotes.assert_called_once()
            self.assertEqual([source.key for source in remotes.call_args.args[0]], ["~/.claude", "~/.claude-harm"])
            self.assertEqual(remotes.call_args.args[2], ("talos", "archon", "peecee-wsl", "agent-ee-gate-c4"))
            self.assertFalse(remotes.call_args.args[3])

    def test_failed_talos_link_check_fails_delivery_and_archon_still_runs(self):
        spec = importlib.util.spec_from_file_location("claude_link_test", SCRIPT)
        refresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(refresh)
        talos = subprocess.CompletedProcess([], 1, "")
        archon = subprocess.CompletedProcess([], 0, "")
        with mock.patch.object(refresh, "remote_job", return_value={"profile": "fixture"}), \
                mock.patch.object(refresh.subprocess, "run", side_effect=[talos, archon]) as ssh:
            self.assertFalse(refresh.mirror_remotes([refresh.Source("~/.claude")], 0, ["talos", "archon"], False))
        talos_command, archon_command = [call.args[0][-1] for call in ssh.call_args_list]
        self.assertIn("&& python3 -I ~/git/infra/hosts/talos/config/striatum/install-profile-links.py", talos_command)
        self.assertNotIn("install-profile-links.py", archon_command)
