#!/usr/bin/env python3
"""Keep proximal the only Codex refresh-token holder, and mirror access tokens to remote hosts.

Codex (ChatGPT login) access tokens live ten days and the CLI renews only
inside its own process, five minutes before expiry; every renewal rotates the
refresh token and the auth server rejects a reused one (`refresh_token_reused`).
A full auth.json copied to another host is therefore a second refresh-token
holder: whichever host renews first invalidates the other.

Each run, for every profile in PROFILES:

1. If the access token expires within LEAD_HOURS, ask the profile's own CLI to
   renew it (`codex app-server`, `account/read` with `refreshToken: true`, the
   app-server's documented proactive-refresh request). The CLI performs and
   persists the rotation itself; this script never writes proximal's auth.json.
2. Push a copy of auth.json with `tokens.refresh_token` set to "" to the same
   path on every host in REMOTE_HOSTS, atomically (temp file + rename, 0600),
   and only when it differs. The CLI accepts an empty refresh token (a missing
   key fails to parse) and authenticates with the access token until it
   expires; a refresh attempt there fails harmlessly and reloads the next push.

Never prints token material.
"""

import argparse
import base64
import json
import logging
import os
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

PROFILES = ("~/.codex", "~/.codex-harm", "~/.codex-3")
REMOTE_HOSTS = ("peecee-wsl", "archon")
# Renew this far ahead of expiry. Seven days into a ten-day token, ahead of the
# eight-day `last_refresh` interval older CLIs (peecee-wsl's 0.153) still use.
LEAD_HOURS = 72
CODEX_BIN = os.environ.get("CODEX_BIN", "~/.npm-global/bin/codex")
APP_SERVER_TIMEOUT = 120
REMOTE_SSH = ("ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
              "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3")
REMOTE_TIMEOUT = 60
# Runs on the remote under `python3 -I -c`; the jobs (token material included)
# arrive on stdin, never in argv. Prints only paths and states.
REMOTE_WRITER = r"""
import json, os, sys, tempfile

for job in json.load(sys.stdin):
    path = os.path.expanduser(job["path"])
    try:
        with open(path) as stream:
            current = json.load(stream)
    except (FileNotFoundError, ValueError):
        current = None
    if current == job["auth"]:
        print(job["profile"], "current")
        continue
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".auth.json-", dir=directory)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(job["auth"], stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    print(job["profile"], "mirrored")
"""
LOG = logging.getLogger("codex-auth-mirror")


def auth_path(profile):
    return Path(profile).expanduser() / "auth.json"


def load(profile):
    try:
        return json.loads(auth_path(profile).read_text())
    except FileNotFoundError:
        return None


def access_expiry(auth):
    """The access token's `exp` claim (seconds), or None. Reads claims only."""
    token = ((auth or {}).get("tokens") or {}).get("access_token") or ""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return int(claims["exp"])
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def chatgpt_login(auth):
    tokens = (auth or {}).get("tokens") or {}
    return (auth or {}).get("auth_mode") in (None, "chatgpt") and bool(tokens.get("refresh_token"))


def renew_via_cli(profile):
    """Have the profile's own CLI rotate its tokens; returns True on a JSON-RPC reply."""
    env = dict(os.environ, CODEX_HOME=str(Path(profile).expanduser()))
    process = subprocess.Popen(
        [str(Path(CODEX_BIN).expanduser()), "app-server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, env=env, cwd=str(Path.home()),
    )
    watchdog = threading.Timer(APP_SERVER_TIMEOUT, process.kill)
    watchdog.start()

    def send(message):
        process.stdin.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
        process.stdin.flush()

    def reply(request_id):
        for line in process.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get("id") == request_id:
                return message
        return None

    try:
        send({"id": 1, "method": "initialize",
              "params": {"clientInfo": {"name": "codex-auth-mirror", "title": None, "version": "1"}}})
        if not (reply(1) or {}).get("result"):
            return False
        send({"method": "initialized"})
        send({"id": 2, "method": "account/read", "params": {"refreshToken": True}})
        return bool((reply(2) or {}).get("result"))
    except (BrokenPipeError, OSError):
        return False
    finally:
        watchdog.cancel()
        try:
            process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()


def renew_profile(profile, lead_seconds, force, dry_run):
    auth = load(profile)
    if auth is None:
        LOG.info("%s: no auth.json, skipping", profile)
        return True
    if not chatgpt_login(auth):
        LOG.info("%s: not a ChatGPT login with a refresh token, skipping renewal", profile)
        return True
    expires = access_expiry(auth)
    if expires is None:
        LOG.error("%s: access token carries no readable exp claim", profile)
        return False
    remaining = expires - time.time()
    if not force and remaining > lead_seconds:
        LOG.info("%s: access token valid for %.1f more days", profile, remaining / 86400)
        return True
    LOG.info("%s: renewing through the CLI (%s)", profile,
             "forced" if force else f"{remaining / 3600:.1f} h to expiry")
    if dry_run:
        return True
    answered = renew_via_cli(profile)
    renewed = access_expiry(load(profile))
    if renewed is None or renewed <= expires:
        LOG.error("%s: CLI renewal did not produce a newer token (reply=%s)", profile, answered)
        return False
    LOG.info("%s: renewed; new token expires in %.1f days", profile, (renewed - time.time()) / 86400)
    return True


def remote_job(profile):
    auth = load(profile)
    if not chatgpt_login(auth):
        return None
    expires = access_expiry(auth)
    if expires is None or expires <= time.time():
        LOG.error("%s: access token expired or unreadable; not mirroring it", profile)
        return None
    stripped = json.loads(json.dumps(auth))
    # Empty, not absent: the CLI's TokenData requires the field.
    stripped["tokens"]["refresh_token"] = ""
    return {"profile": profile, "path": f"{profile}/auth.json", "auth": stripped}


def mirror_remotes(profiles, hosts, dry_run):
    """Push refresh-token-free copies; an unreachable host is logged by name and retried next tick."""
    jobs = [job for job in (remote_job(profile) for profile in profiles) if job]
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
        LOG.info("%s: %s", host, " ".join(result.stdout.split()))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("profiles", nargs="*", default=list(PROFILES),
                        help="CODEX_HOME dirs, ~-relative (default: %(default)s)")
    parser.add_argument("--lead-hours", type=float, default=LEAD_HOURS,
                        help="renew when the access token expires within this many hours")
    parser.add_argument("--force", action="store_true", help="renew regardless of expiry")
    parser.add_argument("--dry-run", action="store_true", help="report without renewing or pushing")
    parser.add_argument("--no-renew", action="store_true", help="push only")
    parser.add_argument("--no-remote", action="store_true", help="renew only")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    ok = True
    if not args.no_renew:
        for profile in args.profiles:
            ok &= renew_profile(profile, args.lead_hours * 3600, args.force, args.dry_run)
    if not args.no_remote:
        mirror_remotes(args.profiles, REMOTE_HOSTS, args.dry_run)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
