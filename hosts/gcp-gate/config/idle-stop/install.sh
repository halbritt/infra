#!/bin/sh
# Install the idle stop on agent-ee-gate-c4. Run from proximal:
#   tar -c -C ~/git/infra/hosts/gcp-gate/config/idle-stop . | ssh agent-ee-gate-c4 'd=$(mktemp -d) && tar -x -C "$d" && sudo sh "$d/install.sh" "$d"; rm -r "$d"'
set -eu
src=${1:-.}
install -m 0755 "$src/infra-idle-stop" /usr/local/sbin/infra-idle-stop
install -m 0644 "$src/infra-idle-stop.service" "$src/infra-idle-stop.timer" /etc/systemd/system/
install -m 0644 "$src/infra-usage.logrotate" /etc/logrotate.d/infra-usage
install -d -m 0755 /var/log/infra-usage
systemctl daemon-reload
systemctl enable --now infra-idle-stop.timer
