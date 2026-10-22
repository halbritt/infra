# Network

talos reaches the network only over Wi-Fi (`wlp0s20f3`). Subiquity's netplan
(`/etc/netplan/00-installer-config.yaml`, mode 0600) also names the wired
`eno1`, which has no cable. The file holds the Wi-Fi PSK, so only the `eno1`
stanza is recorded here.

## eno1 (owner-requested, 2026-10-22)

```yaml
    eno1:
      match:
        macaddress: 1c:69:7a:63:e5:ff
      set-name: eno1
      dhcp4: true      # added
      optional: true   # added
```

- `dhcp4: true`: a cable plugged in gets a DHCP lease. Netplan gives the wired
  route metric 100 and Wi-Fi metric 600, so wired becomes the preferred path.
  Wi-Fi stays up.
- `optional: true`: required, but not sufficient on its own. Netplan 1.2 only
  lists non-optional links in its generated `systemd-networkd-wait-online.service`
  drop-in. It does not write `RequiredForOnline=no` into `10-netplan-eno1.network`.
  `apt-helper wait-online`, run by `ExecStartPre` in `apt-daily.service` and
  `apt-daily-upgrade.service`, calls `systemd-networkd-wait-online` with no `-i`,
  so it still waited for `eno1`. Each run timed out after about 30 s and logged
  `returned an error code (1)`.
- [50-infra-optional.conf](50-infra-optional.conf), installed at
  `/etc/systemd/network/10-netplan-eno1.network.d/`: sets
  `RequiredForOnline=no` on the netplan-generated unit. networkd merges the
  drop-in by the unit's file name, and the drop-in survives `netplan generate`.

The change was applied with `netplan generate` and `networkctl reload`, not
`netplan apply`. The Wi-Fi unit was byte-identical before and after
regeneration, so the link was never reconfigured. The pre-change YAML is kept
root-only at `/root/00-installer-config.yaml.bak-20261022`.

## Verify

```sh
ssh talos 'networkctl status eno1 | grep "Required For Online"; time sudo /usr/lib/apt/apt-helper wait-online; echo rc=$?'
```

Expect `Required For Online: no` and an immediate `rc=0`. Before the change this
took 30 s and returned 1.

## Rollback

```sh
sudo rm -r /etc/systemd/network/10-netplan-eno1.network.d
sudo cp /root/00-installer-config.yaml.bak-20261022 /etc/netplan/00-installer-config.yaml
sudo netplan generate && sudo networkctl reload
```
