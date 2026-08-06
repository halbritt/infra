# Home Assistant at Fernside changelog

## 2026-08-06

### Completed the live hostname migration

Changed the Supervisor host hostname from `homeassistant` to
`home-assistant-fernside` through an authenticated Terminal & SSH add-on shell.
Verified the new mDNS name, key-only SSH, LAN and Tailnet UI, Observer,
fixed-address InfluxDB and ha-mcp listener reachability, and the post-reboot
Tailscale node identity. No checked hostname consumer required a compatibility
alias.

### Installed all available updates

Created a protected pre-update backup, then updated Core to `2026.8.0`, HAOS to
`18.2`, OpenThread Border Router to `3.1.0`, ESPHome Device Builder to
`2026.7.4`, Matter Server to `9.1.1`, Home Assistant MCP Server to installed
version `8.1.1`, and the Midea U Window AC firmware to `0x00000038`.

Rebooted into the HAOS 18.2 slot and verified that Core, Supervisor, Observer,
the UI, and every installed add-on recovered. Supervisor reported no remaining
updates. The Midea OTA completed despite a client timeout and a transient ZHA
unknown-event warning; the update entity confirmed the new firmware with no
operation in progress.

The ha-mcp add-on recovered and its listener was reachable, but the active
Claude configuration lacked the intended user-scope registration and retained
only a legacy project-local entry. This client-side drift remains a separate,
credential-aware follow-up.

## 2026-08-05

### Renamed the installation for its site

Renamed the resource from `home-assistant-yellow` to
`home-assistant-fernside`. Fernside identifies the Home Assistant installation;
Yellow remains its current hardware model. Updated the desired hostname but did
not change the live appliance, which still reports `homeassistant`.

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
