import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "hosts/proximal/config/codex-auth-mirror/codex-auth-mirror.py"
spec = importlib.util.spec_from_file_location("codex_mirror", SCRIPT)
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)


class RenewalTests(unittest.TestCase):
    def test_timer_finds_codex_on_path_and_requests_refresh_for_selected_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli = Path(tmp) / "codex"
            cli.write_text(
                "#!/usr/bin/python3\n"
                "import json, os, sys\n"
                "assert os.environ['CODEX_HOME'] == os.path.dirname(sys.argv[0])\n"
                "assert sys.argv[1:] == ['app-server']\n"
                "def read(): return json.loads(sys.stdin.readline())\n"
                "assert read()['method'] == 'initialize'\n"
                "print(json.dumps({'id': 1, 'result': {'ok': True}}), flush=True)\n"
                "assert read()['method'] == 'initialized'\n"
                "assert read()['params']['refreshToken'] is True\n"
                "print(json.dumps({'id': 2, 'result': {'ok': True}}), flush=True)\n"
            )
            cli.chmod(0o700)
            with mock.patch.dict(os.environ, {"PATH": tmp}):
                os.environ.pop("CODEX_BIN", None)
                self.assertTrue(mirror.renew_via_cli(tmp))

    def test_missing_cli_fails_renewal_and_still_delivers_usable_tokens(self):
        profiles = ["profile-a", "profile-b"]
        auth = {"tokens": {"refresh_token": "source-only"}}
        with mock.patch.object(mirror, "load", return_value=auth), \
                mock.patch.object(mirror, "access_expiry", return_value=time.time() + 3600), \
                mock.patch.object(mirror.subprocess, "Popen", side_effect=FileNotFoundError), \
                mock.patch.object(mirror, "check_access"), \
                mock.patch.object(mirror, "mirror_remotes", return_value=True) as deliver, \
                mock.patch("sys.argv", [str(SCRIPT), *profiles]):
            self.assertEqual(mirror.main(), 1)
        self.assertEqual([job["profile"] for job in deliver.call_args.args[0]], profiles)

    def test_rejected_future_dated_profile_fails_run_but_healthy_profile_is_delivered(self):
        with tempfile.TemporaryDirectory() as tmp:
            profiles = []
            claims = base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + 864000}).encode()).decode()
            for name in ("revoked", "healthy"):
                profile = Path(tmp) / name
                profile.mkdir()
                (profile / "auth.json").write_text(json.dumps({"tokens": {
                    "access_token": f"test.{claims}.fixture", "refresh_token": "source-only", "account_id": name,
                }}))
                profiles.append(str(profile))
            rejected, accepted = mock.Mock(), mock.Mock()
            rejected.getresponse.return_value.status = 401
            accepted.getresponse.return_value.status = 200
            with mock.patch.object(mirror.http.client, "HTTPSConnection", side_effect=[rejected, accepted]), \
                    mock.patch.object(mirror.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "")) as ssh, \
                    mock.patch("sys.argv", [str(SCRIPT), *profiles]):
                self.assertEqual(mirror.main(), 1)
            self.assertEqual([call.args[0][-2] for call in ssh.call_args_list], list(mirror.REMOTE_HOSTS))
            for call in ssh.call_args_list:
                jobs = json.loads(call.kwargs["input"])
                self.assertEqual([job["profile"] for job in jobs], profiles[1:])
                self.assertEqual(jobs[0]["auth"]["tokens"]["refresh_token"], "")

    def test_host_outage_is_reported_after_later_hosts_are_attempted(self):
        job = {"profile": "fixture"}
        for failed_host, expected_ok in (("archon", False), ("talos", False), ("peecee-wsl", True)):
            def deliver(command, **kwargs):
                return subprocess.CompletedProcess(command, int(command[-2] == failed_host), "")

            with self.subTest(host=failed_host), mock.patch.object(mirror.subprocess, "run", side_effect=deliver) as ssh:
                self.assertEqual(mirror.mirror_remotes([job], mirror.REMOTE_HOSTS, False), expected_ok)
                self.assertEqual(ssh.call_count, len(mirror.REMOTE_HOSTS))
