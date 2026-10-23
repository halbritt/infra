#!/bin/sh
# Readiness (2) on talos: fome-mc's pinned environment inside fome-runtime:d96f8e00. Each step is its own
# native-admit lease with the class/weight of its actual work; the run stops at the first failing step and
# exits with its status (logs and .rc kept). Isolated checkouts in ~/.cache/fome-qualify (fome-mc,
# kicad-libraries, home/git/Polygonus-Universal-112).
#   bootstrap  class test  w1  toolchain/bootstrap.sh --no-apt; network for PyPI and the pinned kicad-happy clone
#   doctor     class test  w1  make doctor, --network none
#   smoke      class suite w2  make smoke (RC fixture pytest + KiCad), --network none
# STEPS="doctor smoke" runs a subset. Logs: ~/.cache/fome-qualify/logs/<step>.log and .rc.
# Canonical source: infra hosts/talos/config/fome-runtime/.
set -u
Q=${FOME_QUALIFY_DIR:-$HOME/.cache/fome-qualify}; NA=${NATIVE_ADMIT:-$HOME/.local/bin/native-admit}
mkdir -p "$Q/logs" "$Q/uv-cache" "$Q/home"
step() { # step NAME CLASS WEIGHT NETWORK COMMAND
  name=$1 class=$2 weight=$3 net=$4; shift 4
  "$NA" run --label "fome-qual $(hostname -s) $name d96f8e00" --class "$class" --weight "$weight" -- sh -c '
    exec docker run --rm --network "$0" --label native-admission.lease=$NATIVE_ADMISSION_LEASE \
      --cpus $NATIVE_ADMISSION_CPUS --pids-limit $NATIVE_ADMISSION_PIDS --user "$(id -u):$(id -g)" \
      -e HOME=/work/home -e UV_CACHE_DIR=/work/uv-cache -e FOME_KICAD_LIBS=/work/kicad-libraries \
      -v "$1:/work" -w /work/fome-mc fome-runtime:d96f8e00 sh -c "$2"' "$net" "$Q" "$*" > "$Q/logs/$name.log" 2>&1
  rc=$?; echo $rc > "$Q/logs/$name.rc"; echo "$name rc=$rc"; return $rc
}
for s in ${STEPS:-bootstrap doctor smoke}; do
  case $s in
    bootstrap) step bootstrap test 1 bridge "bash toolchain/bootstrap.sh --no-apt" ;;
    doctor) step doctor test 1 none "make doctor" ;;
    smoke) step smoke suite 2 none "make smoke" ;;
    *) echo "unknown step $s" >&2; exit 2 ;;
  esac || { rc=$?; echo "stopped after $s failed (rc $rc); later steps not run" >&2; exit $rc; }
done
echo "all steps passed"
