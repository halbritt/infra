# Home Assistant VictoriaMetrics

This is the long-retention numeric telemetry store for the Home Assistant
appliance at Fernside. It is deliberately separate from proximal's operational
VictoriaMetrics instance: Community Edition has one retention period per
instance, while this data needs two years and host monitoring keeps 15 days.

Home Assistant writes through authenticated `vmauth-homeassistant` on the
tailnet. The VictoriaMetrics backend binds loopback only. `vmauth` has two
least-privilege users: a write-only Home Assistant user and a query-only user
shared by Grafana and the plant reminder bridge. The installed auth file and
consumer environment files contain secrets and stay outside Git.

Only 34 allowlisted numeric `sensor.*` entities are retained. Both the Home
Assistant integration and `relabel.yml` enforce the list. Influx measurements
are normalized to:

```text
homeassistant_state_value{db="homeassistant",domain="sensor",entity_id="...",unit="..."}
```

This store does not replace Home Assistant Recorder. Recorder remains the
authority for the native History and Activity interfaces and keeps 30 days of
event/state rows. Home Assistant long-term statistics also remain Recorder
owned.

## Install paths

| Repository file | Installed path |
|---|---|
| `victoriametrics-homeassistant.default` | `/etc/default/victoriametrics-homeassistant` |
| `victoriametrics-homeassistant.service` | `/etc/systemd/system/victoriametrics-homeassistant.service` |
| `relabel.yml` | `/etc/victoria-metrics-homeassistant/relabel.yml` |
| `vmauth-homeassistant.default` | `/etc/default/vmauth-homeassistant` |
| `vmauth-homeassistant.service` | `/etc/systemd/system/vmauth-homeassistant.service` |
| `auth.yml.template` | `/etc/vmauth-homeassistant/auth.yml` after secret substitution |

The operator-custody source values used to build `auth.yml` live in
`/etc/vmauth-homeassistant/credentials.env` (0600 root). Grafana receives only
the reader value in `/etc/grafana/ha-victoriametrics.env`; Home Assistant stores
only the writer value in its InfluxDB integration config entry.

The services use the pinned VictoriaMetrics v1.150.0 binaries documented in
the parent observability README. Install `vmctl-prod` and `vmauth-prod` from the
same verified `vmutils` archive as `vmalert-prod`.

## Runtime and retention

- API ingress: `100.85.100.81:8427` (tailnet only, HTTP Basic Auth)
- storage API: `127.0.0.1:8428` (loopback only)
- data: `/var/lib/victoria-metrics-homeassistant/data`
- retention: `2y`
- exact-timestamp deduplication: `1ms` (VictoriaMetrics storage precision;
  makes repeated `vmctl` boundary samples idempotent)
- cache memory ceiling: 512 MiB
- ingestion stop floor: 20 GB free on the filesystem

The source InfluxDB add-on remains running during the acceptance period. It is
the rollback source and must not be removed until the owner accepts the new
dashboards and bridge behavior.

## Rollback

The old `influx-ha` Grafana datasource and original dashboard UIDs remain
provisioned. Set `METRICS_BACKEND=influxdb` in
`~/.config/plant-praxis-bridge.env` to move the reminder bridge back. On the
appliance, stop Core and restore
`/config/.storage/core.config_entries.before-vm-cutover-20260831`, then start
Core; `/config/configuration.yaml.before-vm-cutover-20260831` removes only the
34-entity export options if that is also required. Do not delete either metrics
store as part of rollback.

## Verify

```bash
systemctl is-active victoriametrics-homeassistant vmauth-homeassistant
curl -fsS http://127.0.0.1:8428/health
curl -fsS http://127.0.0.1:8428/metrics | \
  grep 'flag{name="retentionPeriod", value="2y", is_set="true"} 1'
curl -fsS -u "$VM_HA_READ_USER:$VM_HA_READ_PASSWORD" \
  --get http://100.85.100.81:8427/api/v1/query \
  --data-urlencode 'query=count(homeassistant_state_value)'
```

An unauthenticated request and a reader request to `/write` must both fail.
The source add-on stays available at `100.105.145.26:8086` for rollback.
