# Home Assistant Yellow changelog

## 2026-08-05

### Imported and assigned a stable resource name

Imported all eight commits from `github.com/halbritt/homeassistant` without
squashing. The infrastructure identity is `home-assistant-yellow` so additional
Home Assistant installations can receive distinct resource names. The live
hostname remains `homeassistant`; no appliance, network, integration, or
automation state changed during the import.

The clean standalone checkout was moved to desktop trash after its tip was
verified as an ancestor of pushed `infra/master`. Its GitHub repository remains
available as historical source provenance.

### Recorded the hostname migration boundary

Audited live mDNS and Tailnet identity plus the known Grafana,
plant-praxis-bridge, and ha-mcp consumers. The fixed-address consumers do not
depend on the generic hostname. Documented the authenticated Supervisor/CLI
operation and its before-and-after probes. The live hostname was not changed:
the registered agent surface does not expose host options and network SSH is
disabled.
