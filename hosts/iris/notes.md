# Iris operational notes

## Access observed 2026-11-11

SSH key authentication from proximal works for `halbritt`. The owner installed
`/etc/sudoers.d/99-halbritt-nopasswd` with:

```sudoers
halbritt ALL=(ALL:ALL) NOPASSWD: ALL
```

`sudo -n true` succeeded during repair. The LAN address in `machine.yaml` is
the address observed during this session; a DHCP reservation was not checked.

## Display maintenance

The OS had current display overlays while the EEPROM still dated from
2025-05-08. Updating the EEPROM to the installed 2026-09-25 default release
restored automatic panel detection without changing `config.txt`.
See the [repair record](config/display/README.md) for versions and checks.

The update reboot took approximately two minutes before SSH returned. A
temporary loss of mDNS and SSH during that operation did not indicate failure.
Display and touch drivers were verified remotely; physical interaction remains
unverified.
