#!/usr/bin/env python3
"""Small execution/receipt boundary around the installed Hermes harness.

No maintenance commands or installation inventory live here. Host investigation
belongs to the agent; scheduling and descendant cleanup belong to systemd.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

CONFIG = Path('/etc/update-bot')
STATE = Path('/var/lib/update-bot')
HERMES = '/usr/local/lib/update-bot/hermes-frozen'
CAIRN = ['/home/halbritt/.local/bin/cairn', 'agent', '--token-file',
         '/home/halbritt/.local/share/cairn/hosted-agent.token']
COLLECTION = '/home/halbritt/git/cairn'
REPO = '/home/halbritt/git/infra'
SECRET = re.compile(r'(?:xox[baprs]-[A-Za-z0-9-]{12,}|sk-or-v1-[A-Za-z0-9]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)')


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp-' + str(uuid.uuid4()))
    with temporary.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def command(argv, *, input=None, timeout=40, env=None):
    return subprocess.run(argv, input=input, text=True, capture_output=True,
                          timeout=timeout, env=env)


def cairn(argv, *, input=None):
    result = command(CAIRN + argv, input=input)
    if result.returncode:
        raise RuntimeError('Cairn command failed; consult private runner evidence')
    response = json.loads(result.stdout)
    if not response.get('ok'):
        raise RuntimeError('Cairn refused the request')
    return response


def credential(name):
    return (Path(os.environ['CREDENTIALS_DIRECTORY']) / name).read_text().strip()


def validate_report(raw, usage):
    # Fail closed on an interrupted tool loop even if it emitted a plausible answer.
    if usage.get('failed') or usage.get('completed') is not True:
        raise ValueError('Hermes did not report a completed conversation')
    # Tolerate a short presentation preamble/fence, while requiring one complete
    # object and no trailing content. Do not reject useful evidence for typography.
    start = raw.find('{')
    if start < 0 or start > 256:
        raise ValueError('Missing report object')
    value, end = json.JSONDecoder().raw_decode(raw[start:])
    if raw[start + end:].strip() not in ('', '```'):
        raise ValueError('Unexpected trailing report content')
    fields = {'status', 'summary', 'checked', 'deferred', 'unchecked', 'notification'}
    if not isinstance(value, dict) or set(value) not in (fields, fields | {'changes'}):
        raise ValueError('Invalid report fields')
    if value['status'] not in ('completed', 'partial'):
        raise ValueError('Invalid report status')
    for key, limit in [('summary', 4000), ('notification', 3000)]:
        if not isinstance(value[key], str) or len(value[key]) > limit:
            raise ValueError('Invalid report text: ' + key)
    for key, fields in [('checked', {'target', 'evidence', 'outcome'}),
                        ('deferred', {'target', 'reason', 'proposed_action', 'verification', 'recovery'})]:
        if not isinstance(value[key], list):
            raise ValueError('Invalid report list: ' + key)
        for item in value[key]:
            if not isinstance(item, dict) or set(item) != fields or not all(isinstance(v, str) for v in item.values()):
                raise ValueError('Invalid report item: ' + key)
    if not isinstance(value['unchecked'], list) or not all(isinstance(x, str) for x in value['unchecked']):
        raise ValueError('Invalid unchecked coverage')
    if not value['checked']:
        raise ValueError('A completed investigation needs observation evidence')
    change_fields = {'target', 'operation_id', 'before', 'after', 'status', 'verification', 'activation'}
    if not isinstance(value.get('changes', []), list):
        raise ValueError('Invalid maintenance changes list')
    for change in value.get('changes', []):
        if not isinstance(change, dict) or set(change) != change_fields or not all(isinstance(v, str) for v in change.values()):
            raise ValueError('Invalid maintenance change receipt')
        uuid.UUID(change['operation_id'])
    if len(raw) > 30000 or SECRET.search(raw):
        raise ValueError('Report too large or contains a credential-shaped value')
    return value


def record_status(run_dir, status):
    atomic_json(run_dir / 'status.json', status)
    atomic_json(STATE / 'latest.json', status)


def operations_active(run_dir):
    for intent in (run_dir / 'operations').glob('*/intent.json'):
        request = read_json(intent, {})
        units = ('update-bot-os.service', 'update-bot-hermes-activate.service')
        unit = next((u for u in units if request.get('argv') == ['systemctl', 'start', u]), None)
        if unit:
            service = command(['systemctl', 'show', unit, '--property=ActiveState', '--value'])
            if service.stdout.strip() in ('active', 'activating', 'deactivating'):
                return True
    for path in (run_dir / 'operations').glob('*/active.lock'):
        with path.open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
    return False


def drain_operations(run_dir):
    while operations_active(run_dir):
        time.sleep(1)


def finish_report(run_dir, status):
    usage = read_json(run_dir / 'usage.json', {})
    report = validate_report((run_dir / 'stdout.json').read_text(), usage)
    for change in report.get('changes', []):
        folder = run_dir / 'operations' / change['operation_id']
        intent = read_json(folder / 'intent.json', {})
        result = read_json(folder / 'result.json', {})
        if intent.get('target') != change['target']:
            raise ValueError('Reported change lacks a matching operation intent')
        if change['status'] == 'verified' and result.get('status') != 'verified':
            raise ValueError('Reported verification disagrees with native receipt')
    atomic_json(run_dir / 'report.json', report)
    status['usage'] = usage
    status['summary'] = report['summary']
    request_id = status.setdefault('checkpoint_request_id', str(uuid.uuid4()))
    checkpoint_path = run_dir / 'checkpoint.txt'
    if checkpoint_path.exists():
        checkpoint = checkpoint_path.read_text()
    else:
        checkpoint = ('Project infra; host proximal; role update-bot; ' + status['stage'] + ' checkpoint.\n' +
                      'Run ' + status['run_id'] + '; policy ' + status['policy_sha256'] +
                      '; provider/model ' + status['provider'] + '/' + status['model'] +
                      '; evidence ' + str(run_dir) + '. Changes and activation follow the recorded operation receipts.\n' +
                      json.dumps(report, ensure_ascii=False))
        checkpoint_path.write_text(checkpoint)
    record_status(run_dir, status)
    receipt = cairn(['remember', '--repo', COLLECTION, '--request-id', request_id,
                    '--kind', 'observation', '--shareable', '--stdin'], input=checkpoint)
    atomic_json(run_dir / 'checkpoint-receipt.json', receipt)
    status.update(status=report['status'], recording='recorded', finished=time.time())
    record_status(run_dir, status)
    if report['status'] == 'completed':
        atomic_json(STATE / 'last-completed.json', status)
    print('Maintenance ' + status['status'] + '; Cairn checkpoint recorded; run ' + status['run_id'], flush=True)
    return 0 if report['status'] == 'completed' else 2


def reconcile(run_id):
    """Explicit operator record-only retry; never invokes inference or host tools."""
    run_id = str(uuid.UUID(run_id))
    with (STATE / 'host.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if read_json(STATE / 'latest.json', {}).get('run_id') != run_id:
            raise ValueError('Only the latest run can be explicitly finalized')
        run_dir = STATE / 'runs' / run_id
        status = read_json(run_dir / 'status.json')
        if status.get('recording') == 'recorded':
            return 0
        atomic_json(run_dir / 'before-reconciliation.json', status)
        status['record_only_reconciled_at'] = time.time()
        if 'error' in status:
            status['prior_error'] = status.pop('error')
        return finish_report(run_dir, status)


def run():
    if not os.environ.get('INVOCATION_ID'):
        raise RuntimeError('Launch via sudo systemctl start update-bot.service')
    settings = read_json(CONFIG / 'settings.json')
    if settings['stage'] not in ('discovery-v1', 'maintenance-v2'):
        raise RuntimeError('Unknown maintenance policy stage')
    STATE.mkdir(mode=0o700, exist_ok=True)
    with (STATE / 'host.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Skipped duplicate: host maintenance lock is held', flush=True)
            return 0
        previous = read_json(STATE / 'latest.json', {})
        run_id = str(uuid.uuid4())
        run_dir = STATE / 'runs' / run_id
        run_dir.mkdir(parents=True, mode=0o700)
        policy = (CONFIG / 'policy.md').read_text()
        hermes_source = read_json(STATE / 'hermes-installed.json', {}).get(
            'source', '/home/halbritt/.hermes/hermes-agent')
        status = {'run_id': run_id, 'host': settings['host'], 'stage': settings['stage'],
                  'started': time.time(), 'status': 'running', 'recording': 'pending',
                  'policy_sha256': hashlib.sha256(policy.encode()).hexdigest(),
                  'role_sha256': hashlib.sha256((CONFIG / 'role.md').read_bytes()).hexdigest(),
                  'profile_sha256': hashlib.sha256((CONFIG / 'hermes.yaml').read_bytes()).hexdigest(),
                  'launcher_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'infra_revision': command(['git', '-C', REPO, 'rev-parse', 'HEAD']).stdout.strip(),
                  'hermes_source': hermes_source,
                  'hermes_revision': command(['git', '-C', hermes_source,
                                              'rev-parse', 'HEAD']).stdout.strip(),
                  'runtime': read_json(CONFIG / 'runtime.json', {}),
                  'provider': settings['provider'], 'model': settings['model'],
                  'evidence': str(run_dir), 'host_mutations_authorized': settings['stage'] == 'maintenance-v2',
                  'previous_run': previous.get('run_id'),
                  'previous_status': previous.get('status'),
                  'invocation_id': os.environ['INVOCATION_ID']}
        if previous.get('status') == 'running':
            status['reconciliation'] = 'Previous run interrupted; inspect operation intents/processes/results before new mutations; never replay blindly'
        record_status(run_dir, status)
        if not (STATE / 'first-started.json').exists():
            atomic_json(STATE / 'first-started.json', {'started': status['started']})
        print('Started maintenance run ' + run_id, flush=True)
        try:
            for request in (STATE / 'runs').glob('*/operations/*/outcome-request.json'):
                folder = request.parent
                if (folder / 'outcome-receipt.json').exists():
                    continue
                result = read_json(folder / 'result.json')
                receipt = cairn(['remember', '--repo', COLLECTION, '--kind', 'observation',
                                 '--shareable', '--request-id', read_json(request)['request_id'], '--stdin'],
                                input='infra proximal maintenance outcome; evidence ' + str(folder) + '\n' + json.dumps(result))
                atomic_json(folder / 'outcome-receipt.json', receipt)
            if previous.get('checkpoint_request_id') and previous.get('recording') != 'recorded':
                old_dir = STATE / 'runs' / str(uuid.UUID(previous['run_id']))
                checkpoint = (old_dir / 'checkpoint.txt').read_text()
                receipt = cairn(['remember', '--repo', COLLECTION,
                                '--request-id', previous['checkpoint_request_id'],
                                '--kind', 'observation', '--shareable', '--stdin'], input=checkpoint)
                atomic_json(old_dir / 'checkpoint-receipt.json', receipt)
                previous.update(recording='recorded', recording_reconciled_at=time.time())
                atomic_json(old_dir / 'status.json', previous)
                status['reconciled_checkpoint'] = previous['run_id']
                record_status(run_dir, status)
            recalled = cairn(['search', '--repo', COLLECTION, '--task', 'proximal/update-bot',
                             '--run', run_id, 'proximal update-bot checkpoint'])
            atomic_json(run_dir / 'recall.json', recalled)
            profile = STATE / 'hermes'
            profile.mkdir(exist_ok=True)
            config_link = profile / 'config.yaml'
            if config_link.is_symlink() or config_link.exists():
                config_link.unlink()
            config_link.symlink_to(CONFIG / 'hermes.yaml')
            env = os.environ.copy()
            env.update(HERMES_HOME=str(profile), UPDATE_BOT_RUN_ID=run_id,
                       OPENROUTER_API_KEY=credential('openrouter'),
                       PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
                       XDG_CACHE_HOME=str(STATE / 'cache'))
            for key in ('CUSTOM_BASE_URL', 'OPENROUTER_BASE_URL', 'HERMES_INFERENCE_MODEL',
                        'DBUS_SESSION_BUS_ADDRESS', 'SSH_AUTH_SOCK'):
                env.pop(key, None)
            prompt = ((CONFIG / 'role.md').read_text() + '\n\n' + policy +
                      '\n\nRun ID: ' + run_id + '\nPrevious receipt: ' + json.dumps(previous) +
                      '\nStarted UTC: ' + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) +
                      '\nRuntime saves the final Cairn checkpoint; return the required JSON.')
            if (STATE / 'commissioning').exists():
                prompt += ('\nDeployment commissioning is in progress. Disabled update-bot timers and '
                           'failed update-bot-probe units are expected acceptance work, not host incidents. '
                           'The owner already authorized enabling these timers after verification; '
                           'do not request that authorization or notify about commissioning artifacts.')
            args = [HERMES, '--provider', settings['provider'], '--model', settings['model'],
                    '--toolsets', 'terminal,file,cairn', '--usage-file', str(run_dir / 'usage.json'),
                    '--in', REPO, '-z', prompt]
            interrupted = []
            old_term = signal.signal(signal.SIGTERM, lambda *_: interrupted.append(True))
            with (run_dir / 'stdout.json').open('w') as out, (run_dir / 'stderr.log').open('w') as err:
                process = subprocess.Popen(args, stdout=out, stderr=err, env=env,
                                           start_new_session=True, pass_fds=(lock.fileno(),))
                deadline = status['started'] + settings['agent_timeout_seconds']
                while process.poll() is None and time.time() < deadline and not interrupted:
                    time.sleep(0.25)
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    status['draining'] = True
                    record_status(run_dir, status)
                    drain_operations(run_dir)
                    signal.signal(signal.SIGTERM, old_term)
                    raise RuntimeError('Agent stopped; admitted native transactions drained, inspect receipts before retry')
                code = process.returncode
                drain_operations(run_dir)
                signal.signal(signal.SIGTERM, old_term)
            if code:
                raise RuntimeError('Hermes failed with exit status ' + str(code))
            raw = (run_dir / 'stdout.json').read_text()
            if env['OPENROUTER_API_KEY'] in raw:
                raise ValueError('Report contains the provider credential')
            return finish_report(run_dir, status)
        except Exception as exc:
            status.update(status='failed', error=str(exc), finished=time.time())
            record_status(run_dir, status)
            print('Maintenance failed: ' + str(exc), file=sys.stderr, flush=True)
            return 1


def report_line(text, limit):
    """Collapse a reported field to one clipped, scannable notification line."""
    compact = ' '.join(str(text).split())
    if len(compact) <= limit:
        return compact
    cut = compact[:limit]
    for separator in ('. ', '; ', ', '):
        index = cut.rfind(separator)
        if index >= limit // 2:
            return cut[:index + len(separator)].rstrip() + ' …'
    return cut.rstrip() + ' …'


def report_count(number, singular, plural=None):
    return str(number) + ' ' + (singular if number == 1 else (plural or singular + 's'))


# The rendered body must fit one Slack message with room for the header/footer
# that the monitor appends.
SLACK_BUDGET = 3800


def report_blocks(report):
    """Build the notification's display blocks, most consequential first."""
    changes, deferred, unchecked = report.get('changes', []), report.get('deferred', []), report.get('unchecked', [])
    blocks = []
    if changes:
        lines = []
        for change in changes:
            lines.append('• *' + change['target'] + '* — ' + change['status'] + ': ' +
                         report_line(change['before'], 70) + '  →  ' + report_line(change['after'], 160))
            lines.append('    activation: ' + report_line(change['activation'], 150))
        blocks.append(('*Update results*', lines))
    if deferred:
        lines = []
        for item in deferred:
            lines.append('• *' + item['target'] + '* — ' + report_line(item['reason'], 170))
            lines.append('    next: ' + report_line(item['proposed_action'], 160))
        blocks.append(('*Waiting for follow-up*', lines))
    if unchecked:
        blocks.append(('*Not checked this time*', ['• ' + report_line(item, 150) for item in unchecked]))
    accounted = {item['target'] for item in changes} | {item['target'] for item in deferred}
    quiet = ['• *' + item['target'] + '* — ' + report_line(item['outcome'], 120)
             for item in report.get('checked', []) if item['target'] not in accounted]
    if quiet:
        blocks.append(('*Other checks*', quiet))
    return blocks


def report_message(latest, report):
    """Use the agent's reader-facing brief, retaining a receipt-based fallback."""
    minutes = max(0, int((latest.get('finished', 0) - latest.get('started', 0)) // 60))
    status = latest.get('status', 'unknown')
    label = {'completed': 'finished', 'partial': 'finished with issues',
             'failed': 'failed', 'running': 'interrupted'}.get(status, status)
    header = '*Proximal maintenance — ' + label + '* · ' + str(minutes) + ' min'
    # These facts survive even if the brief forgets a failure or coverage limit.
    issues = []
    failed = list(dict.fromkeys(x['target'] for x in report.get('changes', [])
                               if x['status'] in ('failed', 'rolled_back')))
    if failed:
        issues.append('Failed or rolled back: ' + report_line(', '.join(failed), 180))
    if report.get('deferred'):
        issues.append(report_count(len(report['deferred']), 'item waiting for follow-up',
                                   'items waiting for follow-up'))
    if report.get('unchecked'):
        issues.append(report_count(len(report['unchecked']), 'area not checked', 'areas not checked'))
    if issues:
        header += '\n' + ' · '.join(issues)
    brief = report.get('notification', '').strip()
    if brief and len(header) + len(brief) + 3 <= SLACK_BUDGET:
        return header + '\n\n' + brief + '\n'
    blocks = report_blocks(report)
    lines = [header, '']
    budget = SLACK_BUDGET - len(header) - 81
    omitted = 0
    for title, block in blocks:
        kept = []
        cost = len(title) + 1
        for line in block:
            if cost + len(line) + 1 > budget:
                break
            kept.append(line)
            cost += len(line) + 1
        omitted += len(block) - len(kept)
        if kept:
            lines.extend([title] + kept + [''])
            budget -= cost + 1
    if omitted:
        lines.append('… ' + str(omitted) + ' more detail lines in the full report')
    return '\n'.join(lines).strip() + '\n'


def run_message(latest):
    """Prefer the structured renderer; fall back to prose when no report exists."""
    report = read_json(Path(latest.get('evidence') or '.') / 'report.json', {})
    if isinstance(report, dict) and report.get('checked'):
        return report_message(latest, report)
    return ('Maintenance ' +
            ('interrupted' if latest.get('status') == 'running' else str(latest.get('status', 'unknown'))) +
            ': ' + latest.get('error', latest.get('summary', 'Inspect the run evidence.')))


def monitor_messages(latest, completed, service, settings, now):
    messages = []
    age = now - (completed or {}).get('finished', (latest or {}).get('started', 0))
    if age > settings['overdue_seconds']:
        messages.append(('overdue', 'No completed maintenance run in the last 30 hours.'))
    active = service.get('ActiveState') in ('active', 'activating', 'deactivating')
    if latest and active and now - latest.get('started', now) > 1800:
        messages.append(('draining:' + latest['run_id'], 'Maintenance has exceeded 30 minutes; inspect admitted native transactions. Do not kill a package manager blindly.'))
    if latest and (latest.get('status') in ('failed', 'partial') or
                   (latest.get('status') == 'running' and not active)):
        messages.append(('run:' + latest['run_id'], run_message(latest)))
    elif not active and service.get('Result', 'success') != 'success':
        messages.append(('service:' + service.get('InvocationID', ''),
                         'Maintenance service failed: ' + service.get('Result', 'unknown')))
    elif latest and latest.get('status') == 'completed' and latest.get('recording') == 'recorded':
        report = read_json(Path(latest['evidence']) / 'report.json', {})
        if report.get('changes') or report.get('deferred') or report.get('notification'):
            messages.append(('run:' + latest['run_id'], report_message(latest, report)))
    return messages


def slack_message(message, latest, publication):
    """Keep technical provenance in one compact, useful footer."""
    if publication.get('status') == 'pushed':
        details = '<https://github.com/halbritt/infra/commit/' + publication['commit'] + '|Full report>'
    else:
        details = 'Details on proximal: ' + latest.get('evidence', str(STATE))
    footer = '\n\n' + details + ' · Run ' + latest.get('run_id', 'none')[:8]
    room = 4000 - len(footer)
    if len(message) > room:
        message = message[:room - 2].rstrip() + '…'
    return message.rstrip() + footer


def monitor():
    STATE.mkdir(mode=0o700, exist_ok=True)
    with (STATE / 'monitor.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        settings = read_json(CONFIG / 'settings.json')
        publication_error = None
        if settings['stage'] == 'maintenance-v2':
            try:
                import publish
                publish.publish()
            except Exception as exc:
                publication_error = str(exc)
                print('Publication pending: ' + publication_error, file=sys.stderr)
        latest = read_json(STATE / 'latest.json', {})
        completed = read_json(STATE / 'last-completed.json', {})
        if not completed:
            completed = {'finished': read_json(STATE / 'first-started.json', {}).get('started', 0)}
        result = command(['systemctl', 'show', 'update-bot.service',
                          '--property=ActiveState,Result,InvocationID'])
        if result.returncode:
            raise RuntimeError('Cannot inspect maintenance service status')
        service = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        messages = monitor_messages(latest, completed, service, settings, time.time())
        if publication_error:
            messages.append(('publication:' + latest.get('run_id', 'none'),
                             'Maintenance Git publication is pending; host operations will not be repeated. ' + publication_error))
        delivered = read_json(STATE / 'delivery.json', {})
        uncertain = any(item.get('status') == 'sending-uncertain' for item in delivered.values())
        env = os.environ.copy()
        profile = STATE / 'delivery-hermes'
        profile.mkdir(exist_ok=True)
        env.update(HERMES_HOME=str(profile), SLACK_BOT_TOKEN=credential('slack'))
        for key, message in messages:
            old = delivered.get(key, {})
            if old.get('status') == 'sending-uncertain':
                print('Delivery uncertain; manual reconciliation required: ' + key, file=sys.stderr)
                continue
            if time.time() - old.get('at', 0) < settings['reminder_seconds']:
                continue
            # Persist before network I/O. A crash/timeout is ambiguous; do not blindly resend.
            delivered[key] = {'status': 'sending-uncertain', 'at': time.time()}
            atomic_json(STATE / 'delivery.json', delivered)
            publication = read_json(Path(latest.get('evidence', str(STATE))) / 'publication.json', {})
            message = slack_message(message, latest, publication)
            result = command([HERMES, 'send', '--to', settings['slack_target'], '--json'],
                             input=message, env=env, timeout=60)
            if result.returncode:
                # Backend failures may have followed a successful send; retain uncertainty.
                print('Slack delivery failed/uncertain; inspect delivery state', file=sys.stderr)
                return 1
            receipt = json.loads(result.stdout)
            if receipt.get('success') is not True:
                print('Slack rejected delivery', file=sys.stderr)
                return 1
            delivered[key] = {'status': 'sent', 'at': time.time(), 'receipt': receipt}
            atomic_json(STATE / 'delivery.json', delivered)
            print('Delivered ' + key, flush=True)
        if uncertain or publication_error:
            print('Prior delivery uncertainty still requires reconciliation', file=sys.stderr)
            return 1
        return 0


if __name__ == '__main__':
    os.umask(0o077)
    if len(sys.argv) == 3 and sys.argv[1] == 'reconcile':
        sys.exit(reconcile(sys.argv[2]))
    if len(sys.argv) != 2 or sys.argv[1] not in ('run', 'monitor'):
        sys.exit('usage: update_bot.py run|monitor|reconcile RUN_UUID')
    sys.exit(run() if sys.argv[1] == 'run' else monitor())
