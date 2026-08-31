# Home Assistant at Fernside

Durable, inspectable, cross-agent provenance and desired state for the device
`home-assistant-fernside`, a Home Assistant OS installation at Fernside on the
home LAN (`192.168.1.64` / tailnet `100.105.145.26`). Its live mDNS and
Tailscale hostname is `home-assistant-fernside`. See
[`device.yaml`](device.yaml) for identity and [`notes.md`](notes.md) for the
migration and verification record.

This is operational state, not a codebase. Its job is to remember — across runs
and across agents — what this appliance looks like, how it is reached, what
config it should run, and what was already tried and rejected.

## Identity

`home-assistant-fernside` is the stable resource name because it identifies the
installation by site and distinguishes it from future Home Assistant
installations. The former generic hostname `homeassistant` is historical
identity evidence, not a current alias. Home Assistant Yellow remains the
current hardware model; a hardware replacement at Fernside does not silently
create a new installation.

The eight commits from the former standalone repository
`github.com/halbritt/homeassistant` remain in this repository's history. New
desired-state changes belong here.

## The appliance

| fact | value |
|---|---|
| Resource name | `home-assistant-fernside` |
| Hardware | **Home Assistant Yellow** (CM4 carrier, board `yellow`; MAC `2c:cf:67:fb:66:0d` — the RPi Trading OUI is the CM4's, which is why it first scanned as a bare Pi) |
| OS | Home Assistant OS (HAOS) — appliance, not a general Linux host |
| LAN | `192.168.1.64` (`enp3s0` ARP on proximal) |
| Tailscale | `100.105.145.26` · hostname `home-assistant-fernside` · offers exit node |
| Versions | see [`inventory.md`](inventory.md) — HAOS/Supervisor/core/add-ons, captured 2026-07-22 |

Identity, Core, HAOS, and add-on state were reverified 2026-08-06. The inventory
remains a point-in-time 2026-07-22 snapshot; see the changelog for newer version
observations.

## Access posture

- **`:8123`** — Home Assistant web UI + REST API. API answers `401` without a
  token (healthy; auth required).
- **`:4357`** — HAOS observer. Reports: Supervisor **Connected**, Support
  **Supported**, Health **Healthy**.
- **`:9583`** — **[ha-mcp](https://github.com/homeassistant-ai/ha-mcp)** add-on
  (v8.1.1 as of 2026-08-06), the agent interface of record — see below.
- **`:22`** — Terminal & SSH add-on access, enabled 2026-08-06 with one
  authorized public key, no password, and TCP forwarding disabled. This is an
  add-on shell with Supervisor CLI access, not HAOS developer SSH. Keep the
  private key outside Git.
- **Native MCP Server integration: not enabled** (`/mcp_server/sse` → `404`) —
  and not wanted: ha-mcp supersedes it.

### Agent access

The **ha-mcp add-on** (streamable-HTTP MCP, ~89 tools: device control, state
queries, automation management, and more) runs on the appliance at
`:9583`. Its URL contains a **secret path segment** (`/private_…`) that serves
as the credential — **the full URL is a secret; never commit it**. It lives
only in the add-on config on the appliance and in `~/.claude*/.claude.json` on
proximal.

The desired registration on proximal is **user scope** so every Claude Code
session sees it, using the tailnet IP so mDNS is not a dependency:

```bash
claude mcp add --transport http --scope user ha-mcp \
  "http://100.105.145.26:9583/private_<SECRET>"
```

The 2026-08-06 check found the add-on listener reachable on both LAN and
tailnet, but the active Claude configuration did not list a user-scope `ha-mcp`
server. A legacy project-local registration remains under the former
`~/git/ha-mcp` checkout, so sessions launched elsewhere cannot use it. Restore
the user-scope registration with the private URL read directly from the add-on
configuration, then verify it with `claude mcp list`; do not copy the URL into a
shell transcript or this repository. Rotate the secret from the add-on's
configuration page if the URL ever leaks.

## Data out to proximal Grafana

The `influxdb` integration now exports an explicit 34-entity numeric sensor
allowlist to the dedicated VictoriaMetrics store on proximal through
authenticated tailnet ingress `100.85.100.81:8427`. The store keeps two years
and feeds the VictoriaMetrics versions of the **Plant Moisture** and **Indoor
Environment** Grafana dashboards plus `plant-praxis-bridge`.

The former InfluxDB add-on (`:8086`, InfluxQL/v1, db `homeassistant`) remains
running but is no longer the integration's write destination. Its unlimited
retention data, Grafana datasource (`influx-ha`), and original dashboards are
preserved as the rollback path during acceptance. All Grafana desired state lives under
[`hosts/proximal/config/observability/grafana/`](https://github.com/halbritt/infra/tree/master/hosts/proximal/config/observability/grafana);
this appliance retains the old InfluxDB add-on and owns the exporting
integration. VictoriaMetrics credentials remain outside Git.

**Appliance-side bridges for the dashboards** (created here, consumed there):

- **Local Weather template sensors** — the `weather.*` domain is not in the
  numeric export allowlist, so six template helpers (`sensor.local_weather_*`:
  temperature, humidity, pressure, dew_point, wind_speed, uv_index) mirror
  `weather.forecast_home` (met.no) into sensor-domain entities that do record,
  feeding the Indoor Environment dashboard's "Weather (met.no)" overlays.

## Subsystems

- [`config/home-assistant-core/`](config/home-assistant-core/) — canonical
  non-secret Core configuration, including Recorder retention and commit
  policy. The appliance's `/config/secrets.yaml` remains outside Git.

[`inventory.md`](inventory.md) holds the whole-device snapshot (versions,
add-ons, integrations, entity summary). Add another directory only when its
real configuration is worth versioning; do not pre-create empty subsystems.

## The one rule

**Values and config, never credentials.** Commit settings, YAML, dashboards,
and rationale. Never commit long-lived access tokens, `secrets.yaml`, `*.env`,
or keys. Tokens live only in `0600` files on proximal or in the HA keyring.

## Conventions

- **One infrastructure repository, one directory per managed resource.**
- **Canonical-in-repo, installed-on-box.** Each subsystem README maps repo
  files → their install path on the appliance.
- **Commit and push often.** `origin` = `github.com/halbritt/infra`.
