#!/bin/bash
# Run as root inside the WSL Ubuntu distro:
#   wsl -d Ubuntu -u root -- bash /mnt/c/Users/halbr/wsl-setup/setup-sshd.sh
# Installs openssh-server on port 2222, key-only auth, authorizes proximal's key.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q openssh-server build-essential
cat > /etc/ssh/sshd_config.d/10-wsl.conf <<'CONF'
Port 2222
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
CONF
install -d -m 700 -o halbritt -g halbritt /home/halbritt/.ssh
install -m 600 -o halbritt -g halbritt "$HERE/authorized_keys" /home/halbritt/.ssh/authorized_keys
install -m 644 "$HERE/wsl.conf" /etc/wsl.conf
echo 'halbritt ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/halbritt-nopasswd
chmod 440 /etc/sudoers.d/halbritt-nopasswd
systemctl enable --now ssh
systemctl --no-pager status ssh | head -5
ss -ltnp | grep 2222
