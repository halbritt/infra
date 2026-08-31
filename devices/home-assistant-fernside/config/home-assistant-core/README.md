# Home Assistant Core configuration

Canonical, non-secret configuration for Home Assistant Core on
`home-assistant-fernside`.

## Files and installation

| Repository file | Appliance path |
|---|---|
| `configuration.yaml` | `/config/configuration.yaml` |

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
