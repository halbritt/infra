# TPM unlock for archon's root LUKS volume

Owner decision 2026-10-19 ("option 1"): add TPM2 automatic unlock to the root
LUKS2 volume (`/dev/nvme0n1p2`, mapped as `root`) so archon — and the
[imessage-vm](../imessage-vm/README.md) it hosts — comes back after an
unattended reboot. The boot passphrase (keyslot 0) stays as the fallback. Do
not remove it.

## What changed

- `/etc/mkinitcpio.conf.d/zz-archon-tpm-unlock.conf` (this directory) rewrites
  Omarchy's busybox HOOKS to the systemd set: `udev→systemd`,
  `encrypt→sd-encrypt`, `keymap/consolefont→sd-vconsole`,
  `btrfs-overlayfs→sd-btrfs-overlayfs`, `resume` dropped (systemd resumes from
  `resume=`). Omarchy's `omarchy_hooks.conf` (package `omarchy-settings`) is
  left untouched, so its conditionals and future changes still feed in.
- `/etc/default/limine` and `/etc/kernel/cmdline` keep `cryptdevice=…` and add
  `rd.luks.name=<luks-uuid>=root rd.luks.options=<luks-uuid>=tpm2-device=auto`.
  The busybox `encrypt` hook reads the first and the systemd initramfs the
  second, so either initramfs boots this cmdline.
- UKIs rebuilt with `sudo limine-mkinitcpio` (2026-10-19, both kernels). The new
  initramfs contains `systemd-cryptsetup`, `libcryptsetup-token-systemd-tpm2.so`,
  tss2 libraries, plymouth, `overlayfs-setup.service`, `vconsole.conf`; the TPM
  drivers are built into both kernels.
- TPM enrollment (owner, needs the current passphrase):
  `sudo systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 /dev/nvme0n1p2`.
  PCR 7 only, because Secure Boot is off and PCR 4/11 change on every kernel
  update (each would fall back to the passphrase).

## Security trade-off

With TPM unlock, the NUC boots to its login screen without the disk
passphrase. A drive removed from the machine stays encrypted. With Secure Boot
off and PCR 7 only, a modified boot chain on the same machine can still unseal
the key; enabling Secure Boot (sbctl) and binding more PCRs would tighten this.

## Rollback and recovery

Pre-change copies are in root-only `/root/tpm-unlock-20261019/` (LUKS header
backup, `limine`, `cmdline`, `limine.conf`, both UKIs). Snapper snapshot 3
("pre-tpm-unlock 2026-10-19") has a Limine entry under **Snapshots** whose UKIs
are byte-identical to the pre-change ones.

- TPM refuses (firmware/PCR change): the passphrase prompt appears; type it.
  Re-enroll with `systemd-cryptenroll --wipe-slot=tpm2 --tpm2-device=auto --tpm2-pcrs=7 /dev/nvme0n1p2`.
- New initramfs fails to boot: Limine → Snapshots → 3, then revert:
  `rm /etc/mkinitcpio.conf.d/zz-archon-tpm-unlock.conf`, restore `limine` and
  `cmdline` from the backup directory, `limine-mkinitcpio`.
- Remove TPM unlock: `systemd-cryptenroll --wipe-slot=tpm2 /dev/nvme0n1p2` and
  the revert above.

## First reboot — 2026-10-20

Verified on boot `b4f00d05` (02:50): the main Limine entry (linux-omarchy
7.2.5) unlocked root by TPM with no prompt. "Cryptography Setup for root"
took 1.1 s, and `imessage-vm.service` started 7 s into boot.

Before that, the first restart attempt (shutdown logged cleanly at 01:45:23)
and one boot of the old "linux" entry (7.2.3) gave a blank screen. They left
no journal, so the cause is **not established**. The 7.2.3 UKI contains the
same TPM, GPU, plymouth and cryptsetup pieces as the default one. If a blank
screen recurs:
- type the disk passphrase blindly and press Enter (plymouth may be hiding
  the prompt);
- else press `e` on the Limine entry and drop `quiet splash loglevel=0
  systemd.show_status=false` to see the messages;
- else boot Snapshots → 3.
