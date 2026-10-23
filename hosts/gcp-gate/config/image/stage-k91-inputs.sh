#!/bin/sh
# stage-k91-inputs.sh HOST...: fill each gate host's content-addressed K91 store from proximal.
# For every input in k91-inputs.json: verify the test's pinned file hashes and the tree digest on
# proximal, copy to HOST:~/agent-ee-gate/ci-inputs/k91/<name>-<tree sha256>.partial, verify the
# tree digest there, make it read-only, then rename it into place. An existing store is re-verified.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
[ $# -ge 1 ] || { echo "usage: $0 HOST..." >&2; exit 2; }
TREE='find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -c1-64'
python3 - "$HERE/k91-inputs.json" > /tmp/k91-stage.$$ <<'PY'
import hashlib, json, sys
from pathlib import Path
m = json.load(open(sys.argv[1]))
for name, s in m.items():
    if name.startswith("_") or not isinstance(s, dict):
        continue
    for f, h in s["pinned"].items():
        got = hashlib.sha256((Path(s["source"]) / f).read_bytes()).hexdigest()
        if got != h:
            sys.exit(f"{name}: {f} is {got}, pinned {h}")
    print(name, s["source"], s["tree_sha256"])
PY
while read -r name src tree; do
  got=$(cd "$src" && sh -c "$TREE")
  [ "$got" = "$tree" ] || { echo "$name: source tree $got != $tree" >&2; exit 2; }
  for host in "$@"; do
    dest="agent-ee-gate/ci-inputs/k91/$name-$tree"
    tar -C "$src" -c . | ssh -o BatchMode=yes "$host" "set -e; d=\$HOME/$dest
      if [ -d \"\$d\" ]; then t=\$(cd \"\$d\" && $TREE); [ \"\$t\" = $tree ] || { echo \"$name: existing store altered\" >&2; exit 3; }; cat >/dev/null; echo \"$host: $name present and verified\"; exit 0; fi
      rm -rf \"\$d.partial\"; mkdir -p \"\$d.partial\"; tar -x -C \"\$d.partial\"
      t=\$(cd \"\$d.partial\" && $TREE); [ \"\$t\" = $tree ] || { echo \"$name: copy tree \$t != $tree\" >&2; exit 3; }
      chmod -R a+rX,a-w \"\$d.partial\"; mv \"\$d.partial\" \"\$d\"; echo \"$host: $name staged and verified\""
  done
done < /tmp/k91-stage.$$
rm -f /tmp/k91-stage.$$
