#!/bin/sh
# Readiness (2) on talos: fome-mc's pinned environment inside fome-runtime:d96f8e00, under one
# native-admit lease. Isolated checkouts in ~/.cache/fome-qualify (fome-mc, kicad-libraries). Steps:
#   bootstrap  toolchain/bootstrap.sh --no-apt (uv sync --frozen, kicad shim, kicad-happy pin, skills, doctor);
#              network only for PyPI and the pinned kicad-happy clone
#   doctor     make doctor, --network none
#   smoke      make smoke (RC fixture), --network none
# STEPS="doctor smoke" runs a subset. The Universal-112 donor (a doctor-required project) is staged at
# ~/.cache/fome-qualify/home/git/Polygonus-Universal-112 (HOME=/work/home in the container).
# Logs: ~/.cache/fome-qualify/logs/<step>.log and .rc. Canonical source: infra hosts/talos/config/fome-runtime/.
set -u
Q=$HOME/.cache/fome-qualify; mkdir -p "$Q/logs" "$Q/uv-cache"
export STEPS="${STEPS:-bootstrap doctor smoke}"
exec ~/.local/bin/native-admit run --label "talos-qual fome-runtime d96f8e00" --weight 1 -- sh -c '
  Q=$HOME/.cache/fome-qualify
  run() { # run STEP NETWORK COMMAND
    step=$1 net=$2; shift 2
    docker run --rm --network "$net" --label native-admission.lease=$NATIVE_ADMISSION_LEASE \
      --cpus $NATIVE_ADMISSION_CPUS --pids-limit $NATIVE_ADMISSION_PIDS --user "$(id -u):$(id -g)" \
      -e HOME=/work/home -e UV_CACHE_DIR=/work/uv-cache -e FOME_KICAD_LIBS=/work/kicad-libraries \
      -v "$Q:/work" -w /work/fome-mc fome-runtime:d96f8e00 sh -c "mkdir -p /work/home; $*" \
      > "$Q/logs/$step.log" 2>&1
    echo $? > "$Q/logs/$step.rc"; echo "$step rc=$(cat $Q/logs/$step.rc)"
  }
  for step in ${STEPS:-bootstrap doctor smoke}; do
    case $step in
      bootstrap) run bootstrap bridge "bash toolchain/bootstrap.sh --no-apt" ;;
      doctor) run doctor none "make doctor" ;;
      smoke) run smoke none "make smoke" ;;
    esac
  done
'
