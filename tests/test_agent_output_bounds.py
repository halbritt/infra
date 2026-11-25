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


if __name__ == "__main__":
    unittest.main()
