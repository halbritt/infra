#!/usr/bin/env python3
"""Fixed privileged Ubuntu update entrypoint; no caller-supplied commands."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import time

STATE = Path('/var/lib/update-bot-os')
PROTECTED = re.compile(r'^(postgresql|mysql|mariadb|redis|pgbackrest|kube|docker|containerd|nvidia|libnvidia|cuda)')


def approved_origin(version):
    return any(o.origin == 'Ubuntu' and o.archive in ('noble', 'noble-security', 'noble-updates')
               for o in version.origins)


def main():
    import apt
    STATE.mkdir(mode=0o755, exist_ok=True)
    with (STATE / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        stamp = str(time.time_ns())
        run = STATE / stamp
        run.mkdir()
        env = dict(os.environ, DEBIAN_FRONTEND='noninteractive', NEEDRESTART_MODE='l')
        options = ['-o', 'DPkg::Lock::Timeout=600', '-o', 'Dpkg::Options::=--force-confold']
        state = {'started': time.time(), 'status': 'running', 'evidence': str(run)}
        def save():
            body = json.dumps(state, indent=2) + '\n'
            (run / 'status.json').write_text(body)
            temporary = STATE / 'latest.tmp'
            temporary.write_text(body)
            temporary.replace(STATE / 'latest.json')
        save()
        def execute(argv, name):
            with (run / name).open('w') as out:
                subprocess.run(argv, check=True, stdout=out, stderr=subprocess.STDOUT, env=env)
        try:
            execute(['apt-get', *options, 'update'], 'refresh.log')
            cache = apt.Cache()
            candidates = [p for p in cache if p.is_installed and p.is_upgradable]
            selected = [p for p in candidates if not PROTECTED.match(p.name) and approved_origin(p.candidate)]
            state['selected'] = [{'package': p.name, 'before': p.installed.version, 'after': p.candidate.version} for p in selected]
            state['deferred'] = [p.name for p in candidates if p not in selected]
            save()
            if selected:
                specs = [p.name + '=' + p.candidate.version for p in selected]
                argv = ['apt-get', *options, '--no-remove', '--only-upgrade', 'install', *specs]
                execute([*argv[:1], '--simulate', *argv[1:]], 'plan.log')
                plan = (run / 'plan.log').read_text()
                if re.search(r'^Remv ', plan, re.M):
                    raise RuntimeError('APT proposed a removal')
                # Also validate dependencies, not just the requested top-level packages.
                for name, version in re.findall(r'^Inst (\S+)(?: \[[^\]]+\])? \((\S+)', plan, re.M):
                    if PROTECTED.match(name) or name not in cache or version not in cache[name].versions or not approved_origin(cache[name].versions[version]):
                        raise RuntimeError('APT dependency crosses the approved OS scope: ' + name)
                policy = Path('/usr/sbin/policy-rc.d')
                if policy.exists():
                    raise RuntimeError('Existing policy-rc.d requires review; refusing to replace it')
                # Suppress package-script service restarts; needrestart lists deferred activation.
                with policy.open('x') as out:
                    out.write('#!/bin/sh\n# update-bot temporary restart hold\nexit 101\n')
                policy.chmod(0o755)
                try:
                    execute([argv[0], '-y', *argv[1:]], 'install.log')
                finally:
                    policy.unlink()
                execute(['dpkg', '--audit'], 'audit.log')
                if (run / 'audit.log').read_text().strip():
                    raise RuntimeError('dpkg audit reported unfinished state')
                observed = apt.Cache()
                for item in state['selected']:
                    item['observed'] = observed[item['package']].installed.version
                    if item['observed'] != item['after']:
                        raise RuntimeError('Installed version does not match the plan: ' + item['package'])
            state.update(status='completed', finished=time.time(),
                         reboot_required=Path('/var/run/reboot-required').exists())
        except Exception as exc:
            state.update(status='failed', error=str(exc), finished=time.time())
            save()
            raise
        save()
        print(json.dumps(state), flush=True)


if __name__ == '__main__':
    main()
