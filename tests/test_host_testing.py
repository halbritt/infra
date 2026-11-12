"""Contract checks for the shared host task, including opt-in real user scopes.

mise run test:host
Real checks create only their own processes, temporary files and loopback socket.
"""
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "shared/testing/tasks/host/exec"
spec = importlib.util.spec_from_file_location("host_testing_install", ROOT / "shared/testing/install.py")
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)


class InstructionInstallTests(unittest.TestCase):
    def test_reinstall_preserves_other_instructions(self):
        original = "# Existing model routing\nKeep subscription settings.\n"
        first = install.managed_instructions(original, "first workflow")
        second = install.managed_instructions(first, "updated workflow")
        self.assertTrue(second.startswith(original))
        self.assertNotIn("first workflow", second)
        self.assertEqual(second.count(install.BEGIN), 1)
        self.assertEqual(install.managed_instructions(second, "updated workflow"), second)

    def test_incomplete_managed_block_refuses_to_rewrite(self):
        with self.assertRaises(ValueError):
            install.managed_instructions("keep this\n" + install.BEGIN, "replacement")


class HostArgumentsTests(unittest.TestCase):
    def test_refuses_missing_command_without_starting_a_scope(self):
        result = subprocess.run([sys.executable, str(RUNNER)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("supply -- COMMAND", result.stderr)

    def test_refuses_unbounded_or_invalid_deadlines(self):
        for value in ("0", "0s", "infinity", "oops", "-5s"):
            with self.subTest(value=value):
                result = subprocess.run([sys.executable, str(RUNNER), "--timeout=" + value,
                                         "--", "true"], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn("positive duration", result.stderr)


@unittest.skipUnless(os.environ.get("HOST_TEST_INTEGRATION") == "1",
                     "real systemd checks: set HOST_TEST_INTEGRATION=1")
class HostExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="host-testing-")
        self.addCleanup(self.temp.cleanup)
        self.cwd = Path(self.temp.name)

    def run_host(self, code, *args, limit="10s"):
        return subprocess.run([sys.executable, str(RUNNER), "--timeout", limit, "--",
                               sys.executable, "-c", code, *args], cwd=self.cwd,
                              capture_output=True, text=True, timeout=20, close_fds=False)

    def test_environment_argv_working_directory_and_admission(self):
        expected_args = ["two words", "$(touch should-not-exist)", "semi;colon", "--flag"]
        code = """import os,json,sys,subprocess
print(json.dumps({'home':os.environ['HOME'], 'cwd':os.getcwd(), 'args':sys.argv[1:],
                 'path':os.environ['PATH'], 'lease':subprocess.run(['native-admit','verify'],capture_output=True,close_fds=False).returncode}))
"""
        result = self.run_host(code, *expected_args)
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = json.loads(result.stdout)
        self.assertEqual(observed["home"], os.environ["HOME"])
        self.assertEqual(observed["path"], os.environ["PATH"])
        self.assertEqual(observed["cwd"], str(self.cwd))
        self.assertEqual(observed["args"], expected_args)
        self.assertEqual(observed["lease"], 0)
        self.assertFalse((self.cwd / "should-not-exist").exists())

    def test_failure_status_preserved(self):
        result = self.run_host("import sys; sys.exit(37)")
        self.assertEqual(result.returncode, 37, result.stderr)

    def test_command_returning_timeout_status_is_not_reported_as_expired(self):
        result = self.run_host("import sys; sys.exit(124)")
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertNotIn("deadline exceeded", result.stderr)
        self.assertNotIn("sending signal", result.stderr)

    def test_deadline_escalates_when_command_ignores_term(self):
        result = self.run_host("import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)", limit="1s")
        self.assertEqual(result.returncode, 137, result.stderr)
        self.assertIn("KILL", result.stderr)

    def test_localhost_and_unix_socket_access(self):
        with socket.socket() as tcp, socket.socket(socket.AF_UNIX) as unix:
            tcp.bind(("127.0.0.1", 0))
            tcp.listen()
            endpoint = str(self.cwd / "test.sock")
            unix.bind(endpoint)
            unix.listen()
            code = """import socket,sys
with socket.create_connection(('127.0.0.1',int(sys.argv[1])),timeout=2) as s: s.sendall(b'ok')
with socket.socket(socket.AF_UNIX) as s: s.connect(sys.argv[2]); s.sendall(b'ok')
"""
            result = self.run_host(code, str(tcp.getsockname()[1]), endpoint)
            self.assertEqual(result.returncode, 0, result.stderr)
            for listener in (tcp, unix):
                listener.settimeout(2)
                conn, _ = listener.accept()
                with conn:
                    self.assertEqual(conn.recv(2), b"ok")

    def spawn_code(self, ready):
        return f"""import subprocess,sys,time,pathlib
p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True)
pathlib.Path({str(ready)!r}).write_text(str(p.pid))
time.sleep(60)
"""

    def assert_not_running(self, pid):
        # Inspect a child PID reported by our own test. Never signal it.
        # Pipe EOF can precede the kernel's final process teardown briefly.
        stat = Path(f"/proc/{pid}/stat")
        deadline = time.monotonic() + 1
        while True:
            try:
                state = stat.read_text().split(")", 1)[1].split()[0]
            except (FileNotFoundError, ProcessLookupError):
                return
            if state == "Z":
                return
            if time.monotonic() >= deadline:
                self.fail(f"test child {pid} survived scope cleanup (state {state})")
            time.sleep(0.02)

    def test_deadline_reaps_detached_child_holding_output_pipe(self):
        ready = self.cwd / "child.pid"
        started = time.monotonic()
        result = self.run_host(self.spawn_code(ready), limit="1s")
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertIn("TERM", result.stderr)
        self.assertLess(time.monotonic() - started, 7)
        self.assertTrue(ready.exists(), result.stderr)
        self.assert_not_running(int(ready.read_text()))

    def test_normal_exit_reaps_background_child(self):
        ready = self.cwd / "child.pid"
        result = self.run_host(self.spawn_code(ready).replace("time.sleep(60)\n", ""))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_not_running(int(ready.read_text()))

    def test_killed_client_leaves_deadline_in_force(self):
        ready = self.cwd / "child.pid"
        child = subprocess.Popen([sys.executable, str(RUNNER), "--timeout", "2s", "--",
                                  sys.executable, "-c", self.spawn_code(ready)],
                                 cwd=self.cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, close_fds=False)
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(ready.exists(), "owned test command did not start")
            self.assertGreater(child.pid, 1)
            child.kill()
            child.communicate(timeout=12)
            self.assertEqual(child.returncode, -signal.SIGKILL)
            self.assert_not_running(int(ready.read_text()))
        finally:
            if child.poll() is None:
                child.terminate()
                child.communicate(timeout=10)

    def test_cancellation_reaps_only_owned_scope(self):
        ready = self.cwd / "child.pid"
        with subprocess.Popen([sys.executable, "-c", "import time;time.sleep(20)"],
                              start_new_session=True) as canary:
            try:
                child = subprocess.Popen([sys.executable, str(RUNNER), "--timeout", "10s", "--",
                                          sys.executable, "-c", self.spawn_code(ready)],
                                         cwd=self.cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, close_fds=False)
                try:
                    deadline = time.monotonic() + 8
                    while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertTrue(ready.exists(), "owned test command did not start")
                    self.assertGreater(child.pid, 1)
                    child.send_signal(signal.SIGTERM)
                    _, stderr = child.communicate(timeout=7)
                    self.assertEqual(child.returncode, 143, stderr)
                    self.assert_not_running(int(ready.read_text()))
                    self.assertIsNone(canary.poll(), "unrelated canary was stopped")
                finally:
                    if child.poll() is None:
                        child.terminate()
                        child.communicate(timeout=15)
            finally:
                canary.terminate()
                canary.wait(timeout=3)

    def test_two_concurrent_runs_preserve_separate_working_directories(self):
        def run(index):
            path = self.cwd / str(index)
            path.mkdir()
            return subprocess.run([sys.executable, str(RUNNER), "--timeout", "10s", "--",
                                   sys.executable, "-c", "import os,time; time.sleep(.2); print(os.getcwd())"],
                                  cwd=path, capture_output=True, text=True, timeout=15, close_fds=False)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, (0, 1)))
        for index, result in enumerate(results):
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(self.cwd / str(index)))


if __name__ == "__main__":
    unittest.main()
