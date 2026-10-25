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
| `provision-toolchains.sh` | run as `halbritt` over `ssh peecee-wsl` (idempotent) | everything an agent needs to build and test: see **Toolchains** |
| `provision-postgres.sh` | run as `halbritt` over `ssh peecee-wsl` (idempotent) | local PostgreSQL 18 + pgvector, peer-auth socket, role `halbritt` (CREATEDB, CREATEROLE), dbs `engram` / `engram_test` / `hippo` with `vector` + `pgcrypto` — what engram/hippo tests assume from proximal |
| `install-wsl-keepalive.ps1` | run once, elevated, on Windows | installs `.wslconfig`; Scheduled Task **`WslKeepalive`** (At startup, as `halbr`, S4U, no time limit) that holds the distro open so sshd is up with no login session; Windows Firewall + Hyper-V firewall rules for TCP 2222 |

Staging copy of all of these lives at `C:\Users\halbr\wsl-setup\` on peecee.

## Toolchains (provisioned 2026-10-20)

Chosen from what proximal's `~/git` repos actually use (44 python, 21 node,
9 go, 3 cmake, 2 rust, docker compose in several).

| Tool | Version | Source |
|---|---|---|
| gcc / g++ / make, cmake, ninja, ccache, gdb, pkg-config | gcc 15.2, cmake 4.2 | apt |
| python3, venv, pip, dev headers + `uv` | 3.14.4 / uv 0.13 | apt + astral installer (`~/.local/bin`) |
| node + npm (prefix `~/.npm-global`) | 24.x | NodeSource apt repo |
| go | latest stable (1.27) | go.dev tarball → `/usr/local/go` |
| rust (rustup, minimal profile) | stable | rustup → `~/.cargo` |
| docker + compose v2 (halbritt in `docker` group) | 29.x | apt `docker.io`, `docker-compose-v2` |
| gh, ripgrep, ugrep, jq, tmux, shellcheck, sqlite3, git-lfs, postgresql-client | | apt |
| libssl/libffi/libpq/zlib/libsqlite3 dev headers | | apt |
| bubblewrap, slirp4netns, uidmap, binutils | | apt — council's isolated-execution suites |
| `claude`, `codex`, `opencode` CLIs | | `npm -g` (user prefix) |
| `git-wt` / `git-land` | | wrappers around `~/git/cairn/scripts/git_trunk_tools.py` (cairn cloned to `~/git/cairn`) |

PATH for all of the above is set in **`/etc/environment`** (literal `/home/halbritt/...`
entries) because non-interactive `ssh peecee-wsl <cmd>` sources neither `.bashrc`
nor `.profile`; interactive shells also get `~/.profile.d-toolchains.sh`.

GitHub: `gh auth login --with-token` was fed proximal's `gh auth token` and
`gh auth setup-git` wired the credential helper, so private `halbritt/*` repos
clone and push over HTTPS. Git identity set to `halbritt <halbritt@gmail.com>`.
Revoke/rotate on GitHub if peecee is ever considered compromised.

### Proven 2026-10-20 (over non-interactive `ssh peecee-wsl`)

- **Go:** `halbritt/cairn` — `go build ./...` + `go test ./...` all packages `ok`.
- **Python + docker + local postgres:** `halbritt/engram` (private) — `HIPPO_REPO=~/git/hippo make test-docker`
  (venv install, `docker compose` postgres on :54329, pytest): **2528 passed, 5 failed,
  1h39m** on the first full run. 4 failures were tests that use engram's default
  `postgresql:///engram` socket URL (proximal has a local cluster, WSL had none) →
  fixed by `provision-postgres.sh` + `make migrate`; the 5th (`test_restore_smoke_cleans_up_after_signal`)
  passed 3/3 in isolation — a signal-timing flake under full-suite load. All 5 pass
  after provisioning. The suite is slow here mainly because it is serial; expect ~1.5 h.
- **Node:** `halbritt/council` — `npm ci && npm test` (build + vitest): 890 passed,
  2 failed. Both failures are council hardcoding `/sbin/ldconfig.real`
  (`src/v3/runtime-resolver.ts` `DEFAULT_LDCONFIG`); Ubuntu 26.04 ships the real
  ELF at `/sbin/ldconfig` with no `.real` wrapper. Council bug, not a host gap —
  filed as Plane **COUNCIL-1** (work instance, project Council created 2026-10-21 for it).
- **Rust:** `cargo init && cargo test` ok. **docker:** `hello-world` ok.
- **git-wt:** `git-wt create` placed the worktree under `~/.cache/agent-worktrees/cairn/`.
- A pytest run kept running after the launching SSH session was killed (10-min
  client timeout) — long jobs survive disconnects here, unlike Windows OpenSSH.

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
