#!/usr/bin/env python3
"""Publish maintenance receipts from an isolated worktree, independently of retries."""
import fcntl
import json
from pathlib import Path
import subprocess
import time

import update_bot as bot


def git(*args, cwd=bot.REPO):
    result = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Git publication failed: ' + result.stderr[-1000:])
    return result.stdout.strip()


def entry(folder, status):
    report = bot.read_json(folder / 'report.json', {})
    lines = ['## ' + time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(status['started'])) +
             ' — ' + status['run_id'], '',
             'Host: proximal. Policy: ' + status['stage'] + '. Run status: ' + status['status'] + '.', '']
    changes = {x['operation_id']: x for x in report.get('changes', [])}
    for path in sorted((folder / 'operations').glob('*/intent.json')):
        intent = bot.read_json(path)
        result = bot.read_json(path.parent / 'result.json', {})
        if result.get('changed') is False:
            continue
        change = changes.get(path.parent.name, {})
        lines.extend(['- **' + intent['target'] + '** — ' + result.get('status', 'interrupted/uncertain') +
                      '. Before: ' + intent['before'] + '. After: ' + change.get('after', 'see operation receipt') + '.',
                      '  Verification: ' + change.get('verification', 'native verification exit ' + str(result.get('verification_exit_code'))) + '.',
                      '  Activation: ' + change.get('activation', 'not established by this receipt') + '.',
                      '  Evidence: `' + str(path.parent) + '`.', ''])
    return '\n'.join(lines) + '\n'


def publish():
    with (bot.STATE / 'publication.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for status_file in sorted((bot.STATE / 'runs').glob('*/status.json')):
            folder = status_file.parent
            status = bot.read_json(status_file)
            if status.get('stage') != 'maintenance-v2' or status.get('status') == 'running':
                continue
            if not list((folder / 'operations').glob('*/intent.json')):
                continue
            if bot.read_json(folder / 'publication.json', {}).get('status') in ('pushed', 'noop'):
                continue
            if bot.operations_active(folder):
                continue
            if all(bot.read_json(p.parent / 'result.json', {}).get('changed') is False
                   for p in (folder / 'operations').glob('*/intent.json')):
                bot.atomic_json(folder / 'publication.json', {'status': 'noop'})
                continue
            git('fetch', 'origin', 'master')
            relative = 'hosts/proximal/config/update-bot/CHANGELOG.md'
            # Recover a push whose success receipt was lost, without a duplicate entry.
            existing = subprocess.run(['git', '-C', bot.REPO, 'show', 'origin/master:' + relative],
                                      capture_output=True, text=True)
            worktree = Path('/home/halbritt/git/infra-wt') / ('update-bot-publish-' + status['run_id'])
            if status['run_id'] in existing.stdout:
                if worktree.exists() and not git('status', '--porcelain', cwd=worktree):
                    git('worktree', 'remove', str(worktree))
                if git('branch', '--show-current') == 'master' and not git('status', '--porcelain'):
                    git('merge', '--ff-only', 'origin/master')
                bot.atomic_json(folder / 'publication.json', {'status': 'pushed', 'commit': git('rev-parse', 'origin/master'), 'reconciled': True})
                continue
            if worktree.exists():
                receipt = bot.read_json(folder / 'publication.json', {})
                if receipt.get('commit') != git('rev-parse', 'HEAD', cwd=worktree) or git('status', '--porcelain', cwd=worktree):
                    raise RuntimeError('Publication worktree has unaccounted changes: ' + str(worktree))
                # This detached, clean checkout is owned by this exact receipt.
                # Regenerate the entry on the latest target after a push race.
                git('reset', '--hard', 'origin/master', cwd=worktree)
            else:
                git('worktree', 'add', '--detach', str(worktree), 'origin/master')
            pushed = False
            committed = False
            try:
                file = worktree / relative
                old = file.read_text() if file.exists() else '# Maintenance outcomes — proximal\n\n'
                heading, _, remainder = old.partition('\n\n')
                file.write_text(heading + '\n\n' + entry(folder, status) + remainder)
                for argv in (['python3', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py'],
                             ['scripts/validate-infra.py']):
                    result = subprocess.run(argv, cwd=worktree, capture_output=True, text=True)
                    if result.returncode:
                        raise RuntimeError('Publication validation failed; private evidence retained')
                git('add', relative, cwd=worktree)
                git('commit', '-m', 'proximal: maintenance outcomes ' + status['run_id'], cwd=worktree)
                committed = True
                commit = git('rev-parse', 'HEAD', cwd=worktree)
                bot.atomic_json(folder / 'publication.json', {'status': 'committed', 'commit': commit})
                git('push', 'origin', 'HEAD:refs/heads/master', cwd=worktree)
                pushed = True
                bot.atomic_json(folder / 'publication.json', {'status': 'pushed', 'commit': commit})
                if git('branch', '--show-current') == 'master' and not git('status', '--porcelain'):
                    git('merge', '--ff-only', commit)
            finally:
                # A failed push retains a named artifact/ref for safe retry, not a
                # forced reset of someone else's checkout. Monitoring reports it.
                if pushed or not committed:
                    git('worktree', 'remove', '--force', str(worktree))


if __name__ == '__main__':
    publish()
