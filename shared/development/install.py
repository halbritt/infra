#!/usr/bin/env python3
"""Install development-evidence for this user from this infra checkout."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile

SOURCE = Path(__file__).resolve().parent / "development_evidence.py"
TARGET = Path.home() / ".local/bin/development-evidence"


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify installed bytes without changing anything")
    parser.add_argument("--target", type=Path, default=TARGET, help=f"installed executable (default: {TARGET})")
    args = parser.parse_args(argv)
    target, expected = args.target, digest(SOURCE)
    matches = target.is_file() and not target.is_symlink() and digest(target) == expected and os.access(target, os.X_OK)
    if args.check:
        if not matches:
            print(f"Installation differs: {target} is not {SOURCE} (sha256 {expected})")
            return 1
        print(f"{target} matches {SOURCE} (sha256 {expected})")
        return 0
    if not matches:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            temp = Path(handle.name)
            handle.write(SOURCE.read_bytes())
        try:
            temp.chmod(0o755)
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
    print(f"{target} installed from {SOURCE} (sha256 {expected})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
