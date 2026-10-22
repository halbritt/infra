# gcp-gate

Read `machine.yaml`, `README.md`, `notes.md` and `config/image/README.md` before
changes. gcp-gate is not a standing machine: it is the GCE image family
`agent-ee-gate` (project `heath-stuff`) and the throwaway Spot VMs booted from
it, one per agent-ee release-gate run. Build the image with
`config/image/build-image.sh`; run a gate with `config/image/run-gate.sh SHA`.

- `config/image/ci-run.sh` is a byte-identical copy of peecee-wsl
  `~/agent-ee-gate/ci-run.sh`. Do not edit it here; when the peecee copy changes,
  copy it, update `CI_RUN_SHA256` in `build-image.sh` and rebuild the image.
- No credentials in the image or in this directory: VMs run without a service
  account, SSH access comes from project metadata keys at boot, and the build
  removes authorized_keys, host keys and shell history before imaging.
- Delete every VM after use (`gcloud compute instances list`). Keep only images.
  Do not open firewall rules, create static IPs, buckets or service accounts.
