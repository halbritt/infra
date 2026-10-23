#!/bin/sh
# Runs INSIDE agent-ee:ee466-gate-b29cead1 (mounted read-only by observe-router.sh). Prints each kicad-route
# identity and exits non-zero if ANY required one differs from the qualified value or a verification fails.
# KR overrides /opt/kicad-route and VERIFY the install.sh path, for tests only.
KR=${KR:-/opt/kicad-route}; VERIFY=${VERIFY:-/usr/local/share/agent-ee/kicad-route/install.sh}
WANT_COMMIT=b5774496d8466b67ffa0362b6665fee2108155a3
WANT_EXT=ec5fb733d321343456917b2925ec275af233e3a44d34b2f332800d51352b2cd9
WANT_SRC=9cfc5d5e9369fd044ac6555afe57bdc4ccc829421e5496d42599c2d4a71951b2
WANT_PY=3.12.3
fail=0
check() { # check NAME GOT WANT
  if [ "$2" = "$3" ]; then echo "PASS $1 = $2"; else echo "FAIL $1 = ${2:-<none>} (want $3)"; fail=1; fi
}
cd "$KR" || { echo "FAIL kicad-route dir $KR missing"; exit 1; }
echo "pid1=$(cat /proc/1/comm 2>/dev/null)"
check kicad_route_commit "$(git rev-parse HEAD 2>/dev/null)" "$WANT_COMMIT"
check kicad_route_dirty "$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')" 0
check extension_sha256 "$(sha256sum .venv-krt/lib/python3.12/site-packages/grid_router.so 2>/dev/null | cut -d' ' -f1)" "$WANT_EXT"
check manifest_source_sha256 "$(python3 -c 'import json; print(json.load(open("manifest.json"))["krt"]["source_sha256"])' 2>/dev/null)" "$WANT_SRC"
check manifest_extension_sha256 "$(python3 -c 'import json; print(json.load(open("manifest.json"))["krt"]["extension_module"]["sha256"])' 2>/dev/null)" "$WANT_EXT"
check interpreter_version "$(.venv-krt/bin/python -c 'import platform; print(platform.python_version())' 2>/dev/null)" "$WANT_PY"
if "$VERIFY" verify >/dev/null 2>&1; then echo "PASS install_sh_verify (recomputes the source identity)"; else echo "FAIL install_sh_verify"; fail=1; fi
if .venv-krt/bin/python -c 'import grid_router' 2>/dev/null; then echo "PASS grid_router import"; else echo "FAIL grid_router import"; fail=1; fi
[ $fail = 0 ] && echo "router identity: PASS" || echo "router identity: FAIL"
exit $fail
