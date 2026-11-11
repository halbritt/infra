#!/usr/bin/python3
"""Keep the Frank tunnel and its Cairn connector session in one lifecycle."""

import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid


CAIRN = "/home/halbritt/.local/share/cairn/deployments/frank-tunnel-20261110/cairn"
TOKEN = "/home/halbritt/.local/share/cairn/hosted-agent.token"
SOCKET = "/home/halbritt/.local/share/cairn/api.sock"
TUNNEL_ID = "tunnel_6af3d023e590819194500a5bb31fe28e"
SESSION_FILE = Path("/home/halbritt/.local/state/cairn-frank/session.json")
TUNNEL_COMMAND = [
    "/home/halbritt/.local/bin/tunnel-client", "run", "--profile", "cairn-frank",
    "--mcp.stdio-failure-policy", "exit",
]


def session_call(operation, *arguments):
    completed = subprocess.run(
        [CAIRN, "agents", operation, "--token-file", TOKEN, "--socket", SOCKET,
         *arguments],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"Cairn {operation} exited {completed.returncode}")
    envelope = json.loads(completed.stdout)
    if envelope.get("ok") is not True:
        raise RuntimeError(f"Cairn {operation} refused: {envelope.get('status')}")
    return envelope["data"]


def register():
    # A connector has one persistent inbox, shared by its ChatGPT conversations.
    session = session_call(
        "register", "--request-id", str(uuid.uuid4()),
        "--binding", "chatgpt-frank-tunnel", "--native-session", TUNNEL_ID,
        "--harness", "chatgpt", "--project", "frank", "--state", "idle",
        "--workspace", "/home/halbritt", "--repo", "/home/halbritt/git/cairn",
        "--task", "Frank messaging connector; shared inbox polled from ChatGPT",
        "--delivery-mode", "existing-session",
    )
    for field in ("agent_id", "execution_id"):
        uuid.UUID(session[field])
    return session


def save_session(session):
    SESSION_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    pending = SESSION_FILE.with_suffix(".pending")
    pending.write_text(json.dumps(session) + "\n", encoding="utf-8")
    pending.chmod(0o600)
    pending.replace(SESSION_FILE)


def stop_child(child):
    if child.poll() is None:
        if child.pid <= 1:
            raise RuntimeError("refusing to signal an invalid child PID")
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def supervise(stopping):
    session = register()
    identity = ["--agent-id", session["agent_id"],
                "--execution-id", session["execution_id"]]
    child = None
    try:
        save_session(session)
        if stopping.is_set():
            return 0
        child = subprocess.Popen(TUNNEL_COMMAND)
        logging.info("Frank connector registered as %s", session["display_name"])
        next_heartbeat = time.monotonic() + 25
        while not stopping.wait(1):
            exit_code = child.poll()
            if exit_code is not None:
                raise RuntimeError(f"tunnel-client exited unexpectedly: {exit_code}")
            if time.monotonic() >= next_heartbeat:
                session_call("heartbeat", *identity)
                next_heartbeat = time.monotonic() + 25
        return 0
    finally:
        try:
            if child is not None:
                stop_child(child)
        finally:
            # If this fails, presence expires after 90 seconds. Do not claim success.
            session_call("leave", *identity)


def main():
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    stopping = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopping.set())
    return supervise(stopping)


if __name__ == "__main__":
    raise SystemExit(main())
