# Host notes

## Initial observation — 2026-09-15

The owner requested Tailscale setup over the newly enabled Windows OpenSSH server.
SSH to `User@192.168.1.116` reported hostname `USERPAS-GBB8OPO`, Windows 10 Pro
build 19045, 64-bit, and an elevated administrator session. `sshd` was running
with automatic startup. No Tailscale service or default-path executable existed.

The resource name follows the observed hostname; no Windows rename was requested.
The supplied SSH password remains outside Git on the operator host.

## Requested rename — 2026-09-15

The owner selected `truck-pc` for the computer, `halbritt` for the existing `User`
login, and Heath Albritton for its display name. Moved the repository resource to
`hosts/truck-pc/`, preserving its history. The laptop was offline when applying
was attempted; live names remain unverified and the rename recipe is prepared.

The owner reports previously finding the laptop powered off and is unsure whether
it sleeps or has a hardware problem. They were away from the machine during this
attempt. Tailscale reported it offline, last seen at 2026-09-16 01:30 UTC; both
LAN and tailnet SSH failed. These observations do not distinguish sleep,
shutdown, power loss, or a hardware fault. When reachable, inspect Windows power
and shutdown events and power settings before changing sleep behavior or
attributing the problem to hardware.
