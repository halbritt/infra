#!/bin/sh
# Readiness (1) on talos: kicad-route's source, extension and interpreter identities INSIDE the qualified
# image, under native-admit (class test, weight 1: a light single-process probe; lease label, --cpus,
# --pids-limit, tini PID 1). Exits non-zero if any identity check fails. Run on talos:
#   sh observe-router.sh   (with router-identity-check.sh next to it)
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
exec ~/.local/bin/native-admit run --label "talos-qual router-identity d96f8e00" --class test --weight 1 -- sh -c '
  exec docker run --rm --network none --label native-admission.lease=$NATIVE_ADMISSION_LEASE \
    --cpus $NATIVE_ADMISSION_CPUS --pids-limit $NATIVE_ADMISSION_PIDS --entrypoint /usr/bin/tini \
    -v "'"$HERE"'/router-identity-check.sh:/check.sh:ro" agent-ee:ee466-gate-b29cead1 -- sh /check.sh'
