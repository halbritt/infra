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
POLICY_FILE = Path(__file__).with_name('native-input-policy.json')
POLICY_BYTES = POLICY_FILE.read_bytes()
POLICY = json.loads(POLICY_BYTES)


class UnavailableInput(ValueError):
    """A declared module's source is missing; no substitute is selected."""


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
        if not root.exists():
            raise UnavailableInput(f'input is absent: {root}')
        raise ValueError(f'input is not a regular file/directory: {root}')
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


def validate_files(expected):
    if not isinstance(expected, dict) or not expected or any(
            not isinstance(name, str) or not isinstance(sha, str)
            or Path(name).is_absolute() or '..' in Path(name).parts
            or Path(name).as_posix() != name
            or not re.fullmatch('[0-9a-f]{64}', sha) for name, sha in expected.items()):
        raise ValueError('input needs a nonempty relative-file SHA-256 inventory')


def check_files(root, expected):
    validate_files(expected)
    actual = inventory(root)
    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    changed = sorted(name for name in actual.keys() & expected.keys() if actual[name] != expected[name])
    if extra or changed:
        raise ValueError(f'input inventory mismatch at {root}: missing={missing}, extra={extra}, changed={changed}')
    if missing:
        raise UnavailableInput(f'input inventory incomplete at {root}: missing={missing}')
    return actual


def mount_path(path):
    # Docker's --mount grammar uses commas; argv quoting cannot escape that grammar.
    if any(c in str(path) for c in (',', '\n', '\r', '\0')):
        raise ValueError(f'input path cannot contain commas or control characters: {path!s}')
    return str(path)


def direct_path(path):
    """Mount sources must be absolute existing paths without symlink components."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError(f'mount source is not an absolute confined path: {path}')
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f'mount source uses a symlink component: {part}')
    if not path.exists():
        raise ValueError(f'mount source is absent: {path}')
    return path


def overlaps(a, b):
    return a.is_relative_to(b) or b.is_relative_to(a)


def launch_mounts(argv):
    """Read only the existing runner's volume options, before its selected image."""
    mounts = {}
    for index, option in enumerate(argv):
        if option == '-v':
            parts = argv[index + 1].split(':')
            if len(parts) not in (2, 3) or (len(parts) == 3 and parts[2] != 'ro'):
                raise ValueError('unsupported runner volume option')
            src, dest = parts[:2]
            readonly = len(parts) == 3
        elif option == '--mount':
            fields = unique_object([piece.split('=', 1) if '=' in piece else (piece, '')
                                    for piece in argv[index + 1].split(',')])
            if fields.get('type') == 'tmpfs':
                continue
            if fields.get('type') != 'bind':
                raise ValueError('unsupported runner mount type')
            if not {'type', 'src', 'dst'} <= set(fields) <= {'type', 'src', 'dst', 'readonly'}:
                raise ValueError('unsupported runner bind fields')
            src, dest = fields['src'], fields['dst']
            readonly = 'readonly' in fields
        else:
            continue
        if dest in mounts:
            raise ValueError(f'duplicate container mount destination: {dest}')
        if not Path(dest).is_absolute() or '..' in Path(dest).parts:
            raise ValueError(f'invalid container mount destination: {dest}')
        mounts[dest] = (direct_path(src), readonly)
    return mounts


def check_launch(receipt, argv):
    """Validate the actual runner launch, then bind its exact command to the receipt."""
    receipt = direct_path(receipt)
    record = json.loads(receipt.read_bytes(), object_pairs_hook=unique_object)
    if (record.get('schema') != SCHEMA or record.get('status') != 'prepared'
            or record.get('policy_sha256') != hashlib.sha256(POLICY_BYTES).hexdigest()
            or record.get('preparer', {}).get('sha256') != digest(Path(__file__))):
        raise ValueError('launch receipt does not bind this prepared input policy/helper')
    image = record.get('image')
    if not isinstance(image, str) or not re.fullmatch('sha256:[0-9a-f]{64}', image):
        raise ValueError('launch receipt lacks a selected image')
    if argv[:2] != ['docker', 'run'] or image not in argv:
        raise ValueError('expected the existing runner Docker launch and selected image')
    prefix = argv[:argv.index(image)]
    plan = direct_path(record['args_file']).read_bytes()
    if hashlib.sha256(plan).hexdigest() != record.get('mount_plan_sha256'):
        raise ValueError('prepared mount plan changed')
    source = direct_path(record['agent_ee']['path'])
    if checkout_identity(source, source=True) != {k: record['agent_ee'][k] for k in ('commit', 'tree', 'clean')}:
        raise ValueError('agent-ee source changed after input preparation')
    if (source / 'scripts/native-input-policy.json').read_bytes() != POLICY_BYTES:
        raise ValueError('agent-ee source policy changed after preparation')
    if digest(direct_path(record['runner']['path'])) != record['runner']['sha256']:
        raise ValueError('runner changed after input preparation')
    mounts = launch_mounts(prefix)
    expected = {}
    names, bindings, env = set(), {}, {}
    for item in record['inputs']:
        name = item['name']
        if not re.fullmatch('[a-z][a-z0-9-]{0,63}', name) or name in names or name in ('receipt', 'module-env'):
            raise ValueError('invalid or duplicate receipt input name')
        names.add(name)
        selected_item = {k: v for k, v in item.items() if k != 'modules'} if item.get('modules') == ['*'] else item
        scopes = bind_environment(selected_item, bindings)
        mount = '/opt/agent-ee-inputs/' + name
        if item.get('mount_path') != mount or item.get('read_only') is not True:
            raise ValueError('receipt input lacks its canonical read-only mount')
        snapshot = direct_path(item['snapshot'])
        if 'git' in item:
            if not (snapshot / '.git').is_dir() or checkout_identity(snapshot) != item['git']:
                raise ValueError('verifier snapshot is not an independent clean selected checkout')
        else:
            check_files(snapshot, item['files'])
        selector = {k: v for k, v in item.items() if v is not None}
        selected = mount + ('/' + descendant(selector) if selector.get('select') else '')
        layout = historical_layout(selector, scopes)
        if layout:
            check_historical_files(snapshot, item['files'], layout)
            selected = layout['at']
            expected[selected] = (snapshot, True)
        if item['container_path'] != selected:
            raise ValueError('receipt input selection differs from its policy')
        expected[mount] = (snapshot, True)
        if scopes == ['*']:
            env[item['env']] = selected
    output = direct_path(record['output_directory'])
    expected['/artifacts'] = (output, False)
    expected['/opt/agent-ee-inputs/receipt.json'] = (receipt, True)
    env.update(AGENT_EE_EVIDENCE_DIR='/artifacts', AGENT_EE_RUN_INPUT_RECEIPT='/opt/agent-ee-inputs/receipt.json')
    if record.get('module_environment'):
        module_file = direct_path(receipt.parent / 'inputs/module-env.json')
        if (digest(module_file) != record['module_env_sha256']
                or json.loads(module_file.read_bytes()) != record['module_environment']):
            raise ValueError('module selection changed after preparation')
        expected['/opt/agent-ee-inputs/module-env.json'] = (module_file, True)
        env['AGENT_EE_MODULE_ENV'] = '/opt/agent-ee-inputs/module-env.json'
        for module, selection in record['module_environment']['modules'].items():
            for variable, value in selection['outputs'].items():
                if variable not in POLICY['outputs'] or not value.startswith('/artifacts/modules/' + module + '/'):
                    raise ValueError('module output is outside its declared artifact root')
                leaf = Path(value).relative_to('/artifacts')
                if '..' in leaf.parts or (output / leaf).exists() or (output / leaf).is_symlink():
                    raise ValueError(f'module output must start absent: {value}')
    if not plan.endswith(b'\0'):
        raise ValueError('prepared mount plan is not complete')
    plan_argv = plan[:-1].decode().split('\0')
    if len(plan_argv) % 2 or any(option not in ('--mount', '-e') for option in plan_argv[::2]):
        raise ValueError('prepared plan contains an undeclared runner option')
    plan_env = {}
    for option, value in zip(plan_argv[::2], plan_argv[1::2]):
        if option == '-e':
            key, value = value.split('=', 1)
            if key in plan_env:
                raise ValueError('duplicate prepared environment variable')
            plan_env[key] = value
    if launch_mounts(plan_argv) != expected or plan_env != env:
        raise ValueError('prepared plan differs from the finite receipt bindings')
    for dest, binding in expected.items():
        if mounts.get(dest) != binding:
            raise ValueError(f'actual runner mount differs from prepared input: {dest}')
    base_mounts = {dest: value for dest, value in mounts.items() if dest not in expected}
    for dest in expected:
        if any(overlaps(Path(dest), Path(other)) for other in base_mounts):
            raise ValueError(f'input destination overlaps a runner mount: {dest}')
    writable = [src for src, readonly in mounts.values() if not readonly]
    for src, readonly in expected.values():
        if readonly and any(overlaps(src.resolve(), other.resolve()) for other in writable):
            raise ValueError(f'read-only input has a writable alias: {src}')
    actual_env = {}
    for index, option in enumerate(prefix):
        if option == '-e':
            key, value = prefix[index + 1].split('=', 1)
            if key in actual_env:
                raise ValueError(f'duplicate launch environment variable: {key}')
            actual_env[key] = value
    if any(actual_env.get(key) != value for key, value in env.items()):
        raise ValueError('actual runner environment differs from prepared inputs')
    record['launch'] = argv
    record['launch_sha256'] = hashlib.sha256(json.dumps(argv).encode()).hexdigest()
    record['validated_at'] = datetime.now(timezone.utc).isoformat()
    receipt.write_text(json.dumps(record, indent=2) + '\n')


def descendant(item):
    value = item.get('select')
    if 'select' not in item:
        return ''
    if (not isinstance(value, str) or not value or value == '.' or Path(value).is_absolute()
            or '..' in Path(value).parts or Path(value).as_posix() != value
            or any(c in value for c in (',', '\n', '\r', '\0')) or 'git' in item):
        raise ValueError('select must be a canonical confined descendant of a finite-file input')
    if not any(name == value or name.startswith(value + '/') for name in item['files']):
        raise ValueError('selected descendant is not covered by the complete input inventory')
    return value


def historical_layout(item, scopes):
    """Only a reviewed, named policy can select an additional container destination."""
    name = item.get('layout')
    if 'layout' not in item:
        return None
    if not isinstance(name, str) or name not in POLICY.get('layouts', {}):
        raise ValueError('unknown historical input layout')
    layout = POLICY['layouts'][name]
    if ('git' in item or 'select' in item or item['env'] != layout['env']
            or '*' in scopes or not set(scopes) <= set(layout['modules'])):
        raise ValueError('historical layout needs its declared finite input and explicit module scope')
    at = Path(layout['at'])
    # The destination comes from source policy, never from manifest path or receipt metadata.
    if (not at.is_absolute() or '..' in at.parts or str(at) != layout['at']
            or any(at == root or at.is_relative_to(root) or root.is_relative_to(at)
                   for root in map(Path, ('/opt', '/artifacts', '/app', '/work', '/workspace',
                                         '/proc', '/sys', '/dev', '/etc', '/usr', '/bin', '/run', '/tmp')))):
        raise ValueError('historical layout destination overlaps a forbidden runtime root')
    mount_path(at)
    return layout


def check_historical_files(root, files, layout):
    """Keep original absolute generated-file keys and their execution chain unchanged."""
    pins_path, execution_path = 'model-r1/input-pins.json', 'model-r1/execution.json'
    if (files.get(pins_path) != layout['pins_sha256']
            or files.get(execution_path) != layout['execution_sha256']):
        raise ValueError('historical layout requires the exact reviewed pins and execution receipt')
    pins = json.loads((root / pins_path).read_text(), object_pairs_hook=unique_object)
    execution = json.loads((root / execution_path).read_text(), object_pairs_hook=unique_object)
    if execution.get('input_pins_sha256') != layout['pins_sha256']:
        raise ValueError('historical execution does not bind the original input pins')
    generated = pins.get('generated_files')
    if not isinstance(generated, dict) or not generated:
        raise ValueError('historical pins need generated files')
    for absolute, sha in generated.items():
        path = Path(absolute)
        if (not path.is_relative_to(Path(layout['at']) / 'model-r1/probe')
                or '..' in path.parts or str(path) != absolute
                or files.get(path.relative_to(layout['at']).as_posix()) != sha):
            raise ValueError('historical generated file is outside or differs from the finite snapshot')
    outputs = execution.get('outputs')
    if not isinstance(outputs, dict):
        raise ValueError('historical execution needs a finite output inventory')
    for relative, identity in outputs.items():
        if (not isinstance(identity, dict) or relative in ('.', '..') or Path(relative).name != relative
                or files.get('model-r1/probe/' + relative) != identity.get('sha256')
                or type(identity.get('bytes')) is not int
                or (root / 'model-r1/probe' / relative).stat().st_size != identity['bytes']):
            raise ValueError('historical execution output differs from the finite snapshot')


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


def checkout_identity(root, *, source=False):
    if not root.exists():
        raise UnavailableInput(f'verifier source is missing: {root}')
    if not root.is_dir() or Path(git(root, 'rev-parse', '--show-toplevel')).resolve() != root.resolve():
        raise ValueError(f'verifier source must be a Git checkout root: {root}')
    commit = git(root, 'rev-parse', '--verify', 'HEAD^{commit}')
    if not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', commit):
        raise ValueError(f'verifier source has no commit to record: {root}')
    status_args = ['status', '--porcelain', '--untracked-files=all']
    if not source:
        status_args += ['--ignored=matching']
    if git(root, *status_args):
        raise ValueError(f'verifier checkout must be clean: {root}')
    common = Path(git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir'))
    if (common / 'objects/info/alternates').exists():
        raise ValueError(f'verifier checkout depends on object alternates: {root}')
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
    if not isinstance(variable, str) or variable not in POLICY['outputs' if require_scope else 'inputs']:
        raise ValueError(f'undeclared input/output environment variable: {variable!r}')
    previous = bindings.get(variable, set())
    if previous and ('*' in previous or '*' in scopes or previous.intersection(scopes)):
        raise ValueError(f'input environment variable has overlapping module selections: {variable}')
    bindings[variable] = previous | set(scopes)
    return scopes


def prepare(manifest, evidence_dir, args_file=None, image=None, runner=None, source=None):
    if not evidence_dir.is_absolute():
        raise ValueError('native input evidence directory must be absolute')
    raw = manifest.read_bytes()
    document = json.loads(raw, object_pairs_hook=unique_object)
    if (not isinstance(document, dict) or document.get('schema') != SCHEMA
            or not {'schema', 'inputs'} <= set(document) <= {'schema', 'inputs', 'outputs'}):
        raise ValueError(f'expected {SCHEMA} with schema and inputs fields: {manifest}')
    inputs = document['inputs']
    if not isinstance(inputs, list) or not inputs:
        raise ValueError('native input manifest must list at least one input')
    source_identity = checkout_identity(source, source=True) if source else None
    if source and (source / 'scripts/native-input-policy.json').read_bytes() != POLICY_BYTES:
        raise ValueError('runner and agent-ee native input policy differ; select a reviewed source pair')
    if source and evidence_dir.resolve().is_relative_to(source.resolve()):
        raise ValueError('native input evidence must stay outside the agent-ee checkout')
    names, bindings, checked = set(), {}, []
    known_modules = {p.stem for p in (source / 'tests').glob('test_*.py')} if source else None
    for item in inputs:
        if not isinstance(item, dict) or set(item) - {'modules', 'select', 'layout'} not in (
                {'name', 'env', 'path', 'files'}, {'name', 'env', 'path', 'git'}):
            raise ValueError('each native input needs name, env, path, and either files or git=true')
        name = item['name']
        if not isinstance(name, str) or not re.fullmatch('[a-z][a-z0-9-]{0,63}', name) or name in names:
            raise ValueError(f'invalid or duplicate native input name: {name!r}')
        if name in ('receipt', 'module-env'):
            raise ValueError(f'reserved native input name: {name}')
        scopes = bind_environment(item, bindings, known_modules)
        layout = historical_layout(item, scopes)
        names.add(name)
        if not isinstance(item['path'], str) or not Path(item['path']).is_absolute():
            raise ValueError(f'native input path must be absolute: {name}')
        root = Path(item['path'])
        mount_path(root)
        direct_path(root)
        if evidence_dir.resolve().is_relative_to(root.resolve()):
            raise ValueError(f'evidence directory must be outside input source: {root}')
        if 'git' in item:
            if item['git'] is not True:
                raise ValueError(f'Git input selector must be true: {name}')
        else:
            validate_files(item['files'])
        descendant(item)
        identity = checkout_identity(root) if 'git' in item else check_files(root, item['files'])
        if layout:
            check_historical_files(root, identity, layout)
        checked.append((item, root.resolve(), identity, scopes))
    destinations = [Path('/opt/agent-ee-inputs') / name for name in names]
    for item, _, _, scopes in checked:
        layout = historical_layout(item, scopes)
        if layout:
            at = Path(layout['at'])
            if any(at == other or at.is_relative_to(other) or other.is_relative_to(at) for other in destinations):
                raise ValueError('historical layout destinations overlap')
            destinations.append(at)
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
    for component in (evidence_dir, *evidence_dir.parents):
        if component.is_symlink():
            raise ValueError(f'evidence directory uses a symlink component: {component}')
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
    receipt = run / 'native-inputs.json'
    record['output_directory'] = str(output)
    args_file = args_file or (run / 'docker-args')
    record['args_file'] = str(args_file)
    record['policy_sha256'] = hashlib.sha256(POLICY_BYTES).hexdigest()
    argv = []
    module_env = {'schema': 'agent-ee.module-env/1', 'modules': {}}

    def selected_module(name):
        return module_env['modules'].setdefault(name, {'inputs': {}, 'outputs': {}})

    try:
        for item, root, identity, scopes in checked:
            snapshot = snapshots / item['name']
            mount_target = '/opt/agent-ee-inputs/' + item['name']
            target = mount_target + ('/' + descendant(item) if item.get('select') else '')
            layout = historical_layout(item, scopes)
            if layout:
                target = layout['at']
            if 'git' in item:
                git(root, 'clone', '--quiet', '--no-local', '--no-checkout',
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
                if layout:
                    check_historical_files(snapshot, identity, layout)
            argv += ['--mount', f'type=bind,src={mount_path(snapshot)},dst={mount_target},readonly']
            if layout:
                argv += ['--mount', f'type=bind,src={mount_path(snapshot)},dst={target},readonly']
            if scopes == ['*']:
                argv += ['-e', item['env'] + '=' + target]
            else:
                for module in scopes:
                    selected_module(module)['inputs'][item['env']] = target
            record['inputs'].append({'name': item['name'], 'env': item['env'], 'source': str(root),
                                     'snapshot': str(snapshot), 'container_path': target,
                                     'mount_path': mount_target, 'select': item.get('select'), 'read_only': True,
                                     'layout': item.get('layout'),
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
    # Only outputs are writable in the container: input snapshots have no writable alias.
    argv += ['--mount', f'type=bind,src={mount_path(output)},dst=/artifacts',
             '--mount', f'type=bind,src={mount_path(receipt)},dst=/opt/agent-ee-inputs/receipt.json,readonly',
             '-e', 'AGENT_EE_EVIDENCE_DIR=/artifacts',
             '-e', 'AGENT_EE_RUN_INPUT_RECEIPT=/opt/agent-ee-inputs/receipt.json']
    plan_bytes = ('\0'.join(argv) + '\0').encode()
    record['mount_plan_sha256'] = hashlib.sha256(plan_bytes).hexdigest()
    args_file.write_bytes(plan_bytes)
    receipt.write_text(json.dumps(record, indent=2) + '\n')
    return receipt


def retain_failure(args, error):
    """Keep refused setup outside input/source trees; no Docker argv is emitted."""
    root = args.evidence_dir.resolve()
    if not args.evidence_dir.is_absolute() or (args.source and root.is_relative_to(args.source.resolve())):
        return None
    raw = args.manifest.read_bytes() if args.manifest.is_file() else b''
    try:
        document = json.loads(raw)
    except ValueError:
        document = {}
    if isinstance(document, dict) and isinstance(document.get('inputs'), list):
        for item in document['inputs']:
            if isinstance(item, dict) and isinstance(item.get('path'), str):
                if root.is_relative_to(Path(item['path']).resolve()):
                    return None
    root.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix='failed-', dir=root)) / 'native-inputs.json'
    record = {'schema': SCHEMA, 'status': 'failed', 'error': str(error),
              'manifest': str(args.manifest.resolve()), 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
              'image': args.image, 'prepared_at': datetime.now(timezone.utc).isoformat()}
    destination.write_text(json.dumps(record, indent=2) + '\n')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    inspect = commands.add_parser('inventory', help='describe an explicitly selected regular-file input')
    inspect.add_argument('path', type=Path)
    stage = commands.add_parser('prepare', help='verify and retain input copies for one admitted run')
    stage.add_argument('manifest', type=Path)
    stage.add_argument('--evidence-dir', required=True, type=Path)
    stage.add_argument('--args-file', type=Path)
    stage.add_argument('--image')
    stage.add_argument('--runner', type=Path)
    stage.add_argument('--source', type=Path, help='clean agent-ee source selected by the runner')
    bind = commands.add_parser('bind-image', help='bind a prepared receipt to this run\'s selected image')
    bind.add_argument('receipt', type=Path)
    bind.add_argument('image')
    launch = commands.add_parser('check-launch', help='verify the actual existing runner mounts before launch')
    launch.add_argument('receipt', type=Path)
    launch.add_argument('argv', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.operation == 'inventory':
            print(json.dumps(inventory(args.path), indent=2))
        elif args.operation == 'check-launch':
            command = args.argv[1:] if args.argv[:1] == ['--'] else args.argv
            check_launch(args.receipt, command)
        elif args.operation == 'bind-image':
            record = json.loads(args.receipt.read_text(), object_pairs_hook=unique_object)
            if (record.get('schema') != SCHEMA or record.get('status') != 'prepared'
                    or not re.fullmatch('sha256:[0-9a-f]{64}', args.image)
                    or record.get('image') not in (None, args.image)):
                raise ValueError('receipt cannot be rebound to a different or invalid image')
            record['image'] = args.image
            temporary = args.receipt.with_suffix('.binding')
            temporary.write_text(json.dumps(record, indent=2) + '\n')
            temporary.replace(args.receipt)
        else:
            receipt = prepare(args.manifest, args.evidence_dir, args.args_file,
                              args.image, args.runner, args.source)
            print(json.dumps({'receipt': str(receipt), 'args_file': json.loads(receipt.read_text())['args_file']}))
            print(f'ae-ci-exec: native input receipt {receipt}', file=sys.stderr)
    except (OSError, ValueError) as exc:
        print(f'ae-ci-exec: native inputs refused: {exc}', file=sys.stderr)
        if args.operation == 'prepare':
            try:
                receipt = retain_failure(args, exc)
                if receipt:
                    print(f'ae-ci-exec: failed input receipt {receipt}', file=sys.stderr)
            except OSError as save_error:
                print(f'ae-ci-exec: failure receipt unavailable: {save_error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
