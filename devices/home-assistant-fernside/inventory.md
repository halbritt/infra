# Inventory — 2026-07-22

First full capture, taken from `proximal` via ha-mcp (`ha_get_system_health`,
`ha_get_overview`, `ha_get_addon`, `ha_get_integration`). Point-in-time
snapshot; re-capture rather than hand-edit.

## Platform

| fact | value |
|---|---|
| Hardware | **Home Assistant Yellow** (CM4 carrier, board `yellow`) — not a bare Pi; the RPi Trading MAC OUI comes from the CM4 |
| HAOS | 18.1 (kernel `6.18.34-haos-raspi`, aarch64) |
| Supervisor | 2026.07.3 · OS agent 1.9.0 · Docker 29.5.3 |
| HA core | 2026.7.2 (Python 3.14.6) |
| Timezone | America/Los_Angeles |
| Disk | 468.7 GB total, 24.7 GB used · eMMC wear 1% |
| Recorder | SQLite 3.53.2, ~185 MiB, history since 2026-06-25 |
| Dashboards | 5, storage mode |
| Network | `end0` 192.168.1.64/24 + IPv6; `wpan0` = Thread radio |

## Nabu Casa cloud

Logged in; remote UI enabled and connected (us-east-1 relayer). Google
Assistant enabled, Alexa disabled. **Subscription expiration listed as
2026-07-25** — three days after this capture; confirm renewal state.

## Add-ons — 11 installed, all running

| add-on | slug | version | notes |
|---|---|---|---|
| OpenThread Border Router | `core_openthread_border_router` | 3.0.2 | drives the Yellow's onboard radio (`wpan0`) |
| Matter Server | `core_matter_server` | 9.0.4 | update available |
| Terminal & SSH | `core_ssh` | 10.3.0 | running, but ports 22/2222/22222 closed as-found — no exposed port, ingress web terminal only |
| InfluxDB | `a0d7b954_influxdb` | 5.0.2 | paired `influxdb` integration exports states |
| Grafana | `a0d7b954_grafana` | 12.1.0 | |
| Studio Code Server | `a0d7b954_vscode` | 6.0.1 | |
| Tailscale | `a0d7b954_tailscale` | 0.28.1 | tailnet `100.105.145.26`, offers exit node |
| ESPHome Device Builder | `5c53de3b_esphome` | 2026.6.5 | update available |
| Claude Terminal Pro | `cf2feb56_claude_terminal_pro` | 2.0.10 | Claude Code CLI in the HA frontend |
| **Home Assistant MCP Server** | `81f33d0f_ha_mcp` | 7.14.1 | the agent interface of record (`:9583`); self-reports current, no update pending |
| Webhook Proxy for HA MCP | `81f33d0f_ha_mcp_webhook_proxy` | 2.0.5 | paired `mcp_proxy` integration |

## Integrations — 46 config entries, all `loaded`

By function (counts in parens where >1):

- **Radios / fabrics:** `zha` (SLZB-06M Ethernet Zigbee coordinator) +
  `smlight` (coordinator's own mgmt), `otbr` + `thread` (Yellow's OpenThread),
  `matter`
- **Media:** `sonos`, `cast`, `webostv` (LG OLED42C3PUA), `wiim` + `linkplay` +
  `dlna_dmr` (all three are the same WiiM Amp Ultra), `radio_browser`
- **Weather / environment:** `met`, `open_meteo`, `ecowitt` (2 — likely
  duplicate entries for one GW1200B gateway; unverified)
- **Plant monitoring:** `derivative` (5 — moisture-rate sensors: Dracaena,
  Ficus Audrey, Kangaroo Paw Fern, Monstera, Palm)
- **Printers:** `ipp` (2: Brother HL-L2460DW + a CUPS queue shared from
  proximal), `brother`
- **Devices:** `esphome` (one node: `Fernside`), `elgato` (Key Light),
  `vesync` (Levoit humidifier), `mobile_app` (one iPhone)
- **Helpers:** `switch_as_x` (7 — smart plugs re-exposed as lights)
- **System:** `hassio`, `cloud`, `backup`, `analytics`, `go2rtc`, `influxdb`,
  `mcp_proxy`, `homeassistant_yellow`, `sun`, `shopping_list`,
  `google_translate`

## Entities — 454 across 25 domains

| domain | count | | domain | count |
|---|---|---|---|---|
| sensor | 164 | | media_player | 16 |
| number | 82 | | light | 14 |
| update | 47 | | binary_sensor | 13 |
| button | 40 | | automation | 10 |
| switch | 30 | | climate | 3 |
| select | 19 | | tts, weather | 2 each |

…plus 1 each of: conversation, event, stt, zone, person, sun, lock, fan,
device_tracker, notify, todo, humidifier.

10 automations, all enabled — front-door lock/unlock around presence and
time-of-day, grow-light schedules, hall light at sunset, a smart-knob → bedroom
lamp binding, and a plant-drying-rate alert.

## Repairs / notifications

One active repair: `mcp_proxy` `update_restart_required` (warning, raised
2026-07-15) — the webhook-proxy integration wants a restart to finish an
update. One persistent notification (not captured).

## Addendum — later on 2026-07-22

- The `mcp_proxy` repair was cleared by reloading the config entry
  (`homeassistant.reload_config_entry` via ha-mcp); repairs now 0.
- The two pending add-on updates were applied between capture and addendum:
  ESPHome Device Builder → 2026.7.1, Matter Server → 9.1.0.
- HA core restarted at 08:49 UTC; recorder history now starts 2026-07-11
  (older runs purged).
