# GPU unlock investigation — peecee

Current status: the USB unlock succeeded. Matched BF16 runs at the same 450 W
limit show **1.68× throughput at 8192 square** and **1.83× at 4096 square**.
Peecee is currently in the locked baseline boot; another cold USB boot reapplies
the unlock. See the final dated entry below.

## Read-only USB probe staged 2026-10-26

The owner supplied the USB at E: and authorized preparing the diagnostic probe
for the RTX 3090 Ti. No unlock was staged or attempted; no reboot was initiated.
The first owner-operated cold boot completed successfully; see the findings below.
Two captures with a compatible display configuration are still required.

Live checks identified E: as a Lexar USB Flash Drive, disk 2 partition 1,
MBR/FAT32, label Lexar, 61,850,812,416 volume bytes. It is neither the system nor
boot disk. Secure Boot was off. Windows system ESP is disk 0 partition 1,
GUID `c4b263fb-2821-4034-a2b0-3f3a4dfacc15`.

### Installed files and verification

- Probe: `E:\EFI\BOOT\BOOTX64.EFI`, 21,504 bytes.
- SHA-256: `45f6de8386c8f0b04896a9533906aaa72631bb397e0ee9ea2513bb73c9130adc`.
- Supporting manifest, PE verification, instructions: `E:\RTX3090-UNLOCK\`.
- Windows staging copy and original USB file hashes:
  `C:\Users\halbr\gpu-unlock-probe-20261026\`.
- All 49 pre-existing accessible files were hash-verified unchanged; Windows
  System Volume Information was excluded from the inventory. No previous
  `EFI\BOOT\BOOTX64.EFI` was present. No formatting, partition edits, boot-order
  changes, or firmware setting changes were performed.

The binary includes only the generic diagnostic probe and Windows handoff.
The build excludes unlock, GPU writes, driver detachment, DMA, and firmware
variable writes. It writes diagnostic files to the USB.

### Build provenance

Source: [Windows-GPU-UNLOCK](https://github.com/impacifist/Windows-GPU-UNLOCK),
revision `5c98f11eaafdcb7a2a06fb14fcdcde7297eb409e`. Built on proximal with Ubuntu
Clang/LLD 20.1.2, cross-target `x86_64-pc-windows-msvc`, using the same sources,
compiler flags, and linker flags as `research/profile/build-probe.ps1`.
The Windows ESP GUID was checked over SSH before generating the local header
and again before staging. No write-capable firmware assets were required.

Toolchain packages were downloaded from configured Ubuntu repositories and
extracted under `~/.cache/gpu-unlock-probe/toolchain/`; no system packages were
installed. Source export and artifacts are under
`~/.cache/gpu-unlock-probe/source-5c98f11/`. The original checkout remains clean.
[Build manifest](probe-20261026/manifest.json) records exact commands and source
hashes; [PE verification](probe-20261026/pe-verification.json) confirms AMD64
EFI application, correct entry, relocations, NX/ASLR, and no imports.

Upstream generic-probe tests passed 81 RAM-only mock checks. Five capture-parser
regressions passed. These are host tests, not evidence of a successful UEFI boot
on peecee.

### Next physical step

Save work, fully shut down Windows (`shutdown /s /t 0`), power on, and select
the UEFI Lexar USB in the firmware boot menu. The probe should capture data and
start Windows. Repeat from a second full shutdown. Leave the USB connected.
Retrieve `E:\RTX3090-UNLOCK\DIAG??.TXT`, `PROM.BIN`, and `IMG??.BIN` afterward;
require complete captures and inspect GOP/topology before considering unlock.
If the probe fails to hand off, power off and boot Windows Boot Manager normally.

The unresolved questions are the exact NVIDIA GOP fingerprint and whether UEFI
exposes the integrated non-NVIDIA display controller required by the local-profile
path. This preparation does not establish compatibility.

To remove the probe, delete the newly added EFI executable and diagnostic folder
from this USB after preserving any captures. The original Lexar files remain.

## First cold-boot capture — 2026-10-26

`DIAG00.TXT` contains `capture-complete=1` and diagnostic result zero. Retrieved
and SHA-256 verified all 55 files in the USB diagnostic directory, including
50 loaded driver images and the 1 MiB PROM. Full evidence is outside Git at
`~/.local/share/infra/evidence/peecee-gpu-probe-20261026/boot1/`; its
`capture-sha256.json` records the remote file hashes. Preserve this capture set
separately from any later BIOS configuration. The 52 capture files were also
moved into `E:\RTX3090-UNLOCK\capture-before-igpu-20261026\` after hash
verification, leaving the probe ready to produce fresh captures.

The NVIDIA GOP is **0x60010**, with `.text` SHA-256
`615b37a708b1894e18d7fa60cfcdacaa4d8b598863a10b8103d231a595847b2b`
(IMG49.BIN, 134451 code bytes), exactly matching the proven X870/3090 Ti entry.
The VBIOS version difference therefore did not imply an unsupported GOP.
PROM SHA-256 is
`586baad14e09c28019499c7270aa608b878f8a87c457de13490fa7a855cfb30a`.
The GPU meets the generator's cold-state register checks.

Running the upstream per-capture analyzer refuses this setup because UEFI has
zero non-NVIDIA display controllers. Integrated graphics must be enabled for
the current reviewed local-profile path. The log also reports ConOut absent;
console topology remains an additional check after enabling the iGPU, so this
is not a promise that the BIOS change alone makes the machine eligible.

Next owner action: enable iGPU Multi-Monitor under Advanced > System Agent (SA)
Configuration > Graphics Configuration, save and return to Windows, then take
fresh full-shutdown USB captures. Keep primary display/monitor routing on the
RTX initially. [ASUS instructions](https://www.asus.com/global/support/faq/1045574/).
No BIOS setting or unlock was applied remotely.

## Second capture, after enabling integrated graphics — 2026-10-26

The owner enabled iGPU Multi-Monitor and completed another probe boot. Captured
`DIAG00.TXT` SHA-256 is
`455b4439a1af0f1e60b9568c43e5ed64d9e47da322d715fa7f68a96cae95118f`.
All 53 capture files were copied and verified against remote SHA-256 at
`~/.local/share/infra/evidence/peecee-gpu-probe-20261026/boot2-igpu/`;
`analysis.json` records the admission result and `fingerprint.json` is the
upstream offline fingerprint report. Capture-complete is 1 and diagnostic
result is zero. The current capture remains at the USB diagnostic root.

UEFI now enumerates Intel `8086:4680` alongside NVIDIA `10de:2203`, resolving
the absent-iGPU condition. Windows shows the Intel device as Microsoft Basic
Display Adapter with Error status; the NVIDIA device is OK. No Windows driver
change was made, and Windows driver status does not remove the UEFI observation.

The generic local-profile analyzer now refuses because ConOut is absent, rather
than exactly the RTX GOP path. Separate read-only ownership inspection finds:

- No SimpleTextOut BY_DRIVER opener on the physical RTX GOP.
- The physical GOP is owned by AMI combo driver
  `55987e62-1df6-41d1-9062-334fcac3e54d`, version `0x11`.
- EDID driver matches the known AMI identity and runtime code class; code SHA-256
  `a015d52f55fa6441414458e2b699ba2edcb53f03b001ac6367e45bcd908c418e`.
- NVIDIA GOP remains `0x60010` with the same proven code hash (now IMG50.BIN).
- PROM hash is unchanged.

This is an aggregate console arrangement. Upstream `docs/COMPATIBILITY.en.md`
documents an existing aggregate-console release path for ASUS B660M/RTX3070Ti,
but that profile is not peecee's hardware profile. Do not apply it directly or
bypass local-profile admission. The next software task is to evaluate adapting
that existing path to Z690-I/3090Ti with the captured identities and ownership
graph. It is not established that another identical boot or an Intel Windows
driver install would resolve this firmware-topology refusal. No unlock or
further BIOS changes were performed.

### BIOS age checked at owner's suggestion

Live SMBIOS still reports 3501, build date 2024-04-18. ASUS lists 3501 release
2024-04-24 and current 4601 release 2026-09-29. The later release notes cover
security, Intel ME, CPU microcode/defaults, and stability, with no stated fix
for the ConOut/aggregate-console arrangement observed here. Firmware changes
could change this behavior, but an update is not a demonstrated fix. Updating
before custom-profile work would require new captures afterward. BIOS 4601
also updates ME to 16.1.40.2765, which ASUS says does not revert with a BIOS
rollback. No update has been downloaded, staged, or installed by this task.
[ASUS BIOS releases](https://www.asus.com/us/supportonly/rog%20strix%20z690-i%20gaming%20wifi/helpdesk_bios/)
checked 2026-10-26.

## Capture retrieved after return to Windows on 4601 — chronology pending

Live Windows verifies BIOS4601, both GPUs OK and Secure Boot off. USB root
contained a new DIAG00.TXT, SHA-256
`02469daaaadbb739eab9310af47d0e178383ff7c965a6e603ca37f78e8507e0c`.
Retrieved53 capture files and verified their hashes under
`~/.local/share/infra/evidence/peecee-gpu-probe-20261026/boot3-bios4601/`.
Despite that directory's intended label, the owner's confirmation that the USB
was booted after flashing is still pending; do not treat the name as proof of
firmware provenance. The capture is complete, diagnostic result0, and fails
profile admission with the same missing-ConOut/aggregate-console refusal.
Its reported console-driver fingerprints equal the previous3501capture; NVIDIA
and EDID code hashes also remain the same. Need boot chronology confirmation
or a fresh known4601coldboot before concluding the update did not change this.

## Confirmed BIOS4601 reboot capture — 2026-10-26

After verifying4601 live, the owner requested a reboot; issued
`shutdown.exe /r /t 0`. The owner returned from the USB probe to Windows.
New DIAG01.TXT SHA-256 is
`3eb513670d446b5b33c01c7f2eede9a3c048ab27f54880659fd2927e88e06658`.
Retrieved54 root capture files and verified remote SHA-256, archived at
`~/.local/share/infra/evidence/peecee-gpu-probe-20261026/boot4-confirmed4601/`.
The authoritative new log is DIAG01; DIAG00 was already present. Analysis and
upstream fingerprint reports are beside the captures.

Complete=1, diagnostic result0. Although this was an ordinary reboot rather
than a full shutdown, the observed GPU registers meet the current generator's
cold-state checks: PLMffffff8f, GFW8b8f/3ff/10, WPR2zero, SS000452002, SS1six.
This is evidence for this reboot only, not a general guarantee for warm resets.
The generator proceeds to and refuses the same ConOut/aggregate-console check.
Console-driver fingerprints, NVIDIA GOP code hash and EDID code hash match3501.
The BIOS update therefore did not resolve the observed compatibility problem.
There is no need for another identical capture merely to rediscover this refusal.

Next implementation work would adapt and validate the existing upstream
aggregate-console release route for this machine's GA102/3090Ti profile; the
ready-made B660M/3070Ti profile is not suitable to deploy directly. No write-capable
unlock was built or staged in this investigation.

The GPU exporter was again stopped after reboot despite StartModeAuto. Started
it and verified its tailnet RTX3090Ti metric. Recurring startup failure remains
undiagnosed; service configuration was not changed.

## Experimental aggregate-console port built — 2026-10-26

The owner requested implementation after the confirmed BIOS 4601 capture.
Created the private owner repository
[`halbritt/Windows-GPU-UNLOCK`](https://github.com/halbritt/Windows-GPU-UNLOCK)
with upstream history preserved. The upstream remote remains `upstream`; the
owner repository is `origin`. The implementation is committed and pushed on
`main` at `4ecda4a` (upstream base `5c98f11`). Local source:
`~/git/gpu-unlock-winport/Windows-GPU-UNLOCK/`.

The new `z690i-3090ti` profile selects the existing aggregate-console release
path with the captured GPU identity, BAR0, PROM and display path. Captured AMI
binding fingerprints and the EDID/NVIDIA code hashes match that path. No runtime
release algorithm or generic local-profile admission check was changed.
The Windows build script restricts this profile's write build to headless USB.

All 11 host jobs pass against the confirmed DIAG01 capture and verified 610.43.03
assets: 244 PCI preflight checks, 65 graph/driver checks, 197 cold prechecks,
39 handoff cases, port/write locks, 29 bus-master scenarios, transaction fault
injection and the automatic USB child. The old B660M profile rejects the card,
as expected. The existing 12 Python parsing tests pass. These execute production
code with RAM-only firmware mocks; they do not establish hardware unlock success.

Clang/LLD 20.1.2 built the wrapper and child with the previously verified Windows
ESP GUID `c4b263fb-2821-4034-a2b0-3f3a4dfacc15`. Both pass PE verification:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| USB wrapper | 39424 | `e976d28cef44dca9841c66f1ea18504f4955a9d7248083d911fe878b6c52e7dd` |
| Unlock child | 67584 | `29729569c613e7fed16303a6b7faa3ccd997473a8edbccc59e704855263e0a64` |

The package archive on proximal is
`~/.local/share/infra/evidence/peecee-gpu-unlock-port-20261026/peecee-z690i-usb.zip`.
It contains the two EFIs, all five verified assets, the existing Windows staging
script, test evidence and a provenance manifest. Archive entries were read back
and checked against their hashes. Firmware and binaries remain outside Git.
[Package provenance](port-20261026/package-provenance.json) and
[host results](port-20261026/test-results.json) are retained here.

SSH timed out on both `100.113.63.58:22` and `192.168.1.118:22`; no remote files,
boot entries or firmware settings were changed during this implementation.
E: therefore still has the read-only probe. Do not tell the owner to boot the
unlock yet. Once Windows is reachable, recheck the machine, system ESP and USB,
copy/extract the archive, and run its `research/headless/stage-usb.ps1` with
`-Drive E -Assets <extracted-package>\assets`. This preserves the old probe
under `RTX3090-UNLOCK\backup\` and verifies copied hashes.

The first test uses the one-time firmware USB selection. It automatically
attempts the unlock after a five-second Esc window and may blank the display.
The existing failure path stops without retry or Windows handoff after release
or unlock errors. Recovery is a full power-off and Windows Boot Manager; collect
the logs before another attempt. A hardware boot, NVIDIA driver recovery and a
controlled locked/unlocked BF16 comparison remain pending.

The implementation decision and remaining evidence limits are in
[the decision receipt](port-20261026/decision-receipt.json). Pincite packet and
unmet, nonmaterial obligations are recorded in
[doctrine provenance](port-20261026/doctrine-provenance.json).

## USB unlock package staged — 2026-10-26 20:50 UTC

The owner requested another connection attempt. Peecee answered SSH. Live checks
again found BIOS 4601, healthy Intel UHD 770 and RTX 3090 Ti devices, NVIDIA driver
610.88, the expected system ESP, Secure Boot off, and the Lexar FAT32 USB at E:
(disk 2, partition 1). The existing USB boot file still matched the probe hash.

Copied the package to `C:\Users\halbr\Downloads\peecee-z690i-usb.zip`, verified
the archive hash, and extracted it to `C:\gpu-unlock-4ecda4a`. Verified every
manifest entry before running the packaged `research/headless/stage-usb.ps1`.
The wrapper, child and five firmware assets are now installed at the USB paths
listed in [the staging receipt](port-20261026/staging-result.json); all copied
hashes match the package. The old probe is preserved and hash-verified at
`E:\RTX3090-UNLOCK\backup\BOOTX64-45f6de8386c8.EFI`.

This resolves the earlier connectivity/staging blocker. No reboot or hardware
unlock was performed. Next is a full shutdown and one-time boot of the Lexar USB,
followed by collecting the handoff/transaction logs and checking Windows driver
health. The package attempts the unlock automatically after its Esc window;
the display may stop updating during driver release.

## First successful unlock boot and BF16 measurement — 2026-10-26

The owner returned to Windows after the cold USB boot. Retrieved and verified
the hashes of `HLS000000.TXT` and `AUTO000000/REPORT.TXT`. The wrapper records
successful preparation, unlock return, released-state verification and Windows
handoff. The transaction ends with:

```text
post-FLR SEC2 reset released, GSP halted, BME=0 pending=0 WPR2=1ffffe00:00000000 SS0=88888888 SS1=00000008
transaction result=0 containment=0 started=1 quiesced=1 fault=0 retained=0 maps=0 FLR=1
FINAL status=0 stage=transaction attempted=1 driver_release=0 clean=1
```

`driver_release=0` is the child report: the wrapper performed the driver release.
Both Windows display devices report OK and NVIDIA driver 610.88 responds normally.
This is one successful hardware boot of source `4ecda4a` and the exact EFI hashes
recorded above. It does not establish repeated-boot or long-term stability.
Raw logs remain under
`~/.local/share/infra/evidence/peecee-gpu-unlock-port-20261026/boot1/`.

Ran [benchmark-bf16.py](benchmark-bf16.py) with the installed Marker environment's
PyTorch 2.12.1+cu130 / CUDA 13.0. The script measures dense BF16 inputs with FP32
accumulation/output, disables reduced-precision reduction, warms up for 200 GEMMs,
then times five batches of 500 GEMMs using CUDA events. It checks 64 output
elements per size against independent CPU FP64 dot products; both sizes have
zero observed error. The power limit remained 450 W. No model, service, clock or
power setting was changed. The desktop and existing resident processes remained
present; initial GPU utilization was 2%, with 11,306 MiB allocated.

| Square size | Median TFLOPS | Sample range | Mean measured power | Maximum temperature |
| --- | ---: | ---: | ---: | ---: |
| 8192 | 142.870 | 142.785–144.107 | 448.39 W | 67 °C |
| 4096 | 132.952 | 129.094–135.402 | 426.17 W | 67 °C |

The 4096 power average has only four telemetry points inside its short timed
windows. Results are current-state measurements, not a 1.9× claim. This run also
uses a different GPU and power limit from the quoted RTX 3090 / 300 W report.

The benchmark ran under peecee's `marker` fleet lease
`a72f83f4-e06c-4c94-91aa-82fe2327a459`, runner revision
`2de20079385e9792910c4c8a26da8913db11107b`, and exited zero. The lease was released.
An initial nested lease attempt could not acquire the Qwen slot and exited 75
before launching any benchmark; the successful invocation used the Marker lease.
The fleet checkout had unrelated pre-existing changes and was not modified.

[Summary and hashes](results/boot1-20261026/summary.json),
[raw measurements](results/boot1-20261026/bf16-unlocked-boot1.json), and
[telemetry](results/boot1-20261026/bf16-unlocked-boot1.telemetry.csv) are retained.
For a measured speedup, cold-boot Windows Boot Manager directly without the USB
unlock, rerun this same script/environment at the same power limit, and compare
matching sizes. A warm restart is not a proven way to clear the unlock.

## Matched locked baseline — 2026-10-26

The owner confirmed a cold boot directly through Windows Boot Manager without
the USB unlock. Windows boot time is `2026-10-26T21:09:22.5000000Z`; the USB still
has only the prior `HLS000000.TXT`, with its previous timestamp and size.
The benchmark source hash, GPU UUID, driver 610.88, PyTorch/CUDA versions, numerical
settings and 450 W power limit match the unlocked run. Initial login activity
settled to the benchmark's 5% utilization threshold before it started.

The identical benchmark completed under Marker lease
`39c5fd84-b600-4398-b440-c9ca50035610`, exited zero and released the lease.
Both sizes again passed all 64 CPU FP64 reference checks with zero error.

| Square size | Locked TFLOPS | Unlocked TFLOPS | Throughput ratio | Gain |
| --- | ---: | ---: | ---: | ---: |
| 8192 | 85.183 | 142.870 | 1.677× | 67.72% |
| 4096 | 72.767 | 132.952 | 1.827× | 82.71% |

This is a substantial gain on this RTX 3090 Ti at 450 W. It does not reproduce
the exact quoted RTX 3090 / 300 W configuration or establish application speedups.
Each state has one boot and five timed samples per size; the desktop and existing
resident services remained running. The locked run began with 11,439 MiB used,
versus 11,306 MiB in the unlocked run.

Available 8192 telemetry averages 447.49 W locked versus 448.39 W unlocked.
The telemetry subprocess ended with a partial CSV row and did not preserve the
last part of the run, including all locked 4096 samples. That incomplete row is
excluded; missing measurements are null, not zero. CUDA timing and numerical
results completed for both sizes. Do not use this trace for an exact energy
comparison or claim a measured locked 4096 power average.

[Comparison and hashes](results/boot2-locked-20261026/comparison.json),
[locked measurements](results/boot2-locked-20261026/bf16-boot2.json), and
[raw partial telemetry](results/boot2-locked-20261026/bf16-boot2.telemetry.csv)
are retained. Full evidence is in
`~/.local/share/infra/evidence/peecee-gpu-unlock-port-20261026/boot2/`.
The remote output is `C:\gpu-unlock-4ecda4a\bf16-boot2.json`.
No further reboot was initiated. The card remains in the locked baseline state.
