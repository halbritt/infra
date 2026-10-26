# Changelog — peecee

## 2026-10-26 — install internal GPU-unlock EFI entry

Created a dedicated 1 GiB FAT32 ESP on the system SSD by native C: shrink,
preserving Windows EFI and recovery partitions. Installed the Z690-I headless
package and appended its firmware entry, retaining Windows first. Twelve host
jobs, package/installer recovery tests and live installation checks pass.
First internal cold boot and default promotion remain pending.
See [installation evidence](config/gpu-unlock/internal-20261026/install-receipt.json).

## 2026-10-26 — verify BF16 gain against locked baseline

After the owner cold-booted Windows directly, reran the identical BF16 benchmark
at the same 450 W limit. Locked results were 85.183 TFLOPS at 8192 square and
72.767 at 4096; unlocked results were 142.870 and 132.952. Gains are 67.72% and
82.71%, with numerical checks passing in both states. The card remains locked
after this baseline boot. See [comparison](config/gpu-unlock/results/boot2-locked-20261026/comparison.json).

## 2026-10-26 — first successful GPU unlock and BF16 benchmark

Verified successful USB unlock, clean reset/resource cleanup and Windows handoff.
NVIDIA driver 610.88 and both display devices are healthy. Dense BF16 GEMM with
FP32 accumulation/output measured 142.870 TFLOPS at 8192 square and 132.952 TFLOPS
at 4096 square, with numerical checks passing. Power limit remained 450 W;
8192 measured 448.39 W mean and 67 °C maximum. No locked baseline exists yet.
See [results](config/gpu-unlock/results/boot1-20261026/summary.json).

## 2026-10-26 — stage GPU unlock USB package

Peecee became reachable on the owner's retry. Reverified BIOS/GPU/ESP/USB identity
and Secure Boot, then staged the tested Z690-I/3090 Ti package on E:. Verified
all copied hashes and the backup of the read-only probe. No reboot or hardware
unlock was performed; the first cold USB boot remains pending.
See [the staging receipt](config/gpu-unlock/port-20261026/staging-result.json).

## 2026-10-26 — build experimental Z690-I GPU unlock port

Added the exact Z690-I/3090 Ti profile in the private owner source repository,
reusing the existing aggregate-console release path. Eleven host jobs and twelve
Python tests pass; wrapper and child pass PE verification. Prepared a verified
USB package on proximal. Peecee's SSH timed out over Tailscale and LAN, so the
package is not on E: and no hardware unlock was attempted.
See [GPU unlock provenance](config/gpu-unlock/README.md).

## 2026-10-26 — confirmed4601 probe retains console compatibility blocker

Archived and hash-verified DIAG01 after an owner-requested reboot with4601
already verified installed. Probe succeeds and GPU cold-state checks pass, but
the generic profile generator still rejects the ASUS aggregate console. Firmware
update did not resolve this mismatch. Restored the stopped GPU exporter again;
its recurring boot-start issue remains undiagnosed.
Details: [GPU probe](config/gpu-unlock/README.md).

## 2026-10-26 — BIOS 4601 confirmed; restore GPU monitoring

Verified BIOS4601, healthy Intel/NVIDIA display devices, Secure Boot off and
unchanged USB probe/Windows ESP. Started the stopped GPU exporter and verified
metrics; Ollama and Kev tasks were already running. Recorded Aquacomputer
cooling and the CPU_FAN monitoring exception needed after reset. A new probe
capture is archived; its pre/post-flash chronology needs owner confirmation.
See [BIOS](config/bios/README.md) and [GPU probe](config/gpu-unlock/README.md).

## 2026-10-26 — prepare authorized BIOS 4601 update

Downloaded the official ASUS package, matched its published checksum, and
staged the verified CAP on the existing Lexar E: drive. BitLocker is off.
Archived pre-update GPU captures separately. The owner must start ASUS EZ Flash
in firmware; completion and version verification remain pending.
Provenance: [BIOS](config/bios/README.md).

## 2026-10-26 — iGPU visible; GPU probe identifies aggregate console

The post-BIOS-change capture succeeds and now sees Intel 8086:4680. Generic
profile generation instead refuses the ASUS aggregate console arrangement;
NVIDIA GOP still matches the proven hash. Archived and hash-verified 53 capture
files. The existing upstream B660M aggregate path is a potential adaptation
starting point, not a compatible ready-made peecee profile. See
[GPU probe](config/gpu-unlock/README.md).

## 2026-10-26 — first GPU probe capture succeeds; iGPU absent

Archived and hash-verified the first complete cold-boot capture. NVIDIA GOP
0x60010 matches the proven code hash; the local-profile analyzer refuses because
UEFI exposes no integrated display controller. Further compatible captures need
iGPU enabled in BIOS. Details: [GPU probe](config/gpu-unlock/README.md).

## 2026-10-26 — stage read-only GPU UEFI probe on owner USB

Prepared the Lexar FAT32 USB at E: with a diagnostic-only executable for the
RTX 3090 Ti investigation. Verified the staged hash and preserved all 49
accessible existing files. Upstream generic-probe checks and capture-parser
regressions passed. No GPU unlock, reboot, or firmware changes performed;
two physical cold-boot captures remain pending. Build and installed artifact
provenance: [GPU probe](config/gpu-unlock/README.md).

## 2026-10-26 — install ast-grep in peecee-wsl

Installed ast-grep `0.51.0` at `/usr/local/bin/ast-grep` in Linux WSL. Seven
structural-search checks passed. Preserved the existing `sg` command.
Provenance and installation: [shared/ast-grep](../../shared/ast-grep/README.md).

## 2026-10-25 — install Probe in peecee-wsl

Installed the verified upstream `v0.6.0-rc343` native binary at
`/usr/local/bin/probe` in the Linux WSL environment. Ten fixture checks passed
for Probe and ugrep. Release identity, digest, installation and rollback:
[shared/probe](../../shared/probe/README.md).

## 2026-10-25 — install ugrep in peecee-wsl

Owner-requested CLI installation over `ssh peecee-wsl`: `sudo apt-get install
--no-install-recommends ugrep` installed Ubuntu's `7.5.0+dfsg-1` package. Verified
`/usr/bin/ugrep`, its version, and an exact-line stdin search with line numbers.
Added the package to the canonical WSL toolchain provisioning list.

## 2026-10-24 — ollama off the GPU fleet: qwen3.6:27b evicting qwen3-vl:8b (owner: "ollama is down on peecee")

- **Symptom:** the `OllamaServer` task was running and the API answered (0.30.7, up since
  boot on 10-16). gpu-fleet's heartbeat, however, showed peecee slot 0 as `not loadable:
  marker owns card (free=3.6 GiB < 21000)`, with `qwen3.6:27b` resident (16 GB, ctx
  4096, keep-alive forever).
- **Cause:** memory-price-tracker's sentiment step (`OLLAMA_MODEL=qwen3.6:27b`) loaded
  the 27B every ingest run (10-07, 10-10, 10-13, 10-16 and 10-21, about 19:00). With
  `OLLAMA_KEEP_ALIVE=-1` it stayed resident and pushed out the fleet's `qwen3-vl:8b`.
  This is the same drift fixed by hand on 2026-09-23. Its requests also ran past the
  tracker's 12 s timeout, so it got nothing back.
- **Fix:** a request reloaded `qwen3-vl:8b` (32768 ctx, forever, 7.4 GiB). The heartbeat
  went to `resident` at 08:02:04 PDT, and fleet `live` went from 2 to 3. The tracker now
  asks for `qwen3-vl:8b` (memory-price-tracker drop-in and docs; ingest restarted).
- **Follow-up (owner):** the tracker no longer uses peecee at all. Sentiment now runs on
  proximal's resident llama.cpp Qwen3.8-27B (memory-price-tracker `LLAMA_CPP_URL`, with
  no Ollama host set), so nothing requests a model on peecee.

## 2026-10-22 — peecee-wsl: kicad-route worker lanes

Owner request (via the coordinator): run kicad-route lanes here as well as agent-ee lanes. Details: [shared/kicad-route](../../shared/kicad-route/README.md).

- `~/git/kicad-route`: public clone of halbritt/kicad-route with `receive.denyCurrentBranch updateInstead`. proximal's checkout has the remote `peecee-wsl`.
- apt `python3-numpy python3-scipy` (numpy 2.3.5, scipy 1.16.3). The user site has proximal's pins: pytest 9.1.0, shapely 2.2.0 and jsonschema 4.26.0.
- `kicad-route update` built router generation `210bdbb4…` (`owned-3c91fe5c0120`) with the existing rustc 1.99.1. There is no Java, so the Freerouting backend is unavailable.
- Check at kicad-route 409d06ab: 93 focused pcbnew/router tests passed. pytest then segfaulted at teardown (exit 139), a known Python 3.14 + pcbnew issue.

## 2026-10-21 — peecee-wsl: agent-ee tests run in the CI image (`ae-ci-exec`); claude 2.1.307

Owner-requested. Natively (Python 3.14.4, poppler 26.01, ngspice 45.2), main fails
7 modules from toolchain identity drift: test_schematic_render, test_dc_path,
test_netlist_parity, test_empirical_facts, test_datasheet_capabilities,
test_passive_corners and test_stage_receipts. All pass in the image.

- Installed `~/.local/bin/ae-ci-exec` (sha256
  `a824b664ec9907fbb5abef7ee17e3d4a93b6cac6d96488b6a2c9c5c300a877b5`, identical on
  proximal, peecee-wsl and archon). Canonical source and documentation:
  [`shared/agent-ee/`](../../shared/agent-ee/README.md). It runs agent-ee
  commands in the pinned CI image built from the worktree's own Dockerfile, with
  the release gate's sandbox options, fome-mc and J1 inputs, and kicad-route pin.
  agent-ee tests on every host should go through it rather than through the
  distro toolchain.
- Image `agent-ee:exec-2657c88d90d4f0a9` (agent-ee main de12cca).
  State lives in `~/.cache/ae-ci-exec/`: the fome-mc clone at 1289f314, the J1
  drawing, a caller-owned kicad-route copy, build logs and parity results.
- Parity on a clean `git archive de12cca`, run with `strict_suite.py --jobs 3`:
  all 10 modules pass with 295 tests and 0 skips, the same result as on the
  other two hosts. The modules are the 7 peecee-wsl drift modules, test_fab_package,
  test_fab_stage and test_electrical_locality. Doctor output is byte-identical
  across hosts.
- Image build: 2 s, because every toolchain layer was in BuildKit's cache from the
  release gate's `agent-ee:ci-*` builds. The wrapper's context uses git-archive
  modes, so the cache keys match. The gate's containers and `agent-ee:ci-*` images were
  not touched. The parity run waited until the gate finished (load 466 → 14).
  Batch A 102 s, batch B 92 s. WSL has no AppArmor, so the profile is `unconfined`.
- The fome-mc input is a separate clone owned by halbritt. The gate's
  `~/agent-ee-gate/ci-inputs` store is chowned to 10001 for its in-image user.
- Host tools: claude 2.1.305 → 2.1.307 (`npm i -g @anthropic-ai/claude-code@2.1.307`;
  no claude process was running). codex 0.163.0, uv 0.13.4 (standalone) and
  git-wt/git-land (wrappers of `~/git/cairn/scripts/git_trunk_tools.py`) are unchanged.

## 2026-10-21 — peecee-wsl: KiCad stock 3D model library (kicad-packages3d 10.0.7)

Owner-requested, because agent-ee workers, reviewers and the release gate run
here and placement-candidate renders should show component bodies.

- Installed `kicad-packages3d 10.0.7~ubuntu26.04.1` (upstream tag `10.0.7`). It
  comes from the same `kicad-10.0-releases` PPA (resolute) as the installed
  `kicad 10.0.7~ubuntu26.04.1`. It was the only package changed, with no
  dependencies.
- How: the main PPA host was returning 503s, so the `.deb` was downloaded with
  resume from `snapshot.ppa.launchpadcontent.net` (same pool path). Its SHA-256
  `4c5eaac20b86445b4f9926cccb83f163d5037e37ec5277fccea10b1352cf154e` matches the
  apt index. It was then installed with `sudo dpkg -i` and is dpkg-tracked. The
  downloaded file was deleted.
- Path `/usr/share/kicad/3dmodels`: 105 dirs, 7252 `.step`, 3.2 GiB
  (3,368,023,638 bytes, the same as proximal's). This is the path that kicad-cli
  resolves `${KICAD10_3DMODEL_DIR}` to when `KICAD_CONFIG_HOME` is empty, as in
  agent-ee's sandbox. A user path would not reach that sandbox.
- Verified on a copy of the pod candidate: kicad-cli opened all 27 unique stock
  files (0 ENOENT) that the 281 `${KICAD10_3DMODEL_DIR}` references cite. The
  top and bottom renders show bodies (J3 microSD on the bottom). See the
  [proximal entry](../proximal/CHANGELOG.md) for why agent-ee's `model_coverage`
  inventory still reports `unresolved`.

## 2026-10-21 — Claude and Codex logins on peecee-wsl are mirrors of proximal

`~/.claude*/.credentials.json` and `~/.codex*/auth.json` here are now written by
proximal's `claude-oauth-refresh` and `codex-auth-mirror` timers every 15
minutes. They hold access tokens only (Claude refresh fields removed, Codex
`refresh_token` blanked), so this host can never rotate, or invalidate, the
owner's logins. Do not run `claude auth login` or `codex login` here: the next
push overwrites it. `~/.gemini/oauth_creds.json` remains a plain copy, which is
safe because Google refresh tokens do not rotate. See
[proximal codex-auth-mirror](../proximal/config/codex-auth-mirror/README.md).

## 2026-10-21 — council ldconfig portability bug filed as COUNCIL-1

The two council `npm test` failures on the WSL build node (Ubuntu 26.04 ships the
real ELF at `/sbin/ldconfig`; council's `src/v3/runtime-resolver.ts` hardcodes
`/sbin/ldconfig.real`, an Ubuntu 22.04/24.04 wrapper quirk) are tracked as Plane
work item **COUNCIL-1** on the work instance. A Council project (identifier
`COUNCIL`) was created in Plane for it, following the one-project-per-repo
convention. Suggested fix recorded there: prefer `.real` when present, else
`/sbin/ldconfig`, ELF-verified via the existing readelf probe. No change to council.

## 2026-10-20 — WSL build node: toolchains + local postgres, agent build/test proven

`config/wsl/provision-toolchains.sh`: gcc/cmake/ninja, Python 3.14 + uv, Node 24,
Go 1.27, Rust stable, docker + compose v2, gh, rg/jq/tmux/shellcheck, bubblewrap/
slirp4netns, claude/codex/opencode CLIs, git-wt/git-land (cairn clone). PATH via
`/etc/environment` for non-interactive SSH. `gh` authenticated with proximal's
token (`gh auth login --with-token`). `config/wsl/provision-postgres.sh`: PostgreSQL
18 + pgvector on the peer-auth socket, role `halbritt`, dbs engram/engram_test/hippo.
Proven over `ssh peecee-wsl`: cairn `go test ./...` all ok; council `npm test`
890 pass / 2 fail (council hardcodes `/sbin/ldconfig.real`, absent on 26.04 — repo
bug); engram full suite 2528 pass / 5 fail → all 5 pass after local postgres +
migrate (1 was a load flake); cargo, docker hello-world, git-wt worktree ok.

## 2026-10-20 — WSL2 Ubuntu as a Linux build node (sshd on :2222)

Stood up the existing (idle) WSL2 Ubuntu 26.04.1 distro as an SSH-reachable
Linux build host to offload builds from proximal. Inside the distro:
`openssh-server` + `build-essential`, sshd on port 2222 key-only, proximal's
key authorized for `halbritt`, passwordless sudo, hostname `peecee-wsl`.
Windows side: `C:\Users\halbr\.wslconfig` (48 GB / 24 CPUs / mirrored
networking / no idle timeout), Scheduled Task `WslKeepalive` (At startup, as
`halbr`) holding the distro open without a login session, Windows + Hyper-V
firewall rules for TCP 2222. Verified `ssh peecee-wsl` from proximal over
tailnet and LAN; distro survives the launching session ending. Full-reboot
survival not yet tested. Provenance and operate notes in `config/wsl/README.md`.
Same day: `apt full-upgrade` in the distro (77 packages, no reboot required,
cloud-init held back by phasing), WSL runtime already current at 3.0.3.0,
kernel 6.18.54.1-microsoft-standard-WSL2. Windows Update itself left alone
(pending: ASUS firmware, Intel net + Bluetooth drivers — all need a reboot).

## 2026-10-13 — Audio driver recheck

Read-only checks found Realtek USB Audio `6.3.9600.2342` (`oem94.inf`) still
installed and best ranked, with device/endpoint reporting no PnP problems and
both audio services running. The newer Microsoft generic driver remains
outranked. No driver replacement regression found; audible playback and default
output selection remain untested. See `config/audio/README.md`.

## 2026-10-13 — WezTerm LAN backup

Added `Host proximal-local` / `HostName proximal.local` / `User halbritt` to
`C:\Users\halbr\.ssh\config`, and the matching explicit SSH mux domain in
`C:\Users\halbr\.wezterm.lua`. Dated pre-change backups sit beside both files.
Preserved the default proximal connection and local Ctrl-click bindings.
Verified mDNS returned proximal's LAN addresses, the SSH alias reached proximal,
WezTerm parsed the config, and mux panes 0 and 1 were visible through the alias.
Use `wezterm connect proximal-local` while on the home LAN if Tailscale is down.

Machine-level changes for `peecee`, newest first. The exporter README and its Git
history contain the original 2026-06-20 deployment record.

## 2026-09-26 — Stream Deck Home page

Added a 15-key Home page as the first page: HA light toggles, announcements,
Movie/Goodnight, media keys, Grafana, Lock PC and More ›. Added ‹ Home on the
old first page. Profiles backup is in `C:\ProgramData\Infra\streamdeck\`.
See [config/stream-deck/README.md](config/stream-deck/README.md).

## 2026-09-26 — Elgato Stream Deck installed

Installed `Elgato.StreamDeck` 7.6.0.23012 with winget for the owner's Stream
Deck MK.2. It adds two `halbr` Run entries (Stream Deck, Volume Controller)
and no services or tasks. Both were started in the desktop session. The deck
was first on the monitor's Thunderbolt downstream port, which follows archon
(the Thunderbolt host) regardless of USB Selection. After the owner moved it,
peecee enumerated it and the app connected (firmware 1.02.000). See
[config/stream-deck/README.md](config/stream-deck/README.md).

## 2026-09-23 — Zwift uninstalled

Stopped its launcher, ran Zwift 1.1.13's registered quiet uninstaller, and
removed residual files from its program directory. Verified the app and its
startup entry are absent. The previous LG Switch Run value is also absent,
and its recorded executable is missing; its Start app entry remains. See
[config/startup/README.md](config/startup/README.md) for the current inventory.

## 2026-09-23 — Microsoft Teams uninstalled

After the owner clarified that Teams itself should go, removed the installed
`MSTeams` app for all users and its Windows provisioned package. Verified that
the app, its packaged startup task, and Start app entry are absent. The
remaining startup inventory is in [config/startup/README.md](config/startup/README.md).

## 2026-09-23 — LG installer and Teams autostart disabled

After the owner's follow-up, parked the LG Monitor App Installer shortcut
outside Startup, removed its installer manager Run value, and disabled the
installer cleanup logon task. LG Switch and the monitor driver remain in place.
Disabled the packaged Teams startup task without uninstalling Teams. Updated
the dated inventory in [config/startup/README.md](config/startup/README.md).

## 2026-09-23 — Ollama startup shortcut removed; Evernote autostart disabled

Moved the parked `Ollama.lnk.disabled` file out of the user's Startup folder,
where Windows still treated it as a startup command. Updated the Ollama
lifecycle scripts to park and restore the shortcut outside that folder.
Disabled Evernote's packaged `EvernoteStartup` task for user `halbr`. Verified
the Ollama server task and API still run; no other startup entry was changed.
The dated inventory is in [config/startup/README.md](config/startup/README.md).

## 2026-09-23 — ASUS onboard audio driver repaired

The motherboard's Realtek USB audio device (`VID_0B05&PID_1A20`) was using
Windows' generic `usbaudio2.inf` despite a Realtek extension being present.
Installed the signed base driver `6.3.9600.2342` from the newest ASUS audio
package listed for the ROG Strix Z690-I Gaming WiFi. Only the matching driver
files were staged and installed; the package's optional apps and on-logon task
were not run. Windows reported a reboot requirement, so peecee was restarted.
Post-reboot verification found the Realtek driver bound and best ranked, its
device started without a PnP problem, and a live Realtek SPDIF endpoint.
See [config/audio/README.md](config/audio/README.md) for package identity and
reinstallation instructions.

## 2026-09-23 — Kev classifier service; ollama resident model back to qwen3-vl:8b

Owner-directed (option "2" of the VRAM tradeoff in
`showerthoughts/jev/research/tiny-model-benchmark-2026-09-22.md`).

- Unloaded the drifted resident `qwen3.6:27b` (16 GB, ctx 4096) and loaded
  `qwen3-vl:8b` at `num_ctx` 32768 with keep-alive forever, converging the box on
  gpu-fleet migration 013's advertised slot-0 state. No fleet migration needed.
- Installed Kev (`jaredpalmer/kev` @ `557598f`, torch 2.8.0+cu128, triton-windows,
  flash-linear-attention 0.5.2) under `C:\Users\halbr\kev` via the one-shot task
  `KevInstall`, and registered `KevServer` (user, S4U, AtStartup, restart x3) serving
  `kev-4b` bf16 with the adapter unmerged on `0.0.0.0:8008`. New subsystem
  `config/kev/` holds the installer, both task wrappers, the bind shim and a README
  with the serving contract and five Windows gotchas (SSH kills the process tree;
  PS 5.1 Stop preference vs. redirected stderr; cmd quote stripping; DOMAIN\user
  SID mapping; uv venv refuses overwrite).
- Verified from proximal: `/v1/models` reports cuda/bfloat16; the 64-row benchmark
  matches the proximal run (risk 0.83, irreversible 0.88, network 0.92) at 439 ms p50.
- Not changed: ollama task, marker, exporter, firewall. Card is now full (~0.7 GB free
  with the desktop open); marker jobs must stop `KevServer` first.

## 2026-08-11

### GPU exporter made independent of Tailscale service restarts

A Tailscale 1.102.2 MSI update on 2026-08-08 cleanly stopped the
`nvidia_gpu_exporter` service because it declared `depend=Tailscale`. Clean SCM
stops do not activate WinSW failure recovery, and the updater did not restart
the dependent service, leaving Prometheus blind until the exporter was restored
on 2026-08-10 local time.

Removed the hard service dependency and made delayed automatic startup explicit.
The existing 5-second restart-on-failure action, tailnet-only listener, and
tailnet-scoped firewall remain unchanged. This preserves boot-race recovery while
allowing Tailscale upgrades and restarts without stopping the exporter.

Reinstalled the live WinSW service definition and verified delayed automatic
startup, no Tailscale dependency, and the 5-second recovery action. A controlled
exporter child-process termination restarted it with a new PID; its metrics and
the Prometheus `gpu/peecee` target returned healthy.

## 2026-08-05

### Standalone peecee repository imported with history

Imported all 15 commits from `github.com/halbritt/peecee` `main` at
`8bc7435470026341bf547de3da5bd0f654db464b` using an unsquashed subtree merge.
Normalized its Ollama, Marker, and WHEA content under `config/` without changing
the Windows machine. Reconciled its root instructions and operating notes with
the existing fleet host record.

Read-only SSH verification confirmed the Windows host, GPU, Ollama task,
exporter service, and Marker installation were reachable. It also showed that
the currently loaded model differs from the 2026-07-21 repository observation;
the current state is recorded in `notes.md` without treating it as new desired
state.

Updated proximal's WHEA cron entry and the Marker skill's maintenance reference
to the fleet paths after the normalization.

### Existing Windows GPU exporter assigned to its owning host

Moved the already-versioned `nvidia_gpu_exporter` WinSW configuration from the
`proximal` observability subtree to `hosts/peecee/config/nvidia-gpu-exporter/`.
Updated `proximal`'s consumer references. No Windows service, firewall rule,
address, executable, or credential changed, and no live Windows action was
performed.
