# Services

This directory holds desired state for operational systems managed independently
of one host. Use one stable, lowercase kebab-case directory per service and
document the hosts or devices that currently realize it.

For example, a future Home Assistant configuration can live here while the
machine or appliance running Home Assistant remains in `hosts/` or `devices/`.
Host-specific units and overrides stay with the host. Do not import credentials,
access tokens, backup keys, or decrypted secret files. Follow
[`docs/importing-resources.md`](../docs/importing-resources.md) when a service
already has a repository.
