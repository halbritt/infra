"""Unit tests for hosts/proximal/config/agent-output-bounds (sync_bounds.py and bounded-exec)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SUBSYSTEM_DIR = REPO_ROOT / "hosts" / "proximal" / "config" / "agent-output-bounds"
SYNC_SCRIPT = SUBSYSTEM_DIR / "sync_bounds.py"
BOUNDED_EXEC = SUBSYSTEM_DIR / "bounded-exec"
POLICY_PATH = SUBSYSTEM_DIR / "policy.json"


class AgentOutputBoundsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="infra-bounds-test-")
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)

    def _seed_profiles(self) -> None:
        # Codex profiles with comments, top-level keys, and [sections].
        codex_toml = (
            '# Top comment\n'
            'model = "gpt-5"\n'
            'approvals_reviewer = "user"\n\n'
            '[projects."/home/halbritt"]\n'
            'trust_level = "trusted"\n\n'
            '[features]\n'
            'code_mode = true\n'
        )
        for rel in (".codex/config.toml", ".codex-harm/config.toml", ".codex-3/config.toml"):
            p = self.home / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(codex_toml, encoding="utf-8")
            p.chmod(0o600)

        # Claude profiles preserving unrelated keys and env vars.
        claude_main = {
            "env": {"CLAUDE_CODE_DISABLE_MOUSE": "1"},
            "enabledPlugins": {"foo": True},
            "hooks": {"PreToolUse": [{"matcher": "Bash"}]},
        }
        claude_harm = {"hooks": {"Stop": []}}
        for rel, data in ((".claude/settings.json", claude_main), (".claude-harm/settings.json", claude_harm)):
            p = self.home / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            p.chmod(0o600)

        # OpenCode config preserving provider/mcp/permission.
        oc = self.home / ".config" / "opencode" / "opencode.json"
        oc.parent.mkdir(parents=True, exist_ok=True)
        oc.write_text(json.dumps({"model": "fixture/probe", "permission": {"*": "allow"}}, indent=2) + "\n", encoding="utf-8")
        oc.chmod(0o600)

    def test_sync_bounds_check_apply_idempotent_and_revert(self) -> None:
        self._seed_profiles()

        # Before apply: --check detects drift and exits 1.
        pre = subprocess.run(
            [sys.executable, str(SYNC_SCRIPT), "--check", "--home", str(self.home), "--policy", str(POLICY_PATH)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(pre.returncode, 1)
        self.assertIn("DRIFT:", pre.stderr)

        # Apply succeeds, writes 0600 files + backups, preserves existing keys/sections.
        apply1 = subprocess.run(
            [sys.executable, str(SYNC_SCRIPT), "--apply", "--home", str(self.home), "--policy", str(POLICY_PATH)],
            capture_output=True, text=True, check=True,
        )
        self.assertIn("6 file(s) updated", apply1.stdout)

        # Second check passes with exit 0.
        post = subprocess.run(
            [sys.executable, str(SYNC_SCRIPT), "--check", "--home", str(self.home), "--policy", str(POLICY_PATH)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(post.returncode, 0, post.stderr)

        # Re-running --apply is idempotent (0 file(s) updated).
        apply2 = subprocess.run(
            [sys.executable, str(SYNC_SCRIPT), "--apply", "--home", str(self.home), "--policy", str(POLICY_PATH)],
            capture_output=True, text=True, check=True,
        )
        self.assertIn("0 file(s) updated", apply2.stdout)

        # Verify Codex TOML parses cleanly and keeps top-level key before [projects.*].
        for rel in (".codex/config.toml", ".codex-harm/config.toml", ".codex-3/config.toml"):
            p = self.home / rel
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
            raw = p.read_text(encoding="utf-8")
            self.assertLess(raw.index("tool_output_token_limit = 6000"), raw.index("[projects."))
            parsed = tomllib.loads(raw)
            self.assertEqual(parsed["tool_output_token_limit"], 6000)
            self.assertEqual(parsed["projects"]["/home/halbritt"]["trust_level"], "trusted")
            self.assertTrue(parsed["features"]["code_mode"])

        # Verify Claude JSON preserves existing env and hooks.
        c_main = json.loads((self.home / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(c_main["bashOutputMaxChars"], 12000)
        self.assertEqual(c_main["env"]["CLAUDE_CODE_DISABLE_MOUSE"], "1")
        self.assertEqual(c_main["env"]["BASH_MAX_OUTPUT_LENGTH"], "12000")
        self.assertEqual(c_main["env"]["MAX_MCP_OUTPUT_TOKENS"], "8000")
        self.assertEqual(c_main["env"]["CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS"], "12000")
        self.assertEqual(c_main["enabledPlugins"], {"foo": True})

        # Verify OpenCode JSON preserves model/permission.
        oc = json.loads((self.home / ".config/opencode/opencode.json").read_text(encoding="utf-8"))
        self.assertEqual(oc["tool_output"], {"max_lines": 500, "max_bytes": 16384})
        self.assertEqual(oc["model"], "fixture/probe")

        # Verify backups exist under ~/.local/state/agent-output-bounds/.
        state_dir = self.home / ".local" / "state" / "agent-output-bounds"
        self.assertGreaterEqual(len(list(state_dir.glob("*.bak"))), 6)

        # Revert removes only managed keys and preserves original keys; --check returns 1 again.
        subprocess.run(
            [sys.executable, str(SYNC_SCRIPT), "--revert", "--home", str(self.home), "--policy", str(POLICY_PATH)],
            capture_output=True, text=True, check=True,
        )
        reverted_codex = tomllib.loads((self.home / ".codex/config.toml").read_text(encoding="utf-8"))
        self.assertNotIn("tool_output_token_limit", reverted_codex)
        self.assertEqual(reverted_codex["projects"]["/home/halbritt"]["trust_level"], "trusted")

        reverted_claude = json.loads((self.home / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertNotIn("bashOutputMaxChars", reverted_claude)
        self.assertEqual(reverted_claude["env"], {"CLAUDE_CODE_DISABLE_MOUSE": "1"})

        reverted_harm = json.loads((self.home / ".claude-harm/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(reverted_harm, {"hooks": {"Stop": []}})

        reverted_oc = json.loads((self.home / ".config/opencode/opencode.json").read_text(encoding="utf-8"))
        self.assertNotIn("tool_output", reverted_oc)

    def test_bounded_exec_passthrough_truncation_diagnostics_and_opt_out(self) -> None:
        spool_dir = self.home / "cache" / "bounded-output"
        env = dict(os.environ, HOME=str(self.home), BOUNDED_EXEC_OUTPUT_DIR=str(spool_dir))

        # 1. Small pass-through keeps stdout/stderr separated and exit code 0.
        small = subprocess.run(
            [sys.executable, str(BOUNDED_EXEC), "--", "/bin/sh", "-c", "printf 'out\\n'; printf 'err\\n' >&2"],
            env=env, capture_output=True, text=True, check=False,
        )
        self.assertEqual(small.returncode, 0)
        self.assertEqual(small.stdout, "out\n")
        self.assertEqual(small.stderr, "err\n")
        self.assertFalse(spool_dir.exists())

        # 2. >16 KB failing command preserves exit code, head, middle error diagnostic, tail, and 0600 log path.
        script = (
            "printf 'HEAD_MARKER\\n'; i=0; while [ $i -lt 420 ]; do "
            "printf 'noise line %03d padding to exceed sixteen kilobytes\\n' \"$i\"; "
            "if [ \"$i\" -eq 200 ]; then printf 'ERROR: fatal assertion failed at main.rs:77\\n' >&2; fi; "
            "i=$((i+1)); done; printf 'TAIL_MARKER\\n'; exit 3"
        )
        bounded = subprocess.run(
            [sys.executable, str(BOUNDED_EXEC), "--", "/bin/sh", "-c", script],
            env=env, capture_output=True, text=True, check=False,
        )
        self.assertEqual(bounded.returncode, 3)
        self.assertLessEqual(len(bounded.stdout.encode("utf-8")), 16384)
        for want in ("exit_code=3", "HEAD_MARKER", "ERROR: fatal assertion failed at main.rs:77", "TAIL_MARKER", str(spool_dir)):
            self.assertIn(want, bounded.stdout)
        logs = list(spool_dir.glob("*.log"))
        self.assertEqual(len(logs), 1)
        self.assertEqual(stat.S_IMODE(logs[0].stat().st_mode), 0o600)
        full_text = logs[0].read_text(encoding="utf-8")
        self.assertGreater(len(full_text), 16384)
        self.assertIn("noise line 200", full_text)

        # 3. BOUNDED_EXEC_RAW=1 opt-out passes complete output through.
        raw_env = dict(env, BOUNDED_EXEC_RAW="1")
        raw = subprocess.run(
            [sys.executable, str(BOUNDED_EXEC), "--", "/bin/sh", "-c", script],
            env=raw_env, capture_output=True, text=True, check=False,
        )
        self.assertEqual(raw.returncode, 3)
        self.assertEqual(len(raw.stdout) + len(raw.stderr), len(full_text))

    def test_bounded_exec_line_cap_on_short_lines_max_bytes_zero_and_missing_cmd(self) -> None:
        spool_dir = self.home / "cache" / "bounded-output-lines"
        env = dict(os.environ, HOME=str(self.home), BOUNDED_EXEC_OUTPUT_DIR=str(spool_dir))
        short_350_cmd = (
            "python3 -c \"for i in range(350): "
            "print('ERROR: mid failure' if i == 175 else f'line {i:03d}')\""
        )

        # 1. 350 short lines (< 16 KB) genuinely caps lines <= 300 (strictly < 350),
        #    preserves head, middle diagnostic, tail, full 350-line spool log, and accurate omitted counts.
        bounded_lines = subprocess.run(
            [sys.executable, str(BOUNDED_EXEC), "--", "/bin/sh", "-c", short_350_cmd],
            env=env, capture_output=True, text=True, check=False,
        )
        self.assertEqual(bounded_lines.returncode, 0)
        out_lines = bounded_lines.stdout.splitlines()
        self.assertLess(len(out_lines), 350)
        self.assertLessEqual(len(out_lines), 301)
        self.assertIn("line 000", bounded_lines.stdout)
        self.assertIn("ERROR: mid failure", bounded_lines.stdout)
        self.assertIn("line 349", bounded_lines.stdout)
        self.assertNotIn("omitted 1 of", bounded_lines.stdout)
        self.assertIn("bytes (", bounded_lines.stdout)
        self.assertIn("of 350 lines)", bounded_lines.stdout)
        logs = list(spool_dir.glob("*.log"))
        self.assertEqual(len(logs), 1)
        self.assertEqual(stat.S_IMODE(logs[0].stat().st_mode), 0o600)
        self.assertEqual(len(logs[0].read_text(encoding="utf-8").splitlines()), 350)

        # 2. BOUNDED_EXEC_MAX_BYTES=0 on 350 lines passes all 350 lines unclipped without creating a spool log.
        spool_zero = self.home / "cache" / "bounded-output-zero"
        zero_env = dict(
            os.environ,
            HOME=str(self.home),
            BOUNDED_EXEC_OUTPUT_DIR=str(spool_zero),
            BOUNDED_EXEC_MAX_BYTES="0",
        )
        zero_env.pop("BOUNDED_EXEC_MAX_LINES", None)
        unbounded = subprocess.run(
            [sys.executable, str(BOUNDED_EXEC), "--", "/bin/sh", "-c", short_350_cmd],
            env=zero_env, capture_output=True, text=True, check=False,
        )
        self.assertEqual(unbounded.returncode, 0)
        self.assertEqual(len(unbounded.stdout.splitlines()), 350)
        self.assertNotIn("full output:", unbounded.stdout)
        self.assertFalse(spool_zero.exists())

        # 3. Nonexistent command exits 127 cleanly without Python traceback; non-executable exits 126.
        missing = subprocess.run(
            [sys.executable, str(BOUNDED_EXEC), "--", "/nonexistent/bounded_exec_missing_cmd"],
            env=env, capture_output=True, text=True, check=False,
        )
        self.assertEqual(missing.returncode, 127)
        self.assertIn("not found", missing.stderr)
        self.assertNotIn("Traceback", missing.stderr)

        nonexec = self.home / "not_executable.sh"
        nonexec.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
        nonexec.chmod(0o600)
        perm = subprocess.run(
            [sys.executable, str(BOUNDED_EXEC), "--", str(nonexec)],
            env=env, capture_output=True, text=True, check=False,
        )
        self.assertEqual(perm.returncode, 126)
        self.assertIn("permission denied", perm.stderr)
        self.assertNotIn("Traceback", perm.stderr)

    def test_sync_bounds_handles_multiline_nested_toml_arrays_and_strings(self) -> None:
        self._seed_profiles()
        nested_toml = (
            'model = "gpt-5"\n'
            'notify = [\n'
            '  ["echo", "hi"]\n'
            ']\n'
            'note = """\n'
            '[not_a_section]\n'
            'tool_output_token_limit = 999\n'
            '"""\n'
            '[features]\n'
            'code_mode = true\n'
        )
        codex_cfg = self.home / ".codex" / "config.toml"
        codex_cfg.write_text(nested_toml, encoding="utf-8")

        subprocess.run(
            [sys.executable, str(SYNC_SCRIPT), "--apply", "--home", str(self.home), "--policy", str(POLICY_PATH)],
            capture_output=True, text=True, check=True,
        )
        applied_raw = codex_cfg.read_text(encoding="utf-8")
        self.assertLess(applied_raw.index("tool_output_token_limit = 6000"), applied_raw.index("[features]"))
        self.assertGreater(applied_raw.index("tool_output_token_limit = 6000"), applied_raw.index('  ["echo", "hi"]\n]'))
        parsed = tomllib.loads(applied_raw)
        self.assertEqual(parsed["tool_output_token_limit"], 6000)
        self.assertEqual(parsed["notify"], [["echo", "hi"]])
        self.assertTrue(parsed["features"]["code_mode"])

        chk = subprocess.run(
            [sys.executable, str(SYNC_SCRIPT), "--check", "--home", str(self.home), "--policy", str(POLICY_PATH)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(chk.returncode, 0, chk.stderr)

        subprocess.run(
            [sys.executable, str(SYNC_SCRIPT), "--revert", "--home", str(self.home), "--policy", str(POLICY_PATH)],
            capture_output=True, text=True, check=True,
        )
        reverted = tomllib.loads(codex_cfg.read_text(encoding="utf-8"))
        self.assertNotIn("tool_output_token_limit", reverted)
        self.assertEqual(reverted["notify"], [["echo", "hi"]])
        self.assertTrue(reverted["features"]["code_mode"])

    def test_bounded_exec_tiny_max_lines_and_tiny_max_bytes(self) -> None:
        plain_50 = "python3 -c \"[print(f'plain {i:02d}') for i in range(50)]\""
        diag_fail_50 = (
            "python3 -c \"import sys; "
            "[print('ERROR: mid failure' if i == 25 else f'line {i:02d}') for i in range(50)]; "
            "sys.exit(7)\""
        )

        # 1. BOUNDED_EXEC_MAX_BYTES=0 with BOUNDED_EXEC_MAX_LINES in {1..5}:
        #    total emitted lines (including framing lines) must never exceed max_lines,
        #    and spool file must retain all 50 original lines.
        for label, cmd, expected_rc in (
            ("plain_rc0", plain_50, 0),
            ("diag_rc7", diag_fail_50, 7),
        ):
            for max_lines in (1, 2, 3, 4, 5):
                spool_dir = self.home / "cache" / f"tiny-lines-{label}-{max_lines}"
                env = dict(
                    os.environ,
                    HOME=str(self.home),
                    BOUNDED_EXEC_OUTPUT_DIR=str(spool_dir),
                    BOUNDED_EXEC_MAX_BYTES="0",
                    BOUNDED_EXEC_MAX_LINES=str(max_lines),
                )
                proc = subprocess.run(
                    [sys.executable, str(BOUNDED_EXEC), "--", "/bin/sh", "-c", cmd],
                    env=env, capture_output=True, text=True, check=False,
                )
                self.assertEqual(proc.returncode, expected_rc, (label, max_lines))
                out_lines = proc.stdout.splitlines()
                self.assertLessEqual(
                    len(out_lines),
                    max_lines,
                    f"{label} max_lines={max_lines} emitted {len(out_lines)} lines: {proc.stdout!r}",
                )
                self.assertGreaterEqual(len(out_lines), 1)
                if expected_rc != 0:
                    self.assertIn("exit_code=7", proc.stdout)
                if expected_rc != 0 and max_lines == 5:
                    self.assertIn("ERROR: mid failure", proc.stdout)
                logs = list(spool_dir.glob("*.log"))
                self.assertEqual(len(logs), 1)
                self.assertEqual(stat.S_IMODE(logs[0].stat().st_mode), 0o600)
                self.assertEqual(len(logs[0].read_text(encoding="utf-8").splitlines()), 50)

        # 2. Tiny BOUNDED_EXEC_MAX_BYTES in {1, 20, 80} (<= reserve + 32):
        #    output UTF-8 byte length must never exceed max_bytes, remain valid UTF-8,
        #    preserve trailing newline, and retain full output in spool log.
        utf8_100 = "python3 -c \"[print(f'€🚀 line {i:03d}') for i in range(100)]\""
        utf8_fail_100 = (
            "python3 -c \"import sys; "
            "[print(f'€🚀 line {i:03d}') for i in range(100)]; sys.exit(5)\""
        )
        for label, cmd, expected_rc in (
            ("utf8_rc0", utf8_100, 0),
            ("utf8_rc5", utf8_fail_100, 5),
        ):
            for max_bytes in (1, 20, 80):
                spool_dir = self.home / "cache" / f"tiny-bytes-{label}-{max_bytes}"
                env = dict(
                    os.environ,
                    HOME=str(self.home),
                    BOUNDED_EXEC_OUTPUT_DIR=str(spool_dir),
                    BOUNDED_EXEC_MAX_BYTES=str(max_bytes),
                )
                env.pop("BOUNDED_EXEC_MAX_LINES", None)
                proc = subprocess.run(
                    [sys.executable, str(BOUNDED_EXEC), "--", "/bin/sh", "-c", cmd],
                    env=env, capture_output=True, check=False,
                )
                self.assertEqual(proc.returncode, expected_rc)
                self.assertLessEqual(
                    len(proc.stdout),
                    max_bytes,
                    f"{label} max_bytes={max_bytes} emitted {len(proc.stdout)} bytes: {proc.stdout!r}",
                )
                decoded = proc.stdout.decode("utf-8")
                self.assertNotIn("\ufffd", decoded)
                self.assertTrue(decoded.endswith("\n"))
                logs = list(spool_dir.glob("*.log"))
                self.assertEqual(len(logs), 1)
                self.assertEqual(len(logs[0].read_text(encoding="utf-8").splitlines()), 100)

        # 3. Combined tiny caps: max_lines=1 + max_bytes=80 + non-zero exit code.
        combo_spool = self.home / "cache" / "tiny-combo"
        combo_env = dict(
            os.environ,
            HOME=str(self.home),
            BOUNDED_EXEC_OUTPUT_DIR=str(combo_spool),
            BOUNDED_EXEC_MAX_BYTES="80",
            BOUNDED_EXEC_MAX_LINES="1",
        )
        combo = subprocess.run(
            [sys.executable, str(BOUNDED_EXEC), "--", "/bin/sh", "-c", diag_fail_50],
            env=combo_env, capture_output=True, check=False,
        )
        self.assertEqual(combo.returncode, 7)
        self.assertLessEqual(len(combo.stdout), 80)
        combo_text = combo.stdout.decode("utf-8")
        self.assertLessEqual(len(combo_text.splitlines()), 1)
        self.assertTrue(combo_text.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
