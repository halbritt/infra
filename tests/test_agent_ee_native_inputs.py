"""AGENTEE-622/624: admitted runner inputs retain their bytes and source identity."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'shared/agent-ee/native-inputs.py'


class NativeInputsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ae-native-inputs-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'retained'
        self.source.mkdir()
        (self.source / 'receipt.json').write_text('historical receipt\n')
        self.manifest = self.root / 'inputs.json'
        self.inputs = [{'name': 'k91-final', 'env': 'AGENT_EE_K91_FINAL_RECEIPT',
                        'path': str(self.source), 'files': {
                            'receipt.json': hashlib.sha256(b'historical receipt\n').hexdigest()}}]

    def prepare(self):
        document = {'schema': 'agent-ee.native-inputs/1', 'inputs': self.inputs}
        if hasattr(self, 'outputs'):
            document['outputs'] = self.outputs
        self.manifest.write_text(json.dumps(document))
        return subprocess.run([sys.executable, str(getattr(self, 'script', SCRIPT)), 'prepare', str(self.manifest),
                               '--evidence-dir', str(self.root / 'evidence'),
                               '--args-file', str(self.root / 'args')],
                              capture_output=True, text=True, timeout=30)

    def test_receipt_is_copied_read_only_and_retained_outside_writable_outputs(self):
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt_path = Path(json.loads(result.stdout)['receipt'])
        receipt = json.loads(receipt_path.read_text())
        output = Path(receipt['output_directory'])
        source = Path(receipt['inputs'][0]['snapshot'])
        self.assertEqual((source / 'receipt.json').read_bytes(), b'historical receipt\n')
        self.assertEqual(receipt['manifest_sha256'], hashlib.sha256(self.manifest.read_bytes()).hexdigest())
        args = (self.root / 'args').read_bytes().decode().split('\0')[:-1]
        self.assertIn(f'type=bind,src={source},dst=/opt/agent-ee-inputs/k91-final,readonly', args)
        self.assertIn('AGENT_EE_K91_FINAL_RECEIPT=/opt/agent-ee-inputs/k91-final', args)
        self.assertIn(f'type=bind,src={output},dst=/artifacts', args)
        self.assertIn(f'type=bind,src={receipt_path},dst=/opt/agent-ee-inputs/receipt.json,readonly', args)
        self.assertFalse(source.is_relative_to(output))
        self.assertFalse(receipt_path.is_relative_to(output))
        self.assertEqual(receipt['inputs'][0]['files'], self.inputs[0]['files'])
        (self.source / 'receipt.json').write_text('producer changed\n')
        self.assertEqual((source / 'receipt.json').read_bytes(), b'historical receipt\n')

    def git(self, root, *args):
        result = subprocess.run(['git', '-c', 'user.name=Input Test', '-c', 'user.email=inputs@example.invalid',
                                 '-C', str(root), *args], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_selected_clean_verifier_commit_survives_checkout_movement_and_removal(self):
        verifier = self.root / 'verifier'
        verifier.mkdir()
        self.git(verifier, 'init', '-q')
        (verifier / 'verifier.py').write_text('original source\n')
        self.git(verifier, 'add', '.')
        self.git(verifier, 'commit', '-qm', 'original')
        commit = self.git(verifier, 'rev-parse', 'HEAD')
        self.inputs = [{'name': 'pcbschemagen', 'env': 'PCBSCHEMAGEN_ROOT',
                        'path': str(verifier), 'git': True}]
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(Path(json.loads(result.stdout)['receipt']).read_text())
        snapshot = Path(receipt['inputs'][0]['snapshot'])
        self.assertEqual(receipt['inputs'][0]['git']['commit'], commit)
        self.assertTrue(receipt['inputs'][0]['git']['clean'])
        (verifier / 'verifier.py').write_text('later source\n')
        self.git(verifier, 'add', '.')
        self.git(verifier, 'commit', '-qm', 'later')
        self.assertEqual(self.git(snapshot, 'rev-parse', 'HEAD'), commit)
        self.assertEqual((snapshot / 'verifier.py').read_text(), 'original source\n')
        shutil.rmtree(verifier)
        self.assertEqual(self.git(snapshot, 'show', 'HEAD:verifier.py'), 'original source')
        self.assertFalse((snapshot / '.git/objects/info/alternates').exists())

    def test_missing_incomplete_damaged_or_extra_receipt_input_refuses_before_emitting_argv(self):
        for variant in ('absent', 'incomplete', 'damaged', 'extra'):
            with self.subTest(variant=variant):
                (self.root / 'args').unlink(missing_ok=True)
                if not self.source.exists():
                    self.source.mkdir()
                for file in self.source.iterdir():
                    file.unlink()
                (self.source / 'receipt.json').write_text('historical receipt\n')
                if variant in ('absent', 'incomplete'):
                    (self.source / 'receipt.json').unlink()
                    if variant == 'absent':
                        self.source.rmdir()
                elif variant == 'damaged':
                    (self.source / 'receipt.json').write_text('damaged receipt\n')
                else:
                    (self.source / 'other.json').write_text('unrecorded input\n')
                result = self.prepare()
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('native inputs refused', result.stderr)
                self.assertFalse((self.root / 'args').exists())
                failed = list((self.root / 'evidence').glob('failed-*/native-inputs.json'))
                self.assertTrue(failed)
                self.assertTrue(all(json.loads(path.read_text())['status'] == 'failed' for path in failed))

    def test_symlinked_input_is_refused_without_mutating_its_target(self):
        target = self.root / 'outside.json'
        target.write_text('outside source\n')
        target.chmod(0o444)
        (self.source / 'receipt.json').unlink()
        (self.source / 'receipt.json').symlink_to(target)
        result = self.prepare()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('symlink', result.stderr)
        self.assertEqual(target.read_text(), 'outside source\n')
        self.assertEqual(target.stat().st_mode & 0o777, 0o444)

    def test_dirty_verifier_checkout_cannot_be_reported_as_a_clean_commit(self):
        self.git(self.source, 'init', '-q')
        self.git(self.source, 'add', '.')
        self.git(self.source, 'commit', '-qm', 'original')
        self.inputs = [{'name': 'pcbschemagen', 'env': 'PCBSCHEMAGEN_ROOT',
                        'path': str(self.source), 'git': True}]
        (self.source / 'receipt.json').write_text('uncommitted change\n')
        result = self.prepare()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('checkout must be clean', result.stderr)
        self.assertFalse((self.root / 'args').exists())

    def test_manifest_cannot_override_toolchain_requirement_or_alias_input_variables(self):
        for variant in ('reserved', 'duplicate-name', 'duplicate-variable', 'unknown-field'):
            with self.subTest(variant=variant):
                item = {'name': 'k91-final', 'env': 'AGENT_EE_K91_FINAL_RECEIPT',
                        'path': str(self.source), 'files': {
                            'receipt.json': hashlib.sha256(b'historical receipt\n').hexdigest()}}
                self.inputs = [item]
                if variant == 'reserved':
                    item['env'] = 'AGENT_EE_REQUIRE_TOOLCHAIN'
                elif variant == 'duplicate-name':
                    self.inputs.append({**item, 'env': 'AGENT_EE_K91_PROTECTED_EXISTING'})
                elif variant == 'duplicate-variable':
                    self.inputs.append({**item, 'name': 'other-input'})
                else:
                    item['extra'] = 'ignored data would conceal a setup error'
                result = self.prepare()
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse((self.root / 'args').exists())

    def test_distinct_module_inputs_share_a_variable_and_output_leaves_start_absent(self):
        self.inputs[0]['modules'] = ['test_historical']
        current = self.root / 'current'
        current.mkdir()
        (current / 'receipt.json').write_text('public control\n')
        self.inputs[0]['env'] = 'AGENT_EE_ACQUISITION_INPUTS'
        self.inputs.append({'name': 'current', 'env': 'AGENT_EE_ACQUISITION_INPUTS',
                            'path': str(current), 'files': {
                                'receipt.json': hashlib.sha256(b'public control\n').hexdigest()},
                            'modules': ['test_current']})
        self.outputs = [{'name': 'parts', 'env': 'AGENT_EE_POWER_PART_ARTIFACTS',
                         'modules': ['test_current', 'test_historical']}]
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt_path = Path(json.loads(result.stdout)['receipt'])
        record = json.loads(receipt_path.read_text())
        module_file = receipt_path.parent / 'inputs/module-env.json'
        mapping = json.loads(module_file.read_text())
        self.assertEqual(mapping['schema'], 'agent-ee.module-env/1')
        modules = mapping['modules']
        self.assertEqual(modules['test_historical']['inputs']['AGENT_EE_ACQUISITION_INPUTS'],
                         '/opt/agent-ee-inputs/k91-final')
        self.assertEqual(modules['test_current']['inputs']['AGENT_EE_ACQUISITION_INPUTS'],
                         '/opt/agent-ee-inputs/current')
        args = (self.root / 'args').read_bytes().decode().split('\0')[:-1]
        self.assertFalse(any(x.startswith('AGENT_EE_ACQUISITION_INPUTS=') for x in args))
        self.assertIn('AGENT_EE_MODULE_ENV=/opt/agent-ee-inputs/module-env.json', args)
        for name in modules:
            value = modules[name]['outputs']['AGENT_EE_POWER_PART_ARTIFACTS']
            self.assertEqual(value, f'/artifacts/modules/{name}/parts')
            host = Path(record['output_directory']) / 'modules' / name / 'parts'
            self.assertTrue(host.parent.is_dir())
            self.assertFalse(host.exists())
        self.assertEqual(record['module_env_sha256'], hashlib.sha256(module_file.read_bytes()).hexdigest())

    def test_missing_scoped_source_refuses_before_launch_even_with_good_modules(self):
        self.inputs[0]['modules'] = ['test_historical']
        self.inputs.append({**self.inputs[0], 'name': 'absent', 'path': str(self.root / 'absent'),
                            'modules': ['test_current']})
        result = self.prepare()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('absent', result.stderr)
        self.assertFalse((self.root / 'args').exists())
        self.inputs[1]['env'] = 'AGENT_EE_SKIP_VISUALS'
        result = self.prepare()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('undeclared', result.stderr)

    def test_untracked_ignored_and_alternate_dependent_verifier_refuse(self):
        for variant in ('untracked', 'ignored', 'alternates'):
            with self.subTest(variant=variant):
                verifier = self.root / variant
                verifier.mkdir()
                self.git(verifier, 'init', '-q')
                (verifier / 'verifier.py').write_text('selected source\n')
                (verifier / '.gitignore').write_text('ignored.py\n')
                self.git(verifier, 'add', '.')
                self.git(verifier, 'commit', '-qm', 'selected')
                if variant == 'alternates':
                    (verifier / '.git/objects/info/alternates').write_text(str(self.root / 'missing-objects') + '\n')
                else:
                    (verifier / (variant + '.py')).write_text('not part of selected commit\n')
                self.inputs = [{'name': 'pcbschemagen', 'env': 'PCBSCHEMAGEN_ROOT',
                                'path': str(verifier), 'git': True}]
                result = self.prepare()
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse((self.root / 'args').exists())

    def launch_fixture(self):
        source = self.root / 'agent-ee'
        (source / 'scripts').mkdir(parents=True)
        (source / 'tests').mkdir()
        shutil.copyfile(SCRIPT.with_name('native-input-policy.json'), source / 'scripts/native-input-policy.json')
        self.git(source, 'init', '-q')
        self.git(source, 'add', '.')
        self.git(source, 'commit', '-qm', 'source')
        self.manifest.write_text(json.dumps({'schema': 'agent-ee.native-inputs/1', 'inputs': self.inputs}))
        result = subprocess.run([sys.executable, str(SCRIPT), 'prepare', str(self.manifest),
            '--source', str(source), '--runner', str(SCRIPT.with_name('ae-ci-exec')),
            '--evidence-dir', str(self.root / 'evidence')], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = Path(json.loads(result.stdout)['receipt'])
        record = json.loads(receipt.read_bytes())
        image = 'sha256:' + '1' * 64
        bind = subprocess.run([sys.executable, str(SCRIPT), 'bind-image', str(receipt), image],
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(bind.returncode, 0, bind.stderr)
        scratch = self.root / 'scratch'
        scratch.mkdir()
        plan = Path(record['args_file']).read_bytes().decode().split('\0')[:-1]
        command = ['docker', 'run', '--rm', *plan, '-v', f'{source}:/opt/agent-ee',
                   '-v', f'{scratch}:/tmp', image, 'python3', '-c', 'print("native command")']
        return receipt, command

    def check_launch(self, receipt, command):
        return subprocess.run([sys.executable, str(SCRIPT), 'check-launch', str(receipt), '--', *command],
                              capture_output=True, text=True, timeout=30)

    def test_actual_launch_binds_receipt_and_rejects_writable_alias_or_changed_mount(self):
        receipt, command = self.launch_fixture()
        success = self.check_launch(receipt, command)
        self.assertEqual(success.returncode, 0, success.stderr)
        record = json.loads(receipt.read_bytes())
        self.assertEqual(record['launch'], command)
        self.assertEqual(record['launch_sha256'], hashlib.sha256(json.dumps(command).encode()).hexdigest())
        snapshot = Path(record['inputs'][0]['snapshot'])
        for variant in ('writable-input', 'writable-alias', 'duplicate-destination', 'changed-source', 'source-link'):
            with self.subTest(variant=variant):
                argv = command.copy()
                if variant == 'writable-input':
                    index = next(i for i, arg in enumerate(argv) if 'dst=/opt/agent-ee-inputs/k91-final,' in arg)
                    argv[index] = argv[index].removesuffix(',readonly')
                elif variant == 'writable-alias':
                    argv[3:3] = ['-v', str(receipt.parent) + ':/writable-alias']
                elif variant == 'duplicate-destination':
                    argv[3:3] = ['-v', str(snapshot) + ':/opt/agent-ee']
                elif variant == 'changed-source':
                    (snapshot / 'receipt.json').write_text('changed after preparation\n')
                else:
                    (snapshot / 'receipt.json').write_text('historical receipt\n')
                    link = self.root / 'linked-snapshot'
                    link.symlink_to(snapshot, target_is_directory=True)
                    index = next(i for i, arg in enumerate(argv) if 'dst=/opt/agent-ee-inputs/k91-final,' in arg)
                    argv[index] = argv[index].replace(str(snapshot), str(link))
                refused = self.check_launch(receipt, argv)
                self.assertEqual(refused.returncode, 2, refused.stderr)
                self.assertIn('native inputs refused', refused.stderr)
        self.assertEqual((self.source / 'receipt.json').read_text(), 'historical receipt\n')

    def test_selected_image_binding_cannot_be_retargeted_after_preparation(self):
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = Path(json.loads(result.stdout)['receipt'])
        first = 'sha256:' + '1' * 64
        bind = subprocess.run([sys.executable, str(SCRIPT), 'bind-image', str(receipt), first],
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(bind.returncode, 0, bind.stderr)
        before = receipt.read_bytes()
        other = subprocess.run([sys.executable, str(SCRIPT), 'bind-image', str(receipt), 'sha256:'+'2'*64],
                               capture_output=True, text=True, timeout=15)
        self.assertEqual(other.returncode, 2)
        self.assertEqual(receipt.read_bytes(), before)

    def test_authoritative_receipt_input_name_is_reserved_before_argv_is_emitted(self):
        self.inputs[0]['name'] = 'receipt'
        result = self.prepare()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('reserved native input name', result.stderr)
        self.assertFalse((self.root / 'args').exists())

    def test_descendant_selection_keeps_the_sibling_build_plan_in_the_same_readonly_snapshot(self):
        (self.source / 'receipt.json').unlink()
        (self.source / 'inputs').mkdir()
        (self.source / 'inputs/circuit.json').write_bytes(b'original circuit\n')
        (self.source / 'build-plan.json').write_bytes(b'original plan\n')
        original = {p.relative_to(self.source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.source.rglob('*') if p.is_file()}
        self.inputs = [{'name': 'base', 'env': 'AGENT_EE_FILM_BASE', 'path': str(self.source),
                        'files': original, 'select': 'inputs', 'modules': ['test_acquisition_film']}]
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(Path(json.loads(result.stdout)['receipt']).read_text())
        item = receipt['inputs'][0]
        self.assertEqual(item['container_path'], '/opt/agent-ee-inputs/base/inputs')
        selected = Path(item['snapshot']) / 'inputs'
        self.assertEqual((selected.parent / 'build-plan.json').read_bytes(), b'original plan\n')
        args = (self.root / 'args').read_bytes().decode().split('\0')
        self.assertIn(f'type=bind,src={selected.parent},dst=/opt/agent-ee-inputs/base,readonly', args)
        self.assertEqual(receipt['module_environment']['modules']['test_acquisition_film']['inputs'],
                         {'AGENT_EE_FILM_BASE': '/opt/agent-ee-inputs/base/inputs'})
        self.assertEqual(original, {p.relative_to(self.source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in self.source.rglob('*') if p.is_file()})
        for value in ('../inputs', '/inputs', '.', '', None, 'inputs//circuit.json', 'absent'):
            with self.subTest(select=value):
                (self.root/'args').unlink(missing_ok=True)
                self.inputs[0]['select'] = value
                refused = self.prepare()
                self.assertEqual(refused.returncode, 2, refused.stderr)
                self.assertFalse((self.root/'args').exists())
        self.inputs[0]['select'] = 'inputs'
        (self.source/'inputs/link').symlink_to(self.source/'build-plan.json')
        self.assertEqual(self.prepare().returncode, 2)

    def test_named_historical_layout_preserves_pin_bytes_and_binds_only_verified_snapshots_readonly(self):
        runner = self.root / 'runner'
        runner.mkdir()
        self.script = runner / SCRIPT.name
        shutil.copy2(SCRIPT, self.script)
        policy = json.loads(SCRIPT.with_name('native-input-policy.json').read_text())
        alias_tmp = tempfile.TemporaryDirectory(prefix='ae-layout-policy-', dir=Path.home() / '.cache')
        self.addCleanup(alias_tmp.cleanup)
        alias = Path(alias_tmp.name) / 'historical-film'
        (self.source / 'receipt.json').unlink()
        probe = self.source / 'model-r1/probe'
        probe.mkdir(parents=True)
        (probe / 'model.sub').write_bytes(b'genuine fixture model\n')
        model_sha = hashlib.sha256((probe / 'model.sub').read_bytes()).hexdigest()
        pins = self.source / 'model-r1/input-pins.json'
        pins.write_text(json.dumps({'files': {'/outside/metadata-only': '0'*64},
                                   'generated_files': {str(alias/'model-r1/probe/model.sub'): model_sha}}))
        pins_sha = hashlib.sha256(pins.read_bytes()).hexdigest()
        execution = self.source / 'model-r1/execution.json'
        (probe/'result.raw').write_bytes(b'original output\n')
        execution.write_text(json.dumps({'input_pins_sha256': pins_sha, 'outputs': {
            'result.raw': {'bytes': 16, 'sha256': hashlib.sha256(b'original output\n').hexdigest()}}}))
        policy['layouts'] = {'film-model-r1': {
            'at': str(alias), 'env': 'AGENT_EE_FILM_RUN', 'modules': ['test_acquisition_film'],
            'pins_sha256': pins_sha, 'execution_sha256': hashlib.sha256(execution.read_bytes()).hexdigest()}}
        self.script.with_name('native-input-policy.json').write_text(json.dumps(policy))
        files = {p.relative_to(self.source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.source.rglob('*') if p.is_file()}
        self.inputs = [{'name': 'film-run', 'env': 'AGENT_EE_FILM_RUN', 'path': str(self.source),
                        'files': files, 'layout': 'film-model-r1', 'modules': ['test_acquisition_film']}]
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(Path(json.loads(result.stdout)['receipt']).read_text())
        snapshot = Path(record['inputs'][0]['snapshot'])
        args = (self.root / 'args').read_bytes().decode().split('\0')
        self.assertIn(f'type=bind,src={snapshot},dst={alias},readonly', args)
        self.assertIn(f'type=bind,src={snapshot},dst=/opt/agent-ee-inputs/film-run,readonly', args)
        self.assertEqual((snapshot/'model-r1/input-pins.json').read_bytes(), pins.read_bytes())
        self.assertEqual(record['inputs'][0]['container_path'], str(alias))
        self.assertEqual(record['inputs'][0]['layout'], 'film-model-r1')
        self.assertTrue(record['inputs'][0]['read_only'])
        self.assertFalse(alias.exists())
        self.assertEqual(files, {p.relative_to(self.source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in self.source.rglob('*') if p.is_file()})
        original_item = dict(self.inputs[0])
        for fault in ('unknown-layout', 'arbitrary-destination', 'global-scope', 'wrong-module',
                      'select-and-layout', 'forbidden-root', 'collision', 'changed-pins', 'missing-generated'):
            with self.subTest(fault=fault):
                (self.root/'args').unlink(missing_ok=True)
                self.inputs = [dict(original_item)]
                changed_policy = json.loads(json.dumps(policy))
                if fault == 'unknown-layout': self.inputs[0]['layout'] = 'unreviewed'
                if fault == 'arbitrary-destination': self.inputs[0]['layout'] = {'at': '/etc'}
                if fault == 'global-scope': self.inputs[0].pop('modules')
                if fault == 'wrong-module': self.inputs[0]['modules'] = ['test_other']
                if fault == 'select-and-layout': self.inputs[0]['select'] = 'model-r1'
                if fault == 'forbidden-root': changed_policy['layouts']['film-model-r1']['at'] = '/artifacts/private'
                if fault == 'collision':
                    changed_policy['layouts']['film-model-r1']['modules'].append('test_acquisition_film_loop')
                    self.inputs.append({**original_item, 'name': 'film-copy', 'modules': ['test_acquisition_film_loop']})
                if fault == 'changed-pins': pins.write_text('rewritten receipt')
                if fault == 'missing-generated':
                    (probe/'model.sub').unlink()
                    self.inputs[0]['files'] = {k: v for k,v in files.items() if k != 'model-r1/probe/model.sub'}
                self.script.with_name('native-input-policy.json').write_text(json.dumps(changed_policy))
                refused = self.prepare()
                self.assertEqual(refused.returncode, 2, refused.stderr)
                self.assertFalse((self.root/'args').exists())
                if fault == 'changed-pins':
                    pins.write_bytes((snapshot/'model-r1/input-pins.json').read_bytes())
                if fault == 'missing-generated':
                    (probe/'model.sub').write_bytes(b'genuine fixture model\n')


if __name__ == '__main__':
    unittest.main()
