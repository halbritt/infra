#!/bin/sh
# Readiness (1) on talos: observe kicad-route's source, extension and interpreter identities INSIDE the
# qualified image, under native-admit (lease label, --cpus, --pids-limit; tini PID 1). Run on talos.
set -eu
exec ~/.local/bin/native-admit run --label "talos-qual router-identity d96f8e00" --weight 1 -- sh -c '
  docker run --rm --network none --label native-admission.lease=$NATIVE_ADMISSION_LEASE \
    --cpus $NATIVE_ADMISSION_CPUS --pids-limit $NATIVE_ADMISSION_PIDS --entrypoint /usr/bin/tini \
    agent-ee:ee466-gate-b29cead1 -- sh -c "
      cd /opt/kicad-route
      echo pid1=\$(cat /proc/1/comm)
      echo kicad_route_commit=\$(git rev-parse HEAD) dirty=\$(git status --porcelain | wc -l)
      echo extension_sha256=\$(sha256sum .venv-krt/lib/python3.12/site-packages/grid_router.so | cut -d\" \" -f1)
      echo interpreter=\$(readlink -f .venv-krt/bin/python) \$(.venv-krt/bin/python -V 2>&1) sha256=\$(sha256sum \$(readlink -f .venv-krt/bin/python) | cut -c1-16)
      python3 -c \"import json; k=json.load(open(\\\"manifest.json\\\"))[\\\"krt\\\"]; print(\\\"manifest source_sha256=\\\"+k[\\\"source_sha256\\\"], \\\"describe=\\\"+k[\\\"describe\\\"], \\\"extension_sha256=\\\"+k[\\\"extension_module\\\"][\\\"sha256\\\"])\"
      /usr/local/share/agent-ee/kicad-route/install.sh verify >/dev/null 2>&1 && echo install_sh_verify=PASS || echo install_sh_verify=FAIL
      .venv-krt/bin/python -c \"import grid_router; print(\\\"grid_router import OK\\\", getattr(grid_router, \\\"__version__\\\", \\\"\\\"))\"
    "'
