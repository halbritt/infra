# proximal host notes

`proximal` is the original machine represented by this repository: an Ubuntu
workstation and home-lab node that also carries server responsibilities. Its
hardware and stable network metadata are in [`machine.yaml`](machine.yaml).

## Configuration ownership

All configuration that was formerly at the repository root now lives under
[`config/`](config/). Each immediate child is still a self-contained subsystem;
the move changes repository topology, not the subsystem's operational authority
or live behavior.

The host-wide operational ledger is [`CHANGELOG.md`](CHANGELOG.md). Dense
PostgreSQL history remains in
[`config/postgres/CHANGELOG.md`](config/postgres/CHANGELOG.md). Plane operating
guidance remains in [`PLANE_AGENT_GUIDE.md`](PLANE_AGENT_GUIDE.md).

## Host exceptions

- Most canonical files are installed to `/etc`, `~/.config`, or another runtime
  location. The subsystem README records the exact mapping.
- `config/tailscale-index/` is intentionally served directly from this checkout.
  Its unit therefore contains the full infrastructure-layout path and must be reinstalled
  if the checkout moves.
- The SMS gateway and plant-to-Praxis bridge also execute their Python entry
  points directly from this checkout. Their installed units must track path
  changes.
- The local GPU is shared by the primary llama.cpp service, Ollama embeddings,
  and whisper.cpp. A configuration that is valid for one service can still be an
  invalid whole-host allocation.
- Retired subsystems remain in the host record when their rollback path and
  incident history are still useful. Retirement is not permission to erase
  provenance.
- Kubernetes is retired on this host. Do not reinstall kubeadm, kubelet,
  kubectl, CNI packages, or the Kubernetes apt source without a new owner decision.
  Docker and its `containerd.io` runtime remain in service. The retired cluster
  state and rollback archive were deleted at the owner's request.

## Sensitive metadata

This host record intentionally contains non-secret but sensitive operational
metadata such as private addresses, public hostnames, hardware identifiers, a
cellular line and modem identifiers, Slack application identifiers, and service
topology. Treat repository access accordingly. Credentials remain outside Git;
see [`../../secrets/README.md`](../../secrets/README.md).
