# Proximal APT sources

Install `vendors.sources` as root-owned mode 0644 at
`/etc/apt/sources.list.d/vendors.sources`. It restores the existing vendor
repositories disabled by the 2026-10-28 Ubuntu 26.04 upgrade, in deb822 format.
Ubuntu's native sources and the Nala mirror configuration remain separate.

Docker, PGDG, Tailscale, KiCad, graphics-drivers and OpenFOAM use `resolute`.
NVIDIA CUDA uses its `ubuntu2604` repository. Distribution-independent vendor
suites remain unchanged. Mullvad uses its documented `stable` suite rather than
an Ubuntu codename. NVIDIA Container Toolkit uses its current generic stable
repository; the redundant Ubuntu 18.04 entry is retired. Embedded PPA keys are
public signing keys.

Install `cuda-ubuntu2604.asc` at `/usr/share/keyrings/cuda-ubuntu2604.asc` as
root-owned mode 0644. NVIDIA's new Ubuntu 26.04 signing key has fingerprint
`14BA FBC7 562A D710 CA04 E699 05FB B6DA 60DF 8A40`, verified against the key
published at its official Ubuntu 26.04 repository and NVIDIA's
[repository-management documentation](https://github.com/NVIDIA/cuda-repo-management).
The previous CUDA key remains available for rollback; signature checks stay
enabled.

Before installing this file, archive superseded active source files to avoid
duplicate repositories. The upgrade's `.disabled`, `.migrate` and `.distUpgrade`
evidence is retained privately under `/var/backups/ubuntu-26.04-20261028/`.
Run `sudo apt-get update` and verify signature checks and suite availability.

The owner explicitly requested no arbitrary version pins. This source file has
no version constraints. Temporary database migration pins are removed before
installing PostgreSQL 18. Existing holds should be reviewed against a concrete
compatibility requirement rather than carried forward automatically.

NVIDIA package provenance stays with NVIDIA. The exact-source DKMS compatibility
repair is documented in `../nvidia/`; it does not prevent package updates.

## One-time upgrade boot check

Install `ubuntu2604-postboot-check.sh` as root-owned mode 0755 at
`/usr/local/sbin/ubuntu2604-postboot-check`, and the matching service/timer as
root-owned mode 0644 under `/etc/systemd/system/`. Before reboot, write the current
boot ID to `preboot-id` and the installed target kernel release to
`expected-kernel`, both in the private recovery directory named above.
Enable the timer without starting it; it runs two minutes into the next boot.

The check refuses to report success in the original boot. It checks the OS,
kernel, package consistency, NVIDIA, ZFS, PostgreSQL and collation state,
archiving, core services and application HTTP endpoints. SSH is checked with a protocol
handshake so socket activation is exercised before testing availability. Output is retained in
`postboot-check.log`; success creates `postboot-check.passed` and disables the
timer. Failure leaves the native service failed and the timer enabled for a
subsequent boot. Inspect the log and fix actual failures before rerunning.
This checks boot activation; it does not prove complete application behavior.
