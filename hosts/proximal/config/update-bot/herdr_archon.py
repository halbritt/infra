#!/usr/bin/python3
"""Reach one fixed remote helper without exposing SSH to the maintenance agent."""
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time
import update_bot as bot


def run():
    if len(sys.argv) != 1:
        raise RuntimeError('Fixed helper accepts no arguments')
    path = bot.STATE / 'herdr-archon-latest.json'
    with (bot.STATE / 'herdr-archon.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prior = bot.read_json(path, {})
        if prior.get('status') in ('running', 'uncertain'):
            raise RuntimeError('Prior remote update needs reconciliation; no automatic retry')
        receipt = dict(host='archon', status='uncertain', started=time.time())
        bot.atomic_json(path, receipt)
        result = subprocess.run([
            '/usr/bin/ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
            'archon', 'sudo', '-n', '/usr/local/lib/update-bot/herdr_update.py'],
            stdin=subprocess.DEVNULL, capture_output=True, text=True)
        try:
            remote = json.loads(result.stdout)
        except json.JSONDecodeError:
            remote = {}
        if remote.get('host') == 'archon' and remote.get('status') in ('verified', 'failed', 'uncertain'):
            status = remote['status']
            if status == 'verified' and result.returncode != 0:
                status = 'uncertain'
            receipt.update(status=status, finished=time.time(), remote=remote,
                           changed=remote.get('changed'))
            bot.atomic_json(path, receipt)
        else:
            # SSH may have failed after admission. Never retry an uncertain send.
            (bot.STATE / 'herdr-archon-error.log').write_text(result.stderr)
        print(json.dumps(receipt))
        return 0 if receipt['status'] == 'verified' else 1


if __name__ == '__main__':
    sys.exit(run())
