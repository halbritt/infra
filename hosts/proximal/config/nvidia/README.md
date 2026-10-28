# NVIDIA driver on proximal

Keep NVIDIA's own APT packaging, with its Ubuntu 26.04 CUDA repository. The
owner asked to investigate the existing choice during the 2026-10-28 OS upgrade.
The GPU-unlock record verifies NVIDIA 615.71.09 with CUDA 12.8 before the upgrade;
the original repository-selection rationale has not been found in infra history.

## Kernel 7.0 CXL compatibility repair

NVIDIA `615.71.10` fails to build against Ubuntu `7.0.0-42-generic` with
`nv-linux.h:1270: field 'cxlds' has incomplete type`. The kernel exports a
`cxl/cxl.h` header without the driver-facing `struct cxl_dev_state` API.
NVIDIA's own `NV_CXL_INIT_SUPPORTED` feature test correctly rejects that API,
but five header guards check only header presence.

[Upstream issue 1433](https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1433)
records the same failure and a successful compile with these guards corrected.
The [patch](cxl-api-guard.patch) also requires `NV_CXL_INIT_SUPPORTED`, matching
the driver's CXL initialization and cleanup code. The RTX 3090 does not use CXL.

| Canonical file | Installed path |
|---|---|
| `cxl-api-guard.patch` | `/etc/dkms/nvidia/patches/cxl-api-guard.patch` |
| `nvidia-615.71.10.conf` | `/etc/dkms/nvidia-615.71.10.conf` |

Install both as root-owned mode 0644. DKMS applies the patch to its build copy;
the package-owned source remains unchanged. Rebuild with
`sudo dkms install -m nvidia -v 615.71.10 -k 7.0.0-42-generic`, then finish
pending package configuration and regenerate the initramfs.

This is a repair for the observed driver source version, **not an APT hold**.
Later NVIDIA packages remain eligible for normal updates. Check whether a later
release fixes CXL detection before carrying this patch forward. Remove the two
installed files when superseded. Preserve GPU-unlock loading before NVIDIA in
the boot image; its canonical configuration is in `../gpu-unlock/`.

Build and runtime verification is recorded in the host's
[`ubuntu-26.04-upgrade.md`](../../ubuntu-26.04-upgrade.md).
