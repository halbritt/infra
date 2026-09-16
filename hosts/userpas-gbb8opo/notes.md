# Host notes

## Initial observation — 2026-09-15

The owner requested Tailscale setup over the newly enabled Windows OpenSSH server.
SSH to `User@192.168.1.116` reported hostname `USERPAS-GBB8OPO`, Windows 10 Pro
build 19045, 64-bit, and an elevated administrator session. `sshd` was running
with automatic startup. No Tailscale service or default-path executable existed.

The resource name follows the observed hostname; no Windows rename was requested.
The supplied SSH password remains outside Git on the operator host.
