# teardown.sh: sourced by run-gate.sh and build-image.sh (run-overflow.sh has the same semantics inline).
# Needs gc() (gcloud --project ...) and SPEND (the gcp-spend path) from the caller.

# vm_state VM ZONE: running | gone:<status> | unknown. Only explicit GCE status values from a
# successful describe count; absence needs a successful exact-name listing that comes back empty.
vm_state() {
  local out rc
  out=$(gc compute instances describe "$1" --zone "$2" --format='value(status)' 2>/dev/null); rc=$?
  if [ $rc = 0 ]; then
    case $out in
      RUNNING|PROVISIONING|STAGING|REPAIRING) echo running ;;
      TERMINATED|STOPPING|STOPPED|SUSPENDING|SUSPENDED) echo "gone:$out" ;;
      *) echo unknown ;;
    esac
    return
  fi
  out=$(gc compute instances list --filter="name=$1" --format='value(name)' 2>/dev/null); rc=$?
  if [ $rc = 0 ] && [ -z "$out" ]; then echo gone:not-found; else echo unknown; fi
}

# teardown_vm VM ZONE RES: delete VM, then release budget reservation RES ONLY when successful
# exact-name instance AND disk listings prove both are gone. Otherwise keep RES and return 1.
teardown_vm() {
  local vm=$1 zone=$2 res=$3 out_i out_d rc_i=1 rc_d=1 i
  gc compute instances delete "$vm" --zone "$zone" --quiet >/dev/null 2>&1 ||
    echo "teardown: delete of $vm reported failure; checking what remains" >&2
  for i in 1 2 3; do
    out_i=$(gc compute instances list --filter="name=$vm" --format='value(name)' 2>/dev/null); rc_i=$?
    out_d=$(gc compute disks list --filter="name=$vm" --format='value(name)' 2>/dev/null); rc_d=$?
    [ $rc_i = 0 ] && [ $rc_d = 0 ] && [ -z "$out_i$out_d" ] && break
    sleep "${TEARDOWN_SLEEP:-10}"
  done
  if [ $rc_i = 0 ] && [ $rc_d = 0 ] && [ -z "$out_i$out_d" ]; then
    if [ -n "$res" ] && ! "$SPEND" release "$res" --note "teardown verified: $vm" >/dev/null 2>&1; then
      echo "teardown: $vm verified absent, but releasing reservation $res failed (it stays charged)" >&2
    fi
    echo "teardown verified: no instance or disk named $vm"
    return 0
  fi
  echo "TEARDOWN NOT PROVEN for $vm: instances(rc=$rc_i:${out_i:-none}) disks(rc=$rc_d:${out_d:-none}); reservation ${res:-none} kept" >&2
  return 1
}
