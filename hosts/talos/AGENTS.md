# talos

Read `machine.yaml`, `README.md`, `notes.md`, and the target subsystem README
before changes. Headless Ubuntu server. It was an agent-ee worker host from
2026-10-22 to 2026-10-24. The owner retired it from agent-ee on 2026-10-24 for the
striatum-next drive. Do not place agent-ee work, worktrees, images or admission here.
It reaches the network only over
Wi-Fi, so a networking change can strand it. Keep a working Tailscale or LAN
path, and prefer `netplan try` over `netplan apply`. Credentials (Wi-Fi PSK in
netplan, Tailscale state, CLI logins) stay outside Git.

- CLI logins arrive only from proximal's `claude-oauth-refresh` and
  `codex-auth-mirror` timers as access-token-only copies. Never log a CLI in
  here and never copy a refresh token here.
- `docker.io` and `docker-buildx` are held. Upgrade them deliberately.
- Do not open firewall ports.
