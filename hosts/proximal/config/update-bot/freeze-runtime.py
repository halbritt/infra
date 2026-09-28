#!/usr/bin/env python3
"""Install a root-owned, independent copy of the current Hermes CLI runtime."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

source = Path('/home/halbritt/.hermes/hermes-agent')
revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
destination = Path('/opt/update-bot') / ('hermes-' + revision[:12])
if not destination.exists():
    destination.mkdir(parents=True)
    subprocess.run(['rsync', '-a', '--exclude=.git', '--exclude=node_modules',
                    '--exclude=__pycache__', str(source) + '/', str(destination) + '/'], check=True)
    # uv's editable finder and venv scripts embed the old checkout's absolute path.
    paths = list((destination / 'venv/bin').iterdir())
    paths += list((destination / 'venv/lib/python3.11/site-packages').glob('__editable__*'))
    paths += [destination / 'venv/pyvenv.cfg']
    for path in paths:
        if path.is_symlink() or not path.is_file():
            continue
        try:
            body = path.read_text()
        except UnicodeDecodeError:
            continue
        if str(source) in body:
            path.write_text(body.replace(str(source), str(destination)))
    subprocess.run(['chown', '-R', 'root:root', str(destination)], check=True)
    subprocess.run(['chmod', '-R', 'go-w', str(destination)], check=True)
check = subprocess.check_output([str(destination / 'venv/bin/python'), '-c',
                                'import run_agent; print(run_agent.__file__)'],
                               cwd=destination, text=True).strip()
if not check.startswith(str(destination) + '/'):
    sys.exit('Frozen runtime imported the live checkout')
manifest = {'source_revision': revision, 'path': str(destination), 'import_verified': check}
Path('/etc/update-bot/runtime.json').write_text(json.dumps(manifest, indent=2) + '\n')
wrapper = Path('/usr/local/lib/update-bot/hermes-frozen')
wrapper.write_text('#!/bin/sh\nunset PYTHONPATH PYTHONHOME\nexec "' + str(destination / 'venv/bin/python') +
                   '" "' + str(destination / 'hermes') + '" "$@"\n')
wrapper.chmod(0o755)
print(json.dumps(manifest))
