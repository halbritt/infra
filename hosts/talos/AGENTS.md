# talos

Read `machine.yaml`, `README.md`, `notes.md`, and the target subsystem README
before changes. Headless Ubuntu server. Since 2026-10-22 its role is agent-ee
fleet worker host: proximal's burndown launcher runs Claude and Codex workers
here over ssh (`launch.py --host talos`). It reaches the network only over
Wi-Fi, so a networking change can strand it. Keep a working Tailscale or LAN
path, and prefer `netplan try` over `netplan apply`. Credentials (Wi-Fi PSK in
netplan, Tailscale state, CLI logins) stay outside Git.

- CLI logins arrive only from proximal's `claude-oauth-refresh` and
  `codex-auth-mirror` timers as access-token-only copies. Never log a CLI in
  here and never copy a refresh token here.
- Run agent-ee tests through `ae-ci-exec`; native KiCad/ngspice/poppler are
  diagnostic only.
- `docker.io`, `docker-buildx` and the KiCad packages are held. Upgrade them in
  step with the other worker hosts.
- Do not open firewall ports.
