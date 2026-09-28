# Maintenance outcomes — proximal

## 2026-09-28 02:12 UTC — 563e6f35-0993-4491-8b46-8a71a866119e

Host: proximal. Policy: maintenance-v2. Run status: completed.

- **os** — verified. Before: Ubuntu 24.04.5, kernel 6.8.0-138; 39 packages upgradable incl. noble-updates security (apparmor/libapparmor1 4.0.1-0ubuntu0.24.04.8, dnsmasq-base, libaudit1, libpciaccess0, linux-firmware-amd-graphics, xserver-xorg-core/xvfb 21.1.12-1ubuntu1.8) alongside held scope (postgresql 16/17/18 pgdg, kubelet/kubeadm/containerd.io, nvidia-container-toolkit, google-cloud-cli, libpq5/pgbackrest); reboot pending since 2026-09-24 (kernels 6.8.0-139/-142, libc6). No active apt/dpkg transaction observed.. After: 13 packages upgraded and observed at targets (apparmor/libapparmor1 4.0.1really4.0.1-0ubuntu0.24.04.8, libaudit1/common 1:3.1.2-2.1ubuntu0.1, dmidecode 3.5-3ubuntu0.2, dnsmasq-base 2.91-0ubuntu0.24.04.1, dracut-install 060+5-1ubuntu3.4, libpciaccess0 0.17-3ubuntu0.24.04.3, linux-firmware-amd-graphics ...0ubuntu3.3, python3-requests 2.31.0+dfsg-1ubuntu1.2, xserver-common/xserver-xorg-core/xvfb 2:21.1.12-1ubuntu1.8); 28 packages deferred; reboot_required=true (not taken).
  Verification: operation verify_argv asserted /var/lib/update-bot-os/latest.json status=='completed'; each selected package's observed version equals its target; receipt /var/lib/update-bot/runs/563e6f35-0993-4491-8b46-8a71a866119e/operations/c27398f3-4ce9-4bf3-b44e-e5eebf927b0c/result.json has exit_code=0 and verification_exit_code=0.
  Activation: installed (helper suppresses package-script service restarts; kernel/libc activation requires the deferred reboot, so those are installed but not yet active; userspace library packages took effect on install).
  Evidence: `/var/lib/update-bot/runs/563e6f35-0993-4491-8b46-8a71a866119e/operations/c27398f3-4ce9-4bf3-b44e-e5eebf927b0c`.

