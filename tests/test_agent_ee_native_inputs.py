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
        return subprocess.run([sys.executable, str(SCRIPT), 'prepare', str(self.manifest),
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

    def test_missing_scoped_source_is_declared_without_hiding_good_modules_or_global_schema_errors(self):
        self.inputs[0]['modules'] = ['test_historical']
        self.inputs.append({**self.inputs[0], 'name': 'absent', 'path': str(self.root / 'absent'),
                            'modules': ['test_current']})
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(Path(json.loads(result.stdout)['receipt']).read_text())
        self.assertEqual(receipt['status'], 'prepared_with_unavailable_inputs')
        self.assertEqual(set(receipt['module_environment']['unavailable']), {'test_current'})
        self.assertIn('AGENT_EE_K91_FINAL_RECEIPT', receipt['module_environment']['unavailable']['test_current'])
        self.assertEqual(receipt['inputs'][1]['status'], 'unavailable')
        self.inputs[1]['env'] = 'AGENT_EE_SKIP_VISUALS'
        result = self.prepare()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('undeclared', result.stderr)

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


if __name__ == '__main__':
    unittest.main()
