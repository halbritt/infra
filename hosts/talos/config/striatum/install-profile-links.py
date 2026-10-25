#!/usr/bin/env python3
"""Link Striatum harnesses to the access-only profiles mirrored from proximal."""
import json
import os
from pathlib import Path
import stat
import time
import uuid


def main():
    home = Path.home()
    links = [
        (home / ".claude/.credentials.json", "claude-code"),
        (home / ".claude-harm/.credentials.json", "claude-harm"),
    ]
    # Validate both profiles before changing either harness destination.
    for source, _ in links:
        oauth = json.loads(source.read_text())["claudeAiOauth"]
        if any(key in oauth for key in ("refreshToken", "refreshTokenExpiresAt")):
            raise SystemExit("Refusing a profile containing refresh fields")
        if not oauth.get("accessToken") or oauth.get("expiresAt", 0) <= time.time() * 1000:
            raise SystemExit("Refusing a missing or expired access token")
        if stat.S_IMODE(source.stat().st_mode) != 0o600:
            raise SystemExit("Refusing a profile whose permissions are not 0600")
    for source, harness in links:
        destination = home / ".local/share/striatum/harness-config" / harness / ".credentials.json"
        if not destination.parent.is_dir():
            raise SystemExit("Expected harness directory is missing")
        if destination.is_symlink() and destination.resolve() == source:
            print(harness + ": existing access-only profile link verified")
            continue
        temporary = destination.with_name(".credential-link-" + uuid.uuid4().hex)
        try:
            temporary.symlink_to(source)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        print(harness + ": access-only profile link installed")


if __name__ == "__main__":
    main()
