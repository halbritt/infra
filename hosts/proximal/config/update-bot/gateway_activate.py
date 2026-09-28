#!/usr/bin/env python3
"""Fixed user-gateway activation boundary; no caller-supplied command or unit."""
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

import update_bot as bot

HOME = Path('/home/halbritt/.hermes')
LAUNCHER = Path('/home/halbritt/.local/bin/hermes')
UNIT = 'hermes-gateway.service'
DRAIN_SECONDS = 30
START_SECONDS = 90


def systemctl(*args):
    return subprocess.check_output(['systemctl', '--user', *args], text=True, timeout=15).strip()


def snapshot():
    status = bot.read_json(HOME / 'gateway_state.json', {})
    try:
        written = datetime.fromisoformat(status.get('updated_at', '')).timestamp()
    except (TypeError, ValueError):
        written = 0
    return status, written


def healthy(status, pid, revision):
    return (pid > 0 and status.get('pid') == pid and status.get('code_sha') == revision
            and status.get('gateway_state') == 'running'
            and status.get('platforms', {}).get('slack', {}).get('state') == 'connected')


def selected_revision():
    installed = bot.read_json(bot.STATE / 'hermes-installed.json', {})
    revision = installed.get('source_revision', '')
    source = Path(installed.get('source', '/missing')).resolve()
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Missing exact installed Hermes revision')
    if not (source.is_relative_to(bot.STATE.resolve()) or source == HOME / 'hermes-agent'):
        raise ValueError('Hermes source is outside approved generations')
    actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True, timeout=15).strip()
    if actual != revision:
        raise ValueError('Installed Hermes source receipt does not match checkout')
    artifact = next((a for a in installed.get('artifacts', []) if a.get('installed') == str(LAUNCHER)), {})
    if hashlib.sha256(LAUNCHER.read_bytes()).hexdigest() != artifact.get('sha256'):
        raise ValueError('Installed Hermes launcher receipt does not match artifact')
    return revision


def activate():
    # The unit runs the frozen interpreter: these native helpers cannot be
    # replaced by changing the candidate being activated.
    from gateway.drain_control import write_drain_request, clear_drain_request

    revision = selected_revision()
    marker = HOME / '.drain_request.json'
    if marker.exists():
        raise RuntimeError('Existing drain belongs to another operation; reconcile first')
    old_pid = int(systemctl('show', UNIT, '-p', 'MainPID', '--value'))
    status, _ = snapshot()
    if healthy(status, old_pid, revision):
        return {'status': 'verified', 'changed': False, 'revision': revision, 'pid': old_pid}
    if old_pid <= 0:
        raise RuntimeError('Gateway is not running; repair its native service before activation')
    if 'argv[]=' + str(LAUNCHER) + ' gateway run ;' not in systemctl('show', UNIT, '-p', 'ExecStart', '--value'):
        raise RuntimeError('Gateway unit does not select the approved versioned launcher')
    requested_at = time.time()
    owner = 'update-bot/' + str(uuid.uuid4())
    # Reserve only our marker. Native writers can still replace it; cleanup
    # below must never remove a replacement owned by someone else.
    with marker.open('x') as stream:
        json.dump({'principal': owner}, stream)
    try:
        write_drain_request(principal=owner, suppress_notification=True, home=HOME)
        deadline = time.monotonic() + DRAIN_SECONDS
        while True:
            status, written = snapshot()
            if (written >= requested_at and status.get('pid') == old_pid
                    and status.get('gateway_state') == 'draining'
                    and type(status.get('active_agents')) is int and status['active_agents'] == 0):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Fresh zero-work drain was not established; no restart issued')
            time.sleep(0.5)
        if int(systemctl('show', UNIT, '-p', 'MainPID', '--value')) != old_pid:
            raise RuntimeError('Gateway changed while draining; reconcile before restart')
        # Verify ownership immediately before the consequential signal.
        if bot.read_json(marker, {}).get('principal') != owner:
            raise RuntimeError('Drain ownership changed; no restart issued')
        systemctl('reload', UNIT)
        deadline = time.monotonic() + START_SECONDS
        while True:
            new_pid = int(systemctl('show', UNIT, '-p', 'MainPID', '--value'))
            status, written = snapshot()
            connected = status.get('platforms', {}).get('slack', {})
            try:
                connected_at = datetime.fromisoformat(connected.get('updated_at', '')).timestamp()
            except (TypeError, ValueError):
                connected_at = 0
            if (new_pid > 0 and new_pid != old_pid and written >= requested_at
                    and connected_at >= requested_at
                    and status.get('pid') == new_pid and status.get('code_sha') == revision
                    and status.get('gateway_state') in ('draining', 'running')
                    and connected.get('state') == 'connected'):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('New gateway identity/Slack connection unverified; inspect before any retry')
            time.sleep(0.5)
    finally:
        if bot.read_json(marker, {}).get('principal') == owner:
            if not clear_drain_request(home=HOME):
                raise RuntimeError('Could not release owned gateway drain; operator recovery required')
    deadline = time.monotonic() + 10
    while True:
        status, _ = snapshot()
        if healthy(status, int(systemctl('show', UNIT, '-p', 'MainPID', '--value')), revision):
            return {'status': 'verified', 'changed': True, 'revision': revision,
                    'old_pid': old_pid, 'pid': status['pid'], 'drain': 'fresh zero chat/cron/API work',
                    'slack': 'connected'}
        if time.monotonic() >= deadline:
            raise RuntimeError('Gateway did not return to running after drain release')
        time.sleep(0.5)


def main():
    if len(sys.argv) != 1:
        raise SystemExit('This fixed activation helper accepts no arguments')
    bot.STATE.mkdir(exist_ok=True)
    with (bot.STATE / 'gateway-activation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = {'status': 'running', 'started': time.time()}
        path = bot.STATE / 'hermes-activation-latest.json'
        bot.atomic_json(path, result)
        def interrupted(*_):
            raise RuntimeError('Activation interrupted; inspect native state before retry')
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        try:
            result.update(activate())
        except Exception as exc:
            result.update(status='failed', error=str(exc))
        result['finished'] = time.time()
        bot.atomic_json(path, result)
        print(json.dumps(result), flush=True)
        return 0 if result['status'] == 'verified' else 1


if __name__ == '__main__':
    sys.exit(main())
