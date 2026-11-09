#!/usr/bin/env bash
# Install the archon side of imessage-vm from this directory (run on archon as root).
set -euo pipefail
cd "$(dirname "$0")"
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
install -d -m 0755 /usr/local/lib/imessage-vm /etc/imessage-vm
install -m 0755 bin/imessage-vm-run bin/imessage-vm-stop bin/imessage-vm-ctl bin/imessage-vm-build-boot \
  bin/imessage-vm-init-identity bin/imessage-vm-guest bin/verify-chunklist.py bin/bb-readonly-proxy \
  /usr/local/lib/imessage-vm/
install -m 0644 opencore/render-config.py upstream.lock /usr/local/lib/imessage-vm/
[[ -f /etc/imessage-vm/vm.conf ]] || install -m 0644 etc/vm.conf /etc/imessage-vm/vm.conf
diff -u etc/vm.conf /etc/imessage-vm/vm.conf || echo "note: /etc/imessage-vm/vm.conf differs from the repo copy (kept)"
ln -sf /usr/local/lib/imessage-vm/imessage-vm-ctl /usr/local/bin/imessage-vm-ctl
ln -sf /usr/local/lib/imessage-vm/imessage-vm-guest /usr/local/bin/imessage-vm-guest
rm -rf /usr/local/share/imessage-vm/guest
install -d -m 0755 /usr/local/share/imessage-vm
cp -r guest /usr/local/share/imessage-vm/guest
chmod -R a+rX /usr/local/share/imessage-vm
for u in systemd/*.service; do install -m 0644 "$u" /etc/systemd/system/; done
systemctl daemon-reload
# Client token for the read-only BlueBubbles gateway (never the BB password).
tok=/var/lib/imessage-vm/identity/bb-readonly-token
if [[ -d /var/lib/imessage-vm/identity && ! -s $tok ]]; then
  (umask 077; python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$tok")
  chown imsgvm:imsgvm "$tok"; chmod 0600 "$tok"
  echo "generated $tok"
fi
echo "installed; enable with: systemctl enable imessage-vm.service"
