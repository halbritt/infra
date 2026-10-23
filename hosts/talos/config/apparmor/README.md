# AppArmor on talos

`agent-ee-container` is installed at `/etc/apparmor.d/agent-ee-container`
(root:root 0644, loaded at boot by `apparmor.service`, cache written with
`apparmor_parser -r -W`). `ae-ci-exec` selects it with
`--security-opt apparmor=agent-ee-container`.

It differs from agent-ee `docker/agent-ee.apparmor` (and the copy on
`agent-ee-gate-c4`, Ubuntu 24.04 / AppArmor 4.0.1), which is
`profile agent-ee-container flags=(unconfined) { userns, }`. The 2026-10-22
change, and why:

- Ubuntu 26.04 (AppArmor 5.0.2) ships `/etc/apparmor.d/bwrap-userns-restrict`,
  which defines `profile bwrap /usr/bin/bwrap` (allows userns and capabilities)
  and `profile unpriv_bwrap` (`audit deny capability`). Every bwrap child runs
  as `bwrap//&unpriv_bwrap`.
- A profile in unconfined mode ignores its own exec rules and, like the
  unconfined label, attaches an exec to any host profile whose attachment
  matches. Inside the container `/usr/bin/bwrap` therefore attached to `bwrap`,
  and agent-ee's nested Bubblewrap (a stage step in bwrap that runs KiCad in
  bwrap again) ran as `bwrap//&unpriv_bwrap`. The kernel logged
  `apparmor="DENIED" operation="capable" profile="unpriv_bwrap" comm="bwrap"
  capname="sys_admin"`, bwrap printed "No permissions to create new
  namespace", and `tests.test_add_planes` failed 2 tests.
- The installed profile is in enforce mode with `allow all,` and
  `attach_disconnected,mediate_deleted`. `allow all` grants the same access as
  before and its exec rule inherits (`ix`), so nothing inside the container
  attaches to host profiles; every level of bwrap stays `agent-ee-container`,
  as on the 24.04 hosts. The host `bwrap`, `unpriv_bwrap` and `:glycin:bwrap`
  profiles, `/etc/apparmor.d/local/`, and the sysctls
  (`kernel.apparmor_restrict_unprivileged_userns=1`,
  `kernel.apparmor_restrict_unprivileged_unconfined=1`) are unchanged.

The previous file is kept at `~/.cache/agent-ee-container.orig` on talos.
Rollback: `sudo install -m 644 ~/.cache/agent-ee-container.orig
/etc/apparmor.d/agent-ee-container && sudo apparmor_parser -r -W
/etc/apparmor.d/agent-ee-container`.

Caveat: agent-ee `scripts/container_apparmor.sh` reloads
`docker/agent-ee.apparmor` with `apparmor_parser -r`. Until agent-ee adopts this
profile, running that script on talos loads the old profile and brings the
failure back until the next boot or a reload of the file above. `ae-ci-exec`
does not run it.

Probe (labels at each bwrap level):

```sh
docker run --rm --network none --security-opt seccomp=unconfined \
  --security-opt systempaths=unconfined --security-opt apparmor=agent-ee-container \
  --user 1000:1000 --entrypoint /bin/sh agent-ee:exec-4ff2f011477682a7 -c \
  'cat /proc/self/attr/current; bwrap --ro-bind / / --dev /dev --proc /proc --unshare-pid sh -c \
   "cat /proc/self/attr/current; bwrap --ro-bind / / --dev /dev --proc /proc --unshare-pid cat /proc/self/attr/current"'
```

Before: `agent-ee-container (unconfined)`, `bwrap//&unpriv_bwrap (enforce)`,
then the namespace error. After: `agent-ee-container (enforce)` at all three
levels.

AppArmor 4 note (2026-10-23): talos's installed profile is `allow all,` only.
That is enough on AppArmor 5. On AppArmor 4.0.1 (proximal, c4) the same
profile denies bwrap's `rslave` mount. Adding explicit `mount,` `umount,`
`pivot_root,` and `userns,` rules works on both versions. See the proximal
CHANGELOG (AGENTEE-438 H1).
