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
