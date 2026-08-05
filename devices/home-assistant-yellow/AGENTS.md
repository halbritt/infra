# Home Assistant Yellow instructions

This directory is the canonical desired-state and operational record for the
Home Assistant Yellow appliance named `home-assistant-yellow`. Read
[`device.yaml`](device.yaml), [`README.md`](README.md), [`notes.md`](notes.md),
and the relevant subsystem documentation before changing it.

- Treat `home-assistant-yellow` as the stable resource name and `homeassistant`
  as the currently observed hostname. A repository rename is not proof of a live
  network rename.
- Inventory and read-only probes do not authorize automation, integration,
  add-on, device-control, or network mutations.
- Preserve HAOS, Supervisor, add-on, Thread, Matter, Zigbee, and Tailscale
  recovery behavior unless current evidence and explicit authority justify a
  change.
- Never commit Home Assistant tokens, private MCP URLs, `secrets.yaml`, add-on
  credentials, backup keys, SSH keys, or decrypted secret material.
- Keep appliance-specific state here. Move service-level Home Assistant state
  under `services/` only when it has an independently managed lifecycle.
- Record current observations separately from historical inventory snapshots.
- Commit and push through `github.com/halbritt/infra`; the standalone source
  repository is historical provenance, not the destination for new work.
