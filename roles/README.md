# Roles

Roles are reusable responsibility bundles. A host opts into them from
`machine.yaml`. Each role describes invariants and may reference configuration
under `shared/`; it must not point into a particular host.

Roles do not automatically install files. Host subsystem documentation remains
the authority for installation and host-specific overrides.
