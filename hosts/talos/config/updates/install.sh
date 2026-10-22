#!/bin/sh
# Install talos's update policy from this directory. Run on talos as root.
set -eu
cd "$(dirname "$0")"
install -m 0644 52infra-unattended-upgrades /etc/apt/apt.conf.d/52infra-unattended-upgrades
install -m 0644 50-infra-container-runtime.conf /etc/needrestart/conf.d/50-infra-container-runtime.conf
install -m 0755 infra-reboot-if-idle /usr/local/sbin/infra-reboot-if-idle
install -m 0644 infra-reboot-if-idle.service infra-reboot-if-idle.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now infra-reboot-if-idle.timer
