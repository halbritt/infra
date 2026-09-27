# enceladus

Windows 11 Pro (build 26200) desktop: MSI MS-7D75, Ryzen 7 9700X, 62 GiB RAM,
RTX 3060 12 GiB, Samsung 980 PRO 2 TB. First recorded here 2026-09-26.
It was already a GPU scrape target of proximal's monitoring stack.

Local accounts: `halbritt` (owner, administrator) and `Saturn` (a child's
account), plus two Codex sandbox accounts.

LAN: `192.168.1.140`. Tailscale: `100.123.179.99` / `enceladus.tail0ecc2e.ts.net`.
Passwordless administration from proximal: `ssh enceladus`
(`ENCELADUS\halbritt`, elevated PowerShell). SSH did not answer on the LAN
address during the 2026-09-26 scan, so SSH access depends on Tailscale.

- [Machine metadata](machine.yaml)
- [Operational notes](notes.md)
- [Changelog](CHANGELOG.md)
- [Tailscale unattended mode](config/tailscale/README.md)
- [Startup (Wacom Center)](config/startup/README.md)
