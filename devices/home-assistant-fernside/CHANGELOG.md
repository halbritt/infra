# Home Assistant at Fernside changelog

## 2026-08-31

### Extended Recorder history and reduced SQLite commit frequency

Added explicit Recorder policy to the canonical Core configuration:
`purge_keep_days: 30` retains raw states and events for 30 days, and
`commit_interval: 30` replaces the five-second default to reduce routine disk
writes. Recorder remains the source for native Home Assistant History,
Activity, dashboard history cards, events, and long-term statistics; the
separate VictoriaMetrics migration does not replace it.

A full local appliance backup was created before installation. The rollback is
the pre-change `/config/configuration.yaml` plus that backup; configuration
validation and post-restart Recorder/History checks are required before this
change is considered operationally complete.

## 2026-08-12

### Re-enabled the plant watering automation as a redundant channel

Turned `automation.plant_drying_rate_has_slowed` ("Plant needs water — per-plant
rewater point") back on, reversing the 2026-07-23 decision that made Praxis the
sole watering channel. Cause: the proximal `plant-praxis-bridge` stopped firing
for 5 days across the 2026-08-07 reboot and nothing surfaced the outage, so
Praxis is not yet trusted as a single path. Duplicate alerts with Praxis are
expected and deliberate; retire this again only once the bridge has proven it
survives reboots.

Two changes beyond flipping it on:

- Added the missing **Dracaena Michiko** trigger (`below: 20`, `for: 06:00:00`).
  That plant was paired 2026-07-29, six days *after* this automation was
  disabled, so it had never been represented here — re-enabling as-is would have
  silently left one plant uncovered on this channel.
- Set `initial_state: true` (was `false`). Left at `false` the automation would
  have switched itself back off at the next HA restart, which is precisely the
  silent-failure shape being guarded against.

Verified: state `on`, six `numeric_state` triggers, action `notify.notify`
fanning out to `notify.dont_panic` and `notify.moto_g_power_5g_2024`.

Known gap: this channel covers THIRSTY only. A dark sensor never crosses a
numeric threshold, so staleness detection remains exclusive to the bridge's DARK
check. `sensor.ficus_audrey_top_soil_moisture` reads `unavailable` right now
(silent since 2026-08-07 02:14Z) — a battery/sensor fault to chase separately.

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
