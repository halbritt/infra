#!/usr/bin/env python3
"""Renew Claude Code OAuth access tokens ahead of expiry, for every local profile.

Claude Code only refreshes its token while a session is running and the token
is within five minutes of expiry. Between sessions the token lapses, and every
other consumer of the profile (the agent-usage dashboard, headless runs) sees
401s until someone starts the CLI. This performs the same refresh the CLI
does, with the CLI's client id, and rewrites the credentials file atomically.
Running sessions notice the mtime change and reload the file.

Never prints token material.
"""

import argparse
import json
import logging
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # Claude Code's public OAuth client
BETA = "oauth-2025-04-20"
DEFAULT_PROFILES = ("~/.claude", "~/.claude-harm")
LEAD_SECONDS = 45 * 60  # refresh when this close to expiry (CLI itself uses 5 min)
LOG = logging.getLogger("claude-oauth-refresh")


def read(path):
    return json.loads(path.read_text())


def atomic_write(path, payload):
    fd, name = tempfile.mkstemp(prefix=".credentials-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def request_refresh(oauth):
    body = {
        "grant_type": "refresh_token",
        "refresh_token": oauth["refreshToken"],
        "client_id": CLIENT_ID,
    }
    if oauth.get("scopes"):
        body["scope"] = " ".join(oauth["scopes"])
    request = urllib.request.Request(
        TOKEN_URL,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "anthropic-beta": BETA,
            "User-Agent": "claude-oauth-refresh/1 (proximal systemd timer)",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def refresh_profile(directory, now_ms, lead_ms, force, dry_run):
    path = directory / ".credentials.json"
    try:
        saved = read(path)
    except FileNotFoundError:
        LOG.info("%s: no credentials file, skipping", directory)
        return True
    oauth = saved.get("claudeAiOauth") or {}
    if not oauth.get("refreshToken"):
        LOG.info("%s: no refresh token (not a claude.ai login), skipping", directory)
        return True
    expires_at = oauth.get("expiresAt") or 0
    remaining = (expires_at - now_ms) / 1000
    if oauth.get("refreshTokenExpiresAt") and oauth["refreshTokenExpiresAt"] <= now_ms:
        LOG.error("%s: refresh token itself has expired; run `claude auth login`", directory)
        return False
    if not force and expires_at - now_ms > lead_ms:
        LOG.info("%s: access token valid for %.0f more minutes", directory, remaining / 60)
        return True
    LOG.info(
        "%s: refreshing (%s)",
        directory,
        "forced" if force else f"{remaining / 60:.0f} minutes to expiry",
    )
    if dry_run:
        return True
    try:
        data = request_refresh(oauth)
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = json.loads(error.read()).get("error", "")
        except (ValueError, AttributeError):
            pass
        LOG.error("%s: token endpoint returned HTTP %s %s", directory, error.code, detail)
        return False
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        LOG.error("%s: refresh request failed: %s", directory, error)
        return False
    if "access_token" not in data or "expires_in" not in data:
        LOG.error("%s: token endpoint response lacked access_token/expires_in", directory)
        return False

    # Re-read right before writing: if the CLI rotated the refresh token
    # meanwhile, its file wins and ours is discarded rather than clobbering it.
    current = read(path)
    if (current.get("claudeAiOauth") or {}).get("refreshToken") != oauth["refreshToken"]:
        LOG.warning("%s: credentials changed during refresh; keeping the CLI's copy", directory)
        return True
    written_at = int(time.time() * 1000)
    updated = dict(current["claudeAiOauth"])
    updated["accessToken"] = data["access_token"]
    updated["refreshToken"] = data.get("refresh_token") or oauth["refreshToken"]
    updated["expiresAt"] = written_at + int(data["expires_in"]) * 1000
    if data.get("refresh_token_expires_in"):
        updated["refreshTokenExpiresAt"] = written_at + int(data["refresh_token_expires_in"]) * 1000
    if data.get("scope"):
        updated["scopes"] = data["scope"].split()
    current["claudeAiOauth"] = updated
    atomic_write(path, current)
    LOG.info(
        "%s: renewed; new token expires in %.1f h, refresh token in %.0f d",
        directory,
        int(data["expires_in"]) / 3600,
        (updated.get("refreshTokenExpiresAt", written_at) - written_at) / 86400000,
    )
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("profiles", nargs="*", default=list(DEFAULT_PROFILES),
                        help="Claude config dirs (default: %(default)s)")
    parser.add_argument("--lead-minutes", type=float, default=LEAD_SECONDS / 60,
                        help="refresh when the token expires within this many minutes")
    parser.add_argument("--force", action="store_true", help="refresh regardless of expiry")
    parser.add_argument("--dry-run", action="store_true", help="report without contacting the token endpoint")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    now_ms = int(time.time() * 1000)
    ok = True
    for profile in args.profiles:
        ok &= refresh_profile(Path(profile).expanduser(), now_ms, args.lead_minutes * 60000, args.force, args.dry_run)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
