#!/usr/bin/python3
"""Fixed Archon Herdr binary update; never stop or hand off a live session."""
import fcntl
import hashlib
import json
import os
import pwd
import re
import urllib.request
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tempfile

STATE = Path('/var/lib/update-bot-herdr')
BINARY = '/usr/bin/herdr'


def command(argv):
    return subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=True).stdout.strip()


def processes():
    result = {}
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if (proc / 'comm').read_text().strip() != 'herdr':
                continue
            stat = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
            exe = (proc / 'exe').stat()
            result[proc.name] = [stat[19], exe.st_dev, exe.st_ino]
        except FileNotFoundError:
            continue
    return result


def save(receipt):
    tmp = STATE / 'latest.tmp'
    with tmp.open('w') as stream:
        stream.write(json.dumps(receipt, indent=2) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(STATE / 'latest.json')


def run():
    if len(sys.argv) != 1 or os.geteuid() != 0:
        raise RuntimeError('Fixed root helper accepts no arguments')
    STATE.mkdir(mode=0o700, exist_ok=True)
    with (STATE / 'update.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prior = STATE / 'latest.json'
        if prior.exists() and json.loads(prior.read_text())['status'] in ('running', 'uncertain'):
            raise RuntimeError('Prior update needs reconciliation; refusing to repeat it')
        # The owner uses stable; do not silently switch either the root updater or user.
        for argv in ([BINARY, 'channel', 'show'],
                     ['runuser', '-u', 'halbritt', '--', BINARY, 'channel', 'show']):
            if command(argv) != 'stable':
                raise RuntimeError('Herdr channel changed; review required')
        with urllib.request.urlopen('https://api.github.com/repos/herdrdev/herdr/releases/latest', timeout=30) as response:
            target = json.load(response)['tag_name']
        if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', target):
            raise RuntimeError('Unexpected stable release identity')
        before = command([BINARY, '--version'])
        observed = processes()
        digest = hashlib.sha256(Path(BINARY).read_bytes()).hexdigest()
        backup = STATE / ('herdr-' + digest)
        if not backup.exists():
            shutil.copy2(BINARY, backup)
        receipt = dict(host='archon', status='running', started=time.time(), before=before, target=target,
                       before_sha256=digest, backup=str(backup), processes_before=observed)
        save(receipt)
        try:
            # Stage as the desktop user so native session/protocol checks see
            # their actual sessions. Root only backs up and replaces /usr/bin.
            user = pwd.getpwnam('halbritt')
            with tempfile.TemporaryDirectory(prefix='herdr-update-', dir='/var/tmp') as directory:
                stage = Path(directory) / 'herdr'
                shutil.copy2(BINARY, stage)
                os.chown(directory, user.pw_uid, user.pw_gid)
                os.chown(stage, user.pw_uid, user.pw_gid)
                with (STATE / 'update.log').open('w') as log:
                    completed = subprocess.run(['runuser', '-u', 'halbritt', '--', str(stage), 'update'],
                                               stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
                receipt['exit_code'] = completed.returncode
                staged_version = command([str(stage), '--version'])
                unchanged = processes()
                preserved = all(unchanged.get(pid) == identity for pid, identity in observed.items())
                if (completed.returncode == 0 and staged_version == 'herdr ' + target[1:] and preserved
                        and hashlib.sha256(stage.read_bytes()).hexdigest() != digest):
                    # Copy into the destination directory, then replace atomically.
                    candidate = Path(BINARY).with_name('.herdr-maintenance.tmp')
                    shutil.copyfile(stage, candidate)
                    os.chmod(candidate, 0o755)
                    with candidate.open('rb') as stream:
                        os.fsync(stream.fileno())
                    candidate.replace(BINARY)
            receipt['after'] = command([BINARY, '--version'])
            receipt['after_sha256'] = hashlib.sha256(Path(BINARY).read_bytes()).hexdigest()
            after_processes = processes()
            receipt['processes_preserved'] = all(after_processes.get(pid) == identity
                                                 for pid, identity in observed.items())
            receipt['changed'] = digest != receipt['after_sha256']
            receipt['status'] = ('verified' if completed.returncode == 0 and receipt['processes_preserved']
                                 and receipt['after'] == 'herdr ' + target[1:]
                                 else 'failed')
            receipt['activation'] = ('Existing processes retained; installed version: ' + receipt['after']
                                     if receipt['processes_preserved'] else 'Process continuity check failed')
        except Exception as exc:
            receipt.update(status='uncertain', error=str(exc))
        receipt['finished'] = time.time()
        save(receipt)
        print(json.dumps(receipt))
        return 0 if receipt['status'] == 'verified' else 1


if __name__ == '__main__':
    sys.exit(run())
