# Changelog — peecee

Machine-level changes for `peecee`, newest first. The exporter README and its Git
history contain the original 2026-06-20 deployment record.

## 2026-08-05

### Existing Windows GPU exporter assigned to its owning host

Moved the already-versioned `nvidia_gpu_exporter` WinSW configuration from the
`proximal` observability subtree to `hosts/peecee/config/nvidia-gpu-exporter/`.
Updated `proximal`'s consumer references. No Windows service, firewall rule,
address, executable, or credential changed, and no live Windows action was
performed.
