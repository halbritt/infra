#!/bin/sh
# Install native-admit, its per-host config and ae-ci-exec on the agent-ee hosts.
# Run on proximal from infra shared/agent-ee: ./install-native-admission.sh [--tool-only] [HOST...]
# --tool-only installs native-admit and its config but leaves ae-ci-exec as it is.
set -eu
cd "$(dirname "$0")"
tool_only=0; [ "${1:-}" = --tool-only ] && { tool_only=1; shift; }
[ $# -gt 0 ] || set -- proximal peecee-wsl archon talos agent-ee-gate-c4
for host in "$@"; do
  cfg=$(python3 -c "import json,sys; print(json.dumps(json.load(open('native-admission.json'))[sys.argv[1]]))" "$host")
  files="native-admit"; [ "$tool_only" = 1 ] || files="$files ae-ci-exec"
  if [ "$host" = proximal ]; then run="sh -c"; else run="ssh -o BatchMode=yes $host"; fi
  tar -c $files | $run "set -e; d=\$(mktemp -d); tar -x -C \$d; mkdir -p ~/.local/bin ~/.config/native-admission
    printf '%s\n' '$cfg' > ~/.config/native-admission/config.json
    for f in $files; do install -m 0755 \$d/\$f ~/.local/bin/\$f.new && mv ~/.local/bin/\$f.new ~/.local/bin/\$f; done; rm -r \$d
    echo \"$host: \$(cd ~/.local/bin && sha256sum $files | cut -c1-16 | tr '\n' ' ')\""
done
