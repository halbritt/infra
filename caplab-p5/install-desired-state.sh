#!/bin/bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "install-desired-state.sh requires root" >&2
  exit 2
fi

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
install -d -m 0755 /usr/local/libexec/caplab-p5
install -m 0755 "$root/caplab-p5-hostctl.py" /usr/local/libexec/caplab-p5-hostctl
install -m 0755 "$root/bin/"* /usr/local/libexec/caplab-p5/
install -d -m 0750 -o root -g root /etc/caplab-p5
install -m 0644 "$root/SOURCE_COMMIT" /etc/caplab-p5/SOURCE_COMMIT

if ! getent group caplab-p5 >/dev/null; then
  groupadd --system caplab-p5
fi
install -m 0640 -o root -g caplab-p5 "$root/recovery.toml" /etc/caplab-p5/recovery.toml

install -d -m 0755 /etc/systemd/system/restic-backup.service.d
install -d -m 0755 /etc/systemd/system/restic-prune.service.d
install -m 0644 \
  "$root/systemd/restic-backup.service.d/20-caplab-p5-lock.conf" \
  /etc/systemd/system/restic-backup.service.d/20-caplab-p5-lock.conf
install -m 0644 \
  "$root/systemd/restic-prune.service.d/20-caplab-p5-lock.conf" \
  /etc/systemd/system/restic-prune.service.d/20-caplab-p5-lock.conf
install -m 0644 "$root/systemd/caplab-p5-expiry.service" /etc/systemd/system/
install -m 0644 "$root/systemd/caplab-p5-expiry.timer" /etc/systemd/system/
systemctl daemon-reload
