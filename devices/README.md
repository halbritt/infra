# Devices

This directory holds desired state and operational evidence for managed
appliances such as printers, routers, switches, and sensor hubs. Use one stable,
lowercase kebab-case directory per device. Each device has a matching
`device.yaml`, `README.md`, `notes.md`, and `CHANGELOG.md`. Keep credentials out
of plaintext Git and document the external secret or encrypted-file installation
path.

Current devices:

- [`home-assistant-yellow/`](home-assistant-yellow/) — the Home Assistant Yellow
  appliance; its current network hostname is recorded separately from its stable
  resource name.

Use `hosts/` instead when the resource is managed primarily as a general-purpose
operating-system instance. Do not add an example device until its real
configuration or evidence is available. Follow
[`docs/importing-resources.md`](../docs/importing-resources.md) when a device
already has a repository.
