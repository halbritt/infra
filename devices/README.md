# Devices

This directory holds desired state and operational evidence for managed
appliances such as printers, routers, switches, and sensor hubs. Use one stable,
lowercase kebab-case directory per device. Keep credentials out of plaintext
Git and document the external secret or encrypted-file installation path.

Use `hosts/` instead when the resource is managed primarily as a general-purpose
operating-system instance. Do not add an example device until its real
configuration or evidence is available. Follow
[`docs/importing-resources.md`](../docs/importing-resources.md) when a device
already has a repository.
