"""Exercise bundle publication with real ELF libraries and isolated Git repositories."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'hosts/proximal/config/llama/llama-cpp-update'


@unittest.skipUnless(shutil.which('cc') and shutil.which('cmake'), 'native build tools required')
class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.remote = self.root / 'remote'
        self.state = self.root / 'state'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.git('init', '-q', '-b', 'master', str(self.remote))
        self.git('-C', str(self.remote), 'config', 'user.email', 'fixture@example.invalid')
        self.git('-C', str(self.remote), 'config', 'user.name', 'Fixture')
        self.commit('old')
        self.git('clone', '-q', str(self.remote), str(self.repo))
        self.commit('new')
        self.old = self.git('-C', str(self.repo), 'rev-parse', 'HEAD').strip()
        self.target = self.git('-C', str(self.remote), 'rev-parse', 'HEAD').strip()
        toolkit = self.root / 'toolkit'
        (toolkit / 'bin').mkdir(parents=True)
        nvcc = toolkit / 'bin/nvcc'
        nvcc.write_text('#!/bin/sh\necho fixture-toolkit\n')
        nvcc.chmod(0o755)
        cmake = self.bin / 'cmake'
        cmake.write_text('''#!/usr/bin/python3
import os,pathlib,subprocess,sys,shutil
if '--build' not in sys.argv: sys.exit(0)
if os.environ.get('FAIL_BUILD'): sys.exit(1)
p=pathlib.Path(sys.argv[sys.argv.index('--build')+1])/'bin';p.mkdir(parents=True)
(p/'lib.c').write_text('int answer(void) {return 42;}')
(p/'main.c').write_text('extern int answer(void); int main(void) {return answer()!=42;}')
subprocess.run(['cc','-shared','-fPIC',str(p/'lib.c'),'-o',str(p/'libfixture.so')],check=True)
subprocess.run(['cc',str(p/'main.c'),'-L'+str(p),'-lfixture','-Wl,-rpath,$ORIGIN','-o',str(p/'llama-server')],check=True)
for name in ['llama-cli','llama-quantize','llama-bench']: shutil.copy2(p/'llama-server',p/name)
(p/'lib.c').unlink();(p/'main.c').unlink()
''')
        cmake.chmod(0o755)
        self.script = self.root / 'updater'
        text = SOURCE.read_text().replace('repo=/home/halbritt/git/llama.cpp', 'repo='+str(self.repo)).replace('state_dir=/home/halbritt/.local/state/llama-cpp-update', 'state_dir='+str(self.state)).replace('toolkit=/usr/local/cuda-13.4', 'toolkit='+str(toolkit))
        self.script.write_text(text)
        self.script.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin)+':'+os.environ['PATH'])
        legacy = self.state / 'worktree/build/bin'
        legacy.mkdir(parents=True)
        (legacy / 'library').write_text('serving inode')

    def git(self, *args):
        return subprocess.check_output(['git', *args], text=True, stderr=subprocess.DEVNULL)

    def commit(self, value):
        (self.remote / 'source').write_text(value)
        self.git('-C', str(self.remote), 'add', 'source')
        self.git('-C', str(self.remote), 'commit', '-qm', value)

    def run_update(self, *args, fail=False):
        env = dict(self.env)
        if fail:
            env['FAIL_BUILD'] = '1'
        return subprocess.run([str(self.script), *args], env=env, text=True, capture_output=True)

    def test_stage_publish_and_failed_next_build_preserve_serving_bundle(self):
        result = self.run_update('--stage')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.state / 'current').exists())
        self.assertEqual(self.git('-C', str(self.repo), 'rev-parse', 'HEAD').strip(), self.old)
        self.assertEqual(self.run_update().returncode, 0)
        release = (self.state / 'current').resolve()
        self.assertTrue((release / 'bin/libfixture.so').exists())
        self.assertEqual(subprocess.run([release / 'bin/llama-server']).returncode, 0)
        self.assertFalse(list(self.state.glob('build.*')))
        self.commit('third')
        self.assertNotEqual(self.run_update(fail=True).returncode, 0)
        self.assertEqual((self.state / 'current').resolve(), release)
        self.assertEqual((self.state / 'worktree/build/bin/library').read_text(), 'serving inode')

    def test_changed_bundle_is_not_published(self):
        self.assertEqual(self.run_update('--stage').returncode, 0)
        release = self.state / 'releases' / (self.target+'-cuda13.4')
        (release / 'bin/libfixture.so').write_text('corrupt')
        self.assertNotEqual(self.run_update().returncode, 0)
        self.assertFalse((self.state / 'current').exists())
        self.assertEqual(self.git('-C', str(self.repo), 'rev-parse', 'HEAD').strip(), self.old)
