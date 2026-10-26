# GPU unlock investigation — peecee

## Read-only USB probe staged 2026-10-26

The owner supplied the USB at E: and authorized preparing the diagnostic probe
for the RTX 3090 Ti. No unlock was staged or attempted; no reboot was initiated.
Hardware captures are pending two owner-operated full-shutdown boots.

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
