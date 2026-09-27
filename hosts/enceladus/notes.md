# enceladus notes

## Initial record — 2026-09-26

Recorded when the owner reported the tailnet not coming up after a reboot.
Facts in `machine.yaml` come from a live SSH probe on 2026-09-26: `sshd` and
the `nvidia_gpu_exporter` service were Running/Automatic.

Provenance gap (carried over from proximal's observability README): the
`nvidia_gpu_exporter` desired state (a WinSW wrapper on `100.123.179.99:9835`)
has not been recovered into this repository. Record it under
`config/nvidia-gpu-exporter/` from the live host before changing it.
