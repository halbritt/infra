#!/usr/bin/env python3
"""Idempotent surgical sync/check/revert for proximal agent output-bound configs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import tomllib


DEFAULT_POLICY = Path(__file__).resolve().with_name("policy.json")
SECTION_RE = re.compile(r"^\s*\[")


def atomic_write_0600(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".sync-bounds-", dir=str(target.parent))
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp_path, target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def backup_file(target: Path, state_dir: Path, home: Path) -> None:
    if not target.exists():
        return
    state_dir.mkdir(parents=True, exist_ok=True)
    try:
        rel = target.relative_to(home)
        safe_name = str(rel).replace("/", "__")
    except ValueError:
        safe_name = target.name
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = state_dir / f"{stamp}-{safe_name}.bak"
    atomic_write_0600(bak, target.read_text(encoding="utf-8"))


def update_toml_top_level(text: str, key: str, value: int, remove: bool = False) -> str:
    lines = text.splitlines(keepends=True)
    first_section = next((i for i, line in enumerate(lines) if SECTION_RE.match(line)), len(lines))
    key_re = re.compile(rf"^\s*{re.escape(key)}\s*=")

    top_lines = lines[:first_section]
    rest_lines = lines[first_section:]

    found_indices = [i for i, line in enumerate(top_lines) if key_re.match(line)]
    if remove:
        if not found_indices:
            return text
        new_top = [line for i, line in enumerate(top_lines) if i not in found_indices]
        result = "".join(new_top + rest_lines)
        tomllib.loads(result)
        return result

    assignment = f"{key} = {value}\n"
    if found_indices:
        new_top = []
        replaced = False
        for i, line in enumerate(top_lines):
            if i in found_indices:
                if not replaced:
                    new_top.append(assignment)
                    replaced = True
            else:
                new_top.append(line)
    else:
        new_top = list(top_lines)
        insert_at = len(new_top)
        while insert_at > 0 and new_top[insert_at - 1].strip() == "":
            insert_at -= 1
        if insert_at > 0 and not new_top[insert_at - 1].endswith("\n"):
            new_top[insert_at - 1] += "\n"
        new_top.insert(insert_at, assignment)
        if insert_at + 1 == len(new_top) and rest_lines:
            new_top.append("\n")

    result = "".join(new_top + rest_lines)
    parsed = tomllib.loads(result)
    if parsed.get(key) != value:
        raise ValueError(f"TOML verification failed for {key}={value}")
    return result


def check_toml_top_level(target: Path, key: str, value: int) -> str | None:
    if not target.exists():
        return f"missing {target}"
    parsed = tomllib.loads(target.read_text(encoding="utf-8"))
    if parsed.get(key) != value:
        return f"{target}: {key}={parsed.get(key)!r}, want {value!r}"
    return None


def update_claude_json(text: str, policy_claude: dict, remove: bool = False) -> str:
    data = json.loads(text) if text.strip() else {}
    if not isinstance(data, dict):
        raise ValueError("Claude settings JSON root must be an object")
    if remove:
        for k in policy_claude.get("settings", {}):
            data.pop(k, None)
        env = data.get("env")
        if isinstance(env, dict):
            for k in policy_claude.get("env", {}):
                env.pop(k, None)
            if not env:
                data.pop("env", None)
    else:
        for k, v in policy_claude.get("settings", {}).items():
            data[k] = v
        env = data.get("env")
        if env is None:
            env = {}
        elif not isinstance(env, dict):
            raise ValueError("Claude settings env must be an object")
        for k, v in policy_claude.get("env", {}).items():
            env[k] = v
        data["env"] = env
    return json.dumps(data, indent=2) + "\n"


def check_claude_json(target: Path, policy_claude: dict) -> list[str]:
    if not target.exists():
        return [f"missing {target}"]
    data = json.loads(target.read_text(encoding="utf-8"))
    errs: list[str] = []
    for k, want in policy_claude.get("settings", {}).items():
        if data.get(k) != want:
            errs.append(f"{target}: {k}={data.get(k)!r}, want {want!r}")
    env = data.get("env") or {}
    for k, want in policy_claude.get("env", {}).items():
        if env.get(k) != want:
            errs.append(f"{target}: env.{k}={env.get(k)!r}, want {want!r}")
    return errs


def update_opencode_json(text: str, policy_oc: dict, remove: bool = False) -> str:
    data = json.loads(text) if text.strip() else {}
    if not isinstance(data, dict):
        raise ValueError("OpenCode JSON root must be an object")
    if remove:
        for k in policy_oc.get("settings", {}):
            data.pop(k, None)
    else:
        for k, v in policy_oc.get("settings", {}).items():
            data[k] = v
    return json.dumps(data, indent=2) + "\n"


def check_opencode_json(target: Path, policy_oc: dict) -> list[str]:
    if not target.exists():
        return [f"missing {target}"]
    data = json.loads(target.read_text(encoding="utf-8"))
    errs: list[str] = []
    for k, want in policy_oc.get("settings", {}).items():
        if data.get(k) != want:
            errs.append(f"{target}: {k}={data.get(k)!r}, want {want!r}")
    return errs


def run(mode: str, home: Path, policy_path: Path) -> int:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    state_dir = home / ".local" / "state" / "agent-output-bounds"
    codex_cfg = policy["codex"]
    claude_cfg = policy["claude"]
    oc_cfg = policy["opencode"]

    if mode == "check":
        mismatches: list[str] = []
        for rel in codex_cfg["profiles"]:
            for k, v in codex_cfg["top_level"].items():
                msg = check_toml_top_level(home / rel, k, v)
                if msg:
                    mismatches.append(msg)
        for rel in claude_cfg["profiles"]:
            mismatches.extend(check_claude_json(home / rel, claude_cfg))
        for rel in oc_cfg["profiles"]:
            mismatches.extend(check_opencode_json(home / rel, oc_cfg))
        if mismatches:
            for m in mismatches:
                print(f"DRIFT: {m}", file=sys.stderr)
            return 1
        print("OK: all configured Codex, Claude, and OpenCode output bounds match policy")
        return 0

    remove = mode == "revert"
    changed = 0

    for rel in codex_cfg["profiles"]:
        target = home / rel
        if remove and not target.exists():
            continue
        old = target.read_text(encoding="utf-8") if target.exists() else ""
        new = old
        for k, v in codex_cfg["top_level"].items():
            new = update_toml_top_level(new, k, v, remove=remove)
        if new != old:
            backup_file(target, state_dir, home)
            atomic_write_0600(target, new)
            changed += 1

    for rel in claude_cfg["profiles"]:
        target = home / rel
        if remove and not target.exists():
            continue
        old = target.read_text(encoding="utf-8") if target.exists() else "{}\n"
        new = update_claude_json(old, claude_cfg, remove=remove)
        if not target.exists() or new != old:
            backup_file(target, state_dir, home)
            atomic_write_0600(target, new)
            changed += 1

    for rel in oc_cfg["profiles"]:
        target = home / rel
        if remove and not target.exists():
            continue
        old = target.read_text(encoding="utf-8") if target.exists() else "{}\n"
        new = update_opencode_json(old, oc_cfg, remove=remove)
        if not target.exists() or new != old:
            backup_file(target, state_dir, home)
            atomic_write_0600(target, new)
            changed += 1

    action = "reverted" if remove else "applied"
    print(f"OK: {action} output bounds ({changed} file(s) updated)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync or check agent output bounds across Codex, Claude, and OpenCode.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Check whether target files match policy")
    group.add_argument("--apply", action="store_true", help="Apply output bounds to target files")
    group.add_argument("--revert", action="store_true", help="Remove managed output-bound keys from target files")
    parser.add_argument("--home", type=Path, default=Path.home(), help="Target home directory (defaults to current HOME)")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY, help="Policy JSON path")
    args = parser.parse_args(argv)
    mode = "check" if args.check else ("apply" if args.apply else "revert")
    return run(mode, args.home.resolve(), args.policy.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
