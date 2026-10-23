# talos notes

## Initial record — 2026-10-22

Recorded at the owner's request from a read-only SSH survey from proximal
(`ssh talos`), about 45 minutes after first boot. The installer log directory
and root filesystem birth time are both 2026-10-22 04:59 UTC. `cloud-init` is
disabled after install. One user session (`halbritt`, SSH) was present.

Observations to act on only with owner direction:

- 30 packages were upgradable. Unattended-upgrades applies only the security
  origins.
- The root LV uses 100 GiB of a 474 GiB volume group (Subiquity default).
  Extend with `lvextend -r` when space is needed.
- An older `linux-image-unsigned-7.0.0-30-generic` is installed alongside the
  running `7.0.0-38` generic kernel.
- Timezone was `Etc/UTC` (changed to `America/Los_Angeles` the same day at the owner's request).
- Wi-Fi is the only link. MACs: `eno1` `1c:69:7a:63:e5:ff`, `wlp0s20f3`
  `0c:7a:15:6c:b9:7f` (useful for a DHCP reservation).

## Fleet worker setup — 2026-10-22

- The root LV is still 100 GiB (about 82 GiB free after setup). The CI image
  and BuildKit cache fit; if `docker system df` grows, extend with `sudo
  lvextend -r -L +100G /dev/ubuntu-vg/ubuntu-lv` (not done; no owner request).
- No AppArmor profile for agent-ee (owner, 2026-10-23). The distro profiles stay
  loaded, but `/etc/sysctl.d/60-agent-ee-userns.conf` sets
  `kernel.apparmor_restrict_unprivileged_userns=0`, so `ae-ci-exec` containers run with
  `apparmor=unconfined` and bwrap inside them can create user namespaces.
- The Dockerfile's apt snapshot is `noble` (24.04) and cannot be installed on
  26.04. KiCad 10.0.7 comes from the same Launchpad snapshot timestamp with
  suite `resolute` (see [config/apt](config/apt/README.md)). ngspice 45.2,
  bubblewrap 0.11.1 and poppler 26.01 are stock 26.04, the same as peecee-wsl.
  The CI image (24.04: ngspice 42, bwrap 0.9.0, poppler 24.02, Python 3.12) is
  the test authority.

## Worker provisioning observed — 2026-10-22

Within an hour of the initial record, another agent (agent-ee dispatch from
proximal) had installed `docker.io` and KiCad `10.0.7~ubuntu26.04.1` from the
KiCad 10.0 snapshot PPA, plus ngspice, poppler-utils and bubblewrap. It apt-held
`docker.io`, `docker-buildx` and the four KiCad packages. It also cloned
`agent-ee`, `cairn`, `fome-mc` and `kicad-happy` into `~/git` and was running
headless `claude-harm` workers in `~/.cache/agent-worktrees/agent-ee/`. That
provisioning is not yet recorded here. The update policy was shaped around it.
