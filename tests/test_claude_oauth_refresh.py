import errno
import importlib.util
import json
import os
from pathlib import Path
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
                    mock.patch.object(refresh, "mirror_remotes") as remotes, \
                    mock.patch("sys.argv", [str(SCRIPT)]):
                self.assertEqual(refresh.main(), 0)
            self.assertEqual([str(call.args[0]) for call in renew.call_args_list], [str(Path(home) / ".claude"), str(Path(home) / ".claude-harm")])
            local_write.assert_not_called()
            remotes.assert_called_once()
            self.assertEqual([source.key for source in remotes.call_args.args[0]], ["~/.claude", "~/.claude-harm"])
            self.assertEqual(remotes.call_args.args[2], ("peecee-wsl", "archon", "agent-ee-gate-c4", "talos"))
            self.assertFalse(remotes.call_args.args[3])
