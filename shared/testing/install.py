#!/usr/bin/env python3
"""Install the pinned mise binary and shared host test tasks for this user."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

VERSION = "2026.11.7"
ARCHIVE_SHA256 = "3198a5ed5716ca8c17ecfc54521e2769d6cacbf2d13f24f0c2f9706620ec0024"
BINARY_SHA256 = "8f5426d9971eaf713b37509749174ca69cf2f08b8b25e389168dcfcab9cd1a4d"
URL = f"https://github.com/jdx/mise/releases/download/v{VERSION}/mise-v{VERSION}-linux-x64.tar.gz"
BEGIN = "<!-- BEGIN SHARED TEST WORKFLOW -->"
END = "<!-- END SHARED TEST WORKFLOW -->"
INSTRUCTIONS = (".codex/AGENTS.md", ".codex-harm/AGENTS.md", ".codex-3/AGENTS.md",
                ".claude/CLAUDE.md", ".claude-harm/CLAUDE.md", ".gemini/config/AGENTS.md")


def managed_instructions(original, content):
    block = BEGIN + "\n" + content.rstrip() + "\n" + END
    if BEGIN not in original and END not in original:
        return original.rstrip() + "\n\n" + block + "\n"
    if original.count(BEGIN) != 1 or original.count(END) != 1:
        raise ValueError("testing instruction markers are incomplete or duplicated")
    before, rest = original.split(BEGIN, 1)
    _, after = rest.split(END, 1)
    return before + block + after


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def atomic_write(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        f.write(data)
    try:
        temp.chmod(mode)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="already downloaded release archive (hash checked)")
    parser.add_argument("--check", action="store_true", help="verify installed bytes without changing anything")
    args = parser.parse_args()
    if os.uname().machine != "x86_64" or os.uname().sysname != "Linux":
        parser.error("this pinned deployment is Linux x86_64")
    source = Path(__file__).resolve().parent
    binary = Path.home() / ".local/bin/mise"
    tasks = Path.home() / ".config/mise/tasks/host"
    content = (source / "agent-instructions.md").read_text()
    updates = {}
    for relative in INSTRUCTIONS:
        path = Path.home() / relative
        if path.is_file():
            updates[path] = managed_instructions(path.read_text(), content)
    if args.check:
        expected = {binary: BINARY_SHA256}
        expected.update({tasks / name: digest(source / "tasks/host" / name) for name in ("exec", "doctor")})
        bad = [str(p) for p, sha in expected.items() if not p.is_file() or digest(p) != sha or not os.access(p, os.X_OK)]
        bad.extend(str(p) for p, updated in updates.items() if p.read_text() != updated)
        if bad:
            parser.exit(1, "Installation differs: " + ", ".join(bad) + "\n")
        print(f"mise {VERSION} and shared host tasks match their installed source")
        return
    if not binary.is_file() or digest(binary) != BINARY_SHA256:
        cache = Path.home() / ".cache/host-testing"
        cache.mkdir(parents=True, exist_ok=True)
        archive = args.archive or cache / f"mise-v{VERSION}-linux-x64.tar.gz"
        if not args.archive and not archive.exists():
            partial = archive.with_suffix(".partial")
            subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error", "--max-time", "120",
                            "--output", str(partial), URL], check=True)
            partial.replace(archive)
        if digest(archive) != ARCHIVE_SHA256:
            parser.error(f"release archive SHA-256 mismatch: {archive}")
        with tarfile.open(archive) as tar:
            data = tar.extractfile("mise/bin/mise").read()
        if hashlib.sha256(data).hexdigest() != BINARY_SHA256:
            parser.error("release binary SHA-256 mismatch")
        if binary.exists():
            backup = cache / f"mise-before-{digest(binary)}"
            if not backup.exists():
                shutil.copy2(binary, backup)
        atomic_write(binary, data, 0o755)
    for name in ("exec", "doctor"):
        p = source / "tasks/host" / name
        atomic_write(tasks / p.name, p.read_bytes(), 0o755)
    backup_dir = Path.home() / ".cache/host-testing/instruction-backups"
    for path, updated in updates.items():
        if path.read_text() == updated:
            continue
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / (str(path.relative_to(Path.home())).replace("/", "_") + "." + digest(path))
        if not backup.exists():
            shutil.copy2(path, backup)
        atomic_write(path, updated.encode(), path.stat().st_mode & 0o777)
    print(f"Installed mise {VERSION}: {binary}")
    print(f"Installed shared tasks: {tasks}")
    print("No shell activation or global tool/version changes are needed.")


if __name__ == "__main__":
    main()
