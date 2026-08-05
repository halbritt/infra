---
status: accepted
---

# Use infra as the repository identity

The repository is named `infra` because its scope includes more than a machine
fleet: local and remote hosts, managed devices, service-level systems, and
external providers. The hostname `proximal` remains the stable identity of the
original workstation under `hosts/proximal/`; `fleet` remains a term for a group
of like resources, not the repository as a whole. This preserves host identity
while allowing Home Assistant, printers, network gear, and providers such as
Runpod to be represented without pretending that each is a machine.

Renaming the existing repository and checkout preserves its Git history. New
resource categories are added only when real configuration or evidence exists;
the repository does not pre-populate invented resources.
