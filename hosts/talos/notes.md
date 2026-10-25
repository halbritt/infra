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
- No AppArmor profile for agent-ee (owner, 2026-10-23). The userns sysctl relaxation
  added for it was removed again on 2026-10-24, when talos left agent-ee.
- The Dockerfile's apt snapshot is `noble` (24.04) and cannot be installed on
  26.04. KiCad 10.0.7 comes from the same Launchpad snapshot timestamp with
  suite `resolute` (`config/apt`, deleted 2026-10-24 with KiCad). ngspice 45.2,
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

## Retired from agent-ee — 2026-10-24

See README "Retired from agent-ee". The fleet-worker notes above are history.

## Striatum credential delivery repaired — 2026-10-24

The migration left the standard Claude harness with a regular credential file
that expired while the mirrored source profile continued to change. The Harm
harness already used a symlink. Proximal's source-only refresher also aborted on
an obsolete local write into its retired read-only Striatum data; infra commit
`d307152d430dbae07894a1ea1ccbd211746d3e1c` removed that write. Its existing
17:15 PDT timer then refreshed Harm and delivered both access-only profiles to
Talos. No manual login or refresh was invoked.

The canonical installer in `config/striatum/` links both harness credential files
to those existing mirrored profiles. Validation records only permissions,
expiry and absence of refresh fields; no token values enter Git or logs.
Native account holds and attempt history remain unchanged.
