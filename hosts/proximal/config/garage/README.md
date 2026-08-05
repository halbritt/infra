# proximal/garage — Garage S3 object storage (`:3900-3904`)

Desired-state + provenance for the **Garage** single-node S3 service on host **proximal**.
The `garage/` subsystem of the [`proximal`](../README.md) whole-system repo. Captured 2026-07-20.

Garage is the box's S3 endpoint — notably the object store behind the public Plane CE stack
(see [`../plane-public/`](../plane-public/)). Single node, replication factor 1, data on a
**file-backed LUKS volume** mounted at `/var/lib/garage`.

## At a glance

| | |
|---|---|
| version | `garage v2.3.0` — `/usr/local/bin/garage` |
| unit | `garage.service` (system, `User=garage`, hardened: `ProtectSystem=strict` etc.) |
| config | `/etc/garage.toml` (root:garage `0640`) — copy in this dir, **secret-free** (see below) |
| S3 API | `127.0.0.1:3900` (region `garage`) · web `:3902` · k2v `:3904` — loopback only |
| RPC / admin | `127.0.0.1:3901` (rpc) · `127.0.0.1:3903` (admin + metrics) |
| storage | `/var/lib/garage.img` (100 GiB loopback file) → LUKS `garage` → XFS on `/var/lib/garage` |
| db engine | lmdb · metadata auto-snapshot every 6h · compression level 2 |

## Storage chain (generated units)

The mount is driven by `/etc/crypttab` + `/etc/fstab`, which systemd turns into generated units
(`systemd-cryptsetup@garage.service`, `var-lib-garage.mount`) — the unit `Requires=` the mount,
so Garage never starts against an empty mountpoint. The exact lines on the box:

```
# /etc/crypttab
garage	/var/lib/garage.img	/root/garage.key	luks,loop,nofail

# /etc/fstab
LABEL=garage	/var/lib/garage	xfs	defaults,nofail,x-systemd.requires=systemd-cryptsetup@garage.service	0	2
```

`/root/garage.key` is the LUKS keyfile — root-only on the box, **never in this repo**.

## Secrets — referenced, never stored

`garage.toml` contains no secret material: it points at token *files* under `/etc/garage/`
(mode `0600`, owner `garage`), which stay on the box only:

| config key | file on box |
|---|---|
| `rpc_secret_file` | `/etc/garage/rpc_secret` |
| `admin_token_file` | `/etc/garage/admin_token` |
| `metrics_token_file` | `/etc/garage/metrics_token` |

S3 **access keys** (per-application, e.g. the Plane bucket credentials) live in Garage's own
metadata and in the consuming apps' uncommitted env files — also never here.

## Plane bridge

Docker-side consumers reach Garage via
[`../plane-public/plane-harm-org-garage-bridge.service`](../plane-public/plane-harm-org-garage-bridge.service)
(socat `172.17.0.1:13900` → `127.0.0.1:3900`), captured with the rest of the Plane stack in
`plane-public/` — verified identical to the installed unit on 2026-07-20; kept there, not
duplicated here.

## Files → install locations

| repo file | install path |
|---|---|
| `garage.service` | `/etc/systemd/system/garage.service` |
| `garage.toml` | `/etc/garage.toml` (install as root:garage `0640`) |

After editing: `sudo systemctl daemon-reload && sudo systemctl restart garage`.

## Manage

```bash
systemctl status garage var-lib-garage.mount
sudo systemctl restart garage
journalctl -u garage -f
curl -s -o /dev/null -w '%{http_code}\n' localhost:3900/   # S3 API up → 403 (unsigned request)
sudo -u garage garage -c /etc/garage.toml status           # cluster/node health
sudo -u garage garage -c /etc/garage.toml bucket list
sudo -u garage garage -c /etc/garage.toml key list         # key IDs only; secrets stay in garage
```

**Values, never credentials** — the unit, the (pointer-only) toml, and the crypttab/fstab lines
are versioned here; the LUKS keyfile, RPC secret, and all tokens/keys exist only on the box.
