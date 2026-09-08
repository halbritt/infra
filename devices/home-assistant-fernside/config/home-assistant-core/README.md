# Home Assistant Core configuration

Canonical, non-secret configuration for Home Assistant Core on
`home-assistant-fernside`.

## Files and installation

| Repository file | Appliance path |
|---|---|
| `configuration.yaml` | `/config/configuration.yaml` |
| `plant-watering-daily.yaml` | One automation in `/config/automations.yaml`, unique ID `1788880838740` |

Install the canonical file through the authenticated Terminal & SSH add-on,
then validate before restarting Core:

```sh
scp -i ~/.ssh/hassio.key configuration.yaml \
  root@100.105.145.26:/config/configuration.yaml.candidate
ssh -i ~/.ssh/hassio.key root@100.105.145.26 \
  'cp /config/configuration.yaml /config/configuration.yaml.rollback && \
   mv /config/configuration.yaml.candidate /config/configuration.yaml && \
   ha core check'
```

If validation fails, restore `configuration.yaml.rollback` before doing
anything else. A successful check authorizes a controlled `ha core restart`,
not deletion of the rollback copy.

## Recorder policy

Recorder remains the authoritative store for native Home Assistant History,
Activity, dashboard history cards, events, and long-term statistics.

- `purge_keep_days: 30` keeps raw states and events for 30 days after the
  nightly purge.
- `commit_interval: 30` reduces routine SQLite commit frequency from the
  five-second default. Home Assistant streams changes to History and Activity
  before the database commit, so the visible UI does not acquire a 30-second
  delay. A sudden power loss can lose up to roughly 30 seconds of database
  writes.

Do not point Recorder at VictoriaMetrics. VictoriaMetrics is a separate,
derived numeric telemetry store for Grafana and the plant reminder bridge.

## VictoriaMetrics export

The `influxdb:` block intentionally contains only integration options and the
34-entity allowlist. Core 2026.8 stores connection details in the integration
config entry and treats YAML connection keys as deprecated. The live entry
points at the authenticated VictoriaMetrics ingress on proximal; its password
is runtime state and is not copied into this repository.

## Credentials

The canonical YAML may reference keys from `/config/secrets.yaml`, but
`secrets.yaml` and its values never enter Git. Keep the appliance copy outside
repository synchronization and include it in Home Assistant backups.

## Daily plant watering reminder

`plant-watering-daily.yaml` is the canonical configuration for
`automation.plant_watering_daily_summary`. Every day at 09:00 in HA's
`America/Los_Angeles` timezone, it reads six moisture sensors and sends one
summary directly through `notify.mobile_app_dont_panic` if any plant is below
its rewater threshold. A plant appears every day while below threshold and
drops out once it reaches the threshold. If the list is empty, no notification
is sent. This is a native daily time trigger; HA must be running at 09:00.

The six entity/threshold pairs match `PLANTS` in the proximal
`plant-praxis-bridge` script, including the Ficus deep probe below 30%.
Retuning a plant must update this file and the bridge. The separate legacy
threshold-crossing HA automation also holds thresholds; its Ficus top-probe
difference is recorded in the investigation below. The daily summary adds to
the existing threshold alerts and Praxis bridge.

Unknown, unavailable, and nonnumeric readings are omitted, never converted to
zero moisture. The summary does not claim that omitted plants are healthy.
Sensor staleness remains the bridge's DARK check. The summary uses current
readings directly, without a six-hour duration wait or bridge deduplication.

Install this single automation through HA's config API, not by replacing
`automations.yaml`: read `ha_config_get_automation` for the identifier above,
then pass the parsed canonical YAML, identifier, and returned `config_hash` to
`ha_config_set_automation`. Read the ha-mcp best-practices guide and supply its
current acknowledgment key. Read the result back and verify the automation is
`on`; check templates with `ha_eval_template` and validate with `ha core check`.
No Core restart is needed. The list-length condition intentionally uses a
template because it checks the computed summary, not an entity state.

Rollback removes only this automation through `ha_config_remove_automation`
with identifier `1788880838740`. The pre-install appliance file is retained at
`/config/automations.yaml.before-plant-daily-20260908`; do not restore the whole
file over later unrelated automation changes.

## Plant notification investigation

The [September 8 investigation](plant-alert-investigation-2026-09-08.md)
records the watering automation, notification traces, a confirmed direct phone
test, and the owner's subsequent discovery of the morning alerts bundled with
other notifications. It is an observation record, not an installed automation
file.
