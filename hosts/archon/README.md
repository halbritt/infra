# archon

Omarchy 4 (Arch Linux, Hyprland) desktop on an Intel NUC 13 (`NUC13ANHi7`,
i7-1360P, 62 GiB RAM, Samsung 990 PRO 2 TB, LUKS + btrfs root with Snapper).
First recorded 2026-09-26.

LAN: `wlo1`, DHCP, observed `192.168.1.179` (DHCP, may change).
Tailscale: `100.100.42.51` / `archon.tail0ecc2e.ts.net`.
Passwordless administration from proximal: `ssh archon` (client config in
`~/.ssh/config.d/archon`; `archon-lan` targets the LAN address).
`halbritt` has `NOPASSWD: ALL` sudo, but `sudo -v` still prompts. See
[updates](config/updates/README.md).

- [Machine metadata](machine.yaml)
- [Operational notes](notes.md)
- [Changelog](CHANGELOG.md)
- [Updates](config/updates/README.md)
- [Terminal (foot)](config/terminal/README.md)
