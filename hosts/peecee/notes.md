# peecee host notes

The only desired state currently imported for `peecee` is its Windows
`nvidia_gpu_exporter` service. That configuration was previously nested under
`proximal` observability because `proximal` Prometheus consumes it. The fleet
migration separates ownership: the exporter service belongs here; the scrape
job, alert rules, and dashboards remain under `hosts/proximal/`.

Recorded facts come from the deployment record dated 2026-06-20: Windows 11 Pro
x86_64, an RTX 3090 Ti, and tailnet address `100.113.63.58`. They were not
reverified on the Windows machine during the repository migration, so the
manifest status is `documented` rather than a claim of current reachability.

No other `peecee` repository or machine configuration was available in this
checkout. Future imports must merge new evidence here without inventing or
overwriting this subsystem.
