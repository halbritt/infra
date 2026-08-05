# Providers

This directory holds provider-level policy, reusable resource declarations, and
operational evidence for external infrastructure control planes such as Runpod.
Use one stable, lowercase kebab-case directory per provider.

Provider credentials remain outside plaintext Git or in an approved SOPS/age
workflow. A long-lived provisioned machine may also have a record under
`hosts/` when host-level desired state and history matter.
