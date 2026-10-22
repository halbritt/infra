# talos notes

## Initial record — 2026-10-22

Recorded at the owner's request from a read-only SSH survey from proximal
(`ssh talos`), about 45 minutes after first boot. The installer log directory
and root filesystem birth time are both 2026-10-22 04:59 UTC. `cloud-init` is
disabled after install. One user session (`halbritt`, SSH) was present.

Observations to act on only with owner direction:

- 30 packages were upgradable. Unattended-upgrades applies only the security
  origins.
- The root LV uses 100 GiB of a 474 GiB volume group (Subiquity default).
  Extend with `lvextend -r` when space is needed.
- An older `linux-image-unsigned-7.0.0-30-generic` is installed alongside the
  running `7.0.0-38` generic kernel.
- Timezone is `Etc/UTC`.
- Wi-Fi is the only link. MACs: `eno1` `1c:69:7a:63:e5:ff`, `wlp0s20f3`
  `0c:7a:15:6c:b9:7f` (useful for a DHCP reservation).
