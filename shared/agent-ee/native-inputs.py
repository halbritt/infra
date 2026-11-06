#!/usr/bin/env python3
"""Prepare explicitly selected native inputs; emit Docker argv without shell evaluation."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


SCHEMA = 'agent-ee.native-inputs/1'
RESERVED_ENV = {'AGENT_EE_REQUIRE_TOOLCHAIN', 'AGENT_EE_RUN_INPUT_RECEIPT',
                'AGENT_EE_EVIDENCE_DIR', 'AGENT_EE_MODULE_ENV',
                'AGENT_EE_FOME_MC_CHECKOUT', 'AGENT_EE_J1_DRAWING',
                'AGENT_EE_KICAD_ROUTE_CHECKOUT', 'AGENT_EE_KICAD_HAPPY', 'AGENT_EE_RUST_PLANNER'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate native input manifest field: {key}')
        result[key] = value
    return result


def inventory(root):
    """Exact regular-file population; links and special entries are refused, never followed."""
    if root.is_symlink():
        raise ValueError(f'input is a symlink: {root}')
    if root.is_file():
        return {'.': digest(root)}
    if not root.is_dir():
        raise ValueError(f'input is absent or not a regular file/directory: {root}')
    result = {}
    pending = [root]
    while pending:
        directory = pending.pop()
        for path in sorted(directory.iterdir()):
            if path.is_symlink():
                raise ValueError(f'input contains a symlink: {path}')
            if path.is_dir():
                pending.append(path)
            elif path.is_file():
                result[path.relative_to(root).as_posix()] = digest(path)
            else:
                raise ValueError(f'input contains a special entry: {path}')
    return result


def check_files(root, expected):
    if not isinstance(expected, dict) or not expected or any(
            not isinstance(name, str) or not isinstance(sha, str)
            or not re.fullmatch('[0-9a-f]{64}', sha) for name, sha in expected.items()):
        raise ValueError(f'input needs a nonempty relative-file SHA-256 inventory: {root}')
    actual = inventory(root)
    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    changed = sorted(name for name in actual.keys() & expected.keys() if actual[name] != expected[name])
    if missing or extra or changed:
        raise ValueError(f'input inventory mismatch at {root}: missing={missing}, extra={extra}, changed={changed}')
    return actual


def mount_path(path):
    # Docker's --mount grammar uses commas; argv quoting cannot escape that grammar.
    if any(c in str(path) for c in (',', '\n', '\r', '\0')):
        raise ValueError(f'input path cannot contain commas or control characters: {path!s}')
    return str(path)


def git(root, *args):
    environment = {**os.environ, 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
                   'GIT_TERMINAL_PROMPT': '0'}
    try:
        result = subprocess.run(['git', '--no-optional-locks', '-c', 'core.hooksPath=/dev/null',
                                 '-C', str(root), *args], capture_output=True, text=True,
                                timeout=120, env=environment)
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f'Git input operation timed out at {root}: {args[0]}') from exc
    if result.returncode:
        raise ValueError(f'Git input operation failed at {root}: {args[0]}: {result.stderr.strip()}')
    return result.stdout.strip()


def checkout_identity(root):
    if not root.is_dir() or Path(git(root, 'rev-parse', '--show-toplevel')).resolve() != root.resolve():
        raise ValueError(f'verifier source must be a Git checkout root: {root}')
    commit = git(root, 'rev-parse', '--verify', 'HEAD^{commit}')
    if not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', commit):
        raise ValueError(f'verifier source has no commit to record: {root}')
    if git(root, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError(f'verifier checkout must be clean: {root}')
    return {'commit': commit, 'tree': git(root, 'rev-parse', 'HEAD^{tree}'), 'clean': True}


def bind_environment(item, bindings, known_modules=None, require_scope=False):
    variable = item['env']
    scopes = item.get('modules', ['*'])
    if (not isinstance(scopes, list) or not scopes or any(
            not isinstance(name, str) or (name != '*' and not re.fullmatch('test_[A-Za-z0-9_]+', name))
            for name in scopes) or len(set(scopes)) != len(scopes)
            or ('*' in scopes and ('modules' in item or require_scope))):
        raise ValueError('modules must be a nonempty list of distinct test module names')
    if known_modules is not None and set(scopes) - {'*'} - known_modules:
        raise ValueError(f'unknown input modules: {sorted(set(scopes) - {"*"} - known_modules)}')
    if (not isinstance(variable, str) or not re.fullmatch('AGENT_EE_[A-Z0-9_]+|PCBSCHEMAGEN_ROOT', variable)
            or variable in RESERVED_ENV):
        raise ValueError(f'invalid or reserved input environment variable: {variable!r}')
    previous = bindings.get(variable, set())
    if previous and ('*' in previous or '*' in scopes or previous.intersection(scopes)):
        raise ValueError(f'input environment variable has overlapping module selections: {variable}')
    bindings[variable] = previous | set(scopes)
    return scopes


def prepare(manifest, evidence_dir, args_file, image=None, runner=None, source=None):
    raw = manifest.read_bytes()
    document = json.loads(raw, object_pairs_hook=unique_object)
    if (not isinstance(document, dict) or document.get('schema') != SCHEMA
            or not {'schema', 'inputs'} <= set(document) <= {'schema', 'inputs', 'outputs'}):
        raise ValueError(f'expected {SCHEMA} with schema and inputs fields: {manifest}')
    inputs = document['inputs']
    if not isinstance(inputs, list) or not inputs:
        raise ValueError('native input manifest must list at least one input')
    source_identity = checkout_identity(source) if source else None
    if source and evidence_dir.resolve().is_relative_to(source.resolve()):
        raise ValueError('native input evidence must stay outside the agent-ee checkout')
    names, bindings, checked = set(), {}, []
    known_modules = {p.stem for p in (source / 'tests').glob('test_*.py')} if source else None
    for item in inputs:
        if not isinstance(item, dict) or set(item) - {'modules'} not in (
                {'name', 'env', 'path', 'files'}, {'name', 'env', 'path', 'git'}):
            raise ValueError('each native input needs name, env, path, and either files or git=true')
        name = item['name']
        if not isinstance(name, str) or not re.fullmatch('[a-z][a-z0-9-]{0,63}', name) or name in names:
            raise ValueError(f'invalid or duplicate native input name: {name!r}')
        scopes = bind_environment(item, bindings, known_modules)
        names.add(name)
        if not isinstance(item['path'], str) or not Path(item['path']).is_absolute():
            raise ValueError(f'native input path must be absolute: {name}')
        root = Path(item['path'])
        if 'git' in item:
            if item['git'] is not True:
                raise ValueError(f'Git input selector must be true: {name}')
            identity = checkout_identity(root)
        else:
            identity = check_files(root, item['files'])
        root = root.resolve(strict=True)
        mount_path(root)
        if evidence_dir.resolve().is_relative_to(root):
            raise ValueError(f'evidence directory must be outside input source: {root}')
        checked.append((item, root, identity, scopes))
    outputs = document.get('outputs', [])
    if not isinstance(outputs, list):
        raise ValueError('native outputs must be a list of module-specific output selectors')
    output_names = set()
    for item in outputs:
        if not isinstance(item, dict) or set(item) != {'name', 'env', 'modules'}:
            raise ValueError('each native output needs name, env and modules')
        if not isinstance(item['name'], str) or not re.fullmatch('[a-z][a-z0-9-]{0,63}', item['name']):
            raise ValueError(f'invalid native output name: {item["name"]!r}')
        scopes = bind_environment(item, bindings, known_modules, require_scope=True)
        for module in scopes:
            target = (module, item['name'])
            if target in output_names:
                raise ValueError(f'duplicate native output leaf: {target}')
            output_names.add(target)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = evidence_dir.resolve(strict=True)
    mount_path(evidence_dir)
    run = Path(tempfile.mkdtemp(prefix='native-inputs-', dir=evidence_dir))
    snapshots, output = run / 'inputs', run / 'output'
    snapshots.mkdir()
    output.mkdir()
    record = {'schema': SCHEMA, 'status': 'preparing', 'manifest': str(manifest.resolve()),
              'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'image': image,
              'prepared_at': datetime.now(timezone.utc).isoformat(), 'inputs': []}
    record['preparer'] = {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__))}
    if runner:
        record['runner'] = {'path': str(runner.resolve()), 'sha256': digest(runner)}
    if source:
        record['agent_ee'] = {'path': str(source.resolve()), **source_identity}
    receipt = output / 'native-inputs.json'
    argv = []
    module_env = {'schema': 'agent-ee.module-env/1', 'modules': {}}

    def selected_module(name):
        return module_env['modules'].setdefault(name, {'inputs': {}, 'outputs': {}})

    try:
        for item, root, identity, scopes in checked:
            snapshot = snapshots / item['name']
            if 'git' in item:
                git(root, 'clone', '--quiet', '--local', '--no-hardlinks', '--no-checkout',
                    '--', str(root), str(snapshot))
                git(snapshot, 'checkout', '--quiet', '--detach', identity['commit'])
                if checkout_identity(snapshot) != identity:
                    raise ValueError(f'verifier snapshot differs from the selected clean commit: {root}')
            elif root.is_dir():
                shutil.copytree(root, snapshot, symlinks=True)
            else:
                shutil.copyfile(root, snapshot, follow_symlinks=False)
            if 'files' in item:
                check_files(snapshot, identity)
            target = '/opt/agent-ee-inputs/' + item['name']
            argv += ['--mount', f'type=bind,src={mount_path(snapshot)},dst={target},readonly']
            if scopes == ['*']:
                argv += ['-e', item['env'] + '=' + target]
            else:
                for module in scopes:
                    selected_module(module)['inputs'][item['env']] = target
            record['inputs'].append({'name': item['name'], 'env': item['env'], 'source': str(root),
                                     'snapshot': str(snapshot), 'container_path': target,
                                     'modules': scopes,
                                     'git' if 'git' in item else 'files': identity})
        for item in outputs:
            for module in item['modules']:
                (output / 'modules' / module).mkdir(parents=True, exist_ok=True)
                selected_module(module)['outputs'][item['env']] = f'/artifacts/modules/{module}/{item["name"]}'
        if module_env['modules']:
            module_file = snapshots / 'module-env.json'
            module_file.write_text(json.dumps(module_env, indent=2) + '\n')
            record['module_env_sha256'] = digest(module_file)
            record['module_environment'] = module_env
            argv += ['--mount', f'type=bind,src={mount_path(module_file)},dst=/opt/agent-ee-inputs/module-env.json,readonly',
                     '-e', 'AGENT_EE_MODULE_ENV=/opt/agent-ee-inputs/module-env.json']
        record['status'] = 'prepared'
    except (OSError, ValueError) as exc:
        record.update(status='failed', error=str(exc))
        receipt.write_text(json.dumps(record, indent=2) + '\n')
        raise
    receipt.write_text(json.dumps(record, indent=2) + '\n')
    # Only outputs are writable in the container: input snapshots have no writable alias.
    argv += ['--mount', f'type=bind,src={mount_path(output)},dst=/artifacts',
             '-e', 'AGENT_EE_EVIDENCE_DIR=/artifacts',
             '-e', 'AGENT_EE_RUN_INPUT_RECEIPT=/artifacts/native-inputs.json']
    args_file.write_bytes(('\0'.join(argv) + '\0').encode())
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    inspect = commands.add_parser('inventory', help='describe an explicitly selected regular-file input')
    inspect.add_argument('path', type=Path)
    stage = commands.add_parser('prepare', help='verify and retain input copies for one admitted run')
    stage.add_argument('manifest', type=Path)
    stage.add_argument('--evidence-dir', required=True, type=Path)
    stage.add_argument('--args-file', required=True, type=Path)
    stage.add_argument('--image')
    stage.add_argument('--runner', type=Path)
    stage.add_argument('--source', type=Path, help='clean agent-ee source selected by the runner')
    args = parser.parse_args()
    try:
        if args.operation == 'inventory':
            print(json.dumps(inventory(args.path), indent=2))
        else:
            receipt = prepare(args.manifest, args.evidence_dir, args.args_file,
                              args.image, args.runner, args.source)
            print(json.dumps({'receipt': str(receipt)}))
            print(f'ae-ci-exec: native input receipt {receipt}', file=sys.stderr)
    except (OSError, ValueError) as exc:
        print(f'ae-ci-exec: native inputs refused: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
