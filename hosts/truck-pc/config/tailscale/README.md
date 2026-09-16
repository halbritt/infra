# Tailscale

Owner-authorized setup on 2026-09-15 for remote access after Windows logout.

## Installation

The canonical [install.ps1](install.ps1) downloads the official stable amd64 MSI
for version 1.102.4, checks its Authenticode signature, and installs it silently
without rebooting. `TS_UNATTENDEDMODE=always` enables unattended operation.

Run the canonical script in an elevated PowerShell session on this host. The
operator can transmit its contents through the existing SSH connection; it is
an installation recipe, not a resident service wrapper. Tailscale installs its
binaries in `C:\Program Files\Tailscale` and registers the native `Tailscale`
Windows service. The MSI owns the service and firewall configuration.

## Enrollment and verification

```powershell
& 'C:\Program Files\Tailscale\tailscale.exe' up --unattended --timeout=30s
& 'C:\Program Files\Tailscale\tailscale.exe' status
& 'C:\Program Files\Tailscale\tailscale.exe' ip -4
Get-Service Tailscale
sc.exe qc Tailscale
sc.exe qfailure Tailscale
```

Complete any browser authentication using the owner's existing tailnet. Keep
authentication URLs, keys, and generated identity files out of Git and the public
documentation site. Record successful enrollment separately from installation.

To disconnect, run `tailscale down` using the full executable path above. To
uninstall, use Windows Apps & features. Both withdraw remote access and require
an authorized maintenance session with a working LAN fallback.

References: [Windows MSI installation](https://tailscale.com/docs/install/windows/msi),
[unattended mode](https://tailscale.com/docs/how-to/run-unattended).

## Verified deployment — 2026-09-15

- Tailscale 1.102.4 installed; Authenticode signer `Tailscale Inc.` was valid.
- MSI SHA-256: `80EB007E39DFEBE17299FA1A09C79A8E1D934F76E0246C0817EBE3AF675B7EF6`.
- First attempt returned MSI 1618 while Dell SupportAssist was updating. Retried
  after its transaction ended; Tailscale returned MSI 0.
- Enrolled in the existing tailnet, backend state `Running`, IPv4 `100.121.157.17`,
  DNS name `userpas-gbb8opo.tail0ecc2e.ts.net`.
- `UnattendedMode=always`; service automatic, LocalSystem, with native dependencies
  Dnscache, iphlpsvc, netprofm, and WinHttpAutoProxySvc.
- MSI recovery policy: restart delays 1, 2, 4, 9, 16, 25, 36, 49, and 64 seconds;
  failure counter resets after 60 seconds.
- Direct Tailscale ping from proximal took 4 ms. SSH key authentication over the
  Tailscale address returned the expected Windows identity.

Persistence is configured; a reboot has not yet been performed for verification.
