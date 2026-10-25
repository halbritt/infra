# Unattended boot on proximal

The owner reported that GRUB waited for input while the keyboard was
disconnected on 2026-10-25. Inspection found a visible 10-second menu and a
30-second record-failure timeout; no indefinite timeout or current recordfail
flag was present. The exact cause of the observed wait is unconfirmed.

`99-unattended.cfg` makes both normal and record-failure boots select the default
entry immediately. Kernel selection remains automatic (`GRUB_DEFAULT=0` in the
host's base configuration); no kernel version is selected by this drop-in.
The GPU-unlock command-line option remains in its separate drop-in.

Install and validate:

```sh
sudo install -m 0644 hosts/proximal/config/boot/99-unattended.cfg /etc/default/grub.d/99-unattended.cfg
sudo update-grub
sudo grub-script-check /boot/grub/grub.cfg
```

The installed generated configuration was checked for zero timeouts in all
timeout branches. Physical keyboard-free boot remains untested until the next
reboot. This change removes the recovery-menu delay after a failed boot as well.
It does not control any firmware-level keyboard error prompt.

To restore the prior menu, remove `/etc/default/grub.d/99-unattended.cfg` and
run `sudo update-grub`; the base configuration supplies the previous settings.
