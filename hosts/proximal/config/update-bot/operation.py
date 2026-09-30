#!/usr/bin/env python3
"""Generic intent/result envelope, not a catalogue of package-specific adapters."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

import update_bot as bot


def validate(request, status, settings, now):
    required = {'run_id', 'target', 'argv', 'before', 'recovery', 'verify_argv'}
    if set(request) != required:
        raise ValueError('Request requires run_id, target, argv, before, recovery, verify_argv')
    if status['status'] != 'running' or request['run_id'] != status['run_id']:
        raise ValueError('Operation is not owned by the active run')
    if settings['stage'] != 'maintenance-v2' or request['target'] not in settings['update_targets']:
        raise ValueError('Target is outside the approved maintenance scope')
    if now >= status['started'] + settings['agent_timeout_seconds']:
        raise ValueError('Admission budget exhausted; no new mutations')
    for key in ('argv', 'verify_argv'):
        if not isinstance(request[key], list) or not request[key] or not all(isinstance(v, str) for v in request[key]):
            raise ValueError('Commands must be nonempty argv arrays')
    for key in ('before', 'recovery'):
        if not isinstance(request[key], str) or not request[key].strip():
            raise ValueError('Before-state and recovery limits are required')
    if bot.SECRET.search(json.dumps(request)):
        raise ValueError('Credential-shaped command rejected')
    if request['target'] == 'herdr-archon' and request['argv'] != ['systemctl', 'start', 'update-bot-herdr-archon.service']:
        raise ValueError('Archon Herdr changes must use the fixed remote helper')
    if request['target'] == 'os' and request['argv'] != ['systemctl', 'start', 'update-bot-os.service']:
        raise ValueError('OS changes must use the fixed root helper')


def run(request):
    with (bot.STATE / 'operation.lock').open('a') as admission:
        fcntl.flock(admission, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return execute(request)


def execute(request):
    status = bot.read_json(bot.STATE / 'latest.json')
    settings = bot.read_json(bot.CONFIG / 'settings.json')
    validate(request, status, settings, time.time())
    # Any abandoned intent must be inspected and explicitly reconciled first.
    for intent in (bot.STATE / 'runs').glob('*/operations/*/intent.json'):
        if not (intent.parent / 'result.json').exists() and not (intent.parent / 'reconciled.json').exists():
            raise RuntimeError('Unresolved previous operation: ' + str(intent.parent))
        if (intent.parent / 'outcome-request.json').exists() and not (intent.parent / 'outcome-receipt.json').exists():
            raise RuntimeError('Previous operation outcome needs recording reconciliation: ' + str(intent.parent))
    identifier = str(uuid.uuid4())
    folder = bot.STATE / 'runs' / status['run_id'] / 'operations' / identifier
    folder.mkdir(parents=True)
    with (folder / 'active.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        request.update(operation_id=identifier, started=time.time(), policy_sha256=status['policy_sha256'])
        bot.atomic_json(folder / 'intent.json', request)
        print('Operation evidence: ' + str(folder), flush=True)
        receipt = bot.cairn(['remember', '--repo', bot.COLLECTION, '--kind', 'observation',
                            '--shareable', '--request-id', identifier, '--stdin'],
                           input='infra proximal maintenance intent (authorized scope, not completion):\n' + json.dumps(request))
        bot.atomic_json(folder / 'intent-receipt.json', receipt)
        # Each native command has its own process group. Agent timeout may end the
        # model shell but cannot terminate a admitted package transaction.
        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            signal.signal(sig, lambda *_: None)
        result = {'operation_id': identifier, 'target': request['target'], 'started': request['started']}
        with (folder / 'install.log').open('w') as output:
            child = subprocess.Popen(request['argv'], stdout=output, stderr=subprocess.STDOUT,
                                     start_new_session=True, pass_fds=(lock.fileno(),))
            result['pid'] = child.pid
            bot.atomic_json(folder / 'process.json', result)
            result['exit_code'] = child.wait()
        result['verification_exit_code'] = None
        if result['exit_code'] == 0:
            with (folder / 'verify.log').open('w') as output:
                child = subprocess.Popen(request['verify_argv'], stdout=output, stderr=subprocess.STDOUT,
                                         start_new_session=True, pass_fds=(lock.fileno(),))
                result['verification_exit_code'] = child.wait()
        result['finished'] = time.time()
        result['status'] = 'verified' if result['exit_code'] == 0 and result['verification_exit_code'] == 0 else 'failed'
        if request['target'] == 'os' and result['status'] == 'verified':
            os_receipt = bot.read_json('/var/lib/update-bot-os/latest.json', {})
            if os_receipt.get('status') == 'completed':
                result['changed'] = bool(os_receipt.get('selected', []))
                result['native_evidence'] = os_receipt['evidence']
        if request['target'] == 'herdr-archon' and result['status'] == 'verified':
            native = bot.read_json(bot.STATE / 'herdr-archon-latest.json', {})
            if native.get('status') != 'verified' or native.get('started', 0) < result['started']:
                result['status'] = 'failed'
            else:
                bot.atomic_json(folder / 'native-result.json', native)
                result['changed'] = native['changed']
                result['native_evidence'] = str(folder / 'native-result.json')
        if (request['argv'] == ['systemctl', 'start', 'update-bot-hermes-activate.service']
                and result['status'] == 'verified'):
            native = bot.read_json(bot.STATE / 'hermes-activation-latest.json', {})
            if native.get('status') == 'verified' and native.get('started', 0) >= result['started']:
                bot.atomic_json(folder / 'native-result.json', native)
                result['changed'] = native['changed']
                result['native_evidence'] = str(folder / 'native-result.json')
        bot.atomic_json(folder / 'result.json', result)
        result_id = str(uuid.uuid4())
        bot.atomic_json(folder / 'outcome-request.json', {'request_id': result_id})
        receipt = bot.cairn(['remember', '--repo', bot.COLLECTION, '--kind', 'observation',
                            '--shareable', '--request-id', result_id, '--stdin'],
                           input='infra proximal maintenance outcome; evidence ' + str(folder) + '\n' + json.dumps(result))
        bot.atomic_json(folder / 'outcome-receipt.json', receipt)
        print(json.dumps(result), flush=True)
        return 0 if result['status'] == 'verified' else 1


if __name__ == '__main__':
    os.umask(0o077)
    if len(sys.argv) != 2:
        sys.exit('usage: operation.py REQUEST.json')
    sys.exit(run(json.loads(Path(sys.argv[1]).read_text())))
