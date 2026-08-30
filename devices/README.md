# Devices

This directory holds desired state and operational evidence for managed
appliances such as printers, routers, switches, and sensor hubs. Use one stable,
lowercase kebab-case directory per device. Each device has a matching
`device.yaml`, `README.md`, `notes.md`, and `CHANGELOG.md`. Keep credentials out
of plaintext Git and document the external secret or encrypted-file installation
path.

Current devices:

- [`home-assistant-fernside/`](home-assistant-fernside/) — the Home Assistant
  installation at Fernside, currently running on a Yellow appliance; its
  network hostname is recorded separately from its stable resource name.
- [`omezizy-d450/`](omezizy-d450/) — the 4x6 direct-thermal label printer
  USB-attached to `proximal` (QIN `2e3c:5756`, TSPL `XPP,XL`, 203 dpi); driven
  by native TSPL for bin labels and the vendor filter for raster PDFs.

Use `hosts/` instead when the resource is managed primarily as a general-purpose
operating-system instance. Do not add an example device until its real
configuration or evidence is available. Follow
[`docs/importing-resources.md`](../docs/importing-resources.md) when a device
already has a repository.
