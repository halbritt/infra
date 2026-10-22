# gcp-gate notes

## Image build and validation — 2026-10-21/22

- The first image (`agent-ee-gate-20261022-0315`, deleted) passed the gate, but its
  warm cache missed: the per-SHA build took 386 s, rebuilding everything after
  `FROM`. provision.sh had extracted the warm context with umask 0022 (files 644),
  while an SSH login of halbritt has umask 0002 (pam_umask usergroups, files 664,
  the same git-archive modes as on peecee-wsl). BuildKit's COPY cache key
  includes file mode. provision.sh now extracts with umask 0002; the second image
  builds `agent-ee:ci-14ef7275` in 3 s.
- uid: the Ubuntu GCE image already has `ubuntu` at uid 1000, so `halbritt` is
  1001. ae-ci-exec runs containers as the caller's uid; nothing in the gate depends
  on 1000.
- After cleanup the builder has no authorized_keys, so provision.sh reports on the
  serial console (`AGENT-EE-GATE-PROVISION rc=N`) and powers off; build-image.sh
  reads it with `get-serial-port-output`.
- Spot with `PREEMPTIBLE_CPUS` = 0 works: Spot VMs draw on the standard CPU and
  family quotas. C2D quota in us-west1 is 100 vCPUs; C3 24; C4 0.
- No preemptions in four Spot VM sessions (2 builders, 2 gates).
