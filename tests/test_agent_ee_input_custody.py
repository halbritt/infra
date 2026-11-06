"""Execute the runner's fetch/mount boundary with owned Git and HTTP fixtures."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

LIBRARY = Path(__file__).resolve().parents[1] / 'shared/agent-ee/native-input-fetch.sh'


class RunnerInputCustodyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='ae-custody-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repository = self.root / 'owned-repository'
        self.repository.mkdir()
        self.git = shutil.which('git')
        for args in [('init', '-q'), ('add', '.'), ('commit', '--allow-empty', '-qm', 'owned input')]:
            subprocess.run([self.git, '-C', str(self.repository), '-c', 'user.name=fixture',
                            '-c', 'user.email=fixture@invalid', *args], check=True, capture_output=True)
        self.commit = subprocess.check_output([self.git, '-C', str(self.repository), 'rev-parse', 'HEAD'], text=True).strip()
        self.state = self.root / 'state'
        (self.state / 'inputs').mkdir(parents=True)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'calls.jsonl'
        fixture = '''import json,os,pathlib,subprocess,sys
args=sys.argv[1:]
kind=pathlib.Path(sys.argv[0]).name
with open(os.environ['CUSTODY_LOG'],'a') as out:
 out.write(json.dumps({'tool':kind,'argv':args,'git_environment':{k:os.environ.get(k) for k in ['GIT_CONFIG_GLOBAL','GIT_CONFIG_NOSYSTEM','GIT_TERMINAL_PROMPT']}})+'\\n')
if kind=='git':
 if 'clone' in args:
  args[-2]=os.environ['CUSTODY_SOURCE']
 result=subprocess.run([os.environ['CUSTODY_REAL_GIT'],*args])
 if result.returncode==0 and 'clone' in args and os.environ.get('CUSTODY_MODE')=='credential':
  subprocess.run([os.environ['CUSTODY_REAL_GIT'],'-C',args[-1],'config','credential.helper','owned-forbidden-helper'],check=True)
 raise SystemExit(result.returncode)
url=args[-3] if args[-2]=='--output' else ''
if not url.startswith('https://'):raise SystemExit(1)
mode=os.environ.get('CUSTODY_MODE','ok')
pathlib.Path(args[args.index('--output')+1]).write_bytes(b'wrong' if mode=='damaged' else b'owned drawing\\n')
if mode=='timeout':raise SystemExit(28)
'''
        for name in ('git', 'curl'):
            path = self.bin / name
            path.write_text('#!' + sys.executable + '\n' + fixture)
            path.chmod(0o755)
        self.env = {**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH'],
                    'STATE': str(self.state), 'FOME_MC_COMMIT': self.commit,
                    'J1_DRAWING_URL': 'https://fixture.invalid/drawing.pdf',
                    'J1_DRAWING_SHA256': hashlib.sha256(b'owned drawing\n').hexdigest(),
                    'CUSTODY_SOURCE': str(self.repository), 'CUSTODY_REAL_GIT': self.git,
                    'CUSTODY_LOG': str(self.log)}

    def run_fetch(self, mode='ok'):
        script = '''set -euo pipefail
prog=owned-ae-ci-exec
die() { echo "$*" >&2; exit 2; }
source "$1"
fetch_inputs
required_input_mounts
printf '%s\\0' "${REQUIRED_INPUT_MOUNTS[@]}"
'''
        return subprocess.run(['bash', '-c', script, 'fixture', str(LIBRARY)],
                              env={**self.env, 'CUSTODY_MODE': mode}, capture_output=True, timeout=30)

    def test_anonymous_pinned_fetch_https_guards_and_read_only_mounts_are_executed(self):
        result = self.run_fetch()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        clone = next(call for call in calls if 'clone' in call['argv'])
        self.assertIn('credential.helper=', clone['argv'])
        self.assertIn('http.extraheader=', clone['argv'])
        self.assertEqual(clone['git_environment'], {'GIT_CONFIG_GLOBAL': '/dev/null',
                                                   'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TERMINAL_PROMPT': '0'})
        curl = next(call['argv'] for call in calls if call['tool'] == 'curl')
        for flag, value in [('--proto', '=https'), ('--max-time', '90'), ('--max-filesize', '10000000')]:
            self.assertEqual(curl[curl.index(flag)+1], value)
        self.assertIn('--location', curl)
        self.assertTrue(curl[curl.index('--user-agent')+1])
        mounts = result.stdout.decode().split('\0')[:-1]
        self.assertEqual(mounts, ['-v', f'{self.state}/inputs/fome-mc-{self.commit}:/opt/fome-mc:ro',
                                  '-v', f'{self.state}/inputs/te-776228-1.pdf:/opt/j1/te-776228-1.pdf:ro'])
        drawing = self.state / 'inputs/te-776228-1.pdf'
        self.assertEqual(drawing.read_bytes(), b'owned drawing\n')
        self.assertEqual(drawing.stat().st_mode & 0o777, 0o444)

    def test_damaged_or_timed_out_drawing_is_never_published(self):
        for mode in ('damaged', 'timeout'):
            with self.subTest(mode=mode):
                result = self.run_fetch(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.state / 'inputs/te-776228-1.pdf').exists())
                self.assertNotIn(b'/opt/fome-mc:ro', result.stdout)
                self.assertNotIn(b'/opt/j1/te-776228-1.pdf:ro', result.stdout)

    def test_persisted_clone_credentials_refuse_before_drawing_fetch(self):
        result = self.run_fetch('credential')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(b'credentials persisted', result.stderr)
        self.assertFalse(any(json.loads(line)['tool'] == 'curl' for line in self.log.read_text().splitlines()))
        self.assertFalse(result.stdout)

    def test_missing_declared_input_refuses_before_any_docker_process_and_journals_no_start(self):
        source = LIBRARY.parent
        runner_dir = self.root / 'runner'
        runner_dir.mkdir()
        for name in ('ae-ci-exec', 'ae-ci-outcome.py', 'native-inputs.py', 'native-input-policy.json', 'native-input-fetch.sh'):
            shutil.copy2(source / name, runner_dir / name)
        admission = runner_dir / 'native-admit'
        admission.write_text('#!/bin/bash\nif [ "$1" = verify ]; then exit 0; fi\nwhile [ "$1" != -- ]; do shift; done\nshift\nexec "$@"\n')
        admission.chmod(0o755)
        docker = self.bin / 'docker'
        docker_log = self.root / 'docker-called'
        docker.write_text('#!/bin/bash\ntouch "'+str(docker_log)+'"\nexit 99\n')
        docker.chmod(0o755)
        checkout = self.root / 'checkout'
        (checkout / '.github/workflows').mkdir(parents=True)
        (checkout / 'scripts').mkdir()
        shutil.copy2(source / 'native-input-policy.json', checkout / 'scripts/native-input-policy.json')
        (checkout / 'Dockerfile').write_text('FROM owned-fixture\n')
        (checkout / '.github/workflows/ci.yml').write_text(
            f'FOME_MC_COMMIT: {self.commit}\nJ1_DRAWING_SHA256: {self.env["J1_DRAWING_SHA256"]}\n'
            'J1_DRAWING_URL: https://fixture.invalid/drawing.pdf\n')
        for args in [('init','-q'),('add','.'),('commit','-qm','owned source')]:
            subprocess.run([self.git,'-C',str(checkout),'-c','user.name=fixture','-c','user.email=fixture@invalid',*args],
                           check=True,capture_output=True)
        manifest = self.root / 'missing-input.json'
        manifest.write_text(json.dumps({'schema':'agent-ee.native-inputs/1','inputs':[
            {'name':'pcbschemagen','env':'PCBSCHEMAGEN_ROOT','path':str(self.root/'absent-verifier'),'git':True}]}))
        journal = self.root / 'outcome.json'
        evidence = self.root / 'evidence'
        result = subprocess.run([str(runner_dir/'ae-ci-exec'),str(checkout),'--','true'],
                                env={**self.env,'AE_CI_EXEC_HOME':str(self.state),
                                     'AE_CI_INPUT_MANIFEST':str(manifest),'AE_CI_EVIDENCE_DIR':str(evidence),
                                     'AE_CI_OUTCOME_FILE':str(journal)},capture_output=True,timeout=30)
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertFalse(docker_log.exists())
        outcome = json.loads(journal.read_text())
        self.assertTrue(outcome['complete'])
        self.assertEqual(outcome['state'],'not_started')
        failed = list(evidence.glob('failed-*/native-inputs.json'))
        self.assertEqual(len(failed),1)
        self.assertEqual(json.loads(failed[0].read_text())['status'],'failed')


if __name__ == '__main__':
    unittest.main()
