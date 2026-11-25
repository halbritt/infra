#!/usr/bin/env python3
"""Bounded native Codex turns and checkpoint-before-replacement on Talos."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import selectors
import subprocess
import time
import uuid

PERIOD = 48 * 3600
HANDOFF_LEAD = 30 * 60
TURN_LIMIT = 25 * 60


def write_json(path, value):
    temporary = path.with_suffix('.new')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    directory = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def next_action(state, now):
    if state.get('in_flight'):
        raise RuntimeError('Unreconciled prior turn; inspect its events/effects before recovery')
    phase = state['phase']
    if phase == 'blocked':
        return phase
    if phase == 'new':
        return 'bootstrap'
    if phase == 'registered':
        return 'announce'
    if phase == 'active':
        if now >= state['rotate_at'] - HANDOFF_LEAD:
            return 'handoff'
        return 'wait' if now < state.get('next_turn_at', 0) else 'work'
    if phase == 'ready':
        return 'wait' if now < state.get('next_turn_at', 0) else 'ready'
    if phase == 'handoff_saved':
        return 'rotate' if now >= state['rotate_at'] else 'wait'
    raise ValueError(f'Unknown supervisor phase: {phase}')


def checked_receipt(value, thread_id, generation):
    if value.get('thread_id') != thread_id or value.get('generation') != generation:
        raise ValueError('Handoff belongs to another conversation or generation')
    if value.get('quiescent') is not True or value.get('unresolved_effects') != []:
        raise ValueError('Handoff has unresolved effects; replacement withheld')
    record = str(uuid.UUID(value['handoff_record_id']))
    version = value['handoff_version']
    if type(version) is not int or version < 1:
        raise ValueError('Invalid handoff version')
    return {'record_id': record, 'version': version}


def check_saved_handoff(history, reference):
    versions = history.get('versions', [])
    if history.get('record_id') != reference['record_id'] or len(versions) != 1:
        raise ValueError('Handoff lookup returned a different source')
    version = versions[0]
    body = version.get('body')
    if (version.get('version') != reference['version'] or
            version.get('payload_available') is not True or not isinstance(body, str) or not body.strip()):
        raise ValueError('Saved handoff body is unavailable or empty')
    if hashlib.sha256(body.encode()).hexdigest() != version.get('body_sha256'):
        raise ValueError('Saved handoff body does not match its digest')


class Supervisor:
    def __init__(self, home):
        self.home = home
        self.config_dir = home / '.config/striatum/rceb-supervisor'
        self.directory = home / '.local/state/striatum/rceb-supervisor/rotation'
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        self.path = self.directory / 'state.json'
        self.config = json.loads((self.config_dir / 'rotation.json').read_text())
        self.state = json.loads(self.path.read_text()) if self.path.exists() else self.fresh()

    def fresh(self, handoff=None):
        return {'phase': 'new', 'generation': str(uuid.uuid4()),
                'registration_request': str(uuid.uuid4()), 'in_flight': None,
                'handoff': handoff or self.config['initial_handoff']}

    def save(self):
        write_json(self.path, self.state)

    def cairn(self, args, body=None, session=True):
        # The `agents` group parses its operation before connection flags;
        # `agent` memory/event commands accept connection flags before it.
        prefix = 2 if args[0] == 'agents' else 1
        command = [str(self.home / '.local/bin/cairn'), *args[:prefix],
                   '--token-file', str(self.home / '.local/share/cairn/hosted-agent.token')]
        if session:
            identity = self.state['identity']
            command += ['--agent-id', identity['agent_id'], '--execution-id', identity['execution_id']]
        command += args[prefix:]
        result = subprocess.run(command, input=body, text=True, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(f'Cairn {args[0]} failed ({result.returncode}): {result.stdout} {result.stderr}')
        envelope = json.loads(result.stdout)
        if not envelope.get('ok', True):
            raise RuntimeError(f'Cairn refused {args[0]}: {envelope.get("status")}')
        return envelope.get('data', envelope)

    def heartbeat(self):
        if 'identity' in self.state:
            self.cairn(['agents', 'heartbeat'])

    def prompt(self, mode):
        identity = self.state.get('identity')
        context = {
            'generation': self.state['generation'], 'thread_id': self.state.get('thread_id'),
            'identity': identity, 'root_inbox': self.config['root_inbox'],
            'handoff': self.state['handoff'], 'rotate_at': self.state.get('rotate_at'),
        }
        header = ('Launcher context (operational only; never graph truth):\n' + json.dumps(context) + '\n')
        if mode == 'bootstrap':
            return ('Read-only startup. Reply READY and finish this turn. Do not create a goal, '
                    'register an identity, start work, or change files. The launcher will register '
                    'this actual native conversation and supply its identity on your next turn.')
        rules = (self.config_dir / 'driving-agent.txt').read_text()
        if mode == 'ready':
            task = ('Read Cairn/events skills, inspect ONLY your own inbox using the supplied identity. '
                    'Handle the readiness nonce request, explicitly complete and send its causal reply. '
                    'Finish this turn; no compiler effects or substantive work until root activates you.')
        elif mode == 'work':
            task = ('Perform one bounded supervision pass, at most 15 minutes. Handle your own inbox; '
                    'advance the existing target within the assignment; report actual new blockers to root. '
                    'Finish the turn without a goal loop or long polling. The launcher schedules the next pass.')
        elif mode == 'handoff':
            task = ('Your 48-hour replacement is due. Stop initiating effects. Reconcile all owned effects '
                    'and finish owned Cairn deliveries. Use the handoff skill to update the same selected '
                    'Talos driving-role handoff in Cairn, preserving exact unresolved work, holds, '
                    'spent operations, pins and evidence. Do not mark RCEB complete. If any effect '
                    'is uncertain, report quiescent=false and list it. Otherwise quiescent=true and '
                    'unresolved_effects=[]. Return ONLY a JSON object with thread_id, generation, '
                    'quiescent, unresolved_effects, handoff_record_id, handoff_version. Use the '
                    'exact thread_id/generation above. The launcher validates the saved source '
                    'before retiring this conversation; do not start your successor yourself.')
        else:
            raise ValueError(mode)
        return header + rules + '\nCurrent turn:\n' + task

    def run_turn(self, mode):
        pending = self.state.get('pending_result')
        if pending:
            if pending['mode'] != mode:
                raise RuntimeError('Completed turn awaits a different phase transition')
            return (Path(pending['attempt']) / 'answer.txt').read_text()
        attempt = self.directory / self.state['generation'] / str(uuid.uuid4())
        attempt.parent.mkdir(exist_ok=True, mode=0o700)
        attempt.parent.chmod(0o700)
        attempt.mkdir(mode=0o700)
        self.state['in_flight'] = {'mode': mode, 'attempt': str(attempt), 'started_at': time.time()}
        self.save()  # A crash after this point must never silently replay an effect.
        command = [str(self.home / '.local/bin/codex'), 'exec']
        if mode != 'bootstrap':
            command += ['resume']
        command += ['--json', '--dangerously-bypass-approvals-and-sandbox',
                    '-c', 'model_provider="openai"', '-c', 'model_reasoning_effort="high"',
                    '-m', self.config['model'], '-o', str(attempt / 'answer.txt')]
        if mode != 'bootstrap':
            command += [self.state['thread_id']]
        command += ['-']
        environment = dict(os.environ, CODEX_HOME=self.config['codex_home'])
        environment['PATH'] = ':'.join(str(self.home / p) for p in
                                     ('.local/bin', '.npm-global/bin', '.local/go/bin')) + ':' + os.environ['PATH']
        completed = False
        with (attempt / 'stderr.log').open('w') as errors, (attempt / 'events.jsonl').open('wb') as events:
            child = subprocess.Popen(command, cwd=self.config['repo'], env=environment,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
            selector = selectors.DefaultSelector()
            selector.register(child.stdout, selectors.EVENT_READ)
            buffered = b''
            deadline = time.monotonic() + TURN_LIMIT
            heartbeat_at = 0
            try:
                child.stdin.write(self.prompt(mode).encode())
                child.stdin.close()
                while True:
                    now = time.monotonic()
                    if now >= deadline:
                        raise TimeoutError('Codex turn exceeded 25 minutes; effects require reconciliation')
                    if now >= heartbeat_at:
                        self.heartbeat()
                        heartbeat_at = now + 30
                    if not selector.select(min(5, deadline - now)):
                        continue
                    chunk = os.read(child.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    events.write(chunk)
                    events.flush()
                    buffered += chunk
                    while b'\n' in buffered:
                        line, buffered = buffered.split(b'\n', 1)
                        event = json.loads(line)
                        if event.get('type') == 'thread.started':
                            thread = str(uuid.UUID(event['thread_id']))
                            if mode != 'bootstrap' and thread != self.state['thread_id']:
                                raise RuntimeError('Resume selected a different conversation')
                            self.state['thread_id'] = thread
                            self.save()
                        if event.get('type') == 'turn.completed':
                            completed = True
                code = child.wait(timeout=10)
                if code or not completed or not self.state.get('thread_id'):
                    raise RuntimeError(f'Codex turn failed ({code}); inspect {attempt}; no automatic retry/fallback')
            finally:
                selector.close()
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                child.stdout.close()
        self.state['last_turn'] = self.state['in_flight']
        self.state['pending_result'] = self.state['in_flight']
        self.state['in_flight'] = None
        self.save()
        return (attempt / 'answer.txt').read_text()

    def register(self):
        identity = self.cairn([
            'agents', 'register', '--request-id', self.state['registration_request'],
            '--binding', 'striatum-rceb-codex-harm', '--native-session', self.state['thread_id'],
            '--harness', 'codex', '--model', self.config['model'], '--project', 'striatum-next',
            '--workspace', self.config['repo'], '--task', 'Talos RCEB driving agent; readiness only',
        ], session=False)
        self.state['identity'] = identity
        self.state['born_at'] = time.time()
        self.state['rotate_at'] = self.state['born_at'] + PERIOD
        self.state['phase'] = 'registered'
        self.save()
        write_json(self.config_dir / 'identity.json', {'data': identity})

    def notify_root(self, message, name):
        (self.directory / self.state['generation']).chmod(0o700)
        self.cairn(['agent', 'send', '--journal', str(self.directory / self.state['generation'] / name),
                    '--repo', str(self.home / 'git/cairn'), '--kind', 'request', '--shareable',
                    '--summary', 'Fresh Talos driving context awaits root readiness verification and activation.',
                    '--to', self.config['root_inbox'], '--stdin'], message)

    def announce_ready(self):
        self.notify_root(
            f'New Talos RCEB driving context {self.state["identity"]["display_name"]}, '
            f'inbox {self.state["identity"]["inbox"]}, generation {self.state["generation"]}. '
            f'Model {self.config["model"]}, CODEX_HOME {self.config["codex_home"]}. '
            'Bootstrap finished; no substantive work. Send a Cairn readiness nonce request, '
            'verify the causal response and exact execution identity, then activate this exact '
            'generation with striatum-rceb-supervisor.py activate --generation GENERATION on Talos. '
            'This continues the Principal-authorized 48-hour handoff/replacement cycle. '
            'No new approval is needed. Complete this request once the verified successor owns the work.',
            'ready-notice.json')
        self.state['phase'] = 'ready'
        self.finish_turn()
        print(json.dumps({'status': 'ready_for_handshake', 'identity': self.state['identity']}))

    def finish_turn(self):
        self.state.pop('pending_result', None)
        if 'failure' in self.state:
            self.state['last_failure'] = self.state.pop('failure')
        self.state['next_turn_at'] = time.time() + 120
        self.save()

    def tick(self):
        action = next_action(self.state, time.time())
        if action == 'blocked':
            print('BLOCKED: inspect state.json; never blind-retry a failed or uncertain turn')
            return
        self.heartbeat()
        if action == 'bootstrap':
            self.run_turn('bootstrap')
            self.register()
            self.announce_ready()
        elif action == 'announce':
            self.announce_ready()
        elif action in ('ready', 'work'):
            self.run_turn(action)
            self.finish_turn()
        elif action == 'handoff':
            answer = json.loads(self.run_turn('handoff'))
            reference = checked_receipt(answer, self.state['thread_id'], self.state['generation'])
            history = self.cairn(['agent', 'history'], json.dumps(reference), session=False)
            check_saved_handoff(history, reference)
            self.state['handoff'] = reference
            self.state['phase'] = 'handoff_saved'
            self.state.pop('pending_result', None)
            self.save()
        elif action == 'rotate':
            self.cairn(['agents', 'leave'])
            write_json(self.directory / self.state['generation'] / 'retired.json', self.state)
            self.state = self.fresh(self.state['handoff'])
            self.save()
            self.tick()
        else:
            print('Waiting for next bounded turn or replacement boundary')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['tick', 'status', 'activate'])
    parser.add_argument('--generation')
    args = parser.parse_args()
    supervisor = Supervisor(Path.home())
    with (supervisor.directory / 'lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'status':
            print(json.dumps(supervisor.state, indent=2))
        elif args.command == 'activate':
            if args.generation != supervisor.state['generation'] or supervisor.state['phase'] != 'ready':
                raise ValueError('Activation requires the exact ready generation and verified Cairn round trip')
            if supervisor.state.get('in_flight'):
                raise ValueError('Cannot activate during a turn')
            supervisor.state['phase'] = 'active'
            supervisor.save()
        else:
            try:
                supervisor.tick()
            except Exception as error:
                supervisor.state['phase'] = 'blocked'
                supervisor.state['failure'] = {'type': type(error).__name__, 'message': str(error), 'at': time.time()}
                supervisor.save()
                raise


if __name__ == '__main__':
    main()
