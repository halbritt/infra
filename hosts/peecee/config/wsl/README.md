# WSL2 Ubuntu — Linux build node inside peecee

Set up 2026-10-20 so agents can offload Linux builds from proximal (heavily
loaded) onto peecee's i9-12900KS / 64 GiB without touching the Windows side.

## Reach it

```bash
ssh peecee-wsl            # proximal ~/.ssh/config alias → 100.113.63.58:2222, user halbritt
ssh -p 2222 halbritt@192.168.1.118   # LAN path, same thing
```

Key-only auth (proximal's `id_ed25519`), password auth off, root login off.
`halbritt` has passwordless sudo inside the distro. Hostname inside is
`peecee-wsl`. This is **separate** from `ssh peecee` (Windows OpenSSH, user
`halbr`, PowerShell) — the two do not share a filesystem view except via
`/mnt/c` from the WSL side.

## What is in here

| File | Lands at | Purpose |
|---|---|---|
| `.wslconfig` | `C:\Users\halbr\.wslconfig` | VM caps: 48 GB RAM, 24 CPUs, no swap, **`networkingMode=mirrored`** (WSL shares peecee's LAN+tailnet IPs — no port-proxy needed), `vmIdleTimeout=-1` |
| `wsl.conf` | `/etc/wsl.conf` | systemd on, hostname `peecee-wsl`, metadata automount |
| `setup-sshd.sh` | run once as root in the distro | installs `openssh-server` + `build-essential`, sshd on 2222 (`/etc/ssh/sshd_config.d/10-wsl.conf`), authorized key, sudoers drop-in |
| `install-wsl-keepalive.ps1` | run once, elevated, on Windows | installs `.wslconfig`; Scheduled Task **`WslKeepalive`** (At startup, as `halbr`, S4U, no time limit) that holds the distro open so sshd is up with no login session; Windows Firewall + Hyper-V firewall rules for TCP 2222 |

Staging copy of all of these lives at `C:\Users\halbr\wsl-setup\` on peecee.

## Operate (Windows side, elevated)

```powershell
Get-ScheduledTask WslKeepalive ; wsl -l -v
wsl --shutdown ; Start-ScheduledTask WslKeepalive   # apply a changed .wslconfig
wsl -d Ubuntu -u root -- bash                       # root shell without sshd
```

## Verified 2026-10-20

- `ssh peecee-wsl` from proximal over tailnet and over LAN → `peecee-wsl`, nproc 24, 47 GiB free.
- Distro stays Running after the launching SSH session ends (task-owned, not session-owned).
- Distro: Ubuntu 26.04.1 LTS, 1 TB ext4 virtual disk (`/dev/sdd`), gcc 15.2, git.
- **Not yet verified:** survival of a full peecee reboot (not rebooted — Ollama was serving).

## Caveats

- Keep build trees on the ext4 disk (`~`), not `/mnt/c`: cross-FS I/O is ~10× slower.
- GPU is shared with Ollama/Marker on Windows. CUDA works in WSL2 but competes for VRAM.
- Windows OpenSSH (`ssh peecee`) kills the process tree on disconnect; the WSL sshd
  does not, so long builds belong on `peecee-wsl` under `nohup`/`tmux`.
- No docker in the distro yet.
