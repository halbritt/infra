# Home Assistant at Fernside notes

## Repository import

The standalone `github.com/halbritt/homeassistant` repository was imported
without squashing on 2026-08-05. Its clean, synchronized `master` tip was
`1733c24e99a4762b3a08bdec5680a8e67d229c0d`; all eight source commits are
ancestors of subtree import commit
`b48b4d08f444354259a60ce38ef62220522e7783`.

No dedicated secret scanner was installed. A path-only filename scan and a
redacted content-pattern scan of every reachable source commit found no likely
credential. The scan did not print candidate values. This is bounded evidence,
not proof that the history is secret-free.

After the imported tip, current tree, and absence of checkout-bound consumers
were verified, `/home/halbritt/git/homeassistant` was moved to the desktop trash
on 2026-08-05. It is recoverable from trash. The standalone GitHub repository
was not deleted.

The resource directory was later renamed from `home-assistant-yellow` to
`home-assistant-fernside`. For file history across that rename, use:

```sh
git log --follow -- devices/home-assistant-fernside/README.md
```

Use `git log -- devices/home-assistant-yellow` when inspecting the original
subtree path as a whole.

## Identity decision

The stable resource name is `home-assistant-fernside`, not `homeassistant`.
The site identifies this Home Assistant installation; Yellow is the current
hardware model and can change independently. The appliance has reported
`home-assistant-fernside` through both mDNS and Tailscale since the live rename
on 2026-08-06. The former `homeassistant` name is historical evidence and did
not resolve after the post-update reboot.

## Live hostname migration

The repository import did not change the appliance. The live rename was handled
as a separate operational change with before-and-after probes. Known consumers
use fixed addresses rather than the hostname:

- the proximal Grafana InfluxDB datasource uses `100.105.145.26:8086`;
- plant-praxis-bridge uses the same Tailnet address from a root-readable
  environment file and a versioned template;
- agent access to ha-mcp is registered through the Tailnet address, with its
  private path stored outside Git.

The 2026-08-05 preflight inspected Home Assistant's internal and external URLs,
Tailscale identity, and known Grafana, plant-praxis-bridge, and ha-mcp consumers.
No checked consumer depended on the generic hostname, so no compatibility alias
was created.

Terminal & SSH was configured with one authorized public key, no password, TCP
forwarding disabled, and host port 22. The private key remains outside Git. This
provided an authenticated Supervisor client without copying its token into the
repository.

The operation completed on 2026-08-06 was:

```sh
ha host info
ha host options --hostname home-assistant-fernside
ha host info
```

The underlying Supervisor API contract is `GET /host/info` followed by
`POST /host/options` with a `hostname` field. See the official
[Supervisor API endpoint reference](https://developers.home-assistant.io/docs/api/supervisor/endpoints/).
Do not copy a Supervisor token into this repository to automate the call.

The Supervisor accepted the change, mDNS resolved
`home-assistant-fernside.local` to `192.168.1.64`, and key-only SSH worked by the
new name. Tailscale retained the old identity until the HAOS update reboot, then
reported `home-assistant-fernside.tail0ecc2e.ts.net` online at
`100.105.145.26`. The LAN and Tailnet Home Assistant UI endpoints and HAOS
Observer all returned HTTP 200 after startup. The fixed-address InfluxDB and
ha-mcp paths remained reachable.

## 2026-08-06 update maintenance

Before installing updates, created protected local backup
`Before_2026-08-06_updates`. It includes Home Assistant Core, the SSL folder,
and all installed add-ons. No backup key or credential is stored here.

Installed all seven updates that Supervisor and Home Assistant exposed:

- Home Assistant Core `2026.7.4` to `2026.8.0`;
- Home Assistant OS `18.1` to `18.2`;
- OpenThread Border Router `3.0.2` to `3.1.0`;
- ESPHome Device Builder `2026.7.3` to `2026.7.4`;
- Matter Server `9.1.0` to `9.1.1`;
- Home Assistant MCP Server `8.0.0` to installed version `8.1.1`;
- Midea U Window AC firmware `0x0000002f` to `0x00000038`.

Core and ha-mcp dropped their initiating client connections while restarting;
this was expected, and their installed versions and started state were checked
afterward. The Midea OTA request also outlived the client timeout. ZHA logged an
unknown `DeviceFirmwareInfoUpdatedEvent`, but the entity subsequently reported
installed and latest firmware `0x00000038`, state `off`, and no update in
progress. Do not retry that OTA solely because of the transient client timeout.

HAOS 18.2 was staged in the alternate boot slot and required an explicit host
reboot. After reboot, HAOS reported slot B booted and good, with 18.1 retained
as the good inactive slot. Core and Supervisor were healthy and supported,
every installed add-on was started and current, and `ha available-updates`
returned an empty list.

The post-reboot Core log still contained an ESPHome reconnect warning for the
separate device `fernside` at `192.168.1.66`, plus shutdown-time cancellation
noise from the planned Core restart. These did not block the appliance update;
recheck the ESPHome device if its offline condition persists.
