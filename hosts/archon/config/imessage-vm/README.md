# imessage-vm (archon)

Always-on macOS guest on archon that keeps the owner's iMessage running
independently of the MacBook. It provides Windows access through BlueBubbles
and read-only agent access through imessage-mcp. Deployed 2026-10-19.

## Architecture

```text
Windows (peecee) BlueBubbles client ──https://archon.tail0ecc2e.ts.net:8443──┐
Agents (Claude Code on archon, …)  ──https://archon.tail0ecc2e.ts.net:8765──┐ │  tailscale serve
                                                                             │ │  (tailnet only)
archon (Omarchy/Arch, i7-1360P, 62 GiB)                                      ▼ ▼
  imessage-vm-mcp-tunnel.service  127.0.0.1:18765 ─ssh -L─┐      127.0.0.1:11234
  imessage-vm.service (QEMU/KVM, user imsgvm)             │           │ hostfwd
    macOS 15.8.1 guest, user `imessage` (auto-login)      ▼           ▼
      imessage-mcp 3.2.0 (LaunchAgent, 127.0.0.1:8765)    BlueBubbles 1.9.9 (:1234)
      Messages.app (Apple Account, Messages in iCloud)
```

- Guest networking is QEMU user networking (archon is Wi-Fi only, so no
  bridge). Host forwards bind loopback only: guest SSH `127.0.0.1:10022`,
  BlueBubbles `127.0.0.1:11234`. imessage-mcp binds guest loopback, so archon
  reaches it through an SSH tunnel whose guest key may forward only that port.
- Private console: the QEMU VNC unix socket `/run/imessage-vm/vnc.sock`
  (group `imsgvm`, no VNC auth). It is reachable only through SSH to archon.
- Tailscale Serve terminates TLS with archon's tailnet certificate. Funnel is
  off, and nothing is exposed outside the tailnet.

## Versions and why

| Component | Version | Notes |
|---|---|---|
| macOS guest | 15.8.1 Sequoia (24H32) | imessage-mcp needs ≥14. **Not Tahoe:** BlueBubbles #777 breaks non-Private-API AppleScript sends on 26 (`any;-;` chat GUIDs), #761 crashes on connect. Installed from Apple recovery (OSX-KVM `fetch-macOS-v2.py`, chunklist-verified, `DmgLoading=Signed`). |
| QEMU | 11.1.1 (Arch `qemu-base`) | Installed from the Arch Linux Archive at the exact versions in archon's sync DB (mirrors had moved on; no `-Syu`). |
| OSX-KVM | 4c378a4 | OVMF (Debian edk2 2025.11), CPU line `Skylake-Client,-hle,-rtm,…` for Sequoia/Tahoe. |
| OpenCore | 1.0.8 | Config base: LongQT-sea/OpenCore-ISO v0.7 (the config OSX-KVM adopted). Changes in `opencore/render-config.py`: VMHide after Lilu, no VoodooPS2, builtin picker, `HideVerbose` keys, identity. `ocvalidate` clean. OSX-KVM's own `OpenCore.qcow2` was inconsistent (config references kexts absent from the image; Lilu 1.6.8), so it is unused. |
| Kexts | Lilu 1.7.2, VirtualSMC 1.3.8, WhateverGreen 1.7.1, VMHide 2.0.0, AppleMCEReporterDisabler | VMHide hides `kern.hv_vmm_present` from Apple Account processes (needed on 15+; OSX-KVM's kernel patch was dropped in its Tahoe config). |
| BlueBubbles server | 1.9.9 (Intel DMG, sha256 in `guest/bootstrap-root.sh`) | Developer ID signed (team WPV275H8W7) but **not notarized** upstream; codesign plus team ID verified at install. Afterwards the app writes `cloudflare.pid` into its own bundle, which breaks the seal. Private API off; Automation (control Messages) granted. |
| BlueBubbles Windows | 2.1.3 (`bluebubbles_installer.exe`, sha256 e61e3493…, Authenticode SignPath Foundation) | Installed per-user on peecee. |
| Node.js | 24.22.0 LTS at `/opt/imessage-mcp/node` | SHASUMS256-verified; signed by the Node.js Foundation (HX7739G8FX). |
| imessage-mcp | 3.2.0 at `/opt/imessage-mcp/app` | Pinned, not `@latest`. HTTP transport, `IMESSAGE_UPDATE_CHECK=0`, privacy `full` (attachments). |

All artifact hashes are in `upstream.lock` or the bootstrap scripts.

## Resources and paths

- VM: 4 vCPU (`-smp 4,cores=2,threads=2`), 8 GiB RAM, CPUWeight/IOWeight 50
  (the desktop wins contention), `ManagedOOMPreference=avoid`.
- State: btrfs subvolume `/var/lib/imessage-vm` (excluded from snapper's root
  snapshots). Owner `imsgvm:imsgvm`, mode 0750. Inside it:
  - `disks/macos.qcow2`: 256 GiB thin, NOCOW, discard.
  - `boot/OpenCore.img` (+ `.prev`), `boot/recovery.img` (install only).
  - `firmware/OVMF_CODE_4M.fd` (read-only) and `firmware/OVMF_VARS.fd`
    (writable NVRAM).
  - `identity/` (0700): `identity.env` (SMBIOS model, serial, MLB, UUID, ROM,
    MAC), SSH keys, guest known_hosts, secrets.
  - `src/` (OSX-KVM checkout, artifact cache).
- Host tooling: `/usr/local/lib/imessage-vm/`, `/etc/imessage-vm/vm.conf`,
  units `/etc/systemd/system/imessage-vm{,-mcp-tunnel}.service`, guest files
  `/usr/local/share/imessage-vm/guest/`. Install or refresh everything with
  `sudo ./install.sh` from this directory.
- Guest: `/opt/imessage-mcp/{node,app}` (root-owned), the LaunchAgent at
  `~imessage/Library/LaunchAgents/org.halbritt.imessage-mcp.plist`, its log at
  `~imessage/Library/Logs/imessage-mcp.log`, the session watchdog
  `/opt/imessage-vm/bin/session-watchdog` with its LaunchAgent
  `org.halbritt.imessage-vm-watchdog`, and the token at
  `~/.config/imessage-mcp/token` (0600).

### Identity

Generated once by `bin/imessage-vm-init-identity` (macserial from OpenCore
1.0.8; random MAC with QEMU OUI; ROM = en0 MAC). It refuses to overwrite.
iMac19,1, `en0` is IOBuiltin/IOPrimaryInterface (NIC pinned at 00:12.0 to match
the base config's `built-in` DeviceProperty). `IOPlatformUUID` is
`3CF94BDE-6B9A-51CE-91F7-5483B85D2145` and was stable across restarts. Not
derived from the owner's MacBook. The identity, disk, OVMF vars and OpenCore
image are one unit: back up and restore them together.

### Secrets (names only; values never in Git or logs)

| Secret | Location | Consumer |
|---|---|---|
| macOS `imessage` password | `identity/macos-imessage-password` | auto-login (`/etc/kcpassword` in guest), sudo, typed into prompts via `imessage-vm-ctl type -` (stdin) |
| BlueBubbles server password | `identity/bluebubbles-password` | BlueBubbles server; Windows client |
| imessage-mcp bearer token | `identity/imessage-mcp-token`; guest `~/.config/imessage-mcp/token`; archon `~halbritt/.config/imessage-mcp/token` | MCP server and clients (separate from the BB password) |
| host → guest SSH keys | `identity/host_ed25519` (forced `shutdown -h now`), `identity/tunnel_ed25519` (forward to 127.0.0.1:8765 only) | stop hook, MCP tunnel |

Read them with `sudo cat` on archon. Never echo them into a command line;
pipe them instead.

## Connecting

### Windows: BlueBubbles client

Server URL `https://archon.tail0ecc2e.ts.net:8443`, plus the BlueBubbles
password. peecee was set up 2026-10-19 (TigerVNC 1.16.2 and the BlueBubbles
client via winget/installer). For another Windows machine on the tailnet:
install the client from <https://bluebubbles.app/downloads/>, choose manual
entry, and enter the URL and password. Without Private API, the client can
send and receive text and attachments in existing and new 1:1 chats, see
history, and get notifications while open. It cannot send tapbacks, threaded
replies, edits or unsends, typing indicators, read receipts or effects, and it
cannot create group chats. Firebase/Google is not configured, so there is no
Android-style push; desktop clients hold a live socket.

### Console (GUI steps only)

From peecee: double-click `Desktop\imessage-vm-console.cmd`
(`windows/imessage-vm-console.ps1`). It opens an SSH tunnel to the VNC socket
and launches TigerVNC. Click inside the window before typing. Elsewhere:
`ssh -N -L 127.0.0.1:5901:/run/imessage-vm/vnc.sock archon`, then point a VNC
viewer at `localhost:5901`. peecee's key on archon is
`restrict,port-forwarding,command="/usr/bin/false"` (OpenSSH's `permitopen`
would also block the unix-socket forward). archon backup:
`~/.ssh/authorized_keys.bak-20261019`.

### Agents: read-only MCP

Endpoint `https://archon.tail0ecc2e.ts.net:8765/mcp` (tailnet only), Streamable
HTTP, `Authorization: Bearer <token>`. Allowed Host/Origin values:
`localhost,127.0.0.1,archon.tail0ecc2e.ts.net`. The 8 tools are `server_status`,
`resolve_contact`, `list_conversations`, `get_conversation`, `search_messages`,
`analyze_communication`, `get_attachment` and `sync_messages` (cursor-based
new-message feed). All are `readOnlyHint`; there are no send, edit, react,
delete or mark-read tools. The server enforces 60 requests/min and 2
concurrent requests.

- archon, Claude Code (connected): user-scope server `imessage` with
  `headersHelper` `~/.local/bin/imessage-mcp-headers` (`client/`), which reads
  the 0600 token file.
- Windows, Claude Code (not installed on peecee yet): put the token in
  `%USERPROFILE%\.config\imessage-mcp\token`, then
  `claude mcp add --transport http --scope user imessage https://archon.tail0ecc2e.ts.net:8765/mcp --header "Authorization: Bearer <token>"`.
  This stores the token in `~/.claude.json`; a `headersHelper` PowerShell
  script avoids that.
- Windows, Claude Desktop or another stdio-only client: bridge with
  `npx -y mcp-remote https://archon.tail0ecc2e.ts.net:8765/mcp --header "Authorization:${AUTH}"`
  and set `AUTH=Bearer <token>` in the server's `env`.
- Hosted clients (ChatGPT custom connectors, Claude.ai custom connectors) are
  **not connected and deliberately not supported**. They call MCP servers from
  the provider's cloud, so they need a public HTTPS endpoint with OAuth, and
  neither sends static bearer headers. imessage-mcp's SECURITY.md declares
  public exposure and Funnel unsupported. Hosted access would require a public
  OAuth gateway in front of private messages; do not build one without an
  explicit owner decision.

Untrusted content: message text can contain prompt injection. imessage-mcp
labels it as data, and agents should treat it so.

## Operations

```sh
# VM
sudo systemctl start|stop|restart|status imessage-vm        # stop = graceful macOS shutdown (≤200 s)
journalctl -u imessage-vm -u imessage-vm-mcp-tunnel -f
imessage-vm-ctl status | screendump /var/lib/imessage-vm/logs/s.png | powerdown
imessage-vm-guest ssh [cmd]                                 # shell in the guest as imessage (from archon)
# Guest services (inside the guest)
launchctl print gui/501/org.halbritt.imessage-mcp | grep -E 'state|pid'
launchctl kickstart -k gui/501/org.halbritt.imessage-mcp    # restart MCP
tail -f ~/Library/Logs/imessage-mcp.log
pkill -x BlueBubbles   # the watchdog restarts it within 60 s (log: ~/Library/Logs/imessage-vm-watchdog.log)
# Edge
sudo tailscale serve status                                 # 8443 → BB, 8765 → MCP
```

Startup chain (each piece has one mechanism):
1. archon boots: TPM unlock, see [tpm-unlock](../tpm-unlock/README.md).
2. `imessage-vm.service` (enabled, `Restart=on-failure`) starts the VM, and
   pulls in `imessage-vm-mcp-tunnel.service` (`Restart=always`).
3. OpenCore boots macOS (its own volume is hidden via `.contentVisibility`).
4. macOS auto-logs-in `imessage` (FileVault off; the disk image sits on
   archon's LUKS volume).
5. LaunchAgents start imessage-mcp (KeepAlive, ThrottleInterval 30) and the
   session watchdog (RunAtLoad + every 60 s). The watchdog starts Messages and
   BlueBubbles if they are missing; `open` does nothing to a running app.
   BlueBubbles' own auto-start is set to "Do Not Auto Start", with "Start
   Minimized" on. Its "Launch Agent (Crash Persistent)" mode does not
   restart it: the app relaunches itself detached, the launchd job exits 0,
   and a `kill -9` was never recovered (tested 2026-10-19).

The guest never sleeps (`pmset sleep 0 displaysleep 0 disksleep 0 standby 0
hibernatemode 0`, screen saver off, screen lock off, QEMU `disable_s3`, plus
BlueBubbles' keep-awake). macOS and App Store updates are not automatic;
security and config-data updates are.

The GUI session must exist: Messages, BlueBubbles and Full Disk Access depend
on the logged-in `imessage` user. If auto-login breaks, the services stop
until someone logs in through the console.

## Backup and restore

The unit of backup is the whole `/var/lib/imessage-vm` subvolume: disk,
OVMF_VARS, OpenCore image and `identity/` together. Restoring a disk without
its identity or NVRAM changes the Mac as Apple sees it.

```sh
sudo systemctl stop imessage-vm
sudo btrfs subvolume snapshot -r /var/lib/imessage-vm /var/lib/imessage-vm-snap-$(date +%F)
sudo systemctl start imessage-vm
# off-host copy: send the read-only snapshot, or tar it (qcow2 is sparse: use --sparse)
# restore: stop VM; replace /var/lib/imessage-vm contents from the snapshot; start
```

Message history is also in iCloud (Messages in iCloud), so a lost guest can be
rebuilt and resynced. It keeps the same identity if `identity.env` survives.

## Upgrade and rollback

Snapshot first (above) before any of these.

- macOS 15.x updates: System Settings → Software Update over the console,
  then re-check Messages, BlueBubbles and MCP. **Decline macOS 26 Tahoe** until
  BlueBubbles fixes #777/#761 and VMHide supports it. Rollback = restore the
  snapshot.
- OpenCore/kexts: edit `upstream.lock` plus the pins in
  `bin/imessage-vm-build-boot`, then `sudo imessage-vm-build-boot fetch &&
  sudo imessage-vm-build-boot opencore` (it runs `ocvalidate` and keeps
  `OpenCore.img.prev`). Rollback: `mv OpenCore.img.prev OpenCore.img`, restart.
- imessage-mcp or Node: bump `MCP_VER`/`NODE_VER` in `guest/bootstrap-root.sh`,
  `sudo ./install.sh`, then `imessage-vm-guest bootstrap` (Node keeps
  `/opt/imessage-mcp/node.prev`). Full Disk Access is tied to the stable path
  and the Node.js Foundation signature. Re-check `server_status`.
- BlueBubbles: bump `BB_VER`/`BB_SHA256` and rerun the bootstrap. Rollback by
  reinstalling the previous DMG.
- QEMU: updated by archon's normal system updates; takes effect on VM restart.

## Verification (2026-10-19)

Passed and observed:
- KVM with nested support on archon; the CPU has AVX2/SSE4.2 (Sequoia
  requirement).
- Recovery verified against Apple's chunklist (85/85) and loaded via OpenCore
  `DmgLoading=Signed`. Installed unattended with `startosinstall`.
- `kern.hv_vmm_present=0`, VMHide/Lilu/VirtualSMC loaded, `en0` built-in.
- Native gate: owner signed in to the Apple Account with Messages in iCloud
  and Contacts. A `vm-test-5b9b0b` iMessage from the iPhone was received in the
  guest at 15:02:19 PDT; one from the account at 15:02:45. History synced
  (50+ conversations).
- Controlled guest restarts (before sign-in): graceful stop in 7 s,
  unattended boot to the auto-logged-in desktop in about 30 s, identity
  unchanged, imessage-mcp up from launchd with FDA.
- BlueBubbles: FDA pass, API ping on loopback, HTTPS through Serve from
  peecee (401 without a password), Cloudflare tunnel off.
- MCP: initialize, tools/list (8 read-only tools), 401 for a missing or wrong
  token, `server_status` live, `search_messages` found both test messages.
  Done by curl and by a headless Claude Code agent on archon over the tailnet
  endpoint.

- Windows client (peecee): history synced; a received message appeared; a
  send was delivered in 0.75 s once Automation (control Messages) was
  allowed. The first two sends hung on that prompt (-1712). BlueBubbles' main
  AppleScript can't look up chats by ID on 15.8.1 (-1728), so sends go
  through its fallback script; 1:1 chats work, group sends are untested.
  The Focus-status lookup returns 500 (Private API), which is harmless.
- Post-sign-in controlled restarts (16:18 and 16:28, VNC clients 0, no
  terminal attached): graceful stop in 8–9 s, all services back about 54 s
  after start, identity fingerprint unchanged. The watchdog recovered
  BlueBubbles 47 s after a `kill -9`.
- After the restart, with the MacBook (`liminal`) offline on the tailnet:
  `vm-after-restart-b08392` from the iPhone arrived (message 7833) and was
  returned by `sync_messages` from a cursor taken before both restarts, by
  `search_messages`, and by `get_conversation`.

- archon host reboot 2026-10-20 02:50: TPM unlock, then the VM autostarted
  with no owner action. Identity unchanged; Messages and BlueBubbles started
  by the watchdog; BlueBubbles ping and an MCP search over tailnet HTTPS both OK.

Configured but not yet observed: the Windows
client reconnecting after a VM restart (owner confirmation pending), and a
group-chat send.

## Known limitations

- After an archon power loss, the VM only returns if TPM unlock succeeds
  (passphrase fallback needs someone at the keyboard).
- Private API is off; see the client feature limits above.
- BlueBubbles 1.9.9 is unnotarized upstream, and the project is mid-rewrite.
- Apple's macOS licence restricts macOS to Apple-branded hardware; the owner
  chose this deployment knowing that.
- **Never enable QEMU `vnc_key*` trace events** (or any input tracing). On
  2026-10-19 doing so while debugging the console logged the owner's typed
  Apple credentials to the journal. The affected journal file was deleted.
  Diagnose console input with screendumps and `query-vnc` only.
