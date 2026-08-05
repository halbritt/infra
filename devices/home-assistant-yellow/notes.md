# Home Assistant Yellow notes

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

## Identity decision

The stable resource name is `home-assistant-yellow`, not `homeassistant`.
Hardware class is the differentiator because another Home Assistant instance
could run on different hardware or in a VM. The appliance currently reports
`homeassistant` through both mDNS and Tailscale; those remain observed aliases
until the live rename is completed.

## Live hostname migration boundary

The repository import does not change the appliance. A live rename must be a
separate operational change with before-and-after probes. Current consumers
use fixed addresses rather than the generic hostname:

- the proximal Grafana InfluxDB datasource uses `100.105.145.26:8086`;
- plant-praxis-bridge uses the same Tailnet address from a root-readable
  environment file and a versioned template;
- agent access to ha-mcp is registered through the Tailnet address, with its
  private path stored outside Git.

Before renaming, inspect Home Assistant's internal and external URLs, Tailscale
add-on naming, certificates, callbacks, bookmarks, DNS/mDNS discovery, backup
destinations, and any automation or integration that embeds the current name.
After renaming, verify the HA UI, Observer, ha-mcp, InfluxDB consumers, Tailscale
reachability, Thread/Matter control, and a backup. Keep the previous name as a
temporary alias only when an actual consumer requires it; do not create an
unbounded compatibility alias by default.
