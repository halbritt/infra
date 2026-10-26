# GPU unlock investigation — peecee

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
