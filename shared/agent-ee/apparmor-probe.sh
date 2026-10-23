#!/bin/sh
# AGENTEE-438 candidate probe: label, unix sockets, nested bwrap, native KiCad (no provider calls)
set -u
B=/opt/kicad-route/reports/routing-engine/inputs/four-layer-plane/four-layer-plane.kicad_pcb
O=$(mktemp -d)
step() { if "$@" >/dev/null 2>&1; then echo "PASS $*" | cut -c1-90; else echo "FAIL($?) $*" | cut -c1-90; fi; }
echo "label: $(cat /proc/self/attr/current)"
step python3 -c 'import socket; a,b=socket.socketpair(); socket.socket(socket.AF_UNIX).close()'
step kicad-cli pcb drc --format json --output $O/drc.json $B
step kicad-cli pcb export svg --layers F.Cu --output $O/top.svg $B
BW="bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --unshare-pid --unshare-user"
echo "bwrap1 label: $($BW cat /proc/self/attr/current)"
step $BW python3 -c 'import socket; socket.socketpair(); socket.socket(socket.AF_UNIX).close()'
step $BW sh -c "kicad-cli pcb drc --format json --output /tmp/d.json $B"
step $BW sh -c "kicad-cli pcb export svg --layers F.Cu --output /tmp/t.svg $B"
echo "bwrap2 label: $($BW $BW cat /proc/self/attr/current)"
step $BW $BW python3 -c 'import socket; socket.socketpair()'
