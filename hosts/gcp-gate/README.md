# gcp-gate

The agent-ee release gate on Google Compute Engine: a private image family,
`agent-ee-gate` in project `heath-stuff`, and throwaway Spot VMs booted from it.
Each VM runs the same `~/agent-ee-gate/ci-run.sh` as peecee-wsl, so a gate result
here means the same thing as one there. Requested by the owner on 2026-10-21 to
move the CPU-bound gate off shared hosts. Build and run scripts:
[`config/image/`](config/image/README.md).

## Current image

| | |
|---|---|
| Image | `agent-ee-gate-20261022-0352`, family `agent-ee-gate`, storage `us-west1`, labels `purpose=agent-ee-gate,owner=halbritt` |
| Self link | `https://www.googleapis.com/compute/v1/projects/heath-stuff/global/images/agent-ee-gate-20261022-0352` |
| Created | 2026-10-21T21:02:42-07:00; 100 GB disk, 7.50 GB archive (7500887616 bytes) |
| Base | `ubuntu-2404-noble-amd64-v20261021` (family `ubuntu-2404-lts-amd64`) |
| Docker | Ubuntu `docker.io` 29.1.3 (`29.1.3-0ubuntu3~24.04.2`) and `docker-buildx` 0.30.1 (`0.30.1-0ubuntu1~24.04.1`), both held. Same upstream versions and the same Ubuntu packaging as peecee-wsl (`29.1.3-0ubuntu4.1` / `0.30.1-0ubuntu1` on 26.04). containerd image store (overlayfs snapshotter), as on peecee-wsl. |
| Other packages | git, rsync, jq, python3, apparmor, apparmor-utils, zstd, curl |
| User | `halbritt` (uid 1001: the GCE image already has `ubuntu` at 1000), groups `docker`; `/etc/sudoers.d/agent-ee-gate` allows `sudo -n` for `apparmor_parser` and `chown` only, the two commands ci-run.sh runs. The guest agent also adds SSH users to `google-sudoers`. |
| AppArmor | enabled. ci-run.sh loads the commit's `agent-ee-container` profile on every run (unlike peecee-wsl, where WSL has no AppArmor and the profile is `unconfined`). This matches hosted CI. A copy in `/etc/apparmor.d/agent-ee-container` keeps it loaded after boot for `ae-ci-exec`. |

### Contents of `/home/halbritt`

| Path | What |
|---|---|
| `agent-ee-gate/ci-run.sh` | byte-identical to peecee-wsl, sha256 `2c5c20f80838a26e49a21fecce0af5c64a14609ef7cc4d69215c7b4ec3eea3e5` |
| `agent-ee-gate/ci-logs/`, `ctx/`, `tmp/` | empty (ci-run.sh needs `tmp/` for its summary dir) |
| `agent-ee-gate/inputs/te-776228-1.pdf` | J1 drawing, sha256 `14bd5c3b…6e4fe8` (ci.yml `J1_DRAWING_SHA256`) |
| `agent-ee-gate/ci-inputs/fome-mc-1289f3149d2bcaa83a3b490a0bfbd11ed8a17589` | anonymous clone of public github.com/halbritt/fome-mc at the ci.yml `FOME_MC_COMMIT`, owned 10001:10001, no credential config (the ci-run.sh recipe) |
| `.local/bin/ae-ci-exec` | sha256 `0e8cb9d2cd030755859932a52bcbbe3d1207039f195385aa5e20cf2d61015290` ([`shared/agent-ee`](../../shared/agent-ee/README.md)) |

Docker holds `agent-ee:ci-14ef7275` and its BuildKit cache (about 6 GB), so a
new `agent-ee:ci-SHA` build reuses the toolchain layers (KiCad 10.0.7 with
kicad-packages3d, ngspice 42, Bubblewrap, the Rust build stage, kicad-route
5f1c072, kicad-happy 2.3.1 at 06840467). The build context was deleted.

kicad-route and kicad-happy are not host checkouts: the Dockerfile pins and
fetches both into the image (`docker/kicad-route/install.sh`, `KICAD_HAPPY_COMMIT`).
ci-run.sh reads only the two host inputs above. There is no agent-ee bare mirror
(the repository is private), so contexts are staged with `git archive`.

Not in the image: credentials of any kind, SSH host keys, `authorized_keys`,
shell history, apt lists, machine-id, and `.git` directories other than the
public fome-mc store. VMs run with no service account.

## Run a gate

Default recipe (owner, 2026-10-21): a Spot `c2d-highcpu-16` with
termination action DELETE, `JOBS=8` as on peecee-wsl. From proximal:

```sh
~/git/infra/hosts/gcp-gate/config/image/run-gate.sh SHA
```

It creates the VM, stages `git archive SHA`, runs `JOBS=8 ./ci-run.sh SHA >
ci-logs/gate-SHA.out` detached, polls for `=== exit N`, copies `ci-logs/` to
`~/agent-ee-gate-gcp/SHA-<stamp>/` and deletes the VM. A preemption deletes the
VM; the script retries on a new one (3 attempts) and reports the count. By hand:

```sh
gcloud compute instances create agent-ee-gate-SHA --zone us-west1-b \
  --machine-type c2d-highcpu-16 --provisioning-model=SPOT --instance-termination-action=DELETE \
  --max-run-duration=3h --image-family agent-ee-gate --image-project heath-stuff \
  --boot-disk-size=100GB --boot-disk-type=pd-balanced --no-service-account --no-scopes \
  --labels purpose=agent-ee-gate,owner=halbritt
git -C ~/git/agent-ee archive SHA | gcloud compute ssh agent-ee-gate-SHA --zone us-west1-b \
  --command 'mkdir -p ~/agent-ee-gate/ctx/SHA && tar -x -C ~/agent-ee-gate/ctx/SHA'
gcloud compute ssh agent-ee-gate-SHA --zone us-west1-b \
  --command 'cd ~/agent-ee-gate && JOBS=8 ./ci-run.sh SHA > ci-logs/gate-SHA.out 2>&1; tail -n 3 ci-logs/gate-SHA.out'
gcloud compute instances delete agent-ee-gate-SHA --zone us-west1-b --quiet
```

SSH uses the project-metadata key (`~/.ssh/google_compute_engine`) over the
default network's existing SSH rule; no firewall change.

## Validation (2026-10-22, agent-ee main 14ef7275)

`REBUILD=1 run-gate.sh 14ef7275` on Spot `c2d-highcpu-16` (us-west1-b), `JOBS=8`,
0 preemptions. REBUILD forces the image build so the warm cache is exercised.

```
strict suite passed: 258 modules, 4789 tests, no skips.

=== exit 0; log /home/halbritt/agent-ee-gate/ci-logs/14ef7275-20261022T040740Z.log
```

| | GCE c2d-highcpu-16, JOBS=8 | peecee-wsl, JOBS=8 (fc9c9cae) |
|---|---|---|
| image build | 3 s (all layers cached) | cached |
| ci-run.sh wall | about 18 min (1099 s, 60 s polling) | about 21 min (02:20:38Z to 02:41:25Z) |

Module times sum to 8108 s; the longest module (`test_placement_campaign`)
takes 448 s, which bounds the wall time however many JOBS are used. The doctor
JSON is identical across the two GCE runs.

## Cost

Measured with Cloud Billing catalog prices for us-west1 on 2026-10-22 (Spot
prices change):

| Item | Price |
|---|---|
| Spot c2d-highcpu-16 (16 × $0.01428 + 32 GiB × $0.001915) | $0.29/h |
| 100 GB pd-balanced | $0.10/GB-month, about $0.014/h |
| One gate run (about 25 min with boot and staging) | about $0.13 |
| Image storage (7.5 GB archive × $0.05/GB-month) | about $0.38/month |
| Spot c4-highcpu-96 (96 × $0.02074 + 192 GiB × $0.002357) | $2.44/h, plus about $0.08/h for 200 GB Hyperdisk Balanced at 10000 IOPS / 440 MiB/s |

The image build and validation (two builds, two gate runs, about 70 Spot
VM-minutes) cost about $0.40.

## Long-running C4 work host (blocked by quota)

Owner request 2026-10-21: one Spot `c4-highcpu-96` host that stays running.
Not launched. Every us-* region lacks the C4 quota for 96 vCPUs
(`CPUS-PER-VM-FAMILY-per-project-region`, `vm_family=C4`): 0 in us-west1 and
us-west2 (create refused: "Quota 'CPUS_PER_VM_FAMILY' exceeded. Limit: 0.0"),
48 in us-central1, 24 in us-east1, us-east4, us-east5, us-south1, us-west3 and
us-west4. `PREEMPTIBLE_CPUS` is 0 everywhere, so Spot VMs use the standard quotas.
The recipe, once the owner raises the quota:

```sh
gcloud compute instances create agent-ee-gate-c4 --zone ZONE --machine-type c4-highcpu-96 \
  --provisioning-model=SPOT --instance-termination-action=STOP \
  --image-family agent-ee-gate --image-project heath-stuff \
  --boot-disk-size=200GB --boot-disk-type=hyperdisk-balanced \
  --boot-disk-provisioned-iops=10000 --boot-disk-provisioned-throughput=440 \
  --no-service-account --no-scopes --labels purpose=agent-ee-gate,owner=halbritt
```

Hyperdisk needs IOPS and throughput together; 440 MiB/s is the default for
200 GiB (`MIN(2400, 1.5 × 200 + 140)`). A STOP preemption changes the ephemeral
external IP, so an `ssh agent-ee-gate-c4` alias should look the address up:

```
Host agent-ee-gate-c4
  User halbritt
  IdentityFile ~/.ssh/google_compute_engine
  IdentitiesOnly yes
  HostKeyAlias agent-ee-gate-c4
  UserKnownHostsFile ~/.ssh/google_compute_known_hosts
  ProxyCommand sh -c 'exec nc "$(gcloud compute instances describe agent-ee-gate-c4 --zone ZONE --format="value(networkInterfaces[0].accessConfigs[0].natIP)")" %p'
```
