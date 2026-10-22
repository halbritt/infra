#!/usr/bin/env python3
"""Renew Claude Code OAuth access tokens ahead of expiry, for every local profile.

Claude Code only refreshes its token while a session is running and the token
is within five minutes of expiry. Between sessions the token lapses, and every
other consumer of the profile (the agent-usage dashboard, headless runs) sees
401s until someone starts the CLI. This performs the same refresh the CLI
does, with the CLI's client id, and rewrites the credentials file atomically.
Running sessions notice the mtime change and reload the file.

After renewing a profile it mirrors that profile's *access* token into the
consumer profiles declared in MIRRORS (the striatum harness homes), which hold
no login of their own. The refresh token is deliberately not copied: a second
holder of a refresh token destroys the source's lineage the moment either side
rotates it, which is exactly how the striatum copy self-destructed on
2026-09-14. A mirror can only read; it can never rotate.

Never prints token material.
"""

import argparse
import json
import logging
import os
import shlex
import subprocess
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
STRIATUM = "~/.local/share/striatum/harness-config"
# source profile -> (its config file, consumer profiles that mirror its access token)
MIRRORS = {
    "~/.claude": (f"{STRIATUM}/claude-code",),
    "~/.claude-harm": (f"{STRIATUM}/claude-harm",),
}
# Where each source profile's `oauthAccount` block lives. The default profile
# keeps its config beside $HOME, not inside the config dir.
SOURCE_CONFIGS = {
    "~/.claude": "~/.claude.json",
    "~/.claude-harm": "~/.claude-harm/.claude.json",
}
# Copied into a mirror's credentials; everything else (refreshToken above all)
# stays behind.
MIRRORED_FIELDS = ("accessToken", "expiresAt", "scopes", "subscriptionType", "rateLimitTier")
# Remote hosts that run agent workers on the owner's subscription logins. Each
# gets an access-token-only copy of every source profile at the same path, plus
# the source's `oauthAccount` block in the matching config file when that file
# exists there. proximal stays the only holder of the refresh token.
REMOTE_HOSTS = ("peecee-wsl", "archon", "agent-ee-gate-c4")
REMOTE_SSH = ("ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
              "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3")
REMOTE_TIMEOUT = 60  # seconds per host; a hung host must not hold the timer
# Runs on the remote under `python3 -I -c`; the job list (token material
# included) arrives on stdin, never in argv. Prints only profile names and
# states. Mirrors write_mirror()/mirror_account() below.
REMOTE_WRITER = r"""
import json, os, sys, tempfile

def read(path):
    try:
        with open(path) as stream:
            return json.load(stream)
    except FileNotFoundError:
        return None

def write(path, payload):
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + os.path.basename(path) + "-", dir=directory)
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

for job in json.load(sys.stdin):
    path = os.path.expanduser(job["credentials"])
    current = read(path) or {}
    old = current.get("claudeAiOauth") or {}
    block = dict(old)
    block.pop("refreshToken", None)
    block.pop("refreshTokenExpiresAt", None)
    block.update(job["fields"])
    state = "current"
    if block != old:
        current["claudeAiOauth"] = block
        write(path, current)
        state = "mirrored"
    account = job.get("account")
    if account:
        config_path = os.path.expanduser(job["config"])
        try:
            config = read(config_path)
        except ValueError:
            config = None
        if config is not None and config.get("oauthAccount") != account:
            config["oauthAccount"] = account
            write(config_path, config)
            state += "+account"
    print(job["profile"], state)
"""
LEAD_SECONDS = 45 * 60  # refresh when this close to expiry (CLI itself uses 5 min)
LOG = logging.getLogger("claude-oauth-refresh")


class Source:
    """A profile the timer refreshes, and the paths its mirrors read from."""

    def __init__(self, profile):
        self.key = profile
        self.directory = Path(profile).expanduser()
        config = SOURCE_CONFIGS.get(profile, f"{profile}/.claude.json")
        self.config = Path(config).expanduser()

    @property
    def credentials(self):
        return self.directory / ".credentials.json"


def read(path):
    return json.loads(path.read_text())


def atomic_write(path, payload):
    fd, name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
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


def mirror_profile(source, now_ms, dry_run):
    """Copy the source's access token (never its refresh token) to its mirrors.

    A mirror is a consumer config dir with no login of its own: striatum's
    harness homes. It gets a read-only lease on the source's session — valid
    until the source's `expiresAt`, by which time this timer has already
    written the next one. `oauthAccount` is carried across too, so the mirror
    reports the account its token actually belongs to.
    """
    targets = MIRRORS.get(source.key) or ()
    if not targets:
        return True
    try:
        oauth = (read(source.credentials).get("claudeAiOauth") or {})
    except FileNotFoundError:
        LOG.info("%s: no credentials to mirror", source.key)
        return True
    if not oauth.get("accessToken"):
        LOG.error("%s: no access token to mirror; run `claude auth login` for it", source.key)
        return False
    if (oauth.get("expiresAt") or 0) <= now_ms:
        LOG.error("%s: access token already expired; not mirroring a dead token", source.key)
        return False
    try:
        account = read(source.config).get("oauthAccount")
    except (FileNotFoundError, ValueError):
        account = None

    ok = True
    for target in targets:
        directory = Path(target).expanduser()
        if not directory.is_dir():
            LOG.error("%s: mirror target %s does not exist", source.key, directory)
            ok = False
            continue
        ok &= write_mirror(source.key, directory, oauth, account, dry_run)
    return ok


def write_mirror(source_key, directory, oauth, account, dry_run):
    path = directory / ".credentials.json"
    try:
        current = read(path)
    except (FileNotFoundError, ValueError):
        current = {}
    block = dict(current.get("claudeAiOauth") or {})
    # A mirror must never hold a refresh token: whichever holder rotates it
    # first invalidates the other. Drop any left over from an earlier login.
    block.pop("refreshToken", None)
    block.pop("refreshTokenExpiresAt", None)
    for field in MIRRORED_FIELDS:
        if oauth.get(field) is not None:
            block[field] = oauth[field]
    if block == (current.get("claudeAiOauth") or {}) and not account_stale(directory, account):
        LOG.info("%s -> %s: already current", source_key, directory)
        return True
    if dry_run:
        LOG.info("%s -> %s: would mirror access token", source_key, directory)
        return True
    current["claudeAiOauth"] = block
    atomic_write(path, current)
    LOG.info(
        "%s -> %s: mirrored access token (expires in %.1f h)",
        source_key,
        directory,
        (block["expiresAt"] - time.time() * 1000) / 3600000,
    )
    return mirror_account(directory, account)


def account_stale(directory, account):
    if not account:
        return False
    try:
        existing = read(directory / ".claude.json").get("oauthAccount")
    except (FileNotFoundError, ValueError):
        return True
    return existing != account


def mirror_account(directory, account):
    """Point the mirror's config at the account its mirrored token belongs to.

    Without this the CLI reports a stale identity for the profile, which is how
    the 2026-09-14 restore convinced itself it had two distinct accounts when it
    had one. Only `oauthAccount` is touched; every other setting is preserved.
    """
    if not account_stale(directory, account):
        return True
    path = directory / ".claude.json"
    try:
        config = read(path)
    except (FileNotFoundError, ValueError):
        LOG.warning("%s: no readable .claude.json; leaving the account block alone", directory)
        return True
    config["oauthAccount"] = account
    atomic_write(path, config)
    LOG.info("%s: account block set to %s", directory, account.get("emailAddress", "?"))
    return True


def remote_job(source, now_ms):
    """The access-token-only payload one source profile sends to each remote.

    Only the default profiles go remote, under their `~`-relative names, so the
    remote expands them against its own home whatever spelling was passed here.
    """
    canonical = {Path(profile).expanduser(): profile for profile in DEFAULT_PROFILES}
    key = canonical.get(source.directory)
    if key is None:
        return None
    try:
        oauth = (read(source.credentials).get("claudeAiOauth") or {})
    except FileNotFoundError:
        return None
    if not oauth.get("accessToken") or (oauth.get("expiresAt") or 0) <= now_ms:
        LOG.error("%s: no live access token; not mirroring to remote hosts", key)
        return None
    try:
        account = read(source.config).get("oauthAccount")
    except (FileNotFoundError, ValueError):
        account = None
    return {
        "profile": key,
        "credentials": f"{key}/.credentials.json",
        "config": SOURCE_CONFIGS[key],
        "fields": {field: oauth[field] for field in MIRRORED_FIELDS if oauth.get(field) is not None},
        "account": account,
    }


def mirror_remotes(sources, now_ms, hosts, dry_run):
    """Push access-token-only copies of every source profile to the remote hosts.

    The remote paths are the source paths (`~/.claude`, `~/.claude-harm`), so
    worker CLIs there run unmodified. Any refresh token a remote holds is
    dropped: the provider rotates on every renewal, so a second holder either
    dies at proximal's next renewal or, if it renews first, logs proximal out.
    An unreachable or failing host is logged by name only (stderr can carry
    remote paths or tracebacks) and never fails the unit; the next tick retries.
    """
    jobs = [job for job in (remote_job(source, now_ms) for source in sources) if job]
    if not jobs:
        return
    payload = json.dumps(jobs)
    for host in hosts:
        if dry_run:
            LOG.info("%s: would mirror %s", host, ", ".join(job["profile"] for job in jobs))
            continue
        command = [*REMOTE_SSH, host, f"python3 -I -c {shlex.quote(REMOTE_WRITER)}"]
        try:
            result = subprocess.run(command, input=payload, capture_output=True,
                                    text=True, timeout=REMOTE_TIMEOUT, check=False)
        except (OSError, subprocess.TimeoutExpired):
            LOG.warning("%s: remote mirror failed; retrying next tick", host)
            continue
        if result.returncode != 0:
            LOG.warning("%s: remote mirror failed; retrying next tick", host)
            continue
        states = " ".join(result.stdout.split())
        LOG.info("%s: %s", host, states)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("profiles", nargs="*", default=list(DEFAULT_PROFILES),
                        help="Claude config dirs (default: %(default)s)")
    parser.add_argument("--lead-minutes", type=float, default=LEAD_SECONDS / 60,
                        help="refresh when the token expires within this many minutes")
    parser.add_argument("--force", action="store_true", help="refresh regardless of expiry")
    parser.add_argument("--dry-run", action="store_true", help="report without contacting the token endpoint")
    parser.add_argument("--no-mirror", action="store_true",
                        help="renew only; do not update the consumer profiles in MIRRORS or remote hosts")
    parser.add_argument("--no-remote", action="store_true",
                        help="do not push access-token copies to REMOTE_HOSTS")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    now_ms = int(time.time() * 1000)
    ok = True
    sources = [Source(profile) for profile in args.profiles]
    for source in sources:
        ok &= refresh_profile(source.directory, now_ms, args.lead_minutes * 60000, args.force, args.dry_run)
        if not args.no_mirror:
            ok &= mirror_profile(source, now_ms, args.dry_run)
    if not (args.no_mirror or args.no_remote):
        mirror_remotes(sources, int(time.time() * 1000), REMOTE_HOSTS, args.dry_run)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
