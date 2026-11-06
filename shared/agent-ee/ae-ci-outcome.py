#!/usr/bin/env python3
"""Journal whether ae-ci-exec reached its requested Docker command; never infer from exit alone."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import uuid

SCHEMA = 'agent-ee.exec-outcome/1'


def now():
    return datetime.now(timezone.utc).isoformat()


def write_record(path, record):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(record, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, path)


def mark_started(path):
    record = json.loads(path.read_text())
    if (record.get('schema') != SCHEMA or record.get('token') != os.environ.get('AE_CI_OUTCOME_TOKEN')
            or record.get('state') != 'preparing' or record.get('complete') is not False):
        raise ValueError('execution outcome is not this live preparing attempt')
    record.update(state='started_or_uncertain', command_boundary_at=now())
    write_record(path, record)


def confined_record(path, forbidden_paths):
    if not path.is_absolute():
        raise ValueError('AE_CI_OUTCOME_FILE must be absolute')
    if path.is_symlink():
        raise ValueError('AE_CI_OUTCOME_FILE must not select an existing symlink')
    try:
        resolved = path.resolve()
        for root in forbidden_paths:
            if not root.is_absolute():
                raise ValueError('writable runtime paths must be absolute')
            root = root.resolve()
            if resolved.is_relative_to(root) or root.is_relative_to(resolved):
                raise ValueError(f'AE_CI_OUTCOME_FILE must stay outside writable runtime paths: {root}')
    except RuntimeError as exc:
        raise ValueError('AE_CI_OUTCOME_FILE cannot resolve safely') from exc
    return resolved


def supervise(path, runner, command, forbidden_paths=()):
    path = confined_record(path, forbidden_paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    token = str(uuid.uuid4())
    record = {'schema': SCHEMA, 'attempt_id': token, 'token': token, 'complete': False,
              'state': 'preparing', 'created_at': now(),
              'runner_sha256': hashlib.sha256(runner.read_bytes()).hexdigest(),
              'supervisor_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'command_sha256': hashlib.sha256(json.dumps(command).encode()).hexdigest()}
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'w') as stream:
        json.dump(record, stream)
        stream.flush()
        os.fsync(stream.fileno())
    child = None
    interrupted = None

    def interrupt(signum, _frame):
        nonlocal interrupted
        interrupted = signum
        if child is not None:
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass

    previous = {s: signal.signal(s, interrupt) for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    try:
        if interrupted is not None:
            status = 128 + interrupted
        else:
            try:
                child = subprocess.Popen(command, env={**os.environ, 'AE_CI_OUTCOME_FILE': str(path),
                                                       'AE_CI_OUTCOME_TOKEN': token}, start_new_session=True)
                if interrupted is not None:
                    interrupt(interrupted, None)
                status = child.wait()
                if status < 0:
                    status = 128 - status
            except OSError as exc:
                status = 127
                record['launch_error'] = str(exc)
        try:
            observed = json.loads(path.read_text())
            if observed.get('schema') != SCHEMA or observed.get('token') != token:
                raise ValueError('execution outcome changed identity during the attempt')
            if observed['state'] not in ('preparing', 'started_or_uncertain') or observed['complete'] is not False:
                raise ValueError('execution outcome has an unexpected transition')
        except (OSError, ValueError, KeyError) as exc:
            record.update(state='uncertain', complete=False, exit_code=status, error=str(exc), finished_at=now())
            write_record(path, record)
            raise ValueError('execution outcome is uncertain; no retry clearance') from exc
        observed.update(exit_code=status, finished_at=now())
        if interrupted is None:
            observed.update(complete=True, state='not_started' if observed['state'] == 'preparing'
                            else 'started_or_uncertain')
        else:
            observed.update(complete=False, state='interrupted', signal=interrupted)
        if 'launch_error' in record:
            observed['launch_error'] = record['launch_error']
        write_record(path, observed)
        return status
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='operation', required=True)
    run = subs.add_parser('run')
    run.add_argument('--record', type=Path, required=True)
    run.add_argument('--runner', type=Path, required=True)
    run.add_argument('--forbid-path', type=Path, action='append', default=[])
    run.add_argument('command', nargs=argparse.REMAINDER)
    mark = subs.add_parser('mark-started')
    mark.add_argument('record', type=Path)
    args = parser.parse_args()
    try:
        if args.operation == 'mark-started':
            mark_started(args.record)
            return 0
        command = args.command[1:] if args.command and args.command[0] == '--' else args.command
        if not command:
            raise ValueError('supervised command is empty')
        return supervise(args.record, args.runner, command, args.forbid_path)
    except (OSError, ValueError) as exc:
        print(f'ae-ci-exec: execution outcome refused: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
